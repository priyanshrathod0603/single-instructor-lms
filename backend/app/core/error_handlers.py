"""Centralized exception handlers and standard error response formatting.

Follows the backend architecture defined in:
- docs/backend/01-SYSTEM-ARCHITECTURE.md
- docs/backend/06-API-ARCHITECTURE.md (Standard Error Response Envelope)
- docs/backend/18-SECURITY-ARCHITECTURE.md (A05 Security Misconfiguration & Traceback Sanitization)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK006)

Ensures:
1. Every error produces the standard envelope:
   {
       "success": false,
       "error": {
           "code": "ERROR_CODE",
           "message": "Human-readable description",
           "details": {},
           "request_id": "UUID"
       }
   }
2. Request ID from request.state.request_id (or contextvars) is propagated into:
   - JSON response body (`error.request_id`)
   - HTTP response header (`X-Request-ID`)
   - Correlated structured JSON log entries
3. HTTP status codes are strictly preserved (400, 401, 403, 404, 409, 422, 429, 500).
4. Raw database errors, tracebacks, internal file paths, and SQL queries are NEVER leaked.
5. Allowed CORS origins receive CORS headers even on 500 errors handled by ServerErrorMiddleware.
"""

from __future__ import annotations

import http
import logging
from typing import Any, Optional
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings, get_settings
from app.core.exceptions import AppException
from app.core.logging import SENSITIVE_KEYS, get_request_id, redact_sensitive_text

logger = logging.getLogger(__name__)

# Canonical status code to error code mapping for standard HTTP exceptions
HTTP_STATUS_CODE_MAP: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_406_NOT_ACCEPTABLE: "NOT_ACCEPTABLE",
    status.HTTP_408_REQUEST_TIMEOUT: "REQUEST_TIMEOUT",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_410_GONE: "GONE",
    status.HTTP_413_CONTENT_TOO_LARGE: "PAYLOAD_TOO_LARGE",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "UNSUPPORTED_MEDIA_TYPE",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "UNPROCESSABLE_ENTITY",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMIT_EXCEEDED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
    status.HTTP_501_NOT_IMPLEMENTED: "NOT_IMPLEMENTED",
    status.HTTP_502_BAD_GATEWAY: "BAD_GATEWAY",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
    status.HTTP_504_GATEWAY_TIMEOUT: "GATEWAY_TIMEOUT",
}


def resolve_request_id(request: Request) -> str:
    """Retrieve the active request ID or generate a deterministic fallback UUID.

    Priority order:
    1. request.state.request_id (populated on ASGI scope by RequestIDMiddleware)
    2. get_request_id() (contextvars from logging module)
    3. uuid.uuid4() fallback if neither is available.
    """
    req_id = getattr(request.state, "request_id", None)
    if req_id and isinstance(req_id, str):
        return req_id

    req_id = get_request_id()
    if req_id and isinstance(req_id, str):
        return req_id

    fallback_id = str(uuid.uuid4())
    try:
        request.state.request_id = fallback_id
    except Exception:
        pass
    return fallback_id


def create_error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
) -> JSONResponse:
    """Construct a standardized error JSONResponse with security & CORS headers.

    Args:
        request: Incoming FastAPI/Starlette Request.
        status_code: HTTP response status code.
        code: Canonical machine-readable error string (e.g. 'NOT_FOUND').
        message: Human-readable safe description.
        details: Structured error metadata dictionary.
        headers: Optional additional HTTP headers to inject.

    Returns:
        JSONResponse with standard envelope and correlated X-Request-ID.
    """
    request_id = resolve_request_id(request)

    response_headers: dict[str, str] = {
        "X-Request-ID": request_id,
    }
    if headers:
        response_headers.update(headers)

    # Attach CORS headers if origin is in configured allowed origins
    origin = request.headers.get("origin")
    if origin:
        settings: Optional[Settings] = getattr(request.app.state, "settings", None)
        if not settings:
            try:
                settings = get_settings()
            except Exception:
                settings = None

        if settings:
            allowed_origins = (
                settings.CORS_ORIGINS
                if isinstance(settings.CORS_ORIGINS, list) and settings.CORS_ORIGINS
                else [settings.FRONTEND_URL]
            )
            is_allowed = origin in allowed_origins or "*" in allowed_origins
            if not is_allowed and not settings.is_production:
                has_localhost = any("localhost" in o or "127.0.0.1" in o for o in allowed_origins)
                if has_localhost:
                    import re
                    lan_regex = r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?$"
                    if re.match(lan_regex, origin):
                        is_allowed = True
            if is_allowed:
                response_headers["Access-Control-Allow-Origin"] = origin
                response_headers["Access-Control-Allow-Credentials"] = "true"
                response_headers["Access-Control-Expose-Headers"] = "X-Request-ID"

    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "details": details if details is not None else {},
                "request_id": request_id,
            },
        },
        headers=response_headers,
    )


def sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize and format Pydantic RequestValidationErrors.

    Guards against:
    - Leaking sensitive input values (passwords, tokens, cards).
    - Unserializable Python objects or internal memory addresses.
    """
    sanitized: list[dict[str, Any]] = []

    for err in errors:
        loc = list(err.get("loc", []))
        msg = redact_sensitive_text(str(err.get("msg", "Invalid value.")))
        err_type = str(err.get("type", "value_error"))

        is_sensitive = any(
            isinstance(part, str) and part.lower() in SENSITIVE_KEYS
            for part in loc
        )

        entry: dict[str, Any] = {
            "field": ".".join(str(part) for part in loc),
            "location": loc,
            "message": msg,
            "type": err_type,
        }

        # Include non-sensitive context if serializable
        raw_ctx = err.get("ctx")
        if isinstance(raw_ctx, dict) and not is_sensitive:
            safe_ctx: dict[str, Any] = {}
            for k, v in raw_ctx.items():
                if isinstance(v, (str, int, float, bool)):
                    safe_ctx[k] = v
                else:
                    safe_ctx[k] = str(v)
            if safe_ctx:
                entry["context"] = safe_ctx

        sanitized.append(entry)

    return sanitized


# =============================================================================
# Exception Handlers
# =============================================================================


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handler for all domain and operational AppException subclasses."""
    req_id = resolve_request_id(request)
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error(
            "Application error [%s]: %s (code=%s, status=%d)",
            req_id,
            exc.message,
            exc.code,
            exc.status_code,
            extra={"request_id": req_id, "error_code": exc.code},
            exc_info=True,
        )
    else:
        logger.info(
            "Application exception [%s]: %s (code=%s, status=%d)",
            req_id,
            exc.message,
            exc.code,
            exc.status_code,
            extra={"request_id": req_id, "error_code": exc.code},
        )

    response = create_error_response(
        request=request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        headers=exc.headers,
    )

    # If session was revoked due to displacement, purge the revoked session cookie
    if exc.code == "SESSION_REVOKED":
        settings: Optional[Settings] = getattr(request.app.state, "settings", None)
        if not settings:
            try:
                settings = get_settings()
            except Exception:
                settings = None
        if settings:
            response.delete_cookie(
                key=settings.SESSION_COOKIE_NAME,
                path=settings.SESSION_COOKIE_PATH,
            )

    return response


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handler for Starlette and FastAPI HTTPExceptions."""
    req_id = resolve_request_id(request)
    status_code = exc.status_code
    code = HTTP_STATUS_CODE_MAP.get(status_code, f"HTTP_{status_code}")

    # Extract message and details cleanly
    if isinstance(exc.detail, str):
        message = exc.detail
        details: dict[str, Any] = {}
    elif isinstance(exc.detail, dict):
        if "message" in exc.detail and isinstance(exc.detail["message"], str):
            message = exc.detail["message"]
            details = {k: v for k, v in exc.detail.items() if k != "message"}
        else:
            try:
                message = http.HTTPStatus(status_code).phrase
            except ValueError:
                message = "An HTTP error occurred."
            details = exc.detail
    elif isinstance(exc.detail, list):
        try:
            message = http.HTTPStatus(status_code).phrase
        except ValueError:
            message = "An HTTP error occurred."
        details = {"errors": exc.detail}
    else:
        try:
            message = http.HTTPStatus(status_code).phrase
        except ValueError:
            message = "An HTTP error occurred."
        details = {}

    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error(
            "HTTP exception [%s]: %s (code=%s, status=%d)",
            req_id,
            message,
            code,
            status_code,
            extra={"request_id": req_id, "error_code": code},
            exc_info=True,
        )
    else:
        logger.info(
            "HTTP exception [%s]: %s (code=%s, status=%d)",
            req_id,
            message,
            code,
            status_code,
            extra={"request_id": req_id, "error_code": code},
        )

    return create_error_response(
        request=request,
        status_code=status_code,
        code=code,
        message=message,
        details=details,
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handler for request schema and parameter validation errors (HTTP 422)."""
    req_id = resolve_request_id(request)
    sanitized_errors = sanitize_validation_errors(exc.errors())

    logger.info(
        "Request validation failed [%s]: %d field error(s)",
        req_id,
        len(sanitized_errors),
        extra={"request_id": req_id, "error_code": "VALIDATION_ERROR"},
    )

    return create_error_response(
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="VALIDATION_ERROR",
        message="Request validation failed.",
        details={"errors": sanitized_errors},
    )


async def sqlalchemy_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """Handler for database errors, ensuring internal SQL is never leaked."""
    req_id = resolve_request_id(request)

    if isinstance(exc, IntegrityError):
        logger.warning(
            "Database integrity conflict [%s]: %s",
            req_id,
            exc,
            extra={"request_id": req_id, "error_code": "RESOURCE_CONFLICT"},
            exc_info=True,
        )
        return create_error_response(
            request=request,
            status_code=status.HTTP_409_CONFLICT,
            code="RESOURCE_CONFLICT",
            message="A database integrity constraint was violated.",
            details={},
        )

    logger.error(
        "Database execution error [%s]: %s",
        req_id,
        exc,
        extra={"request_id": req_id, "error_code": "DATABASE_ERROR"},
        exc_info=True,
    )
    return create_error_response(
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="DATABASE_ERROR",
        message="A database error occurred while processing your request.",
        details={},
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all handler for unexpected server exceptions (HTTP 500).

    Mounted on Starlette's ServerErrorMiddleware outside user middleware stack.
    """
    req_id = resolve_request_id(request)
    logger.exception(
        "Unhandled server exception [%s]: %s",
        req_id,
        exc,
        extra={"request_id": req_id, "error_code": "INTERNAL_SERVER_ERROR"},
    )
    return create_error_response(
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected internal server error occurred.",
        details={},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all centralized exception handlers on the FastAPI application."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
