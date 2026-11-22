"""create_permissions_and_notifications_tables

Revision ID: f71a9b2c3d4e
Revises: e59a7c3b1f2d
Create Date: 2026-11-15 02:00:00.000000

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 1, Tables 2, 3; Module 7, Table 33)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.11)
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md (Sections 1, 2)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK201, TASK205)

Strict Invariants:
1. Permissions: Granular standardized domain:action permission registry.
2. Role Permissions: Pure positive grant aggregation across assigned roles.
3. In-App Notifications: Notification feed with read state and recipient isolation.
4. Cascading Integrity: Cascade deletions on role/permission removals.
5. Idempotent & Symmetric: Full upgrade and downgrade migration lifecycle.
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Custom application types support for timezone-aware UTC persistence
from app.core.permissions import CANONICAL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'f71a9b2c3d4e'
down_revision: Union[str, Sequence[str], None] = 'e59a7c3b1f2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create permissions, role_permissions, and notifications tables and seed default mappings."""
    # 1. Create permissions table
    op.create_table(
        "permissions",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
    )
    op.create_index(op.f("ix_permissions_module"), "permissions", ["module"], unique=False)

    # 2. Create role_permissions join table
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.String(length=32), nullable=False),
        sa.Column("permission_id", sa.String(length=64), nullable=False),
        sa.Column("assigned_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_role_permissions_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("fk_role_permissions_permission_id_permissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name=op.f("pk_role_permissions")),
    )

    # 3. Create notifications table (In-App notification feed)
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "notification_type",
            sa.String(length=32),
            server_default=sa.text("'ANNOUNCEMENT'"),
            nullable=False,
        ),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("data", json_type, nullable=True),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id", "is_read", sa.text("created_at DESC")],
        unique=False,
    )

    # 4. Seed canonical permissions
    now = datetime.now(timezone.utc)
    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.String(64)),
        sa.column("module", sa.String(32)),
        sa.column("description", sa.Text),
        sa.column("created_at", UTCDateTime),
    )
    perm_records = [
        {
            "id": key,
            "module": mod,
            "description": desc,
            "created_at": now,
        }
        for key, mod, desc in CANONICAL_PERMISSIONS
    ]
    op.bulk_insert(permissions_table, perm_records)

    # 5. Seed default role permissions
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.String(32)),
        sa.column("permission_id", sa.String(64)),
        sa.column("assigned_at", UTCDateTime),
    )
    role_perm_records = []
    for role_id, perm_keys in DEFAULT_ROLE_PERMISSIONS.items():
        for perm_id in perm_keys:
            role_perm_records.append({
                "role_id": role_id,
                "permission_id": perm_id,
                "assigned_at": now,
            })
    op.bulk_insert(role_permissions_table, role_perm_records)


def downgrade() -> None:
    """Drop notifications, role_permissions, and permissions tables."""
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("role_permissions")
    op.drop_index(op.f("ix_permissions_module"), table_name="permissions")
    op.drop_table("permissions")
