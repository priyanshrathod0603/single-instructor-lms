"""Unit tests for Assignment, Rubric, Submission, and GradeOverride database models.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 3, Tables 14-19)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Section 1)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK701)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003, ADR-013)
"""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.models.assignment import (
    SUBMISSION_STATUS_GRADED,
    SUBMISSION_STATUS_SUBMITTED,
    Assignment,
    AssignmentSubmission,
    GradeOverride,
    Rubric,
    RubricCriteria,
    RubricScore,
)
from app.models.base import Base
from app.models.course import COURSE_STATUS_PUBLISHED, Course, CourseRevision
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.user import User


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
def student_user(db_session: Session) -> User:
    """Fixture creating a student user."""
    user = User(
        email="student@lms.local",
        full_name="Enrolled Student",
        password_hash=hash_password("StudentPassword123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Fixture creating an admin user."""
    user = User(
        email="admin@lms.local",
        full_name="Platform Admin",
        password_hash=hash_password("AdminPassword123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def lesson(db_session: Session, admin_user: User) -> CurriculumLesson:
    """Fixture creating a curriculum lesson."""
    course = Course(
        title="Distributed Systems",
        slug="distributed-systems",
        price_inr=999900,
        status=COURSE_STATUS_PUBLISHED,
    )
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(
        course_id=course.id,
        revision_no=1,
        status="PUBLISHED",
        title="Distributed Systems v1",
        created_by=admin_user.id,
    )
    db_session.add(rev)
    db_session.flush()

    section = CurriculumSection(
        course_revision_id=rev.id,
        title="Module 1: Concurrency",
    )
    db_session.add(section)
    db_session.flush()

    curriculum_lesson = CurriculumLesson(
        section_id=section.id,
        title="Assignment 1: Distributed Key-Value Store",
        lesson_type="ASSIGNMENT",
    )
    db_session.add(curriculum_lesson)
    db_session.flush()
    return curriculum_lesson


def test_assignment_model_creation(db_session: Session, lesson: CurriculumLesson):
    """Assignment initializes with default scores, timestamps, and UUID PK."""
    due = datetime.now(timezone.utc) + timedelta(days=14)
    assignment = Assignment(
        lesson_id=lesson.id,
        title="Build a Raft Consensus Node",
        instructions="Implement leader election and log replication.",
        max_score=100.0,
        pass_score=60.0,
        allow_late=True,
        due_date=due,
    )
    db_session.add(assignment)
    db_session.commit()

    assert isinstance(assignment.id, uuid.UUID)
    assert assignment.lesson_id == lesson.id
    assert assignment.title == "Build a Raft Consensus Node"
    assert assignment.max_score == 100.0
    assert assignment.pass_score == 60.0
    assert assignment.allow_late is True
    assert assignment.due_date == due
    assert "Assignment" in repr(assignment)


def test_assignment_unique_lesson_constraint(db_session: Session, lesson: CurriculumLesson):
    """Only one assignment configuration allowed per curriculum lesson."""
    a1 = Assignment(
        lesson_id=lesson.id,
        title="Assignment A",
        instructions="Instructions A",
    )
    db_session.add(a1)
    db_session.commit()

    a2 = Assignment(
        lesson_id=lesson.id,
        title="Assignment B",
        instructions="Instructions B",
    )
    db_session.add(a2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_rubric_and_criteria_hierarchy(db_session: Session, lesson: CurriculumLesson):
    """Rubric and RubricCriteria models maintain parent-child relationships and sort orders."""
    assignment = Assignment(
        lesson_id=lesson.id,
        title="Architecture Project",
        instructions="Build scalable API.",
    )
    db_session.add(assignment)
    db_session.flush()

    rubric = Rubric(
        assignment_id=assignment.id,
        title="Standard Grading Rubric",
        version=1,
        is_active=True,
    )
    db_session.add(rubric)
    db_session.flush()

    c1 = RubricCriteria(
        rubric_id=rubric.id,
        title="Code Quality & Modularity",
        max_points=40.0,
        weight=1.0,
        sort_order=0,
    )
    c2 = RubricCriteria(
        rubric_id=rubric.id,
        title="Test Coverage & Reliability",
        max_points=60.0,
        weight=1.0,
        sort_order=1,
    )
    db_session.add_all([c1, c2])
    db_session.commit()

    db_session.refresh(rubric)
    assert len(rubric.criteria) == 2
    assert rubric.criteria[0].title == "Code Quality & Modularity"
    assert rubric.criteria[1].title == "Test Coverage & Reliability"
    assert "Rubric" in repr(rubric)
    assert "RubricCriteria" in repr(c1)


def test_assignment_submission_attempt_tracking(
    db_session: Session,
    lesson: CurriculumLesson,
    student_user: User,
):
    """UNIQUE(assignment_id, student_id, attempt_no) strictly enforces versioning."""
    assignment = Assignment(
        lesson_id=lesson.id,
        title="Term Paper",
        instructions="Write 10 pages on Paxos.",
    )
    db_session.add(assignment)
    db_session.flush()

    sub1 = AssignmentSubmission(
        assignment_id=assignment.id,
        student_id=student_user.id,
        attempt_no=1,
        file_url="https://storage.lms.local/submissions/paxos_v1.pdf",
        text_notes="First draft submission.",
        status=SUBMISSION_STATUS_SUBMITTED,
    )
    db_session.add(sub1)
    db_session.commit()

    # Attempt 2 for same student succeeds
    sub2 = AssignmentSubmission(
        assignment_id=assignment.id,
        student_id=student_user.id,
        attempt_no=2,
        file_url="https://storage.lms.local/submissions/paxos_v2.pdf",
        text_notes="Second revised submission.",
        status=SUBMISSION_STATUS_SUBMITTED,
    )
    db_session.add(sub2)
    db_session.commit()

    # Duplicate attempt 2 raises IntegrityError
    dup_sub = AssignmentSubmission(
        assignment_id=assignment.id,
        student_id=student_user.id,
        attempt_no=2,
        file_url="https://storage.lms.local/submissions/paxos_v2_dup.pdf",
    )
    db_session.add(dup_sub)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_rubric_scores_and_grade_overrides(
    db_session: Session,
    lesson: CurriculumLesson,
    student_user: User,
    admin_user: User,
):
    """RubricScore and GradeOverride models link cleanly to submissions."""
    assignment = Assignment(lesson_id=lesson.id, title="Final Project", instructions="Submit repo.")
    db_session.add(assignment)
    db_session.flush()

    rubric = Rubric(assignment_id=assignment.id, title="Rubric v1")
    db_session.add(rubric)
    db_session.flush()

    crit = RubricCriteria(rubric_id=rubric.id, title="Correctness", max_points=100.0)
    db_session.add(crit)
    db_session.flush()

    sub = AssignmentSubmission(
        assignment_id=assignment.id,
        student_id=student_user.id,
        attempt_no=1,
        file_url="https://storage.lms.local/repo.zip",
        status=SUBMISSION_STATUS_GRADED,
        final_score=85.0,
        graded_by=admin_user.id,
    )
    db_session.add(sub)
    db_session.flush()

    # Rubric score
    score = RubricScore(
        submission_id=sub.id,
        criteria_id=crit.id,
        points_awarded=85.0,
        feedback="Well executed edge-case handling.",
    )
    db_session.add(score)

    # Grade override
    override = GradeOverride(
        submission_id=sub.id,
        original_score=85.0,
        overridden_score=95.0,
        reason="Demonstrated advanced lock-free queue in live interview.",
        overridden_by=admin_user.id,
    )
    db_session.add(override)
    db_session.commit()

    db_session.refresh(sub)
    assert len(sub.rubric_scores) == 1
    assert sub.rubric_scores[0].points_awarded == 85.0
    assert len(sub.grade_overrides) == 1
    assert sub.grade_overrides[0].original_score == 85.0
    assert sub.grade_overrides[0].overridden_score == 95.0
    assert "GradeOverride" in repr(override)
    assert "RubricScore" in repr(score)
