"""FastAPI REST API integration tests for Quizzes & Question Banks.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 4, Tables 20-24)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.6)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Sections 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK801-TASK805)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-008, ADR-011)
"""

from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.permissions import CANONICAL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.base import Base
from app.models.course import COURSE_STATUS_PUBLISHED, Course, CourseRevision
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.enrollment import ENROLLMENT_STATUS_ACTIVE, Enrollment
from app.models.permission import Permission, RolePermission
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    Role,
    User,
    UserRole,
)


@pytest.fixture
def db_session():
    """Provides isolated in-memory SQLite database session seeded with RBAC roles and permissions."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()

    # Seed canonical permissions
    for key, module, desc in CANONICAL_PERMISSIONS:
        session.add(Permission(id=key, module=module, description=desc))

    # Seed canonical roles and permission mappings
    for r_id, p_keys in DEFAULT_ROLE_PERMISSIONS.items():
        role = Role(id=r_id, name=r_id.title())
        session.add(role)
        for pk in p_keys:
            session.add(RolePermission(role_id=r_id, permission_id=pk))

    session.flush()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def super_admin_user(db_session: Session) -> User:
    """Creates a Super Admin user."""
    user = User(
        email="superadmin@lms.local",
        full_name="Platform Owner",
        password_hash=hash_password("SuperSecure123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.get(Role, ROLE_SUPER_ADMIN)
    db_session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=user.id))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def staff_user(db_session: Session) -> User:
    """Creates a Staff user."""
    user = User(
        email="staff@lms.local",
        full_name="Staff Evaluator",
        password_hash=hash_password("StaffSecure123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.get(Role, ROLE_STAFF)
    db_session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=user.id))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def student_user(db_session: Session) -> User:
    """Creates an active, verified Student user."""
    user = User(
        email="student@lms.local",
        full_name="Enrolled Student",
        password_hash=hash_password("StudentPassword123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.get(Role, ROLE_STUDENT)
    db_session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=user.id))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_student_user(db_session: Session) -> User:
    """Creates a second active, verified Student user."""
    user = User(
        email="other_student@lms.local",
        full_name="Other Student",
        password_hash=hash_password("StudentPassword123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.get(Role, ROLE_STUDENT)
    db_session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=user.id))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def course_hierarchy(db_session: Session, super_admin_user: User) -> tuple[Course, CurriculumLesson]:
    """Creates Course -> Revision -> Section -> Lesson hierarchy."""
    course = Course(
        title="High-Performance Asynchronous Python",
        slug="high-performance-async-python",
        headline="Complete guide to asynchronous architectures",
        price_inr=699900,
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
        title="Section 1: Event Loops",
        sort_order=0,
    )
    db_session.add(section)
    db_session.flush()

    lesson = CurriculumLesson(
        section_id=section.id,
        title="Event Loop Quiz",
        lesson_type="QUIZ",
        sort_order=0,
        is_preview=False,
    )
    db_session.add(lesson)
    db_session.commit()
    db_session.refresh(course)
    db_session.refresh(lesson)
    return course, lesson


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """TestClient overriding get_db dependency."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth_headers(user: User) -> dict[str, str]:
    """Generates valid Authorization Bearer header for user."""
    from tests.conftest import create_test_auth_headers
    return create_test_auth_headers(user)


# =============================================================================
# 1. Quiz & Question Configuration API Tests (TASK801)
# =============================================================================

def test_create_and_manage_quiz_endpoints(
    client: TestClient,
    super_admin_user: User,
    student_user: User,
    course_hierarchy: tuple[Course, CurriculumLesson],
):
    """Admin configures quiz; student is forbidden; patch updates parameters."""
    _, lesson = course_hierarchy
    create_payload = {
        "title": "Event Loop Architecture Assessment",
        "description": "Evaluate non-blocking I/O fundamentals",
        "pass_percentage": 75,
        "time_limit_minutes": 20,
        "shuffle_questions": True,
        "max_attempts": 2,
    }

    # 1. Student unauthorized -> 403 Forbidden
    assert client.post(
        f"/api/v1/lessons/{lesson.id}/quiz",
        json=create_payload,
        headers=auth_headers(student_user),
    ).status_code == 403

    # 2. Admin authorized -> 201 Created
    create_resp = client.post(
        f"/api/v1/lessons/{lesson.id}/quiz",
        json=create_payload,
        headers=auth_headers(super_admin_user),
    )
    assert create_resp.status_code == 201
    quiz_data = create_resp.json()
    quiz_id = quiz_data["id"]
    assert quiz_data["title"] == "Event Loop Architecture Assessment"
    assert quiz_data["pass_percentage"] == 75

    # 3. Add individual question -> 201 Created
    question_payload = {
        "question_type": "MCQ_SINGLE",
        "prompt": "What executes coroutines in asyncio?",
        "points": 2.0,
        "explanation": "The event loop schedules and runs tasks.",
        "options": [
            {"option_text": "Event Loop", "is_correct": True},
            {"option_text": "Operating System Kernel", "is_correct": False},
            {"option_text": "GPU Shader", "is_correct": False},
        ],
    }
    q_resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json=question_payload,
        headers=auth_headers(super_admin_user),
    )
    assert q_resp.status_code == 201
    assert len(q_resp.json()["options"]) == 3

    # 4. PATCH quiz settings -> 200 OK
    patch_resp = client.patch(
        f"/api/v1/quizzes/{quiz_id}",
        json={"title": "Updated Quiz Title", "time_limit_minutes": 35},
        headers=auth_headers(super_admin_user),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["title"] == "Updated Quiz Title"
    assert patch_resp.json()["time_limit_minutes"] == 35


# =============================================================================
# 2. Bulk CSV Import API Tests (TASK802)
# =============================================================================

def test_bulk_csv_import_endpoint(
    client: TestClient,
    super_admin_user: User,
    course_hierarchy: tuple[Course, CurriculumLesson],
):
    """Admin bulk imports question bank via raw CSV body."""
    _, lesson = course_hierarchy
    create_resp = client.post(
        f"/api/v1/lessons/{lesson.id}/quiz",
        json={"title": "CSV Assessment"},
        headers=auth_headers(super_admin_user),
    )
    quiz_id = create_resp.json()["id"]

    csv_text = """question_type,prompt,points,explanation,option_1,option_2,option_3,option_4,correct_options
MCQ_SINGLE,"What does ACID stand for?",1.0,"Atomicity Consistency Isolation Durability","Atomicity Consistency Isolation Durability","Cats In Denmark","Async Code","Access Control","1"
TRUE_FALSE,"Is Python dynamically typed?",1.0,"Python is dynamically typed","True","False","","","1"
"""

    resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions/bulk-csv",
        content=csv_text,
        headers={**auth_headers(super_admin_user), "Content-Type": "text/csv"},
    )
    assert resp.status_code == 201
    assert resp.json()["imported_count"] == 2
    assert len(resp.json()["question_ids"]) == 2


# =============================================================================
# 3. Quiz Attempt, Autosave & Finalization API Tests (TASK803, TASK804, TASK805)
# =============================================================================

def test_quiz_attempt_full_workflow_endpoints(
    client: TestClient,
    db_session: Session,
    super_admin_user: User,
    staff_user: User,
    student_user: User,
    other_student_user: User,
    course_hierarchy: tuple[Course, CurriculumLesson],
):
    """Full lifecycle: start attempt -> autosave -> submit -> calculate score -> review."""
    course, lesson = course_hierarchy

    # 1. Admin creates quiz with 2 questions
    create_resp = client.post(
        f"/api/v1/lessons/{lesson.id}/quiz",
        json={
            "title": "Full Lifecycle Quiz",
            "time_limit_minutes": 20,
            "pass_percentage": 50,
            "questions": [
                {
                    "question_type": "MCQ_SINGLE",
                    "prompt": "Select True",
                    "points": 2.0,
                    "explanation": "True is true",
                    "options": [
                        {"option_text": "Correct Option", "is_correct": True},
                        {"option_text": "Wrong Option", "is_correct": False},
                    ],
                },
                {
                    "question_type": "TRUE_FALSE",
                    "prompt": "Is 2 + 2 = 4?",
                    "points": 2.0,
                    "explanation": "Basic math",
                    "options": [
                        {"option_text": "True", "is_correct": True},
                        {"option_text": "False", "is_correct": False},
                    ],
                },
            ],
        },
        headers=auth_headers(super_admin_user),
    )
    quiz_id = create_resp.json()["id"]

    # 2. Enroll student_user
    db_session.add(Enrollment(
        student_id=student_user.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        granted_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    # 3. Student starts attempt -> 201 Created
    start_resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts",
        headers=auth_headers(student_user),
    )
    assert start_resp.status_code == 201
    start_data = start_resp.json()
    attempt_id = start_data["attempt_id"]
    assert start_data["attempt_no"] == 1
    assert start_data["server_deadline"] is not None

    # Verify answers and explanations are CONCEALED from student
    for q in start_data["questions"]:
        assert q["explanation"] is None
        for opt in q["options"]:
            assert opt["is_correct"] is None

    q1 = start_data["questions"][0]
    q1_opt_id = q1["options"][0]["id"]

    # 4. Autosave answer for Q1 -> 200 OK
    autosave_resp = client.patch(
        f"/api/v1/quiz-attempts/{attempt_id}/autosave",
        json={"question_id": q1["id"], "selected_option_ids": [q1_opt_id]},
        headers=auth_headers(student_user),
    )
    assert autosave_resp.status_code == 200
    assert autosave_resp.json()["success"] is True

    # 5. Finalize / submit attempt -> 200 OK
    submit_resp = client.post(
        f"/api/v1/quiz-attempts/{attempt_id}/submit",
        headers=auth_headers(student_user),
    )
    assert submit_resp.status_code == 200
    res_data = submit_resp.json()
    assert res_data["status"] == "SUBMITTED"
    assert res_data["score"] is not None
    assert res_data["is_passed"] is not None

    # Review now reveals explanations and correct options
    assert res_data["answers"] is not None
    for ans in res_data["answers"]:
        assert ans["explanation"] is not None

    # 6. Anti-IDOR: Stranger student cannot inspect Alice's attempt -> 403 Forbidden
    assert client.get(
        f"/api/v1/quiz-attempts/{attempt_id}",
        headers=auth_headers(other_student_user),
    ).status_code == 403

    # 7. Staff can inspect Alice's attempt -> 200 OK
    staff_view = client.get(
        f"/api/v1/quiz-attempts/{attempt_id}",
        headers=auth_headers(staff_user),
    )
    assert staff_view.status_code == 200

    # 8. Staff lists all attempts for quiz -> 200 OK
    quiz_attempts_resp = client.get(
        f"/api/v1/quizzes/{quiz_id}/attempts",
        headers=auth_headers(staff_user),
    )
    assert quiz_attempts_resp.status_code == 200
    assert quiz_attempts_resp.json()["total"] == 1

    # 9. Student lists own quiz attempts -> 200 OK
    student_own_resp = client.get(
        "/api/v1/quiz-attempts",
        headers=auth_headers(student_user),
    )
    assert student_own_resp.status_code == 200
    assert student_own_resp.json()["total"] == 1
