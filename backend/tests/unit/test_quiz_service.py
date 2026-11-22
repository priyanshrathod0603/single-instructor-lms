"""Unit tests for QuizService domain workflows.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 4, Tables 20-24)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Sections 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK801-TASK805)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-008, ADR-011, ADR-012, ADR-013)
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
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.course import COURSE_STATUS_PUBLISHED, Course, CourseRevision
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.enrollment import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_EXPIRED,
    ENROLLMENT_STATUS_REVOKED,
    Enrollment,
)
from app.models.notification import NotificationOutbox
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
)
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
from app.schemas.quiz import (
    AutosaveAnswerRequest,
    QuestionCreateRequest,
    QuestionOptionCreateRequest,
    QuizAnswerSubmissionInput,
    QuizCreateRequest,
    QuizSubmitRequest,
    QuizUpdateRequest,
)
from app.services.quiz_service import QuizService


@pytest.fixture
def db_session():
    """In-memory SQLite session seeded with canonical system roles."""
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
        email="staff@lms.local",
        full_name="Staff Evaluator",
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
        email="admin@lms.local",
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
        title="Async Python Architecture",
        slug="async-python-architecture",
        headline="Production-grade asynchronous architectures",
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
        title="Lesson 1 Quiz: Async Basics",
        lesson_type="QUIZ",
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
    """Fixture creating active course enrollment for student_user."""
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
def quiz_service() -> QuizService:
    """QuizService instance."""
    return QuizService()


# =============================================================================
# 1. Quiz & Question Configuration Tests (TASK801)
# =============================================================================

def test_create_quiz_success(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    super_admin_user: User,
):
    """Admin creates quiz configuration; audit log created."""
    _, lesson = course_hierarchy
    data = QuizCreateRequest(
        title="Async Fundamentals Quiz",
        description="Test basic event loop understanding",
        pass_percentage=75,
        time_limit_minutes=25,
        shuffle_questions=True,
        max_attempts=2,
    )

    resp = quiz_service.create_quiz(
        session=db_session,
        lesson_id=lesson.id,
        data=data,
        actor_id=super_admin_user.id,
    )

    assert resp.title == "Async Fundamentals Quiz"
    assert resp.pass_percentage == 75
    assert resp.time_limit_minutes == 25
    assert resp.max_attempts == 2

    audit = db_session.execute(
        select(AuditLog).filter(AuditLog.action == "QUIZ_CREATED")
    ).scalar_one_or_none()
    assert audit is not None
    assert audit.resource_id == str(resp.id)


def test_create_quiz_duplicate_on_lesson_rejected(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    super_admin_user: User,
):
    """Cannot create two quizzes for the same curriculum lesson (1:1 constraint)."""
    _, lesson = course_hierarchy
    data = QuizCreateRequest(title="Quiz 1")
    quiz_service.create_quiz(db_session, lesson.id, data, super_admin_user.id)

    with pytest.raises(BadRequestException) as exc:
        quiz_service.create_quiz(db_session, lesson.id, data, super_admin_user.id)
    assert exc.value.code == "QUIZ_ALREADY_EXISTS"


def test_update_quiz_success(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    super_admin_user: User,
):
    """Admin updates quiz settings; audit log created."""
    _, lesson = course_hierarchy
    created = quiz_service.create_quiz(db_session, lesson.id, QuizCreateRequest(title="Initial"), super_admin_user.id)

    updated = quiz_service.update_quiz(
        session=db_session,
        quiz_id=created.id,
        data=QuizUpdateRequest(title="Updated Title", time_limit_minutes=45),
        actor_id=super_admin_user.id,
    )

    assert updated.title == "Updated Title"
    assert updated.time_limit_minutes == 45


def test_add_question_validation(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    super_admin_user: User,
):
    """Questions validate option correctness counts based on question_type."""
    _, lesson = course_hierarchy
    quiz = quiz_service.create_quiz(db_session, lesson.id, QuizCreateRequest(title="Quiz"), super_admin_user.id)

    # 1. MCQ_SINGLE with 0 correct options -> rejected
    with pytest.raises(BadRequestException) as exc1:
        quiz_service.add_question(
            session=db_session,
            quiz_id=quiz.id,
            data=QuestionCreateRequest(
                question_type=QUESTION_TYPE_MCQ_SINGLE,
                prompt="Prompt?",
                options=[
                    QuestionOptionCreateRequest(option_text="Opt 1", is_correct=False),
                    QuestionOptionCreateRequest(option_text="Opt 2", is_correct=False),
                ],
            ),
            actor_id=super_admin_user.id,
        )
    assert exc1.value.code == "INVALID_CORRECT_OPTIONS_COUNT"

    # 2. MCQ_SINGLE with 2 correct options -> rejected
    with pytest.raises(BadRequestException) as exc2:
        quiz_service.add_question(
            session=db_session,
            quiz_id=quiz.id,
            data=QuestionCreateRequest(
                question_type=QUESTION_TYPE_MCQ_SINGLE,
                prompt="Prompt?",
                options=[
                    QuestionOptionCreateRequest(option_text="Opt 1", is_correct=True),
                    QuestionOptionCreateRequest(option_text="Opt 2", is_correct=True),
                ],
            ),
            actor_id=super_admin_user.id,
        )
    assert exc2.value.code == "INVALID_CORRECT_OPTIONS_COUNT"

    # 3. Valid MCQ_SINGLE with exactly 1 correct option -> succeeds
    q = quiz_service.add_question(
        session=db_session,
        quiz_id=quiz.id,
        data=QuestionCreateRequest(
            question_type=QUESTION_TYPE_MCQ_SINGLE,
            prompt="Prompt?",
            options=[
                QuestionOptionCreateRequest(option_text="Opt 1", is_correct=True),
                QuestionOptionCreateRequest(option_text="Opt 2", is_correct=False),
            ],
        ),
        actor_id=super_admin_user.id,
    )
    assert len(q.options) == 2


# =============================================================================
# 2. Bulk CSV Question Bank Importer Tests (TASK802)
# =============================================================================

def test_import_questions_from_csv_success(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    super_admin_user: User,
):
    """Bulk CSV imports various question types atomically; audit log recorded."""
    _, lesson = course_hierarchy
    quiz = quiz_service.create_quiz(db_session, lesson.id, QuizCreateRequest(title="CSV Quiz"), super_admin_user.id)

    csv_data = """question_type,prompt,points,explanation,option_1,option_2,option_3,option_4,correct_options
MCQ_SINGLE,"What does asyncio run on?",2.0,"Single-threaded event loop","Event Loop","Multi-threaded pool","GPU cluster","Process fork","1"
MCQ_MULTI,"Which methods are awaitable?",3.0,"Coroutines and Tasks are awaitable","async def fn()","asyncio.Task","os.getpid()","time.sleep()","1,2"
TRUE_FALSE,"Asyncio code requires an active event loop.",1.0,"Event loop schedules coroutines.","True","False","","","1"
TEXT_SHORT,"Keyword to define a coroutine?",1.0,"async keyword defines coroutines","async","","","","1"
"""

    resp = quiz_service.import_questions_from_csv(
        session=db_session,
        quiz_id=quiz.id,
        csv_content=csv_data,
        actor_id=super_admin_user.id,
    )

    assert resp.imported_count == 4
    assert len(resp.question_ids) == 4

    # Verify questions and options were persisted
    q_list = quiz_service.repo.get_questions_for_quiz(db_session, quiz.id)
    assert len(q_list) == 4
    assert q_list[0].question_type == QUESTION_TYPE_MCQ_SINGLE
    assert q_list[1].question_type == QUESTION_TYPE_MCQ_MULTI
    assert q_list[2].question_type == QUESTION_TYPE_TRUE_FALSE
    assert q_list[3].question_type == QUESTION_TYPE_TEXT_SHORT


def test_import_questions_from_csv_validation_errors(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    super_admin_user: User,
):
    """Invalid CSV content is rejected with appropriate error codes."""
    _, lesson = course_hierarchy
    quiz = quiz_service.create_quiz(db_session, lesson.id, QuizCreateRequest(title="CSV Quiz"), super_admin_user.id)

    # 1. Empty CSV
    with pytest.raises(BadRequestException) as exc1:
        quiz_service.import_questions_from_csv(db_session, quiz.id, "", super_admin_user.id)
    assert exc1.value.code == "EMPTY_CSV"

    # 2. Missing headers
    with pytest.raises(BadRequestException) as exc2:
        quiz_service.import_questions_from_csv(db_session, quiz.id, "bad,header\n1,2", super_admin_user.id)
    assert exc2.value.code == "MISSING_CSV_HEADERS"

    # 3. Invalid question type
    bad_type_csv = """question_type,prompt,points,explanation,option_1,option_2,correct_options
INVALID_TYPE,"What is this?",1.0,"No explanation","A","B","1"
"""
    with pytest.raises(BadRequestException) as exc3:
        quiz_service.import_questions_from_csv(db_session, quiz.id, bad_type_csv, super_admin_user.id)
    assert exc3.value.code == "INVALID_CSV_ROW"


# =============================================================================
# 3. Server-Authoritative Timer & Attempt Initiation Tests (TASK803)
# =============================================================================

def test_start_quiz_attempt_happy_path(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Enrolled student starts attempt; server timer initialized; answers concealed."""
    _, lesson = course_hierarchy
    quiz = quiz_service.create_quiz(
        db_session,
        lesson.id,
        QuizCreateRequest(
            title="Timed Assessment",
            time_limit_minutes=30,
            questions=[
                QuestionCreateRequest(
                    question_type=QUESTION_TYPE_MCQ_SINGLE,
                    prompt="What is asyncio?",
                    explanation="Secret explanation",
                    options=[
                        QuestionOptionCreateRequest(option_text="Async runtime", is_correct=True),
                        QuestionOptionCreateRequest(option_text="Database", is_correct=False),
                    ],
                )
            ],
        ),
        super_admin_user.id,
    )

    attempt_resp = quiz_service.start_quiz_attempt(
        session=db_session,
        quiz_id=quiz.id,
        student=student_user,
    )

    assert attempt_resp.attempt_no == 1
    assert attempt_resp.time_limit_minutes == 30
    assert attempt_resp.server_deadline is not None
    assert len(attempt_resp.questions) == 1

    # CRITICAL: Explanation and is_correct are strictly concealed!
    q0 = attempt_resp.questions[0]
    assert q0.explanation is None
    for opt in q0.options:
        assert opt.is_correct is None

    # Audit log
    audit = db_session.execute(
        select(AuditLog).filter(AuditLog.action == "QUIZ_ATTEMPT_STARTED")
    ).scalar_one_or_none()
    assert audit is not None


def test_start_quiz_attempt_unenrolled_rejected(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    other_student_user: User,
    super_admin_user: User,
):
    """Unenrolled student cannot initiate quiz attempt."""
    _, lesson = course_hierarchy
    quiz = quiz_service.create_quiz(
        db_session,
        lesson.id,
        QuizCreateRequest(
            title="Quiz",
            questions=[
                QuestionCreateRequest(
                    question_type=QUESTION_TYPE_TRUE_FALSE,
                    prompt="TF Prompt",
                    options=[
                        QuestionOptionCreateRequest(option_text="True", is_correct=True),
                        QuestionOptionCreateRequest(option_text="False", is_correct=False),
                    ],
                )
            ],
        ),
        super_admin_user.id,
    )

    with pytest.raises(ForbiddenException) as exc:
        quiz_service.start_quiz_attempt(db_session, quiz.id, other_student_user)
    assert exc.value.code == "ENROLLMENT_REQUIRED"


def test_start_quiz_attempt_max_attempts_enforced(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Student cannot exceed max_attempts configuration."""
    _, lesson = course_hierarchy
    quiz = quiz_service.create_quiz(
        db_session,
        lesson.id,
        QuizCreateRequest(
            title="Strict Quiz",
            max_attempts=1,  # Only 1 attempt allowed
            time_limit_minutes=0,
            questions=[
                QuestionCreateRequest(
                    question_type=QUESTION_TYPE_TRUE_FALSE,
                    prompt="TF Prompt",
                    options=[
                        QuestionOptionCreateRequest(option_text="True", is_correct=True),
                        QuestionOptionCreateRequest(option_text="False", is_correct=False),
                    ],
                )
            ],
        ),
        super_admin_user.id,
    )

    # 1. First attempt succeeds
    att1 = quiz_service.start_quiz_attempt(db_session, quiz.id, student_user)
    quiz_service.submit_quiz_attempt(db_session, att1.attempt_id, None, student_user)

    # 2. Second attempt rejected
    with pytest.raises(BadRequestException) as exc:
        quiz_service.start_quiz_attempt(db_session, quiz.id, student_user)
    assert exc.value.code == "MAX_ATTEMPTS_EXCEEDED"


# =============================================================================
# 4. Incremental Answer Autosave Tests (TASK804)
# =============================================================================

def test_autosave_answer_happy_path(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Autosaving response updates answer row without page reload."""
    _, lesson = course_hierarchy
    quiz = quiz_service.create_quiz(
        db_session,
        lesson.id,
        QuizCreateRequest(
            title="Autosave Quiz",
            questions=[
                QuestionCreateRequest(
                    question_type=QUESTION_TYPE_MCQ_SINGLE,
                    prompt="Prompt",
                    options=[
                        QuestionOptionCreateRequest(option_text="A", is_correct=True),
                        QuestionOptionCreateRequest(option_text="B", is_correct=False),
                    ],
                )
            ],
        ),
        super_admin_user.id,
    )

    attempt_resp = quiz_service.start_quiz_attempt(db_session, quiz.id, student_user)
    q_id = attempt_resp.questions[0].id
    opt_a_id = attempt_resp.questions[0].options[0].id
    opt_b_id = attempt_resp.questions[0].options[1].id

    # 1. Autosave option A
    save1 = quiz_service.autosave_answer(
        session=db_session,
        attempt_id=attempt_resp.attempt_id,
        data=AutosaveAnswerRequest(question_id=q_id, selected_option_ids=[opt_a_id]),
        student=student_user,
    )
    assert save1.success is True

    # 2. Update autosave to option B (idempotent UPSERT)
    save2 = quiz_service.autosave_answer(
        session=db_session,
        attempt_id=attempt_resp.attempt_id,
        data=AutosaveAnswerRequest(question_id=q_id, selected_option_ids=[opt_b_id]),
        student=student_user,
    )
    assert save2.success is True

    # Check persistence: exactly 1 answer row exists with opt_b
    answers = quiz_service.repo.get_answers_for_attempt(db_session, attempt_resp.attempt_id)
    assert len(answers) == 1
    assert answers[0].selected_option_ids == [str(opt_b_id)]


def test_autosave_answer_timer_expiration(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Autosave past deadline (+30s grace) marks attempt EXPIRED and rejects request."""
    _, lesson = course_hierarchy
    quiz = quiz_service.create_quiz(
        db_session,
        lesson.id,
        QuizCreateRequest(
            title="Fast Quiz",
            time_limit_minutes=1,  # 1 minute timer
            questions=[
                QuestionCreateRequest(
                    question_type=QUESTION_TYPE_TRUE_FALSE,
                    prompt="Prompt",
                    options=[
                        QuestionOptionCreateRequest(option_text="True", is_correct=True),
                        QuestionOptionCreateRequest(option_text="False", is_correct=False),
                    ],
                )
            ],
        ),
        super_admin_user.id,
    )

    attempt_resp = quiz_service.start_quiz_attempt(db_session, quiz.id, student_user)
    attempt = db_session.get(QuizAttempt, attempt_resp.attempt_id)

    # Artificially age started_at by 2 minutes (exceeds 1m + 30s grace)
    attempt.started_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    db_session.flush()

    q_id = attempt_resp.questions[0].id
    opt_id = attempt_resp.questions[0].options[0].id

    with pytest.raises(BadRequestException) as exc:
        quiz_service.autosave_answer(
            session=db_session,
            attempt_id=attempt.id,
            data=AutosaveAnswerRequest(question_id=q_id, selected_option_ids=[opt_id]),
            student=student_user,
        )
    assert exc.value.code == "QUIZ_ATTEMPT_EXPIRED"
    assert attempt.status == ATTEMPT_STATUS_EXPIRED


# =============================================================================
# 5. Attempt Finalization & Scoring Tests (TASK805)
# =============================================================================

def test_submit_quiz_attempt_scoring_and_passing(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Student answers questions, submits within time; server calculates score and pass status."""
    _, lesson = course_hierarchy
    quiz = quiz_service.create_quiz(
        db_session,
        lesson.id,
        QuizCreateRequest(
            title="Scored Assessment",
            pass_percentage=70,
            questions=[
                QuestionCreateRequest(
                    question_type=QUESTION_TYPE_MCQ_SINGLE,
                    prompt="Q1",
                    points=2.0,
                    explanation="Exp 1",
                    options=[
                        QuestionOptionCreateRequest(option_text="Correct", is_correct=True),
                        QuestionOptionCreateRequest(option_text="Wrong", is_correct=False),
                    ],
                ),
                QuestionCreateRequest(
                    question_type=QUESTION_TYPE_TRUE_FALSE,
                    prompt="Q2",
                    points=1.0,
                    explanation="Exp 2",
                    options=[
                        QuestionOptionCreateRequest(option_text="True", is_correct=True),
                        QuestionOptionCreateRequest(option_text="False", is_correct=False),
                    ],
                ),
                QuestionCreateRequest(
                    question_type=QUESTION_TYPE_TEXT_SHORT,
                    prompt="Q3",
                    points=1.0,
                    explanation="Exp 3",
                    options=[
                        QuestionOptionCreateRequest(option_text="Python", is_correct=True),
                    ],
                ),
            ],
        ),
        super_admin_user.id,
    )

    attempt_resp = quiz_service.start_quiz_attempt(db_session, quiz.id, student_user)
    q1 = quiz.questions[0]
    q2 = quiz.questions[1]
    q3 = quiz.questions[2]

    # Q1: Correct (2.0 pts)
    q1_corr_opt = [o.id for o in q1.options if o.is_correct][0]
    quiz_service.autosave_answer(
        db_session, attempt_resp.attempt_id,
        AutosaveAnswerRequest(question_id=q1.id, selected_option_ids=[q1_corr_opt]),
        student_user,
    )

    # Q2: Correct (1.0 pts)
    q2_corr_opt = [o.id for o in q2.options if o.is_correct][0]
    quiz_service.autosave_answer(
        db_session, attempt_resp.attempt_id,
        AutosaveAnswerRequest(question_id=q2.id, selected_option_ids=[q2_corr_opt]),
        student_user,
    )

    # Q3: Wrong (0 pts, answered 'Java' instead of 'Python')
    quiz_service.autosave_answer(
        db_session, attempt_resp.attempt_id,
        AutosaveAnswerRequest(question_id=q3.id, text_response="Java"),
        student_user,
    )

    # Submit attempt (Total: 3/4 pts = 75.0% -> Passed because pass_percentage=70)
    result = quiz_service.submit_quiz_attempt(
        session=db_session,
        attempt_id=attempt_resp.attempt_id,
        data=None,
        student=student_user,
    )

    assert result.status == ATTEMPT_STATUS_SUBMITTED
    assert result.score == 75.0
    assert result.is_passed is True
    assert result.completed_at is not None

    # Review reveals explanations and correct options after submission
    assert len(result.answers) == 3
    for ans_rev in result.answers:
        assert ans_rev.explanation is not None
        for opt in ans_rev.options:
            assert opt.is_correct is not None

    # Outbox event emitted
    outbox = db_session.execute(
        select(NotificationOutbox).filter(NotificationOutbox.event_type == "QUIZ_COMPLETED")
    ).scalar_one_or_none()
    assert outbox is not None
    assert outbox.recipient == student_user.email
    assert outbox.payload["score"] == 75.0
    assert outbox.payload["is_passed"] is True


def test_submit_quiz_attempt_past_deadline_marks_expired(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Submitting past deadline (+30s grace) marks attempt EXPIRED with 0 score."""
    _, lesson = course_hierarchy
    quiz = quiz_service.create_quiz(
        db_session,
        lesson.id,
        QuizCreateRequest(
            title="Fast Assessment",
            time_limit_minutes=10,
            questions=[
                QuestionCreateRequest(
                    question_type=QUESTION_TYPE_TRUE_FALSE,
                    prompt="Prompt",
                    options=[
                        QuestionOptionCreateRequest(option_text="True", is_correct=True),
                        QuestionOptionCreateRequest(option_text="False", is_correct=False),
                    ],
                )
            ],
        ),
        super_admin_user.id,
    )

    attempt_resp = quiz_service.start_quiz_attempt(db_session, quiz.id, student_user)
    attempt = db_session.get(QuizAttempt, attempt_resp.attempt_id)

    # Artificially age attempt start time past 10m + 30s grace
    attempt.started_at = datetime.now(timezone.utc) - timedelta(minutes=15)
    db_session.flush()

    result = quiz_service.submit_quiz_attempt(
        session=db_session,
        attempt_id=attempt.id,
        data=None,
        student=student_user,
    )

    assert result.status == ATTEMPT_STATUS_EXPIRED
    assert result.score == 0.0
    assert result.is_passed is False

    # Outbox event QUIZ_EXPIRED emitted
    outbox = db_session.execute(
        select(NotificationOutbox).filter(NotificationOutbox.event_type == "QUIZ_EXPIRED")
    ).scalar_one_or_none()
    assert outbox is not None
    assert outbox.recipient == student_user.email


def test_get_attempt_result_access_control(
    db_session: Session,
    quiz_service: QuizService,
    course_hierarchy: tuple[Course, CurriculumLesson],
    student_user: User,
    other_student_user: User,
    staff_user: User,
    active_enrollment: Enrollment,
    super_admin_user: User,
):
    """Student cannot inspect another student's attempt; staff can inspect."""
    _, lesson = course_hierarchy
    quiz = quiz_service.create_quiz(
        db_session,
        lesson.id,
        QuizCreateRequest(
            title="Quiz",
            questions=[
                QuestionCreateRequest(
                    question_type=QUESTION_TYPE_TRUE_FALSE,
                    prompt="Prompt",
                    options=[
                        QuestionOptionCreateRequest(option_text="True", is_correct=True),
                        QuestionOptionCreateRequest(option_text="False", is_correct=False),
                    ],
                )
            ],
        ),
        super_admin_user.id,
    )

    attempt_resp = quiz_service.start_quiz_attempt(db_session, quiz.id, student_user)
    quiz_service.submit_quiz_attempt(db_session, attempt_resp.attempt_id, None, student_user)

    # Alice (owner) -> 200 OK
    res_alice = quiz_service.get_attempt_result(db_session, attempt_resp.attempt_id, student_user)
    assert res_alice.id == attempt_resp.attempt_id

    # Staff -> 200 OK
    res_staff = quiz_service.get_attempt_result(db_session, attempt_resp.attempt_id, staff_user)
    assert res_staff.id == attempt_resp.attempt_id

    # Bob (stranger) -> 403 Forbidden
    with pytest.raises(ForbiddenException) as exc:
        quiz_service.get_attempt_result(db_session, attempt_resp.attempt_id, other_student_user)
    assert exc.value.code == "ATTEMPT_ACCESS_DENIED"
