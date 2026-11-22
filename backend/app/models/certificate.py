"""Certificate database model for digitally verifiable proof of course completion.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 31)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Section 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901, TASK903, TASK904)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)

Strict Invariants:
1. Issued strictly upon 100% course completion and active enrollment.
2. Unique constraints: UNIQUE(certificate_no), UNIQUE(verification_hash), UNIQUE(student_id, course_id).
3. Cryptographic Verification: Verification hash computed via HMAC-SHA256.
4. Permanent & Audited: Certificates cannot be casually modified; revocations are permanently logged.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
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
    from app.models.user import User


class Certificate(Base, UUIDPrimaryKeyMixin):
    """Digitally verifiable proof of course completion."""

    __tablename__ = "certificates"

    certificate_no: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True,
        doc="Human-readable certificate identifier (e.g. CERT-202611-9842)",
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Certified student user foreign key",
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Completed course foreign key",
    )
    issued_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when certificate was issued",
    )
    verification_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        doc="HMAC-SHA256 signature hash for public QR verification",
    )
    pdf_url: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        doc="Object storage URL / key for immutable certificate PDF",
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
        doc="Whether this certificate has been administratively revoked",
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="UTC timestamp of certificate revocation",
    )
    revoked_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Audited justification for administrative certificate revocation",
    )

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_certificates_student_course"),
        Index("ix_certificates_student_course", "student_id", "course_id"),
    )

    # Relationships
    student: Mapped["User"] = relationship("User", lazy="joined")
    course: Mapped["Course"] = relationship("Course", lazy="joined")

    def __init__(self, **kwargs: Any) -> None:
        if "is_revoked" not in kwargs or kwargs["is_revoked"] is None:
            kwargs["is_revoked"] = False
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<Certificate id={self.id} "
            f"certificate_no={self.certificate_no!r} "
            f"student_id={self.student_id} "
            f"course_id={self.course_id} "
            f"is_revoked={self.is_revoked}>"
        )
