"""MediaService orchestrating presigned uploads, video protection, and PDF watermarking.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 7, Table 32)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.10)
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md (Sections 1-4)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK401, TASK402, TASK403, TASK404)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-009, ADR-010)

Strict Invariants:
1. Zero App Server Memory Load: Large file uploads execute directly against S3/R2 presigned URLs.
2. Short-Lived Playback Tokens: 2-hour TTL HMAC/JWT playback tokens tied to student identity and IP.
3. Access Authorization: Video playback and protected PDFs require active enrollment or instructor roles.
4. Dynamic Provenance Watermarking: PDFs are stamped dynamically with student identity upon streaming.
"""

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import re
import struct
from typing import Any, Optional, Tuple, Union
import uuid

import jwt
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    ResourceNotFoundException,
    UnauthorizedException,
    ValidationException,
)
from app.core.pdf_watermark import apply_pdf_watermark
from app.core.permissions import MEDIA_VIEW_PROTECTED
from app.core.storage import StorageClient
from app.models.base import utc_now
from app.models.course import (
    COURSE_STATUS_PUBLISHED,
    REVISION_STATUS_PUBLISHED,
    Course,
    CourseRevision,
)
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.enrollment import ENROLLMENT_STATUS_REVOKED
from app.models.media import (
    MAX_VIDEO_SIZE_BYTES,
    MEDIA_STATUS_FAILED,
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
    MEDIA_STATUS_UPLOADED,
    MEDIA_STATUS_UPLOADING,
    MIME_CONFIG,
    MediaAsset,
    validate_media_file,
)
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_SUPER_ADMIN,
    User,
)
from app.models.transcode_job import (
    MediaTranscodeJob,
    TRANSCODE_STATUS_FAILED,
    TRANSCODE_STATUS_PROCESSING,
    TRANSCODE_STATUS_QUEUED,
)
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.media_repo import MediaRepository
from app.repositories.transcode_job_repo import MediaTranscodeJobRepository
from app.schemas.course import slugify
from app.schemas.media import (
    MediaAssetListResponse,
    MediaAssetResponse,
    PlaybackTokenResponse,
    TranscodeJobResponse,
    UploadConfirmRequest,
    UploadIntentRequest,
    UploadIntentResponse,
)
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


_EXTENSIONS_BY_MIME = {
    "application/pdf": {".pdf"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/webp": {".webp"},
    "video/mp4": {".mp4"},
    "video/quicktime": {".mov", ".qt"},
    "video/webm": {".webm"},
    "application/zip": {".zip"},
    "application/x-tar": {".tar"},
    "application/gzip": {".gz", ".gzip"},
}


def _extract_image_dimensions(mime_type: str, data: bytes) -> Optional[Tuple[int, int]]:
    """Decode and validate structural image headers (PNG, JPEG, WebP) without Pillow."""
    if mime_type == "image/png":
        if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b"IHDR":
            return None
        width, height = struct.unpack(">II", data[16:24])
        return (width, height) if 0 < width <= 16384 and 0 < height <= 16384 else None

    if mime_type == "image/jpeg":
        if len(data) < 4 or not data.startswith(b"\xff\xd8"):
            return None
        i = 2
        length = len(data)
        sof_markers = {
            0xC0, 0xC1, 0xC2, 0xC3,
            0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB,
            0xCD, 0xCE, 0xCF,
        }
        while i < length:
            while i < length and data[i] != 0xFF:
                i += 1
            while i < length and data[i] == 0xFF:
                i += 1
            if i >= length:
                break
            marker = data[i]
            i += 1
            if marker in (0xD8, 0xD9, 0x00, 0x01) or (0xD0 <= marker <= 0xD7):
                continue
            if i + 2 > length:
                break
            seg_len = struct.unpack(">H", data[i : i + 2])[0]
            if seg_len < 2 or i + seg_len > length:
                break
            if marker in sof_markers:
                if seg_len < 7:
                    return None
                height, width = struct.unpack(">HH", data[i + 3 : i + 7])
                return (width, height) if 0 < width <= 16384 and 0 < height <= 16384 else None
            i += seg_len
        return None

    if mime_type == "image/webp":
        if len(data) < 21 or not data.startswith(b"RIFF") or data[8:12] != b"WEBP":
            return None
        chunk_type = data[12:16]
        if chunk_type == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            raw_w, raw_h = struct.unpack("<HH", data[26:30])
            width = raw_w & 0x3FFF
            height = raw_h & 0x3FFF
            return (width, height) if 0 < width <= 16384 and 0 < height <= 16384 else None
        if chunk_type == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
            bits = struct.unpack("<I", data[21:25])[0]
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return (width, height) if 0 < width <= 16384 and 0 < height <= 16384 else None
        if chunk_type == b"VP8X" and len(data) >= 30:
            width = int.from_bytes(data[24:27], "little") + 1
            height = int.from_bytes(data[27:30], "little") + 1
            return (width, height) if 0 < width <= 16384 and 0 < height <= 16384 else None
        return None

    return None


def _matches_binary_signature(mime_type: str, prefix: bytes) -> bool:
    """Validate declared type from bounded bytes, never the entire upload."""
    if mime_type == "application/pdf":
        return prefix.startswith(b"%PDF-")
    if mime_type == "image/png":
        return prefix.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/jpeg":
        return prefix.startswith(b"\xff\xd8\xff")
    if mime_type == "image/webp":
        return prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP"
    if mime_type == "video/mp4":
        return len(prefix) >= 12 and prefix[4:8] == b"ftyp"
    if mime_type == "video/quicktime":
        return len(prefix) >= 12 and prefix[4:8] == b"ftyp" and prefix[8:12] == b"qt  "
    if mime_type == "video/webm":
        return prefix.startswith(b"\x1a\x45\xdf\xa3")
    if mime_type == "application/zip":
        return prefix.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
    if mime_type == "application/gzip":
        return prefix.startswith(b"\x1f\x8b")
    if mime_type == "application/x-tar":
        return len(prefix) >= 262 and prefix[257:262] == b"ustar"
    return False


class MediaService:
    """Service layer managing secure media ingestion, playback token issuance, and protected streaming."""

    def __init__(
        self,
        repository: Optional[MediaRepository] = None,
        enrollment_repo: Optional[EnrollmentRepository] = None,
        storage_client: Optional[StorageClient] = None,
        audit_service: Optional[AuditService] = None,
        transcode_job_repo: Optional[MediaTranscodeJobRepository] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.repo = repository or MediaRepository()
        self.enrollment_repo = enrollment_repo or EnrollmentRepository()
        self.storage_client = storage_client or StorageClient(settings=settings)
        self.audit_service = audit_service or AuditService()
        self.transcode_job_repo = transcode_job_repo or MediaTranscodeJobRepository()
        self.settings = settings or get_settings()

    # =========================================================================
    # 1. Presigned Upload Pipeline (TASK401, TASK402)
    # =========================================================================

    async def create_upload_intent(
        self,
        session: Session,
        uploader: User,
        data: UploadIntentRequest,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UploadIntentResponse:
        """Validate file boundaries and generate short-lived S3/R2 presigned PUT upload URL."""
        # 1. Validate MIME and size boundaries
        if "\x00" in data.filename or ".." in data.filename or "/" in data.filename or "\\" in data.filename:
            raise ValidationException(
                message="Filename contains directory separators or path traversal sequences.",
                code="INVALID_FILENAME",
            )
        cfg = validate_media_file(data.mime_type, data.file_size_bytes)
        prefix = cfg["prefix"]

        # 2. Generate clean unique object storage key
        safe_name = slugify(data.filename.rsplit(".", 1)[0]) or "asset"
        ext = data.filename.rsplit(".", 1)[1].lower() if "." in data.filename else ""
        ext_suffix = f".{ext}" if ext else ""
        if ext_suffix not in _EXTENSIONS_BY_MIME[data.mime_type]:
            raise ValidationException(
                message="Filename extension does not match the declared media type.",
                code="FILE_EXTENSION_MISMATCH",
            )
        unique_id = uuid.uuid4()
        file_key = f"{prefix}/{unique_id}/{safe_name}{ext_suffix}"

        # 3. Generate presigned PUT URL (15-min TTL)
        expires_in = self.settings.UPLOAD_INTENT_EXPIRE_MINUTES * 60
        presigned_url, headers = self.storage_client.generate_presigned_upload_url(
            file_key=file_key,
            mime_type=data.mime_type,
            file_size_bytes=data.file_size_bytes,
            expires_in_seconds=expires_in,
        )

        # 4. Insert MediaAsset record with initial UPLOADING status
        asset = self.repo.create_asset(
            session,
            uploader_id=uploader.id,
            filename=data.filename,
            file_key=file_key,
            bucket=self.storage_client.bucket,
            mime_type=data.mime_type,
            file_size_bytes=data.file_size_bytes,
        )

        # 5. Record audit log
        await self.audit_service.record_event(
            session,
            action="MEDIA_UPLOAD_INTENT_CREATED",
            resource_type="media_asset",
            resource_id=str(asset.id),
            actor_id=uploader.id,
            actor_type="USER",
            after_state={
                "id": str(asset.id),
                "filename": asset.filename,
                "file_key": asset.file_key,
                "mime_type": asset.mime_type,
                "file_size_bytes": asset.file_size_bytes,
                "status": asset.status,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return UploadIntentResponse(
            media_id=asset.id,
            file_key=asset.file_key,
            bucket=asset.bucket,
            presigned_url=presigned_url,
            headers=headers,
            expires_in_seconds=expires_in,
        )

    async def confirm_upload(
        self,
        session: Session,
        media_id: uuid.UUID,
        data: UploadConfirmRequest,
        actor: User,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> MediaAssetResponse:
        """Confirm that binary upload completed and trigger processing/transcode."""
        asset = self.repo.get_by_id(session, media_id, for_update=True)
        if asset is None:
            raise ResourceNotFoundException("MediaAsset", str(media_id))

        # 1. Check ownership or admin role
        is_owner = asset.uploader_id == actor.id
        is_elevated = any(r in actor.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF))
        if not (is_owner or is_elevated):
            raise ForbiddenException(
                message="Not authorized to confirm this media asset upload.",
                code="PERMISSION_DENIED",
            )

        # Idempotent check: if already confirmed/processing/ready
        if asset.status in (MEDIA_STATUS_READY, MEDIA_STATUS_PROCESSING):
            return MediaAssetResponse.model_validate(asset)
        if asset.status == MEDIA_STATUS_FAILED:
            raise BadRequestException(
                message="Cannot confirm an asset that has failed.",
                code="INVALID_ASSET_STATUS",
            )

        # 2. Verify upload intent expiration
        age_seconds = (datetime.now(timezone.utc) - asset.created_at).total_seconds()
        ttl_seconds = self.settings.UPLOAD_INTENT_EXPIRE_MINUTES * 60
        if age_seconds > ttl_seconds:
            self.repo.update_status(session, asset, status=MEDIA_STATUS_FAILED)
            raise BadRequestException(
                message="Upload intent has expired.",
                code="UPLOAD_INTENT_EXPIRED",
            )

        # 3. Verify actual object existence in remote/persistent storage (BUG-017)
        storage_meta = self.storage_client.head_object(asset.file_key)
        if not storage_meta or not storage_meta.get("exists"):
            raise BadRequestException(
                message="Uploaded binary object not found in storage.",
                code="OBJECT_NOT_FOUND",
            )

        # 4. Verify the uploaded object is exactly the approved object size.
        actual_size = storage_meta.get("size", 0)
        if actual_size <= 0:
            raise BadRequestException(
                message="Uploaded binary object is empty or invalid.",
                code="INVALID_OBJECT_SIZE",
            )

        if actual_size != asset.file_size_bytes:
            raise BadRequestException(
                message="Uploaded object size does not match its approved upload intent.",
                code="FILE_SIZE_MISMATCH",
            )

        from app.models.media import MIME_CONFIG
        cfg = MIME_CONFIG.get(asset.mime_type)
        if cfg and actual_size > cfg["max_bytes"]:
            raise BadRequestException(
                message=f"Uploaded binary object ({actual_size} bytes) exceeds maximum permitted size ({cfg['max_bytes']} bytes).",
                code="FILE_TOO_LARGE",
            )

        actual_mime = str(storage_meta.get("content_type") or "").split(";", 1)[0].strip().lower()
        if actual_mime != asset.mime_type:
            raise BadRequestException(
                message="Storage content type does not match the approved upload intent.",
                code="MIME_TYPE_MISMATCH",
            )

        # Bounded remote range read: all allowed binary types get signature checks.
        try:
            signature_prefix = self.storage_client.get_object_prefix(asset.file_key, 512)
        except Exception as sig_err:
            logger.warning("Could not verify uploaded file signature: %s", sig_err)
            raise BadRequestException(
                message="Uploaded file signature could not be verified.",
                code="FILE_SIGNATURE_UNVERIFIABLE",
            ) from sig_err
        if not _matches_binary_signature(asset.mime_type, signature_prefix):
            raise BadRequestException(
                message="Uploaded file content does not match its declared media type.",
                code="INVALID_FILE_SIGNATURE",
            )

        before_status = asset.status

        # 5. Video assets transition to truthful PROCESSING state and enqueue transcode job (VM-02)
        if asset.mime_type.startswith("video/"):
            new_status = MEDIA_STATUS_PROCESSING
            job = self.transcode_job_repo.create_job(
                session,
                media_id=asset.id,
                priority=100,
                max_retries=self.settings.TRANSCODE_MAX_RETRIES,
                job_metadata={
                    "file_key": asset.file_key,
                    "filename": asset.filename,
                    "mime_type": asset.mime_type,
                    "file_size_bytes": asset.file_size_bytes,
                    "duration_seconds": data.duration_seconds or 0,
                    "metadata": data.metadata or {},
                },
            )
            transcode_output = {
                "status": "PROCESSING",
                "job_id": str(job.id),
                "duration_seconds": data.duration_seconds or 0,
                "metadata": data.metadata or {},
            }
        else:
            # Images, PDFs, archives transition directly to READY
            image_meta: dict[str, Any] = dict(data.metadata or {})
            if asset.mime_type in {"image/png", "image/jpeg", "image/webp"}:
                try:
                    image_bytes = self.storage_client.get_object(asset.file_key)
                except Exception as img_err:
                    raise BadRequestException(
                        message="Uploaded image file could not be read from storage.",
                        code="IMAGE_UNREADABLE",
                    ) from img_err
                dimensions = _extract_image_dimensions(asset.mime_type, image_bytes)
                if dimensions is None:
                    raise BadRequestException(
                        message="Uploaded image file is corrupted or has invalid image structure.",
                        code="INVALID_IMAGE_CONTENT",
                    )
                image_meta["width"] = dimensions[0]
                image_meta["height"] = dimensions[1]
            new_status = MEDIA_STATUS_READY
            transcode_output = {
                "metadata": image_meta,
            }

        updated = self.repo.update_status(
            session,
            asset,
            status=new_status,
            transcode_output=transcode_output,
        )

        # Record audit log
        await self.audit_service.record_event(
            session,
            action="MEDIA_UPLOAD_CONFIRMED",
            resource_type="media_asset",
            resource_id=str(updated.id),
            actor_id=actor.id,
            actor_type="USER",
            before_state={"status": before_status},
            after_state={"status": updated.status, "transcode_output": updated.transcode_output},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return MediaAssetResponse.model_validate(updated)

    def get_public_image(
        self,
        session: Session,
        media_id: uuid.UUID,
    ) -> Tuple[bytes, str]:
        """Return verified public-images READY asset bytes and safe MIME type."""
        asset = self.repo.get_by_id(session, media_id)
        if asset is None:
            raise ResourceNotFoundException("MediaAsset", str(media_id))

        if (
            not asset.file_key.startswith("public-images/")
            or asset.mime_type not in {"image/png", "image/jpeg", "image/webp"}
        ):
            raise ForbiddenException(
                message="Direct public access is restricted to verified course images.",
                code="PUBLIC_ACCESS_DENIED",
            )

        if asset.status != "READY":
            raise ResourceNotFoundException("MediaAsset", str(media_id))

        try:
            data = self.storage_client.get_object(asset.file_key)
        except KeyError as err:
            raise ResourceNotFoundException("MediaAsset", str(media_id)) from err

        return data, asset.mime_type

    async def complete_video_transcode(
        self,
        session: Session,
        media_id: uuid.UUID,
        *,
        hls_master_url: str,
        resolutions: list[str],
        duration_seconds: int,
        actor: Optional[User] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MediaAssetResponse:
        """Mark video transcoding workflow completed and record authoritative HLS manifest."""
        asset = self.repo.get_by_id(session, media_id, for_update=True)
        if asset is None:
            raise ResourceNotFoundException("MediaAsset", str(media_id))

        before_status = asset.status
        transcode_output = {
            "hls_master_url": hls_master_url,
            "resolutions": resolutions,
            "duration_seconds": duration_seconds,
            "metadata": metadata or {},
        }
        updated = self.repo.update_status(
            session,
            asset,
            status=MEDIA_STATUS_READY,
            transcode_output=transcode_output,
        )

        await self.audit_service.record_event(
            session,
            action="MEDIA_TRANSCODE_COMPLETED",
            resource_type="media_asset",
            resource_id=str(updated.id),
            actor_id=actor.id if actor else None,
            actor_type="USER" if actor else "SYSTEM",
            before_state={"status": before_status},
            after_state={"status": updated.status, "transcode_output": updated.transcode_output},
        )
        return MediaAssetResponse.model_validate(updated)

    def get_transcode_job(
        self,
        session: Session,
        media_id: uuid.UUID,
        user: User,
    ) -> Optional[MediaTranscodeJob]:
        """Fetch the latest transcode job for a media asset with authorization check."""
        asset = self.repo.get_by_id(session, media_id)
        if asset is None:
            raise ResourceNotFoundException("MediaAsset", str(media_id))

        is_owner = asset.uploader_id == user.id
        is_elevated = any(r in user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF))
        if not (is_owner or is_elevated):
            raise ForbiddenException(
                message="Not authorized to inspect this media asset's transcoding status.",
                code="PERMISSION_DENIED",
            )

        return self.transcode_job_repo.get_latest_job_by_media_id(session, media_id)

    async def retry_transcode(
        self,
        session: Session,
        media_id: uuid.UUID,
        actor: User,
    ) -> MediaTranscodeJob:
        """Retry or re-enqueue a failed or stalled transcoding job for a media asset."""
        asset = self.repo.get_by_id(session, media_id, for_update=True)
        if asset is None:
            raise ResourceNotFoundException("MediaAsset", str(media_id))

        is_owner = asset.uploader_id == actor.id
        is_elevated = any(r in actor.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF))
        if not (is_owner or is_elevated):
            raise ForbiddenException(
                message="Not authorized to retry transcoding for this media asset.",
                code="PERMISSION_DENIED",
            )

        if not asset.mime_type.startswith("video/"):
            raise BadRequestException(
                message="Cannot transcode non-video media assets.",
                code="NOT_A_VIDEO",
            )

        if asset.status == MEDIA_STATUS_READY and asset.transcode_output and "hls_master_url" in asset.transcode_output:
            raise BadRequestException(
                message="Media asset is already in READY status with complete HLS streams.",
                code="ALREADY_READY",
            )

        # Reset asset status to PROCESSING
        self.repo.update_status(session, asset, status=MEDIA_STATUS_PROCESSING)

        existing_job = self.transcode_job_repo.get_latest_job_by_media_id(session, media_id)
        if existing_job and existing_job.status in (TRANSCODE_STATUS_FAILED, TRANSCODE_STATUS_PROCESSING):
            existing_job.status = TRANSCODE_STATUS_QUEUED
            existing_job.retry_count = 0
            existing_job.next_retry_at = utc_now()
            existing_job.locked_at = None
            existing_job.locked_by = None
            existing_job.error_message = None
            existing_job.error_details = None
            session.flush()
            job = existing_job
        else:
            job = self.transcode_job_repo.create_job(
                session,
                media_id=asset.id,
                priority=50,
                max_retries=self.settings.TRANSCODE_MAX_RETRIES,
                job_metadata={
                    "file_key": asset.file_key,
                    "filename": asset.filename,
                    "mime_type": asset.mime_type,
                    "file_size_bytes": asset.file_size_bytes,
                },
            )

        await self.audit_service.record_event(
            session,
            action="MEDIA_TRANSCODE_RETRIED",
            resource_type="media_asset",
            resource_id=str(asset.id),
            actor_id=actor.id,
            actor_type="USER",
            metadata={"job_id": str(job.id)},
        )

        return job

    async def delete_media_asset(
        self,
        session: Session,
        media_id: uuid.UUID,
        actor: User,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Delete media asset, remove underlying storage object, and record audit log."""
        asset = self.repo.get_by_id(session, media_id, for_update=True)
        if asset is None:
            raise ResourceNotFoundException("MediaAsset", str(media_id))

        is_owner = asset.uploader_id == actor.id
        is_elevated = any(r in actor.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF))
        if not (is_owner or is_elevated):
            raise ForbiddenException(
                message="Not authorized to delete this media asset.",
                code="PERMISSION_DENIED",
            )

        # Check if asset is attached to curriculum lessons or resources
        import sqlalchemy as sa
        from app.models.curriculum import CurriculumLesson, LessonResource

        # 1. Check curriculum lesson content (video bindings or interactive media)
        asset_id_str = str(asset.id)
        candidate_lessons = session.query(CurriculumLesson).filter(
            CurriculumLesson.content.isnot(None),
            (
                sa.cast(CurriculumLesson.content, sa.String).like(f"%{asset_id_str}%") |
                sa.cast(CurriculumLesson.content, sa.String).like(f"%{asset.file_key}%")
            )
        ).all()
        for cand in candidate_lessons:
            if self._is_asset_attached_to_lesson(session, asset, cand):
                raise BadRequestException(
                    message="Cannot delete a media asset currently attached to curriculum lessons.",
                    code="MEDIA_ASSET_IN_USE",
                )

        # 2. Check curriculum resources (PDFs, downloadable documents, source code)
        attached_res = session.query(LessonResource).filter(
            (LessonResource.file_url == asset.file_key) |
            (LessonResource.file_url.like(f"%{asset.id}%"))
        ).first()
        if attached_res:
            raise BadRequestException(
                message="Cannot delete a media asset currently attached to curriculum resources.",
                code="MEDIA_ASSET_IN_USE",
            )

        # Delete physical object from storage client
        try:
            self.storage_client.delete_object(asset.file_key)
        except Exception as exc:
            logger.warning("Failed to delete object from storage: %s", exc)

        # Record audit log
        await self.audit_service.record_event(
            session,
            action="MEDIA_ASSET_DELETED",
            resource_type="media_asset",
            resource_id=str(asset.id),
            actor_id=actor.id,
            actor_type="USER",
            before_state={
                "id": str(asset.id),
                "filename": asset.filename,
                "file_key": asset.file_key,
                "status": asset.status,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Delete from DB
        self.repo.delete_asset(session, asset)

    def cleanup_expired_intents(
        self,
        session: Session,
        max_age_hours: int = 24,
    ) -> int:
        """Identify and transition abandoned UPLOADING media intents to FAILED status."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        query = session.query(MediaAsset).filter(
            MediaAsset.status == MEDIA_STATUS_UPLOADING,
            MediaAsset.created_at < cutoff,
        )
        expired_assets = query.all()
        count = 0
        for asset in expired_assets:
            asset.status = MEDIA_STATUS_FAILED
            asset.updated_at = utc_now()
            count += 1
        if count > 0:
            session.flush()
        return count

    async def get_media_asset(
        self,
        session: Session,
        media_id: uuid.UUID,
        user: Optional[User] = None,
        lesson_id: Optional[uuid.UUID] = None,
    ) -> MediaAssetResponse:
        """Fetch media asset details with strict authorization (P1-02)."""
        asset = self.repo.get_by_id(session, media_id)
        if asset is None:
            raise ResourceNotFoundException("MediaAsset", str(media_id))

        if user:
            is_owner = asset.uploader_id == user.id
            is_elevated = any(r in user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF))
            if not (is_owner or is_elevated):
                self._check_media_access(session, asset, user, lesson_id=lesson_id)

        return MediaAssetResponse.model_validate(asset)

    async def list_media_assets(
        self,
        session: Session,
        *,
        uploader_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> MediaAssetListResponse:
        """List paginated media assets."""
        items, total = self.repo.list_assets(
            session,
            uploader_id=uploader_id,
            status=status,
            page=page,
            per_page=per_page,
        )
        summaries = [MediaAssetResponse.model_validate(a) for a in items]
        total_pages = (total + per_page - 1) // per_page if total > 0 else 0
        return MediaAssetListResponse(
            items=summaries,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
        )

    # =========================================================================
    # 2. Video Protection & Signed Playback Token Issuance (TASK403)
    # =========================================================================

    def generate_playback_token(
        self,
        session: Session,
        media_id: uuid.UUID,
        user: User,
        *,
        lesson_id: Optional[uuid.UUID] = None,
        course_id: Optional[uuid.UUID] = None,
        client_ip: Optional[str] = None,
    ) -> PlaybackTokenResponse:
        """Issue an HMAC-signed, short-lived (2-hour TTL) HLS streaming playback token."""
        asset = self.repo.get_by_id(session, media_id)
        if asset is None:
            raise ResourceNotFoundException("MediaAsset", str(media_id))

        if not asset.mime_type.startswith("video/"):
            raise BadRequestException(
                message="Target media asset is not a video file.",
                code="NOT_A_VIDEO",
            )

        if asset.status != MEDIA_STATUS_READY:
            raise BadRequestException(
                message=f"Media asset is not ready for streaming (current status: {asset.status}).",
                code="MEDIA_NOT_READY",
            )

        # Access Authorization check
        self._check_media_access(session, asset, user, lesson_id=lesson_id, course_id=course_id)

        now = datetime.now(timezone.utc)
        ttl_minutes = self.settings.PLAYBACK_TOKEN_EXPIRE_MINUTES
        ttl_seconds = ttl_minutes * 60
        expires_at = now + timedelta(minutes=ttl_minutes)

        token_payload = {
            "sub": str(user.id),
            "media_id": str(media_id),
            "lesson_id": str(lesson_id) if lesson_id else None,
            "course_id": str(course_id) if course_id else None,
            "ip": client_ip,
            "token_type": "playback",
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": str(uuid.uuid4()),
        }

        signed_token = jwt.encode(
            token_payload,
            self.settings.SECRET_KEY.get_secret_value(),
            algorithm=self.settings.ALGORITHM,
        )

        stream_url = f"{self.settings.CDN_STREAM_BASE_URL}/hls/{media_id}/master.m3u8?token={signed_token}"

        # Record audit log
        try:
            self.audit_service.record_sync_event(
                session,
                action="PLAYBACK_TOKEN_ISSUED",
                resource_type="media_asset",
                resource_id=str(asset.id),
                actor_id=user.id,
                actor_type="USER",
                metadata={
                    "lesson_id": str(lesson_id) if lesson_id else None,
                    "course_id": str(course_id) if course_id else None,
                    "client_ip": client_ip,
                    "ttl_seconds": ttl_seconds,
                },
                ip_address=client_ip,
            )
        except Exception as audit_err:
            logger.warning("Could not record PLAYBACK_TOKEN_ISSUED audit event: %s", audit_err)

        return PlaybackTokenResponse(
            media_id=asset.id,
            playback_token=signed_token,
            stream_url=stream_url,
            expires_at=expires_at,
            ttl_seconds=ttl_seconds,
        )

    def stream_hls_resource(
        self,
        session: Session,
        media_id: uuid.UUID,
        file_path: str,
        *,
        token: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> Tuple[bytes, str, dict[str, str]]:
        """Stream an authorized HLS resource (master playlist, variant playlist, or video segment).

        Requirements (VM-03 D1-D4):
        1. Token is strictly verified (valid signature, unexpired, matching media_id, matching IP).
        2. Media asset must be in READY state and be a video.
        3. File path is strictly checked against directory traversal (no .., no null bytes, extension whitelist).
        4. Playlists (.m3u8) are dynamically rewritten to append token to all child playlist/segment lines.
        5. Segments (.ts, .m4s) are streamed with appropriate binary headers and no-store caching.
        """
        if not token:
            raise UnauthorizedException(
                message="Video playback token is required to stream protected HLS assets.",
                code="MISSING_TOKEN",
            )

        # 1. Verify token cryptographic integrity, expiration, and media binding
        self.verify_playback_token(token, media_id, client_ip=client_ip)

        # 2. Verify media asset exists, is video, and is READY
        asset = self.repo.get_by_id(session, media_id)
        if asset is None:
            raise ResourceNotFoundException("MediaAsset", str(media_id))

        if not asset.mime_type.startswith("video/"):
            raise BadRequestException(
                message="Target media asset is not a video file.",
                code="NOT_A_VIDEO",
            )

        if asset.status != MEDIA_STATUS_READY:
            raise BadRequestException(
                message=f"Media asset is not ready for streaming (current status: {asset.status}).",
                code="MEDIA_NOT_READY",
            )

        if not asset.transcode_output or not isinstance(asset.transcode_output, dict):
            raise BadRequestException(
                message="Media asset has no transcoded HLS output.",
                code="HLS_OUTPUT_MISSING",
            )

        # 3. Path sanitization and traversal prevention
        clean_path = file_path.strip().lstrip("/")
        if not clean_path or ".." in clean_path or "\x00" in clean_path or "\\" in clean_path:
            raise BadRequestException(
                message="Invalid HLS resource path.",
                code="INVALID_HLS_PATH",
            )

        # Extension whitelist: only .m3u8, .ts, .m4s permitted
        ext = Path(clean_path).suffix.lower()
        if ext not in (".m3u8", ".ts", ".m4s"):
            raise BadRequestException(
                message="Requested resource is not a valid HLS asset.",
                code="INVALID_HLS_EXTENSION",
            )

        # 4. Fetch binary asset from storage
        storage_key = f"media/{asset.id}/hls/{clean_path}"
        try:
            raw_bytes = self.storage_client.get_object(storage_key)
        except KeyError:
            raise ResourceNotFoundException("HlsResource", f"{asset.id}/{clean_path}")

        # 5. Process playlists or segments
        if ext == ".m3u8":
            content_type = "application/vnd.apple.mpegurl"
            try:
                playlist_text = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                playlist_text = raw_bytes.decode("latin-1")

            # Rewrite relative URI lines to propagate authorization token
            rewritten_lines = []
            for line in playlist_text.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    delimiter = "&" if "?" in stripped else "?"
                    rewritten_lines.append(f"{stripped}{delimiter}token={token}")
                else:
                    rewritten_lines.append(line)

            output_bytes = "\n".join(rewritten_lines).encode("utf-8")
        elif ext == ".ts":
            content_type = "video/MP2T"
            output_bytes = raw_bytes
        else:
            content_type = "video/iso.segment"
            output_bytes = raw_bytes

        headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(output_bytes)),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
        }

        return output_bytes, content_type, headers

    def verify_playback_token(
        self,
        token: str,
        media_id: uuid.UUID,
        client_ip: Optional[str] = None,
    ) -> dict[str, Any]:
        """Verify that playback token is valid, unexpired, and matches target media.

        Raises:
            UnauthorizedException: If token is expired, tampered, or mismatched.
        """
        try:
            payload = jwt.decode(
                token,
                self.settings.SECRET_KEY.get_secret_value(),
                algorithms=[self.settings.ALGORITHM],
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.ExpiredSignatureError:
            raise UnauthorizedException(
                message="Video playback token has expired. Please refresh.",
                code="PLAYBACK_TOKEN_EXPIRED",
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedException(
                message="Invalid video playback token signature.",
                code="INVALID_PLAYBACK_TOKEN",
            ) from exc

        if payload.get("token_type") != "playback":
            raise UnauthorizedException(
                message="Invalid token claims: expected playback token.",
                code="INVALID_TOKEN_TYPE",
            )

        if payload.get("media_id") != str(media_id):
            raise UnauthorizedException(
                message="Playback token does not match target media asset.",
                code="TOKEN_MEDIA_MISMATCH",
            )

        token_ip = payload.get("ip")
        if token_ip and client_ip and token_ip != client_ip:
            raise UnauthorizedException(
                message="Playback token client IP mismatch.",
                code="TOKEN_IP_MISMATCH",
            )

        return payload

    # =========================================================================
    # 3. Dynamic PDF Watermarking Engine (TASK404)
    # =========================================================================

    def get_watermarked_pdf(
        self,
        session: Session,
        media_id: uuid.UUID,
        user: User,
        *,
        lesson_id: Optional[uuid.UUID] = None,
    ) -> Tuple[bytes, str]:
        """Retrieve protected PDF and dynamically stamp learner provenance watermark."""
        asset = self.repo.get_by_id(session, media_id)
        if asset is None:
            raise ResourceNotFoundException("MediaAsset", str(media_id))

        if asset.mime_type != "application/pdf":
            raise BadRequestException(
                message="Target media asset is not a PDF document.",
                code="NOT_A_PDF",
            )

        if asset.status != MEDIA_STATUS_READY:
            raise BadRequestException(
                message=f"Media asset is not ready for viewing (current status: {asset.status}).",
                code="MEDIA_NOT_READY",
            )

        # Verify access authorization
        self._check_media_access(session, asset, user, lesson_id=lesson_id)

        raw_bytes = self.storage_client.get_object(asset.file_key)
        watermarked_bytes = apply_pdf_watermark(
            raw_bytes,
            student_name=user.full_name,
            student_email=user.email,
            student_id=str(user.id),
        )

        try:
            self.audit_service.record_sync_event(
                session,
                action="PROTECTED_PDF_ACCESSED",
                resource_type="media_asset",
                resource_id=str(asset.id),
                actor_id=user.id,
                actor_type="USER",
                metadata={
                    "lesson_id": str(lesson_id) if lesson_id else None,
                    "filename": asset.filename,
                },
            )
        except Exception as audit_err:
            logger.warning("Could not record PROTECTED_PDF_ACCESSED audit event: %s", audit_err)

        return watermarked_bytes, asset.filename

    # =========================================================================
    # Helpers & Access Control
    # =========================================================================

    def _is_asset_attached_to_lesson(
        self,
        session: Session,
        asset: MediaAsset,
        lesson: CurriculumLesson,
    ) -> bool:
        """Check if a MediaAsset is canonically attached to a CurriculumLesson (P0-02).

        Strictly requires exact UUID or exact file_key binding:
        1. Lesson content dictionary: exact match on 'media_asset_id', 'media_id', 'video_id', or 'asset_id'.
        2. Lesson resources: exact match on resource file_key, exact resource URL pointing to /api/v1/media/{asset_id}, or exact asset UUID.

        Arbitrary string substring matches and filename/title similarities are strictly rejected.
        """
        asset_id_str = str(asset.id)

        # 1. Check lesson content (videos, interactive assets)
        if lesson.content and isinstance(lesson.content, dict):
            for key in ("media_asset_id", "media_id", "video_id", "asset_id"):
                raw_val = lesson.content.get(key)
                if raw_val and str(raw_val).strip() == asset_id_str:
                    return True
            content_file_key = lesson.content.get("file_key")
            if content_file_key and str(content_file_key).strip() == asset.file_key:
                return True

        # 2. Check lesson resources (PDFs, downloadable documents, source code)
        from app.models.curriculum import LessonResource
        resources = session.query(LessonResource).filter(LessonResource.lesson_id == lesson.id).all()
        for res in resources:
            target_url = (res.file_url or "").strip()
            # Exact match on file key or asset UUID
            if target_url in (asset.file_key, asset_id_str):
                return True
            # Canonical API endpoint prefix match (e.g., /api/v1/media/<UUID>)
            for prefix in ("/api/v1/media/", "api/v1/media/", "/media/", "media/"):
                if target_url.startswith(prefix):
                    extracted_id = target_url[len(prefix):].split("?")[0].strip("/")
                    if extracted_id == asset_id_str:
                        return True
            # URL path ending with exact asset UUID
            if target_url.rstrip("/").rsplit("/", 1)[-1] == asset_id_str:
                return True

        return False

    def _record_access_denied(
        self,
        session: Session,
        asset: MediaAsset,
        user: User,
        reason: str,
        lesson_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Record an immutable audit log for denied media access attempts."""
        try:
            self.audit_service.record_sync_event(
                session,
                action="MEDIA_ACCESS_DENIED",
                resource_type="media_asset",
                resource_id=str(asset.id),
                actor_id=user.id,
                actor_type="USER",
                metadata={
                    "reason": reason,
                    "lesson_id": str(lesson_id) if lesson_id else None,
                },
            )
        except Exception as audit_err:
            logger.warning("Could not record MEDIA_ACCESS_DENIED audit event: %s", audit_err)

    def _check_media_access(
        self,
        session: Session,
        asset: MediaAsset,
        user: User,
        lesson_id: Optional[uuid.UUID] = None,
        course_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Verify caller is authorized to access protected media asset (Fail-Closed BUG-002, VM-03).

        Access Granted if:
        1. Caller account is active AND:
        2. Caller has elevated role (SUPER_ADMIN, ADMIN, STAFF) or media:view_protected permission.
        3. For students:
           a. lesson_id context is strictly required.
           b. The asset is genuinely attached to the specified lesson.
           c. If lesson is an authorized preview (is_preview=True), course revision must be published.
           d. If course_id is provided, lesson must belong to that exact course.
           e. Parent course must be published.
           f. Otherwise, active, unexpired, unrevoked course enrollment is strictly required.
        """
        # 0. Validate account status (suspended users are always denied)
        if not user.is_active:
            self._record_access_denied(session, asset, user, "ACCOUNT_SUSPENDED", lesson_id)
            raise ForbiddenException(
                message="User account has been suspended.",
                code="ACCOUNT_SUSPENDED",
            )

        # 1. Staff and Admins always have access
        is_elevated = any(r in user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF))
        if is_elevated:
            return

        # 2. Student requests strictly require lesson context
        if not lesson_id:
            self._record_access_denied(session, asset, user, "LESSON_CONTEXT_REQUIRED", lesson_id)
            raise ForbiddenException(
                message="Lesson context is required to access protected media.",
                code="LESSON_CONTEXT_REQUIRED",
            )

        lesson = session.get(CurriculumLesson, lesson_id)
        if lesson is None:
            raise ResourceNotFoundException("CurriculumLesson", str(lesson_id))

        # 3. Verify asset is genuinely attached to the specified lesson
        if not self._is_asset_attached_to_lesson(session, asset, lesson):
            self._record_access_denied(session, asset, user, "MEDIA_NOT_ATTACHED_TO_LESSON", lesson_id)
            raise ForbiddenException(
                message="The requested media asset is not attached to this lesson.",
                code="MEDIA_NOT_ATTACHED_TO_LESSON",
            )

        # 4. Preview lesson access (only for its own attached media on live published course)
        if lesson.is_preview:
            parent_info = (
                session.query(
                    CourseRevision.id,
                    CourseRevision.status,
                    Course.status,
                    Course.live_revision_id,
                )
                .join(CurriculumSection, CurriculumSection.course_revision_id == CourseRevision.id)
                .join(Course, Course.id == CourseRevision.course_id)
                .filter(CurriculumSection.id == lesson.section_id)
                .first()
            )
            if parent_info:
                rev_id, rev_status, course_status, live_rev_id = parent_info
                if (
                    course_status == COURSE_STATUS_PUBLISHED
                    and rev_status == REVISION_STATUS_PUBLISHED
                    and live_rev_id == rev_id
                ):
                    return

            self._record_access_denied(session, asset, user, "PREVIEW_NOT_PUBLISHED", lesson_id)
            raise ForbiddenException(
                message="Preview media is only available for published courses.",
                code="PREVIEW_NOT_PUBLISHED",
            )

        # 5. Non-preview content requires verified active enrollment in parent course
        parent_course_id = (
            session.query(CourseRevision.course_id)
            .join(CurriculumSection, CurriculumSection.course_revision_id == CourseRevision.id)
            .filter(CurriculumSection.id == lesson.section_id)
            .scalar()
        )
        if not parent_course_id:
            self._record_access_denied(session, asset, user, "INVALID_LESSON_STRUCTURE", lesson_id)
            raise ForbiddenException(
                message="Lesson does not belong to a valid course revision.",
                code="INVALID_LESSON_STRUCTURE",
            )

        # Verify lesson belongs to requested course if course_id is provided
        if course_id and str(parent_course_id) != str(course_id):
            self._record_access_denied(session, asset, user, "COURSE_LESSON_MISMATCH", lesson_id)
            raise ForbiddenException(
                message="Lesson does not belong to the requested course.",
                code="COURSE_LESSON_MISMATCH",
            )

        # Verify parent course is published
        parent_course = session.get(Course, parent_course_id)
        if not parent_course or parent_course.status != COURSE_STATUS_PUBLISHED:
            self._record_access_denied(session, asset, user, "COURSE_NOT_PUBLISHED", lesson_id)
            raise ForbiddenException(
                message="Target course is not published.",
                code="COURSE_NOT_PUBLISHED",
            )

        enrollment = self.enrollment_repo.get_by_student_and_course(session, user.id, parent_course_id)
        if not enrollment:
            self._record_access_denied(session, asset, user, "ENROLLMENT_REQUIRED", lesson_id)
            raise ForbiddenException(
                message="Active enrollment required to access protected media.",
                code="ENROLLMENT_REQUIRED",
            )
        if enrollment.status == ENROLLMENT_STATUS_REVOKED:
            self._record_access_denied(session, asset, user, "ENROLLMENT_REVOKED", lesson_id)
            raise ForbiddenException(
                message="Course enrollment has been revoked.",
                code="ENROLLMENT_REVOKED",
            )
        if not enrollment.is_access_valid:
            self._record_access_denied(session, asset, user, "ENROLLMENT_EXPIRED", lesson_id)
            raise ForbiddenException(
                message="Course enrollment has expired.",
                code="ENROLLMENT_EXPIRED",
            )
