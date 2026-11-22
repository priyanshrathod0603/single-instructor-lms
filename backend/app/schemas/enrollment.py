"""Pydantic v2 schemas for Student Course Enrollments.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 28)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.8)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK601, TASK603, TASK604)
"""

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class EnrollmentResponse(BaseModel):
    """Schema representing an enrollment record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    course_id: uuid.UUID
    order_id: Optional[uuid.UUID] = None
    status: str
    granted_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None
    course_title: Optional[str] = None
    course_slug: Optional[str] = None


class EnrollmentListResponse(BaseModel):
    """Paginated list envelope for course enrollments."""

    items: List[EnrollmentResponse]
    total: int
    page: int
    size: int


class ManualEnrollmentGrantRequest(BaseModel):
    """Payload for administrative manual enrollment provisioning."""

    student_id: uuid.UUID = Field(
        ...,
        description="Target student user UUID",
    )
    course_id: uuid.UUID = Field(
        ...,
        description="Target course UUID",
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="Optional expiration timestamp. None represents lifetime access.",
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional administrative justification or scholarship note",
    )


class EnrollmentRevokeRequest(BaseModel):
    """Payload for administrative enrollment revocation."""

    reason: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Mandatory business reason for revoking student access",
    )


class EnrollmentCheckResponse(BaseModel):
    """Quick boolean access verification envelope."""

    course_id: uuid.UUID
    is_enrolled: bool
    status: Optional[str] = None
    access_granted: bool
