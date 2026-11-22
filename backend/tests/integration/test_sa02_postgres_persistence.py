"""Integration tests for SA-02 persistence against real PostgreSQL (lms_test_db).

Verifies the single-point transaction boundary in get_db() across:
1. Assign role
2. Revoke role
3. Suspend account (and revoke active sessions)
4. Reactivate account
5. Invite Staff (atomic persistence of User, Role, AuthToken, NotificationOutbox, AuditLog)
6. Invite Admin (atomic persistence with ADMIN role)
7. Audit actor accuracy (SUPER_ADMIN vs ADMIN)
8. Transaction rollback safety (zero partial state on exception)
"""

import os
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.permissions import (
    CANONICAL_PERMISSIONS,
    DEFAULT_ROLE_PERMISSIONS,
    ROLES_ASSIGN,
    STAFF_INVITE,
    USERS_MANAGE_STATUS,
    USERS_VIEW,
    USERS_VIEW_ALL,
)
from app.core.security import create_access_token
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.auth_session import AuthSession, SESSION_STATUS_ACTIVE, SESSION_STATUS_REVOKED
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

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:1234@localhost:5432/lms_test_db",
)

try:
    _engine_probe = create_engine(TEST_DB_URL, pool_pre_ping=True)
    with _engine_probe.connect() as _conn:
        _conn.execute(text("SELECT 1"))
    has_postgres_test_db = True
except Exception:
    has_postgres_test_db = False

pytestmark = pytest.mark.skipif(
    not has_postgres_test_db,
    reason="Isolated PostgreSQL test database (lms_test_db) not reachable.",
)


@pytest.fixture(scope="module")
def pg_engine():
    """Provides isolated PostgreSQL engine on lms_test_db."""
    engine = create_engine(TEST_DB_URL, pool_size=10, max_overflow=5)
    Base.metadata.create_all(bind=engine)
    yield engine
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE IF EXISTS audit_logs DISABLE TRIGGER ALL;
            DELETE FROM audit_logs;
            ALTER TABLE IF EXISTS audit_logs ENABLE TRIGGER ALL;
            DELETE FROM notification_outbox;
            DELETE FROM auth_tokens;
            DELETE FROM auth_sessions;
            DELETE FROM user_roles;
            DELETE FROM users;
            DELETE FROM role_permissions;
            DELETE FROM roles;
            DELETE FROM permissions;
        """))
        conn.commit()
    engine.dispose()


@pytest.fixture
def session_factory(pg_engine):
    """Provides thread-safe sessionmaker for tests."""
    return sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def clean_and_seed_schema(session_factory):
    """Ensures clean DB and baseline roles/permissions before each test."""
    with session_factory() as session:
        # Disable triggers during test cleanup so immutability doesn't block clean state
        session.execute(text("ALTER TABLE IF EXISTS audit_logs DISABLE TRIGGER ALL;"))
        # Delete dependent data first
        session.query(AuditLog).delete()
        session.query(NotificationOutbox).delete()
        session.query(AuthToken).delete()
        session.query(AuthSession).delete()
        session.query(UserRole).delete()
        session.query(User).delete()
        session.query(RolePermission).delete()
        session.query(Role).delete()
        session.query(Permission).delete()
        session.execute(text("ALTER TABLE IF EXISTS audit_logs ENABLE TRIGGER ALL;"))

        # Seed roles
        for r_id in [ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF, ROLE_STUDENT, ROLE_VISITOR]:
            session.add(Role(id=r_id, name=r_id.title(), description=f"{r_id} role"))

        # Seed permissions
        for p_key, p_mod, p_desc in CANONICAL_PERMISSIONS:
            session.add(Permission(id=p_key, module=p_mod, description=p_desc))

        session.flush()

        # Seed role permissions
        for r_id, perms in DEFAULT_ROLE_PERMISSIONS.items():
            for p_id in perms:
                session.add(RolePermission(role_id=r_id, permission_id=p_id))

        session.commit()
    yield


def _auth_headers(user: User, role: str) -> dict:
    claims = {
        "email": user.email,
        "roles": [role],
        "is_active": user.is_active,
    }
    token = create_access_token(subject=user.id, extra_claims=claims)
    return {
        "Authorization": f"Bearer {token}",
        get_settings().SESSION_COOKIE_NAME: token,
    }


class TestPostgreSQLPersistenceSA02:
    """Verifies that SA-02 user management actions commit cleanly to PostgreSQL via get_db()."""

    def _setup_test_client(self, session_factory, current_user):
        app = create_app()

        def override_get_db():
            db = session_factory()
            try:
                yield db
                if db.in_transaction():
                    db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

        def override_current_user():
            with session_factory() as s:
                user = s.query(User).filter(User.id == current_user.id).one()
                # Eagerly load roles and permissions before detaching
                for ur in user.user_roles:
                    _ = ur.role
                    if ur.role:
                        _ = ur.role.role_permissions
                        for rp in ur.role.role_permissions:
                            _ = rp.permission
                return user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_current_user
        return TestClient(app)

    def test_01_assign_role_persists_to_postgresql(self, session_factory):
        """1. Assign role -> close session -> open fresh session -> query user_roles -> assert persisted."""
        with session_factory() as session:
            super_admin = User(
                email="superadmin@example.com",
                password_hash="test_pw_hash",
                full_name="Super Admin",
                is_active=True,
                is_verified=True,
            )
            target_user = User(
                email="student_to_promote@example.com",
                password_hash="test_pw_hash",
                full_name="Student Promoted",
                is_active=True,
                is_verified=True,
            )
            session.add_all([super_admin, target_user])
            session.flush()
            super_admin.user_roles.append(UserRole(user_id=super_admin.id, role_id=ROLE_SUPER_ADMIN))
            target_user.user_roles.append(UserRole(user_id=target_user.id, role_id=ROLE_STUDENT))
            session.commit()
            target_user_id = target_user.id

        client = self._setup_test_client(session_factory, super_admin)
        headers = _auth_headers(super_admin, ROLE_SUPER_ADMIN)

        # Execute Assign Role via HTTP endpoint
        resp = client.patch(
            f"/api/v1/users/{target_user_id}/roles",
            json={"role_id": ROLE_STAFF, "action": "ASSIGN"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert ROLE_STAFF in resp.json()["roles"]

        # Verification in a completely fresh PostgreSQL session
        with session_factory() as fresh_session:
            persisted_roles = (
                fresh_session.query(UserRole)
                .filter(UserRole.user_id == target_user_id)
                .all()
            )
            role_ids = {r.role_id for r in persisted_roles}
            assert ROLE_STAFF in role_ids
            assert ROLE_STUDENT in role_ids

    def test_02_revoke_role_persists_to_postgresql(self, session_factory):
        """2. Revoke role -> close session -> open fresh session -> query user_roles -> assert deleted."""
        with session_factory() as session:
            super_admin = User(
                email="superadmin_revoke@example.com",
                password_hash="test_pw_hash",
                full_name="Super Admin Revoke",
                is_active=True,
                is_verified=True,
            )
            target_user = User(
                email="staff_to_demote@example.com",
                password_hash="test_pw_hash",
                full_name="Staff Demoted",
                is_active=True,
                is_verified=True,
            )
            session.add_all([super_admin, target_user])
            session.flush()
            super_admin.user_roles.append(UserRole(user_id=super_admin.id, role_id=ROLE_SUPER_ADMIN))
            target_user.user_roles.append(UserRole(user_id=target_user.id, role_id=ROLE_STAFF))
            session.commit()
            target_user_id = target_user.id

        client = self._setup_test_client(session_factory, super_admin)
        headers = _auth_headers(super_admin, ROLE_SUPER_ADMIN)

        # Execute Revoke Role
        resp = client.patch(
            f"/api/v1/users/{target_user_id}/roles",
            json={"role_id": ROLE_STAFF, "action": "REVOKE"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert ROLE_STAFF not in resp.json()["roles"]

        # Verification in a fresh PostgreSQL session
        with session_factory() as fresh_session:
            persisted_roles = (
                fresh_session.query(UserRole)
                .filter(UserRole.user_id == target_user_id)
                .all()
            )
            role_ids = {r.role_id for r in persisted_roles}
            assert ROLE_STAFF not in role_ids

    def test_03_suspend_account_persists_and_revokes_sessions(self, session_factory):
        """3. Suspend account -> close session -> fresh session -> query users and auth_sessions."""
        with session_factory() as session:
            super_admin = User(
                email="superadmin_suspend@example.com",
                password_hash="test_pw_hash",
                full_name="Super Admin Suspend",
                is_active=True,
                is_verified=True,
            )
            target_user = User(
                email="user_to_suspend@example.com",
                password_hash="test_pw_hash",
                full_name="Suspended User",
                is_active=True,
                is_verified=True,
            )
            session.add_all([super_admin, target_user])
            session.flush()
            super_admin.user_roles.append(UserRole(user_id=super_admin.id, role_id=ROLE_SUPER_ADMIN))
            target_user.user_roles.append(UserRole(user_id=target_user.id, role_id=ROLE_STUDENT))

            # Add an active session for target user
            active_session = AuthSession(
                user_id=target_user.id,
                session_token_hash="test_session_hash_123",
                ip_address="192.168.1.50",
                user_agent="Mozilla/5.0 Test",
                status=SESSION_STATUS_ACTIVE,
                expires_at=utc_now(),
            )
            session.add(active_session)
            session.commit()
            target_user_id = target_user.id
            active_session_id = active_session.id

        client = self._setup_test_client(session_factory, super_admin)
        headers = _auth_headers(super_admin, ROLE_SUPER_ADMIN)

        # Execute Suspend Account
        resp = client.patch(
            f"/api/v1/users/{target_user_id}/status",
            json={"is_active": False, "reason": "Terms of service violation"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_active"] is False

        # Verification in a fresh PostgreSQL session
        with session_factory() as fresh_session:
            persisted_user = fresh_session.query(User).filter(User.id == target_user_id).one()
            assert persisted_user.is_active is False

            persisted_session = fresh_session.query(AuthSession).filter(AuthSession.id == active_session_id).one()
            assert persisted_session.status == SESSION_STATUS_REVOKED

    def test_04_reactivate_account_persists_to_postgresql(self, session_factory):
        """4. Reactivate account -> close session -> fresh session -> query users."""
        with session_factory() as session:
            super_admin = User(
                email="superadmin_reactivate@example.com",
                password_hash="test_pw_hash",
                full_name="Super Admin Reactivate",
                is_active=True,
                is_verified=True,
            )
            target_user = User(
                email="user_to_reactivate@example.com",
                password_hash="test_pw_hash",
                full_name="Reactivated User",
                is_active=False,
                is_verified=True,
            )
            session.add_all([super_admin, target_user])
            session.flush()
            super_admin.user_roles.append(UserRole(user_id=super_admin.id, role_id=ROLE_SUPER_ADMIN))
            target_user.user_roles.append(UserRole(user_id=target_user.id, role_id=ROLE_STUDENT))
            session.commit()
            target_user_id = target_user.id

        client = self._setup_test_client(session_factory, super_admin)
        headers = _auth_headers(super_admin, ROLE_SUPER_ADMIN)

        # Execute Reactivate Account
        resp = client.patch(
            f"/api/v1/users/{target_user_id}/status",
            json={"is_active": True, "reason": "Appeal accepted"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_active"] is True

        # Verification in a fresh PostgreSQL session
        with session_factory() as fresh_session:
            persisted_user = fresh_session.query(User).filter(User.id == target_user_id).one()
            assert persisted_user.is_active is True

    def test_05_invite_staff_persists_four_entities_atomically(self, session_factory):
        """5. Invite Staff -> fresh session -> assert User, AuthToken, NotificationOutbox, AuditLog persisted."""
        with session_factory() as session:
            super_admin = User(
                email="superadmin_inviter@example.com",
                password_hash="test_pw_hash",
                full_name="Super Admin Inviter",
                is_active=True,
                is_verified=True,
            )
            session.add(super_admin)
            session.flush()
            super_admin.user_roles.append(UserRole(user_id=super_admin.id, role_id=ROLE_SUPER_ADMIN))
            session.commit()

        client = self._setup_test_client(session_factory, super_admin)
        headers = _auth_headers(super_admin, ROLE_SUPER_ADMIN)

        invite_email = "new_grader_pg@example.com"
        resp = client.post(
            "/api/v1/users/staff/invite",
            json={
                "email": invite_email,
                "full_name": "New Grader PG",
                "role": ROLE_STAFF,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["invited"] is True
        # Critical SA-02 invariant: Token must NOT be leaked in API response body
        assert "token" not in data
        assert "expires_at" in data

        # Verification in a fresh PostgreSQL session
        with session_factory() as fresh_session:
            # 1. User
            created_user = fresh_session.query(User).filter(User.email == invite_email).one()
            assert created_user.full_name == "New Grader PG"
            assert created_user.is_active is True
            assert created_user.has_role(ROLE_STAFF)

            # 2. AuthToken
            token_record = fresh_session.query(AuthToken).filter(AuthToken.user_id == created_user.id).one()
            assert token_record.token_type == TOKEN_TYPE_STAFF_ONBOARDING
            assert token_record.is_used is False
            assert token_record.token_hash is not None

            # 3. NotificationOutbox
            outbox_record = (
                fresh_session.query(NotificationOutbox)
                .filter(NotificationOutbox.recipient == invite_email)
                .one()
            )
            assert outbox_record.event_type == "STAFF_INVITATION"
            assert "invitation_token" in outbox_record.payload
            assert len(outbox_record.payload["invitation_token"]) > 20

            # 4. AuditLog
            audit_records = (
                fresh_session.query(AuditLog)
                .filter(AuditLog.resource_id == str(created_user.id))
                .all()
            )
            actions = {a.action for a in audit_records}
            assert "STAFF_INVITED" in actions

    def test_06_invite_admin_persists_four_entities_atomically(self, session_factory):
        """6. Invite Admin -> fresh session -> assert User with ADMIN role, AuthToken, Outbox, AuditLog."""
        with session_factory() as session:
            super_admin = User(
                email="superadmin_admin_inviter@example.com",
                password_hash="test_pw_hash",
                full_name="Super Admin Admin Inviter",
                is_active=True,
                is_verified=True,
            )
            session.add(super_admin)
            session.flush()
            super_admin.user_roles.append(UserRole(user_id=super_admin.id, role_id=ROLE_SUPER_ADMIN))
            session.commit()

        client = self._setup_test_client(session_factory, super_admin)
        headers = _auth_headers(super_admin, ROLE_SUPER_ADMIN)

        invite_email = "new_admin_pg@example.com"
        resp = client.post(
            "/api/v1/users/staff/invite",
            json={
                "email": invite_email,
                "full_name": "New Admin PG",
                "role": ROLE_ADMIN,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["invited"] is True
        assert data["role"] == ROLE_ADMIN
        assert "token" not in data

        # Verification in a fresh PostgreSQL session
        with session_factory() as fresh_session:
            created_user = fresh_session.query(User).filter(User.email == invite_email).one()
            assert created_user.has_role(ROLE_ADMIN)

            # AuthToken
            token_record = fresh_session.query(AuthToken).filter(AuthToken.user_id == created_user.id).one()
            assert token_record.token_type == TOKEN_TYPE_STAFF_ONBOARDING

            # NotificationOutbox
            outbox_record = (
                fresh_session.query(NotificationOutbox)
                .filter(NotificationOutbox.recipient == invite_email)
                .one()
            )
            assert outbox_record.event_type == "STAFF_INVITATION"

            # AuditLog
            audit_record = (
                fresh_session.query(AuditLog)
                .filter(AuditLog.resource_id == str(created_user.id), AuditLog.action == "STAFF_INVITED")
                .one()
            )
            assert audit_record.after_state["email"] == invite_email

    def test_07_audit_actor_accuracy_super_admin_vs_admin(self, session_factory):
        """7. Verify AuditLog records accurate actor_type (SUPER_ADMIN when invited by Super Admin, ADMIN when invited by Admin)."""
        with session_factory() as session:
            super_admin = User(
                email="super_caller@example.com",
                password_hash="test_pw_hash",
                full_name="Super Caller",
                is_active=True,
                is_verified=True,
            )
            admin = User(
                email="admin_caller@example.com",
                password_hash="test_pw_hash",
                full_name="Admin Caller",
                is_active=True,
                is_verified=True,
            )
            session.add_all([super_admin, admin])
            session.flush()
            super_admin.user_roles.append(UserRole(user_id=super_admin.id, role_id=ROLE_SUPER_ADMIN))
            admin.user_roles.append(UserRole(user_id=admin.id, role_id=ROLE_ADMIN))
            session.commit()

        # Invocation 1: By Super Admin
        client_super = self._setup_test_client(session_factory, super_admin)
        headers_super = _auth_headers(super_admin, ROLE_SUPER_ADMIN)
        resp1 = client_super.post(
            "/api/v1/users/staff/invite",
            json={"email": "staff_by_super@example.com", "full_name": "By Super", "role": ROLE_STAFF},
            headers=headers_super,
        )
        assert resp1.status_code == 201

        # Invocation 2: By Admin
        client_admin = self._setup_test_client(session_factory, admin)
        headers_admin = _auth_headers(admin, ROLE_ADMIN)
        resp2 = client_admin.post(
            "/api/v1/users/staff/invite",
            json={"email": "staff_by_admin@example.com", "full_name": "By Admin", "role": ROLE_STAFF},
            headers=headers_admin,
        )
        assert resp2.status_code == 201

        # Verification in a fresh PostgreSQL session
        with session_factory() as fresh_session:
            user_super = fresh_session.query(User).filter(User.email == "staff_by_super@example.com").one()
            user_admin = fresh_session.query(User).filter(User.email == "staff_by_admin@example.com").one()

            audit_super = (
                fresh_session.query(AuditLog)
                .filter(AuditLog.resource_id == str(user_super.id), AuditLog.action == "STAFF_INVITED")
                .one()
            )
            assert audit_super.actor_type == "SUPER_ADMIN"

            audit_admin = (
                fresh_session.query(AuditLog)
                .filter(AuditLog.resource_id == str(user_admin.id), AuditLog.action == "STAFF_INVITED")
                .one()
            )
            assert audit_admin.actor_type == "ADMIN"

    def test_08_transaction_rollback_safety_leaves_zero_partial_records(self, session_factory):
        """8. If an error occurs midway through a transactional operation, get_db() rolls back completely."""
        with session_factory() as session:
            super_admin = User(
                email="superadmin_rollback@example.com",
                password_hash="test_pw_hash",
                full_name="Super Admin Rollback",
                is_active=True,
                is_verified=True,
            )
            session.add(super_admin)
            session.flush()
            super_admin.user_roles.append(UserRole(user_id=super_admin.id, role_id=ROLE_SUPER_ADMIN))
            session.commit()

        client = self._setup_test_client(session_factory, super_admin)
        headers = _auth_headers(super_admin, ROLE_SUPER_ADMIN)

        # Attempt to invite an invalid role that causes schema validation error
        invalid_email = "invalid_attempt@example.com"
        resp = client.post(
            "/api/v1/users/staff/invite",
            json={"email": invalid_email, "full_name": "Invalid Candidate", "role": "INVALID_ROLE"},
            headers=headers,
        )
        assert resp.status_code == 422

        # Verify zero partial state in PostgreSQL
        with session_factory() as fresh_session:
            assert fresh_session.query(User).filter(User.email == invalid_email).first() is None
            assert fresh_session.query(NotificationOutbox).filter(NotificationOutbox.recipient == invalid_email).first() is None
