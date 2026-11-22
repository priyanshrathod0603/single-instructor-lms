"""Pydantic v2 schemas for Commercial Offers Management (SA-05.1).

Architecture Specifications:
- SA-05 — Complete Commercial Governance (Section 3)
- docs/backend/06-API-ARCHITECTURE.md
"""

from datetime import datetime
from typing import Any, List, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OfferCourseSummary(BaseModel):
    """Minimal representation of a course attached to an offer."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    slug: str


class OfferCreatorSummary(BaseModel):
    """Minimal representation of Super Admin who created the offer."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str


class OfferCreateRequest(BaseModel):
    """Payload for creating a new promotional offer."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255, description="Promotional offer title")
    code: str = Field(..., min_length=2, max_length=64, description="Unique uppercase coupon/promo code")
    description: Optional[str] = Field(None, max_length=2000, description="Campaign description")
    discount_type: Literal["PERCENTAGE", "FIXED"] = Field(..., description="Discount type")
    discount_value: int = Field(..., ge=1, description="Discount amount: 1-100 for PERCENTAGE, or paise for FIXED")
    course_id: Optional[uuid.UUID] = Field(None, description="Course scope (null = platform-wide)")
    valid_from: datetime = Field(..., description="Start date timestamp")
    valid_to: datetime = Field(..., description="Expiry date timestamp")
    usage_limit: Optional[int] = Field(None, ge=1, description="Max usage redemptions")
    status: Optional[Literal["ACTIVE", "INACTIVE", "ARCHIVED"]] = Field("ACTIVE", description="Initial lifecycle status")

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        code = v.strip().upper()
        if not code:
            raise ValueError("Offer code cannot be empty")
        import re
        if not re.match(r"^[A-Z0-9_\-]+$", code):
            raise ValueError("Offer code must contain only alphanumeric characters, underscores, or hyphens")
        return code

    @model_validator(mode="after")
    def validate_offer(self) -> "OfferCreateRequest":
        if self.valid_to <= self.valid_from:
            raise ValueError("Expiry date (valid_to) must be strictly after start date (valid_from)")
        if self.discount_type == "PERCENTAGE" and (self.discount_value < 1 or self.discount_value > 100):
            raise ValueError("Percentage discount value must be between 1 and 100 percent")
        if self.discount_type == "FIXED" and self.discount_value <= 0:
            raise ValueError("Fixed discount value must be a positive amount in paise")
        return self


class OfferUpdateRequest(BaseModel):
    """Payload for updating an existing promotional offer."""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    discount_type: Optional[Literal["PERCENTAGE", "FIXED"]] = None
    discount_value: Optional[int] = Field(None, ge=1)
    course_id: Optional[uuid.UUID] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    usage_limit: Optional[int] = Field(None, ge=1)
    status: Optional[Literal["ACTIVE", "INACTIVE", "ARCHIVED"]] = None

    @model_validator(mode="after")
    def validate_update(self) -> "OfferUpdateRequest":
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("Expiry date (valid_to) must be strictly after start date (valid_from)")
        if self.discount_type == "PERCENTAGE" and self.discount_value is not None:
            if self.discount_value < 1 or self.discount_value > 100:
                raise ValueError("Percentage discount value must be between 1 and 100 percent")
        if self.discount_type == "FIXED" and self.discount_value is not None:
            if self.discount_value <= 0:
                raise ValueError("Fixed discount value must be a positive amount in paise")
        return self


class OfferStatusRequest(BaseModel):
    """Quick lifecycle status toggle request."""
    model_config = ConfigDict(extra="forbid")

    status: Literal["ACTIVE", "INACTIVE", "ARCHIVED"]


class OfferResponse(BaseModel):
    """Detailed response model for a single promotional offer."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    description: Optional[str] = None
    discount_type: str
    discount_value: int
    course_id: Optional[uuid.UUID] = None
    course: Optional[OfferCourseSummary] = None
    valid_from: datetime
    valid_to: datetime
    usage_limit: Optional[int] = None
    times_used: int
    status: str
    created_by_id: uuid.UUID
    creator: Optional[OfferCreatorSummary] = None
    created_at: datetime
    updated_at: datetime


class OfferListResponse(BaseModel):
    """Paginated list of promotional offers."""
    model_config = ConfigDict(from_attributes=True)

    items: List[OfferResponse]
    total: int
    page: int
    per_page: int
    pages: int
