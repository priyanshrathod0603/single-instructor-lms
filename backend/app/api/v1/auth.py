"""Authentication and identity REST API endpoints.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 3)
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/08-SESSION-MANAGEMENT.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK104, TASK105, TASK106)

Strict Invariants:
1. Cookie Security: __Host-lms_session cookie with HttpOnly, Secure (in production), SameSite=Lax.
2. Single-Active-Session: Invalidation on concurrent login returns HTTP 401 SESSION_REVOKED.
3. Anti-Enumeration: Password reset request and resend verification return uniform responses.
4. Password Reset Invariant: Resetting password atomically revokes ALL active sessions for that user.
"""

from datetime import timedelta
import json
import logging
import os
import ssl
from typing import Any, Optional
import uuid

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status
import jwt
from sqlalchemy.orm import Session

from app.api.deps import (
    get_auth_service,
    get_current_active_session,
    get_current_user,
    get_current_user_and_session,
)
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    RateLimitException,
    SessionRevokedException,
    UnauthorizedException,
)
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_token,
)
from app.core.rate_limit import enforce_auth_rate_limit
from app.models.auth_session import (
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_REVOKED,
    AuthSession,
)
from app.models.base import utc_now
from app.models.user import User
from app.schemas.auth import (
    GoogleOAuthRequest,
    LoginResponse,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ResendVerificationRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.schemas.user import StaffOnboardingClaimRequest
from app.services.auth_service import AuthService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

# Expected Google OIDC issuers for ID token verification
_GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})

# Google public JWKS endpoint for RSA key discovery
_GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"

_google_jwks_client: Optional[jwt.PyJWKClient] = None


def _get_google_ssl_context() -> ssl.SSLContext:
    """Create a verified SSL context with root CA certificates for Google JWKS retrieval.

    Resolution strategy:
      1. Primary: certifi CA bundle (certifi.where()).
      2. Secondary: Well-known system CA bundle paths (e.g. /etc/ssl/cert.pem on macOS/Alpine,
         /etc/ssl/certs/ca-certificates.crt on Debian/Ubuntu, /etc/pki/tls/certs/ca-bundle.crt on RHEL)
         if certifi is unavailable or system trust store has zero root certificates.
      3. Fallback: ssl.create_default_context() with warning if zero certificates are loaded.
    """
    ca_file: Optional[str] = None

    try:
        import certifi

        certifi_path = certifi.where()
        if os.path.exists(certifi_path):
            ca_file = certifi_path
    except Exception as exc:
        logger.warning(
            "Could not load certifi CA bundle for Google JWKS verification: %s.",
            exc,
        )

    if ca_file is None:
        # Fallback to well-known system CA bundle paths if default store lacks certificates
        system_ca_candidates = (
            "/etc/ssl/cert.pem",                          # macOS, Alpine, FreeBSD
            "/etc/ssl/certs/ca-certificates.crt",        # Debian, Ubuntu
            "/etc/pki/tls/certs/ca-bundle.crt",          # Fedora, RHEL, CentOS
            "/etc/ssl/ca-bundle.pem",                     # OpenSUSE
        )
        for candidate in system_ca_candidates:
            if os.path.exists(candidate):
                ca_file = candidate
                break

    if ca_file:
        try:
            return ssl.create_default_context(cafile=ca_file)
        except Exception as exc:
            logger.warning(
                "Failed to create SSL context with cafile=%s: %s. Falling back to default trust store.",
                ca_file,
                exc,
            )

    ctx = ssl.create_default_context()
    if len(ctx.get_ca_certs()) == 0:
        logger.warning(
            "SSL context contains 0 root CA certificates. TLS verification to Google JWKS will likely fail."
        )
    return ctx


def reset_google_jwks_client() -> None:
    """Reset the singleton Google JWKS client."""
    global _google_jwks_client
    _google_jwks_client = None


def get_google_jwks_client() -> jwt.PyJWKClient:
    """Singleton getter for Google's public JWKS client with in-memory key caching and verified SSL context."""
    global _google_jwks_client
    if _google_jwks_client is None:
        _google_jwks_client = jwt.PyJWKClient(
            _GOOGLE_JWKS_URI,
            cache_jwk_set=True,
            lifespan=3600,
            timeout=10,
            ssl_context=_get_google_ssl_context(),
        )
    return _google_jwks_client


def _verify_google_id_token(
    id_token: str,
    settings: Settings,
    jwks_client: Optional[jwt.PyJWKClient] = None,
) -> dict:
    """Verify Google ID token signature and claims cryptographically (BUG-001).

    Validates:
      1. Cryptographic RSA signature (RS256) against Google's public JWKS.
      2. Token expiration (exp) and issued-at (iat).
      3. Trusted issuer (accounts.google.com or https://accounts.google.com).
      4. Audience matching GOOGLE_CLIENT_ID when configured.
      5. Email presence and email_verified=True.

    Raises:
        UnauthorizedException: If any check fails.
    """
    client = jwks_client or get_google_jwks_client()

    # In production, GOOGLE_CLIENT_ID must be configured and audience validation is mandatory (P1-02)
    if settings.is_production:
        if not settings.GOOGLE_CLIENT_ID or "mock" in settings.GOOGLE_CLIENT_ID.lower():
            raise UnauthorizedException(
                message="Google OAuth client ID is not configured in production.",
                code="OAUTH_NOT_CONFIGURED",
            )

    try:
        signing_key = client.get_signing_key_from_jwt(id_token)
    except Exception as exc:
        logger.warning("Google ID token key lookup failed: %s", exc, exc_info=True)
        raise UnauthorizedException(
            message="Google ID token key lookup failed.",
            code="INVALID_OAUTH_TOKEN",
            details={"error": str(exc)},
        ) from exc

    expected_aud = settings.GOOGLE_CLIENT_ID if settings.GOOGLE_CLIENT_ID else None
    require_aud = bool(expected_aud or settings.is_production)

    try:
        verified_claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=expected_aud,
            issuer=list(_GOOGLE_ISSUERS),
            options={
                "verify_signature": True,
                "verify_aud": require_aud,
                "require": ["exp", "iat", "sub", "iss"] + (["aud"] if require_aud else []),
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedException(
            message="Google ID token has expired.",
            code="OAUTH_TOKEN_EXPIRED",
        ) from exc
    except jwt.InvalidAudienceError as exc:
        raise UnauthorizedException(
            message="Google token audience mismatch.",
            code="INVALID_OAUTH_AUDIENCE",
        ) from exc
    except jwt.InvalidIssuerError as exc:
        raise UnauthorizedException(
            message="Google token issuer is not trusted.",
            code="INVALID_OAUTH_ISSUER",
        ) from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedException(
            message="Google ID token signature verification failed.",
            code="INVALID_OAUTH_TOKEN",
            details={"error": str(exc)},
        ) from exc

    # Validate verified email
    email = verified_claims.get("email")
    if not email or not isinstance(email, str):
        raise UnauthorizedException(
            message="Google token does not contain a valid email address.",
            code="INVALID_OAUTH_TOKEN",
        )
    if not verified_claims.get("email_verified", False):
        raise UnauthorizedException(
            message="Google account email is not verified.",
            code="OAUTH_EMAIL_UNVERIFIED",
        )

    return verified_claims


router = APIRouter(prefix="/auth", tags=["Authentication"])


def set_session_cookie(
    response: Response,
    session_token: str,
    settings: Settings,
) -> None:
    """Set secure session cookie according to RFC 6265bis and environment security policy."""
    cookie_name = settings.SESSION_COOKIE_NAME
    # RFC 6265bis: Any cookie beginning with __Host- MUST have Secure=True in real browsers.
    # Modern browsers accept Secure=True cookies on localhost/127.0.0.1 (W3C Secure Context).
    # In testing environment with testclient (http://testserver), honor SESSION_COOKIE_SECURE setting.
    if settings.ENVIRONMENT == "testing":
        secure_cookie = settings.SESSION_COOKIE_SECURE
    elif cookie_name.startswith("__Host-"):
        secure_cookie = True
    else:
        secure_cookie = settings.SESSION_COOKIE_SECURE

    response.set_cookie(
        key=cookie_name,
        value=session_token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        path=settings.SESSION_COOKIE_PATH,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        secure=secure_cookie,
        samesite=settings.SESSION_COOKIE_SAMESITE,
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    """Clear session cookie across domain paths and common cookie names."""
    cookie_names = {settings.SESSION_COOKIE_NAME, "__Host-lms_session", "lms_session"}
    for name in cookie_names:
        response.delete_cookie(
            key=name,
            path=settings.SESSION_COOKIE_PATH or "/",
        )
        if name.startswith("__Host-"):
            response.delete_cookie(
                key=name,
                path="/",
                secure=True,
            )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=MessageResponse,
    summary="Register new student account",
)
async def register(
    payload: UserRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """Register student account, stage verification email in outbox, and record audit log."""
    client_ip = request.client.host if request.client else None
    enforce_auth_rate_limit("register", identifier=str(payload.email), client_ip=client_ip)
    user_agent = request.headers.get("User-Agent")

    await auth_service.register(
        db,
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()

    return MessageResponse(
        message="Registration successful. Please check your email to verify your account."
    )


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=LoginResponse,
    summary="Authenticate credentials and establish single active session",
)
async def login(
    payload: UserLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """Authenticate student or staff credentials, atomically displace prior active sessions,

    set secure __Host-lms_session cookie, and return short-lived JWT access token.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    try:
        enforce_auth_rate_limit("login", identifier=str(payload.email), client_ip=client_ip, settings=settings)
    except RateLimitException as exc:
        await auth_service.record_rate_limit_breach(
            db,
            action="login",
            email=str(payload.email),
            client_ip=client_ip,
            user_agent=user_agent,
            retry_after=exc.retry_after,
        )
        raise exc

    user, raw_session_token, auth_session, access_token = await auth_service.login(
        db,
        email=str(payload.email),
        password=payload.password,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()

    set_session_cookie(response, raw_session_token, settings)

    return LoginResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        token_type="bearer",
        expires_in=900,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    response_model=MessageResponse,
    summary="Revoke active session and clear session cookie",
)
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    """Revoke authenticated session and remove session cookie."""
    raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not raw_token:
        # Check alternative cookie names across environments
        raw_token = request.cookies.get("__Host-lms_session") or request.cookies.get("lms_session")

    if raw_token:
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")
        try:
            await auth_service.logout(
                db,
                raw_session_token=raw_token,
                ip_address=client_ip,
                user_agent=user_agent,
            )
            db.commit()
        except Exception as exc:
            logger.warning("Error during session logout revocation: %s", exc)
            db.rollback()

    clear_session_cookie(response, settings)
    return MessageResponse(message="Logged out successfully.")


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=UserResponse,
    summary="Retrieve current authenticated user profile",
)
async def me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return profile and assigned roles for currently authenticated user."""
    return UserResponse.model_validate(current_user)


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    summary="Issue fresh access token using active session cookie",
)
async def refresh(
    auth_tuple: tuple[User, Optional[AuthSession]] = Depends(get_current_user_and_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Generate fresh short-lived JWT access token for active session."""
    user, auth_session = auth_tuple
    session_id = str(auth_session.id) if auth_session else None

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"roles": user.roles, "session_id": session_id},
        expires_delta=timedelta(minutes=15),
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 900,
    }


@router.post(
    "/verify-email",
    status_code=status.HTTP_200_OK,
    response_model=MessageResponse,
    summary="Verify student email address using single-use token",
)
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """Consume single-use verification token and mark user verified."""
    client_ip = request.client.host if request.client else None
    enforce_auth_rate_limit("email_verify", identifier=payload.token, client_ip=client_ip)
    user_agent = request.headers.get("User-Agent")

    await auth_service.verify_email(
        db,
        raw_token=payload.token,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()

    return MessageResponse(
        message="Email address verified successfully. You may now access your course content."
    )


@router.post(
    "/resend-verification",
    status_code=status.HTTP_200_OK,
    response_model=MessageResponse,
    summary="Resend verification email adhering to anti-enumeration principles",
)
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """Generate new verification token if user unverified; return generic response."""
    enforce_auth_rate_limit("resend_verification", identifier=str(payload.email), client_ip=request.client.host if request.client else None)
    await auth_service.resend_verification_email(db, email=str(payload.email))
    db.commit()

    return MessageResponse(
        message="If this email is unverified, a new verification link has been sent."
    )


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_200_OK,
    response_model=MessageResponse,
    summary="Request password reset link adhering to anti-enumeration principles",
)
async def password_reset_request(
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """Initiate password reset flow. Always returns uniform HTTP 200 to prevent account enumeration."""
    client_ip = request.client.host if request.client else None
    enforce_auth_rate_limit("password_reset", identifier=str(payload.email), client_ip=client_ip)
    user_agent = request.headers.get("User-Agent")

    await auth_service.request_password_reset(
        db,
        email=str(payload.email),
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()

    return MessageResponse(
        message="If this email is registered, password reset instructions have been sent."
    )


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_200_OK,
    response_model=MessageResponse,
    summary="Confirm password reset and revoke all active user sessions",
)
async def password_reset_confirm(
    payload: PasswordResetConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """Consume reset token, update password hash, and atomically revoke all active sessions."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    await auth_service.confirm_password_reset(
        db,
        raw_token=payload.token,
        new_password=payload.new_password,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()

    return MessageResponse(
        message="Password reset completed successfully. All active sessions have been terminated. Please log in with your new password."
    )


@router.post(
    "/oauth/google",
    status_code=status.HTTP_200_OK,
    response_model=LoginResponse,
    summary="Authenticate via Google Identity Services OAuth 2.0 / OIDC",
)
async def google_oauth(
    payload: GoogleOAuthRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """Verify Google ID token, provision or link student account, enforce session displacement,

    and issue authentication cookies and JWT access token.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    # Verify Google ID token with cryptographic signature validation
    try:
        verified_claims = _verify_google_id_token(payload.id_token, settings)
    except UnauthorizedException:
        raise
    except Exception as exc:
        raise UnauthorizedException(
            message="Malformed or invalid Google ID token.",
            code="INVALID_OAUTH_TOKEN",
            details={"error": str(exc)},
        ) from exc

    user, raw_session_token, auth_session, access_token = await auth_service.google_oauth_authenticate(
        db,
        id_token_payload=verified_claims,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()

    set_session_cookie(response, raw_session_token, settings)

    return LoginResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        token_type="bearer",
        expires_in=900,
    )


@router.post(
    "/onboarding/claim",
    status_code=status.HTTP_200_OK,
    response_model=LoginResponse,
    summary="Claim staff onboarding invitation token and set initial password",
)
async def claim_staff_onboarding_endpoint(
    payload: StaffOnboardingClaimRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """Validate 48h invitation token, set user password, create active session, and issue cookie."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    user_service = UserService(settings=settings)
    user, raw_session_token, auth_session = await user_service.claim_staff_onboarding(
        db,
        token=payload.token,
        password=payload.password,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()

    set_session_cookie(response, raw_session_token, settings)

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"roles": user.roles, "session_id": str(auth_session.id)},
        expires_delta=timedelta(minutes=15),
    )

    return LoginResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        token_type="bearer",
        expires_in=900,
    )

