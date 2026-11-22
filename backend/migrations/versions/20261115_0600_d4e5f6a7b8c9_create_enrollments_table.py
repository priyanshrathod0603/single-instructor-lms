"""create_enrollments_table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-15 06:00:00.000000

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 28)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK601)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)

Strict Invariants:
1. Zero trust on browser redirect: Enrollments granted exclusively on verified payment webhook or manual admin grant.
2. Unique Active Enrollment: UNIQUE(student_id, course_id) prevents duplicate enrollment rows.
3. Clean Downgrade: Symmetrically drops indexes, foreign keys, and enrollments table.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# Custom application types support for timezone-aware UTC persistence
from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create enrollments table with composite unique constraint and indexes."""
    op.create_table(
        "enrollments",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("student_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column("granted_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", UTCDateTime, nullable=True),
        sa.Column("revoked_at", UTCDateTime, nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name=op.f("fk_enrollments_student_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_enrollments_course_id_courses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_enrollments_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollments")),
        sa.UniqueConstraint("student_id", "course_id", name="uq_enrollments_student_id_course_id"),
    )
    op.create_index(op.f("ix_enrollments_student_id"), "enrollments", ["student_id"], unique=False)
    op.create_index(op.f("ix_enrollments_course_id"), "enrollments", ["course_id"], unique=False)
    op.create_index(op.f("ix_enrollments_order_id"), "enrollments", ["order_id"], unique=False)
    op.create_index(op.f("ix_enrollments_status"), "enrollments", ["status"], unique=False)
    op.create_index("ix_enrollments_student_status", "enrollments", ["student_id", "status"], unique=False)
    op.create_index("ix_enrollments_course_status", "enrollments", ["course_id", "status"], unique=False)


def downgrade() -> None:
    """Drop enrollments table and associated indexes."""
    op.drop_index("ix_enrollments_course_status", table_name="enrollments")
    op.drop_index("ix_enrollments_student_status", table_name="enrollments")
    op.drop_index(op.f("ix_enrollments_status"), table_name="enrollments")
    op.drop_index(op.f("ix_enrollments_order_id"), table_name="enrollments")
    op.drop_index(op.f("ix_enrollments_course_id"), table_name="enrollments")
    op.drop_index(op.f("ix_enrollments_student_id"), table_name="enrollments")
    op.drop_table("enrollments")
