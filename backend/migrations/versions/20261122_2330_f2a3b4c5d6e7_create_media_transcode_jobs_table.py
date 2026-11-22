"""create_media_transcode_jobs_table

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-22 23:30:00.000000

Architecture Specifications:
- VM-02: Video Transcoding Infrastructure (FFmpeg + HLS)
- docs/backend/04-DATABASE-ARCHITECTURE.md
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md

Strict Invariants:
1. Transactional Queueing: Jobs created atomically alongside upload confirmation.
2. High-Throughput Worker Claiming: Polling utilizes compound index on (status, next_retry_at).
3. Cascade Lifecycle: Transcode jobs are tied to media_assets via cascading foreign keys.
4. Clean Downgrade: Symmetrically drops all indexes and table.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create media_transcode_jobs table with indexing."""
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    op.create_table(
        "media_transcode_jobs",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("media_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'QUEUED'"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            server_default=sa.text("100"),
            nullable=False,
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_retries",
            sa.Integer(),
            server_default=sa.text("3"),
            nullable=False,
        ),
        sa.Column("next_retry_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("locked_at", UTCDateTime, nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", json_type, nullable=True),
        sa.Column("job_metadata", json_type, nullable=True),
        sa.Column("started_at", UTCDateTime, nullable=True),
        sa.Column("completed_at", UTCDateTime, nullable=True),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media_assets.id"],
            name=op.f("fk_media_transcode_jobs_media_id_media_assets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_transcode_jobs")),
    )
    op.create_index(op.f("ix_media_transcode_jobs_media_id"), "media_transcode_jobs", ["media_id"], unique=False)
    op.create_index(op.f("ix_media_transcode_jobs_status"), "media_transcode_jobs", ["status"], unique=False)
    op.create_index(
        "ix_media_transcode_jobs_status_next_retry",
        "media_transcode_jobs",
        ["status", "next_retry_at"],
        unique=False,
    )
    op.create_index(
        "ix_media_transcode_jobs_media_created",
        "media_transcode_jobs",
        ["media_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop media_transcode_jobs table and indexes."""
    op.drop_index("ix_media_transcode_jobs_media_created", table_name="media_transcode_jobs")
    op.drop_index("ix_media_transcode_jobs_status_next_retry", table_name="media_transcode_jobs")
    op.drop_index(op.f("ix_media_transcode_jobs_status"), table_name="media_transcode_jobs")
    op.drop_index(op.f("ix_media_transcode_jobs_media_id"), table_name="media_transcode_jobs")
    op.drop_table("media_transcode_jobs")
