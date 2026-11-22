"""Unit and integration tests for Structured JSON Logging and Request ID Middleware.

Follows the backend architecture defined in:
- docs/backend/01-SYSTEM-ARCHITECTURE.md
- docs/backend/06-API-ARCHITECTURE.md
- docs/backend/18-SECURITY-ARCHITECTURE.md (A09 Logging Failures)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK005)

Tests:
1. Request ID context lifecycle (get, set, reset, contextvars isolation).
2. Client request ID validation & sanitization (CRLF, XSS, length, regex).
3. Sensitive information redaction (passwords, tokens, bearer headers, cookies, payment cards).
4. JSONFormatter structure (valid JSON, ISO 8601 UTC timestamp, level, message, request_id, exc_info, extra).
5. RequestIDMiddleware integration with FastAPI (headers, state, context propagation, error handling, CORS).
6. Concurrent request isolation (zero context bleed between async tasks).
7. Regression verification for all health endpoints (/healthz, /api/v1/health).
"""

from __future__ import annotations

import asyncio
import datetime
import io
import json
import logging
import re
import sys
from typing import Any
from unittest.mock import MagicMock
import uuid

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.core.logging import (
    JSONFormatter,
    RequestIDFilter,
    RequestIDMiddleware,
    get_request_id,
    is_valid_request_id,
    redact_sensitive_data,
    redact_sensitive_text,
    reset_request_id,
    set_request_id,
    setup_logging,
    validate_or_generate_request_id,
)
from app.main import create_app


# =============================================================================
# 1. Request ID Context Lifecycle Tests
# =============================================================================

class TestRequestIDContextLifecycle:
    """Verifies get, set, reset, and contextvar safety."""

    def test_get_request_id_default_is_none(self):
        """Outside an active request, get_request_id() must return None."""
        assert get_request_id() is None

    def test_set_and_reset_request_id(self):
        """Setting request ID updates context, and reset restores previous value."""
        initial = get_request_id()
        assert initial is None

        test_uuid = str(uuid.uuid4())
        token = set_request_id(test_uuid)
        assert get_request_id() == test_uuid

        reset_request_id(token)
        assert get_request_id() is None

    def test_nested_set_and_reset(self):
        """Nested context token sets and resets properly restore parent contexts."""
        token1 = set_request_id("parent-id")
        assert get_request_id() == "parent-id"

        token2 = set_request_id("child-id")
        assert get_request_id() == "child-id"

        reset_request_id(token2)
        assert get_request_id() == "parent-id"

        reset_request_id(token1)
        assert get_request_id() is None

    @pytest.mark.asyncio
    async def test_async_task_context_isolation(self):
        """Async tasks executing concurrently must maintain isolated request IDs."""
        results: list[tuple[str, bool, str | None]] = []

        async def worker(worker_name: str, assigned_id: str):
            token = set_request_id(assigned_id)
            try:
                await asyncio.sleep(0.01)
                current = get_request_id()
                results.append((worker_name, current == assigned_id, current))
            finally:
                reset_request_id(token)

        tasks = [
            worker("worker-1", "uuid-1111-1111-1111"),
            worker("worker-2", "uuid-2222-2222-2222"),
            worker("worker-3", "uuid-3333-3333-3333"),
        ]
        await asyncio.gather(*tasks)

        assert len(results) == 3
        for name, matches, current in results:
            assert matches is True, f"Context leaked in {name}: got {current}"

        assert get_request_id() is None


# =============================================================================
# 2. Client Request ID Validation & Sanitization Tests
# =============================================================================

class TestRequestIDValidation:
    """Verifies that client-supplied request IDs are validated against injection attacks."""

    def test_validate_generates_fresh_uuid_when_none(self):
        """When input is None, a valid UUIDv4 must be generated."""
        req_id = validate_or_generate_request_id(None)
        assert isinstance(req_id, str)
        assert uuid.UUID(req_id).version == 4

    def test_validate_generates_fresh_uuid_when_empty_or_whitespace(self):
        """When input is empty or whitespace, a valid UUIDv4 must be generated."""
        assert uuid.UUID(validate_or_generate_request_id("")).version == 4
        assert uuid.UUID(validate_or_generate_request_id("   ")).version == 4

    def test_validate_accepts_valid_uuid(self):
        """A valid RFC 4122 UUID must be accepted as-is."""
        valid_uuid = str(uuid.uuid4())
        assert validate_or_generate_request_id(valid_uuid) == valid_uuid

    def test_validate_accepts_valid_alphanumeric_custom_id(self):
        """Alphanumeric IDs with hyphens/underscores (8-64 chars) must be accepted."""
        custom_id = "req_trace_2026_test-client-001"
        assert validate_or_generate_request_id(custom_id) == custom_id

    def test_validate_rejects_crlf_injection(self):
        """CRLF injection attempts must be rejected and replaced with fresh UUID."""
        malicious = "legit-id\r\nSet-Cookie: evil=session\r\n"
        sanitized = validate_or_generate_request_id(malicious)
        assert sanitized != malicious
        assert uuid.UUID(sanitized).version == 4

    def test_validate_rejects_html_and_script_injection(self):
        """HTML / script tags must be rejected."""
        malicious = "<script>alert(1)</script>"
        sanitized = validate_or_generate_request_id(malicious)
        assert sanitized != malicious
        assert uuid.UUID(sanitized).version == 4

    def test_validate_rejects_sql_characters(self):
        """SQL injection special characters must be rejected."""
        malicious = "'; DROP TABLE users; --"
        sanitized = validate_or_generate_request_id(malicious)
        assert sanitized != malicious
        assert uuid.UUID(sanitized).version == 4

    def test_validate_rejects_too_short_string(self):
        """Strings shorter than 8 characters must be rejected."""
        short_id = "abc-12"  # 6 chars
        assert is_valid_request_id(short_id) is False
        assert uuid.UUID(validate_or_generate_request_id(short_id)).version == 4

    def test_validate_rejects_oversized_string(self):
        """Strings longer than 64 characters must be rejected."""
        oversized = "a" * 65
        assert is_valid_request_id(oversized) is False
        assert uuid.UUID(validate_or_generate_request_id(oversized)).version == 4


# =============================================================================
# 3. Sensitive Data Redaction Tests
# =============================================================================

class TestSensitiveDataRedaction:
    """Verifies that secrets, tokens, passwords, cookies, and payment cards are redacted."""

    def test_redact_bearer_token_in_text(self):
        """Bearer tokens in free-form log text must be replaced with [REDACTED]."""
        raw = "Header Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
        redacted = redact_sensitive_text(raw)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz" not in redacted
        assert "Bearer [REDACTED]" in redacted

    def test_redact_key_value_pairs_in_text(self):
        """Sensitive key-values (password, token, cookie) in strings must be redacted."""
        raw = "Auth failed for user alice with password=supersecret and token: my_secret_token_123"
        redacted = redact_sensitive_text(raw)
        assert "supersecret" not in redacted
        assert "my_secret_token_123" not in redacted
        assert "password=[REDACTED]" in redacted
        assert "token: [REDACTED]" in redacted

    def test_redact_dictionary_sensitive_keys(self):
        """Dictionary keys matching sensitive names must have values replaced by [REDACTED]."""
        data = {
            "username": "instructor",
            "password": "ClearTextPassword!",
            "secret_key": "topsecret",
            "access_token": "token123",
            "cookie": "session_cookie_val",
            "card_number": "4111111111111111",
            "cvv": "123",
            "nested": {
                "api_key": "resend_api_key_secret",
                "normal_field": "public_data",
            },
        }
        sanitized = redact_sensitive_data(data)

        assert sanitized["username"] == "instructor"
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["secret_key"] == "[REDACTED]"
        assert sanitized["access_token"] == "[REDACTED]"
        assert sanitized["cookie"] == "[REDACTED]"
        assert sanitized["card_number"] == "[REDACTED]"
        assert sanitized["cvv"] == "[REDACTED]"
        assert sanitized["nested"]["api_key"] == "[REDACTED]"
        assert sanitized["nested"]["normal_field"] == "public_data"

    def test_redact_nested_lists(self):
        """Sensitive fields inside lists of dictionaries must be sanitized recursively."""
        items = [
            {"token": "secret_abc", "id": 1},
            {"token": "secret_xyz", "id": 2},
        ]
        sanitized = redact_sensitive_data(items)
        assert sanitized[0]["token"] == "[REDACTED]"
        assert sanitized[0]["id"] == 1
        assert sanitized[1]["token"] == "[REDACTED]"
        assert sanitized[1]["id"] == 2

    def test_redact_all_sensitive_audit_categories(self):
        """Verifies redaction of all 13 sensitive categories required by audit specifications."""
        # 1. Test dictionary keys
        audit_dict = {
            "password": "cleartext_password",
            "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$somehash",
            "authorization": "Bearer eyJhbGciOi...",
            "access_token": "at_xyz123",
            "refresh_token": "rt_xyz456",
            "session_token": "sess_xyz789",
            "cookie": "__Host-lms_session=abc",
            "api_key": "live_api_key_val",
            "client_secret": "cs_secret_val",
            "webhook_secret": "whsec_val",
            "card_number": "4111222233334444",
            "cvv": "123",
            "cvc": "456",
            "safe_field": "visible_data",
        }
        sanitized = redact_sensitive_data(audit_dict)
        assert sanitized["safe_field"] == "visible_data"
        for key in audit_dict:
            if key != "safe_field":
                assert sanitized[key] == "[REDACTED]", f"Key {key} was not redacted in dict!"

        # 2. Test free-form text strings
        text_samples = [
            ("password=plainsecret123", "password=[REDACTED]"),
            ("password_hash=$argon2id$hash", "password_hash=[REDACTED]"),
            ("authorization: Bearer jwt_val_here", "authorization: Bearer [REDACTED]"),
            ("Token: Bearer standalone_jwt_token", "Bearer [REDACTED]"),
            ("access_token=at_secret_123", "access_token=[REDACTED]"),
            ("refresh_token=rt_secret_456", "refresh_token=[REDACTED]"),
            ("session_token=sess_token_789", "session_token=[REDACTED]"),
            ("cookie: session_id=abc_cookie", "cookie: [REDACTED]"),
            ("api_key=ak_secret_key", "api_key=[REDACTED]"),
            ("client_secret=cs_secret_val", "client_secret=[REDACTED]"),
            ("webhook_secret=whsec_xyz", "webhook_secret=[REDACTED]"),
            ("card_number: 4111222233334444", "card_number: [REDACTED]"),
            ("cvv: 999 and cvc=888", "cvv: [REDACTED] and cvc=[REDACTED]"),
        ]
        for raw, expected_substring in text_samples:
            redacted = redact_sensitive_text(raw)
            assert expected_substring in redacted, f"Failed redacting '{raw}': got '{redacted}'"


# =============================================================================
# 4. JSON Log Formatter Tests
# =============================================================================

class TestJSONFormatter:
    """Verifies that JSONFormatter produces valid structured JSON logs matching specifications."""

    def test_formatter_outputs_valid_json(self):
        """Formatter output must be deserializable JSON."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="app.core.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="User registration initiated",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_formatter_required_fields_present(self):
        """Output must include timestamp, level, logger, message, and request_id."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="app.test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=42,
            msg="Resource threshold warning",
            args=(),
            exc_info=None,
        )
        record.funcName = "check_threshold"
        record.module = "test"

        output = formatter.format(record)
        data = json.loads(output)

        assert "timestamp" in data
        assert data["level"] == "WARNING"
        assert data["logger"] == "app.test"
        assert data["message"] == "Resource threshold warning"
        assert "request_id" in data
        assert data["module"] == "test"
        assert data["func_name"] == "check_threshold"
        assert data["line"] == 42

    def test_formatter_iso_8601_utc_timestamp(self):
        """Timestamp must be a valid ISO 8601 UTC string."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        # Parse timestamp back to datetime
        ts = datetime.datetime.fromisoformat(data["timestamp"])
        assert ts.tzinfo is not None

    def test_formatter_captures_active_request_id(self):
        """Formatter must read request_id from contextvar or record attribute."""
        formatter = JSONFormatter()
        test_uuid = str(uuid.uuid4())
        token = set_request_id(test_uuid)

        try:
            record = logging.LogRecord(
                name="app.test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Operation under request",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            data = json.loads(output)
            assert data["request_id"] == test_uuid
        finally:
            reset_request_id(token)

    def test_formatter_handles_exception_safely(self):
        """Exceptions in exc_info must be formatted into structured dictionary."""
        formatter = JSONFormatter()
        try:
            raise ValueError("Test internal division by zero error with password=mysecret")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="app.test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Calculation failed",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert "exception" in data
        assert data["exception"]["type"] == "ValueError"
        assert "password=[REDACTED]" in data["exception"]["message"]
        assert "traceback" in data["exception"]

    def test_formatter_includes_and_sanitizes_extras(self):
        """Custom extras passed to logger must appear under extra with sensitive values redacted."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Order paid",
            args=(),
            exc_info=None,
        )
        record.order_id = "ord_123"
        record.card_number = "4111222233334444"
        record.amount_cents = 5000

        output = formatter.format(record)
        data = json.loads(output)

        assert "extra" in data
        assert data["extra"]["order_id"] == "ord_123"
        assert data["extra"]["card_number"] == "[REDACTED]"
        assert data["extra"]["amount_cents"] == 5000

    def test_exception_traceback_secrets_are_redacted(self):
        """Secrets appearing in formatted exception tracebacks must be scrubbed."""
        formatter = JSONFormatter()
        try:
            secret_in_code = "super_secret_db_password_987654321"
            raise ValueError(f"OperationalError: auth failed with password={secret_in_code}")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="app.test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Database error occurred",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert "exception" in data
        assert "password=[REDACTED]" in data["exception"]["message"]
        # Ensure secret does NOT appear anywhere in the traceback string
        assert "super_secret_db_password_987654321" not in data["exception"]["traceback"]
        assert "password=[REDACTED]" in data["exception"]["traceback"]


# =============================================================================
# 5. RequestIDMiddleware Integration Tests
# =============================================================================

class TestRequestIDMiddlewareIntegration:
    """Verifies RequestIDMiddleware behavior within FastAPI."""

    @pytest.fixture
    def app_client(self):
        """Create a TestClient with a fresh application instance."""
        test_app = create_app()
        return TestClient(test_app)

    def test_middleware_generates_x_request_id_response_header(self, app_client):
        """HTTP response must contain an X-Request-ID header with a valid UUIDv4."""
        response = app_client.get("/healthz")
        assert response.status_code == 200
        req_id = response.headers.get("x-request-id")
        assert req_id is not None
        assert uuid.UUID(req_id).version == 4

    def test_middleware_accepts_valid_client_supplied_request_id(self, app_client):
        """Valid client-supplied X-Request-ID must be echoed in response header."""
        client_id = "client-trace-12345678"
        response = app_client.get("/healthz", headers={"X-Request-ID": client_id})
        assert response.status_code == 200
        assert response.headers.get("x-request-id") == client_id

    def test_middleware_sanitizes_malicious_client_supplied_id(self, app_client):
        """Unsafe client IDs (CRLF / symbols) must be discarded and replaced with UUIDv4."""
        malicious_id = "bad\r\nInjected: True"
        response = app_client.get("/healthz", headers={"X-Request-ID": malicious_id})
        assert response.status_code == 200
        assigned_id = response.headers.get("x-request-id")
        assert assigned_id != malicious_id
        assert uuid.UUID(assigned_id).version == 4

    def test_middleware_stores_request_id_in_request_state(self):
        """Route handlers must be able to read request.state.request_id."""
        test_app = create_app()
        captured_state_id = None

        @test_app.get("/test-state-read")
        def route_with_state(request: Request):
            nonlocal captured_state_id
            captured_state_id = getattr(request.state, "request_id", None)
            return {"status": "ok"}

        client = TestClient(test_app)
        res = client.get("/test-state-read", headers={"X-Request-ID": "test-state-req-123"})
        assert res.status_code == 200
        assert captured_state_id == "test-state-req-123"

    def test_middleware_cleans_up_context_after_request_finishes(self, app_client):
        """After request execution, get_request_id() must be None (zero context leakage)."""
        app_client.get("/healthz")
        assert get_request_id() is None

    def test_middleware_cors_exposes_x_request_id_header(self, app_client):
        """CORS response headers must include Access-Control-Expose-Headers for X-Request-ID."""
        response = app_client.get("/healthz", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200
        expose_headers = response.headers.get("access-control-expose-headers", "")
        assert "x-request-id" in expose_headers.lower()

    def test_middleware_logs_exception_with_correlated_request_id(self, monkeypatch):
        """When an unhandled exception occurs, the error log must capture the correlated request ID."""
        test_app = create_app()
        captured_logs: list[str] = []

        class MemoryLogHandler(logging.Handler):
            def emit(self, record):
                captured_logs.append(record.getMessage())

        mem_handler = MemoryLogHandler()
        logging.getLogger("app.core.logging").addHandler(mem_handler)

        @test_app.get("/test-crash-route")
        def crash_endpoint():
            raise RuntimeError("Database connection suddenly dropped")

        client = TestClient(test_app, raise_server_exceptions=False)
        res = client.get("/test-crash-route")
        assert res.status_code == 500

        # Context must still be cleanly reset
        assert get_request_id() is None

        # Verify error log was emitted
        assert any("Unhandled error processing request" in log for log in captured_logs)

    def test_setup_logging_idempotence_multiple_create_app(self):
        """Repeated create_app() or setup_logging() calls must maintain exactly 1 stdout handler."""
        for _ in range(3):
            setup_logging()
        for _ in range(3):
            create_app()

        stdout_handlers = [
            h for h in logging.getLogger().handlers
            if isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
        ]
        assert len(stdout_handlers) == 1

    def test_duplicate_header_prevention(self):
        """Middleware must not duplicate X-Request-ID if already added."""
        test_app = create_app()

        @test_app.get("/test-manual-header")
        def route_with_manual_header():
            return JSONResponse(
                status_code=200,
                content={"status": "ok"},
                headers={"X-Request-ID": "manual-id-12345678"},
            )

        client = TestClient(test_app)
        res = client.get("/test-manual-header")
        assert res.status_code == 200
        # Check that header value is as expected and not duplicated/corrupted
        assert res.headers.get("x-request-id") == "manual-id-12345678"


# =============================================================================
# 6. Existing Health Endpoints Regression Tests
# =============================================================================

class TestHealthEndpointsRegressionWithMiddleware:
    """Confirms all health endpoints (/healthz, /api/v1/health) remain functional and return X-Request-ID."""

    def test_healthz_returns_200_and_x_request_id(self):
        """GET /healthz must return 200, status ok, and X-Request-ID header."""
        test_app = create_app()
        with TestClient(test_app) as client:
            res = client.get("/healthz")
            assert res.status_code == status.HTTP_200_OK
            assert res.json() == {"status": "ok"}
            assert "x-request-id" in res.headers
            assert uuid.UUID(res.headers["x-request-id"]).version == 4

    def test_readiness_probe_returns_200_and_x_request_id_when_healthy(self, monkeypatch):
        """GET /api/v1/health must return 200, ready, and X-Request-ID header."""
        monkeypatch.setattr("app.main.check_db_connectivity", lambda: True)
        test_app = create_app()
        with TestClient(test_app) as client:
            res = client.get("/api/v1/health")
            assert res.status_code == status.HTTP_200_OK
            data = res.json()
            assert data["status"] == "ready"
            assert data["dependencies"]["database"] == "connected"
            assert "x-request-id" in res.headers

    def test_readiness_probe_returns_503_and_x_request_id_when_unhealthy(self, monkeypatch):
        """GET /api/v1/health must return 503, not_ready, and X-Request-ID header when DB down."""
        monkeypatch.setattr("app.main.check_db_connectivity", lambda: False)
        test_app = create_app()
        with TestClient(test_app) as client:
            res = client.get("/api/v1/health")
            assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            data = res.json()
            assert data["status"] == "not_ready"
            assert "x-request-id" in res.headers

    def test_health_live_alias_includes_x_request_id(self):
        """GET /api/v1/health/live must return 200 and X-Request-ID header."""
        test_app = create_app()
        with TestClient(test_app) as client:
            res = client.get("/api/v1/health/live")
            assert res.status_code == status.HTTP_200_OK
            assert "x-request-id" in res.headers

    def test_health_ready_alias_includes_x_request_id(self, monkeypatch):
        """GET /api/v1/health/ready must return 200 and X-Request-ID header."""
        monkeypatch.setattr("app.main.check_db_connectivity", lambda: True)
        test_app = create_app()
        with TestClient(test_app) as client:
            res = client.get("/api/v1/health/ready")
            assert res.status_code == status.HTTP_200_OK
            assert "x-request-id" in res.headers


# =============================================================================
# 7. Unhandled HTTP 500 Exception Correlation Tests
# =============================================================================

class TestUnhandledExceptionCorrelation:
    """Verifies Request ID correlation through unhandled HTTP 500 exceptions."""

    def test_unhandled_500_exception_logging_and_context_cleanup_with_client_id(self):
        """When an endpoint raises an unhandled exception with client ID, logs capture the ID and context resets."""
        test_app = create_app()
        captured_records: list[logging.LogRecord] = []

        class RecordCaptureHandler(logging.Handler):
            def emit(self, record):
                captured_records.append(record)

        handler = RecordCaptureHandler()
        logging.getLogger("app.core.logging").addHandler(handler)

        @test_app.get("/test-unhandled-client-id")
        def crash_route():
            raise RuntimeError("Fatal unhandled crash with client ID")

        client = TestClient(test_app, raise_server_exceptions=False)
        client_id = "trace-client-crash-999"
        res = client.get("/test-unhandled-client-id", headers={"X-Request-ID": client_id})

        assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # 1. ContextVar is deterministically cleaned up after response
        assert get_request_id() is None

        # 2. Exception log record contains the correlated client ID
        error_records = [r for r in captured_records if r.levelno == logging.ERROR]
        assert len(error_records) >= 1
        assert getattr(error_records[0], "request_id", None) == client_id

    def test_unhandled_500_exception_logging_and_context_cleanup_with_generated_id(self):
        """When an endpoint raises an unhandled exception with no client ID, logs capture the generated UUIDv4."""
        test_app = create_app()
        captured_records: list[logging.LogRecord] = []

        class RecordCaptureHandler(logging.Handler):
            def emit(self, record):
                captured_records.append(record)

        handler = RecordCaptureHandler()
        logging.getLogger("app.core.logging").addHandler(handler)

        @test_app.get("/test-unhandled-generated-id")
        def crash_route():
            raise RuntimeError("Fatal unhandled crash with generated ID")

        client = TestClient(test_app, raise_server_exceptions=False)
        res = client.get("/test-unhandled-generated-id")

        assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # 1. ContextVar is deterministically cleaned up
        assert get_request_id() is None

        # 2. Exception log record contains a valid UUIDv4
        error_records = [r for r in captured_records if r.levelno == logging.ERROR]
        assert len(error_records) >= 1
        assigned_id = getattr(error_records[0], "request_id", None)
        assert assigned_id is not None
        assert uuid.UUID(assigned_id).version == 4

    def test_unhandled_500_preserves_request_id_in_request_state_for_outer_handlers(self):
        """Request.state.request_id remains preserved on scope for outer exception handlers."""
        settings = Settings(DEBUG=False)
        test_app = create_app(settings=settings)
        captured_state_id = None

        @test_app.exception_handler(500)
        async def outer_500_handler(request: Request, exc: Exception):
            nonlocal captured_state_id
            captured_state_id = getattr(request.state, "request_id", None)
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse("Handled Internal Server Error", status_code=500)

        @test_app.get("/test-state-propagation-on-500")
        def crash_route():
            raise RuntimeError("Testing state preservation on 500")

        client = TestClient(test_app, raise_server_exceptions=False)
        client_id = "test-state-corr-555"
        res = client.get("/test-state-propagation-on-500", headers={"X-Request-ID": client_id})

        assert res.status_code == 500
        # request.state.request_id was available to the 500 error handler
        assert captured_state_id == client_id
