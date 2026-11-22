"""create_quiz_and_question_tables

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-15 08:00:00.000000

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 4, Tables 20-24)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.6)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Sections 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK801)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-011, ADR-013)

Strict Invariants:
1. Linear migration sequence: down_revision is 'e5f6a7b8c9d0'.
2. Referential integrity: Foreign keys enforce RESTRICT or CASCADE as per architecture specification.
3. Attempt tracking: UNIQUE(quiz_id, student_id, attempt_no) on quiz_attempts.
4. Autosave integrity: UNIQUE(attempt_id, question_id) on quiz_answers.
5. Clean reversible lifecycle: downgrade symmetrically drops indexes, constraints, and tables in reverse dependency order.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Module 4 tables: quizzes, quiz_questions, quiz_question_options, quiz_attempts, quiz_answers."""
    # 1. quizzes
    op.create_table(
        "quizzes",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lesson_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pass_percentage", sa.Integer(), server_default=sa.text("70"), nullable=False),
        sa.Column("time_limit_minutes", sa.Integer(), server_default=sa.text("30"), nullable=False),
        sa.Column("shuffle_questions", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["curriculum_lessons.id"],
            name=op.f("fk_quizzes_lesson_id_curriculum_lessons"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quizzes")),
        sa.UniqueConstraint("lesson_id", name=op.f("uq_quizzes_lesson_id")),
    )
    op.create_index(op.f("ix_quizzes_lesson_id"), "quizzes", ["lesson_id"], unique=True)

    # 2. quiz_questions
    op.create_table(
        "quiz_questions",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("quiz_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("question_type", sa.String(length=16), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("points", sa.Numeric(precision=5, scale=2), server_default=sa.text("1.00"), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(
            ["quiz_id"],
            ["quizzes.id"],
            name=op.f("fk_quiz_questions_quiz_id_quizzes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_questions")),
    )
    op.create_index(op.f("ix_quiz_questions_quiz_id"), "quiz_questions", ["quiz_id"], unique=False)
    op.create_index("ix_quiz_questions_quiz_sort", "quiz_questions", ["quiz_id", "sort_order"], unique=False)

    # 3. quiz_question_options
    op.create_table(
        "quiz_question_options",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("question_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("option_text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["quiz_questions.id"],
            name=op.f("fk_quiz_question_options_question_id_quiz_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_question_options")),
    )
    op.create_index(op.f("ix_quiz_question_options_question_id"), "quiz_question_options", ["question_id"], unique=False)
    op.create_index("ix_quiz_question_options_q_sort", "quiz_question_options", ["question_id", "sort_order"], unique=False)

    # 4. quiz_attempts
    op.create_table(
        "quiz_attempts",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("quiz_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("student_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("attempt_no", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("started_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", UTCDateTime, nullable=True),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("is_passed", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'IN_PROGRESS'"), nullable=False),
        sa.ForeignKeyConstraint(
            ["quiz_id"],
            ["quizzes.id"],
            name=op.f("fk_quiz_attempts_quiz_id_quizzes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name=op.f("fk_quiz_attempts_student_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_attempts")),
        sa.UniqueConstraint(
            "quiz_id",
            "student_id",
            "attempt_no",
            name="uq_quiz_attempts_quiz_student_attempt",
        ),
    )
    op.create_index(op.f("ix_quiz_attempts_quiz_id"), "quiz_attempts", ["quiz_id"], unique=False)
    op.create_index(op.f("ix_quiz_attempts_student_id"), "quiz_attempts", ["student_id"], unique=False)
    op.create_index(op.f("ix_quiz_attempts_status"), "quiz_attempts", ["status"], unique=False)
    op.create_index("ix_quiz_attempts_student_status", "quiz_attempts", ["student_id", "status"], unique=False)

    # 5. quiz_answers
    json_variant = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
    op.create_table(
        "quiz_answers",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("attempt_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("question_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("selected_option_ids", json_variant, nullable=True),
        sa.Column("text_response", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("points_earned", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("autosaved_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["quiz_attempts.id"],
            name=op.f("fk_quiz_answers_attempt_id_quiz_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["quiz_questions.id"],
            name=op.f("fk_quiz_answers_question_id_quiz_questions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_answers")),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_quiz_answers_attempt_question"),
    )
    op.create_index(op.f("ix_quiz_answers_attempt_id"), "quiz_answers", ["attempt_id"], unique=False)
    op.create_index(op.f("ix_quiz_answers_question_id"), "quiz_answers", ["question_id"], unique=False)


def downgrade() -> None:
    """Drop Module 4 tables in reverse dependency order."""
    op.drop_index(op.f("ix_quiz_answers_question_id"), table_name="quiz_answers")
    op.drop_index(op.f("ix_quiz_answers_attempt_id"), table_name="quiz_answers")
    op.drop_table("quiz_answers")

    op.drop_index("ix_quiz_attempts_student_status", table_name="quiz_attempts")
    op.drop_index(op.f("ix_quiz_attempts_status"), table_name="quiz_attempts")
    op.drop_index(op.f("ix_quiz_attempts_student_id"), table_name="quiz_attempts")
    op.drop_index(op.f("ix_quiz_attempts_quiz_id"), table_name="quiz_attempts")
    op.drop_table("quiz_attempts")

    op.drop_index("ix_quiz_question_options_q_sort", table_name="quiz_question_options")
    op.drop_index(op.f("ix_quiz_question_options_question_id"), table_name="quiz_question_options")
    op.drop_table("quiz_question_options")

    op.drop_index("ix_quiz_questions_quiz_sort", table_name="quiz_questions")
    op.drop_index(op.f("ix_quiz_questions_quiz_id"), table_name="quiz_questions")
    op.drop_table("quiz_questions")

    op.drop_index(op.f("ix_quizzes_lesson_id"), table_name="quizzes")
    op.drop_table("quizzes")
