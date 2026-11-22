"""Assignment, Rubric, Submission, and Grade Override SQLAlchemy 2.0 models.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 3, Tables 14-19)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Section 1)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK701)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003, ADR-013)

Strict Invariants:
1. Lesson Coupling: One assignment configuration per curriculum lesson (lesson_id is UNIQUE).
2. Criteria Immutability: Once a student submission is graded, active rubric version is frozen.
3. Attempt Tracking: UNIQUE (assignment_id, student_id, attempt_no) strictly versions submissions.
4. Audited Grade Overrides: Super Admin grade overrides record original score, new score, and mandatory justification.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
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
    from app.models.curriculum import CurriculumLesson
    from app.models.user import User

# Submission Status Constants
SUBMISSION_STATUS_SUBMITTED = "SUBMITTED"
SUBMISSION_STATUS_GRADING = "GRADING"
SUBMISSION_STATUS_GRADED = "GRADED"
SUBMISSION_STATUS_REJECTED = "REJECTED"

VALID_SUBMISSION_STATUSES = frozenset({
    SUBMISSION_STATUS_SUBMITTED,
    SUBMISSION_STATUS_GRADING,
    SUBMISSION_STATUS_GRADED,
    SUBMISSION_STATUS_REJECTED,
})


class Assignment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Configuration for project and practical assignment submissions."""

    __tablename__ = "assignments"

    lesson_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("curriculum_lessons.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
        doc="Associated curriculum lesson foreign key",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Assignment headline or project name",
    )
    instructions: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Comprehensive markdown prompt and submission guidelines",
    )
    max_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=100.00,
        server_default=sa.text("100.00"),
        doc="Maximum possible score",
    )
    pass_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=50.00,
        server_default=sa.text("50.00"),
        doc="Minimum score required to pass",
    )
    allow_late: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
        doc="Whether student submissions are accepted past due_date",
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="UTC deadline timestamp for project submission",
    )

    # Relationships
    lesson: Mapped["CurriculumLesson"] = relationship(
        "CurriculumLesson",
        foreign_keys=[lesson_id],
        lazy="joined",
    )
    rubrics: Mapped[List["Rubric"]] = relationship(
        "Rubric",
        back_populates="assignment",
        cascade="all, delete-orphan",
        order_by="desc(Rubric.version)",
        lazy="selectin",
    )
    submissions: Mapped[List["AssignmentSubmission"]] = relationship(
        "AssignmentSubmission",
        back_populates="assignment",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Assignment id={self.id} title={self.title!r} max_score={self.max_score}>"


class AssignmentSubmission(Base, UUIDPrimaryKeyMixin):
    """Student project submission record, file upload link, and evaluation result."""

    __tablename__ = "assignment_submissions"

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("assignments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Target assignment foreign key",
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Submitting student user foreign key",
    )
    attempt_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=sa.text("1"),
        doc="Sequential submission attempt counter (1, 2, 3...)",
    )
    file_url: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        doc="Storage URL or key to student project archive/PDF in object storage",
    )
    text_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Optional student commentary or project context",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=SUBMISSION_STATUS_SUBMITTED,
        server_default=sa.text("'SUBMITTED'"),
        index=True,
        doc="Lifecycle status: SUBMITTED, GRADING, GRADED, REJECTED",
    )
    submitted_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when submission was uploaded",
    )
    final_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        doc="Calculated final score after rubric evaluation or override",
    )
    graded_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="UTC timestamp when grading was finalized",
    )
    graded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="Staff or Admin user UUID who evaluated this submission",
    )
    feedback: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Overall evaluator feedback and qualitative commentary",
    )

    # Relationships
    assignment: Mapped["Assignment"] = relationship(
        "Assignment",
        back_populates="submissions",
        foreign_keys=[assignment_id],
        lazy="joined",
    )
    student: Mapped["User"] = relationship(
        "User",
        foreign_keys=[student_id],
        lazy="joined",
    )
    grader: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[graded_by],
        lazy="joined",
    )
    rubric_scores: Mapped[List["RubricScore"]] = relationship(
        "RubricScore",
        back_populates="submission",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    grade_overrides: Mapped[List["GradeOverride"]] = relationship(
        "GradeOverride",
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="desc(GradeOverride.created_at)",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "student_id",
            "attempt_no",
            name="uq_assignment_submissions_attempt",
        ),
        Index("ix_assignment_submissions_assignment_student", "assignment_id", "student_id"),
        Index("ix_assignment_submissions_student_status", "student_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<AssignmentSubmission id={self.id} "
            f"assignment_id={self.assignment_id} "
            f"student_id={self.student_id} "
            f"attempt={self.attempt_no} "
            f"status={self.status!r}>"
        )


class Rubric(Base, UUIDPrimaryKeyMixin):
    """Grading criteria template version attached to an assignment."""

    __tablename__ = "rubrics"

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent assignment foreign key",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Rubric template title (e.g. 'Standard Coding & Architecture Rubric')",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=sa.text("1"),
        doc="Sequential rubric version counter",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa.text("true"),
        doc="True indicates the current active rubric used for new submissions",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when rubric version was created",
    )

    # Relationships
    assignment: Mapped["Assignment"] = relationship(
        "Assignment",
        back_populates="rubrics",
        foreign_keys=[assignment_id],
        lazy="joined",
    )
    criteria: Mapped[List["RubricCriteria"]] = relationship(
        "RubricCriteria",
        back_populates="rubric",
        cascade="all, delete-orphan",
        order_by="RubricCriteria.sort_order",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Rubric id={self.id} assignment_id={self.assignment_id} version={self.version} active={self.is_active}>"


class RubricCriteria(Base, UUIDPrimaryKeyMixin):
    """Individual grading dimension and point allocation within a rubric."""

    __tablename__ = "rubric_criteria"

    rubric_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("rubrics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent rubric foreign key",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Evaluation dimension title (e.g. 'Code Correctness', 'Concurrency Safety')",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Guidance notes for grading expectations",
    )
    max_points: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        doc="Maximum point ceiling for this criterion",
    )
    weight: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=1.00,
        server_default=sa.text("1.00"),
        doc="Multiplier weighting for score calculation",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
        doc="Relative sort ordering within rubric",
    )

    # Relationships
    rubric: Mapped["Rubric"] = relationship(
        "Rubric",
        back_populates="criteria",
        foreign_keys=[rubric_id],
        lazy="joined",
    )
    scores: Mapped[List["RubricScore"]] = relationship(
        "RubricScore",
        back_populates="criteria",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<RubricCriteria id={self.id} title={self.title!r} max_points={self.max_points} weight={self.weight}>"


class RubricScore(Base, UUIDPrimaryKeyMixin):
    """Criterion-level points and feedback awarded to a student submission."""

    __tablename__ = "rubric_scores"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("assignment_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Target student submission foreign key",
    )
    criteria_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("rubric_criteria.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Evaluated rubric criteria foreign key",
    )
    points_awarded: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        doc="Raw points awarded for this criterion",
    )
    feedback: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Specific feedback regarding this evaluation dimension",
    )

    # Relationships
    submission: Mapped["AssignmentSubmission"] = relationship(
        "AssignmentSubmission",
        back_populates="rubric_scores",
        foreign_keys=[submission_id],
        lazy="joined",
    )
    criteria: Mapped["RubricCriteria"] = relationship(
        "RubricCriteria",
        back_populates="scores",
        foreign_keys=[criteria_id],
        lazy="joined",
    )

    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "criteria_id",
            name="uq_rubric_scores_submission_criteria",
        ),
    )

    def __repr__(self) -> str:
        return f"<RubricScore submission_id={self.submission_id} criteria_id={self.criteria_id} points={self.points_awarded}>"


class GradeOverride(Base, UUIDPrimaryKeyMixin):
    """Immutable audit log of administrative grade adjustments."""

    __tablename__ = "grade_overrides"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("assignment_submissions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Overridden submission foreign key",
    )
    original_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        doc="Score prior to administrative override",
    )
    overridden_score: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        doc="New adjusted score applied by administrator",
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Mandatory justification note explaining score change",
    )
    overridden_by: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Admin user UUID who authorized this override",
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when override was recorded",
    )

    # Relationships
    submission: Mapped["AssignmentSubmission"] = relationship(
        "AssignmentSubmission",
        back_populates="grade_overrides",
        foreign_keys=[submission_id],
        lazy="joined",
    )
    overrider: Mapped["User"] = relationship(
        "User",
        foreign_keys=[overridden_by],
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<GradeOverride id={self.id} "
            f"submission_id={self.submission_id} "
            f"original={self.original_score} "
            f"new={self.overridden_score}>"
        )
