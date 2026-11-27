"""FastAPI REST API integration tests for Assignment & Rubric Grading.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 3, Tables 14-19)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.5)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Section 1)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK701, TASK702, TASK703, TASK704)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003, ADR-008, ADR-012, ADR-013)
"""

from datetime import datetime, timedelta, timezone
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
    """Creates a Staff evaluator user."""
    user = User(
        email="staff@lms.local",
        full_name="Teaching Assistant",
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
        title="Production Microservices",
        slug="production-microservices",
        headline="Advanced Go & Python Microservices",
        price_inr=799900,
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
        title="Module 1: Architecture",
        sort_order=0,
    )
    db_session.add(section)
    db_session.flush()

    lesson = CurriculumLesson(
        section_id=section.id,
        title="Capstone Project",
        lesson_type="ASSIGNMENT",
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
# 1. Assignment Configuration & Rubrics API Tests (TASK701)
# =============================================================================

def test_create_assignment_endpoint(
    client: TestClient,
    super_admin_user: User,
    student_user: User,
    course_hierarchy: tuple[Course, CurriculumLesson],
):
    """Admin creates assignment configuration; unauthorized student is denied."""
    _, lesson = course_hierarchy
    payload = {
        "title": "Build a Resilient Event Bus",
        "instructions": "Implement event sourcing with delivery guarantees.",
        "max_score": 100.0,
        "pass_score": 70.0,
        "allow_late": False,
        "rubric": {
            "title": "Architecture Rubric",
            "criteria": [
                {
                    "title": "Correctness",
                    "max_points": 60.0,
                    "weight": 1.0,
                    "description": "Zero message loss under failure.",
                },
                {
                    "title": "Code Quality",
                    "max_points": 40.0,
                    "weight": 1.0,
                    "description": "Modular design with unit tests.",
                },
            ],
        },
    }

    # 1. Student attempted creation -> 403 Forbidden
    resp_student = client.post(
        f"/api/v1/lessons/{lesson.id}/assignment",
        json=payload,
        headers=auth_headers(student_user),
    )
    assert resp_student.status_code == 403

    # 2. Super Admin creation -> 201 Created
    resp_admin = client.post(
        f"/api/v1/lessons/{lesson.id}/assignment",
        json=payload,
        headers=auth_headers(super_admin_user),
    )
    assert resp_admin.status_code == 201
    data = resp_admin.json()
    assert data["title"] == "Build a Resilient Event Bus"
    assert data["lesson_id"] == str(lesson.id)
    assert data["active_rubric"] is not None
    assert len(data["active_rubric"]["criteria"]) == 2


def test_get_assignment_endpoint(
    client: TestClient,
    db_session: Session,
    super_admin_user: User,
    student_user: User,
    other_student_user: User,
    course_hierarchy: tuple[Course, CurriculumLesson],
):
    """Enrolled student can view assignment; unenrolled student is blocked."""
    course, lesson = course_hierarchy

    # Create assignment
    payload = {
        "title": "Build a Resilient Event Bus",
        "instructions": "Instructions",
        "max_score": 100.0,
    }
    create_resp = client.post(
        f"/api/v1/lessons/{lesson.id}/assignment",
        json=payload,
        headers=auth_headers(super_admin_user),
    )
    assignment_id = create_resp.json()["id"]

    # Enroll student_user
    db_session.add(Enrollment(
        student_id=student_user.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        granted_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    # 1. Enrolled student accesses assignment by ID -> 200 OK
    resp_enrolled = client.get(
        f"/api/v1/assignments/{assignment_id}",
        headers=auth_headers(student_user),
    )
    assert resp_enrolled.status_code == 200
    assert resp_enrolled.json()["title"] == "Build a Resilient Event Bus"

    # 2. Enrolled student accesses assignment by lesson ID -> 200 OK
    resp_by_lesson = client.get(
        f"/api/v1/lessons/{lesson.id}/assignment",
        headers=auth_headers(student_user),
    )
    assert resp_by_lesson.status_code == 200

    # 3. Unenrolled student accesses assignment -> 403 Forbidden
    resp_unenrolled = client.get(
        f"/api/v1/assignments/{assignment_id}",
        headers=auth_headers(other_student_user),
    )
    assert resp_unenrolled.status_code == 403


def test_update_assignment_and_rubric_endpoints(
    client: TestClient,
    super_admin_user: User,
    course_hierarchy: tuple[Course, CurriculumLesson],
):
    """Admin updates assignment settings and creates a new rubric version."""
    _, lesson = course_hierarchy
    create_resp = client.post(
        f"/api/v1/lessons/{lesson.id}/assignment",
        json={"title": "Original Title", "instructions": "Original", "max_score": 100.0},
        headers=auth_headers(super_admin_user),
    )
    assignment_id = create_resp.json()["id"]

    # 1. PATCH assignment
    patch_resp = client.patch(
        f"/api/v1/assignments/{assignment_id}",
        json={"title": "Updated Title", "pass_score": 80.0},
        headers=auth_headers(super_admin_user),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["title"] == "Updated Title"
    assert patch_resp.json()["pass_score"] == 80.0

    # 2. POST rubric version
    rubric_payload = {
        "title": "Rubric Version 2",
        "criteria": [
            {"title": "Criteria 1", "max_points": 50.0},
            {"title": "Criteria 2", "max_points": 50.0},
        ],
    }
    rubric_resp = client.post(
        f"/api/v1/assignments/{assignment_id}/rubric",
        json=rubric_payload,
        headers=auth_headers(super_admin_user),
    )
    assert rubric_resp.status_code == 201
    assert rubric_resp.json()["title"] == "Rubric Version 2"
    assert len(rubric_resp.json()["criteria"]) == 2


# =============================================================================
# 2. Student Submissions API Tests (TASK702)
# =============================================================================

def test_student_submission_workflow_endpoints(
    client: TestClient,
    db_session: Session,
    super_admin_user: User,
    staff_user: User,
    student_user: User,
    other_student_user: User,
    course_hierarchy: tuple[Course, CurriculumLesson],
):
    """Student submits project work; attempts increment monotonically; anti-IDOR enforced."""
    course, lesson = course_hierarchy
    create_resp = client.post(
        f"/api/v1/lessons/{lesson.id}/assignment",
        json={"title": "Project", "instructions": "Do project", "max_score": 100.0},
        headers=auth_headers(super_admin_user),
    )
    assignment_id = create_resp.json()["id"]

    # Enroll student_user
    db_session.add(Enrollment(
        student_id=student_user.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        granted_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    # 1. Student submits attempt 1
    sub1_resp = client.post(
        f"/api/v1/assignments/{assignment_id}/submissions",
        json={"file_url": "https://storage.local/sub1.zip", "text_notes": "Attempt 1 notes"},
        headers=auth_headers(student_user),
    )
    assert sub1_resp.status_code == 201
    sub1 = sub1_resp.json()
    assert sub1["attempt_no"] == 1
    assert sub1["status"] == "SUBMITTED"

    # 2. Student submits attempt 2
    sub2_resp = client.post(
        f"/api/v1/assignments/{assignment_id}/submissions",
        json={"file_url": "https://storage.local/sub2.zip", "text_notes": "Attempt 2 notes"},
        headers=auth_headers(student_user),
    )
    assert sub2_resp.status_code == 201
    sub2 = sub2_resp.json()
    assert sub2["attempt_no"] == 2

    # 3. List submissions endpoint (Staff view)
    list_resp = client.get(
        f"/api/v1/assignments/{assignment_id}/submissions",
        headers=auth_headers(staff_user),
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 2

    # 4. View submission details (Anti-IDOR checks)
    sub1_id = sub1["id"]

    # Alice (owner) -> 200 OK
    assert client.get(f"/api/v1/submissions/{sub1_id}", headers=auth_headers(student_user)).status_code == 200

    # Staff -> 200 OK
    assert client.get(f"/api/v1/submissions/{sub1_id}", headers=auth_headers(staff_user)).status_code == 200

    # Bob (stranger) -> 403 Forbidden
    assert client.get(f"/api/v1/submissions/{sub1_id}", headers=auth_headers(other_student_user)).status_code == 403


# =============================================================================
# 3. Rubric Grading & Override API Tests (TASK703 & TASK704)
# =============================================================================

def test_grade_and_override_workflow_endpoints(
    client: TestClient,
    db_session: Session,
    super_admin_user: User,
    staff_user: User,
    student_user: User,
    course_hierarchy: tuple[Course, CurriculumLesson],
):
    """Staff grades submission with rubric; Super Admin applies grade override."""
    course, lesson = course_hierarchy
    create_resp = client.post(
        f"/api/v1/lessons/{lesson.id}/assignment",
        json={
            "title": "Graded Assignment",
            "instructions": "Instructions",
            "max_score": 100.0,
            "rubric": {
                "title": "Rubric",
                "criteria": [
                    {"title": "Section A", "max_points": 50.0},
                    {"title": "Section B", "max_points": 50.0},
                ],
            },
        },
        headers=auth_headers(super_admin_user),
    )
    assignment = create_resp.json()
    assignment_id = assignment["id"]
    crit1_id = assignment["active_rubric"]["criteria"][0]["id"]
    crit2_id = assignment["active_rubric"]["criteria"][1]["id"]

    # Enroll student and submit
    db_session.add(Enrollment(
        student_id=student_user.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        granted_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    sub_resp = client.post(
        f"/api/v1/assignments/{assignment_id}/submissions",
        json={"file_url": "https://storage.local/work.zip"},
        headers=auth_headers(student_user),
    )
    submission_id = sub_resp.json()["id"]

    # 1. Staff grades submission
    grade_payload = {
        "scores": [
            {"criteria_id": crit1_id, "points_awarded": 45.0, "feedback": "Well done"},
            {"criteria_id": crit2_id, "points_awarded": 40.0, "feedback": "Minor improvements needed"},
        ],
        "overall_feedback": "Great overall solution.",
    }
    grade_resp = client.post(
        f"/api/v1/submissions/{submission_id}/grade",
        json=grade_payload,
        headers=auth_headers(staff_user),
    )
    assert grade_resp.status_code == 200
    graded_data = grade_resp.json()
    assert graded_data["status"] == "GRADED"
    assert graded_data["final_score"] == 85.0
    assert graded_data["feedback"] == "Great overall solution."

    # 2. Student attempts grade override -> 403 Forbidden
    override_payload = {
        "new_score": 95.0,
        "reason": "Student requested higher score.",
    }
    assert client.post(
        f"/api/v1/submissions/{submission_id}/override-grade",
        json=override_payload,
        headers=auth_headers(student_user),
    ).status_code == 403

    # 3. Staff attempts grade override -> 403 Forbidden (requires assignment:override)
    assert client.post(
        f"/api/v1/submissions/{submission_id}/override-grade",
        json=override_payload,
        headers=auth_headers(staff_user),
    ).status_code == 403

    # 4. Super Admin applies grade override -> 200 OK
    admin_override_resp = client.post(
        f"/api/v1/submissions/{submission_id}/override-grade",
        json=override_payload,
        headers=auth_headers(super_admin_user),
    )
    assert admin_override_resp.status_code == 200
    override_data = admin_override_resp.json()
    assert override_data["original_score"] == 85.0
    assert override_data["overridden_score"] == 95.0
    assert override_data["reason"] == "Student requested higher score."

    # 5. Check submission details reflected updated final score
    check_resp = client.get(
        f"/api/v1/submissions/{submission_id}",
        headers=auth_headers(student_user),
    )
    assert check_resp.status_code == 200
    assert check_resp.json()["final_score"] == 95.0
    assert len(check_resp.json()["grade_overrides"]) == 1

    # 6. Student can list their own submissions without requiring assignment:view_all
    own_resp = client.get(
        f"/api/v1/assignments/{assignment_id}/my-submissions",
        headers=auth_headers(student_user),
    )
    assert own_resp.status_code == 200
    own_data = own_resp.json()
    assert own_data["total"] == 1
    assert own_data["items"][0]["id"] == submission_id

    # Staff without assignment:submit cannot call student-only my-submissions
    staff_own_resp = client.get(
        f"/api/v1/assignments/{assignment_id}/my-submissions",
        headers=auth_headers(staff_user),
    )
    assert staff_own_resp.status_code == 403
