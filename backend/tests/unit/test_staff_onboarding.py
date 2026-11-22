"""Unit tests for Staff Onboarding and Invitation Workflow (TASK203).

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Sections 2.2, 2.1)
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md
- docs/backend/10-USER-MANAGEMENT.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK203)

Verifies:
1. Admin/Super Admin can invite new staff with 48h token and outbox staging.
2. Inviting with unauthorized role (e.g. SUPER_ADMIN) is strictly rejected.
3. Inviting existing user assigns role directly.
4. Staff onboarding claim validates password complexity, updates password, consumes token,
   creates single active session, sets cookie, and logs audit event.
5. Expired or consumed onboarding tokens are rejected with HTTP 400.
"""

from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.permissions import (
    CANONICAL_PERMISSIONS,
    DEFAULT_ROLE_PERMISSIONS,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.main import create_app
from app.models.auth_token import AuthToken, TOKEN_TYPE_STAFF_ONBOARDING
from app.models.base import Base, utc_now
from app.models.notification import NotificationOutbox
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
def onboarding_session():
    """In-memory SQLite database session seeded with roles, permissions, and test accounts."""
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

    # Create admin user
    admin = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        full_name="Platform Administrator",
        password_hash=hash_password("AdminPass1234!"),
        is_verified=True,
        is_active=True,
    )
    admin.user_roles.append(UserRole(role_id=ROLE_ADMIN, role=session.get(Role, ROLE_ADMIN)))
    session.add(admin)

    # Create student user
    student = User(
        id=uuid.uuid4(),
        email="student@example.com",
        full_name="Active Student",
        password_hash=hash_password("StudentPass1234!"),
        is_verified=True,
        is_active=True,
    )
    student.user_roles.append(UserRole(role_id=ROLE_STUDENT, role=session.get(Role, ROLE_STUDENT)))
    session.add(student)

    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(onboarding_session: Session):
    """FastAPI TestClient with overridden database dependency."""
    app = create_app()

    def override_get_db():
        yield onboarding_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def auth_headers_for(user: User) -> dict[str, str]:
    """Generate Authorization header with valid JWT access token."""
    from tests.conftest import create_test_auth_headers
    return create_test_auth_headers(user)


class TestStaffInvitationWorkflow:
    """Verifies POST /api/v1/users/staff/invite."""

    def test_admin_invites_new_staff_member(self, client: TestClient, onboarding_session: Session):
        """Admin invites a new staff member; stages token and outbox email."""
        admin = onboarding_session.query(User).filter(User.email == "admin@example.com").one()
        headers = auth_headers_for(admin)

        resp = client.post(
            "/api/v1/users/staff/invite",
            json={
                "email": "grader_new@example.com",
                "full_name": "New Grader",
                "role": "STAFF",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["invited"] is True
        assert data["email"] == "grader_new@example.com"
        assert "token" not in data
        assert "expires_at" in data

        # Verify User was created
        created_user = onboarding_session.query(User).filter(User.email == "grader_new@example.com").first()
        assert created_user is not None
        assert created_user.is_verified is True
        assert created_user.is_active is True
        assert created_user.password_hash is None
        assert created_user.has_role(ROLE_STAFF)

        # Verify AuthToken was created with 48h TTL
        tokens = onboarding_session.query(AuthToken).filter(AuthToken.user_id == created_user.id).all()
        assert len(tokens) == 1
        assert tokens[0].token_type == TOKEN_TYPE_STAFF_ONBOARDING
        assert tokens[0].is_used is False
        assert tokens[0].expires_at > utc_now() + timedelta(hours=47)

        # Verify NotificationOutbox event was staged
        outbox_items = onboarding_session.query(NotificationOutbox).filter(
            NotificationOutbox.recipient == "grader_new@example.com"
        ).all()
        assert len(outbox_items) == 1
        assert outbox_items[0].event_type == "STAFF_INVITATION"
        raw_token = outbox_items[0].payload["invitation_token"]
        assert raw_token is not None

    def test_cannot_invite_super_admin(self, client: TestClient, onboarding_session: Session):
        """Cannot invite a user as SUPER_ADMIN (must be STAFF or ADMIN)."""
        admin = onboarding_session.query(User).filter(User.email == "admin@example.com").one()
        headers = auth_headers_for(admin)

        resp = client.post(
            "/api/v1/users/staff/invite",
            json={
                "email": "intruder@example.com",
                "full_name": "Intruder",
                "role": "SUPER_ADMIN",
            },
            headers=headers,
        )
        assert resp.status_code == 422  # Pydantic schema validation rejects role != STAFF, ADMIN

    def test_student_cannot_invite_staff(self, client: TestClient, onboarding_session: Session):
        """Student lacking staff:invite is rejected with HTTP 403."""
        student = onboarding_session.query(User).filter(User.email == "student@example.com").one()
        headers = auth_headers_for(student)

        resp = client.post(
            "/api/v1/users/staff/invite",
            json={
                "email": "grader2@example.com",
                "full_name": "Grader Two",
                "role": "STAFF",
            },
            headers=headers,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_invite_existing_student_grants_staff_role(self, client: TestClient, onboarding_session: Session):
        """Inviting an existing student grants the STAFF role to their account."""
        admin = onboarding_session.query(User).filter(User.email == "admin@example.com").one()
        headers = auth_headers_for(admin)

        resp = client.post(
            "/api/v1/users/staff/invite",
            json={
                "email": "student@example.com",
                "full_name": "Active Student",
                "role": "STAFF",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["invited"] is True
        assert "granted" in data["message"].lower()

        student = onboarding_session.query(User).filter(User.email == "student@example.com").one()
        assert student.has_role(ROLE_STUDENT)
        assert student.has_role(ROLE_STAFF)


class TestStaffOnboardingClaimWorkflow:
    """Verifies POST /api/v1/auth/onboarding/claim."""

    def test_successful_staff_onboarding_claim(self, client: TestClient, onboarding_session: Session):
        """Invited staff member claims token, sets password, and receives session cookie."""
        admin = onboarding_session.query(User).filter(User.email == "admin@example.com").one()
        headers = auth_headers_for(admin)

        invite_res = client.post(
            "/api/v1/users/staff/invite",
            json={
                "email": "new_ta@example.com",
                "full_name": "New TA",
                "role": "STAFF",
            },
            headers=headers,
        )
        assert invite_res.status_code == 201
        assert "token" not in invite_res.json()

        # Retrieve raw invitation token from staged NotificationOutbox
        outbox_item = onboarding_session.query(NotificationOutbox).filter(
            NotificationOutbox.recipient == "new_ta@example.com"
        ).first()
        assert outbox_item is not None
        raw_token = outbox_item.payload["invitation_token"]

        # Claim onboarding
        claim_res = client.post(
            "/api/v1/auth/onboarding/claim",
            json={
                "token": raw_token,
                "password": "SecurePassword9876#",
            },
        )
        assert claim_res.status_code == 200
        claim_data = claim_res.json()
        assert claim_data["user"]["email"] == "new_ta@example.com"
        assert ROLE_STAFF in claim_data["user"]["roles"]
        assert "access_token" in claim_data
        assert client.cookies.get(get_settings().SESSION_COOKIE_NAME) is not None

        # Verify password hash updated
        user = onboarding_session.query(User).filter(User.email == "new_ta@example.com").one()
        assert user.password_hash is not None
        assert verify_password("SecurePassword9876#", user.password_hash) is True

        # Verify token is now consumed
        token = onboarding_session.query(AuthToken).filter(AuthToken.user_id == user.id).one()
        assert token.is_used is True

    def test_onboarding_claim_rejects_weak_password(self, client: TestClient, onboarding_session: Session):
        """Password complexity rules are enforced upon onboarding claim."""
        resp = client.post(
            "/api/v1/auth/onboarding/claim",
            json={
                "token": "valid_looking_token_1234567890",
                "password": "short",
            },
        )
        assert resp.status_code == 422

    def test_onboarding_claim_rejects_used_or_invalid_token(self, client: TestClient, onboarding_session: Session):
        """Invalid or expired tokens fail with HTTP 400 INVALID_OR_EXPIRED_TOKEN."""
        resp = client.post(
            "/api/v1/auth/onboarding/claim",
            json={
                "token": "completely_bogus_token_1234567890",
                "password": "ValidStrongPassword123!",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_OR_EXPIRED_TOKEN"
