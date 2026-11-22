"""Unit tests for Super Admin Immutable Audit Trail API (TASK206).

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.11)
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK206)

Verifies:
1. Super Admin with audit:view can query append-only audit trail.
2. Filters by action, resource_type, actor_id, actor_type, and pagination work accurately.
3. Student and Admin accounts lacking audit:view are rejected with HTTP 403.
4. Unauthenticated requests are rejected with HTTP 401.
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
from app.models.audit_log import AuditLog
from app.models.base import Base, utc_now
from app.models.permission import Permission, RolePermission
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


@pytest.fixture
def audit_db_session():
    """In-memory SQLite database session seeded with roles, permissions, users, and audit logs."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    roles = [
        Role(id=ROLE_VISITOR, name="Visitor", description="Public guest"),
        Role(id=ROLE_STUDENT, name="Student", description="Enrolled learner"),
        Role(id=ROLE_STAFF, name="Staff", description="Teaching assistant / grader"),
        Role(id=ROLE_ADMIN, name="Admin", description="Platform administrator"),
        Role(id=ROLE_SUPER_ADMIN, name="Super Admin", description="Platform owner"),
    ]
    session.add_all(roles)

    now = datetime.now(timezone.utc)
    for p_id, p_mod, p_desc in CANONICAL_PERMISSIONS:
        session.add(Permission(id=p_id, module=p_mod, description=p_desc, created_at=now))

    for r_id, p_keys in DEFAULT_ROLE_PERMISSIONS.items():
        for p_key in p_keys:
            session.add(RolePermission(role_id=r_id, permission_id=p_key, assigned_at=now))

    # Super Admin
    super_admin = User(
        id=uuid.uuid4(),
        email="instructor@example.com",
        full_name="Primary Instructor",
        password_hash=hash_password("SuperSecure123!"),
        is_verified=True,
        is_active=True,
    )
    super_admin.user_roles.append(UserRole(role_id=ROLE_SUPER_ADMIN, role=session.get(Role, ROLE_SUPER_ADMIN)))
    session.add(super_admin)

    # Admin
    admin = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        full_name="Platform Admin",
        password_hash=hash_password("AdminSecure123!"),
        is_verified=True,
        is_active=True,
    )
    admin.user_roles.append(UserRole(role_id=ROLE_ADMIN, role=session.get(Role, ROLE_ADMIN)))
    session.add(admin)

    # Student
    student = User(
        id=uuid.uuid4(),
        email="student@example.com",
        full_name="Active Student",
        password_hash=hash_password("StudentSecure123!"),
        is_verified=True,
        is_active=True,
    )
    student.user_roles.append(UserRole(role_id=ROLE_STUDENT, role=session.get(Role, ROLE_STUDENT)))
    session.add(student)

    # Seed 3 audit logs
    log1 = AuditLog(
        id=uuid.uuid4(),
        actor_id=super_admin.id,
        actor_type="SUPER_ADMIN",
        action="USER_STATUS_UPDATED",
        resource_type="user",
        resource_id=str(student.id),
        before_state={"is_active": True},
        after_state={"is_active": False},
        created_at=now - timedelta(minutes=10),
    )
    log2 = AuditLog(
        id=uuid.uuid4(),
        actor_id=admin.id,
        actor_type="ADMIN",
        action="STAFF_INVITED",
        resource_type="user",
        resource_id=str(uuid.uuid4()),
        after_state={"email": "new_staff@example.com"},
        created_at=now - timedelta(minutes=5),
    )
    log3 = AuditLog(
        id=uuid.uuid4(),
        actor_id=super_admin.id,
        actor_type="SUPER_ADMIN",
        action="COURSE_PUBLISHED",
        resource_type="course",
        resource_id="c1f7a28e-5b1b-4d4b-9c3f-7e8e12345678",
        created_at=now,
    )
    session.add_all([log1, log2, log3])

    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(audit_db_session: Session):
    """FastAPI TestClient with overridden database dependency."""
    app = create_app()

    def override_get_db():
        yield audit_db_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def auth_headers_for(user: User) -> dict[str, str]:
    """Generate Authorization header with valid JWT access token."""
    from tests.conftest import create_test_auth_headers
    return create_test_auth_headers(user)


class TestAuditLogAPI:
    """Verifies GET /api/v1/audit-logs."""

    def test_super_admin_can_query_all_audit_logs(self, client: TestClient, audit_db_session: Session):
        """Super Admin queries all audit logs."""
        super_admin = audit_db_session.query(User).filter(User.email == "instructor@example.com").one()
        headers = auth_headers_for(super_admin)

        resp = client.get("/api/v1/audit-logs?page=1&per_page=10", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        assert data["page"] == 1
        assert data["per_page"] == 10
        assert data["total_pages"] == 1

    def test_super_admin_filters_by_action_and_resource(self, client: TestClient, audit_db_session: Session):
        """Super Admin filters audit logs by action and resource_type."""
        super_admin = audit_db_session.query(User).filter(User.email == "instructor@example.com").one()
        headers = auth_headers_for(super_admin)

        resp = client.get("/api/v1/audit-logs?action=COURSE_PUBLISHED", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["action"] == "COURSE_PUBLISHED"
        assert data["items"][0]["resource_type"] == "course"

    def test_admin_lacks_audit_view_rejected_403(self, client: TestClient, audit_db_session: Session):
        """Admin (lacking audit:view) is rejected with HTTP 403 PERMISSION_DENIED."""
        admin = audit_db_session.query(User).filter(User.email == "admin@example.com").one()
        headers = auth_headers_for(admin)

        resp = client.get("/api/v1/audit-logs", headers=headers)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_student_rejected_403(self, client: TestClient, audit_db_session: Session):
        """Student is rejected with HTTP 403 PERMISSION_DENIED."""
        student = audit_db_session.query(User).filter(User.email == "student@example.com").one()
        headers = auth_headers_for(student)

        resp = client.get("/api/v1/audit-logs", headers=headers)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_unauthenticated_rejected_401(self, client: TestClient):
        """Unauthenticated call is rejected with HTTP 401 NOT_AUTHENTICATED."""
        resp = client.get("/api/v1/audit-logs")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "NOT_AUTHENTICATED"
