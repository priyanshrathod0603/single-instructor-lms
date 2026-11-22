"""Domain service for Promotional Offers Management (SA-05.1).

Architecture Specifications:
- SA-05 — Complete Commercial Governance (Section 3)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
"""

from datetime import datetime
import logging
from typing import Any, List, Optional
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestException, ResourceNotFoundException
from app.models.audit_log import AuditLog
from app.models.course import Course
from app.models.offer import (
    OFFER_STATUS_ACTIVE,
    OFFER_STATUS_ARCHIVED,
    OFFER_STATUS_INACTIVE,
    Offer,
)
from app.models.user import User
from app.repositories.offer_repo import OfferRepository
from app.schemas.offer import (
    OfferCourseSummary,
    OfferCreateRequest,
    OfferCreatorSummary,
    OfferListResponse,
    OfferResponse,
    OfferUpdateRequest,
)

logger = logging.getLogger(__name__)


class OfferService:
    """Domain service for Super Admin promotional offers governance."""

    def __init__(self, repo: Optional[OfferRepository] = None) -> None:
        self.repo = repo or OfferRepository()

    def _to_response(self, offer: Offer) -> OfferResponse:
        """Convert Offer model to Pydantic response."""
        course_summary = None
        if offer.course:
            course_summary = OfferCourseSummary(
                id=offer.course.id,
                title=offer.course.title,
                slug=offer.course.slug,
            )

        creator_summary = None
        if offer.creator:
            creator_summary = OfferCreatorSummary(
                id=offer.creator.id,
                email=offer.creator.email,
                full_name=offer.creator.full_name,
            )

        return OfferResponse(
            id=offer.id,
            name=offer.name,
            code=offer.code,
            description=offer.description,
            discount_type=offer.discount_type,
            discount_value=offer.discount_value,
            course_id=offer.course_id,
            course=course_summary,
            valid_from=offer.valid_from,
            valid_to=offer.valid_to,
            usage_limit=offer.usage_limit,
            times_used=offer.times_used,
            status=offer.status,
            created_by_id=offer.created_by_id,
            creator=creator_summary,
            created_at=offer.created_at,
            updated_at=offer.updated_at,
        )

    def list_offers(
        self,
        db: Session,
        *,
        search: Optional[str] = None,
        status: Optional[str] = None,
        discount_type: Optional[str] = None,
        course_id: Optional[uuid.UUID] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        per_page: int = 20,
    ) -> OfferListResponse:
        """List promotional offers with search, filter, and pagination."""
        items, total = self.repo.list_offers(
            db,
            search=search,
            status=status,
            discount_type=discount_type,
            course_id=course_id,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            per_page=per_page,
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return OfferListResponse(
            items=[self._to_response(o) for o in items],
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
        )

    def get_offer(self, db: Session, offer_id: uuid.UUID) -> OfferResponse:
        """Retrieve single promotional offer by primary key."""
        offer = self.repo.get_by_id(db, offer_id)
        if not offer:
            raise ResourceNotFoundException("Offer", str(offer_id))
        return self._to_response(offer)

    def create_offer(
        self,
        db: Session,
        current_user: User,
        data: OfferCreateRequest,
        *,
        ip_address: Optional[str] = None,
    ) -> OfferResponse:
        """Create a new promotional offer with business validations and audit logging."""
        # 1. Unique code check
        existing = self.repo.get_by_code(db, data.code)
        if existing:
            raise BadRequestException(f"Offer with code '{data.code}' already exists.")

        # 2. Check course reference if supplied
        if data.course_id:
            course = db.get(Course, data.course_id)
            if not course:
                raise BadRequestException(f"Target course ID {data.course_id} does not exist.")

        # 3. Create offer entity
        offer = self.repo.create_offer(
            db,
            name=data.name,
            code=data.code,
            description=data.description,
            discount_type=data.discount_type,
            discount_value=data.discount_value,
            course_id=data.course_id,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            usage_limit=data.usage_limit,
            status=data.status or OFFER_STATUS_ACTIVE,
            created_by_id=current_user.id,
        )

        # 4. Audit Log
        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action="OFFER_CREATED",
                resource_type="offer",
                resource_id=str(offer.id),
                before_state=None,
                after_state={
                    "name": offer.name,
                    "code": offer.code,
                    "discount_type": offer.discount_type,
                    "discount_value": offer.discount_value,
                    "course_id": str(offer.course_id) if offer.course_id else None,
                    "status": offer.status,
                },
                ip_address=ip_address,
            )
        )
        db.commit()
        db.refresh(offer)
        return self._to_response(offer)

    def update_offer(
        self,
        db: Session,
        current_user: User,
        offer_id: uuid.UUID,
        data: OfferUpdateRequest,
        *,
        ip_address: Optional[str] = None,
    ) -> OfferResponse:
        """Update fields on an existing promotional offer."""
        offer = self.repo.get_by_id(db, offer_id)
        if not offer:
            raise ResourceNotFoundException("Offer", str(offer_id))

        before_state = {
            "name": offer.name,
            "code": offer.code,
            "discount_type": offer.discount_type,
            "discount_value": offer.discount_value,
            "status": offer.status,
            "valid_from": offer.valid_from.isoformat(),
            "valid_to": offer.valid_to.isoformat(),
        }

        # Check course if updated
        if data.course_id is not None and data.course_id != offer.course_id:
            course = db.get(Course, data.course_id)
            if not course:
                raise BadRequestException(f"Target course ID {data.course_id} does not exist.")

        updates = data.model_dump(exclude_unset=True)
        offer = self.repo.update_offer(db, offer, updates)

        after_state = {
            "name": offer.name,
            "code": offer.code,
            "discount_type": offer.discount_type,
            "discount_value": offer.discount_value,
            "status": offer.status,
            "valid_from": offer.valid_from.isoformat(),
            "valid_to": offer.valid_to.isoformat(),
        }

        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action="OFFER_UPDATED",
                resource_type="offer",
                resource_id=str(offer.id),
                before_state=before_state,
                after_state=after_state,
                ip_address=ip_address,
            )
        )
        db.commit()
        db.refresh(offer)
        return self._to_response(offer)

    def change_status(
        self,
        db: Session,
        current_user: User,
        offer_id: uuid.UUID,
        new_status: str,
        *,
        ip_address: Optional[str] = None,
    ) -> OfferResponse:
        """Activate, deactivate, or archive an offer."""
        offer = self.repo.get_by_id(db, offer_id)
        if not offer:
            raise ResourceNotFoundException("Offer", str(offer_id))

        prev_status = offer.status
        offer = self.repo.update_offer(db, offer, {"status": new_status})

        action = (
            "OFFER_ACTIVATED"
            if new_status == OFFER_STATUS_ACTIVE
            else "OFFER_DEACTIVATED"
            if new_status == OFFER_STATUS_INACTIVE
            else "OFFER_ARCHIVED"
        )

        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action=action,
                resource_type="offer",
                resource_id=str(offer.id),
                before_state={"status": prev_status},
                after_state={"status": new_status},
                ip_address=ip_address,
            )
        )
        db.commit()
        db.refresh(offer)
        return self._to_response(offer)

    def delete_offer(
        self,
        db: Session,
        current_user: User,
        offer_id: uuid.UUID,
        *,
        ip_address: Optional[str] = None,
    ) -> None:
        """Permanently delete an offer record."""
        offer = self.repo.get_by_id(db, offer_id)
        if not offer:
            raise ResourceNotFoundException("Offer", str(offer_id))

        deleted_state = {
            "name": offer.name,
            "code": offer.code,
            "discount_type": offer.discount_type,
            "discount_value": offer.discount_value,
            "status": offer.status,
        }

        self.repo.delete_offer(db, offer)

        db.add(
            AuditLog(
                actor_id=current_user.id,
                actor_type=current_user.roles[0] if current_user.roles else "SUPER_ADMIN",
                action="OFFER_DELETED",
                resource_type="offer",
                resource_id=str(offer_id),
                before_state=deleted_state,
                after_state=None,
                ip_address=ip_address,
            )
        )
        db.commit()
