"""BlogPost SQLAlchemy 2.0 persistence model for Blog CMS (SA-04).

Architecture Specifications:
- SA-04 — Complete Content & Course Governance (Section 4)
- docs/backend/04-DATABASE-ARCHITECTURE.md
- docs/backend/06-API-ARCHITECTURE.md
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf [Pages 1-16]

Strict Invariants:
1. Normalized Slug: Lowercase alphanumeric with hyphens, strictly unique across posts.
2. Canonical Statuses: DRAFT, PUBLISHED, ARCHIVED.
3. Publication Timestamps: published_at populated when transitioning to PUBLISHED.
4. Author Attribution: Linked to User via author_id.
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

# Canonical Blog Post Status Constants
BLOG_STATUS_DRAFT = "DRAFT"
BLOG_STATUS_PUBLISHED = "PUBLISHED"
BLOG_STATUS_ARCHIVED = "ARCHIVED"

VALID_BLOG_STATUSES = frozenset({
    BLOG_STATUS_DRAFT,
    BLOG_STATUS_PUBLISHED,
    BLOG_STATUS_ARCHIVED,
})

# Default Blog Categories
DEFAULT_BLOG_CATEGORIES = (
    "Tutorials",
    "Architecture",
    "Deep Learning",
    "Engineering",
    "Announcements",
    "General",
)


class BlogPost(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Blog post entity managed by Super Admin for platform content publishing."""

    __tablename__ = "blog_posts"

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
        doc="Blog post headline title",
    )
    excerpt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Optional brief summary or lead paragraph",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Full article body content (Markdown)",
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="General",
        server_default=text("'General'"),
        index=True,
        doc="Classification category",
    )
    thumbnail_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        doc="Public CDN URL or object storage path to thumbnail asset",
    )
    thumbnail_media_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("media_assets.id", ondelete="SET NULL"),
        nullable=True,
        doc="Optional reference to underlying MediaAsset entity",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=BLOG_STATUS_DRAFT,
        server_default=text("'DRAFT'"),
        index=True,
        doc="Publication status: DRAFT, PUBLISHED, ARCHIVED",
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="Timestamp when post was first or most recently published",
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
    thumbnail_media: Mapped[Optional["MediaAsset"]] = relationship(
        "MediaAsset",
        foreign_keys=[thumbnail_media_id],
        lazy="select",
    )

    def publish(self) -> None:
        """Transition blog post to PUBLISHED state."""
        self.status = BLOG_STATUS_PUBLISHED
        self.published_at = utc_now()

    def unpublish(self) -> None:
        """Revert blog post to DRAFT state."""
        self.status = BLOG_STATUS_DRAFT

    def archive(self) -> None:
        """Retire blog post to ARCHIVED state."""
        self.status = BLOG_STATUS_ARCHIVED

    def __repr__(self) -> str:
        return (
            f"<BlogPost id={self.id} "
            f"slug={self.slug!r} "
            f"status={self.status!r} "
            f"category={self.category!r}>"
        )
