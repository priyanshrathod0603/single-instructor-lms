"""create_assignment_and_rubric_tables

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-15 07:00:00.000000

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 3, Tables 14-19)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Section 1)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK701)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003, ADR-013)

Strict Invariants:
1. Linear migration sequence: down_revision is 'd4e5f6a7b8c9'.
2. Referential integrity: Foreign keys enforce RESTRICT or CASCADE as per architecture specification.
3. Attempt tracking: UNIQUE(assignment_id, student_id, attempt_no) on assignment_submissions.
4. Clean reversible lifecycle: downgrade symmetrically drops indexes, constraints, and tables in reverse dependency order.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Module 3 tables: assignments, rubrics, rubric_criteria, assignment_submissions, rubric_scores, grade_overrides."""
    # 1. assignments
    op.create_table(
        "assignments",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lesson_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("max_score", sa.Numeric(precision=5, scale=2), server_default=sa.text("100.00"), nullable=False),
        sa.Column("pass_score", sa.Numeric(precision=5, scale=2), server_default=sa.text("50.00"), nullable=False),
        sa.Column("allow_late", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("due_date", UTCDateTime, nullable=True),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["curriculum_lessons.id"],
            name=op.f("fk_assignments_lesson_id_curriculum_lessons"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignments")),
        sa.UniqueConstraint("lesson_id", name=op.f("uq_assignments_lesson_id")),
    )
    op.create_index(op.f("ix_assignments_lesson_id"), "assignments", ["lesson_id"], unique=True)

    # 2. rubrics
    op.create_table(
        "rubrics",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("assignment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_rubrics_assignment_id_assignments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubrics")),
    )
    op.create_index(op.f("ix_rubrics_assignment_id"), "rubrics", ["assignment_id"], unique=False)

    # 3. rubric_criteria
    op.create_table(
        "rubric_criteria",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("rubric_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("max_points", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("weight", sa.Numeric(precision=5, scale=2), server_default=sa.text("1.00"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(
            ["rubric_id"],
            ["rubrics.id"],
            name=op.f("fk_rubric_criteria_rubric_id_rubrics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_criteria")),
    )
    op.create_index(op.f("ix_rubric_criteria_rubric_id"), "rubric_criteria", ["rubric_id"], unique=False)

    # 4. assignment_submissions
    op.create_table(
        "assignment_submissions",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("assignment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("student_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("attempt_no", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("file_url", sa.String(length=512), nullable=False),
        sa.Column("text_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'SUBMITTED'"), nullable=False),
        sa.Column("submitted_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("final_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("graded_at", UTCDateTime, nullable=True),
        sa.Column("graded_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_assignment_submissions_assignment_id_assignments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name=op.f("fk_assignment_submissions_student_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["graded_by"],
            ["users.id"],
            name=op.f("fk_assignment_submissions_graded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_submissions")),
        sa.UniqueConstraint(
            "assignment_id",
            "student_id",
            "attempt_no",
            name="uq_assignment_submissions_attempt",
        ),
    )
    op.create_index(op.f("ix_assignment_submissions_assignment_id"), "assignment_submissions", ["assignment_id"], unique=False)
    op.create_index(op.f("ix_assignment_submissions_student_id"), "assignment_submissions", ["student_id"], unique=False)
    op.create_index(op.f("ix_assignment_submissions_status"), "assignment_submissions", ["status"], unique=False)
    op.create_index("ix_assignment_submissions_assignment_student", "assignment_submissions", ["assignment_id", "student_id"], unique=False)
    op.create_index("ix_assignment_submissions_student_status", "assignment_submissions", ["student_id", "status"], unique=False)

    # 5. rubric_scores
    op.create_table(
        "rubric_scores",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("submission_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("criteria_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("points_awarded", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["assignment_submissions.id"],
            name=op.f("fk_rubric_scores_submission_id_assignment_submissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["criteria_id"],
            ["rubric_criteria.id"],
            name=op.f("fk_rubric_scores_criteria_id_rubric_criteria"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_scores")),
        sa.UniqueConstraint("submission_id", "criteria_id", name="uq_rubric_scores_submission_criteria"),
    )
    op.create_index(op.f("ix_rubric_scores_submission_id"), "rubric_scores", ["submission_id"], unique=False)
    op.create_index(op.f("ix_rubric_scores_criteria_id"), "rubric_scores", ["criteria_id"], unique=False)

    # 6. grade_overrides
    op.create_table(
        "grade_overrides",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("submission_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("original_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("overridden_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("overridden_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["assignment_submissions.id"],
            name=op.f("fk_grade_overrides_submission_id_assignment_submissions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["overridden_by"],
            ["users.id"],
            name=op.f("fk_grade_overrides_overridden_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grade_overrides")),
    )
    op.create_index(op.f("ix_grade_overrides_submission_id"), "grade_overrides", ["submission_id"], unique=False)
    op.create_index(op.f("ix_grade_overrides_overridden_by"), "grade_overrides", ["overridden_by"], unique=False)


def downgrade() -> None:
    """Drop Module 3 tables in reverse dependency order."""
    op.drop_index(op.f("ix_grade_overrides_overridden_by"), table_name="grade_overrides")
    op.drop_index(op.f("ix_grade_overrides_submission_id"), table_name="grade_overrides")
    op.drop_table("grade_overrides")

    op.drop_index(op.f("ix_rubric_scores_criteria_id"), table_name="rubric_scores")
    op.drop_index(op.f("ix_rubric_scores_submission_id"), table_name="rubric_scores")
    op.drop_table("rubric_scores")

    op.drop_index("ix_assignment_submissions_student_status", table_name="assignment_submissions")
    op.drop_index("ix_assignment_submissions_assignment_student", table_name="assignment_submissions")
    op.drop_index(op.f("ix_assignment_submissions_status"), table_name="assignment_submissions")
    op.drop_index(op.f("ix_assignment_submissions_student_id"), table_name="assignment_submissions")
    op.drop_index(op.f("ix_assignment_submissions_assignment_id"), table_name="assignment_submissions")
    op.drop_table("assignment_submissions")

    op.drop_index(op.f("ix_rubric_criteria_rubric_id"), table_name="rubric_criteria")
    op.drop_table("rubric_criteria")

    op.drop_index(op.f("ix_rubrics_assignment_id"), table_name="rubrics")
    op.drop_table("rubrics")

    op.drop_index(op.f("ix_assignments_lesson_id"), table_name="assignments")
    op.drop_table("assignments")
