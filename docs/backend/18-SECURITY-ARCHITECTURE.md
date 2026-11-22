# Security Architecture & Defense-in-Depth Specification

## 1. Security Philosophy & Principles

The Single-Instructor LMS architecture implements defense-in-depth across the presentation, application, data, and infrastructure layers. Security controls are proactive, automated, and enforced at runtime.

---

## 2. OWASP Top 10 Threat Mitigation Matrix

| Vulnerability | Platform Risk | Engineered Mitigation |
| :--- | :--- | :--- |
| **A01: Broken Access Control** | Unauthorized student accessing other submissions or admin routes | Strict RBAC dependency injection (`require_permissions`); record-level scope verification (`student_id == current_user.id`) on all detail endpoints. |
| **A02: Cryptographic Failures** | Compromised credentials or token interception | Argon2id password hashing; TLS 1.3 in transit; HMAC-SHA256 signed webhooks; high-entropy tokens via `secrets.token_urlsafe(32)`. |
| **A03: Injection (SQL / Command)** | Database compromise via user input | 100% parameterized queries via SQLAlchemy 2.0 ORM; strict Pydantic v2 type coercion; zero raw SQL string concatenation. |
| **A04: Insecure Design** | Concurrent credential sharing; payment bypass | Architectural invariants: Single-Active-Session with atomic displacement; zero trust on browser redirects (verified webhooks only). |
| **A05: Security Misconfiguration** | Verbose error leaks; permissive headers | Production exception handlers strip stack traces; strict HTTP security headers (HSTS, CSP, X-Frame-Options: DENY). |
| **A06: Vulnerable Components** | Outdated or exploited libraries | Pinned dependencies with hash verification (`uv.lock`); continuous vulnerability scanning via `pip-audit`. |
| **A07: Identification & Auth** | Credential stuffing; brute-force attacks | Redis-backed rate limiting (5 attempts / 15 min); single active session enforcement; mandatory email verification before learning access. |
| **A08: Software & Data Integrity** | Falsified payment receipts; fake certificates | Cryptographic HMAC webhook verification; public certificate hashes signed with server-side HMAC secret. |
| **A09: Logging & Monitoring Failures** | Undetected administrative malfeasance | Append-only `audit_logs` table with DB-level triggers revoking `UPDATE` and `DELETE`; structured JSON logging with `request_id`. |
| **A10: Server-Side Request Forgery** | Attacker probes internal cloud metadata (169.254.169.254) | Direct presigned uploads (backend never fetches arbitrary remote URLs); URL validators block RFC 1918 private IP ranges. |

---

## 3. Insecure Direct Object Reference (IDOR) Mitigation

To prevent learners from accessing other students' assignment files, quiz answers, or certificates:
1. Every query filtering on a user-owned entity enforces ownership at the SQL query level:
   ```python
   # Correct IDOR-safe query pattern
   stmt = (
       select(AssignmentSubmission)
       .where(
           AssignmentSubmission.id == submission_id,
           AssignmentSubmission.student_id == current_user.id # Explicit ownership bound
       )
   )
   ```
2. Administrative roles (`STAFF`, `ADMIN`, `SUPER_ADMIN`) bypass this clause only when explicitly requested through authorized management routes.

---

## 4. Hardened HTTP Security Headers

The FastAPI middleware injects the following response headers on all outgoing responses:

```http
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Content-Security-Policy: default-src 'self'; script-src 'self'; img-src 'self' data: https:; media-src 'self' https:;
```

---

## 5. Cross-Origin Resource Sharing (CORS) Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL], # e.g. "https://learn.instructor.com"
    allow_credentials=True,                # Permits __Host- cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key", "X-Requested-With"],
    max_age=3600,
)
```
Wildcards (`*`) are strictly prohibited in production environments when credentials are enabled.
