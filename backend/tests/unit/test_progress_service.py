"""Unit tests for ProgressService granular lesson tracking, validation, summaries, and certificate triggers.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Tables 29, 30)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Sections 1, 2)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901, TASK902, TASK903)
"""

from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.exceptions import ForbiddenException, ResourceNotFoundException
from app.core.storage import StorageClient
from app.models import Base
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.certificate import Certificate
from app.models.course import Course, CourseRevision
from app.models.curriculum import (
    LESSON_TYPE_ARTICLE,
    LESSON_TYPE_ASSIGNMENT,
    LESSON_TYPE_QUIZ,
    LESSON_TYPE_VIDEO,
    CurriculumLesson,
    CurriculumSection,
)
from app.models.enrollment import ENROLLMENT_STATUS_ACTIVE, ENROLLMENT_STATUS_REVOKED, Enrollment
from app.models.progress import CourseProgressSummary, LessonProgress
from app.models.quiz import Quiz, QuizAttempt
from app.models.user import User
from app.repositories.certificate_repo import CertificateRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.progress_repo import ProgressRepository
from app.services.audit_service import AuditService
from app.services.certificate_service import CertificateService
from app.services.progress_service import ProgressService


@pytest.fixture
def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def storage_client():
    return StorageClient(get_settings())


@pytest.fixture
def certificate_service(storage_client):
    return CertificateService(
        certificate_repo=CertificateRepository(),
        progress_repo=ProgressRepository(),
        enrollment_repo=EnrollmentRepository(),
        audit_service=AuditService(),
        storage_client=storage_client,
        settings=get_settings(),
    )


@pytest.fixture
def progress_service(certificate_service):
    return ProgressService(
        progress_repo=ProgressRepository(),
        enrollment_repo=EnrollmentRepository(),
        certificate_service=certificate_service,
    )


def _seed_curriculum_environment(session: Session):
    """Seed helper for student, course, revision, section, and 3 lessons."""
    student = User(
        email=f"prog_student_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="mock_hash",
        full_name="Bob Learner",
        is_verified=True,
    )
    course = Course(
        title="Python Distributed Systems",
        slug=f"py-dist-{uuid.uuid4().hex[:6]}",
        price_inr=599900,
    )
    session.add_all([student, course])
    session.flush()

    # Active course enrollment
    enrollment = Enrollment(
        student_id=student.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        granted_at=datetime.now(timezone.utc),
    )
    session.add(enrollment)
    session.flush()

    # Course Revision & Section
    revision = CourseRevision(
        course_id=course.id,
        revision_no=1,
        title="v1.0 Published",
        status="PUBLISHED",
    )
    session.add(revision)
    session.flush()

    section = CurriculumSection(
        course_revision_id=revision.id,
        title="Module 1: Foundations",
        sort_order=0,
    )
    session.add(section)
    session.flush()

    # Lesson 1: Video (600s duration -> 90% is 540s)
    video_lesson = CurriculumLesson(
        section_id=section.id,
        title="Architecture Overview",
        lesson_type=LESSON_TYPE_VIDEO,
        duration_seconds=600,
        sort_order=0,
    )
    # Lesson 2: Article
    article_lesson = CurriculumLesson(
        section_id=section.id,
        title="Reading Assignment",
        lesson_type=LESSON_TYPE_ARTICLE,
        sort_order=1,
    )
    # Lesson 3: Quiz
    quiz_lesson = CurriculumLesson(
        section_id=section.id,
        title="Check Your Knowledge",
        lesson_type=LESSON_TYPE_QUIZ,
        sort_order=2,
    )

    session.add_all([video_lesson, article_lesson, quiz_lesson])
    session.flush()

    # Create Quiz entity for quiz_lesson
    quiz = Quiz(
        lesson_id=quiz_lesson.id,
        title="Module 1 Quiz",
        pass_percentage=70,
    )
    session.add(quiz)
    session.flush()

    return student, course, revision, video_lesson, article_lesson, quiz_lesson, quiz


class TestProgressService:
    """Tests covering granular lesson progress, completion rules, and summary calculations."""

    def test_record_video_progress_below_90_percent_not_completed(
        self,
        db_session: Session,
        progress_service: ProgressService,
    ):
        """Video playback below 90% (e.g. 500s out of 600s) does NOT mark lesson as completed."""
        student, course, _, video_lesson, _, _, _ = _seed_curriculum_environment(db_session)

        res = progress_service.record_lesson_progress(
            session=db_session,
            student=student,
            lesson_id=video_lesson.id,
            watch_position_seconds=500,
        )
        assert res.lesson_id == video_lesson.id
        assert res.is_completed is False
        assert res.watch_position_seconds == 500
        assert res.course_progress.completed_lessons_count == 0
        assert res.course_progress.progress_percentage == Decimal("0.00")

    def test_record_video_progress_at_90_percent_marks_completed(
        self,
        db_session: Session,
        progress_service: ProgressService,
    ):
        """Video playback at or above 90% (e.g. 540s of 600s) marks lesson completed."""
        student, course, _, video_lesson, _, _, _ = _seed_curriculum_environment(db_session)

        res = progress_service.record_lesson_progress(
            session=db_session,
            student=student,
            lesson_id=video_lesson.id,
            watch_position_seconds=540,
        )
        assert res.is_completed is True
        assert res.completed_at is not None
        assert res.course_progress.completed_lessons_count == 1
        assert res.course_progress.total_lessons_count == 3
        # 1/3 = 33.33%
        assert res.course_progress.progress_percentage == Decimal("33.33")

    def test_record_article_progress_completed_toggle(
        self,
        db_session: Session,
        progress_service: ProgressService,
    ):
        """Article lesson completes when learner marks it as complete."""
        student, course, _, _, article_lesson, _, _ = _seed_curriculum_environment(db_session)

        res = progress_service.record_lesson_progress(
            session=db_session,
            student=student,
            lesson_id=article_lesson.id,
            is_completed=True,
        )
        assert res.is_completed is True
        assert res.course_progress.completed_lessons_count == 1

    def test_record_quiz_progress_requires_passed_attempt_rejects_manual_toggle(
        self,
        db_session: Session,
        progress_service: ProgressService,
    ):
        """Learner cannot manually mark quiz lesson complete; must pass quiz attempt."""
        student, course, _, _, _, quiz_lesson, quiz = _seed_curriculum_environment(db_session)

        # Attempt to mark complete manually without passed quiz attempt
        res = progress_service.record_lesson_progress(
            session=db_session,
            student=student,
            lesson_id=quiz_lesson.id,
            is_completed=True,
        )
        assert res.is_completed is False

        # Now simulate student passing the quiz
        attempt = QuizAttempt(
            quiz_id=quiz.id,
            student_id=student.id,
            attempt_no=1,
            score=Decimal("85.00"),
            is_passed=True,
            status="SUBMITTED",
        )
        db_session.add(attempt)
        db_session.flush()

        res2 = progress_service.record_lesson_progress(
            session=db_session,
            student=student,
            lesson_id=quiz_lesson.id,
        )
        assert res2.is_completed is True

    def test_record_assignment_progress_requires_submission(
        self,
        db_session: Session,
        progress_service: ProgressService,
    ):
        """Assignment lesson completes only when a valid submission is submitted or graded."""
        student, course, revision, _, _, _, _ = _seed_curriculum_environment(db_session)
        section = db_session.query(CurriculumSection).first()

        assign_lesson = CurriculumLesson(
            section_id=section.id,
            title="Capstone Project",
            lesson_type=LESSON_TYPE_ASSIGNMENT,
            sort_order=3,
        )
        db_session.add(assign_lesson)
        db_session.flush()

        assignment = Assignment(
            lesson_id=assign_lesson.id,
            title="Design Document",
            instructions="Complete the architecture design document adhering to specifications.",
            max_score=Decimal("100.00"),
            pass_score=Decimal("70.00"),
        )
        db_session.add(assignment)
        db_session.flush()

        # Manual toggle should not complete without submission
        res = progress_service.record_lesson_progress(
            session=db_session,
            student=student,
            lesson_id=assign_lesson.id,
            is_completed=True,
        )
        assert res.is_completed is False

        # Add valid submission
        submission = AssignmentSubmission(
            assignment_id=assignment.id,
            student_id=student.id,
            attempt_no=1,
            file_url="submissions/project.zip",
            text_notes="Architectural design document submitted",
            status="SUBMITTED",
        )
        db_session.add(submission)
        db_session.flush()

        res2 = progress_service.record_lesson_progress(
            session=db_session,
            student=student,
            lesson_id=assign_lesson.id,
        )
        assert res2.is_completed is True

    def test_progress_denied_without_active_enrollment(
        self,
        db_session: Session,
        progress_service: ProgressService,
    ):
        """Students without active enrollment are denied progress recording."""
        student, course, _, video_lesson, _, _, _ = _seed_curriculum_environment(db_session)

        enrollment = db_session.query(Enrollment).filter_by(student_id=student.id, course_id=course.id).first()
        enrollment.status = ENROLLMENT_STATUS_REVOKED
        db_session.flush()

        with pytest.raises(ForbiddenException) as exc_info:
            progress_service.record_lesson_progress(
                session=db_session,
                student=student,
                lesson_id=video_lesson.id,
                watch_position_seconds=600,
            )
        assert exc_info.value.code == "ENROLLMENT_REQUIRED"

    def test_progress_denied_suspended_or_unverified_student(
        self,
        db_session: Session,
        progress_service: ProgressService,
    ):
        """Suspended students or unverified emails are denied progress tracking."""
        student, _, _, video_lesson, _, _, _ = _seed_curriculum_environment(db_session)

        # Suspended check
        student.status = "SUSPENDED"
        db_session.flush()
        with pytest.raises(ForbiddenException) as exc_info:
            progress_service.record_lesson_progress(
                session=db_session,
                student=student,
                lesson_id=video_lesson.id,
            )
        assert exc_info.value.code == "ACCOUNT_SUSPENDED"

        # Unverified email check
        student.status = "ACTIVE"
        student.is_verified = False
        db_session.flush()
        with pytest.raises(ForbiddenException) as exc_info2:
            progress_service.record_lesson_progress(
                session=db_session,
                student=student,
                lesson_id=video_lesson.id,
            )
        assert exc_info2.value.code == "EMAIL_NOT_VERIFIED"

    def test_idempotent_progress_upsert_non_decreasing(
        self,
        db_session: Session,
        progress_service: ProgressService,
    ):
        """watch_position_seconds is non-decreasing; completion remains true once completed."""
        student, course, _, video_lesson, _, _, _ = _seed_curriculum_environment(db_session)

        # Watch 550s (marks complete)
        res1 = progress_service.record_lesson_progress(
            session=db_session,
            student=student,
            lesson_id=video_lesson.id,
            watch_position_seconds=550,
        )
        assert res1.is_completed is True
        assert res1.watch_position_seconds == 550

        # Subsequent heartbeat rewind to 100s must NOT decrease position or reset completion
        res2 = progress_service.record_lesson_progress(
            session=db_session,
            student=student,
            lesson_id=video_lesson.id,
            watch_position_seconds=100,
        )
        assert res2.is_completed is True
        assert res2.watch_position_seconds == 550

    def test_100_percent_progress_triggers_certificate_generation(
        self,
        db_session: Session,
        progress_service: ProgressService,
    ):
        """Completing all course lessons reaches 100% and automatically generates a certificate."""
        student, course, _, video_lesson, article_lesson, quiz_lesson, quiz = _seed_curriculum_environment(db_session)

        # Complete lesson 1 (video)
        progress_service.record_lesson_progress(
            session=db_session,
            student=student,
            lesson_id=video_lesson.id,
            watch_position_seconds=600,
        )

        # Complete lesson 2 (article)
        progress_service.record_lesson_progress(
            session=db_session,
            student=student,
            lesson_id=article_lesson.id,
            is_completed=True,
        )

        # Pass quiz attempt for lesson 3
        attempt = QuizAttempt(
            quiz_id=quiz.id,
            student_id=student.id,
            attempt_no=1,
            score=Decimal("100.00"),
            is_passed=True,
            status="SUBMITTED",
        )
        db_session.add(attempt)
        db_session.flush()

        # Complete lesson 3 (quiz) -> should hit 100%
        res3 = progress_service.record_lesson_progress(
            session=db_session,
            student=student,
            lesson_id=quiz_lesson.id,
        )
        assert res3.course_progress.completed_lessons_count == 3
        assert res3.course_progress.total_lessons_count == 3
        assert res3.course_progress.progress_percentage == Decimal("100.00")
        assert res3.course_progress.is_completed is True

        # Verify Certificate automatically created in DB
        cert = db_session.query(Certificate).filter_by(student_id=student.id, course_id=course.id).first()
        assert cert is not None
        assert cert.certificate_no.startswith("CERT-")
        assert cert.is_revoked is False
