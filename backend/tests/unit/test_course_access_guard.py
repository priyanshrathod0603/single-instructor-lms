"""Unit and integration tests for Course Access Dependency Guard and lesson/media gating.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 28)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.4, 2.8)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK604)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)
"""

from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import check_course_access, get_db
from app.core.exceptions import ForbiddenException
from app.core.permissions import CANONICAL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.base import Base
from app.models.course import COURSE_STATUS_PUBLISHED, Course, CourseRevision
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.enrollment import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_EXPIRED,
    ENROLLMENT_STATUS_REVOKED,
    Enrollment,
)
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

    for key, module, desc in CANONICAL_PERMISSIONS:
        session.add(Permission(id=key, module=module, description=desc))
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
    """Super Admin user fixture."""
    user = User(
        email="owner@lms.local",
        full_name="Platform Owner",
        password_hash=hash_password("SuperSecret123!"),
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
def staff_user(db_session: Session, super_admin_user: User) -> User:
    """Staff teaching assistant fixture."""
    user = User(
        email="staff@lms.local",
        full_name="Teaching Assistant",
        password_hash=hash_password("StaffSecret123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    role = db_session.get(Role, ROLE_STAFF)
    db_session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=super_admin_user.id))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def student_user(db_session: Session) -> User:
    """Active Student user fixture."""
    user = User(
        email="learner@lms.local",
        full_name="Alice Student",
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
def course_hierarchy(db_session: Session, super_admin_user: User):
    """Creates a complete published course hierarchy with preview and non-preview lessons."""
    course = Course(
        title="Distributed Consensus Engineering",
        slug="distributed-consensus-engineering",
        headline="Raft, Paxos, and Byzantine Fault Tolerance",
        price_inr=799900,
        status=COURSE_STATUS_PUBLISHED,
    )
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(
        course_id=course.id,
        revision_no=1,
        status="PUBLISHED",
        title="Distributed Consensus v1",
        created_by=super_admin_user.id,
    )
    db_session.add(rev)
    db_session.flush()

    course.live_revision_id = rev.id
    db_session.flush()

    section = CurriculumSection(
        course_revision_id=rev.id,
        title="Module 1: The Raft Consensus Algorithm",
        sort_order=0,
    )
    db_session.add(section)
    db_session.flush()

    preview_lesson = CurriculumLesson(
        section_id=section.id,
        title="Lesson 1: Introduction to Quorums (Preview)",
        sort_order=0,
        is_preview=True,
        duration_seconds=600,
    )
    db_session.add(preview_lesson)

    paid_lesson = CurriculumLesson(
        section_id=section.id,
        title="Lesson 2: Leader Election & Log Replication",
        sort_order=1,
        is_preview=False,
        duration_seconds=1800,
    )
    db_session.add(paid_lesson)
    db_session.commit()

    return {
        "course": course,
        "revision": rev,
        "section": section,
        "preview_lesson": preview_lesson,
        "paid_lesson": paid_lesson,
    }


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """TestClient configured with database override."""
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
# 1. Lesson Gating Tests (TASK604)
# =============================================================================

def test_preview_lesson_publicly_accessible(client: TestClient, course_hierarchy: dict):
    """Preview lessons (is_preview=True) can be accessed anonymously without authentication."""
    preview_lesson = course_hierarchy["preview_lesson"]
    resp = client.get(f"/api/v1/lessons/{preview_lesson.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(preview_lesson.id)
    assert data["is_preview"] is True


def test_paid_lesson_unauthenticated_rejected(client: TestClient, course_hierarchy: dict):
    """Non-preview lessons reject anonymous unauthenticated visitors with 403 ENROLLMENT_REQUIRED."""
    paid_lesson = course_hierarchy["paid_lesson"]
    resp = client.get(f"/api/v1/lessons/{paid_lesson.id}")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] in ("FORBIDDEN", "ENROLLMENT_REQUIRED")


def test_paid_lesson_unenrolled_student_rejected(
    client: TestClient,
    course_hierarchy: dict,
    student_user: User,
):
    """Authenticated student without active enrollment cannot view non-preview lesson."""
    paid_lesson = course_hierarchy["paid_lesson"]
    resp = client.get(
        f"/api/v1/lessons/{paid_lesson.id}",
        headers=auth_headers(student_user),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ENROLLMENT_REQUIRED"


def test_paid_lesson_enrolled_student_allowed(
    client: TestClient,
    db_session: Session,
    course_hierarchy: dict,
    student_user: User,
):
    """Authenticated student with active enrollment accesses non-preview lesson successfully."""
    paid_lesson = course_hierarchy["paid_lesson"]
    course = course_hierarchy["course"]

    enrollment = Enrollment(
        student_id=student_user.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
    )
    db_session.add(enrollment)
    db_session.commit()

    resp = client.get(
        f"/api/v1/lessons/{paid_lesson.id}",
        headers=auth_headers(student_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(paid_lesson.id)
    assert data["title"] == paid_lesson.title


def test_paid_lesson_revoked_enrollment_rejected(
    client: TestClient,
    db_session: Session,
    course_hierarchy: dict,
    student_user: User,
):
    """Student whose enrollment is REVOKED is denied access with HTTP 403 ENROLLMENT_REVOKED."""
    paid_lesson = course_hierarchy["paid_lesson"]
    course = course_hierarchy["course"]

    enrollment = Enrollment(
        student_id=student_user.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_REVOKED,
        revoked_at=datetime.now(timezone.utc),
        revoked_reason="PAYMENT_REFUNDED",
    )
    db_session.add(enrollment)
    db_session.commit()

    resp = client.get(
        f"/api/v1/lessons/{paid_lesson.id}",
        headers=auth_headers(student_user),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ENROLLMENT_REVOKED"


def test_paid_lesson_expired_enrollment_rejected(
    client: TestClient,
    db_session: Session,
    course_hierarchy: dict,
    student_user: User,
):
    """Student whose enrollment has expired is denied access with HTTP 403 ENROLLMENT_EXPIRED."""
    paid_lesson = course_hierarchy["paid_lesson"]
    course = course_hierarchy["course"]

    enrollment = Enrollment(
        student_id=student_user.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(enrollment)
    db_session.commit()

    resp = client.get(
        f"/api/v1/lessons/{paid_lesson.id}",
        headers=auth_headers(student_user),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ENROLLMENT_EXPIRED"


def test_paid_lesson_elevated_roles_bypass_enrollment(
    client: TestClient,
    course_hierarchy: dict,
    staff_user: User,
    super_admin_user: User,
):
    """Staff and Super Admins view non-preview lessons without personal course enrollments."""
    paid_lesson = course_hierarchy["paid_lesson"]

    resp_staff = client.get(
        f"/api/v1/lessons/{paid_lesson.id}",
        headers=auth_headers(staff_user),
    )
    assert resp_staff.status_code == 200

    resp_admin = client.get(
        f"/api/v1/lessons/{paid_lesson.id}",
        headers=auth_headers(super_admin_user),
    )
    assert resp_admin.status_code == 200


# =============================================================================
# 2. check_course_access Guard Unit Function Tests
# =============================================================================

def test_check_course_access_unit_evaluations(
    db_session: Session,
    course_hierarchy: dict,
    student_user: User,
    super_admin_user: User,
):
    """Direct verification of check_course_access helper function."""
    course_id = course_hierarchy["course"].id

    # 1. Super Admin always allowed
    assert check_course_access(course_id, super_admin_user, db_session) is True

    # 2. Suspended user raises ACCOUNT_SUSPENDED
    student_user.is_active = False
    with pytest.raises(ForbiddenException) as exc_info:
        check_course_access(course_id, student_user, db_session)
    assert exc_info.value.code == "ACCOUNT_SUSPENDED"

    # 3. Active student without enrollment raises ENROLLMENT_REQUIRED
    student_user.is_active = True
    with pytest.raises(ForbiddenException) as exc_info:
        check_course_access(course_id, student_user, db_session)
    assert exc_info.value.code == "ENROLLMENT_REQUIRED"

    # 4. Active enrollment returns True
    enrollment = Enrollment(
        student_id=student_user.id,
        course_id=course_id,
        status=ENROLLMENT_STATUS_ACTIVE,
    )
    db_session.add(enrollment)
    db_session.commit()
    assert check_course_access(course_id, student_user, db_session) is True
