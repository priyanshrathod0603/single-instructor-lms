"""Pydantic schemas for User Management, Staff Onboarding, and RBAC Administration.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Sections 2.2, 3.1)
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md
- docs/backend/10-USER-MANAGEMENT.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK203, TASK204)
"""

from datetime import datetime
import re
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.user import ROLE_ADMIN, ROLE_STAFF, SYSTEM_ROLES

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE_REGEX = re.compile(r"^\+?[0-9\s\-().]{7,32}$")


def validate_email_syntax(v: str) -> str:
    """Validate email format without requiring external packages."""
    if not isinstance(v, str):
        raise ValueError("Email must be a string")
    cleaned = v.strip().lower()
    if not cleaned or not EMAIL_REGEX.match(cleaned):
        raise ValueError("Invalid email format")
    return cleaned


def validate_phone_syntax(v: str) -> str:
    """Validate phone format ensuring proper structure and digit count."""
    if not isinstance(v, str):
        raise ValueError("Phone number must be a string")
    cleaned = v.strip()
    if not cleaned:
        raise ValueError("Phone number cannot be blank")
    if not PHONE_REGEX.match(cleaned):
        raise ValueError("Invalid phone number format")
    digits = sum(1 for c in cleaned if c.isdigit())
    if digits < 7 or digits > 15:
        raise ValueError("Phone number must contain between 7 and 15 digits")
    return cleaned


class UserProfileResponse(BaseModel):
    """Detailed user profile response with assigned roles and aggregated permissions."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_verified: bool
    is_active: bool
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class UserDirectoryItemResponse(BaseModel):
    """User summary item for paginated directory lists."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_verified: bool
    is_active: bool
    roles: list[str] = Field(default_factory=list)
    created_at: datetime


class UserCreateRequest(BaseModel):
    """Request payload for Super Admin user creation."""
    full_name: str = Field(..., min_length=1, max_length=128, description="User full display name")
    email: str = Field(..., max_length=255, description="User email address")
    phone: str = Field(..., min_length=7, max_length=32, description="Contact phone number")
    password: str = Field(..., min_length=12, max_length=128, description="Plaintext password")
    role: str = Field(..., description="Assigned role: SUPER_ADMIN, ADMIN, STAFF, or STUDENT")

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_syntax(v)

    @field_validator("full_name")
    @classmethod
    def check_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Full name cannot be blank")
        return cleaned

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        return validate_phone_syntax(v)

    @field_validator("role")
    @classmethod
    def check_role(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if cleaned not in ("SUPER_ADMIN", "ADMIN", "STAFF", "STUDENT"):
            raise ValueError("Role must be one of: SUPER_ADMIN, ADMIN, STAFF, STUDENT")
        return cleaned


class UserDirectoryResponse(BaseModel):
    """Paginated user directory response envelope."""
    items: list[UserDirectoryItemResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class UserProfileUpdateRequest(BaseModel):
    """Request payload for updating user profile fields."""
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    avatar_url: Optional[str] = Field(default=None, max_length=512)

    @field_validator("full_name")
    @classmethod
    def sanitize_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Full name cannot be blank")
            return cleaned
        return v

    @field_validator("avatar_url")
    @classmethod
    def validate_avatar_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                return None
            if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
                raise ValueError("Avatar URL must begin with http:// or https://")
            return cleaned
        return v


class UserStatusUpdateRequest(BaseModel):
    """Request payload for administrative user activation/suspension."""
    is_active: bool
    reason: Optional[str] = Field(default=None, max_length=500)


class StaffInviteRequest(BaseModel):
    """Request payload for inviting a new staff member or administrator."""
    email: str = Field(..., max_length=255)
    full_name: str = Field(..., min_length=1, max_length=128)
    role: str = Field(default=ROLE_STAFF)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_syntax(v)

    @field_validator("full_name")
    @classmethod
    def check_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Full name cannot be blank")
        return cleaned

    @field_validator("role")
    @classmethod
    def check_role(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if cleaned not in (ROLE_STAFF, ROLE_ADMIN):
            raise ValueError(f"Role must be either '{ROLE_STAFF}' or '{ROLE_ADMIN}'")
        return cleaned


class StaffOnboardingClaimRequest(BaseModel):
    """Request payload for claiming a staff onboarding invitation and setting password."""
    token: str = Field(..., min_length=10, max_length=255)
    password: str = Field(..., min_length=12, max_length=128)


class UserRoleUpdateRequest(BaseModel):
    """Request payload for assigning or revoking a user role."""
    role_id: str = Field(..., max_length=32)
    action: str = Field(..., description="Action to perform: 'ASSIGN' or 'REVOKE'")

    @field_validator("role_id")
    @classmethod
    def check_role_id(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if cleaned not in SYSTEM_ROLES:
            raise ValueError(f"Unknown system role: {cleaned}")
        return cleaned

    @field_validator("action")
    @classmethod
    def check_action(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if cleaned not in ("ASSIGN", "REVOKE"):
            raise ValueError("Action must be either 'ASSIGN' or 'REVOKE'")
        return cleaned


class StudentEnrollmentSummary(BaseModel):
    """Student course enrollment summary with calculated progress."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    course_title: str
    course_slug: Optional[str] = None
    status: str
    granted_at: datetime
    expires_at: Optional[datetime] = None
    progress_percentage: float = 0.0
    completed_lessons_count: int = 0
    total_lessons_count: int = 0
    last_activity_at: Optional[datetime] = None


class StudentQuizAttemptSummary(BaseModel):
    """Student quiz attempt summary."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quiz_id: uuid.UUID
    quiz_title: str
    attempt_no: int
    status: str
    score: Optional[float] = None
    is_passed: Optional[bool] = None
    started_at: datetime
    completed_at: Optional[datetime] = None


class StudentAssignmentSubmissionSummary(BaseModel):
    """Student assignment submission summary."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assignment_id: uuid.UUID
    assignment_title: str
    attempt_no: int
    status: str
    final_score: Optional[float] = None
    max_score: float = 100.0
    pass_score: float = 50.0
    file_url: str
    submitted_at: datetime
    graded_at: Optional[datetime] = None
    feedback: Optional[str] = None


class StudentCertificateSummary(BaseModel):
    """Student verifiable certificate summary."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    certificate_no: str
    course_id: uuid.UUID
    course_title: str
    issued_at: datetime
    verification_hash: str
    pdf_url: str
    is_revoked: bool = False
    revoked_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None


class StudentLearningSummaryResponse(BaseModel):
    """Aggregated academic and audit ledger for a student user."""
    user: UserProfileResponse
    enrollments: list[StudentEnrollmentSummary] = Field(default_factory=list)
    quiz_attempts: list[StudentQuizAttemptSummary] = Field(default_factory=list)
    assignment_submissions: list[StudentAssignmentSubmissionSummary] = Field(default_factory=list)
    certificates: list[StudentCertificateSummary] = Field(default_factory=list)
    audit_logs: list[dict[str, Any]] = Field(default_factory=list)

