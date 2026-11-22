"""Custom application exception hierarchy for the Single-Instructor LMS.

Follows the backend architecture defined in:
- docs/backend/01-SYSTEM-ARCHITECTURE.md
- docs/backend/06-API-ARCHITECTURE.md (Standard Error Response Envelope)
- docs/backend/18-SECURITY-ARCHITECTURE.md (A05 Security Misconfiguration & Error Sanitization)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK006)

Provides domain-specific exceptions carrying canonical error codes, HTTP status codes,
sanitized human-readable messages, and structured details.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import status


class AppException(Exception):
    """Base application exception for all domain and operational errors.

    All custom exceptions in the LMS inherit from this base class to ensure
    consistent error response formatting and centralized exception handling.
    """

    def __init__(
        self,
        message: str = "An unexpected internal server error occurred.",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: str = "INTERNAL_SERVER_ERROR",
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}
        self.headers = headers or {}

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"code={self.code!r}, "
            f"status_code={self.status_code}, "
            f"message={self.message!r}, "
            f"details={self.details!r})"
        )

    def __str__(self) -> str:
        return self.message


# =============================================================================
# 1. Client-Side Exceptions (HTTP 4xx)
# =============================================================================


class BadRequestException(AppException):
    """Raised when client sends an invalid request, malformed payload, or invalid parameter."""

    def __init__(
        self,
        message: str = "The request payload or parameters are invalid.",
        code: str = "BAD_REQUEST",
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            code=code,
            details=details,
            headers=headers,
        )


class UnauthorizedException(AppException):
    """Raised when authentication credentials are missing, expired, or invalid."""

    def __init__(
        self,
        message: str = "Authentication credentials are required or invalid.",
        code: str = "UNAUTHORIZED",
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        auth_headers = {"WWW-Authenticate": "Bearer"}
        if headers:
            auth_headers.update(headers)
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=code,
            details=details,
            headers=auth_headers,
        )


class SessionRevokedException(UnauthorizedException):
    """Raised when an active session was superseded by a new login on another device.

    Enforces the single-active-session invariant [Source: LMS Blueprint v2.0, Page 8;
    06-API-ARCHITECTURE.md Section 3.2].
    """

    def __init__(
        self,
        message: str = "Your session has been terminated because a newer login occurred on another device.",
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code="SESSION_REVOKED",
            details=details,
            headers=headers,
        )


class ForbiddenException(AppException):
    """Raised when an authenticated caller lacks required RBAC permissions or scope."""

    def __init__(
        self,
        message: str = "You do not have permission to access this resource.",
        code: str = "FORBIDDEN",
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            code=code,
            details=details,
            headers=headers,
        )


class NotFoundException(AppException):
    """Raised when a requested resource (course, lesson, user, order) cannot be found."""

    def __init__(
        self,
        message: str = "The requested resource could not be found.",
        code: str = "NOT_FOUND",
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            code=code,
            details=details,
            headers=headers,
        )


class ResourceNotFoundException(NotFoundException):
    """Raised when a specific named domain resource does not exist."""

    def __init__(
        self,
        resource_type: str = "Resource",
        resource_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        msg = f"{resource_type} not found." if not resource_id else f"{resource_type} '{resource_id}' not found."
        details_dict = details or {}
        if resource_id:
            details_dict = {"resource_type": resource_type, "resource_id": resource_id, **details_dict}
        super().__init__(
            message=msg,
            code="RESOURCE_NOT_FOUND",
            details=details_dict,
            headers=headers,
        )


class ConflictException(AppException):
    """Raised on state conflicts such as stale revision reordering or duplicate records."""

    def __init__(
        self,
        message: str = "The request could not be completed due to a resource conflict.",
        code: str = "CONFLICT",
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            code=code,
            details=details,
            headers=headers,
        )


class ValidationException(AppException):
    """Raised when domain or business rule validation fails."""

    def __init__(
        self,
        message: str = "Request validation failed.",
        code: str = "VALIDATION_ERROR",
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=code,
            details=details,
            headers=headers,
        )


class RateLimitException(AppException):
    """Raised when client exceeds designated API rate limit threshold."""

    def __init__(
        self,
        message: str = "Too many requests. Please try again later.",
        retry_after: Optional[int] = None,
        code: str = "RATE_LIMIT_EXCEEDED",
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        resp_headers = {}
        if retry_after is not None:
            resp_headers["Retry-After"] = str(retry_after)
            details = {"retry_after_seconds": retry_after, **(details or {})}
        if headers:
            resp_headers.update(headers)
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code=code,
            details=details,
            headers=resp_headers,
        )


# =============================================================================
# 2. Server-Side Exceptions (HTTP 5xx)
# =============================================================================


class InternalServerException(AppException):
    """Raised on unexpected internal application errors."""

    def __init__(
        self,
        message: str = "An unexpected internal server error occurred.",
        code: str = "INTERNAL_SERVER_ERROR",
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=code,
            details=details,
            headers=headers,
        )


class DatabaseException(AppException):
    """Raised on internal database connectivity or execution errors.

    Ensures raw SQL queries, credentials, and connection strings are never leaked.
    """

    def __init__(
        self,
        message: str = "A database error occurred while processing your request.",
        code: str = "DATABASE_ERROR",
        details: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=code,
            details=details,
            headers=headers,
        )
