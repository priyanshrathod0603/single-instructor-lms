"""Order, PaymentTransaction, and Refund database models for LMS commerce.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 5, Tables 25, 26, 27)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK501)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004, ADR-005)

Strict Invariants:
1. Minor Currency Units: All prices and transaction amounts are stored in BIGINT paise (1 INR = 100 paise).
2. Zero Trust on Browser Redirect: Paid status is updated exclusively upon verified webhook ingestion.
3. Idempotent Processing: Unique constraint on payment_transactions.razorpay_payment_id prevents double execution.
4. Clean Foreign Keys: RESTRICT deletion on users and courses to maintain immutable commercial ledger.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
    utc_now,
)

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.user import User

# Canonical order status constants
ORDER_STATUS_PENDING = "PENDING"
ORDER_STATUS_PAID = "PAID"
ORDER_STATUS_FAILED = "FAILED"
ORDER_STATUS_EXPIRED = "EXPIRED"
ORDER_STATUS_REFUNDED = "REFUNDED"

ORDER_STATUSES = frozenset({
    ORDER_STATUS_PENDING,
    ORDER_STATUS_PAID,
    ORDER_STATUS_FAILED,
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_REFUNDED,
})

# Canonical payment transaction status constants
TRANSACTION_STATUS_SUCCESS = "SUCCESS"
TRANSACTION_STATUS_FAILED = "FAILED"

TRANSACTION_STATUSES = frozenset({
    TRANSACTION_STATUS_SUCCESS,
    TRANSACTION_STATUS_FAILED,
})

# Canonical refund status constants
REFUND_STATUS_PENDING = "PENDING"
REFUND_STATUS_PROCESSED = "PROCESSED"
REFUND_STATUS_FAILED = "FAILED"

REFUND_STATUSES = frozenset({
    REFUND_STATUS_PENDING,
    REFUND_STATUS_PROCESSED,
    REFUND_STATUS_FAILED,
})


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Commercial intent records representing a course checkout order."""

    __tablename__ = "orders"

    order_no: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
        doc="Human-readable unique order identifier (e.g. 'ORD-202611-0001')",
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Student user purchasing the course",
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Target course being purchased",
    )
    amount_inr: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Order amount in minor currency units (paise in INR; 1 INR = 100 paise)",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default=sa.text("'INR'"),
        doc="ISO 4217 three-letter currency code (strictly 'INR')",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ORDER_STATUS_PENDING,
        server_default=sa.text("'PENDING'"),
        index=True,
        doc="Order status: PENDING, PAID, FAILED, EXPIRED, REFUNDED",
    )
    razorpay_order_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        unique=True,
        nullable=True,
        index=True,
        doc="External Razorpay order ID (e.g. 'order_Hdf81923ns')",
    )

    # Relationships
    student: Mapped["User"] = relationship(
        "User",
        back_populates="orders",
        foreign_keys=[student_id],
        lazy="joined",
    )
    course: Mapped["Course"] = relationship(
        "Course",
        back_populates="orders",
        foreign_keys=[course_id],
        lazy="joined",
    )
    transactions: Mapped[List["PaymentTransaction"]] = relationship(
        "PaymentTransaction",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="select",
    )
    refunds: Mapped[List["Refund"]] = relationship(
        "Refund",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="select",
    )

    __table_args__ = (
        Index("ix_orders_student_status", "student_id", "status"),
        Index("ix_orders_course_status", "course_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Order id={self.id} order_no={self.order_no!r} status={self.status!r} amount={self.amount_inr}>"


class PaymentTransaction(Base, UUIDPrimaryKeyMixin):
    """Payment gateway execution logs verified via cryptographic webhook."""

    __tablename__ = "payment_transactions"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Parent commercial order foreign key",
    )
    gateway: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="RAZORPAY",
        server_default=sa.text("'RAZORPAY'"),
        doc="Payment gateway identifier (e.g. 'RAZORPAY')",
    )
    razorpay_payment_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        doc="External gateway payment ID (e.g. 'pay_29QQoUBcxQtv4w')",
    )
    razorpay_signature: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="HMAC-SHA256 signature transmitted in X-Razorpay-Signature header",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        doc="Transaction execution status: SUCCESS or FAILED",
    )
    amount_inr: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Captured payment amount in minor units (paise)",
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
        nullable=False,
        doc="Exact incoming signed webhook JSON payload for complete financial auditability",
    )
    processed_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when transaction was processed and verified",
    )

    # Relationships
    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="transactions",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<PaymentTransaction id={self.id} payment_id={self.razorpay_payment_id!r} status={self.status!r}>"


class Refund(Base, UUIDPrimaryKeyMixin):
    """Authorized payment refund records approved by Super Admin."""

    __tablename__ = "refunds"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Parent order being refunded",
    )
    amount_inr: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Refund amount in minor units (paise)",
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Mandatory business reason and justification for the refund",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=REFUND_STATUS_PENDING,
        server_default=sa.text("'PENDING'"),
        doc="Refund execution status: PENDING, PROCESSED, FAILED",
    )
    razorpay_refund_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        unique=True,
        nullable=True,
        index=True,
        doc="External gateway refund ID (e.g. 'rfnd_Hdf81923ns')",
    )
    approved_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Super Admin user who authorized the refund",
    )
    processed_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        default=utc_now,
        server_default=func.now(),
        doc="UTC timestamp when refund was executed",
    )

    # Relationships
    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="refunds",
        lazy="joined",
    )
    approver: Mapped["User"] = relationship(
        "User",
        foreign_keys=[approved_by],
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<Refund id={self.id} order_id={self.order_id} amount={self.amount_inr} status={self.status!r} razorpay_refund_id={self.razorpay_refund_id!r}>"
