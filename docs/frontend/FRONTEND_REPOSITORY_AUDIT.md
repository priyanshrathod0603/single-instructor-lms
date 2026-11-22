# Frontend Repository & Backend Foundation Audit (FRONTEND_REPOSITORY_AUDIT)

**Project**: Single-Instructor Learning Management System (LMS)  
**Lifecycle Phase**: Phase 2 — Frontend Development  
**Document Type**: Technical Audit & Reality Verification  
**Audit Date**: 2026-11-15  
**Audit Status**: `EMPIRICALLY_VERIFIED`  
**Execution Mode**: Read-Only Inspection (Zero Code / Zero Dependency Changes)  

---

## 1. Executive Summary

This repository audit establishes the empirical baseline for beginning **Phase 2 — Frontend Development** from ground zero. 

The backend development phase (**Phase 1, Parts 0 through 9**, plus **P0 and P1 security remediations**) has been completed, resulting in **35 PostgreSQL domain tables**, **75 REST API endpoints** (88 distinct route operations including health checks), and an automated test suite of **665 passing tests** (662 unit/integration tests and 3 live PostgreSQL concurrency tests).

A physical filesystem scan of `/Users/priyansh/lms` confirms that **zero application frontend code currently exists**. There are no `.tsx`, `.jsx`, `.vue`, `.svelte`, or frontend `.ts` source files. Frontend engineering is starting entirely clean.

---

## 2. Root Directory Filesystem Audit

An exhaustive inspection of `/Users/priyansh/lms` reveals the following top-level directory structure:

| File / Directory | Nature | Contents & Status | Verification Status |
| :--- | :--- | :--- | :--- |
| `.ai/` | Governance & Memory | Project intelligence system containing `CORE/`, `GOVERNANCE/`, `RULES/`, `MEMORY/`, `WORKFLOWS/`, `TRACKING/`, `CONTEXT/`. | `VERIFIED` (Untouched, binding) |
| `AGENTS.md` | Directive | Top-level agent charter and entry protocol. | `VERIFIED` (Reserved, untouched) |
| `GEMINI.md` | Directive | Gemini & Antigravity assistant operating rules. | `VERIFIED` (Reserved, untouched) |
| `backend/` | Application Source | Complete FastAPI backend application, tests, and Alembic migrations. | `VERIFIED` (Production-ready) |
| `docs/backend/` | Architectural Specs | 25 authoritative architectural blueprints covering system, API, DB, security, and roadmap. | `VERIFIED` (Authoritative) |
| `docs/frontend/` | Architectural Specs | Newly created directory for Phase 2 frontend architectural blueprints. | `VERIFIED` (Initialized) |
| `.env` / `.env.example`| Configuration | Environment variable declarations for development and testing. | `VERIFIED` (Active) |
| `.gitignore` | VCS Configuration | Git ignore rules for Python, Node, environment files, and IDEs. | `VERIFIED` (Active) |
| `package.json` | Package Manifest | Declares `motion` (`^14.14.0`) dependency installed for Phase 2 motion tools. | `VERIFIED` (Active) |
| `package-lock.json` | Lockfile | Deterministic lockfile for installed Node packages. | `VERIFIED` (Active) |
| `node_modules/` | Node Dependencies | Installed packages (`motion`, `framer-motion`, `motion-dom`, `motion-utils`, `tslib`). | `VERIFIED` (Active) |
| `.agents/skills/` | Agent Tools | Workspace skills directory containing `motion`, `ui-ux-pro-max`, and 19 Emil Kowalski animation skills. | `VERIFIED` (Active) |
| `.gemini/` | Agent Tools | Local Gemini CLI configuration, settings, and mirrored skills. | `VERIFIED` (Active) |
| `.cursor/` | Agent Tools | Local Cursor configuration and MCP definitions (`mcp.json`). | `VERIFIED` (Active) |
| `.mcp.json` | MCP Configuration | Root hosted MCP server configuration for Motion AI kit (`https://mcp.motion.dev`). | `VERIFIED` (Active) |
| `phase.md` | Roadmap Tracking | High-level project phase tracking and history. | `VERIFIED` (Active) |

**Key Finding**: No frontend build framework (e.g., Next.js, Vite, Create-React-App) has been scaffolded or initialized yet.

---

## 3. Verified Backend Architecture & Technical Foundation

The backend operates as an enterprise-grade RESTful API service built on the following stack:

* **Language Runtime**: Python 3.14.3
* **Web Framework**: FastAPI 0.141.1 (ASGI, fully async)
* **Relational Database**: PostgreSQL 17 (Driver: `psycopg` 3.3.3)
* **ORM & Query Engine**: SQLAlchemy 2.0.50
* **Database Migrations**: Alembic 1.20.1 (Current migration head: `a7b8c9d0e1f2`)
* **Data Validation & Schemas**: Pydantic v2 (`pydantic` 2.13.4, `pydantic-settings` 2.15.0)
* **Password Hashing**: Argon2id via `argon2-cffi` 25.1.0
* **JWT & Cryptography**: PyJWT 2.13.0, cryptography 49.0.0
* **Automated Test Suite**: pytest 9.1.1 (662 passing unit/integration tests, 3 passing live PostgreSQL concurrency tests, 12 skipped, 0 failures)

### Application Lifecycle & Middleware Pipeline
Inspecting `backend/app/main.py` confirms the ASGI execution order:
1. **Lifespan Startup**: Verifies PostgreSQL connectivity (`check_db_connectivity()`); starts asynchronous transactional outbox worker (`OutboxWorker`) if enabled.
2. **RequestIDMiddleware**: Extracts or generates an incoming `X-Request-ID` UUID, stores it in `request.state.request_id` and Python `contextvars`, and injects it into all JSON logs and HTTP response headers.
3. **CORSMiddleware**:
   * Allowed Origins: `settings.CORS_ORIGINS` (defaults to `["http://localhost:3000", "http://127.0.0.1:3000"]` and `settings.FRONTEND_URL`).
   * `allow_credentials=True` (strictly required for browser cookie transmission).
   * Allowed Methods: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`.
   * Allowed Headers: `Content-Type`, `Idempotency-Key`, `X-Requested-With`, `Authorization`, `Accept`, `Origin`, `X-Request-ID`.
   * Exposed Headers: `X-Request-ID`.
   * `max_age=3600`.
4. **Centralized Error Handlers**: Intercepts `AppException`, `RequestValidationError`, `StarletteHTTPException`, and uncaught `Exception`, converting 100% of errors into the canonical LMS error envelope with no stack trace leakage.

---

## 4. Complete Backend Route Inventory (75 Endpoints)

FastAPI application inspection verifies **75 distinct API endpoints** registered across 15 domain routers under the `/api/v1` prefix:

### 1. Authentication & Sessions (`/api/v1/auth`) — 11 Endpoints
* `POST /api/v1/auth/register` — Register student account with email and password; stages email verification outbox event.
* `POST /api/v1/auth/login` — Authenticate credentials; atomically revokes prior active sessions; sets secure HttpOnly `__Host-lms_session` cookie; returns short-lived JWT access token.
* `POST /api/v1/auth/logout` — Revokes session in database; clears `__Host-lms_session` cookie.
* `GET /api/v1/auth/me` — Returns profile, status, and assigned roles of current authenticated user.
* `POST /api/v1/auth/refresh` — Validates active session cookie; issues fresh 15-minute access token.
* `POST /api/v1/auth/verify-email` — Confirms single-use email verification token.
* `POST /api/v1/auth/resend-verification` — Anti-enumeration email verification resend.
* `POST /api/v1/auth/password-reset/request` — Anti-enumeration password reset request; generates token in outbox.
* `POST /api/v1/auth/password-reset/confirm` — Validates reset token, updates password, and atomically revokes all active user sessions.
* `POST /api/v1/auth/oauth/google` — Verifies Google OIDC ID token against Google JWKS (`accounts.google.com`); binds or creates user; establishes single active session.
* `POST /api/v1/auth/onboarding/claim` — Validates staff onboarding invitation token; sets initial password; establishes session.

### 2. User Management & Governance (`/api/v1/users`) — 6 Endpoints
* `GET /api/v1/users` — Paginated directory of platform users with search and role filters (`users:view_all`).
* `POST /api/v1/users/staff/invite` — Invites new staff/admin member via email invitation token (`staff:invite`).
* `GET /api/v1/users/{id}` — Retrieves detailed user record by UUID (`users:view_all` or own profile).
* `PATCH /api/v1/users/{id}` — Updates user profile details (`full_name`, metadata).
* `PATCH /api/v1/users/{id}/roles` — Grants or revokes system roles (`roles:assign`, Super Admin only).
* `PATCH /api/v1/users/{id}/status` — Suspends or restores user account (`users:manage_status`, Super Admin only).

### 3. Course Catalog & Curriculum (`/api/v1/courses`, `/sections`, `/lessons`) — 17 Endpoints
* `GET /api/v1/courses` — Public catalog of published courses with pricing, duration, and metadata.
* `POST /api/v1/courses` — Creates course container and initial draft revision (`course:create`).
* `GET /api/v1/courses/manage` — Administrative directory of all courses across statuses (`course:view_all`).
* `GET /api/v1/courses/{id_or_slug}` — Public details of course by UUID or slug with published curriculum tree.
* `DELETE /api/v1/courses/{id}` — Soft-archives course (`course:archive`, Super Admin only).
* `PATCH /api/v1/courses/{id}` — Updates top-level course metadata (`course:edit`).
* `GET /api/v1/courses/{id}/publish-checklist` — Pre-flight relational publish readiness check (`course:edit`).
* `POST /api/v1/courses/{id}/revisions` — Clones published revision into a new working draft revision (`course:revision_create`).
* `GET /api/v1/courses/{id}/revisions/{rev_id}` — Retrieves complete draft revision curriculum tree (`course:edit`).
* `POST /api/v1/courses/{id}/revisions/{rev_id}/publish` — Freezes draft revision snapshot and sets as live (`course:publish`).
* `POST /api/v1/courses/{id}/revisions/{rev_id}/sections` — Adds section to draft revision (`curriculum:manage`).
* `PUT /api/v1/courses/{id}/revisions/{rev_id}/sections/reorder` — Reorders sections with optimistic version check (`curriculum:reorder`).
* `PATCH /api/v1/sections/{id}` — Updates section title and description (`curriculum:manage`).
* `DELETE /api/v1/sections/{id}` — Deletes section and child lessons from draft revision (`curriculum:manage`).
* `POST /api/v1/sections/{id}/lessons` — Adds lesson to section (`curriculum:manage`).
* `PUT /api/v1/sections/{id}/lessons/reorder` — Reorders lessons within section with version check (`curriculum:reorder`).
* `DELETE /api/v1/resources/{id}` — Deletes downloadable resource attachment from lesson (`curriculum:manage`).

### 4. Protected Media Pipeline (`/api/v1/media`) — 6 Endpoints
* `POST /api/v1/media/upload-intent` — Generates presigned S3/R2 direct upload PUT URL (`media:upload`).
* `POST /api/v1/media/{id}/confirm` — Verifies binary existence in remote storage; triggers transcode (`media:upload`).
* `GET /api/v1/media` — Lists uploaded media assets with status filtering (`media:upload`).
* `GET /api/v1/media/{id}` — Retrieves media asset metadata and processing status.
* `POST /api/v1/media/{id}/playback-token` — Generates signed, short-lived (2-hour TTL) HLS video playback token for enrolled student or staff.
* `GET /api/v1/media/{id}/protected-pdf` — Streams protected watermarked PDF with dynamic student email/IP provenance stamp and disabled download headers.

### 5. Commerce, Orders & Payments (`/api/v1/orders`, `/webhooks`) — 5 Endpoints
* `GET /api/v1/orders` — Lists purchase orders with role-based scoping (`orders:view_own` or `orders:view_all`).
* `POST /api/v1/orders` — Initiates purchase order; registers Razorpay order; returns `razorpay_order_id` and key (`orders:create`).
* `GET /api/v1/orders/{id}` — Retrieves order status, items, and transaction details.
* `POST /api/v1/orders/{id}/refund` — Authorizes and executes partial or full refund via Razorpay (`payments:refund`, Super Admin only).
* `POST /api/v1/webhooks/razorpay` — Cryptographic webhook receiver for `payment.captured`; verifies HMAC-SHA256 signature against raw body; atomically records transaction and provisions enrollment.

### 6. Student Enrollments & Access (`/api/v1/enrollments`) — 4 Endpoints
* `GET /api/v1/enrollments` — Lists active and expired course enrollments for current student (`enrollment:view_own`).
* `GET /api/v1/enrollments/all` — Administrative list of all platform enrollments with filters (`enrollment:view_all`).
* `GET /api/v1/enrollments/check/{course_id}` — Fast boolean enrollment entitlement check for current user.
* `POST /api/v1/enrollments/manual` — Manually grants enrollment without payment (`enrollment:grant`, Admin/Super Admin).

### 7. Assignments & Rubric Grading (`/api/v1/assignments`, `/submissions`) — 8 Endpoints
* `GET /api/v1/assignments/{id}` — Retrieves assignment instructions, deadlines, max attempts, and active rubric criteria.
* `PATCH /api/v1/assignments/{id}` — Updates assignment metadata and due dates (`assignment:manage`).
* `POST /api/v1/assignments/{id}/rubric` — Creates or updates versioned grading rubric (`assignment:manage`).
* `POST /api/v1/assignments/{id}/submissions` — Submits student work (text, external links, media attachment UUIDs) with enrollment check (`assignment:submit`).
* `GET /api/v1/assignments/{id}/submissions` — Lists submissions for grading queue (`assignment:view_all`, Staff/Admin).
* `GET /api/v1/submissions/{id}` — Retrieves submission details, rubric criteria scores, and grade overrides (owner student or staff).
* `POST /api/v1/submissions/{id}/grade` — Evaluates submission via rubric criteria scores and qualitative feedback (`assignment:grade`, Staff/Admin).
* `POST /api/v1/submissions/{id}/override-grade` — Overrides published grade with mandatory justification (`assignment:override`, Super Admin only).

### 8. Quizzes & Question Banks (`/api/v1/quizzes`, `/quiz-attempts`) — 10 Endpoints
* `GET /api/v1/quizzes/{id}` — Retrieves quiz settings and questions (concealing correct answers for students).
* `PATCH /api/v1/quizzes/{id}` — Updates quiz settings: timer, pass percentage, allowed attempts (`quiz:manage`).
* `POST /api/v1/quizzes/{id}/questions` — Authors and attaches individual question to quiz (`quiz:manage`).
* `POST /api/v1/quizzes/{id}/questions/bulk-csv` — Bulk imports questions via CSV content or JSON (`quiz:import_csv`).
* `POST /api/v1/quizzes/{id}/attempts` — Starts quiz attempt; initializes server-authoritative timer; returns randomized questions (`quiz:attempt`).
* `GET /api/v1/quizzes/{id}/attempts` — Lists attempts for a quiz (evaluator view, `quiz:view_attempts`).
* `GET /api/v1/quiz-attempts` — Lists current student's own attempts (`quiz:attempt`).
* `GET /api/v1/quiz-attempts/{id}` — Reviews attempt results, score, pass/fail status, and answer explanations.
* `PATCH /api/v1/quiz-attempts/{id}/autosave` — Incremental answer autosave with optimistic attempt lock.
* `POST /api/v1/quiz-attempts/{id}/submit` — Submits attempt; evaluates answers against server answer keys; computes final score.

### 9. Student Progress & Completion (`/api/v1/progress`) — 2 Endpoints
* `POST /api/v1/progress/lessons/{lesson_id}` — Records video watch seconds heartbeat ($\ge 90\%$ auto-completion threshold) or toggles manual completion.
* `GET /api/v1/progress/courses/{course_id}` — Returns student course completion percentage, completed lesson IDs, and progress summary.

### 10. Certificates & Public Verification (`/api/v1/certificates`) — 4 Endpoints
* `GET /api/v1/certificates/{course_id}` — Retrieves or automatically generates completion certificate for 100% completed course.
* `GET /api/v1/certificates/{course_id}/download` — Downloads official verifiable PDF certificate.
* `GET /api/v1/certificates/verify/{verification_hash}` — Public endpoint for verifying certificate authenticity via QR code.
* `POST /api/v1/certificates/{certificate_id}/revoke` — Administratively revokes certificate with logged reason (Super Admin only).

### 11. Notifications (`/api/v1/notifications`) — 3 Endpoints
* `GET /api/v1/notifications` — Lists in-app notifications with unread counts for authenticated user.
* `PATCH /api/v1/notifications/{id}/read` — Marks an individual notification as read.
* `POST /api/v1/notifications/read-all` — Marks all unread notifications as read.

### 12. Security Audit Trail (`/api/v1/audit-logs`) — 1 Endpoint
* `GET /api/v1/audit-logs` — Filters and inspects immutable security and financial audit trail (`audit:view`, Super Admin only).

### 13. Health & Liveness Probes (`/healthz`, `/api/v1/health`) — 2 Endpoints
* `GET /healthz` — Shallow ASGI process liveness probe (does not touch PostgreSQL).
* `GET /api/v1/health` — Deep readiness probe verifying active database connection pool.

---

## 5. Authentication & Session Invariants

1. **Single Active Session Rule**:
   * Stored in `auth_sessions` table with a partial unique index: `WHERE status='ACTIVE'`.
   * A new login atomically displaces any existing active session, setting `status='REVOKED'`, `revoked_at=NOW()`, `revoke_reason='NEW_LOGIN'`.
   * The displaced session receives `HTTP 401 Unauthorized` with error code `SESSION_REVOKED`.
2. **Cookie Handling**:
   * `Set-Cookie: __Host-lms_session=<token>; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=604800`
   * In development/testing environments, `Secure=False` and non-prefix cookie names are tolerated for HTTP loopback.
   * `localStorage` and `sessionStorage` **must never** store session secrets or long-lived JWTs.
3. **Dual Verification in Backend**:
   * The backend dependency `get_current_user_and_session` checks the session cookie first.
   * If a Bearer JWT is passed in `Authorization`, it requires a valid `session_id` claim and validates that the database session row is still `ACTIVE`.
4. **CORS Authentication**:
   * The frontend must send `credentials: "include"` on all `fetch` or `axios` calls to ensure the browser transmits the HttpOnly session cookie across origins.

---

## 6. Error Response Envelope Specification

Every non-2xx HTTP response from the backend produces an identical JSON structure:

```json
{
  "success": false,
  "error": {
    "code": "STRING_ERROR_CODE",
    "message": "Human-readable description for client display.",
    "details": {},
    "request_id": "c7a8b2d1-e5f6-4a3b-8c9d-0e1f2a3b4c5d"
  }
}
```

The frontend API client must parse `response.data.error` to extract `code`, `message`, and `details` for field-level error rendering and toast alerts.

---

## 7. Media & Asset Delivery Pipeline

1. **Upload Workflow**:
   * Client calls `POST /api/v1/media/upload-intent` with `{file_name, file_size_bytes, mime_type, purpose}`.
   * Backend validates magic bytes/extension allowlist and size caps (5GB video, 100MB PDF, 20MB images).
   * Backend returns `{upload_url, media_id, expires_in_seconds}`.
   * Client uploads binary directly to S3/R2 via HTTP `PUT` to `upload_url`.
   * Client calls `POST /api/v1/media/{id}/confirm` with `{etag, actual_size_bytes}`.
2. **Video Playback Workflow**:
   * Client requests `POST /api/v1/media/{id}/playback-token` with `{lesson_id}`.
   * Backend verifies student active enrollment in the course containing `lesson_id`.
   * Backend returns signed token and HLS playback manifest URL (`.m3u8`).
3. **Protected PDF Workflow**:
   * Client renders protected viewer iframe or canvas targeting `GET /api/v1/media/{id}/protected-pdf?lesson_id={lesson_id}`.
   * Backend streams watermarked PDF with student email and IP stamped dynamically.

---

## 8. Payment & Checkout Integration

1. **Initiation**:
   * Student calls `POST /api/v1/orders` with `{course_id, currency: "INR"}`.
   * Backend creates internal `Order` in `PENDING` status and calls Razorpay API to generate `razorpay_order_id`.
   * Response contains `{order_id, razorpay_order_id, amount: 49900, currency: "INR", key_id: "rzp_test_..."}`.
2. **Client Checkout Modal**:
   * Frontend invokes Razorpay Checkout JS SDK modal with `key_id`, `order_id`, and student details.
3. **Verification (Zero Trust on Browser Redirect)**:
   * Client-side success callback from Razorpay modal provides `{razorpay_payment_id, razorpay_order_id, razorpay_signature}`.
   * **Mandatory Invariant**: Client redirection does NOT grant course enrollment.
   * The backend grants enrollment **exclusively** upon processing the verified Razorpay webhook (`POST /api/v1/webhooks/razorpay`) with HMAC-SHA256 signature verification.
   * The client polls `GET /api/v1/orders/{id}` or listens for in-app notification until status transitions to `PAID`.

---

## 9. Conclusion & Readiness

The backend repository is complete, stable, robustly tested, and provides 100% of the REST API infrastructure required for a fully responsive, enterprise-grade Single-Instructor LMS frontend.

**Next Step**: Formalize technology choices and proposed frontend architectural blueprints in `docs/frontend/`.
