# Error Handling Standards & Exception Architecture Specification

## 1. Unified Error Response Philosophy

The Single-Instructor LMS backend guarantees that **100% of non-2xx HTTP responses** adhere to an identical JSON error envelope. Under no circumstances does the API return bare HTML error pages or unformatted strings.

```json
{
  "success": false,
  "error": {
    "code": "STRING_ERROR_CODE",
    "message": "Human-readable description for client display.",
    "details": {},
    "request_id": "req-9842a1bc-7832-4d0f-b12e-198273645012"
  }
}
```

---

## 2. Standard Error Codes Catalog

| HTTP Status | Error Code | Description / Trigger Scenario |
| :--- | :--- | :--- |
| **400 Bad Request** | `INVALID_INPUT` | Malformed parameters or business logic precondition failed |
| | `PASSWORD_TOO_WEAK` | Password does not satisfy complexity requirements |
| | `FILE_TOO_LARGE` | Uploaded asset exceeds permitted byte limit |
| | `MISSING_SIGNATURE` | Webhook request missing cryptographic signature header |
| **401 Unauthorized** | `UNAUTHENTICATED` | Missing session cookie or expired credentials |
| | `INVALID_CREDENTIALS`| Incorrect email or password provided |
| | `SESSION_REVOKED` | Session displaced by newer login on another device |
| | `TOKEN_EXPIRED` | Email verification or password reset token has expired |
| **403 Forbidden** | `PERMISSION_DENIED` | Caller lacks granular RBAC permission key |
| | `ACCOUNT_SUSPENDED` | User account locked by administrator |
| | `EMAIL_NOT_VERIFIED` | Mandatory email verification pending |
| | `NOT_ENROLLED` | Access to paid lesson denied due to missing enrollment |
| **404 Not Found** | `RESOURCE_NOT_FOUND` | Target entity does not exist or caller lacks access |
| **409 Conflict** | `CONCURRENT_CONFLICT` | Stale version collision during drag-and-drop reorder |
| | `EMAIL_EXISTS` | Registration email already exists in system |
| | `SLUG_EXISTS` | Course URL slug collision |
| | `ALREADY_ENROLLED` | Student already holds active course enrollment |
| **422 Unprocessable** | `VALIDATION_ERROR` | Pydantic payload schema violation |
| **429 Too Many Req** | `RATE_LIMIT_EXCEEDED` | Request frequency threshold exceeded |
| **500 Server Error** | `INTERNAL_ERROR` | Uncaught server exception (sanitized output) |

---

## 3. Exception Hierarchy Implementation

```python
class LMSBaseException(Exception):
    """Base exception for all domain and operational errors."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500, details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

class EntityNotFoundException(LMSBaseException):
    def __init__(self, entity_name: str, identifier: str):
        super().__init__(
            message=f"{entity_name} with identifier '{identifier}' was not found.",
            code=f"{entity_name.upper()}_NOT_FOUND",
            status_code=404
        )

class SessionRevokedException(LMSBaseException):
    def __init__(self):
        super().__init__(
            message="Your session has been terminated because your account was logged in from another device.",
            code="SESSION_REVOKED",
            status_code=401
        )

class ConcurrentEditConflictException(LMSBaseException):
    def __init__(self, message: str = "This resource was modified by another request. Please reload."):
        super().__init__(message=message, code="CONCURRENT_CONFLICT", status_code=409)

class PaymentVerificationException(LMSBaseException):
    def __init__(self, message: str):
        super().__init__(message=message, code="PAYMENT_VERIFICATION_FAILED", status_code=400)
```

---

## 4. Global Exception Handlers

In `app/core/error_handlers.py`, global handlers ensure every exception is transformed into the standard envelope:

```python
from fastapi import Request, FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging

logger = logging.getLogger("app.security")

def register_error_handlers(app: FastAPI):
    @app.exception_handler(LMSBaseException)
    async def lms_exception_handler(request: Request, exc: LMSBaseException):
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": false,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request_id
                }
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", "unknown")
        formatted_errors = [
            {"field": ".".join(str(loc) for loc in err["loc"]), "issue": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": false,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Input validation failed. Please inspect field details.",
                    "details": {"fields": formatted_errors},
                    "request_id": request_id
                }
            }
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception("Unhandled server crash [request_id=%s]: %s", request_id, str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": false,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected server error occurred. Please contact support with the request ID.",
                    "details": {},
                    "request_id": request_id
                }
            }
        )
```
