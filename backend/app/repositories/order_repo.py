"""Order, PaymentTransaction, and Refund repository operations.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 5, Tables 25-27)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK501, TASK502, TASK503, TASK504)
"""

from typing import Any, List, Optional, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.base import utc_now
from app.models.payment import (
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING,
    REFUND_STATUS_PROCESSED,
    TRANSACTION_STATUS_SUCCESS,
    Order,
    PaymentTransaction,
    Refund,
)


class OrderRepository:
    """Persistence operations for orders, transactions, and refunds."""

    def create_order(
        self,
        session: Session,
        order_no: str,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
        amount_inr: int,
        currency: str = "INR",
        razorpay_order_id: Optional[str] = None,
        status: str = ORDER_STATUS_PENDING,
    ) -> Order:
        """Create a new commercial order record."""
        order = Order(
            order_no=order_no,
            student_id=student_id,
            course_id=course_id,
            amount_inr=amount_inr,
            currency=currency,
            razorpay_order_id=razorpay_order_id,
            status=status,
        )
        session.add(order)
        session.flush()
        return order

    def get_by_id(
        self,
        session: Session,
        order_id: uuid.UUID,
        for_update: bool = False,
    ) -> Optional[Order]:
        """Fetch order by UUID with optional row-level pessimistic locking."""
        stmt = select(Order).where(Order.id == order_id)
        if for_update:
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalars().first()

    def get_by_order_no(
        self,
        session: Session,
        order_no: str,
        for_update: bool = False,
    ) -> Optional[Order]:
        """Fetch order by order_no with optional row-level locking."""
        stmt = select(Order).where(Order.order_no == order_no)
        if for_update:
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalars().first()

    def get_by_razorpay_order_id(
        self,
        session: Session,
        razorpay_order_id: str,
        for_update: bool = False,
    ) -> Optional[Order]:
        """Fetch order by Razorpay order ID with optional row-level locking."""
        stmt = select(Order).where(Order.razorpay_order_id == razorpay_order_id)
        if for_update:
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalars().first()

    def find_active_order_for_course(
        self,
        session: Session,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
        status: Optional[str] = None,
    ) -> Optional[Order]:
        """Finds student order for target course, optionally filtered by status."""
        stmt = select(Order).where(
            Order.student_id == student_id,
            Order.course_id == course_id,
        )
        if status:
            stmt = stmt.where(Order.status == status)
        stmt = stmt.order_by(desc(Order.created_at))
        return session.execute(stmt).scalars().first()

    def list_student_orders(
        self,
        session: Session,
        student_id: uuid.UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Order], int]:
        """Returns paginated orders for a student alongside total count."""
        base_query = select(Order).where(Order.student_id == student_id)
        count_query = select(func.count(Order.id)).where(Order.student_id == student_id)
        total = session.execute(count_query).scalar_one()

        stmt = base_query.order_by(desc(Order.created_at)).offset(skip).limit(limit)
        items = list(session.execute(stmt).scalars().all())
        return items, total

    def list_all_orders(
        self,
        session: Session,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Order], int]:
        """Returns paginated platform orders for administrators alongside total count."""
        base_query = select(Order)
        count_query = select(func.count(Order.id))

        if status:
            base_query = base_query.where(Order.status == status)
            count_query = count_query.where(Order.status == status)

        total = session.execute(count_query).scalar_one()
        stmt = base_query.order_by(desc(Order.created_at)).offset(skip).limit(limit)
        items = list(session.execute(stmt).scalars().all())
        return items, total

    def update_status(
        self,
        session: Session,
        order: Order,
        status: str,
    ) -> Order:
        """Transitions order status and records updated timestamp."""
        order.status = status
        order.updated_at = utc_now()
        session.flush()
        return order

    def create_transaction(
        self,
        session: Session,
        order_id: uuid.UUID,
        razorpay_payment_id: str,
        razorpay_signature: str,
        status: str,
        amount_inr: int,
        raw_payload: dict[str, Any],
        gateway: str = "RAZORPAY",
    ) -> PaymentTransaction:
        """Insert cryptographically verified payment transaction record."""
        tx = PaymentTransaction(
            order_id=order_id,
            gateway=gateway,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
            status=status,
            amount_inr=amount_inr,
            raw_payload=raw_payload,
        )
        session.add(tx)
        session.flush()
        return tx

    def get_transaction_by_payment_id(
        self,
        session: Session,
        razorpay_payment_id: str,
    ) -> Optional[PaymentTransaction]:
        """Find transaction by Razorpay payment ID for idempotency check."""
        stmt = select(PaymentTransaction).where(
            PaymentTransaction.razorpay_payment_id == razorpay_payment_id
        )
        return session.execute(stmt).scalars().first()

    def get_successful_transaction_for_order(
        self,
        session: Session,
        order_id: uuid.UUID,
    ) -> Optional[PaymentTransaction]:
        """Find the successful payment transaction record for an order."""
        stmt = select(PaymentTransaction).where(
            PaymentTransaction.order_id == order_id,
            PaymentTransaction.status == TRANSACTION_STATUS_SUCCESS,
        ).order_by(desc(PaymentTransaction.processed_at))
        return session.execute(stmt).scalars().first()

    def create_refund(
        self,
        session: Session,
        order_id: uuid.UUID,
        amount_inr: int,
        reason: str,
        approved_by: uuid.UUID,
        razorpay_refund_id: Optional[str] = None,
        status: str = REFUND_STATUS_PROCESSED,
    ) -> Refund:
        """Insert authorized refund record."""
        refund = Refund(
            order_id=order_id,
            amount_inr=amount_inr,
            reason=reason,
            approved_by=approved_by,
            razorpay_refund_id=razorpay_refund_id,
            status=status,
        )
        session.add(refund)
        session.flush()
        return refund

    def get_refunds_for_order(
        self,
        session: Session,
        order_id: uuid.UUID,
    ) -> List[Refund]:
        """Retrieve all refund records associated with an order."""
        stmt = select(Refund).where(Refund.order_id == order_id).order_by(desc(Refund.processed_at))
        return list(session.execute(stmt).scalars().all())

    def get_refund_by_razorpay_id(
        self,
        session: Session,
        razorpay_refund_id: str,
        for_update: bool = False,
    ) -> Optional[Refund]:
        """Retrieve refund record by its Razorpay gateway refund ID."""
        stmt = select(Refund).where(Refund.razorpay_refund_id == razorpay_refund_id)
        if for_update:
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalars().first()
