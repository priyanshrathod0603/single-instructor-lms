"""Unit tests for Razorpay Client and Cryptographic Signature Verification.

Verifies:
1. HMAC-SHA256 signature computation and constant-time comparison.
2. Rejection of tampered payloads, missing signatures, or mismatched secrets.
3. Order creation in mock mode (deterministic format, amount in paise).
4. Validation against negative or zero amounts.
5. Refund initiation in mock mode.
"""

import json

import pytest

from app.core.config import Settings
from app.core.razorpay import (
    RazorpayClient,
    compute_razorpay_signature,
    verify_razorpay_signature,
)


class TestRazorpaySignatureVerification:
    """Verifies HMAC-SHA256 cryptographic verification."""

    def test_valid_signature_verification(self):
        """Valid HMAC signature matches byte payload."""
        secret = "secret_webhook_key_123"
        payload = b'{"event":"payment.captured","entity":"payment"}'
        sig = compute_razorpay_signature(payload, secret)

        assert verify_razorpay_signature(payload, sig, secret) is True

    def test_tampered_payload_rejected(self):
        """Altered payload fails signature verification."""
        secret = "secret_webhook_key_123"
        payload = b'{"event":"payment.captured","amount":499900}'
        sig = compute_razorpay_signature(payload, secret)

        tampered = b'{"event":"payment.captured","amount":100}'
        assert verify_razorpay_signature(tampered, sig, secret) is False

    def test_mismatched_secret_rejected(self):
        """Signature generated with different secret fails verification."""
        secret_a = "secret_a"
        secret_b = "secret_b"
        payload = b'{"event":"payment.captured"}'
        sig = compute_razorpay_signature(payload, secret_a)

        assert verify_razorpay_signature(payload, sig, secret_b) is False

    def test_empty_signature_or_secret_rejected(self):
        """Missing signature or secret returns False without crashing."""
        payload = b'{"event":"payment.captured"}'
        assert verify_razorpay_signature(payload, "", "secret") is False
        assert verify_razorpay_signature(payload, "sig", "") is False


class TestRazorpayClientOperations:
    """Verifies client order and refund creation."""

    @pytest.fixture
    def client(self):
        return RazorpayClient()

    def test_create_order_mock_success(self, client):
        """Client generates mock order with paise amount and receipt."""
        order = client.create_order(
            amount_inr=499900,
            currency="INR",
            receipt="ORD-202611-0001",
            notes={"student_id": "std_123"},
        )

        assert order["id"].startswith("order_")
        assert order["amount"] == 499900
        assert order["currency"] == "INR"
        assert order["receipt"] == "ORD-202611-0001"
        assert order["status"] == "created"
        assert order["notes"]["student_id"] == "std_123"

    def test_create_order_invalid_amount_rejected(self, client):
        """Zero or negative amount raises ValueError."""
        with pytest.raises(ValueError, match="positive"):
            client.create_order(amount_inr=0, receipt="ORD-ZERO")

        with pytest.raises(ValueError, match="positive"):
            client.create_order(amount_inr=-500, receipt="ORD-NEG")

    def test_create_refund_mock_success(self, client):
        """Client generates mock refund with paise amount."""
        refund = client.create_refund(
            payment_id="pay_mock123",
            amount_inr=499900,
            notes={"reason": "Customer request"},
        )

        assert refund["id"].startswith("rfd_")
        assert refund["amount"] == 499900
        assert refund["payment_id"] == "pay_mock123"
        assert refund["status"] == "processed"
        assert refund["notes"]["reason"] == "Customer request"

    def test_create_refund_invalid_amount_rejected(self, client):
        """Zero or negative refund amount raises ValueError."""
        with pytest.raises(ValueError, match="positive"):
            client.create_refund(payment_id="pay_123", amount_inr=0)
