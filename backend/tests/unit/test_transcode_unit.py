"""Unit tests for VM-02 Video Transcoding Infrastructure (FFmpeg + HLS).

Verifies:
1. FFmpeg & ffprobe detection and version extraction.
2. ffprobe metadata parsing, validation of invalid/corrupted files, no-video rejection.
3. Aspect ratio preservation and strict NO-UPSCALING profile derivation.
4. Portrait and landscape dimension bounding.
5. Sub-480p low-resolution custom profile derivation.
6. HLS playlist and segment structural validation.
7. MediaTranscodeJob database model, state transitions, and exponential backoff retry math.
8. MediaTranscodeJobRepository claiming with row locking, stale job recovery, and deduplication.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import ValidationException
from app.models.base import Base, utc_now
from app.models.media import (
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
    MEDIA_STATUS_UPLOADING,
    MediaAsset,
)
from app.models.transcode_job import (
    ERROR_CATEGORY_CORRUPT_MEDIA,
    ERROR_CATEGORY_FFMPEG_CRASH,
    ERROR_CATEGORY_FFMPEG_TIMEOUT,
    ERROR_CATEGORY_PROBE_FAILED,
    TRANSCODE_STATUS_COMPLETED,
    TRANSCODE_STATUS_FAILED,
    TRANSCODE_STATUS_PROCESSING,
    TRANSCODE_STATUS_QUEUED,
    MediaTranscodeJob,
)
from app.models.user import ROLE_ADMIN, Role, User, UserRole
from app.repositories.transcode_job_repo import MediaTranscodeJobRepository
from app.services.ffmpeg_service import (
    FFmpegNotFoundError,
    FFmpegService,
    HlsValidationResult,
    STANDARD_PROFILES,
    VideoProbeResult,
    VideoProfile,
)


@pytest.fixture
def db_session():
    """Provides isolated in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def ffmpeg_service():
    """FFmpegService instance."""
    return FFmpegService()


@pytest.fixture
def transcode_repo():
    """MediaTranscodeJobRepository instance."""
    return MediaTranscodeJobRepository()


@pytest.fixture
def dummy_media_asset(db_session: Session) -> MediaAsset:
    """Creates a baseline MediaAsset."""
    user = User(
        email="instructor@lms.local",
        full_name="Instructor",
        password_hash="dummyhash",
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    asset = MediaAsset(
        uploader_id=user.id,
        filename="lecture_video.mp4",
        file_key="raw-videos/test-id/lecture.mp4",
        bucket="lms-media",
        mime_type="video/mp4",
        file_size_bytes=10_000_000,
        status=MEDIA_STATUS_PROCESSING,
    )
    db_session.add(asset)
    db_session.commit()
    return asset


# =============================================================================
# 1. FFmpeg & ffprobe Detection & Version Diagnostics
# =============================================================================

def test_ffmpeg_detection_and_version(ffmpeg_service: FFmpegService):
    """FFmpeg service detects binary availability and extracts version line."""
    assert ffmpeg_service.is_ffmpeg_available is True
    version = ffmpeg_service.get_ffmpeg_version()
    assert version is not None
    assert "ffmpeg version" in version.lower()


def test_ffprobe_detection_and_version(ffmpeg_service: FFmpegService):
    """FFprobe service detects binary availability and extracts version line."""
    assert ffmpeg_service.is_ffprobe_available is True
    version = ffmpeg_service.get_ffprobe_version()
    assert version is not None
    assert "ffprobe version" in version.lower()


def test_ffmpeg_service_custom_paths():
    """FFmpeg service respects explicit custom binary paths."""
    from app.core.config import Settings
    custom_settings = Settings(
        FFMPEG_PATH="/nonexistent/ffmpeg",
        FFPROBE_PATH="/nonexistent/ffprobe",
    )
    svc = FFmpegService(settings=custom_settings)
    assert svc.is_ffmpeg_available is False
    assert svc.is_ffprobe_available is False


# =============================================================================
# 2. Source Video Validation & Probing
# =============================================================================

def test_probe_nonexistent_file(ffmpeg_service: FFmpegService):
    """Probing nonexistent file raises ValidationException with FILE_NOT_FOUND."""
    with pytest.raises(ValidationException) as exc_info:
        ffmpeg_service.probe_video(Path("/tmp/nonexistent_video_file_123.mp4"))
    assert exc_info.value.code == "FILE_NOT_FOUND"


def test_probe_corrupt_text_file(ffmpeg_service: FFmpegService, tmp_path: Path):
    """Probing non-video file raises ValidationException with INVALID_MEDIA_SOURCE."""
    fake_video = tmp_path / "corrupt.mp4"
    fake_video.write_text("This is definitely not a video file.")

    with pytest.raises(ValidationException) as exc_info:
        ffmpeg_service.probe_video(fake_video)
    assert exc_info.value.code in ("INVALID_MEDIA_SOURCE", "NO_VIDEO_STREAM")


# =============================================================================
# 3. Profile Derivation & Strict NO-UPSCALING Invariant
# =============================================================================

def test_profile_derivation_1080p_landscape(ffmpeg_service: FFmpegService):
    """1080p source video yields 1080p, 720p, and 480p profiles."""
    probe = VideoProbeResult(
        width=1920,
        height=1080,
        duration_seconds=60.0,
        video_codec="h264",
        audio_codec="aac",
        frame_rate=30.0,
        bitrate=4500000,
        has_audio=True,
        container_format="mov,mp4",
        file_size_bytes=30_000_000,
        is_portrait=False,
        aspect_ratio="16:9",
    )
    profiles = ffmpeg_service.derive_transcode_profiles(probe)
    profile_names = [p.name for p in profiles]
    assert profile_names == ["1080p", "720p", "480p"]
    assert profiles[0].width == 1920 and profiles[0].height == 1080
    assert profiles[1].width == 1280 and profiles[1].height == 720
    assert profiles[2].width == 854 and profiles[2].height == 480


def test_profile_derivation_720p_source_no_upscaling(ffmpeg_service: FFmpegService):
    """720p source video derives 720p and 480p; NEVER upscales to 1080p."""
    probe = VideoProbeResult(
        width=1280,
        height=720,
        duration_seconds=30.0,
        video_codec="h264",
        audio_codec="aac",
        frame_rate=30.0,
        bitrate=2500000,
        has_audio=True,
        container_format="mov,mp4",
        file_size_bytes=10_000_000,
        is_portrait=False,
        aspect_ratio="16:9",
    )
    profiles = ffmpeg_service.derive_transcode_profiles(probe)
    profile_names = [p.name for p in profiles]
    assert "1080p" not in profile_names
    assert profile_names == ["720p", "480p"]


def test_profile_derivation_portrait_1080x1920(ffmpeg_service: FFmpegService):
    """Portrait video (1080x1920) derives portrait bounding boxes preserving aspect ratio."""
    probe = VideoProbeResult(
        width=1080,
        height=1920,
        duration_seconds=15.0,
        video_codec="h264",
        audio_codec=None,
        frame_rate=30.0,
        bitrate=3000000,
        has_audio=False,
        container_format="mov,mp4",
        file_size_bytes=5_000_000,
        is_portrait=True,
        aspect_ratio="9:16",
    )
    profiles = ffmpeg_service.derive_transcode_profiles(probe)
    profile_names = [p.name for p in profiles]
    assert profile_names == ["1080p", "720p", "480p"]
    # Portrait widths and heights are flipped relative to landscape standard
    assert profiles[0].width == 1080 and profiles[0].height == 1920
    assert profiles[1].width == 720 and profiles[1].height == 1280
    assert profiles[2].width == 480 and profiles[2].height == 854


def test_profile_derivation_sub_480p_fallback(ffmpeg_service: FFmpegService):
    """Sub-480p low-resolution video (e.g. 640x360) generates capped single profile without upscaling."""
    probe = VideoProbeResult(
        width=640,
        height=360,
        duration_seconds=20.0,
        video_codec="h264",
        audio_codec="aac",
        frame_rate=24.0,
        bitrate=800000,
        has_audio=True,
        container_format="mov,mp4",
        file_size_bytes=2_000_000,
        is_portrait=False,
        aspect_ratio="16:9",
    )
    profiles = ffmpeg_service.derive_transcode_profiles(probe)
    assert len(profiles) == 1
    # Bounded to source dimensions
    assert profiles[0].width <= 640
    assert profiles[0].height <= 360
    assert profiles[0].width % 2 == 0
    assert profiles[0].height % 2 == 0


# =============================================================================
# 4. HLS Output Structural Validation
# =============================================================================

def test_validate_hls_output_success(ffmpeg_service: FFmpegService, tmp_path: Path):
    """Valid master, variant playlists, and non-empty segments pass validation."""
    p_dir = tmp_path / "720p"
    seg_dir = p_dir / "segments"
    seg_dir.mkdir(parents=True)

    # Write segment
    (seg_dir / "segment_000.ts").write_bytes(b"G" * 188)  # Valid TS packet size

    # Write variant playlist
    variant_m3u8 = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-TARGETDURATION:6\n"
        "#EXTINF:6.000000,\n"
        "segments/segment_000.ts\n"
        "#EXT-X-ENDLIST\n"
    )
    (p_dir / "playlist.m3u8").write_text(variant_m3u8)

    # Write master playlist
    master_m3u8 = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1280x720,CODECS="avc1.4d401f,mp4a.40.2"\n'
        "720p/playlist.m3u8\n"
    )
    (tmp_path / "master.m3u8").write_text(master_m3u8)

    profile = STANDARD_PROFILES[1]  # 720p
    result = ffmpeg_service.validate_hls_output(tmp_path, [profile])

    assert result.is_valid is True
    assert result.total_segments == 1
    assert len(result.errors) == 0


def test_validate_hls_output_missing_master(ffmpeg_service: FFmpegService, tmp_path: Path):
    """Missing master.m3u8 fails validation."""
    result = ffmpeg_service.validate_hls_output(tmp_path, STANDARD_PROFILES[:1])
    assert result.is_valid is False
    assert any("master.m3u8 not found" in e for e in result.errors)


def test_validate_hls_output_missing_segment(ffmpeg_service: FFmpegService, tmp_path: Path):
    """Referenced segment not present on disk fails validation."""
    p_dir = tmp_path / "720p"
    p_dir.mkdir(parents=True)

    variant_m3u8 = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-TARGETDURATION:6\n"
        "#EXTINF:6.000000,\n"
        "segments/missing_segment.ts\n"
        "#EXT-X-ENDLIST\n"
    )
    (p_dir / "playlist.m3u8").write_text(variant_m3u8)

    master_m3u8 = (
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1280x720\n"
        "720p/playlist.m3u8\n"
    )
    (tmp_path / "master.m3u8").write_text(master_m3u8)

    result = ffmpeg_service.validate_hls_output(tmp_path, [STANDARD_PROFILES[1]])
    assert result.is_valid is False
    assert any("does not exist" in e for e in result.errors)


# =============================================================================
# 5. MediaTranscodeJob Lifecycle & Repository Logic
# =============================================================================

def test_create_transcode_job_idempotent(
    db_session: Session,
    transcode_repo: MediaTranscodeJobRepository,
    dummy_media_asset: MediaAsset,
):
    """Creating a transcode job is idempotent; repeated calls return the existing active job."""
    job1 = transcode_repo.create_job(
        db_session,
        media_id=dummy_media_asset.id,
        priority=100,
        max_retries=3,
    )
    db_session.commit()

    assert job1.id is not None
    assert job1.status == TRANSCODE_STATUS_QUEUED
    assert job1.media_id == dummy_media_asset.id
    assert job1.retry_count == 0

    # Repeat call
    job2 = transcode_repo.create_job(
        db_session,
        media_id=dummy_media_asset.id,
        priority=50,
    )
    assert job1.id == job2.id


def test_claim_pending_jobs(
    db_session: Session,
    transcode_repo: MediaTranscodeJobRepository,
    dummy_media_asset: MediaAsset,
):
    """Claiming pending jobs transitions status to PROCESSING and locks the job."""
    job = transcode_repo.create_job(db_session, media_id=dummy_media_asset.id)
    db_session.commit()

    claimed = transcode_repo.claim_pending_jobs(db_session, batch_size=5, worker_id="worker_test_1")
    assert len(claimed) == 1
    assert claimed[0].id == job.id
    assert claimed[0].status == TRANSCODE_STATUS_PROCESSING
    assert claimed[0].locked_by == "worker_test_1"
    assert claimed[0].locked_at is not None

    # Subsequent claim returns empty because job is now in PROCESSING
    claimed2 = transcode_repo.claim_pending_jobs(db_session, batch_size=5, worker_id="worker_test_2")
    assert len(claimed2) == 0


def test_mark_failed_exponential_backoff(
    db_session: Session,
    transcode_repo: MediaTranscodeJobRepository,
    dummy_media_asset: MediaAsset,
):
    """Failed retryable job increments retry_count and calculates exponential backoff."""
    job = transcode_repo.create_job(db_session, media_id=dummy_media_asset.id, max_retries=3)
    db_session.commit()

    before = utc_now()
    # Retry 1
    settled = transcode_repo.mark_failed(
        db_session,
        job.id,
        error_message="FFmpeg timeout",
        error_details={"category": ERROR_CATEGORY_FFMPEG_TIMEOUT},
        is_retryable=True,
        base_backoff_seconds=30,
    )
    db_session.commit()

    assert settled.status == TRANSCODE_STATUS_QUEUED
    assert settled.retry_count == 1
    # 30 * 2^0 = 30 seconds
    assert settled.next_retry_at >= before + timedelta(seconds=29)

    # Retry 2
    settled2 = transcode_repo.mark_failed(
        db_session,
        job.id,
        error_message="FFmpeg timeout #2",
        is_retryable=True,
        base_backoff_seconds=30,
    )
    db_session.commit()
    assert settled2.status == TRANSCODE_STATUS_QUEUED
    assert settled2.retry_count == 2
    # 30 * 2^1 = 60 seconds
    assert settled2.next_retry_at >= before + timedelta(seconds=58)

    # Retry 3 -> Max retries reached -> FAILED
    settled3 = transcode_repo.mark_failed(
        db_session,
        job.id,
        error_message="FFmpeg timeout #3",
        is_retryable=True,
    )
    db_session.commit()
    assert settled3.status == TRANSCODE_STATUS_FAILED
    assert settled3.retry_count == 3
    assert settled3.completed_at is not None


def test_recover_stale_processing_jobs(
    db_session: Session,
    transcode_repo: MediaTranscodeJobRepository,
    dummy_media_asset: MediaAsset,
):
    """Stale PROCESSING jobs past the threshold are recovered back to QUEUED."""
    job = transcode_repo.create_job(db_session, media_id=dummy_media_asset.id)
    job.status = TRANSCODE_STATUS_PROCESSING
    job.locked_at = utc_now() - timedelta(minutes=15)
    job.locked_by = "dead_worker"
    db_session.commit()

    recovered_count = transcode_repo.recover_stale_processing_jobs(
        db_session,
        stale_threshold_seconds=600,
    )
    db_session.commit()

    assert recovered_count == 1
    refreshed = transcode_repo.get_by_id(db_session, job.id)
    assert refreshed.status == TRANSCODE_STATUS_QUEUED
    assert refreshed.locked_by is None
    assert refreshed.locked_at is None
    assert refreshed.retry_count == 1
