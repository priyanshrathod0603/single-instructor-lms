"""Pydantic v2 schemas for Commercial Payment Overview (SA-05.2).

Architecture Specifications:
- SA-05 — Complete Commercial Governance (Section 4)
- docs/backend/06-API-ARCHITECTURE.md
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md
"""

from datetime import datetime
from typing import Any, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class PaymentMetricsResponse(BaseModel):
    """Aggregate financial metrics calculated strictly from real database records."""
    model_config = ConfigDict(from_attributes=True)

    total_transactions_count: int = Field(..., description="Total payment gateway transactions")
    successful_payments_count: int = Field(..., description="Successful transactions with status SUCCESS")
    failed_payments_count: int = Field(..., description="Failed transactions with status FAILED")
    pending_orders_count: int = Field(..., description="Orders awaiting gateway payment fulfillment")
    refunded_orders_count: int = Field(..., description="Orders marked as REFUNDED")
    gross_revenue_paise: int = Field(..., description="Total collected amount before refunds in integer paise")
    successful_collected_paise: int = Field(..., description="Total successfully settled revenue in paise")
    refunded_amount_paise: int = Field(..., description="Total processed refunds in integer paise")
    net_collected_paise: int = Field(..., description="Net revenue (successful_collected_paise - refunded_amount_paise)")
    currency: str = Field("INR", description="Currency standard (INR)")
    generated_at: datetime = Field(..., description="UTC timestamp when metrics were calculated")


class TransactionRefundSummary(BaseModel):
    """Refund details associated with a transaction order."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount_inr: int
    reason: str
    status: str
    razorpay_refund_id: Optional[str] = None
    processed_at: datetime


class TransactionStudentSummary(BaseModel):
    """Student reference for a transaction."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str


class TransactionCourseSummary(BaseModel):
    """Course reference for a transaction."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    slug: str


class TransactionOrderSummary(BaseModel):
    """Parent order summary for a transaction."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_no: str
    status: str
    amount_inr: int
    currency: str


class TransactionItemResponse(BaseModel):
    """Complete transaction detail for surveillance directory and inspection."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    gateway: str
    razorpay_payment_id: str
    status: str
    amount_inr: int
    currency: str = "INR"
    processed_at: datetime
    order: Optional[TransactionOrderSummary] = None
    student: Optional[TransactionStudentSummary] = None
    course: Optional[TransactionCourseSummary] = None
    refunds: List[TransactionRefundSummary] = Field(default_factory=list)


class TransactionListResponse(BaseModel):
    """Paginated list of payment transactions."""
    model_config = ConfigDict(from_attributes=True)

    items: List[TransactionItemResponse]
    total: int
    page: int
    per_page: int
    pages: int
