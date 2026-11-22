"""create_course_and_curriculum_tables

Revision ID: a1b2c3d4e5f6
Revises: f71a9b2c3d4e
Create Date: 2026-11-15 03:00:00.000000

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 2, Tables 8, 9, 10, 11, 12, 13)
- docs/backend/11-COURSE-MANAGEMENT.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK301)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-003, ADR-005)

Strict Invariants:
1. Immutability: Published revisions frozen with complete JSONB snapshot.
2. Minor Currency: price_inr stored in integer paise.
3. Strict Hierarchy: courses -> course_revisions -> curriculum_sections -> curriculum_lessons -> lesson_resources.
4. Circular Reference Management: courses.live_revision_id references course_revisions.id with post_update/use_alter.
5. Idempotent & Symmetric: Clean upgrade and reverse downgrade lifecycle.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Custom application types support for timezone-aware UTC persistence
from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f71a9b2c3d4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create courses, course_revisions, course_tags, sections, lessons, and resources."""
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    # 1. Create courses table
    op.create_table(
        "courses",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("headline", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=512), nullable=True),
        sa.Column("live_revision_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'DRAFT'"),
            nullable=False,
        ),
        sa.Column(
            "price_inr",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "is_free",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
    )
    op.create_index(op.f("ix_courses_slug"), "courses", ["slug"], unique=True)
    op.create_index(op.f("ix_courses_status"), "courses", ["status"], unique=False)

    # 2. Create course_revisions table
    op.create_table(
        "course_revisions",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("course_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'DRAFT'"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("snapshot", json_type, nullable=True),
        sa.Column("published_at", UTCDateTime, nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_revisions_course_id_courses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_course_revisions_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_revisions")),
        sa.UniqueConstraint(
            "course_id",
            "revision_no",
            name=op.f("uq_course_revisions_course_id_revision_no"),
        ),
    )
    op.create_index(op.f("ix_course_revisions_course_id"), "course_revisions", ["course_id"], unique=False)
    op.create_index(op.f("ix_course_revisions_status"), "course_revisions", ["status"], unique=False)
    op.create_index(
        "ix_course_revisions_course_status",
        "course_revisions",
        ["course_id", "status"],
        unique=False,
    )

    # 3. Add foreign key from courses.live_revision_id to course_revisions.id
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_courses_live_revision_id_course_revisions",
            "courses",
            "course_revisions",
            ["live_revision_id"],
            ["id"],
            ondelete="SET NULL",
            use_alter=True,
        )

    # 4. Create course_tags table
    op.create_table(
        "course_tags",
        sa.Column("course_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tag", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_tags_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("course_id", "tag", name=op.f("pk_course_tags")),
    )

    # 5. Create curriculum_sections table
    op.create_table(
        "curriculum_sections",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("course_revision_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_revision_id"],
            ["course_revisions.id"],
            name=op.f("fk_curriculum_sections_course_revision_id_course_revisions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curriculum_sections")),
    )
    op.create_index(
        op.f("ix_curriculum_sections_course_revision_id"),
        "curriculum_sections",
        ["course_revision_id"],
        unique=False,
    )
    op.create_index(
        "ix_curriculum_sections_rev_order",
        "curriculum_sections",
        ["course_revision_id", "sort_order"],
        unique=False,
    )

    # 6. Create curriculum_lessons table
    op.create_table(
        "curriculum_lessons",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("section_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "lesson_type",
            sa.String(length=16),
            server_default=sa.text("'VIDEO'"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_preview", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("content", json_type, nullable=True),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["curriculum_sections.id"],
            name=op.f("fk_curriculum_lessons_section_id_curriculum_sections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curriculum_lessons")),
    )
    op.create_index(
        op.f("ix_curriculum_lessons_section_id"),
        "curriculum_lessons",
        ["section_id"],
        unique=False,
    )
    op.create_index(
        "ix_curriculum_lessons_section_order",
        "curriculum_lessons",
        ["section_id", "sort_order"],
        unique=False,
    )

    # 7. Create lesson_resources table
    op.create_table(
        "lesson_resources",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lesson_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "resource_type",
            sa.String(length=16),
            server_default=sa.text("'PDF'"),
            nullable=False,
        ),
        sa.Column("file_url", sa.String(length=512), nullable=False),
        sa.Column(
            "file_size_bytes",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["curriculum_lessons.id"],
            name=op.f("fk_lesson_resources_lesson_id_curriculum_lessons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lesson_resources")),
    )
    op.create_index(
        op.f("ix_lesson_resources_lesson_id"),
        "lesson_resources",
        ["lesson_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop lesson_resources, lessons, sections, course_tags, and courses tables in reverse order."""
    bind = op.get_bind()

    op.drop_index(op.f("ix_lesson_resources_lesson_id"), table_name="lesson_resources")
    op.drop_table("lesson_resources")

    op.drop_index("ix_curriculum_lessons_section_order", table_name="curriculum_lessons")
    op.drop_index(op.f("ix_curriculum_lessons_section_id"), table_name="curriculum_lessons")
    op.drop_table("curriculum_lessons")

    op.drop_index("ix_curriculum_sections_rev_order", table_name="curriculum_sections")
    op.drop_index(op.f("ix_curriculum_sections_course_revision_id"), table_name="curriculum_sections")
    op.drop_table("curriculum_sections")

    op.drop_table("course_tags")

    # Drop circular FK constraint before dropping course_revisions
    if bind.dialect.name == "postgresql":
        op.drop_constraint("fk_courses_live_revision_id_course_revisions", "courses", type_="foreignkey")

    op.drop_index("ix_course_revisions_course_status", table_name="course_revisions")
    op.drop_index(op.f("ix_course_revisions_status"), table_name="course_revisions")
    op.drop_index(op.f("ix_course_revisions_course_id"), table_name="course_revisions")
    op.drop_table("course_revisions")

    op.drop_index(op.f("ix_courses_status"), table_name="courses")
    op.drop_index(op.f("ix_courses_slug"), table_name="courses")
    op.drop_table("courses")
