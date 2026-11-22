"""CertificateService orchestrating cryptographic certificate generation, public QR verification, and revocation.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 31)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.9)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Section 3)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md (CERTIFICATE_ISSUED)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901, TASK903, TASK904)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)

Strict Invariants:
1. Automated Issuance: Triggered strictly upon verified 100% course completion and active enrollment.
2. Cryptographic Integrity: Verification hash is an HMAC-SHA256 signature generated with server SECRET_KEY.
3. PDF Delivery: Generates verifiable PDF with embedded QR code pointing to public verification endpoint.
4. Idempotency: Duplicate calls for an already issued certificate return the existing record without duplicate generation.
5. Revocation Safeguard: Revoked certificates return unverified/revoked status upon public QR verification.
"""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import io
import logging
from typing import Any, Optional
import uuid

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    ResourceNotFoundException,
)
from app.core.storage import StorageClient
from app.models.certificate import Certificate
from app.models.course import Course
from app.models.enrollment import ENROLLMENT_STATUS_ACTIVE
from app.models.notification import Notification, NotificationOutbox
from app.models.user import User
from app.repositories.certificate_repo import CertificateRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.progress_repo import ProgressRepository
from app.schemas.certificate import CertificateResponse, CertificateVerifyResponse
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class CertificateService:
    """Service managing certificate generation, storage, public verification, and administrative revocation."""

    def __init__(
        self,
        certificate_repo: Optional[CertificateRepository] = None,
        progress_repo: Optional[ProgressRepository] = None,
        enrollment_repo: Optional[EnrollmentRepository] = None,
        audit_service: Optional[AuditService] = None,
        storage_client: Optional[StorageClient] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.certificate_repo = certificate_repo or CertificateRepository()
        self.progress_repo = progress_repo or ProgressRepository()
        self.enrollment_repo = enrollment_repo or EnrollmentRepository()
        self.audit_service = audit_service or AuditService()
        self.storage_client = storage_client or StorageClient()
        self.settings = settings or get_settings()

    def _get_signing_key(self) -> bytes:
        """Derive cryptographic key for HMAC-SHA256 certificate hashing."""
        secret = (
            self.settings.SECRET_KEY.get_secret_value()
            if hasattr(self.settings.SECRET_KEY, "get_secret_value")
            else str(self.settings.SECRET_KEY)
        )
        return secret.encode("utf-8")

    def compute_verification_hash(
        self,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
        certificate_no: str,
        issued_at: datetime,
    ) -> str:
        """Compute tamper-proof HMAC-SHA256 signature hash for certificate metadata.
        
        Formula: HMAC-SHA256(SECRET_KEY, student_id || course_id || certificate_no || formatted_utc_timestamp)
        """
        # Ensure standard ISO timestamp without sub-second dialect discrepancies
        dt = issued_at if issued_at.tzinfo is not None else issued_at.replace(tzinfo=timezone.utc)
        dt_str = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = f"{student_id}:{course_id}:{certificate_no}:{dt_str}".encode("utf-8")
        return hmac.new(self._get_signing_key(), payload, hashlib.sha256).hexdigest()

    def generate_certificate_no(self, issued_at: datetime) -> str:
        """Generate human-readable certificate number e.g. CERT-202611-9842."""
        period = issued_at.strftime("%Y%m")
        suffix = uuid.uuid4().hex[:6].upper()
        return f"CERT-{period}-{suffix}"

    def get_verification_url(self, verification_hash: str) -> str:
        """Construct absolute verification URL according to system configuration (BUG-013)."""
        base_url = (self.settings.BACKEND_URL or self.settings.FRONTEND_URL or "").rstrip("/")
        if self.settings.is_production:
            if not base_url or not base_url.startswith("https://") or "localhost" in base_url or "127.0.0.1" in base_url:
                raise ValueError("Valid HTTPS public URL required in production for certificate verification.")
        elif not base_url:
            base_url = "http://localhost:8000"
        return f"{base_url}/api/v1/certificates/verify/{verification_hash}"

    def render_certificate_pdf(
        self,
        student_name: str,
        course_title: str,
        certificate_no: str,
        verification_hash: str,
        issued_at: datetime,
    ) -> bytes:
        """Render high-fidelity landscape PDF certificate with embedded QR code using ReportLab."""
        buffer = io.BytesIO()
        width, height = landscape(A4)
        c = canvas.Canvas(buffer, pagesize=landscape(A4))

        # Background and decorative borders
        c.setStrokeColor(colors.HexColor("#1E3A8A"))  # Dark Blue
        c.setLineWidth(6)
        c.rect(20, 20, width - 40, height - 40)

        c.setStrokeColor(colors.HexColor("#D97706"))  # Amber / Gold accent
        c.setLineWidth(2)
        c.rect(28, 28, width - 56, height - 56)

        # Title / Header
        c.setFont("Helvetica-Bold", 32)
        c.setFillColor(colors.HexColor("#1E3A8A"))
        c.drawCentredString(width / 2.0, height - 90, "CERTIFICATE OF COMPLETION")

        c.setFont("Helvetica", 14)
        c.setFillColor(colors.HexColor("#4B5563"))
        c.drawCentredString(width / 2.0, height - 125, "This is proudly presented to")

        # Student Name
        c.setFont("Helvetica-Bold", 26)
        c.setFillColor(colors.HexColor("#111827"))
        c.drawCentredString(width / 2.0, height - 175, student_name)

        # Body text
        c.setFont("Helvetica", 13)
        c.setFillColor(colors.HexColor("#4B5563"))
        c.drawCentredString(
            width / 2.0,
            height - 220,
            "for successfully completing all curriculum requirements and pedagogical assessments for",
        )

        # Course Title
        c.setFont("Helvetica-Bold", 20)
        c.setFillColor(colors.HexColor("#1E3A8A"))
        c.drawCentredString(width / 2.0, height - 265, course_title)

        # Metadata
        formatted_date = issued_at.strftime("%B %d, %Y")
        c.setFont("Helvetica", 11)
        c.setFillColor(colors.HexColor("#374151"))
        c.drawString(60, 90, f"Issued Date: {formatted_date}")
        c.drawString(60, 70, f"Certificate ID: {certificate_no}")

        # Embedded QR Code for public instant verification (BUG-013: Absolute public verification URL)
        verify_url = self.get_verification_url(verification_hash)
        qr = QrCodeWidget(verify_url)
        qr_bounds = qr.getBounds()
        qr_w = qr_bounds[2] - qr_bounds[0]
        qr_h = qr_bounds[3] - qr_bounds[1]

        # Desired QR size on canvas: 80x80 pt
        qr_size = 80.0
        d = Drawing(qr_size, qr_size, transform=[qr_size / qr_w, 0, 0, qr_size / qr_h, 0, 0])
        d.add(qr)
        d.drawOn(c, width - 150, 55)

        c.setFont("Helvetica-Oblique", 9)
        c.setFillColor(colors.HexColor("#6B7280"))
        c.drawCentredString(width - 110, 42, "Scan to verify authenticity")

        c.showPage()
        c.save()
        return buffer.getvalue()

    def issue_certificate_if_eligible(
        self,
        session: Session,
        student: User,
        course: Course,
    ) -> Optional[Certificate]:
        """Automatically evaluate 100% completion and issue cryptographic certificate.
        
        Idempotent: Returns existing certificate if already issued.
        """
        # 1. Check if certificate already exists
        existing_cert = self.certificate_repo.get_by_student_and_course(session, student.id, course.id)
        if existing_cert:
            return existing_cert

        # 2. Verify active course enrollment
        enrollment = self.enrollment_repo.get_by_student_and_course(session, student.id, course.id)
        if not enrollment or not enrollment.is_access_valid:
            logger.warning(
                "Certificate issuance denied: student %s not actively enrolled in course %s",
                student.id,
                course.id,
            )
            return None

        # 3. Verify course completion summary is 100%
        summary = self.progress_repo.get_course_progress_summary(session, student.id, course.id)
        if not summary or summary.progress_percentage < Decimal("100.00") or summary.total_lessons_count == 0:
            logger.warning(
                "Certificate issuance denied: student %s progress is %s%% (required 100.00%%)",
                student.id,
                summary.progress_percentage if summary else 0,
            )
            return None

        # 4. Generate certificate number and verification hash
        issued_at = datetime.now(timezone.utc)
        certificate_no = self.generate_certificate_no(issued_at)
        while self.certificate_repo.get_by_certificate_no(session, certificate_no) is not None:
            certificate_no = self.generate_certificate_no(issued_at)

        verification_hash = self.compute_verification_hash(
            student_id=student.id,
            course_id=course.id,
            certificate_no=certificate_no,
            issued_at=issued_at,
        )

        # 5. Render verifiable PDF and upload to storage
        pdf_bytes = self.render_certificate_pdf(
            student_name=student.full_name,
            course_title=course.title,
            certificate_no=certificate_no,
            verification_hash=verification_hash,
            issued_at=issued_at,
        )
        file_key = f"certificates/{certificate_no}.pdf"
        self.storage_client.put_object(file_key, pdf_bytes, content_type="application/pdf")
        pdf_url = file_key

        # 6. Persist Certificate record
        cert = self.certificate_repo.create_certificate(
            session=session,
            certificate_no=certificate_no,
            student_id=student.id,
            course_id=course.id,
            verification_hash=verification_hash,
            pdf_url=pdf_url,
            issued_at=issued_at,
        )

        # 7. Enqueue Transactional Outbox Notification & In-App Notification
        verify_path = f"/api/v1/certificates/verify/{verification_hash}"
        outbox_event = NotificationOutbox(
            event_type="certificate.issued",
            channel="EMAIL",
            recipient=student.email,
            subject=f"Congratulations! Certificate Issued for {course.title}",
            payload={
                "student_name": student.full_name,
                "course_title": course.title,
                "certificate_no": certificate_no,
                "verification_hash": verification_hash,
                "verify_url": verify_path,
                "pdf_url": pdf_url,
            },
            dedupe_key=f"cert_issued:{cert.id}",
            status="PENDING",
        )
        session.add(outbox_event)

        in_app_notification = Notification(
            user_id=student.id,
            title=f"Certificate Issued: {course.title}",
            message=f"You earned your certificate for {course.title} (No: {certificate_no}).",
            notification_type="CERTIFICATE_ISSUED",
            data={
                "certificate_id": str(cert.id),
                "certificate_no": certificate_no,
                "verification_hash": verification_hash,
                "course_id": str(course.id),
            },
        )
        session.add(in_app_notification)

        # 8. Record Immutable Audit Log
        self.audit_service.record_sync_event(
            session=session,
            action="CERTIFICATE_ISSUED",
            resource_type="certificate",
            resource_id=cert.id,
            actor_id=student.id,
            actor_type="USER",
            after_state={
                "certificate_no": cert.certificate_no,
                "student_id": str(cert.student_id),
                "course_id": str(cert.course_id),
                "verification_hash": cert.verification_hash,
                "issued_at": cert.issued_at.isoformat(),
            },
        )

        logger.info(
            "Certificate %s successfully issued for student %s in course %s",
            cert.certificate_no,
            student.id,
            course.id,
        )
        return cert

    def get_certificate_for_course(
        self,
        session: Session,
        student: User,
        course_id: uuid.UUID,
    ) -> CertificateResponse:
        """Retrieve certificate for an enrolled course, issuing it if 100% completed."""
        # Check active enrollment
        enrollment = self.enrollment_repo.get_by_student_and_course(session, student.id, course_id)
        if not enrollment or not enrollment.is_access_valid:
            raise ForbiddenException(
                message="Active course enrollment required to view or issue certificate",
                code="ENROLLMENT_REQUIRED",
            )

        cert = self.certificate_repo.get_by_student_and_course(session, student.id, course_id)
        if not cert:
            # Check if course is eligible for issuance
            course = session.get(Course, course_id)
            if not course:
                raise ResourceNotFoundException(
                    message="Course not found",
                    code="COURSE_NOT_FOUND",
                )
            cert = self.issue_certificate_if_eligible(session, student, course)
            if not cert:
                summary = self.progress_repo.get_course_progress_summary(session, student.id, course_id)
                pct = summary.progress_percentage if summary else 0
                raise BadRequestException(
                    message=f"Course completion criteria not satisfied (Current progress: {pct}%). 100% completion required for certificate.",
                    code="CERTIFICATE_NOT_ELIGIBLE",
                )

        return CertificateResponse(
            id=cert.id,
            certificate_no=cert.certificate_no,
            student_id=cert.student_id,
            course_id=cert.course_id,
            issued_at=cert.issued_at,
            verification_hash=cert.verification_hash,
            pdf_url=cert.pdf_url,
            is_revoked=cert.is_revoked,
            student_name=cert.student.full_name if cert.student else None,
            course_title=cert.course.title if cert.course else None,
            verify_url=f"/api/v1/certificates/verify/{cert.verification_hash}",
        )

    def verify_certificate_public(
        self,
        session: Session,
        verification_hash: str,
    ) -> CertificateVerifyResponse:
        """Public verification endpoint resolving certificate authenticity without student authentication."""
        cert = self.certificate_repo.get_by_verification_hash(session, verification_hash)
        if not cert:
            return CertificateVerifyResponse(
                verified=False,
                status="INVALID",
            )

        # Handle revoked status
        if cert.is_revoked:
            return CertificateVerifyResponse(
                verified=False,
                status="REVOKED",
                certificate_no=cert.certificate_no,
                student_name=cert.student.full_name if cert.student else "Student",
                course_title=cert.course.title if cert.course else "Course",
                issued_at=cert.issued_at,
                verification_hash=cert.verification_hash,
                revoked_at=cert.revoked_at,
                revoked_reason=cert.revoked_reason,
            )

        # Validate cryptographic HMAC signature
        expected_hash = self.compute_verification_hash(
            student_id=cert.student_id,
            course_id=cert.course_id,
            certificate_no=cert.certificate_no,
            issued_at=cert.issued_at,
        )
        if not hmac.compare_digest(expected_hash, cert.verification_hash):
            return CertificateVerifyResponse(
                verified=False,
                status="INVALID_SIGNATURE",
                certificate_no=cert.certificate_no,
            )

        return CertificateVerifyResponse(
            verified=True,
            status="VALID",
            certificate_no=cert.certificate_no,
            student_name=cert.student.full_name if cert.student else "Student",
            course_title=cert.course.title if cert.course else "Course",
            issued_at=cert.issued_at,
            verification_hash=cert.verification_hash,
            pdf_url=cert.pdf_url,
        )

    def revoke_certificate(
        self,
        session: Session,
        certificate_id: uuid.UUID,
        reason: str,
        actor: User,
    ) -> Certificate:
        """Administratively revoke an issued certificate with mandatory justification."""
        cert = self.certificate_repo.get_by_id(session, certificate_id)
        if not cert:
            raise ResourceNotFoundException(
                message="Certificate not found",
                code="CERTIFICATE_NOT_FOUND",
            )

        before_state = {
            "is_revoked": cert.is_revoked,
            "revoked_at": cert.revoked_at.isoformat() if cert.revoked_at else None,
            "revoked_reason": cert.revoked_reason,
        }

        updated_cert = self.certificate_repo.revoke_certificate(session, certificate_id, reason)

        self.audit_service.record_sync_event(
            session=session,
            action="CERTIFICATE_REVOKED",
            resource_type="certificate",
            resource_id=cert.id,
            actor_id=actor.id,
            actor_type="USER",
            before_state=before_state,
            after_state={
                "is_revoked": True,
                "revoked_at": updated_cert.revoked_at.isoformat() if updated_cert.revoked_at else None,
                "revoked_reason": reason,
            },
        )
        return updated_cert
