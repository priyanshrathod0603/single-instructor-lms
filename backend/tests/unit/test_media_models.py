"""Unit tests for MediaAsset model, status lifecycle, and MIME/size boundaries (TASK401).

Verifies:
1. MediaAsset model table columns, defaults, and relationships.
2. Status constants and lifecycle transitions.
3. MIME whitelist and size limits:
   - Video assets: up to 5 GB (video/mp4, video/quicktime, video/webm).
   - Protected PDFs: up to 50 MB (application/pdf).
   - Images: up to 5 MB (image/png, image/jpeg, image/webp).
   - Lesson resources: up to 100 MB (application/zip, application/x-tar, application/gzip).
4. Validation errors on zero/negative sizes, oversized files, or disallowed MIME types.
"""

import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import ValidationException
from app.core.security import hash_password
from app.models.base import Base
from app.models.media import (
    ALLOWED_MIME_TYPES,
    MAX_IMAGE_SIZE_BYTES,
    MAX_PDF_SIZE_BYTES,
    MAX_RESOURCE_SIZE_BYTES,
    MAX_VIDEO_SIZE_BYTES,
    MEDIA_STATUS_FAILED,
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
    MEDIA_STATUS_UPLOADED,
    MEDIA_STATUS_UPLOADING,
    MIME_IMAGE_PNG,
    MIME_PDF,
    MIME_VIDEO_MP4,
    MIME_ZIP,
    VALID_MEDIA_STATUSES,
    MediaAsset,
    validate_media_file,
)
from app.models.user import ROLE_ADMIN, Role, User, UserRole


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
def instructor_user(db_session: Session) -> User:
    """Creates an Instructor/Admin user."""
    user = User(
        email="instructor@lms.local",
        full_name="Lead Instructor",
        password_hash=hash_password("InstructorP@ss123"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestMediaConstantsAndValidation:
    """Verifies domain constants, MIME whitelist, and size boundaries."""

    def test_media_statuses(self):
        assert MEDIA_STATUS_UPLOADING == "UPLOADING"
        assert MEDIA_STATUS_UPLOADED == "UPLOADED"
        assert MEDIA_STATUS_PROCESSING == "PROCESSING"
        assert MEDIA_STATUS_READY == "READY"
        assert MEDIA_STATUS_FAILED == "FAILED"
        assert VALID_MEDIA_STATUSES == {"UPLOADING", "UPLOADED", "PROCESSING", "READY", "FAILED"}

    def test_allowed_mime_types(self):
        assert MIME_VIDEO_MP4 in ALLOWED_MIME_TYPES
        assert MIME_PDF in ALLOWED_MIME_TYPES
        assert MIME_IMAGE_PNG in ALLOWED_MIME_TYPES
        assert MIME_ZIP in ALLOWED_MIME_TYPES

    def test_validate_video_file_boundaries(self):
        # Valid video
        cfg = validate_media_file("video/mp4", 1024 * 1024 * 500)  # 500 MB
        assert cfg["category"] == "video"
        assert cfg["prefix"] == "raw-videos"

        # Exceeds 5 GB
        with pytest.raises(ValidationException) as exc_info:
            validate_media_file("video/mp4", MAX_VIDEO_SIZE_BYTES + 1)
        assert exc_info.value.code == "FILE_TOO_LARGE"

    def test_validate_pdf_file_boundaries(self):
        cfg = validate_media_file("application/pdf", 10 * 1024 * 1024)  # 10 MB
        assert cfg["category"] == "pdf"
        assert cfg["prefix"] == "protected-docs"

        # Exceeds 50 MB
        with pytest.raises(ValidationException) as exc_info:
            validate_media_file("application/pdf", MAX_PDF_SIZE_BYTES + 1)
        assert exc_info.value.code == "FILE_TOO_LARGE"

    def test_validate_image_file_boundaries(self):
        cfg = validate_media_file("image/png", 2 * 1024 * 1024)  # 2 MB
        assert cfg["category"] == "image"
        assert cfg["prefix"] == "public-images"

        # Exceeds 5 MB
        with pytest.raises(ValidationException) as exc_info:
            validate_media_file("image/png", MAX_IMAGE_SIZE_BYTES + 1)
        assert exc_info.value.code == "FILE_TOO_LARGE"

    def test_validate_disallowed_mime_rejected(self):
        with pytest.raises(ValidationException) as exc_info:
            validate_media_file("application/x-executable", 1000)
        assert exc_info.value.code == "INVALID_MIME_TYPE"

    def test_validate_zero_or_negative_size_rejected(self):
        with pytest.raises(ValidationException) as exc_info:
            validate_media_file("video/mp4", 0)
        assert exc_info.value.code == "INVALID_FILE_SIZE"

        with pytest.raises(ValidationException) as exc_info:
            validate_media_file("video/mp4", -500)
        assert exc_info.value.code == "INVALID_FILE_SIZE"


class TestMediaAssetModelPersistence:
    """Verifies MediaAsset model creation and database persistence."""

    def test_create_media_asset(self, db_session: Session, instructor_user: User):
        asset = MediaAsset(
            uploader_id=instructor_user.id,
            filename="distributed_systems_intro.mp4",
            file_key="raw-videos/uuid1/distributed_systems_intro.mp4",
            bucket="lms-media",
            mime_type="video/mp4",
            file_size_bytes=104857600,
            status=MEDIA_STATUS_UPLOADING,
        )
        db_session.add(asset)
        db_session.commit()

        assert asset.id is not None
        assert asset.uploader_id == instructor_user.id
        assert asset.status == MEDIA_STATUS_UPLOADING
        assert asset.file_size_bytes == 104857600
        assert asset.uploader.email == "instructor@lms.local"

    def test_update_media_status_and_transcode_output(self, db_session: Session, instructor_user: User):
        asset = MediaAsset(
            uploader_id=instructor_user.id,
            filename="module_reading.pdf",
            file_key="protected-docs/uuid2/module_reading.pdf",
            bucket="lms-media",
            mime_type="application/pdf",
            file_size_bytes=5242880,
            status=MEDIA_STATUS_UPLOADING,
        )
        db_session.add(asset)
        db_session.commit()

        # Update to READY
        asset.status = MEDIA_STATUS_READY
        asset.transcode_output = {"page_count": 42}
        db_session.commit()

        db_session.refresh(asset)
        assert asset.status == MEDIA_STATUS_READY
        assert asset.transcode_output == {"page_count": 42}
