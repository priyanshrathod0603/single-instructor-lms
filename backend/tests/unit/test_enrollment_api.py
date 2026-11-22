"""FastAPI REST API integration tests for Student Course Enrollments.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 28)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.8)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK603, TASK604)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004, ADR-012)
"""

from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.permissions import CANONICAL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.base import Base
from app.models.course import COURSE_STATUS_PUBLISHED, Course, CourseRevision
from app.models.enrollment import ENROLLMENT_STATUS_ACTIVE, Enrollment
from app.models.permission import Permission, RolePermission
from app.models.user import (
    ROLE_ADMIN,
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

    # Seed permissions
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
def published_course(db_session: Session, super_admin_user: User) -> Course:
    """Creates a published course with live revision."""
    course = Course(
        title="Microservices and Event Sourcing",
        slug="microservices-event-sourcing",
        headline="Advanced cloud software engineering",
        price_inr=599900,
        status=COURSE_STATUS_PUBLISHED,
    )
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(
        course_id=course.id,
        revision_no=1,
        status="PUBLISHED",
        title="Microservices v1",
        created_by=super_admin_user.id,
    )
    db_session.add(rev)
    db_session.flush()

    course.live_revision_id = rev.id
    db_session.commit()
    db_session.refresh(course)
    return course


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
# API Endpoint Tests
# =============================================================================

def test_list_own_enrollments_endpoint(
    client: TestClient,
    db_session: Session,
    student_user: User,
    published_course: Course,
):
    """Student can list their own course enrollments."""
    # Initially 0 enrollments
    resp = client.get("/api/v1/enrollments", headers=auth_headers(student_user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []

    # Provision enrollment directly
    enrollment = Enrollment(
        student_id=student_user.id,
        course_id=published_course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
    )
    db_session.add(enrollment)
    db_session.commit()

    resp = client.get("/api/v1/enrollments", headers=auth_headers(student_user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["course_id"] == str(published_course.id)
    assert item["course_title"] == published_course.title
    assert item["status"] == "ACTIVE"


def test_list_all_enrollments_rbac(
    client: TestClient,
    student_user: User,
    super_admin_user: User,
):
    """GET /api/v1/enrollments/all is restricted to administrators (enrollment:view_all)."""
    # Student forbidden
    resp_student = client.get("/api/v1/enrollments/all", headers=auth_headers(student_user))
    assert resp_student.status_code == 403

    # Super Admin allowed
    resp_admin = client.get("/api/v1/enrollments/all", headers=auth_headers(super_admin_user))
    assert resp_admin.status_code == 200
    assert "items" in resp_admin.json()


def test_grant_manual_enrollment_api(
    client: TestClient,
    db_session: Session,
    super_admin_user: User,
    student_user: User,
    published_course: Course,
):
    """Super Admin can manually grant enrollment via POST /api/v1/enrollments/grant-manual."""
    expires_at = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    payload = {
        "student_id": str(student_user.id),
        "course_id": str(published_course.id),
        "expires_at": expires_at,
        "reason": "Administrative Full Scholarship",
    }

    # Student cannot grant
    resp_denied = client.post(
        "/api/v1/enrollments/grant-manual",
        json=payload,
        headers=auth_headers(student_user),
    )
    assert resp_denied.status_code == 403

    # Super Admin can grant
    resp = client.post(
        "/api/v1/enrollments/grant-manual",
        json=payload,
        headers=auth_headers(super_admin_user),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["student_id"] == str(student_user.id)
    assert data["course_id"] == str(published_course.id)
    assert data["status"] == "ACTIVE"
    assert data["course_title"] == published_course.title


def test_revoke_enrollment_api(
    client: TestClient,
    db_session: Session,
    super_admin_user: User,
    student_user: User,
    published_course: Course,
):
    """Super Admin can revoke enrollment via PATCH /api/v1/enrollments/{id}/revoke."""
    enrollment = Enrollment(
        student_id=student_user.id,
        course_id=published_course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
    )
    db_session.add(enrollment)
    db_session.commit()

    revoke_payload = {"reason": "Violation of Community Terms of Service"}

    # Student cannot revoke
    resp_denied = client.patch(
        f"/api/v1/enrollments/{enrollment.id}/revoke",
        json=revoke_payload,
        headers=auth_headers(student_user),
    )
    assert resp_denied.status_code == 403

    # Super Admin can revoke
    resp = client.patch(
        f"/api/v1/enrollments/{enrollment.id}/revoke",
        json=revoke_payload,
        headers=auth_headers(super_admin_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "REVOKED"
    assert data["revoked_reason"] == "Violation of Community Terms of Service"


def test_check_enrollment_api(
    client: TestClient,
    db_session: Session,
    student_user: User,
    published_course: Course,
):
    """GET /api/v1/enrollments/check/{course_id} evaluates access booleans accurately."""
    # Before enrollment
    resp1 = client.get(
        f"/api/v1/enrollments/check/{published_course.id}",
        headers=auth_headers(student_user),
    )
    assert resp1.status_code == 200
    assert resp1.json()["is_enrolled"] is False
    assert resp1.json()["access_granted"] is False

    # After enrollment
    enrollment = Enrollment(
        student_id=student_user.id,
        course_id=published_course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
    )
    db_session.add(enrollment)
    db_session.commit()

    resp2 = client.get(
        f"/api/v1/enrollments/check/{published_course.id}",
        headers=auth_headers(student_user),
    )
    assert resp2.status_code == 200
    assert resp2.json()["is_enrolled"] is True
    assert resp2.json()["access_granted"] is True
