"""Unit tests for In-App Notification Feed and User Receipts (TASK205).

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 33)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.11)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK205)

Verifies:
1. User receives own notifications with accurate unread counts.
2. Unread-only filter returns strictly unread items.
3. Strict user isolation: User A cannot view User B's notifications.
4. Marking an individual notification read enforces owner validation.
5. Marking all notifications read updates only the authenticated user's records.
6. Unauthenticated requests are rejected with HTTP 401.
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
from app.models.notification import (
    NOTIFICATION_TYPE_ANNOUNCEMENT,
    NOTIFICATION_TYPE_ENROLLMENT,
    Notification,
)
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
def notif_db_session():
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

    # User A (Alice)
    alice = User(
        id=uuid.uuid4(),
        email="alice@example.com",
        full_name="Alice Learner",
        password_hash=hash_password("AliceSecure123!"),
        is_verified=True,
        is_active=True,
    )
    alice.user_roles.append(UserRole(role_id=ROLE_STUDENT, role=session.get(Role, ROLE_STUDENT)))
    session.add(alice)

    # User B (Bob)
    bob = User(
        id=uuid.uuid4(),
        email="bob@example.com",
        full_name="Bob Learner",
        password_hash=hash_password("BobSecure123!"),
        is_verified=True,
        is_active=True,
    )
    bob.user_roles.append(UserRole(role_id=ROLE_STUDENT, role=session.get(Role, ROLE_STUDENT)))
    session.add(bob)

    # Seed notifications for Alice: 2 unread, 1 read
    n1 = Notification(
        id=uuid.uuid4(),
        user_id=alice.id,
        title="Welcome Alice",
        message="Glad to have you aboard!",
        notification_type=NOTIFICATION_TYPE_ANNOUNCEMENT,
        is_read=False,
    )
    n2 = Notification(
        id=uuid.uuid4(),
        user_id=alice.id,
        title="Course Enrolled",
        message="You are enrolled in Full-Stack Architecture",
        notification_type=NOTIFICATION_TYPE_ENROLLMENT,
        is_read=False,
    )
    n3 = Notification(
        id=uuid.uuid4(),
        user_id=alice.id,
        title="Profile Created",
        message="Your profile has been created",
        notification_type=NOTIFICATION_TYPE_ANNOUNCEMENT,
        is_read=True,
    )
    session.add_all([n1, n2, n3])

    # Seed notification for Bob: 1 unread
    n_bob = Notification(
        id=uuid.uuid4(),
        user_id=bob.id,
        title="Welcome Bob",
        message="Private notice for Bob only",
        notification_type=NOTIFICATION_TYPE_ANNOUNCEMENT,
        is_read=False,
    )
    session.add(n_bob)

    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(notif_db_session: Session):
    """FastAPI TestClient with overridden database dependency."""
    app = create_app()

    def override_get_db():
        yield notif_db_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def auth_headers_for(user: User) -> dict[str, str]:
    """Generate Authorization header with valid JWT access token."""
    from tests.conftest import create_test_auth_headers
    return create_test_auth_headers(user)


class TestInAppNotificationFeed:
    """Verifies GET /api/v1/notifications."""

    def test_user_lists_own_notifications(self, client: TestClient, notif_db_session: Session):
        """Alice lists all her notifications; receives 3 total and unread_count=2."""
        alice = notif_db_session.query(User).filter(User.email == "alice@example.com").one()
        headers = auth_headers_for(alice)

        resp = client.get("/api/v1/notifications", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["unread_count"] == 2
        assert len(data["items"]) == 3

    def test_user_filters_unread_only(self, client: TestClient, notif_db_session: Session):
        """Alice filters to unread_only=true; receives 2 items."""
        alice = notif_db_session.query(User).filter(User.email == "alice@example.com").one()
        headers = auth_headers_for(alice)

        resp = client.get("/api/v1/notifications?unread_only=true", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert all(item["is_read"] is False for item in data["items"])

    def test_strict_user_isolation(self, client: TestClient, notif_db_session: Session):
        """Bob only sees his single notification, never Alice's."""
        bob = notif_db_session.query(User).filter(User.email == "bob@example.com").one()
        headers = auth_headers_for(bob)

        resp = client.get("/api/v1/notifications", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Welcome Bob"

    def test_unauthenticated_request_rejected(self, client: TestClient):
        """Calling without authentication returns HTTP 401 NOT_AUTHENTICATED."""
        resp = client.get("/api/v1/notifications")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "NOT_AUTHENTICATED"


class TestMarkNotificationRead:
    """Verifies PATCH /api/v1/notifications/{id}/read and POST /api/v1/notifications/read-all."""

    def test_mark_individual_notification_as_read(self, client: TestClient, notif_db_session: Session):
        """Alice marks one of her unread notifications as read."""
        alice = notif_db_session.query(User).filter(User.email == "alice@example.com").one()
        unread_notif = (
            notif_db_session.query(Notification)
            .filter(Notification.user_id == alice.id, Notification.is_read.is_(False))
            .first()
        )
        headers = auth_headers_for(alice)

        resp = client.patch(f"/api/v1/notifications/{unread_notif.id}/read", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True

        # Verify DB state
        refreshed = notif_db_session.get(Notification, unread_notif.id)
        assert refreshed.is_read is True

    def test_cannot_mark_other_users_notification_as_read(self, client: TestClient, notif_db_session: Session):
        """Alice attempting to mark Bob's notification receives HTTP 404 NOT_FOUND."""
        alice = notif_db_session.query(User).filter(User.email == "alice@example.com").one()
        bob = notif_db_session.query(User).filter(User.email == "bob@example.com").one()
        bob_notif = notif_db_session.query(Notification).filter(Notification.user_id == bob.id).first()

        headers = auth_headers_for(alice)
        resp = client.patch(f"/api/v1/notifications/{bob_notif.id}/read", headers=headers)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOTIFICATION_NOT_FOUND"

    def test_mark_all_notifications_as_read(self, client: TestClient, notif_db_session: Session):
        """Alice marks all her unread notifications as read."""
        alice = notif_db_session.query(User).filter(User.email == "alice@example.com").one()
        headers = auth_headers_for(alice)

        resp = client.post("/api/v1/notifications/read-all", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_count"] == 2

        # Verify Alice now has 0 unread
        unread_alice = (
            notif_db_session.query(Notification)
            .filter(Notification.user_id == alice.id, Notification.is_read.is_(False))
            .count()
        )
        assert unread_alice == 0

        # Verify Bob's notification was NOT affected
        bob = notif_db_session.query(User).filter(User.email == "bob@example.com").one()
        bob_unread = (
            notif_db_session.query(Notification)
            .filter(Notification.user_id == bob.id, Notification.is_read.is_(False))
            .count()
        )
        assert bob_unread == 1
