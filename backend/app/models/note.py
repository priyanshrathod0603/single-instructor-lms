"""Note SQLAlchemy 2.0 persistence model for Notes CMS (SA-04).

Architecture Specifications:
- SA-04 — Complete Content & Course Governance (Section 5)
- docs/backend/04-DATABASE-ARCHITECTURE.md
- docs/backend/06-API-ARCHITECTURE.md
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf [Pages 1-16]

Strict Invariants:
1. Normalized Slug: Unique alphanumeric URL identifier.
2. PDF Reference: Document metadata and storage path tracked via MediaAsset reference;
   raw PDF binary is NEVER stored in PostgreSQL.
3. Canonical Statuses: DRAFT, PUBLISHED, ARCHIVED.
4. Author Attribution: Linked to User via author_id.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    utc_now,
)

if TYPE_CHECKING:
    from app.models.media import MediaAsset
    from app.models.user import User

# Canonical Note Status Constants
NOTE_STATUS_DRAFT = "DRAFT"
NOTE_STATUS_PUBLISHED = "PUBLISHED"
NOTE_STATUS_ARCHIVED = "ARCHIVED"

VALID_NOTE_STATUSES = frozenset({
    NOTE_STATUS_DRAFT,
    NOTE_STATUS_PUBLISHED,
    NOTE_STATUS_ARCHIVED,
})

# Default Note Categories
DEFAULT_NOTE_CATEGORIES = (
    "Cheatsheets",
    "Lecture Notes",
    "System Design",
    "Reference",
    "Guides",
    "General",
)


class Note(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Study note / PDF resource entity managed by Super Admin for student reference."""

    __tablename__ = "notes"

    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        doc="URL-friendly unique slug identifier",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Note display title",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Optional overview or summary of note contents",
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="General",
        server_default=text("'General'"),
        index=True,
        doc="Classification category",
    )
    pdf_media_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("media_assets.id", ondelete="SET NULL"),
        nullable=True,
        doc="Reference to underlying PDF MediaAsset entity",
    )
    pdf_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        doc="Storage path or direct download location for the PDF",
    )
    file_size_bytes: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        doc="Size of the attached PDF in bytes",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=NOTE_STATUS_DRAFT,
        server_default=text("'DRAFT'"),
        index=True,
        doc="Publication status: DRAFT, PUBLISHED, ARCHIVED",
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="Timestamp when note was published",
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="User ID of the author/creator",
    )

    # Relationships
    author: Mapped["User"] = relationship(
        "User",
        foreign_keys=[author_id],
        lazy="joined",
    )
    pdf_media: Mapped[Optional["MediaAsset"]] = relationship(
        "MediaAsset",
        foreign_keys=[pdf_media_id],
        lazy="select",
    )

    def publish(self) -> None:
        """Transition note to PUBLISHED state."""
        self.status = NOTE_STATUS_PUBLISHED
        self.published_at = utc_now()

    def unpublish(self) -> None:
        """Revert note to DRAFT state."""
        self.status = NOTE_STATUS_DRAFT

    def archive(self) -> None:
        """Retire note to ARCHIVED state."""
        self.status = NOTE_STATUS_ARCHIVED

    def __repr__(self) -> str:
        return (
            f"<Note id={self.id} "
            f"slug={self.slug!r} "
            f"status={self.status!r} "
            f"category={self.category!r}>"
        )
