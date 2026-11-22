"""Unit tests for SA-05 Complete Commercial Governance.

Architecture Specifications:
- SA-05 — Complete Commercial Governance (Sections 3, 4, 5, 8, 10, 11)
- docs/backend/06-API-ARCHITECTURE.md
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
"""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import create_access_token
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.auth_session import AuthSession, SESSION_STATUS_ACTIVE
from app.models.base import Base
from app.models.course import Course, COURSE_STATUS_PUBLISHED
from app.models.offer import (
    DISCOUNT_TYPE_FIXED,
    DISCOUNT_TYPE_PERCENTAGE,
    OFFER_STATUS_ACTIVE,
    OFFER_STATUS_INACTIVE,
    Offer,
)
from app.models.payment import (
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REFUNDED,
    REFUND_STATUS_PROCESSED,
    TRANSACTION_STATUS_SUCCESS,
    Order,
    PaymentTransaction,
    Refund,
)
from app.models.platform_setting import PlatformSetting
from app.models.user import ROLE_ADMIN, ROLE_STAFF, ROLE_STUDENT, ROLE_SUPER_ADMIN, Role, User, UserRole


@pytest.fixture
def db_session():
    """In-memory SQLite database session with all schemas initialized."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    # Seed roles
    roles = [
        Role(id=ROLE_STUDENT, name="Student", description="Enrolled learner"),
        Role(id=ROLE_STAFF, name="Staff", description="Teaching assistant"),
        Role(id=ROLE_ADMIN, name="Admin", description="Platform administrator"),
        Role(id=ROLE_SUPER_ADMIN, name="Super Admin", description="Platform owner"),
    ]
    session.add_all(roles)
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_test_user_with_session(db_session, role_id: str, email: str, name: str) -> tuple[User, str]:
    """Helper to create authenticated user and active session token."""
    role = db_session.get(Role, role_id)
    user = User(
        email=email,
        password_hash="mock_hash",
        full_name=name,
        is_active=True,
        is_verified=True,
    )
    user.user_roles.append(UserRole(role_id=role_id, role=role))
    db_session.add(user)
    db_session.flush()

    session_id = uuid.uuid4()
    auth_session = AuthSession(
        id=session_id,
        user_id=user.id,
        session_token_hash=f"mock_token_hash_{uuid.uuid4().hex}",
        status=SESSION_STATUS_ACTIVE,
        ip_address="127.0.0.1",
        user_agent="TestAgent/1.0",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(auth_session)
    db_session.commit()

    roles = [ur.role_id for ur in user.user_roles]
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"roles": roles, "email": user.email, "session_id": str(session_id)},
    )
    return user, token


class TestSA05CommercialGovernance:
    """Test suite for SA-05 commercial governance endpoints and security."""

    def test_unauthenticated_blocked(self, client):
        """Unauthenticated requests to SA-05 endpoints must receive 401 Unauthorized."""
        res_offers = client.get("/api/v1/control/offers")
        assert res_offers.status_code == 401

        res_payments = client.get("/api/v1/control/payments/overview")
        assert res_payments.status_code == 401

        res_settings = client.get("/api/v1/control/settings")
        assert res_settings.status_code == 401

    def test_non_super_admin_forbidden_from_sa05(self, db_session, client):
        """Standard ADMIN, STAFF, and STUDENT roles must receive 403 Forbidden."""
        _, student_token = create_test_user_with_session(
            db_session, ROLE_STUDENT, "student@example.com", "Test Student"
        )
        _, staff_token = create_test_user_with_session(
            db_session, ROLE_STAFF, "staff@example.com", "Test Staff"
        )
        _, admin_token = create_test_user_with_session(
            db_session, ROLE_ADMIN, "admin@example.com", "Test Admin"
        )

        for token in [student_token, staff_token, admin_token]:
            headers = {"Authorization": f"Bearer {token}"}
            assert client.get("/api/v1/control/offers", headers=headers).status_code == 403
            assert client.get("/api/v1/control/payments/overview", headers=headers).status_code == 403
            assert client.get("/api/v1/control/settings", headers=headers).status_code == 403

    def test_super_admin_can_access_sa05_endpoints(self, db_session, client):
        """Super Admin can access all SA-05 endpoints."""
        _, sa_token = create_test_user_with_session(
            db_session, ROLE_SUPER_ADMIN, "superadmin@example.com", "Super Admin"
        )
        headers = {"Authorization": f"Bearer {sa_token}"}

        res_offers = client.get("/api/v1/control/offers", headers=headers)
        assert res_offers.status_code == 200
        assert "items" in res_offers.json()

        res_payments = client.get("/api/v1/control/payments/overview", headers=headers)
        assert res_payments.status_code == 200
        assert res_payments.json()["currency"] == "INR"

        res_settings = client.get("/api/v1/control/settings", headers=headers)
        assert res_settings.status_code == 200
        assert "platform_name" in res_settings.json()

    def test_create_and_read_offer(self, db_session, client):
        """Create a promotional offer with code, percentage discount, and verify retrieval."""
        super_admin, sa_token = create_test_user_with_session(
            db_session, ROLE_SUPER_ADMIN, "superadmin@example.com", "Super Admin"
        )
        headers = {"Authorization": f"Bearer {sa_token}"}

        now = datetime.now(timezone.utc)
        payload = {
            "name": "Diwali 2026 Special",
            "code": "DIWALI50",
            "description": "50% festive discount",
            "discount_type": "PERCENTAGE",
            "discount_value": 50,
            "valid_from": now.isoformat(),
            "valid_to": (now + timedelta(days=10)).isoformat(),
            "usage_limit": 100,
            "status": "ACTIVE",
        }

        res_create = client.post("/api/v1/control/offers", json=payload, headers=headers)
        assert res_create.status_code == 201
        data = res_create.json()
        assert data["code"] == "DIWALI50"
        assert data["discount_value"] == 50
        assert data["times_used"] == 0
        offer_id = data["id"]

        # Read single offer
        res_get = client.get(f"/api/v1/control/offers/{offer_id}", headers=headers)
        assert res_get.status_code == 200
        assert res_get.json()["name"] == "Diwali 2026 Special"

        # List offers
        res_list = client.get("/api/v1/control/offers?search=DIWALI", headers=headers)
        assert res_list.status_code == 200
        assert res_list.json()["total"] == 1
        assert res_list.json()["items"][0]["id"] == offer_id

    def test_offer_validation_boundaries(self, db_session, client):
        """Offer validation rejects percentage > 100, valid_to <= valid_from, and duplicate codes."""
        _, sa_token = create_test_user_with_session(
            db_session, ROLE_SUPER_ADMIN, "superadmin@example.com", "Super Admin"
        )
        headers = {"Authorization": f"Bearer {sa_token}"}

        now = datetime.now(timezone.utc)

        # 1. Percentage > 100
        res1 = client.post(
            "/api/v1/control/offers",
            json={
                "name": "Invalid Percentage",
                "code": "INVALID150",
                "discount_type": "PERCENTAGE",
                "discount_value": 150,
                "valid_from": now.isoformat(),
                "valid_to": (now + timedelta(days=5)).isoformat(),
            },
            headers=headers,
        )
        assert res1.status_code == 422

        # 2. Expiry before start date
        res2 = client.post(
            "/api/v1/control/offers",
            json={
                "name": "Invalid Dates",
                "code": "BAD_DATES",
                "discount_type": "FIXED",
                "discount_value": 50000,
                "valid_from": (now + timedelta(days=5)).isoformat(),
                "valid_to": now.isoformat(),
            },
            headers=headers,
        )
        assert res2.status_code == 422

        # 3. Duplicate code rejection
        res3_ok = client.post(
            "/api/v1/control/offers",
            json={
                "name": "Offer 1",
                "code": "SAVE20",
                "discount_type": "PERCENTAGE",
                "discount_value": 20,
                "valid_from": now.isoformat(),
                "valid_to": (now + timedelta(days=5)).isoformat(),
            },
            headers=headers,
        )
        assert res3_ok.status_code == 201

        res3_dup = client.post(
            "/api/v1/control/offers",
            json={
                "name": "Offer 2 Duplicate",
                "code": "SAVE20",
                "discount_type": "PERCENTAGE",
                "discount_value": 30,
                "valid_from": now.isoformat(),
                "valid_to": (now + timedelta(days=5)).isoformat(),
            },
            headers=headers,
        )
        assert res3_dup.status_code == 400
        error_msg = res3_dup.json().get("detail") or res3_dup.json().get("error", {}).get("message", "")
        assert "already exists" in error_msg

    def test_update_status_toggle_and_delete_offer(self, db_session, client):
        """Update offer details, toggle status, and delete with audit trail."""
        super_admin, sa_token = create_test_user_with_session(
            db_session, ROLE_SUPER_ADMIN, "superadmin@example.com", "Super Admin"
        )
        headers = {"Authorization": f"Bearer {sa_token}"}
        now = datetime.now(timezone.utc)

        res_create = client.post(
            "/api/v1/control/offers",
            json={
                "name": "Summer Offer",
                "code": "SUMMER10",
                "discount_type": "PERCENTAGE",
                "discount_value": 10,
                "valid_from": now.isoformat(),
                "valid_to": (now + timedelta(days=5)).isoformat(),
            },
            headers=headers,
        )
        offer_id = res_create.json()["id"]

        # Update
        res_update = client.put(
            f"/api/v1/control/offers/{offer_id}",
            json={"name": "Summer Offer Extended", "discount_value": 15},
            headers=headers,
        )
        assert res_update.status_code == 200
        assert res_update.json()["name"] == "Summer Offer Extended"
        assert res_update.json()["discount_value"] == 15

        # Status Toggle
        res_status = client.patch(
            f"/api/v1/control/offers/{offer_id}/status",
            json={"status": "INACTIVE"},
            headers=headers,
        )
        assert res_status.status_code == 200
        assert res_status.json()["status"] == "INACTIVE"

        # Delete
        res_delete = client.delete(f"/api/v1/control/offers/{offer_id}", headers=headers)
        assert res_delete.status_code == 204

        # Verify 404
        assert client.get(f"/api/v1/control/offers/{offer_id}", headers=headers).status_code == 404

    def test_payment_overview_metrics_accuracy(self, db_session, client):
        """Payment metrics calculate accurately with strict integer paise math and zero drift."""
        super_admin, sa_token = create_test_user_with_session(
            db_session, ROLE_SUPER_ADMIN, "superadmin@example.com", "Super Admin"
        )
        student, _ = create_test_user_with_session(
            db_session, ROLE_STUDENT, "student1@example.com", "Student One"
        )
        headers = {"Authorization": f"Bearer {sa_token}"}

        # Create Course
        course = Course(
            title="FastAPI Masterclass",
            slug="fastapi-masterclass",
            price_inr=500000,  # 5,000 INR in paise
            is_free=False,
            status=COURSE_STATUS_PUBLISHED,
        )
        db_session.add(course)
        db_session.flush()

        # 1. Successful Order & Transaction (₹5,000 = 500000 paise)
        order1 = Order(
            order_no="ORD-202611-0001",
            student_id=student.id,
            course_id=course.id,
            amount_inr=500000,
            status=ORDER_STATUS_PAID,
            razorpay_order_id="order_1",
        )
        db_session.add(order1)
        db_session.flush()

        tx1 = PaymentTransaction(
            order_id=order1.id,
            gateway="RAZORPAY",
            razorpay_payment_id="pay_success_1",
            razorpay_signature="mock_sig",
            status=TRANSACTION_STATUS_SUCCESS,
            amount_inr=500000,
            raw_payload={"mock": "data"},
        )
        db_session.add(tx1)

        # 2. Refunded Order & Refund Record (Refund ₹1,000 = 100000 paise)
        order2 = Order(
            order_no="ORD-202611-0002",
            student_id=student.id,
            course_id=course.id,
            amount_inr=300000,
            status=ORDER_STATUS_REFUNDED,
            razorpay_order_id="order_2",
        )
        db_session.add(order2)
        db_session.flush()

        tx2 = PaymentTransaction(
            order_id=order2.id,
            gateway="RAZORPAY",
            razorpay_payment_id="pay_success_2",
            razorpay_signature="mock_sig",
            status=TRANSACTION_STATUS_SUCCESS,
            amount_inr=300000,
            raw_payload={"mock": "data"},
        )
        db_session.add(tx2)

        refund2 = Refund(
            order_id=order2.id,
            amount_inr=100000,
            reason="Student requested refund",
            status=REFUND_STATUS_PROCESSED,
            approved_by=super_admin.id,
        )
        db_session.add(refund2)

        # 3. Pending Order (no transaction yet)
        order3 = Order(
            order_no="ORD-202611-0003",
            student_id=student.id,
            course_id=course.id,
            amount_inr=200000,
            status=ORDER_STATUS_PENDING,
            razorpay_order_id="order_3",
        )
        db_session.add(order3)

        db_session.commit()

        # Query metrics endpoint
        res = client.get("/api/v1/control/payments/overview", headers=headers)
        assert res.status_code == 200
        metrics = res.json()

        assert metrics["total_transactions_count"] == 2
        assert metrics["successful_payments_count"] == 2
        assert metrics["failed_payments_count"] == 0
        assert metrics["pending_orders_count"] == 1
        assert metrics["refunded_orders_count"] == 1
        assert metrics["gross_revenue_paise"] == 800000  # 500000 + 300000
        assert metrics["refunded_amount_paise"] == 100000
        assert metrics["net_collected_paise"] == 700000  # 800000 - 100000

        # Query transactions list
        res_txs = client.get("/api/v1/control/payments/transactions", headers=headers)
        assert res_txs.status_code == 200
        txs = res_txs.json()
        assert txs["total"] == 2
        assert txs["items"][0]["student"]["email"] == "student1@example.com"
        assert txs["items"][0]["course"]["slug"] == "fastapi-masterclass"

    def test_get_and_update_platform_settings(self, db_session, client):
        """Retrieve safe platform settings and update branding without exposing secrets."""
        super_admin, sa_token = create_test_user_with_session(
            db_session, ROLE_SUPER_ADMIN, "superadmin@example.com", "Super Admin"
        )
        headers = {"Authorization": f"Bearer {sa_token}"}

        # 1. Fetch settings
        res = client.get("/api/v1/control/settings", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "platform_name" in data
        assert "SECRET_KEY" not in str(res.json())  # Security guard: Zero secret disclosure
        assert "DATABASE_URL" not in str(res.json())

        # 2. Update branding & platform settings
        update_payload = {
            "platform_name": "Pro Python Academy",
            "brand_name": "Dr. Python",
            "brand_description": "Elite Python engineering training",
            "support_email": "help@propython.com",
            "support_phone": "+91 9988776655",
            "logo_url": "https://assets.propython.com/logo.webp",
        }
        res_update = client.put("/api/v1/control/settings", json=update_payload, headers=headers)
        assert res_update.status_code == 200
        updated = res_update.json()
        assert updated["platform_name"] == "Pro Python Academy"
        assert updated["brand_name"] == "Dr. Python"
        assert updated["support_email"] == "help@propython.com"

        # 3. Verify audit log was recorded
        audit = db_session.query(AuditLog).filter(AuditLog.action == "PLATFORM_SETTINGS_UPDATED").first()
        assert audit is not None
        assert audit.actor_id == super_admin.id
        assert audit.resource_type == "platform_settings"
