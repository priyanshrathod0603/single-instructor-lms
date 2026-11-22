# Technology Stack: Detected, Proposed & Pending

This document details the technology choices for the Single-Instructor LMS, rigorously separating verified codebase facts from proposed blueprint recommendations and unresolved technical decisions.

---

## 1. Section A: Currently Detected Stack (Verified Repository State)

A physical filesystem inspection was conducted on **2026-11-13** in `/Users/priyansh/lms`:

| Component Layer | Technology Detected | Version | Verification Evidence | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Workspace Root** | Empty Directory | N/A | `ls -la` returned 0 entries | `INITIALIZED_EMPTY` |
| **Frontend Framework** | None | None | No `package.json`, `tsconfig.json`, or UI source files | `NOT_INSTALLED` |
| **Frontend Language** | None | None | No `.ts`, `.tsx`, or `.js` source files | `NOT_INSTALLED` |
| **Build Tooling** | None | None | No Webpack, Vite, or Next.js config | `NOT_INSTALLED` |
| **Styling Framework** | None | None | No Tailwind, CSS Modules, or Sass files | `NOT_INSTALLED` |
| **Backend Framework** | None | None | No `manage.py`, `app.py`, `main.py`, or Express/Nest files | `NOT_INSTALLED` |
| **Database & ORM** | None | None | No migration scripts, schema definitions, or DB configs | `NOT_CONFIGURED` |
| **Queue / Cache** | None | None | No Redis config, Celery tasks, or BullMQ queues | `NOT_CONFIGURED` |
| **Storage & Video** | None | None | No AWS/GCS/Cloudflare client configs | `NOT_INTEGRATED` |
| **Payment Gateway** | None | None | No Razorpay or payment provider SDKs | `NOT_INTEGRATED` |
| **Version Control** | None | None | Directory not yet initialized as a Git repository | `UNINITIALIZED` |

---

## 2. Section B: Proposed Blueprint Stack

The proposed baseline is specified in `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 1–16]:

| Layer | Proposed Technology | Justification in Blueprint | Blueprint Reference |
| :--- | :--- | :--- | :--- |
| **Frontend Core** | Next.js / React + TypeScript | High performance, server-side rendering (SSR) for marketing SEO, client-side rendering (CSR) for interactive dashboards and video players. | [Source: LMS Blueprint v2.0, Page 2] |
| **Backend API** | Django REST Framework (DRF) | Robust ORM, built-in admin tooling, transactional boundaries, enterprise security baseline, maturity with relational schemas. | [Source: LMS Blueprint v2.0, Page 2] |
| **Primary Database** | PostgreSQL 15+ | Native support for UUIDs (`gen_random_uuid()`), case-insensitive text (`CITEXT`), `JSONB` document snapshots, and partial unique indexes for single-active-session enforcement. | [Source: LMS Blueprint v2.0, Pages 8–11] |
| **Queue & Cache** | Celery + Redis | Asynchronous video transcode coordination, transactional outbox mailer processing, CSV bulk question import, and distributed locks. | [Source: LMS Blueprint v2.0, Pages 2, 14] |
| **Payment Gateway** | Razorpay | Direct-to-instructor merchant settlement, Indian/international cards, UPI, net banking, signed webhook events, automated refunds. | [Source: LMS Blueprint v2.0, Pages 2, 10, 13] |
| **Asset Storage** | Private S3 / GCS Object Store | Secure private buckets, presigned upload intents, checksum/MIME validation, immutable asset versioning. | [Source: LMS Blueprint v2.0, Pages 5, 9, 14] |
| **Video Delivery** | Managed Signed Video Provider | Adaptive bitrate HLS streaming, token-authenticated short-lived playback URLs preventing stream scraping (e.g., Cloudflare Stream, Mux, or AWS CloudFront Signed Cookies). | [Source: LMS Blueprint v2.0, Pages 5, 16] |
| **PDF Delivery** | Protected Canvas / Signed Stream | File signature validation, malware scanning, watermarking, download suppression by default. | [Source: LMS Blueprint v2.0, Pages 5, 14] |

---

## 3. Section C: Confirmed Stack Decisions

* **Backend Framework**: **FastAPI** (Python 3.14) with **SQLAlchemy 2.0** ORM, **Pydantic v2**, and **Alembic** migrations. Formally approved by project owner as `DEC-008` (resolving `DEC-PEND-01`).
* **Database Engine**: PostgreSQL 17 is formally confirmed as the relational database engine due to structural schema requirements (partial unique indexes on `auth_sessions`, `CITEXT` unique emails, and `JSONB` snapshots) [Source: LMS Blueprint v2.0, Pages 8–11].
* **Currency Standard**: All monetary values stored as `BIGINT` in minor currency units (e.g., paise for INR) [Source: LMS Blueprint v2.0, Page 8].
* **Timezone Standard**: All server timestamps stored in UTC using `TIMESTAMPTZ`; localized at client presentation layer [Source: LMS Blueprint v2.0, Page 8].
* **Primary Key Standard**: All tables utilize UUID primary keys (`UUID DEFAULT gen_random_uuid()`) [Source: LMS Blueprint v2.0, Page 8].
* **Password Hashing**: Argon2id ($m=65536, t=3, p=4$) [ADR-006].
* **Session Management**: Single-Active-Session with atomic database displacement and `__Host-lms_session` cookies [ADR-002].
* **Documentation Base**: Complete 24-document architectural specification in `docs/backend/`.

---

## 4. Section D: Pending Technology Decisions (Pre-Production)

The following 9 architectural decisions remain for vendor selection during implementation:

| Decision Key | Topic | Proposed Baseline / Recommended Default | Alternatives Under Consideration | Impact & Risks | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| ~~**DEC-PEND-01**~~ | ~~**Backend Stack Finalization**~~ | ~~Django REST Framework~~ | **FastAPI (Python 3.14 + SQLAlchemy 2.0)** | High performance async, Pydantic type safety. | **RESOLVED (`DEC-008`)** |
| **DEC-PEND-02** | **Video Delivery Provider** | Managed signed playback provider (e.g., Cloudflare Stream / Mux) | Self-hosted AWS MediaConvert + S3 + CloudFront signed URLs | Managed providers reduce transcoding maintenance; self-hosted reduces per-minute streaming costs at high volume. |
| **DEC-PEND-03** | **PDF Security & Viewer** | Private storage with short-lived signed URLs; downloads disabled by default | Dynamic server-side watermarking (student email/IP stamped on pages) + canvas rendering | Watermarking increases deterrence against screenshots but adds rendering latency. |
| **DEC-PEND-04** | **Course Revision Cutover** | Immutable published revision snapshot; new draft branch; preserve stable lesson IDs | In-place live edits with warning badges | In-place edits risk breaking student progress; revision branching preserves historical integrity. |
| **DEC-PEND-05** | **Enrollment Duration Policy** | Lifetime access default unless course config specifies `fixed_days` | Time-bounded access or monthly/annual subscription | Impacts database expiration checkers and recurring billing logic. |
| **DEC-PEND-06** | **Late Assignment Policy** | Accept late submissions with visible `is_late` flag; configurable penalty per day | Hard cutoff (reject submissions after deadline) | Pedagogical flexibility vs. strict automated grading rules. |
| **DEC-PEND-07** | **Quiz Results Release** | Objective questions auto-score; essay questions manual review; configurable release (immediate vs after close) | Strictly manual release for all exams | Immediate release improves learner feedback; scheduled release prevents answer sharing among peers. |
| **DEC-PEND-08** | **Session Revocation Mechanism** | Atomic DB update (`status='REVOKED'`) + `auth_version` bump + `401 SESSION_REVOKED` | Distributed Redis token blacklist with TTL | DB row lock guarantees zero-race condition; Redis blacklist provides sub-millisecond lookups. |
| **DEC-PEND-09** | **Refund Entitlement Revocation** | Explicit immediate entitlement revocation upon successful refund | Grace period until end of billing cycle | Immediate revocation prevents exploitation; requires transaction coordination. |
| **DEC-PEND-10** | **Audit & Log Data Retention** | Indefinite append-only storage for financial and security audit trails; 90-day retention for raw access logs | 1-year rolling purge for all logs | Compliance and accounting obligations require permanent financial records. |

---

## 5. Section E: Technologies Explicitly Not Approved for Migration

To prevent architectural thrashing, the following rules apply:
1. **No Unapproved Framework Swaps**: The proposed baseline (Next.js/React + Django REST Framework + PostgreSQL) must not be replaced with micro-frameworks (e.g., Flask, Express) or NoSQL databases (e.g., MongoDB) without explicit written user approval [Source: LMS Blueprint v2.0, Pages 2, 16].
2. **No Multi-Tenant Add-Ons**: Framework extensions adding multi-tenant schema routing (e.g., `django-tenants`) are prohibited as the product model is strictly single-instructor [Source: LMS Blueprint v2.0, Page 1].
3. **No Insecure Client-Side Storage**: Storing authentication bearer tokens in `localStorage` or `sessionStorage` is strictly forbidden [Source: LMS Blueprint v2.0, Page 8].
