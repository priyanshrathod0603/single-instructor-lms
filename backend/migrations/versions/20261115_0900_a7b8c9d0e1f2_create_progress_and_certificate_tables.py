"""create_progress_and_certificate_tables

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-15 09:00:00.000000

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Tables 29, 30, 31)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.9)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Sections 1-3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)

Strict Invariants:
1. Linear migration sequence: down_revision is 'f6a7b8c9d0e1'.
2. Referential integrity: Foreign keys enforce CASCADE on progress records and RESTRICT on certificates.
3. Idempotent progress UPSERT: UNIQUE(student_id, lesson_id) on lesson_progress.
4. Summary uniqueness: UNIQUE(student_id, course_id) on course_progress_summaries.
5. Verifiable certification: UNIQUE(certificate_no), UNIQUE(verification_hash), UNIQUE(student_id, course_id).
6. Clean reversible lifecycle: downgrade symmetrically drops indexes, constraints, and tables in reverse dependency order.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Module 6 progress and certificate tables: lesson_progress, course_progress_summaries, certificates."""
    # 1. lesson_progress
    op.create_table(
        "lesson_progress",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("student_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("lesson_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("is_completed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("watch_position_seconds", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("completed_at", UTCDateTime, nullable=True),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name="fk_lesson_progress_student_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["curriculum_lessons.id"],
            name="fk_lesson_progress_lesson_id_curriculum_lessons",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lesson_progress"),
        sa.UniqueConstraint("student_id", "lesson_id", name="uq_lesson_progress_student_lesson"),
    )
    op.create_index("ix_lesson_progress_student_id", "lesson_progress", ["student_id"], unique=False)
    op.create_index("ix_lesson_progress_lesson_id", "lesson_progress", ["lesson_id"], unique=False)
    op.create_index("ix_lesson_progress_student_completed", "lesson_progress", ["student_id", "is_completed"], unique=False)

    # 2. course_progress_summaries
    op.create_table(
        "course_progress_summaries",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("student_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("completed_lessons_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_lessons_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("progress_percentage", sa.Numeric(precision=5, scale=2), server_default=sa.text("0.00"), nullable=False),
        sa.Column("last_activity_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name="fk_course_progress_summaries_student_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name="fk_course_progress_summaries_course_id_courses",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_course_progress_summaries"),
        sa.UniqueConstraint("student_id", "course_id", name="uq_course_progress_summaries_student_course"),
    )
    op.create_index("ix_course_progress_summaries_student_id", "course_progress_summaries", ["student_id"], unique=False)
    op.create_index("ix_course_progress_summaries_course_id", "course_progress_summaries", ["course_id"], unique=False)
    op.create_index(
        "ix_course_progress_summaries_student_course",
        "course_progress_summaries",
        ["student_id", "course_id"],
        unique=False,
    )

    # 3. certificates
    op.create_table(
        "certificates",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("certificate_no", sa.String(length=32), nullable=False),
        sa.Column("student_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("issued_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("verification_hash", sa.String(length=64), nullable=False),
        sa.Column("pdf_url", sa.String(length=512), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("revoked_at", UTCDateTime, nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name="fk_certificates_student_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name="fk_certificates_course_id_courses",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_certificates"),
        sa.UniqueConstraint("certificate_no", name="uq_certificates_certificate_no"),
        sa.UniqueConstraint("verification_hash", name="uq_certificates_verification_hash"),
        sa.UniqueConstraint("student_id", "course_id", name="uq_certificates_student_course"),
    )
    op.create_index("ix_certificates_certificate_no", "certificates", ["certificate_no"], unique=True)
    op.create_index("ix_certificates_student_id", "certificates", ["student_id"], unique=False)
    op.create_index("ix_certificates_course_id", "certificates", ["course_id"], unique=False)
    op.create_index("ix_certificates_verification_hash", "certificates", ["verification_hash"], unique=True)
    op.create_index("ix_certificates_student_course", "certificates", ["student_id", "course_id"], unique=False)


def downgrade() -> None:
    """Drop Module 6 progress and certificate tables in reverse dependency order."""
    # 3. certificates
    op.drop_index("ix_certificates_student_course", table_name="certificates")
    op.drop_index("ix_certificates_verification_hash", table_name="certificates")
    op.drop_index("ix_certificates_course_id", table_name="certificates")
    op.drop_index("ix_certificates_student_id", table_name="certificates")
    op.drop_index("ix_certificates_certificate_no", table_name="certificates")
    op.drop_table("certificates")

    # 2. course_progress_summaries
    op.drop_index("ix_course_progress_summaries_student_course", table_name="course_progress_summaries")
    op.drop_index("ix_course_progress_summaries_course_id", table_name="course_progress_summaries")
    op.drop_index("ix_course_progress_summaries_student_id", table_name="course_progress_summaries")
    op.drop_table("course_progress_summaries")

    # 1. lesson_progress
    op.drop_index("ix_lesson_progress_student_completed", table_name="lesson_progress")
    op.drop_index("ix_lesson_progress_lesson_id", table_name="lesson_progress")
    op.drop_index("ix_lesson_progress_student_id", table_name="lesson_progress")
    op.drop_table("lesson_progress")
