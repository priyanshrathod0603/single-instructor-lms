"""Centralized API dependencies and RBAC evaluators.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 1)
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/08-SESSION-MANAGEMENT.md
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md (Sections 1, 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK202)

Strict Invariants:
1. Deny-Overrides-Allow: Inactive accounts encounter HTTP 403 ACCOUNT_SUSPENDED before permission checks.
2. Super Admin Bypass: Users with SUPER_ADMIN role bypass individual permission key requirements.
3. Multi-Role Union: Permissions are aggregated across all assigned roles.
4. Single-Active-Session: Invalidation on concurrent login returns HTTP 401 SESSION_REVOKED.
5. Fail Closed: Any missing required permission key results in HTTP 403 PERMISSION_DENIED.
"""

from collections.abc import Callable
import logging
from typing import Any, Optional
import uuid

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.exceptions import (
    ForbiddenException,
    SessionRevokedException,
    UnauthorizedException,
)
from app.core.permissions import COURSE_VIEW_ALL
from app.core.security import decode_access_token
from app.models.auth_session import (
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_REVOKED,
    AuthSession,
)
from app.models.base import utc_now
from app.models.enrollment import ENROLLMENT_STATUS_REVOKED
from app.models.user import ROLE_ADMIN, ROLE_STAFF, ROLE_SUPER_ADMIN, User
from app.repositories.enrollment_repo import EnrollmentRepository
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


def get_auth_service(settings: Settings = Depends(get_settings)) -> AuthService:
    """Dependency providing configured AuthService instance."""
    return AuthService(settings=settings)


async def get_current_user_and_session(
    request: Request,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> tuple[User, Optional[AuthSession]]:
    """Extract and validate current authenticated user and session.

    Enforces Single-Active-Session invariant [Blueprint v2.0 Page 8]:
    If session was superseded by a newer login, raises SessionRevokedException (HTTP 401 SESSION_REVOKED).
    """
    # 1. Try session cookie first
    raw_session_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if raw_session_token:
        user, auth_session = await auth_service.validate_session(
            db,
            raw_session_token=raw_session_token,
        )
        return user, auth_session

    # 2. Try Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token_str = auth_header[7:].strip()
        payload = decode_access_token(token_str)
        user_id_str = payload.get("sub")
        session_id_str = payload.get("session_id")

        if not user_id_str:
            raise UnauthorizedException(
                message="Invalid access token claims.",
                code="INVALID_TOKEN",
            )

        # Enforce session validation for access tokens (BUG-014)
        if not session_id_str:
            raise UnauthorizedException(
                message="Access token is missing required session identifier.",
                code="SESSION_REQUIRED",
            )

        try:
            session_uuid = uuid.UUID(session_id_str)
        except (ValueError, TypeError):
            raise UnauthorizedException(
                message="Invalid session identifier format.",
                code="INVALID_SESSION",
            )

        session_stmt = (
            db.query(AuthSession)
            .filter(AuthSession.id == session_uuid)
            .first()
        )
        if session_stmt is None:
            raise UnauthorizedException(
                message="Session not found or expired.",
                code="SESSION_NOT_FOUND",
            )

        if str(session_stmt.user_id) != user_id_str:
            raise UnauthorizedException(
                message="Session does not belong to token subject.",
                code="SESSION_USER_MISMATCH",
            )

        if session_stmt.status == SESSION_STATUS_REVOKED:
            raise SessionRevokedException()
        if session_stmt.status != SESSION_STATUS_ACTIVE or session_stmt.expires_at <= utc_now():
            raise UnauthorizedException(
                message="Your session has expired.",
                code="SESSION_EXPIRED",
            )

        user = await auth_service.user_repo.get_by_id(db, user_id_str)
        if user is None:
            raise UnauthorizedException(
                message="User account no longer exists.",
                code="USER_NOT_FOUND",
            )
        if not user.is_active:
            raise ForbiddenException(
                message="User account has been suspended.",
                code="ACCOUNT_SUSPENDED",
            )
        if not user.is_verified:
            raise ForbiddenException(
                message="Email verification is required.",
                code="EMAIL_NOT_VERIFIED",
            )

        return user, session_stmt

    raise UnauthorizedException(
        message="Authentication required.",
        code="NOT_AUTHENTICATED",
    )


async def get_current_user(
    auth_tuple: tuple[User, Optional[AuthSession]] = Depends(get_current_user_and_session),
) -> User:
    """Dependency returning verified current User instance."""
    return auth_tuple[0]


async def get_optional_current_user(
    request: Request,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> Optional[User]:
    """Dependency returning verified current User or None if unauthenticated (P1-03).
    
    Preserves intentional public visitor preview behavior when no credentials
    are supplied, but fails safely on infrastructure errors, suspended accounts,
    or revoked sessions.
    """
    cfg = settings if isinstance(settings, Settings) else get_settings()
    svc = auth_service if isinstance(auth_service, AuthService) else get_auth_service(settings=cfg)
    has_cookie = bool(request.cookies.get(cfg.SESSION_COOKIE_NAME))
    auth_header = request.headers.get("Authorization")
    has_bearer = bool(auth_header and auth_header.startswith("Bearer "))

    if not has_cookie and not has_bearer:
        return None

    try:
        user, _ = await get_current_user_and_session(
            request,
            db=db,
            auth_service=svc,
            settings=cfg,
        )
        return user
    except UnauthorizedException as exc:
        if exc.code == "NOT_AUTHENTICATED":
            return None
        # Explicit invalid credentials, expired session, revoked session must not silently become anonymous
        raise
    except ForbiddenException:
        # Suspended accounts must fail closed
        raise


async def get_current_active_session(
    auth_tuple: tuple[User, Optional[AuthSession]] = Depends(get_current_user_and_session),
) -> Optional[AuthSession]:
    """Dependency returning verified active AuthSession instance if cookie/session authenticated."""
    return auth_tuple[1]


def require_permissions(*required_keys: str) -> Callable[..., Any]:
    """FastAPI route dependency enforcing granular permission keys with deny-overrides-allow.

    Evaluation Pipeline:
    1. Check user.is_active == TRUE (else HTTP 403 ACCOUNT_SUSPENDED).
    2. Check if user possesses SUPER_ADMIN role (bypasses individual keys).
    3. Aggregate permissions across all assigned roles.
    4. Verify every required key is granted (else HTTP 403 PERMISSION_DENIED).
    """
    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.is_active:
            raise ForbiddenException(
                message="User account has been suspended.",
                code="ACCOUNT_SUSPENDED",
            )

        # Super Admin bypasses individual permission checks
        if ROLE_SUPER_ADMIN in current_user.roles:
            return current_user

        user_permissions = current_user.get_aggregated_permissions()
        missing = [key for key in required_keys if key not in user_permissions]
        if missing:
            raise ForbiddenException(
                message=f"Missing required permission: {', '.join(missing)}",
                code="PERMISSION_DENIED",
                details={
                    "missing_permissions": missing,
                    "required_permissions": list(required_keys),
                },
            )
        return current_user

    return permission_checker


def require_role(*allowed_roles: str) -> Callable[..., Any]:
    """FastAPI route dependency enforcing assigned role membership with Super Admin bypass."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.is_active:
            raise ForbiddenException(
                message="User account has been suspended.",
                code="ACCOUNT_SUSPENDED",
            )

        # Super Admin bypasses role restrictions
        if ROLE_SUPER_ADMIN in current_user.roles:
            return current_user

        if not any(r in current_user.roles for r in allowed_roles):
            raise ForbiddenException(
                message=f"Requires one of roles: {', '.join(allowed_roles)}",
                code="ROLE_NOT_AUTHORIZED",
                details={
                    "allowed_roles": list(allowed_roles),
                    "user_roles": current_user.roles,
                },
            )
        return current_user

    return role_checker


async def require_verified_student(current_user: User = Depends(get_current_user)) -> User:
    """Verify that learner is active and email verified before accessing course content."""
    if not current_user.is_active:
        raise ForbiddenException(
            message="User account has been suspended.",
            code="ACCOUNT_SUSPENDED",
        )

    # Elevated roles bypass email verification requirement for viewing
    if any(r in current_user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF)):
        return current_user

    if not current_user.is_verified:
        raise ForbiddenException(
            message="Email verification is required to access course content.",
            code="EMAIL_NOT_VERIFIED",
        )
    return current_user


def check_course_access(
    course_id: uuid.UUID,
    user: User,
    db: Session,
) -> bool:
    """Verify that a user is authorized to access course content.

    Rules:
    1. Inactive user -> HTTP 403 ACCOUNT_SUSPENDED
    2. Elevated role (SUPER_ADMIN, ADMIN, STAFF) -> True
    3. User has course:view_all permission -> True
    4. Student possesses active, unexpired enrollment -> True
    5. If enrollment is REVOKED -> HTTP 403 ENROLLMENT_REVOKED
    6. If enrollment is EXPIRED or past expires_at -> HTTP 403 ENROLLMENT_EXPIRED
    7. If no enrollment found -> HTTP 403 ENROLLMENT_REQUIRED
    """
    if not user.is_active:
        raise ForbiddenException(
            message="User account has been suspended.",
            code="ACCOUNT_SUSPENDED",
        )

    # Elevated roles and course managers bypass enrollment checks
    if any(r in user.roles for r in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_STAFF)):
        return True
    if user.has_permission(COURSE_VIEW_ALL):
        return True

    enrollment_repo = EnrollmentRepository()
    enrollment = enrollment_repo.get_by_student_and_course(db, user.id, course_id)
    if not enrollment:
        raise ForbiddenException(
            message="Enrollment required to access this course content.",
            code="ENROLLMENT_REQUIRED",
        )

    if enrollment.status == ENROLLMENT_STATUS_REVOKED:
        raise ForbiddenException(
            message="Your enrollment in this course has been revoked.",
            code="ENROLLMENT_REVOKED",
        )

    if not enrollment.is_access_valid:
        raise ForbiddenException(
            message="Your enrollment in this course has expired.",
            code="ENROLLMENT_EXPIRED",
        )

    return True


def require_course_enrollment(course_id_param: str = "course_id") -> Callable[..., Any]:
    """FastAPI route dependency ensuring active course enrollment for non-preview content."""

    async def enrollment_guard(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> User:
        param_val = request.path_params.get(course_id_param) or request.query_params.get(course_id_param)
        if not param_val:
            raise ForbiddenException(
                message=f"Missing {course_id_param} parameter for enrollment verification.",
                code="COURSE_ID_REQUIRED",
            )
        try:
            course_uuid = uuid.UUID(str(param_val))
        except (ValueError, TypeError):
            raise ForbiddenException(
                message=f"Invalid {course_id_param} UUID.",
                code="INVALID_COURSE_ID",
            )

        check_course_access(course_uuid, current_user, db)
        return current_user

    return enrollment_guard

