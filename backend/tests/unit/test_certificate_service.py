"""Unit tests for CertificateService cryptographic generation, verification, and revocation.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 31)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Section 3)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901, TASK903, TASK904)
"""

from datetime import datetime, timezone
from decimal import Decimal
import io
import uuid

import pytest
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.exceptions import BadRequestException, ForbiddenException, ResourceNotFoundException
from app.core.storage import StorageClient
from app.models import Base
from app.models.certificate import Certificate
from app.models.course import Course, CourseRevision
from app.models.curriculum import CurriculumLesson, CurriculumSection
from app.models.enrollment import ENROLLMENT_STATUS_ACTIVE, ENROLLMENT_STATUS_REVOKED, Enrollment
from app.models.notification import Notification, NotificationOutbox
from app.models.progress import CourseProgressSummary, LessonProgress
from app.models.user import ROLE_STUDENT, ROLE_SUPER_ADMIN, User
from app.repositories.certificate_repo import CertificateRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.progress_repo import ProgressRepository
from app.services.audit_service import AuditService
from app.services.certificate_service import CertificateService


@pytest.fixture
def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def storage_client():
    """StorageClient with isolated in-memory storage."""
    return StorageClient(get_settings())


@pytest.fixture
def certificate_service(storage_client):
    """CertificateService instance wired with mock storage."""
    return CertificateService(
        certificate_repo=CertificateRepository(),
        progress_repo=ProgressRepository(),
        enrollment_repo=EnrollmentRepository(),
        audit_service=AuditService(),
        storage_client=storage_client,
        settings=get_settings(),
    )


def _seed_completed_student_and_course(session: Session):
    """Helper seeding an actively enrolled student with 100% course completion."""
    student = User(
        email=f"cert_student_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="mock_hash",
        full_name="Evelyn Student",
        is_verified=True,
    )
    admin = User(
        email=f"admin_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="mock_hash",
        full_name="Super Admin",
        is_verified=True,
    )
    course = Course(
        title="Distributed Systems at Scale",
        slug=f"dist-sys-{uuid.uuid4().hex[:6]}",
        price_inr=999900,
    )
    session.add_all([student, admin, course])
    session.flush()

    enrollment = Enrollment(
        student_id=student.id,
        course_id=course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        granted_at=datetime.now(timezone.utc),
    )
    summary = CourseProgressSummary(
        student_id=student.id,
        course_id=course.id,
        completed_lessons_count=5,
        total_lessons_count=5,
        progress_percentage=Decimal("100.00"),
    )
    session.add_all([enrollment, summary])
    session.flush()
    return student, admin, course, summary


class TestCertificateService:
    """Tests for CertificateService generation, verification, and revocation."""

    def test_compute_verification_hash_integrity(self, certificate_service: CertificateService):
        """Verification hash must be deterministic and tamper-sensitive."""
        student_id = uuid.uuid4()
        course_id = uuid.uuid4()
        cert_no = "CERT-202611-9842"
        now = datetime.now(timezone.utc)

        hash1 = certificate_service.compute_verification_hash(student_id, course_id, cert_no, now)
        hash2 = certificate_service.compute_verification_hash(student_id, course_id, cert_no, now)
        assert hash1 == hash2
        assert len(hash1) == 64

        # Altering any field must alter the hash
        hash_altered = certificate_service.compute_verification_hash(student_id, course_id, "CERT-202611-0000", now)
        assert hash1 != hash_altered

    def test_render_certificate_pdf_valid(self, certificate_service: CertificateService):
        """PDF rendering must produce valid PDF bytes containing the PDF magic header."""
        pdf_bytes = certificate_service.render_certificate_pdf(
            student_name="Jane Doe",
            course_title="Advanced FastAPI Architecture",
            certificate_no="CERT-202611-1234",
            verification_hash="a" * 64,
            issued_at=datetime.now(timezone.utc),
        )
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF")
        assert len(pdf_bytes) > 1000

    def test_issue_certificate_if_eligible_creates_records(
        self,
        db_session: Session,
        certificate_service: CertificateService,
        storage_client: StorageClient,
    ):
        """100% completion must issue certificate, upload PDF, insert outbox and in-app notifications, and audit log."""
        student, _, course, _ = _seed_completed_student_and_course(db_session)

        cert = certificate_service.issue_certificate_if_eligible(db_session, student, course)
        assert cert is not None
        assert cert.certificate_no.startswith("CERT-")
        assert cert.student_id == student.id
        assert cert.course_id == course.id
        assert cert.verification_hash is not None
        assert cert.is_revoked is False
        assert storage_client.object_exists(cert.pdf_url)

        # Verify outbox event created
        outbox_event = db_session.query(NotificationOutbox).filter_by(recipient=student.email).first()
        assert outbox_event is not None
        assert outbox_event.channel == "EMAIL"
        assert "Certificate Issued" in outbox_event.subject
        assert outbox_event.payload["certificate_no"] == cert.certificate_no

        # Verify in-app notification created
        notif = db_session.query(Notification).filter_by(user_id=student.id).first()
        assert notif is not None
        assert notif.notification_type == "CERTIFICATE_ISSUED"

    def test_issue_certificate_idempotent_duplicate_prevention(
        self,
        db_session: Session,
        certificate_service: CertificateService,
    ):
        """Multiple calls to issue_certificate_if_eligible must return existing certificate without reissuing."""
        student, _, course, _ = _seed_completed_student_and_course(db_session)

        cert1 = certificate_service.issue_certificate_if_eligible(db_session, student, course)
        cert2 = certificate_service.issue_certificate_if_eligible(db_session, student, course)

        assert cert1.id == cert2.id
        assert cert1.certificate_no == cert2.certificate_no
        assert cert1.verification_hash == cert2.verification_hash
        assert db_session.query(Certificate).count() == 1

    def test_issue_certificate_denied_if_progress_below_100(
        self,
        db_session: Session,
        certificate_service: CertificateService,
    ):
        """Certificates cannot be issued if progress is below 100%."""
        student, _, course, summary = _seed_completed_student_and_course(db_session)
        summary.progress_percentage = Decimal("80.00")
        summary.completed_lessons_count = 4
        db_session.flush()

        cert = certificate_service.issue_certificate_if_eligible(db_session, student, course)
        assert cert is None
        assert db_session.query(Certificate).count() == 0

    def test_issue_certificate_denied_if_enrollment_revoked(
        self,
        db_session: Session,
        certificate_service: CertificateService,
    ):
        """Certificates cannot be issued if course enrollment is revoked."""
        student, _, course, _ = _seed_completed_student_and_course(db_session)
        enrollment = db_session.query(Enrollment).filter_by(student_id=student.id, course_id=course.id).first()
        enrollment.status = ENROLLMENT_STATUS_REVOKED
        db_session.flush()

        cert = certificate_service.issue_certificate_if_eligible(db_session, student, course)
        assert cert is None
        assert db_session.query(Certificate).count() == 0

    def test_verify_certificate_public_valid(
        self,
        db_session: Session,
        certificate_service: CertificateService,
    ):
        """Public verification returns valid response with student and course metadata."""
        student, _, course, _ = _seed_completed_student_and_course(db_session)
        cert = certificate_service.issue_certificate_if_eligible(db_session, student, course)

        verify_res = certificate_service.verify_certificate_public(db_session, cert.verification_hash)
        assert verify_res.verified is True
        assert verify_res.status == "VALID"
        assert verify_res.certificate_no == cert.certificate_no
        assert verify_res.student_name == student.full_name
        assert verify_res.course_title == course.title

    def test_verify_certificate_public_nonexistent(
        self,
        db_session: Session,
        certificate_service: CertificateService,
    ):
        """Public verification for unknown hash returns verified=False, status=INVALID."""
        verify_res = certificate_service.verify_certificate_public(db_session, "nonexistent_hash_12345")
        assert verify_res.verified is False
        assert verify_res.status == "INVALID"

    def test_verify_certificate_public_revoked(
        self,
        db_session: Session,
        certificate_service: CertificateService,
    ):
        """Public verification for revoked certificate reports verified=False and status=REVOKED."""
        student, admin, course, _ = _seed_completed_student_and_course(db_session)
        cert = certificate_service.issue_certificate_if_eligible(db_session, student, course)

        certificate_service.revoke_certificate(
            session=db_session,
            certificate_id=cert.id,
            reason="Violation of academic integrity policy",
            actor=admin,
        )

        verify_res = certificate_service.verify_certificate_public(db_session, cert.verification_hash)
        assert verify_res.verified is False
        assert verify_res.status == "REVOKED"
        assert verify_res.revoked_reason == "Violation of academic integrity policy"
        assert verify_res.revoked_at is not None

    def test_revoke_certificate_records_audit_log(
        self,
        db_session: Session,
        certificate_service: CertificateService,
    ):
        """Revoking a certificate marks is_revoked=True and writes immutable audit log."""
        student, admin, course, _ = _seed_completed_student_and_course(db_session)
        cert = certificate_service.issue_certificate_if_eligible(db_session, student, course)

        revoked_cert = certificate_service.revoke_certificate(
            session=db_session,
            certificate_id=cert.id,
            reason="Fraudulent payment chargeback",
            actor=admin,
        )
        assert revoked_cert.is_revoked is True
        assert revoked_cert.revoked_reason == "Fraudulent payment chargeback"
        assert revoked_cert.revoked_at is not None
