"""Progress database models for lesson and course completion tracking.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Tables 29, 30)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Sections 1, 2)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901, TASK902)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)

Strict Invariants:
1. Student progress is granular per lesson and aggregated into materialized course summaries.
2. Unique constraints: UNIQUE(student_id, lesson_id) and UNIQUE(student_id, course_id).
3. Non-decreasing completion: Once a lesson is marked completed, it remains completed.
4. Server-Authoritative Evaluation: Video completes at >= 90% watch duration, quizzes upon pass.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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
    from app.models.curriculum import CurriculumLesson
    from app.models.user import User


class LessonProgress(Base, UUIDPrimaryKeyMixin):
    """Granular playback and completion tracking per student per lesson."""

    __tablename__ = "lesson_progress"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Enrolled student user foreign key",
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Curriculum lesson foreign key",
    )
    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
        doc="Whether this lesson meets completion criteria",
    )
    watch_position_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
        doc="Furthest playback position reached by student in seconds",
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="UTC timestamp when completion was achieved",
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        doc="UTC timestamp of last progress heartbeat",
    )

    __table_args__ = (
        UniqueConstraint("student_id", "lesson_id", name="uq_lesson_progress_student_lesson"),
        Index("ix_lesson_progress_student_completed", "student_id", "is_completed"),
    )

    # Relationships
    student: Mapped["User"] = relationship("User", lazy="joined")
    lesson: Mapped["CurriculumLesson"] = relationship("CurriculumLesson", lazy="joined")

    def __init__(self, **kwargs: Any) -> None:
        if "is_completed" not in kwargs or kwargs["is_completed"] is None:
            kwargs["is_completed"] = False
        if "watch_position_seconds" not in kwargs or kwargs["watch_position_seconds"] is None:
            kwargs["watch_position_seconds"] = 0
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<LessonProgress id={self.id} "
            f"student_id={self.student_id} "
            f"lesson_id={self.lesson_id} "
            f"is_completed={self.is_completed}>"
        )


class CourseProgressSummary(Base, UUIDPrimaryKeyMixin):
    """Materialized summary of course completion to avoid expensive aggregation queries."""

    __tablename__ = "course_progress_summaries"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Enrolled student user foreign key",
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Course container foreign key",
    )
    completed_lessons_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
        doc="Total completed lessons in course",
    )
    total_lessons_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
        doc="Total published lessons in course",
    )
    progress_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=sa.text("0.00"),
        doc="Calculated completion percentage (0.00 to 100.00)",
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        doc="UTC timestamp of last learner activity in course",
    )

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_course_progress_summaries_student_course"),
        Index("ix_course_progress_summaries_student_course", "student_id", "course_id"),
    )

    # Relationships
    student: Mapped["User"] = relationship("User", lazy="joined")
    course: Mapped["Course"] = relationship("Course", lazy="joined")

    def __init__(self, **kwargs: Any) -> None:
        if "completed_lessons_count" not in kwargs or kwargs["completed_lessons_count"] is None:
            kwargs["completed_lessons_count"] = 0
        if "total_lessons_count" not in kwargs or kwargs["total_lessons_count"] is None:
            kwargs["total_lessons_count"] = 0
        if "progress_percentage" not in kwargs or kwargs["progress_percentage"] is None:
            kwargs["progress_percentage"] = Decimal("0.00")
        super().__init__(**kwargs)

    @property
    def is_completed(self) -> bool:
        """Helper checking if course is 100% completed."""
        return self.progress_percentage >= Decimal("100.00")

    def __repr__(self) -> str:
        return (
            f"<CourseProgressSummary id={self.id} "
            f"student_id={self.student_id} "
            f"course_id={self.course_id} "
            f"progress={self.progress_percentage}%>"
        )
