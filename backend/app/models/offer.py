"""Offer SQLAlchemy 2.0 model for Commercial Governance (SA-05.1).

Architecture Specifications:
- SA-05 — Complete Commercial Governance (Section 3)
- docs/backend/04-DATABASE-ARCHITECTURE.md
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf

Strict Invariants:
1. Canonical Statuses: ACTIVE, INACTIVE, ARCHIVED.
2. Discount Types: PERCENTAGE (1-100), FIXED (in minor units / paise).
3. Date Validity: valid_to must be >= valid_from.
4. Unique Code: Normalized uppercase coupon/offer code.
5. Administrative Configuration: SA-05 manages commercial offers administratively;
   no student-facing checkout application is performed in this module.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.user import User

# Canonical Discount Type Constants
DISCOUNT_TYPE_PERCENTAGE = "PERCENTAGE"
DISCOUNT_TYPE_FIXED = "FIXED"

VALID_DISCOUNT_TYPES = frozenset({
    DISCOUNT_TYPE_PERCENTAGE,
    DISCOUNT_TYPE_FIXED,
})

# Canonical Offer Status Constants
OFFER_STATUS_ACTIVE = "ACTIVE"
OFFER_STATUS_INACTIVE = "INACTIVE"
OFFER_STATUS_ARCHIVED = "ARCHIVED"

VALID_OFFER_STATUSES = frozenset({
    OFFER_STATUS_ACTIVE,
    OFFER_STATUS_INACTIVE,
    OFFER_STATUS_ARCHIVED,
})


class Offer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Commercial offer / promotional discount entity managed by Super Admin."""

    __tablename__ = "offers"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Human-readable title of the promotional offer (e.g. 'Diwali Special 2026')",
    )
    code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        doc="Unique uppercase promo code (e.g. 'DIWALI50')",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Optional administrative description or marketing campaign note",
    )
    discount_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DISCOUNT_TYPE_PERCENTAGE,
        doc="Discount category: PERCENTAGE (1-100) or FIXED (paise)",
    )
    discount_value: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Discount amount: 1-100 for PERCENTAGE, or integer paise for FIXED",
    )
    course_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Target course ID if scoped to specific course; NULL if platform-wide",
    )
    valid_from: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        doc="UTC timestamp when offer becomes effective",
    )
    valid_to: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        doc="UTC timestamp when offer expires",
    )
    usage_limit: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Maximum allowed redemptions (optional cap)",
    )
    times_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
        doc="Number of times this offer has been redeemed",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=OFFER_STATUS_ACTIVE,
        server_default=sa.text("'ACTIVE'"),
        index=True,
        doc="Lifecycle status: ACTIVE, INACTIVE, ARCHIVED",
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Super Admin who created this offer",
    )

    # Relationships
    course: Mapped[Optional["Course"]] = relationship(
        "Course",
        lazy="joined",
    )
    creator: Mapped["User"] = relationship(
        "User",
        foreign_keys=[created_by_id],
        lazy="joined",
    )

    __table_args__ = (
        Index("ix_offers_status_validity", "status", "valid_from", "valid_to"),
    )

    def __repr__(self) -> str:
        return f"<Offer id={self.id} code={self.code!r} status={self.status!r} type={self.discount_type!r}>"
