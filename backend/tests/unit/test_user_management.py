"""Unit tests for User Directory, Profile Management, and Administrative Suspension (TASK204).

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.2)
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md
- docs/backend/10-USER-MANAGEMENT.md
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK204)
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf [Pages 2-3, 8]

Verifies:
1. User directory filtering (search, role, active, verified) and pagination.
2. User profile retrieval with self-access and administrative viewing.
3. User profile updating with self-access.
4. Administrative suspension revoking all active sessions and setting is_active=False.
5. Sole Super Admin Protection Invariant:
   - Cannot suspend the last active Super Admin (HTTP 409 Conflict).
   - Cannot demote/revoke SUPER_ADMIN role from the last active Super Admin (HTTP 409 Conflict).
   - Permitted if another active Super Admin account exists.
6. Role assignment and revocation workflow.
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
from app.core.permissions import (
    CANONICAL_PERMISSIONS,
    DEFAULT_ROLE_PERMISSIONS,
)
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.auth_session import AuthSession, SESSION_STATUS_ACTIVE, SESSION_STATUS_REVOKED
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
def user_mgmt_session():
    """In-memory SQLite database session seeded with roles, permissions, and test personas."""
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

    # 1. Super Admin (Sole platform owner)
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

    # 2. Admin
    admin = User(
        id=uuid.uuid4(),
        email="operations@example.com",
        full_name="Operations Admin",
        password_hash=hash_password("AdminSecure123!"),
        is_verified=True,
        is_active=True,
    )
    admin.user_roles.append(UserRole(role_id=ROLE_ADMIN, role=session.get(Role, ROLE_ADMIN)))
    session.add(admin)

    # 3. Student 1
    student1 = User(
        id=uuid.uuid4(),
        email="student1@example.com",
        full_name="Alice Student",
        password_hash=hash_password("StudentSecure123!"),
        is_verified=True,
        is_active=True,
    )
    student1.user_roles.append(UserRole(role_id=ROLE_STUDENT, role=session.get(Role, ROLE_STUDENT)))
    session.add(student1)

    # 4. Student 2
    student2 = User(
        id=uuid.uuid4(),
        email="student2@example.com",
        full_name="Bob Student",
        password_hash=hash_password("StudentSecure123!"),
        is_verified=False,
        is_active=True,
    )
    student2.user_roles.append(UserRole(role_id=ROLE_STUDENT, role=session.get(Role, ROLE_STUDENT)))
    session.add(student2)

    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(user_mgmt_session: Session):
    """FastAPI TestClient with overridden database dependency."""
    app = create_app()

    def override_get_db():
        yield user_mgmt_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def auth_headers_for(user: User) -> dict[str, str]:
    """Generate Authorization header with valid JWT access token."""
    from tests.conftest import create_test_auth_headers
    return create_test_auth_headers(user)


class TestUserDirectory:
    """Verifies GET /api/v1/users."""

    def test_admin_can_list_and_filter_users(self, client: TestClient, user_mgmt_session: Session):
        """Admin with users:view_all can list and search users."""
        admin = user_mgmt_session.query(User).filter(User.email == "operations@example.com").one()
        headers = auth_headers_for(admin)

        resp = client.get("/api/v1/users?page=1&per_page=10", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4
        assert len(data["items"]) == 4

        # Filter by search
        search_res = client.get("/api/v1/users?search=alice", headers=headers)
        assert search_res.status_code == 200
        assert search_res.json()["total"] == 1
        assert search_res.json()["items"][0]["email"] == "student1@example.com"

        # Filter by role
        role_res = client.get("/api/v1/users?role=ADMIN", headers=headers)
        assert role_res.status_code == 200
        assert role_res.json()["total"] == 1
        assert role_res.json()["items"][0]["email"] == "operations@example.com"

    def test_student_cannot_list_users(self, client: TestClient, user_mgmt_session: Session):
        """Student lacking users:view_all receives HTTP 403 PERMISSION_DENIED."""
        student = user_mgmt_session.query(User).filter(User.email == "student1@example.com").one()
        headers = auth_headers_for(student)

        resp = client.get("/api/v1/users", headers=headers)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


class TestUserProfileAccess:
    """Verifies GET /api/v1/users/{id} and PATCH /api/v1/users/{id}."""

    def test_student_can_view_own_profile(self, client: TestClient, user_mgmt_session: Session):
        """Student can view their own profile."""
        student = user_mgmt_session.query(User).filter(User.email == "student1@example.com").one()
        headers = auth_headers_for(student)

        resp = client.get(f"/api/v1/users/{student.id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "student1@example.com"
        assert "roles" in data
        assert "permissions" in data

    def test_student_cannot_view_another_student_profile(self, client: TestClient, user_mgmt_session: Session):
        """Student cannot view another user's profile (Anti-IDOR)."""
        student1 = user_mgmt_session.query(User).filter(User.email == "student1@example.com").one()
        student2 = user_mgmt_session.query(User).filter(User.email == "student2@example.com").one()
        headers = auth_headers_for(student1)

        resp = client.get(f"/api/v1/users/{student2.id}", headers=headers)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_student_can_update_own_profile(self, client: TestClient, user_mgmt_session: Session):
        """Student can update their own display name."""
        student = user_mgmt_session.query(User).filter(User.email == "student1@example.com").one()
        headers = auth_headers_for(student)

        resp = client.patch(
            f"/api/v1/users/{student.id}",
            json={"full_name": "Alice In Wonderland"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Alice In Wonderland"


class TestAdministrativeSuspensionAndSoleSuperAdminProtection:
    """Verifies PATCH /api/v1/users/{id}/status and Sole Super Admin invariants."""

    def test_super_admin_suspends_student_and_revokes_sessions(self, client: TestClient, user_mgmt_session: Session):
        """Suspending a user marks is_active=False and revokes all active sessions."""
        super_admin = user_mgmt_session.query(User).filter(User.email == "instructor@example.com").one()
        student = user_mgmt_session.query(User).filter(User.email == "student1@example.com").one()

        # Create active session for student
        active_sess = AuthSession(
            user_id=student.id,
            session_token_hash="a" * 64,
            expires_at=utc_now() + timedelta(days=7),
            status=SESSION_STATUS_ACTIVE,
        )
        user_mgmt_session.add(active_sess)
        user_mgmt_session.commit()

        headers = auth_headers_for(super_admin)
        resp = client.patch(
            f"/api/v1/users/{student.id}/status",
            json={"is_active": False, "reason": "Violation of terms of service"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        # Verify session was revoked in database
        refreshed_sess = user_mgmt_session.get(AuthSession, active_sess.id)
        assert refreshed_sess.status == SESSION_STATUS_REVOKED

    def test_cannot_suspend_sole_super_admin(self, client: TestClient, user_mgmt_session: Session):
        """Attempting to suspend the only active Super Admin fails with HTTP 409 Conflict."""
        super_admin = user_mgmt_session.query(User).filter(User.email == "instructor@example.com").one()
        headers = auth_headers_for(super_admin)

        resp = client.patch(
            f"/api/v1/users/{super_admin.id}/status",
            json={"is_active": False, "reason": "Self suspension test"},
            headers=headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CANNOT_SUSPEND_LAST_SUPER_ADMIN"

    def test_cannot_demote_or_revoke_sole_super_admin(self, client: TestClient, user_mgmt_session: Session):
        """Attempting to revoke SUPER_ADMIN role from the only active Super Admin fails with HTTP 409."""
        super_admin = user_mgmt_session.query(User).filter(User.email == "instructor@example.com").one()
        headers = auth_headers_for(super_admin)

        resp = client.patch(
            f"/api/v1/users/{super_admin.id}/roles",
            json={"role_id": "SUPER_ADMIN", "action": "REVOKE"},
            headers=headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CANNOT_DEMOTE_LAST_SUPER_ADMIN"

    def test_can_suspend_super_admin_if_second_super_admin_exists(self, client: TestClient, user_mgmt_session: Session):
        """When a second active Super Admin exists, suspending one is permitted."""
        second_super = User(
            id=uuid.uuid4(),
            email="backup_instructor@example.com",
            full_name="Co-Instructor",
            is_verified=True,
            is_active=True,
        )
        second_super.user_roles.append(
            UserRole(role_id=ROLE_SUPER_ADMIN, role=user_mgmt_session.get(Role, ROLE_SUPER_ADMIN))
        )
        user_mgmt_session.add(second_super)
        user_mgmt_session.commit()

        super_admin = user_mgmt_session.query(User).filter(User.email == "instructor@example.com").one()
        headers = auth_headers_for(super_admin)

        resp = client.patch(
            f"/api/v1/users/{second_super.id}/status",
            json={"is_active": False, "reason": "Retirement"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False


class TestRoleAssignmentWorkflow:
    """Verifies PATCH /api/v1/users/{id}/roles."""

    def test_super_admin_assigns_and_revokes_admin_role(self, client: TestClient, user_mgmt_session: Session):
        """Super Admin assigns ADMIN role to student, then revokes it."""
        super_admin = user_mgmt_session.query(User).filter(User.email == "instructor@example.com").one()
        student = user_mgmt_session.query(User).filter(User.email == "student1@example.com").one()
        headers = auth_headers_for(super_admin)

        # Assign ADMIN
        assign_res = client.patch(
            f"/api/v1/users/{student.id}/roles",
            json={"role_id": "ADMIN", "action": "ASSIGN"},
            headers=headers,
        )
        assert assign_res.status_code == 200
        assert ROLE_ADMIN in assign_res.json()["roles"]

        # Revoke ADMIN
        revoke_res = client.patch(
            f"/api/v1/users/{student.id}/roles",
            json={"role_id": "ADMIN", "action": "REVOKE"},
            headers=headers,
        )
        assert revoke_res.status_code == 200
        assert ROLE_ADMIN not in revoke_res.json()["roles"]
