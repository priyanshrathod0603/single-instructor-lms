"""create_blog_and_notes_tables

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-16 19:00:00.000000

Architecture Specifications:
- SA-04 — Complete Content & Course Governance (Sections 4 & 5)
- docs/backend/04-DATABASE-ARCHITECTURE.md
- docs/backend/06-API-ARCHITECTURE.md
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf [Pages 1-16]

Strict Invariants & Safety Controls:
1. Lock Timeout: Applies SET lock_timeout = '2s' on PostgreSQL before DDL.
2. Canonical Statuses: 'DRAFT', 'PUBLISHED', 'ARCHIVED'.
3. Storage Protection: Binary files are stored in object storage; tables store only
   metadata and MediaAsset foreign keys (ON DELETE SET NULL).
4. Referential Integrity: author_id references users.id ON DELETE RESTRICT.
5. Idempotent & Symmetric: Full upgrade and reverse downgrade lifecycle.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# Custom application types support for timezone-aware UTC persistence
from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create blog_posts and notes tables with foreign keys and performance indexes."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Step 1: Set lock timeout on PostgreSQL to prevent connection pool queueing
    if is_postgres:
        op.execute("SET lock_timeout = '2s';")

    # Step 2: Create blog_posts table
    op.create_table(
        "blog_posts",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "category",
            sa.String(length=64),
            server_default=sa.text("'General'"),
            nullable=False,
        ),
        sa.Column("thumbnail_url", sa.String(length=512), nullable=True),
        sa.Column("thumbnail_media_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'DRAFT'"),
            nullable=False,
        ),
        sa.Column("published_at", UTCDateTime, nullable=True),
        sa.Column("author_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_blog_posts_author_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["thumbnail_media_id"],
            ["media_assets.id"],
            name=op.f("fk_blog_posts_thumbnail_media_id_media_assets"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_posts")),
    )
    op.create_index(op.f("ix_blog_posts_slug"), "blog_posts", ["slug"], unique=True)
    op.create_index(op.f("ix_blog_posts_status"), "blog_posts", ["status"])
    op.create_index(op.f("ix_blog_posts_category"), "blog_posts", ["category"])
    op.create_index(op.f("ix_blog_posts_author_id"), "blog_posts", ["author_id"])

    # Step 3: Create notes table
    op.create_table(
        "notes",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "category",
            sa.String(length=64),
            server_default=sa.text("'General'"),
            nullable=False,
        ),
        sa.Column("pdf_media_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("pdf_url", sa.String(length=512), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'DRAFT'"),
            nullable=False,
        ),
        sa.Column("published_at", UTCDateTime, nullable=True),
        sa.Column("author_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_notes_author_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pdf_media_id"],
            ["media_assets.id"],
            name=op.f("fk_notes_pdf_media_id_media_assets"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
    )
    op.create_index(op.f("ix_notes_slug"), "notes", ["slug"], unique=True)
    op.create_index(op.f("ix_notes_status"), "notes", ["status"])
    op.create_index(op.f("ix_notes_category"), "notes", ["category"])
    op.create_index(op.f("ix_notes_author_id"), "notes", ["author_id"])


def downgrade() -> None:
    """Drop notes and blog_posts tables in reverse dependency order."""
    op.drop_index(op.f("ix_notes_author_id"), table_name="notes")
    op.drop_index(op.f("ix_notes_category"), table_name="notes")
    op.drop_index(op.f("ix_notes_status"), table_name="notes")
    op.drop_index(op.f("ix_notes_slug"), table_name="notes")
    op.drop_table("notes")

    op.drop_index(op.f("ix_blog_posts_author_id"), table_name="blog_posts")
    op.drop_index(op.f("ix_blog_posts_category"), table_name="blog_posts")
    op.drop_index(op.f("ix_blog_posts_status"), table_name="blog_posts")
    op.drop_index(op.f("ix_blog_posts_slug"), table_name="blog_posts")
    op.drop_table("blog_posts")
