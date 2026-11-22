"""create_media_assets_table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-15 04:00:00.000000

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 7, Table 32)
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md (Sections 1-4)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK401)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-009, ADR-010)

Strict Invariants:
1. Direct Presigned Ingestion: Large binaries never proxy through app server RAM.
2. Status Tracking: UPLOADING -> UPLOADED -> PROCESSING -> READY / FAILED.
3. Clean Downgrade: Symmetrically drops all indexes and table.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Custom application types support for timezone-aware UTC persistence
from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create media_assets table with compound indexes."""
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    op.create_table(
        "media_assets",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("uploader_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_key", sa.String(length=512), nullable=False),
        sa.Column("bucket", sa.String(length=128), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'UPLOADING'"),
            nullable=False,
        ),
        sa.Column("transcode_output", json_type, nullable=True),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["uploader_id"],
            ["users.id"],
            name=op.f("fk_media_assets_uploader_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_assets")),
    )
    op.create_index(op.f("ix_media_assets_file_key"), "media_assets", ["file_key"], unique=True)
    op.create_index(op.f("ix_media_assets_uploader_id"), "media_assets", ["uploader_id"], unique=False)
    op.create_index(op.f("ix_media_assets_status"), "media_assets", ["status"], unique=False)
    op.create_index(
        "ix_media_assets_uploader_created",
        "media_assets",
        ["uploader_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_media_assets_status_created",
        "media_assets",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop media_assets table and indexes."""
    op.drop_index("ix_media_assets_status_created", table_name="media_assets")
    op.drop_index("ix_media_assets_uploader_created", table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_status"), table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_uploader_id"), table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_file_key"), table_name="media_assets")
    op.drop_table("media_assets")
