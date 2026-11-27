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
    CheckConstraint,
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
    from app.models.media import MediaAsset
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

# Canonical Course Difficulty Constants
DIFFICULTY_BEGINNER = "BEGINNER"
DIFFICULTY_INTERMEDIATE = "INTERMEDIATE"
DIFFICULTY_ADVANCED = "ADVANCED"
DIFFICULTY_ALL_LEVELS = "ALL_LEVELS"

VALID_DIFFICULTY_LEVELS = frozenset({
    DIFFICULTY_BEGINNER,
    DIFFICULTY_INTERMEDIATE,
    DIFFICULTY_ADVANCED,
    DIFFICULTY_ALL_LEVELS,
})

DIFFICULTY_LEVEL_LABELS: dict[str, str] = {
    DIFFICULTY_BEGINNER: "Beginner",
    DIFFICULTY_INTERMEDIATE: "Intermediate",
    DIFFICULTY_ADVANCED: "Advanced",
    DIFFICULTY_ALL_LEVELS: "All Levels",
}

DEFAULT_COURSE_CATEGORIES: tuple[str, ...] = (
    "Web Development",
    "Backend Engineering",
    "System Design",
    "Data Science & AI",
    "Mobile Development",
    "Cloud & DevOps",
    "Cybersecurity",
    "Programming Languages",
    "Career & Interview Prep",
    "General",
)

DEFAULT_COURSE_LANGUAGES: tuple[str, ...] = (
    "English",
    "Hindi",
    "Hinglish",
    "Spanish",
    "French",
    "German",
)

DEFAULT_CURRENCY_INR = "INR"

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
    thumbnail_media_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey(
            "media_assets.id",
            name="fk_courses_thumbnail_media_id_media_assets",
            ondelete="SET NULL",
        ),
        nullable=True,
        doc="Optional reference to uploaded MediaAsset representing the course thumbnail",
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="General",
        server_default=text("'General'"),
        index=True,
        doc="Primary instructional category for catalog discovery and filtering",
    )
    difficulty_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="ALL_LEVELS",
        server_default=text("'ALL_LEVELS'"),
        index=True,
        doc="Target learner proficiency level: BEGINNER, INTERMEDIATE, ADVANCED, or ALL_LEVELS",
    )
    language: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="English",
        server_default=text("'English'"),
        index=True,
        doc="Primary instruction language (e.g. English, Hindi, Hinglish)",
    )
    learning_outcomes: Mapped[List[str]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
        doc="Ordered list of structured learning outcomes ('What you will learn')",
    )
    requirements: Mapped[List[str]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
        doc="Ordered list of prerequisite knowledge or tools required before enrolling",
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
        doc="Effective selling commercial price in minor currency units (paise, 1 INR = 100 paise)",
    )
    compare_at_price_inr: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        doc="Optional regular/compare-at price in paise when a discounted selling price is active",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default=text("'INR'"),
        doc="ISO 4217 3-letter currency code (currently INR)",
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
    thumbnail_media: Mapped[Optional["MediaAsset"]] = relationship(
        "MediaAsset",
        foreign_keys=[thumbnail_media_id],
        lazy="select",
    )

    __table_args__ = (
        CheckConstraint("price_inr >= 0", name="price_non_negative"),
        CheckConstraint(
            "compare_at_price_inr IS NULL OR compare_at_price_inr > 0",
            name="compare_at_price_positive",
        ),
        CheckConstraint(
            "compare_at_price_inr IS NULL OR compare_at_price_inr >= price_inr",
            name="compare_at_ge_price",
        ),
        CheckConstraint(
            "NOT is_free OR (price_inr = 0 AND compare_at_price_inr IS NULL)",
            name="free_zero_price",
        ),
        CheckConstraint(
            "difficulty_level IN ('BEGINNER', 'INTERMEDIATE', 'ADVANCED', 'ALL_LEVELS')",
            name="difficulty_level",
        ),
    )

    @property
    def discount_percentage(self) -> Optional[int]:
        """Compute rounded discount percentage when compare_at_price_inr exceeds price_inr."""
        if (
            self.is_free
            or self.compare_at_price_inr is None
            or self.compare_at_price_inr <= 0
            or self.price_inr >= self.compare_at_price_inr
        ):
            return None
        pct = round(
            ((self.compare_at_price_inr - self.price_inr) / self.compare_at_price_inr)
            * 100
        )
        return pct if pct > 0 else None

    def __init__(self, **kwargs: Any) -> None:
        """Instantiate course with normalized metadata defaults."""
        if "slug" in kwargs and kwargs["slug"]:
            kwargs["slug"] = str(kwargs["slug"]).strip().lower()
        if "category" not in kwargs or not kwargs["category"]:
            kwargs["category"] = "General"
        else:
            kwargs["category"] = str(kwargs["category"]).strip()
        if "difficulty_level" not in kwargs or not kwargs["difficulty_level"]:
            kwargs["difficulty_level"] = DIFFICULTY_ALL_LEVELS
        if "language" not in kwargs or not kwargs["language"]:
            kwargs["language"] = "English"
        else:
            kwargs["language"] = str(kwargs["language"]).strip()
        if "learning_outcomes" not in kwargs or kwargs["learning_outcomes"] is None:
            kwargs["learning_outcomes"] = []
        else:
            kwargs["learning_outcomes"] = list(kwargs["learning_outcomes"])
        if "requirements" not in kwargs or kwargs["requirements"] is None:
            kwargs["requirements"] = []
        else:
            kwargs["requirements"] = list(kwargs["requirements"])
        if "currency" not in kwargs or not kwargs["currency"]:
            kwargs["currency"] = DEFAULT_CURRENCY_INR
        else:
            kwargs["currency"] = str(kwargs["currency"]).strip().upper()
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
