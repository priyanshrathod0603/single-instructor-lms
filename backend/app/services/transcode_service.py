"""Transcoding orchestration service coordinating FFmpeg processing, storage, and job status.

Architecture Specifications:
- VM-02: Video Transcoding Infrastructure (FFmpeg + HLS)
- docs/backend/04-DATABASE-ARCHITECTURE.md
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md

Strict Invariants:
1. Atomic Verification: Media is marked READY only after all HLS playlists and segments are verified and uploaded.
2. Isolated Working Directory: Each transcoding job runs in a dedicated temporary directory cleaned up on exit.
3. Diagnostic Persistence: Full operational failure details (exit code, category, stderr) recorded in job record.
4. Non-Destructive Storage: Original uploaded binaries are never deleted or modified during transcoding.
5. Idempotent Completion: Completed assets with existing READY status are never downgraded.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Optional, Union
import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationException
from app.core.storage import StorageClient
from app.models.media import (
    MEDIA_STATUS_FAILED,
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
    MediaAsset,
)
from app.models.transcode_job import (
    ERROR_CATEGORY_CORRUPT_MEDIA,
    ERROR_CATEGORY_DISK_EXHAUSTED,
    ERROR_CATEGORY_FFMPEG_CRASH,
    ERROR_CATEGORY_FFMPEG_TIMEOUT,
    ERROR_CATEGORY_PROBE_FAILED,
    ERROR_CATEGORY_STORAGE_FAILED,
    ERROR_CATEGORY_UNKNOWN,
    ERROR_CATEGORY_VALIDATION_FAILED,
    TRANSCODE_STATUS_COMPLETED,
    TRANSCODE_STATUS_FAILED,
    TRANSCODE_STATUS_PROCESSING,
    TRANSCODE_STATUS_QUEUED,
    MediaTranscodeJob,
)
from app.repositories.media_repo import MediaRepository
from app.repositories.transcode_job_repo import MediaTranscodeJobRepository
from app.services.audit_service import AuditService
from app.services.ffmpeg_service import (
    FFmpegError,
    FFmpegExecutionError,
    FFmpegNotFoundError,
    FFmpegService,
    FFmpegTimeoutError,
    HlsValidationResult,
    VideoProbeResult,
)

logger = logging.getLogger(__name__)


class TranscodeService:
    """Orchestrates video probing, multi-resolution HLS encoding, storage upload, and state settlement."""

    def __init__(
        self,
        job_repo: Optional[MediaTranscodeJobRepository] = None,
        media_repo: Optional[MediaRepository] = None,
        storage_client: Optional[StorageClient] = None,
        ffmpeg_service: Optional[FFmpegService] = None,
        audit_service: Optional[AuditService] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.job_repo = job_repo or MediaTranscodeJobRepository()
        self.media_repo = media_repo or MediaRepository()
        self.storage_client = storage_client or StorageClient(settings=self.settings)
        self.ffmpeg_service = ffmpeg_service or FFmpegService(settings=self.settings)
        self.audit_service = audit_service or AuditService()

    async def process_job(
        self,
        session: Session,
        job_id: Union[uuid.UUID, str],
    ) -> MediaTranscodeJob:
        """Execute the end-to-end transcoding pipeline for a claimed job.

        Args:
            session: SQLAlchemy DB session.
            job_id: Transcode job ID.

        Returns:
            Settled MediaTranscodeJob.
        """
        job = self.job_repo.get_by_id(session, job_id, for_update=True)
        if not job:
            raise ValueError(f"Transcode job {job_id} not found.")

        # Guard against duplicate execution of completed jobs
        if job.status == TRANSCODE_STATUS_COMPLETED:
            logger.info("TranscodeJob %s already completed; skipping.", job.id)
            return job

        asset = self.media_repo.get_by_id(session, job.media_id, for_update=True)
        if not asset:
            err_msg = f"Associated MediaAsset {job.media_id} not found."
            self.job_repo.mark_failed(
                session,
                job.id,
                error_message=err_msg,
                error_details={"category": ERROR_CATEGORY_PROBE_FAILED},
                is_retryable=False,
            )
            return job

        # Guard against reprocessing assets that are already READY
        if asset.status == MEDIA_STATUS_READY and asset.transcode_output and "hls_master_url" in asset.transcode_output:
            logger.info("MediaAsset %s already READY; completing job %s.", asset.id, job.id)
            self.job_repo.mark_completed(
                session,
                job.id,
                job_metadata={"note": "MediaAsset already marked READY with valid stream."},
            )
            return job

        # Ensure asset reflects truthful PROCESSING status
        if asset.status != MEDIA_STATUS_PROCESSING:
            self.media_repo.update_status(session, asset, status=MEDIA_STATUS_PROCESSING)

        start_time = time.monotonic()
        temp_dir_str = tempfile.mkdtemp(prefix=f"lms_transcode_{job.id}_")
        work_dir = Path(temp_dir_str)

        try:
            # 1. Download source video from storage
            source_filename = Path(asset.filename).name or "source.mp4"
            local_source = work_dir / f"source_{source_filename}"

            logger.info("Downloading media %s (key: %s) to %s", asset.id, asset.file_key, local_source)
            try:
                self.storage_client.download_file(asset.file_key, local_source)
            except Exception as e:
                raise StorageError(f"Failed to download source video from storage: {e}") from e

            # 2. Probe video metadata with ffprobe
            logger.info("Probing media %s with ffprobe", asset.id)
            try:
                probe_result = self.ffmpeg_service.probe_video(local_source)
            except ValidationException as e:
                # Corrupt or non-video: non-retryable
                logger.error("Media probing failed for %s: %s", asset.id, e.message)
                self.media_repo.update_status(session, asset, status=MEDIA_STATUS_FAILED)
                self.job_repo.mark_failed(
                    session,
                    job.id,
                    error_message=e.message,
                    error_details={"category": ERROR_CATEGORY_CORRUPT_MEDIA, "details": e.details},
                    is_retryable=False,
                )
                return job

            # 3. Derive target adaptive profiles (ensuring NO UPSCALING)
            profiles = self.ffmpeg_service.derive_transcode_profiles(probe_result)
            logger.info(
                "Derived %d transcoding profile(s) for %s (%dx%d): %s",
                len(profiles),
                asset.id,
                probe_result.width,
                probe_result.height,
                [p.name for p in profiles],
            )

            # 4. Transcode to multi-resolution HLS
            hls_output_dir = work_dir / "hls"
            transcode_diag = self.ffmpeg_service.transcode_to_hls(
                input_path=local_source,
                output_dir=hls_output_dir,
                profiles=profiles,
                has_audio=probe_result.has_audio,
                segment_duration=self.settings.TRANSCODE_SEGMENT_DURATION_SECONDS,
                timeout_seconds=self.settings.TRANSCODE_TIMEOUT_SECONDS,
            )

            # 5. Strictly validate generated HLS playlists and media segments
            validation: HlsValidationResult = self.ffmpeg_service.validate_hls_output(hls_output_dir, profiles)
            if not validation.is_valid:
                err_text = f"HLS validation failed: {'; '.join(validation.errors)}"
                logger.error("Job %s validation error: %s", job.id, err_text)
                raise FFmpegError(err_text)

            logger.info(
                "Validated HLS output for job %s: %d total segments across %d profiles",
                job.id,
                validation.total_segments,
                len(profiles),
            )

            # 6. Upload master playlist, variant playlists, and segments to storage
            storage_hls_prefix = f"media/{asset.id}/hls"
            logger.info("Uploading HLS output for media %s to storage prefix %s", asset.id, storage_hls_prefix)
            try:
                uploaded_keys = self.storage_client.upload_directory(hls_output_dir, storage_hls_prefix)
            except Exception as e:
                raise StorageError(f"Failed to upload HLS assets to storage: {e}") from e

            # 7. Settle MediaAsset to READY with authoritative transcode_output
            duration_secs = int(round(probe_result.duration_seconds))
            cdn_base = self.settings.CDN_STREAM_BASE_URL.rstrip("/")
            hls_master_url = f"{cdn_base}/{storage_hls_prefix}/master.m3u8"
            resolutions = [p.name for p in profiles]

            metadata_payload = {
                "width": probe_result.width,
                "height": probe_result.height,
                "duration_seconds": duration_secs,
                "video_codec": probe_result.video_codec,
                "audio_codec": probe_result.audio_codec,
                "frame_rate": probe_result.frame_rate,
                "bitrate": probe_result.bitrate,
                "has_audio": probe_result.has_audio,
                "aspect_ratio": probe_result.aspect_ratio,
                "total_segments": validation.total_segments,
                "profiles": [
                    {"name": p.name, "width": p.width, "height": p.height, "bandwidth_bps": p.bandwidth_bps}
                    for p in profiles
                ],
                "transcode_duration_seconds": round(time.monotonic() - start_time, 2),
                "job_id": str(job.id),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

            self.media_repo.update_status(
                session,
                asset,
                status=MEDIA_STATUS_READY,
                transcode_output={
                    "hls_master_url": hls_master_url,
                    "resolutions": resolutions,
                    "duration_seconds": duration_secs,
                    "metadata": metadata_payload,
                },
            )

            # 8. Mark TranscodeJob as COMPLETED
            job_meta = {
                "probe": {
                    "width": probe_result.width,
                    "height": probe_result.height,
                    "duration": duration_secs,
                    "has_audio": probe_result.has_audio,
                },
                "profiles": resolutions,
                "hls_master_url": hls_master_url,
                "total_segments": validation.total_segments,
                "uploaded_files_count": len(uploaded_keys),
                "duration_seconds": round(time.monotonic() - start_time, 2),
                "ffmpeg_version": self.ffmpeg_service.get_ffmpeg_version(),
            }
            self.job_repo.mark_completed(session, job.id, job_metadata=job_meta)

            # Record audit event
            await self.audit_service.record_event(
                session,
                action="MEDIA_TRANSCODE_COMPLETED",
                resource_type="media_asset",
                resource_id=str(asset.id),
                actor_id=None,
                actor_type="SYSTEM",
                before_state={"status": MEDIA_STATUS_PROCESSING},
                after_state={"status": MEDIA_STATUS_READY, "transcode_output": asset.transcode_output},
                metadata={"job_id": str(job.id), "duration_seconds": job_meta["duration_seconds"]},
            )

            logger.info("TranscodeJob %s for MediaAsset %s COMPLETED successfully in %.2fs", job.id, asset.id, job_meta["duration_seconds"])
            return job

        except FFmpegTimeoutError as e:
            logger.error("TranscodeJob %s timed out: %s", job.id, e)
            self._handle_failure(session, job, asset, str(e), ERROR_CATEGORY_FFMPEG_TIMEOUT, is_retryable=True)
            return job

        except FFmpegExecutionError as e:
            logger.error("TranscodeJob %s FFmpeg crash: %s", job.id, e)
            self._handle_failure(
                session,
                job,
                asset,
                str(e),
                ERROR_CATEGORY_FFMPEG_CRASH,
                is_retryable=True,
                extra={"exit_code": e.returncode, "stderr_tail": e.stderr[-1000:] if e.stderr else ""},
            )
            return job

        except StorageError as e:
            logger.error("TranscodeJob %s storage failure: %s", job.id, e)
            self._handle_failure(session, job, asset, str(e), ERROR_CATEGORY_STORAGE_FAILED, is_retryable=True)
            return job

        except Exception as e:
            logger.exception("TranscodeJob %s unhandled exception: %s", job.id, e)
            self._handle_failure(session, job, asset, str(e), ERROR_CATEGORY_UNKNOWN, is_retryable=True)
            return job

        finally:
            # Clean up temporary disk files
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception as clean_err:
                logger.warning("Failed to remove temp transcode directory %s: %s", work_dir, clean_err)

    def _handle_failure(
        self,
        session: Session,
        job: MediaTranscodeJob,
        asset: MediaAsset,
        error_message: str,
        category: str,
        is_retryable: bool = True,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        """Handle failure settlement, exponential retry scheduling, and media state degradation if terminal."""
        details = {"category": category}
        if extra:
            details.update(extra)

        settled = self.job_repo.mark_failed(
            session,
            job.id,
            error_message=error_message,
            error_details=details,
            is_retryable=is_retryable,
            base_backoff_seconds=30,
        )

        # If job has permanently failed (max retries exhausted), mark MediaAsset as FAILED
        if settled and settled.status == TRANSCODE_STATUS_FAILED:
            self.media_repo.update_status(
                session,
                asset,
                status=MEDIA_STATUS_FAILED,
                transcode_output={"error": error_message, "category": category, "failed_at": datetime.now(timezone.utc).isoformat()},
            )
            logger.error("MediaAsset %s transitioned to FAILED following job %s exhaustion.", asset.id, job.id)


class StorageError(Exception):
    """Raised when an object storage operation fails during transcoding."""
    pass
