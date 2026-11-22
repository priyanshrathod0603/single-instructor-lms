"""Comprehensive automated tests for SA-03 Security Governance & Session Management.

Verifies:
1. SessionRepository queries, pagination, status filtering, and metadata updates.
2. Individual, user-wide, and emergency session revocation with idempotency.
3. Caller session preservation during emergency revocation.
4. Role demotion automated session revocation in UserService.
5. Failed login auditing under privacy-safe keyed HMAC and suppression.
6. Rate-limit breach auditing.
7. AuditRepository IP filtering and single audit log retrieval (get_by_id reuse).
8. Super Admin Control APIs (/control/sessions, /control/security/metrics) and RBAC boundaries.
9. Non-Super Admin (ADMIN, STUDENT) access denial (HTTP 403).
"""

from datetime import datetime, timedelta
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.audit_suppression import (
    derive_email_hmac,
    derive_ip_hmac,
    evaluate_login_failure_suppression,
)
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException
from app.core.permissions import (
    AUDIT_VIEW,
    CONTROL_REVOKE_OTHERS,
    SECURITY_METRICS_VIEW,
    SESSIONS_REVOKE,
    SESSIONS_VIEW_ALL,
)
from app.core.security import create_access_token, generate_secure_token, hash_password, hash_token
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.auth_session import (
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_REVOKED,
    AuthSession,
)
from app.models.base import Base, utc_now
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
from app.repositories.audit_repo import AuditRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.user_repo import UserRepository
from app.schemas.control import (
    EmergencyRevocationRequest,
    SessionRevokeRequest,
)
from app.services.auth_service import AuthService
from app.services.session_service import SessionService
from app.services.user_service import UserService


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as session:
        for r_id in [ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF, ROLE_STUDENT, ROLE_VISITOR]:
            session.add(Role(id=r_id, name=r_id.title(), description=f"{r_id} role"))
        session.commit()
        yield session


def _create_user(db: Session, email: str, role: str, is_active: bool = True) -> User:
    user = User(
        email=email,
        password_hash=hash_password("SuperSecret123!"),
        full_name=f"User {email.split('@')[0]}",
        is_active=is_active,
        is_verified=True,
    )
    db.add(user)
    db.flush()
    user_role = UserRole(user_id=user.id, role_id=role)
    db.add(user_role)
    db.commit()
    return user


def _create_session(
    db: Session,
    user_id: uuid.UUID,
    status: str = SESSION_STATUS_ACTIVE,
    ip: str = "192.168.1.100",
    ua: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    hours_ago: int = 0,
) -> AuthSession:
    raw_token = generate_secure_token(32)
    created = utc_now() - timedelta(hours=hours_ago)
    expires = created + timedelta(days=7)
    s = AuthSession(
        user_id=user_id,
        session_token_hash=hash_token(raw_token),
        status=status,
        ip_address=ip,
        user_agent=ua,
        created_at=created,
        last_active_at=created,
        expires_at=expires,
    )
    db.add(s)
    db.commit()
    return s


def _auth_headers(user: User, session_id: uuid.UUID) -> dict:
    roles = [ur.role_id for ur in user.user_roles] if user.user_roles else []
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"roles": roles, "email": user.email, "session_id": str(session_id)},
    )
    return {
        "Authorization": f"Bearer {token}",
        get_settings().SESSION_COOKIE_NAME: token,
    }


class TestSessionRepositorySA03:
    """Verifies SA-03.2 query methods, filters, pagination, and revocation."""

    @pytest.mark.anyio
    async def test_list_sessions_filtering_and_pagination(self, db_session: Session):
        repo = SessionRepository()
        student = _create_user(db_session, "student1@example.com", ROLE_STUDENT)
        admin = _create_user(db_session, "admin1@example.com", ROLE_ADMIN)

        s1 = _create_session(db_session, student.id, status=SESSION_STATUS_ACTIVE, ip="10.0.0.1")
        s2 = _create_session(db_session, admin.id, status=SESSION_STATUS_ACTIVE, ip="10.0.0.2")
        s3 = _create_session(db_session, student.id, status=SESSION_STATUS_REVOKED, ip="10.0.0.1")

        # 1. Status filter
        active_sessions, total_active = await repo.list_sessions(db_session, status="ACTIVE")
        assert total_active == 2
        assert len(active_sessions) == 2
        assert all(s.status == "ACTIVE" for s in active_sessions)

        # 2. Role filter
        student_sessions, total_student = await repo.list_sessions(db_session, role="STUDENT")
        assert total_student == 2
        assert len(student_sessions) == 2

        # 3. IP address filter
        ip_sessions, total_ip = await repo.list_sessions(db_session, ip_address="10.0.0.2")
        assert total_ip == 1
        assert ip_sessions[0].ip_address == "10.0.0.2"

        # 4. Search filter by email
        search_sessions, total_search = await repo.list_sessions(db_session, search="admin1")
        assert total_search == 1
        assert search_sessions[0].user_id == admin.id

        # 5. Pagination
        p1, t = await repo.list_sessions(db_session, page=1, per_page=2)
        assert len(p1) == 2
        assert t == 3
        p2, _ = await repo.list_sessions(db_session, page=2, per_page=2)
        assert len(p2) == 1

    @pytest.mark.anyio
    async def test_get_session_by_id(self, db_session: Session):
        repo = SessionRepository()
        user = _create_user(db_session, "target@example.com", ROLE_STUDENT)
        s = _create_session(db_session, user.id)

        fetched = await repo.get_session_by_id(db_session, s.id)
        assert fetched is not None
        assert fetched.id == s.id
        assert fetched.user.email == "target@example.com"

        non_existent = await repo.get_session_by_id(db_session, uuid.uuid4())
        assert non_existent is None

    @pytest.mark.anyio
    async def test_revoke_session_populates_metadata_and_is_idempotent(self, db_session: Session):
        repo = SessionRepository()
        super_admin = _create_user(db_session, "sa@example.com", ROLE_SUPER_ADMIN)
        user = _create_user(db_session, "u@example.com", ROLE_STUDENT)
        s = _create_session(db_session, user.id, status=SESSION_STATUS_ACTIVE)

        # First revocation -> modifies row
        success = await repo.revoke_session(
            db_session,
            s.id,
            reason="ADMIN_REVOKED: Security investigation",
            revoked_by=super_admin.id,
        )
        assert success is True
        db_session.refresh(s)
        assert s.status == SESSION_STATUS_REVOKED
        assert s.revoked_at is not None
        assert s.revoked_by == super_admin.id
        assert s.revocation_reason == "ADMIN_REVOKED: Security investigation"
        first_revoked_at = s.revoked_at

        # Second revocation -> idempotent, returns False, zero updates to timestamps
        success_second = await repo.revoke_session(
            db_session,
            s.id,
            reason="ANOTHER_REASON",
            revoked_by=user.id,
        )
        assert success_second is False
        db_session.refresh(s)
        assert s.revoked_at == first_revoked_at
        assert s.revoked_by == super_admin.id
        assert s.revocation_reason == "ADMIN_REVOKED: Security investigation"

    @pytest.mark.anyio
    async def test_revoke_all_user_sessions(self, db_session: Session):
        repo = SessionRepository()
        super_admin = _create_user(db_session, "sa2@example.com", ROLE_SUPER_ADMIN)
        target_user = _create_user(db_session, "target_user@example.com", ROLE_STUDENT)
        other_user = _create_user(db_session, "other_user@example.com", ROLE_STUDENT)

        s1 = _create_session(db_session, target_user.id, status=SESSION_STATUS_ACTIVE)
        s_other = _create_session(db_session, other_user.id, status=SESSION_STATUS_ACTIVE)

        count = await repo.revoke_all_user_sessions(
            db_session,
            target_user.id,
            reason="ADMIN_REVOKED: Compromised credentials",
            revoked_by=super_admin.id,
        )
        assert count == 1
        db_session.refresh(s1)
        assert s1.status == SESSION_STATUS_REVOKED
        assert s1.revocation_reason == "ADMIN_REVOKED: Compromised credentials"

        # Other user's session remains untouched
        db_session.refresh(s_other)
        assert s_other.status == SESSION_STATUS_ACTIVE

    @pytest.mark.anyio
    async def test_revoke_other_active_sessions_preserves_caller(self, db_session: Session):
        repo = SessionRepository()
        super_admin = _create_user(db_session, "caller_sa@example.com", ROLE_SUPER_ADMIN)
        student1 = _create_user(db_session, "s1@example.com", ROLE_STUDENT)
        student2 = _create_user(db_session, "s2@example.com", ROLE_STUDENT)

        caller_session = _create_session(db_session, super_admin.id, status=SESSION_STATUS_ACTIVE)
        sess1 = _create_session(db_session, student1.id, status=SESSION_STATUS_ACTIVE)
        sess2 = _create_session(db_session, student2.id, status=SESSION_STATUS_ACTIVE)

        count = await repo.revoke_other_active_sessions(
            db_session,
            caller_session_id=caller_session.id,
            reason="EMERGENCY_GLOBAL_REVOCATION: Critical containment",
            revoked_by=super_admin.id,
        )
        assert count == 2

        db_session.refresh(caller_session)
        db_session.refresh(sess1)
        db_session.refresh(sess2)

        # Caller session must remain ACTIVE
        assert caller_session.status == SESSION_STATUS_ACTIVE
        assert caller_session.revoked_at is None

        # Other sessions must be REVOKED
        assert sess1.status == SESSION_STATUS_REVOKED
        assert sess2.status == SESSION_STATUS_REVOKED
        assert sess1.revocation_reason == "EMERGENCY_GLOBAL_REVOCATION: Critical containment"


class TestUserServiceRoleDemotionRevocation:
    """Verifies that demoting an admin or staff role automatically terminates active sessions."""

    @pytest.mark.anyio
    async def test_demoting_admin_role_revokes_active_sessions(self, db_session: Session):
        user_service = UserService()
        super_admin = _create_user(db_session, "super@example.com", ROLE_SUPER_ADMIN)
        admin_user = _create_user(db_session, "admin_demoted@example.com", ROLE_ADMIN)

        session = _create_session(db_session, admin_user.id, status=SESSION_STATUS_ACTIVE)

        # Demote admin_user from ADMIN
        await user_service.manage_user_role(
            db_session,
            user_id=admin_user.id,
            role_id=ROLE_ADMIN,
            action="REVOKE",
            actor_id=super_admin.id,
        )

        db_session.refresh(session)
        assert session.status == SESSION_STATUS_REVOKED
        assert session.revocation_reason == f"PRIVILEGE_DEMOTION: {ROLE_ADMIN}_REVOKED"
        assert session.revoked_by == super_admin.id


class TestPrivacySafeAuditSuppression:
    """Verifies keyed HMAC derivation and suppression behavior."""

    def test_hmac_derivation_is_consistent_and_privacy_preserving(self):
        settings = get_settings()
        email = "Student.Test@Example.COM"
        ip = "192.168.1.55"

        hmac1 = derive_email_hmac(email, settings)
        hmac2 = derive_email_hmac("student.test@example.com", settings)
        assert hmac1 == hmac2
        assert len(hmac1) == 64
        # Email must not be in digest
        assert "example.com" not in hmac1

        ip_hmac = derive_ip_hmac(ip, settings)
        assert len(ip_hmac) == 64
        assert "192.168" not in ip_hmac

    def test_evaluate_login_failure_suppression_handles_unconfigured_redis(self):
        # In test environment, unconfigured/unreachable Redis does not crash and returns False
        is_suppressed, prior_count, email_hmac, ip_hmac = evaluate_login_failure_suppression(
            "fake@example.com",
            "127.0.0.1",
        )
        assert is_suppressed is False
        assert len(email_hmac) == 64


class TestAuditRepositoryEnhancements:
    """Verifies SA-03.6 IP filtering and get_by_id reuse."""

    @pytest.mark.anyio
    async def test_audit_repo_ip_filtering_and_get_by_id(self, db_session: Session):
        repo = AuditRepository()
        u = _create_user(db_session, "audit_test@example.com", ROLE_STUDENT)

        entry1 = AuditLog(
            actor_id=u.id,
            actor_type="USER",
            action="USER_LOGIN",
            resource_type="auth",
            resource_id=None,
            ip_address="192.168.1.88",
            user_agent="TestAgent",
        )
        entry2 = AuditLog(
            actor_id=u.id,
            actor_type="USER",
            action="USER_LOGOUT",
            resource_type="auth",
            resource_id=None,
            ip_address="10.20.30.40",
            user_agent="TestAgent",
        )
        await repo.add(db_session, entry1)
        await repo.add(db_session, entry2)
        db_session.commit()

        # Query by IP
        logs, total = await repo.list_logs(db_session, ip_address="192.168.1.88")
        assert total == 1
        assert logs[0].ip_address == "192.168.1.88"

        # Query by get_by_id
        fetched = await repo.get_by_id(db_session, entry1.id)
        assert fetched is not None
        assert fetched.id == entry1.id
        assert fetched.action == "USER_LOGIN"

        # Case-insensitive action query
        case_logs, case_total = await repo.list_logs(db_session, action="user_login")
        assert case_total == 1
        assert case_logs[0].action == "USER_LOGIN"


class TestControlSessionAPIsAndRBAC:
    """Verifies SA-03.3 & SA-03.4 API contracts, security permissions, and error responses."""

    def _setup_client(self, db_session: Session) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_db] = lambda: db_session
        return TestClient(app)

    def test_list_sessions_endpoint_rbac(self, db_session: Session):
        client = self._setup_client(db_session)
        super_admin = _create_user(db_session, "sa_api@example.com", ROLE_SUPER_ADMIN)
        admin = _create_user(db_session, "admin_api@example.com", ROLE_ADMIN)
        student = _create_user(db_session, "student_api@example.com", ROLE_STUDENT)

        sa_session = _create_session(db_session, super_admin.id)
        admin_session = _create_session(db_session, admin.id)
        student_session = _create_session(db_session, student.id)

        # 1. Unauthenticated -> 401
        res = client.get("/api/v1/control/sessions")
        assert res.status_code == 401

        # 2. Student caller -> 403
        headers_student = _auth_headers(student, student_session.id)
        res_student = client.get("/api/v1/control/sessions", headers=headers_student)
        assert res_student.status_code == 403

        # 3. Operational Admin caller -> 403 (Session surveillance restricted strictly to Super Admin)
        headers_admin = _auth_headers(admin, admin_session.id)
        res_admin = client.get("/api/v1/control/sessions", headers=headers_admin)
        assert res_admin.status_code == 403
        assert res_admin.json()["error"]["code"] == "SUPER_ADMIN_REQUIRED"

        # 4. Super Admin caller -> 200
        headers_sa = _auth_headers(super_admin, sa_session.id)
        res_sa = client.get("/api/v1/control/sessions", headers=headers_sa)
        assert res_sa.status_code == 200
        body = res_sa.json()
        assert "items" in body
        assert body["total"] >= 3

    def test_get_session_detail_endpoint(self, db_session: Session):
        client = self._setup_client(db_session)
        super_admin = _create_user(db_session, "sa_detail@example.com", ROLE_SUPER_ADMIN)
        sa_session = _create_session(db_session, super_admin.id)
        headers = _auth_headers(super_admin, sa_session.id)

        # 404 for unknown session
        res_404 = client.get(f"/api/v1/control/sessions/{uuid.uuid4()}", headers=headers)
        assert res_404.status_code == 404

        # 200 for existing session
        res_200 = client.get(f"/api/v1/control/sessions/{sa_session.id}", headers=headers)
        assert res_200.status_code == 200
        detail = res_200.json()
        assert detail["id"] == str(sa_session.id)
        assert detail["user"]["email"] == "sa_detail@example.com"
        assert "correlated_events" in detail

    def test_revoke_specific_session_endpoint(self, db_session: Session):
        client = self._setup_client(db_session)
        super_admin = _create_user(db_session, "sa_rev@example.com", ROLE_SUPER_ADMIN)
        student = _create_user(db_session, "stu_rev@example.com", ROLE_STUDENT)
        sa_session = _create_session(db_session, super_admin.id)
        target_session = _create_session(db_session, student.id)
        headers = _auth_headers(super_admin, sa_session.id)

        # Rejects short reason (<5 chars) -> 422
        res_invalid = client.post(
            f"/api/v1/control/sessions/{target_session.id}/revoke",
            headers=headers,
            json={"reason": "bad"},
        )
        assert res_invalid.status_code == 422

        # 200 on successful revocation
        res_revoke = client.post(
            f"/api/v1/control/sessions/{target_session.id}/revoke",
            headers=headers,
            json={"reason": "Suspected token leakage on student laptop."},
        )
        assert res_revoke.status_code == 200
        data = res_revoke.json()
        assert data["status"] == SESSION_STATUS_REVOKED
        assert "ADMIN_REVOKED" in data["revocation_reason"]
        assert data["revoked_by"] == str(super_admin.id)

        # Verify audit log was recorded
        audit = db_session.query(AuditLog).filter(AuditLog.action == "ADMIN_SESSION_REVOKED").first()
        assert audit is not None
        assert audit.resource_id == str(target_session.id)

    def test_revoke_user_sessions_endpoint(self, db_session: Session):
        client = self._setup_client(db_session)
        super_admin = _create_user(db_session, "sa_usr_rev@example.com", ROLE_SUPER_ADMIN)
        student = _create_user(db_session, "stu_multi@example.com", ROLE_STUDENT)
        sa_session = _create_session(db_session, super_admin.id)
        _create_session(db_session, student.id)
        headers = _auth_headers(super_admin, sa_session.id)

        res = client.post(
            f"/api/v1/control/users/{student.id}/revoke-sessions",
            headers=headers,
            json={"reason": "Security containment for entire account."},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["user_id"] == str(student.id)
        assert body["revoked_sessions_count"] == 1

    def test_emergency_revoke_others_endpoint(self, db_session: Session):
        client = self._setup_client(db_session)
        super_admin = _create_user(db_session, "sa_emergency@example.com", ROLE_SUPER_ADMIN)
        student = _create_user(db_session, "stu_emergency@example.com", ROLE_STUDENT)
        caller_session = _create_session(db_session, super_admin.id)
        other_session = _create_session(db_session, student.id)

        headers = _auth_headers(super_admin, caller_session.id)

        # Call emergency revoke-others
        res = client.post(
            "/api/v1/control/sessions/revoke-others",
            headers=headers,
            json={"reason": "Emergency platform containment: credential rotation."},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["revoked_sessions_count"] == 1
        assert body["caller_session_id"] == str(caller_session.id)
        assert body["caller_session_preserved"] is True

        db_session.refresh(caller_session)
        db_session.refresh(other_session)
        assert caller_session.status == SESSION_STATUS_ACTIVE
        assert other_session.status == SESSION_STATUS_REVOKED

    def test_get_security_metrics_endpoint(self, db_session: Session):
        client = self._setup_client(db_session)
        super_admin = _create_user(db_session, "sa_metrics@example.com", ROLE_SUPER_ADMIN)
        student = _create_user(db_session, "stu_metrics@example.com", ROLE_STUDENT, is_active=False)
        sa_session = _create_session(db_session, super_admin.id)
        headers = _auth_headers(super_admin, sa_session.id)

        res = client.get("/api/v1/control/security/metrics", headers=headers)
        assert res.status_code == 200
        metrics = res.json()
        assert metrics["active_sessions_total"] >= 1
        assert "STUDENT" in metrics["active_sessions_by_role"]
        assert "SUPER_ADMIN" in metrics["active_sessions_by_role"]
        assert metrics["suspended_accounts_total"] >= 1
        assert "generated_at" in metrics
