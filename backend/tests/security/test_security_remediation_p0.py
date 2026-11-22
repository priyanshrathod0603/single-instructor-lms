"""Comprehensive P0 Security Remediation Regression Test Suite.

Authoritative Specification:
- BUG-001: Google OAuth Token Signature Verification (RS256, JWKS, aud, iss, email_verified)
- BUG-002: Protected Media Authorization Fail-Open (fail-closed, lesson context, attachment, enrollment, preview)
- BUG-003: Razorpay Webhook Secret and Gateway Production Hardening (no placeholder secrets, fail-closed)
- BUG-014: Staff Onboarding JWT Session Binding and Dependency Enforcement
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch
import uuid

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ForbiddenException,
    SessionRevokedException,
    UnauthorizedException,
)
from app.core.permissions import CANONICAL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
from app.core.razorpay import RazorpayClient, compute_razorpay_signature
from app.core.security import (
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
)
from app.main import create_app
from app.models.auth_session import (
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_REVOKED,
    AuthSession,
)
from app.models.auth_token import AuthToken, TOKEN_TYPE_STAFF_ONBOARDING
from app.models.base import Base, utc_now
from app.models.course import Course, CourseRevision, COURSE_STATUS_PUBLISHED
from app.models.curriculum import (
    LESSON_TYPE_VIDEO,
    CurriculumLesson,
    CurriculumSection,
    LessonResource,
    RESOURCE_TYPE_PDF,
)
from app.models.enrollment import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_REVOKED,
    Enrollment,
)
from app.models.media import MEDIA_STATUS_READY, MediaAsset
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
from tests.conftest import create_test_auth_headers


@pytest.fixture
def sec_db():
    """In-memory SQLite database seeded with full RBAC roles and permissions."""
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
        Role(id=ROLE_STAFF, name="Staff", description="Teaching assistant"),
        Role(id=ROLE_ADMIN, name="Admin", description="Platform admin"),
        Role(id=ROLE_SUPER_ADMIN, name="Super Admin", description="Owner"),
    ]
    session.add_all(roles)

    now = datetime.now(timezone.utc)
    for p_id, p_mod, p_desc in CANONICAL_PERMISSIONS:
        session.add(Permission(id=p_id, module=p_mod, description=p_desc, created_at=now))

    for r_id, p_keys in DEFAULT_ROLE_PERMISSIONS.items():
        for p_key in p_keys:
            session.add(RolePermission(role_id=r_id, permission_id=p_key, assigned_at=now))

    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def sec_client(sec_db: Session):
    """FastAPI TestClient with overridden get_db dependency."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: sec_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# =============================================================================
# BUG-001: Google OAuth Token Signature Verification Regression Tests
# =============================================================================

class TestBug001GoogleOAuthTokenVerification:
    """Verifies that Google OAuth ID tokens require cryptographic RS256 verification."""

    @pytest.fixture(autouse=True)
    def setup_rsa(self):
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key = self.private_key.public_key()

        self.mock_jwks = MagicMock()
        mock_key = MagicMock()
        mock_key.key = self.public_key
        self.mock_jwks.get_signing_key_from_jwt.return_value = mock_key

    def _mint_google_jwt(self, claims: dict, key=None) -> str:
        k = key or self.private_key
        payload = dict(claims)
        client_id = get_settings().GOOGLE_CLIENT_ID
        if client_id and "aud" not in payload:
            payload["aud"] = client_id
        return jwt.encode(payload, k, algorithm="RS256", headers={"kid": "google-rsa-kid"})

    def test_valid_google_token_accepted(self, sec_client: TestClient):
        """Valid Google token with RS256 signature is accepted."""
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "sub": "valid-sub-001",
            "email": "learner@example.com",
            "email_verified": True,
            "name": "Valid Learner",
            "iat": now,
            "exp": now + 3600,
        }
        token = self._mint_google_jwt(claims)
        with patch("app.api.v1.auth.get_google_jwks_client", return_value=self.mock_jwks):
            resp = sec_client.post("/api/v1/auth/oauth/google", json={"id_token": token})
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == "learner@example.com"

    def test_forged_signature_rejected(self, sec_client: TestClient):
        """Token signed with attacker private key fails signature verification."""
        attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "sub": "attacker-sub",
            "email": "victim@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
        }
        token = self._mint_google_jwt(claims, key=attacker_key)
        with patch("app.api.v1.auth.get_google_jwks_client", return_value=self.mock_jwks):
            resp = sec_client.post("/api/v1/auth/oauth/google", json={"id_token": token})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_OAUTH_TOKEN"

    def test_forged_email_rejected_if_unverified(self, sec_client: TestClient):
        """Token with email_verified=False is rejected to prevent account takeover."""
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "sub": "unverified-sub",
            "email": "ceo@example.com",
            "email_verified": False,
            "iat": now,
            "exp": now + 3600,
        }
        token = self._mint_google_jwt(claims)
        with patch("app.api.v1.auth.get_google_jwks_client", return_value=self.mock_jwks):
            resp = sec_client.post("/api/v1/auth/oauth/google", json={"id_token": token})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "OAUTH_EMAIL_UNVERIFIED"

    def test_incorrect_audience_rejected(self, sec_client: TestClient, monkeypatch):
        """Token with audience mismatch against configured GOOGLE_CLIENT_ID is rejected."""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "configured-expected-aud.apps.googleusercontent.com")
        get_settings.cache_clear()

        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "aud": "wrong-malicious-aud.apps.googleusercontent.com",
            "sub": "wrong-aud-sub",
            "email": "learner@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
        }
        token = self._mint_google_jwt(claims)
        with patch("app.api.v1.auth.get_google_jwks_client", return_value=self.mock_jwks):
            resp = sec_client.post("/api/v1/auth/oauth/google", json={"id_token": token})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_OAUTH_AUDIENCE"

    def test_incorrect_issuer_rejected(self, sec_client: TestClient):
        """Token with untrusted issuer is rejected."""
        now = int(time.time())
        claims = {
            "iss": "https://fake-google.com",
            "sub": "fake-iss-sub",
            "email": "learner@example.com",
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
        }
        token = self._mint_google_jwt(claims)
        with patch("app.api.v1.auth.get_google_jwks_client", return_value=self.mock_jwks):
            resp = sec_client.post("/api/v1/auth/oauth/google", json={"id_token": token})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_OAUTH_ISSUER"

    def test_expired_token_rejected(self, sec_client: TestClient):
        """Expired Google token is rejected."""
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "sub": "expired-sub",
            "email": "learner@example.com",
            "email_verified": True,
            "iat": now - 7200,
            "exp": now - 3600,
        }
        token = self._mint_google_jwt(claims)
        with patch("app.api.v1.auth.get_google_jwks_client", return_value=self.mock_jwks):
            resp = sec_client.post("/api/v1/auth/oauth/google", json={"id_token": token})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "OAUTH_TOKEN_EXPIRED"


# =============================================================================
# BUG-002: Protected Media Authorization Fail-Open Regression Tests
# =============================================================================

class TestBug002MediaAuthorizationFailClosed:
    """Verifies that media authorization is strictly fail-closed."""

    @pytest.fixture
    def media_fixture(self, sec_db: Session):
        admin = User(
            email="admin_media@lms.local",
            full_name="Media Admin",
            password_hash=hash_password("Pass1234!@#$"),
            is_verified=True,
            is_active=True,
        )
        student = User(
            email="enrolled_student@lms.local",
            full_name="Enrolled Student",
            password_hash=hash_password("Pass1234!@#$"),
            is_verified=True,
            is_active=True,
        )
        non_enrolled = User(
            email="intruder@lms.local",
            full_name="Non Enrolled",
            password_hash=hash_password("Pass1234!@#$"),
            is_verified=True,
            is_active=True,
        )
        suspended = User(
            email="suspended@lms.local",
            full_name="Suspended Student",
            password_hash=hash_password("Pass1234!@#$"),
            is_verified=True,
            is_active=False,
        )
        sec_db.add_all([admin, student, non_enrolled, suspended])
        sec_db.flush()

        admin.user_roles.append(UserRole(role_id=ROLE_SUPER_ADMIN, user_id=admin.id))
        student.user_roles.append(UserRole(role_id=ROLE_STUDENT, user_id=student.id))
        non_enrolled.user_roles.append(UserRole(role_id=ROLE_STUDENT, user_id=non_enrolled.id))
        suspended.user_roles.append(UserRole(role_id=ROLE_STUDENT, user_id=suspended.id))

        # Course 1: Protected
        c1 = Course(
            title="Protected Course 1",
            slug="c1",
            price_inr=1000,
            is_free=False,
            status=COURSE_STATUS_PUBLISHED,
        )
        sec_db.add(c1)
        sec_db.flush()
        rev1 = CourseRevision(
            course_id=c1.id,
            revision_no=1,
            title="Rev 1",
            status=COURSE_STATUS_PUBLISHED,
        )
        sec_db.add(rev1)
        sec_db.flush()
        c1.live_revision_id = rev1.id
        sec_db.flush()
        s1 = CurriculumSection(course_revision_id=rev1.id, title="Sec 1", sort_order=0)
        sec_db.add(s1)
        sec_db.flush()

        # Media assets
        protected_video = MediaAsset(
            uploader_id=admin.id,
            filename="protected_vid.mp4",
            file_key="videos/protected_vid.mp4",
            bucket="lms-media",
            mime_type="video/mp4",
            file_size_bytes=1000,
            status=MEDIA_STATUS_READY,
        )
        preview_video = MediaAsset(
            uploader_id=admin.id,
            filename="preview_vid.mp4",
            file_key="videos/preview_vid.mp4",
            bucket="lms-media",
            mime_type="video/mp4",
            file_size_bytes=1000,
            status=MEDIA_STATUS_READY,
        )
        unrelated_video = MediaAsset(
            uploader_id=admin.id,
            filename="unrelated_vid.mp4",
            file_key="videos/unrelated_vid.mp4",
            bucket="lms-media",
            mime_type="video/mp4",
            file_size_bytes=1000,
            status=MEDIA_STATUS_READY,
        )
        protected_pdf = MediaAsset(
            uploader_id=admin.id,
            filename="syllabus.pdf",
            file_key="docs/syllabus.pdf",
            bucket="lms-media",
            mime_type="application/pdf",
            file_size_bytes=500,
            status=MEDIA_STATUS_READY,
        )
        sec_db.add_all([protected_video, preview_video, unrelated_video, protected_pdf])
        sec_db.flush()

        # Lessons
        lesson_protected = CurriculumLesson(
            section_id=s1.id,
            title="Protected Lesson",
            lesson_type=LESSON_TYPE_VIDEO,
            is_preview=False,
            content={"media_asset_id": str(protected_video.id)},
        )
        lesson_preview = CurriculumLesson(
            section_id=s1.id,
            title="Preview Lesson",
            lesson_type=LESSON_TYPE_VIDEO,
            is_preview=True,
            content={"media_asset_id": str(preview_video.id)},
        )
        sec_db.add_all([lesson_protected, lesson_preview])
        sec_db.flush()

        # Resource for PDF
        res_pdf = LessonResource(
            lesson_id=lesson_protected.id,
            title="syllabus.pdf",
            resource_type=RESOURCE_TYPE_PDF,
            file_url=f"/api/v1/media/{protected_pdf.id}",
        )
        sec_db.add(res_pdf)

        # Enrollment for student in c1
        enr = Enrollment(student_id=student.id, course_id=c1.id, status=ENROLLMENT_STATUS_ACTIVE)
        sec_db.add(enr)
        sec_db.commit()

        return {
            "admin": admin,
            "student": student,
            "non_enrolled": non_enrolled,
            "suspended": suspended,
            "protected_video": protected_video,
            "preview_video": preview_video,
            "unrelated_video": unrelated_video,
            "protected_pdf": protected_pdf,
            "lesson_protected": lesson_protected,
            "lesson_preview": lesson_preview,
            "course": c1,
        }

    def test_missing_lesson_context_is_rejected_for_student(self, sec_client: TestClient, media_fixture):
        """Student cannot access protected media without providing lesson_id context."""
        f = media_fixture
        headers = create_test_auth_headers(f["student"])
        resp = sec_client.post(
            f"/api/v1/media/{f['protected_video'].id}/playback-token",
            json={},  # No lesson_id
            headers=headers,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "LESSON_CONTEXT_REQUIRED"

    def test_preview_lesson_cannot_access_unrelated_protected_media(self, sec_client: TestClient, media_fixture):
        """Supplying a preview lesson_id does NOT grant access to unrelated protected media."""
        f = media_fixture
        headers = create_test_auth_headers(f["non_enrolled"])
        resp = sec_client.post(
            f"/api/v1/media/{f['protected_video'].id}/playback-token",
            json={"lesson_id": str(f["lesson_preview"].id)},  # Forged relation!
            headers=headers,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "MEDIA_NOT_ATTACHED_TO_LESSON"

    def test_preview_lesson_can_access_own_attached_media(self, sec_client: TestClient, media_fixture):
        """Preview lesson genuinely attached media is accessible without enrollment."""
        f = media_fixture
        headers = create_test_auth_headers(f["non_enrolled"])
        resp = sec_client.post(
            f"/api/v1/media/{f['preview_video'].id}/playback-token",
            json={"lesson_id": str(f["lesson_preview"].id)},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["media_id"] == str(f["preview_video"].id)

    def test_non_enrolled_student_is_rejected(self, sec_client: TestClient, media_fixture):
        """Student not enrolled in course cannot access protected media."""
        f = media_fixture
        headers = create_test_auth_headers(f["non_enrolled"])
        resp = sec_client.post(
            f"/api/v1/media/{f['protected_video'].id}/playback-token",
            json={"lesson_id": str(f["lesson_protected"].id)},
            headers=headers,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "ENROLLMENT_REQUIRED"

    def test_active_enrolled_student_can_access(self, sec_client: TestClient, media_fixture):
        """Enrolled student can access protected video with genuine lesson context."""
        f = media_fixture
        headers = create_test_auth_headers(f["student"])
        resp = sec_client.post(
            f"/api/v1/media/{f['protected_video'].id}/playback-token",
            json={"lesson_id": str(f["lesson_protected"].id)},
            headers=headers,
        )
        assert resp.status_code == 200

    def test_suspended_student_is_rejected(self, sec_client: TestClient, media_fixture):
        """Suspended student is rejected with ACCOUNT_SUSPENDED."""
        f = media_fixture
        headers = create_test_auth_headers(f["suspended"])
        resp = sec_client.post(
            f"/api/v1/media/{f['protected_video'].id}/playback-token",
            json={"lesson_id": str(f["lesson_protected"].id)},
            headers=headers,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "ACCOUNT_SUSPENDED"

    def test_protected_pdf_requires_valid_lesson_attachment(self, sec_client: TestClient, media_fixture):
        """Protected PDF stream without lesson context is rejected."""
        f = media_fixture
        headers = create_test_auth_headers(f["student"])
        resp = sec_client.get(
            f"/api/v1/media/{f['protected_pdf'].id}/protected-pdf",  # No lesson_id
            headers=headers,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "LESSON_CONTEXT_REQUIRED"

    def test_staff_access_remains_functional(self, sec_client: TestClient, media_fixture):
        """Elevated roles bypass enrollment and lesson context requirement."""
        f = media_fixture
        headers = create_test_auth_headers(f["admin"], extra_claims={"roles": [ROLE_SUPER_ADMIN]})
        resp = sec_client.post(
            f"/api/v1/media/{f['protected_video'].id}/playback-token",
            headers=headers,
        )
        assert resp.status_code == 200


# =============================================================================
# BUG-003: Razorpay Webhook Secret and Gateway Production Hardening Tests
# =============================================================================

class TestBug003RazorpayProductionHardening:
    """Verifies that Razorpay gateway fails closed in production and rejects placeholder secrets."""

    def test_missing_credentials_in_production_fails_closed(self, monkeypatch):
        """Razorpay credentials missing in production fails configuration/initialization."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
        monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
        monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
        get_settings.cache_clear()

        # Settings instantiation with missing production credentials must fail
        with pytest.raises((RuntimeError, ValueError)):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY="production-secret-must-be-at-least-32-chars-long",
                DATABASE_URL="postgresql+psycopg://user:pass@prod-db.example.com:5432/lms_db",
                CORS_ORIGINS=["https://instructor.com"],
                RAZORPAY_KEY_ID="rzp_live_test",
                # Missing KEY_SECRET and WEBHOOK_SECRET
            )

    def test_placeholder_mock_webhook_secret_rejected_in_production(self):
        """Placeholder/mock webhook secret cannot be used in production."""
        with pytest.raises((RuntimeError, ValueError)):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY="production-secret-must-be-at-least-32-chars-long",
                DATABASE_URL="postgresql+psycopg://user:pass@prod-db.example.com:5432/lms_db",
                CORS_ORIGINS=["https://instructor.com"],
                RAZORPAY_KEY_ID="rzp_live_valid123",
                RAZORPAY_KEY_SECRET="valid_production_secret_key_123",
                RAZORPAY_WEBHOOK_SECRET="mock_webhook_secret_for_dev_test",  # Insecure!
            )

    def test_mock_gateway_prohibited_in_production(self):
        """Mock order creation raises RuntimeError in production."""
        from unittest.mock import PropertyMock, patch
        client = RazorpayClient()
        client.settings = MagicMock(ENVIRONMENT="production", is_testing=False)

        with patch.object(RazorpayClient, "is_live_configured", new_callable=PropertyMock, return_value=False):
            with pytest.raises(RuntimeError, match="Mock payment order creation is strictly prohibited"):
                client.create_order(amount_inr=1000)

    def test_valid_webhook_signature_accepted(self):
        """Valid HMAC-SHA256 signature is accepted."""
        client = RazorpayClient()
        secret = "secret_for_test_12345"
        client.webhook_secret = secret
        raw_body = b'{"event":"payment.captured","payload":{}}'
        sig = compute_razorpay_signature(raw_body, secret)
        assert client.verify_webhook_signature(raw_body, sig) is True

    def test_tampered_request_body_rejected(self):
        """Modified request body fails signature verification."""
        client = RazorpayClient()
        secret = "secret_for_test_12345"
        client.webhook_secret = secret
        raw_body = b'{"event":"payment.captured","amount":500}'
        tampered_body = b'{"event":"payment.captured","amount":50000}'
        sig = compute_razorpay_signature(raw_body, secret)
        assert client.verify_webhook_signature(tampered_body, sig) is False


# =============================================================================
# BUG-014: Staff Onboarding JWT Session Binding Regression Tests
# =============================================================================

class TestBug014StaffOnboardingSessionBinding:
    """Verifies that all access tokens are bound to active server-side sessions."""

    def test_token_without_session_id_rejected(self, sec_client: TestClient, sec_db: Session):
        """Access token without session_id claim is rejected with 401 SESSION_REQUIRED."""
        user = User(
            email="victim@lms.local",
            full_name="Victim User",
            password_hash=hash_password("Pass1234!@#$"),
            is_verified=True,
            is_active=True,
        )
        sec_db.add(user)
        sec_db.commit()

        # Token minted WITHOUT session_id
        token = create_access_token(
            subject=str(user.id),
            extra_claims={"roles": [ROLE_STUDENT]},  # Missing session_id!
        )
        resp = sec_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "SESSION_REQUIRED"

    def test_unknown_session_rejected(self, sec_client: TestClient, sec_db: Session):
        """Token with unknown session_id (not in database) is rejected with 401 SESSION_NOT_FOUND."""
        user = User(
            email="nosess@lms.local",
            full_name="No Session User",
            password_hash=hash_password("Pass1234!@#$"),
            is_verified=True,
            is_active=True,
        )
        sec_db.add(user)
        sec_db.commit()

        fake_session_id = uuid.uuid4()
        token = create_access_token(
            subject=str(user.id),
            extra_claims={"roles": [ROLE_STUDENT], "session_id": str(fake_session_id)},
        )
        resp = sec_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "SESSION_NOT_FOUND"

    def test_revoked_session_rejected(self, sec_client: TestClient, sec_db: Session):
        """Token referencing a revoked session is rejected with 401 SESSION_REVOKED."""
        user = User(
            email="revoked@lms.local",
            full_name="Revoked User",
            password_hash=hash_password("Pass1234!@#$"),
            is_verified=True,
            is_active=True,
        )
        sec_db.add(user)
        sec_db.flush()

        sess = AuthSession(
            user_id=user.id,
            session_token_hash=hash_token(generate_secure_token(32)),
            status=SESSION_STATUS_REVOKED,
            expires_at=utc_now() + timedelta(days=1),
        )
        sec_db.add(sess)
        sec_db.commit()

        token = create_access_token(
            subject=str(user.id),
            extra_claims={"roles": [ROLE_STUDENT], "session_id": str(sess.id)},
        )
        resp = sec_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "SESSION_REVOKED"

    def test_session_owned_by_another_user_rejected(self, sec_client: TestClient, sec_db: Session):
        """Token with session_id belonging to another user is rejected with SESSION_USER_MISMATCH."""
        user_alice = User(
            email="alice@lms.local",
            full_name="Alice",
            password_hash=hash_password("Pass1234!@#$"),
            is_verified=True,
            is_active=True,
        )
        user_bob = User(
            email="bob@lms.local",
            full_name="Bob",
            password_hash=hash_password("Pass1234!@#$"),
            is_verified=True,
            is_active=True,
        )
        sec_db.add_all([user_alice, user_bob])
        sec_db.flush()

        # Session belongs to Bob
        bob_session = AuthSession(
            user_id=user_bob.id,
            session_token_hash=hash_token(generate_secure_token(32)),
            status=SESSION_STATUS_ACTIVE,
            expires_at=utc_now() + timedelta(days=1),
        )
        sec_db.add(bob_session)
        sec_db.commit()

        # Alice crafts token with Bob's session_id
        alice_token = create_access_token(
            subject=str(user_alice.id),
            extra_claims={"roles": [ROLE_STUDENT], "session_id": str(bob_session.id)},
        )
        resp = sec_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {alice_token}"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "SESSION_USER_MISMATCH"

    def test_staff_onboarding_token_contains_valid_session(self, sec_client: TestClient, sec_db: Session):
        """Staff onboarding claim issues an access token with a valid session_id that works immediately."""
        admin = User(
            email="admin_inviter@lms.local",
            full_name="Admin Inviter",
            password_hash=hash_password("AdminPass1234!"),
            is_verified=True,
            is_active=True,
        )
        sec_db.add(admin)
        sec_db.flush()
        admin.user_roles.append(UserRole(role_id=ROLE_ADMIN, user_id=admin.id))
        sec_db.commit()

        headers = create_test_auth_headers(admin, extra_claims={"roles": [ROLE_ADMIN]})
        invite_resp = sec_client.post(
            "/api/v1/users/staff/invite",
            json={"email": "onboarded_ta@example.com", "full_name": "Onboarded TA", "role": "STAFF"},
            headers=headers,
        )
        assert invite_resp.status_code == 201
        assert "token" not in invite_resp.json()

        # Retrieve raw invitation token from staged NotificationOutbox
        outbox_item = sec_db.query(NotificationOutbox).filter(
            NotificationOutbox.recipient == "onboarded_ta@example.com"
        ).first()
        assert outbox_item is not None
        raw_token = outbox_item.payload["invitation_token"]

        # Claim onboarding
        claim_resp = sec_client.post(
            "/api/v1/auth/onboarding/claim",
            json={"token": raw_token, "password": "SecurePassword1234#"},
        )
        assert claim_resp.status_code == 200
        access_token = claim_resp.json()["access_token"]

        # Inspect token payload: session_id MUST be present
        decoded = jwt.decode(access_token, options={"verify_signature": False})
        assert "session_id" in decoded
        session_uuid = uuid.UUID(decoded["session_id"])

        # Verify session exists in DB and is active
        sess = sec_db.query(AuthSession).filter(AuthSession.id == session_uuid).one()
        assert sess.status == SESSION_STATUS_ACTIVE
        assert str(sess.user_id) == decoded["sub"]

        # Call /me with this access token: MUST succeed with 200 OK
        me_resp = sec_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == "onboarded_ta@example.com"
