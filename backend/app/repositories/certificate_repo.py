"""Certificate repository for certificate issuance, verification, and revocation.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 31)
- docs/backend/14-STUDENT-PROGRESS-ARCHITECTURE.md (Section 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK901, TASK903, TASK904)
"""

from datetime import datetime, timezone
from typing import Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.certificate import Certificate


class CertificateRepository:
    """Repository handling certificate lifecycle and public verification lookups."""

    def get_by_student_and_course(
        self,
        session: Session,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> Optional[Certificate]:
        """Fetch certificate for a student in a specific course."""
        stmt = (
            select(Certificate)
            .options(joinedload(Certificate.student), joinedload(Certificate.course))
            .where(
                Certificate.student_id == student_id,
                Certificate.course_id == course_id,
            )
        )
        return session.execute(stmt).scalars().first()

    def get_by_verification_hash(
        self,
        session: Session,
        verification_hash: str,
    ) -> Optional[Certificate]:
        """Fetch certificate by public verification hash with student and course joined."""
        stmt = (
            select(Certificate)
            .options(joinedload(Certificate.student), joinedload(Certificate.course))
            .where(Certificate.verification_hash == verification_hash)
        )
        return session.execute(stmt).scalars().first()

    def get_by_certificate_no(
        self,
        session: Session,
        certificate_no: str,
    ) -> Optional[Certificate]:
        """Fetch certificate by human-readable certificate number."""
        stmt = select(Certificate).where(Certificate.certificate_no == certificate_no)
        return session.execute(stmt).scalars().first()

    def get_by_id(
        self,
        session: Session,
        certificate_id: uuid.UUID,
    ) -> Optional[Certificate]:
        """Fetch certificate by primary key."""
        stmt = (
            select(Certificate)
            .options(joinedload(Certificate.student), joinedload(Certificate.course))
            .where(Certificate.id == certificate_id)
        )
        return session.execute(stmt).scalars().first()

    def create_certificate(
        self,
        session: Session,
        certificate_no: str,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
        verification_hash: str,
        pdf_url: str,
        issued_at: Optional[datetime] = None,
    ) -> Certificate:
        """Create and persist a new immutable certificate."""
        now = issued_at or datetime.now(timezone.utc)
        cert = Certificate(
            certificate_no=certificate_no,
            student_id=student_id,
            course_id=course_id,
            verification_hash=verification_hash,
            pdf_url=pdf_url,
            issued_at=now,
            is_revoked=False,
        )
        session.add(cert)
        session.flush()
        return cert

    def revoke_certificate(
        self,
        session: Session,
        certificate_id: uuid.UUID,
        reason: str,
    ) -> Optional[Certificate]:
        """Mark certificate as revoked with mandatory justification."""
        cert = self.get_by_id(session, certificate_id)
        if cert:
            cert.is_revoked = True
            cert.revoked_at = datetime.now(timezone.utc)
            cert.revoked_reason = reason
            session.flush()
        return cert
