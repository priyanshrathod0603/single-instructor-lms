"""Course, CourseRevision, and CourseTag SQLAlchemy 2.0 persistence models.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 2, Tables 8, 9, 10)
- docs/backend/11-COURSE-MANAGEMENT.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK301)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003, ADR-005)

Strict Invariants:
1. Immutability: Published revisions are permanently frozen; authoring occurs in draft revisions.
2. Snapshotting: Published revisions preserve complete frozen curriculum in JSONB snapshot.
3. Minor Currency: price_inr stored in integer paise (1 INR = 100 paise), avoiding float errors.
4. Slug Uniqueness: Normalized case-insensitive uniqueness across course containers.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    utc_now,
)

if TYPE_CHECKING:
    from app.models.curriculum import CurriculumSection
    from app.models.enrollment import Enrollment
    from app.models.payment import Order
    from app.models.user import User

# Canonical Course Status Constants
COURSE_STATUS_DRAFT = "DRAFT"
COURSE_STATUS_PUBLISHED = "PUBLISHED"
COURSE_STATUS_ARCHIVED = "ARCHIVED"

VALID_COURSE_STATUSES = frozenset({
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    COURSE_STATUS_ARCHIVED,
})

# Canonical Revision Status Constants
REVISION_STATUS_DRAFT = "DRAFT"
REVISION_STATUS_PUBLISHED = "PUBLISHED"
REVISION_STATUS_ARCHIVED = "ARCHIVED"

VALID_REVISION_STATUSES = frozenset({
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
    REVISION_STATUS_ARCHIVED,
})


class Course(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Top-level course container for direct course commercialization."""

    __tablename__ = "courses"

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
        doc="Public course display title",
    )
    headline: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        doc="Short marketing subtitle or value proposition",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Comprehensive markdown syllabus and course description",
    )
    thumbnail_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        doc="Public CDN URL to thumbnail image asset in object storage",
    )
    live_revision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey(
            "course_revisions.id",
            use_alter=True,
            name="fk_courses_live_revision_id_course_revisions",
            ondelete="SET NULL",
        ),
        nullable=True,
        doc="Pointer to currently active published revision consumed by enrolled students",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=COURSE_STATUS_DRAFT,
        server_default=text("'DRAFT'"),
        index=True,
        doc="Container lifecycle state: DRAFT, PUBLISHED, or ARCHIVED",
    )
    price_inr: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
        doc="Commercial price in minor currency units (paise, 1 INR = 100 paise)",
    )
    is_free: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        doc="Toggle flag indicating whether course is free of charge",
    )

    # Relationships
    revisions: Mapped[List["CourseRevision"]] = relationship(
        "CourseRevision",
        foreign_keys="CourseRevision.course_id",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CourseRevision.revision_no",
        lazy="select",
    )
    live_revision: Mapped[Optional["CourseRevision"]] = relationship(
        "CourseRevision",
        foreign_keys=[live_revision_id],
        lazy="joined",
        post_update=True,
    )
    tags: Mapped[List["CourseTag"]] = relationship(
        "CourseTag",
        back_populates="course",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    orders: Mapped[List["Order"]] = relationship(
        "Order",
        back_populates="course",
        foreign_keys="Order.course_id",
        lazy="select",
    )
    enrollments: Mapped[List["Enrollment"]] = relationship(
        "Enrollment",
        back_populates="course",
        foreign_keys="Enrollment.course_id",
        lazy="select",
    )

    def __init__(self, **kwargs: Any) -> None:
        """Instantiate course with normalized lowercase slug and default timestamps."""
        if "slug" in kwargs and kwargs["slug"]:
            kwargs["slug"] = str(kwargs["slug"]).strip().lower()
        if "price_inr" not in kwargs or kwargs["price_inr"] is None:
            kwargs["price_inr"] = 0
        if "is_free" not in kwargs or kwargs["is_free"] is None:
            kwargs["is_free"] = False
        if "status" not in kwargs or kwargs["status"] is None:
            kwargs["status"] = COURSE_STATUS_DRAFT
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<Course id={self.id} "
            f"slug={self.slug!r} "
            f"status={self.status!r} "
            f"price_inr={self.price_inr}>"
        )


class CourseRevision(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Versioned, immutable curriculum revision tree and frozen snapshot."""

    __tablename__ = "course_revisions"

    course_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("courses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Parent course container foreign key",
    )
    revision_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Sequential revision counter (1, 2, 3...)",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=REVISION_STATUS_DRAFT,
        server_default=text("'DRAFT'"),
        index=True,
        doc="Revision authoring state: DRAFT, PUBLISHED, or ARCHIVED",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Revision-specific course title snapshot",
    )
    changelog: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Summary of pedagogical curriculum updates introduced in this revision",
    )
    snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
        nullable=True,
        default=None,
        doc="Complete frozen curriculum tree serialized into JSONB upon publication",
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="UTC timestamp when this revision was published and frozen",
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        doc="Admin user UUID who spawned this revision",
    )

    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "revision_no",
            name="uq_course_revisions_course_id_revision_no",
        ),
        Index("ix_course_revisions_course_status", "course_id", "status"),
    )

    # Relationships
    course: Mapped["Course"] = relationship(
        "Course",
        foreign_keys=[course_id],
        back_populates="revisions",
        lazy="joined",
    )
    sections: Mapped[List["CurriculumSection"]] = relationship(
        "CurriculumSection",
        back_populates="revision",
        cascade="all, delete-orphan",
        order_by="CurriculumSection.sort_order",
        lazy="selectin",
    )

    def __init__(self, **kwargs: Any) -> None:
        """Instantiate revision with default DRAFT state and timestamps."""
        if "status" not in kwargs or kwargs["status"] is None:
            kwargs["status"] = REVISION_STATUS_DRAFT
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<CourseRevision id={self.id} "
            f"course_id={self.course_id} "
            f"revision_no={self.revision_no} "
            f"status={self.status!r}>"
        )


class CourseTag(Base):
    """Search and categorization tags for course discovery."""

    __tablename__ = "course_tags"

    course_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
        doc="Associated course container foreign key",
    )
    tag: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        doc="Search keyword or category tag (normalized lowercase)",
    )

    # Relationships
    course: Mapped["Course"] = relationship("Course", back_populates="tags", lazy="joined")

    def __init__(self, **kwargs: Any) -> None:
        if "tag" in kwargs and kwargs["tag"]:
            kwargs["tag"] = str(kwargs["tag"]).strip().lower()
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<CourseTag course_id={self.course_id} tag={self.tag!r}>"
