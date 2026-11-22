# Phase 1 Backend Development Roadmap (Part 0 to Part 9)

## 1. Roadmap Architecture & Execution Directives

This document defines the 10-part implementation sequence for the Single-Instructor LMS backend.

### 1.1 Non-Negotiable Sequencing Rules
1. **Strictly Sequential**: No Part may commence until the preceding Part passes all automated tests and achieves formal completion sign-off.
2. **Atomic Verification**: Every individual task (`PHASE1-PARTX-TASKXXX`) must include automated unit, integration, and security tests.
3. **No Premature Coding**: The current stage is pure architecture design; application implementation begins only after owner approval.

---

## 2. Comprehensive 10-Part Breakdown

### Part 0 — Backend Foundation & Infrastructure

* **Goal**: Establish the core runtime, database connectivity, configuration parsing, logging, and base model abstractions.

#### Tasks:
* `PHASE1-PART0-TASK001`: Initialize Configuration & Environment Parsing
  - **Files**: `app/core/config.py`, `.env.example`
  - **Dependencies**: None
  - **Acceptance Criteria**: Pydantic Settings validates all required variables (`DATABASE_URL`, `SECRET_KEY`, `RAZORPAY_*`, `CORS_ORIGINS`); raises clear error on missing required values.
* `PHASE1-PART0-TASK002`: Set Up SQLAlchemy 2.0 Engine & Connection Pooling
  - **Files**: `app/core/database.py`, `app/models/base.py`
  - **Dependencies**: `TASK001`
  - **Acceptance Criteria**: DeclarativeBase with UUIDv4 primary key and UTC `created_at`/`updated_at` mixins; connection pool health checked.
* `PHASE1-PART0-TASK003`: Configure Alembic Migration Pipeline
  - **Files**: `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`
  - **Dependencies**: `TASK002`
  - **Acceptance Criteria**: `alembic upgrade head` and `alembic check` run with zero configuration errors.
* `PHASE1-PART0-TASK004`: Implement Structured JSON Logger & Request ID Middleware
  - **Files**: `app/core/logging.py`, `app/main.py`
  - **Dependencies**: `TASK001`
  - **Acceptance Criteria**: Every incoming HTTP request assigns a unique `request_id` propagated across logs and response headers.
* `PHASE1-PART0-TASK005`: Implement Unified Error Envelope Handlers
  - **Files**: `app/core/exceptions.py`, `app/core/error_handlers.py`
  - **Dependencies**: `TASK004`
  - **Acceptance Criteria**: 4xx/5xx exceptions return standard JSON `{success: false, error: {...}}` without leaking stack traces.
* `PHASE1-PART0-TASK006`: Implement Liveness & Readiness Probes
  - **Files**: `app/api/v1/health.py`
  - **Dependencies**: `TASK002`
  - **Acceptance Criteria**: `GET /api/v1/health/live` returns 200; `GET /api/v1/health/ready` verifies PostgreSQL connection.
* `PHASE1-PART0-TASK007`: Implement Immutable Audit Log Persistence & DB Triggers
  - **Files**: `app/models/audit_log.py`, `app/repositories/audit_repo.py`, `app/services/audit_service.py`
  - **Dependencies**: `TASK002`
  - **Acceptance Criteria**: Append-only `audit_logs` table created; PostgreSQL trigger `trg_audit_logs_prevent_mutation` raises exception on UPDATE/DELETE; application role permissions restricted.
* `PHASE1-PART0-TASK008`: Implement Transactional Outbox Engine & Worker
  - **Files**: `app/models/notification.py`, `app/repositories/notification_repo.py`, `app/workers/outbox_worker.py`
  - **Dependencies**: `TASK002`
  - **Acceptance Criteria**: `notification_outbox` table initialized; worker polls pending tasks using `FOR UPDATE SKIP LOCKED`; exponential backoff with dead-letter queue on $\ge 5$ failures.

---

### Part 1 — Authentication & Session Management

* **Goal**: Implement zero-trust authentication, Argon2id hashing, Google OIDC token verification, and the Single-Active-Session invariant.

#### Tasks:
* `PHASE1-PART1-TASK101`: Implement Password Hashing & Security Utilities
  - **Files**: `app/core/security.py`, `tests/unit/test_security.py`
  - **Dependencies**: `PART 0`
  - **Acceptance Criteria**: Argon2id hashes passwords with $m=65536, t=3, p=4$; constant-time token comparison passes tests.
* `PHASE1-PART1-TASK102`: Create User, Session & Token Models
  - **Files**: `app/models/user.py`, `app/models/auth_session.py`, `app/models/auth_token.py`
  - **Dependencies**: `TASK101`
  - **Acceptance Criteria**: Partial unique index on `auth_sessions(user_id) WHERE status='ACTIVE'`; migrations generate cleanly.
* `PHASE1-PART1-TASK103`: Implement Single-Active-Session Repository & Atomic Revocation
  - **Files**: `app/repositories/session_repo.py`, `tests/integration/test_session_repo.py`
  - **Dependencies**: `TASK102`
  - **Acceptance Criteria**: Concurrent logins atomically revoke existing sessions; displaced sessions encounter `SESSION_REVOKED`.
* `PHASE1-PART1-TASK104`: Implement Email/Password Registration & Verification Flow
  - **Files**: `app/services/auth_service.py`, `app/api/v1/auth.py`
  - **Dependencies**: `TASK103`
  - **Acceptance Criteria**: User receives verification token; unverified accounts blocked from learning access.
* `PHASE1-PART1-TASK105`: Implement Google OAuth 2.0 / OIDC Verification Endpoint
  - **Files**: `app/services/auth_service.py`, `app/api/v1/auth.py`
  - **Dependencies**: `TASK104`
  - **Acceptance Criteria**: Valid Google ID token automatically verifies user and issues single-active-session cookie.
* `PHASE1-PART1-TASK106`: Implement Password Reset & Session Invalidation
  - **Files**: `app/services/auth_service.py`, `app/api/v1/auth.py`
  - **Dependencies**: `TASK104`
  - **Acceptance Criteria**: Password reset revokes all prior active sessions across all devices.

---

### Part 2 — User Management & RBAC Permissions

* **Goal**: Implement the 5 roles, granular permission evaluation, staff invitations, and profile administration.

#### Tasks:
* `PHASE1-PART2-TASK201`: Create Role & Permission Database Models
  - **Files**: `app/models/user.py`, `app/core/permissions.py`
  - **Dependencies**: `PART 1`
  - **Acceptance Criteria**: Models for `roles`, `permissions`, `user_roles`, `role_permissions` with seeding migration.
* `PHASE1-PART2-TASK202`: Implement RBAC Dependency Evaluator
  - **Files**: `app/api/deps.py`, `tests/unit/test_permissions.py`
  - **Dependencies**: `TASK201`
  - **Acceptance Criteria**: `require_permissions` evaluates keys with deny-overrides-allow; rejects inactive/suspended accounts.
* `PHASE1-PART2-TASK203`: Implement Staff Invitation & Onboarding Workflow
  - **Files**: `app/services/user_service.py`, `app/api/v1/users.py`
  - **Dependencies**: `TASK202`
  - **Acceptance Criteria**: Admin invites staff; staff member claims token and sets credentials within 48h TTL.
* `PHASE1-PART2-TASK204`: Implement User Directory & Administrative Suspension
  - **Files**: `app/services/user_service.py`, `app/api/v1/users.py`
  - **Dependencies**: `TASK202`
  - **Acceptance Criteria**: Account suspension instantly revokes all active sessions and sets `is_active=False`.
* `PHASE1-PART2-TASK205`: Implement In-App Notification Feed & User Preferences
  - **Files**: `app/api/v1/notifications.py`, `app/services/notification_service.py`
  - **Dependencies**: `TASK201`
  - **Acceptance Criteria**: Authenticated users can list notifications (`GET /notifications`), mark individual notifications read (`PATCH /notifications/{id}/read`), and mark all read.
* `PHASE1-PART2-TASK206`: Implement Super Admin Audit Trail API
  - **Files**: `app/api/v1/audit.py`, `app/services/audit_service.py`
  - **Dependencies**: `TASK202`, `PHASE1-PART0-TASK007`
  - **Acceptance Criteria**: Super Admin query endpoint `GET /api/v1/audit-logs` filters immutable audit events by actor, action, entity type, and date range. Sensitive data masked.

---

### Part 3 — Course Catalog & Versioned Curriculum Builder

* **Goal**: Implement course containers, immutable revision cloning, drag-and-drop reordering with optimistic concurrency, and publishing checklist.

#### Tasks:
* `PHASE1-PART3-TASK301`: Create Course & Revision Models
  - **Files**: `app/models/course.py`, `app/models/curriculum.py`
  - **Dependencies**: `PART 2`
  - **Acceptance Criteria**: `courses`, `course_revisions`, `curriculum_sections`, `curriculum_lessons`, `lesson_resources` models.
* `PHASE1-PART3-TASK302`: Implement Revision Spawning & Deep Hierarchy Cloning
  - **Files**: `app/services/course_service.py`, `app/repositories/course_repo.py`
  - **Dependencies**: `TASK301`
  - **Acceptance Criteria**: Cloning live course generates draft revision `N+1` with full copy of sections/lessons; published snapshot untouched.
* `PHASE1-PART3-TASK303`: Implement Curriculum Drag-and-Drop Reordering with Concurrency Guards
  - **Files**: `app/api/v1/sections.py`, `app/api/v1/lessons.py`
  - **Dependencies**: `TASK302`
  - **Acceptance Criteria**: Bulk reorder updates sort orders; stale version timestamps return HTTP 409 Conflict.
* `PHASE1-PART3-TASK304`: Implement Pre-Flight Publishing Checklist
  - **Files**: `app/services/course_service.py`, `app/api/v1/courses.py`
  - **Dependencies**: `TASK302`
  - **Acceptance Criteria**: `GET /courses/{id}/publish-checklist` validates all 8 publishing rules.
* `PHASE1-PART3-TASK305`: Implement Atomic Publication & JSONB Snapshotting
  - **Files**: `app/services/course_service.py`, `app/api/v1/courses.py`
  - **Dependencies**: `TASK304`
  - **Acceptance Criteria**: Draft revision frozen into JSONB `snapshot`; sets `live_revision_id`; prior live revision archived.

---

### Part 4 — Media Asset Storage & Video Protection

* **Goal**: Implement presigned upload pipeline, video transcode hooks, and signed HLS playback tokens.

#### Tasks:
* `PHASE1-PART4-TASK401`: Create Media Asset Models & Storage Client
  - **Files**: `app/models/media.py`, `app/services/media_service.py`
  - **Dependencies**: `PART 3`
  - **Acceptance Criteria**: Cloudflare R2 / S3 client initializes; `media_assets` model tracks upload and transcode states.
* `PHASE1-PART4-TASK402`: Implement Presigned Upload Intent Endpoint
  - **Files**: `app/api/v1/media.py`, `app/schemas/media.py`
  - **Dependencies**: `TASK401`
  - **Acceptance Criteria**: Validates MIME types and size limits; issues 15-minute presigned PUT URLs.
* `PHASE1-PART4-TASK403`: Implement Secure Signed Playback Token Generator
  - **Files**: `app/api/v1/media.py`, `app/services/media_service.py`
  - **Dependencies**: `TASK401`
  - **Acceptance Criteria**: Verifies student course enrollment before issuing short-lived signed HLS streaming token (2h TTL).
* `PHASE1-PART4-TASK404`: Implement Protected PDF Streaming with Dynamic Watermarking
  - **Files**: `app/api/v1/media.py`, `app/services/media_service.py`
  - **Dependencies**: `TASK401`
  - **Acceptance Criteria**: Streams PDF with learner name, email, and timestamp dynamically stamped across pages.

---

### Part 5 — Commerce, Orders & Payment Reconciliation

* **Goal**: Implement minor-currency order placement, Razorpay gateway integration, and cryptographic webhook reconciliation.

#### Tasks:
* `PHASE1-PART5-TASK501`: Create Order & Transaction Database Models
  - **Files**: `app/models/payment.py`
  - **Dependencies**: `PART 4`
  - **Acceptance Criteria**: `orders`, `payment_transactions`, `refunds` models with `BIGINT` minor units (paise).
* `PHASE1-PART5-TASK502`: Implement Order Initialization with Razorpay API
  - **Files**: `app/services/payment_service.py`, `app/api/v1/orders.py`
  - **Dependencies**: `TASK501`
  - **Acceptance Criteria**: Generates internal order and initiates Razorpay order; prevents duplicate orders if already enrolled.
* `PHASE1-PART5-TASK503`: Implement Cryptographic HMAC Webhook Ingestion & Idempotency
  - **Files**: `app/api/v1/webhooks.py`, `tests/security/test_tamper_webhook.py`
  - **Dependencies**: `TASK502`
  - **Acceptance Criteria**: HMAC-SHA256 signature verified; invalid signatures rejected; duplicate webhooks handled idempotently with row locks.
* `PHASE1-PART5-TASK504`: Implement Refund Authorization & Execution
  - **Files**: `app/services/payment_service.py`, `app/api/v1/orders.py`
  - **Dependencies**: `TASK503`
  - **Acceptance Criteria**: Super Admin authorizes refund; calls Razorpay API; revokes enrollment; logs audit entry.

---

### Part 6 — Student Enrollment & Access Control

* **Goal**: Implement zero-trust webhook-driven enrollment provisioning, manual admin overrides, and access gates.

#### Tasks:
* `PHASE1-PART6-TASK601`: Create Enrollment Database Model
  - **Files**: `app/models/enrollment.py`
  - **Dependencies**: `PART 5`
  - **Acceptance Criteria**: `enrollments` model with `UNIQUE(student_id, course_id)` and status flags.
* `PHASE1-PART6-TASK602`: Wire Webhook Payment Capture to Enrollment Grant
  - **Files**: `app/services/enrollment_service.py`, `app/repositories/enrollment_repo.py`
  - **Dependencies**: `TASK601`
  - **Acceptance Criteria**: Webhook `payment.captured` atomically sets order `PAID` and creates active enrollment record.
* `PHASE1-PART6-TASK603`: Implement Manual Admin Enrollment Grant & Revocation
  - **Files**: `app/api/v1/enrollments.py`
  - **Dependencies**: `TASK602`
  - **Acceptance Criteria**: Admin grants access without payment; revocation terminates student access immediately.
* `PHASE1-PART6-TASK604`: Implement Course Access Dependency Guard
  - **Files**: `app/api/deps.py`
  - **Dependencies**: `TASK602`
  - **Acceptance Criteria**: Route dependency verifies active enrollment before delivering non-preview lesson content.

---

### Part 7 — Assignments & Rubric Grading

* **Goal**: Implement assignment creation, rubric versioning, student file submissions, staff grading, and grade overrides.

#### Tasks:
* `PHASE1-PART7-TASK701`: Create Assignment & Rubric Models
  - **Files**: `app/models/assignment.py`
  - **Dependencies**: `PART 6`
  - **Acceptance Criteria**: `assignments`, `assignment_submissions`, `rubrics`, `rubric_criteria`, `rubric_scores`, `grade_overrides` models.
* `PHASE1-PART7-TASK702`: Implement Student Project Submission Endpoint
  - **Files**: `app/services/assignment_service.py`, `app/api/v1/assignments.py`
  - **Dependencies**: `TASK701`
  - **Acceptance Criteria**: Enrolled student uploads work; enforces due date and late submission policies.
* `PHASE1-PART7-TASK703`: Implement Rubric Grading & Weighted Score Calculation
  - **Files**: `app/services/assignment_service.py`, `app/api/v1/assignments.py`
  - **Dependencies**: `TASK702`
  - **Acceptance Criteria**: Staff awards points per rubric criterion; calculates weighted score; updates submission status.
* `PHASE1-PART7-TASK704`: Implement Super Admin Grade Override & Audit Logging
  - **Files**: `app/api/v1/assignments.py`
  - **Dependencies**: `TASK703`
  - **Acceptance Criteria**: Super Admin overrides finalized grade with mandatory justification recorded in `grade_overrides`.

---

### Part 8 — Quizzes & Question Banks

* **Goal**: Implement quiz configuration, question types, bulk CSV import, server-authoritative timers, and answer autosave.

#### Tasks:
* `PHASE1-PART8-TASK801`: Create Quiz & Question Models
  - **Files**: `app/models/quiz.py`
  - **Dependencies**: `PART 7`
  - **Acceptance Criteria**: `quizzes`, `quiz_questions`, `quiz_question_options`, `quiz_attempts`, `quiz_answers` models.
* `PHASE1-PART8-TASK802`: Implement Bulk CSV Question Bank Importer
  - **Files**: `app/services/quiz_service.py`, `app/api/v1/quizzes.py`
  - **Dependencies**: `TASK801`
  - **Acceptance Criteria**: Parses CSV format, validates options and correct keys, bulk-inserts questions in one transaction.
* `PHASE1-PART8-TASK803`: Implement Server-Authoritative Quiz Timer & Attempt Initiation
  - **Files**: `app/services/quiz_service.py`, `app/api/v1/quizzes.py`
  - **Dependencies**: `TASK801`
  - **Acceptance Criteria**: Sets `started_at = NOW()`; client clock changes cannot alter server deadline.
* `PHASE1-PART8-TASK804`: Implement Incremental Answer Autosave
  - **Files**: `app/api/v1/quizzes.py`
  - **Dependencies**: `TASK803`
  - **Acceptance Criteria**: Periodic autosave UPSERTs selected option IDs into `quiz_answers` without page reload.
* `PHASE1-PART8-TASK805`: Implement Attempt Finalization & Automated Score Calculation
  - **Files**: `app/services/quiz_service.py`, `app/api/v1/quizzes.py`
  - **Dependencies**: `TASK804`
  - **Acceptance Criteria**: Validates submission within deadline (+30s grace); calculates score and evaluates `is_passed`.

---

### Part 9 — Student Progress, Verification & Certification

* **Goal**: Implement video playback heartbeats, course progress summaries, automated certificate generation, and public QR verification.

#### Tasks:
* `PHASE1-PART9-TASK901`: Create Progress & Certificate Models
  - **Files**: `app/models/progress.py`, `app/models/certificate.py`
  - **Dependencies**: `PART 8`
  - **Acceptance Criteria**: `lesson_progress`, `course_progress_summaries`, `certificates` models.
* `PHASE1-PART9-TASK902`: Implement Granular Lesson Progress Heartbeat & Completion Logic
  - **Files**: `app/services/progress_service.py`, `app/api/v1/progress.py`
  - **Dependencies**: `TASK901`
  - **Acceptance Criteria**: Video completes at $\ge 90\%$ watch duration; quizzes complete upon passing; updates materialized summary.
* `PHASE1-PART9-TASK903`: Implement Automated Certificate Issuance Pipeline
  - **Files**: `app/services/certificate_service.py`
  - **Dependencies**: `TASK902`
  - **Acceptance Criteria**: 100% completion automatically computes cryptographic hash and generates verifiable PDF certificate.
* `PHASE1-PART9-TASK904`: Implement Public Certificate Verification Endpoint
  - **Files**: `app/api/v1/certificates.py`
  - **Dependencies**: `TASK903`
  - **Acceptance Criteria**: `GET /api/v1/certificates/verify/{hash}` publicly renders student name, course title, and completion proof.
