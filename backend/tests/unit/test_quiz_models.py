"""Unit tests for Quiz, Question, Option, Attempt, and Answer models.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 4, Tables 20-24)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Sections 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK801)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-011)
"""

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.models.base import Base
from app.models.course import COURSE_STATUS_PUBLISHED, Course, CourseRevision
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.quiz import (
    ATTEMPT_STATUS_EXPIRED,
    ATTEMPT_STATUS_IN_PROGRESS,
    ATTEMPT_STATUS_SUBMITTED,
    QUESTION_TYPE_MCQ_MULTI,
    QUESTION_TYPE_MCQ_SINGLE,
    QUESTION_TYPE_TEXT_SHORT,
    QUESTION_TYPE_TRUE_FALSE,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
    QuizQuestionOption,
)
from app.models.user import ROLE_STUDENT, ROLE_SUPER_ADMIN, Role, User, UserRole


@pytest.fixture
def db_session():
    """In-memory SQLite session with full schema initialized."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def instructor(db_session: Session) -> User:
    """Creates instructor user."""
    user = User(
        email="instructor@lms.local",
        full_name="Chief Instructor",
        password_hash=hash_password("Secret123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def student(db_session: Session) -> User:
    """Creates student user."""
    user = User(
        email="learner@lms.local",
        full_name="Enrolled Learner",
        password_hash=hash_password("Secret123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def lesson(db_session: Session, instructor: User) -> CurriculumLesson:
    """Creates Course -> Revision -> Section -> Lesson structure."""
    course = Course(
        title="Microservices Architecture",
        slug="microservices-architecture",
        headline="Complete guide to microservices",
        price_inr=999900,
        status=COURSE_STATUS_PUBLISHED,
    )
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(
        course_id=course.id,
        revision_no=1,
        status="PUBLISHED",
        title="v1",
        created_by=instructor.id,
    )
    db_session.add(rev)
    db_session.flush()
    course.live_revision_id = rev.id

    section = CurriculumSection(
        course_revision_id=rev.id,
        title="Module 1: Fundamentals",
        sort_order=0,
    )
    db_session.add(section)
    db_session.flush()

    lesson = CurriculumLesson(
        section_id=section.id,
        title="Quiz 1: Microservices Fundamentals",
        lesson_type="QUIZ",
        sort_order=0,
        is_preview=False,
    )
    db_session.add(lesson)
    db_session.flush()
    return lesson


def test_quiz_model_creation_and_defaults(db_session: Session, lesson: CurriculumLesson):
    """Verifies default values and attributes on Quiz model."""
    quiz = Quiz(
        lesson_id=lesson.id,
        title="Fundamentals Assessment",
        description="Test your understanding of services.",
    )
    db_session.add(quiz)
    db_session.flush()

    assert quiz.id is not None
    assert quiz.pass_percentage == 70
    assert quiz.time_limit_minutes == 30
    assert quiz.shuffle_questions is True
    assert quiz.max_attempts == 3
    assert quiz.created_at is not None
    assert quiz.updated_at is not None
    assert quiz.lesson.id == lesson.id


def test_quiz_lesson_uniqueness(db_session: Session, lesson: CurriculumLesson):
    """A lesson can have at most one quiz attached (1:1 constraint)."""
    quiz1 = Quiz(lesson_id=lesson.id, title="Quiz 1")
    db_session.add(quiz1)
    db_session.flush()

    quiz2 = Quiz(lesson_id=lesson.id, title="Quiz 2")
    db_session.add(quiz2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_question_and_option_cascade_delete(db_session: Session, lesson: CurriculumLesson):
    """Deleting a quiz cascades to its questions and options."""
    quiz = Quiz(lesson_id=lesson.id, title="Cascading Quiz")
    db_session.add(quiz)
    db_session.flush()

    q1 = QuizQuestion(
        quiz_id=quiz.id,
        question_type=QUESTION_TYPE_MCQ_SINGLE,
        prompt="What is a microservice?",
        points=2.0,
        sort_order=1,
    )
    db_session.add(q1)
    db_session.flush()

    opt1 = QuizQuestionOption(question_id=q1.id, option_text="A small service", is_correct=True, sort_order=1)
    opt2 = QuizQuestionOption(question_id=q1.id, option_text="A big monolith", is_correct=False, sort_order=2)
    db_session.add_all([opt1, opt2])
    db_session.flush()

    assert len(quiz.questions) == 1
    assert len(q1.options) == 2

    # Delete quiz and verify cascade
    db_session.delete(quiz)
    db_session.flush()

    assert db_session.get(QuizQuestion, q1.id) is None
    assert db_session.get(QuizQuestionOption, opt1.id) is None
    assert db_session.get(QuizQuestionOption, opt2.id) is None


def test_quiz_attempt_unique_constraint(db_session: Session, lesson: CurriculumLesson, student: User):
    """UNIQUE(quiz_id, student_id, attempt_no) prevents duplicate attempt numbers."""
    quiz = Quiz(lesson_id=lesson.id, title="Attempt Quiz")
    db_session.add(quiz)
    db_session.flush()

    attempt1 = QuizAttempt(quiz_id=quiz.id, student_id=student.id, attempt_no=1)
    db_session.add(attempt1)
    db_session.flush()

    # Attempt 2 is allowed
    attempt2 = QuizAttempt(quiz_id=quiz.id, student_id=student.id, attempt_no=2)
    db_session.add(attempt2)
    db_session.flush()

    # Duplicate attempt 1 must fail
    dup = QuizAttempt(quiz_id=quiz.id, student_id=student.id, attempt_no=1)
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_quiz_answer_autosave_and_unique_constraint(db_session: Session, lesson: CurriculumLesson, student: User):
    """UNIQUE(attempt_id, question_id) ensures single response row per question during autosave."""
    quiz = Quiz(lesson_id=lesson.id, title="Autosave Quiz")
    db_session.add(quiz)
    db_session.flush()

    q = QuizQuestion(quiz_id=quiz.id, question_type=QUESTION_TYPE_MCQ_SINGLE, prompt="Prompt")
    db_session.add(q)
    db_session.flush()

    attempt = QuizAttempt(quiz_id=quiz.id, student_id=student.id, attempt_no=1)
    db_session.add(attempt)
    db_session.flush()

    # Create answer
    ans = QuizAnswer(
        attempt_id=attempt.id,
        question_id=q.id,
        selected_option_ids=[str(uuid.uuid4())],
    )
    db_session.add(ans)
    db_session.flush()

    # Duplicate answer for same attempt and question must fail
    dup = QuizAnswer(
        attempt_id=attempt.id,
        question_id=q.id,
        selected_option_ids=[str(uuid.uuid4())],
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
