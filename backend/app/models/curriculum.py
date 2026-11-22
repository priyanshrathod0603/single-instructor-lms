"""CurriculumSection, CurriculumLesson, and LessonResource SQLAlchemy 2.0 models.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 2, Tables 11, 12, 13)
- docs/backend/11-COURSE-MANAGEMENT.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK301)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003)

Strict Invariants:
1. Strict Hierarchy: Revision -> Section -> Lesson -> Resources.
2. Cascade Integrity: Deleting a section cascades to delete all child lessons and resources.
3. Drag-and-Drop Sequencing: sort_order (0-indexed integer) governs pedagogical order.
4. Preview Control: is_preview=True allows Visitor/unauthenticated public access.
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
    from app.models.course import CourseRevision

# Lesson Types
LESSON_TYPE_VIDEO = "VIDEO"
LESSON_TYPE_ARTICLE = "ARTICLE"
LESSON_TYPE_QUIZ = "QUIZ"
LESSON_TYPE_ASSIGNMENT = "ASSIGNMENT"

VALID_LESSON_TYPES = frozenset({
    LESSON_TYPE_VIDEO,
    LESSON_TYPE_ARTICLE,
    LESSON_TYPE_QUIZ,
    LESSON_TYPE_ASSIGNMENT,
})

# Resource Types
RESOURCE_TYPE_PDF = "PDF"
RESOURCE_TYPE_SOURCE_CODE = "SOURCE_CODE"
RESOURCE_TYPE_LINK = "LINK"
RESOURCE_TYPE_ASSET = "ASSET"

VALID_RESOURCE_TYPES = frozenset({
    RESOURCE_TYPE_PDF,
    RESOURCE_TYPE_SOURCE_CODE,
    RESOURCE_TYPE_LINK,
    RESOURCE_TYPE_ASSET,
})


class CurriculumSection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Logical curriculum module/chapter within a course revision."""

    __tablename__ = "curriculum_sections"

    course_revision_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("course_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent course revision foreign key",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Section title (e.g. 'Module 1: Distributed Concurrency')",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Optional section syllabus overview",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        doc="Relative 0-based sort ordering within the parent revision",
    )

    __table_args__ = (
        Index("ix_curriculum_sections_rev_order", "course_revision_id", "sort_order"),
    )

    # Relationships
    revision: Mapped["CourseRevision"] = relationship(
        "CourseRevision",
        back_populates="sections",
        lazy="joined",
    )
    lessons: Mapped[List["CurriculumLesson"]] = relationship(
        "CurriculumLesson",
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="CurriculumLesson.sort_order",
        lazy="selectin",
    )

    def __init__(self, **kwargs: Any) -> None:
        if "sort_order" not in kwargs or kwargs["sort_order"] is None:
            kwargs["sort_order"] = 0
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<CurriculumSection id={self.id} "
            f"revision_id={self.course_revision_id} "
            f"title={self.title!r} "
            f"order={self.sort_order}>"
        )


class CurriculumLesson(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Pedagogical learning unit (video, article, quiz, assignment)."""

    __tablename__ = "curriculum_lessons"

    section_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("curriculum_sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent section foreign key",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Lesson headline/title",
    )
    lesson_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=LESSON_TYPE_VIDEO,
        server_default=text("'VIDEO'"),
        doc="Category: VIDEO, ARTICLE, QUIZ, or ASSIGNMENT",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        doc="Relative 0-based sort ordering within the parent section",
    )
    duration_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        doc="Total estimated content duration in seconds",
    )
    is_preview: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        doc="Public preview flag; true allows unauthenticated visitor access",
    )
    content: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
        nullable=True,
        default=None,
        doc="Structured lesson content (markdown body, video player configuration, etc.)",
    )

    __table_args__ = (
        Index("ix_curriculum_lessons_section_order", "section_id", "sort_order"),
    )

    # Relationships
    section: Mapped["CurriculumSection"] = relationship(
        "CurriculumSection",
        back_populates="lessons",
        lazy="joined",
    )
    resources: Mapped[List["LessonResource"]] = relationship(
        "LessonResource",
        back_populates="lesson",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __init__(self, **kwargs: Any) -> None:
        if "lesson_type" not in kwargs or kwargs["lesson_type"] is None:
            kwargs["lesson_type"] = LESSON_TYPE_VIDEO
        if "sort_order" not in kwargs or kwargs["sort_order"] is None:
            kwargs["sort_order"] = 0
        if "duration_seconds" not in kwargs or kwargs["duration_seconds"] is None:
            kwargs["duration_seconds"] = 0
        if "is_preview" not in kwargs or kwargs["is_preview"] is None:
            kwargs["is_preview"] = False
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<CurriculumLesson id={self.id} "
            f"section_id={self.section_id} "
            f"type={self.lesson_type!r} "
            f"title={self.title!r} "
            f"order={self.sort_order}>"
        )


class LessonResource(Base, UUIDPrimaryKeyMixin):
    """Downloadable asset attached to a lesson (PDF, source code, asset link)."""

    __tablename__ = "lesson_resources"

    lesson_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("curriculum_lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent lesson foreign key",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Descriptive resource file label",
    )
    resource_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=RESOURCE_TYPE_PDF,
        server_default=text("'PDF'"),
        doc="Type: PDF, SOURCE_CODE, LINK, or ASSET",
    )
    file_url: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        doc="Public or presigned URL to the downloadable file",
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
        doc="Resource byte size for transfer estimation",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when resource was attached",
    )

    # Relationships
    lesson: Mapped["CurriculumLesson"] = relationship(
        "CurriculumLesson",
        back_populates="resources",
        lazy="joined",
    )

    def __init__(self, **kwargs: Any) -> None:
        if "resource_type" not in kwargs or kwargs["resource_type"] is None:
            kwargs["resource_type"] = RESOURCE_TYPE_PDF
        if "file_size_bytes" not in kwargs or kwargs["file_size_bytes"] is None:
            kwargs["file_size_bytes"] = 0
        if "created_at" not in kwargs or kwargs["created_at"] is None:
            kwargs["created_at"] = utc_now()
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<LessonResource id={self.id} "
            f"lesson_id={self.lesson_id} "
            f"type={self.resource_type!r} "
            f"title={self.title!r}>"
        )
