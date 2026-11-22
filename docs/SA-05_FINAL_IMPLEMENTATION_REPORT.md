# SA-05 Complete Commercial Governance — Final Implementation & Acceptance Report

**Project**: Single-Instructor Learning Management System (LMS)  
**Lifecycle**: Super Admin Platform Governance  
**Task ID**: `SA-05`  
**Priority**: P0 Critical  
**Architecture Status**: Fully Approved, Implemented, and Empirically Verified  
**Report Status**: `COMPLETED_AND_VERIFIED`  
**Execution Timestamp**: 2026-11-16T20:55:00+05:30  

---

## 1. Executive Summary

Task **SA-05 Complete Commercial Governance** has been fully implemented end-to-end in accordance with the single-instructor architectural paradigm (`ONE INSTRUCTOR -> ONE BRAND -> MULTIPLE COURSES -> MULTIPLE STUDENTS -> DIRECT SALES`). The implementation provides the Super Admin with complete centralized commercial administrative control across three cohesive submodules:

1. **SA-05.1 — Offers & Discounts Management** (`/control/offers`):
   - Comprehensive directory of promotional discount campaigns and coupons.
   - Support for both percentage-based discounts (1–100%) and fixed amount discounts (in integer paise).
   - Flexible campaign scoping: platform-wide (all courses) or restricted to a specific course.
   - Lifecycle state machine: `ACTIVE`, `INACTIVE`, `ARCHIVED` with quick status toggles.
   - Strict validity window enforcement (`valid_to > valid_from`) and optional redemption limits (`usage_limit`).
   - Copy-to-clipboard code utility, detailed offer inspector, edit modal, and permanent deletion workflow with full audit logging.

2. **SA-05.2 — Payment Overview & Financial Surveillance** (`/control/payments`):
   - Real-time commercial surveillance dashboard computing financial metrics strictly from verified database records (`payment_transactions`, `orders`, `refunds`).
   - Strict integer paise arithmetic with zero floating-point rounding drift.
   - Surveillance KPI cards: Gross Revenue, Net Collections, Processed Refunds, Successful Payments, Pending Orders, and Failed Payments.
   - Multi-criteria transaction directory with search (payment ID, order number, student name/email, course), gateway status filtering (`SUCCESS`, `FAILED`), and date range filters (`start_date`, `end_date`).
   - Deep transaction inspection modal displaying order details, student metadata, enrolled course, and associated refund history.

3. **SA-05.3 — Platform Information & Settings** (`/control/settings`):
   - Centralized management of public brand identity and customer support channels (`platform_name`, `brand_name`, `brand_description`, `support_email`, `support_phone`, `logo_url`).
   - Safe, non-sensitive runtime system telemetry display (`version`, `environment`, `currency`, `frontend_url`, `cdn_stream_base_url`, `email_provider`, `storage_provider`, `updated_at`).
   - **Strict Master Secret Isolation Guarantee**: Cryptographic keys (`SECRET_KEY`), database passwords, Redis URLs, payment gateway secrets, SMTP credentials, and cloud storage access keys are strictly isolated in environment variables. They are never stored in the database or serialized across the control portal API.

---

## 2. Exact Files Created and Modified

### Database Schema & Migrations
- **Created**: [`backend/migrations/versions/20261116_1930_d0e1f2a3b4c5_create_offers_and_settings_tables.py`](file:///Users/priyansh/lms/backend/migrations/versions/20261116_1930_d0e1f2a3b4c5_create_offers_and_settings_tables.py)
  - Revision: `d0e1f2a3b4c5` (revises `c9d0e1f2a3b4`).
  - Creates `offers` table with foreign keys to `users.id` (RESTRICT) and `courses.id` (SET NULL), plus indexes on `code`, `status`, `course_id`, and `created_by_id`.
  - Creates `platform_settings` table with foreign key to `users.id` (SET NULL) and unique index on `key`.

### Backend Models & Schemas
- **Created**: [`backend/app/models/offer.py`](file:///Users/priyansh/lms/backend/app/models/offer.py) — SQLAlchemy model `Offer`, discount type constants (`PERCENTAGE`, `FIXED`), status constants (`ACTIVE`, `INACTIVE`, `ARCHIVED`), and ORM relationships.
- **Created**: [`backend/app/models/platform_setting.py`](file:///Users/priyansh/lms/backend/app/models/platform_setting.py) — SQLAlchemy model `PlatformSetting` with JSON value store and relationship to updating user.
- **Modified**: [`backend/app/models/__init__.py`](file:///Users/priyansh/lms/backend/app/models/__init__.py) — Exported `Offer`, `PlatformSetting`, and related status/discount constants.
- **Created**: [`backend/app/schemas/offer.py`](file:///Users/priyansh/lms/backend/app/schemas/offer.py) — Pydantic v2 schemas: `OfferCreateRequest`, `OfferUpdateRequest`, `OfferStatusRequest`, `OfferResponse`, `OfferListResponse`, `OfferCourseSummary`, `OfferCreatorSummary`.
- **Created**: [`backend/app/schemas/payment_overview.py`](file:///Users/priyansh/lms/backend/app/schemas/payment_overview.py) — Pydantic v2 schemas: `PaymentMetricsResponse`, `TransactionItemResponse`, `TransactionListResponse`, `TransactionOrderSummary`, `TransactionStudentSummary`, `TransactionCourseSummary`, `TransactionRefundSummary`.
- **Created**: [`backend/app/schemas/settings.py`](file:///Users/priyansh/lms/backend/app/schemas/settings.py) — Pydantic v2 schemas: `PublicPlatformInfoResponse`, `PlatformSettingsUpdateRequest`.

### Backend Repositories & Services
- **Created**: [`backend/app/repositories/offer_repo.py`](file:///Users/priyansh/lms/backend/app/repositories/offer_repo.py) — `OfferRepository` implementing filtered paginated queries, unique code verification, CRUD operations, and status updates.
- **Created**: [`backend/app/repositories/payment_overview_repo.py`](file:///Users/priyansh/lms/backend/app/repositories/payment_overview_repo.py) — `PaymentOverviewRepository` computing financial aggregates via SQL `coalesce(sum(...), 0)` and paginated transactions with consistent joined/selectin loader options.
- **Created**: [`backend/app/repositories/platform_settings_repo.py`](file:///Users/priyansh/lms/backend/app/repositories/platform_settings_repo.py) — `PlatformSettingsRepository` supporting `get_setting`, `set_setting`, and `get_all_settings`.
- **Created**: [`backend/app/services/offer_service.py`](file:///Users/priyansh/lms/backend/app/services/offer_service.py) — `OfferService` implementing business rule validations, unique code normalization, course scope verification, and structured audit events.
- **Created**: [`backend/app/services/payment_overview_service.py`](file:///Users/priyansh/lms/backend/app/services/payment_overview_service.py) — `PaymentOverviewService` providing commercial metrics calculation and transaction listing.
- **Created**: [`backend/app/services/platform_settings_service.py`](file:///Users/priyansh/lms/backend/app/services/platform_settings_service.py) — `PlatformSettingsService` synthesizing environment defaults with database overrides and emitting audit logs.

### Backend Control Endpoints & Security
- **Modified**: [`backend/app/api/v1/control.py`](file:///Users/priyansh/lms/backend/app/api/v1/control.py) — Added 11 endpoints under `/control/offers`, `/control/payments`, and `/control/settings` protected by Super Admin RBAC dependencies.
- **Modified**: [`backend/app/core/permissions.py`](file:///Users/priyansh/lms/backend/app/core/permissions.py) — Registered canonical permissions `OFFERS_MANAGE`, `PAYMENTS_VIEW_ALL`, `SETTINGS_MANAGE`. Excluded from `ROLE_ADMIN`, `ROLE_STAFF`, `ROLE_STUDENT`; included in `ROLE_SUPER_ADMIN`.
- **Modified**: [`backend/tests/unit/test_rbac_models.py`](file:///Users/priyansh/lms/backend/tests/unit/test_rbac_models.py) — Updated expected canonical permission count (42 -> 45) and verified Super Admin exclusivity.
- **Modified**: [`backend/tests/unit/test_migrations.py`](file:///Users/priyansh/lms/backend/tests/unit/test_migrations.py) — Updated expected tables (`offers`, `platform_settings`) and head revision (`d0e1f2a3b4c5`).

### Frontend Implementation
- **Created**: [`src/types/commerce.ts`](file:///Users/priyansh/lms/src/types/commerce.ts) — Full TypeScript types for Offers, Payments, and Settings.
- **Modified**: [`src/lib/api/control.ts`](file:///Users/priyansh/lms/src/lib/api/control.ts) — Added client methods for Offers, Payments, and Settings.
- **Modified**: [`src/components/navigation/StaffAdminSidebar.tsx`](file:///Users/priyansh/lms/src/components/navigation/StaffAdminSidebar.tsx) — Added sidebar navigation links and contextual back routing for `/control/offers`, `/control/payments`, and `/control/settings`.
- **Created**: [`src/app/(control)/control/offers/page.tsx`](file:///Users/priyansh/lms/src/app/(control)/control/offers/page.tsx) — Offers governance UI with KPI cards, filters, table, create modal, edit modal, inspect modal, and delete dialog.
- **Created**: [`src/app/(control)/control/payments/page.tsx`](file:///Users/priyansh/lms/src/app/(control)/control/payments/page.tsx) — Payment overview UI with 6 financial KPI cards, surveillance filters, transactions table, and inspection modal.
- **Created**: [`src/app/(control)/control/settings/page.tsx`](file:///Users/priyansh/lms/src/app/(control)/control/settings/page.tsx) — Platform settings UI with branding form, secret isolation notice, and runtime telemetry.

### Automated Test Suites
- **Created**: [`backend/tests/unit/test_sa05_commercial_governance.py`](file:///Users/priyansh/lms/backend/tests/unit/test_sa05_commercial_governance.py) — Comprehensive backend tests covering RBAC boundaries, offer CRUD, date validation, duplicate codes, status toggles, financial metrics accuracy, integer paise reconciliation, and settings secret isolation.
- **Created**: [`src/tests/unit/controlOffers.test.tsx`](file:///Users/priyansh/lms/src/tests/unit/controlOffers.test.tsx) — Frontend tests for Offers page (KPIs, table, create, inspect, edit, delete).
- **Created**: [`src/tests/unit/controlPayments.test.tsx`](file:///Users/priyansh/lms/src/tests/unit/controlPayments.test.tsx) — Frontend tests for Payments page (financial metrics, directory, inspection).
- **Created**: [`src/tests/unit/controlSettings.test.tsx`](file:///Users/priyansh/lms/src/tests/unit/controlSettings.test.tsx) — Frontend tests for Settings page (secret notice, form editing, submission).
- **Modified**: [`src/tests/unit/controlApi.test.ts`](file:///Users/priyansh/lms/src/tests/unit/controlApi.test.ts) — Added 3 test suites covering all SA-05 API client methods.

---

## 3. Endpoints Implemented

| Method | Route | Description | Permission Guard |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/control/offers` | Paginated listing of promotional offers with search, status, and discount type filters | `OFFERS_MANAGE` |
| `POST` | `/api/v1/control/offers` | Create a new promotional discount offer with validation | `OFFERS_MANAGE` |
| `GET` | `/api/v1/control/offers/{id}` | Inspect a single offer with creator and course metadata | `OFFERS_MANAGE` |
| `PUT` | `/api/v1/control/offers/{id}` | Update an existing offer (dates, discount value, scope, limits) | `OFFERS_MANAGE` |
| `PATCH` | `/api/v1/control/offers/{id}/status` | Quick toggle of offer lifecycle status (`ACTIVE`, `INACTIVE`, `ARCHIVED`) | `OFFERS_MANAGE` |
| `DELETE` | `/api/v1/control/offers/{id}` | Permanently delete an offer | `OFFERS_MANAGE` |
| `GET` | `/api/v1/control/payments/overview` | Real-time aggregate financial metrics calculated from DB | `PAYMENTS_VIEW_ALL` |
| `GET` | `/api/v1/control/payments/transactions` | Paginated transactions directory with search, status, and date range filters | `PAYMENTS_VIEW_ALL` |
| `GET` | `/api/v1/control/payments/transactions/{id}` | Deep transaction inspection with order, student, course, and refund relations | `PAYMENTS_VIEW_ALL` |
| `GET` | `/api/v1/control/settings` | Read-only runtime context and non-sensitive platform settings | `SETTINGS_MANAGE` |
| `PUT` | `/api/v1/control/settings` | Update authorized platform branding and contact settings | `SETTINGS_MANAGE` |

---

## 4. Database Migrations and Revision State

- **Current Revision**: `d0e1f2a3b4c5`
- **Migration Script**: `backend/migrations/versions/20261116_1930_d0e1f2a3b4c5_create_offers_and_settings_tables.py`
- **Revises**: `c9d0e1f2a3b4` (from SA-04 Content Governance)
- **Applied Environments**:
  - `lms_db` (Development PostgreSQL)
  - `lms_test_db` (Integration Test PostgreSQL)
- **Tables Created**:
  - `offers`: `id`, `name`, `code` (UNIQUE), `description`, `discount_type`, `discount_value`, `course_id` (FK -> `courses.id` ON DELETE SET NULL), `valid_from`, `valid_to`, `usage_limit`, `times_used`, `status`, `created_by_id` (FK -> `users.id` ON DELETE RESTRICT), `created_at`, `updated_at`.
  - `platform_settings`: `id`, `key` (UNIQUE), `value` (JSONB/TEXT), `updated_by_id` (FK -> `users.id` ON DELETE SET NULL), `updated_at`.

---

## 5. RBAC & Security Governance

- **Canonical Permissions Added**:
  - `OFFERS_MANAGE = "offers:manage"`
  - `PAYMENTS_VIEW_ALL = "payments:view_all"`
  - `SETTINGS_MANAGE = "settings:manage"`
- **Total Canonical Permissions**: 45 (expanded from 42).
- **Role Isolation Verification**:
  - `ROLE_SUPER_ADMIN`: Granted all 45 permissions via `ALL_PERMISSION_KEYS`.
  - `ROLE_ADMIN`: **Denied** (`offers:manage`, `payments:view_all`, `settings:manage` are excluded). Returns `403 Forbidden`.
  - `ROLE_STAFF`: **Denied**. Returns `403 Forbidden`.
  - `ROLE_STUDENT`: **Denied**. Returns `403 Forbidden`.
  - `ROLE_VISITOR` / Unauthenticated: Returns `401 Unauthorized`.
- **Master Secret Isolation Invariant**:
  - Master secrets (`SECRET_KEY`, database connection strings, Redis credentials, Razorpay key secret, Google OAuth secrets, SMTP passwords, cloud storage secrets) are never returned in `GET /control/settings`.
  - Master secrets cannot be overwritten via `PUT /control/settings`.
  - The frontend only receives safe, approved metadata (`version`, `environment`, `currency`, `frontend_url`, `cdn_stream_base_url`, `email_provider`, `storage_provider`).

---

## 6. Audit Trail & Event Logging

The following structured audit events are emitted and persisted directly to the `audit_logs` table:

| Event Name | Trigger | Resource Type | Metadata Captured |
| :--- | :--- | :--- | :--- |
| `OFFER_CREATED` | New offer created | `offer` | `code`, `discount_type`, `discount_value`, `course_id`, `valid_from`, `valid_to` |
| `OFFER_UPDATED` | Offer fields updated | `offer` | Changed fields, new discount/scope/date values |
| `OFFER_ACTIVATED` | Offer toggled to ACTIVE | `offer` | `previous_status`, `new_status: ACTIVE` |
| `OFFER_DEACTIVATED` | Offer toggled to INACTIVE | `offer` | `previous_status`, `new_status: INACTIVE` |
| `OFFER_ARCHIVED` | Offer toggled to ARCHIVED | `offer` | `previous_status`, `new_status: ARCHIVED` |
| `OFFER_DELETED` | Offer permanently deleted | `offer` | `code`, `deleted_at` |
| `PLATFORM_SETTINGS_UPDATED` | Brand settings updated | `platform_settings` | `updated_fields` list |

---

## 7. Financial Calculation Definitions

To prevent financial discrepancies, all monetary values are computed using integer paise:
1. **Gross Revenue (`gross_revenue_paise`)**:
   $$\text{gross\_revenue\_paise} = \sum_{\substack{\text{PaymentTransaction.status} = \text{'SUCCESS'}}} \text{amount\_inr}$$
2. **Refunded Amount (`refunded_amount_paise`)**:
   $$\text{refunded\_amount\_paise} = \sum_{\substack{\text{Refund.status} = \text{'PROCESSED'}}} \text{amount\_inr}$$
3. **Net Collected Revenue (`net_collected_paise`)**:
   $$\text{net\_collected\_paise} = \text{gross\_revenue\_paise} - \text{refunded\_amount\_paise}$$
4. **Order Counts**:
   - `successful_payments_count`: Count of transactions with `status = 'SUCCESS'`.
   - `failed_payments_count`: Count of transactions with `status = 'FAILED'`.
   - `pending_orders_count`: Count of orders with `status = 'PENDING'`.
   - `refunded_orders_count`: Count of orders with `status = 'REFUNDED'`.

---

## 8. Empirical Verification & Test Results

### 8.1 Backend Unit Tests
Command: `pytest backend/tests/unit/test_sa05_commercial_governance.py`
```
============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
backend/tests/unit/test_sa05_commercial_governance.py ........           [100%]
========================= 8 passed, 1 warning in 1.34s =========================
```

Full Backend Unit Test Suite: `pytest backend/tests/unit`
```
====================== 694 passed, 122 warnings in 41.64s ======================
```
- **Passed**: 694 / 694 tests (100% passing).
- Zero regressions across Auth, User Management, Content Governance, Sessions, Orders, and Security.

### 8.2 Backend PostgreSQL Integration Tests
Command: `pytest backend/tests/integration`
```
============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
backend/tests/integration/test_audit_triggers.py .....                   [ 25%]
backend/tests/integration/test_outbox_concurrency.py ..                  [ 35%]
backend/tests/integration/test_sa02_postgres_persistence.py ........     [ 75%]
backend/tests/integration/test_session_concurrency.py ..                 [ 85%]
backend/tests/integration/test_super_admin_concurrency.py ...            [100%]
======================== 20 passed, 1 warning in 1.78s =========================
```
- **Passed**: 20 / 20 integration tests on live PostgreSQL.

### 8.3 Frontend TypeScript & Vitest Tests
TypeScript Compile Check: `npx tsc --noEmit`
```
Exit code: 0 (Zero errors)
```

SA-05 Specific Frontend Unit Tests:
Command: `npm test src/tests/unit/controlOffers.test.tsx src/tests/unit/controlPayments.test.tsx src/tests/unit/controlSettings.test.tsx src/tests/unit/controlApi.test.ts`
```
Test Files  4 passed (4)
     Tests  27 passed (27)
  Duration  887ms
```

Full Frontend Vitest Suite: `npm test`
```
Test Files  38 passed (38)
     Tests  181 passed (181)
  Duration  3.56s
```
- **Passed**: 181 / 181 tests (100% passing across 38 files).

### 8.4 Production Next.js Build
Command: `npm run build`
```
Route (app)                                 Size  First Load JS
├ ƒ /control/offers                      9.31 kB         157 kB
├ ƒ /control/payments                    6.77 kB         152 kB
├ ƒ /control/settings                    6.12 kB         139 kB
✓ Generating static pages (40/40)
✓ Compiled successfully in 3.3s
```
- All 40 Next.js routes compiled cleanly with zero build errors or hydration warnings.

---

## 9. Governance & Invariant Compliance

1. **Reserved Files Integrity**: All 17 reserved governance files (`.ai/CORE/GOLDEN_RULES.md`, `.ai/RULES/*`, `.ai/GOVERNANCE/*`, `.ai/USER_WORKFLOW.md`) were verified and remain strictly untouched.
2. **Explicit Non-Goals & Scope Exclusions**:
   - **No Live Payment Gateway Modification**: No new payment gateways (Cashfree, Stripe) were introduced; existing Razorpay client infrastructure was preserved.
   - **No Student-Facing Offers / Checkout Total Alteration**: Offers management is exclusively administrative within the Super Admin portal (`/control/offers`). Checkout coupon redemption and student-facing checkout math were intentionally excluded from this scope.
   - **No Multi-Tenant Additions**: The platform strictly adheres to the single-instructor direct-to-student architecture.

---

## 10. Final Verification Status

**Final Status**: `COMPLETED_AND_VERIFIED`  
All components of SA-05 (Offers Management, Payment Overview, Platform Information & Settings) have been designed, implemented, migrated, tested, and verified end-to-end with 100% passing automated tests.
