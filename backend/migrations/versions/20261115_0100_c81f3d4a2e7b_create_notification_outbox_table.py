"""create_notification_outbox_table

Revision ID: c81f3d4a2e7b
Revises: 56068b4ebfb3
Create Date: 2026-11-15 01:00:00.000000

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 34)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md (Section 2)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK008)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-012)

Strict Invariants:
1. Transactional atomicity: Outbox records are inserted in the same transaction as business events.
2. High-throughput polling index on status, next_retry_at, and created_at.
3. Unique constraint on dedupe_key to guarantee idempotent dispatch.
4. Exponential backoff and dead-letter queue support via retry_count and max_retries.
"""
from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Custom application types support for timezone-aware UTC persistence
from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'c81f3d4a2e7b'
down_revision: Union[str, Sequence[str], None] = '56068b4ebfb3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create notification_outbox table and polling/idempotency indexes."""
    # 1. Create notification_outbox table
    op.create_table(
        "notification_outbox",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=16), server_default=sa.text("'EMAIL'"), nullable=False),
        sa.Column("recipient", sa.String(length=255), server_default=sa.text("''"), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default=sa.text("5"), nullable=False),
        sa.Column("next_retry_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", UTCDateTime, nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_outbox")),
    )

    # 2. Performance & Idempotency Indexes
    op.create_index(
        op.f("ix_notification_outbox_status_next_retry_at"),
        "notification_outbox",
        ["status", "next_retry_at", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_outbox_dedupe_key"),
        "notification_outbox",
        ["dedupe_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_notification_outbox_event_type"),
        "notification_outbox",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_outbox_created_at"),
        "notification_outbox",
        [sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Drop indexes and notification_outbox table."""
    op.drop_index(op.f("ix_notification_outbox_created_at"), table_name="notification_outbox")
    op.drop_index(op.f("ix_notification_outbox_event_type"), table_name="notification_outbox")
    op.drop_index(op.f("ix_notification_outbox_dedupe_key"), table_name="notification_outbox")
    op.drop_index(op.f("ix_notification_outbox_status_next_retry_at"), table_name="notification_outbox")
    op.drop_table("notification_outbox")
