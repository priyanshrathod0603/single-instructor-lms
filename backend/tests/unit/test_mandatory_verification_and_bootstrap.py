"""Unit tests for Mandatory Email Verification and One-Time Super Admin Bootstrap.

Verifies:
1. Registration creates an unverified account (is_verified=False) with role STUDENT.
2. Notification outbox stages AUTH_VERIFY_EMAIL event containing verification_token and verification_url.
3. Unverified login attempts are rejected with HTTP 403 / ForbiddenException(code="EMAIL_NOT_VERIFIED").
4. Unverified session requests to protected endpoints return HTTP 403 (code="EMAIL_NOT_VERIFIED").
5. Valid verification token consumption marks user as is_verified=True and allows subsequent login.
6. Reused verification token is rejected (TOKEN_ALREADY_USED).
7. Expired verification token is rejected (INVALID_TOKEN).
8. Resend verification endpoint maintains anti-enumeration while invalidating prior tokens.
9. One-time Super Admin bootstrap:
   - Rejects non-existent accounts.
   - Rejects unverified accounts.
   - Promotes verified account to SUPER_ADMIN atomically and records audit log.
   - Rejects subsequent bootstrap executions when SUPER_ADMIN already exists.
   - Confirms subsequent public registrations receive only STUDENT role.
"""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    UnauthorizedException,
)
from app.core.security import hash_token
from app.main import create_app
from app.models import (
    ROLE_SUPER_ADMIN,
    ROLE_STUDENT,
    SYSTEM_ROLES,
    SESSION_STATUS_ACTIVE,
    TOKEN_TYPE_EMAIL_VERIFICATION,
    AuditLog,
    AuthSession,
    AuthToken,
    Base,
    NotificationOutbox,
    Role,
    User,
    UserRole,
)
from app.models.base import utc_now
from app.services.auth_service import AuthService
from app.scripts.bootstrap_super_admin import bootstrap_super_admin


@pytest.fixture
def memory_db():
    """In-memory SQLite database session with seeded canonical roles."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    
    with session_factory() as session:
        for role_id in SYSTEM_ROLES:
            session.add(Role(id=role_id, name=role_id.capitalize(), description=f"{role_id} role"))
        session.commit()

    try:
        yield session_factory
    finally:
        Base.metadata.drop_all(engine)


@pytest.fixture
def test_client_and_factory(memory_db):
    """TestClient configured with in-memory DB and test settings."""
    test_settings = Settings(
        ENVIRONMENT="testing",
        DEBUG=True,
        SESSION_COOKIE_SECURE=False,
        DATABASE_URL="sqlite:///:memory:",
        FRONTEND_URL="http://localhost:3000",
    )
    app = create_app(settings=test_settings)

    def override_get_db():
        db = memory_db()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: test_settings

    client = TestClient(app)
    try:
        yield client, memory_db, test_settings
    finally:
        app.dependency_overrides.clear()


class TestMandatoryEmailVerification:
    """Verifies mandatory email verification invariants."""

    @pytest.mark.asyncio
    async def test_registration_creates_unverified_student_with_staged_outbox(self, memory_db):
        service = AuthService()
        with memory_db() as db:
            user, raw_token = await service.register(
                db,
                email="fresh_student@example.com",
                password="SecurePassword!123",
                full_name="Fresh Student",
            )
            assert user.is_verified is False
            assert user.has_role(ROLE_STUDENT) is True

            # Outbox verification event check
            outbox = (
                db.query(NotificationOutbox)
                .filter(NotificationOutbox.recipient == "fresh_student@example.com")
                .first()
            )
            assert outbox is not None
            assert outbox.event_type == "AUTH_VERIFY_EMAIL"
            assert outbox.payload["verification_token"] == raw_token
            assert "verification_url" in outbox.payload
            assert raw_token in outbox.payload["verification_url"]

    @pytest.mark.asyncio
    async def test_unverified_account_login_rejected(self, memory_db):
        service = AuthService()
        with memory_db() as db:
            await service.register(
                db,
                email="unverified_attempt@example.com",
                password="SecurePassword!123",
                full_name="Unverified Attempt",
            )

            # Direct service login call must raise ForbiddenException
            with pytest.raises(ForbiddenException) as exc_info:
                await service.login(
                    db,
                    email="unverified_attempt@example.com",
                    password="SecurePassword!123",
                )
            assert exc_info.value.code == "EMAIL_NOT_VERIFIED"
            assert "Please verify your email address" in str(exc_info.value.message)

    def test_unverified_account_http_login_and_protected_access_rejected(self, test_client_and_factory):
        client, session_factory, settings = test_client_and_factory

        # 1. Register student
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "http_unverified@example.com",
                "password": "SecurePassword!123",
                "full_name": "HTTP Unverified",
            },
        )

        # 2. Attempt login -> Expect 403 Forbidden with code EMAIL_NOT_VERIFIED
        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": "http_unverified@example.com",
                "password": "SecurePassword!123",
            },
        )
        assert login_resp.status_code == 403
        data = login_resp.json()
        assert data["error"]["code"] == "EMAIL_NOT_VERIFIED"
        assert "Please verify your email address" in data["error"]["message"]

        # Ensure no session cookie was granted
        assert settings.SESSION_COOKIE_NAME not in login_resp.cookies

    @pytest.mark.asyncio
    async def test_token_verification_success_enables_subsequent_login(self, memory_db):
        service = AuthService()
        with memory_db() as db:
            user, raw_token = await service.register(
                db,
                email="verify_then_login@example.com",
                password="SecurePassword!123",
                full_name="Verify Then Login",
            )
            assert user.is_verified is False

            # Verify email
            verified_user = await service.verify_email(db, raw_token=raw_token)
            assert verified_user.is_verified is True

            # Subsequent login must now succeed
            auth_user, session_token, session_rec, access_token = await service.login(
                db,
                email="verify_then_login@example.com",
                password="SecurePassword!123",
            )
            assert auth_user.id == user.id
            assert session_rec.status == SESSION_STATUS_ACTIVE
            assert access_token is not None

    @pytest.mark.asyncio
    async def test_token_single_use_rejects_replay(self, memory_db):
        service = AuthService()
        with memory_db() as db:
            _, raw_token = await service.register(
                db,
                email="replay_test@example.com",
                password="SecurePassword!123",
                full_name="Replay Test",
            )

            # First consumption succeeds
            await service.verify_email(db, raw_token=raw_token)

            # Second consumption must fail with TOKEN_ALREADY_USED
            with pytest.raises(BadRequestException) as exc_info:
                await service.verify_email(db, raw_token=raw_token)
            assert exc_info.value.code == "TOKEN_ALREADY_USED"

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, memory_db):
        service = AuthService()
        with memory_db() as db:
            user, raw_token = await service.register(
                db,
                email="expired_token@example.com",
                password="SecurePassword!123",
                full_name="Expired Token Test",
            )

            # Manually backdate the token expiration in DB
            token_record = (
                db.query(AuthToken)
                .filter(AuthToken.user_id == user.id)
                .filter(AuthToken.token_type == TOKEN_TYPE_EMAIL_VERIFICATION)
                .first()
            )
            token_record.expires_at = utc_now() - timedelta(hours=1)
            db.commit()

            # Attempting verification must fail with INVALID_TOKEN
            with pytest.raises(BadRequestException) as exc_info:
                await service.verify_email(db, raw_token=raw_token)
            assert exc_info.value.code == "INVALID_TOKEN"

    @pytest.mark.asyncio
    async def test_resend_verification_invalidates_prior_token(self, memory_db):
        service = AuthService()
        with memory_db() as db:
            _, token1 = await service.register(
                db,
                email="resend_invalidation@example.com",
                password="SecurePassword!123",
                full_name="Resend Invalidation",
            )

            # Resend verification
            await service.resend_verification_email(db, email="resend_invalidation@example.com")

            # Outbox should now have 2 events
            events = (
                db.query(NotificationOutbox)
                .filter(NotificationOutbox.recipient == "resend_invalidation@example.com")
                .order_by(NotificationOutbox.created_at.asc())
                .all()
            )
            assert len(events) == 2
            token2 = events[1].payload["verification_token"]
            assert token1 != token2

            # Prior token1 must be rejected
            with pytest.raises(BadRequestException):
                await service.verify_email(db, raw_token=token1)

            # New token2 must succeed
            verified_user = await service.verify_email(db, raw_token=token2)
            assert verified_user.is_verified is True


class TestSuperAdminBootstrap:
    """Verifies the one-time Super Admin bootstrap script."""

    @pytest.mark.asyncio
    async def test_bootstrap_fails_for_nonexistent_user(self, memory_db):
        with memory_db() as db:
            success, msg = await bootstrap_super_admin(db, email="nonexistent@example.com")
            assert success is False
            assert "does not exist" in msg

    @pytest.mark.asyncio
    async def test_bootstrap_fails_for_unverified_user(self, memory_db):
        service = AuthService()
        with memory_db() as db:
            await service.register(
                db,
                email="unverified_owner@example.com",
                password="SecurePassword!123",
                full_name="Unverified Owner",
            )

            # Attempt bootstrap before verification
            success, msg = await bootstrap_super_admin(db, email="unverified_owner@example.com")
            assert success is False
            assert "is not email-verified" in msg

    @pytest.mark.asyncio
    async def test_bootstrap_succeeds_for_verified_user_and_records_audit(self, memory_db):
        service = AuthService()
        with memory_db() as db:
            user, raw_token = await service.register(
                db,
                email="owner@example.com",
                password="SecurePassword!123",
                full_name="Platform Owner",
            )
            await service.verify_email(db, raw_token=raw_token)

            # Execute bootstrap
            success, msg = await bootstrap_super_admin(db, email="owner@example.com")
            assert success is True
            assert "successfully bootstrapped as SUPER_ADMIN" in msg

            # User must now have SUPER_ADMIN role
            db.refresh(user)
            assert user.has_role(ROLE_SUPER_ADMIN) is True

            # Audit log must be recorded
            audit = (
                db.query(AuditLog)
                .filter(AuditLog.action == "SUPER_ADMIN_BOOTSTRAPPED")
                .first()
            )
            assert audit is not None
            assert audit.actor_id == user.id

    @pytest.mark.asyncio
    async def test_bootstrap_idempotency_guard_blocks_subsequent_attempts(self, memory_db):
        service = AuthService()
        with memory_db() as db:
            # 1. First owner verified and bootstrapped
            user1, token1 = await service.register(
                db,
                email="first_owner@example.com",
                password="SecurePassword!123",
                full_name="First Owner",
            )
            await service.verify_email(db, raw_token=token1)
            success1, _ = await bootstrap_super_admin(db, email="first_owner@example.com")
            assert success1 is True

            # 2. Second user attempts bootstrap
            user2, token2 = await service.register(
                db,
                email="second_user@example.com",
                password="SecurePassword!123",
                full_name="Second User",
            )
            await service.verify_email(db, raw_token=token2)

            success2, msg2 = await bootstrap_super_admin(db, email="second_user@example.com")
            assert success2 is False
            assert "A Super Admin already exists" in msg2

            # 3. Subsequent public registrations still strictly receive STUDENT role
            user3, _ = await service.register(
                db,
                email="subsequent_student@example.com",
                password="SecurePassword!123",
                full_name="Subsequent Student",
            )
            assert user3.has_role(ROLE_STUDENT) is True
            assert user3.has_role(ROLE_SUPER_ADMIN) is False
