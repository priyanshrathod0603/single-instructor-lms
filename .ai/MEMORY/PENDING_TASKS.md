# Project Backlog & Pending Engineering Tasks

This backlog translates the implementation sequence from `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 15–16] into structured, actionable engineering tasks.

Status Taxonomy:
* `NOT_STARTED`: Ready to be scheduled once dependencies clear.
* `IN_PROGRESS`: Actively under development.
* `BLOCKED`: Awaiting prerequisite task, decision, or credential.
* `NEEDS_VERIFICATION`: Requires review or validation before proceeding.

---

## Phase 0: Project Baseline & Technical Decisions Setup

### TASK-PH0-001: Reconcile Backend & Frontend Framework Choices
* **Module**: Architecture & Infrastructure
* **Description**: Confirm selection of backend framework (FastAPI approved as DEC-008) and frontend setup (Next.js / TypeScript) with project owner.
* **Priority**: `CRITICAL`
* **Dependencies**: None
* **Related Requirements**: DEC-PEND-01, DEC-008
* **Suggested Phase**: Phase 0
* **Current Status**: `COMPLETED`
* **Acceptance Criteria**: Owner approval recorded in `.ai/MEMORY/DECISIONS.md`. FastAPI approved; 24 backend architecture design documents created in `docs/backend/`. Implementation roadmap defined in `docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md` (Parts 0 through 9).

### TASK-PH0-002: Cloud Providers & Video Delivery Strategy Confirmation
* **Module**: Media & Storage
* **Description**: Select cloud object storage (AWS S3 vs Cloudflare R2 vs GCS) and video streaming provider (Cloudflare Stream, Mux, or MediaConvert).
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH0-001
* **Related Requirements**: REQ-MED-001, DEC-PEND-02, DEC-PEND-10
* **Suggested Phase**: Phase 0
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Selected provider signed off in decision register.

### TASK-PH0-003: Payment Gateway & Commerce Policy Confirmation
* **Module**: Commerce
* **Description**: Confirm Razorpay credentials structure, webhook secrets rotation, and tax/refund business rules.
* **Priority**: `HIGH`
* **Dependencies**: None
* **Related Requirements**: REQ-COM-001, DEC-PEND-05, DEC-PEND-09
* **Suggested Phase**: Phase 0
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Commerce policies documented in decision register.

---

## Phase 1: Identity, RBAC, Single-Session & Super Admin Bootstrap

### TASK-PH1-001: PostgreSQL Database Initialization & Core Schemas
* **Module**: Database
* **Description**: Initialize PostgreSQL with UUID extension, `CITEXT`, and core tables: `users`, `external_identities`, `roles`, `permissions`, `role_permissions`, `user_role_grants`, `user_permission_overrides`, `auth_sessions`, `login_events`, and `audit_logs` [Source: LMS Blueprint v2.0, Pages 8–11].
* **Priority**: `CRITICAL`
* **Dependencies**: TASK-PH0-001
* **Related Requirements**: REQ-AUTH-001, REQ-GOV-002, REQ-GOV-004
* **Suggested Phase**: Phase 1
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Migrations run cleanly; partial unique index on `auth_sessions(user_id) WHERE status='ACTIVE'` is verified.

### TASK-PH1-002: Student Registration & Authentication Engine
* **Module**: Authentication
* **Description**: Implement `POST /api/v1/auth/signup`, `POST /api/v1/auth/login`, and `POST /api/v1/auth/logout`. Enforce that signup creates `Student` role exclusively [Source: LMS Blueprint v2.0, Pages 8, 11].
* **Priority**: `CRITICAL`
* **Dependencies**: TASK-PH1-001
* **Related Requirements**: REQ-AUTH-001, REQ-AUTH-002
* **Suggested Phase**: Phase 1
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Passwords hashed securely; HttpOnly cookies issued; unverified accounts prompted for verification.

### TASK-PH1-003: Atomic Single-Active-Session Enforcement
* **Module**: Authentication & Security
* **Description**: Implement atomic transaction for login with row lock (`FOR UPDATE`), revoking old session with `revoke_reason='NEW_LOGIN'` and bumping `auth_version` [Source: LMS Blueprint v2.0, Page 8].
* **Priority**: `CRITICAL`
* **Dependencies**: TASK-PH1-002
* **Related Requirements**: REQ-AUTH-002
* **Suggested Phase**: Phase 1
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Simultaneous parallel logins leave exactly one active session; displaced device receives `401 SESSION_REVOKED`.

### TASK-PH1-004: Google OIDC Authentication Integration
* **Module**: Authentication
* **Description**: Implement `POST /api/v1/auth/google` exchanging authorization code for verified Google identity and mapping to `external_identities` [Source: LMS Blueprint v2.0, Pages 8, 11].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH1-002
* **Related Requirements**: REQ-AUTH-003
* **Suggested Phase**: Phase 1
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Verified Google subject maps uniquely; creates `Student` role; enforces single-active-session invariant.

### TASK-PH1-005: Super Admin CLI & Initial Seed Bootstrap
* **Module**: Super Admin & Governance
* **Description**: Create CLI command/script to bootstrap the initial Super Admin account and seed system roles and permission keys [Source: LMS Blueprint v2.0, Pages 3, 7, 9].
* **Priority**: `CRITICAL`
* **Dependencies**: TASK-PH1-001
* **Related Requirements**: REQ-GOV-002
* **Suggested Phase**: Phase 1
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Super Admin account seeded; system roles cannot be deleted; last Super Admin protection active.

### TASK-PH1-006: Granular RBAC Evaluation Middleware
* **Module**: Security & Governance
* **Description**: Build authorization middleware checking user active status, session validity, exact permission key, record scope, and audit logging [Source: LMS Blueprint v2.0, Page 3].
* **Priority**: `CRITICAL`
* **Dependencies**: TASK-PH1-003
* **Related Requirements**: REQ-GOV-002, REQ-GOV-004
* **Suggested Phase**: Phase 1
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Deny-overrides-allow enforced; all unauthorized attempts return `403 FORBIDDEN`.

---

## Phase 2: Catalog, Course Builder, Media Pipeline & Player

### TASK-PH2-001: Course & Curriculum Database Schema
* **Module**: Course Builder
* **Description**: Implement schema and migrations for `courses`, `course_revisions`, `course_sections`, `lessons`, and `assets` [Source: LMS Blueprint v2.0, Page 9].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH1-001
* **Related Requirements**: REQ-CRS-001, REQ-CRS-002
* **Suggested Phase**: Phase 2
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Referential integrity and unique constraints (`UNIQUE(revision_id, position)`) pass validation.

### TASK-PH2-002: Course Authoring & Revision Management API
* **Module**: Course Builder
* **Description**: Implement CRUD endpoints for courses, draft revisions, sections, and lessons under `/api/v1/admin/courses` [Source: LMS Blueprint v2.0, Pages 12–13].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH2-001, TASK-PH1-006
* **Related Requirements**: REQ-CRS-001, REQ-CRS-002
* **Suggested Phase**: Phase 2
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Editing published course creates new draft revision; published snapshot remains immutable.

### TASK-PH2-003: Atomic Curriculum Reordering Endpoint
* **Module**: Course Builder
* **Description**: Implement `PATCH /api/v1/admin/courses/:id/curriculum/order` with version-checked optimistic concurrency [Source: LMS Blueprint v2.0, Page 5].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH2-002
* **Related Requirements**: REQ-CRS-003
* **Suggested Phase**: Phase 2
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Version conflicts return `409 CURRICULUM_VERSION_CONFLICT`; valid reorder commits atomically.

### TASK-PH2-004: Direct Presigned Asset Upload & Transcoding Pipeline
* **Module**: Media Pipeline
* **Description**: Implement `POST /api/v1/admin/assets/upload-intents` and completion webhooks for video and PDF processing [Source: LMS Blueprint v2.0, Pages 5, 12, 14].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH0-002, TASK-PH2-001
* **Related Requirements**: REQ-MED-001, REQ-MED-002
* **Suggested Phase**: Phase 2
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Files stream directly to private storage; MIME/magic bytes validated; only `READY` assets can be attached to published lessons.

### TASK-PH2-005: Student Course Player & Progress Tracker
* **Module**: Student Portal
* **Description**: Build player route `/learn/:courseId/:lessonId` and endpoints `GET /student/lessons/:id/playback` and `PATCH /student/lessons/:id/progress` [Source: LMS Blueprint v2.0, Pages 4, 12].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH2-004
* **Related Requirements**: REQ-STU-002, REQ-STU-003, REQ-STU-004
* **Suggested Phase**: Phase 2
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Playback tokens are short-lived; progress persists in `lesson_progress`; un-enrolled students are blocked.

---

## Phase 3: Checkout, Webhooks, Enrollment, Orders & Refunds

### TASK-PH3-001: Orders, Payments & Coupons Schema
* **Module**: Commerce
* **Description**: Create tables for `orders`, `order_items`, `payments`, `payment_webhook_events`, `refunds`, `coupons`, and `coupon_redemptions` [Source: LMS Blueprint v2.0, Pages 10–11].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH1-001, TASK-PH2-001
* **Related Requirements**: REQ-COM-001, REQ-COM-002, REQ-COM-003
* **Suggested Phase**: Phase 3
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Amounts stored as `BIGINT` paise; foreign key cascades set to `RESTRICT`.

### TASK-PH3-002: Checkout Intent & Order Creation API
* **Module**: Commerce
* **Description**: Implement `POST /api/v1/checkout/orders` to calculate pricing, validate coupons, create pending orders, and issue Razorpay payment intent [Source: LMS Blueprint v2.0, Page 13].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH3-001
* **Related Requirements**: REQ-COM-001
* **Suggested Phase**: Phase 3
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Server calculates price authoritatively; client amount tampering is impossible.

### TASK-PH3-003: Idempotent Razorpay Webhook Handler
* **Module**: Commerce
* **Description**: Implement `POST /api/v1/webhooks/razorpay` validating HMAC signature and executing atomic payment update, enrollment creation, and audit logging [Source: LMS Blueprint v2.0, Pages 11, 14].
* **Priority**: `CRITICAL`
* **Dependencies**: TASK-PH3-002
* **Related Requirements**: REQ-COM-002
* **Suggested Phase**: Phase 3
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Duplicate webhooks return 200 without creating duplicate enrollments; client redirect never grants access.

### TASK-PH3-004: Audited Refund Processing API
* **Module**: Commerce
* **Description**: Implement `POST /api/v1/admin/payments/:id/refund` checking cumulative refund amounts, triggering gateway refund, revoking enrollment, and writing audit log [Source: LMS Blueprint v2.0, Pages 11, 13, 14].
* **Priority**: `MEDIUM`
* **Dependencies**: TASK-PH3-003
* **Related Requirements**: REQ-COM-003
* **Suggested Phase**: Phase 3
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Cumulative refund cannot exceed captured payment; enrollment revoked immediately.

---

## Phase 4: Assignments, Rubric Grading & Overrides

### TASK-PH4-001: Assignment & Rubric Schemas
* **Module**: Assignments
* **Description**: Implement database tables for `assignments`, `rubrics`, `rubric_criteria`, `assignment_submissions`, `submission_files`, `grades`, and `grade_criterion_scores` [Source: LMS Blueprint v2.0, Page 10].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH2-001
* **Related Requirements**: REQ-ASN-001, REQ-ASN-002, REQ-ASN-003
* **Suggested Phase**: Phase 4
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Criteria point totals match assignment max points; submission versioning supported.

### TASK-PH4-002: Student Assignment Submission Workflow
* **Module**: Assignments
* **Description**: Implement draft autosave, file attachment with anti-malware verification, and final submission with `Idempotency-Key` [Source: LMS Blueprint v2.0, Pages 6, 11, 12].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH4-001
* **Related Requirements**: REQ-ASN-002
* **Suggested Phase**: Phase 4
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Server clock determines `is_late` flag; submission snapshots active rubric; attempts tracked atomically.

### TASK-PH4-003: Staff Rubric Grading Queue & Grade Release
* **Module**: Assignments & Grading
* **Description**: Implement `/staff/reviews/:id` UI and APIs for scoring rubric criteria, saving drafts, and releasing immutable grades [Source: LMS Blueprint v2.0, Pages 6, 13].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH4-002
* **Related Requirements**: REQ-ASN-003
* **Suggested Phase**: Phase 4
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Feedback separated from internal notes; grade release publishes outbox notification; grade overrides audited.

---

## Phase 5: Quizzes, Question Bank, Randomization & Results

### TASK-PH5-001: Quiz & Question Bank Schemas
* **Module**: Quizzes
* **Description**: Create tables: `quizzes`, `quiz_revisions`, `question_bank_questions`, `question_options`, `quiz_question_pool`, `quiz_attempts`, `quiz_attempt_questions`, and `quiz_answers` [Source: LMS Blueprint v2.0, Page 10].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH2-001
* **Related Requirements**: REQ-QZ-001, REQ-QZ-002
* **Suggested Phase**: Phase 5
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Foreign keys configured; GIN index on question tags; unique attempt order.

### TASK-PH5-002: CSV Question Import Engine
* **Module**: Quizzes
* **Description**: Implement CSV parsing, row-level validation, conflict preview, and transactional ingestion into question bank [Source: LMS Blueprint v2.0, Pages 7, 13, 14].
* **Priority**: `MEDIUM`
* **Dependencies**: TASK-PH5-001
* **Related Requirements**: REQ-QZ-003
* **Suggested Phase**: Phase 5
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Rejected rows returned with line number and specific error code; partial failures handled cleanly.

### TASK-PH5-003: Cheat-Resistant Quiz Attempt Engine & Server Timer
* **Module**: Quizzes
* **Description**: Implement `POST /student/quizzes/:id/attempts` (snapshots randomized questions/options) and `PUT /student/attempts/:id/answers/:qid` with server-authoritative timer [Source: LMS Blueprint v2.0, Pages 7, 12, 14].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH5-001
* **Related Requirements**: REQ-QZ-004
* **Suggested Phase**: Phase 5
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Answers after timer expiry rejected; answers autosave with revision counters; answers hidden until release.

---

## Phase 6: Dashboards, Governance, Operations & Launch Hardening

### TASK-PH6-001: Super Admin Access Governance & Staff Invites
* **Module**: Super Admin
* **Description**: Build `/control/staff` and `/control/permissions` for inviting staff, granting scoped permissions, and revoking credentials [Source: LMS Blueprint v2.0, Pages 3, 7, 13].
* **Priority**: `HIGH`
* **Dependencies**: TASK-PH1-005, TASK-PH1-006
* **Related Requirements**: REQ-GOV-001, REQ-GOV-002
* **Suggested Phase**: Phase 6
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: 48h invitation token hash stored; last Super Admin protection active; all changes audited.

### TASK-PH6-002: Transactional Outbox Worker & Notifications
* **Module**: Operations
* **Description**: Build background processor to poll `notifications` table and deliver transactional emails with deduplication keys [Source: LMS Blueprint v2.0, Pages 11, 14].
* **Priority**: `MEDIUM`
* **Dependencies**: TASK-PH1-001
* **Related Requirements**: REQ-OPS-001
* **Suggested Phase**: Phase 6
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: Exponential backoff on provider failure; dead-letter queue for exhausted retries.

### TASK-PH6-003: Production Security Hardening & Penetration Testing
* **Module**: Testing & Security
* **Description**: Execute automated security test matrix: IDOR, CSRF, XSS, SQL injection, session races, secret masking, and backup recovery [Source: LMS Blueprint v2.0, Page 15].
* **Priority**: `CRITICAL`
* **Dependencies**: All previous phases
* **Related Requirements**: REQ-AUTH-002, REQ-GOV-004, REQ-OPS-002
* **Suggested Phase**: Phase 6
* **Current Status**: `NOT_STARTED`
* **Acceptance Criteria**: 100% pass on security test matrix; zero high-severity findings.
