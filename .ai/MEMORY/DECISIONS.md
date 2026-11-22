# Permanent Architecture & Product Decision Register

This register documents all fundamental architectural, technical, and business decisions for the Single-Instructor LMS.

Taxonomy of Approval Status:
* `APPROVED`: Formally signed off by project owner.
* `PROPOSED`: Proposed in the Blueprint specification baseline; active recommendation.
* `PENDING_APPROVAL`: Flagged as an open decision requiring explicit stakeholder sign-off prior to production.
* `SUPERSEDED`: Replaced by a newer approved decision.
* `REJECTED`: Formally considered and declined.

---

## 1. Approved Baseline Decisions

### DEC-001: Strict Single-Instructor / Single-Brand Product Model
* **Date**: 2026-11-13
* **Approval Status**: `APPROVED`
* **Decision Owner**: Project Owner / Blueprint Specification
* **Source**: `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 1, 2]
* **Context**: Choosing between a multi-instructor open marketplace (e.g., Udemy), a multi-tenant SaaS ERP (e.g., Canvas/Moodle), or a proprietary direct-to-student platform.
* **Chosen Option**: Single-Instructor Direct Sales Platform (`ONE INSTRUCTOR -> ONE BRAND -> MULTIPLE COURSES -> MULTIPLE STUDENTS -> DIRECT SALES`).

---

### DEC-002: Atomic Single-Active-Session Enforcement
* **Date**: 2026-11-13
* **Approval Status**: `APPROVED`
* **Decision Owner**: Project Owner / Blueprint Specification
* **Source**: `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 2, 8]
* **Context**: Credential sharing and account pooling severely erode digital course revenue.
* **Chosen Option**: Atomic server-side session revocation. Exactly one `ACTIVE` session per user in `auth_sessions`. A newly authenticated login atomically revokes the prior session (`status='REVOKED'`, `revoke_reason='NEW_LOGIN'`) and increments `auth_version`.

---

### DEC-003: PostgreSQL as Primary Relational Engine with UUID & JSONB
* **Date**: 2026-11-13
* **Approval Status**: `APPROVED`
* **Decision Owner**: Project Owner / Blueprint Specification
* **Source**: `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 8–11]
* **Chosen Option**: PostgreSQL with UUID primary keys (`gen_random_uuid()`), case-insensitive email (`CITEXT`), `JSONB` snapshots, and partial unique indexes (`WHERE status='ACTIVE'`).

---

### DEC-004: Immutable Published Course Revisions
* **Date**: 2026-11-13
* **Approval Status**: `APPROVED`
* **Decision Owner**: Project Owner / Blueprint Specification
* **Source**: `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 5, 9]
* **Chosen Option**: Revision branching. Published revisions are strictly immutable. Edits spawn a draft revision (`revision_no = N + 1`). Enrolled students remain anchored to the stable published revision until atomic cutover.

---

### DEC-005: Financial Precision: Minor Currency Units as BIGINT
* **Date**: 2026-11-13
* **Approval Status**: `APPROVED`
* **Decision Owner**: Project Owner / Blueprint Specification
* **Source**: `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 5, 8, 10]
* **Chosen Option**: `BIGINT` representing minor currency units (e.g., INR ₹499.00 is stored as `49900` paise).

---

### DEC-006: Webhook-Reconciled Enrollments (Zero Trust on Client Redirect)
* **Date**: 2026-11-13
* **Approval Status**: `APPROVED`
* **Decision Owner**: Project Owner / Blueprint Specification
* **Source**: `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 11, 14, 15]
* **Chosen Option**: Zero trust on browser redirect. Access is granted **only** after the server verifies the payment gateway's cryptographic webhook signature and updates the order status in an atomic transaction.

---

### DEC-007: Append-Only Immutable Audit Log
* **Date**: 2026-11-13
* **Approval Status**: `APPROVED`
* **Decision Owner**: Project Owner / Blueprint Specification
* **Source**: `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 3, 11]
* **Chosen Option**: Dedicated `audit_logs` table with DB permissions preventing `UPDATE` and `DELETE`. Records actor ID, resource type/ID, before/after JSON snapshots, IP prefix, and correlation IDs.

---

### DEC-008: FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Alembic Backend Framework
* **Date**: 2026-11-13
* **Approval Status**: `APPROVED`
* **Decision Owner**: Project Owner (Approved in TASK 0.2 Checkpoint)
* **Source**: Owner selection in Phase 1 Part 0 prompt interaction resolving `DEC-PEND-01`.
* **Context**: Reconciling proposed blueprint recommendation (Django REST Framework) with modern Python 3.14 async ecosystem.
* **Problem**: Selecting a backend framework that provides native asynchronous performance, strong Pydantic typing, clean OpenAPI generation, and seamless integration with PostgreSQL and Alembic.
* **Alternatives Considered**:
  1. Django REST Framework (DRF + Django ORM) — Proposed default in Blueprint v2.0 Page 2.
  2. FastAPI (Python 3.14 + SQLAlchemy 2.0 + Pydantic v2 + Alembic).
  3. NestJS (Node.js/TypeScript).
* **Chosen Option**: **FastAPI** with SQLAlchemy 2.0 ORM, Pydantic v2 settings/validation, and Alembic migrations.
* **Consequences**:
  * High-performance async request handling and automatic OpenAPI documentation.
  * Native type safety and clean separation between schemas and ORM models.
  * Resolves `DEC-PEND-01`.
* **Affected Modules**: All backend services, controllers, and database layers.

---

## 2. Pending Decisions (Pre-Production Stakeholder Review)

| Decision ID | Topic | Proposed Option | Pending Alternatives | Owner | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DEC-PEND-01** | Backend Framework | FastAPI (Python 3.14) | Resolved by DEC-008 | Project Owner | `SUPERSEDED` |
| **DEC-PEND-02** | Video Delivery Provider | Managed Signed Video (Mux / Cloudflare Stream) | AWS MediaConvert + CloudFront Signed Cookies | Project Owner | `PENDING_APPROVAL` |
| **DEC-PEND-03** | PDF Security Viewer | Protected Canvas + Signed URL (No Download) | Dynamic PDF Watermarking (Student Email Stamp) | Project Owner | `PENDING_APPROVAL` |
| **DEC-PEND-04** | Assignment Late Penalty | Configurable daily % penalty | Hard cutoff (Reject after due date) | Project Owner | `PENDING_APPROVAL` |
| **DEC-PEND-05** | Enrollment Expiration | Lifetime access default | Fixed 365-day access / Subscription | Project Owner | `PENDING_APPROVAL` |
| **DEC-PEND-06** | Quiz Result Release | Immediate auto-score for objective questions | Scheduled release after quiz close date | Project Owner | `PENDING_APPROVAL` |
| **DEC-PEND-07** | Session Cache Layer | PostgreSQL Row Lock + auth_version | Redis Token Blacklist with TTL | Engineering Lead | `PENDING_APPROVAL` |
| **DEC-PEND-08** | Asynchronous Job Broker | Celery + Redis | BullMQ / Redis or AWS SQS | Engineering Lead | `PENDING_APPROVAL` |
| **DEC-PEND-09** | Email Service Provider | Transactional SMTP (Postmark / Resend / SES) | SendGrid, Mailgun | Engineering Lead | `PENDING_APPROVAL` |
| **DEC-PEND-10** | Storage Provider | AWS S3 Private Bucket | Cloudflare R2 / Google Cloud Storage | Engineering Lead | `PENDING_APPROVAL` |
