"""Commerce and Orders REST API endpoints.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.7)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK502, TASK504)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004, ADR-005, ADR-008)
"""

import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_permissions
from app.core.exceptions import ForbiddenException
from app.core.permissions import ORDERS_CREATE, ORDERS_VIEW_ALL, ORDERS_VIEW_OWN, PAYMENTS_REFUND
from app.models.user import User
from app.schemas.order import (
    OrderCheckoutResponse,
    OrderCreateRequest,
    OrderListResponse,
    OrderResponse,
    RefundRequest,
    RefundResponse,
)
from app.services.audit_service import AuditService
from app.services.payment_service import PaymentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["Commerce & Orders"])


def get_payment_service() -> PaymentService:
    """Dependency providing configured PaymentService instance."""
    return PaymentService()


@router.post(
    "",
    response_model=OrderCheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate course purchase and create checkout order",
)
def create_order(
    body: OrderCreateRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(ORDERS_CREATE)),
    payment_service: PaymentService = Depends(get_payment_service),
) -> OrderCheckoutResponse:
    """Creates a new commercial order and initializes a Razorpay gateway order."""
    ctx = AuditService.extract_request_context(request)
    return payment_service.create_order(
        session=db,
        student=current_user,
        course_id=body.course_id,
        request_context=ctx,
    )


@router.get(
    "",
    response_model=OrderListResponse,
    summary="List orders with role-based scoping",
)
def list_orders(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Optional status filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
) -> OrderListResponse:
    """Lists orders. Students view own orders; Admins view all platform orders."""
    user_permissions = current_user.get_aggregated_permissions()
    user_roles = {ur.role_id for ur in current_user.user_roles}
    is_admin = bool(user_roles.intersection({"ADMIN", "SUPER_ADMIN"}))

    if not is_admin and ORDERS_VIEW_OWN not in user_permissions and ORDERS_VIEW_ALL not in user_permissions:
        raise ForbiddenException(
            message="Missing required permission to view orders.",
            code="PERMISSION_DENIED",
        )

    return payment_service.list_orders(
        session=db,
        current_user=current_user,
        status_filter=status,
        page=page,
        size=size,
    )


@router.get(
    "/{id}",
    response_model=OrderResponse,
    summary="Get order status and payment details",
)
def get_order(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
) -> OrderResponse:
    """Get single order details verifying ownership or admin authorization."""
    return payment_service.get_order_by_id(
        session=db,
        order_id=id,
        current_user=current_user,
    )


@router.post(
    "/{id}/refund",
    response_model=RefundResponse,
    summary="Authorize and execute order refund",
)
def refund_order(
    id: uuid.UUID,
    body: RefundRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions(PAYMENTS_REFUND)),
    payment_service: PaymentService = Depends(get_payment_service),
) -> RefundResponse:
    """Super Admin endpoint to refund an order via Razorpay Refunds API."""
    ctx = AuditService.extract_request_context(request)
    return payment_service.refund_order(
        session=db,
        order_id=id,
        reason=body.reason,
        amount_inr=body.amount_inr,
        current_user=current_user,
        request_context=ctx,
        idempotency_key=idempotency_key,
    )
