"""Unit and domain integration tests for EnrollmentService and PaymentService enrollment grant/revocation.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 28)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK602, TASK603)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004, ADR-012)
"""

from datetime import datetime, timedelta, timezone
import json
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.exceptions import ForbiddenException, ResourceNotFoundException
from app.core.razorpay import RazorpayClient, compute_razorpay_signature
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.course import (
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    Course,
    CourseRevision,
)
from app.models.enrollment import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_EXPIRED,
    ENROLLMENT_STATUS_REVOKED,
    Enrollment,
)
from app.models.notification import NotificationOutbox
from app.models.payment import ORDER_STATUS_PAID, ORDER_STATUS_PENDING, Order
from app.models.user import ROLE_ADMIN, ROLE_SUPER_ADMIN, User
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.order_repo import OrderRepository
from app.services.audit_service import AuditService
from app.services.enrollment_service import EnrollmentService
from app.services.payment_service import PaymentService


@pytest.fixture
def db_session():
    """In-memory SQLite session with full schema initialized."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def student_user(db_session: Session) -> User:
    """Fixture creating an active, verified student user."""
    user = User(
        email="student@lms.local",
        full_name="Enrolled Student",
        password_hash=hash_password("StudentSecret123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Fixture creating an active administrator."""
    user = User(
        email="admin@lms.local",
        full_name="Platform Admin",
        password_hash=hash_password("AdminSecret123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def published_course(db_session: Session, admin_user: User) -> Course:
    """Fixture creating a published course container with live revision."""
    course = Course(
        title="Distributed Systems with Python",
        slug="distributed-systems-python",
        headline="Production-grade asynchronous architectures",
        price_inr=499900,
        status=COURSE_STATUS_PUBLISHED,
    )
    db_session.add(course)
    db_session.flush()

    rev = CourseRevision(
        course_id=course.id,
        revision_no=1,
        status="PUBLISHED",
        title="Distributed Systems v1",
        created_by=admin_user.id,
    )
    db_session.add(rev)
    db_session.flush()

    course.live_revision_id = rev.id
    db_session.flush()
    return course


@pytest.fixture
def enrollment_service() -> EnrollmentService:
    """EnrollmentService instance with real dependencies."""
    return EnrollmentService()


# =============================================================================
# 1. Manual Grant & Reactivation Tests (TASK603)
# =============================================================================

def test_grant_manual_enrollment_happy_path(
    db_session: Session,
    enrollment_service: EnrollmentService,
    student_user: User,
    admin_user: User,
    published_course: Course,
):
    """Administrator manually grants active course enrollment; outbox and audit logs recorded."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=90)
    resp = enrollment_service.grant_manual_enrollment(
        session=db_session,
        student_id=student_user.id,
        course_id=published_course.id,
        expires_at=expires_at,
        reason="Merit Scholarship Grant",
        actor_id=admin_user.id,
    )
    db_session.commit()

    assert resp.student_id == student_user.id
    assert resp.course_id == published_course.id
    assert resp.status == ENROLLMENT_STATUS_ACTIVE
    assert resp.expires_at == expires_at
    assert resp.course_title == published_course.title
    assert resp.course_slug == published_course.slug

    # Verify outbox event emitted
    outbox_item = db_session.execute(
        select(NotificationOutbox).where(NotificationOutbox.recipient == student_user.email)
    ).scalars().first()
    assert outbox_item is not None
    assert outbox_item.event_type == "ENROLLMENT_MANUAL_GRANTED"
    assert published_course.title in outbox_item.subject

    # Verify immutable audit log
    audit_log = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ENROLLMENT_MANUALLY_GRANTED")
    ).scalars().first()
    assert audit_log is not None
    assert audit_log.actor_id == admin_user.id
    assert audit_log.resource_id == str(resp.id)


def test_grant_manual_enrollment_idempotent_reactivation(
    db_session: Session,
    enrollment_service: EnrollmentService,
    student_user: User,
    admin_user: User,
    published_course: Course,
):
    """Reactivating an existing revoked or expired enrollment restores ACTIVE status idempotently."""
    # First provision and revoke
    e1 = enrollment_service.grant_manual_enrollment(
        session=db_session,
        student_id=student_user.id,
        course_id=published_course.id,
        actor_id=admin_user.id,
    )
    db_session.commit()

    revoked = enrollment_service.revoke_enrollment(
        session=db_session,
        enrollment_id=e1.id,
        reason="Administrative Hold",
        actor_id=admin_user.id,
    )
    db_session.commit()
    assert revoked.status == ENROLLMENT_STATUS_REVOKED

    # Re-grant
    reactivated = enrollment_service.grant_manual_enrollment(
        session=db_session,
        student_id=student_user.id,
        course_id=published_course.id,
        actor_id=admin_user.id,
        reason="Hold Lifted",
    )
    db_session.commit()

    assert reactivated.id == e1.id
    assert reactivated.status == ENROLLMENT_STATUS_ACTIVE
    assert reactivated.revoked_at is None
    assert reactivated.revoked_reason is None


def test_grant_manual_enrollment_suspended_student_fails(
    db_session: Session,
    enrollment_service: EnrollmentService,
    student_user: User,
    admin_user: User,
    published_course: Course,
):
    """Cannot grant course enrollment to a suspended user account."""
    student_user.is_active = False
    db_session.flush()

    with pytest.raises(ForbiddenException) as exc_info:
        enrollment_service.grant_manual_enrollment(
            session=db_session,
            student_id=student_user.id,
            course_id=published_course.id,
            actor_id=admin_user.id,
        )
    assert exc_info.value.code == "ACCOUNT_SUSPENDED"


def test_grant_manual_enrollment_nonexistent_targets_fail(
    db_session: Session,
    enrollment_service: EnrollmentService,
    student_user: User,
    admin_user: User,
    published_course: Course,
):
    """Missing user or course raises ResourceNotFoundException."""
    fake_id = uuid.uuid4()
    with pytest.raises(ResourceNotFoundException):
        enrollment_service.grant_manual_enrollment(
            session=db_session,
            student_id=fake_id,
            course_id=published_course.id,
            actor_id=admin_user.id,
        )

    with pytest.raises(ResourceNotFoundException):
        enrollment_service.grant_manual_enrollment(
            session=db_session,
            student_id=student_user.id,
            course_id=fake_id,
            actor_id=admin_user.id,
        )


# =============================================================================
# 2. Revocation & Access Checking Tests (TASK603, TASK604)
# =============================================================================

def test_revoke_enrollment_happy_path(
    db_session: Session,
    enrollment_service: EnrollmentService,
    student_user: User,
    admin_user: User,
    published_course: Course,
):
    """Revoking enrollment transitions status to REVOKED with recorded reason and timestamp."""
    e = enrollment_service.grant_manual_enrollment(
        session=db_session,
        student_id=student_user.id,
        course_id=published_course.id,
        actor_id=admin_user.id,
    )
    db_session.commit()

    rev = enrollment_service.revoke_enrollment(
        session=db_session,
        enrollment_id=e.id,
        reason="Honor Code Violation",
        actor_id=admin_user.id,
    )
    db_session.commit()

    assert rev.status == ENROLLMENT_STATUS_REVOKED
    assert rev.revoked_at is not None
    assert rev.revoked_reason == "Honor Code Violation"

    # Verify check_access reflects revocation immediately
    check = enrollment_service.check_access(db_session, student_user.id, published_course.id)
    assert check.is_enrolled is True
    assert check.status == ENROLLMENT_STATUS_REVOKED
    assert check.access_granted is False


def test_check_access_states(
    db_session: Session,
    enrollment_service: EnrollmentService,
    student_user: User,
    admin_user: User,
    published_course: Course,
):
    """Evaluates check_access across non-enrolled, active, and expired states."""
    # 1. Unenrolled student
    check_none = enrollment_service.check_access(db_session, student_user.id, published_course.id)
    assert check_none.is_enrolled is False
    assert check_none.access_granted is False

    # 2. Active lifetime enrollment
    e = enrollment_service.grant_manual_enrollment(
        session=db_session,
        student_id=student_user.id,
        course_id=published_course.id,
        actor_id=admin_user.id,
    )
    db_session.commit()
    check_active = enrollment_service.check_access(db_session, student_user.id, published_course.id)
    assert check_active.is_enrolled is True
    assert check_active.status == ENROLLMENT_STATUS_ACTIVE
    assert check_active.access_granted is True

    # 3. Expired enrollment
    enrollment_repo = EnrollmentRepository()
    row = enrollment_repo.get_by_id(db_session, e.id)
    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    check_expired = enrollment_service.check_access(db_session, student_user.id, published_course.id)
    assert check_expired.is_enrolled is True
    assert check_expired.access_granted is False


# =============================================================================
# 3. Webhook Payment Capture & Refund Integration (TASK602)
# =============================================================================

def test_webhook_payment_capture_grants_enrollment(
    db_session: Session,
    student_user: User,
    admin_user: User,
    published_course: Course,
):
    """Verified payment.captured webhook automatically creates active enrollment for student."""
    settings = Settings(
        RAZORPAY_KEY_ID="rzp_test_mock",
        RAZORPAY_KEY_SECRET="rzp_test_secret_key_1234567890",
        RAZORPAY_WEBHOOK_SECRET="test_webhook_secret_key",
    )
    rzp_client = RazorpayClient(settings=settings)
    payment_service = PaymentService(razorpay_client=rzp_client, settings=settings)

    # 1. Create order
    checkout_resp = payment_service.create_order(
        session=db_session,
        course_id=published_course.id,
        student=student_user,
    )
    db_session.commit()

    # 2. Simulate webhook payment.captured payload
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_capture_enrollment_001",
                    "order_id": checkout_resp.razorpay_order_id,
                    "amount": published_course.price_inr,
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_razorpay_signature(raw_body, "test_webhook_secret_key")

    # 3. Process webhook
    result = payment_service.process_razorpay_webhook(
        session=db_session,
        raw_body=raw_body,
        signature_header=sig,
    )
    db_session.commit()

    assert result["status"] == "ok"

    # 4. Verify enrollment was created
    enrollment_repo = EnrollmentRepository()
    enrollment = enrollment_repo.get_by_student_and_course(
        session=db_session,
        student_id=student_user.id,
        course_id=published_course.id,
    )
    assert enrollment is not None
    assert enrollment.status == ENROLLMENT_STATUS_ACTIVE
    assert enrollment.order_id == checkout_resp.order_id
    assert enrollment.is_access_valid is True


def test_full_refund_revokes_enrollment(
    db_session: Session,
    student_user: User,
    admin_user: User,
    published_course: Course,
):
    """Full refund execution by Super Admin automatically revokes student enrollment."""
    settings = Settings(
        RAZORPAY_KEY_ID="rzp_test_mock",
        RAZORPAY_KEY_SECRET="rzp_test_secret_key_1234567890",
        RAZORPAY_WEBHOOK_SECRET="test_webhook_secret_key",
    )
    rzp_client = RazorpayClient(settings=settings)
    payment_service = PaymentService(razorpay_client=rzp_client, settings=settings)

    # 1. Create order and process capture
    checkout_resp = payment_service.create_order(
        session=db_session,
        course_id=published_course.id,
        student=student_user,
    )
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_refund_enrollment_002",
                    "order_id": checkout_resp.razorpay_order_id,
                    "amount": published_course.price_inr,
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = compute_razorpay_signature(raw_body, "test_webhook_secret_key")
    payment_service.process_razorpay_webhook(db_session, raw_body, sig)
    db_session.commit()

    # Verify initial active enrollment
    enrollment_repo = EnrollmentRepository()
    enrollment = enrollment_repo.get_by_student_and_course(db_session, student_user.id, published_course.id)
    assert enrollment.status == ENROLLMENT_STATUS_ACTIVE

    # 2. Super Admin executes full refund
    refund_resp = payment_service.refund_order(
        session=db_session,
        order_id=checkout_resp.order_id,
        reason="Student requested refund within 7-day guarantee",
        amount_inr=published_course.price_inr,
        current_user=admin_user,
    )
    db_session.commit()

    assert refund_resp.amount_inr == published_course.price_inr

    # 3. Verify enrollment was revoked
    db_session.refresh(enrollment)
    assert enrollment.status == ENROLLMENT_STATUS_REVOKED
    assert "PAYMENT_REFUNDED" in enrollment.revoked_reason
    assert enrollment.is_access_valid is False
