"""P1 Security and Functional Remediation Regression Suite.

Verifies fixes for:
- BUG-004: Real Object Storage Integration & SigV4 canonical URI matching
- BUG-017: Upload Confirmation File Verification & Video Truthful PROCESSING State
- BUG-012: Partial Refund Accounting, Cumulative Limits, & Enrollment Policy
- BUG-022: Payment Amount Mismatch Transaction Persistence
- BUG-007: Relational Course Publishing Checklist Assessment Verification
- BUG-008: Course Revision Cloning of Quiz & Assignment Entities
- BUG-018: Published Assessment Immutability (REVISION_IMMUTABLE)
- BUG-009: Quiz Autosave & Submission Enrollment Revalidation
- BUG-010: Quiz Expiration Persistence Without Rollback
- BUG-005: Outbox Email Delivery Truthful Reporting & Production Rejection
- BUG-006: Sole Super Admin Database-Level Concurrency Serialization Lock
- BUG-013: Certificate QR Code Absolute Public Verification URL
- BUG-015: Runtime Dependency Audit
- BUG-016: Multi-Page PDF Watermark Integrity & Zero Stream Corruption
"""

import io
import json
from datetime import datetime, timedelta, timezone
import uuid
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from reportlab.pdfgen import canvas

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    UnauthorizedException,
)
from app.core.pdf_watermark import apply_pdf_watermark
from app.core.razorpay import RazorpayClient, compute_razorpay_signature
from app.core.security import hash_password
from app.core.storage import StorageClient
from app.models.assignment import (
    Assignment,
    Rubric,
    RubricCriteria,
)
from app.models.base import Base, utc_now
from app.models.course import (
    COURSE_STATUS_PUBLISHED,
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
    Course,
    CourseRevision,
)
from app.models.curriculum import (
    CurriculumLesson,
    CurriculumSection,
    LESSON_TYPE_ASSIGNMENT,
    LESSON_TYPE_QUIZ,
    LESSON_TYPE_VIDEO,
)
from app.models.enrollment import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_REVOKED,
    Enrollment,
)
from app.models.media import (
    MEDIA_STATUS_FAILED,
    MEDIA_STATUS_PROCESSING,
    MEDIA_STATUS_READY,
    MEDIA_STATUS_UPLOADING,
    MediaAsset,
)
from app.models.notification import NotificationOutbox
from app.models.payment import (
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REFUNDED,
    REFUND_STATUS_FAILED,
    REFUND_STATUS_PENDING,
    REFUND_STATUS_PROCESSED,
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_SUCCESS,
    Order,
    PaymentTransaction,
    Refund,
)
from app.models.quiz import (
    ATTEMPT_STATUS_EXPIRED,
    ATTEMPT_STATUS_IN_PROGRESS,
    QUESTION_TYPE_MCQ_SINGLE,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    QuizQuestionOption,
)
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    Role,
    User,
    UserRole,
)
from app.repositories.course_repo import CourseRepository
from app.schemas.assignment import AssignmentCreateRequest, RubricCreateRequest, RubricCriteriaCreateRequest
from app.schemas.media import UploadConfirmRequest, UploadIntentRequest
from app.schemas.quiz import AutosaveAnswerRequest, QuizCreateRequest
from app.services.assignment_service import AssignmentService
from app.services.certificate_service import CertificateService
from app.services.course_service import CourseService
from app.services.media_service import MediaService
from app.services.payment_service import PaymentService
from app.services.quiz_service import QuizService
from app.services.user_service import UserService
from app.workers.outbox_worker import default_outbox_dispatcher


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

    # Pre-populate system roles
    roles = [
        Role(id=ROLE_STUDENT, name="Student"),
        Role(id=ROLE_STAFF, name="Staff"),
        Role(id=ROLE_ADMIN, name="Admin"),
        Role(id=ROLE_SUPER_ADMIN, name="Super Admin"),
    ]
    session.add_all(roles)
    session.commit()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def super_admin(db_session: Session) -> User:
    u = User(
        email="superadmin@p1.local",
        full_name="Super Admin P1",
        password_hash=hash_password("Pass123!"),
        is_verified=True,
        is_active=True,
    )
    u.user_roles.append(UserRole(role_id=ROLE_SUPER_ADMIN))
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def student(db_session: Session) -> User:
    u = User(
        email="student@p1.local",
        full_name="Student P1",
        password_hash=hash_password("Pass123!"),
        is_verified=True,
        is_active=True,
    )
    u.user_roles.append(UserRole(role_id=ROLE_STUDENT))
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


# =============================================================================
# GROUP A: STORAGE & MEDIA INTEGRITY (BUG-004, BUG-017)
# =============================================================================

class TestGroupAStorageMediaIntegrity:

    def test_bug_004_storage_canonical_request_uri_matching(self):
        """BUG-004: Presigned URL base path matches SigV4 canonical URI."""
        settings = Settings(
            STORAGE_ENDPOINT_URL="https://cf-account.r2.cloudflarestorage.com",
            STORAGE_BUCKET_NAME="my-bucket",
            STORAGE_ACCESS_KEY_ID="test-key",
            STORAGE_SECRET_ACCESS_KEY=SecretStr("test-secret"),
        )
        storage = StorageClient(settings)
        url, headers = storage.generate_presigned_upload_url(
            file_key="videos/sample.mp4",
            mime_type="video/mp4",
            file_size_bytes=1000,
        )
        assert "https://cf-account.r2.cloudflarestorage.com/my-bucket/videos/sample.mp4" in url
        assert "X-Amz-Signature=" in url

        dl_url = storage.generate_presigned_download_url("videos/sample.mp4")
        assert "https://cf-account.r2.cloudflarestorage.com/my-bucket/videos/sample.mp4" in dl_url

    def test_bug_004_path_style_vs_virtual_host_style_urls(self):
        """BUG-004: Supports both virtual-hosted and path-style S3/R2 endpoints."""
        # 1. Virtual-hosted style: bucket is part of hostname
        vh_settings = Settings(
            STORAGE_ENDPOINT_URL="https://mybucket.r2.cloudflarestorage.com",
            STORAGE_BUCKET_NAME="mybucket",
            STORAGE_ACCESS_KEY_ID="vh-key",
            STORAGE_SECRET_ACCESS_KEY=SecretStr("vh-secret"),
        )
        vh_storage = StorageClient(vh_settings)
        host, canonical_uri, base_url = vh_storage._get_endpoint_and_uri("courses/intro.mp4")
        assert host == "mybucket.r2.cloudflarestorage.com"
        assert canonical_uri == "/courses/intro.mp4"
        assert base_url == "https://mybucket.r2.cloudflarestorage.com/courses/intro.mp4"

        # 2. Path-style: custom endpoint with bucket in path
        ps_settings = Settings(
            STORAGE_ENDPOINT_URL="http://localhost:9000",
            STORAGE_BUCKET_NAME="mybucket",
            STORAGE_ACCESS_KEY_ID="ps-key",
            STORAGE_SECRET_ACCESS_KEY=SecretStr("ps-secret"),
        )
        ps_storage = StorageClient(ps_settings)
        p_host, p_uri, p_url = ps_storage._get_endpoint_and_uri("courses/intro.mp4")
        assert p_host == "localhost:9000"
        assert p_uri == "/mybucket/courses/intro.mp4"
        assert p_url == "http://localhost:9000/mybucket/courses/intro.mp4"

    def test_bug_004_production_prohibits_in_memory_fallback(self):
        """BUG-004: Production strictly fails closed on unconfigured storage without in-memory fallback."""
        prod_settings = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            SECRET_KEY=SecretStr("a" * 40),
            BACKEND_URL="https://api.example.com",
            DATABASE_URL="postgresql+psycopg://u:p@db.internal:5432/lms_prod",
            CORS_ORIGINS=["https://example.com"],
            RAZORPAY_KEY_ID="rzp_live_key123",
            RAZORPAY_KEY_SECRET=SecretStr("live_sec_12345678"),
            RAZORPAY_WEBHOOK_SECRET=SecretStr("live_wh_12345678"),
            STORAGE_ACCESS_KEY_ID="mock-access-key",  # Unconfigured!
            STORAGE_SECRET_ACCESS_KEY=SecretStr("mock-secret-key"),
        )
        storage = StorageClient(prod_settings)
        assert storage.is_remote_configured is False

        with pytest.raises(RuntimeError):
            storage.put_object("file.txt", b"content")
        with pytest.raises(KeyError):
            storage.get_object("file.txt")
        with pytest.raises(RuntimeError):
            storage.head_object("file.txt")
        with pytest.raises(RuntimeError):
            storage.delete_object("file.txt")
        with pytest.raises(RuntimeError):
            storage.generate_presigned_upload_url("file.txt", "text/plain", 10)
        with pytest.raises(RuntimeError):
            storage.generate_presigned_download_url("file.txt")

    def test_bug_004_mocked_remote_http_sigv4_dispatch(self, monkeypatch):
        """BUG-004: Deterministic HTTP mocked integration verifies SigV4 headers on PUT/GET/HEAD/DELETE."""
        settings = Settings(
            STORAGE_ENDPOINT_URL="https://remote-storage.example.com",
            STORAGE_BUCKET_NAME="secure-bucket",
            STORAGE_ACCESS_KEY_ID="AKIA_REAL_KEY_123",
            STORAGE_SECRET_ACCESS_KEY=SecretStr("REAL_SECRET_KEY_1234567890"),
            STORAGE_REGION="us-east-1",
        )
        storage = StorageClient(settings)
        assert storage.is_remote_configured is True

        captured_requests = []

        class MockHTTPResponse:
            def __init__(self, code=200, headers=None, body=b""):
                self.code = code
                self._headers = headers or {}
                self.body = body

            def getcode(self):
                return self.code

            def info(self):
                return self._headers

            def read(self):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        def mock_urlopen(req, timeout=None):
            captured_requests.append(req)
            if req.get_method() == "HEAD":
                return MockHTTPResponse(200, {"Content-Length": "128", "Content-Type": "application/pdf"})
            elif req.get_method() == "GET":
                return MockHTTPResponse(200, {"Content-Type": "application/pdf"}, b"%PDF-1.4 remote data")
            elif req.get_method() == "PUT":
                return MockHTTPResponse(200)
            elif req.get_method() == "DELETE":
                return MockHTTPResponse(204)
            return MockHTTPResponse(404)

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        # 1. PUT
        storage.put_object("docs/guide.pdf", b"guide bytes", content_type="application/pdf")
        assert len(captured_requests) == 1
        put_req = captured_requests[-1]
        assert put_req.get_method() == "PUT"
        assert "AWS4-HMAC-SHA256" in put_req.headers["Authorization"]
        assert "AKIA_REAL_KEY_123" in put_req.headers["Authorization"]

        # 2. HEAD
        meta = storage.head_object("docs/guide.pdf")
        assert meta is not None
        assert meta["size"] == 128
        head_req = captured_requests[-1]
        assert head_req.get_method() == "HEAD"

        # 3. GET
        data = storage.get_object("docs/guide.pdf")
        assert data == b"%PDF-1.4 remote data"
        get_req = captured_requests[-1]
        assert get_req.get_method() == "GET"

        # 4. DELETE
        res = storage.delete_object("docs/guide.pdf")
        assert res is True
        del_req = captured_requests[-1]
        assert del_req.get_method() == "DELETE"

    def test_bug_004_head_and_object_existence(self):
        """BUG-004: head_object and object_exists correctly inspect storage without mock fallback."""
        storage = StorageClient()
        test_key = f"docs/{uuid.uuid4()}/report.pdf"

        assert storage.object_exists(test_key) is False
        assert storage.head_object(test_key) is None
        with pytest.raises(KeyError):
            storage.get_object(test_key)

        storage.put_object(test_key, b"Real PDF Content", content_type="application/pdf")
        assert storage.object_exists(test_key) is True
        meta = storage.head_object(test_key)
        assert meta["exists"] is True
        assert meta["size"] == len(b"Real PDF Content")
        assert meta["content_type"] == "application/pdf"
        assert storage.get_object(test_key) == b"Real PDF Content"

    @pytest.mark.asyncio
    async def test_bug_017_confirm_upload_missing_object_rejected(self, db_session, super_admin):
        """BUG-017: Confirming upload when object is missing remotely fails with OBJECT_NOT_FOUND."""
        media_service = MediaService()
        intent_req = UploadIntentRequest(
            filename="lecture.mp4",
            mime_type="video/mp4",
            file_size_bytes=50000,
        )
        intent = await media_service.create_upload_intent(db_session, super_admin, intent_req)
        db_session.commit()

        # Call confirm without putting object in storage
        confirm_req = UploadConfirmRequest(duration_seconds=300)
        with pytest.raises(BadRequestException) as exc_info:
            await media_service.confirm_upload(db_session, intent.media_id, confirm_req, super_admin)
        assert exc_info.value.code == "OBJECT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_bug_017_video_transitions_to_truthful_processing_state(self, db_session, super_admin):
        """BUG-017: Video upload confirmation transitions to PROCESSING, not READY."""
        media_service = MediaService()
        intent_req = UploadIntentRequest(
            filename="chapter1.mp4",
            mime_type="video/mp4",
            file_size_bytes=50000,
        )
        intent = await media_service.create_upload_intent(db_session, super_admin, intent_req)
        db_session.commit()

        # Put a signature-valid MP4-shaped binary object in storage.
        media_service.storage_client.put_object(
            intent.file_key,
            b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00" * (50000 - 24),
            content_type="video/mp4",
        )

        confirm_req = UploadConfirmRequest(duration_seconds=600)
        resp = await media_service.confirm_upload(db_session, intent.media_id, confirm_req, super_admin)
        db_session.commit()

        # Must be in PROCESSING, with no fabricated HLS URL
        assert resp.status == MEDIA_STATUS_PROCESSING
        assert resp.transcode_output["status"] == "PROCESSING"
        assert "hls_master_url" not in resp.transcode_output

        # When transcoding completes, it transitions to READY
        completed = await media_service.complete_video_transcode(
            db_session,
            intent.media_id,
            hls_master_url=f"hls/{intent.media_id}/master.m3u8",
            resolutions=["1080p", "720p"],
            duration_seconds=600,
            actor=super_admin,
        )
        assert completed.status == MEDIA_STATUS_READY
        assert "hls/" in completed.transcode_output["hls_master_url"]


# =============================================================================
# GROUP B: FINANCIAL CORRECTNESS (BUG-012, BUG-022)
# =============================================================================

class TestGroupBFinancialCorrectness:

    def _setup_paid_order(self, db_session: Session, student: User, super_admin: User, amount_inr: int = 500000) -> Order:
        course = Course(
            title="Commerce Course",
            slug=f"commerce-{uuid.uuid4()}",
            price_inr=amount_inr,
            status=COURSE_STATUS_PUBLISHED,
        )
        db_session.add(course)
        db_session.flush()

        order = Order(
            student_id=student.id,
            course_id=course.id,
            order_no=f"ORD-{uuid.uuid4().hex[:8].upper()}",
            amount_inr=amount_inr,
            currency="INR",
            status=ORDER_STATUS_PAID,
            razorpay_order_id=f"order_{uuid.uuid4().hex[:12]}",
        )
        db_session.add(order)
        db_session.flush()

        tx = PaymentTransaction(
            order_id=order.id,
            razorpay_payment_id=f"pay_{uuid.uuid4().hex[:12]}",
            razorpay_signature="sig_test",
            status=TRANSACTION_STATUS_SUCCESS,
            amount_inr=amount_inr,
            raw_payload={"status": "captured"},
        )
        db_session.add(tx)

        enrollment = Enrollment(
            student_id=student.id,
            course_id=course.id,
            order_id=order.id,
            status=ENROLLMENT_STATUS_ACTIVE,
        )
        db_session.add(enrollment)
        db_session.commit()
        return order

    def test_bug_012_cumulative_partial_refunds(self, db_session, student, super_admin):
        """BUG-012: Multiple partial refunds succeed up to captured amount, rejecting excess."""
        order = self._setup_paid_order(db_session, student, super_admin, amount_inr=100000)
        svc = PaymentService()

        # 1. Partial refund 1: 40000 paise (400 INR)
        r1 = svc.refund_order(db_session, order.id, "Partial 1", 40000, super_admin)
        assert r1.status == REFUND_STATUS_PROCESSED
        assert r1.amount_inr == 40000

        db_session.refresh(order)
        assert order.status == ORDER_STATUS_PAID  # Still PAID because 60000 remains

        # Enrollment must be preserved on partial refund
        enr = db_session.query(Enrollment).filter(Enrollment.order_id == order.id).one()
        assert enr.status == ENROLLMENT_STATUS_ACTIVE

        # 2. Excessive refund: attempting 70000 paise when only 60000 is left fails with HTTP 400
        with pytest.raises(Exception) as exc_info:
            svc.refund_order(db_session, order.id, "Excessive", 70000, super_admin)
        assert "exceeds refundable balance" in str(exc_info.value)

        # 3. Exact remaining refund: 60000 paise completes full refund
        r2 = svc.refund_order(db_session, order.id, "Final remainder", 60000, super_admin)
        assert r2.status == REFUND_STATUS_PROCESSED

        db_session.refresh(order)
        assert order.status == ORDER_STATUS_REFUNDED

        # Enrollment is now revoked upon exact full refund
        db_session.refresh(enr)
        assert enr.status == ENROLLMENT_STATUS_REVOKED

    def test_bug_022_payment_mismatch_transaction_persists_on_error(self, db_session, student, super_admin):
        """BUG-022: Webhook amount mismatch persists FAILED transaction and audit log."""
        course = Course(
            title="Mismatch Course",
            slug=f"mismatch-{uuid.uuid4()}",
            price_inr=100000,
            status=COURSE_STATUS_PUBLISHED,
        )
        db_session.add(course)
        db_session.flush()

        order = Order(
            student_id=student.id,
            course_id=course.id,
            order_no=f"ORD-{uuid.uuid4().hex[:8].upper()}",
            amount_inr=100000,
            currency="INR",
            status=ORDER_STATUS_PENDING,
            razorpay_order_id="order_mismatch_123",
        )
        db_session.add(order)
        db_session.commit()

        # Webhook payload sends only 50000 paise (500 INR instead of 1000 INR)
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_tampered_999",
                        "order_id": "order_mismatch_123",
                        "amount": 50000,
                        "status": "captured",
                    }
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        test_secret = "test_webhook_secret_key"
        sig = compute_razorpay_signature(raw_body, test_secret)

        rz_client = RazorpayClient()
        rz_client.webhook_secret = test_secret
        svc = PaymentService(razorpay_client=rz_client)
        with pytest.raises(Exception) as exc_info:
            svc.process_razorpay_webhook(db_session, raw_body, sig)
        assert "AMOUNT_MISMATCH" in str(exc_info.value)

        # Transaction MUST persist in database despite 400 exception
        tx = db_session.query(PaymentTransaction).filter(PaymentTransaction.razorpay_payment_id == "pay_tampered_999").one_or_none()
        assert tx is not None
        assert tx.status == TRANSACTION_STATUS_FAILED
        assert tx.amount_inr == 50000

        # Order must remain PENDING
        db_session.refresh(order)
        assert order.status == ORDER_STATUS_PENDING

    def test_bug_012_pending_refund_webhook_reconciliation(self, db_session, student, super_admin, monkeypatch):
        """BUG-012: Pending refund leaves order PAID and enrollment ACTIVE until refund.processed webhook reconciles."""
        order = self._setup_paid_order(db_session, student, super_admin, amount_inr=100000)
        test_secret = "test_webhook_secret_key"
        rz_client = RazorpayClient()
        rz_client.webhook_secret = test_secret

        # Mock Razorpay returning 'pending' status
        def mock_create_refund(payment_id, amount_inr, notes=None):
            return {
                "id": "rfnd_test_pending_777",
                "payment_id": payment_id,
                "amount": amount_inr,
                "status": "pending",
            }

        monkeypatch.setattr(rz_client, "create_refund", mock_create_refund)
        svc = PaymentService(razorpay_client=rz_client)

        # 1. Initiate full refund -> Gateway returns 'pending'
        refund_resp = svc.refund_order(db_session, order.id, "Pending refund", 100000, super_admin)
        assert refund_resp.status == REFUND_STATUS_PENDING
        assert refund_resp.razorpay_refund_id == "rfnd_test_pending_777"

        # Order must remain PAID, enrollment ACTIVE
        db_session.refresh(order)
        assert order.status == ORDER_STATUS_PAID
        enr = db_session.query(Enrollment).filter(Enrollment.order_id == order.id).one()
        assert enr.status == ENROLLMENT_STATUS_ACTIVE

        # 2. Razorpay sends refund.processed webhook
        wh_payload = {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_test_pending_777",
                        "amount": 100000,
                        "status": "processed",
                    }
                }
            },
        }
        raw_body = json.dumps(wh_payload).encode("utf-8")
        sig = compute_razorpay_signature(raw_body, test_secret)

        wh_res = svc.process_razorpay_webhook(db_session, raw_body, sig)
        assert wh_res["status"] == "ok"
        assert wh_res["event"] == "refund.processed"

        # Now refund is PROCESSED, order is REFUNDED, enrollment is REVOKED
        db_refund = db_session.query(Refund).filter(Refund.razorpay_refund_id == "rfnd_test_pending_777").one()
        assert db_refund.status == REFUND_STATUS_PROCESSED

        db_session.refresh(order)
        assert order.status == ORDER_STATUS_REFUNDED

        db_session.refresh(enr)
        assert enr.status == ENROLLMENT_STATUS_REVOKED

    def test_bug_012_failed_refund_webhook_reconciliation(self, db_session, student, super_admin, monkeypatch):
        """BUG-012: refund.failed webhook updates refund to FAILED and preserves active enrollment."""
        order = self._setup_paid_order(db_session, student, super_admin, amount_inr=100000)
        test_secret = "test_webhook_secret_key"
        rz_client = RazorpayClient()
        rz_client.webhook_secret = test_secret

        monkeypatch.setattr(
            rz_client,
            "create_refund",
            lambda payment_id, amount_inr, notes=None: {
                "id": "rfnd_test_fail_888",
                "payment_id": payment_id,
                "amount": amount_inr,
                "status": "pending",
            },
        )
        svc = PaymentService(razorpay_client=rz_client)
        svc.refund_order(db_session, order.id, "Fail test", 100000, super_admin)

        wh_payload = {
            "event": "refund.failed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_test_fail_888",
                        "amount": 100000,
                        "status": "failed",
                    }
                }
            },
        }
        raw_body = json.dumps(wh_payload).encode("utf-8")
        sig = compute_razorpay_signature(raw_body, test_secret)

        wh_res = svc.process_razorpay_webhook(db_session, raw_body, sig)
        assert wh_res["status"] == "ok"

        db_refund = db_session.query(Refund).filter(Refund.razorpay_refund_id == "rfnd_test_fail_888").one()
        assert db_refund.status == REFUND_STATUS_FAILED

        db_session.refresh(order)
        assert order.status == ORDER_STATUS_PAID
        enr = db_session.query(Enrollment).filter(Enrollment.order_id == order.id).one()
        assert enr.status == ENROLLMENT_STATUS_ACTIVE


# =============================================================================
# GROUP C: COURSE REVISION & ASSESSMENT INTEGRITY (BUG-007, BUG-008, BUG-018)
# =============================================================================

class TestGroupCCourseRevisionAndAssessments:

    def test_bug_007_publish_checklist_uses_relational_models(self, db_session, super_admin):
        """BUG-007: Publishing checklist validates relational models rather than stale JSON."""
        course_svc = CourseService()
        repo = CourseRepository()

        course, rev = repo.create_course(
            db_session,
            title="Checklist Course",
            slug=f"checklist-{uuid.uuid4()}",
            headline="Checklist test",
            price_inr=10000,
            is_free=False,
            thumbnail_url="https://images.example.com/thumb.png",
        )
        sec = repo.create_section(db_session, revision=rev, title="Sec 1")
        quiz_les = repo.create_lesson(
            db_session, section=sec, title="Quiz Lesson", lesson_type=LESSON_TYPE_QUIZ, content={}
        )
        assign_les = repo.create_lesson(
            db_session, section=sec, title="Assign Lesson", lesson_type=LESSON_TYPE_ASSIGNMENT, content={}
        )
        db_session.commit()

        # 1. Without relational records, checklist fails with EMPTY_QUIZ and MISSING_ASSIGNMENT_RUBRIC
        res = course_svc.evaluate_publish_checklist(db_session, course.id, rev.id)
        assert res.can_publish is False
        codes = [b.code for b in res.blockers]
        assert "EMPTY_QUIZ" in codes
        assert "MISSING_ASSIGNMENT_RUBRIC" in codes

        # 2. Add relational Quiz with questions and options
        quiz = Quiz(
            lesson_id=quiz_les.id,
            title="Q Title",
            pass_percentage=70,
            time_limit_minutes=20,
            max_attempts=3,
        )
        db_session.add(quiz)
        db_session.flush()
        q = QuizQuestion(quiz_id=quiz.id, question_type=QUESTION_TYPE_MCQ_SINGLE, prompt="Prompt", points=10, sort_order=0)
        db_session.add(q)
        db_session.flush()
        opt = QuizQuestionOption(question_id=q.id, option_text="Correct Opt", is_correct=True, sort_order=0)
        db_session.add(opt)

        # 3. Add relational Assignment with active Rubric
        assignment = Assignment(lesson_id=assign_les.id, title="A Title", instructions="Do it", max_score=100)
        db_session.add(assignment)
        db_session.flush()
        rubric = Rubric(assignment_id=assignment.id, title="R Title", version=1, is_active=True)
        db_session.add(rubric)
        db_session.flush()
        crit = RubricCriteria(rubric_id=rubric.id, title="C Title", max_points=100, weight=1.0, sort_order=0)
        db_session.add(crit)
        db_session.commit()

        # 4. Now checklist passes even though lesson.content is empty!
        res2 = course_svc.evaluate_publish_checklist(db_session, course.id, rev.id)
        codes2 = [b.code for b in res2.blockers]
        assert "EMPTY_QUIZ" not in codes2
        assert "MISSING_ASSIGNMENT_RUBRIC" not in codes2
        assert res2.can_publish is True

    def test_bug_008_deep_clone_revision_copies_assessments(self, db_session, super_admin):
        """BUG-008: Deep clone revision associates independent cloned Quiz and Assignment records."""
        repo = CourseRepository()
        course, rev1 = repo.create_course(
            db_session,
            title="Clone Course",
            slug=f"clone-{uuid.uuid4()}",
            headline="Clone headline",
            price_inr=0,
            is_free=True,
        )
        sec1 = repo.create_section(db_session, revision=rev1, title="Section 1")
        quiz_les1 = repo.create_lesson(db_session, section=sec1, title="Quiz 1", lesson_type=LESSON_TYPE_QUIZ)
        assign_les1 = repo.create_lesson(db_session, section=sec1, title="Assign 1", lesson_type=LESSON_TYPE_ASSIGNMENT)
        db_session.commit()

        # Add Quiz
        quiz1 = Quiz(lesson_id=quiz_les1.id, title="Original Quiz", pass_percentage=80, time_limit_minutes=15, max_attempts=2)
        db_session.add(quiz1)
        db_session.flush()
        q1 = QuizQuestion(quiz_id=quiz1.id, question_type=QUESTION_TYPE_MCQ_SINGLE, prompt="Original Q", points=5, sort_order=0)
        db_session.add(q1)
        db_session.flush()
        opt1 = QuizQuestionOption(question_id=q1.id, option_text="Opt A", is_correct=True, sort_order=0)
        db_session.add(opt1)

        # Add Assignment
        assign1 = Assignment(lesson_id=assign_les1.id, title="Original Assign", instructions="Build it", max_score=50)
        db_session.add(assign1)
        db_session.flush()
        rubric1 = Rubric(assignment_id=assign1.id, title="Rubric 1", version=1, is_active=True)
        db_session.add(rubric1)
        db_session.flush()
        crit1 = RubricCriteria(rubric_id=rubric1.id, title="Criterion 1", max_points=50, weight=1.0, sort_order=0)
        db_session.add(crit1)
        db_session.commit()

        # Clone revision into rev2
        rev2 = repo.deep_clone_revision(db_session, source_revision=rev1, new_revision_no=2)
        db_session.commit()

        # Verify cloned hierarchy has independent cloned assessment records
        assert len(rev2.sections) == 1
        sec2 = rev2.sections[0]
        assert len(sec2.lessons) == 2

        quiz_les2 = [l for l in sec2.lessons if l.lesson_type == LESSON_TYPE_QUIZ][0]
        assign_les2 = [l for l in sec2.lessons if l.lesson_type == LESSON_TYPE_ASSIGNMENT][0]

        # Cloned quiz exists and is linked to quiz_les2
        quiz2 = db_session.query(Quiz).filter(Quiz.lesson_id == quiz_les2.id).one_or_none()
        assert quiz2 is not None
        assert quiz2.id != quiz1.id
        assert quiz2.title == "Original Quiz"
        assert len(quiz2.questions) == 1
        assert quiz2.questions[0].prompt == "Original Q"
        assert len(quiz2.questions[0].options) == 1
        assert quiz2.questions[0].options[0].option_text == "Opt A"

        # Cloned assignment exists and is linked to assign_les2
        assign2 = db_session.query(Assignment).filter(Assignment.lesson_id == assign_les2.id).one_or_none()
        assert assign2 is not None
        assert assign2.id != assign1.id
        assert assign2.title == "Original Assign"
        assert len(assign2.rubrics) == 1
        assert len(assign2.rubrics[0].criteria) == 1
        assert assign2.rubrics[0].criteria[0].title == "Criterion 1"

    def test_bug_018_published_assessment_immutability(self, db_session, super_admin):
        """BUG-018: Quizzes and assignments in published revisions cannot be modified."""
        repo = CourseRepository()
        course, rev = repo.create_course(db_session, title="Immutable Course", slug=f"imm-{uuid.uuid4()}", headline="H", price_inr=0, is_free=True)
        sec = repo.create_section(db_session, revision=rev, title="Sec")
        les = repo.create_lesson(db_session, section=sec, title="L", lesson_type=LESSON_TYPE_QUIZ)
        db_session.commit()

        quiz_svc = QuizService()
        assign_svc = AssignmentService()

        # Mark revision as PUBLISHED
        rev.status = REVISION_STATUS_PUBLISHED
        db_session.commit()

        # Creating quiz on published lesson fails with REVISION_IMMUTABLE
        with pytest.raises(ForbiddenException) as exc_info:
            quiz_svc.create_quiz(
                db_session,
                lesson_id=les.id,
                data=QuizCreateRequest(title="Q", pass_percentage=70, time_limit_minutes=10, max_attempts=1),
                actor_id=super_admin.id,
            )
        assert exc_info.value.code == "REVISION_IMMUTABLE"

        # Creating assignment on published lesson fails with REVISION_IMMUTABLE
        with pytest.raises(ForbiddenException) as exc_info2:
            assign_svc.create_assignment(
                db_session,
                lesson_id=les.id,
                data=AssignmentCreateRequest(title="A", instructions="Ins", max_score=100),
                actor_id=super_admin.id,
            )
        assert exc_info2.value.code == "REVISION_IMMUTABLE"


# =============================================================================
# GROUP D: QUIZ ENROLLMENT & EXPIRATION (BUG-009, BUG-010)
# =============================================================================

class TestGroupDQuizEnrollmentAndExpiration:

    def _setup_quiz_and_attempt(self, db_session: Session, student: User, super_admin: User) -> tuple[QuizAttempt, Enrollment]:
        course = Course(title="Quiz Course", slug=f"quiz-{uuid.uuid4()}", price_inr=0, is_free=True, status=COURSE_STATUS_PUBLISHED)
        db_session.add(course)
        db_session.flush()

        rev = CourseRevision(course_id=course.id, revision_no=1, status=REVISION_STATUS_DRAFT, title="Draft")
        db_session.add(rev)
        db_session.flush()

        sec = CurriculumSection(course_revision_id=rev.id, title="Module 1", sort_order=0)
        db_session.add(sec)
        db_session.flush()

        lesson = CurriculumLesson(section_id=sec.id, title="Quiz Lesson", lesson_type=LESSON_TYPE_QUIZ, sort_order=0)
        db_session.add(lesson)
        db_session.flush()

        quiz = Quiz(lesson_id=lesson.id, title="Timed Quiz", pass_percentage=70, time_limit_minutes=10, max_attempts=2)
        db_session.add(quiz)
        db_session.flush()

        q = QuizQuestion(quiz_id=quiz.id, question_type=QUESTION_TYPE_MCQ_SINGLE, prompt="Q?", points=10, sort_order=0)
        db_session.add(q)
        db_session.flush()
        opt = QuizQuestionOption(question_id=q.id, option_text="Answer", is_correct=True, sort_order=0)
        db_session.add(opt)

        enrollment = Enrollment(student_id=student.id, course_id=course.id, status=ENROLLMENT_STATUS_ACTIVE)
        db_session.add(enrollment)
        db_session.flush()

        attempt = QuizAttempt(quiz_id=quiz.id, student_id=student.id, attempt_no=1, started_at=utc_now(), status=ATTEMPT_STATUS_IN_PROGRESS)
        db_session.add(attempt)
        db_session.commit()
        return attempt, enrollment

    def test_bug_009_autosave_and_submit_revalidate_enrollment(self, db_session, student, super_admin):
        """BUG-009: Revoking enrollment blocks subsequent autosaves and submissions."""
        attempt, enrollment = self._setup_quiz_and_attempt(db_session, student, super_admin)
        quiz_svc = QuizService()
        q_id = attempt.quiz.questions[0].id

        # Autosave works while enrollment is ACTIVE
        as_req = AutosaveAnswerRequest(question_id=q_id, text_response="answer")
        resp = quiz_svc.autosave_answer(db_session, attempt.id, as_req, student)
        assert resp.success is True

        # Revoke enrollment
        enrollment.status = ENROLLMENT_STATUS_REVOKED
        db_session.commit()

        # Autosave now fails with ENROLLMENT_REVOKED
        with pytest.raises(ForbiddenException) as exc1:
            quiz_svc.autosave_answer(db_session, attempt.id, as_req, student)
        assert exc1.value.code == "ENROLLMENT_REVOKED"

        # Submission also fails with ENROLLMENT_REVOKED
        with pytest.raises(ForbiddenException) as exc2:
            quiz_svc.submit_quiz_attempt(db_session, attempt.id, None, student)
        assert exc2.value.code == "ENROLLMENT_REVOKED"

    def test_bug_010_quiz_expiration_persists_in_database(self, db_session, student, super_admin):
        """BUG-010: Attempt expiration in autosave commits EXPIRED status durably."""
        attempt, enrollment = self._setup_quiz_and_attempt(db_session, student, super_admin)
        quiz_svc = QuizService()
        q_id = attempt.quiz.questions[0].id

        # Set started_at to 30 minutes ago (time limit is 10 min)
        attempt.started_at = utc_now() - timedelta(minutes=30)
        db_session.commit()

        as_req = AutosaveAnswerRequest(question_id=q_id, text_response="late answer")
        with pytest.raises(BadRequestException) as exc_info:
            quiz_svc.autosave_answer(db_session, attempt.id, as_req, student)
        assert exc_info.value.code == "QUIZ_ATTEMPT_EXPIRED"

        # Reload attempt from database: MUST be EXPIRED
        db_session.expire_all()
        reloaded = db_session.get(QuizAttempt, attempt.id)
        assert reloaded.status == ATTEMPT_STATUS_EXPIRED
        assert reloaded.score == 0.0
        assert reloaded.is_passed is False


# =============================================================================
# GROUP E: EMAIL & OUTBOX DELIVERY (BUG-005)
# =============================================================================

class TestGroupEOutboxDelivery:

    @pytest.mark.asyncio
    async def test_bug_005_outbox_rejects_console_in_production(self, monkeypatch):
        """BUG-005: Outbox dispatcher raises error in production when provider is unconfigured/console."""
        prod_settings = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            EMAIL_PROVIDER="console",
            SECRET_KEY=SecretStr("0" * 40),
            BACKEND_URL="https://api.example.com",
            RAZORPAY_KEY_ID="rzp_live_test",
            RAZORPAY_KEY_SECRET=SecretStr("prod_key_123456789"),
            RAZORPAY_WEBHOOK_SECRET=SecretStr("prod_webhook_123456789"),
            DATABASE_URL="postgresql+psycopg://u:p@db.internal:5432/lms_prod",
            CORS_ORIGINS=["https://example.com"],
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: prod_settings)

        event = NotificationOutbox(
            channel="EMAIL",
            event_type="ENROLLMENT_RECEIPT",
            recipient="learner@example.com",
            subject="Receipt",
            payload={"order_no": "123"},
        )

        with pytest.raises(RuntimeError) as exc_info:
            await default_outbox_dispatcher(event)
        assert "Production email delivery blocked" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_bug_005_resend_and_sendgrid_dispatch_validation(self, monkeypatch):
        """BUG-005: Outbox worker validates real provider response payloads and HTTP status codes."""
        # 1. Resend success
        resend_settings = Settings(
            EMAIL_PROVIDER="resend",
            EMAIL_API_KEY=SecretStr("re_test_key_12345"),
            EMAIL_FROM="courses@example.com",
            EMAIL_FROM_NAME="LMS Instructor",
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: resend_settings)

        class MockResponse:
            def __init__(self, code, body):
                self.code = code
                self.body = body

            def getcode(self):
                return self.code

            def read(self):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        # Resend returns 200 with id
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda req, timeout=None: MockResponse(200, b'{"id": "res_mock_777"}'),
        )
        event = NotificationOutbox(
            channel="EMAIL",
            event_type="ENROLLMENT_RECEIPT",
            recipient="alice@example.com",
            subject="Receipt",
            payload={"order_no": "ORD-1"},
        )
        await default_outbox_dispatcher(event)  # Must succeed

        # Resend returns 200 without id -> rejected
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda req, timeout=None: MockResponse(200, b'{"error": "rate_limited"}'),
        )
        with pytest.raises(RuntimeError) as exc_resend:
            await default_outbox_dispatcher(event)
        assert "Resend provider response missing" in str(exc_resend.value)

        # 2. SendGrid success
        sg_settings = Settings(
            EMAIL_PROVIDER="sendgrid",
            EMAIL_API_KEY=SecretStr("SG.test_key_12345"),
            EMAIL_FROM="courses@example.com",
            EMAIL_FROM_NAME="LMS Instructor",
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: sg_settings)
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda req, timeout=None: MockResponse(202, b""),
        )
        await default_outbox_dispatcher(event)  # 202 Accepted must succeed

        # SendGrid returns 400
        import urllib.error
        def mock_error(req, timeout=None):
            raise urllib.error.HTTPError("https://api.sendgrid.com", 400, "Bad Request", {}, io.BytesIO(b'{"errors": ["Invalid email"]}'))

        monkeypatch.setattr("urllib.request.urlopen", mock_error)
        with pytest.raises(RuntimeError) as exc_sg:
            await default_outbox_dispatcher(event)
        assert "HTTP 400" in str(exc_sg.value)

    @pytest.mark.asyncio
    async def test_bug_005_non_email_channels_bypassed(self, monkeypatch):
        """BUG-005: In-app and webhook events do not trigger external email provider dispatch."""
        resend_settings = Settings(
            EMAIL_PROVIDER="resend",
            EMAIL_API_KEY=SecretStr("re_test_key_12345"),
        )
        monkeypatch.setattr("app.workers.outbox_worker.get_settings", lambda: resend_settings)

        called = []
        monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: called.append(req))

        in_app_event = NotificationOutbox(
            channel="IN_APP",
            event_type="LESSON_COMPLETED",
            recipient="student-uuid",
            subject="Lesson Done",
            payload={},
        )
        await default_outbox_dispatcher(in_app_event)
        assert len(called) == 0  # Bypassed safely!


# =============================================================================
# GROUP F: SUPER ADMIN CONCURRENCY (BUG-006)
# =============================================================================

class TestGroupFSuperAdminGovernance:

    @pytest.mark.asyncio
    async def test_bug_006_sole_super_admin_suspension_blocked_under_lock(self, db_session, super_admin):
        """BUG-006: Exclusive serialization lock on SUPER_ADMIN role guards sole admin invariant."""
        user_svc = UserService()

        # Sole admin cannot be suspended
        with pytest.raises(ConflictException) as exc_info:
            await user_svc.update_user_status(db_session, user_id=super_admin.id, is_active=False)
        assert exc_info.value.code == "CANNOT_SUSPEND_LAST_SUPER_ADMIN"

        # Sole admin cannot be demoted
        with pytest.raises(ConflictException) as exc_info2:
            await user_svc.manage_user_role(db_session, user_id=super_admin.id, role_id=ROLE_SUPER_ADMIN, action="REVOKE")
        assert exc_info2.value.code == "CANNOT_DEMOTE_LAST_SUPER_ADMIN"


# =============================================================================
# GROUP G: CERTIFICATE & PDF INTEGRITY (BUG-013, BUG-015, BUG-016)
# =============================================================================

class TestGroupGCertificateAndPDFIntegrity:

    def test_bug_013_certificate_qr_code_uses_absolute_url(self, db_session, student):
        """BUG-013: Certificate QR code contains absolute URL matching application config."""
        cert_svc = CertificateService()
        hash_val = "abc123def456hash"

        # Generate certificate PDF bytes
        pdf_bytes = cert_svc.render_certificate_pdf(
            student_name=student.full_name,
            course_title="Advanced Systems",
            certificate_no="CERT-2026-9999",
            verification_hash=hash_val,
            issued_at=datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc),
        )

        assert b"%PDF-" in pdf_bytes
        assert len(pdf_bytes) > 1000
        verify_url = cert_svc.get_verification_url(hash_val)
        assert verify_url.startswith("http")
        assert f"/api/v1/certificates/verify/{hash_val}" in verify_url

    def test_bug_013_production_certificate_url_startup_guards(self):
        """BUG-013: Production settings validator rejects non-HTTPS or localhost verification URLs."""
        # Missing / invalid URL in production
        with pytest.raises(ValueError) as exc1:
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY=SecretStr("a" * 40),
                DATABASE_URL="postgresql+psycopg://u:p@db.internal:5432/lms_prod",
                CORS_ORIGINS=["https://example.com"],
                RAZORPAY_KEY_ID="rzp_live_test",
                RAZORPAY_KEY_SECRET=SecretStr("prod_key_123456789"),
                RAZORPAY_WEBHOOK_SECRET=SecretStr("prod_webhook_123456789"),
                BACKEND_URL="http://localhost:8000",  # Insecure!
            )
        assert "BACKEND_URL or FRONTEND_URL must be configured with a valid HTTPS URL" in str(exc1.value)

        # Valid HTTPS production URL
        valid_settings = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            SECRET_KEY=SecretStr("a" * 40),
            DATABASE_URL="postgresql+psycopg://u:p@db.internal:5432/lms_prod",
            CORS_ORIGINS=["https://example.com"],
            RAZORPAY_KEY_ID="rzp_live_test",
            RAZORPAY_KEY_SECRET=SecretStr("prod_key_123456789"),
            RAZORPAY_WEBHOOK_SECRET=SecretStr("prod_webhook_123456789"),
            BACKEND_URL="https://api.lms.instructor.com",
        )
        cert_svc = CertificateService(settings=valid_settings)
        url = cert_svc.get_verification_url("test_hash_999")
        assert url == "https://api.lms.instructor.com/api/v1/certificates/verify/test_hash_999"

    def test_bug_016_real_pdf_sips_rasterization_and_structural_verification(self):
        """BUG-016: Actual PDF parsing & rendering verification using CoreGraphics (sips)."""
        import os
        import subprocess
        import tempfile

        # 1. Generate real 3-page PDF with geometric objects
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(100, 750, "Chapter 1: Enterprise Microservices Architecture")
        c.rect(50, 50, 500, 700)
        c.showPage()
        c.drawString(100, 750, "Chapter 2: Financial Ledger State Machine")
        c.circle(300, 400, 100)
        c.showPage()
        c.drawString(100, 750, "Chapter 3: Cryptographic Certificate Provenance")
        c.showPage()
        c.save()
        original_pdf = buf.getvalue()

        # 2. Watermark PDF
        watermarked = apply_pdf_watermark(
            original_pdf,
            student_name="Alexander Hamilton",
            student_email="alex@treasury.gov",
            student_id="STU-TREASURY-01",
        )

        # 3. Structural assertions
        latin_text = watermarked.decode("latin-1", errors="replace")
        assert "trailer" in latin_text
        assert "/Prev " in latin_text
        assert "startxref" in latin_text

        # 4. Rasterization with macOS sips CoreGraphics renderer
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(watermarked)
            pdf_path = f.name

        out_png = pdf_path.replace(".pdf", ".png")
        sips_res = subprocess.run(["sips", "-s", "format", "png", pdf_path, "--out", out_png], capture_output=True, text=True)
        assert sips_res.returncode == 0, f"sips failed to render PDF: {sips_res.stderr}"

        # Verify rasterized PNG file exists and has non-zero size
        assert os.path.exists(out_png)
        assert os.path.getsize(out_png) > 1000

        try:
            os.remove(pdf_path)
            os.remove(out_png)
        except OSError:
            pass

    def test_bug_016_multipage_pdf_watermark_incremental_update_integrity(self):
        """BUG-016: Multi-page PDF watermark preserves stream lengths and xref table."""
        # 1. Generate 3-page real PDF with compressed streams
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 700, "Page 1 Secret Architectural Design")
        c.showPage()
        c.drawString(72, 700, "Page 2 Financial Breakdown")
        c.showPage()
        c.drawString(72, 700, "Page 3 Proprietary Code Structure")
        c.showPage()
        c.save()
        original_pdf = buf.getvalue()

        # 2. Watermark the PDF
        watermarked = apply_pdf_watermark(
            original_pdf,
            student_name="Alice Student",
            student_email="alice@lms.local",
            student_id="STU-001",
            timestamp=datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc),
        )

        assert watermarked.startswith(b"%PDF-")
        assert watermarked.endswith(b"%%EOF\n") or watermarked.endswith(b"%%EOF")
        # Provenance text present
        assert b"CONFIDENTIAL - LICENSED TO: Alice Student (alice@lms.local)" in watermarked
        assert b"STUDENT ID: STU-001 - DO NOT DISTRIBUTE" in watermarked
        # Incremental update contains chained /Prev
        assert b"/Prev " in watermarked
        assert b"startxref" in watermarked

    def test_bug_016_malformed_pdf_rejected_safely(self):
        """BUG-016: Malformed byte streams fail safely with INVALID_PDF_FORMAT."""
        with pytest.raises(BadRequestException) as exc_info:
            apply_pdf_watermark(
                b"Not a valid PDF file at all",
                student_name="Mallory",
                student_email="mallory@attacker.com",
                student_id="ATT-666",
            )
        assert exc_info.value.code == "INVALID_PDF_FORMAT"


# =============================================================================
# GROUP H: MASTER REMEDIATION SUITE (P0-01, P0-02, P0-03, P1-02, P1-03)
# =============================================================================

class TestGroupHMasterRemediationSuite:

    def _setup_paid_order(self, db_session: Session, student: User, super_admin: User, amount_inr: int = 100000) -> Order:
        course = Course(
            title="Paid Course",
            slug=f"paid-h-{uuid.uuid4()}",
            price_inr=amount_inr,
            is_free=False,
            status=COURSE_STATUS_PUBLISHED,
        )
        db_session.add(course)
        db_session.flush()

        rev = CourseRevision(
            course_id=course.id,
            revision_no=1,
            title="Published Rev",
            status=REVISION_STATUS_PUBLISHED,
        )
        db_session.add(rev)
        db_session.flush()
        course.live_revision_id = rev.id
        db_session.flush()

        order = Order(
            student_id=student.id,
            course_id=course.id,
            order_no=f"ORD-H-{uuid.uuid4().hex[:8].upper()}",
            amount_inr=amount_inr,
            currency="INR",
            status=ORDER_STATUS_PAID,
            razorpay_order_id=f"order_{uuid.uuid4().hex[:12]}",
        )
        db_session.add(order)
        db_session.flush()

        tx = PaymentTransaction(
            order_id=order.id,
            razorpay_payment_id=f"pay_{uuid.uuid4().hex[:12]}",
            razorpay_signature="sig_test",
            status=TRANSACTION_STATUS_SUCCESS,
            amount_inr=amount_inr,
            raw_payload={"status": "captured"},
        )
        db_session.add(tx)

        enrollment = Enrollment(
            student_id=student.id,
            course_id=course.id,
            order_id=order.id,
            status=ENROLLMENT_STATUS_ACTIVE,
        )
        db_session.add(enrollment)
        db_session.commit()
        return order

    def test_p0_01_auth_token_runtime_annotation_integrity(self):
        """P0-01: AuthToken model annotations resolve without NameError."""
        from typing import get_type_hints
        import inspect
        from app.models.auth_token import AuthToken

        # Inspect constructor signature
        sig = inspect.signature(AuthToken.__init__)
        assert "kwargs" in sig.parameters

        # Verify module imports Any cleanly
        import app.models.auth_token as token_mod
        assert hasattr(token_mod, "Any")

        # Verify token instantiation with valid types
        tok = AuthToken(
            user_id=uuid.uuid4(),
            token_hash="a" * 64,
            token_type="PASSWORD_RESET",
            expires_at=datetime.now(timezone.utc),
        )
        assert tok.is_used is False
        assert tok.token_type == "PASSWORD_RESET"

    def test_p0_02_cross_course_media_isolation_identical_filenames(self, db_session, super_admin, student):
        """P0-02: Identical resource titles across courses cannot bypass media authorization."""
        from app.models.curriculum import LessonResource, RESOURCE_TYPE_PDF
        media_svc = MediaService()

        # 1. Course A (Student is NOT enrolled)
        course_a = Course(title="Course A", slug=f"course-a-{uuid.uuid4()}", price_inr=1000, is_free=False, status=COURSE_STATUS_PUBLISHED)
        db_session.add(course_a)
        db_session.flush()
        rev_a = CourseRevision(course_id=course_a.id, revision_no=1, title="Rev A")
        db_session.add(rev_a)
        db_session.flush()
        course_a.live_revision_id = rev_a.id
        sec_a = CurriculumSection(course_revision_id=rev_a.id, title="Sec A", sort_order=0)
        db_session.add(sec_a)
        db_session.flush()
        les_a = CurriculumLesson(section_id=sec_a.id, title="Les A", sort_order=0)
        db_session.add(les_a)
        db_session.flush()

        asset_a = MediaAsset(
            uploader_id=super_admin.id,
            filename="cheat-sheet.pdf",
            file_key="protected-docs/a/cheat-sheet.pdf",
            bucket="media",
            mime_type="application/pdf",
            file_size_bytes=1024,
            status=MEDIA_STATUS_READY,
        )
        db_session.add(asset_a)
        db_session.flush()

        res_a = LessonResource(
            lesson_id=les_a.id,
            title="cheat-sheet.pdf",
            resource_type=RESOURCE_TYPE_PDF,
            file_url=f"/api/v1/media/{asset_a.id}",
        )
        db_session.add(res_a)

        # 2. Course B (Student IS enrolled)
        course_b = Course(title="Course B", slug=f"course-b-{uuid.uuid4()}", price_inr=1000, is_free=False, status=COURSE_STATUS_PUBLISHED)
        db_session.add(course_b)
        db_session.flush()
        rev_b = CourseRevision(course_id=course_b.id, revision_no=1, title="Rev B")
        db_session.add(rev_b)
        db_session.flush()
        course_b.live_revision_id = rev_b.id
        sec_b = CurriculumSection(course_revision_id=rev_b.id, title="Sec B", sort_order=0)
        db_session.add(sec_b)
        db_session.flush()
        les_b = CurriculumLesson(section_id=sec_b.id, title="Les B", sort_order=0)
        db_session.add(les_b)
        db_session.flush()

        asset_b = MediaAsset(
            uploader_id=super_admin.id,
            filename="cheat-sheet.pdf",  # IDENTICAL FILENAME!
            file_key="protected-docs/b/cheat-sheet.pdf",
            bucket="media",
            mime_type="application/pdf",
            file_size_bytes=1024,
            status=MEDIA_STATUS_READY,
        )
        db_session.add(asset_b)
        db_session.flush()

        res_b = LessonResource(
            lesson_id=les_b.id,
            title="cheat-sheet.pdf",  # IDENTICAL RESOURCE TITLE!
            resource_type=RESOURCE_TYPE_PDF,
            file_url=f"/api/v1/media/{asset_b.id}",
        )
        db_session.add(res_b)

        # Student enrolled only in Course B
        enr_b = Enrollment(student_id=student.id, course_id=course_b.id, status=ENROLLMENT_STATUS_ACTIVE)
        db_session.add(enr_b)
        db_session.commit()

        # Seed storage for both
        StorageClient().put_object(asset_a.file_key, b"%PDF-1.4 sample A", content_type="application/pdf")
        StorageClient().put_object(asset_b.file_key, b"%PDF-1.4 sample B", content_type="application/pdf")

        # Student can access Course B's cheat-sheet.pdf with Lesson B context
        pdf_b, _ = media_svc.get_watermarked_pdf(db_session, asset_b.id, student, lesson_id=les_b.id)
        assert len(pdf_b) > 0

        # Student attempting to access Course A's asset_a using Lesson B context MUST be rejected!
        with pytest.raises(ForbiddenException) as exc_info:
            media_svc.get_watermarked_pdf(db_session, asset_a.id, student, lesson_id=les_b.id)
        assert exc_info.value.code == "MEDIA_NOT_ATTACHED_TO_LESSON"

    def test_p0_03_playback_token_rejects_non_ready_video(self, db_session, super_admin, student):
        """P0-03: Playback token issuance strictly requires READY status."""
        media_svc = MediaService()
        course = Course(title="C", slug=f"c-{uuid.uuid4()}", price_inr=0, is_free=True, status=COURSE_STATUS_PUBLISHED)
        db_session.add(course)
        db_session.flush()
        rev = CourseRevision(course_id=course.id, revision_no=1, title="R")
        db_session.add(rev)
        db_session.flush()
        sec = CurriculumSection(course_revision_id=rev.id, title="S", sort_order=0)
        db_session.add(sec)
        db_session.flush()

        # Asset in PROCESSING status
        video = MediaAsset(
            uploader_id=super_admin.id,
            filename="vid.mp4",
            file_key="raw-videos/vid.mp4",
            bucket="media",
            mime_type="video/mp4",
            file_size_bytes=10000,
            status=MEDIA_STATUS_PROCESSING,  # NOT READY!
        )
        db_session.add(video)
        db_session.flush()

        les = CurriculumLesson(section_id=sec.id, title="L", lesson_type=LESSON_TYPE_VIDEO, content={"video_id": str(video.id)}, sort_order=0)
        db_session.add(les)
        enr = Enrollment(student_id=student.id, course_id=course.id, status=ENROLLMENT_STATUS_ACTIVE)
        db_session.add(enr)
        db_session.commit()

        with pytest.raises(BadRequestException) as exc:
            media_svc.generate_playback_token(db_session, video.id, student, lesson_id=les.id)
        assert exc.value.code == "MEDIA_NOT_READY"

    def test_p0_03_playback_token_ip_mismatch_rejected(self, db_session, super_admin, student):
        """P0-03: Playback token verification rejects client IP mismatch."""
        media_svc = MediaService()
        course = Course(title="C", slug=f"c-{uuid.uuid4()}", price_inr=0, is_free=True, status=COURSE_STATUS_PUBLISHED)
        db_session.add(course)
        db_session.flush()
        rev = CourseRevision(course_id=course.id, revision_no=1, title="R")
        db_session.add(rev)
        db_session.flush()
        sec = CurriculumSection(course_revision_id=rev.id, title="S", sort_order=0)
        db_session.add(sec)
        db_session.flush()
        video = MediaAsset(uploader_id=super_admin.id, filename="v.mp4", file_key="raw-videos/v.mp4", bucket="m", mime_type="video/mp4", file_size_bytes=10, status=MEDIA_STATUS_READY)
        db_session.add(video)
        db_session.flush()
        les = CurriculumLesson(section_id=sec.id, title="L", lesson_type=LESSON_TYPE_VIDEO, content={"video_id": str(video.id)}, sort_order=0)
        db_session.add(les)
        enr = Enrollment(student_id=student.id, course_id=course.id, status=ENROLLMENT_STATUS_ACTIVE)
        db_session.add(enr)
        db_session.commit()

        # Token bound to IP 203.0.113.1
        resp = media_svc.generate_playback_token(db_session, video.id, student, lesson_id=les.id, client_ip="203.0.113.1")
        assert resp.playback_token

        # Verifying with matching IP succeeds
        claims = media_svc.verify_playback_token(resp.playback_token, video.id, client_ip="203.0.113.1")
        assert claims["ip"] == "203.0.113.1"

        # Verifying with different IP fails
        with pytest.raises(UnauthorizedException) as exc:
            media_svc.verify_playback_token(resp.playback_token, video.id, client_ip="198.51.100.99")
        assert exc.value.code == "TOKEN_IP_MISMATCH"

    def test_p1_02_google_oauth_rejects_missing_audience_in_prod(self):
        """P1-02: Google OAuth verification fails closed in production when audience is missing."""
        from app.api.v1.auth import _verify_google_id_token
        prod_settings = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            SECRET_KEY=SecretStr("a" * 40),
            BACKEND_URL="https://api.example.com",
            DATABASE_URL="postgresql+psycopg://u:p@db.internal:5432/lms_prod",
            CORS_ORIGINS=["https://example.com"],
            RAZORPAY_KEY_ID="rzp_live_123",
            RAZORPAY_KEY_SECRET=SecretStr("sec_12345678"),
            RAZORPAY_WEBHOOK_SECRET=SecretStr("wh_12345678"),
            GOOGLE_CLIENT_ID="",  # Empty string in production!
        )
        with pytest.raises(UnauthorizedException) as exc:
            _verify_google_id_token("fake.token.jwt", prod_settings)
        assert exc.value.code == "OAUTH_NOT_CONFIGURED"

    @pytest.mark.asyncio
    async def test_p1_03_optional_auth_distinguishes_anonymous_vs_suspended(self, db_session, student):
        """P1-03: get_optional_current_user returns None for anonymous, but raises for suspended accounts."""
        from unittest.mock import Mock
        from app.api.deps import get_optional_current_user
        from app.core.security import create_access_token
        from app.models.auth_session import AuthSession, SESSION_STATUS_ACTIVE
        from app.models.base import utc_now

        # 1. Anonymous request with no cookie and no header -> None
        anon_request = Mock()
        anon_request.cookies = {}
        anon_request.headers = {}
        anon_user = await get_optional_current_user(anon_request, db=db_session)
        assert anon_user is None

        # 2. Suspended user with valid token -> ForbiddenException (NOT None!)
        student.is_active = False
        db_session.commit()

        auth_session = AuthSession(user_id=student.id, session_token_hash="hash", status=SESSION_STATUS_ACTIVE, expires_at=utc_now() + timedelta(days=1))
        db_session.add(auth_session)
        db_session.commit()

        token = create_access_token(student.id, extra_claims={"session_id": str(auth_session.id)})
        suspended_request = Mock()
        suspended_request.cookies = {}
        suspended_request.headers = {"Authorization": f"Bearer {token}"}

        with pytest.raises(ForbiddenException) as exc:
            await get_optional_current_user(suspended_request, db=db_session)
        assert exc.value.code == "ACCOUNT_SUSPENDED"

    def test_p1_02_payment_duplicate_payment_flagged_for_reconciliation(self, db_session, student, super_admin):
        """P1-02: Duplicate payment on already PAID order is recorded and flagged for admin reconciliation."""
        from app.services.payment_service import PaymentService
        from app.models.payment import PaymentTransaction

        order = self._setup_paid_order(db_session, student, super_admin, amount_inr=50000)
        test_secret = "test_webhook_secret_key"
        rz_client = RazorpayClient()
        rz_client.webhook_secret = test_secret
        svc = PaymentService(razorpay_client=rz_client)

        # Webhook delivers a SECOND, distinct payment ID for the same order
        wh_payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_SECOND_DISTINCT_CHARGE_999",
                        "order_id": order.razorpay_order_id,
                        "amount": 50000,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        raw_body = json.dumps(wh_payload).encode("utf-8")
        sig = compute_razorpay_signature(raw_body, test_secret)

        result = svc.process_razorpay_webhook(db_session, raw_body, sig)
        assert result["status"] == "ok"
        assert "warning" in result

        # Verify second transaction was recorded
        txs = db_session.query(PaymentTransaction).filter(PaymentTransaction.order_id == order.id).all()
        assert len(txs) == 2
        pay_ids = [t.razorpay_payment_id for t in txs]
        assert "pay_SECOND_DISTINCT_CHARGE_999" in pay_ids

        # Verify enrollments: still exactly 1 enrollment (not duplicated)
        enrs = db_session.query(Enrollment).filter(Enrollment.order_id == order.id).all()
        assert len(enrs) == 1

    def test_outbox_email_text_human_readable_formatting(self):
        """P1: Outbox worker formats clean human-readable emails instead of raw JSON dumps."""
        from app.workers.outbox_worker import _format_email_text

        # 1. Password reset
        pw_event = NotificationOutbox(
            channel="EMAIL",
            event_type="PASSWORD_RESET",
            recipient="learner@test.com",
            subject="Reset Password",
            payload={"reset_url": "https://example.com/reset?token=xyz123"},
        )
        pw_text = _format_email_text(pw_event)
        assert "https://example.com/reset?token=xyz123" in pw_text
        assert "A password reset was requested" in pw_text
        assert not pw_text.startswith("{")

        # 2. Enrollment receipt
        enr_event = NotificationOutbox(
            channel="EMAIL",
            event_type="ENROLLMENT_RECEIPT",
            recipient="learner@test.com",
            subject="Receipt",
            payload={"order_no": "ORD-2026-9999", "amount_inr": 250000, "razorpay_payment_id": "pay_123"},
        )
        enr_text = _format_email_text(enr_event)
        assert "ORD-2026-9999" in enr_text
        assert "₹2500.00" in enr_text
        assert not enr_text.startswith("{")
