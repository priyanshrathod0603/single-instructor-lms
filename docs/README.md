# Documentation Index — Single-Instructor LMS

This directory contains the engineering specifications, architecture blueprints, completion audits, UI/UX reviews, and captured screenshots for the **Single-Instructor LMS** repository.

> **Important Source-of-Truth Note**: Historical milestone reports inside `docs/` and `.ai/MEMORY/` capture point-in-time snapshots from iterative implementation phases (for example, `FINAL_API_INTEGRATION_AUDIT.md` on 2026-11-16 predates later `SA-02`–`SA-05`, `VM-02`/`VM-03`, and Course Metadata Phase 1 additions). For the current end-to-end verified system state, refer to the root [README.md](../README.md) and actual source code.

---

## 1. Documentation Structure

| Directory / File | Scope |
| :--- | :--- |
| [Root README.md](../README.md) | Comprehensive project overview, verified feature audit, architecture diagrams, setup, API reference, and release status |
| [Backend Architecture (`docs/backend/`)](#2-backend-architecture-documents) | 25 technical specifications covering FastAPI, PostgreSQL 17 schema, security, workers, and deployment |
| [Frontend Blueprints (`docs/frontend/`)](#3-frontend-architecture--reports) | 17 architecture plans, route/API matrices, responsive audit reports, and 30 responsive Playwright screenshots |
| [Milestone & Governance Audits](#4-milestone--governance-reports) | Feature acceptance audits (`SA-02`–`SA-05`, `VM-02`, Phase 2 completion & remediation reports) |
| [UI/UX Redesign Preview (`docs/redesign_preview/`)](#5-uiux-audit--redesign-preview) | Nov 2026 UI/UX audit across 46 routes plus proposed redesign preview gallery and mock frames |
| [Early Roadmap (`phase.md`)](../phase.md) | Original multi-phase feature planning checklist |

---

## 2. Backend Architecture Documents

Located in [`docs/backend/`](backend/):

| Document | Topic |
| :--- | :--- |
| [00-BACKEND-OVERVIEW.md](backend/00-BACKEND-OVERVIEW.md) | System mission charter and design principles |
| [01-SYSTEM-ARCHITECTURE.md](backend/01-SYSTEM-ARCHITECTURE.md) | High-level backend subsystem architecture |
| [02-TECHNOLOGY-STACK.md](backend/02-TECHNOLOGY-STACK.md) | Backend runtime, framework, and library choices |
| [03-BACKEND-FOLDER-STRUCTURE.md](backend/03-BACKEND-FOLDER-STRUCTURE.md) | FastAPI layered directory organization |
| [04-DATABASE-ARCHITECTURE.md](backend/04-DATABASE-ARCHITECTURE.md) | Relational PostgreSQL schema and indexing design |
| [05-DATABASE-ER-DIAGRAM.md](backend/05-DATABASE-ER-DIAGRAM.md) | Entity-relationship specification |
| [06-API-ARCHITECTURE.md](backend/06-API-ARCHITECTURE.md) | REST endpoint design, pagination, and error envelopes |
| [07-AUTHENTICATION-ARCHITECTURE.md](backend/07-AUTHENTICATION-ARCHITECTURE.md) | Password hashing, JWT tokens, email reset, and Google OIDC |
| [08-SESSION-MANAGEMENT.md](backend/08-SESSION-MANAGEMENT.md) | Single-active-session invariant and displacement model |
| [09-RBAC-PERMISSION-ARCHITECTURE.md](backend/09-RBAC-PERMISSION-ARCHITECTURE.md) | Canonical 45-permission RBAC across 5 system roles |
| [10-USER-MANAGEMENT.md](backend/10-USER-MANAGEMENT.md) | Account lifecycle, status governance, and staff onboarding |
| [11-COURSE-MANAGEMENT.md](backend/11-COURSE-MANAGEMENT.md) | Immutable course revisions, drafts, sections, and lessons |
| [12-ENROLLMENT-PAYMENT-ARCHITECTURE.md](backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md) | Razorpay orders, webhook capture, refunds, and enrollments |
| [13-ASSIGNMENT-QUIZ-ARCHITECTURE.md](backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md) | Rubric versioning, submissions, overrides, and timed quizzes |
| [14-STUDENT-PROGRESS-ARCHITECTURE.md](backend/14-STUDENT-PROGRESS-ARCHITECTURE.md) | Watch telemetry, completion tracking, and QR certificates |
| [15-FILE-MEDIA-ARCHITECTURE.md](backend/15-FILE-MEDIA-ARCHITECTURE.md) | Presigned S3/R2 uploads, HLS transcoding, and PDF watermarking |
| [16-NOTIFICATION-ARCHITECTURE.md](backend/16-NOTIFICATION-ARCHITECTURE.md) | Transactional outbox pattern and multi-driver delivery |
| [17-AUDIT-LOG-ARCHITECTURE.md](backend/17-AUDIT-LOG-ARCHITECTURE.md) | Immutable audit trail design |
| [18-SECURITY-ARCHITECTURE.md](backend/18-SECURITY-ARCHITECTURE.md) | Defense-in-depth controls and secret management |
| [19-ERROR-HANDLING-STANDARDS.md](backend/19-ERROR-HANDLING-STANDARDS.md) | Structured API error codes and exception mapping |
| [20-TESTING-STRATEGY.md](backend/20-TESTING-STRATEGY.md) | Unit, security, and PostgreSQL concurrency testing strategy |
| [21-DEPLOYMENT-ARCHITECTURE.md](backend/21-DEPLOYMENT-ARCHITECTURE.md) | Production deployment topology and worker processes |
| [22-BACKEND-DEVELOPMENT-ROADMAP.md](backend/22-BACKEND-DEVELOPMENT-ROADMAP.md) | Backend task breakdown |
| [23-ARCHITECTURAL-DECISIONS.md](backend/23-ARCHITECTURAL-DECISIONS.md) | Recorded Architecture Decision Records (ADRs) |
| [24-FINAL-ARCHITECTURE-REVIEW.md](backend/24-FINAL-ARCHITECTURE-REVIEW.md) | Backend architecture review summary |
| [FINAL_SECURITY_REMEDIATION_REPORT.md](backend/FINAL_SECURITY_REMEDIATION_REPORT.md) | Security remediation verification report |

---

## 3. Frontend Architecture & Reports

Located in [`docs/frontend/`](frontend/):

- **Architecture & Planning**:
  - [FRONTEND_TECHNOLOGY_DECISION_REPORT.md](frontend/FRONTEND_TECHNOLOGY_DECISION_REPORT.md)
  - [FRONTEND_REPOSITORY_AUDIT.md](frontend/FRONTEND_REPOSITORY_AUDIT.md)
  - [FRONTEND_ARCHITECTURE_BLUEPRINT.md](frontend/FRONTEND_ARCHITECTURE_BLUEPRINT.md)
  - [FRONTEND_DESIGN_SYSTEM_IMPLEMENTATION_PLAN.md](frontend/FRONTEND_DESIGN_SYSTEM_IMPLEMENTATION_PLAN.md)
  - [FRONTEND_SECURITY_ARCHITECTURE.md](frontend/FRONTEND_SECURITY_ARCHITECTURE.md)
  - [FRONTEND_RESPONSIVE_STRATEGY.md](frontend/FRONTEND_RESPONSIVE_STRATEGY.md)
  - [FRONTEND_TESTING_STRATEGY.md](frontend/FRONTEND_TESTING_STRATEGY.md)
  - [FRONTEND_ROUTE_INVENTORY.md](frontend/FRONTEND_ROUTE_INVENTORY.md)
  - [FRONTEND_API_INTEGRATION_MATRIX.md](frontend/FRONTEND_API_INTEGRATION_MATRIX.md)
  - [FRONTEND_PART_1_IMPLEMENTATION_PLAN.md](frontend/FRONTEND_PART_1_IMPLEMENTATION_PLAN.md)
- **Phase Completion & Compliance Reports**:
  - [PART_1_1_FINAL_AUDIT_REPORT.md](frontend/PART_1_1_FINAL_AUDIT_REPORT.md)
  - [PART_1_2_COMPLIANCE_REMEDIATION_REPORT.md](frontend/PART_1_2_COMPLIANCE_REMEDIATION_REPORT.md)
  - [PART_2_COMPLETION_REPORT.md](frontend/PART_2_COMPLETION_REPORT.md)
  - [PART_2_UI_UX_CORRECTION_REPORT.md](frontend/PART_2_UI_UX_CORRECTION_REPORT.md)
  - [PART_3_COMPLETION_REPORT.md](frontend/PART_3_COMPLETION_REPORT.md)
  - [PART_5_READINESS_REPORT.md](frontend/PART_5_READINESS_REPORT.md)
  - [PART_5_COMPLETION_REPORT.md](frontend/PART_5_COMPLETION_REPORT.md)
- **Playwright Multi-Viewport Captures**: [`docs/frontend/screenshots/`](frontend/screenshots/) (30 screenshots across `320px`–`1440px`).

---

## 4. Milestone & Governance Reports

Located in [`docs/`](.):

- **Master Specification**: [MASTER_LMS_PRODUCT_REQUIREMENTS_AND_DEVELOPMENT_ROADMAP.md](MASTER_LMS_PRODUCT_REQUIREMENTS_AND_DEVELOPMENT_ROADMAP.md)
- **Phase 2 Audits & Remediation**:
  - [PHASE_2_PART_4_COMPLETION_REPORT.md](PHASE_2_PART_4_COMPLETION_REPORT.md)
  - [PHASE_2_PART_6_ACCEPTANCE_AUDIT.md](PHASE_2_PART_6_ACCEPTANCE_AUDIT.md)
  - [FINAL_API_INTEGRATION_AUDIT.md](FINAL_API_INTEGRATION_AUDIT.md)
  - [REMEDIATION_AUTH_MOBILE_NAV_RESPONSIVE_REPORT.md](REMEDIATION_AUTH_MOBILE_NAV_RESPONSIVE_REPORT.md)
- **Super Admin Governance (`SA-02`–`SA-05`)**:
  - [SA-02_USER_ADMIN_STAFF_MANAGEMENT_REPORT.md](SA-02_USER_ADMIN_STAFF_MANAGEMENT_REPORT.md)
  - [SA-02_FINAL_ACCEPTANCE_AUDIT.md](SA-02_FINAL_ACCEPTANCE_AUDIT.md)
  - [SA-03_SECURITY_GOVERNANCE_SPECIFICATION.md](SA-03_SECURITY_GOVERNANCE_SPECIFICATION.md)
  - [SA-03_FINAL_IMPLEMENTATION_REPORT.md](SA-03_FINAL_IMPLEMENTATION_REPORT.md)
  - [SA-04_FINAL_IMPLEMENTATION_REPORT.md](SA-04_FINAL_IMPLEMENTATION_REPORT.md)
  - [SA-05_FINAL_IMPLEMENTATION_REPORT.md](SA-05_FINAL_IMPLEMENTATION_REPORT.md)
- **Media & Transcoding (`VM-02`)**:
  - [VM-02_FINAL_IMPLEMENTATION_REPORT.md](VM-02_FINAL_IMPLEMENTATION_REPORT.md)

---

## 5. UI/UX Audit & Redesign Preview

Located in [`docs/redesign_preview/`](redesign_preview/):

- [FULL_LMS_UI_UX_AUDIT_REPORT.md](redesign_preview/FULL_LMS_UI_UX_AUDIT_REPORT.md) — Route-by-route UI/UX inspection across the 46 App Router pages.
- [index.html](redesign_preview/index.html) & [generate_previews.mjs](redesign_preview/generate_previews.mjs) — Interactive proposed redesign gallery and preview generator (`screenshots/`, `frames/`, and `lms_full_redesign_preview.mp4`). Note that images in `docs/redesign_preview/screenshots/` represent **proposed design mockups**, whereas [`docs/frontend/screenshots/`](frontend/screenshots/) holds live browser captures.
