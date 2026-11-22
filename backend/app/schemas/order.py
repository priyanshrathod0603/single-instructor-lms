"""Pydantic v2 schemas for Commerce, Orders, Payments, and Refunds.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 5, Tables 25-27)
- docs/backend/06-API-ARCHITECTURE.md (Section 2.7)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK501-TASK504)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004, ADR-005)
"""

from datetime import datetime
from typing import Any, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class OrderCreateRequest(BaseModel):
    """Payload to initiate checkout and create a pending order."""

    course_id: uuid.UUID = Field(
        ...,
        description="Target published course UUID to purchase",
    )


class OrderResponse(BaseModel):
    """Schema representing an order record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_no: str
    student_id: uuid.UUID
    course_id: uuid.UUID
    amount_inr: int
    currency: str
    status: str
    razorpay_order_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class OrderCheckoutResponse(BaseModel):
    """Client checkout payload containing order metadata and Razorpay credentials."""

    order_id: uuid.UUID
    order_no: str
    amount_inr: int
    currency: str
    razorpay_order_id: str
    razorpay_key_id: str
    course_title: str


class OrderListResponse(BaseModel):
    """Paginated list envelope for orders."""

    items: List[OrderResponse]
    total: int
    page: int
    size: int


class PaymentTransactionResponse(BaseModel):
    """Cryptographically verified payment transaction record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    gateway: str
    razorpay_payment_id: str
    status: str
    amount_inr: int
    processed_at: datetime


class RefundRequest(BaseModel):
    """Super Admin authorization payload for order refund."""

    reason: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Mandatory business reason and justification for the refund",
    )
    amount_inr: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional partial refund amount in paise. Defaults to full order total.",
    )


class RefundResponse(BaseModel):
    """Schema representing an authorized refund execution record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    amount_inr: int
    reason: str
    status: str
    razorpay_refund_id: Optional[str] = None
    approved_by: uuid.UUID
    processed_at: datetime
