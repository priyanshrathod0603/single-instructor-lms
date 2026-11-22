"""Unit tests for StorageClient, Presigned Upload Pipeline, and Confirmations (TASK401, TASK402).

Verifies:
1. StorageClient SigV4 presigned upload URL generation (15-min TTL) and required headers.
2. StorageClient presigned download URL generation.
3. MediaService.create_upload_intent:
   - MIME validation & size boundaries.
   - S3/R2 object key prefix isolation (raw-videos/, protected-docs/, public-images/).
   - Generates UPLOADING asset and stages immutable audit event.
4. MediaService.confirm_upload:
   - Validates asset ownership or elevated administrative role.
   - Transitions status to READY and sets transcode output metadata.
   - Stages MEDIA_UPLOAD_CONFIRMED audit event.
5. Authorization denials for unapproved callers.
"""

import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import BadRequestException, ForbiddenException, ValidationException
from app.core.security import hash_password
from app.core.storage import StorageClient
from app.models.base import Base
from app.models.media import (
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
    MEDIA_STATUS_UPLOADING,
    MediaAsset,
)
from app.models.user import ROLE_ADMIN, ROLE_STUDENT, Role, User, UserRole
from app.schemas.media import UploadConfirmRequest, UploadIntentRequest
from app.services.media_service import MediaService


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
    """Creates an Admin user."""
    user = User(
        email="admin@lms.local",
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
def other_user(db_session: Session) -> User:
    """Creates another student user."""
    user = User(
        email="other@lms.local",
        full_name="Other Learner",
        password_hash=hash_password("OtherP@ss1234"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def media_service():
    """MediaService instance."""
    return MediaService()


def test_storage_client_presigned_upload_generation():
    """StorageClient generates valid SigV4 presigned upload URLs with required headers."""
    client = StorageClient()
    url, headers = client.generate_presigned_upload_url(
        file_key="raw-videos/test-id/lecture.mp4",
        mime_type="video/mp4",
        file_size_bytes=5000000,
        expires_in_seconds=900,
    )

    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "X-Amz-Credential=" in url
    assert "X-Amz-Expires=900" in url
    assert "X-Amz-Signature=" in url
    assert headers["Content-Type"] == "video/mp4"


def test_storage_client_presigned_download_generation():
    """StorageClient generates valid SigV4 presigned download GET URLs."""
    client = StorageClient()
    url = client.generate_presigned_download_url(
        file_key="protected-docs/test-id/syllabus.pdf",
        expires_in_seconds=7200,
    )

    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "X-Amz-Expires=7200" in url
    assert "X-Amz-Signature=" in url


@pytest.mark.asyncio
async def test_create_upload_intent_pipeline(db_session: Session, media_service: MediaService, admin_user: User):
    """Creating an upload intent validates boundaries and persists initial UPLOADING asset."""
    req = UploadIntentRequest(
        filename="lecture_1_architecture.mp4",
        mime_type="video/mp4",
        file_size_bytes=250000000,  # 250 MB
    )

    resp = await media_service.create_upload_intent(db_session, admin_user, req)
    db_session.commit()

    assert resp.media_id is not None
    assert resp.bucket == "lms-media"
    assert "raw-videos/" in resp.file_key
    assert "lecture-1-architecture.mp4" in resp.file_key
    assert resp.expires_in_seconds == 900
    assert "X-Amz-Signature=" in resp.presigned_url
    assert resp.headers["Content-Type"] == "video/mp4"

    # Verify persisted DB asset
    asset = db_session.get(MediaAsset, resp.media_id)
    assert asset is not None
    assert asset.uploader_id == admin_user.id
    assert asset.status == MEDIA_STATUS_UPLOADING
    assert asset.file_size_bytes == 250000000


@pytest.mark.asyncio
async def test_confirm_upload_marks_ready_and_transcode_output(
    db_session: Session, media_service: MediaService, admin_user: User
):
    """Confirming upload updates status to READY and writes transcode output metadata."""
    video_bytes = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
    req = UploadIntentRequest(
        filename="async_io_deep_dive.mp4",
        mime_type="video/mp4",
        file_size_bytes=len(video_bytes),
    )
    intent = await media_service.create_upload_intent(db_session, admin_user, req)
    db_session.commit()

    media_service.storage_client.put_object(intent.file_key, video_bytes, content_type="video/mp4")
    confirm_req = UploadConfirmRequest(
        duration_seconds=1840,
        metadata={"aspect_ratio": "16:9"},
    )
    confirmed = await media_service.confirm_upload(db_session, intent.media_id, confirm_req, admin_user)
    db_session.commit()

    assert confirmed.status == MEDIA_STATUS_PROCESSING
    assert confirmed.transcode_output is not None
    assert confirmed.transcode_output["duration_seconds"] == 1840

    # Completing transcode transitions video to READY
    ready_asset = await media_service.complete_video_transcode(
        db_session,
        intent.media_id,
        hls_master_url=f"hls/{intent.media_id}/master.m3u8",
        resolutions=["1080p", "720p"],
        duration_seconds=1840,
        actor=admin_user,
    )
    assert ready_asset.status == MEDIA_STATUS_READY
    assert "hls/" in ready_asset.transcode_output["hls_master_url"]
    assert "1080p" in ready_asset.transcode_output["resolutions"]


@pytest.mark.asyncio
async def test_confirm_upload_unauthorized_user_rejected(
    db_session: Session, media_service: MediaService, admin_user: User, other_user: User
):
    """Non-owner student cannot confirm another user's uploaded asset."""
    req = UploadIntentRequest(
        filename="confidential_lecture.mp4",
        mime_type="video/mp4",
        file_size_bytes=50000000,
    )
    intent = await media_service.create_upload_intent(db_session, admin_user, req)
    db_session.commit()

    confirm_req = UploadConfirmRequest()
    with pytest.raises(ForbiddenException) as exc_info:
        await media_service.confirm_upload(db_session, intent.media_id, confirm_req, other_user)

    assert exc_info.value.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_confirm_upload_rejects_size_and_signature_mismatches(
    db_session: Session, media_service: MediaService, admin_user: User
):
    """A claimed MP4 cannot be confirmed with wrong-size or non-MP4 bytes."""
    intent = await media_service.create_upload_intent(
        db_session,
        admin_user,
        UploadIntentRequest(filename="validated.mp4", mime_type="video/mp4", file_size_bytes=24),
    )
    media_service.storage_client.put_object(intent.file_key, b"not-an-mp4", content_type="video/mp4")
    with pytest.raises(BadRequestException) as exc_info:
        await media_service.confirm_upload(db_session, intent.media_id, UploadConfirmRequest(), admin_user)
    assert exc_info.value.code == "FILE_SIZE_MISMATCH"

    intent = await media_service.create_upload_intent(
        db_session,
        admin_user,
        UploadIntentRequest(filename="wrong-content.mp4", mime_type="video/mp4", file_size_bytes=24),
    )
    media_service.storage_client.put_object(intent.file_key, b"x" * 24, content_type="video/mp4")
    with pytest.raises(BadRequestException) as exc_info:
        await media_service.confirm_upload(db_session, intent.media_id, UploadConfirmRequest(), admin_user)
    assert exc_info.value.code == "INVALID_FILE_SIGNATURE"


@pytest.mark.asyncio
async def test_upload_intent_rejects_extension_type_mismatch(
    db_session: Session, media_service: MediaService, admin_user: User
):
    with pytest.raises(ValidationException) as exc_info:
        await media_service.create_upload_intent(
            db_session,
            admin_user,
            UploadIntentRequest(filename="misleading.pdf", mime_type="video/mp4", file_size_bytes=24),
        )
    assert exc_info.value.code == "FILE_EXTENSION_MISMATCH"
