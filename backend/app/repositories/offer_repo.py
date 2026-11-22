"""Offer repository for database persistence operations (SA-05.1).

Architecture Specifications:
- SA-05 — Complete Commercial Governance (Section 3)
- docs/backend/04-DATABASE-ARCHITECTURE.md
"""

from typing import Any, List, Optional, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.base import utc_now
from app.models.offer import (
    OFFER_STATUS_ACTIVE,
    OFFER_STATUS_ARCHIVED,
    OFFER_STATUS_INACTIVE,
    Offer,
)


class OfferRepository:
    """Persistence operations for promotional offers."""

    def list_offers(
        self,
        session: Session,
        search: Optional[str] = None,
        status: Optional[str] = None,
        discount_type: Optional[str] = None,
        course_id: Optional[uuid.UUID] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        per_page: int = 10,
    ) -> Tuple[List[Offer], int]:
        """List offers with filtering, search, sorting, and pagination."""
        query = select(Offer).options(
            joinedload(Offer.course),
            joinedload(Offer.creator),
        )
        base_count_query = select(Offer.id)

        # Filters
        if search:
            search_clean = f"%{search.strip()}%"
            search_filter = or_(
                Offer.name.ilike(search_clean),
                Offer.code.ilike(search_clean),
                Offer.description.ilike(search_clean),
            )
            query = query.where(search_filter)
            base_count_query = base_count_query.where(search_filter)

        if status and status != "ALL":
            query = query.where(Offer.status == status)
            base_count_query = base_count_query.where(Offer.status == status)

        if discount_type and discount_type != "ALL":
            query = query.where(Offer.discount_type == discount_type)
            base_count_query = base_count_query.where(Offer.discount_type == discount_type)

        if course_id:
            query = query.where(Offer.course_id == course_id)
            base_count_query = base_count_query.where(Offer.course_id == course_id)

        # Count total
        count_stmt = select(func.count()).select_from(base_count_query.subquery())
        total = session.scalar(count_stmt) or 0

        # Sorting
        sort_col = getattr(Offer, sort_by, Offer.created_at)
        if sort_order.lower() == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        # Pagination
        offset = max(0, (page - 1) * per_page)
        query = query.offset(offset).limit(per_page)

        items = list(session.execute(query).scalars().unique().all())
        return items, total

    def get_by_id(self, session: Session, offer_id: uuid.UUID) -> Optional[Offer]:
        """Fetch offer by primary key."""
        stmt = (
            select(Offer)
            .where(Offer.id == offer_id)
            .options(joinedload(Offer.course), joinedload(Offer.creator))
        )
        return session.execute(stmt).scalars().first()

    def get_by_code(self, session: Session, code: str) -> Optional[Offer]:
        """Fetch offer by unique promo code."""
        stmt = select(Offer).where(Offer.code == code.strip().upper())
        return session.execute(stmt).scalars().first()

    def create_offer(
        self,
        session: Session,
        name: str,
        code: str,
        discount_type: str,
        discount_value: int,
        valid_from: Any,
        valid_to: Any,
        created_by_id: uuid.UUID,
        description: Optional[str] = None,
        course_id: Optional[uuid.UUID] = None,
        usage_limit: Optional[int] = None,
        status: str = OFFER_STATUS_ACTIVE,
    ) -> Offer:
        """Insert a new promotional offer."""
        offer = Offer(
            name=name,
            code=code.strip().upper(),
            description=description,
            discount_type=discount_type,
            discount_value=discount_value,
            course_id=course_id,
            valid_from=valid_from,
            valid_to=valid_to,
            usage_limit=usage_limit,
            status=status,
            created_by_id=created_by_id,
        )
        session.add(offer)
        session.flush()
        return offer

    def update_offer(
        self,
        session: Session,
        offer: Offer,
        updates: dict[str, Any],
    ) -> Offer:
        """Update fields on an existing offer."""
        for field, value in updates.items():
            if hasattr(offer, field) and value is not None:
                if field == "code":
                    setattr(offer, field, str(value).strip().upper())
                else:
                    setattr(offer, field, value)
        offer.updated_at = utc_now()
        session.flush()
        return offer

    def delete_offer(self, session: Session, offer: Offer) -> None:
        """Permanently delete an offer."""
        session.delete(offer)
        session.flush()
