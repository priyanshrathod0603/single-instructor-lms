# Testing Strategy & Quality Assurance Architecture

## 1. Quality Assurance Mandate: Test Before Moving Forward

In accordance with Phase 1 directives, development enforces the principle:
$$\text{Feature Complete} \iff \text{Automated Tests Pass With Empirical Evidence}$$

No module, endpoint, or repository may be declared complete without accompanying automated test suites executed against a live test environment.

---

## 2. The Four-Tier Testing Pyramid

```mermaid
pie title Test Suite Distribution
    "Unit Tests (Fast, Isolated)" : 45
    "Integration Tests (PostgreSQL / Transactions)" : 30
    "API / Route Tests (HTTP Endpoints)" : 15
    "Security & Concurrency Tests" : 10
```

### 2.1 Unit Tests (`tests/unit/`)
* **Focus**: Pure logic execution without database or network I/O.
* **Target Areas**:
  - Argon2id password hashing parameters and complexity validation.
  - Pydantic v2 request/response schema coercion and validation errors.
  - RBAC permission evaluator (role aggregation, deny-overrides-allow).
  - Minor currency math calculations (paise conversion, rubric score weighting).

### 2.2 Integration Tests (`tests/integration/`)
* **Focus**: Persistence logic, database constraints, and transactional consistency.
* **Target Areas**:
  - `auth_sessions`: Single-Active-Session atomic displacement under concurrent load.
  - `course_revisions`: Immutability of published revisions and draft hierarchy cloning.
  - `orders` & `enrollments`: Idempotent payment webhook reconciliation and enrollment provisioning.
  - `audit_logs`: Database-level trigger blocking `UPDATE` and `DELETE` queries.

### 2.3 API End-to-End Tests (`tests/api/`)
* **Focus**: HTTP presentation layer via `TestClient`.
* **Target Areas**:
  - HTTP status codes, standard response envelopes, and custom error formats.
  - Cookie lifecycle (`__Host-lms_session` set, updated, and revoked).
  - File upload presigned URL generation.
  - Server-authoritative quiz timer enforcement and autosave.

### 2.4 Security & Penetration Tests (`tests/security/`)
* **Focus**: Exploit simulations and boundary testing.
* **Target Areas**:
  - **Concurrent Login Race**: Simulate two concurrent login requests from the same user account; verify exactly one active session survives.
  - **Insecure Direct Object Reference (IDOR)**: Student A attempts to view or submit Student B's assignment; verify HTTP 403/404 response.
  - **Webhook Forgery**: Send forged Razorpay webhook with invalid HMAC signature; verify immediate HTTP 400 rejection and security log entry.
  - **XSS Payload Sanitization**: Inject `<script>alert(1)</script>` into lesson text or profile fields; verify proper HTML escaping.

---

## 3. Test Fixture Architecture & Database Isolation

Every test runs within an isolated database transaction that rolls back upon test completion, guaranteeing zero state leakage across test cases:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.base import Base

@pytest.fixture(scope="session")
def engine():
    return create_engine("postgresql+psycopg://postgres:postgres@localhost:5432/lms_test")

@pytest.fixture(scope="function")
def db_session(engine):
    """
    Wraps each individual test inside an isolated database transaction
    that automatically rolls back at teardown.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
```

---

## 4. External Service Mocking Contracts

To maintain determinism and avoid cloud egress during testing, external infrastructure is strictly mocked:
1. **Razorpay SDK**: Mock order generation and refund APIs.
2. **Email Provider (Resend / SendGrid)**: Worker tests verify task insertion into `notification_outbox` rather than sending live emails.
3. **Storage (Cloudflare R2 / S3)**: Presigned URL generator uses local deterministic dummy strings.
4. **Google Identity JWKS**: Mocked public certificate responses during OAuth token tests.

---

## 5. Execution & Coverage Thresholds

```bash
# Execute entire test suite with coverage report
pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=85
```

* **Overall Code Coverage Target**: $\ge 85\%$
* **Security & Auth Layer Target**: $\ge 95\%$
* **Zero Skipped Security Tests**: All IDOR, webhook, and session displacement tests must pass green.
