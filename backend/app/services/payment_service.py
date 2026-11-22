"""Payment, Order lifecycle, Webhook reconciliation, and Refund domain service.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 5, Tables 25-27)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.7)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK501, TASK502, TASK503, TASK504)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004, ADR-005, ADR-008, ADR-012, ADR-013)

Strict Invariants:
1. Zero Trust on Browser Redirect: Paid status is updated exclusively upon verified webhook.
2. Minor Currency Math: All values calculated in integer paise.
3. Cryptographic Webhook Security: HMAC-SHA256 signature verification.
4. Idempotent Processing: Row locks + unique transaction constraint prevents double fulfillment.
5. Mandatory Email Verification: Unverified students cannot create checkout orders (ADR-008).
"""

from datetime import datetime, timezone
import json
import logging
import socket
from typing import Any, List, Optional, Tuple
import urllib.error
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import ORDERS_VIEW_ALL
from app.core.razorpay import RazorpayClient
from app.models.course import COURSE_STATUS_PUBLISHED, Course
from app.models.enrollment import ENROLLMENT_STATUS_ACTIVE, Enrollment
from app.models.notification import NotificationOutbox
from app.models.payment import (
    ORDER_STATUS_FAILED,
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
from app.models.user import User
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.notification_repo import NotificationOutboxRepository
from app.repositories.order_repo import OrderRepository
from app.schemas.order import (
    OrderCheckoutResponse,
    OrderListResponse,
    OrderResponse,
    RefundResponse,
)
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class PaymentService:
    """Orchestrator for checkout orders, Razorpay gateway integration, webhooks, and refunds."""

    def __init__(
        self,
        order_repo: Optional[OrderRepository] = None,
        enrollment_repo: Optional[EnrollmentRepository] = None,
        audit_service: Optional[AuditService] = None,
        outbox_repo: Optional[NotificationOutboxRepository] = None,
        razorpay_client: Optional[RazorpayClient] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.order_repo = order_repo or OrderRepository()
        self.enrollment_repo = enrollment_repo or EnrollmentRepository()
        self.audit_service = audit_service or AuditService()
        self.outbox_repo = outbox_repo or NotificationOutboxRepository()
        self.razorpay_client = razorpay_client or RazorpayClient()
        self.settings = settings or get_settings()

    def _log_audit(
        self,
        session: Session,
        action: str,
        resource_id: str,
        actor_id: Optional[uuid.UUID] = None,
        actor_type: str = "SYSTEM",
        before_state: Optional[dict[str, Any]] = None,
        after_state: Optional[dict[str, Any]] = None,
        request_context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Internal helper to invoke audit service synchronously."""
        if isinstance(request_context, tuple) and len(request_context) == 3:
            req_id, ip, ua = request_context
        elif isinstance(request_context, dict):
            req_id = request_context.get("request_id")
            ip = request_context.get("ip_address")
            ua = request_context.get("user_agent")
        else:
            req_id, ip, ua = None, None, None

        self.audit_service.record_sync_event(
            session=session,
            action=action,
            resource_type="order",
            resource_id=resource_id,
            actor_id=actor_id,
            actor_type=actor_type,
            before_state=before_state,
            after_state=after_state,
            request_id=req_id,
            ip_address=ip,
            user_agent=ua,
        )

    def _emit_outbox_event(
        self,
        session: Session,
        event_type: str,
        recipient_email: str,
        subject: str,
        payload: dict[str, Any],
        dedupe_key: Optional[str] = None,
    ) -> NotificationOutbox:
        """Internal helper to insert an outbox event synchronously."""
        event = NotificationOutbox(
            event_type=event_type,
            channel="EMAIL",
            recipient=recipient_email,
            subject=subject,
            payload=payload,
            dedupe_key=dedupe_key,
        )
        session.add(event)
        session.flush()
        return event

    def create_order(
        self,
        session: Session,
        student: User,
        course_id: uuid.UUID,
        request_context: Optional[dict[str, Any]] = None,
    ) -> OrderCheckoutResponse:
        """Initiates a commercial order and creates a Razorpay gateway order.

        Args:
            session: Active database transaction.
            student: Authenticated student user.
            course_id: UUID of published course to purchase.
            request_context: Audit context containing IP, User-Agent, Request ID.

        Returns:
            OrderCheckoutResponse containing internal order ID, Razorpay order ID, and key.
        """
        # 1. Verify student account state
        if not student.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "ACCOUNT_SUSPENDED", "message": "Suspended user accounts cannot initiate checkout"},
            )

        # 2. Mandatory email verification guard (ADR-008)
        if not student.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "EMAIL_NOT_VERIFIED",
                    "message": "Email verification is required before initiating course checkout",
                },
            )

        # 3. Verify course exists and is published
        course = session.get(Course, course_id)
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "COURSE_NOT_FOUND", "message": "Target course not found"},
            )

        if course.status != COURSE_STATUS_PUBLISHED or not course.live_revision_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "COURSE_NOT_PUBLISHED",
                    "message": "Cannot purchase an unpublished or archived course",
                },
            )

        # 4. Check for existing active enrollment or paid order
        has_enrollment = self.enrollment_repo.has_active_enrollment(
            session=session,
            student_id=student.id,
            course_id=course.id,
        )
        existing_paid = self.order_repo.find_active_order_for_course(
            session=session,
            student_id=student.id,
            course_id=course.id,
            status=ORDER_STATUS_PAID,
        )
        if has_enrollment or existing_paid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "ALREADY_ENROLLED",
                    "message": "Student is already enrolled in this course",
                },
            )

        # 5. Check if recent pending order exists to prevent redundant duplicate order creation
        pending_order = self.order_repo.find_active_order_for_course(
            session=session,
            student_id=student.id,
            course_id=course.id,
            status=ORDER_STATUS_PENDING,
        )
        if pending_order and pending_order.razorpay_order_id:
            return OrderCheckoutResponse(
                order_id=pending_order.id,
                order_no=pending_order.order_no,
                amount_inr=pending_order.amount_inr,
                currency=pending_order.currency,
                razorpay_order_id=pending_order.razorpay_order_id,
                razorpay_key_id=self.razorpay_client.key_id,
                course_title=course.title,
            )

        # 6. Server-side price calculation (minor currency units)
        price_inr = course.price_inr
        if price_inr <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_COURSE_PRICE", "message": "Course price must be greater than zero for gateway checkout"},
            )

        # 7. Generate human-readable unique order number
        now_utc = datetime.now(timezone.utc)
        order_no = f"ORD-{now_utc.strftime('%Y%m')}-{uuid.uuid4().hex[:8].upper()}"

        # 8. Create Razorpay order
        rzp_order = self.razorpay_client.create_order(
            amount_inr=price_inr,
            currency="INR",
            receipt=order_no,
            notes={
                "student_id": str(student.id),
                "course_id": str(course.id),
                "order_no": order_no,
            },
        )

        # 9. Persist internal order
        order = self.order_repo.create_order(
            session=session,
            order_no=order_no,
            student_id=student.id,
            course_id=course.id,
            amount_inr=price_inr,
            currency="INR",
            razorpay_order_id=rzp_order["id"],
            status=ORDER_STATUS_PENDING,
        )

        # 10. Financial audit log
        self._log_audit(
            session=session,
            action="ORDER_CREATED",
            resource_id=str(order.id),
            actor_id=student.id,
            actor_type="USER",
            after_state={
                "order_no": order.order_no,
                "student_id": str(student.id),
                "course_id": str(course.id),
                "amount_inr": order.amount_inr,
                "status": order.status,
            },
            request_context=request_context,
        )

        return OrderCheckoutResponse(
            order_id=order.id,
            order_no=order.order_no,
            amount_inr=order.amount_inr,
            currency=order.currency,
            razorpay_order_id=order.razorpay_order_id,
            razorpay_key_id=self.razorpay_client.key_id,
            course_title=course.title,
        )

    def process_razorpay_webhook(
        self,
        session: Session,
        raw_body: bytes,
        signature_header: str,
        request_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Ingests and cryptographically verifies an incoming Razorpay webhook.

        Args:
            session: Active database session.
            raw_body: Exact unmodified byte payload from request body.
            signature_header: X-Razorpay-Signature header value.
            request_context: Audit request context.

        Returns:
            Status dictionary response.
        """
        # 1. Cryptographic HMAC-SHA256 signature verification
        if not signature_header:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "MISSING_SIGNATURE", "message": "Missing X-Razorpay-Signature header"},
            )

        if not self.razorpay_client.verify_webhook_signature(raw_body, signature_header):
            logger.warning("Razorpay webhook signature verification failed.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_SIGNATURE", "message": "Cryptographic webhook signature verification failed"},
            )

        # 2. Parse JSON payload
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "MALFORMED_WEBHOOK_PAYLOAD", "message": f"Invalid JSON payload: {exc}"},
            ) from exc

        event = payload.get("event")
        logger.info("Processing verified Razorpay webhook event: %s", event)

        # 3. Handle successful payment capture events
        if event in ("payment.captured", "order.paid"):
            payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
            rzp_order_id = payment_entity.get("order_id")
            rzp_payment_id = payment_entity.get("id")
            amount = payment_entity.get("amount")

            if not rzp_order_id or not rzp_payment_id:
                return {"status": "ignored", "reason": "missing_payment_identifiers"}

            # Pessimistic row locking on target order
            order = self.order_repo.get_by_razorpay_order_id(session, rzp_order_id, for_update=True)
            if not order:
                logger.warning("Webhook received for unknown Razorpay order: %s", rzp_order_id)
                return {"status": "ignored", "reason": "order_not_found"}

            # Idempotency check: unique payment transaction guard
            existing_tx = self.order_repo.get_transaction_by_payment_id(session, rzp_payment_id)
            if existing_tx:
                logger.info("Duplicate webhook delivery detected for payment %s; returning 200 OK", rzp_payment_id)
                return {"status": "ok", "message": "Payment already processed (idempotent)"}

            # Currency validation (P1-02)
            currency = payment_entity.get("currency", "INR")
            if currency and currency.upper() != "INR":
                logger.error("Payment currency mismatch! Expected INR, got %s", currency)
                self.order_repo.create_transaction(
                    session=session,
                    order_id=order.id,
                    razorpay_payment_id=rzp_payment_id,
                    razorpay_signature=signature_header,
                    status=TRANSACTION_STATUS_FAILED,
                    amount_inr=amount,
                    raw_payload=payload,
                )
                self._log_audit(
                    session=session,
                    action="PAYMENT_CURRENCY_MISMATCH",
                    resource_id=str(order.id),
                    actor_id=None,
                    actor_type="SYSTEM",
                    before_state={"status": order.status},
                    after_state={
                        "status": TRANSACTION_STATUS_FAILED,
                        "currency": currency,
                        "payment_id": rzp_payment_id,
                    },
                    request_context=request_context,
                )
                session.commit()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "CURRENCY_MISMATCH", "message": f"Expected INR currency, received '{currency}'"},
                )

            # If order already marked PAID, record additional charge and flag for reconciliation (P1-02)
            if order.status == ORDER_STATUS_PAID:
                logger.warning("Order %s already marked PAID; additional distinct payment %s received", order.order_no, rzp_payment_id)
                self.order_repo.create_transaction(
                    session=session,
                    order_id=order.id,
                    razorpay_payment_id=rzp_payment_id,
                    razorpay_signature=signature_header,
                    status=TRANSACTION_STATUS_SUCCESS,
                    amount_inr=amount,
                    raw_payload=payload,
                )
                self._log_audit(
                    session=session,
                    action="DUPLICATE_PAYMENT_CAPTURED",
                    resource_id=str(order.id),
                    actor_id=None,
                    actor_type="SYSTEM",
                    before_state={"status": ORDER_STATUS_PAID},
                    after_state={
                        "order_no": order.order_no,
                        "amount_inr": amount,
                        "duplicate_payment_id": rzp_payment_id,
                        "flag": "REQUIRES_ADMINISTRATIVE_RECONCILIATION",
                    },
                    request_context=request_context,
                )
                return {
                    "status": "ok",
                    "order_id": str(order.id),
                    "payment_id": rzp_payment_id,
                    "warning": "Duplicate payment captured on paid order; flagged for admin reconciliation",
                }
            else:
                # Validate amount matches internal order
                if amount != order.amount_inr:
                    logger.error("Payment amount mismatch! Expected %d, got %d", order.amount_inr, amount)
                    self.order_repo.create_transaction(
                        session=session,
                        order_id=order.id,
                        razorpay_payment_id=rzp_payment_id,
                        razorpay_signature=signature_header,
                        status=TRANSACTION_STATUS_FAILED,
                        amount_inr=amount,
                        raw_payload=payload,
                    )
                    self._log_audit(
                        session=session,
                        action="PAYMENT_AMOUNT_MISMATCH",
                        resource_id=str(order.id),
                        actor_id=None,
                        actor_type="SYSTEM",
                        before_state={"status": order.status},
                        after_state={
                            "status": TRANSACTION_STATUS_FAILED,
                            "expected_amount": order.amount_inr,
                            "received_amount": amount,
                            "payment_id": rzp_payment_id,
                        },
                        request_context=request_context,
                    )
                    session.commit()
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"code": "AMOUNT_MISMATCH", "message": "Payment amount does not match order total"},
                    )

                # Transition order to PAID
                self.order_repo.update_status(session, order, ORDER_STATUS_PAID)

            # Record verified payment transaction
            self.order_repo.create_transaction(
                session=session,
                order_id=order.id,
                razorpay_payment_id=rzp_payment_id,
                razorpay_signature=signature_header,
                status=TRANSACTION_STATUS_SUCCESS,
                amount_inr=amount,
                raw_payload=payload,
            )

            # Provision student course enrollment (Zero Trust on Browser Redirect - ADR-004)
            enrollment = self.enrollment_repo.create_or_activate_enrollment(
                session=session,
                student_id=order.student_id,
                course_id=order.course_id,
                order_id=order.id,
            )

            # Transactional Outbox: enrollment receipt notification
            student_email = order.student.email if order.student else ""
            self._emit_outbox_event(
                session=session,
                event_type="ENROLLMENT_RECEIPT",
                recipient_email=student_email,
                subject=f"Receipt for Order {order.order_no}",
                payload={
                    "order_no": order.order_no,
                    "amount_inr": order.amount_inr,
                    "course_id": str(order.course_id),
                    "enrollment_id": str(enrollment.id),
                    "razorpay_payment_id": rzp_payment_id,
                },
                dedupe_key=f"receipt_{order.id}_{rzp_payment_id}",
            )

            # Immutable financial audit record
            self._log_audit(
                session=session,
                action="PAYMENT_CAPTURED",
                resource_id=str(order.id),
                actor_id=None,
                actor_type="SYSTEM",
                before_state={"status": ORDER_STATUS_PENDING},
                after_state={
                    "status": ORDER_STATUS_PAID,
                    "order_no": order.order_no,
                    "amount_inr": order.amount_inr,
                    "payment_id": rzp_payment_id,
                    "enrollment_id": str(enrollment.id),
                },
                request_context=request_context,
            )

            return {"status": "ok", "order_id": str(order.id), "payment_id": rzp_payment_id}

        # 4. Handle failed payment events
        elif event == "payment.failed":
            payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
            rzp_order_id = payment_entity.get("order_id")
            rzp_payment_id = payment_entity.get("id")
            amount = payment_entity.get("amount", 0)

            if rzp_order_id and rzp_payment_id:
                order = self.order_repo.get_by_razorpay_order_id(session, rzp_order_id, for_update=True)
                if order and order.status != ORDER_STATUS_PAID:
                    self.order_repo.update_status(session, order, ORDER_STATUS_FAILED)
                    self.order_repo.create_transaction(
                        session=session,
                        order_id=order.id,
                        razorpay_payment_id=rzp_payment_id,
                        razorpay_signature=signature_header,
                        status=TRANSACTION_STATUS_FAILED,
                        amount_inr=amount,
                        raw_payload=payload,
                    )
                    self._log_audit(
                        session=session,
                        action="PAYMENT_FAILED",
                        resource_id=str(order.id),
                        actor_id=None,
                        actor_type="SYSTEM",
                        after_state={"status": ORDER_STATUS_FAILED, "payment_id": rzp_payment_id},
                        request_context=request_context,
                    )

            return {"status": "ok", "event": "payment.failed"}

        # 5. Handle refund processed and failed events (BUG-012 Reconciliation)
        elif event == "refund.processed":
            refund_entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
            rzp_refund_id = refund_entity.get("id")
            if rzp_refund_id:
                refund = self.order_repo.get_refund_by_razorpay_id(session, rzp_refund_id, for_update=True)
                if not refund:
                    # P0-05: Missing local refund record reconciliation
                    rzp_payment_id = refund_entity.get("payment_id")
                    if rzp_payment_id:
                        tx = self.order_repo.get_transaction_by_payment_id(session, rzp_payment_id)
                        if tx and tx.order:
                            order = tx.order
                            refund_amount = refund_entity.get("amount", order.amount_inr)
                            refund = self.order_repo.create_refund(
                                session=session,
                                order_id=order.id,
                                amount_inr=refund_amount,
                                reason=refund_entity.get("notes", {}).get("reason", "Gateway direct refund"),
                                approved_by=order.student_id,
                                razorpay_refund_id=rzp_refund_id,
                                status=REFUND_STATUS_PENDING,
                            )
                if refund and refund.status != REFUND_STATUS_PROCESSED:
                    refund.status = REFUND_STATUS_PROCESSED
                    session.flush()
                    order = self.order_repo.get_by_id(session, refund.order_id, for_update=True)
                    if order:
                        prior_refunds = session.query(Refund).filter(
                            Refund.order_id == order.id,
                            Refund.status == REFUND_STATUS_PROCESSED,
                        ).all()
                        cumulative = sum(r.amount_inr for r in prior_refunds)
                        if cumulative == order.amount_inr:
                            self.order_repo.update_status(session, order, ORDER_STATUS_REFUNDED)
                            enrollment = self.enrollment_repo.get_by_student_and_course(
                                session=session,
                                student_id=order.student_id,
                                course_id=order.course_id,
                            )
                            if enrollment and enrollment.status == ENROLLMENT_STATUS_ACTIVE:
                                self.enrollment_repo.revoke_enrollment(
                                    session=session,
                                    enrollment=enrollment,
                                    reason="PAYMENT_REFUNDED: Full refund processed via webhook reconciliation",
                                )
                    self._log_audit(
                        session=session,
                        action="REFUND_PROCESSED_WEBHOOK",
                        resource_id=str(refund.id),
                        actor_id=None,
                        actor_type="SYSTEM",
                        after_state={"status": REFUND_STATUS_PROCESSED, "refund_id": rzp_refund_id},
                        request_context=request_context,
                    )
            return {"status": "ok", "event": "refund.processed", "refund_id": rzp_refund_id}

        elif event == "refund.failed":
            refund_entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
            rzp_refund_id = refund_entity.get("id")
            if rzp_refund_id:
                refund = self.order_repo.get_refund_by_razorpay_id(session, rzp_refund_id, for_update=True)
                if refund and refund.status not in (REFUND_STATUS_FAILED, REFUND_STATUS_PROCESSED):
                    refund.status = REFUND_STATUS_FAILED
                    self._log_audit(
                        session=session,
                        action="REFUND_FAILED_WEBHOOK",
                        resource_id=str(refund.id),
                        actor_id=None,
                        actor_type="SYSTEM",
                        after_state={"status": REFUND_STATUS_FAILED, "refund_id": rzp_refund_id},
                        request_context=request_context,
                    )
            return {"status": "ok", "event": "refund.failed", "refund_id": rzp_refund_id}

        # P0-05: Track and audit all unhandled webhook events so none are silently dropped
        self._log_audit(
            session=session,
            action="WEBHOOK_EVENT_UNHANDLED",
            resource_id=str(payload.get("account_id") or "gateway"),
            actor_id=None,
            actor_type="SYSTEM",
            after_state={"event": event},
            request_context=request_context,
        )
        return {"status": "ignored", "event": event}

    def refund_order(
        self,
        session: Session,
        order_id: uuid.UUID,
        reason: str,
        amount_inr: Optional[int],
        current_user: User,
        request_context: Optional[dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> RefundResponse:
        """Authorizes and executes a payment refund via Razorpay API.

        Restricted strictly to users with payments:refund permission (Super Admin).

        Args:
            session: Active database transaction.
            order_id: Target order UUID to refund.
            reason: Mandatory business justification.
            amount_inr: Optional partial refund amount in paise (defaults to full order total).
            current_user: Authorizing administrator.
            request_context: Audit request context.
            idempotency_key: Optional client-provided idempotency key.

        Returns:
            RefundResponse representing processed refund record.
        """
        # 1. Fetch order with row-level pessimistic lock
        order = self.order_repo.get_by_id(session, order_id, for_update=True)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "ORDER_NOT_FOUND", "message": "Order not found"},
            )

        # 2. Status guard: only PAID orders can be refunded
        if order.status != ORDER_STATUS_PAID:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_ORDER_STATUS",
                    "message": f"Cannot refund order with status {order.status}",
                },
            )

        # 3. Guard against concurrent or un-reconciled pending refunds (P0-05)
        pending = session.query(Refund).filter(
            Refund.order_id == order.id,
            Refund.status == REFUND_STATUS_PENDING,
        ).first()
        if pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "REFUND_PENDING_RECONCILIATION",
                    "message": "A refund is currently pending reconciliation for this order.",
                    "refund_id": str(pending.id),
                },
            )

        # 4. Find the successful payment transaction for gateway payment ID
        tx = self.order_repo.get_successful_transaction_for_order(session, order.id)
        if not tx:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "NO_TRANSACTION_FOUND",
                    "message": "No successful payment transaction found for this order",
                },
            )

        # 5. Calculate cumulative processed and pending refund exposure (BUG-012)
        prior_refunds = session.query(Refund).filter(
            Refund.order_id == order.id,
            Refund.status.in_([REFUND_STATUS_PROCESSED, REFUND_STATUS_PENDING]),
        ).all()
        cumulative_refunded = sum(r.amount_inr for r in prior_refunds)
        remaining_refundable = order.amount_inr - cumulative_refunded

        refund_amount = amount_inr or remaining_refundable
        if refund_amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_REFUND_AMOUNT",
                    "message": "Refund amount must be positive.",
                },
            )

        if refund_amount > remaining_refundable:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_REFUND_AMOUNT",
                    "message": f"Refund amount ({refund_amount} paise) exceeds refundable balance ({remaining_refundable} paise)",
                },
            )

        # 6. Call Razorpay Refund API with error handling and idempotency (P0-05)
        try:
            refund_kwargs: dict[str, Any] = {
                "payment_id": tx.razorpay_payment_id,
                "amount_inr": refund_amount,
                "notes": {
                    "reason": reason,
                    "order_no": order.order_no,
                    "approved_by": str(current_user.id),
                },
            }
            if idempotency_key:
                refund_kwargs["idempotency_key"] = idempotency_key
                refund_kwargs["notes"]["idempotency_key"] = idempotency_key

            rzp_refund = self.razorpay_client.create_refund(**refund_kwargs)
        except Exception as exc:
            logger.error("Razorpay refund API call failed: %s", exc)
            is_timeout = (
                isinstance(exc, (TimeoutError, socket.timeout))
                or (isinstance(exc, urllib.error.URLError) and "timed out" in str(exc.reason).lower())
                or any(t in str(exc).lower() for t in ("timeout", "timed out", "connection reset", "broken pipe"))
            )
            if is_timeout:
                # Ambiguous gateway state: persist PENDING record durably for webhook reconciliation
                refund = self.order_repo.create_refund(
                    session=session,
                    order_id=order.id,
                    amount_inr=refund_amount,
                    reason=reason,
                    approved_by=current_user.id,
                    razorpay_refund_id=None,
                    status=REFUND_STATUS_PENDING,
                )
                self._log_audit(
                    session=session,
                    action="REFUND_PENDING_TIMEOUT",
                    resource_id=str(order.id),
                    actor_id=current_user.id,
                    actor_type="USER",
                    before_state={"status": order.status},
                    after_state={
                        "status": order.status,
                        "refund_status": REFUND_STATUS_PENDING,
                        "pending_amount": refund_amount,
                        "error": str(exc),
                        "idempotency_key": idempotency_key,
                    },
                    request_context=request_context,
                )
                session.commit()
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail={
                        "code": "GATEWAY_TIMEOUT_PENDING_RECONCILIATION",
                        "message": "Payment gateway timed out during refund. A pending refund record was recorded for webhook reconciliation.",
                        "refund_id": str(refund.id),
                    },
                )
            else:
                refund = self.order_repo.create_refund(
                    session=session,
                    order_id=order.id,
                    amount_inr=refund_amount,
                    reason=reason,
                    approved_by=current_user.id,
                    razorpay_refund_id=None,
                    status=REFUND_STATUS_FAILED,
                )
                self._log_audit(
                    session=session,
                    action="REFUND_FAILED",
                    resource_id=str(order.id),
                    actor_id=current_user.id,
                    actor_type="USER",
                    before_state={"status": order.status},
                    after_state={
                        "status": order.status,
                        "refund_status": REFUND_STATUS_FAILED,
                        "failed_amount": refund_amount,
                        "error": str(exc),
                        "idempotency_key": idempotency_key,
                    },
                    request_context=request_context,
                )
                session.commit()
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "code": "GATEWAY_REFUND_FAILED",
                        "message": f"Payment gateway refund failed: {str(exc)}",
                        "refund_id": str(refund.id),
                    },
                )

        # 6. Parse gateway refund status truthfully
        gateway_status = (rzp_refund.get("status") or "").lower()
        if gateway_status == "processed":
            refund_status = REFUND_STATUS_PROCESSED
        elif gateway_status == "failed":
            refund_status = REFUND_STATUS_FAILED
        else:
            refund_status = REFUND_STATUS_PENDING

        refund = self.order_repo.create_refund(
            session=session,
            order_id=order.id,
            amount_inr=refund_amount,
            reason=reason,
            approved_by=current_user.id,
            razorpay_refund_id=rzp_refund.get("id"),
            status=refund_status,
        )

        # 7. Transition order to REFUNDED only when cumulative successful refunds equal order amount
        if refund_status == REFUND_STATUS_PROCESSED:
            new_total_processed = cumulative_refunded + refund_amount
            if new_total_processed == order.amount_inr:
                self.order_repo.update_status(session, order, ORDER_STATUS_REFUNDED)
                enrollment = self.enrollment_repo.get_by_student_and_course(
                    session=session,
                    student_id=order.student_id,
                    course_id=order.course_id,
                )
                if enrollment and enrollment.status == ENROLLMENT_STATUS_ACTIVE:
                    self.enrollment_repo.revoke_enrollment(
                        session=session,
                        enrollment=enrollment,
                        reason=f"PAYMENT_REFUNDED: {reason}",
                    )
                    self._log_audit(
                        session=session,
                        action="ENROLLMENT_REVOKED",
                        resource_id=str(enrollment.id),
                        actor_id=current_user.id,
                        actor_type="USER",
                        before_state={"status": ENROLLMENT_STATUS_ACTIVE},
                        after_state={
                            "status": "REVOKED",
                            "reason": f"PAYMENT_REFUNDED: {reason}",
                        },
                        request_context=request_context,
                    )

        # 8. Transactional Outbox: notify student of refund
        student_email = order.student.email if order.student else ""
        self._emit_outbox_event(
            session=session,
            event_type="REFUND_ISSUED",
            recipient_email=student_email,
            subject=f"Refund Processed for Order {order.order_no}",
            payload={
                "order_no": order.order_no,
                "refund_amount_inr": refund_amount,
                "reason": reason,
            },
            dedupe_key=f"refund_{refund.id}",
        )

        # 9. Immutable financial audit log
        self._log_audit(
            session=session,
            action="PAYMENT_REFUNDED",
            resource_id=str(order.id),
            actor_id=current_user.id,
            actor_type="USER",
            before_state={"status": ORDER_STATUS_PAID},
            after_state={
                "status": order.status,
                "refund_id": str(refund.id),
                "amount_inr": refund_amount,
                "reason": reason,
            },
            request_context=request_context,
        )

        return RefundResponse.model_validate(refund)

    def get_order_by_id(
        self,
        session: Session,
        order_id: uuid.UUID,
        current_user: User,
    ) -> OrderResponse:
        """Fetch an order verifying ownership or administrative permission."""
        order = self.order_repo.get_by_id(session, order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "ORDER_NOT_FOUND", "message": "Order not found"},
            )

        user_roles = {ur.role_id for ur in current_user.user_roles}
        is_admin = bool(user_roles.intersection({"ADMIN", "SUPER_ADMIN"}))

        if order.student_id != current_user.id and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Access to another user's order is prohibited"},
            )

        return OrderResponse.model_validate(order)

    def list_orders(
        self,
        session: Session,
        current_user: User,
        status_filter: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> OrderListResponse:
        """Lists orders with role-based scoping (own orders for student; all for admin)."""
        skip = (page - 1) * size
        user_roles = {ur.role_id for ur in current_user.user_roles}
        is_admin = bool(user_roles.intersection({"ADMIN", "SUPER_ADMIN"}))

        if is_admin:
            items, total = self.order_repo.list_all_orders(session, status=status_filter, skip=skip, limit=size)
        else:
            items, total = self.order_repo.list_student_orders(session, current_user.id, skip=skip, limit=size)

        return OrderListResponse(
            items=[OrderResponse.model_validate(o) for o in items],
            total=total,
            page=page,
            size=size,
        )
