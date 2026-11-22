"""Pydantic v2 schemas for certificate issuance, retrieval, and public verification.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.9)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Section 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901, TASK903, TASK904)
"""

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class CertificateResponse(BaseModel):
    """Authenticated student or administrative certificate response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    certificate_no: str
    student_id: uuid.UUID
    course_id: uuid.UUID
    issued_at: datetime
    verification_hash: str
    pdf_url: str
    is_revoked: bool = False
    student_name: Optional[str] = None
    course_title: Optional[str] = None
    verify_url: Optional[str] = None


class CertificateVerifyResponse(BaseModel):
    """Publicly accessible QR code certificate verification payload."""

    model_config = ConfigDict(from_attributes=True)

    verified: bool
    status: str = Field(default="VALID", description="'VALID', 'REVOKED', or 'INVALID'")
    certificate_no: Optional[str] = None
    student_name: Optional[str] = None
    course_title: Optional[str] = None
    issued_at: Optional[datetime] = None
    verification_hash: Optional[str] = None
    pdf_url: Optional[str] = None
    revoked_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None


class CertificateRevokeRequest(BaseModel):
    """Administrative payload for certificate revocation."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Audited justification for administrative certificate revocation",
    )
