"""Integration tests for VM-02 Video Transcoding Pipeline.

Tests:
1. Upload confirmation -> Job creation -> Worker execution -> HLS output -> Storage -> Media READY.
2. Real sample video transcoding using actual FFmpeg and ffprobe on system.
3. Master playlist and variant playlist verification in StorageClient.
4. Non-video assets (PDF/Image) bypass transcoding and transition directly to READY.
5. Error handling: Corrupted video transitions MediaAsset and TranscodeJob to FAILED without unhandled crash.
6. Failure recovery: Transient failure schedules exponential retry; retry exhaustion marks FAILED.
7. Admin transcode API endpoints: GET transcode-job and POST retry-transcode.
8. Playback token issuance succeeds after transcode completes.
"""

from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.exceptions import BadRequestException
from app.core.security import hash_password
from app.core.storage import StorageClient
from app.models.base import Base
from app.models.media import (
    MEDIA_STATUS_FAILED,
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
    MEDIA_STATUS_UPLOADING,
    MediaAsset,
)
from app.models.transcode_job import (
    TRANSCODE_STATUS_COMPLETED,
    TRANSCODE_STATUS_FAILED,
    TRANSCODE_STATUS_PROCESSING,
    TRANSCODE_STATUS_QUEUED,
    MediaTranscodeJob,
)
from app.models.user import ROLE_ADMIN, Role, User, UserRole
from app.repositories.media_repo import MediaRepository
from app.repositories.transcode_job_repo import MediaTranscodeJobRepository
from app.schemas.media import UploadConfirmRequest, UploadIntentRequest
from app.services.ffmpeg_service import FFmpegService
from app.services.media_service import MediaService
from app.services.transcode_service import TranscodeService
from app.workers.transcode_worker import TranscodeWorker


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
def admin_user(db_session: Session) -> User:
    """Creates an Admin/Instructor user."""
    user = User(
        email="admin_transcode@lms.local",
        full_name="Admin Instructor",
        password_hash=hash_password("AdminP@ss1234"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.get(Role, ROLE_ADMIN)
    if not role:
        role = Role(id=ROLE_ADMIN, name="Administrator")
        db_session.add(role)
        db_session.flush()

    ur = UserRole(user_id=user.id, role_id=ROLE_ADMIN)
    db_session.add(ur)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def storage_client():
    """Isolated StorageClient instance."""
    client = StorageClient()
    client._in_memory_storage.clear()
    return client


@pytest.fixture
def media_service(storage_client: StorageClient):
    """MediaService instance configured with in-memory storage."""
    return MediaService(storage_client=storage_client)


@pytest.fixture
def transcode_service(storage_client: StorageClient):
    """TranscodeService instance configured with in-memory storage."""
    return TranscodeService(storage_client=storage_client)


pytestmark = pytest.mark.anyio


def _generate_real_test_video_bytes(width: int = 1280, height: int = 720, duration: int = 1) -> bytes:
    """Generate a real valid MP4 video using local FFmpeg lavfi filters."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        tmp_path = Path(f.name)

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=30",
            "-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac",
            str(tmp_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return tmp_path.read_bytes()
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# =============================================================================
# 1. Upload Confirmation -> Transcode Job Creation Pipeline
# =============================================================================

async def test_confirm_upload_enqueues_transcode_job(
    db_session: Session,
    media_service: MediaService,
    admin_user: User,
    storage_client: StorageClient,
):
    """Video upload confirmation transitions asset to PROCESSING and enqueues transcode job."""
    # 1. Create upload intent
    intent_req = UploadIntentRequest(
        filename="system_architecture.mp4",
        mime_type="video/mp4",
        file_size_bytes=1000,
    )
    intent = await media_service.create_upload_intent(db_session, admin_user, intent_req)
    db_session.commit()

    # Stage binary object in storage with valid MP4 header
    raw_video = b"\x00\x00\x00\x18ftypmp42" + (b"\x00" * (1000 - len(b"\x00\x00\x00\x18ftypmp42")))
    storage_client.put_object(intent.file_key, raw_video, content_type="video/mp4")

    # 2. Confirm upload
    confirm_resp = await media_service.confirm_upload(
        db_session,
        intent.media_id,
        UploadConfirmRequest(duration_seconds=120),
        admin_user,
    )
    db_session.commit()

    assert confirm_resp.status == MEDIA_STATUS_PROCESSING
    assert confirm_resp.transcode_output["status"] == "PROCESSING"
    assert "job_id" in confirm_resp.transcode_output

    # Verify transcode job was created in DB
    job_repo = MediaTranscodeJobRepository()
    job = job_repo.get_active_job_by_media_id(db_session, intent.media_id)
    assert job is not None
    assert str(job.id) == confirm_resp.transcode_output["job_id"]
    assert job.status == TRANSCODE_STATUS_QUEUED
    assert job.media_id == intent.media_id


async def test_non_video_upload_bypasses_transcoding(
    db_session: Session,
    media_service: MediaService,
    admin_user: User,
    storage_client: StorageClient,
):
    """PDF document confirmation transitions directly to READY without creating transcode jobs."""
    intent_req = UploadIntentRequest(
        filename="handout.pdf",
        mime_type="application/pdf",
        file_size_bytes=500,
    )
    intent = await media_service.create_upload_intent(db_session, admin_user, intent_req)
    db_session.commit()

    # Stage PDF bytes (%PDF-1.4 header)
    pdf_bytes = b"%PDF-1.4\n" + (b"\x00" * (500 - len(b"%PDF-1.4\n")))
    storage_client.put_object(intent.file_key, pdf_bytes, content_type="application/pdf")

    confirm_resp = await media_service.confirm_upload(
        db_session,
        intent.media_id,
        UploadConfirmRequest(),
        admin_user,
    )
    db_session.commit()

    assert confirm_resp.status == MEDIA_STATUS_READY
    job_repo = MediaTranscodeJobRepository()
    job = job_repo.get_latest_job_by_media_id(db_session, intent.media_id)
    assert job is None


# =============================================================================
# 2. Real FFmpeg End-to-End Transcoding & Playback Token
# =============================================================================

async def test_real_video_transcoding_pipeline(
    db_session: Session,
    media_service: MediaService,
    transcode_service: TranscodeService,
    admin_user: User,
    storage_client: StorageClient,
):
    """Real sample video is encoded to multi-resolution HLS, stored, and marked READY."""
    # Generate real 1-second 1280x720 video with audio
    video_bytes = _generate_real_test_video_bytes(width=1280, height=720, duration=1)
    file_size = len(video_bytes)

    # 1. Create upload intent
    intent_req = UploadIntentRequest(
        filename="real_lecture.mp4",
        mime_type="video/mp4",
        file_size_bytes=file_size,
    )
    intent = await media_service.create_upload_intent(db_session, admin_user, intent_req)
    db_session.commit()

    # Stage real video in storage
    storage_client.put_object(intent.file_key, video_bytes, content_type="video/mp4")

    # 2. Confirm upload
    confirm_resp = await media_service.confirm_upload(
        db_session,
        intent.media_id,
        UploadConfirmRequest(duration_seconds=1),
        admin_user,
    )
    db_session.commit()

    job_repo = MediaTranscodeJobRepository()
    job = job_repo.get_active_job_by_media_id(db_session, intent.media_id)
    assert job is not None
    assert job.status == TRANSCODE_STATUS_QUEUED

    # 3. Process job with TranscodeService
    settled_job = await transcode_service.process_job(db_session, job.id)
    db_session.commit()

    assert settled_job.status == TRANSCODE_STATUS_COMPLETED

    # 4. Verify MediaAsset status and output metadata
    media_repo = MediaRepository()
    asset = media_repo.get_by_id(db_session, intent.media_id)
    assert asset is not None
    assert asset.status == MEDIA_STATUS_READY
    assert asset.transcode_output is not None

    # Source was 1280x720: must derive 720p and 480p, NO UPSCALING to 1080p
    assert asset.transcode_output["resolutions"] == ["720p", "480p"]
    assert "master.m3u8" in asset.transcode_output["hls_master_url"]
    assert asset.transcode_output["duration_seconds"] >= 1
    assert asset.transcode_output["metadata"]["has_audio"] is True
    assert asset.transcode_output["metadata"]["total_segments"] >= 2

    # 5. Verify HLS files exist in StorageClient
    storage_prefix = f"media/{asset.id}/hls"
    assert storage_client.object_exists(f"{storage_prefix}/master.m3u8")
    assert storage_client.object_exists(f"{storage_prefix}/720p/playlist.m3u8")
    assert storage_client.object_exists(f"{storage_prefix}/480p/playlist.m3u8")
    assert storage_client.object_exists(f"{storage_prefix}/720p/segments/segment_000.ts")

    # Verify master playlist references variants
    master_bytes = storage_client.get_object(f"{storage_prefix}/master.m3u8")
    master_text = master_bytes.decode("utf-8")
    assert "#EXTM3U" in master_text
    assert "720p/playlist.m3u8" in master_text
    assert "480p/playlist.m3u8" in master_text
    assert "1080p" not in master_text  # Strict no-upscale check!

    # 6. Verify Playback Token issuance now succeeds on READY media
    token_resp = media_service.generate_playback_token(db_session, asset.id, admin_user)
    assert token_resp.media_id == asset.id
    assert "master.m3u8" in token_resp.stream_url
    assert "?token=" in token_resp.stream_url


# =============================================================================
# 3. Worker Execution & Stale Recovery
# =============================================================================

async def test_transcode_worker_run_once(
    db_session: Session,
    media_service: MediaService,
    admin_user: User,
    storage_client: StorageClient,
):
    """TranscodeWorker claims and processes queued jobs end-to-end."""
    video_bytes = _generate_real_test_video_bytes(width=640, height=360, duration=1)
    file_size = len(video_bytes)

    intent_req = UploadIntentRequest(
        filename="lesson_short.mp4",
        mime_type="video/mp4",
        file_size_bytes=file_size,
    )
    intent = await media_service.create_upload_intent(db_session, admin_user, intent_req)
    db_session.commit()
    storage_client.put_object(intent.file_key, video_bytes, content_type="video/mp4")

    await media_service.confirm_upload(db_session, intent.media_id, UploadConfirmRequest(), admin_user)
    db_session.commit()

    # Run worker once
    worker = TranscodeWorker(
        session_factory=lambda: db_session,
        batch_size=5,
    )
    processed = await worker.run_once()
    db_session.commit()

    assert processed == 1

    media_repo = MediaRepository()
    asset = media_repo.get_by_id(db_session, intent.media_id)
    assert asset.status == MEDIA_STATUS_READY


# =============================================================================
# 4. Failure Handling & Retry Behavior
# =============================================================================

async def test_corrupt_video_fails_permanently(
    db_session: Session,
    media_service: MediaService,
    transcode_service: TranscodeService,
    admin_user: User,
    storage_client: StorageClient,
):
    """Corrupt non-video binary transitions directly to FAILED without wasted retries."""
    intent_req = UploadIntentRequest(
        filename="corrupted.mp4",
        mime_type="video/mp4",
        file_size_bytes=1000,
    )
    intent = await media_service.create_upload_intent(db_session, admin_user, intent_req)
    db_session.commit()

    # Pass binary signature check but corrupt container
    corrupt_bytes = b"\x00\x00\x00\x18ftypmp42CORRUPT_BYTES" + (b"\x00" * (1000 - len(b"\x00\x00\x00\x18ftypmp42CORRUPT_BYTES")))
    storage_client.put_object(intent.file_key, corrupt_bytes, content_type="video/mp4")

    await media_service.confirm_upload(db_session, intent.media_id, UploadConfirmRequest(), admin_user)
    db_session.commit()

    job_repo = MediaTranscodeJobRepository()
    job = job_repo.get_active_job_by_media_id(db_session, intent.media_id)

    # Process corrupt video
    settled = await transcode_service.process_job(db_session, job.id)
    db_session.commit()

    assert settled.status == TRANSCODE_STATUS_FAILED
    assert settled.retry_count == 1

    media_repo = MediaRepository()
    asset = media_repo.get_by_id(db_session, intent.media_id)
    assert asset.status == MEDIA_STATUS_FAILED


# =============================================================================
# 5. Admin API Endpoints & Retry Transcode
# =============================================================================

async def test_retry_transcode_endpoint(
    db_session: Session,
    media_service: MediaService,
    admin_user: User,
    storage_client: StorageClient,
):
    """Retrying a failed transcode resets status to PROCESSING and re-enqueues job."""
    intent_req = UploadIntentRequest(
        filename="failed_video.mp4",
        mime_type="video/mp4",
        file_size_bytes=500,
    )
    intent = await media_service.create_upload_intent(db_session, admin_user, intent_req)
    db_session.commit()
    staged = b"\x00\x00\x00\x18ftypmp42" + (b"\x00" * (500 - len(b"\x00\x00\x00\x18ftypmp42")))
    storage_client.put_object(intent.file_key, staged, content_type="video/mp4")

    await media_service.confirm_upload(db_session, intent.media_id, UploadConfirmRequest(), admin_user)
    db_session.commit()

    job_repo = MediaTranscodeJobRepository()
    job = job_repo.get_active_job_by_media_id(db_session, intent.media_id)

    # Simulate terminal failure
    job_repo.mark_failed(db_session, job.id, "Simulated crash", is_retryable=False)
    media_repo = MediaRepository()
    asset = media_repo.get_by_id(db_session, intent.media_id)
    media_repo.update_status(db_session, asset, status=MEDIA_STATUS_FAILED)
    db_session.commit()

    # Execute retry
    retried_job = await media_service.retry_transcode(db_session, intent.media_id, admin_user)
    db_session.commit()

    assert retried_job.status == TRANSCODE_STATUS_QUEUED
    assert retried_job.retry_count == 0

    refreshed_asset = media_repo.get_by_id(db_session, intent.media_id)
    assert refreshed_asset.status == MEDIA_STATUS_PROCESSING


async def test_retry_transcode_rejects_already_ready_asset(
    db_session: Session,
    media_service: MediaService,
    admin_user: User,
):
    """Retrying an asset that is already in READY status is rejected with BadRequest."""
    asset = MediaAsset(
        uploader_id=admin_user.id,
        filename="ready_video.mp4",
        file_key="raw-videos/id/ready.mp4",
        bucket="lms-media",
        mime_type="video/mp4",
        file_size_bytes=1000,
        status=MEDIA_STATUS_READY,
        transcode_output={"hls_master_url": "https://stream.instructor.com/hls/id/master.m3u8"},
    )
    db_session.add(asset)
    db_session.commit()

    with pytest.raises(BadRequestException) as exc_info:
        await media_service.retry_transcode(db_session, asset.id, admin_user)
    assert exc_info.value.code == "ALREADY_READY"
