# Detailed User Requirements Specification

This document extracts and formalizes every product requirement from `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 1–16].

Status Taxonomy:
* `NOT_STARTED`: Specified but no code exists.
* `IN_PROGRESS`: Currently being implemented.
* `IMPLEMENTED`: Code written but unverified by tests.
* `VERIFIED`: Confirmed by automated test suites.
* `BLOCKED`: Blocked by dependency or architectural decision.
* `NOT_VERIFIED`: Exists in codebase but lacks verification evidence.

---

## 1. Public Website & Storefront (PUB)

### REQ-PUB-001: Public Storefront & Homepage
* **Module**: Public Website
* **Description**: Provide a branded landing page that introduces the instructor, highlights learning outcomes, showcases testimonials, and features published courses.
* **Expected Behaviour**: Visitors see a responsive header with navigation (Courses, About, FAQ, Login/Signup), hero banner with primary CTA, featured course cards, instructor bio, FAQs, and policy footer links [Source: LMS Blueprint v2.0, Page 3].
* **Responsible Role**: Visitor
* **Dependencies**: MOD-03 (Course publishing)
* **Validation Conditions**: Draft or archived courses must never render in public featured lists.
* **Acceptance Criteria**: Desktop and mobile layouts render without horizontal scroll; metric links navigate to target sections; SEO metadata is populated.
* **Source PDF**: Page 3 — Dashboard layouts
* **Status**: `NOT_STARTED`

### REQ-PUB-002: Course Catalogue & Search/Filter
* **Module**: Public Website
* **Description**: Enable prospective students to discover courses via search queries, level filters, and sorting controls.
* **Expected Behaviour**: Route `/courses` renders published courses with cursor pagination, keyword search (`q`), difficulty level filter (`beginner`, `intermediate`, `advanced`), and sorting options [Source: LMS Blueprint v2.0, Pages 4, 12].
* **Responsible Role**: Visitor
* **Dependencies**: Courses table
* **Validation Conditions**: Exclude draft and unpublished courses from search indexes and catalogue responses.
* **Acceptance Criteria**: Search filters update URL query params; pagination maintains search state; empty state displayed when no courses match.
* **Source PDF**: Pages 4, 12 — Route inventory & Public API
* **Status**: `NOT_STARTED`

### REQ-PUB-003: Public Course Details & Curriculum Preview
* **Module**: Public Website
* **Description**: Showcase complete course syllabus, learning outcomes, pricing, and free preview lessons.
* **Expected Behaviour**: Route `/courses/:slug` displays course title, description, instructor profile, pricing in local currency (INR default), syllabus outline, and previews for designated preview lessons without requiring login [Source: LMS Blueprint v2.0, Pages 4, 5, 12].
* **Responsible Role**: Visitor
* **Dependencies**: Course revisions, sections, lessons, assets
* **Validation Conditions**: Private lesson assets (non-preview) must never expose stream URLs or storage keys to unauthenticated callers.
* **Acceptance Criteria**: Public syllabus accurately mirrors the latest published course revision snapshot.
* **Source PDF**: Pages 4, 5, 12 — Course builder & API contracts
* **Status**: `NOT_STARTED`

---

## 2. Authentication & Session Management (AUTH)

### REQ-AUTH-001: Public Student Registration
* **Module**: Authentication
* **Description**: Allow visitors to create a student account with email, password, and display name.
* **Expected Behaviour**: Client posts `{email, password, display_name}` to `/api/v1/auth/signup`. System creates a user with `Student` role and sends an email verification link [Source: LMS Blueprint v2.0, Pages 2, 8, 11].
* **Responsible Role**: Visitor
* **Dependencies**: Users, Roles tables
* **Validation Conditions**: Client cannot submit a role parameter; email must be valid format and unique (`CITEXT`); password must meet security complexity rules.
* **Acceptance Criteria**: Role defaults strictly to `Student`. Return 201 with verification requirement message.
* **Source PDF**: Pages 2, 8, 11 — Product baseline & Auth APIs
* **Status**: `NOT_STARTED`

### REQ-AUTH-002: Secure Login & Atomic One-Active-Session Enforcement
* **Module**: Authentication
* **Description**: Authenticate credentials and enforce that an account has at most one active session across all devices.
* **Expected Behaviour**: Upon successful login, the system executes an atomic transaction that revokes any existing `ACTIVE` session with `revoke_reason='NEW_LOGIN'`, increments `auth_version`, inserts a new active session, and sets a Secure, HttpOnly cookie [Source: LMS Blueprint v2.0, Page 8].
* **Responsible Role**: Student, Staff, Admin, Super Admin
* **Dependencies**: Users, Auth Sessions tables, PostgreSQL partial unique index
* **Validation Conditions**: Concurrent logins for the same user must be serialized with row lock (`FOR UPDATE`). Two simultaneous logins must result in exactly one active session.
* **Acceptance Criteria**: The displaced session receives `401 SESSION_REVOKED` on its next protected request and displays: "You signed in on another device" [Source: LMS Blueprint v2.0, Page 8].
* **Source PDF**: Pages 2, 8, 11, 14 — Login security & race handling
* **Status**: `NOT_STARTED`

### REQ-AUTH-003: Google OIDC Authentication
* **Module**: Authentication
* **Description**: Enable one-tap registration and login using verified Google identity.
* **Expected Behaviour**: Client sends `{code, state, verifier}` to `/api/v1/auth/google`. Server exchanges code with Google, maps verified email and subject ID to `external_identities`, creates a user if new, and atomically establishes an active session [Source: LMS Blueprint v2.0, Pages 8, 9, 11].
* **Responsible Role**: Visitor, Student
* **Dependencies**: External Identities table, Google OAuth2 client
* **Validation Conditions**: State parameter must match session state to prevent CSRF. Provider subject must map uniquely.
* **Acceptance Criteria**: Verified Google login creates `Student` role by default; enforces single-active-session invariant.
* **Source PDF**: Pages 8, 9, 11 — External identities & Auth APIs
* **Status**: `NOT_STARTED`

### REQ-AUTH-004: Password Reset & Account Recovery
* **Module**: Authentication
* **Description**: Secure self-service password reset via expiring email tokens.
* **Expected Behaviour**: Submitting email triggers a single-use token with short expiration. Submitting new password updates hash, revokes all active sessions, and increments `auth_version` [Source: LMS Blueprint v2.0, Pages 7, 8, 11].
* **Responsible Role**: All Users
* **Dependencies**: Mailer, Auth Sessions
* **Validation Conditions**: Return generic accepted response to prevent email enumeration. Tokens stored hashed.
* **Acceptance Criteria**: Previous sessions immediately invalidated; user receives notification email.
* **Source PDF**: Pages 7, 8, 11 — Recovery playbook & Auth endpoints
* **Status**: `NOT_STARTED`

### REQ-AUTH-005: Multi-Factor Authentication (MFA)
* **Module**: Authentication
* **Description**: Enforce TOTP-based multi-factor authentication for privileged roles (Staff, Admin, Super Admin).
* **Expected Behaviour**: During login for MFA-enabled accounts, return challenge ID. Issue active session cookie only after valid TOTP code verification [Source: LMS Blueprint v2.0, Pages 7, 8, 11].
* **Responsible Role**: Privileged Roles (Staff, Admin, Super Admin)
* **Dependencies**: MFA secret store, TOTP verification engine
* **Validation Conditions**: Pending MFA challenge must not revoke the currently active session until full authentication succeeds [Source: LMS Blueprint v2.0, Page 8].
* **Acceptance Criteria**: Privileged access blocked without MFA; recovery codes shown once and stored hashed.
* **Source PDF**: Pages 7, 8, 11 — MFA & Recovery
* **Status**: `NOT_STARTED`

---

## 3. Student Learning Experience (STU)

### REQ-STU-001: Student Dashboard Overview
* **Module**: Student
* **Description**: Personalized portal summarizing active enrollments, course progress, pending deadlines, and recent grades.
* **Expected Behaviour**: Route `/app` shows enrolled course count, average progress percentage, "Resume lesson" shortcut, upcoming assignment deadlines, and quiz closing dates [Source: LMS Blueprint v2.0, Pages 3, 4, 12].
* **Responsible Role**: Student
* **Dependencies**: Enrollments, Lesson Progress, Assignments, Quizzes
* **Validation Conditions**: Student views only their own learning data (`user_id = auth.user_id`).
* **Acceptance Criteria**: Metric cards link directly to relevant filtered list views.
* **Source PDF**: Pages 3, 4, 12 — Student home layout & wireframe
* **Status**: `NOT_STARTED`

### REQ-STU-002: Distraction-Free Learning Player
* **Module**: Student
* **Description**: Course viewer providing video streaming, PDF reader, lesson outline, and progress controls.
* **Expected Behaviour**: Route `/learn/:courseId/:lessonId` renders curriculum sidebar, protected video/PDF canvas, personal notes drawer, bookmarking toggle, and "Mark as Complete" button [Source: LMS Blueprint v2.0, Pages 4, 9, 12].
* **Responsible Role**: Student
* **Dependencies**: Entitlements, Assets, Playback Token API
* **Validation Conditions**: Check active enrollment entitlement before issuing short-lived playback token. Raw asset storage URLs must never be exposed to the client [Source: LMS Blueprint v2.0, Page 5].
* **Acceptance Criteria**: Playback token expires within short TTL; playback halts if session is revoked.
* **Source PDF**: Pages 4, 5, 12 — Route inventory & Media workflows
* **Status**: `NOT_STARTED`

### REQ-STU-003: Video Playback & Automatic Progress Tracking
* **Module**: Student
* **Description**: Track playback position in seconds and mark lessons completed based on completion rules.
* **Expected Behaviour**: Client patches position updates to `/api/v1/student/lessons/:id/progress`. When watch duration reaches threshold (e.g., 90%), status updates to `COMPLETED` [Source: LMS Blueprint v2.0, Pages 9, 12].
* **Responsible Role**: Student
* **Dependencies**: `lesson_progress` table
* **Validation Conditions**: `progress_seconds >= 0`, `last_position_seconds <= duration_seconds`.
* **Acceptance Criteria**: Resuming lesson starts playback at `last_position_seconds`.
* **Source PDF**: Pages 9, 12 — Schema & student endpoints
* **Status**: `NOT_STARTED`

### REQ-STU-004: Lesson Notes & Bookmarks
* **Module**: Student
* **Description**: Allow students to take timestamped notes and bookmark critical lessons.
* **Expected Behaviour**: Notes include text body and video timestamp seconds. Bookmarks store a unique toggle per user/lesson [Source: LMS Blueprint v2.0, Pages 9, 12].
* **Responsible Role**: Student
* **Dependencies**: `lesson_notes`, `lesson_bookmarks` tables
* **Validation Conditions**: Student can only create, read, update, or delete their own notes and bookmarks.
* **Acceptance Criteria**: Clicking a note timestamp seeks the video player to that exact second.
* **Source PDF**: Pages 9, 12 — Schema & endpoints
* **Status**: `NOT_STARTED`

### REQ-STU-005: Certificate Verification & Download
* **Module**: Student
* **Description**: Issue a cryptographically verifiable certificate upon complete course fulfillment.
* **Expected Behaviour**: When all mandatory lessons are completed and pass marks achieved, generate a unique certificate with verification hash (`CHAR(64)`), publicly viewable via `/verify/:certificate_number` [Source: LMS Blueprint v2.0, Pages 10, 11, 14].
* **Responsible Role**: Student
* **Dependencies**: Enrollments, Certificates table
* **Validation Conditions**: Generation job must be idempotent; duplicate course completions must not duplicate certificates [Source: LMS Blueprint v2.0, Page 14].
* **Acceptance Criteria**: Certificate verification renders student name, course title, issue date, and validity status.
* **Source PDF**: Pages 10, 11, 14 — Schema & failure scenarios
* **Status**: `NOT_STARTED`

---

## 4. Course Builder & Curriculum Management (CRS)

### REQ-CRS-001: Course Revision Lifecycle
* **Module**: Course Builder
* **Description**: Enforce safe course editing via draft revisions to protect enrolled students from breaking changes.
* **Expected Behaviour**: Lifecycle follows `Draft` -> optional `Review` -> `Published` -> `Unpublished`/`Archived`. Published revisions are immutable; any subsequent edit creates a new draft revision [Source: LMS Blueprint v2.0, Page 5].
* **Responsible Role**: Admin, Super Admin
* **Dependencies**: `courses`, `course_revisions` tables
* **Validation Conditions**: Enrolled students continue consuming the published snapshot until a new revision is explicitly published.
* **Acceptance Criteria**: `UNIQUE(course_id, revision_no)` enforced; database triggers or service rules block updates to published revision rows.
* **Source PDF**: Pages 5, 9 — Course builder & schema
* **Status**: `NOT_STARTED`

### REQ-CRS-002: Sections & Multi-Type Lesson Authoring
* **Module**: Course Builder
* **Description**: Create, edit, duplicate, and archive sections and lessons supporting Video, PDF, Text, Resource, Quiz, and Assignment types.
* **Expected Behaviour**: Admin manages curriculum structure; each lesson defines title, description, visibility, completion rule, duration, and associated asset [Source: LMS Blueprint v2.0, Page 5].
* **Responsible Role**: Admin, Super Admin
* **Dependencies**: `course_sections`, `lessons`, `assets` tables
* **Validation Conditions**: Durations must be non-negative; lesson titles sanitized; text content scrubbed of XSS payloads.
* **Acceptance Criteria**: Draft autosaves with debounced requests, dirty state indicators, and recovery after browser reload [Source: LMS Blueprint v2.0, Page 5].
* **Source PDF**: Pages 5, 9 — Course builder wireframe & schema
* **Status**: `NOT_STARTED`

### REQ-CRS-003: Atomic Drag-and-Drop Curriculum Reordering
* **Module**: Course Builder
* **Description**: Reorder sections and lessons seamlessly using optimistic client UI backed by atomic server validation.
* **Expected Behaviour**: Client sends `PATCH /api/v1/admin/courses/:id/curriculum/order` with `version` and ordered array of section/lesson IDs and positions [Source: LMS Blueprint v2.0, Page 5].
* **Responsible Role**: Admin, Super Admin
* **Dependencies**: `course_revisions`, `course_sections`, `lessons`
* **Validation Conditions**: All IDs must belong to the target revision; positions must be strictly unique; version must match current revision version.
* **Acceptance Criteria**: On conflict (version mismatch), server returns `409 CURRICULUM_VERSION_CONFLICT`; UI restores previous order and prompts for reload [Source: LMS Blueprint v2.0, Pages 5, 14].
* **Source PDF**: Pages 5, 11, 14 — Atomic reorder contract & error handling
* **Status**: `NOT_STARTED`

### REQ-CRS-004: Publish Checklist & Audit Enforcement
* **Module**: Course Builder
* **Description**: Validate all prerequisite criteria before a course can transition to `Published`.
* **Expected Behaviour**: Publishing checks: valid metadata, price and access policy configured, thumbnail attached, at least one section with at least one lesson, and all attached assets in `READY` processing state [Source: LMS Blueprint v2.0, Page 5].
* **Responsible Role**: Admin (if granted `courses.publish`), Super Admin
* **Dependencies**: Publish validation engine, Audit logs
* **Validation Conditions**: Cannot publish if any referenced video/PDF is in `PROCESSING` or `FAILED` state.
* **Acceptance Criteria**: Transition records before/after state, actor ID, timestamp, and audit record in a single transaction.
* **Source PDF**: Pages 5, 11 — Publish checklist & transaction boundaries
* **Status**: `NOT_STARTED`

---

## 5. Protected Media Pipeline (MED)

### REQ-MED-001: Video Upload & Transcoding Pipeline
* **Module**: Media
* **Description**: Upload video assets directly to private cloud storage and initiate transcode processing.
* **Expected Behaviour**: Flow: 1. Request presigned upload intent (`/admin/assets/upload-intents`), 2. Direct client upload to private bucket, 3. Call `/admin/assets/:id/complete`, 4. Validate MIME type, file signature, and size, 5. Asynchronous transcode job triggers, 6. Status transitions to `READY` or `FAILED` [Source: LMS Blueprint v2.0, Pages 5, 14].
* **Responsible Role**: Admin, Super Admin
* **Dependencies**: Storage service, Background transcode worker, Assets table
* **Validation Conditions**: Raw video files must never be publicly readable. Transcode errors must record diagnostics without publishing broken assets.
* **Acceptance Criteria**: Only assets in `READY` state can be attached to published lessons.
* **Source PDF**: Pages 5, 9, 14 — Media workflows & failure scenarios
* **Status**: `NOT_STARTED`

### REQ-MED-002: PDF Protection & Delivery
* **Module**: Media
* **Description**: Store and render PDF documents securely, preventing direct download by default.
* **Expected Behaviour**: PDFs undergo file-signature validation, malware scanning, and size/page cap validation. Delivery occurs via an embedded protected viewer or short-lived signed URLs with download flags disabled by default [Source: LMS Blueprint v2.0, Page 5].
* **Responsible Role**: Admin, Super Admin (upload); Student (view)
* **Dependencies**: Anti-malware scanner, Asset versioning
* **Validation Conditions**: Replacing a PDF creates a new version in `asset_versions`; in-place overwrite is prohibited [Source: LMS Blueprint v2.0, Page 5].
* **Acceptance Criteria**: Referenced PDFs cannot be deleted while attached to active lessons.
* **Source PDF**: Pages 5, 9, 14 — PDF protection & failure handling
* **Status**: `NOT_STARTED`

---

## 6. Assignment System & Rubric Grading (ASN)

### REQ-ASN-001: Assignment Configuration & Late Policies
* **Module**: Assignment System
* **Description**: Define assignment tasks with clear instructions, due dates, submission limits, and rubric criteria.
* **Expected Behaviour**: Admin configures: title, sanitized rich-text instructions, UTC `available_at` and `due_at`, `max_points`, accepted `submission_types` (text, file, URL), `allowed_extensions` allowlist, `max_file_size_bytes`, `max_attempts`, and `late_policy` (`accept`, `reject`, `penalty`) [Source: LMS Blueprint v2.0, Page 5].
* **Responsible Role**: Admin, Super Admin
* **Dependencies**: `assignments`, `rubrics` tables
* **Validation Conditions**: `max_points > 0`; sum of rubric criterion max points must exactly equal assignment `max_points` [Source: LMS Blueprint v2.0, Page 6].
* **Acceptance Criteria**: Due dates display in student's local timezone while stored in UTC.
* **Source PDF**: Pages 5, 6, 10 — Assignment fields & rubrics
* **Status**: `NOT_STARTED`

### REQ-ASN-002: Student Submission Lifecycle & Autosave
* **Module**: Assignment System
* **Description**: Enable students to draft text, attach validated files, and submit assignments within allowed attempt limits.
* **Expected Behaviour**: Draft responses autosave. Final submission locks attempt counter, records server `submitted_at`, flags `is_late` based on server clock, and snapshots current rubric [Source: LMS Blueprint v2.0, Pages 6, 11].
* **State Machine**:
  $$\text{NOT\_SUBMITTED} \longrightarrow \text{DRAFT} \longrightarrow \text{SUBMITTED/LATE} \longrightarrow \text{UNDER\_REVIEW} \longrightarrow \text{GRADED / RETURNED}$$
  $$\text{RETURNED} \longrightarrow \text{RESUBMITTED} \longrightarrow \text{UNDER\_REVIEW}$$
  $$\text{GRADED} \longrightarrow \text{REGRADING\_REQUESTED} \longrightarrow \text{REGRADING} \longrightarrow \text{NEW GRADED VERSION}$$
* **Responsible Role**: Student
* **Dependencies**: `assignment_submissions`, `submission_files` tables
* **Validation Conditions**: All attached files must complete malware/antivirus scan before submission can be finalized [Source: LMS Blueprint v2.0, Pages 10, 14].
* **Acceptance Criteria**: Duplicate clicks on submission are rejected via `Idempotency-Key` header [Source: LMS Blueprint v2.0, Pages 11, 14].
* **Source PDF**: Pages 6, 10, 11, 14 — Submissions & state machine
* **Status**: `NOT_STARTED`

### REQ-ASN-003: Versioned Rubric Grading & Overrides
* **Module**: Assignment System
* **Description**: Provide graders with a structured review queue to score criteria, attach feedback, and release immutable grades.
* **Expected Behaviour**: Graders enter points per criterion. Total score is computed server-side with bounds checking. Graders can save drafts without releasing. Grade release is versioned and triggers a single deduplicated notification [Source: LMS Blueprint v2.0, Page 6].
* **Responsible Role**: Staff (with `assignments.grade`), Admin, Super Admin
* **Dependencies**: `grades`, `grade_criterion_scores`, Outbox notifications
* **Validation Conditions**: Grader feedback is separated from private internal notes. Overriding a released grade requires `assignments.override_grade`, records before/after score, justification reason, and appends to audit log [Source: LMS Blueprint v2.0, Page 6].
* **Acceptance Criteria**: Released grades are immutable; appeals or revisions create a new review record version rather than silently editing past grades.
* **Source PDF**: Pages 6, 10, 11 — Grading interface & overrides
* **Status**: `NOT_STARTED`

---

## 7. Quiz & Assessment Engine (QZ)

### REQ-QZ-001: Quiz Configuration & Attempt Parameters
* **Module**: Quiz System
* **Description**: Build flexible assessments with time limits, passing scores, randomization, and attempt quotas.
* **Expected Behaviour**: Settings include: `time_limit_seconds` (server-authoritative), `available_from`/`until`, `attempt_limit` (>= 1), `pass_mark`, `shuffle_questions`, `shuffle_options`, `question_selection` (`fixed` or `random_pool`), `show_result` policy (`immediate`, `after_close`, `manual`), and optional `negative_marking` [Source: LMS Blueprint v2.0, Page 6].
* **Responsible Role**: Admin, Super Admin
* **Dependencies**: `quizzes`, `quiz_revisions` tables
* **Validation Conditions**: Server validates and enforces `attempt_limit` transactionally [Source: LMS Blueprint v2.0, Pages 6, 11].
* **Acceptance Criteria**: Editing a quiz after attempts exist automatically spawns a new quiz revision; existing attempts stay attached to their original revision [Source: LMS Blueprint v2.0, Page 7].
* **Source PDF**: Pages 6, 10 — Quiz settings & revisions
* **Status**: `NOT_STARTED`

### REQ-QZ-002: Question Bank & Question Authoring
* **Module**: Quiz System
* **Description**: Centralized repository of reusable questions categorized by tag, topic, and difficulty.
* **Expected Behaviour**: Supports single choice, multiple select, true/false, short answer, long answer, and numeric with tolerance. Each question contains sanitized prompt, points, explanation, options, and difficulty [Source: LMS Blueprint v2.0, Pages 6–7].
* **Responsible Role**: Admin, Super Admin
* **Dependencies**: `question_bank_questions`, `question_options` tables
* **Validation Conditions**: Exactly one correct option for single choice; at least one for multiple select; no empty/duplicate option bodies [Source: LMS Blueprint v2.0, Page 7].
* **Acceptance Criteria**: Correct answers and explanations are scrubbed from attempt payloads before official result release [Source: LMS Blueprint v2.0, Page 7].
* **Source PDF**: Pages 6, 7, 10 — Question bank & options
* **Status**: `NOT_STARTED`

### REQ-QZ-003: CSV Bulk Import Engine
* **Module**: Quiz System
* **Description**: Ingest question sets en masse via structured CSV files with validation and collision checks.
* **Expected Behaviour**: Workflow: 1. Upload CSV -> 2. Validate encoding and headers -> 3. Parse rows -> 4. Display preview of valid rows and duplicate conflicts -> 5. Explicit user confirmation -> 6. Transactional database insertion -> 7. Return job ID and detailed rejected-row report [Source: LMS Blueprint v2.0, Page 7].
* **Responsible Role**: Admin, Super Admin
* **Dependencies**: `file_import_jobs` table, Async CSV parser
* **Validation Conditions**: Enforce caps on total rows and file size. Reject malformed rows with line numbers and specific error codes [Source: LMS Blueprint v2.0, Pages 7, 14].
* **Acceptance Criteria**: Partial failure does not corrupt the question bank; non-conflicting rows insert transactionally.
* **Source PDF**: Pages 7, 11, 14 — Bulk import & failure handling
* **Status**: `NOT_STARTED`

### REQ-QZ-004: Quiz Attempts, Server Timer & Autosaved Answers
* **Module**: Quiz System
* **Description**: Deliver secure, cheat-resistant exam attempts with server-side time tracking and network-loss resilience.
* **Expected Behaviour**: Starting an attempt creates immutable question/option snapshots in `quiz_attempt_questions`. Timer is calculated strictly as `started_at + duration`; client clock is purely cosmetic. Answers autosave with revision counters and idempotency keys. On submission, attempt is marked final and subsequent edits are rejected [Source: LMS Blueprint v2.0, Pages 7, 10, 11].
* **Responsible Role**: Student
* **Dependencies**: `quiz_attempts`, `quiz_attempt_questions`, `quiz_answers` tables
* **Validation Conditions**: Answers submitted after timer expiration are rejected server-side [Source: LMS Blueprint v2.0, Pages 7, 14].
* **Acceptance Criteria**: Offline queueing in client preserves unsaved answers and flushes without duplicate revision records on reconnect [Source: LMS Blueprint v2.0, Pages 7, 14].
* **Source PDF**: Pages 7, 10, 11, 14 — Attempts, timer & network resilience
* **Status**: `NOT_STARTED`

---

## 8. Commerce, Payments & Automated Enrollment (COM)

### REQ-COM-001: Integrated Checkout & Order Creation
* **Module**: Commerce
* **Description**: Create pending orders and payment gateway intents for course purchases.
* **Expected Behaviour**: Student initiates checkout; server creates `orders` record (amounts in minor units, e.g. paise), generates unique order number, and returns gateway payment intent [Source: LMS Blueprint v2.0, Pages 10, 13].
* **Responsible Role**: Student
* **Dependencies**: Orders table, Payment Gateway SDK (Razorpay recommended)
* **Validation Conditions**: Verify course pricing against database; never accept client-submitted amounts.
* **Acceptance Criteria**: Pending order expires if payment is not completed within configured TTL.
* **Source PDF**: Pages 10, 13 — Schema & checkout endpoints
* **Status**: `NOT_STARTED`

### REQ-COM-002: Webhook Processing & Idempotent Enrollment
* **Module**: Commerce
* **Description**: Reconcile payment provider webhook events and grant course access.
* **Expected Behaviour**: On receiving payment webhook: 1. Validate cryptographic HMAC signature, 2. Check provider event ID for uniqueness, 3. Lock order and payment records, 4. Update order to `PAID`, 5. Create `enrollments` row, 6. Emit audit record—all within a single database transaction [Source: LMS Blueprint v2.0, Pages 10, 11, 14].
* **Responsible Role**: System / Webhook Controller
* **Dependencies**: `payment_webhook_events`, `payments`, `enrollments`
* **Validation Conditions**: Duplicate webhooks must return 200 OK without creating duplicate enrollments (`UNIQUE(user_id, course_id)`). Access must NEVER be granted purely on browser redirect [Source: LMS Blueprint v2.0, Pages 11, 14, 15].
* **Acceptance Criteria**: Webhook processing is completely idempotent and safe against network retries.
* **Source PDF**: Pages 10, 11, 14, 15 — Transactions, webhooks & QA criteria
* **Status**: `NOT_STARTED`

### REQ-COM-003: Audited Refunds & Entitlement Revocation
* **Module**: Commerce
* **Description**: Execute full or partial refunds with automatic entitlement revocation and audit trails.
* **Expected Behaviour**: Admin initiates refund with mandatory reason. System locks order, checks that cumulative refunds do not exceed captured amount, executes gateway refund API, updates payment state, revokes enrollment, and writes audit record [Source: LMS Blueprint v2.0, Pages 11, 13, 14].
* **Responsible Role**: Super Admin, Admin (with `payments.refund`)
* **Dependencies**: Gateway refund API, `refunds` table, `enrollments`
* **Validation Conditions**: Cumulative refund cannot exceed captured amount [Source: LMS Blueprint v2.0, Page 11].
* **Acceptance Criteria**: Student access to course content is immediately terminated upon refund completion.
* **Source PDF**: Pages 11, 13, 14 — Schema, transaction & failure rules
* **Status**: `NOT_STARTED`

---

## 9. Super Admin Governance, RBAC & Recovery (GOV)

### REQ-GOV-001: Staff Invitation Lifecycle
* **Module**: Super Admin
* **Description**: Secure onboarding workflow for Staff and Admin team members.
* **Expected Behaviour**: Super Admin enters invitee email, role, permission overrides, and optional expiration. System stores a cryptographic hash of a one-time token (recommended 48h TTL) and sends invite email. Invitee verifies email, sets password, and configures MFA. Acceptance atomically creates account and grants [Source: LMS Blueprint v2.0, Page 7].
* **Responsible Role**: Super Admin
* **Dependencies**: Mailer, `user_role_grants` table
* **Validation Conditions**: Tokens stored only as hashes. Resending invalidates previous token. Revocation immediately blocks acceptance [Source: LMS Blueprint v2.0, Page 7].
* **Acceptance Criteria**: All invitations, revocations, and acceptances generate immutable audit events.
* **Source PDF**: Pages 7, 13 — Invitation lifecycle & API contracts
* **Status**: `NOT_STARTED`

### REQ-GOV-002: Granular RBAC & Permission Evaluation
* **Module**: Super Admin
* **Description**: Multi-tier permission checking evaluating roles, granular keys, explicit overrides, and resource scopes.
* **Expected Behaviour**: Evaluation sequence:
  $$\text{Authenticate} \longrightarrow \text{Check Active Account} \longrightarrow \text{Validate Session} \longrightarrow \text{Check Action Permission} \longrightarrow \text{Check Scope/Ownership} \longrightarrow \text{Check Business Rules} \longrightarrow \text{Audit}$$
  Deny overrides allow. Scopes include `own`, `assigned`, `course-specific`, or `all` [Source: LMS Blueprint v2.0, Page 3].
* **Responsible Role**: System / Security Middleware
* **Dependencies**: `roles`, `permissions`, `user_role_grants`, `user_permission_overrides`
* **Validation Conditions**: System roles cannot be deleted. The final active Super Admin account cannot be removed or demoted [Source: LMS Blueprint v2.0, Pages 3, 9].
* **Acceptance Criteria**: Sensitive permission changes immediately revoke target user sessions or increment `auth_version` [Source: LMS Blueprint v2.0, Page 3].
* **Source PDF**: Pages 2, 3, 9 — Permission matrix & keys
* **Status**: `NOT_STARTED`

### REQ-GOV-003: Account Recovery & Incident Playbooks
* **Module**: Super Admin
* **Description**: Managed recovery procedures for lost passwords, lost MFA devices, suspected account takeover, or departure.
* **Expected Behaviour**: Provide documented recovery paths:
  * Forgot Password: Expiring single-use token; revoke all sessions on completion.
  * Lost MFA: Supervised identity verification; rotate MFA secret; revoke active sessions.
  * Suspected Takeover: Instantly suspend user, revoke all sessions/tokens, preserve logs, force password reset + MFA re-enrollment.
  * Super Admin Lockout: Offline break-glass recovery codes stored hashed [Source: LMS Blueprint v2.0, Pages 7–8].
* **Responsible Role**: Super Admin
* **Dependencies**: `login_events`, `auth_sessions`, MFA engine
* **Validation Conditions**: Passwords and raw MFA secrets must never be viewable or transmitted via email [Source: LMS Blueprint v2.0, Page 7].
* **Acceptance Criteria**: Every recovery action requires mandatory justification and produces an audit trail.
* **Source PDF**: Pages 7–8 — Recovery playbook & guardrails
* **Status**: `NOT_STARTED`

### REQ-GOV-004: Immutable Audit Logging
* **Module**: Super Admin
* **Description**: Tamper-proof recording of all administrative, financial, security, and grading actions.
* **Expected Behaviour**: Logs record: `actor_id`, `action`, `resource_type`, `resource_id`, `before_json`, `after_json`, `reason`, `ip_prefix`, `user_agent_hash`, `correlation_id`, and `created_at` [Source: LMS Blueprint v2.0, Page 11].
* **Responsible Role**: System / Auditing Middleware
* **Dependencies**: `audit_logs` table
* **Validation Conditions**: Table is strictly append-only. Service layer and database constraints prohibit `UPDATE` and `DELETE` queries [Source: LMS Blueprint v2.0, Page 11].
* **Acceptance Criteria**: Searchable by actor, resource, action, and date range via Super Admin portal (`/control/audit`).
* **Source PDF**: Pages 3, 4, 11 — Audit schema & Super Admin routes
* **Status**: `NOT_STARTED`

---

## 10. Operational Infrastructure & Monitoring (OPS)

### REQ-OPS-001: Transactional Outbox Notifications
* **Module**: Operations
* **Description**: Reliable, deduplicated notification delivery for grade releases, announcements, and receipts.
* **Expected Behaviour**: System writes notifications to `notifications` table within the same transaction as the triggering business event. Background workers poll and deliver messages via email/in-app with deduplication keys [Source: LMS Blueprint v2.0, Pages 11, 14].
* **Responsible Role**: Background Workers
* **Dependencies**: Outbox table, Email provider
* **Validation Conditions**: Duplicate events must be ignored based on `dedupe_key VARCHAR(160)` unique constraint [Source: LMS Blueprint v2.0, Pages 11, 14].
* **Acceptance Criteria**: Failed deliveries retry with exponential backoff and route to dead-letter queue after max attempts.
* **Source PDF**: Pages 11, 14 — Schema & failure scenarios
* **Status**: `NOT_STARTED`

### REQ-OPS-002: Structured Logging & Redaction
* **Module**: Operations
* **Description**: Centralized structured logging across all API endpoints and background tasks.
* **Expected Behaviour**: Every log line outputs JSON including `request_id`, `actor`, `action`, `resource`, `result`, and latency. Sensitive fields (passwords, tokens, card details, webhook secrets) are automatically masked [Source: LMS Blueprint v2.0, Pages 14, 15].
* **Responsible Role**: System Middleware
* **Dependencies**: Logging framework
* **Validation Conditions**: Stack traces, raw SQL queries, and secrets must never leak into client HTTP error responses [Source: LMS Blueprint v2.0, Pages 11, 14].
* **Acceptance Criteria**: Client receives sanitized error envelope `{error: {code, message, details, request_id}}` [Source: LMS Blueprint v2.0, Page 14].
* **Source PDF**: Pages 11, 14, 15 — Error envelope & monitoring
* **Status**: `NOT_STARTED`
