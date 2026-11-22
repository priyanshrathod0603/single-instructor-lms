"""create_commerce_and_order_tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-15 05:00:00.000000

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 5, Tables 25, 26, 27)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK501)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004, ADR-005)

Strict Invariants:
1. Minor currency math: BIGINT paise for exact integer ledger calculations.
2. Zero trust on browser redirect: Payment verification occurs via cryptographic webhook.
3. Clean downgrade: Symmetrically drops refunds, payment_transactions, and orders.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Custom application types support for timezone-aware UTC persistence
from app.models.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create orders, payment_transactions, and refunds tables."""
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    # 1. orders table
    op.create_table(
        "orders",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("order_no", sa.String(length=32), nullable=False),
        sa.Column("student_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("amount_inr", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'INR'"), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("razorpay_order_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name=op.f("fk_orders_student_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_orders_course_id_courses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("order_no", name=op.f("uq_orders_order_no")),
        sa.UniqueConstraint("razorpay_order_id", name=op.f("uq_orders_razorpay_order_id")),
    )
    op.create_index(op.f("ix_orders_order_no"), "orders", ["order_no"], unique=True)
    op.create_index(op.f("ix_orders_student_id"), "orders", ["student_id"], unique=False)
    op.create_index(op.f("ix_orders_course_id"), "orders", ["course_id"], unique=False)
    op.create_index(op.f("ix_orders_status"), "orders", ["status"], unique=False)
    op.create_index(op.f("ix_orders_razorpay_order_id"), "orders", ["razorpay_order_id"], unique=True)
    op.create_index("ix_orders_student_status", "orders", ["student_id", "status"], unique=False)
    op.create_index("ix_orders_course_status", "orders", ["course_id", "status"], unique=False)

    # 2. payment_transactions table
    op.create_table(
        "payment_transactions",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("gateway", sa.String(length=32), server_default=sa.text("'RAZORPAY'"), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(length=64), nullable=False),
        sa.Column("razorpay_signature", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("amount_inr", sa.BigInteger(), nullable=False),
        sa.Column("raw_payload", json_type, nullable=False),
        sa.Column("processed_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_payment_transactions_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_transactions")),
        sa.UniqueConstraint("razorpay_payment_id", name=op.f("uq_payment_transactions_razorpay_payment_id")),
    )
    op.create_index(op.f("ix_payment_transactions_order_id"), "payment_transactions", ["order_id"], unique=False)
    op.create_index(op.f("ix_payment_transactions_razorpay_payment_id"), "payment_transactions", ["razorpay_payment_id"], unique=True)

    # 3. refunds table
    op.create_table(
        "refunds",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("amount_inr", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("razorpay_refund_id", sa.String(length=64), nullable=True),
        sa.Column("approved_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("processed_at", UTCDateTime, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_refunds_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name=op.f("fk_refunds_approved_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refunds")),
        sa.UniqueConstraint("razorpay_refund_id", name=op.f("uq_refunds_razorpay_refund_id")),
    )
    op.create_index(op.f("ix_refunds_order_id"), "refunds", ["order_id"], unique=False)
    op.create_index(op.f("ix_refunds_razorpay_refund_id"), "refunds", ["razorpay_refund_id"], unique=True)
    op.create_index(op.f("ix_refunds_approved_by"), "refunds", ["approved_by"], unique=False)


def downgrade() -> None:
    """Drop refunds, payment_transactions, and orders tables."""
    # 1. refunds
    op.drop_index(op.f("ix_refunds_approved_by"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_razorpay_refund_id"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_order_id"), table_name="refunds")
    op.drop_table("refunds")

    # 2. payment_transactions
    op.drop_index(op.f("ix_payment_transactions_razorpay_payment_id"), table_name="payment_transactions")
    op.drop_index(op.f("ix_payment_transactions_order_id"), table_name="payment_transactions")
    op.drop_table("payment_transactions")

    # 3. orders
    op.drop_index("ix_orders_course_status", table_name="orders")
    op.drop_index("ix_orders_student_status", table_name="orders")
    op.drop_index(op.f("ix_orders_razorpay_order_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_status"), table_name="orders")
    op.drop_index(op.f("ix_orders_course_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_student_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_order_no"), table_name="orders")
    op.drop_table("orders")
