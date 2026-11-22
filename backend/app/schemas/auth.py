"""Pydantic request and response schemas for authentication and identity flows.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/08-SESSION-MANAGEMENT.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK104, TASK105, TASK106)

Strict Invariants:
1. Pure Pydantic v2 validation without optional external dependencies.
2. Email normalization and syntax validation using standard RFC pattern.
"""

from datetime import datetime
import re
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def validate_email_syntax(v: str) -> str:
    """Normalize and validate email syntax."""
    if not isinstance(v, str):
        raise ValueError("Email must be a string.")
    normalized = v.strip().lower()
    if not normalized or len(normalized) > 255:
        raise ValueError("Email must be between 1 and 255 characters.")
    if not EMAIL_REGEX.match(normalized):
        raise ValueError("Invalid email format.")
    return normalized


class UserRegisterRequest(BaseModel):
    """Payload for student registration."""

    email: str = Field(..., max_length=255, description="Student email address.")
    password: str = Field(..., min_length=12, max_length=128, description="Raw plaintext password.")
    full_name: str = Field(..., min_length=2, max_length=128, description="Student full display name.")

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_syntax(v)


class UserLoginRequest(BaseModel):
    """Payload for credentials authentication."""

    email: str = Field(..., max_length=255, description="Account email address.")
    password: str = Field(..., min_length=1, max_length=128, description="Account password.")

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_syntax(v)


class UserResponse(BaseModel):
    """Public representation of an authenticated user entity."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="User unique identifier.")
    email: str = Field(..., description="Normalized email address.")
    full_name: str = Field(..., description="Full display name.")
    avatar_url: Optional[str] = Field(None, description="Public avatar URL.")
    is_verified: bool = Field(..., description="Email verification status.")
    is_active: bool = Field(..., description="Account active status.")
    roles: list[str] = Field(default_factory=list, description="Assigned role identifiers.")
    created_at: datetime = Field(..., description="Creation UTC timestamp.")


class LoginResponse(BaseModel):
    """Response returned upon successful authentication."""

    user: UserResponse = Field(..., description="Authenticated user profile.")
    access_token: str = Field(..., description="Short-lived JWT bearer access token.")
    token_type: str = Field(default="bearer", description="Token authorization type.")
    expires_in: int = Field(default=900, description="Access token lifespan in seconds (15 minutes).")


class VerifyEmailRequest(BaseModel):
    """Payload for email address verification."""

    token: str = Field(..., min_length=16, description="Cryptographic verification token received via email.")


class ResendVerificationRequest(BaseModel):
    """Payload to request re-delivery of verification email."""

    email: str = Field(..., max_length=255, description="Registered account email address.")

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_syntax(v)


class PasswordResetRequest(BaseModel):
    """Payload to initiate a password reset request."""

    email: str = Field(..., max_length=255, description="Account email address to receive reset instructions.")

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_syntax(v)


class PasswordResetConfirmRequest(BaseModel):
    """Payload to complete password reset."""

    token: str = Field(..., min_length=16, description="Cryptographic password reset token.")
    new_password: str = Field(..., min_length=12, max_length=128, description="New compliant password.")


class GoogleOAuthRequest(BaseModel):
    """Payload for Google Identity OAuth 2.0 exchange."""

    id_token: str = Field(..., min_length=16, description="Google Identity OIDC JWT ID token.")


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str = Field(..., description="Informational message.")
