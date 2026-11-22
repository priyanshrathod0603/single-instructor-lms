"""Domain service for Payment Overview and Financial Surveillance (SA-05.2).

Architecture Specifications:
- SA-05 — Complete Commercial Governance (Section 4)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md

Strict Invariants:
1. Strict integer paise minor currency calculations.
2. Metrics calculated from real database records (PaymentTransaction, Order, Refund).
3. Zero floating point drift.
"""

from datetime import datetime
import logging
from typing import Any, List, Optional
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundException
from app.models.payment import PaymentTransaction
from app.repositories.payment_overview_repo import PaymentOverviewRepository
from app.schemas.payment_overview import (
    PaymentMetricsResponse,
    TransactionCourseSummary,
    TransactionItemResponse,
    TransactionListResponse,
    TransactionOrderSummary,
    TransactionRefundSummary,
    TransactionStudentSummary,
)

logger = logging.getLogger(__name__)


class PaymentOverviewService:
    """Domain service for Super Admin financial overview and transactions surveillance."""

    def __init__(self, repo: Optional[PaymentOverviewRepository] = None) -> None:
        self.repo = repo or PaymentOverviewRepository()

    def _to_transaction_item(self, tx: PaymentTransaction) -> TransactionItemResponse:
        """Convert PaymentTransaction entity to TransactionItemResponse."""
        order_summary = None
        student_summary = None
        course_summary = None
        refunds_summary = []

        if tx.order:
            order_summary = TransactionOrderSummary(
                id=tx.order.id,
                order_no=tx.order.order_no,
                status=tx.order.status,
                amount_inr=tx.order.amount_inr,
                currency=tx.order.currency,
            )
            if tx.order.student:
                student_summary = TransactionStudentSummary(
                    id=tx.order.student.id,
                    email=tx.order.student.email,
                    full_name=tx.order.student.full_name,
                )
            if tx.order.course:
                course_summary = TransactionCourseSummary(
                    id=tx.order.course.id,
                    title=tx.order.course.title,
                    slug=tx.order.course.slug,
                )
            if tx.order.refunds:
                refunds_summary = [
                    TransactionRefundSummary(
                        id=r.id,
                        amount_inr=r.amount_inr,
                        reason=r.reason,
                        status=r.status,
                        razorpay_refund_id=r.razorpay_refund_id,
                        processed_at=r.processed_at,
                    )
                    for r in tx.order.refunds
                ]

        return TransactionItemResponse(
            id=tx.id,
            gateway=tx.gateway,
            razorpay_payment_id=tx.razorpay_payment_id,
            status=tx.status,
            amount_inr=tx.amount_inr,
            currency="INR",
            processed_at=tx.processed_at,
            order=order_summary,
            student=student_summary,
            course=course_summary,
            refunds=refunds_summary,
        )

    def get_financial_metrics(self, db: Session) -> PaymentMetricsResponse:
        """Calculate commercial financial metrics strictly from database records."""
        data = self.repo.get_financial_metrics(db)
        return PaymentMetricsResponse(**data)

    def list_transactions(
        self,
        db: Session,
        *,
        search: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sort_by: str = "processed_at",
        sort_order: str = "desc",
        page: int = 1,
        per_page: int = 20,
    ) -> TransactionListResponse:
        """List transactions with search, filter, and pagination."""
        items, total = self.repo.list_transactions(
            db,
            search=search,
            status=status,
            start_date=start_date,
            end_date=end_date,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            per_page=per_page,
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return TransactionListResponse(
            items=[self._to_transaction_item(tx) for tx in items],
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
        )

    def get_transaction(
        self, db: Session, transaction_id: uuid.UUID
    ) -> TransactionItemResponse:
        """Fetch single transaction detail."""
        tx = self.repo.get_transaction_by_id(db, transaction_id)
        if not tx:
            raise ResourceNotFoundException("PaymentTransaction", str(transaction_id))
        return self._to_transaction_item(tx)
