"""Pydantic v2 schemas for Platform Information & Settings (SA-05.3).

Architecture Specifications:
- SA-05 — Complete Commercial Governance (Section 5)
- docs/backend/06-API-ARCHITECTURE.md

Strict Invariants:
1. Master Secret Isolation: SECRET_KEY, DB passwords, Redis credentials,
   Razorpay secrets, SMTP passwords, and cloud storage keys are never exposed.
2. Only approved, safe editable platform fields are serialized.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, EmailStr


class PublicPlatformInfoResponse(BaseModel):
    """Safe, non-sensitive platform settings and system metadata."""
    model_config = ConfigDict(from_attributes=True)

    # General Platform Branding
    platform_name: str = Field(..., description="Platform display name")
    brand_name: str = Field(..., description="Instructor brand name")
    brand_description: Optional[str] = Field(None, description="Public platform description")
    support_email: Optional[str] = Field(None, description="Customer support email")
    support_phone: Optional[str] = Field(None, description="Customer support phone")
    logo_url: Optional[str] = Field(None, description="Platform logo asset URL")

    # Safe System Context (Read-Only)
    frontend_url: str = Field(..., description="Configured client origin")
    cdn_stream_base_url: str = Field(..., description="Video streaming CDN origin")
    version: str = Field(..., description="Application semver version")
    environment: str = Field(..., description="Current environment mode (development/staging/production)")
    currency: str = Field("INR", description="Primary platform currency")
    email_provider: str = Field(..., description="Configured transactional email provider")
    storage_provider: str = Field(..., description="Configured object storage provider")
    updated_at: Optional[datetime] = Field(None, description="Timestamp of last settings modification")


class PlatformSettingsUpdateRequest(BaseModel):
    """Payload for updating authorized platform and branding settings."""
    model_config = ConfigDict(extra="forbid")

    platform_name: Optional[str] = Field(None, min_length=1, max_length=255, description="Platform display title")
    brand_name: Optional[str] = Field(None, min_length=1, max_length=255, description="Brand name")
    brand_description: Optional[str] = Field(None, max_length=2000, description="Brand description")
    support_email: Optional[str] = Field(None, max_length=255, description="Support contact email")
    support_phone: Optional[str] = Field(None, max_length=32, description="Support contact phone")
    logo_url: Optional[str] = Field(None, max_length=1024, description="Logo image asset URL")
