"""Quiz, Question, Option, Attempt, and Answer models for LMS assessments.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 4, Tables 20-24)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.6)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Sections 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK801-TASK805)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-008, ADR-011, ADR-012, ADR-013)

Strict Invariants:
1. Server-Authoritative Timers (ADR-011): Quiz deadline is calculated and enforced on the server.
2. Anti-Cheating & Answer Protection: Correct answers and explanations are never exposed during an attempt.
3. Unique Attempt Versioning: UNIQUE(quiz_id, student_id, attempt_no) strictly tracks learner attempts.
4. Autosave Idempotency: UNIQUE(attempt_id, question_id) ensures single response record per question.
5. Enrollment Gate: Attempts are restricted to students with an active, unexpired course enrollment.
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
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
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
    from app.models.curriculum import CurriculumLesson
    from app.models.user import User

# Question types
QUESTION_TYPE_MCQ_SINGLE = "MCQ_SINGLE"
QUESTION_TYPE_MCQ_MULTI = "MCQ_MULTI"
QUESTION_TYPE_TRUE_FALSE = "TRUE_FALSE"
QUESTION_TYPE_TEXT_SHORT = "TEXT_SHORT"

QUESTION_TYPES = frozenset({
    QUESTION_TYPE_MCQ_SINGLE,
    QUESTION_TYPE_MCQ_MULTI,
    QUESTION_TYPE_TRUE_FALSE,
    QUESTION_TYPE_TEXT_SHORT,
})

# Quiz attempt lifecycle statuses
ATTEMPT_STATUS_IN_PROGRESS = "IN_PROGRESS"
ATTEMPT_STATUS_SUBMITTED = "SUBMITTED"
ATTEMPT_STATUS_EXPIRED = "EXPIRED"

ATTEMPT_STATUSES = frozenset({
    ATTEMPT_STATUS_IN_PROGRESS,
    ATTEMPT_STATUS_SUBMITTED,
    ATTEMPT_STATUS_EXPIRED,
})


class Quiz(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Assessment configuration attached to a curriculum lesson."""

    __tablename__ = "quizzes"

    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("curriculum_lessons.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
        index=True,
        doc="Curriculum lesson foreign key (1:1 relationship with quiz)",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Quiz display title",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Detailed quiz instructions and pedagogical goals",
    )
    pass_percentage: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=70,
        server_default=sa.text("70"),
        doc="Minimum score percentage required to pass",
    )
    time_limit_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        server_default=sa.text("30"),
        doc="Timer duration in minutes; 0 indicates untimed assessment",
    )
    shuffle_questions: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa.true(),
        doc="Whether to randomize question delivery order per attempt",
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default=sa.text("3"),
        doc="Maximum attempts permitted; 0 indicates unlimited attempts",
    )

    # Relationships
    lesson: Mapped["CurriculumLesson"] = relationship("CurriculumLesson", lazy="joined")
    questions: Mapped[List["QuizQuestion"]] = relationship(
        "QuizQuestion",
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizQuestion.sort_order",
    )
    attempts: Mapped[List["QuizAttempt"]] = relationship(
        "QuizAttempt",
        back_populates="quiz",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Quiz id={self.id} title={self.title!r} time_limit={self.time_limit_minutes}m pass={self.pass_percentage}%>"


class QuizQuestion(Base, UUIDPrimaryKeyMixin):
    """Question definition within a quiz."""

    __tablename__ = "quiz_questions"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent quiz foreign key",
    )
    question_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        doc="Question format: MCQ_SINGLE, MCQ_MULTI, TRUE_FALSE, TEXT_SHORT",
    )
    prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Question prompt / Markdown text",
    )
    points: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=1.00,
        server_default=sa.text("1.00"),
        doc="Total points allocated to this question",
    )
    explanation: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Post-submission pedagogical explanation of the correct solution",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
        doc="Default presentation order within the quiz",
    )

    # Relationships
    quiz: Mapped["Quiz"] = relationship("Quiz", back_populates="questions")
    options: Mapped[List["QuizQuestionOption"]] = relationship(
        "QuizQuestionOption",
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuizQuestionOption.sort_order",
    )

    __table_args__ = (
        Index("ix_quiz_questions_quiz_sort", "quiz_id", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<QuizQuestion id={self.id} type={self.question_type!r} points={self.points}>"


class QuizQuestionOption(Base, UUIDPrimaryKeyMixin):
    """Selectable answer option for multiple choice / true-false questions."""

    __tablename__ = "quiz_question_options"

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quiz_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent question foreign key",
    )
    option_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Answer option text",
    )
    is_correct: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa.false(),
        doc="Whether this option is considered correct",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
        doc="Display order within the question options",
    )

    # Relationships
    question: Mapped["QuizQuestion"] = relationship("QuizQuestion", back_populates="options")

    __table_args__ = (
        Index("ix_quiz_question_options_q_sort", "question_id", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<QuizQuestionOption id={self.id} is_correct={self.is_correct}>"


class QuizAttempt(Base, UUIDPrimaryKeyMixin):
    """Student attempt session tracking server-authoritative timer and score."""

    __tablename__ = "quiz_attempts"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quizzes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Target quiz foreign key",
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Attempting student foreign key",
    )
    attempt_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=sa.text("1"),
        doc="Sequential attempt number for this student and quiz",
    )
    started_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when attempt initiated (server-authoritative start time)",
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime,
        nullable=True,
        doc="UTC timestamp when attempt finalized or expired",
    )
    score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        doc="Final percentage score calculated (0.00 to 100.00)",
    )
    is_passed: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        doc="Whether final score met or exceeded quiz pass_percentage",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ATTEMPT_STATUS_IN_PROGRESS,
        server_default=sa.text("'IN_PROGRESS'"),
        index=True,
        doc="Attempt state: IN_PROGRESS, SUBMITTED, EXPIRED",
    )

    # Relationships
    quiz: Mapped["Quiz"] = relationship("Quiz", back_populates="attempts")
    student: Mapped["User"] = relationship("User", lazy="joined")
    answers: Mapped[List["QuizAnswer"]] = relationship(
        "QuizAnswer",
        back_populates="attempt",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("quiz_id", "student_id", "attempt_no", name="uq_quiz_attempts_quiz_student_attempt"),
        Index("ix_quiz_attempts_student_status", "student_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<QuizAttempt id={self.id} quiz_id={self.quiz_id} student_id={self.student_id} attempt={self.attempt_no} status={self.status!r}>"


class QuizAnswer(Base, UUIDPrimaryKeyMixin):
    """Incremental autosaved student responses recorded during an attempt."""

    __tablename__ = "quiz_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent attempt session foreign key",
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quiz_questions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Target question foreign key",
    )
    selected_option_ids: Mapped[Optional[list[str]]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
        nullable=True,
        doc="Array of selected option UUID strings (for MCQ/TRUE_FALSE)",
    )
    text_response: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Freeform text response (for TEXT_SHORT questions)",
    )
    is_correct: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        doc="Automated evaluation outcome (True/False/None before evaluation)",
    )
    points_earned: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        doc="Points awarded for this question after evaluation",
    )
    autosaved_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
        doc="UTC timestamp of the most recent autosave",
    )

    # Relationships
    attempt: Mapped["QuizAttempt"] = relationship("QuizAttempt", back_populates="answers")
    question: Mapped["QuizQuestion"] = relationship("QuizQuestion", lazy="joined")

    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_quiz_answers_attempt_question"),
    )

    def __repr__(self) -> str:
        return f"<QuizAnswer id={self.id} attempt_id={self.attempt_id} question_id={self.question_id} is_correct={self.is_correct}>"
