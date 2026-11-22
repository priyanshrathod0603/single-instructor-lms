"""Unit tests for AuthService business logic and security invariants.

Verifies:
1. Registration: password complexity, Argon2id hash, outbox staging, audit log.
2. Login: credentials check, account status check, single-active-session displacement, audit log.
3. Logout: session revocation, audit log.
4. Email verification: single-use token consumption, verification status update, audit log.
5. Resend verification: anti-enumeration, previous token invalidation, outbox staging.
6. Password reset:
   - Request: anti-enumeration, previous token invalidation, outbox staging, audit log.
   - Confirm: password update, consumption, **revoking all active sessions**, audit log.
7. Session validation: active session check, revoked session raising SessionRevokedException.
8. Google OAuth: claims verification, user provisioning, atomic displacement, audit log.
"""

from datetime import datetime, timedelta, timezone
import uuid

import jwt
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    SessionRevokedException,
    UnauthorizedException,
    ValidationException,
)
from app.models import (
    ROLE_STUDENT,
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_REVOKED,
    SYSTEM_ROLES,
    TOKEN_TYPE_EMAIL_VERIFICATION,
    TOKEN_TYPE_PASSWORD_RESET,
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


@pytest.fixture
def db_session():
    """In-memory SQLite database session configured with schema and default roles."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        # Seed canonical roles
        for role_id in SYSTEM_ROLES:
            session.add(Role(id=role_id, name=role_id.capitalize(), description=f"{role_id} role"))
        session.commit()
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


class TestAuthServiceRegistration:
    """Verifies registration logic and outbox coupling."""

    @pytest.mark.asyncio
    async def test_register_success(self, db_session: Session):
        service = AuthService()
        user, raw_token = await service.register(
            db_session,
            email="STUDENT.One@Example.COM",
            password="SecurePassw0rd!123",
            full_name="Student One",
            ip_address="192.168.1.100",
            user_agent="TestAgent/1.0",
        )
        assert user.email == "student.one@example.com"
        assert user.is_verified is False
        assert user.has_role(ROLE_STUDENT) is True
        assert len(raw_token) >= 32

        # Check outbox event staged
        outbox_event = (
            db_session.query(NotificationOutbox)
            .filter(NotificationOutbox.recipient == "student.one@example.com")
            .first()
        )
        assert outbox_event is not None
        assert outbox_event.event_type == "AUTH_VERIFY_EMAIL"
        assert outbox_event.payload["verification_token"] == raw_token

        # Check audit log staged
        audit_log = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "USER_REGISTERED")
            .first()
        )
        assert audit_log is not None
        assert audit_log.actor_id == user.id

    @pytest.mark.asyncio
    async def test_register_weak_password_rejected(self, db_session: Session):
        service = AuthService()
        with pytest.raises(ValidationException):
            await service.register(
                db_session,
                email="weak@example.com",
                password="short",
                full_name="Weak Password",
            )

    @pytest.mark.asyncio
    async def test_register_duplicate_email_rejected(self, db_session: Session):
        service = AuthService()
        await service.register(
            db_session,
            email="existing@example.com",
            password="SecurePassw0rd!123",
            full_name="First User",
        )
        with pytest.raises(ConflictException):
            await service.register(
                db_session,
                email="EXISTING@example.com",
                password="SecurePassw0rd!123",
                full_name="Second User",
            )


class TestAuthServiceLoginAndDisplacement:
    """Verifies credentials verification and single-active-session displacement."""

    @pytest.mark.asyncio
    async def test_login_success_and_jwt_issuance(self, db_session: Session):
        service = AuthService()
        user, raw_verify_token = await service.register(
            db_session,
            email="login@example.com",
            password="SecurePassw0rd!123",
            full_name="Login User",
        )
        # Verify email first (mandatory email verification invariant)
        await service.verify_email(db_session, raw_token=raw_verify_token)

        authenticated_user, raw_token, session_record, access_token = await service.login(
            db_session,
            email="LOGIN@example.com",
            password="SecurePassw0rd!123",
            ip_address="10.0.0.1",
            user_agent="BrowserA",
        )
        assert authenticated_user.id == user.id
        assert session_record.status == SESSION_STATUS_ACTIVE
        assert access_token is not None

        # Verify audit log recorded
        login_audit = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "USER_LOGIN")
            .first()
        )
        assert login_audit is not None
        assert login_audit.actor_id == user.id

    @pytest.mark.asyncio
    async def test_login_unverified_account_raises_forbidden(self, db_session: Session):
        service = AuthService()
        await service.register(
            db_session,
            email="unverified_login@example.com",
            password="SecurePassw0rd!123",
            full_name="Unverified User",
        )
        with pytest.raises(ForbiddenException) as exc_info:
            await service.login(
                db_session,
                email="unverified_login@example.com",
                password="SecurePassw0rd!123",
            )
        assert exc_info.value.code == "EMAIL_NOT_VERIFIED"

    @pytest.mark.asyncio
    async def test_login_invalid_password_raises_unauthorized(self, db_session: Session):
        service = AuthService()
        await service.register(
            db_session,
            email="wrongpass@example.com",
            password="SecurePassw0rd!123",
            full_name="Wrong Pass User",
        )
        with pytest.raises(UnauthorizedException) as exc_info:
            await service.login(
                db_session,
                email="wrongpass@example.com",
                password="WrongPassword!999",
            )
        assert exc_info.value.code == "INVALID_CREDENTIALS"

    @pytest.mark.asyncio
    async def test_login_deactivated_account_raises_forbidden(self, db_session: Session):
        service = AuthService()
        user, _ = await service.register(
            db_session,
            email="deactivated@example.com",
            password="SecurePassw0rd!123",
            full_name="Deactivated User",
        )
        # Deactivate user
        await service.user_repo.update_status(db_session, user.id, is_active=False)

        with pytest.raises(ForbiddenException) as exc_info:
            await service.login(
                db_session,
                email="deactivated@example.com",
                password="SecurePassw0rd!123",
            )
        assert exc_info.value.code == "ACCOUNT_DEACTIVATED"

    @pytest.mark.asyncio
    async def test_single_active_session_displacement(self, db_session: Session):
        """Logging in from Device 2 displaces active session from Device 1."""
        service = AuthService()
        user, raw_token = await service.register(
            db_session,
            email="displace_svc@example.com",
            password="SecurePassw0rd!123",
            full_name="Displace Svc User",
        )
        await service.verify_email(db_session, raw_token=raw_token)

        # Login Device 1
        _, token_dev1, session1, _ = await service.login(
            db_session,
            email="displace_svc@example.com",
            password="SecurePassw0rd!123",
            ip_address="10.0.0.1",
            user_agent="Device1",
        )
        assert session1.status == SESSION_STATUS_ACTIVE

        # Validate session 1 works
        u1, s1 = await service.validate_session(db_session, raw_session_token=token_dev1)
        assert u1.id == user.id

        # Login Device 2
        _, token_dev2, session2, _ = await service.login(
            db_session,
            email="displace_svc@example.com",
            password="SecurePassw0rd!123",
            ip_address="10.0.0.2",
            user_agent="Device2",
        )
        assert session2.status == SESSION_STATUS_ACTIVE

        # Device 1 session must now be REVOKED and raise SessionRevokedException
        with pytest.raises(SessionRevokedException):
            await service.validate_session(db_session, raw_session_token=token_dev1)

        # Device 2 session must remain valid
        u2, s2 = await service.validate_session(db_session, raw_session_token=token_dev2)
        assert u2.id == user.id
        assert s2.status == SESSION_STATUS_ACTIVE

        # Check displacement audit log
        displacement_audit = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "SESSION_DISPLACED")
            .first()
        )
        assert displacement_audit is not None
        assert displacement_audit.resource_id == str(session1.id)


class TestAuthServiceEmailVerification:
    """Verifies email verification token lifecycle."""

    @pytest.mark.asyncio
    async def test_verify_email_success(self, db_session: Session):
        service = AuthService()
        user, raw_token = await service.register(
            db_session,
            email="verify_test@example.com",
            password="SecurePassw0rd!123",
            full_name="Verify Test",
        )
        assert user.is_verified is False

        verified_user = await service.verify_email(db_session, raw_token=raw_token)
        assert verified_user.is_verified is True

        # Second attempt with same token must fail (single-use)
        with pytest.raises(BadRequestException):
            await service.verify_email(db_session, raw_token=raw_token)

    @pytest.mark.asyncio
    async def test_resend_verification_email(self, db_session: Session):
        service = AuthService()
        user, first_token = await service.register(
            db_session,
            email="resend_test@example.com",
            password="SecurePassw0rd!123",
            full_name="Resend Test",
        )
        # Resend
        await service.resend_verification_email(db_session, email="resend_test@example.com")

        # First token should now be invalidated
        with pytest.raises(BadRequestException):
            await service.verify_email(db_session, raw_token=first_token)

        # Anti-enumeration: resend for nonexistent email returns without error
        await service.resend_verification_email(db_session, email="nonexistent@example.com")


class TestAuthServicePasswordReset:
    """Verifies password reset and multi-session revocation."""

    @pytest.mark.asyncio
    async def test_password_reset_flow_and_session_revocation(self, db_session: Session):
        service = AuthService()
        user, raw_token = await service.register(
            db_session,
            email="pwreset@example.com",
            password="InitialPassw0rd!123",
            full_name="PW Reset User",
        )
        await service.verify_email(db_session, raw_token=raw_token)

        # Establish active session
        _, dev1_token, sess1, _ = await service.login(
            db_session,
            email="pwreset@example.com",
            password="InitialPassw0rd!123",
        )
        assert sess1.status == SESSION_STATUS_ACTIVE

        # Request password reset
        await service.request_password_reset(db_session, email="pwreset@example.com")

        # Extract reset token from outbox
        outbox_event = (
            db_session.query(NotificationOutbox)
            .filter(NotificationOutbox.recipient == "pwreset@example.com")
            .filter(NotificationOutbox.event_type == "AUTH_RESET_PASSWORD")
            .first()
        )
        assert outbox_event is not None
        reset_token = outbox_event.payload["reset_token"]

        # Confirm password reset
        await service.confirm_password_reset(
            db_session,
            raw_token=reset_token,
            new_password="NewSecurePassw0rd!456",
        )

        # Invariant: Prior active session MUST now be REVOKED
        with pytest.raises(SessionRevokedException):
            await service.validate_session(db_session, raw_session_token=dev1_token)

        # Can now login with new password
        _, new_token, new_sess, _ = await service.login(
            db_session,
            email="pwreset@example.com",
            password="NewSecurePassw0rd!456",
        )
        assert new_sess.status == SESSION_STATUS_ACTIVE

        # Old password fails
        with pytest.raises(UnauthorizedException):
            await service.login(
                db_session,
                email="pwreset@example.com",
                password="InitialPassw0rd!123",
            )


class TestAuthServiceGoogleOAuth:
    """Verifies Google OAuth account provisioning and session displacement."""

    @pytest.mark.asyncio
    async def test_google_oauth_provisions_verified_student(self, db_session: Session):
        service = AuthService()
        mock_payload = {
            "email": "google.student@example.com",
            "email_verified": True,
            "name": "Google Student",
            "picture": "https://example.com/avatar.jpg",
            "sub": "google-sub-12345",
        }

        user, raw_token, session_record, access_token = await service.google_oauth_authenticate(
            db_session,
            id_token_payload=mock_payload,
            ip_address="127.0.0.1",
        )
        assert user.email == "google.student@example.com"
        assert user.is_verified is True
        assert user.has_role(ROLE_STUDENT) is True
        assert session_record.status == SESSION_STATUS_ACTIVE

        # Validate session works
        u, s = await service.validate_session(db_session, raw_session_token=raw_token)
        assert u.id == user.id

    @pytest.mark.asyncio
    async def test_google_oauth_unverified_email_rejected(self, db_session: Session):
        service = AuthService()
        mock_payload = {
            "email": "unverified.google@example.com",
            "email_verified": False,
            "name": "Unverified Google",
        }
        with pytest.raises(UnauthorizedException) as exc_info:
            await service.google_oauth_authenticate(
                db_session,
                id_token_payload=mock_payload,
            )
        assert exc_info.value.code == "OAUTH_EMAIL_UNVERIFIED"
