"""create_identity_and_auth_tables

Revision ID: e59a7c3b1f2d
Revises: c81f3d4a2e7b
Create Date: 2026-11-15 01:30:00.000000

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 1, Tables 1, 2, 3, 4, 5)
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md
- docs/backend/08-SESSION-MANAGEMENT.md
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK102)

Strict Invariants:
1. Roles: Canonical system roles (VISITOR, STUDENT, STAFF, ADMIN, SUPER_ADMIN).
2. Users: Normalized email unique index, Argon2id password hash, email verification flag.
3. User Roles: User-role junction table linking users to assigned system roles.
4. Single-Active-Session: Partial unique index on auth_sessions(user_id) WHERE status='ACTIVE'.
5. Auth Tokens: Single-use cryptographic tokens for email verification and password reset.
6. Audit Log FK: actor_id linked to users.id with ON DELETE SET NULL.
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Union

from alembic import op
import sqlalchemy as sa

# Custom application types support for timezone-aware UTC persistence
from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'e59a7c3b1f2d'
down_revision: Union[str, Sequence[str], None] = 'c81f3d4a2e7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create roles, users, user_roles, auth_sessions, auth_tokens tables and audit_logs FK."""
    bind = op.get_bind()

    # 1. Create roles table
    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=32), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
    )

    # Seed canonical roles
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.String(32)),
        sa.column("name", sa.String(64)),
        sa.column("description", sa.Text),
        sa.column("created_at", UTCDateTime),
    )
    op.bulk_insert(
        roles_table,
        [
            {
                "id": "VISITOR",
                "name": "Visitor",
                "description": "Unauthenticated public guest or lead browsing public content",
                "created_at": datetime.now(timezone.utc),
            },
            {
                "id": "STUDENT",
                "name": "Enrolled Student",
                "description": "Paying student enrolled in one or more courses",
                "created_at": datetime.now(timezone.utc),
            },
            {
                "id": "STAFF",
                "name": "Operations Staff",
                "description": "Support and administrative staff helping manage the platform",
                "created_at": datetime.now(timezone.utc),
            },
            {
                "id": "ADMIN",
                "name": "Platform Administrator",
                "description": "Platform administrator with elevated content and operations privileges",
                "created_at": datetime.now(timezone.utc),
            },
            {
                "id": "SUPER_ADMIN",
                "name": "Primary Instructor / Owner",
                "description": "Full-access owner and primary instructor of the proprietary platform",
                "created_at": datetime.now(timezone.utc),
            },
        ],
    )

    # 2. Create users table
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=128), nullable=False),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_is_active"), "users", ["is_active"], unique=False)
    op.create_index(op.f("ix_users_created_at"), "users", [sa.text("created_at DESC")], unique=False)

    # 3. Create user_roles junction table
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role_id", sa.String(length=32), nullable=False),
        sa.Column("assigned_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("assigned_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_roles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_user_roles_role_id_roles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by"],
            ["users.id"],
            name=op.f("fk_user_roles_assigned_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name=op.f("pk_user_roles")),
    )

    # 4. Create auth_sessions table
    op.create_table(
        "auth_sessions",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("last_active_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", UTCDateTime, nullable=False),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
    )
    op.create_index(
        op.f("ix_auth_sessions_session_token_hash"),
        "auth_sessions",
        ["session_token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_auth_sessions_user_id"),
        "auth_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_auth_sessions_user_status"),
        "auth_sessions",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_auth_sessions_expires_at"),
        "auth_sessions",
        ["expires_at"],
        unique=False,
    )
    # Partial unique index enforcing single active session per user
    op.create_index(
        "idx_auth_sessions_unique_active_user",
        "auth_sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )

    # 5. Create auth_tokens table
    op.create_table(
        "auth_tokens",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_type", sa.String(length=32), nullable=False),
        sa.Column("is_used", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("expires_at", UTCDateTime, nullable=False),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_tokens")),
    )
    op.create_index(op.f("ix_auth_tokens_token_hash"), "auth_tokens", ["token_hash"], unique=True)
    op.create_index(op.f("ix_auth_tokens_user_id"), "auth_tokens", ["user_id"], unique=False)
    op.create_index(
        "ix_auth_tokens_hash_type_used",
        "auth_tokens",
        ["token_hash", "token_type", "is_used"],
        unique=False,
    )
    op.create_index(
        "ix_auth_tokens_user_type",
        "auth_tokens",
        ["user_id", "token_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_auth_tokens_expires_at"),
        "auth_tokens",
        ["expires_at"],
        unique=False,
    )

    # 6. Attach Foreign Key on audit_logs.actor_id -> users.id (PostgreSQL only)
    if bind.dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_audit_logs_actor_id_users",
            "audit_logs",
            "users",
            ["actor_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Drop FKs, auth_tokens, auth_sessions, user_roles, users, and roles tables."""
    bind = op.get_bind()

    # Drop audit_logs FK if present
    if bind.dialect.name == "postgresql":
        op.drop_constraint("fk_audit_logs_actor_id_users", "audit_logs", type_="foreignkey")

    # Drop auth_tokens indexes and table
    op.drop_index(op.f("ix_auth_tokens_expires_at"), table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_user_type", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_hash_type_used", table_name="auth_tokens")
    op.drop_index(op.f("ix_auth_tokens_user_id"), table_name="auth_tokens")
    op.drop_index(op.f("ix_auth_tokens_token_hash"), table_name="auth_tokens")
    op.drop_table("auth_tokens")

    # Drop auth_sessions indexes and table
    op.drop_index("idx_auth_sessions_unique_active_user", table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_expires_at"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_user_status"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_session_token_hash"), table_name="auth_sessions")
    op.drop_table("auth_sessions")

    # Drop user_roles table
    op.drop_table("user_roles")

    # Drop users indexes and table
    op.drop_index(op.f("ix_users_created_at"), table_name="users")
    op.drop_index(op.f("ix_users_is_active"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    # Drop roles table
    op.drop_table("roles")
