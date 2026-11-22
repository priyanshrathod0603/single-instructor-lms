"""add_session_revocation_metadata_and_indexes

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-16 18:10:00.000000

Architecture Specifications:
- docs/SA-03_SECURITY_GOVERNANCE_SPECIFICATION.md (SA-03.1, Sections 4.3, 11.1, 14.1, 14.2)
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf [Blueprint v2.0, Pages 1-16]

Strict Invariants & Safety Controls:
1. Lock Timeout: Applies SET lock_timeout = '2s' before DDL to prevent connection pool queueing.
2. Nullable Columns: Adds revoked_at (TIMESTAMPTZ), revoked_by (UUID), revocation_reason (VARCHAR(255))
   as nullable columns. Preserves all existing active, revoked, and expired session records.
3. Two-Phase FK Constraint: In PostgreSQL, adds foreign key constraint with NOT VALID followed by
   VALIDATE CONSTRAINT to avoid table read/write locks during validation.
4. Concurrent Indexes: In PostgreSQL, creates indexes using postgresql_concurrently=True inside an
   Alembic autocommit_block() to avoid write locks and transaction block violations.
5. Invariant Preservation: Preserves existing single-active-session partial unique index
   (idx_auth_sessions_unique_active_user) and primary key constraints.
6. Downgrade Implementation: Completely reversible teardown dropping indexes, constraints, and columns.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# Custom application types support for timezone-aware UTC persistence
from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add revocation metadata columns and performance indexes with lock timeout and concurrent index builds."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Step 1: Set strict lock timeout to prevent queueing behind long-running queries
    if is_postgres:
        op.execute("SET lock_timeout = '2s';")

    # Step 2: Add nullable session revocation metadata columns to auth_sessions
    op.add_column("auth_sessions", sa.Column("revoked_at", UTCDateTime, nullable=True))
    op.add_column("auth_sessions", sa.Column("revoked_by", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("auth_sessions", sa.Column("revocation_reason", sa.String(length=255), nullable=True))

    # Step 3: Add foreign key constraint from auth_sessions.revoked_by to users.id
    if is_postgres:
        # Two-phase constraint creation: add NOT VALID, then validate to avoid table locks
        op.execute("""
            ALTER TABLE auth_sessions
            ADD CONSTRAINT fk_auth_sessions_revoked_by_users
            FOREIGN KEY (revoked_by) REFERENCES users(id) ON DELETE SET NULL NOT VALID;
        """)
        op.execute("""
            ALTER TABLE auth_sessions
            VALIDATE CONSTRAINT fk_auth_sessions_revoked_by_users;
        """)
        # Reset lock timeout to default
        op.execute("SET lock_timeout = '0';")
    else:
        with op.batch_alter_table("auth_sessions") as batch_op:
            batch_op.create_foreign_key(
                "fk_auth_sessions_revoked_by_users",
                "users",
                ["revoked_by"],
                ["id"],
                ondelete="SET NULL",
            )

    # Step 4: Approved Performance & Forensic Indexes
    # In PostgreSQL, CREATE INDEX CONCURRENTLY must run outside an active transaction block.
    if is_postgres:
        with op.get_context().autocommit_block():
            # A. Composite index for admin session surveillance (filtering by status and sorting by created_at DESC)
            op.create_index(
                "ix_auth_sessions_status_created_at",
                "auth_sessions",
                ["status", sa.text("created_at DESC")],
                unique=False,
                postgresql_concurrently=True,
            )
            # B. Partial index on auth_sessions client IP for incident investigation
            op.create_index(
                "ix_auth_sessions_ip_address",
                "auth_sessions",
                ["ip_address"],
                unique=False,
                postgresql_where=sa.text("ip_address IS NOT NULL"),
                postgresql_concurrently=True,
            )
            # C. Partial index on immutable audit_logs client IP for forensic tracing
            op.create_index(
                "ix_audit_logs_ip_address",
                "audit_logs",
                ["ip_address"],
                unique=False,
                postgresql_where=sa.text("ip_address IS NOT NULL"),
                postgresql_concurrently=True,
            )
    else:
        op.create_index(
            "ix_auth_sessions_status_created_at",
            "auth_sessions",
            ["status", sa.text("created_at DESC")],
            unique=False,
        )
        op.create_index(
            "ix_auth_sessions_ip_address",
            "auth_sessions",
            ["ip_address"],
            unique=False,
            sqlite_where=sa.text("ip_address IS NOT NULL"),
        )
        op.create_index(
            "ix_audit_logs_ip_address",
            "audit_logs",
            ["ip_address"],
            unique=False,
            sqlite_where=sa.text("ip_address IS NOT NULL"),
        )


def downgrade() -> None:
    """Safely drop indexes, foreign key constraint, and columns in reverse order."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Step 1: Drop indexes (concurrently in PostgreSQL outside transaction block)
    if is_postgres:
        with op.get_context().autocommit_block():
            op.drop_index(
                "ix_audit_logs_ip_address",
                table_name="audit_logs",
                postgresql_concurrently=True,
            )
            op.drop_index(
                "ix_auth_sessions_ip_address",
                table_name="auth_sessions",
                postgresql_concurrently=True,
            )
            op.drop_index(
                "ix_auth_sessions_status_created_at",
                table_name="auth_sessions",
                postgresql_concurrently=True,
            )
        op.execute("SET lock_timeout = '2s';")
    else:
        op.drop_index("ix_audit_logs_ip_address", table_name="audit_logs")
        op.drop_index("ix_auth_sessions_ip_address", table_name="auth_sessions")
        op.drop_index("ix_auth_sessions_status_created_at", table_name="auth_sessions")

    # Step 2 & 3: Drop foreign key constraint and added columns
    if is_postgres:
        op.drop_constraint("fk_auth_sessions_revoked_by_users", "auth_sessions", type_="foreignkey")
        op.drop_column("auth_sessions", "revocation_reason")
        op.drop_column("auth_sessions", "revoked_by")
        op.drop_column("auth_sessions", "revoked_at")
        op.execute("SET lock_timeout = '0';")
    else:
        with op.batch_alter_table("auth_sessions") as batch_op:
            batch_op.drop_constraint("fk_auth_sessions_revoked_by_users", type_="foreignkey")
            batch_op.drop_column("revocation_reason")
            batch_op.drop_column("revoked_by")
            batch_op.drop_column("revoked_at")
