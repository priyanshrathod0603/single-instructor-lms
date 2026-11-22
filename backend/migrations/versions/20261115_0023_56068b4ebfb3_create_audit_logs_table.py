"""create_audit_logs_table

Revision ID: 56068b4ebfb3
Revises: 
Create Date: 2026-11-15 00:23:58.904121

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 35)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-013)

Strict Invariants:
1. Append-only persistence. No updated_at column.
2. PostgreSQL trigger function and 3 distinct triggers preventing UPDATE, DELETE, and TRUNCATE.
3. No foreign key constraint on actor_id in Part 0.
4. Production requirement: runtime role must not possess UPDATE, DELETE, or TRUNCATE privileges.
"""
from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Custom application types support for timezone-aware UTC persistence
from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = '56068b4ebfb3'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create audit_logs table, indexes, and PostgreSQL immutability triggers."""
    # 1. Create audit_logs table
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(length=32), server_default=sa.text("'SYSTEM'"), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column(
            "before_state",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "after_state",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )

    # 2. Required Performance Indexes
    op.create_index(
        op.f("ix_audit_logs_actor_id_created_at"),
        "audit_logs",
        ["actor_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_logs_resource_created_at"),
        "audit_logs",
        ["resource_type", "resource_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_logs_action_created_at"),
        "audit_logs",
        ["action", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_logs_request_id"),
        "audit_logs",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_logs_created_at"),
        "audit_logs",
        [sa.text("created_at DESC")],
        unique=False,
    )

    # 3. PostgreSQL Immutability Function and Triggers
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Create immutability trigger function
        op.execute("""
            CREATE OR REPLACE FUNCTION trg_audit_logs_prevent_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Security Policy Violation: audit_logs records are strictly immutable. % operations are prohibited.', TG_OP
                    USING ERRCODE = 'integrity_constraint_violation';
            END;
            $$ LANGUAGE plpgsql;
        """)

        # Trigger A: UPDATE protection (BEFORE UPDATE FOR EACH ROW)
        op.execute("""
            CREATE TRIGGER trg_audit_logs_prevent_update
            BEFORE UPDATE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION trg_audit_logs_prevent_mutation();
        """)

        # Trigger B: DELETE protection (BEFORE DELETE FOR EACH ROW)
        op.execute("""
            CREATE TRIGGER trg_audit_logs_prevent_delete
            BEFORE DELETE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION trg_audit_logs_prevent_mutation();
        """)

        # Trigger C: TRUNCATE protection (BEFORE TRUNCATE FOR EACH STATEMENT)
        op.execute("""
            CREATE TRIGGER trg_audit_logs_prevent_truncate
            BEFORE TRUNCATE ON audit_logs
            FOR EACH STATEMENT EXECUTE FUNCTION trg_audit_logs_prevent_mutation();
        """)


def downgrade() -> None:
    """Drop PostgreSQL immutability triggers, trigger function, indexes, and audit_logs table."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Drop triggers before dropping function
        op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_prevent_truncate ON audit_logs;")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_prevent_delete ON audit_logs;")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_prevent_update ON audit_logs;")
        op.execute("DROP FUNCTION IF EXISTS trg_audit_logs_prevent_mutation();")

    # Drop indexes
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_request_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_resource_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id_created_at"), table_name="audit_logs")

    # Drop table
    op.drop_table("audit_logs")
