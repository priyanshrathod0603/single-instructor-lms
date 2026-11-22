"""Unit and integration tests for centralized error handlers and exception envelopes.

Verifies:
1. Application exception hierarchy (AppException and all standard subclasses).
2. Standard error response contract:
   {
       "success": false,
       "error": {
           "code": "ERROR_CODE",
           "message": "Human-readable description",
           "details": {},
           "request_id": "UUID"
       }
   }
3. Request ID propagation into body (`error.request_id`) and header (`X-Request-ID`).
4. Correlated request ID in structured logging records.
5. Fallback UUID generation when request ID is absent.
6. HTTP status preservation (400, 401, 403, 404, 409, 422, 429, 500).
7. Request validation error formatting and sensitive field protection.
8. Database error sanitization (IntegrityError -> 409, OperationalError -> 500, no leaked SQL).
9. Unhandled exception handling (500 without stack trace leakage).
10. CORS headers on error responses for allowed origins.
11. Regression verification on existing health and success routes.
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
import uuid

from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
import pytest
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings
from app.core.error_handlers import (
    create_error_response,
    register_error_handlers,
    resolve_request_id,
    sanitize_validation_errors,
)
from app.core.exceptions import (
    AppException,
    BadRequestException,
    ConflictException,
    DatabaseException,
    ForbiddenException,
    InternalServerException,
    NotFoundException,
    RateLimitException,
    ResourceNotFoundException,
    SessionRevokedException,
    UnauthorizedException,
    ValidationException,
)
from app.core.logging import JSONFormatter, RequestIDFilter, RequestIDMiddleware
from app.main import create_app


# =============================================================================
# Helper Fixtures & Test Schemas
# =============================================================================


class DummyPayload(BaseModel):
    name: str = Field(min_length=3)
    email: str
    password: str = Field(min_length=8)
    age: int = Field(ge=18)


def build_test_app_with_routes(settings: Settings | None = None) -> FastAPI:
    """Build a test application with error handlers and test routes."""
    app_settings = settings or Settings(DEBUG=False)
    app = create_app(settings=app_settings)

    @app.get("/test/app-bad-request")
    def route_bad_request():
        raise BadRequestException(message="Custom bad request message.", details={"field": "username"})

    @app.get("/test/app-unauthorized")
    def route_unauthorized():
        raise UnauthorizedException(message="Token expired.", details={"reason": "expired"})

    @app.get("/test/app-session-revoked")
    def route_session_revoked():
        raise SessionRevokedException(
            message="Your session has been terminated because a newer login occurred on another device.",
            details={"revoked_at": "2026-11-14T10:00:00Z", "new_ip": "192.0.2.1"},
        )

    @app.get("/test/app-forbidden")
    def route_forbidden():
        raise ForbiddenException(message="Insufficient permissions.", details={"required": "admin"})

    @app.get("/test/app-not-found")
    def route_not_found():
        raise NotFoundException(message="Course not found.", details={"slug": "math-101"})

    @app.get("/test/app-resource-not-found")
    def route_resource_not_found():
        raise ResourceNotFoundException(resource_type="Lesson", resource_id="les-456")

    @app.get("/test/app-conflict")
    def route_conflict():
        raise ConflictException(message="Course revision is outdated.", details={"version": 3})

    @app.get("/test/app-validation")
    def route_validation():
        raise ValidationException(message="Business rule violated.", details={"reason": "quota_full"})

    @app.get("/test/app-rate-limit")
    def route_rate_limit():
        raise RateLimitException(message="Rate limit reached.", retry_after=60)

    @app.get("/test/app-internal")
    def route_internal():
        raise InternalServerException()

    @app.get("/test/app-database")
    def route_database():
        raise DatabaseException()

    @app.get("/test/http-400")
    def route_http_400():
        raise HTTPException(status_code=400, detail="Bad request syntax.")

    @app.get("/test/http-401")
    def route_http_401():
        raise HTTPException(status_code=401, detail="Invalid bearer token.", headers={"WWW-Authenticate": "Bearer"})

    @app.get("/test/http-403")
    def route_http_403():
        raise HTTPException(status_code=403, detail="Forbidden resource.")

    @app.get("/test/http-404")
    def route_http_404():
        raise HTTPException(status_code=404, detail="Entity does not exist.")

    @app.get("/test/http-405")
    def route_http_405():
        raise HTTPException(status_code=405, detail="Method Not Allowed.")

    @app.get("/test/http-409")
    def route_http_409():
        raise HTTPException(status_code=409, detail="Duplicate resource.")

    @app.get("/test/http-429")
    def route_http_429():
        raise HTTPException(status_code=429, detail="Quota exceeded.", headers={"Retry-After": "120"})

    @app.get("/test/http-dict-detail")
    def route_http_dict():
        raise HTTPException(status_code=400, detail={"message": "Malformed body", "code": "INVALID_SYNTAX"})

    @app.get("/test/http-list-detail")
    def route_http_list():
        raise HTTPException(status_code=400, detail=["error 1", "error 2"])

    @app.post("/test/validation-body")
    def route_validation_body(payload: DummyPayload):
        return {"success": True, "name": payload.name}

    @app.get("/test/db-integrity")
    def route_db_integrity():
        raise IntegrityError(
            statement="INSERT INTO users (email) VALUES ('test@example.com')",
            params={"email": "test@example.com"},
            orig=Exception("duplicate key value violates unique constraint 'uq_users_email'"),
        )

    @app.get("/test/db-operational")
    def route_db_operational():
        raise OperationalError(
            statement="SELECT * FROM secret_table",
            params={},
            orig=Exception("could not connect to server: Connection refused at postgresql://user:super_secret_pw@db:5432"),
        )

    @app.get("/test/unhandled-runtime")
    def route_unhandled_runtime():
        raise RuntimeError("Fatal unhandled exception in core engine!")

    @app.get("/test/unhandled-keyerror")
    def route_unhandled_keyerror():
        raise KeyError("missing_secret_key")

    @app.get("/test/unhandled-valueerror")
    def route_unhandled_valueerror():
        raise ValueError("Invalid internal computation state")

    @app.get("/test/success")
    def route_success():
        return {"success": True, "data": {"message": "All good"}}

    return app


# =============================================================================
# 1. Custom Application Exception Hierarchy Tests
# =============================================================================


class TestAppExceptionsHierarchy:
    """Verifies all AppException subclasses carry correct defaults and contracts."""

    def test_base_app_exception_defaults(self):
        exc = AppException()
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc.code == "INTERNAL_SERVER_ERROR"
        assert exc.message == "An unexpected internal server error occurred."
        assert exc.details == {}
        assert exc.headers == {}
        assert str(exc) == "An unexpected internal server error occurred."
        assert "INTERNAL_SERVER_ERROR" in repr(exc)

    def test_bad_request_exception(self):
        exc = BadRequestException(message="Invalid format", details={"foo": "bar"})
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert exc.code == "BAD_REQUEST"
        assert exc.message == "Invalid format"
        assert exc.details == {"foo": "bar"}

    def test_unauthorized_exception(self):
        exc = UnauthorizedException()
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc.code == "UNAUTHORIZED"
        assert exc.headers.get("WWW-Authenticate") == "Bearer"

    def test_session_revoked_exception(self):
        exc = SessionRevokedException(details={"revoked_by": "192.168.1.1"})
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc.code == "SESSION_REVOKED"
        assert "session has been terminated" in exc.message
        assert exc.details["revoked_by"] == "192.168.1.1"

    def test_forbidden_exception(self):
        exc = ForbiddenException()
        assert exc.status_code == status.HTTP_403_FORBIDDEN
        assert exc.code == "FORBIDDEN"

    def test_not_found_exception(self):
        exc = NotFoundException()
        assert exc.status_code == status.HTTP_404_NOT_FOUND
        assert exc.code == "NOT_FOUND"

    def test_resource_not_found_exception(self):
        exc = ResourceNotFoundException(resource_type="Course", resource_id="crs-123")
        assert exc.status_code == status.HTTP_404_NOT_FOUND
        assert exc.code == "RESOURCE_NOT_FOUND"
        assert "Course 'crs-123' not found." in exc.message
        assert exc.details["resource_type"] == "Course"
        assert exc.details["resource_id"] == "crs-123"

    def test_conflict_exception(self):
        exc = ConflictException()
        assert exc.status_code == status.HTTP_409_CONFLICT
        assert exc.code == "CONFLICT"

    def test_validation_exception(self):
        exc = ValidationException(details={"field": "title"})
        assert exc.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert exc.code == "VALIDATION_ERROR"
        assert exc.details == {"field": "title"}

    def test_rate_limit_exception(self):
        exc = RateLimitException(retry_after=45)
        assert exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert exc.code == "RATE_LIMIT_EXCEEDED"
        assert exc.headers["Retry-After"] == "45"
        assert exc.details["retry_after_seconds"] == 45

    def test_internal_server_exception(self):
        exc = InternalServerException()
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc.code == "INTERNAL_SERVER_ERROR"

    def test_database_exception(self):
        exc = DatabaseException()
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc.code == "DATABASE_ERROR"


# =============================================================================
# 2. Standard Error Response Envelope Tests
# =============================================================================


class TestStandardErrorEnvelope:
    """Verifies that all error responses conform strictly to the standard envelope."""

    @pytest.fixture
    def client(self):
        app = build_test_app_with_routes()
        return TestClient(app, raise_server_exceptions=False)

    def test_app_bad_request_envelope(self, client):
        res = client.get("/test/app-bad-request", headers={"X-Request-ID": "test-req-bad-req"})
        assert res.status_code == 400
        assert res.headers.get("X-Request-ID") == "test-req-bad-req"

        body = res.json()
        assert body["success"] is False
        assert "error" in body
        error = body["error"]
        assert error["code"] == "BAD_REQUEST"
        assert error["message"] == "Custom bad request message."
        assert error["details"] == {"field": "username"}
        assert error["request_id"] == "test-req-bad-req"

    def test_app_unauthorized_envelope_and_header(self, client):
        res = client.get("/test/app-unauthorized", headers={"X-Request-ID": "test-req-unauth"})
        assert res.status_code == 401
        assert res.headers.get("X-Request-ID") == "test-req-unauth"
        assert "Bearer" in res.headers.get("WWW-Authenticate", "")

        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "UNAUTHORIZED"
        assert body["error"]["message"] == "Token expired."
        assert body["error"]["details"] == {"reason": "expired"}
        assert body["error"]["request_id"] == "test-req-unauth"

    def test_app_session_revoked_envelope(self, client):
        res = client.get("/test/app-session-revoked", headers={"X-Request-ID": "test-req-revoked"})
        assert res.status_code == 401
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "SESSION_REVOKED"
        assert body["error"]["details"]["new_ip"] == "192.0.2.1"
        assert body["error"]["request_id"] == "test-req-revoked"

    def test_app_forbidden_envelope(self, client):
        res = client.get("/test/app-forbidden", headers={"X-Request-ID": "test-req-forbid"})
        assert res.status_code == 403
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "FORBIDDEN"
        assert body["error"]["details"] == {"required": "admin"}
        assert body["error"]["request_id"] == "test-req-forbid"

    def test_app_not_found_envelope(self, client):
        res = client.get("/test/app-not-found", headers={"X-Request-ID": "test-req-notfound"})
        assert res.status_code == 404
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["details"] == {"slug": "math-101"}
        assert body["error"]["request_id"] == "test-req-notfound"

    def test_app_resource_not_found_envelope(self, client):
        res = client.get("/test/app-resource-not-found", headers={"X-Request-ID": "test-req-resnotfound"})
        assert res.status_code == 404
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert body["error"]["details"]["resource_type"] == "Lesson"
        assert body["error"]["details"]["resource_id"] == "les-456"

    def test_app_conflict_envelope(self, client):
        res = client.get("/test/app-conflict", headers={"X-Request-ID": "test-req-conflict"})
        assert res.status_code == 409
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "CONFLICT"
        assert body["error"]["details"] == {"version": 3}
        assert body["error"]["request_id"] == "test-req-conflict"

    def test_app_validation_envelope(self, client):
        res = client.get("/test/app-validation", headers={"X-Request-ID": "test-req-val"})
        assert res.status_code == 422
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["details"] == {"reason": "quota_full"}

    def test_app_rate_limit_envelope_and_retry_header(self, client):
        res = client.get("/test/app-rate-limit", headers={"X-Request-ID": "test-req-ratelimit"})
        assert res.status_code == 429
        assert res.headers.get("Retry-After") == "60"
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert body["error"]["details"]["retry_after_seconds"] == 60

    def test_app_internal_server_envelope(self, client):
        res = client.get("/test/app-internal", headers={"X-Request-ID": "test-req-internal"})
        assert res.status_code == 500
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert body["error"]["message"] == "An unexpected internal server error occurred."
        assert body["error"]["request_id"] == "test-req-internal"

    def test_app_database_envelope(self, client):
        res = client.get("/test/app-database", headers={"X-Request-ID": "test-req-db"})
        assert res.status_code == 500
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "DATABASE_ERROR"
        assert body["error"]["message"] == "A database error occurred while processing your request."
        assert body["error"]["request_id"] == "test-req-db"


# =============================================================================
# 3. Standard HTTP Exceptions Tests
# =============================================================================


class TestStandardHTTPExceptions:
    """Verifies Starlette/FastAPI HTTPExceptions are mapped to the standard envelope."""

    @pytest.fixture
    def client(self):
        app = build_test_app_with_routes()
        return TestClient(app, raise_server_exceptions=False)

    def test_http_400_mapped(self, client):
        res = client.get("/test/http-400", headers={"X-Request-ID": "test-http-400"})
        assert res.status_code == 400
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "BAD_REQUEST"
        assert body["error"]["message"] == "Bad request syntax."
        assert body["error"]["request_id"] == "test-http-400"

    def test_http_401_mapped_with_headers(self, client):
        res = client.get("/test/http-401", headers={"X-Request-ID": "test-http-401"})
        assert res.status_code == 401
        assert res.headers.get("WWW-Authenticate") == "Bearer"
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "UNAUTHORIZED"
        assert body["error"]["message"] == "Invalid bearer token."

    def test_http_403_mapped(self, client):
        res = client.get("/test/http-403", headers={"X-Request-ID": "test-http-403"})
        assert res.status_code == 403
        body = res.json()
        assert body["error"]["code"] == "FORBIDDEN"
        assert body["error"]["message"] == "Forbidden resource."

    def test_http_404_mapped(self, client):
        res = client.get("/test/http-404", headers={"X-Request-ID": "test-http-404"})
        assert res.status_code == 404
        body = res.json()
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "Entity does not exist."

    def test_http_404_unregistered_endpoint(self, client):
        res = client.get("/nonexistent-endpoint-12345", headers={"X-Request-ID": "test-404-unreg"})
        assert res.status_code == 404
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "Not Found"
        assert body["error"]["request_id"] == "test-404-unreg"

    def test_http_405_mapped(self, client):
        res = client.get("/test/http-405", headers={"X-Request-ID": "test-http-405"})
        assert res.status_code == 405
        body = res.json()
        assert body["error"]["code"] == "METHOD_NOT_ALLOWED"

    def test_http_409_mapped(self, client):
        res = client.get("/test/http-409", headers={"X-Request-ID": "test-http-409"})
        assert res.status_code == 409
        body = res.json()
        assert body["error"]["code"] == "CONFLICT"
        assert body["error"]["message"] == "Duplicate resource."

    def test_http_429_mapped_with_headers(self, client):
        res = client.get("/test/http-429", headers={"X-Request-ID": "test-http-429"})
        assert res.status_code == 429
        assert res.headers.get("Retry-After") == "120"
        body = res.json()
        assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    def test_http_dict_detail_extracted(self, client):
        res = client.get("/test/http-dict-detail", headers={"X-Request-ID": "test-dict-detail"})
        assert res.status_code == 400
        body = res.json()
        assert body["error"]["code"] == "BAD_REQUEST"
        assert body["error"]["message"] == "Malformed body"
        assert body["error"]["details"]["code"] == "INVALID_SYNTAX"

    def test_http_list_detail_extracted(self, client):
        res = client.get("/test/http-list-detail", headers={"X-Request-ID": "test-list-detail"})
        assert res.status_code == 400
        body = res.json()
        assert body["error"]["code"] == "BAD_REQUEST"
        assert body["error"]["details"]["errors"] == ["error 1", "error 2"]


# =============================================================================
# 4. Request Validation Error Sanitization & Protection Tests
# =============================================================================


class TestRequestValidationErrorHandling:
    """Verifies schema validation errors (HTTP 422) never leak sensitive field data."""

    @pytest.fixture
    def client(self):
        app = build_test_app_with_routes()
        return TestClient(app, raise_server_exceptions=False)

    def test_validation_error_missing_fields(self, client):
        res = client.post(
            "/test/validation-body",
            json={},
            headers={"X-Request-ID": "test-val-missing"},
        )
        assert res.status_code == 422
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["message"] == "Request validation failed."
        assert body["error"]["request_id"] == "test-val-missing"

        errors = body["error"]["details"]["errors"]
        assert len(errors) == 4
        fields = [err["field"] for err in errors]
        assert "body.name" in fields
        assert "body.email" in fields
        assert "body.password" in fields
        assert "body.age" in fields

    def test_validation_error_sensitive_password_not_leaked(self, client):
        res = client.post(
            "/test/validation-body",
            json={
                "name": "Al",  # Too short
                "email": "invalid-email",
                "password": "short",  # Too short: sensitive value
                "age": 16,  # Less than 18
            },
            headers={"X-Request-ID": "test-val-sensitive"},
        )
        assert res.status_code == 422
        body = res.json()
        errors = body["error"]["details"]["errors"]

        # Ensure raw password value 'short' is NOT reflected in the response
        res_text = res.text
        assert "short" in [err.get("type") for err in errors] or "string_too_short" in [err.get("type") for err in errors]
        # Check that no input password field leaked
        for err in errors:
            if "password" in err["field"]:
                assert "input" not in err
                assert err["type"] == "string_too_short"

    def test_sanitize_validation_errors_direct(self):
        raw_errors = [
            {
                "type": "string_too_short",
                "loc": ("body", "password"),
                "msg": "String should have at least 8 characters",
                "input": "secret1",
                "ctx": {"min_length": 8},
            },
            {
                "type": "greater_than_equal",
                "loc": ("body", "age"),
                "msg": "Input should be greater than or equal to 18",
                "input": 15,
                "ctx": {"ge": 18},
            },
        ]
        sanitized = sanitize_validation_errors(raw_errors)
        assert len(sanitized) == 2

        # Password error: sensitive context stripped, input omitted
        pw_err = sanitized[0]
        assert pw_err["field"] == "body.password"
        assert "input" not in pw_err
        assert "context" not in pw_err

        # Age error: non-sensitive context retained
        age_err = sanitized[1]
        assert age_err["field"] == "body.age"
        assert age_err["context"]["ge"] == 18


# =============================================================================
# 5. Database Error Sanitization Tests
# =============================================================================


class TestDatabaseErrorSanitization:
    """Verifies database errors never leak SQL queries, tables, or credentials."""

    @pytest.fixture
    def client(self):
        app = build_test_app_with_routes()
        return TestClient(app, raise_server_exceptions=False)

    def test_integrity_error_maps_to_409_conflict(self, client):
        res = client.get("/test/db-integrity", headers={"X-Request-ID": "test-db-integrity"})
        assert res.status_code == 409
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "RESOURCE_CONFLICT"
        assert body["error"]["message"] == "A database integrity constraint was violated."
        assert body["error"]["details"] == {}
        assert body["error"]["request_id"] == "test-db-integrity"

        # Verify no raw SQL or constraint name leaked
        assert "INSERT INTO" not in res.text
        assert "uq_users_email" not in res.text
        assert "duplicate key" not in res.text

    def test_operational_error_maps_to_500_database_error(self, client):
        res = client.get("/test/db-operational", headers={"X-Request-ID": "test-db-operational"})
        assert res.status_code == 500
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "DATABASE_ERROR"
        assert body["error"]["message"] == "A database error occurred while processing your request."
        assert body["error"]["details"] == {}
        assert body["error"]["request_id"] == "test-db-operational"

        # Verify no credentials, table names, or connection strings leaked
        assert "super_secret_pw" not in res.text
        assert "secret_table" not in res.text
        assert "postgresql://" not in res.text
        assert "5432" not in res.text


# =============================================================================
# 6. Unhandled Server Exceptions (HTTP 500) Tests
# =============================================================================


class TestUnhandledServerExceptions:
    """Verifies unexpected exceptions return HTTP 500 without stack trace leaks."""

    @pytest.fixture
    def client(self):
        app = build_test_app_with_routes()
        return TestClient(app, raise_server_exceptions=False)

    def test_unhandled_runtime_error_500(self, client):
        res = client.get("/test/unhandled-runtime", headers={"X-Request-ID": "test-unhandled-runtime"})
        assert res.status_code == 500
        assert res.headers.get("X-Request-ID") == "test-unhandled-runtime"

        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert body["error"]["message"] == "An unexpected internal server error occurred."
        assert body["error"]["details"] == {}
        assert body["error"]["request_id"] == "test-unhandled-runtime"

        # Verify stack trace and internal message not leaked
        assert "Fatal unhandled exception in core engine" not in res.text
        assert "Traceback" not in res.text
        assert ".py" not in res.text

    def test_unhandled_keyerror_500(self, client):
        res = client.get("/test/unhandled-keyerror", headers={"X-Request-ID": "test-unhandled-key"})
        assert res.status_code == 500
        body = res.json()
        assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert "missing_secret_key" not in res.text

    def test_unhandled_valueerror_500(self, client):
        res = client.get("/test/unhandled-valueerror", headers={"X-Request-ID": "test-unhandled-val"})
        assert res.status_code == 500
        body = res.json()
        assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert "Invalid internal computation state" not in res.text


# =============================================================================
# 7. Request ID Correlation & Logging Tests
# =============================================================================


class TestRequestIdCorrelationAndLogging:
    """Verifies Request ID consistency between client header, body, and logs."""

    def test_request_id_matches_in_structured_logs(self):
        log_stream = io.StringIO()
        stream_handler = logging.StreamHandler(log_stream)
        stream_handler.setFormatter(JSONFormatter())
        stream_handler.addFilter(RequestIDFilter())

        test_logger = logging.getLogger("app.core.error_handlers")
        test_logger.addHandler(stream_handler)
        test_logger.setLevel(logging.INFO)

        app = build_test_app_with_routes()
        client = TestClient(app, raise_server_exceptions=False)

        correlation_id = "corr-log-test-8899"
        res = client.get("/test/app-bad-request", headers={"X-Request-ID": correlation_id})
        assert res.status_code == 400
        assert res.headers.get("X-Request-ID") == correlation_id
        assert res.json()["error"]["request_id"] == correlation_id

        # Inspect captured log output
        log_output = log_stream.getvalue()
        test_logger.removeHandler(stream_handler)

        assert correlation_id in log_output
        parsed_logs = [json.loads(line) for line in log_output.strip().split("\n") if line.strip()]
        matching = [log for log in parsed_logs if log.get("request_id") == correlation_id]
        assert len(matching) >= 1
        assert matching[0]["level"] == "INFO"
        assert matching[0]["extra"]["error_code"] == "BAD_REQUEST"

    def test_unhandled_500_matches_in_structured_logs(self):
        log_stream = io.StringIO()
        stream_handler = logging.StreamHandler(log_stream)
        stream_handler.setFormatter(JSONFormatter())
        stream_handler.addFilter(RequestIDFilter())

        test_logger = logging.getLogger("app.core.error_handlers")
        test_logger.addHandler(stream_handler)
        test_logger.setLevel(logging.ERROR)

        app = build_test_app_with_routes()
        client = TestClient(app, raise_server_exceptions=False)

        correlation_id = "corr-500-test-9900"
        res = client.get("/test/unhandled-runtime", headers={"X-Request-ID": correlation_id})
        assert res.status_code == 500
        assert res.headers.get("X-Request-ID") == correlation_id
        assert res.json()["error"]["request_id"] == correlation_id

        log_output = log_stream.getvalue()
        test_logger.removeHandler(stream_handler)

        assert correlation_id in log_output
        parsed_logs = [json.loads(line) for line in log_output.strip().split("\n") if line.strip()]
        matching = [log for log in parsed_logs if log.get("request_id") == correlation_id]
        assert len(matching) >= 1
        assert matching[0]["level"] == "ERROR"
        assert matching[0]["extra"]["error_code"] == "INTERNAL_SERVER_ERROR"

    def test_missing_client_request_id_generates_valid_uuid_fallback(self):
        app = build_test_app_with_routes()
        client = TestClient(app, raise_server_exceptions=False)

        res = client.get("/test/app-not-found")
        assert res.status_code == 404
        header_id = res.headers.get("X-Request-ID")
        assert header_id is not None

        body = res.json()
        body_id = body["error"]["request_id"]
        assert body_id == header_id

        # Verify valid UUIDv4
        parsed_uuid = uuid.UUID(body_id)
        assert parsed_uuid.version == 4


# =============================================================================
# 8. CORS Headers on Error Responses Tests
# =============================================================================


class TestCORSHeadersOnErrorResponses:
    """Verifies that CORS headers are appropriately attached to error responses."""

    def test_cors_headers_on_handled_error_for_allowed_origin(self):
        settings = Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="test-secret-key-minimum-32-chars-long!",
            CORS_ORIGINS=["https://frontend.lms.com"],
            DEBUG=False,
        )
        app = build_test_app_with_routes(settings=settings)
        client = TestClient(app, raise_server_exceptions=False)

        res = client.get(
            "/test/app-bad-request",
            headers={"Origin": "https://frontend.lms.com", "X-Request-ID": "test-cors-400"},
        )
        assert res.status_code == 400
        assert res.headers.get("Access-Control-Allow-Origin") == "https://frontend.lms.com"
        assert res.headers.get("Access-Control-Allow-Credentials") == "true"
        assert res.headers.get("Access-Control-Expose-Headers") == "X-Request-ID"

    def test_cors_headers_on_unhandled_500_for_allowed_origin(self):
        settings = Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="test-secret-key-minimum-32-chars-long!",
            CORS_ORIGINS=["https://frontend.lms.com"],
            DEBUG=False,
        )
        app = build_test_app_with_routes(settings=settings)
        client = TestClient(app, raise_server_exceptions=False)

        res = client.get(
            "/test/unhandled-runtime",
            headers={"Origin": "https://frontend.lms.com", "X-Request-ID": "test-cors-500"},
        )
        assert res.status_code == 500
        assert res.headers.get("Access-Control-Allow-Origin") == "https://frontend.lms.com"
        assert res.headers.get("Access-Control-Allow-Credentials") == "true"
        assert res.headers.get("Access-Control-Expose-Headers") == "X-Request-ID"

    def test_cors_headers_disallowed_origin_omitted(self):
        settings = Settings(
            DATABASE_URL="sqlite:///test.db",
            SECRET_KEY="test-secret-key-minimum-32-chars-long!",
            CORS_ORIGINS=["https://frontend.lms.com"],
            DEBUG=False,
        )
        app = build_test_app_with_routes(settings=settings)
        client = TestClient(app, raise_server_exceptions=False)

        res = client.get(
            "/test/app-not-found",
            headers={"Origin": "https://malicious-site.com", "X-Request-ID": "test-cors-disallowed"},
        )
        assert res.status_code == 404
        assert "Access-Control-Allow-Origin" not in res.headers


# =============================================================================
# 9. Health & Success Endpoints Regression Tests
# =============================================================================


class TestHealthAndSuccessEndpointsRegression:
    """Verifies that normal operations, health endpoints, and success responses are unaffected."""

    @pytest.fixture
    def client(self):
        app = build_test_app_with_routes()
        return TestClient(app, raise_server_exceptions=False)

    def test_liveness_probe_regression(self, client):
        res = client.get("/healthz", headers={"X-Request-ID": "test-healthz-ok"})
        assert res.status_code == 200
        assert res.headers.get("X-Request-ID") == "test-healthz-ok"
        assert res.json() == {"status": "ok"}

    def test_readiness_probe_regression(self, client):
        res = client.get("/api/v1/health", headers={"X-Request-ID": "test-readiness"})
        assert res.status_code in (200, 503)
        assert res.headers.get("X-Request-ID") == "test-readiness"
        assert "status" in res.json()

    def test_successful_route_not_altered(self, client):
        res = client.get("/test/success", headers={"X-Request-ID": "test-success-ok"})
        assert res.status_code == 200
        assert res.headers.get("X-Request-ID") == "test-success-ok"
        body = res.json()
        assert body == {"success": True, "data": {"message": "All good"}}
