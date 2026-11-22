# Backend Engineering Rules & Service Integrity (BACKEND_RULES)

## 1. Backend Architectural Baseline & Service Layer

This document governs all server-side logic, controllers, domain services, background workers, transaction management, and third-party integrations for the Single-Instructor LMS.

All backend code must strictly adhere to the universal directives in [.ai/RULES/GLOBAL_RULES.md](file:///Users/priyansh/lms/.ai/RULES/GLOBAL_RULES.md) and database invariants in [.ai/RULES/DATABASE_RULES.md](file:///Users/priyansh/lms/.ai/RULES/DATABASE_RULES.md).

---

## 2. Core Architectural & Code Modification Rules

### Clean Service Boundary
* **Controllers / Endpoints**: Responsible solely for request parsing, session authentication, permission verification, schema validation, and returning standardized HTTP responses.
* **Domain Services**: Encapsulate all business rules, calculations, state machine transitions, and database transactions.
* **Data Access / Repository Layer**: Encapsulates raw SQL queries or ORM models.

### Modification Restrictions:
* **NEVER** modify a business rule, validation threshold, or security check merely to make an implementation easier or bypass an edge-case failure.
* **NEVER** execute long-running operations (transcoding, PDF parsing, bulk CSV imports, email delivery) synchronously inside HTTP request threads.
* **NEVER** swallow exceptions with bare `except:` or `catch(e) {}` blocks. Always log structured context with error codes.

---

## 3. Critical LMS Business Workflows & Invariants

The backend must rigorously enforce and protect the following 10 domain workflows [Source: LMS Blueprint v2.0]:

### 1. Course Revision Immutability [Page 5]
* Published course revisions are strictly immutable.
* Any modification to a published course MUST create a new draft revision (`revision_no = N + 1`).
* Enrolled students must remain attached to the published revision snapshot until an explicit cutover.

### 2. Atomic Curriculum Reordering [Page 5]
* Curriculum reordering (`PATCH /api/v1/admin/courses/:id/curriculum/order`) must accept an optimistic `version` parameter.
* Execute reordering inside an atomic transaction; if version conflicts occur, return `409 CURRICULUM_VERSION_CONFLICT`.
* Validate that all section and lesson IDs belong strictly to the target revision and positions are contiguous and unique.

### 3. Server-Authoritative Paid Enrollment [Pages 2, 11, 14]
* Paid course access is granted **ONLY** upon verified payment gateway webhook execution.
* **NEVER** grant enrollment based on client browser redirection or client-supplied status flags.
* Webhook processing must be fully idempotent: verify HMAC signature, check `provider_event_id` uniqueness, lock the order, update payment, insert enrollment, and write audit log in a single transaction [Source: LMS Blueprint v2.0, Page 11].

### 4. Financial Precision & Minor Units [Pages 5, 8, 10]
* All monetary values must be stored and calculated as `BIGINT` in minor currency units (e.g., paise for INR: ₹499.00 = `49900`).
* Floating-point calculations for prices, order totals, or refund balances are strictly prohibited.

### 5. Audited Refund Boundaries [Pages 11, 14]
* Cumulative successful refunds for an order can **NEVER** exceed the captured payment amount.
* Executing a refund requires an atomic revocation of the student's course enrollment and an immutable audit log entry.

### 6. Assignment Attempt & Deadline Invariants [Pages 5–6, 11]
* Submission deadlines are evaluated server-side using UTC timestamps. Late submissions must be flagged `is_late = true` based on the server clock.
* Submissions beyond `max_attempts` must be rejected at the service layer.
* Submissions must snapshot the active rubric (`rubric_snapshot` JSONB) to guarantee evaluation integrity.

### 7. Versioned Rubric Grading & Audited Overrides [Page 6]
* Graders score criteria individually; total points are computed server-side with bounds checking against `max_points`.
* Saving a draft grade does not release it to the student. Grade release is immutable and publishes a deduplicated transactional outbox notification.
* Overriding a released grade requires `assignments.override_grade`, records before/after scores, requires a mandatory justification reason, and writes an audit log.

### 8. Cheat-Resistant Quiz Engine & Authoritative Timer [Pages 6–7, 14]
* Quiz timers are server-authoritative (`started_at + duration_seconds`). Client timer displays are purely decorative.
* Any quiz answer received after `expires_at` must be rejected server-side.
* Question and option order must be randomized at attempt initialization using cryptographically secure random generators, and snapshotted in `quiz_attempt_questions`.
* Correct answers and explanations must **NEVER** appear in quiz attempt payloads until official release.

### 9. Learning Progress Tracking [Page 9]
* Track progress seconds and last position. Validate that `progress_seconds >= 0` and `progress_seconds <= lesson.duration_seconds`.
* Mark lesson `COMPLETED` only when the watch threshold defined in `completion_rule` is reached.

### 10. Atomic Single-Active-Session Revocation [Page 8]
* Enforce at most one `ACTIVE` row per user in `auth_sessions`.
* A new login transaction must execute:
  1. `SELECT id FROM users WHERE id = :uid FOR UPDATE;`
  2. `UPDATE auth_sessions SET status = 'REVOKED', revoked_at = NOW(), revoke_reason = 'NEW_LOGIN' WHERE user_id = :uid AND status = 'ACTIVE';`
  3. `INSERT INTO auth_sessions ... VALUES (..., 'ACTIVE', ...);`
  4. `UPDATE users SET auth_version = auth_version + 1 WHERE id = :uid;`
  5. `COMMIT;`
* Issue the session cookie strictly after commit. Previous session gets `401 SESSION_REVOKED`.

---

## 4. Concurrency, Locking & Race Condition Defenses

1. **Row-Level Locking (`FOR UPDATE`)**:
   * Must be used when checking attempt counters, executing payments, updating inventory/pool quotas, and revoking sessions.
2. **Partial Unique Indexes**:
   * Enforced in PostgreSQL: `CREATE UNIQUE INDEX ... ON auth_sessions(user_id) WHERE status='ACTIVE'`.
3. **Idempotency Keys**:
   * State-changing endpoints (`POST /checkout/orders`, `POST /admin/payments/:id/refund`, `POST /student/submissions/:id/submit`, `POST /student/attempts/:id/submit`) must enforce unique request keys to eliminate double-submission bugs.

---

## 5. Background Workers & Transactional Outbox Pattern

* **Outbox Pattern for External Side Effects**:
  * Emails, push notifications, and analytics events must be written to a `notifications` or `events` table inside the same database transaction as the business event.
  * Dedicated background workers (e.g., Celery) poll and deliver messages with automatic retries and exponential backoff.
* **Worker Idempotency**:
  * Every background job must check a unique task/event key (`dedupe_key`) before processing to prevent duplicate processing on worker restarts.
  * Dead-letter queues must be configured for tasks failing after max retries.

---

## 6. Verification & Logging Standards

* **Structured Logging**:
  * Output all server logs as JSON containing `request_id`, `actor_id`, `action`, `resource`, `status_code`, and `duration_ms`.
  * **Zero Secret Leakage**: Automatically redact passwords, tokens, cardholder data, and webhook HMAC secrets from all logs.
* **Standard Error Responses**:
  * All controller exceptions must format errors using `{error: {code, message, details, request_id}}` [Source: LMS Blueprint v2.0, Page 14].
