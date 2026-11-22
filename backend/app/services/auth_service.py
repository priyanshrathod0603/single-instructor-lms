"""AuthService orchestrating authentication, identity, and session lifecycles.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/08-SESSION-MANAGEMENT.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK104, TASK105, TASK106)

Strict Invariants:
1. Single-Active-Session: Logging in atomically revokes prior active sessions across all devices.
2. Anti-Enumeration: Password reset and resend verification endpoints return uniform responses.
3. Password Reset Invalidation: Confirming password reset revokes ALL active sessions for that user.
4. Outbox Coupling: Verification and password reset tokens stage outbox events within the same transaction.
5. Audit Persistence: All authentication events record immutable audit logs within transaction.
"""

from datetime import datetime, timedelta
import logging
from typing import Any, Optional, Tuple, Union
import uuid

import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    SessionRevokedException,
    UnauthorizedException,
    ValidationException,
)
from app.core.security import (
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    needs_rehash,
    validate_password_complexity,
    verify_password,
)
from app.core.audit_suppression import (
    derive_email_hmac,
    derive_ip_hmac,
    evaluate_login_failure_suppression,
)
from app.models.auth_session import (
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_REVOKED,
    AuthSession,
)
from app.models.auth_token import (
    TOKEN_TYPE_EMAIL_VERIFICATION,
    TOKEN_TYPE_PASSWORD_RESET,
    AuthToken,
)
from app.models.base import utc_now
from app.models.notification import OUTBOX_CHANNEL_EMAIL
from app.models.user import ROLE_STUDENT, User
from app.repositories.session_repo import SessionRepository
from app.repositories.token_repo import AuthTokenRepository
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService
from app.services.outbox_service import OutboxService

logger = logging.getLogger(__name__)


class AuthService:
    """Domain service managing identity, credentials, sessions, and authentication security."""

    def __init__(
        self,
        *,
        user_repo: Optional[UserRepository] = None,
        session_repo: Optional[SessionRepository] = None,
        token_repo: Optional[AuthTokenRepository] = None,
        audit_service: Optional[AuditService] = None,
        outbox_service: Optional[OutboxService] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.user_repo = user_repo or UserRepository()
        self.session_repo = session_repo or SessionRepository()
        self.token_repo = token_repo or AuthTokenRepository()
        self.audit_service = audit_service or AuditService()
        self.outbox_service = outbox_service or OutboxService()
        self.settings = settings or get_settings()

    async def register(
        self,
        session: Union[AsyncSession, Session],
        *,
        email: str,
        password: str,
        full_name: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[User, str]:
        """Register a new student account, generate verification token, and stage email dispatch.

        Args:
            session: Active database session.
            email: Raw email address.
            password: Raw plaintext password.
            full_name: Student display name.
            ip_address: Client IP address.
            user_agent: Client User-Agent header.

        Returns:
            Tuple of (created_user, raw_verification_token).
        """
        # 1. Enforce password complexity
        validate_password_complexity(password)

        # 2. Hash password with approved Argon2id parameters
        pwd_hash = hash_password(password)

        # 3. Create User and assign default ROLE_STUDENT
        user = await self.user_repo.create_user(
            session,
            email=email,
            full_name=full_name,
            password_hash=pwd_hash,
            is_verified=False,
            role_id=ROLE_STUDENT,
        )

        # 4. Generate 32-byte cryptographic email verification token
        raw_token = generate_secure_token(32)
        token_hash = hash_token(raw_token)
        exp_minutes = self.settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES
        token_exp = utc_now() + timedelta(minutes=exp_minutes)

        await self.token_repo.create_token(
            session,
            user_id=user.id,
            token_hash=token_hash,
            token_type=TOKEN_TYPE_EMAIL_VERIFICATION,
            expires_at=token_exp,
        )

        # 5. Stage transactional outbox notification
        frontend_url = self.settings.FRONTEND_URL.rstrip("/")
        verify_url = f"{frontend_url}/verify-email?token={raw_token}"
        await self.outbox_service.publish_event(
            session,
            event_type="AUTH_VERIFY_EMAIL",
            channel=OUTBOX_CHANNEL_EMAIL,
            recipient=user.email,
            subject="Verify your email address",
            payload={
                "user_id": str(user.id),
                "full_name": user.full_name,
                "verification_token": raw_token,
                "verification_url": verify_url,
            },
            dedupe_key=f"verify_{user.id}_{token_hash[:16]}",
        )

        # 6. Record immutable audit log
        await self.audit_service.record_event(
            session,
            action="USER_REGISTERED",
            resource_type="user",
            resource_id=user.id,
            actor_id=user.id,
            actor_type="USER",
            after_state=user,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return user, raw_token

    async def _handle_failed_login(
        self,
        session: Union[AsyncSession, Session],
        normalized_email: str,
        ip_address: Optional[str],
        user_agent: Optional[str],
        user: Optional[User] = None,
    ) -> None:
        """Record privacy-safe AUTH_LOGIN_FAILED audit event under Redis suppression policy."""
        try:
            is_suppressed, prior_count, email_hmac, ip_hmac = evaluate_login_failure_suppression(
                normalized_email,
                ip_address,
                settings=self.settings,
            )
            if not is_suppressed:
                metadata = {
                    "email_hmac": email_hmac,
                    "ip_hmac": ip_hmac,
                }
                if prior_count > 0:
                    metadata["suppressed_failures_in_window"] = prior_count

                await self.audit_service.record_event(
                    session,
                    action="AUTH_LOGIN_FAILED",
                    resource_type="auth",
                    resource_id=None,
                    actor_id=user.id if user else None,
                    actor_type="USER" if user else "VISITOR",
                    metadata=metadata,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                if hasattr(session, "commit"):
                    session.commit()
                elif hasattr(session, "flush"):
                    if isinstance(session, AsyncSession):
                        await session.flush()
                    else:
                        session.flush()
        except Exception as exc:
            logger.warning("Failed to record failed login audit event: %s", exc)

    async def record_rate_limit_breach(
        self,
        session: Union[AsyncSession, Session],
        *,
        action: str,
        email: str,
        client_ip: Optional[str],
        user_agent: Optional[str],
        retry_after: int,
    ) -> None:
        """Record AUTH_RATE_LIMIT_EXCEEDED audit event upon rate limiter exhaustion."""
        try:
            email_hmac = derive_email_hmac(email, self.settings)
            ip_hmac = derive_ip_hmac(client_ip, self.settings)
            await self.audit_service.record_event(
                session,
                action="AUTH_RATE_LIMIT_EXCEEDED",
                resource_type="auth",
                resource_id=None,
                actor_id=None,
                actor_type="VISITOR",
                metadata={
                    "rate_limited_action": action,
                    "email_hmac": email_hmac,
                    "ip_hmac": ip_hmac,
                    "retry_after_seconds": retry_after,
                },
                ip_address=client_ip,
                user_agent=user_agent,
            )
            if hasattr(session, "commit"):
                session.commit()
            elif hasattr(session, "flush"):
                if isinstance(session, AsyncSession):
                    await session.flush()
                else:
                    session.flush()
        except Exception as exc:
            logger.warning("Failed to record rate limit breach audit event: %s", exc)

    async def login(
        self,
        session: Union[AsyncSession, Session],
        *,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[User, str, AuthSession, str]:
        """Authenticate user credentials and enforce Single-Active-Session displacement.

        Args:
            session: Active database session.
            email: Account email.
            password: Plaintext password.
            ip_address: Client IP address.
            user_agent: Client User-Agent.

        Returns:
            Tuple of (user, raw_session_token, auth_session, access_token).

        Raises:
            UnauthorizedException: On invalid credentials.
            ForbiddenException: If account is deactivated.
        """
        normalized_email = email.strip().lower()
        user = await self.user_repo.get_by_email(session, normalized_email)

        # Constant-time-safe failure on missing user or OAuth-only user
        if user is None or not user.password_hash:
            await self._handle_failed_login(session, normalized_email, ip_address, user_agent, user=None)
            raise UnauthorizedException(
                message="Invalid email or password.",
                code="INVALID_CREDENTIALS",
            )

        if not verify_password(password, user.password_hash):
            await self._handle_failed_login(session, normalized_email, ip_address, user_agent, user=user)
            raise UnauthorizedException(
                message="Invalid email or password.",
                code="INVALID_CREDENTIALS",
            )

        if not user.is_active:
            raise ForbiddenException(
                message="Your account has been deactivated. Please contact support.",
                code="ACCOUNT_DEACTIVATED",
            )

        if not user.is_verified:
            raise ForbiddenException(
                message="Please verify your email address before logging in.",
                code="EMAIL_NOT_VERIFIED",
            )

        # Transparent password rehashing if parameters upgraded
        if needs_rehash(user.password_hash):
            new_hash = hash_password(password)
            await self.user_repo.update_password_hash(session, user.id, new_hash)

        # Generate 32-byte session token
        raw_session_token = generate_secure_token(32)
        session_token_hash = hash_token(raw_session_token)
        session_exp = utc_now() + timedelta(seconds=self.settings.SESSION_MAX_AGE_SECONDS)

        # Single-Active-Session invariant atomic displacement
        new_session, displaced = await self.session_repo.atomic_displace_session(
            session,
            user_id=user.id,
            new_session_token_hash=session_token_hash,
            expires_at=session_exp,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # If an active session was superseded, record displacement audit
        if displaced is not None:
            await self.audit_service.record_event(
                session,
                action="SESSION_DISPLACED",
                resource_type="auth_session",
                resource_id=displaced.id,
                actor_id=user.id,
                actor_type="USER",
                metadata={"displaced_by_session_id": str(new_session.id)},
                ip_address=ip_address,
                user_agent=user_agent,
            )

        # Record login audit log
        await self.audit_service.record_event(
            session,
            action="USER_LOGIN",
            resource_type="auth_session",
            resource_id=new_session.id,
            actor_id=user.id,
            actor_type="USER",
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Generate short-lived JWT access token (15 minutes)
        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"roles": user.roles, "session_id": str(new_session.id)},
            expires_delta=timedelta(minutes=15),
        )

        return user, raw_session_token, new_session, access_token

    async def logout(
        self,
        session: Union[AsyncSession, Session],
        *,
        raw_session_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Revoke active session and record logout audit trail."""
        if not raw_session_token or not raw_session_token.strip():
            return

        session_token_hash = hash_token(raw_session_token)
        auth_session = await self.session_repo.get_session_by_token_hash(session, session_token_hash)
        if auth_session is not None and auth_session.status == SESSION_STATUS_ACTIVE:
            await self.session_repo.revoke_session(
                session,
                auth_session.id,
                reason="USER_LOGOUT",
                revoked_by=auth_session.user_id,
            )
            await self.audit_service.record_event(
                session,
                action="USER_LOGOUT",
                resource_type="auth_session",
                resource_id=auth_session.id,
                actor_id=auth_session.user_id,
                actor_type="USER",
                ip_address=ip_address,
                user_agent=user_agent,
            )

    async def verify_email(
        self,
        session: Union[AsyncSession, Session],
        *,
        raw_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> User:
        """Verify user's email address via single-use token consumption."""
        if not raw_token or not raw_token.strip():
            raise BadRequestException(
                message="Invalid or missing verification token.",
                code="INVALID_TOKEN",
            )

        token_hash = hash_token(raw_token)
        auth_token = await self.token_repo.get_by_hash(
            session,
            token_hash=token_hash,
            token_type=TOKEN_TYPE_EMAIL_VERIFICATION,
        )
        if auth_token is None:
            raise BadRequestException(
                message="Invalid verification token.",
                code="INVALID_TOKEN",
            )
        if auth_token.is_used:
            raise BadRequestException(
                message="Verification token has already been consumed.",
                code="TOKEN_ALREADY_USED",
            )
        if auth_token.expires_at <= utc_now():
            raise BadRequestException(
                message="Verification token has expired.",
                code="INVALID_TOKEN",
            )

        # Atomically consume token
        consumed = await self.token_repo.consume_token(session, auth_token.id)
        if not consumed:
            raise BadRequestException(
                message="Verification token has already been consumed.",
                code="TOKEN_ALREADY_USED",
            )

        # Mark user as verified
        await self.user_repo.mark_email_verified(session, auth_token.user_id)
        user = await self.user_repo.get_by_id(session, auth_token.user_id)
        if user is None:
            raise BadRequestException(
                message="User associated with token not found.",
                code="USER_NOT_FOUND",
            )

        # Audit event
        await self.audit_service.record_event(
            session,
            action="EMAIL_VERIFIED",
            resource_type="user",
            resource_id=user.id,
            actor_id=user.id,
            actor_type="USER",
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return user

    async def resend_verification_email(
        self,
        session: Union[AsyncSession, Session],
        *,
        email: str,
    ) -> None:
        """Resend email verification token without leaking user existence."""
        normalized_email = email.strip().lower()
        user = await self.user_repo.get_by_email(session, normalized_email)

        # Anti-enumeration: Silent return if user does not exist or already verified
        if user is None or user.is_verified or not user.is_active:
            return

        # Invalidate any prior pending verification tokens
        await self.token_repo.invalidate_user_tokens(
            session,
            user_id=user.id,
            token_type=TOKEN_TYPE_EMAIL_VERIFICATION,
        )

        # Generate new token
        raw_token = generate_secure_token(32)
        token_hash = hash_token(raw_token)
        exp_minutes = self.settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES
        token_exp = utc_now() + timedelta(minutes=exp_minutes)

        await self.token_repo.create_token(
            session,
            user_id=user.id,
            token_hash=token_hash,
            token_type=TOKEN_TYPE_EMAIL_VERIFICATION,
            expires_at=token_exp,
        )

        # Stage outbox notification
        frontend_url = self.settings.FRONTEND_URL.rstrip("/")
        verify_url = f"{frontend_url}/verify-email?token={raw_token}"
        await self.outbox_service.publish_event(
            session,
            event_type="AUTH_VERIFY_EMAIL",
            channel=OUTBOX_CHANNEL_EMAIL,
            recipient=user.email,
            subject="Verify your email address",
            payload={
                "user_id": str(user.id),
                "full_name": user.full_name,
                "verification_token": raw_token,
                "verification_url": verify_url,
            },
            dedupe_key=f"verify_{user.id}_{token_hash[:16]}",
        )

    async def request_password_reset(
        self,
        session: Union[AsyncSession, Session],
        *,
        email: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Initiate password reset flow adhering to anti-enumeration invariants.

        Always succeeds from the caller's perspective regardless of user existence.
        """
        normalized_email = email.strip().lower()
        user = await self.user_repo.get_by_email(session, normalized_email)

        # Anti-enumeration guard
        if user is None or not user.is_active:
            logger.info("Password reset requested for nonexistent or inactive email: %s", normalized_email)
            return

        # Invalidate previous unused password reset tokens
        await self.token_repo.invalidate_user_tokens(
            session,
            user_id=user.id,
            token_type=TOKEN_TYPE_PASSWORD_RESET,
        )

        # Generate single-use token (1 hour TTL)
        raw_token = generate_secure_token(32)
        token_hash = hash_token(raw_token)
        exp_minutes = self.settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        token_exp = utc_now() + timedelta(minutes=exp_minutes)

        await self.token_repo.create_token(
            session,
            user_id=user.id,
            token_hash=token_hash,
            token_type=TOKEN_TYPE_PASSWORD_RESET,
            expires_at=token_exp,
        )

        # Stage transactional outbox email
        frontend_url = self.settings.FRONTEND_URL.rstrip("/")
        reset_url = f"{frontend_url}/reset-password?token={raw_token}"
        await self.outbox_service.publish_event(
            session,
            event_type="AUTH_RESET_PASSWORD",
            channel=OUTBOX_CHANNEL_EMAIL,
            recipient=user.email,
            subject="Reset your LMS password",
            payload={
                "user_id": str(user.id),
                "full_name": user.full_name,
                "reset_token": raw_token,
                "reset_url": reset_url,
            },
            dedupe_key=f"reset_{user.id}_{token_hash[:16]}",
        )

        # Record audit log
        await self.audit_service.record_event(
            session,
            action="PASSWORD_RESET_REQUESTED",
            resource_type="user",
            resource_id=user.id,
            actor_id=user.id,
            actor_type="USER",
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def confirm_password_reset(
        self,
        session: Union[AsyncSession, Session],
        *,
        raw_token: str,
        new_password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> User:
        """Confirm password reset, consume token, and atomically revoke ALL active sessions.

        Strict Security Invariant [07-AUTHENTICATION-ARCHITECTURE.md Section 5]:
        Atomically revokes ALL active sessions for that user across all devices.
        """
        if not raw_token or not raw_token.strip():
            raise BadRequestException(
                message="Invalid or missing reset token.",
                code="INVALID_RESET_TOKEN",
            )

        token_hash = hash_token(raw_token)
        auth_token = await self.token_repo.get_valid_token(
            session,
            token_hash=token_hash,
            token_type=TOKEN_TYPE_PASSWORD_RESET,
        )
        if auth_token is None:
            raise BadRequestException(
                message="Invalid or expired password reset token.",
                code="INVALID_RESET_TOKEN",
            )

        # Enforce password complexity
        validate_password_complexity(new_password)

        # Consume token
        consumed = await self.token_repo.consume_token(session, auth_token.id)
        if not consumed:
            raise BadRequestException(
                message="Password reset token has already been consumed.",
                code="RESET_TOKEN_ALREADY_USED",
            )

        # Update password hash
        new_hash = hash_password(new_password)
        await self.user_repo.update_password_hash(session, auth_token.user_id, new_hash)

        # Revoke ALL active sessions for this user across all devices with metadata
        revoked_count = await self.session_repo.revoke_all_user_sessions(
            session,
            auth_token.user_id,
            reason="PASSWORD_RESET_COMPLETED",
            revoked_by=auth_token.user_id,
        )
        logger.info("Password reset confirmed for user %s; %d active session(s) revoked.", auth_token.user_id, revoked_count)

        user = await self.user_repo.get_by_id(session, auth_token.user_id)
        if user is None:
            raise BadRequestException(
                message="User associated with reset token not found.",
                code="USER_NOT_FOUND",
            )

        # Record audit log
        await self.audit_service.record_event(
            session,
            action="PASSWORD_RESET_COMPLETED",
            resource_type="user",
            resource_id=user.id,
            actor_id=user.id,
            actor_type="USER",
            metadata={"revoked_active_sessions": revoked_count},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return user

    async def validate_session(
        self,
        session: Union[AsyncSession, Session],
        *,
        raw_session_token: str,
    ) -> Tuple[User, AuthSession]:
        """Validate session token, enforce single-active-session invariant, and throttle activity timestamp.

        Raises:
            UnauthorizedException: If token is missing, expired, or invalid.
            SessionRevokedException: If session was superseded by a newer login on another device.
            ForbiddenException: If account is deactivated.
        """
        if not raw_session_token or not raw_session_token.strip():
            raise UnauthorizedException(
                message="Authentication session cookie or token is missing.",
                code="NOT_AUTHENTICATED",
            )

        token_hash = hash_token(raw_session_token)
        auth_session = await self.session_repo.get_session_by_token_hash(session, token_hash)
        if auth_session is None:
            raise UnauthorizedException(
                message="Invalid or unrecognized authentication session.",
                code="INVALID_SESSION",
            )

        # Single-Active-Session supersession check
        if auth_session.status == SESSION_STATUS_REVOKED:
            raise SessionRevokedException()

        if auth_session.status != SESSION_STATUS_ACTIVE or auth_session.expires_at <= utc_now():
            raise UnauthorizedException(
                message="Your session has expired. Please log in again.",
                code="SESSION_EXPIRED",
            )

        user = auth_session.user
        if not user.is_active:
            raise ForbiddenException(
                message="Your account has been deactivated. Please contact support.",
                code="ACCOUNT_DEACTIVATED",
            )

        if not user.is_verified:
            raise ForbiddenException(
                message="Please verify your email address before logging in.",
                code="EMAIL_NOT_VERIFIED",
            )

        # Throttled activity timestamp update (at most once every 5 minutes)
        await self.session_repo.touch_last_active(session, auth_session, threshold_seconds=300)

        return user, auth_session

    async def google_oauth_authenticate(
        self,
        session: Union[AsyncSession, Session],
        *,
        id_token_payload: dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[User, str, AuthSession, str]:
        """Authenticate via Google OAuth / OIDC verified payload and enforce atomic displacement.

        Args:
            session: Active database session.
            id_token_payload: Pre-verified Google JWT claims dictionary.
            ip_address: Client IP.
            user_agent: Client User-Agent.

        Returns:
            Tuple of (user, raw_session_token, auth_session, access_token).
        """
        email = id_token_payload.get("email")
        if not email or not isinstance(email, str):
            raise UnauthorizedException(
                message="Google token does not contain a valid email address.",
                code="INVALID_OAUTH_TOKEN",
            )

        email_verified = id_token_payload.get("email_verified", False)
        if not email_verified:
            raise UnauthorizedException(
                message="Google account email is not verified.",
                code="OAUTH_EMAIL_UNVERIFIED",
            )

        full_name = id_token_payload.get("name") or email.split("@")[0]
        avatar_url = id_token_payload.get("picture")

        normalized_email = email.strip().lower()
        user = await self.user_repo.get_by_email(session, normalized_email)

        if user is None:
            # First-time OAuth user: create with verified=True and default STUDENT role
            user = await self.user_repo.create_user(
                session,
                email=normalized_email,
                full_name=full_name,
                password_hash=None,
                avatar_url=avatar_url,
                is_verified=True,
                role_id=ROLE_STUDENT,
            )
        else:
            # Existing user: ensure marked verified if Google verified it
            if not user.is_verified:
                await self.user_repo.mark_email_verified(session, user.id)
            if not user.is_active:
                raise ForbiddenException(
                    message="Your account has been deactivated. Please contact support.",
                    code="ACCOUNT_DEACTIVATED",
                )

        # Single-Active-Session displacement
        raw_session_token = generate_secure_token(32)
        session_token_hash = hash_token(raw_session_token)
        session_exp = utc_now() + timedelta(seconds=self.settings.SESSION_MAX_AGE_SECONDS)

        new_session, displaced = await self.session_repo.atomic_displace_session(
            session,
            user_id=user.id,
            new_session_token_hash=session_token_hash,
            expires_at=session_exp,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        if displaced is not None:
            await self.audit_service.record_event(
                session,
                action="SESSION_DISPLACED",
                resource_type="auth_session",
                resource_id=displaced.id,
                actor_id=user.id,
                actor_type="USER",
                metadata={"displaced_by_session_id": str(new_session.id)},
                ip_address=ip_address,
                user_agent=user_agent,
            )

        # Record login audit log
        await self.audit_service.record_event(
            session,
            action="USER_OAUTH_LOGIN",
            resource_type="auth_session",
            resource_id=new_session.id,
            actor_id=user.id,
            actor_type="USER",
            metadata={"provider": "google"},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Generate short-lived JWT access token
        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"roles": user.roles, "session_id": str(new_session.id)},
            expires_delta=timedelta(minutes=15),
        )

        return user, raw_session_token, new_session, access_token
