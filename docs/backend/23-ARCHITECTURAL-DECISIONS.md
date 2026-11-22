# Architectural Decision Records (ADR-001 to ADR-014)

## 1. Overview & ADR Standard

This document catalogs the definitive Architectural Decision Records (ADRs) governing the backend of the Single-Instructor LMS. Each record articulates context, alternatives evaluated, the chosen decision, and resulting trade-offs.

---

## 2. Definitive Architecture Decision Records

### ADR-001: Framework Selection — FastAPI with SQLAlchemy 2.0 & Pydantic v2
* **Status**: Accepted (Approved by User, Recorded as `DEC-008`).
* **Context**: The platform requires high-performance async I/O for webhooks, streaming tokens, and fast JSON serialization, paired with compile-time type safety.
* **Alternatives Evaluated**: Django + Django REST Framework, Express / NestJS (Node.js), Go (Gin/Fiber).
* **Decision**: Adopt FastAPI running on Python 3.14 with SQLAlchemy 2.0 (psycopg3 async/sync driver) and Pydantic v2.
* **Consequences**:
  - Native OpenAPI/Swagger generation directly from type annotations.
  - High concurrency for I/O-bound operations.
  - Type-safe schema validation via Rust-accelerated Pydantic v2.

---

### ADR-002: Session Concurrency — Single-Active-Session via PostgreSQL Partial Unique Index
* **Status**: Accepted.
* **Context**: Educational course sharing via shared credentials diminishes revenue and breaks student progress tracking.
* **Alternatives Evaluated**: Redis key-per-user tracking, JWT blacklisting, WebSockets presence monitoring.
* **Decision**: Enforce at most one active session per account directly at the database level using a PostgreSQL partial unique index:
  `CREATE UNIQUE INDEX idx_auth_sessions_unique_active_user ON auth_sessions(user_id) WHERE status='ACTIVE';`
  A newly authenticated login acquires a row lock, atomically sets any existing active session to `REVOKED`, and inserts the new session as `ACTIVE`.
* **Consequences**:
  - Guarantees zero race conditions regardless of application cluster size.
  - Displaced sessions encounter immediate `401 SESSION_REVOKED` on next request.

---

### ADR-003: Curriculum Versioning — Immutable Course Revisions & JSONB Snapshots
* **Status**: Accepted.
* **Context**: Modifying a course while students are actively studying causes broken quiz links, altered lesson counts, and invalid progress calculations.
* **Alternatives Evaluated**: In-place edits with version flags on individual lessons, temporal database tables.
* **Decision**: All edits occur inside working draft revisions. Published revisions are permanently immutable. Upon publication, the complete curriculum tree is serialized into `course_revisions.snapshot` (JSONB).
* **Consequences**:
  - Enrolled students experience zero curriculum disruption during authoring.
  - Historical student submissions link permanently to the exact revision studied.
  - Spawning a new draft revision clones existing sections and lessons.

---

### ADR-004: Payment Security — Zero Trust on Browser Redirect
* **Status**: Accepted.
* **Context**: Malicious clients can simulate query strings or client callbacks (e.g. `?status=success&payment_id=...`) to claim course access without paying.
* **Alternatives Evaluated**: Client redirect with immediate frontend verification call.
* **Decision**: Course enrollment access is granted **exclusively** upon server receipt of cryptographically verified Razorpay webhooks (`POST /api/v1/webhooks/razorpay`) with valid HMAC-SHA256 signatures.
* **Consequences**:
  - Fraudulent browser redirects cannot grant course access.
  - Browser polls backend verification endpoint upon checkout modal dismissal.

---

### ADR-005: Financial Math — Minor Currency Units (`BIGINT` Paise)
* **Status**: Accepted.
* **Context**: Floating-point numbers (`FLOAT`, `DOUBLE`) suffer from IEEE-754 representation inaccuracies, leading to rounding discrepancies in financial ledgers.
* **Alternatives Evaluated**: Python `Decimal`, PostgreSQL `NUMERIC`.
* **Decision**: Store all prices, transaction amounts, and refund values as `BIGINT` minor currency units (paise in INR, where 1 INR = 100 paise).
* **Consequences**:
  - Exact integer arithmetic eliminates rounding errors.
  - Standardized alignment with Stripe and Razorpay API standards.

---

### ADR-006: Password Hashing — Argon2id over Bcrypt
* **Status**: Accepted.
* **Context**: Modern GPU and ASIC clusters can crack legacy MD5, SHA-256, and under-tuned Bcrypt hashes at low cost.
* **Alternatives Evaluated**: PBKDF2, Bcrypt, Scrypt.
* **Decision**: Use Argon2id with memory cost $m=65536$ KiB (64 MiB), time cost $t=3$, parallelism $p=4$.
* **Consequences**:
  - Highly resistant to GPU/ASIC brute-force cracking.
  - Defends against side-channel timing attacks.

---

### ADR-007: Federated Authentication — Google OIDC Token Exchange
* **Status**: Accepted.
* **Context**: Traditional OAuth authorization-code redirects require complex multi-hop browser redirects and cookie state tracking.
* **Alternatives Evaluated**: Full-page OAuth redirect dance, Passport.js proxy.
* **Decision**: Frontend integrates Google Identity Services SDK and transmits verified Google `id_token` JWTs to `POST /api/v1/auth/oauth/google`. Backend verifies token against Google JWKS public certs.
* **Consequences**:
  - Seamless one-tap sign-in UX without full-page reloads.
  - Cryptographically robust server-side signature verification.

---

### ADR-008: Feature Access Gating — Mandatory Email Verification
* **Status**: Accepted.
* **Context**: Disposable or mistyped emails prevent delivery of course receipts, certificates, and password resets.
* **Alternatives Evaluated**: Optional verification, soft banner reminders.
* **Decision**: Unverified student accounts are blocked from accessing paid lessons, quizzes, assignments, and checkout.
* **Consequences**:
  - Guarantees high-reputation student communications.
  - Prevents credential stuffing with unmonitored email addresses.

---

### ADR-009: File Ingestion — Direct Presigned Uploads to Cloudflare R2 / S3
* **Status**: Accepted.
* **Context**: Uploading multi-gigabyte video files through the application server exhausts server RAM, occupies worker threads, and degrades API latency.
* **Alternatives Evaluated**: Chunked multipart upload through FastAPI endpoints.
* **Decision**: Backend issues short-lived presigned PUT URLs (15-minute TTL) allowing clients to upload binary data directly to object storage.
* **Consequences**:
  - Zero application server memory or network load during uploads.
  - Enforces MIME whitelist and size limits before issuing upload URLs.

---

### ADR-010: Video Delivery — HLS Adaptive Bitrate with Signed URL Tokens
* **Status**: Accepted.
* **Context**: Direct MP4 file links allow students to download complete video files with one click, enabling piracy and unauthorized distribution.
* **Alternatives Evaluated**: Public S3 video streaming, DRM (Widevine/FairPlay).
* **Decision**: Videos are transcoded into HTTP Live Streaming (HLS) multi-resolution segments. Backend generates short-lived HMAC-signed playback tokens (2-hour TTL) tied to student enrollment.
* **Consequences**:
  - Prevents casual video downloading and direct link sharing.
  - Adaptive resolution switching provides smooth playback across devices.

---

### ADR-011: Assessment Integrity — Server-Authoritative Quiz Timers
* **Status**: Accepted.
* **Context**: Client-side countdown timers can be manipulated by altering local system clocks or pausing browser execution.
* **Alternatives Evaluated**: Client-reported duration elapsed.
* **Decision**: The backend records `started_at = NOW()` upon quiz attempt initiation. The absolute deadline is calculated on the server (`started_at + time_limit_minutes + 30s grace window`).
* **Consequences**:
  - Client clock modifications have zero impact on evaluation.
  - Network jitter is accounted for via the 30-second server grace period.

---

### ADR-012: Asynchronous Delivery — Transactional Outbox Pattern
* **Status**: Accepted.
* **Context**: Direct HTTP calls to third-party email providers (Resend/SendGrid) inside database transactions create dual-write failures if external APIs time out.
* **Alternatives Evaluated**: Celery with Redis broker, background threads in FastAPI.
* **Decision**: All transactional emails and webhooks are inserted into the `notification_outbox` table within the same atomic database transaction as the business event. A dedicated worker polls using `FOR UPDATE SKIP LOCKED`.
* **Consequences**:
  - Zero dual-write failures; guaranteed at-least-once message dispatch.
  - Built-in exponential backoff and dead-letter queue handling.

---

### ADR-013: Security Auditing — Database-Level Immutable Audit Logs
* **Status**: Accepted.
* **Context**: Administrative accounts or compromised application layers could alter audit records to conceal fraudulent or malicious activity.
* **Alternatives Evaluated**: Application-level log-only auditing, third-party SIEM.
* **Decision**: The `audit_logs` table disallows `UPDATE`, `DELETE`, and `TRUNCATE` operations via PostgreSQL permission revocation and an immutable database trigger.
* **Consequences**:
  - Non-repudiation and forensic integrity guaranteed at the persistence tier.
  - Super Admins have read-only inspection access.

---

### ADR-014: Curriculum Sequencing — Optimistic Concurrency Control
* **Status**: Accepted.
* **Context**: Multiple administrators editing curriculum hierarchy simultaneously could cause sort order interleaving and lost updates.
* **Alternatives Evaluated**: Pessimistic screen locking (exclusive course checkout).
* **Decision**: Drag-and-drop reordering requests transmit a `version_timestamp`. If the revision's `updated_at` is newer than the client's timestamp, the API rejects the request with HTTP `409 Conflict`.
* **Consequences**:
  - Prevents accidental overwrites during concurrent curriculum edits.
  - Prompts frontend client to reload latest curriculum tree before retrying.
