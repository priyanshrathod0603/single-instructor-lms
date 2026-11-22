"""Unit tests for Protected PDF Streaming and Dynamic Watermarking (TASK404).

Verifies:
1. Dynamic provenance watermark stamping on PDF streams:
   - Includes student full name, email, student ID, and UTC timestamp.
   - Generates valid PDF document byte stream.
2. MediaService.get_watermarked_pdf:
   - Verifies active access authorization.
   - Retrieves stored document bytes and returns stamped binary with original filename.
   - Rejects non-PDF assets with NOT_A_PDF.
"""

from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import BadRequestException, ForbiddenException
from app.core.pdf_watermark import apply_pdf_watermark
from app.core.security import hash_password
from app.models.base import Base
from app.models.course import COURSE_STATUS_PUBLISHED, Course, CourseRevision
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.media import (
    MEDIA_STATUS_READY,
    MediaAsset,
)
from app.models.user import ROLE_STUDENT, Role, User, UserRole
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
    """Creates a student user."""
    user = User(
        email="alice.student@lms.local",
        full_name="Alice Student",
        password_hash=hash_password("AliceSecureP@ss1"),
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
def pdf_asset(db_session: Session, student_user: User) -> MediaAsset:
    """Creates a ready PDF MediaAsset."""
    asset = MediaAsset(
        uploader_id=student_user.id,
        filename="lecture_slides_advanced_architecture.pdf",
        file_key="protected-docs/uuid-pdf/lecture_slides_advanced_architecture.pdf",
        bucket="lms-media",
        mime_type="application/pdf",
        file_size_bytes=204800,
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
def preview_lesson(db_session: Session, pdf_asset: MediaAsset) -> CurriculumLesson:
    """Creates a preview lesson with pdf_asset attached."""
    course = Course(
        title="Sample Course",
        slug="sample-course",
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
        title="PDF Lecture Lesson",
        lesson_type="ARTICLE",
        sort_order=0,
        is_preview=True,
        content={"media_asset_id": str(pdf_asset.id)},
    )
    db_session.add(lesson)
    db_session.commit()
    db_session.refresh(lesson)
    return lesson


def test_apply_pdf_watermark_stamps_student_identity():
    """apply_pdf_watermark injects student identity, email, and ID into PDF stream."""
    sample_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nendstream\nxref\ntrailer\n%%EOF"
    watermarked = apply_pdf_watermark(
        sample_pdf,
        student_name="Bob Learner",
        student_email="bob@example.com",
        student_id="ENR-9842",
        timestamp=datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert b"%PDF-" in watermarked
    assert b"CONFIDENTIAL - LICENSED TO: Bob Learner (bob@example.com)" in watermarked
    assert b"STUDENT ID: ENR-9842 - DO NOT DISTRIBUTE" in watermarked
    assert b"2026-11-15 12:00:00 UTC" in watermarked


def test_get_watermarked_pdf_streaming(
    db_session: Session,
    media_service: MediaService,
    pdf_asset: MediaAsset,
    student_user: User,
    preview_lesson: CurriculumLesson,
):
    """MediaService retrieves object and applies dynamic student watermark."""
    # Seed storage client with initial mock PDF
    raw_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nendstream\nxref\ntrailer\n%%EOF"
    media_service.storage_client.put_object(pdf_asset.file_key, raw_pdf, content_type="application/pdf")

    pdf_bytes, filename = media_service.get_watermarked_pdf(
        db_session, pdf_asset.id, student_user, lesson_id=preview_lesson.id
    )

    assert filename == "lecture_slides_advanced_architecture.pdf"
    assert b"%PDF-" in pdf_bytes
    assert b"Alice Student" in pdf_bytes
    assert b"alice.student@lms.local" in pdf_bytes
    assert str(student_user.id).encode("utf-8") in pdf_bytes


def test_get_watermarked_pdf_rejects_non_pdf(
    db_session: Session, media_service: MediaService, student_user: User
):
    """Attempting to stream a video or image via PDF watermarking endpoint fails with NOT_A_PDF."""
    video = MediaAsset(
        uploader_id=student_user.id,
        filename="lecture.mp4",
        file_key="raw-videos/lecture.mp4",
        bucket="lms-media",
        mime_type="video/mp4",
        file_size_bytes=5000000,
        status=MEDIA_STATUS_READY,
    )
    db_session.add(video)
    db_session.commit()

    with pytest.raises(BadRequestException) as exc_info:
        media_service.get_watermarked_pdf(db_session, video.id, student_user)
    assert exc_info.value.code == "NOT_A_PDF"
