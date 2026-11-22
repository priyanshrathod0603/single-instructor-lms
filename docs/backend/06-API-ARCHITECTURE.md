# RESTful API Architecture & Endpoint Catalog Specification

## 1. API Architecture Principles & Standards

The Single-Instructor LMS backend exposes a versioned, RESTful API under the `/api/v1/` prefix.

### 1.1 Core Directives
1. **Unambiguous Response Envelopes**: All JSON responses conform to standard schema envelopes:
   * Success: `{"success": true, "data": ..., "meta": ...}`
   * Failure: `{"success": false, "error": {"code": "...", "message": "...", "details": ..., "request_id": "..."}}`
2. **Idempotency on Critical Mutations**: State-mutating operations (payment orders, refunds, course publication) accept an `Idempotency-Key: <UUID>` header to guard against duplicate network transmissions.
3. **HTTP Status Code Discipline**:
   * `200 OK`: Successful synchronous retrieval or state update.
   * `201 Created`: Resource successfully created (includes `Location` header where applicable).
   * `400 Bad Request`: Malformed payload or domain validation failure.
   * `401 Unauthorized`: Missing credentials, expired token, or displaced session (`SESSION_REVOKED`).
   * `403 Forbidden`: Authenticated identity lacks required RBAC permissions.
   * `404 Not Found`: Target entity does not exist or caller lacks access.
   * `409 Conflict`: Concurrency conflict (e.g., stale curriculum version reordering).
   * `422 Unprocessable Entity`: Pydantic schema validation failure.
   * `429 Too Many Requests`: Rate limit threshold exceeded.
   * `500 Internal Server Error`: Unhandled server exception (sanitized error message with trace ID).
4. **Standard Pagination**: List endpoints accept query parameters `page` (default 1) and `page_size` (default 20, max 100), returning pagination metadata:
   ```json
   {
     "page": 1,
     "page_size": 20,
     "total_items": 142,
     "total_pages": 8
   }
   ```

---

## 2. Global Route Inventory

### 2.1 Identity, Authentication & Sessions (`/api/v1/auth`)

| Method | Endpoint | Description | Auth Required | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/auth/register` | Register student account with email and password | No | Public |
| `POST` | `/auth/login` | Authenticate credentials; atomic session issuance | No | Public |
| `POST` | `/auth/logout` | Revoke active session token | Yes | Any Active |
| `GET` | `/auth/me` | Fetch active user identity, roles, and permissions | Yes | Any Active |
| `POST` | `/auth/refresh` | Refresh short-lived access credentials | Yes | Any Active |
| `POST` | `/auth/verify-email` | Validate email verification token | No | Public |
| `POST` | `/auth/resend-verification` | Resend verification email token | Yes | Unverified Active |
| `POST` | `/auth/password-reset/request`| Initiate password reset workflow | No | Public |
| `POST` | `/auth/password-reset/confirm`| Submit new password using reset token | No | Public |
| `POST` | `/auth/oauth/google` | Exchange Google OIDC token for user session | No | Public |

### 2.2 User & Staff Management (`/api/v1/users`)

| Method | Endpoint | Description | Auth Required | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/users` | Paginated user directory with search/role filters | Yes | `users:view_all` |
| `GET` | `/users/{id}` | Retrieve detailed user profile and enrollment records | Yes | `users:view` or Self |
| `PATCH` | `/users/{id}` | Update user profile data | Yes | `users:edit` or Self |
| `PATCH` | `/users/{id}/status` | Activate, suspend, or ban user account | Yes | `users:manage_status` |
| `POST` | `/users/staff/invite` | Send onboarding invitation token to new staff | Yes | `staff:invite` |
| `PATCH` | `/users/{id}/roles` | Assign or revoke roles for a user | Yes | `roles:assign` |

### 2.3 Course Catalog & Revision Control (`/api/v1/courses`)

| Method | Endpoint | Description | Auth Required | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/courses` | Public catalog of published courses | No | Public |
| `GET` | `/courses/manage` | Admin view of all courses (drafts, published, archived) | Yes | `course:view_all` |
| `POST` | `/courses` | Create new course entity and initial draft revision | Yes | `course:create` |
| `GET` | `/courses/{id_or_slug}` | Retrieve course details and live published curriculum | No | Public |
| `PATCH` | `/courses/{id}` | Update top-level course metadata (slug, title, price) | Yes | `course:edit` |
| `POST` | `/courses/{id}/revisions` | Clone live revision into a new working draft revision | Yes | `course:revision_create` |
| `GET` | `/courses/{id}/revisions/{rev_id}` | Fetch specific revision draft tree | Yes | `course:edit` |
| `GET` | `/courses/{id}/publish-checklist` | Evaluate pre-flight publishing requirements | Yes | `course:publish` |
| `POST` | `/courses/{id}/revisions/{rev_id}/publish` | Atomically publish draft revision as live snapshot | Yes | `course:publish` |
| `DELETE` | `/courses/{id}` | Archive course (soft status update) | Yes | `course:archive` |

### 2.4 Curriculum Sections & Lessons (`/api/v1/sections`, `/api/v1/lessons`)

| Method | Endpoint | Description | Auth Required | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/courses/{id}/revisions/{rev_id}/sections` | Add section to draft revision | Yes | `course:edit` |
| `PATCH` | `/sections/{id}` | Update section title and description | Yes | `course:edit` |
| `DELETE` | `/sections/{id}` | Remove section and child lessons from draft | Yes | `course:edit` |
| `PUT` | `/courses/{id}/revisions/{rev_id}/sections/reorder` | Bulk reorder sections with version check | Yes | `course:edit` |
| `POST` | `/sections/{id}/lessons` | Add lesson to section | Yes | `course:edit` |
| `GET` | `/lessons/{id}` | Retrieve lesson details and content | Yes | Enrolled or `course:edit` |
| `PATCH` | `/lessons/{id}` | Update lesson content, duration, preview flag | Yes | `course:edit` |
| `DELETE` | `/lessons/{id}` | Remove lesson from section | Yes | `course:edit` |
| `PUT` | `/sections/{id}/lessons/reorder` | Bulk reorder lessons within section | Yes | `course:edit` |

### 2.5 Assignments & Rubrics (`/api/v1/assignments`, `/api/v1/submissions`)

| Method | Endpoint | Description | Auth Required | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/lessons/{id}/assignment` | Configure assignment for lesson | Yes | `assignment:manage` |
| `GET` | `/lessons/{id}/assignment` | Get assignment instructions and active rubric | Yes | Enrolled or `assignment:view` |
| `POST` | `/assignments/{id}/submissions` | Submit project work (file URL, notes) | Yes | Student Enrolled |
| `GET` | `/assignments/{id}/submissions` | List submissions for grading | Yes | `assignment:grade` |
| `GET` | `/submissions/{id}` | View submission details and rubric scores | Yes | `assignment:grade` or Owner |
| `POST` | `/submissions/{id}/grade` | Submit rubric criteria points and feedback | Yes | `assignment:grade` |
| `POST` | `/submissions/{id}/override-grade` | Apply administrative grade override | Yes | `assignment:override` |

### 2.6 Quizzes & Questions (`/api/v1/quizzes`, `/api/v1/quiz-attempts`)

| Method | Endpoint | Description | Auth Required | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/lessons/{id}/quiz` | Configure quiz parameters (timer, pass score) | Yes | `quiz:manage` |
| `GET` | `/lessons/{id}/quiz` | Get quiz configuration | Yes | Enrolled or `quiz:view` |
| `POST` | `/quizzes/{id}/questions` | Add individual question and options | Yes | `quiz:manage` |
| `POST` | `/quizzes/{id}/questions/bulk-csv` | Import questions via CSV upload | Yes | `quiz:manage` |
| `POST` | `/quizzes/{id}/attempts` | Start quiz attempt (initializes server-side timer) | Yes | Student Enrolled |
| `PATCH` | `/quiz-attempts/{id}/autosave` | Autosave selected answers incrementally | Yes | Attempt Owner |
| `POST` | `/quiz-attempts/{id}/submit` | Finalize attempt, calculate score, evaluate pass | Yes | Attempt Owner |
| `GET` | `/quiz-attempts/{id}` | Review completed attempt results and explanations | Yes | Attempt Owner or `quiz:grade` |

### 2.7 Commerce, Orders & Webhooks (`/api/v1/orders`, `/api/v1/webhooks`)

| Method | Endpoint | Description | Auth Required | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/orders` | Create checkout order and initialize Razorpay order | Yes | Student (Verified) |
| `GET` | `/orders/{id}` | Get order status and payment details | Yes | Order Owner or `orders:view` |
| `POST` | `/webhooks/razorpay` | Cryptographic webhook endpoint for payment capture | No | Public (HMAC verified) |
| `POST` | `/orders/{id}/refund` | Initiate refund for an order | Yes | `payments:refund` |

### 2.8 Student Enrollments (`/api/v1/enrollments`)

| Method | Endpoint | Description | Auth Required | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/enrollments` | List enrolled courses for current student | Yes | Student Active |
| `GET` | `/enrollments/all` | Admin list of all platform enrollments | Yes | `enrollment:view_all` |
| `POST` | `/enrollments/grant-manual` | Manually grant student enrollment | Yes | `enrollment:grant` |
| `PATCH` | `/enrollments/{id}/revoke` | Revoke student access to course | Yes | `enrollment:revoke` |
| `GET` | `/enrollments/check/{course_id}` | Quick boolean check of active course access | Yes | Any Active |

### 2.9 Progress & Verification (`/api/v1/progress`, `/api/v1/certificates`)

| Method | Endpoint | Description | Auth Required | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/progress/courses/{course_id}` | Get course progress summary and completed lessons | Yes | Enrolled Student |
| `POST` | `/progress/lessons/{lesson_id}` | Record video watch seconds or toggle completion | Yes | Enrolled Student |
| `GET` | `/certificates/{course_id}` | Retrieve or generate certificate for finished course | Yes | Enrolled Student |
| `GET` | `/certificates/verify/{hash}` | Public endpoint for certificate QR verification | No | Public |

### 2.10 Media & Storage Security (`/api/v1/media`)

| Method | Endpoint | Description | Auth Required | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/media/upload-intent` | Generate presigned S3/R2 upload URL | Yes | `media:upload` |
| `POST` | `/media/{id}/confirm` | Confirm upload completion and trigger transcode | Yes | `media:upload` |
| `POST` | `/media/{id}/playback-token` | Issue signed, short-lived HLS video stream token | Yes | Enrolled Student |
| `GET` | `/media/{id}/protected-pdf` | Stream protected watermarked PDF | Yes | Enrolled Student |

### 2.11 Notifications, Auditing & Health (`/api/v1/notifications`, `/api/v1/audit-logs`, `/api/v1/health`)

| Method | Endpoint | Description | Auth Required | Permissions |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/notifications` | List in-app notifications for authenticated user | Yes | Any Active |
| `PATCH` | `/notifications/{id}/read` | Mark individual notification as read | Yes | Notification Owner |
| `POST` | `/notifications/read-all` | Mark all notifications as read | Yes | Any Active |
| `GET` | `/audit-logs` | Filter and inspect immutable security audit trail | Yes | `audit:view` (Super Admin) |
| `GET` | `/health/live` | Kubernetes liveness probe (HTTP 200 if process runs) | No | Public |
| `GET` | `/health/ready` | Readiness probe (verifies PostgreSQL and Redis links) | No | Public |

---

## 3. Standard Request and Response Formats

### 3.1 Standard Success Envelope
```json
{
  "success": true,
  "data": {
    "id": "c1f7a28e-5b1b-4d4b-9c3f-7e8e12345678",
    "title": "Mastering Full-Stack Architecture",
    "slug": "mastering-full-stack-architecture",
    "status": "PUBLISHED",
    "price_inr": 499900
  },
  "meta": {
    "request_id": "req-9842a1bc-7832-4d0f-b12e-198273645012",
    "timestamp": "2026-11-13T21:45:00.000Z"
  }
}
```

### 3.2 Standard Error Envelope
```json
{
  "success": false,
  "error": {
    "code": "SESSION_REVOKED",
    "message": "Your session has been terminated because a newer login occurred on another device.",
    "details": {
      "revoked_at": "2026-11-13T21:44:50.000Z",
      "new_login_ip": "203.0.113.195"
    },
    "request_id": "req-9842a1bc-7832-4d0f-b12e-198273645012"
  }
}
```
