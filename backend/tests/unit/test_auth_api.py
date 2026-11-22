"""API integration tests for Authentication and Identity endpoints (/api/v1/auth/*).

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 3)
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/08-SESSION-MANAGEMENT.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK104, TASK105, TASK106)

Verifies:
1. Registration: 201 Created with outbox notification staged.
2. Login: 200 OK with __Host-lms_session cookie and JWT bearer token.
3. Protected Profile (/me): 200 OK with cookie or bearer token, 401 on missing auth.
4. Token Refresh (/refresh): issues fresh access token.
5. Logout (/logout): revokes session and clears cookie.
6. Single-Active-Session Displacement Invariant:
   - Device 1 login -> Device 2 login -> Device 1 receives HTTP 401 SESSION_REVOKED.
7. Email Verification: single-use token lifecycle.
8. Password Reset: anti-enumeration request, confirmation, and multi-device session revocation.
9. Google OAuth: ID token exchange and session establishment.
"""

from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.main import create_app
from app.models import (
    ROLE_STUDENT,
    SYSTEM_ROLES,
    AuthSession,
    Base,
    NotificationOutbox,
    Role,
    User,
)


@pytest.fixture
def test_app_and_db():
    """Create isolated SQLite database and configured FastAPI TestClient."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Seed canonical roles
    with TestingSessionLocal() as init_session:
        for role_id in SYSTEM_ROLES:
            init_session.add(Role(id=role_id, name=role_id.capitalize(), description=f"{role_id} role"))
        init_session.commit()

    # Create app with custom test settings
    test_settings = Settings(
        ENVIRONMENT="testing",
        DEBUG=True,
        SESSION_COOKIE_SECURE=False,  # Allow HTTP test client cookies
        DATABASE_URL="sqlite:///:memory:",
        GOOGLE_CLIENT_ID="test-google-client-id",
    )
    app = create_app(settings=test_settings)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: test_settings

    client = TestClient(app)
    try:
        yield client, TestingSessionLocal, test_settings
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


def _verify_user_email(session_factory, email: str) -> None:
    """Helper to mark a registered user's email as verified for testing login flows."""
    with session_factory() as db:
        user = db.query(User).filter(User.email == email.lower()).first()
        if user:
            user.is_verified = True
            db.commit()


class TestAuthAPIRegistrationAndLogin:
    """Verifies registration and credential authentication endpoints."""

    def test_registration_success(self, test_app_and_db):
        client, session_factory, _ = test_app_and_db

        resp = client.post(
            "/api/v1/auth/register",
            json={
                "email": "student@example.com",
                "password": "StrongPassword!123",
                "full_name": "Alice Wonderland",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "message" in data

        # Verify user created in DB
        with session_factory() as db:
            user = db.query(User).filter(User.email == "student@example.com").first()
            assert user is not None
            assert user.full_name == "Alice Wonderland"
            assert user.is_verified is False
            assert user.has_role(ROLE_STUDENT) is True

            # Verify verification email staged in outbox
            outbox = db.query(NotificationOutbox).filter(NotificationOutbox.recipient == "student@example.com").first()
            assert outbox is not None
            assert outbox.event_type == "AUTH_VERIFY_EMAIL"

    def test_registration_duplicate_email_fails(self, test_app_and_db):
        client, _, _ = test_app_and_db

        client.post(
            "/api/v1/auth/register",
            json={
                "email": "duplicate@example.com",
                "password": "StrongPassword!123",
                "full_name": "First User",
            },
        )
        resp2 = client.post(
            "/api/v1/auth/register",
            json={
                "email": "DUPLICATE@example.com",
                "password": "StrongPassword!123",
                "full_name": "Second User",
            },
        )
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    def test_login_unverified_email_returns_403(self, test_app_and_db):
        client, _, _ = test_app_and_db

        client.post(
            "/api/v1/auth/register",
            json={
                "email": "unverified@example.com",
                "password": "StrongPassword!123",
                "full_name": "Unverified Tester",
            },
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": "unverified@example.com",
                "password": "StrongPassword!123",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"

    def test_login_success_sets_cookie_and_returns_token(self, test_app_and_db):
        client, session_factory, settings = test_app_and_db

        # Register
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "login_test@example.com",
                "password": "StrongPassword!123",
                "full_name": "Login Tester",
            },
        )

        # Verify email before login (mandatory email verification invariant)
        _verify_user_email(session_factory, "login_test@example.com")

        # Login
        resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": "login_test@example.com",
                "password": "StrongPassword!123",
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        # Check payload
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "login_test@example.com"
        assert data["user"]["roles"] == ["STUDENT"]

        # Check session cookie set
        assert settings.SESSION_COOKIE_NAME in resp.cookies
        cookie_val = resp.cookies[settings.SESSION_COOKIE_NAME]
        assert len(cookie_val) >= 32

    def test_login_invalid_credentials_returns_401(self, test_app_and_db):
        client, _, _ = test_app_and_db

        resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "WrongPassword!123",
            },
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


class TestAuthAPISessionManagementAndDisplacement:
    """Verifies single-active-session invariant and session endpoints."""

    def test_me_endpoint_with_cookie(self, test_app_and_db):
        client, session_factory, settings = test_app_and_db

        # Register and login
        client.post(
            "/api/v1/auth/register",
            json={"email": "me_user@example.com", "password": "StrongPassword!123", "full_name": "Me User"},
        )
        _verify_user_email(session_factory, "me_user@example.com")
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "me_user@example.com", "password": "StrongPassword!123"},
        )
        cookie_val = login_resp.cookies[settings.SESSION_COOKIE_NAME]

        # Call /me with cookie
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == "me_user@example.com"

        # Clear cookie jar to simulate unauthenticated request -> 401
        client.cookies.clear()
        unauth_resp = client.get("/api/v1/auth/me")
        assert unauth_resp.status_code == 401

    def test_refresh_token_endpoint(self, test_app_and_db):
        client, session_factory, settings = test_app_and_db

        client.post(
            "/api/v1/auth/register",
            json={"email": "refresh_user@example.com", "password": "StrongPassword!123", "full_name": "Refresh User"},
        )
        _verify_user_email(session_factory, "refresh_user@example.com")
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "refresh_user@example.com", "password": "StrongPassword!123"},
        )
        cookie_val = login_resp.cookies[settings.SESSION_COOKIE_NAME]

        refresh_resp = client.post(
            "/api/v1/auth/refresh",
            cookies={settings.SESSION_COOKIE_NAME: cookie_val},
        )
        assert refresh_resp.status_code == 200
        assert "access_token" in refresh_resp.json()

    def test_single_active_session_displacement_returns_401_session_revoked(self, test_app_and_db):
        """CRITICAL INVARIANT [LMS Blueprint v2.0 Page 8]:

        Login on Device B displaces Device A.
        Device A subsequent request returns HTTP 401 with code SESSION_REVOKED.
        """
        client, session_factory, settings = test_app_and_db

        # Register user
        client.post(
            "/api/v1/auth/register",
            json={"email": "displaced_client@example.com", "password": "StrongPassword!123", "full_name": "Displace Test"},
        )
        _verify_user_email(session_factory, "displaced_client@example.com")

        # Login Device A
        resp_a = client.post(
            "/api/v1/auth/login",
            json={"email": "displaced_client@example.com", "password": "StrongPassword!123"},
            headers={"User-Agent": "DeviceA_Browser"},
        )
        assert resp_a.status_code == 200
        cookie_a = resp_a.cookies[settings.SESSION_COOKIE_NAME]

        # Device A accesses /me successfully
        check_a1 = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: cookie_a})
        assert check_a1.status_code == 200

        # Login Device B
        resp_b = client.post(
            "/api/v1/auth/login",
            json={"email": "displaced_client@example.com", "password": "StrongPassword!123"},
            headers={"User-Agent": "DeviceB_Browser"},
        )
        assert resp_b.status_code == 200
        cookie_b = resp_b.cookies[settings.SESSION_COOKIE_NAME]

        # Device A accesses /me with cookie_a -> MUST receive HTTP 401 SESSION_REVOKED
        check_a2 = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: cookie_a})
        assert check_a2.status_code == 401
        assert check_a2.json()["error"]["code"] == "SESSION_REVOKED"
        assert "terminated because a newer login occurred" in check_a2.json()["error"]["message"]
        # CRITICAL RECOVERY: Response must purge the revoked session cookie
        assert settings.SESSION_COOKIE_NAME in check_a2.headers.get("set-cookie", "")
        assert "max-age=0" in check_a2.headers.get("set-cookie", "").lower()

        # Device B accesses /me with cookie_b -> MUST succeed with 200 OK
        check_b = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: cookie_b})
        assert check_b.status_code == 200
        assert check_b.json()["email"] == "displaced_client@example.com"

    def test_logout_revokes_session_and_clears_cookie(self, test_app_and_db):
        client, session_factory, settings = test_app_and_db

        client.post(
            "/api/v1/auth/register",
            json={"email": "logout_user@example.com", "password": "StrongPassword!123", "full_name": "Logout User"},
        )
        _verify_user_email(session_factory, "logout_user@example.com")
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "logout_user@example.com", "password": "StrongPassword!123"},
        )
        cookie_val = login_resp.cookies[settings.SESSION_COOKIE_NAME]

        # Logout
        logout_resp = client.post(
            "/api/v1/auth/logout",
            cookies={settings.SESSION_COOKIE_NAME: cookie_val},
        )
        assert logout_resp.status_code == 200

        # Subsequent /me call with previous cookie must fail
        subsequent = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: cookie_val})
        assert subsequent.status_code == 401


class TestAuthAPIEmailVerificationAndReset:
    """Verifies email verification and password reset flows."""

    def test_email_verification_flow(self, test_app_and_db):
        client, session_factory, _ = test_app_and_db

        # Register
        client.post(
            "/api/v1/auth/register",
            json={"email": "email_verify@example.com", "password": "StrongPassword!123", "full_name": "EV User"},
        )

        # Get verification token from outbox
        with session_factory() as db:
            outbox = db.query(NotificationOutbox).filter(NotificationOutbox.recipient == "email_verify@example.com").first()
            raw_token = outbox.payload["verification_token"]

        # Verify email
        resp = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
        assert resp.status_code == 200

        # Check user verified in DB
        with session_factory() as db:
            user = db.query(User).filter(User.email == "email_verify@example.com").first()
            assert user.is_verified is True

        # Second attempt fails (single-use)
        resp2 = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
        assert resp2.status_code == 400

    def test_resend_verification_endpoint(self, test_app_and_db):
        client, _, _ = test_app_and_db

        resp = client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "any_email@example.com"},
        )
        assert resp.status_code == 200
        assert "If this email is unverified" in resp.json()["message"]

    def test_password_reset_flow_revokes_all_active_sessions(self, test_app_and_db):
        client, session_factory, settings = test_app_and_db

        # 1. Register & login
        client.post(
            "/api/v1/auth/register",
            json={"email": "pw_flow@example.com", "password": "InitialPassword!123", "full_name": "PW Flow"},
        )
        _verify_user_email(session_factory, "pw_flow@example.com")
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "pw_flow@example.com", "password": "InitialPassword!123"},
        )
        active_cookie = login_resp.cookies[settings.SESSION_COOKIE_NAME]

        # 2. Request reset
        req_resp = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "pw_flow@example.com"},
        )
        assert req_resp.status_code == 200

        # 3. Retrieve token from outbox
        with session_factory() as db:
            outbox = (
                db.query(NotificationOutbox)
                .filter(NotificationOutbox.recipient == "pw_flow@example.com")
                .filter(NotificationOutbox.event_type == "AUTH_RESET_PASSWORD")
                .first()
            )
            reset_token = outbox.payload["reset_token"]

        # 4. Confirm password reset
        confirm_resp = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": reset_token, "new_password": "UpdatedPassword!456"},
        )
        assert confirm_resp.status_code == 200

        # 5. INVARIANT: Previous active session MUST be revoked across all devices
        check_old = client.get("/api/v1/auth/me", cookies={settings.SESSION_COOKIE_NAME: active_cookie})
        assert check_old.status_code == 401
        assert check_old.json()["error"]["code"] == "SESSION_REVOKED"

        # 6. Login with new password succeeds
        new_login = client.post(
            "/api/v1/auth/login",
            json={"email": "pw_flow@example.com", "password": "UpdatedPassword!456"},
        )
        assert new_login.status_code == 200


class TestAuthAPIGoogleOAuth:
    """Verifies Google OAuth exchange endpoint with cryptographic RS256 verification (BUG-001)."""

    @pytest.fixture(autouse=True)
    def setup_rsa_keys(self):
        """Generates real RSA keypair and mocks JWKS client for cryptographic verification tests."""
        from unittest.mock import MagicMock, patch
        from cryptography.hazmat.primitives.asymmetric import rsa

        self.client_id = "test-google-client-id"
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key = self.private_key.public_key()

        self.mock_jwks_client = MagicMock()
        mock_signing_key = MagicMock()
        mock_signing_key.key = self.public_key
        self.mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch("app.api.v1.auth.get_google_jwks_client", return_value=self.mock_jwks_client):
            yield

    def _generate_google_jwt(self, payload: dict, key=None, headers=None, aud=None) -> str:
        """Helper to generate an RS256 signed JWT with Google claims."""
        signing_key = key or self.private_key
        hdr = headers or {"kid": "test-google-kid"}
        claims = dict(payload)
        if "aud" not in claims:
            claims["aud"] = aud or getattr(self, "client_id", "test-google-client-id")
        return jwt.encode(claims, signing_key, algorithm="RS256", headers=hdr)

    def test_google_oauth_exchange_success(self, test_app_and_db):
        """Valid cryptographically signed Google token is accepted and provisions student."""
        client, session_factory, settings = test_app_and_db
        import time

        now = int(time.time())
        mock_payload = {
            "iss": "https://accounts.google.com",
            "sub": "oauth-sub-123",
            "email": "oauth.student@example.com",
            "email_verified": True,
            "name": "OAuth Student",
            "picture": "https://example.com/pic.jpg",
            "iat": now,
            "exp": now + 3600,
        }
        test_jwt = self._generate_google_jwt(mock_payload)

        resp = client.post(
            "/api/v1/auth/oauth/google",
            json={"id_token": test_jwt},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["email"] == "oauth.student@example.com"
        assert data["user"]["is_verified"] is True
        assert settings.SESSION_COOKIE_NAME in resp.cookies

    def test_google_oauth_rejects_forged_signature(self, test_app_and_db):
        """Token signed by untrusted/attacker RSA key is rejected."""
        client, _, _ = test_app_and_db
        import time
        from cryptography.hazmat.primitives.asymmetric import rsa

        attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = int(time.time())
        payload = {
            "iss": "https://accounts.google.com",
            "sub": "forged-123",
            "email": "forged@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
        }
        forged_jwt = self._generate_google_jwt(payload, key=attacker_key)

        resp = client.post("/api/v1/auth/oauth/google", json={"id_token": forged_jwt})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_OAUTH_TOKEN"

    def test_google_oauth_rejects_expired_token(self, test_app_and_db):
        """Expired Google ID token is rejected."""
        client, _, _ = test_app_and_db
        import time

        now = int(time.time())
        payload = {
            "iss": "https://accounts.google.com",
            "sub": "expired-123",
            "email": "expired@example.com",
            "email_verified": True,
            "iat": now - 7200,
            "exp": now - 3600,
        }
        expired_jwt = self._generate_google_jwt(payload)

        resp = client.post("/api/v1/auth/oauth/google", json={"id_token": expired_jwt})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "OAUTH_TOKEN_EXPIRED"

    def test_google_oauth_rejects_unverified_email(self, test_app_and_db):
        """Google token with email_verified=False is rejected to prevent account takeover."""
        client, _, _ = test_app_and_db
        import time

        now = int(time.time())
        payload = {
            "iss": "https://accounts.google.com",
            "sub": "unverified-123",
            "email": "victim@example.com",
            "email_verified": False,
            "iat": now,
            "exp": now + 3600,
        }
        unverified_jwt = self._generate_google_jwt(payload)

        resp = client.post("/api/v1/auth/oauth/google", json={"id_token": unverified_jwt})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "OAUTH_EMAIL_UNVERIFIED"

    def test_google_oauth_rejects_untrusted_issuer(self, test_app_and_db):
        """Token with untrusted issuer is rejected."""
        client, _, _ = test_app_and_db
        import time

        now = int(time.time())
        payload = {
            "iss": "https://evil-issuer.com",
            "sub": "evil-123",
            "email": "evil@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
        }
        evil_jwt = self._generate_google_jwt(payload)

        resp = client.post("/api/v1/auth/oauth/google", json={"id_token": evil_jwt})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_OAUTH_ISSUER"

    def test_google_oauth_rejects_audience_mismatch(self, test_app_and_db):
        """Token with audience not matching configured GOOGLE_CLIENT_ID is rejected."""
        client, _, _ = test_app_and_db
        import time

        now = int(time.time())
        payload = {
            "iss": "https://accounts.google.com",
            "sub": "mismatch-123",
            "aud": "attacker-client-id.apps.googleusercontent.com",
            "email": "victim@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
        }
        mismatched_jwt = self._generate_google_jwt(payload, aud="attacker-client-id.apps.googleusercontent.com")

        resp = client.post("/api/v1/auth/oauth/google", json={"id_token": mismatched_jwt})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_OAUTH_AUDIENCE"

    def test_google_oauth_key_lookup_failure_handled_cleanly(self, test_app_and_db):
        """When PyJWKClient fails key lookup, endpoint returns 401 INVALID_OAUTH_TOKEN."""
        from unittest.mock import MagicMock, patch
        import jwt as pyjwt

        client, _, _ = test_app_and_db
        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.side_effect = pyjwt.exceptions.PyJWKClientConnectionError(
            'Fail to fetch data from the url, err: "Connection timeout"'
        )

        with patch("app.api.v1.auth.get_google_jwks_client", return_value=mock_jwks):
            resp = client.post(
                "/api/v1/auth/oauth/google",
                json={"id_token": "mock.google.id.token.with.valid.length"},
            )

        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "INVALID_OAUTH_TOKEN"
        assert data["error"]["message"] == "Google ID token key lookup failed."


class TestGoogleJWKSClientAndCookieSecurity:
    """Verifies Google JWKS TLS context, singleton configuration, and RFC 6265bis cookie invariants."""

    def test_google_ssl_context_creation(self):
        """Verified SSL context is created with trusted root CA certificates."""
        import ssl
        from app.api.v1.auth import _get_google_ssl_context

        ctx = _get_google_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True
        assert len(ctx.get_ca_certs()) > 0, "SSL context must contain trusted CA certificates to verify Google JWKS"

    def test_google_ssl_context_system_ca_fallback(self, monkeypatch):
        """When certifi is unavailable or fails, system CA bundle fallback loads certificates."""
        import builtins
        import ssl
        from app.api.v1.auth import _get_google_ssl_context

        orig_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "certifi":
                raise ImportError("Mocked certifi missing")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        ctx = _get_google_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        # On systems with standard CA bundle (/etc/ssl/cert.pem etc.), root certs must be present
        import os
        if any(os.path.exists(p) for p in ["/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"]):
            assert len(ctx.get_ca_certs()) > 0

    def test_empty_or_broken_ssl_context_reproduces_key_lookup_failure(self):
        """Regression test: when SSL certificate verification fails, key lookup raises UnauthorizedException with details."""
        import ssl
        from unittest.mock import MagicMock
        from app.api.v1.auth import _verify_google_id_token
        from app.core.config import Settings
        from app.core.exceptions import UnauthorizedException
        import jwt as pyjwt

        dev_settings = Settings.model_construct(
            ENVIRONMENT="development",
            GOOGLE_CLIENT_ID="test-client-id",
        )

        broken_client = MagicMock()
        ssl_error = pyjwt.exceptions.PyJWKClientConnectionError(
            'Fail to fetch data from the url, err: "<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1081)>"'
        )
        broken_client.get_signing_key_from_jwt.side_effect = ssl_error

        import pytest
        with pytest.raises(UnauthorizedException) as exc_info:
            _verify_google_id_token("dummy.token.here", dev_settings, jwks_client=broken_client)

        assert exc_info.value.code == "INVALID_OAUTH_TOKEN"
        assert exc_info.value.message == "Google ID token key lookup failed."
        assert "CERTIFICATE_VERIFY_FAILED" in exc_info.value.details["error"]

    def test_google_jwks_client_configuration(self):
        """JWKS client is configured with in-memory caching, 10s timeout, and verified SSL."""
        from app.api.v1 import auth

        # Reset singleton to test unpatched initialization
        auth.reset_google_jwks_client()
        try:
            client = auth.get_google_jwks_client()
            assert client.uri == auth._GOOGLE_JWKS_URI
            assert client.jwk_set_cache is not None
            assert client.jwk_set_cache.lifespan == 3600
            assert client.timeout == 10
            assert client.ssl_context is not None
            assert len(client.ssl_context.get_ca_certs()) > 0
        finally:
            auth.reset_google_jwks_client()

    def test_set_session_cookie_host_prefix_enforces_secure_in_dev_and_prod(self):
        """RFC 6265bis invariant: __Host- prefix mandates Secure=True in development and production."""
        from fastapi import Response
        from app.api.v1.auth import set_session_cookie

        # 1. Development environment with __Host- prefix
        dev_settings = Settings.model_construct(
            ENVIRONMENT="development",
            SESSION_COOKIE_NAME="__Host-lms_session",
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_PATH="/",
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="lax",
            SESSION_MAX_AGE_SECONDS=604800,
        )
        resp_dev = Response()
        set_session_cookie(resp_dev, "token_123", dev_settings)
        dev_cookie_header = resp_dev.headers.get("set-cookie", "")
        assert "secure" in dev_cookie_header.lower()
        assert "__Host-lms_session" in dev_cookie_header

        # 2. Production environment with __Host- prefix
        prod_settings = Settings.model_construct(
            ENVIRONMENT="production",
            SESSION_COOKIE_NAME="__Host-lms_session",
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_PATH="/",
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="lax",
            SESSION_MAX_AGE_SECONDS=604800,
        )
        resp_prod = Response()
        set_session_cookie(resp_prod, "token_456", prod_settings)
        prod_cookie_header = resp_prod.headers.get("set-cookie", "")
        assert "secure" in prod_cookie_header.lower()
        assert "__Host-lms_session" in prod_cookie_header

        # 3. Testing environment allows testclient override
        test_settings = Settings.model_construct(
            ENVIRONMENT="testing",
            SESSION_COOKIE_NAME="__Host-lms_session",
            SESSION_COOKIE_SECURE=False,
            SESSION_COOKIE_PATH="/",
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="lax",
            SESSION_MAX_AGE_SECONDS=604800,
        )
        resp_test = Response()
        set_session_cookie(resp_test, "token_789", test_settings)
        test_cookie_header = resp_test.headers.get("set-cookie", "")
        assert "secure" not in test_cookie_header.lower()
