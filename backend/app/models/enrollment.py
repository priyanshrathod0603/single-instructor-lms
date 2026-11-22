"""Enrollment database model for student course access rights.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 28)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK601)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)

Strict Invariants:
1. Zero Trust on Browser Redirect: Granted strictly upon verified webhook or manual admin override.
2. Unique Active Enrollment: UNIQUE(student_id, course_id) prevents duplicate enrollment rows.
3. Access Expiration: Null expires_at indicates lifetime access; past expires_at denies access.
4. Clean Revocation: Status transitions to REVOKED with mandatory reason recorded.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    utc_now,
)

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.payment import Order
    from app.models.user import User

# Canonical enrollment status constants
ENROLLMENT_STATUS_ACTIVE = "ACTIVE"
ENROLLMENT_STATUS_REVOKED = "REVOKED"
ENROLLMENT_STATUS_EXPIRED = "EXPIRED"

ENROLLMENT_STATUSES = frozenset({
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_REVOKED,
    ENROLLMENT_STATUS_EXPIRED,
})


class Enrollment(Base, UUIDPrimaryKeyMixin):
    """Course access rights granted strictly upon verified payment or admin override."""

    __tablename__ = "enrollments"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Enrolled student user foreign key",
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Enrolled course foreign key",
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        doc="Associated commercial order; null for manual admin grant",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ENROLLMENT_STATUS_ACTIVE,
        server_default=sa.text("'ACTIVE'"),
        index=True,
        doc="Enrollment lifecycle status: ACTIVE, REVOKED, EXPIRED",
    )
    granted_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when course access was granted",
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="UTC timestamp when access expires; null indicates lifetime access",
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="UTC timestamp when access was revoked",
    )
    revoked_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Explanation for revocation (e.g. PAYMENT_REFUNDED, ADMINISTRATIVE_REVOCATION)",
    )

    # Relationships
    student: Mapped["User"] = relationship(
        "User",
        back_populates="enrollments",
        foreign_keys=[student_id],
        lazy="joined",
    )
    course: Mapped["Course"] = relationship(
        "Course",
        back_populates="enrollments",
        foreign_keys=[course_id],
        lazy="joined",
    )
    order: Mapped[Optional["Order"]] = relationship(
        "Order",
        foreign_keys=[order_id],
        lazy="joined",
    )

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_enrollments_student_id_course_id"),
        Index("ix_enrollments_student_status", "student_id", "status"),
        Index("ix_enrollments_course_status", "course_id", "status"),
    )

    @property
    def is_access_valid(self) -> bool:
        """Returns True if the enrollment is ACTIVE and has not expired."""
        if self.status != ENROLLMENT_STATUS_ACTIVE:
            return False
        if self.expires_at is not None and self.expires_at <= utc_now():
            return False
        return True

    def __repr__(self) -> str:
        return f"<Enrollment id={self.id} student_id={self.student_id} course_id={self.course_id} status={self.status!r}>"
