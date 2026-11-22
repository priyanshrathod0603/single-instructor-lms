# Enrollment & Payment Architecture Specification

## 1. Zero Trust on Browser Redirect Invariant

In accordance with the LMS Blueprint v2.0 (Page 14), client-side browser events are completely untrusted for granting course access:
$$\text{Enrollment Grant} \iff \text{Cryptographically Verified Webhook Ingestion}$$

Under no circumstances does the backend grant course enrollment based on frontend redirection, client callback parameters, or query string flags (e.g., `?payment_status=success`). Course enrollment is granted **exclusively** upon server-to-server webhook receipt with verified cryptographic HMAC-SHA256 signatures.

```mermaid
sequenceDiagram
    autonumber
    actor Student
    participant Browser as Client Browser (React)
    participant API as FastAPI Backend
    participant DB as PostgreSQL
    participant RZP as Razorpay Payment Gateway

    Student->>Browser: Click "Enroll Now"
    Browser->>API: POST /api/v1/orders { "course_id": "..." }
    API->>DB: Check email verified & no duplicate active enrollment
    API->>RZP: POST /v1/orders (amount_inr, currency='INR', receipt)
    RZP-->>API: { "id": "order_Hdf81923ns" }
    API->>DB: INSERT INTO orders (order_no, student_id, course_id, amount_inr, status='PENDING', razorpay_order_id)
    API-->>Browser: { "order_id": "...", "razorpay_order_id": "order_Hdf81923ns", "amount": 499900 }
    
    Browser->>RZP: Open Razorpay Checkout Modal
    Student->>RZP: Enters UPI / Card details & Approves Payment
    RZP-->>Browser: Payment modal closes; redirect to /checkout/success
    
    note over RZP,API: Asynchronous Server-to-Server Webhook
    RZP->>API: POST /api/v1/webhooks/razorpay (X-Razorpay-Signature: <HMAC>)
    API->>API: Compute HMAC-SHA256(raw_body, RAZORPAY_WEBHOOK_SECRET)
    API->>API: Constant-time compare signature
    alt Signature Valid
        API->>DB: BEGIN Transaction
        API->>DB: SELECT * FROM orders WHERE razorpay_order_id = ... FOR UPDATE
        API->>DB: UPDATE orders SET status = 'PAID'
        API->>DB: INSERT INTO payment_transactions (order_id, razorpay_payment_id, status='SUCCESS')
        API->>DB: INSERT INTO enrollments (student_id, course_id, order_id, status='ACTIVE')
        API->>DB: INSERT INTO notification_outbox (type='ENROLLMENT_RECEIPT')
        API->>DB: COMMIT Transaction
        API-->>RZP: HTTP 200 OK
    else Signature Invalid
        API-->>RZP: HTTP 400 Bad Request (Security Alert Logged)
    end

    Browser->>API: GET /api/v1/enrollments/check/{course_id}
    API->>DB: SELECT status FROM enrollments WHERE student_id = ... AND course_id = ...
    DB-->>API: status = 'ACTIVE'
    API-->>Browser: { "is_enrolled": true, "access_granted": true }
    Browser-->>Student: Display Course Dashboard with Active Access
```

---

## 2. Minor Currency Units Standard

To eliminate rounding errors and floating-point precision hazards:
* All prices, fees, and transaction amounts are stored and calculated strictly in **minor currency units** (`BIGINT` paise for INR).
* Formula: $\text{Paise} = \text{Rupees} \times 100$.
* Example: A course priced at ₹4,999.00 is stored as `499900` paise.
* Division or conversion to major units occurs strictly in the presentation layer.

---

## 3. Webhook Signature Verification Specification

The webhook endpoint `POST /api/v1/webhooks/razorpay` verifies requests using the shared secret configured in `RAZORPAY_WEBHOOK_SECRET`:

```python
import hmac
import hashlib
from fastapi import Request, HTTPException, status

async def verify_razorpay_webhook(request: Request, webhook_secret: str) -> bytes:
    """
    Verifies that the incoming webhook payload was authentically signed by Razorpay.
    Reads the raw body bytes to guarantee zero whitespace modification.
    """
    signature_header = request.headers.get("X-Razorpay-Signature")
    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MISSING_SIGNATURE", "message": "Missing webhook signature header"}
        )

    raw_body = await request.body()
    expected_signature = hmac.new(
        key=webhook_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature_header):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_SIGNATURE", "message": "Cryptographic webhook signature verification failed"}
        )

    return raw_body
```

---

## 4. Webhook Idempotency & Concurrency Handling

Because payment gateways may deliver duplicate webhooks for the same transaction event:
1. **Row Locking**: The transaction executes `SELECT * FROM orders WHERE razorpay_order_id = :rzp_order_id FOR UPDATE`.
2. **Idempotency Check**: If the order record is already in `status = 'PAID'`, the handler skips redundant enrollment creation and immediately returns `HTTP 200 OK`.
3. **Transaction Collision Guard**: The unique constraint on `payment_transactions.razorpay_payment_id` prevents duplicate transaction rows from ever committing.

---

## 5. Refunds & Access Revocation

Refunds are restricted exclusively to Super Admins (`payments:refund` permission).

### 5.1 Refund Workflow (`POST /api/v1/orders/{id}/refund`)
1. Super Admin inputs refund reason and authorization confirmation.
2. Backend calls Razorpay Refunds API: `POST /v1/payments/{payment_id}/refund`.
3. Upon gateway approval:
   - Inserts record into `refunds` table (`status = 'PROCESSED'`).
   - Updates `orders.status = 'REFUNDED'`.
   - Transitions `enrollments.status = 'REVOKED'` and sets `revoked_reason = 'PAYMENT_REFUNDED'`.
   - Records immutable security audit record in `audit_logs`.
   - Emits transactional outbox email informing the student of the refund and enrollment termination.
