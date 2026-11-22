"""FastAPI REST API integration tests for Orders, Checkout, Webhooks, and Refunds.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.7)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK501-TASK504)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004, ADR-005, ADR-008)
"""

from datetime import datetime, timedelta
import json
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.permissions import CANONICAL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
from app.core.razorpay import compute_razorpay_signature
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.base import Base, utc_now
from app.models.course import COURSE_STATUS_PUBLISHED, Course, CourseRevision
from app.models.payment import (
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REFUNDED,
    Order,
    PaymentTransaction,
    Refund,
)
from app.models.permission import Permission, RolePermission
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    Role,
    User,
    UserRole,
)


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
    for key, module, desc in CANONICAL_PERMISSIONS:
        session.add(Permission(id=key, module=module, description=desc))
    for r_id, p_keys in DEFAULT_ROLE_PERMISSIONS.items():
        role = Role(id=r_id, name=r_id.title())
        session.add(role)
        for pk in p_keys:
            session.add(RolePermission(role_id=r_id, permission_id=pk))
    session.flush()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def super_admin_user(db_session: Session) -> User:
    """Creates a Super Admin user."""
    role = db_session.get(Role, ROLE_SUPER_ADMIN)
    if not role:
        role = Role(id=ROLE_SUPER_ADMIN, name="Super Administrator")
        db_session.add(role)
        db_session.flush()

    user = User(
        email="superadmin@lms.local",
        full_name="Super Administrator",
        password_hash=hash_password("SuperP@ss12345"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    ur = UserRole(user_id=user.id, role_id=ROLE_SUPER_ADMIN)
    db_session.add(ur)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def student_user(db_session: Session) -> User:
    """Creates a standard verified Student user."""
    role = db_session.get(Role, ROLE_STUDENT)
    if not role:
        role = Role(id=ROLE_STUDENT, name="Student")
        db_session.add(role)
        db_session.flush()

    user = User(
        email="student@lms.local",
        full_name="Enrolled Student",
        password_hash=hash_password("StudentP@ss12345"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    ur = UserRole(user_id=user.id, role_id=ROLE_STUDENT)
    db_session.add(ur)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def stranger_user(db_session: Session) -> User:
    """Creates another student user for IDOR testing."""
    role = db_session.get(Role, ROLE_STUDENT)
    if not role:
        role = Role(id=ROLE_STUDENT, name="Student")
        db_session.add(role)
        db_session.flush()

    user = User(
        email="stranger@lms.local",
        full_name="Stranger Student",
        password_hash=hash_password("StrangerP@ss12345"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    ur = UserRole(user_id=user.id, role_id=ROLE_STUDENT)
    db_session.add(ur)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def published_course(db_session: Session) -> Course:
    """Creates a published course with live revision."""
    course_id = uuid.uuid4()
    rev_id = uuid.uuid4()

    course = Course(
        id=course_id,
        slug="architecture-deep-dive",
        title="Architecture Deep Dive",
        price_inr=599900,  # ₹5,999.00
        is_free=False,
        status=COURSE_STATUS_PUBLISHED,
        live_revision_id=rev_id,
    )
    db_session.add(course)

    revision = CourseRevision(
        id=rev_id,
        course_id=course_id,
        revision_no=1,
        title="Architecture Deep Dive v1",
        status="PUBLISHED",
        snapshot={"sections": []},
        published_at=utc_now(),
    )
    db_session.add(revision)
    db_session.commit()
    db_session.refresh(course)
    return course


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


def make_token(user, extra_claims=None):
    from tests.conftest import create_test_auth_headers
    return create_test_auth_headers(user, extra_claims=extra_claims)["Authorization"].split("Bearer ")[1]


class TestOrdersAPI:
    """Verifies REST endpoints for orders and checkout."""

    def test_create_order_authenticated_student(self, client, student_user, published_course):
        """Student with valid token initiates checkout order successfully."""
        token = make_token(student_user, {"roles": [ROLE_STUDENT]})

        response = client.post(
            "/api/v1/orders",
            json={"course_id": str(published_course.id)},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["amount_inr"] == 599900
        assert data["currency"] == "INR"
        assert data["order_no"].startswith("ORD-")
        assert data["razorpay_order_id"].startswith("order_")
        assert data["course_title"] == "Architecture Deep Dive"

    def test_create_order_unauthenticated_fails(self, client, published_course):
        """Unauthenticated request is rejected with HTTP 401."""
        response = client.post(
            "/api/v1/orders",
            json={"course_id": str(published_course.id)},
        )
        assert response.status_code == 401

    def test_get_orders_list_scoping(self, client, student_user, stranger_user, super_admin_user, published_course, db_session):
        """Student sees own orders; Super Admin sees all."""
        # Create order for student
        order_student = Order(
            order_no="ORD-STD-001",
            student_id=student_user.id,
            course_id=published_course.id,
            amount_inr=599900,
            status=ORDER_STATUS_PENDING,
        )
        # Create order for stranger
        order_stranger = Order(
            order_no="ORD-STR-002",
            student_id=stranger_user.id,
            course_id=published_course.id,
            amount_inr=599900,
            status=ORDER_STATUS_PENDING,
        )
        db_session.add_all([order_student, order_stranger])
        db_session.commit()

        # Student token
        token_student = make_token(student_user, {"roles": [ROLE_STUDENT]})
        resp_student = client.get(
            "/api/v1/orders",
            headers={"Authorization": f"Bearer {token_student}"},
        )
        assert resp_student.status_code == 200
        assert resp_student.json()["total"] == 1
        assert resp_student.json()["items"][0]["order_no"] == "ORD-STD-001"

        # Super Admin token
        token_admin = make_token(super_admin_user, {"roles": [ROLE_SUPER_ADMIN]})
        resp_admin = client.get(
            "/api/v1/orders",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert resp_admin.status_code == 200
        assert resp_admin.json()["total"] == 2

    def test_get_order_by_id_anti_idor(self, client, student_user, stranger_user, published_course, db_session):
        """Stranger cannot access student's order details (Anti-IDOR)."""
        order = Order(
            order_no="ORD-PRIVATE-001",
            student_id=student_user.id,
            course_id=published_course.id,
            amount_inr=599900,
            status=ORDER_STATUS_PENDING,
        )
        db_session.add(order)
        db_session.commit()

        # Stranger attempts to view student's order
        token_stranger = make_token(stranger_user, {"roles": [ROLE_STUDENT]})
        response = client.get(
            f"/api/v1/orders/{order.id}",
            headers={"Authorization": f"Bearer {token_stranger}"},
        )
        assert response.status_code == 403


class TestRefundAPI:
    """Verifies refund execution via REST endpoint."""

    def test_refund_order_super_admin_success(self, client, super_admin_user, student_user, published_course, db_session):
        """Super Admin with payments:refund permission successfully refunds paid order."""
        order = Order(
            order_no="ORD-PAID-REFUND",
            student_id=student_user.id,
            course_id=published_course.id,
            amount_inr=599900,
            status=ORDER_STATUS_PAID,
            razorpay_order_id="order_to_refund_rzp",
        )
        db_session.add(order)
        db_session.flush()

        tx = PaymentTransaction(
            order_id=order.id,
            gateway="RAZORPAY",
            razorpay_payment_id="pay_to_refund_rzp",
            razorpay_signature="mock_sig",
            status="SUCCESS",
            amount_inr=599900,
            raw_payload={"status": "captured"},
        )
        db_session.add(tx)
        db_session.commit()

        token_admin = make_token(super_admin_user, {"roles": [ROLE_SUPER_ADMIN]})
        response = client.post(
            f"/api/v1/orders/{order.id}/refund",
            json={"reason": "Customer dissatisfied within 30 days money-back guarantee window"},
            headers={"Authorization": f"Bearer {token_admin}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["amount_inr"] == 599900
        assert data["status"] == "PROCESSED"
        assert data["razorpay_refund_id"].startswith("rfd_")

        # Verify order transitioned to REFUNDED
        db_session.refresh(order)
        assert order.status == ORDER_STATUS_REFUNDED

    def test_refund_order_student_forbidden(self, client, student_user, published_course, db_session):
        """Student cannot trigger refund endpoint (HTTP 403)."""
        order = Order(
            order_no="ORD-STUDENT-TRY",
            student_id=student_user.id,
            course_id=published_course.id,
            amount_inr=599900,
            status=ORDER_STATUS_PAID,
        )
        db_session.add(order)
        db_session.commit()

        token_student = make_token(student_user, {"roles": [ROLE_STUDENT]})
        response = client.post(
            f"/api/v1/orders/{order.id}/refund",
            json={"reason": "Student self refund attempt"},
            headers={"Authorization": f"Bearer {token_student}"},
        )
        assert response.status_code == 403


class TestWebhooksAPI:
    """Verifies cryptographic webhook ingestion endpoint."""

    def test_webhook_payment_captured_success(self, client, student_user, published_course, db_session):
        """Cryptographically signed webhook transitions order to PAID."""
        settings = get_settings()
        secret = (
            settings.RAZORPAY_WEBHOOK_SECRET.get_secret_value()
            if settings.RAZORPAY_WEBHOOK_SECRET
            else "mock_webhook_secret_for_dev_test"
        )

        order = Order(
            order_no="ORD-WEBHOOK-TEST",
            student_id=student_user.id,
            course_id=published_course.id,
            amount_inr=599900,
            status=ORDER_STATUS_PENDING,
            razorpay_order_id="order_webhook_live_123",
        )
        db_session.add(order)
        db_session.commit()

        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_captured_live_123",
                        "order_id": "order_webhook_live_123",
                        "amount": 599900,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        sig = compute_razorpay_signature(raw_body, secret)

        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        db_session.refresh(order)
        assert order.status == ORDER_STATUS_PAID

    def test_webhook_missing_signature_rejected(self, client):
        """Webhook without signature header is rejected with HTTP 400."""
        response = client.post(
            "/api/v1/webhooks/razorpay",
            json={"event": "payment.captured"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "BAD_REQUEST"
        assert "Missing X-Razorpay-Signature" in data["error"]["message"]

    def test_webhook_invalid_signature_rejected(self, client):
        """Webhook with invalid signature is rejected with HTTP 400."""
        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=b'{"event":"payment.captured"}',
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": "invalid_tampered_signature",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "BAD_REQUEST"
        assert "signature verification failed" in data["error"]["message"]
