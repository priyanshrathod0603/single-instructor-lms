"""Payment Gateway Webhook Ingestion API endpoints.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.7)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-4)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK503)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)

Strict Invariants:
1. Cryptographic HMAC-SHA256 signature verification over unmodified request byte body.
2. Zero trust on browser redirect: Payment verification occurs exclusively via this webhook.
3. Idempotent processing with pessimistic row locks to prevent duplicate enrollments or double records.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.audit_service import AuditService
from app.services.payment_service import PaymentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Payment Webhooks"])


def get_payment_service() -> PaymentService:
    """Dependency providing configured PaymentService instance."""
    return PaymentService()


@router.post(
    "/razorpay",
    status_code=status.HTTP_200_OK,
    summary="Cryptographic webhook endpoint for Razorpay payment capture",
)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    db: Session = Depends(get_db),
    payment_service: PaymentService = Depends(get_payment_service),
) -> dict:
    """Ingests, cryptographically verifies, and idempotently reconciles incoming Razorpay webhooks."""
    raw_body = await request.body()
    ctx = AuditService.extract_request_context(request)

    if not x_razorpay_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MISSING_SIGNATURE", "message": "Missing X-Razorpay-Signature header"},
        )

    return payment_service.process_razorpay_webhook(
        session=db,
        raw_body=raw_body,
        signature_header=x_razorpay_signature,
        request_context=ctx,
    )
