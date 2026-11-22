"""Certificate REST API endpoints for issuance, public QR verification, and revocation.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 31)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.9)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Section 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901, TASK903, TASK904)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_db,
    require_permissions,
)
from app.core.exceptions import ResourceNotFoundException
from app.core.permissions import ENROLLMENT_REVOKE
from app.core.storage import StorageClient
from app.models.user import User
from app.schemas.certificate import (
    CertificateResponse,
    CertificateRevokeRequest,
    CertificateVerifyResponse,
)
from app.services.certificate_service import CertificateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/certificates", tags=["Certificates"])


def get_certificate_service() -> CertificateService:
    """Dependency providing CertificateService instance."""
    return CertificateService()


@router.get(
    "/verify/{verification_hash}",
    response_model=CertificateVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Public endpoint for QR code certificate verification",
)
def verify_certificate_endpoint(
    verification_hash: str,
    db: Session = Depends(get_db),
    service: CertificateService = Depends(get_certificate_service),
) -> CertificateVerifyResponse:
    """Public verification endpoint resolving certificate authenticity without student authentication."""
    return service.verify_certificate_public(
        session=db,
        verification_hash=verification_hash,
    )


@router.get(
    "/{course_id}",
    response_model=CertificateResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve or generate certificate for finished course",
)
def get_or_issue_course_certificate_endpoint(
    course_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: CertificateService = Depends(get_certificate_service),
) -> CertificateResponse:
    """Retrieve existing certificate or trigger automated issuance if 100% course requirements completed."""
    return service.get_certificate_for_course(
        session=db,
        student=current_user,
        course_id=course_id,
    )


@router.get(
    "/{course_id}/download",
    summary="Download verifiable certificate PDF",
)
def download_certificate_pdf_endpoint(
    course_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: CertificateService = Depends(get_certificate_service),
) -> Response:
    """Download the high-fidelity verifiable PDF certificate with embedded QR code."""
    cert_response = service.get_certificate_for_course(
        session=db,
        student=current_user,
        course_id=course_id,
    )
    storage_client = service.storage_client
    pdf_bytes = storage_client.get_object(cert_response.pdf_url)

    filename = f"{cert_response.certificate_no}.pdf"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "application/pdf",
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@router.post(
    "/{certificate_id}/revoke",
    response_model=CertificateResponse,
    status_code=status.HTTP_200_OK,
    summary="Administratively revoke an issued certificate",
)
def revoke_certificate_endpoint(
    certificate_id: uuid.UUID,
    payload: CertificateRevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ENROLLMENT_REVOKE)),
    service: CertificateService = Depends(get_certificate_service),
) -> CertificateResponse:
    """Revoke an issued certificate with mandatory justification recorded in immutable audit logs."""
    cert = service.revoke_certificate(
        session=db,
        certificate_id=certificate_id,
        reason=payload.reason,
        actor=current_user,
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
