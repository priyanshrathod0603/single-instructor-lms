"""Unit tests for LessonProgress, CourseProgressSummary, and Certificate models.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Tables 29, 30, 31)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Sections 1-3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901)
"""

from decimal import Decimal
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base
from app.models.certificate import Certificate
from app.models.course import Course
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.progress import CourseProgressSummary, LessonProgress
from app.models.user import User


@pytest.fixture
def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def _seed_student_course_lesson(session: Session):
    """Seed helper for student, course, and lesson."""
    student = User(
        email=f"student_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="argon2id_mock_hash",
        full_name="Alice Learner",
    )
    course = Course(
        title="Full Stack Architecture",
        slug=f"full-stack-{uuid.uuid4().hex[:6]}",
        price_inr=499900,
    )
    session.add_all([student, course])
    session.flush()

    section = CurriculumSection(
        course_revision_id=course.id,  # using course id as mock revision id for test
        title="Module 1",
        sort_order=0,
    )
    session.add(section)
    session.flush()

    lesson = CurriculumLesson(
        section_id=section.id,
        title="Intro Video",
        lesson_type="VIDEO",
        duration_seconds=600,
    )
    session.add(lesson)
    session.flush()
    return student, course, lesson


class TestProgressModels:
    """Tests for LessonProgress, CourseProgressSummary, and Certificate entities."""

    def test_lesson_progress_defaults_and_creation(self, db_session: Session):
        """LessonProgress must default is_completed=False, watch_position_seconds=0."""
        student, course, lesson = _seed_student_course_lesson(db_session)

        progress = LessonProgress(
            student_id=student.id,
            lesson_id=lesson.id,
        )
        db_session.add(progress)
        db_session.commit()

        assert progress.id is not None
        assert progress.is_completed is False
        assert progress.watch_position_seconds == 0
        assert progress.completed_at is None
        assert progress.updated_at is not None

    def test_lesson_progress_unique_student_lesson_constraint(self, db_session: Session):
        """Cannot insert two LessonProgress records for the same (student_id, lesson_id)."""
        student, course, lesson = _seed_student_course_lesson(db_session)

        p1 = LessonProgress(student_id=student.id, lesson_id=lesson.id)
        p2 = LessonProgress(student_id=student.id, lesson_id=lesson.id)
        db_session.add(p1)
        db_session.commit()

        db_session.add(p2)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_course_progress_summary_defaults_and_properties(self, db_session: Session):
        """CourseProgressSummary defaults to 0 and provides is_completed property."""
        student, course, _ = _seed_student_course_lesson(db_session)

        summary = CourseProgressSummary(
            student_id=student.id,
            course_id=course.id,
        )
        db_session.add(summary)
        db_session.commit()

        assert summary.completed_lessons_count == 0
        assert summary.total_lessons_count == 0
        assert summary.progress_percentage == Decimal("0.00")
        assert summary.is_completed is False

        # Set to 100%
        summary.completed_lessons_count = 10
        summary.total_lessons_count = 10
        summary.progress_percentage = Decimal("100.00")
        db_session.commit()
        assert summary.is_completed is True

    def test_course_progress_summary_unique_constraint(self, db_session: Session):
        """Cannot insert duplicate course progress summaries for the same student and course."""
        student, course, _ = _seed_student_course_lesson(db_session)

        s1 = CourseProgressSummary(student_id=student.id, course_id=course.id)
        s2 = CourseProgressSummary(student_id=student.id, course_id=course.id)
        db_session.add(s1)
        db_session.commit()

        db_session.add(s2)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_certificate_model_creation_and_uniqueness(self, db_session: Session):
        """Certificate enforces uniqueness on certificate_no, verification_hash, and (student_id, course_id)."""
        student, course, _ = _seed_student_course_lesson(db_session)

        cert = Certificate(
            certificate_no="CERT-202611-1234",
            student_id=student.id,
            course_id=course.id,
            verification_hash="a" * 64,
            pdf_url="certificates/CERT-202611-1234.pdf",
        )
        db_session.add(cert)
        db_session.commit()

        assert cert.id is not None
        assert cert.is_revoked is False
        assert cert.revoked_at is None
        assert cert.revoked_reason is None

        # Duplicate (student_id, course_id)
        duplicate_cert = Certificate(
            certificate_no="CERT-202611-5678",
            student_id=student.id,
            course_id=course.id,
            verification_hash="b" * 64,
            pdf_url="certificates/CERT-202611-5678.pdf",
        )
        db_session.add(duplicate_cert)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
