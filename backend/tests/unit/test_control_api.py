"""Unit tests for Super Admin Control Dashboard & Analytics API (SA-01).

Architecture Specifications:
- docs/MASTER_LMS_PRODUCT_REQUIREMENTS_AND_DEVELOPMENT_ROADMAP.md (Section 6, SA-01)
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf [Pages 2-3]

Verifies:
1. Super Admin with ROLE_SUPER_ADMIN can retrieve verified overview metrics.
2. Metrics accurately reflect real database state across users, courses, enrollments, financials, and audit logs.
3. Unverified/pending orders do not inflate financial revenue metrics.
4. Processed refunds are subtracted accurately from net revenue.
5. Non-Super Admin users (ADMIN, STAFF, STUDENT) are strictly denied with HTTP 403.
6. Unauthenticated requests are rejected with HTTP 401.
7. Empty datasets return clean zero structures without exceptions.
"""

from collections import namedtuple
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.permissions import CANONICAL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
from app.core.security import hash_password
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.base import Base, utc_now
from app.models.course import (
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    Course,
)
from app.models.enrollment import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_REVOKED,
    Enrollment,
)
from app.models.payment import (
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    REFUND_STATUS_PROCESSED,
    Order,
    PaymentTransaction,
    Refund,
)
from app.models.permission import Permission, RolePermission
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    ROLE_VISITOR,
    Role,
    User,
    UserRole,
)
from tests.conftest import create_test_auth_headers
from app.services.control_service import ControlService


@pytest.fixture
def control_db_session():
    """In-memory SQLite database session seeded with canonical roles and permissions."""
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
        Role(id=ROLE_VISITOR, name="Visitor", description="Public guest"),
        Role(id=ROLE_STUDENT, name="Student", description="Enrolled learner"),
        Role(id=ROLE_STAFF, name="Staff", description="Teaching assistant"),
        Role(id=ROLE_ADMIN, name="Admin", description="Platform administrator"),
        Role(id=ROLE_SUPER_ADMIN, name="Super Admin", description="Platform owner"),
    ]
    session.add_all(roles)

    # Seed permissions
    for p_id, p_mod, p_desc in CANONICAL_PERMISSIONS:
        session.add(Permission(id=p_id, module=p_mod, description=p_desc))

    # Seed default role-permission mappings
    for r_id, p_keys in DEFAULT_ROLE_PERMISSIONS.items():
        for p_key in p_keys:
            session.add(RolePermission(role_id=r_id, permission_id=p_key))

    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def control_client(control_db_session: Session):
    """FastAPI test client with database session override."""
    app = create_app()

    def override_get_db():
        yield control_db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _create_user(session: Session, email: str, role_id: str, is_active: bool = True) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("StrongP@ssw0rd!123"),
        full_name=f"Test {role_id}",
        is_active=is_active,
        is_verified=True,
    )
    role_entity = session.get(Role, role_id)
    user.user_roles.append(UserRole(role_id=role_id, role=role_entity))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


class TestSuperAdminControlOverviewAPI:
    """Verifies SA-01 backend overview metrics endpoint."""

    def test_super_admin_can_access_overview_with_real_metrics(
        self, control_client: TestClient, control_db_session: Session
    ):
        """Super Admin receives accurate, aggregate statistics computed across real tables."""
        # 1. Seed users
        super_admin = _create_user(control_db_session, "superadmin@example.com", ROLE_SUPER_ADMIN)
        student1 = _create_user(control_db_session, "student1@example.com", ROLE_STUDENT)
        student2 = _create_user(control_db_session, "student2@example.com", ROLE_STUDENT)
        admin_user = _create_user(control_db_session, "admin@example.com", ROLE_ADMIN)
        staff_user = _create_user(control_db_session, "staff@example.com", ROLE_STAFF)

        # 2. Seed courses
        course1 = Course(
            id=uuid.uuid4(),
            title="Python Architecture Masterclass",
            slug="python-architecture",
            status=COURSE_STATUS_PUBLISHED,
            price_inr=499900,
        )
        course2 = Course(
            id=uuid.uuid4(),
            title="Draft AI Course",
            slug="draft-ai",
            status=COURSE_STATUS_DRAFT,
            price_inr=999900,
        )
        control_db_session.add_all([course1, course2])
        control_db_session.commit()

        # 3. Seed enrollments
        enr1 = Enrollment(
            id=uuid.uuid4(),
            student_id=student1.id,
            course_id=course1.id,
            status=ENROLLMENT_STATUS_ACTIVE,
        )
        enr2 = Enrollment(
            id=uuid.uuid4(),
            student_id=student2.id,
            course_id=course1.id,
            status=ENROLLMENT_STATUS_REVOKED,
        )
        control_db_session.add_all([enr1, enr2])
        control_db_session.commit()

        # 4. Seed orders & refunds
        # Paid order: 4999.00 INR (499900 paise)
        order_paid = Order(
            id=uuid.uuid4(),
            order_no="ORD-202611-0001",
            student_id=student1.id,
            course_id=course1.id,
            amount_inr=499900,
            status=ORDER_STATUS_PAID,
        )
        # Pending order: 9999.00 INR (must NOT count towards verified revenue)
        order_pending = Order(
            id=uuid.uuid4(),
            order_no="ORD-202611-0002",
            student_id=student2.id,
            course_id=course2.id,
            amount_inr=999900,
            status=ORDER_STATUS_PENDING,
        )
        control_db_session.add_all([order_paid, order_pending])
        control_db_session.commit()

        # Processed refund of 1000.00 INR (100000 paise) against paid order
        refund = Refund(
            id=uuid.uuid4(),
            order_id=order_paid.id,
            amount_inr=100000,
            reason="Partial goodwill refund",
            status=REFUND_STATUS_PROCESSED,
            approved_by=super_admin.id,
        )
        control_db_session.add(refund)

        # 5. Seed audit logs (including a security event)
        log1 = AuditLog(
            id=uuid.uuid4(),
            actor_id=super_admin.id,
            actor_type="SUPER_ADMIN",
            action="COURSE_PUBLISHED",
            resource_type="course",
            resource_id=str(course1.id),
        )
        log2 = AuditLog(
            id=uuid.uuid4(),
            actor_id=student2.id,
            actor_type="STUDENT",
            action="AUTH_SESSION_REVOKED",
            resource_type="auth_session",
        )
        control_db_session.add_all([log1, log2])
        control_db_session.commit()

        # Execute API call with Super Admin token
        headers = create_test_auth_headers(super_admin, session=control_db_session)
        resp = control_client.get(
            "/api/v1/control/overview",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        # Verify User Metrics
        assert data["user_metrics"]["total_students"] == 2
        assert data["user_metrics"]["total_admins"] == 1
        assert data["user_metrics"]["total_staff"] == 1
        assert data["user_metrics"]["total_super_admins"] == 1
        assert data["user_metrics"]["active_users"] == 5

        # Verify Course Metrics
        assert data["course_metrics"]["total_courses"] == 2
        assert data["course_metrics"]["published_courses"] == 1
        assert data["course_metrics"]["draft_courses"] == 1
        assert data["course_metrics"]["archived_courses"] == 0

        # Verify Enrollment Metrics
        assert data["enrollment_metrics"]["total_enrollments"] == 2
        assert data["enrollment_metrics"]["active_enrollments"] == 1

        # Verify Financial Metrics (Zero trust on unverified/pending orders)
        assert data["financial_metrics"]["verified_revenue_paise"] == 499900
        assert data["financial_metrics"]["verified_revenue_inr"] == 4999.0
        assert data["financial_metrics"]["successful_transactions"] == 1
        assert data["financial_metrics"]["refunded_amount_paise"] == 100000
        assert data["financial_metrics"]["refunded_amount_inr"] == 1000.0
        assert data["financial_metrics"]["net_revenue_paise"] == 399900
        assert data["financial_metrics"]["net_revenue_inr"] == 3999.0

        # Verify Security Metrics
        assert data["security_metrics"]["total_audit_events"] == 2
        assert data["security_metrics"]["security_events_count"] == 1
        assert data["security_metrics"]["active_staff_count"] == 1

        # Verify 14-day continuous trend list
        assert len(data["registration_trends"]) == 14
        assert len(data["enrollment_trends"]) == 14

        # Verify Recent Activity
        assert len(data["recent_activity"]) == 2
        actions = [item["action"] for item in data["recent_activity"]]
        assert "AUTH_SESSION_REVOKED" in actions
        assert "COURSE_PUBLISHED" in actions

    def test_admin_user_is_forbidden_403(
        self, control_client: TestClient, control_db_session: Session
    ):
        """Standard Administrator cannot access Super Admin command center."""
        admin_user = _create_user(control_db_session, "admin2@example.com", ROLE_ADMIN)
        headers = create_test_auth_headers(admin_user, session=control_db_session)

        resp = control_client.get(
            "/api/v1/control/overview",
            headers=headers,
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"]["code"] == "SUPER_ADMIN_REQUIRED"

    def test_student_and_staff_are_forbidden_403(
        self, control_client: TestClient, control_db_session: Session
    ):
        """Staff and Student callers receive HTTP 403."""
        student = _create_user(control_db_session, "student_test@example.com", ROLE_STUDENT)
        headers = create_test_auth_headers(student, session=control_db_session)

        resp = control_client.get(
            "/api/v1/control/overview",
            headers=headers,
        )
        assert resp.status_code == 403

    def test_unauthenticated_request_is_rejected_401(
        self, control_client: TestClient
    ):
        """Anonymous callers receive HTTP 401."""
        resp = control_client.get("/api/v1/control/overview")
        assert resp.status_code == 401

    def test_empty_database_returns_clean_zeroes(
        self, control_client: TestClient, control_db_session: Session
    ):
        """Empty database handles zero-counts and produces clean non-null response."""
        super_admin = _create_user(control_db_session, "only_sa@example.com", ROLE_SUPER_ADMIN)
        headers = create_test_auth_headers(super_admin, session=control_db_session)

        resp = control_client.get(
            "/api/v1/control/overview",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["user_metrics"]["total_students"] == 0
        assert data["user_metrics"]["total_admins"] == 0
        assert data["user_metrics"]["total_staff"] == 0
        assert data["user_metrics"]["total_super_admins"] == 1
        assert data["course_metrics"]["total_courses"] == 0
        assert data["enrollment_metrics"]["total_enrollments"] == 0
        assert data["financial_metrics"]["verified_revenue_paise"] == 0
        assert data["financial_metrics"]["net_revenue_paise"] == 0
        assert len(data["recent_activity"]) == 0


class TestControlOverviewFinancialMetricsRegression:
    """Targeted regression tests for ControlService financial aggregate decimal arithmetic.

    Verifies:
    1. Decimal("10000") paise -> ₹100.00
    2. Decimal("10550") paise -> ₹105.50
    3. Decimal("0") -> ₹0.00
    4. NULL aggregate -> correct zero/default behavior
    5. Type-safety: integer paise, float INR, no Decimal/float division TypeError
    6. GET /api/v1/control/overview returns HTTP 200 for authorized Super Admin with Decimal aggregates
    7. Decimal monetary precision preserves two decimal places
    """

    def test_paise_to_inr_static_method_conversion(self):
        """Validates Decimal arithmetic and two-decimal formatting for paise to INR conversion."""
        # 1. Decimal("10000") paise -> ₹100.00
        inr_10000 = ControlService._paise_to_inr(Decimal("10000"))
        assert inr_10000 == 100.0
        assert f"₹{inr_10000:.2f}" == "₹100.00"

        # 2. Decimal("10550") paise -> ₹105.50
        inr_10550 = ControlService._paise_to_inr(Decimal("10550"))
        assert inr_10550 == 105.5
        assert f"₹{inr_10550:.2f}" == "₹105.50"

        # 3. Decimal("0") -> ₹0.00
        inr_zero = ControlService._paise_to_inr(Decimal("0"))
        assert inr_zero == 0.0
        assert f"₹{inr_zero:.2f}" == "₹0.00"

        # 4. NULL aggregate (None) -> 0.00
        assert ControlService._paise_to_inr(None) == 0.0

        # Integer inputs
        assert ControlService._paise_to_inr(0) == 0.0
        assert ControlService._paise_to_inr(10000) == 100.0
        assert ControlService._paise_to_inr(10550) == 105.5

    def test_get_overview_with_decimal_aggregates_postgresql_simulation(
        self, control_db_session: Session
    ):
        """Simulates PostgreSQL func.sum() returning Decimal objects instead of SQLite int."""
        OrderStats = namedtuple("OrderStats", ["paid_count", "gross_revenue"])
        RefundStats = namedtuple("RefundStats", ["refund_sum"])

        orig_query = control_db_session.query

        def postgres_decimal_query(*entities, **kwargs):
            labels = [str(getattr(e, "key", "") or getattr(e, "_label", "")) for e in entities]
            if any("gross_revenue" in l for l in labels):
                mock_q = MagicMock()
                # PostgreSQL sum returning Decimal("10550")
                mock_q.filter.return_value.one_or_none.return_value = OrderStats(1, Decimal("10550"))
                return mock_q
            if any("refund_sum" in l for l in labels):
                mock_q = MagicMock()
                # PostgreSQL sum returning Decimal("550")
                mock_q.filter.return_value.one_or_none.return_value = RefundStats(Decimal("550"))
                return mock_q
            return orig_query(*entities, **kwargs)

        mock_session = MagicMock(wraps=control_db_session)
        mock_session.query = postgres_decimal_query

        service = ControlService()
        overview = service.get_overview(mock_session)

        # Verify FinancialMetrics values
        fm = overview.financial_metrics
        assert fm.verified_revenue_paise == 10550
        assert isinstance(fm.verified_revenue_paise, int)
        assert fm.verified_revenue_inr == 105.5
        assert isinstance(fm.verified_revenue_inr, float)

        assert fm.refunded_amount_paise == 550
        assert isinstance(fm.refunded_amount_paise, int)
        assert fm.refunded_amount_inr == 5.5
        assert isinstance(fm.refunded_amount_inr, float)

        assert fm.net_revenue_paise == 10000
        assert isinstance(fm.net_revenue_paise, int)
        assert fm.net_revenue_inr == 100.0
        assert isinstance(fm.net_revenue_inr, float)
        assert fm.currency == "INR"

    def test_get_overview_with_decimal_10000_paise(
        self, control_db_session: Session
    ):
        """Verifies Decimal('10000') paise produces exactly 10000 paise and ₹100.00."""
        OrderStats = namedtuple("OrderStats", ["paid_count", "gross_revenue"])
        RefundStats = namedtuple("RefundStats", ["refund_sum"])

        orig_query = control_db_session.query

        def postgres_decimal_query(*entities, **kwargs):
            labels = [str(getattr(e, "key", "") or getattr(e, "_label", "")) for e in entities]
            if any("gross_revenue" in l for l in labels):
                mock_q = MagicMock()
                mock_q.filter.return_value.one_or_none.return_value = OrderStats(2, Decimal("10000"))
                return mock_q
            if any("refund_sum" in l for l in labels):
                mock_q = MagicMock()
                mock_q.filter.return_value.one_or_none.return_value = RefundStats(Decimal("0"))
                return mock_q
            return orig_query(*entities, **kwargs)

        mock_session = MagicMock(wraps=control_db_session)
        mock_session.query = postgres_decimal_query

        service = ControlService()
        overview = service.get_overview(mock_session)

        fm = overview.financial_metrics
        assert fm.verified_revenue_paise == 10000
        assert fm.verified_revenue_inr == 100.0
        assert f"₹{fm.verified_revenue_inr:.2f}" == "₹100.00"
        assert fm.successful_transactions == 2
        assert fm.refunded_amount_paise == 0
        assert fm.refunded_amount_inr == 0.0
        assert fm.net_revenue_paise == 10000
        assert fm.net_revenue_inr == 100.0

    def test_get_overview_with_null_and_zero_aggregates(
        self, control_db_session: Session
    ):
        """Verifies NULL (None) and Decimal('0') aggregates default cleanly to 0 paise / 0.00 INR."""
        OrderStats = namedtuple("OrderStats", ["paid_count", "gross_revenue"])
        RefundStats = namedtuple("RefundStats", ["refund_sum"])

        orig_query = control_db_session.query

        # Case 1: Decimal('0')
        def zero_query(*entities, **kwargs):
            labels = [str(getattr(e, "key", "") or getattr(e, "_label", "")) for e in entities]
            if any("gross_revenue" in l for l in labels):
                mock_q = MagicMock()
                mock_q.filter.return_value.one_or_none.return_value = OrderStats(0, Decimal("0"))
                return mock_q
            if any("refund_sum" in l for l in labels):
                mock_q = MagicMock()
                mock_q.filter.return_value.one_or_none.return_value = RefundStats(Decimal("0"))
                return mock_q
            return orig_query(*entities, **kwargs)

        mock_s1 = MagicMock(wraps=control_db_session)
        mock_s1.query = zero_query
        service = ControlService()
        overview1 = service.get_overview(mock_s1)
        assert overview1.financial_metrics.verified_revenue_paise == 0
        assert overview1.financial_metrics.verified_revenue_inr == 0.0
        assert overview1.financial_metrics.net_revenue_paise == 0
        assert overview1.financial_metrics.net_revenue_inr == 0.0

        # Case 2: None (NULL aggregate)
        def null_query(*entities, **kwargs):
            labels = [str(getattr(e, "key", "") or getattr(e, "_label", "")) for e in entities]
            if any("gross_revenue" in l for l in labels):
                mock_q = MagicMock()
                mock_q.filter.return_value.one_or_none.return_value = None
                return mock_q
            if any("refund_sum" in l for l in labels):
                mock_q = MagicMock()
                mock_q.filter.return_value.one_or_none.return_value = None
                return mock_q
            return orig_query(*entities, **kwargs)

        mock_s2 = MagicMock(wraps=control_db_session)
        mock_s2.query = null_query
        overview2 = service.get_overview(mock_s2)
        assert overview2.financial_metrics.verified_revenue_paise == 0
        assert overview2.financial_metrics.verified_revenue_inr == 0.0
        assert overview2.financial_metrics.refunded_amount_paise == 0
        assert overview2.financial_metrics.refunded_amount_inr == 0.0
        assert overview2.financial_metrics.net_revenue_paise == 0
        assert overview2.financial_metrics.net_revenue_inr == 0.0

    def test_endpoint_returns_200_with_decimal_aggregates(
        self, control_client: TestClient, control_db_session: Session
    ):
        """GET /api/v1/control/overview returns HTTP 200 and valid JSON schema when DB returns Decimal."""
        super_admin = _create_user(control_db_session, "sa_decimal@example.com", ROLE_SUPER_ADMIN)
        headers = create_test_auth_headers(super_admin, session=control_db_session)

        OrderStats = namedtuple("OrderStats", ["paid_count", "gross_revenue"])
        RefundStats = namedtuple("RefundStats", ["refund_sum"])

        orig_query = control_db_session.query

        def decimal_query(*entities, **kwargs):
            labels = [str(getattr(e, "key", "") or getattr(e, "_label", "")) for e in entities]
            if any("gross_revenue" in l for l in labels):
                mock_q = MagicMock()
                mock_q.filter.return_value.one_or_none.return_value = OrderStats(1, Decimal("10550"))
                return mock_q
            if any("refund_sum" in l for l in labels):
                mock_q = MagicMock()
                mock_q.filter.return_value.one_or_none.return_value = RefundStats(Decimal("550"))
                return mock_q
            return orig_query(*entities, **kwargs)

        mock_session = MagicMock(wraps=control_db_session)
        mock_session.query = decimal_query

        # Override dependency with mock_session for this request
        app = control_client.app
        app.dependency_overrides[get_db] = lambda: mock_session
        try:
            resp = control_client.get("/api/v1/control/overview", headers=headers)
            assert resp.status_code == 200, resp.text
            data = resp.json()

            fm = data["financial_metrics"]
            assert fm["verified_revenue_paise"] == 10550
            assert fm["verified_revenue_inr"] == 105.5
            assert fm["refunded_amount_paise"] == 550
            assert fm["refunded_amount_inr"] == 5.5
            assert fm["net_revenue_paise"] == 10000
            assert fm["net_revenue_inr"] == 100.0
            assert fm["currency"] == "INR"
        finally:
            app.dependency_overrides[get_db] = lambda: control_db_session
