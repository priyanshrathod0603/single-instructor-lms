"""Structured JSON logging and Request ID correlation middleware.

Follows the backend architecture defined in:
- docs/backend/01-SYSTEM-ARCHITECTURE.md
- docs/backend/06-API-ARCHITECTURE.md
- docs/backend/18-SECURITY-ARCHITECTURE.md (A09 Logging Failures & OWASP Mitigation)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK004/TASK005)

Features:
1. Context-isolated Request ID management via contextvars.
2. Safe client-supplied request ID validation (preventing CRLF, header, or log injection).
3. Structured JSON log formatting writing to stdout with UTC ISO 8601 timestamps.
4. Comprehensive redaction of sensitive credentials, tokens, cookies, and payment details.
5. Pure ASGI RequestIDMiddleware with deterministic context cleanup and X-Request-ID header propagation.
"""

from __future__ import annotations

import contextvars
import datetime
import json
import logging
import re
import sys
from typing import Any, Optional
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# =============================================================================
# 1. Context Variable & Request ID Lifecycle
# =============================================================================

REQUEST_ID_CTX_KEY = "request_id"
REQUEST_ID_HEADER = "X-Request-ID"

_request_id_ctx_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    REQUEST_ID_CTX_KEY, default=None
)


def get_request_id() -> Optional[str]:
    """Retrieve the active request ID from the current async execution context."""
    return _request_id_ctx_var.get()


def set_request_id(request_id: Optional[str]) -> contextvars.Token[Optional[str]]:
    """Set the request ID for the current execution context.

    Args:
        request_id: Unique correlation identifier.

    Returns:
        contextvars.Token: Token to restore previous context state upon exit.
    """
    return _request_id_ctx_var.set(request_id)


def reset_request_id(token: contextvars.Token[Optional[str]]) -> None:
    """Reset the request ID to the previous context state using the token.

    Args:
        token: Context token returned by set_request_id().
    """
    _request_id_ctx_var.reset(token)


# =============================================================================
# 2. Client Request ID Validation & Sanitization
# =============================================================================

# Strict alphanumeric, hyphen, underscore pattern (8 to 64 chars)
# Blocks control characters (\r, \n), null bytes, spaces, HTML, quotes, and oversized inputs.
SAFE_REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{8,64}$")


def is_valid_request_id(candidate: Optional[str]) -> bool:
    """Verify if a client-supplied request ID string meets safety and format standards.

    Guards against:
    - HTTP header injection / response splitting (CRLF).
    - Log injection (CWE-117) and terminal escape sequences.
    - Resource exhaustion via oversized strings.
    """
    if not candidate or not isinstance(candidate, str):
        return False
    candidate = candidate.strip()
    return bool(SAFE_REQUEST_ID_PATTERN.match(candidate))


def validate_or_generate_request_id(client_supplied_id: Optional[str] = None) -> str:
    """Return the client-supplied ID if valid; otherwise generate a fresh UUIDv4 string.

    Args:
        client_supplied_id: Optional incoming correlation header from client.

    Returns:
        str: Validated client request ID or newly minted UUIDv4 string.
    """
    if client_supplied_id and is_valid_request_id(client_supplied_id):
        return client_supplied_id.strip()
    return str(uuid.uuid4())


# =============================================================================
# 3. Sensitive Data Redaction
# =============================================================================

SENSITIVE_KEYS: frozenset[str] = frozenset({
    "password",
    "password_hash",
    "passwd",
    "secret",
    "secret_key",
    "token",
    "session_token",
    "access_token",
    "refresh_token",
    "id_token",
    "authorization",
    "cookie",
    "set-cookie",
    "api_key",
    "apikey",
    "key_secret",
    "webhook_secret",
    "card_number",
    "credit_card",
    "pan",
    "cvv",
    "cvc",
    "client_secret",
    "private_key",
    "ssn",
})

REDACTED_SUBSTITUTE = "[REDACTED]"

# Matches standalone Bearer / Token authorization tokens in string messages
STANDALONE_BEARER_REGEX = re.compile(r"(?i)\bbearer\s+[a-z0-9\-._~+/]+=*")

# Matches key-value patterns in string messages (e.g. password=..., "token": "...", Authorization: Bearer ...)
KEY_VALUE_SENSITIVE_REGEX = re.compile(
    r"""(?i)(?P<prefix>['"]?(?:[a-z0-9_\-]*(?:password|passwd|secret|token|authorization|cookie|set-cookie|api_key|apikey|cvv|cvc|card_number|credit_card)[a-z0-9_\-]*)['"]?\s*[:=]\s*(?:bearer\s+)?)(?:(?P<q>['"])(?P<qval>.*?)(?P=q)|(?P<uval>[^'\",;\s]+))"""
)


def redact_sensitive_text(text: str) -> str:
    """Scrub sensitive credentials, tokens, and secrets from free-form text strings."""
    if not isinstance(text, str):
        return text
    # 1. Key-value pairs (including "Authorization: Bearer <token>")
    def _replace_kv(match: re.Match) -> str:
        prefix = match.group("prefix")
        if match.group("q"):
            q = match.group("q")
            return f"{prefix}{q}{REDACTED_SUBSTITUTE}{q}"
        return f"{prefix}{REDACTED_SUBSTITUTE}"

    scrubbed = KEY_VALUE_SENSITIVE_REGEX.sub(_replace_kv, text)
    # 2. Standalone Bearer tokens without key: "Bearer eyJ..." -> "Bearer [REDACTED]"
    scrubbed = STANDALONE_BEARER_REGEX.sub(f"Bearer {REDACTED_SUBSTITUTE}", scrubbed)
    return scrubbed


def redact_sensitive_data(data: Any) -> Any:
    """Recursively redact sensitive key-values from dictionaries, lists, or primitives.

    Args:
        data: Arbitrary data structure (dict, list, tuple, primitive).

    Returns:
        Sanitized structure with all sensitive fields replaced by [REDACTED].
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, val in data.items():
            key_str = str(key).lower()
            if any(sensitive in key_str for sensitive in SENSITIVE_KEYS):
                sanitized[key] = REDACTED_SUBSTITUTE
            else:
                sanitized[key] = redact_sensitive_data(val)
        return sanitized
    elif isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(redact_sensitive_data(item) for item in data)
    elif isinstance(data, str):
        return redact_sensitive_text(data)
    return data


# =============================================================================
# 4. Structured JSON Logging Formatter & Filter
# =============================================================================

class RequestIDFilter(logging.Filter):
    """Logging filter that injects the active request_id from contextvars into LogRecords."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id") or record.request_id is None:
            record.request_id = get_request_id()
        return True


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter outputting machine-readable JSON logs to stdout."""

    def format(self, record: logging.LogRecord) -> str:
        # Determine request ID from record (set by filter) or contextvar
        request_id = getattr(record, "request_id", None) or get_request_id()

        # Format ISO 8601 UTC timestamp
        timestamp = datetime.datetime.fromtimestamp(
            record.created, tz=datetime.timezone.utc
        ).isoformat()

        # Sanitize message
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        message = redact_sensitive_text(message)

        log_entry: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "request_id": request_id,
            "module": record.module,
            "func_name": record.funcName,
            "line": record.lineno,
        }

        # Include exception traceback if present
        if record.exc_info:
            exc_type, exc_val, _ = record.exc_info
            log_entry["exception"] = {
                "type": exc_type.__name__ if exc_type else "Exception",
                "message": redact_sensitive_text(str(exc_val)),
                "traceback": redact_sensitive_text(self.formatException(record.exc_info)),
            }

        # Include extra structured attributes passed via extra={...}
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "request_id", "taskName",
        }
        raw_extras = {
            key: val
            for key, val in record.__dict__.items()
            if key not in standard_attrs and not key.startswith("_")
        }
        if raw_extras:
            log_entry["extra"] = redact_sensitive_data(raw_extras)

        return json.dumps(log_entry, default=str)


def setup_logging(
    level: Optional[str | int] = None,
    settings: Optional[Any] = None,
) -> None:
    """Configure structured JSON logging for the application runtime.

    Args:
        level: Explicit log level override (e.g. "INFO", logging.DEBUG).
        settings: Optional Settings instance to derive level from settings.DEBUG.
    """
    if level is None:
        if settings is not None and hasattr(settings, "DEBUG"):
            level = logging.DEBUG if settings.DEBUG else logging.INFO
        else:
            level = logging.INFO

    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Replace any existing stdout StreamHandlers to prevent duplicate logs
    existing_stdout_handlers = [
        h for h in root_logger.handlers
        if isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
    ]
    for h in existing_stdout_handlers:
        root_logger.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(JSONFormatter())
    handler.addFilter(RequestIDFilter())
    root_logger.addHandler(handler)

    # Ensure application loggers propagate to root handler
    for logger_name in ("app", "uvicorn", "uvicorn.access", "uvicorn.error"):
        sub_logger = logging.getLogger(logger_name)
        sub_logger.setLevel(level)
        sub_logger.propagate = True


# =============================================================================
# 5. ASGI Request ID Middleware
# =============================================================================

logger = logging.getLogger(__name__)


class RequestIDMiddleware:
    """Pure ASGI middleware managing Request ID correlation lifecycle:

    1. Extracts and validates incoming client X-Request-ID header, or generates a UUIDv4.
    2. Stores request_id in request.state.request_id (via scope["state"]).
    3. Binds request_id to contextvars for correlated logging across all downstream async tasks.
    4. Injects X-Request-ID into outgoing HTTP response headers.
    5. Catches unhandled exceptions to record structured error logs with correlated request_id.
    6. Deterministically resets contextvars in a finally block to prevent context leakage.
    """

    def __init__(self, app: ASGIApp, header_name: str = REQUEST_ID_HEADER):
        self.app = app
        self.header_name = header_name
        self.header_bytes = header_name.lower().encode("latin1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. Extract incoming header if present
        client_req_id: Optional[str] = None
        for key, value in scope.get("headers", []):
            if key.lower() == self.header_bytes:
                client_req_id = value.decode("latin1", errors="ignore")
                break

        # 2. Validate client-supplied ID or generate UUIDv4
        request_id = validate_or_generate_request_id(client_req_id)

        # 3. Store on scope state so request.state.request_id is available in route handlers
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        # 4. Bind to contextvars
        token = set_request_id(request_id)

        # 5. Wrap send to inject X-Request-ID header into http.response.start
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                has_header = any(k.lower() == self.header_bytes for k, _ in headers)
                if not has_header:
                    headers.append((self.header_bytes, request_id.encode("latin1")))
                    message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            # Log unhandled exception with correlated request ID before bubbling
            logger.exception("Unhandled error processing request: %s", exc)
            raise exc
        finally:
            reset_request_id(token)
