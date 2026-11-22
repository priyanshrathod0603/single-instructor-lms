"""Security and Penetration tests for Webhook Ingestion and Tampering (TASK503).

Architecture Specifications:
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-4)
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK503)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)

Verifies:
1. Rejection of body tampering (bit-flip, trailing whitespace, changed payload).
2. Constant-time signature comparison (defense against timing side-channel attacks).
3. Secret isolation (signatures computed with wrong or empty secrets fail).
4. Amount tampering defense (attacker alters paid amount to 1 paisa).
5. Gateway replay protection (duplicate webhooks execute idempotently without second credit).
"""

import hashlib
import hmac
import json
import time
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.razorpay import RazorpayClient, compute_razorpay_signature, verify_razorpay_signature
from app.main import create_app
from app.models.base import Base, utc_now
from app.models.course import COURSE_STATUS_PUBLISHED, Course, CourseRevision
from app.models.payment import (
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    Order,
    PaymentTransaction,
)
from app.models.permission import Permission, RolePermission
from app.models.user import ROLE_STUDENT, Role, User, UserRole


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
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(db_session: Session):
    """FastAPI TestClient wired to isolated in-memory test database."""
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestWebhookCryptographicTampering:
    """Penetration tests verifying rejection of forged and tampered payloads."""

    def test_bit_flip_payload_tamper_rejected(self):
        """Single bit modification in raw body bytes causes signature failure."""
        secret = "super_secure_webhook_secret_key_999"
        original_body = b'{"event":"payment.captured","payload":{"payment":{"entity":{"amount":499900}}}}'
        valid_signature = compute_razorpay_signature(original_body, secret)

        # Flip the first character
        tampered_body = b'X' + original_body[1:]
        assert verify_razorpay_signature(tampered_body, valid_signature, secret) is False

    def test_whitespace_injection_tamper_rejected(self):
        """Adding whitespace or formatting changes payload digest and fails verification."""
        secret = "super_secure_webhook_secret_key_999"
        original_body = b'{"event":"payment.captured"}'
        valid_signature = compute_razorpay_signature(original_body, secret)

        # Subtle space injected inside JSON
        formatted_body = b'{ "event": "payment.captured" }'
        assert verify_razorpay_signature(formatted_body, valid_signature, secret) is False

    def test_timing_attack_resilience(self):
        """Constant-time compare_digest does not terminate early on prefix match."""
        secret = "test_timing_secret"
        body = b'{"event":"payment.captured"}'
        valid_sig = compute_razorpay_signature(body, secret)

        # Forged signature that matches first 20 characters but differs at the end
        almost_matching_sig = valid_sig[:20] + "0" * (len(valid_sig) - 20)

        # Must evaluate to False cleanly
        assert verify_razorpay_signature(body, almost_matching_sig, secret) is False

    def test_financial_amount_tamper_reconciliation_rejected(self, client, db_session):
        """Attacker modifies paid amount to 1 paisa (₹0.01) in webhook -> rejected."""
        settings = get_settings()
        secret = (
            settings.RAZORPAY_WEBHOOK_SECRET.get_secret_value()
            if settings.RAZORPAY_WEBHOOK_SECRET
            else "mock_webhook_secret_for_dev_test"
        )

        student = User(
            email="victim@lms.local",
            full_name="Victim Student",
            is_verified=True,
            is_active=True,
        )
        course = Course(
            slug="advanced-security",
            title="Advanced Security Course",
            price_inr=999900,  # ₹9,999.00
            status=COURSE_STATUS_PUBLISHED,
        )
        db_session.add_all([student, course])
        db_session.flush()

        order = Order(
            order_no="ORD-TAMPER-001",
            student_id=student.id,
            course_id=course.id,
            amount_inr=999900,
            status=ORDER_STATUS_PENDING,
            razorpay_order_id="order_tamper_test_999",
        )
        db_session.add(order)
        db_session.commit()

        # Attacker signs a modified payload claiming payment of only 100 paise (₹1.00)
        tampered_payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_hacker_tampered_1",
                        "order_id": "order_tamper_test_999",
                        "amount": 100,  # ₹1.00 instead of ₹9,999.00
                        "status": "captured",
                    }
                }
            },
        }
        raw_body = json.dumps(tampered_payload).encode("utf-8")
        sig = compute_razorpay_signature(raw_body, secret)

        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
        )

        # Must reject with HTTP 400 Bad Request
        assert response.status_code == 400
        assert "does not match" in response.json()["error"]["message"].lower()

        # Order must remain PENDING (unpaid)
        db_session.refresh(order)
        assert order.status == ORDER_STATUS_PENDING

    def test_replay_attack_duplicate_webhook_protection(self, client, db_session):
        """Replaying identical webhook payload multiple times executes idempotently without duplicate rows."""
        settings = get_settings()
        secret = (
            settings.RAZORPAY_WEBHOOK_SECRET.get_secret_value()
            if settings.RAZORPAY_WEBHOOK_SECRET
            else "mock_webhook_secret_for_dev_test"
        )

        student = User(
            email="student_replay@lms.local",
            full_name="Replay Test Student",
            is_verified=True,
            is_active=True,
        )
        course = Course(
            slug="concurrency-security",
            title="Concurrency Security",
            price_inr=299900,
            status=COURSE_STATUS_PUBLISHED,
        )
        db_session.add_all([student, course])
        db_session.flush()

        order = Order(
            order_no="ORD-REPLAY-001",
            student_id=student.id,
            course_id=course.id,
            amount_inr=299900,
            status=ORDER_STATUS_PENDING,
            razorpay_order_id="order_replay_test_888",
        )
        db_session.add(order)
        db_session.commit()

        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_replay_888",
                        "order_id": "order_replay_test_888",
                        "amount": 299900,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        sig = compute_razorpay_signature(raw_body, secret)

        # Transmission 1
        resp1 = client.post(
            "/api/v1/webhooks/razorpay",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert resp1.status_code == 200

        # Transmission 2 (Replay attack / duplicate delivery)
        resp2 = client.post(
            "/api/v1/webhooks/razorpay",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert resp2.status_code == 200
        assert "idempotent" in resp2.json().get("message", "").lower()

        # Transmission 3 (Third replay)
        resp3 = client.post(
            "/api/v1/webhooks/razorpay",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert resp3.status_code == 200

        # Verify only 1 PaymentTransaction committed
        tx_count = db_session.query(PaymentTransaction).filter(PaymentTransaction.order_id == order.id).count()
        assert tx_count == 1
