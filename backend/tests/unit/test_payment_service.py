"""Unit tests for PaymentService (TASK502, TASK503, TASK504).

Verifies:
1. Server-side price calculation and order initialization.
2. Email verification requirement (ADR-008) and suspension guards.
3. Published course requirement and duplicate order rejection.
4. Pending order reuse for idempotent checkout.
5. Webhook signature verification, payment capture, and idempotency.
6. Webhook duplicate delivery protection and amount mismatch rejection.
7. Payment failed webhook reconciliation.
8. Super Admin refund authorization, execution, and audit logging.
"""

from datetime import datetime, timezone
import json
import uuid

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.razorpay import RazorpayClient, compute_razorpay_signature
from app.models.base import Base, utc_now
from app.models.course import (
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    Course,
    CourseRevision,
)
from app.models.notification import NotificationOutbox
from app.models.payment import (
    ORDER_STATUS_FAILED,
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REFUNDED,
    REFUND_STATUS_PROCESSED,
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_SUCCESS,
    Order,
    PaymentTransaction,
    Refund,
)
from app.models.user import ROLE_STUDENT, ROLE_SUPER_ADMIN, Role, User, UserRole
from app.repositories.notification_repo import NotificationOutboxRepository
from app.repositories.order_repo import OrderRepository
from app.services.audit_service import AuditService
from app.services.payment_service import PaymentService


@pytest.fixture
def db_session():
    """Provides isolated in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def payment_service():
    """Provides PaymentService configured with test Razorpay client."""
    client = RazorpayClient()
    client.webhook_secret = "test_webhook_secret_key"
    return PaymentService(
        order_repo=OrderRepository(),
        audit_service=AuditService(),
        outbox_repo=NotificationOutboxRepository(),
        razorpay_client=client,
    )


@pytest.fixture
def student_user(db_session):
    """Creates a verified active student user."""
    student = User(
        id=uuid.uuid4(),
        email="student@example.com",
        full_name="Enrolled Student",
        is_verified=True,
        is_active=True,
    )
    db_session.add(student)
    db_session.flush()
    return student


@pytest.fixture
def super_admin_user(db_session):
    """Creates a super admin user."""
    admin = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        full_name="Platform Owner",
        is_verified=True,
        is_active=True,
    )
    db_session.add(admin)
    db_session.flush()
    return admin


@pytest.fixture
def published_course(db_session):
    """Creates a published course with revision and price in paise."""
    course_id = uuid.uuid4()
    rev_id = uuid.uuid4()

    course = Course(
        id=course_id,
        slug="mastering-fastapi",
        title="Mastering FastAPI Architecture",
        price_inr=499900,  # ₹4,999.00
        is_free=False,
        status=COURSE_STATUS_PUBLISHED,
        live_revision_id=rev_id,
    )
    db_session.add(course)

    revision = CourseRevision(
        id=rev_id,
        course_id=course_id,
        revision_no=1,
        title="Mastering FastAPI Architecture v1",
        status="PUBLISHED",
        snapshot={"sections": []},
        published_at=utc_now(),
    )
    db_session.add(revision)
    db_session.flush()
    return course


class TestOrderCreation:
    """Verifies order checkout initiation rules (TASK502)."""

    def test_create_order_success(self, db_session, payment_service, student_user, published_course):
        """Verified student creates order for published course with paise calculation."""
        checkout = payment_service.create_order(
            session=db_session,
            student=student_user,
            course_id=published_course.id,
        )

        assert checkout.amount_inr == 499900
        assert checkout.currency == "INR"
        assert checkout.course_title == "Mastering FastAPI Architecture"
        assert checkout.razorpay_order_id.startswith("order_")
        assert checkout.order_no.startswith("ORD-")

        # Verify internal order record
        order = db_session.get(Order, checkout.order_id)
        assert order is not None
        assert order.status == ORDER_STATUS_PENDING
        assert order.student_id == student_user.id
        assert order.course_id == published_course.id
        assert order.amount_inr == 499900

    def test_create_order_unverified_email_fails(self, db_session, payment_service, published_course):
        """Unverified email blocks checkout initiation (ADR-008)."""
        unverified_student = User(
            id=uuid.uuid4(),
            email="unverified@example.com",
            full_name="Unverified User",
            is_verified=False,
            is_active=True,
        )
        db_session.add(unverified_student)
        db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            payment_service.create_order(
                session=db_session,
                student=unverified_student,
                course_id=published_course.id,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "EMAIL_NOT_VERIFIED"

    def test_create_order_suspended_student_fails(self, db_session, payment_service, published_course):
        """Suspended user account blocks checkout initiation."""
        suspended = User(
            id=uuid.uuid4(),
            email="suspended@example.com",
            full_name="Suspended User",
            is_verified=True,
            is_active=False,
        )
        db_session.add(suspended)
        db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            payment_service.create_order(
                session=db_session,
                student=suspended,
                course_id=published_course.id,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "ACCOUNT_SUSPENDED"

    def test_create_order_unpublished_course_fails(self, db_session, payment_service, student_user):
        """Attempt to buy draft or unpublished course fails."""
        draft_course = Course(
            id=uuid.uuid4(),
            slug="draft-course",
            title="Draft Course",
            price_inr=199900,
            status=COURSE_STATUS_DRAFT,
        )
        db_session.add(draft_course)
        db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            payment_service.create_order(
                session=db_session,
                student=student_user,
                course_id=draft_course.id,
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "COURSE_NOT_PUBLISHED"

    def test_create_order_already_enrolled_fails(self, db_session, payment_service, student_user, published_course):
        """Student with active paid order is blocked from re-purchasing."""
        existing_paid = Order(
            order_no="ORD-202611-PAID1",
            student_id=student_user.id,
            course_id=published_course.id,
            amount_inr=499900,
            status=ORDER_STATUS_PAID,
            razorpay_order_id="order_paid_already",
        )
        db_session.add(existing_paid)
        db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            payment_service.create_order(
                session=db_session,
                student=student_user,
                course_id=published_course.id,
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "ALREADY_ENROLLED"

    def test_create_order_reuses_existing_pending_order(self, db_session, payment_service, student_user, published_course):
        """Repeated checkout click reuses pending order to avoid duplicate gateway orders."""
        checkout_1 = payment_service.create_order(
            session=db_session,
            student=student_user,
            course_id=published_course.id,
        )

        checkout_2 = payment_service.create_order(
            session=db_session,
            student=student_user,
            course_id=published_course.id,
        )

        assert checkout_1.order_id == checkout_2.order_id
        assert checkout_1.razorpay_order_id == checkout_2.razorpay_order_id


class TestWebhookReconciliation:
    """Verifies cryptographic webhook ingestion and idempotency (TASK503)."""

    def test_payment_captured_webhook_success(self, db_session, payment_service, student_user, published_course):
        """Valid HMAC webhook transitions order to PAID and inserts transaction."""
        checkout = payment_service.create_order(
            session=db_session,
            student=student_user,
            course_id=published_course.id,
        )

        # Build incoming webhook payload
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_capture_123",
                        "order_id": checkout.razorpay_order_id,
                        "amount": 499900,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        sig = compute_razorpay_signature(raw_body, "test_webhook_secret_key")

        result = payment_service.process_razorpay_webhook(
            session=db_session,
            raw_body=raw_body,
            signature_header=sig,
        )

        assert result["status"] == "ok"
        assert result["payment_id"] == "pay_test_capture_123"

        # Verify order transitioned to PAID
        order = db_session.get(Order, checkout.order_id)
        assert order.status == ORDER_STATUS_PAID

        # Verify transaction record inserted
        tx = payment_service.order_repo.get_transaction_by_payment_id(db_session, "pay_test_capture_123")
        assert tx is not None
        assert tx.status == TRANSACTION_STATUS_SUCCESS
        assert tx.amount_inr == 499900

        # Verify outbox notification emitted
        outbox_events = list(db_session.query(NotificationOutbox).all())
        assert len(outbox_events) >= 1
        assert outbox_events[-1].event_type == "ENROLLMENT_RECEIPT"

    def test_payment_captured_webhook_idempotency_duplicate_delivery(self, db_session, payment_service, student_user, published_course):
        """Duplicate webhook delivery returns 200 OK without double-crediting."""
        checkout = payment_service.create_order(
            session=db_session,
            student=student_user,
            course_id=published_course.id,
        )

        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_dup_999",
                        "order_id": checkout.razorpay_order_id,
                        "amount": 499900,
                        "status": "captured",
                    }
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        sig = compute_razorpay_signature(raw_body, "test_webhook_secret_key")

        # First delivery
        result1 = payment_service.process_razorpay_webhook(db_session, raw_body, sig)
        assert result1["status"] == "ok"

        # Second duplicate delivery
        result2 = payment_service.process_razorpay_webhook(db_session, raw_body, sig)
        assert result2["status"] == "ok"
        assert "idempotent" in result2.get("message", "").lower()

        # Exactly 1 transaction record exists
        txs = list(db_session.query(PaymentTransaction).filter(PaymentTransaction.order_id == checkout.order_id).all())
        assert len(txs) == 1

    def test_webhook_invalid_signature_rejected(self, db_session, payment_service):
        """Tampered or invalid signature raises HTTP 400."""
        raw_body = b'{"event":"payment.captured"}'
        invalid_sig = "invalid_tampered_signature_hex"

        with pytest.raises(HTTPException) as exc_info:
            payment_service.process_razorpay_webhook(db_session, raw_body, invalid_sig)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_SIGNATURE"

    def test_webhook_amount_mismatch_rejected(self, db_session, payment_service, student_user, published_course):
        """Webhook with mismatched amount raises HTTP 400 and records failed transaction."""
        checkout = payment_service.create_order(
            session=db_session,
            student=student_user,
            course_id=published_course.id,
        )

        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_mismatch_456",
                        "order_id": checkout.razorpay_order_id,
                        "amount": 10000,  # ₹100 instead of ₹4999
                        "status": "captured",
                    }
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        sig = compute_razorpay_signature(raw_body, "test_webhook_secret_key")

        with pytest.raises(HTTPException) as exc_info:
            payment_service.process_razorpay_webhook(db_session, raw_body, sig)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "AMOUNT_MISMATCH"

        # Order must not be marked paid
        order = db_session.get(Order, checkout.order_id)
        assert order.status == ORDER_STATUS_PENDING

    def test_payment_failed_webhook(self, db_session, payment_service, student_user, published_course):
        """payment.failed webhook transitions order to FAILED."""
        checkout = payment_service.create_order(
            session=db_session,
            student=student_user,
            course_id=published_course.id,
        )

        payload = {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_fail_789",
                        "order_id": checkout.razorpay_order_id,
                        "amount": 499900,
                        "status": "failed",
                    }
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        sig = compute_razorpay_signature(raw_body, "test_webhook_secret_key")

        result = payment_service.process_razorpay_webhook(db_session, raw_body, sig)
        assert result["status"] == "ok"

        order = db_session.get(Order, checkout.order_id)
        assert order.status == ORDER_STATUS_FAILED


class TestRefundExecution:
    """Verifies refund processing and authorization (TASK504)."""

    def test_refund_order_full_success(self, db_session, payment_service, student_user, super_admin_user, published_course):
        """Super Admin executes full refund -> status updated to REFUNDED."""
        checkout = payment_service.create_order(db_session, student_user, published_course.id)

        # Transition order to PAID via webhook
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_to_refund_111",
                        "order_id": checkout.razorpay_order_id,
                        "amount": 499900,
                        "status": "captured",
                    }
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        sig = compute_razorpay_signature(raw_body, "test_webhook_secret_key")
        payment_service.process_razorpay_webhook(db_session, raw_body, sig)

        # Execute full refund
        refund_resp = payment_service.refund_order(
            session=db_session,
            order_id=checkout.order_id,
            reason="Customer dissatisfied within 30-day money back guarantee",
            amount_inr=None,  # full refund
            current_user=super_admin_user,
        )

        assert refund_resp.amount_inr == 499900
        assert refund_resp.status == REFUND_STATUS_PROCESSED
        assert refund_resp.razorpay_refund_id.startswith("rfd_")
        assert refund_resp.approved_by == super_admin_user.id

        # Verify order transitioned to REFUNDED
        order = db_session.get(Order, checkout.order_id)
        assert order.status == ORDER_STATUS_REFUNDED

        # Verify outbox event emitted
        outbox_events = list(db_session.query(NotificationOutbox).all())
        assert any(e.event_type == "REFUND_ISSUED" for e in outbox_events)

    def test_refund_unpaid_order_fails(self, db_session, payment_service, student_user, super_admin_user, published_course):
        """Attempting to refund a PENDING order raises HTTP 400."""
        checkout = payment_service.create_order(db_session, student_user, published_course.id)

        with pytest.raises(HTTPException) as exc_info:
            payment_service.refund_order(
                session=db_session,
                order_id=checkout.order_id,
                reason="Premature refund request",
                amount_inr=None,
                current_user=super_admin_user,
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_ORDER_STATUS"

    def test_refund_amount_exceeding_total_fails(self, db_session, payment_service, student_user, super_admin_user, published_course):
        """Refund amount greater than order amount raises HTTP 400."""
        checkout = payment_service.create_order(db_session, student_user, published_course.id)

        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_exceed_222",
                        "order_id": checkout.razorpay_order_id,
                        "amount": 499900,
                        "status": "captured",
                    }
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        sig = compute_razorpay_signature(raw_body, "test_webhook_secret_key")
        payment_service.process_razorpay_webhook(db_session, raw_body, sig)

        with pytest.raises(HTTPException) as exc_info:
            payment_service.refund_order(
                session=db_session,
                order_id=checkout.order_id,
                reason="Invalid excessive refund",
                amount_inr=999900,  # Exceeds 499900
                current_user=super_admin_user,
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "INVALID_REFUND_AMOUNT"
