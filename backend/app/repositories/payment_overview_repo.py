"""Payment Overview repository for commercial transactions and financial metrics (SA-05.2).

Architecture Specifications:
- SA-05 — Complete Commercial Governance (Section 4)
- docs/backend/04-DATABASE-ARCHITECTURE.md
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md

Strict Invariants:
1. All currency calculations execute in integer minor units (paise). Zero floating point drift.
2. Metrics derive strictly from real database records (PaymentTransaction, Order, Refund).
3. If no records exist, zero counts/amounts are accurately returned.
"""

from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.course import Course
from app.models.payment import (
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REFUNDED,
    REFUND_STATUS_PROCESSED,
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_SUCCESS,
    Order,
    PaymentTransaction,
    Refund,
)
from app.models.user import User


class PaymentOverviewRepository:
    """Persistence operations for financial surveillance and payment transactions."""

    def get_financial_metrics(self, session: Session) -> dict[str, Any]:
        """Aggregate platform financial metrics strictly from database records."""
        # 1. Transactions counts
        total_tx = session.scalar(
            select(func.count(PaymentTransaction.id))
        ) or 0

        success_tx = session.scalar(
            select(func.count(PaymentTransaction.id)).where(
                PaymentTransaction.status == TRANSACTION_STATUS_SUCCESS
            )
        ) or 0

        failed_tx = session.scalar(
            select(func.count(PaymentTransaction.id)).where(
                PaymentTransaction.status == TRANSACTION_STATUS_FAILED
            )
        ) or 0

        # 2. Orders counts
        pending_orders = session.scalar(
            select(func.count(Order.id)).where(
                Order.status == ORDER_STATUS_PENDING
            )
        ) or 0

        refunded_orders = session.scalar(
            select(func.count(Order.id)).where(
                Order.status == ORDER_STATUS_REFUNDED
            )
        ) or 0

        # 3. Revenue sums in integer paise
        gross_collected = session.scalar(
            select(func.coalesce(func.sum(PaymentTransaction.amount_inr), 0)).where(
                PaymentTransaction.status == TRANSACTION_STATUS_SUCCESS
            )
        ) or 0

        total_refunded = session.scalar(
            select(func.coalesce(func.sum(Refund.amount_inr), 0)).where(
                Refund.status == REFUND_STATUS_PROCESSED
            )
        ) or 0

        net_collected = max(0, gross_collected - total_refunded)

        return {
            "total_transactions_count": total_tx,
            "successful_payments_count": success_tx,
            "failed_payments_count": failed_tx,
            "pending_orders_count": pending_orders,
            "refunded_orders_count": refunded_orders,
            "gross_revenue_paise": gross_collected,
            "successful_collected_paise": gross_collected,
            "refunded_amount_paise": total_refunded,
            "net_collected_paise": net_collected,
            "currency": "INR",
            "generated_at": datetime.now(timezone.utc),
        }

    def list_transactions(
        self,
        session: Session,
        search: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sort_by: str = "processed_at",
        sort_order: str = "desc",
        page: int = 1,
        per_page: int = 10,
    ) -> Tuple[List[PaymentTransaction], int]:
        """List transactions with student, course, order, and refund relations."""
        query = (
            select(PaymentTransaction)
            .join(PaymentTransaction.order)
            .join(Order.student)
            .join(Order.course)
            .options(
                joinedload(PaymentTransaction.order).joinedload(Order.student),
                joinedload(PaymentTransaction.order).joinedload(Order.course),
                joinedload(PaymentTransaction.order).selectinload(Order.refunds),
            )
        )

        base_count_query = (
            select(PaymentTransaction.id)
            .join(PaymentTransaction.order)
            .join(Order.student)
            .join(Order.course)
        )

        # Filters
        if search:
            s_clean = f"%{search.strip()}%"
            search_cond = or_(
                PaymentTransaction.razorpay_payment_id.ilike(s_clean),
                Order.order_no.ilike(s_clean),
                User.email.ilike(s_clean),
                User.full_name.ilike(s_clean),
                Course.title.ilike(s_clean),
            )
            query = query.where(search_cond)
            base_count_query = base_count_query.where(search_cond)

        if status and status != "ALL":
            query = query.where(PaymentTransaction.status == status)
            base_count_query = base_count_query.where(PaymentTransaction.status == status)

        if start_date:
            query = query.where(PaymentTransaction.processed_at >= start_date)
            base_count_query = base_count_query.where(PaymentTransaction.processed_at >= start_date)

        if end_date:
            query = query.where(PaymentTransaction.processed_at <= end_date)
            base_count_query = base_count_query.where(PaymentTransaction.processed_at <= end_date)

        # Total count
        total = session.scalar(
            select(func.count()).select_from(base_count_query.subquery())
        ) or 0

        # Sort
        sort_col = getattr(PaymentTransaction, sort_by, PaymentTransaction.processed_at)
        if sort_order.lower() == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        # Pagination
        offset = max(0, (page - 1) * per_page)
        query = query.offset(offset).limit(per_page)

        items = list(session.execute(query).scalars().unique().all())
        return items, total

    def get_transaction_by_id(
        self, session: Session, transaction_id: uuid.UUID
    ) -> Optional[PaymentTransaction]:
        """Fetch transaction with full order, student, course, and refund relations."""
        stmt = (
            select(PaymentTransaction)
            .where(PaymentTransaction.id == transaction_id)
            .options(
                joinedload(PaymentTransaction.order).joinedload(Order.student),
                joinedload(PaymentTransaction.order).joinedload(Order.course),
                joinedload(PaymentTransaction.order).selectinload(Order.refunds),
            )
        )
        return session.execute(stmt).scalars().first()
