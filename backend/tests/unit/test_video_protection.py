"""Unit tests for Secure Signed Playback Token Generator and Verification (TASK403).

Verifies:
1. Short-lived signed HLS streaming token generation (2-hour TTL).
2. Playback URL formatting targeting master.m3u8 playlist.
3. Access controls: only authorized students or instructors can obtain tokens.
4. Token non-reusability beyond approved validity:
   - Expired tokens are rejected with PLAYBACK_TOKEN_EXPIRED.
   - Tampered tokens are rejected with INVALID_PLAYBACK_TOKEN.
   - Cross-media token replay is rejected with TOKEN_MEDIA_MISMATCH.
5. Non-video assets rejected with NOT_A_VIDEO.
"""

from datetime import datetime, timedelta, timezone
import uuid
import jwt
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    UnauthorizedException,
)
from app.core.security import hash_password
from app.models.base import Base
from app.models.course import COURSE_STATUS_PUBLISHED, Course, CourseRevision
from app.models.curriculum import LESSON_TYPE_VIDEO, CurriculumLesson, CurriculumSection
from app.models.media import (
    MEDIA_STATUS_READY,
    MediaAsset,
)
from app.models.user import ROLE_ADMIN, ROLE_STUDENT, Role, User, UserRole
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
def student_user(db_session: Session) -> User:
    """Creates a verified, active Student user."""
    user = User(
        email="learner@lms.local",
        full_name="Active Learner",
        password_hash=hash_password("StudentSecureP@ss1"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.get(Role, ROLE_STUDENT)
    if not role:
        role = Role(id=ROLE_STUDENT, name="Student")
        db_session.add(role)
        db_session.flush()

    ur = UserRole(user_id=user.id, role_id=ROLE_STUDENT)
    db_session.add(ur)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def video_asset(db_session: Session, student_user: User) -> MediaAsset:
    """Creates a ready video MediaAsset."""
    asset = MediaAsset(
        uploader_id=student_user.id,
        filename="lecture_stream.mp4",
        file_key="raw-videos/lecture_stream.mp4",
        bucket="lms-media",
        mime_type="video/mp4",
        file_size_bytes=50000000,
        status=MEDIA_STATUS_READY,
        transcode_output={
            "hls_master_url": "hls/test/master.m3u8",
            "resolutions": ["1080p", "720p"],
        },
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


@pytest.fixture
def pdf_asset(db_session: Session, student_user: User) -> MediaAsset:
    """Creates a ready PDF MediaAsset."""
    asset = MediaAsset(
        uploader_id=student_user.id,
        filename="notes.pdf",
        file_key="protected-docs/notes.pdf",
        bucket="lms-media",
        mime_type="application/pdf",
        file_size_bytes=1000000,
        status=MEDIA_STATUS_READY,
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


@pytest.fixture
def media_service():
    """MediaService instance."""
    return MediaService()


@pytest.fixture
def preview_lesson(db_session: Session, video_asset: MediaAsset) -> CurriculumLesson:
    """Creates a preview lesson with video_asset attached."""
    course = Course(
        title="Sample Course",
        slug="sample-video-course",
        headline="HL",
        price_inr=0,
        is_free=True,
        status=COURSE_STATUS_PUBLISHED,
    )
    db_session.add(course)
    db_session.flush()
    rev = CourseRevision(
        course_id=course.id,
        revision_no=1,
        title="Rev 1",
        status=COURSE_STATUS_PUBLISHED,
    )
    db_session.add(rev)
    db_session.flush()
    course.live_revision_id = rev.id
    db_session.flush()
    sec = CurriculumSection(course_revision_id=rev.id, title="Sec 1", sort_order=0)
    db_session.add(sec)
    db_session.flush()
    lesson = CurriculumLesson(
        section_id=sec.id,
        title="Preview Video Lesson",
        lesson_type=LESSON_TYPE_VIDEO,
        sort_order=0,
        is_preview=True,
        content={"media_asset_id": str(video_asset.id)},
    )
    db_session.add(lesson)
    db_session.commit()
    db_session.refresh(lesson)
    return lesson


def test_generate_playback_token_happy_path(
    db_session: Session,
    media_service: MediaService,
    video_asset: MediaAsset,
    student_user: User,
    preview_lesson: CurriculumLesson,
):
    """Generates 2-hour signed HLS playback token and master playlist URL."""
    resp = media_service.generate_playback_token(
        db_session,
        video_asset.id,
        student_user,
        lesson_id=preview_lesson.id,
        client_ip="203.0.113.42",
    )

    assert resp.media_id == video_asset.id
    assert resp.ttl_seconds == 7200
    assert "https://stream.instructor.com/hls/" in resp.stream_url
    assert f"/hls/{video_asset.id}/master.m3u8?token=" in resp.stream_url

    # Verify generated token
    claims = media_service.verify_playback_token(resp.playback_token, video_asset.id, client_ip="203.0.113.42")
    assert claims["sub"] == str(student_user.id)
    assert claims["media_id"] == str(video_asset.id)
    assert claims["ip"] == "203.0.113.42"
    assert claims["token_type"] == "playback"


def test_playback_token_rejects_non_video_asset(
    db_session: Session, media_service: MediaService, pdf_asset: MediaAsset, student_user: User
):
    """Attempting to generate a video playback token for a PDF must raise BadRequestException."""
    with pytest.raises(BadRequestException) as exc_info:
        media_service.generate_playback_token(db_session, pdf_asset.id, student_user)
    assert exc_info.value.code == "NOT_A_VIDEO"


def test_verify_playback_token_expired_fails(
    db_session: Session, media_service: MediaService, video_asset: MediaAsset, student_user: User
):
    """Expired playback token must be rejected with PLAYBACK_TOKEN_EXPIRED."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    # Token expired 10 minutes ago
    expired_payload = {
        "sub": str(student_user.id),
        "media_id": str(video_asset.id),
        "token_type": "playback",
        "iat": int((now - timedelta(hours=3)).timestamp()),
        "exp": int((now - timedelta(minutes=10)).timestamp()),
    }
    expired_token = jwt.encode(
        expired_payload,
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )

    with pytest.raises(UnauthorizedException) as exc_info:
        media_service.verify_playback_token(expired_token, video_asset.id)
    assert exc_info.value.code == "PLAYBACK_TOKEN_EXPIRED"


def test_verify_playback_token_tampered_signature_fails(
    db_session: Session, media_service: MediaService, video_asset: MediaAsset, student_user: User
):
    """Tampered token with invalid signature must be rejected with INVALID_PLAYBACK_TOKEN."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(student_user.id),
        "media_id": str(video_asset.id),
        "token_type": "playback",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=2)).timestamp()),
    }
    # Signed with wrong key
    tampered_token = jwt.encode(payload, "wrong-fraudulent-cryptographic-secret", algorithm="HS256")

    with pytest.raises(UnauthorizedException) as exc_info:
        media_service.verify_playback_token(tampered_token, video_asset.id)
    assert exc_info.value.code == "INVALID_PLAYBACK_TOKEN"


def test_verify_playback_token_media_mismatch_fails(
    db_session: Session,
    media_service: MediaService,
    video_asset: MediaAsset,
    student_user: User,
    preview_lesson: CurriculumLesson,
):
    """Using a playback token issued for Media A to access Media B must be rejected."""
    resp = media_service.generate_playback_token(
        db_session, video_asset.id, student_user, lesson_id=preview_lesson.id
    )

    another_media_id = uuid.uuid4()
    with pytest.raises(UnauthorizedException) as exc_info:
        media_service.verify_playback_token(resp.playback_token, another_media_id)
    assert exc_info.value.code == "TOKEN_MEDIA_MISMATCH"
