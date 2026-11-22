"""Unit tests for Gmail SMTP delivery in OutboxWorker.

Architecture Specifications:
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK008)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-012)
"""

import email
import io
import smtplib
import ssl
from unittest.mock import MagicMock
import urllib.error
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.models.notification import OUTBOX_CHANNEL_EMAIL, NotificationOutbox
from app.workers.outbox_worker import (
    _format_email_html,
    _format_email_text,
    _send_smtp_email,
    default_outbox_dispatcher,
    main as outbox_main,
)


# =============================================================================
# Helper Fixtures & Mock Objects
# =============================================================================

@pytest.fixture
def sample_verify_email_event():
    """Provides a sample AUTH_VERIFY_EMAIL outbox notification event."""
    return NotificationOutbox(
        channel=OUTBOX_CHANNEL_EMAIL,
        event_type="EMAIL_VERIFICATION",
        recipient="alice.student@example.com",
        subject="Verify your LMS account email",
        payload={
            "verification_url": "https://courses.example.com/verify-email?token=cryptographic_token_abc123",
            "token": "cryptographic_token_abc123",
        },
    )


@pytest.fixture
def sample_smtp_settings():
    """Provides valid development SMTP settings for Gmail."""
    return Settings(
        ENVIRONMENT="development",
        DEBUG=True,
        EMAIL_PROVIDER="smtp",
        EMAIL_FROM="instructor@gmail.com",
        EMAIL_FROM_NAME="Expert Instructor",
        SMTP_HOST="smtp.gmail.com",
        SMTP_PORT=587,
        SMTP_USERNAME="instructor@gmail.com",
        SMTP_PASSWORD=SecretStr("abcd-efgh-ijkl-mnop"),
        SMTP_USE_TLS=True,
        SMTP_TIMEOUT_SECONDS=10,
    )


# =============================================================================
# 1. SMTP Configuration Validation Tests
# =============================================================================

class TestSMTPConfigurationValidation:
    """Verifies SMTP settings declaration, defaults, and SecretStr masking."""

    def test_smtp_configuration_defaults(self):
        """Settings must declare Gmail-compatible defaults for SMTP."""
        settings = Settings(_env_file=None)
        assert settings.SMTP_HOST == "smtp.gmail.com"
        assert settings.SMTP_PORT == 587
        assert settings.SMTP_USE_TLS is True
        assert settings.SMTP_TIMEOUT_SECONDS == 10
        assert settings.SMTP_USERNAME is None
        assert settings.SMTP_PASSWORD is None

    def test_smtp_password_secret_str_masking(self):
        """SMTP_PASSWORD must be wrapped in SecretStr and never leaked in repr or str."""
        raw_app_password = "secret-app-password-1234"
        settings = Settings(SMTP_PASSWORD=SecretStr(raw_app_password))

        assert isinstance(settings.SMTP_PASSWORD, SecretStr)
        assert raw_app_password not in str(settings.SMTP_PASSWORD)
        assert raw_app_password not in repr(settings.SMTP_PASSWORD)
        assert settings.SMTP_PASSWORD.get_secret_value() == raw_app_password


# =============================================================================
# 2. Successful SMTP Authentication & Delivery Tests
# =============================================================================

class TestSMTPAthenticationAndDelivery:
    """Verifies successful SMTP handshake, STARTTLS, authentication, and MIME dispatch."""

    @pytest.mark.asyncio
    async def test_successful_smtp_dispatch_lifecycle(
        self, sample_verify_email_event, sample_smtp_settings, monkeypatch
    ):
        """Worker establishes connection, negotiates STARTTLS, authenticates, and dispatches email."""
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: sample_smtp_settings)

        mock_server = MagicMock()
        mock_server.__enter__.return_value = mock_server

        smtp_init_calls = []

        def mock_smtp_init(host, port, timeout):
            smtp_init_calls.append({"host": host, "port": port, "timeout": timeout})
            return mock_server

        monkeypatch.setattr("smtplib.SMTP", mock_smtp_init)

        await default_outbox_dispatcher(sample_verify_email_event)

        # 1. Verify connection parameters
        assert len(smtp_init_calls) == 1
        assert smtp_init_calls[0]["host"] == "smtp.gmail.com"
        assert smtp_init_calls[0]["port"] == 587
        assert smtp_init_calls[0]["timeout"] == 10

        # 2. Verify EHLO called before and after STARTTLS
        assert mock_server.ehlo.call_count >= 2

        # 3. Verify STARTTLS invoked with secure SSL context
        assert mock_server.starttls.call_count == 1
        starttls_kwargs = mock_server.starttls.call_args[1]
        assert "context" in starttls_kwargs
        assert isinstance(starttls_kwargs["context"], ssl.SSLContext)

        # 4. Verify login called with credentials
        mock_server.login.assert_called_once_with("instructor@gmail.com", "abcd-efgh-ijkl-mnop")

        # 5. Verify send_message called
        assert mock_server.send_message.call_count == 1
        call_args, call_kwargs = mock_server.send_message.call_args
        sent_msg = call_args[0]

        assert call_kwargs.get("from_addr") == "instructor@gmail.com"
        assert call_kwargs.get("to_addrs") == ["alice.student@example.com"]

        # 6. Verify MIME headers and multipart content
        assert sent_msg["To"] == "alice.student@example.com"
        assert sent_msg["From"] == "Expert Instructor <instructor@gmail.com>"
        assert sent_msg["Subject"] == "Verify your LMS account email"
        assert sent_msg["Date"] is not None
        assert sent_msg["Message-ID"] is not None

        expected_body = _format_email_text(sample_verify_email_event)
        expected_html = _format_email_html(sample_verify_email_event)
        assert sent_msg.is_multipart() is True
        parts = sent_msg.get_payload()
        assert len(parts) == 2
        assert parts[0].get_content_type() == "text/plain"
        assert parts[0].get_payload(decode=True).decode("utf-8") == expected_body
        assert parts[1].get_content_type() == "text/html"
        assert parts[1].get_payload(decode=True).decode("utf-8") == expected_html
        assert "https://courses.example.com/verify-email?token=" in expected_body
        assert "https://courses.example.com/verify-email?token=" in expected_html
        assert "#006B60" in expected_html

    @pytest.mark.asyncio
    async def test_smtp_plain_text_fallback_when_no_html(
        self, sample_smtp_settings, monkeypatch
    ):
        """When body_html is None, _send_smtp_email creates a single-part plain-text MIME message."""
        mock_server = MagicMock()
        mock_server.__enter__.return_value = mock_server
        monkeypatch.setattr("smtplib.SMTP", lambda host, port, timeout: mock_server)

        _send_smtp_email(
            settings=sample_smtp_settings,
            from_addr="instructor@gmail.com",
            recipient="bob@example.com",
            subject="Plain Subject",
            body_text="Plain message text.",
            body_html=None,
        )

        assert mock_server.send_message.call_count == 1
        call_args, _ = mock_server.send_message.call_args
        sent_msg = call_args[0]
        assert sent_msg.is_multipart() is False
        assert sent_msg.get_payload(decode=True).decode("utf-8") == "Plain message text."

    @pytest.mark.asyncio
    async def test_smtp_uses_certifi_ca_bundle(
        self, sample_smtp_settings, monkeypatch
    ):
        """_send_smtp_email passes certifi CA bundle to ssl.create_default_context when available."""
        mock_server = MagicMock()
        mock_server.__enter__.return_value = mock_server
        monkeypatch.setattr("smtplib.SMTP", lambda host, port, timeout: mock_server)

        contexts_created = []
        real_create_context = ssl.create_default_context

        def mock_create_context(*args, **kwargs):
            contexts_created.append(kwargs)
            return real_create_context(*args, **kwargs)

        monkeypatch.setattr("ssl.create_default_context", mock_create_context)

        _send_smtp_email(
            settings=sample_smtp_settings,
            from_addr="instructor@gmail.com",
            recipient="test@example.com",
            subject="TLS Test",
            body_text="TLS Test Body",
        )

        assert len(contexts_created) >= 1
        assert "cafile" in contexts_created[0]
        import certifi
        assert contexts_created[0]["cafile"] == certifi.where()

    @pytest.mark.asyncio
    async def test_format_email_html_structure(self, sample_verify_email_event):
        """_format_email_html produces styled HTML with Deep Teal brand and verification URL."""
        html = _format_email_html(sample_verify_email_event)
        assert html is not None
        assert "<!DOCTYPE html>" in html
        assert "#006B60" in html
        assert "Verify Your Email Address" in html
        assert "https://courses.example.com/verify-email?token=" in html

    def test_outbox_cli_main_once_flag(self, monkeypatch):
        """outbox_worker main() CLI parses --once flag and executes single cycle."""
        import sys
        from unittest.mock import AsyncMock

        monkeypatch.setattr(sys, "argv", ["outbox_worker.py", "--once", "--batch-size", "10"])
        mock_run_once = AsyncMock(return_value=3)
        monkeypatch.setattr("app.workers.outbox_worker.OutboxWorker.run_once", mock_run_once)

        outbox_main()
        mock_run_once.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_smtp_without_tls_when_disabled(
        self, sample_verify_email_event, monkeypatch
    ):
        """When SMTP_USE_TLS=False, starttls is not invoked."""
        no_tls_settings = Settings(
            EMAIL_PROVIDER="smtp",
            SMTP_HOST="localhost",
            SMTP_PORT=1025,
            SMTP_USERNAME="test_user",
            SMTP_PASSWORD=SecretStr("test_pass"),
            SMTP_USE_TLS=False,
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: no_tls_settings)

        mock_server = MagicMock()
        mock_server.__enter__.return_value = mock_server
        monkeypatch.setattr("smtplib.SMTP", lambda host, port, timeout: mock_server)

        await default_outbox_dispatcher(sample_verify_email_event)

        assert mock_server.starttls.call_count == 0
        mock_server.login.assert_called_once_with("test_user", "test_pass")
        assert mock_server.send_message.call_count == 1


# =============================================================================
# 3. SMTP Failure & Error Handling Tests
# =============================================================================

class TestSMTPErrorHandling:
    """Verifies that SMTP authentication, connection, and credential errors raise clean exceptions."""

    @pytest.mark.asyncio
    async def test_smtp_authentication_failure_raises_and_masks_password(
        self, sample_verify_email_event, sample_smtp_settings, monkeypatch
    ):
        """Authentication error raises RuntimeError without leaking password."""
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: sample_smtp_settings)

        mock_server = MagicMock()
        mock_server.__enter__.return_value = mock_server
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"5.7.8 Authentication credentials invalid")
        monkeypatch.setattr("smtplib.SMTP", lambda host, port, timeout: mock_server)

        with pytest.raises(RuntimeError) as exc_info:
            await default_outbox_dispatcher(sample_verify_email_event)

        assert "SMTP authentication failed" in str(exc_info.value)
        # Verify secret app password is NOT in the error message
        assert "abcd-efgh-ijkl-mnop" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_smtp_connection_failure_raises_runtime_error(
        self, sample_verify_email_event, sample_smtp_settings, monkeypatch
    ):
        """Connection error during SMTP initialization raises RuntimeError."""
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: sample_smtp_settings)

        def mock_connection_failure(*args, **kwargs):
            raise smtplib.SMTPConnectError(421, "Cannot connect to SMTP server")

        monkeypatch.setattr("smtplib.SMTP", mock_connection_failure)

        with pytest.raises(RuntimeError) as exc_info:
            await default_outbox_dispatcher(sample_verify_email_event)

        assert "SMTP connection error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_smtp_network_timeout_raises_runtime_error(
        self, sample_verify_email_event, sample_smtp_settings, monkeypatch
    ):
        """Network timeout during socket connection raises RuntimeError."""
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: sample_smtp_settings)

        def mock_timeout(*args, **kwargs):
            raise TimeoutError("Connection timed out after 10s")

        monkeypatch.setattr("smtplib.SMTP", mock_timeout)

        with pytest.raises(RuntimeError) as exc_info:
            await default_outbox_dispatcher(sample_verify_email_event)

        assert "SMTP network error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_smtp_credentials_raises_runtime_error(
        self, sample_verify_email_event, monkeypatch
    ):
        """Missing username or password when EMAIL_PROVIDER='smtp' raises RuntimeError."""
        missing_creds_settings = Settings(
            EMAIL_PROVIDER="smtp",
            SMTP_HOST="smtp.gmail.com",
            SMTP_PORT=587,
            SMTP_USERNAME=None,
            SMTP_PASSWORD=None,
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: missing_creds_settings)

        with pytest.raises(RuntimeError) as exc_info:
            await default_outbox_dispatcher(sample_verify_email_event)

        assert "missing SMTP_USERNAME or SMTP_PASSWORD" in str(exc_info.value)


# =============================================================================
# 4. Production SMTP Validation Tests
# =============================================================================

class TestProductionSMTPValidation:
    """Verifies that production guards strictly validate SMTP credentials and block placeholders."""

    PROD_COMMON_SETTINGS = {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "SECRET_KEY": SecretStr("68f9a2b8e4c7d1e0f3b5a6c9d8e7f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8"),
        "DATABASE_URL": "postgresql+psycopg://user:p@prod-db.internal:5432/lms_prod",
        "CORS_ORIGINS": ["https://courses.instructor.com"],
        "SESSION_COOKIE_SECURE": True,
        "SESSION_COOKIE_NAME": "__Host-session_id",
        "RAZORPAY_KEY_ID": "rzp_live_real_id_12345",
        "RAZORPAY_KEY_SECRET": SecretStr("real_secret_live_12345"),
        "RAZORPAY_WEBHOOK_SECRET": SecretStr("real_wh_secret_live_12345"),
        "BACKEND_URL": "https://api.instructor.com",
        "FRONTEND_URL": "https://courses.instructor.com",
    }

    @pytest.mark.asyncio
    async def test_production_allows_valid_smtp_configuration(
        self, sample_verify_email_event, monkeypatch
    ):
        """Production permits EMAIL_PROVIDER='smtp' with valid live credentials."""
        prod_smtp_settings = Settings(
            **self.PROD_COMMON_SETTINGS,
            EMAIL_PROVIDER="smtp",
            SMTP_HOST="smtp.gmail.com",
            SMTP_PORT=587,
            SMTP_USERNAME="instructor@gmail.com",
            SMTP_PASSWORD=SecretStr("live-google-app-password"),
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: prod_smtp_settings)

        mock_server = MagicMock()
        mock_server.__enter__.return_value = mock_server
        monkeypatch.setattr("smtplib.SMTP", lambda host, port, timeout: mock_server)

        # Must succeed without production guard rejection
        await default_outbox_dispatcher(sample_verify_email_event)
        assert mock_server.send_message.call_count == 1

    @pytest.mark.asyncio
    async def test_production_rejects_missing_smtp_credentials(
        self, sample_verify_email_event, monkeypatch
    ):
        """Production rejects EMAIL_PROVIDER='smtp' when credentials are missing."""
        prod_settings = Settings(
            **self.PROD_COMMON_SETTINGS,
            EMAIL_PROVIDER="smtp",
            SMTP_USERNAME=None,
            SMTP_PASSWORD=None,
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: prod_settings)

        with pytest.raises(RuntimeError) as exc_info:
            await default_outbox_dispatcher(sample_verify_email_event)

        assert "Production email delivery blocked" in str(exc_info.value)
        assert "missing SMTP_HOST, SMTP_PORT, SMTP_USERNAME, or SMTP_PASSWORD" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_production_rejects_placeholder_smtp_password(
        self, sample_verify_email_event, monkeypatch
    ):
        """Production rejects placeholder or mock SMTP passwords."""
        prod_settings = Settings(
            **self.PROD_COMMON_SETTINGS,
            EMAIL_PROVIDER="smtp",
            SMTP_USERNAME="instructor@gmail.com",
            SMTP_PASSWORD=SecretStr("mock_password_placeholder"),
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: prod_settings)

        with pytest.raises(RuntimeError) as exc_info:
            await default_outbox_dispatcher(sample_verify_email_event)

        assert "placeholder or mock SMTP_PASSWORD" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_production_prohibits_console_provider(
        self, sample_verify_email_event, monkeypatch
    ):
        """Production strictly prohibits console provider."""
        prod_settings = Settings(
            **self.PROD_COMMON_SETTINGS,
            EMAIL_PROVIDER="console",
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: prod_settings)

        with pytest.raises(RuntimeError) as exc_info:
            await default_outbox_dispatcher(sample_verify_email_event)

        assert "Production email delivery blocked: EMAIL_PROVIDER 'console' is prohibited in production" in str(exc_info.value)


# =============================================================================
# 5. Existing Provider Regressions (Console, Resend, SendGrid)
# =============================================================================

class TestExistingProviderRegressions:
    """Verifies that console, Resend, and SendGrid providers continue working without regression."""

    @pytest.mark.asyncio
    async def test_console_provider_dispatches_cleanly(
        self, sample_verify_email_event, monkeypatch
    ):
        """In non-production, console provider logs and returns without network calls."""
        console_settings = Settings(
            ENVIRONMENT="development",
            EMAIL_PROVIDER="console",
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: console_settings)

        # Must complete without error and without touching smtplib or urllib
        await default_outbox_dispatcher(sample_verify_email_event)

    @pytest.mark.asyncio
    async def test_resend_provider_regression_success(
        self, sample_verify_email_event, monkeypatch
    ):
        """Resend provider continues to function and format requests correctly."""
        resend_settings = Settings(
            EMAIL_PROVIDER="resend",
            EMAIL_API_KEY=SecretStr("re_valid_api_key_12345"),
            EMAIL_FROM="courses@example.com",
            EMAIL_FROM_NAME="LMS Instructor",
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: resend_settings)

        class MockResponse:
            def getcode(self):
                return 200

            def read(self):
                return b'{"id": "res_sample_abc123"}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: MockResponse())

        await default_outbox_dispatcher(sample_verify_email_event)

    @pytest.mark.asyncio
    async def test_sendgrid_provider_regression_success(
        self, sample_verify_email_event, monkeypatch
    ):
        """SendGrid provider continues to function and accept HTTP 202."""
        sg_settings = Settings(
            EMAIL_PROVIDER="sendgrid",
            EMAIL_API_KEY=SecretStr("SG.valid_api_key_12345"),
            EMAIL_FROM="courses@example.com",
            EMAIL_FROM_NAME="LMS Instructor",
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: sg_settings)

        class MockResponse:
            def getcode(self):
                return 202

            def read(self):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: MockResponse())

        await default_outbox_dispatcher(sample_verify_email_event)
