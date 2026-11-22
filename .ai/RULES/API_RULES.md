# API Contract, Versioning & Endpoint Rules (API_RULES)

## 1. API Architecture Baseline & URI Standards

This document establishes the binding standards for all RESTful API endpoints, request/response contracts, serialization schemas, error envelopes, and webhook integrations across the Single-Instructor LMS.

All endpoints must strictly adhere to the universal directives in [.ai/RULES/GLOBAL_RULES.md](file:///Users/priyansh/lms/.ai/RULES/GLOBAL_RULES.md) and security rules in [.ai/RULES/SECURITY_RULES.md](file:///Users/priyansh/lms/.ai/RULES/SECURITY_RULES.md).

---

## 2. Global API Conventions

* **Root Base Path**: All application endpoints must be prefixed with `/api/v1/` [Source: LMS Blueprint v2.0, Page 11].
* **Format & Serialization**: All payloads are strictly `application/json`. Charset is UTF-8.
* **Identifiers & Timestamps**:
  * All entity IDs must be valid UUID v4 strings (e.g., `3fa85f64-5717-4562-b3fc-2c963f66afa6`).
  * All timestamp fields must be serialized in ISO 8601 UTC format (`YYYY-MM-DDTHH:MM:SSZ`).
* **Monetary Values**: All financial amounts must be serialized as `BIGINT` in minor currency units (e.g., `49900` for INR ₹499.00).

---

## 3. Standard HTTP Methods & Semantic Rules

| Method | Idempotent | Semantic Purpose & Usage Rules |
| :--- | :---: | :--- |
| `GET` | Yes | Retrieve a resource or list of resources. Must never produce side effects or mutate server state. |
| `POST` | No | Create a new resource, execute a state transition, or initiate a transaction (e.g., checkout, login, submit). |
| `PUT` | Yes | Completely replace a mutable resource (e.g., autosaving answer payloads). |
| `PATCH` | No/Yes | Partial update to an existing resource (e.g., updating course fields, reordering curriculum, updating progress). |
| `DELETE` | Yes | Soft-delete or revoke a resource (e.g., revoking a session, archiving a question). |

* **Prohibited**: NEVER silently change an endpoint's HTTP method or URL path without explicit owner sign-off.

---

## 4. Standard Response & Error Envelopes

### Success Envelopes
* **Single Resource**: `200 OK` or `201 Created`
  ```json
  {
    "data": {
      "id": "c7a8b2d1-e5f6-4a3b-8c9d-0e1f2a3b4c5d",
      "title": "Python Mastery",
      "status": "draft",
      "version": 1
    },
    "request_id": "req_01HXYZ987654321"
  }
  ```
* **Collection / Paginated Response**:
  ```json
  {
    "data": [ ... ],
    "pagination": {
      "next_cursor": "eyJpZCI6ICJjN2E4YjJkMS0...In0=",
      "has_more": true,
      "page_size": 20
    },
    "request_id": "req_01HXYZ987654321"
  }
  ```

### Standard Error Envelope (Mandatory for All Errors) [Source: LMS Blueprint v2.0, Page 14]
```json
{
  "error": {
    "code": "CURRICULUM_VERSION_CONFLICT",
    "message": "This course was changed by another editor.",
    "details": {
      "current_version": 14
    },
    "request_id": "req_01HXYZ987654321"
  }
}
```

* **Zero Information Leakage**: The `error` object must **NEVER** expose stack traces, database schema names, raw SQL queries, or internal secret keys in any environment.

---

## 5. HTTP Status Code Mapping Table [Source: LMS Blueprint v2.0, Page 14]

| HTTP Code | Error Code Name | Semantic Meaning & Client Recovery Behavior |
| :---: | :--- | :--- |
| **`200`** | `OK` | Request succeeded. |
| **`201`** | `CREATED` | Resource successfully created. |
| **`400`** | `BAD_REQUEST` | Malformed payload or schema validation failure. Display field errors; preserve input. |
| **`401`** | `UNAUTHORIZED` | Missing, expired, or revoked session. Displaced session receives `SESSION_REVOKED`. |
| **`403`** | `FORBIDDEN` | Authenticated user lacks granular permission or record is out-of-scope. Deny without retry. |
| **`404`** | `NOT_FOUND` | Resource does not exist or user has no visibility. |
| **`409`** | `CONFLICT` | State, optimistic version, or idempotency conflict. Client reloads latest version and retries. |
| **`413`** | `PAYLOAD_TOO_LARGE` | Uploaded file or body exceeds configured byte limit. Display size cap message. |
| **`415`** | `UNSUPPORTED_MEDIA` | File format not on allowlist. Display accepted extensions. |
| **`422`** | `UNPROCESSABLE_ENTITY`| Business rule violation (e.g., sum of rubric points does not equal max points). Actionable message. |
| **`429`** | `TOO_MANY_REQUESTS` | Rate limit exceeded. Client must respect `Retry-After` header. |
| **`500`** | `INTERNAL_SERVER_ERROR`| Unhandled server crash. Log full details internally; display request ID to user. |
| **`502/503`**| `SERVICE_UNAVAILABLE`| Downstream dependency (payment gateway, transcoder) unreachable. Back off and queue async work. |

---

## 6. State Changes, Idempotency & Concurrency

1. **Mandatory Idempotency Keys**:
   * All state-changing mutation endpoints (`/checkout/orders`, `/admin/payments/:id/refund`, `/student/submissions/:id/submit`, `/student/attempts/:id/submit`) must require an `Idempotency-Key` header.
   * If a request is received with an existing idempotency key within its TTL window (e.g., 24 hours), the server must return the cached original response without re-executing business logic.
2. **Optimistic Concurrency**:
   * Mutable entities (curriculum sections, published courses) must use `version` integers or `ETag` headers. Updates must verify version match or return `409 CONFLICT`.

---

## 7. Pagination, Filtering & Sorting Standards

* **Cursor-Based Pagination**: High-volume listing endpoints (course catalog, student rosters, audit logs, order history) must implement cursor pagination using base64-encoded position markers. Offset-based (`LIMIT/OFFSET`) pagination is prohibited on large tables.
* **Safe Sorting**: Sort parameters must be restricted to an allowlist of indexed columns (e.g., `created_at`, `title`, `published_at`). Arbitrary column sorting that bypasses indexes is prohibited.
* **Scope-Aware Filtering**: All list filters must be applied inside the database query; in-memory filtering of out-of-scope records is strictly prohibited.

---

## 8. Webhook Endpoints & External Integrations

* **Webhook Route**: `POST /api/v1/webhooks/razorpay` [Source: LMS Blueprint v2.0, Pages 11, 13]
* **HMAC Signature Verification**: Every webhook request must verify the gateway's cryptographic signature using the configured webhook secret before parsing the payload.
* **Event Idempotency**: System must check `provider_event_id` against `payment_webhook_events`. Duplicate deliveries must immediately return `200 OK` without re-executing transactions.
