"""Unit tests for AssignmentService domain workflows.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 3, Tables 14-19)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Section 1)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK701, TASK702, TASK703, TASK704)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003, ADR-008, ADR-012, ADR-013)
"""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    ResourceNotFoundException,
)
from app.core.security import hash_password
from app.models.assignment import (
    SUBMISSION_STATUS_GRADED,
    SUBMISSION_STATUS_REJECTED,
    SUBMISSION_STATUS_SUBMITTED,
    Assignment,
    AssignmentSubmission,
    GradeOverride,
    Rubric,
    RubricCriteria,
)
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.course import (
    COURSE_STATUS_PUBLISHED,
    Course,
    CourseRevision,
)
from app.models.curriculum import (
    CurriculumLesson,
    CurriculumSection,
)
from app.models.enrollment import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_EXPIRED,
    ENROLLMENT_STATUS_REVOKED,
    Enrollment,
)
from app.models.notification import NotificationOutbox
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    ROLE_VISITOR,
    Role,
    User,
    UserRole,
)
from app.schemas.assignment import (
    AssignmentCreateRequest,
    AssignmentUpdateRequest,
    GradeOverrideRequest,
    GradeSubmissionRequest,
    RubricCreateRequest,
    RubricCriteriaCreateRequest,
    RubricScoreInput,
    SubmissionCreateRequest,
)
from app.services.assignment_service import AssignmentService


@pytest.fixture
def db_session():
    """In-memory SQLite session with all models created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    roles = [
        Role(id=ROLE_VISITOR, name="Visitor", description="Public guest"),
        Role(id=ROLE_STUDENT, name="Student", description="Enrolled learner"),
        Role(id=ROLE_STAFF, name="Staff", description="Teaching assistant / grader"),
        Role(id=ROLE_ADMIN, name="Admin", description="Platform administrator"),
        Role(id=ROLE_SUPER_ADMIN, name="Super Admin", description="Platform owner"),
    ]
    session.add_all(roles)
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def student_user(db_session: Session) -> User:
    """Fixture creating an active, verified student."""
    user = User(
        email="student@lms.local",
        full_name="Alice Student",
        password_hash=hash_password("StudentPass123!"),
        is_verified=True,
        is_active=True,
    )
    user.user_roles.append(UserRole(role_id=ROLE_STUDENT))
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def other_student_user(db_session: Session) -> User:
    """Fixture creating a second active, verified student."""
    user = User(
        email="stranger@lms.local",
        full_name="Bob Stranger",
        password_hash=hash_password("StudentPass123!"),
        is_verified=True,
        is_active=True,
    )
    user.user_roles.append(UserRole(role_id=ROLE_STUDENT))
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def staff_user(db_session: Session) -> User:
    """Fixture creating a staff evaluator."""
    user = User(
        email="evaluator@lms.local",
        full_name="Prof Evaluator",
        password_hash=hash_password("StaffPass123!"),
        is_verified=True,
        is_active=True,
    )
    user.user_roles.append(UserRole(role_id=ROLE_STAFF))
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def super_admin_user(db_session: Session) -> User:
    """Fixture creating a super administrator."""
    user = User(
        email="owner@lms.local",
        full_name="Chief Executive",
        password_hash=hash_password("AdminPass123!"),
        is_verified=True,
        is_active=True,
    )
    user.user_roles.append(UserRole(role_id=ROLE_SUPER_ADMIN))
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def course_hierarchy(db_session: Session, super_admin_user: User) -> tuple[Course, CurriculumLesson]:
    """Fixture creating Course -> Revision -> Section -> Lesson hierarchy."""
    course = Course(
        title="Modern Python Concurrency",
        slug="modern-python-concurrency",
        headline="Deep Dive into Asyncio and Multiprocessing",
        price_inr=599900,
        status=COURSE_STATUS_PUBLISHED,
    )
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(
        course_id=course.id,
        revision_no=1,
        status="DRAFT",
        title="v1",
        created_by=super_admin_user.id,
    )
    db_session.add(rev)
    db_session.flush()
    course.live_revision_id = rev.id

    section = CurriculumSection(
        course_revision_id=rev.id,
        title="Module 1: Foundations",
        sort_order=0,
    )
    db_session.add(section)
    db_session.flush()

    lesson = CurriculumLesson(
        section_id=section.id,
        title="Project Assignment: Async Rate Limiter",
        lesson_type="ASSIGNMENT",
        sort_order=0,
        is_preview=False,
    )
    db_session.add(lesson)
    db_session.flush()

    return course, lesson


@pytest.fixture
def active_enrollment(
    db_session: Session,
    student_user: User,
    course_hierarchy: tuple[Course, CurriculumLesson],
) -> Enrollment:
    """Fixture creating an active course enrollment for student_user."""
    course, _ = course_hierarchy
    enrollment = Enrollment(
        student_id=student_user.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        granted_at=datetime.now(timezone.utc),
    )
    db_session.add(enrollment)
    db_session.flush()
    return enrollment


@pytest.fixture
def assignment_service() -> AssignmentService:
    """AssignmentService instance."""
    return AssignmentService()


# =============================================================================
# 1. Assignment Creation & Configuration Tests (TASK701)
# =============================================================================

def test_create_assignment_success(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    super_admin_user: User,
):
    """Test creating an assignment with instructions, due date and pass score."""
    _, lesson = course_hierarchy
    due = datetime.now(timezone.utc) + timedelta(days=14)
    data = AssignmentCreateRequest(
        title="Async Rate Limiter Implementation",
        instructions="Implement a token bucket rate limiter using asyncio and Redis.",
        max_score=100.0,
        pass_score=70.0,
        allow_late=False,
        due_date=due,
    )

    resp = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=data,
        actor_id=super_admin_user.id,
    )

    assert resp.title == "Async Rate Limiter Implementation"
    assert resp.lesson_id == lesson.id
    assert resp.max_score == 100.0
    assert resp.pass_score == 70.0
    assert resp.allow_late is False

    # Verify audit log
    audit = db_session.execute(
        select(AuditLog).filter(AuditLog.action == "ASSIGNMENT_CREATED")
    ).scalar_one_or_none()
    assert audit is not None
    assert audit.resource_id == str(resp.id)


def test_create_assignment_with_initial_rubric(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    super_admin_user: User,
):
    """Test creating an assignment with nested rubric criteria."""
    _, lesson = course_hierarchy
    rubric_in = RubricCreateRequest(
        title="Async Performance Rubric",
        criteria=[
            RubricCriteriaCreateRequest(
                title="Code Concurrency Correctness",
                max_points=50.0,
                weight=1.0,
                description="Deadlock-free asyncio task execution.",
            ),
            RubricCriteriaCreateRequest(
                title="Unit Test Suite & Coverage",
                max_points=50.0,
                weight=1.0,
                description="At least 90% branch coverage.",
            ),
        ],
    )
    data = AssignmentCreateRequest(
        title="Practical Project",
        instructions="Complete the project.",
        max_score=100.0,
        pass_score=60.0,
        rubric=rubric_in,
    )

    resp = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=data,
        actor_id=super_admin_user.id,
    )

    assert resp.active_rubric is not None
    assert resp.active_rubric.version == 1
    assert len(resp.active_rubric.criteria) == 2


def test_create_assignment_duplicate_on_same_lesson_rejected(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    super_admin_user: User,
):
    """Cannot create two assignments for the same curriculum lesson."""
    _, lesson = course_hierarchy
    data = AssignmentCreateRequest(
        title="Project",
        instructions="Instructions",
        max_score=100.0,
    )
    assignment_service.create_assignment(db_session, lesson.id, data, super_admin_user.id)

    with pytest.raises(BadRequestException) as exc:
        assignment_service.create_assignment(db_session, lesson.id, data, super_admin_user.id)
    assert exc.value.code == "ASSIGNMENT_ALREADY_EXISTS"


def test_create_assignment_lesson_not_found(
    db_session: Session,
    assignment_service: AssignmentService,
    super_admin_user: User,
):
    """Non-existent lesson ID raises ResourceNotFoundException."""
    fake_id = uuid.uuid4()
    data = AssignmentCreateRequest(
        title="Project",
        instructions="Instructions",
        max_score=100.0,
    )
    with pytest.raises(ResourceNotFoundException):
        assignment_service.create_assignment(db_session, fake_id, data, super_admin_user.id)


def test_update_assignment_success(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    super_admin_user: User,
):
    """Update instructions and pass score of existing assignment."""
    _, lesson = course_hierarchy
    created = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Initial Title",
            instructions="Initial Instructions",
            max_score=100.0,
        ),
        actor_id=super_admin_user.id,
    )

    updated = assignment_service.update_assignment(
        session=db_session,
        assignment_id=created.id,
        data=AssignmentUpdateRequest(
            title="Revised Title",
            pass_score=75.0,
            allow_late=True,
        ),
        actor_id=super_admin_user.id,
    )

    assert updated.title == "Revised Title"
    assert updated.pass_score == 75.0
    assert updated.allow_late is True


def test_create_rubric_versioning_and_immutability(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    super_admin_user: User,
):
    """Updating rubric creates version 2 and deactivates version 1."""
    _, lesson = course_hierarchy
    created = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Initial Title",
            instructions="Instructions",
            max_score=100.0,
            rubric=RubricCreateRequest(
                title="Rubric v1",
                criteria=[
                    RubricCriteriaCreateRequest(
                        title="Criteria 1",
                        max_points=100.0,
                    )
                ],
            ),
        ),
        actor_id=super_admin_user.id,
    )

    # Add Rubric v2
    rubric_v2 = assignment_service.create_or_update_rubric(
        session=db_session,
        assignment_id=created.id,
        data=RubricCreateRequest(
            title="Rubric v2",
            criteria=[
                RubricCriteriaCreateRequest(
                    title="Criteria A",
                    max_points=50.0,
                ),
                RubricCriteriaCreateRequest(
                    title="Criteria B",
                    max_points=50.0,
                ),
            ],
        ),
        actor_id=super_admin_user.id,
    )

    assert rubric_v2.version == 2
    assert rubric_v2.is_active is True

    # Check database: version 1 must now be inactive
    all_rubrics = db_session.execute(
        select(Rubric).filter(Rubric.assignment_id == created.id).order_by(Rubric.version.asc())
    ).scalars().all()
    assert len(all_rubrics) == 2
    assert all_rubrics[0].version == 1
    assert all_rubrics[0].is_active is False
    assert all_rubrics[1].version == 2
    assert all_rubrics[1].is_active is True


# =============================================================================
# 2. Student Submission Workflow Tests (TASK702)
# =============================================================================

def test_submit_project_happy_path(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Enrolled, verified student submits project; outbox and audit recorded."""
    _, lesson = course_hierarchy
    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Async Project",
            instructions="Do the project.",
            max_score=100.0,
        ),
        actor_id=super_admin_user.id,
    )

    sub = assignment_service.submit_project(
        session=db_session,
        assignment_id=assignment.id,
        data=SubmissionCreateRequest(
            file_url="https://s3.local/submissions/project1.zip",
            text_notes="Completed with asyncio.Queue.",
        ),
        student=student_user,
    )

    assert sub.status == SUBMISSION_STATUS_SUBMITTED
    assert sub.attempt_no == 1
    assert sub.student_id == student_user.id
    assert sub.file_url == "https://s3.local/submissions/project1.zip"

    # Verify outbox event
    outbox = db_session.execute(
        select(NotificationOutbox).filter(NotificationOutbox.event_type == "ASSIGNMENT_SUBMITTED")
    ).scalar_one_or_none()
    assert outbox is not None
    assert outbox.recipient == student_user.email

    # Verify audit log
    audit = db_session.execute(
        select(AuditLog).filter(AuditLog.action == "ASSIGNMENT_SUBMISSION_CREATED")
    ).scalar_one_or_none()
    assert audit is not None
    assert audit.resource_id == str(sub.id)


def test_submit_project_attempt_increment(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Subsequent submissions by same student increment attempt_no monotonically."""
    _, lesson = course_hierarchy
    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Async Project",
            instructions="Do the project.",
            max_score=100.0,
        ),
        actor_id=super_admin_user.id,
    )

    sub1 = assignment_service.submit_project(
        db_session,
        assignment.id,
        SubmissionCreateRequest(file_url="https://s3.local/attempt1.zip"),
        student_user,
    )
    assert sub1.attempt_no == 1

    sub2 = assignment_service.submit_project(
        db_session,
        assignment.id,
        SubmissionCreateRequest(file_url="https://s3.local/attempt2.zip"),
        student_user,
    )
    assert sub2.attempt_no == 2


def test_submit_project_unenrolled_rejected(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    other_student_user: User,
    super_admin_user: User,
):
    """Unenrolled student cannot submit project work."""
    _, lesson = course_hierarchy
    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Async Project",
            instructions="Do the project.",
            max_score=100.0,
        ),
        actor_id=super_admin_user.id,
    )

    with pytest.raises(ForbiddenException) as exc:
        assignment_service.submit_project(
            session=db_session,
            assignment_id=assignment.id,
            data=SubmissionCreateRequest(file_url="https://s3.local/hack.zip"),
            student=other_student_user,
        )
    assert exc.value.code == "ENROLLMENT_REQUIRED"


def test_submit_project_revoked_enrollment_rejected(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Revoked enrollment blocks submission."""
    _, lesson = course_hierarchy
    active_enrollment.status = ENROLLMENT_STATUS_REVOKED
    db_session.flush()

    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Async Project",
            instructions="Do the project.",
            max_score=100.0,
        ),
        actor_id=super_admin_user.id,
    )

    with pytest.raises(ForbiddenException) as exc:
        assignment_service.submit_project(
            session=db_session,
            assignment_id=assignment.id,
            data=SubmissionCreateRequest(file_url="https://s3.local/hack.zip"),
            student=student_user,
        )
    assert exc.value.code == "ENROLLMENT_REVOKED"


def test_submit_project_expired_enrollment_rejected(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Expired enrollment blocks submission."""
    _, lesson = course_hierarchy
    active_enrollment.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.flush()

    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Async Project",
            instructions="Do the project.",
            max_score=100.0,
        ),
        actor_id=super_admin_user.id,
    )

    with pytest.raises(ForbiddenException) as exc:
        assignment_service.submit_project(
            session=db_session,
            assignment_id=assignment.id,
            data=SubmissionCreateRequest(file_url="https://s3.local/hack.zip"),
            student=student_user,
        )
    assert exc.value.code == "ENROLLMENT_EXPIRED"


def test_submit_project_unverified_email_rejected(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Unverified email blocks submission."""
    _, lesson = course_hierarchy
    student_user.is_verified = False
    db_session.flush()

    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Async Project",
            instructions="Do the project.",
            max_score=100.0,
        ),
        actor_id=super_admin_user.id,
    )

    with pytest.raises(ForbiddenException) as exc:
        assignment_service.submit_project(
            session=db_session,
            assignment_id=assignment.id,
            data=SubmissionCreateRequest(file_url="https://s3.local/hack.zip"),
            student=student_user,
        )
    assert exc.value.code == "EMAIL_NOT_VERIFIED"


def test_submit_project_deadline_enforcement(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Past due date with allow_late=False rejects; allow_late=True allows."""
    _, lesson = course_hierarchy
    past_due = datetime.now(timezone.utc) - timedelta(days=2)

    # 1. allow_late = False
    assignment_strict = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Strict Assignment",
            instructions="Strict",
            max_score=100.0,
            allow_late=False,
            due_date=past_due,
        ),
        actor_id=super_admin_user.id,
    )

    with pytest.raises(BadRequestException) as exc:
        assignment_service.submit_project(
            session=db_session,
            assignment_id=assignment_strict.id,
            data=SubmissionCreateRequest(file_url="https://s3.local/late.zip"),
            student=student_user,
        )
    assert exc.value.code == "DEADLINE_PASSED"

    # 2. Update to allow_late = True
    assignment_service.update_assignment(
        session=db_session,
        assignment_id=assignment_strict.id,
        data=AssignmentUpdateRequest(allow_late=True),
        actor_id=super_admin_user.id,
    )

    # Now submission succeeds
    sub = assignment_service.submit_project(
        session=db_session,
        assignment_id=assignment_strict.id,
        data=SubmissionCreateRequest(file_url="https://s3.local/late_allowed.zip"),
        student=student_user,
    )
    assert sub.attempt_no == 1


# =============================================================================
# 3. Rubric Grading & Weighted Score Tests (TASK703)
# =============================================================================

def test_grade_submission_weighted_score_calculation(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    staff_user: User,
    super_admin_user: User,
):
    """Grading evaluates criteria points with weights and computes total score."""
    _, lesson = course_hierarchy
    rubric_in = RubricCreateRequest(
        title="Grading Rubric",
        criteria=[
            RubricCriteriaCreateRequest(
                title="Design Patterns",
                max_points=50.0,
                weight=1.0,
            ),
            RubricCriteriaCreateRequest(
                title="Test Coverage",
                max_points=50.0,
                weight=1.0,
            ),
        ],
    )
    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Async Project",
            instructions="Do the project.",
            max_score=100.0,
            rubric=rubric_in,
        ),
        actor_id=super_admin_user.id,
    )

    sub = assignment_service.submit_project(
        db_session,
        assignment.id,
        SubmissionCreateRequest(file_url="https://s3.local/work.zip"),
        student_user,
    )

    crit1_id = assignment.active_rubric.criteria[0].id
    crit2_id = assignment.active_rubric.criteria[1].id

    grade_req = GradeSubmissionRequest(
        scores=[
            RubricScoreInput(criteria_id=crit1_id, points_awarded=45.0, feedback="Clean patterns"),
            RubricScoreInput(criteria_id=crit2_id, points_awarded=40.0, feedback="Good coverage"),
        ],
        overall_feedback="Excellent submission!",
    )

    graded = assignment_service.grade_submission(
        session=db_session,
        submission_id=sub.id,
        data=grade_req,
        grader=staff_user,
    )

    assert graded.status == SUBMISSION_STATUS_GRADED
    assert graded.final_score == 85.0
    assert graded.feedback == "Excellent submission!"
    assert graded.graded_by == staff_user.id
    assert len(graded.rubric_scores) == 2

    # Verify outbox event for student
    outbox = db_session.execute(
        select(NotificationOutbox).filter(NotificationOutbox.event_type == "SUBMISSION_GRADED")
    ).scalar_one_or_none()
    assert outbox is not None
    assert outbox.recipient == student_user.email
    assert outbox.payload["final_score"] == 85.0

    # Verify audit log
    audit = db_session.execute(
        select(AuditLog).filter(AuditLog.action == "ASSIGNMENT_GRADED")
    ).scalar_one_or_none()
    assert audit is not None
    assert audit.resource_id == str(sub.id)


def test_grade_submission_score_capped_at_max_score(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    staff_user: User,
    super_admin_user: User,
):
    """Calculated score is capped at assignment.max_score."""
    _, lesson = course_hierarchy
    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Capped Assignment",
            instructions="Instructions",
            max_score=80.0,  # Max score is 80
            rubric=RubricCreateRequest(
                title="Bonus Rubric",
                criteria=[
                    RubricCriteriaCreateRequest(
                        title="Work",
                        max_points=100.0,
                        weight=1.0,
                    )
                ],
            ),
        ),
        actor_id=super_admin_user.id,
    )

    sub = assignment_service.submit_project(
        db_session,
        assignment.id,
        SubmissionCreateRequest(file_url="https://s3.local/work.zip"),
        student_user,
    )

    crit_id = assignment.active_rubric.criteria[0].id
    graded = assignment_service.grade_submission(
        session=db_session,
        submission_id=sub.id,
        data=GradeSubmissionRequest(
            scores=[RubricScoreInput(criteria_id=crit_id, points_awarded=95.0)],
        ),
        grader=staff_user,
    )

    # 95 awarded points capped at max_score of 80.0
    assert graded.final_score == 80.0


def test_grade_submission_criteria_points_out_of_bounds(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    staff_user: User,
    super_admin_user: User,
):
    """Points awarded outside [0, max_points] raise BadRequestException."""
    _, lesson = course_hierarchy
    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Assignment",
            instructions="Instructions",
            max_score=100.0,
            rubric=RubricCreateRequest(
                title="Rubric",
                criteria=[
                    RubricCriteriaCreateRequest(
                        title="Section 1",
                        max_points=50.0,
                    )
                ],
            ),
        ),
        actor_id=super_admin_user.id,
    )

    sub = assignment_service.submit_project(
        db_session,
        assignment.id,
        SubmissionCreateRequest(file_url="https://s3.local/work.zip"),
        student_user,
    )

    crit_id = assignment.active_rubric.criteria[0].id

    # Case 1: points > max_points
    with pytest.raises(BadRequestException) as exc1:
        assignment_service.grade_submission(
            session=db_session,
            submission_id=sub.id,
            data=GradeSubmissionRequest(
                scores=[RubricScoreInput(criteria_id=crit_id, points_awarded=55.0)]
            ),
            grader=staff_user,
        )
    assert exc1.value.code == "INVALID_CRITERIA_POINTS"

    # Case 2: points < 0 (rejected at Pydantic schema validation boundary)
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RubricScoreInput(criteria_id=crit_id, points_awarded=-5.0)


def test_grade_submission_incomplete_criteria_scoring(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    staff_user: User,
    super_admin_user: User,
):
    """Omitting any rubric criteria raises BadRequestException."""
    _, lesson = course_hierarchy
    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Assignment",
            instructions="Instructions",
            max_score=100.0,
            rubric=RubricCreateRequest(
                title="Rubric",
                criteria=[
                    RubricCriteriaCreateRequest(title="Crit 1", max_points=50.0),
                    RubricCriteriaCreateRequest(title="Crit 2", max_points=50.0),
                ],
            ),
        ),
        actor_id=super_admin_user.id,
    )

    sub = assignment_service.submit_project(
        db_session,
        assignment.id,
        SubmissionCreateRequest(file_url="https://s3.local/work.zip"),
        student_user,
    )

    crit1_id = assignment.active_rubric.criteria[0].id
    with pytest.raises(BadRequestException) as exc:
        assignment_service.grade_submission(
            session=db_session,
            submission_id=sub.id,
            data=GradeSubmissionRequest(
                scores=[RubricScoreInput(criteria_id=crit1_id, points_awarded=40.0)]
            ),
            grader=staff_user,
        )
    assert exc.value.code == "INCOMPLETE_RUBRIC_EVALUATION"


# =============================================================================
# 4. Super Admin Grade Override Tests (TASK704)
# =============================================================================

def test_override_grade_success(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    staff_user: User,
    super_admin_user: User,
):
    """Super Admin adjusts finalized grade with justification; outbox and audit recorded."""
    _, lesson = course_hierarchy
    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Assignment",
            instructions="Instructions",
            max_score=100.0,
            rubric=RubricCreateRequest(
                title="Rubric",
                criteria=[RubricCriteriaCreateRequest(title="Crit 1", max_points=100.0)],
            ),
        ),
        actor_id=super_admin_user.id,
    )

    sub = assignment_service.submit_project(
        db_session,
        assignment.id,
        SubmissionCreateRequest(file_url="https://s3.local/work.zip"),
        student_user,
    )

    crit_id = assignment.active_rubric.criteria[0].id
    assignment_service.grade_submission(
        session=db_session,
        submission_id=sub.id,
        data=GradeSubmissionRequest(
            scores=[RubricScoreInput(criteria_id=crit_id, points_awarded=65.0)],
        ),
        grader=staff_user,
    )

    # Super Admin applies override
    override_resp = assignment_service.override_grade(
        session=db_session,
        submission_id=sub.id,
        data=GradeOverrideRequest(
            new_score=85.0,
            reason="Appeal granted after secondary review of async race condition mitigation.",
        ),
        admin=super_admin_user,
    )

    assert override_resp.original_score == 65.0
    assert override_resp.overridden_score == 85.0
    assert override_resp.overridden_by == super_admin_user.id

    # Verify submission's final_score is updated
    updated_sub = assignment_service.get_submission(db_session, sub.id, super_admin_user)
    assert updated_sub.final_score == 85.0
    assert len(updated_sub.grade_overrides) == 1

    # Verify outbox event for student
    outbox = db_session.execute(
        select(NotificationOutbox).filter(NotificationOutbox.event_type == "GRADE_OVERRIDDEN")
    ).scalar_one_or_none()
    assert outbox is not None
    assert outbox.recipient == student_user.email
    assert outbox.payload["new_score"] == 85.0

    # Verify audit log
    audit = db_session.execute(
        select(AuditLog).filter(AuditLog.action == "GRADE_OVERRIDDEN")
    ).scalar_one_or_none()
    assert audit is not None
    assert audit.resource_id == str(sub.id)


def test_override_grade_rejects_ungraded_submission(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Cannot override score for an un-graded submission."""
    _, lesson = course_hierarchy
    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Assignment",
            instructions="Instructions",
            max_score=100.0,
        ),
        actor_id=super_admin_user.id,
    )

    sub = assignment_service.submit_project(
        db_session,
        assignment.id,
        SubmissionCreateRequest(file_url="https://s3.local/work.zip"),
        student_user,
    )

    with pytest.raises(BadRequestException) as exc:
        assignment_service.override_grade(
            session=db_session,
            submission_id=sub.id,
            data=GradeOverrideRequest(new_score=90.0, reason="Premature override"),
            admin=super_admin_user,
        )
    assert exc.value.code == "SUBMISSION_NOT_GRADED"


def test_override_grade_rejects_invalid_score_bounds(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    staff_user: User,
    super_admin_user: User,
):
    """Override score cannot be negative or exceed assignment max_score."""
    _, lesson = course_hierarchy
    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Assignment",
            instructions="Instructions",
            max_score=100.0,
            rubric=RubricCreateRequest(
                title="Rubric",
                criteria=[RubricCriteriaCreateRequest(title="Crit", max_points=100.0)],
            ),
        ),
        actor_id=super_admin_user.id,
    )

    sub = assignment_service.submit_project(
        db_session,
        assignment.id,
        SubmissionCreateRequest(file_url="https://s3.local/work.zip"),
        student_user,
    )

    crit_id = assignment.active_rubric.criteria[0].id
    assignment_service.grade_submission(
        session=db_session,
        submission_id=sub.id,
        data=GradeSubmissionRequest(scores=[RubricScoreInput(criteria_id=crit_id, points_awarded=70.0)]),
        grader=staff_user,
    )

    # Exceeds max score
    with pytest.raises(BadRequestException) as exc:
        assignment_service.override_grade(
            session=db_session,
            submission_id=sub.id,
            data=GradeOverrideRequest(new_score=110.0, reason="Too generous"),
            admin=super_admin_user,
        )
    assert exc.value.code == "INVALID_OVERRIDE_SCORE"


# =============================================================================
# 5. Authorization & Submission Inspection Tests
# =============================================================================

def test_get_submission_ownership_enforcement(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    other_student_user: User,
    active_enrollment: Enrollment,
    staff_user: User,
    super_admin_user: User,
):
    """Student cannot inspect another student's submission (anti-IDOR)."""
    _, lesson = course_hierarchy
    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Assignment",
            instructions="Instructions",
            max_score=100.0,
        ),
        actor_id=super_admin_user.id,
    )

    sub = assignment_service.submit_project(
        db_session,
        assignment.id,
        SubmissionCreateRequest(file_url="https://s3.local/alice.zip"),
        student_user,
    )

    # Alice (owner) can view
    resp_alice = assignment_service.get_submission(db_session, sub.id, student_user)
    assert resp_alice.id == sub.id

    # Staff can view
    resp_staff = assignment_service.get_submission(db_session, sub.id, staff_user)
    assert resp_staff.id == sub.id

    # Bob (stranger student) is blocked
    with pytest.raises(ForbiddenException) as exc:
        assignment_service.get_submission(db_session, sub.id, other_student_user)
    assert exc.value.code == "SUBMISSION_ACCESS_DENIED"


def test_list_assignment_submissions_and_own_submissions(
    db_session: Session,
    assignment_service: AssignmentService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Test pagination and filtering of submissions."""
    _, lesson = course_hierarchy
    assignment = assignment_service.create_assignment(
        session=db_session,
        lesson_id=lesson.id,
        data=AssignmentCreateRequest(
            title="Assignment",
            instructions="Instructions",
            max_score=100.0,
        ),
        actor_id=super_admin_user.id,
    )

    assignment_service.submit_project(
        db_session,
        assignment.id,
        SubmissionCreateRequest(file_url="https://s3.local/attempt1.zip"),
        student_user,
    )
    assignment_service.submit_project(
        db_session,
        assignment.id,
        SubmissionCreateRequest(file_url="https://s3.local/attempt2.zip"),
        student_user,
    )

    # List submissions for assignment
    eval_list = assignment_service.list_assignment_submissions(
        session=db_session,
        assignment_id=assignment.id,
        page=1,
        size=10,
    )
    assert eval_list.total == 2
    assert len(eval_list.items) == 2

    # List student's own submissions
    own_list = assignment_service.list_own_submissions(
        session=db_session,
        student_id=student_user.id,
        assignment_id=assignment.id,
    )
    assert own_list.total == 2
    assert own_list.items[0].attempt_no == 2
    assert own_list.items[1].attempt_no == 1
