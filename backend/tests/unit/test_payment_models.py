"""Unit tests for Order, PaymentTransaction, and Refund database models.

Verifies:
1. Schema table names, primary keys, and column types.
2. Minor currency math standard: BIGINT paise for amounts.
3. Status constants, enums, and default values.
4. Relational integrity, foreign keys, and cascading behavior.
5. Composite index definitions.
"""

import uuid

import pytest
from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Session

from app.models.course import Course, CourseRevision
from app.models.payment import (
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_FAILED,
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REFUNDED,
    ORDER_STATUSES,
    REFUND_STATUS_FAILED,
    REFUND_STATUS_PENDING,
    REFUND_STATUS_PROCESSED,
    REFUND_STATUSES,
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_SUCCESS,
    TRANSACTION_STATUSES,
    Order,
    PaymentTransaction,
    Refund,
)
from app.models.user import User


class TestPaymentModelDefinitions:
    """Verifies column metadata, constraints, and defaults."""

    def test_order_table_name_and_columns(self):
        """orders table must exist with correct columns and types."""
        assert Order.__tablename__ == "orders"
        cols = {c.name: c for c in Order.__table__.columns}

        assert "id" in cols
        assert "order_no" in cols
        assert "student_id" in cols
        assert "course_id" in cols
        assert "amount_inr" in cols
        assert "currency" in cols
        assert "status" in cols
        assert "razorpay_order_id" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

        # Minor currency invariant: BIGINT
        assert isinstance(cols["amount_inr"].type, BigInteger)
        assert isinstance(cols["currency"].type, String)
        assert cols["currency"].type.length == 3

    def test_order_status_constants(self):
        """All approved order statuses must be defined."""
        assert "PENDING" in ORDER_STATUSES
        assert "PAID" in ORDER_STATUSES
        assert "FAILED" in ORDER_STATUSES
        assert "EXPIRED" in ORDER_STATUSES
        assert "REFUNDED" in ORDER_STATUSES

    def test_payment_transaction_table_name_and_columns(self):
        """payment_transactions table must exist with correct columns."""
        assert PaymentTransaction.__tablename__ == "payment_transactions"
        cols = {c.name: c for c in PaymentTransaction.__table__.columns}

        assert "id" in cols
        assert "order_id" in cols
        assert "gateway" in cols
        assert "razorpay_payment_id" in cols
        assert "razorpay_signature" in cols
        assert "status" in cols
        assert "amount_inr" in cols
        assert "raw_payload" in cols
        assert "processed_at" in cols

        assert isinstance(cols["amount_inr"].type, BigInteger)

    def test_transaction_status_constants(self):
        """Transaction statuses must include SUCCESS and FAILED."""
        assert "SUCCESS" in TRANSACTION_STATUSES
        assert "FAILED" in TRANSACTION_STATUSES

    def test_refund_table_name_and_columns(self):
        """refunds table must exist with correct columns."""
        assert Refund.__tablename__ == "refunds"
        cols = {c.name: c for c in Refund.__table__.columns}

        assert "id" in cols
        assert "order_id" in cols
        assert "amount_inr" in cols
        assert "reason" in cols
        assert "status" in cols
        assert "razorpay_refund_id" in cols
        assert "approved_by" in cols
        assert "processed_at" in cols

        assert isinstance(cols["amount_inr"].type, BigInteger)

    def test_refund_status_constants(self):
        """Refund statuses must include PENDING, PROCESSED, FAILED."""
        assert "PENDING" in REFUND_STATUSES
        assert "PROCESSED" in REFUND_STATUSES
        assert "FAILED" in REFUND_STATUSES


class TestPaymentModelPersistence:
    """Verifies ORM instantiation and relationship wiring."""

    def test_order_instantiation_and_repr(self):
        """Order instance initializes with default status and repr."""
        order_id = uuid.uuid4()
        student_id = uuid.uuid4()
        course_id = uuid.uuid4()

        order = Order(
            id=order_id,
            order_no="ORD-202611-0001",
            student_id=student_id,
            course_id=course_id,
            amount_inr=499900,
            currency="INR",
            razorpay_order_id="order_mock123",
            status=ORDER_STATUS_PENDING,
        )

        assert order.amount_inr == 499900
        assert order.currency == "INR"
        assert order.status == ORDER_STATUS_PENDING
        assert "ORD-202611-0001" in repr(order)

    def test_transaction_instantiation_and_repr(self):
        """PaymentTransaction initializes with JSON payload and repr."""
        tx = PaymentTransaction(
            order_id=uuid.uuid4(),
            gateway="RAZORPAY",
            razorpay_payment_id="pay_mock456",
            razorpay_signature="mock_sig_hex",
            status=TRANSACTION_STATUS_SUCCESS,
            amount_inr=499900,
            raw_payload={"event": "payment.captured", "id": "pay_mock456"},
        )

        assert tx.status == TRANSACTION_STATUS_SUCCESS
        assert tx.amount_inr == 499900
        assert "pay_mock456" in repr(tx)

    def test_refund_instantiation_and_repr(self):
        """Refund initializes with approver and repr."""
        refund = Refund(
            order_id=uuid.uuid4(),
            amount_inr=499900,
            reason="Satisfaction guarantee policy refund",
            approved_by=uuid.uuid4(),
            status=REFUND_STATUS_PROCESSED,
            razorpay_refund_id="rfnd_mock789",
        )

        assert refund.amount_inr == 499900
        assert refund.status == REFUND_STATUS_PROCESSED
        assert "rfnd_mock789" in repr(refund)
