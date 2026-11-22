"""Security Regression Test Suite for P0 Vulnerability Remediation.

Covers:
- P0-03: Unpublished Course Preview Disclosure Guard
- P0-04: Course Governance Publication Checklist Enforcement
- P0-05: Refund Idempotency and Financial Integrity
- P0-06: Sensitive Outbox Token Fernet Encryption
- P0-07: Trusted Proxy IP Resolution
- F-01 & F-02: Auth Reset & Staff Invitation Outbox Formatting
"""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import MagicMock, patch
import uuid

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.exceptions import ValidationException
from app.core.network import get_trusted_client_ip
from app.core.permissions import CANONICAL_PERMISSIONS
from app.core.razorpay import RazorpayClient
from app.core.security import decrypt_payload, encrypt_payload, hash_password
from app.main import create_app
from app.models.auth_session import SESSION_STATUS_ACTIVE, AuthSession
from app.models.base import Base, utc_now
from app.models.course import (
    COURSE_STATUS_ARCHIVED,
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    Course,
    CourseRevision,
)
from app.models.curriculum import (
    LESSON_TYPE_VIDEO,
    CurriculumLesson,
    CurriculumSection,
)
from app.models.enrollment import ENROLLMENT_STATUS_ACTIVE, Enrollment
from app.models.media import MEDIA_STATUS_READY, MediaAsset
from app.models.notification import (
    OUTBOX_CHANNEL_EMAIL,
    OUTBOX_STATUS_PENDING,
    NotificationOutbox,
)
from app.models.payment import (
    ORDER_STATUS_PAID,
    REFUND_STATUS_PENDING,
    REFUND_STATUS_PROCESSED,
    TRANSACTION_STATUS_SUCCESS,
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
from app.services.course_governance_service import CourseGovernanceService
from app.services.media_service import MediaService
from app.services.outbox_service import OutboxService
from app.services.payment_service import PaymentService
from app.workers.outbox_worker import _format_email_html, _format_email_text
from tests.conftest import create_test_auth_headers


@pytest.fixture
def p0_db():
    """In-memory SQLite database seeded with core RBAC roles and permissions."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    roles = [
        Role(id=ROLE_VISITOR, name="Visitor", description="Public guest"),
        Role(id=ROLE_STUDENT, name="Student", description="Enrolled learner"),
        Role(id=ROLE_STAFF, name="Staff", description="Teaching assistant"),
        Role(id=ROLE_ADMIN, name="Admin", description="Platform admin"),
        Role(id=ROLE_SUPER_ADMIN, name="Super Admin", description="Owner"),
    ]
    session.add_all(roles)

    now = datetime.now(timezone.utc)
    for p_id, p_mod, p_desc in CANONICAL_PERMISSIONS:
        session.add(Permission(id=p_id, module=p_mod, description=p_desc, created_at=now))
    session.flush()

    super_perms = [
        RolePermission(role_id=ROLE_SUPER_ADMIN, permission_id=p[0])
        for p in CANONICAL_PERMISSIONS
    ]
    session.add_all(super_perms)
    session.commit()

    yield session
    session.close()


@pytest.fixture
def p0_client(p0_db: Session):
    """FastAPI TestClient with overridden database dependency."""
    app = create_app()

    def override_get_db():
        try:
            yield p0_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# =============================================================================
# P0-03: Unpublished Course Preview Disclosure Tests
# =============================================================================
class TestP03UnpublishedCoursePreviewDisclosure:
    """Test suite verifying preview lessons and preview media cannot be accessed
    unless parent course and revision are strictly published.
    """

    def test_anonymous_preview_published_course_success(self, p0_client: TestClient, p0_db: Session):
        """Anonymous user can access a preview lesson if course and revision are PUBLISHED."""
        course = Course(
            title="Published Python",
            slug="published-python",
            price_inr=99900,
            status=COURSE_STATUS_PUBLISHED,
        )
        p0_db.add(course)
        p0_db.flush()

        revision = CourseRevision(
            course_id=course.id,
            revision_no=1,
            title="Rev 1",
            status=COURSE_STATUS_PUBLISHED,
        )
        p0_db.add(revision)
        p0_db.flush()
        course.live_revision_id = revision.id

        section = CurriculumSection(course_revision_id=revision.id, title="Intro", sort_order=0)
        p0_db.add(section)
        p0_db.flush()

        lesson = CurriculumLesson(
            section_id=section.id,
            title="Free Preview Lesson",
            lesson_type=LESSON_TYPE_VIDEO,
            is_preview=True,
            sort_order=0,
        )
        p0_db.add(lesson)
        p0_db.commit()

        # Anonymous request
        resp = p0_client.get(f"/api/v1/lessons/{lesson.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(lesson.id)
        assert data["is_preview"] is True

    def test_anonymous_preview_draft_course_blocked(self, p0_client: TestClient, p0_db: Session):
        """Anonymous user cannot access preview lesson if course is DRAFT."""
        course = Course(
            title="Draft Python",
            slug="draft-python",
            price_inr=99900,
            status=COURSE_STATUS_DRAFT,
        )
        p0_db.add(course)
        p0_db.flush()

        revision = CourseRevision(
            course_id=course.id,
            revision_no=1,
            title="Draft Rev",
            status=COURSE_STATUS_DRAFT,
        )
        p0_db.add(revision)
        p0_db.flush()

        section = CurriculumSection(course_revision_id=revision.id, title="Intro", sort_order=0)
        p0_db.add(section)
        p0_db.flush()

        lesson = CurriculumLesson(
            section_id=section.id,
            title="Draft Preview Lesson",
            lesson_type=LESSON_TYPE_VIDEO,
            is_preview=True,
            sort_order=0,
        )
        p0_db.add(lesson)
        p0_db.commit()

        # Anonymous request must fail with 403
        resp = p0_client.get(f"/api/v1/lessons/{lesson.id}")
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "COURSE_NOT_PUBLISHED"

    def test_anonymous_preview_archived_revision_blocked(self, p0_client: TestClient, p0_db: Session):
        """Anonymous user cannot access preview lesson on an archived non-live revision."""
        course = Course(
            title="Course Live Rev 2",
            slug="course-live-rev-2",
            price_inr=99900,
            status=COURSE_STATUS_PUBLISHED,
        )
        p0_db.add(course)
        p0_db.flush()

        rev1 = CourseRevision(
            course_id=course.id,
            revision_no=1,
            title="Rev 1 Archived",
            status=COURSE_STATUS_ARCHIVED,
        )
        rev2 = CourseRevision(
            course_id=course.id,
            revision_no=2,
            title="Rev 2 Live",
            status=COURSE_STATUS_PUBLISHED,
        )
        p0_db.add_all([rev1, rev2])
        p0_db.flush()
        course.live_revision_id = rev2.id

        sec1 = CurriculumSection(course_revision_id=rev1.id, title="Old Section", sort_order=0)
        p0_db.add(sec1)
        p0_db.flush()

        old_lesson = CurriculumLesson(
            section_id=sec1.id,
            title="Old Preview Lesson",
            lesson_type=LESSON_TYPE_VIDEO,
            is_preview=True,
            sort_order=0,
        )
        p0_db.add(old_lesson)
        p0_db.commit()

        # Anonymous request to old revision preview lesson must be blocked
        resp = p0_client.get(f"/api/v1/lessons/{old_lesson.id}")
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "COURSE_NOT_PUBLISHED"

    def test_preview_media_in_draft_course_blocked(self, p0_client: TestClient, p0_db: Session):
        """Preview media playback token is blocked if parent course is DRAFT."""
        super_admin = User(
            email="admin_p03@example.com",
            full_name="Admin P03",
            password_hash=hash_password("SuperSecret123!"),
            is_verified=True,
            is_active=True,
        )
        student = User(
            email="student_p03@example.com",
            full_name="Student P03",
            password_hash=hash_password("SuperSecret123!"),
            is_verified=True,
            is_active=True,
        )
        p0_db.add_all([super_admin, student])
        p0_db.flush()
        student.user_roles.append(UserRole(role_id=ROLE_STUDENT, user_id=student.id))

        media = MediaAsset(
            uploader_id=super_admin.id,
            filename="draft_preview.mp4",
            file_key="videos/draft_preview.mp4",
            bucket="lms-media",
            mime_type="video/mp4",
            file_size_bytes=1000,
            status=MEDIA_STATUS_READY,
        )
        p0_db.add(media)
        p0_db.flush()

        course = Course(
            title="Draft Media Course",
            slug="draft-media-course",
            price_inr=50000,
            status=COURSE_STATUS_DRAFT,
        )
        p0_db.add(course)
        p0_db.flush()

        rev = CourseRevision(course_id=course.id, revision_no=1, title="Draft Rev", status=COURSE_STATUS_DRAFT)
        p0_db.add(rev)
        p0_db.flush()

        sec = CurriculumSection(course_revision_id=rev.id, title="Sec", sort_order=0)
        p0_db.add(sec)
        p0_db.flush()

        lesson = CurriculumLesson(
            section_id=sec.id,
            title="Draft Lesson",
            lesson_type=LESSON_TYPE_VIDEO,
            is_preview=True,
            content={"media_asset_id": str(media.id)},
        )
        p0_db.add(lesson)
        p0_db.commit()

        # Non-enrolled student attempting to get playback token for draft preview media
        headers = create_test_auth_headers(student, p0_db)
        resp = p0_client.post(
            f"/api/v1/media/{media.id}/playback-token",
            json={"lesson_id": str(lesson.id)},
            headers=headers,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "PREVIEW_NOT_PUBLISHED"


# =============================================================================
# P0-04: Course Governance Publication Checklist Bypass Tests
# =============================================================================
class TestP04CourseGovernancePublicationChecklist:
    """Test suite verifying Super Admin status updates route through the
    canonical CourseService publication checklist workflow.
    """

    @pytest.mark.anyio
    async def test_publish_empty_course_rejected_by_checklist(self, p0_db: Session):
        """Transitioning empty draft course to PUBLISHED fails with checklist validation error."""
        super_admin = User(
            email="super_gov@example.com",
            full_name="Super Gov",
            password_hash=hash_password("SuperSecret123!"),
            is_verified=True,
            is_active=True,
        )
        p0_db.add(super_admin)
        p0_db.flush()
        super_admin.user_roles.append(UserRole(role_id=ROLE_SUPER_ADMIN, user_id=super_admin.id))

        course = Course(
            title="Empty Draft Course",
            slug="empty-draft-course",
            price_inr=100000,
            status=COURSE_STATUS_DRAFT,
        )
        p0_db.add(course)
        p0_db.flush()

        # Revision with NO curriculum
        revision = CourseRevision(
            course_id=course.id,
            revision_no=1,
            title="Rev 1 Empty",
            status=COURSE_STATUS_DRAFT,
        )
        p0_db.add(revision)
        p0_db.commit()

        gov_service = CourseGovernanceService()
        with pytest.raises((HTTPException, ValidationException)) as exc_info:
            await gov_service.update_course_status(
                db=p0_db,
                current_user=super_admin,
                course_id=course.id,
                target_status=COURSE_STATUS_PUBLISHED,
            )

        err_str = str(exc_info.value).lower()
        assert "checklist" in err_str or getattr(exc_info.value, "code", "") == "PUBLISH_CHECKLIST_FAILED"

    @pytest.mark.anyio
    async def test_publish_valid_course_creates_snapshot(self, p0_db: Session):
        """Transitioning valid course to PUBLISHED creates immutable JSONB snapshot and sets live revision."""
        super_admin = User(
            email="super_gov2@example.com",
            full_name="Super Gov 2",
            password_hash=hash_password("SuperSecret123!"),
            is_verified=True,
            is_active=True,
        )
        p0_db.add(super_admin)
        p0_db.flush()
        super_admin.user_roles.append(UserRole(role_id=ROLE_SUPER_ADMIN, user_id=super_admin.id))

        course = Course(
            title="Valid Complete Course",
            slug="valid-complete-course",
            headline="Complete professional course from zero to hero",
            price_inr=100000,
            status=COURSE_STATUS_DRAFT,
        )
        p0_db.add(course)
        p0_db.flush()

        revision = CourseRevision(
            course_id=course.id,
            revision_no=1,
            title="Rev 1 Complete",
            status=COURSE_STATUS_DRAFT,
        )
        p0_db.add(revision)
        p0_db.flush()

        sec = CurriculumSection(course_revision_id=revision.id, title="Module 1", sort_order=0)
        p0_db.add(sec)
        p0_db.flush()

        media = MediaAsset(
            uploader_id=super_admin.id,
            filename="vid.mp4",
            file_key="videos/vid.mp4",
            bucket="lms-media",
            mime_type="video/mp4",
            file_size_bytes=5000,
            status=MEDIA_STATUS_READY,
        )
        p0_db.add(media)
        p0_db.flush()

        lesson = CurriculumLesson(
            section_id=sec.id,
            title="Lesson 1",
            lesson_type=LESSON_TYPE_VIDEO,
            is_preview=True,
            sort_order=0,
            content={"media_asset_id": str(media.id)},
        )
        p0_db.add(lesson)
        p0_db.commit()

        gov_service = CourseGovernanceService()
        updated_course = await gov_service.update_course_status(
            db=p0_db,
            current_user=super_admin,
            course_id=course.id,
            target_status=COURSE_STATUS_PUBLISHED,
        )

        assert updated_course.status == COURSE_STATUS_PUBLISHED
        assert updated_course.live_revision_id == revision.id
        p0_db.refresh(revision)
        assert revision.status == COURSE_STATUS_PUBLISHED
        assert revision.snapshot is not None


# =============================================================================
# P0-05: Refund Idempotency and Financial Integrity Tests
# =============================================================================
class TestP05RefundIdempotencyAndIntegrity:
    """Test suite verifying refund idempotency, durable pending state on gateway timeout,
    and webhook reconciliation for unrecorded refunds.
    """

    def test_duplicate_refund_rejected_when_pending(self, p0_db: Session):
        """Order with existing PENDING refund rejects subsequent refund attempt with 409 Conflict."""
        super_admin = User(
            email="super_refund@example.com",
            full_name="Super Refund",
            password_hash=hash_password("SuperSecret123!"),
            is_verified=True,
            is_active=True,
        )
        student = User(
            email="student_refund@example.com",
            full_name="Student Refund",
            password_hash=hash_password("SuperSecret123!"),
            is_verified=True,
            is_active=True,
        )
        p0_db.add_all([super_admin, student])
        p0_db.flush()
        super_admin.user_roles.append(UserRole(role_id=ROLE_SUPER_ADMIN, user_id=super_admin.id))

        course = Course(title="Course R", slug="course-r", price_inr=50000, status=COURSE_STATUS_PUBLISHED)
        p0_db.add(course)
        p0_db.flush()

        order = Order(
            order_no="ORD-TEST-001",
            student_id=student.id,
            course_id=course.id,
            amount_inr=50000,
            status=ORDER_STATUS_PAID,
            razorpay_order_id="order_test_001",
        )
        p0_db.add(order)
        p0_db.flush()

        tx = PaymentTransaction(
            order_id=order.id,
            razorpay_payment_id="pay_test_001",
            razorpay_signature="sig_test_001",
            status=TRANSACTION_STATUS_SUCCESS,
            amount_inr=50000,
            raw_payload={"mock": True},
        )
        p0_db.add(tx)

        # Existing pending refund
        existing_pending = Refund(
            order_id=order.id,
            amount_inr=50000,
            reason="Prior attempt pending reconciliation",
            status=REFUND_STATUS_PENDING,
            approved_by=super_admin.id,
        )
        p0_db.add(existing_pending)
        p0_db.commit()

        payment_service = PaymentService()
        with pytest.raises(HTTPException) as exc_info:
            payment_service.refund_order(
                session=p0_db,
                order_id=order.id,
                reason="Second refund attempt",
                amount_inr=50000,
                current_user=super_admin,
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "REFUND_PENDING_RECONCILIATION"

    def test_gateway_timeout_persists_pending_refund_durably(self, p0_db: Session):
        """Gateway timeout during refund persists PENDING record and raises 504 Gateway Timeout."""
        super_admin = User(
            email="super_refund2@example.com",
            full_name="Super Refund 2",
            password_hash=hash_password("SuperSecret123!"),
            is_verified=True,
            is_active=True,
        )
        student = User(
            email="student_refund2@example.com",
            full_name="Student Refund 2",
            password_hash=hash_password("SuperSecret123!"),
            is_verified=True,
            is_active=True,
        )
        p0_db.add_all([super_admin, student])
        p0_db.flush()
        super_admin.user_roles.append(UserRole(role_id=ROLE_SUPER_ADMIN, user_id=super_admin.id))

        course = Course(title="Course R2", slug="course-r2", price_inr=50000, status=COURSE_STATUS_PUBLISHED)
        p0_db.add(course)
        p0_db.flush()

        order = Order(
            order_no="ORD-TEST-002",
            student_id=student.id,
            course_id=course.id,
            amount_inr=50000,
            status=ORDER_STATUS_PAID,
            razorpay_order_id="order_test_002",
        )
        p0_db.add(order)
        p0_db.flush()

        tx = PaymentTransaction(
            order_id=order.id,
            razorpay_payment_id="pay_test_002",
            razorpay_signature="sig_test_002",
            status=TRANSACTION_STATUS_SUCCESS,
            amount_inr=50000,
            raw_payload={"mock": True},
        )
        p0_db.add(tx)
        p0_db.commit()

        mock_razorpay = MagicMock()
        mock_razorpay.create_refund.side_effect = TimeoutError("Connection to Razorpay gateway timed out")

        payment_service = PaymentService(razorpay_client=mock_razorpay)
        with pytest.raises(HTTPException) as exc_info:
            payment_service.refund_order(
                session=p0_db,
                order_id=order.id,
                reason="Customer requested refund",
                amount_inr=50000,
                current_user=super_admin,
            )

        assert exc_info.value.status_code == 504
        assert exc_info.value.detail["code"] == "GATEWAY_TIMEOUT_PENDING_RECONCILIATION"

        # Verify durable persistence in database
        saved_refund = p0_db.query(Refund).filter(Refund.order_id == order.id).first()
        assert saved_refund is not None
        assert saved_refund.status == REFUND_STATUS_PENDING
        assert saved_refund.amount_inr == 50000

    def test_webhook_reconciliation_missing_refund_record(self, p0_db: Session):
        """refund.processed webhook for unrecorded gateway refund creates local record and reconciles."""
        student = User(
            email="student_refund3@example.com",
            full_name="Student Refund 3",
            password_hash=hash_password("SuperSecret123!"),
            is_verified=True,
            is_active=True,
        )
        p0_db.add(student)
        p0_db.flush()

        course = Course(title="Course R3", slug="course-r3", price_inr=30000, status=COURSE_STATUS_PUBLISHED)
        p0_db.add(course)
        p0_db.flush()

        order = Order(
            order_no="ORD-TEST-003",
            student_id=student.id,
            course_id=course.id,
            amount_inr=30000,
            status=ORDER_STATUS_PAID,
            razorpay_order_id="order_test_003",
        )
        p0_db.add(order)
        p0_db.flush()

        tx = PaymentTransaction(
            order_id=order.id,
            razorpay_payment_id="pay_test_003",
            razorpay_signature="sig_test_003",
            status=TRANSACTION_STATUS_SUCCESS,
            amount_inr=30000,
            raw_payload={"mock": True},
        )
        p0_db.add(tx)

        enrollment = Enrollment(
            student_id=student.id,
            course_id=course.id,
            order_id=order.id,
            status=ENROLLMENT_STATUS_ACTIVE,
        )
        p0_db.add(enrollment)
        p0_db.commit()

        webhook_payload = {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_direct_gw_999",
                        "payment_id": "pay_test_003",
                        "amount": 30000,
                        "notes": {"reason": "Direct dashboard refund"},
                    }
                }
            },
        }

        mock_razorpay = MagicMock()
        mock_razorpay.verify_webhook_signature.return_value = True

        payment_service = PaymentService(razorpay_client=mock_razorpay)
        result = payment_service.process_razorpay_webhook(
            session=p0_db,
            raw_body=json.dumps(webhook_payload).encode(),
            signature_header="mock_valid_signature",
        )

        assert result["status"] == "ok"
        p0_db.commit()

        # Check that refund record was created and reconciled
        refund = p0_db.query(Refund).filter(Refund.razorpay_refund_id == "rfnd_direct_gw_999").first()
        assert refund is not None
        assert refund.status == REFUND_STATUS_PROCESSED
        assert refund.amount_inr == 30000

        # Check that order status transitioned to REFUNDED
        p0_db.refresh(order)
        assert order.status == "REFUNDED"

        # Check that enrollment was revoked
        p0_db.refresh(enrollment)
        assert enrollment.status == "REVOKED"


# =============================================================================
# P0-06: Sensitive Outbox Token Fernet Encryption Tests
# =============================================================================
class TestP06OutboxTokenEncryption:
    """Test suite verifying sensitive outbox payloads are encrypted at rest with Fernet."""

    @pytest.mark.anyio
    async def test_sensitive_tokens_encrypted_in_database(self, p0_db: Session):
        """Outbox payload with verification_token is stored encrypted in raw database row."""
        outbox_service = OutboxService()
        raw_secret_token = "ultra_secret_high_entropy_token_xyz987"

        event = await outbox_service.publish_event(
            session=p0_db,
            event_type="AUTH_VERIFY_EMAIL",
            channel=OUTBOX_CHANNEL_EMAIL,
            recipient="test_crypto@example.com",
            subject="Verify Email",
            payload={
                "user_id": str(uuid.uuid4()),
                "full_name": "Crypto Test",
                "verification_token": raw_secret_token,
                "verification_url": f"https://lms.local/verify-email?token={raw_secret_token}",
            },
        )
        p0_db.commit()

        # Query RAW database value bypassing ORM to verify encryption at rest
        with p0_db.get_bind().connect() as conn:
            raw_payload_str = conn.execute(
                text("SELECT payload FROM notification_outbox WHERE id = :id"),
                {"id": event.id.hex},
            ).scalar()

        raw_payload = json.loads(raw_payload_str)
        # Raw active token must NEVER appear in raw database storage
        assert raw_secret_token not in raw_payload_str
        assert raw_payload.get("is_encrypted") is True
        assert "_encrypted" in raw_payload

        # ORM transparently decrypts on retrieval
        p0_db.expire_all()
        retrieved_event = p0_db.query(NotificationOutbox).filter(NotificationOutbox.id == event.id).first()
        assert retrieved_event is not None
        assert retrieved_event.payload["verification_token"] == raw_secret_token
        assert raw_secret_token in retrieved_event.payload["verification_url"]

    def test_direct_fernet_crypto_roundtrip(self):
        """Verifies Fernet encrypt and decrypt utilities produce exact plaintext match."""
        sensitive_data = {"token": "secret_abc_123", "action": "staff_invite"}
        ciphertext = encrypt_payload(sensitive_data)
        assert "secret_abc_123" not in ciphertext
        decrypted = decrypt_payload(ciphertext)
        assert decrypted == sensitive_data


# =============================================================================
# P0-07: Trusted Proxy IP Resolution Tests
# =============================================================================
class TestP07TrustedProxyIPResolution:
    """Test suite verifying client IP address resolution adheres to trusted proxy hops."""

    def test_untrusted_direct_peer_ignores_spoofed_x_forwarded_for(self):
        """Peer from untrusted IP cannot spoof IP using X-Forwarded-For."""
        request = MagicMock()
        request.client.host = "198.51.100.25"  # Public untrusted IP
        request.headers.get.side_effect = lambda h: {
            "x-forwarded-for": "203.0.113.195, 198.51.100.25",
        }.get(h.lower())

        resolved_ip = get_trusted_client_ip(request)
        # Must return the direct untrusted peer host, NOT the spoofed header
        assert resolved_ip == "198.51.100.25"

    def test_trusted_proxy_resolves_immediate_client(self):
        """Trusted reverse proxy (127.0.0.1) properly unwraps client IP."""
        request = MagicMock()
        request.client.host = "127.0.0.1"  # Default trusted loopback proxy
        request.headers.get.side_effect = lambda h: {
            "x-forwarded-for": "203.0.113.50",
        }.get(h.lower())

        resolved_ip = get_trusted_client_ip(request)
        assert resolved_ip == "203.0.113.50"


# =============================================================================
# F-01 & F-02: Outbox Worker Email Formatting Tests
# =============================================================================
class TestF01F02EmailFormatting:
    """Test suite verifying password reset and staff invitation email templates."""

    def test_f01_auth_reset_password_formatted_properly(self):
        """AUTH_RESET_PASSWORD event formats both plain text and HTML with reset link."""
        event = NotificationOutbox(
            event_type="AUTH_RESET_PASSWORD",
            channel=OUTBOX_CHANNEL_EMAIL,
            recipient="learner@example.com",
            subject="Reset your LMS password",
            payload={
                "user_id": str(uuid.uuid4()),
                "full_name": "Learner",
                "reset_token": "token_reset_999",
                "reset_url": "https://lms.local/reset-password?token=token_reset_999",
            },
        )

        text_body = _format_email_text(event)
        html_body = _format_email_html(event)

        assert "https://lms.local/reset-password?token=token_reset_999" in text_body
        assert "Reset Your Password" in html_body
        assert "https://lms.local/reset-password?token=token_reset_999" in html_body

    def test_f02_staff_invitation_formatted_with_html_template(self):
        """STAFF_INVITATION event formats both plain text and full HTML with claim link."""
        event = NotificationOutbox(
            event_type="STAFF_INVITATION",
            channel=OUTBOX_CHANNEL_EMAIL,
            recipient="newstaff@example.com",
            subject="Invitation to join LMS team",
            payload={
                "user_id": str(uuid.uuid4()),
                "email": "newstaff@example.com",
                "full_name": "Alice Assistant",
                "role": "Staff",
                "invitation_token": "invite_token_123",
                "invitation_url": "https://lms.local/onboarding/claim?token=invite_token_123",
            },
        )

        text_body = _format_email_text(event)
        html_body = _format_email_html(event)

        assert "https://lms.local/onboarding/claim?token=invite_token_123" in text_body
        assert "Alice Assistant" in text_body
        assert "Staff Invitation" in html_body
        assert "Accept Invitation" in html_body
        assert "https://lms.local/onboarding/claim?token=invite_token_123" in html_body
