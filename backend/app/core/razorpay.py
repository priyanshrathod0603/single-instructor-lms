"""Razorpay Gateway Client and Cryptographic Signature Verification.

Architecture Specifications:
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-4)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK502, TASK503, TASK504)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004, ADR-005)

Features:
1. Standard library HMAC-SHA256 signature verification for webhook payloads.
2. Constant-time signature comparison to eliminate timing attacks.
3. Minor currency arithmetic (BIGINT paise; 1 INR = 100 paise).
4. Pure standard library HTTP transport (urllib.request) with Basic Authentication.
5. Deterministic mock generation when credentials are not configured (test/dev mode).
"""

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Optional
import urllib.error
import urllib.request
import uuid

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def compute_razorpay_signature(raw_body: bytes, webhook_secret: str) -> str:
    """Computes the HMAC-SHA256 hex digest signature for incoming Razorpay webhooks.

    Args:
        raw_body: Raw request body bytes.
        webhook_secret: Shared secret configured in Razorpay dashboard.

    Returns:
        Hex-encoded HMAC-SHA256 signature string.
    """
    return hmac.new(
        key=webhook_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()


def verify_razorpay_signature(raw_body: bytes, signature_header: str, webhook_secret: str) -> bool:
    """Constant-time comparison of expected vs received Razorpay webhook signature.

    Args:
        raw_body: Unmodified byte payload from the incoming HTTP request.
        signature_header: X-Razorpay-Signature header value.
        webhook_secret: Shared webhook secret key.

    Returns:
        True if the signature is valid; False otherwise.
    """
    if not signature_header or not webhook_secret:
        return False

    expected_signature = compute_razorpay_signature(raw_body, webhook_secret)
    return hmac.compare_digest(expected_signature, signature_header)


class RazorpayClient:
    """Razorpay payment gateway integration supporting live API calls and mock testing."""

    BASE_URL = "https://api.razorpay.com/v1"

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

        # Enforce fail-closed production payment configuration (BUG-003)
        if self.settings.ENVIRONMENT == "production":
            if not self.settings.RAZORPAY_KEY_ID or self.settings.RAZORPAY_KEY_ID.startswith("rzp_test_mock"):
                raise RuntimeError("Razorpay Key ID must be configured in production.")
            if not self.settings.RAZORPAY_KEY_SECRET:
                raise RuntimeError("Razorpay Key Secret must be configured in production.")
            if not self.settings.RAZORPAY_WEBHOOK_SECRET:
                raise RuntimeError("Razorpay Webhook Secret must be configured in production.")

            key_sec = self.settings.RAZORPAY_KEY_SECRET.get_secret_value()
            webhook_sec = self.settings.RAZORPAY_WEBHOOK_SECRET.get_secret_value()
            if "mock" in key_sec.lower() or "dev_test" in key_sec.lower():
                raise RuntimeError("Placeholder/mock RAZORPAY_KEY_SECRET is prohibited in production.")
            if "mock" in webhook_sec.lower() or "dev_test" in webhook_sec.lower():
                raise RuntimeError("Placeholder/mock RAZORPAY_WEBHOOK_SECRET is prohibited in production.")

            self.key_id = self.settings.RAZORPAY_KEY_ID
            self.key_secret = key_sec
            self.webhook_secret = webhook_sec
        else:
            self.key_id = self.settings.RAZORPAY_KEY_ID or "rzp_test_mock_key_id"
            self.key_secret = (
                self.settings.RAZORPAY_KEY_SECRET.get_secret_value()
                if self.settings.RAZORPAY_KEY_SECRET
                else "mock_key_secret_for_dev_test"
            )
            self.webhook_secret = (
                self.settings.RAZORPAY_WEBHOOK_SECRET.get_secret_value()
                if self.settings.RAZORPAY_WEBHOOK_SECRET
                else "mock_webhook_secret_for_dev_test"
            )

        # In-memory store for orders and refunds created in test/mock mode
        self._mock_orders: dict[str, dict[str, Any]] = {}
        self._mock_refunds: dict[str, dict[str, Any]] = {}

    @property
    def is_live_configured(self) -> bool:
        """Returns True if live Razorpay credentials are present and non-default."""
        return (
            bool(self.settings.RAZORPAY_KEY_ID)
            and bool(self.settings.RAZORPAY_KEY_SECRET)
            and not self.settings.RAZORPAY_KEY_ID.startswith("rzp_test_mock")
            and not self.settings.is_testing
        )

    def _get_auth_header(self) -> str:
        """Derives HTTP Basic Auth header for Razorpay API authentication."""
        token = base64.b64encode(f"{self.key_id}:{self.key_secret}".encode("utf-8")).decode("utf-8")
        return f"Basic {token}"

    def create_order(
        self,
        amount_inr: int,
        currency: str = "INR",
        receipt: str = "",
        notes: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Creates an order in Razorpay for checkout initiation.

        Args:
            amount_inr: Amount in minor units (paise). Must be integer > 0.
            currency: Three-letter ISO currency code (default: 'INR').
            receipt: Internal LMS unique order reference number.
            notes: Arbitrary key-value metadata attached to the order.

        Returns:
            Dictionary containing Razorpay order payload (including 'id').
        """
        if amount_inr <= 0:
            raise ValueError(f"Order amount must be positive, got {amount_inr}")

        payload = {
            "amount": amount_inr,
            "currency": currency,
            "receipt": receipt,
            "notes": notes or {},
        }

        if self.is_live_configured:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url=f"{self.BASE_URL}/orders",
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": self._get_auth_header(),
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                logger.error("Razorpay order creation failed: %d %s", exc.code, body)
                raise RuntimeError(f"Razorpay order creation failed with status {exc.code}: {body}") from exc
        else:
            if self.settings.ENVIRONMENT not in ("development", "testing"):
                raise RuntimeError(
                    f"Mock payment order creation is strictly prohibited in '{self.settings.ENVIRONMENT}' environment."
                )

        # Mock order generation for dev/test mode
        order_hash = hashlib.sha256(f"{receipt}_{amount_inr}_{time.time()}_{uuid.uuid4().hex}".encode()).hexdigest()[:14]
        order_id = f"order_{order_hash}"
        mock_resp = {
            "id": order_id,
            "entity": "order",
            "amount": amount_inr,
            "amount_paid": 0,
            "amount_due": amount_inr,
            "currency": currency,
            "receipt": receipt,
            "status": "created",
            "attempts": 0,
            "notes": notes or {},
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        }
        self._mock_orders[order_id] = mock_resp
        return mock_resp

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature_header: str,
        secret: Optional[str] = None,
    ) -> bool:
        """Verifies incoming webhook signature against configured webhook secret."""
        effective_secret = secret or self.webhook_secret
        if not effective_secret or not signature_header:
            return False

        # In production, placeholder or mock secrets must never be accepted (BUG-003)
        if self.settings.ENVIRONMENT == "production":
            if "mock" in effective_secret.lower() or "dev_test" in effective_secret.lower():
                logger.error("Rejecting webhook in production: placeholder/mock secret in use.")
                return False

        return verify_razorpay_signature(raw_body, signature_header, effective_secret)

    def create_refund(
        self,
        payment_id: str,
        amount_inr: int,
        notes: Optional[dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Creates a refund via Razorpay Refunds API.

        Args:
            payment_id: Razorpay payment transaction identifier (e.g. 'pay_...').
            amount_inr: Refund amount in minor units (paise).
            notes: Reason and metadata for the refund.
            idempotency_key: Optional unique idempotency key for the refund request.

        Returns:
            Dictionary containing Razorpay refund response (including 'id').
        """
        if amount_inr <= 0:
            raise ValueError(f"Refund amount must be positive, got {amount_inr}")

        merged_notes = dict(notes or {})
        if idempotency_key:
            merged_notes["idempotency_key"] = idempotency_key

        payload = {
            "amount": amount_inr,
            "notes": merged_notes,
        }

        if self.is_live_configured:
            req_data = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Authorization": self._get_auth_header(),
            }
            if idempotency_key:
                headers["X-Refund-Idempotency"] = idempotency_key
            req = urllib.request.Request(
                url=f"{self.BASE_URL}/payments/{payment_id}/refund",
                data=req_data,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                logger.error("Razorpay refund failed: %d %s", exc.code, body)
                raise RuntimeError(f"Razorpay refund failed with status {exc.code}: {body}") from exc
        else:
            if self.settings.ENVIRONMENT not in ("development", "testing"):
                raise RuntimeError(
                    f"Mock payment refund creation is strictly prohibited in '{self.settings.ENVIRONMENT}' environment."
                )

        # Mock refund generation for dev/test mode
        refund_hash = hashlib.sha256(f"{payment_id}_{amount_inr}_{time.time()}_{uuid.uuid4().hex}".encode()).hexdigest()[:14]
        refund_id = f"rfd_{refund_hash}"
        mock_resp = {
            "id": refund_id,
            "entity": "refund",
            "amount": amount_inr,
            "currency": "INR",
            "payment_id": payment_id,
            "status": "processed",
            "notes": merged_notes,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        }
        self._mock_refunds[refund_id] = mock_resp
        return mock_resp
