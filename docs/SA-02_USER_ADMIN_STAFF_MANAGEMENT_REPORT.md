# Implementation & Verification Report: SA-02 — Complete User, Admin & Staff Management

**Project**: Single-Instructor LMS  
**Lifecycle**: Super Admin Platform Governance  
**Task ID**: `SA-02`  
**Priority**: CRITICAL  
**Status**: **COMPLETED & EMPIRICALLY VERIFIED**  
**Date**: November 16, 2026  
**Execution Mode**: INSPECT → PLAN → IMPLEMENT → TEST → VERIFY  

---

## 1. Executive Summary

Task **SA-02: Complete User, Admin & Staff Management** has been successfully designed, implemented, and verified end-to-end within the Single-Instructor LMS architecture.

SA-02 establishes centralized governance authority over the entire platform identity lifecycle. It provides the Super Administrator (Platform Owner) with comprehensive administrative interfaces and secure backend endpoints to:
1. Search, filter, sort, inspect, and manage all platform users across all system roles (**User Directory** at `/control/users`).
2. Audit comprehensive academic and performance ledgers for enrolled students, including course progress, quiz assessments, assignment deliverables, verifiable certificates, and security audit trails (**Student Profile View** at `/control/users/[id]`).
3. Onboard and govern delegated platform administrators with strict privilege escalation prevention (**Administrator Hub** at `/control/admins`).
4. Onboard, audit, and regulate teaching assistants and grading staff with scoped rubric evaluation privileges (**Staff Management** at `/control/staff`).
5. Enforce mathematical safeguards protecting the sole active Super Admin account against demotion or suspension via database row-level serialization locks.
6. Trigger immediate session displacement and token revocation upon administrative account suspension while preserving student learning history.

All features are connected to live backend database models with zero unapproved migrations, zero synthetic numbers, and zero security bypasses.

---

## 2. Business Architecture & Single-Instructor Product Model

The LMS adheres strictly to the single-instructor commercial model:
$$\text{ONE INSTRUCTOR} \longrightarrow \text{ONE BRAND} \longrightarrow \text{MULTIPLE COURSES} \longrightarrow \text{MULTIPLE STUDENTS} \longrightarrow \text{DIRECT SALES}$$

### Core Operating Principles
* **Non-Marketplace Architecture**: Public self-registration always assigns `ROLE_STUDENT`. There is no public instructor registration, multi-vendor commission splits, or third-party storefronts.
* **Centralized Authority Delegation**: Privileged roles (`STAFF`, `ADMIN`, `SUPER_ADMIN`) cannot be granted via public checkout or self-assignment. Privileged access is granted strictly through cryptographically signed onboarding tokens (48h TTL) or direct Super Admin assignment.
* **Separation of Concerns**:
  - **Student**: Consumes courses, takes assessments, submits deliverables, views certificates.
  - **Staff**: Evaluates submissions, grades against rubrics, reviews student progress.
  - **Admin**: Manages courses, curriculum hierarchy, media library, student rosters, and orders.
  - **Super Admin**: Platform Owner with absolute governance, API secret management, and role delegation.

---

## 3. Technical Architecture & Component Tree

```mermaid
graph TD
    subgraph Frontend ["Frontend (Next.js 15 App Router)"]
        Nav["StaffAdminSidebar (/control Navigation)"]
        UserDir["/control/users (User Directory)"]
        UserDetail["/control/users/[id] (Student Learning Profile)"]
        AdminHub["/control/admins (Administrator Hub)"]
        StaffPage["/control/staff (Staff Management)"]

        UserDir --> RoleModal["Role Management Modal"]
        UserDir --> StatusModal["Status Confirmation Modal"]
        AdminHub --> InviteAdminModal["Invite Administrator Modal"]
        StaffPage --> InviteStaffModal["Invite Staff Modal"]
    end

    subgraph ClientAPI ["Frontend API Layer (src/lib/api/users.ts)"]
        listUsers["usersApi.listUsers()"]
        getUser["usersApi.getUser()"]
        getLearning["usersApi.getStudentLearningRecords()"]
        manageRole["usersApi.manageRole()"]
        updateStatus["usersApi.updateStatus()"]
        inviteStaff["usersApi.inviteStaff()"]
    end

    subgraph BackendAPI ["FastAPI REST Endpoints (backend/app/api/v1/users.py)"]
        GET_Users["GET /api/v1/users"]
        GET_User["GET /api/v1/users/{id}"]
        GET_Records["GET /api/v1/users/{id}/learning-records"]
        PATCH_Roles["PATCH /api/v1/users/{id}/roles"]
        PATCH_Status["PATCH /api/v1/users/{id}/status"]
        POST_Invite["POST /api/v1/users/staff/invite"]
    end

    subgraph ServiceLayer ["UserService (backend/app/services/user_service.py)"]
        SvcList["list_users(search, role, active, verified, sort)"]
        SvcLearning["get_student_learning_summary(user_id)"]
        SvcRoles["manage_user_role(sole_super_admin_lock)"]
        SvcStatus["update_user_status(session_revocation)"]
        SvcInvite["invite_staff(super_admin_guard)"]
    end

    subgraph DatabaseLayer ["PostgreSQL Database Tables"]
        T_Users["users & user_roles"]
        T_Enrollments["enrollments & courses"]
        T_Progress["course_progress_summaries"]
        T_Quizzes["quizzes & quiz_attempts"]
        T_Assignments["assignments & assignment_submissions"]
        T_Certs["certificates"]
        T_Audit["audit_logs"]
        T_Sessions["auth_sessions"]
    end

    UserDir --> listUsers
    UserDetail --> getLearning
    AdminHub --> inviteStaff
    RoleModal --> manageRole
    StatusModal --> updateStatus

    listUsers --> GET_Users --> SvcList --> T_Users
    getLearning --> GET_Records --> SvcLearning --> T_Enrollments & T_Progress & T_Quizzes & T_Assignments & T_Certs & T_Audit
    manageRole --> PATCH_Roles --> SvcRoles --> T_Users & T_Audit
    updateStatus --> PATCH_Status --> SvcStatus --> T_Users & T_Sessions & T_Audit
    inviteStaff --> POST_Invite --> SvcInvite --> T_Users & T_Audit
```

---

## 4. Backend Schema & API Specifications

### New & Enhanced Schemas (`backend/app/schemas/user.py`)
* `StudentEnrollmentSummary`: `id`, `course_id`, `course_title`, `course_slug`, `status`, `granted_at`, `expires_at`, `progress_percentage`, `completed_lessons_count`, `total_lessons_count`, `last_activity_at`.
* `StudentQuizAttemptSummary`: `id`, `quiz_id`, `quiz_title`, `attempt_no`, `status`, `score`, `is_passed`, `started_at`, `completed_at`.
* `StudentAssignmentSubmissionSummary`: `id`, `assignment_id`, `assignment_title`, `attempt_no`, `status`, `final_score`, `max_score`, `pass_score`, `file_url`, `submitted_at`, `graded_at`, `feedback`.
* `StudentCertificateSummary`: `id`, `certificate_no`, `course_id`, `course_title`, `issued_at`, `verification_hash`, `pdf_url`, `is_revoked`, `revoked_at`, `revoked_reason`.
* `StudentLearningSummaryResponse`: Consolidated academic ledger containing `user`, `enrollments`, `quiz_attempts`, `assignment_submissions`, `certificates`, and `audit_logs`.
* `UserRoleUpdateRequest`: `{ role_id: str, action: "ASSIGN" | "REVOKE" }`.

### API Endpoints
| HTTP Method | Route | Permission Guard | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/users` | `users:view_all` | Paginated directory with `search`, `role`, `is_active`, `is_verified`, `sort_by`, `sort_order`. |
| `GET` | `/api/v1/users/{id}` | Self / `users:view` / Super Admin | Detailed profile with roles and aggregated permissions. |
| `GET` | `/api/v1/users/{id}/learning-records` | Self / `users:view` / Super Admin | Complete student performance and academic history ledger. |
| `PATCH` | `/api/v1/users/{id}/profile` | Self / `users:edit` / Super Admin | Updates full_name and avatar_url with transactional auditing. |
| `PATCH` | `/api/v1/users/{id}/status` | `users:manage_status` | Activates or suspends user with atomic session revocation. |
| `PATCH` | `/api/v1/users/{id}/roles` | `roles:assign` | Assigns or revokes roles with sole Super Admin protection lock. |
| `POST` | `/api/v1/users/staff/invite` | `staff:invite` | Issues 48h onboarding token; role `ADMIN` strictly requires Super Admin caller. |

---

## 5. Centralized User Directory (`/control/users`) Implementation

### Features
1. **Multi-Role Filtering Tabs**: All Users, Students, Staff, Admins, Super Admins with count awareness and page reset.
2. **Search with Dynamic Query**: Debounced search query across normalized email and full name.
3. **Status Filter**: All Statuses, Active Only, Suspended Only.
4. **Verification Filter**: All Accounts, Verified Only, Unverified Only.
5. **Multi-Column Sorting**:
   - Newest First (`created_at` DESC)
   - Oldest First (`created_at` ASC)
   - Name A-Z (`full_name` ASC)
   - Name Z-A (`full_name` DESC)
   - Email A-Z (`email` ASC)
6. **Directory Table**: Full name, email, avatar fallback, role badges, status badge, verification indicator, joined date, action buttons.
7. **Action Modals**:
   - Role Management Modal: Assign or revoke roles with warning on Super Admin modification.
   - Status Confirmation Modal: Suspend or activate account with reason input and session displacement warning.
8. **Server-Side Pagination**: Previous / Next controls with page count summary.

---

## 6. Student Profile & Academic Ledger (`/control/users/[id]`) Implementation

### Overview
Located at `/control/users/[id]`, this view provides administrators with an exhaustive pedagogical ledger for any student user.

### Five Structured Data Tabs
1. **Course Enrollments & Progress**:
   - Course title, slug, and status badge (`ACTIVE`, `REVOKED`, `EXPIRED`).
   - Dynamic progress bar with exact completion percentage (e.g., 75.0%).
   - Lessons completed versus total published lessons.
   - Access expiration date (or Lifetime Access indicator).
2. **Quiz Assessments**:
   - Assessment title and attempt counter.
   - Status (`SUBMITTED`, `IN_PROGRESS`, `EXPIRED`).
   - Final score percentage and Pass/Fail badge.
   - Started and completed timestamps.
3. **Assignment Deliverables**:
   - Project title and attempt counter.
   - Status (`GRADED`, `SUBMITTED`, `GRADING`, `REJECTED`).
   - Final score versus maximum and passing thresholds.
   - Evaluator qualitative feedback.
   - Signed deliverable download link (`file_url`).
4. **Verifiable Certificates**:
   - Certificate number and associated course.
   - Verification status badge (`Verifiable` vs `Revoked`).
   - HMAC-SHA256 signature hash.
   - Direct link to public verification endpoint (`/verify/certificate/[hash]`).
   - Direct PDF download link.
5. **Security & Operational Activity Trail**:
   - Chronological table of audit events where the user was actor or target.
   - Action verbs, actor types, IP addresses, and timestamps.

---

## 7. Administrator Management Hub (`/control/admins`) Implementation

### Features
1. **Dedicated Administrator Roster**: Displays all active and suspended users holding `ADMIN` or `SUPER_ADMIN` roles.
2. **Invite Administrator Flow**:
   - Modal to invite a new Administrator with full name and email.
   - Enforces backend check: only callers holding `ROLE_SUPER_ADMIN` can issue `ADMIN` invitations.
   - Generates 32-byte cryptographic token (48h TTL) and stages transactional outbox email.
3. **Demote Administrator Action**:
   - Revokes the `ADMIN` role from delegated operators.
   - Disabled for Super Admin platform owners to prevent accidental lockout.
4. **Suspend / Activate Administrator Action**:
   - Immediately terminates active administrator sessions across all devices.

---

## 8. Staff & Teaching Assistant Management (`/control/staff`) Implementation

### Enhancements
1. **Roster Integration**: Table displaying all staff members holding `ROLE_STAFF`.
2. **Direct Profile Navigation**: "Profile" action navigating to `/control/users/[id]`.
3. **Demote Staff Action**: Modal allowing Super Admins to revoke teaching assistant privileges.
4. **Suspend / Activate Staff Action**: Modal allowing immediate suspension of staff accounts with session revocation.
5. **Invite Staff Flow**: Stages transactional outbox invitation with role `STAFF`.

---

## 9. Role-Based Access Control (RBAC) & Dynamic Role Mutation

### Roles Hierarchy & Canonical Permissions
* `ROLE_STUDENT`: `assignment:submit`, `quiz:attempt`, `media:view_protected`.
* `ROLE_STAFF`: `assignment:grade`, `students:view_progress`, `media:upload`.
* `ROLE_ADMIN`: `course:create`, `course:edit`, `course:publish`, `curriculum:manage`, `staff:invite`, `enrollment:grant`, `payments:refund`.
* `ROLE_SUPER_ADMIN`: Universal bypass across all permissions, `roles:assign`, `course:delete`, platform key management.

### Transactional Mutation (`PATCH /api/v1/users/{id}/roles`)
* Role assignments and revocations are atomic.
* Every role transition creates an immutable record in `audit_logs` capturing `actor_id`, `actor_type="SUPER_ADMIN"`, and `after_state={"role_id": ..., "action": ...}`.

---

## 10. Sole Super Admin Protection Invariant (Row-Level DB Serialization Lock)

### Mathematical Protection Guarantee
Under no circumstances may the final active Super Admin account be suspended, demoted, or deleted.

### Database Serialization Lock (BUG-006)
```python
if clean_action == "REVOKE" and clean_role == ROLE_SUPER_ADMIN:
    stmt_lock = select(Role).where(Role.id == ROLE_SUPER_ADMIN).with_for_update()
    if isinstance(session, AsyncSession):
        await session.execute(stmt_lock)
    else:
        session.execute(stmt_lock)

    active_count = await self.user_repo.count_active_super_admins(session)
    if active_count <= 1:
        raise ConflictException(
            message="Cannot demote or revoke role from the sole active Super Admin.",
            code="CANNOT_DEMOTE_LAST_SUPER_ADMIN",
        )
```
* Even under high-concurrency race conditions where two administrators attempt simultaneous mutual demotion, the row-level lock on `roles WHERE id='SUPER_ADMIN'` serializes execution, guaranteeing that `active_count` is evaluated sequentially.

---

## 11. Account Status Transitions & Immediate Session Displacement

### Invariant
Suspending an account (`is_active=False`) must immediately displace all active sessions across all devices.

### Implementation
In `UserService.update_user_status`:
```python
await self.user_repo.update_status(session, user.id, is_active)

if not is_active:
    await self.session_repo.revoke_all_user_sessions(session, user.id)
```
* `revoke_all_user_sessions` transitions all `auth_sessions` rows where `user_id = :id` and `status = 'ACTIVE'` to `'REVOKED'`, recording `revoked_at = utc_now()`.
* On the next API heartbeat or navigation, the client encounters HTTP `401 SESSION_REVOKED`, which triggers the frontend displacement overlay and clears local credentials.
* Any future authentication attempts fail closed with HTTP `403 ACCOUNT_SUSPENDED`.

---

## 12. Search, Filter, and Dynamic Multi-Column Sorting

### Repository Query Optimization (`backend/app/repositories/user_repo.py`)
```python
sort_col = User.created_at
if sort_by == "full_name":
    sort_col = User.full_name
elif sort_by == "email":
    sort_col = User.email
elif sort_by == "created_at":
    sort_col = User.created_at

if sort_order and sort_order.lower() == "asc":
    stmt = stmt.order_by(sort_col.asc())
else:
    stmt = stmt.order_by(sort_col.desc())
```
* Sanitized against SQL injection: `sort_by` is whitelist-matched against explicit SQLAlchemy entity attributes.

---

## 13. Security Analysis & Privilege Escalation Defenses

### Vulnerability Analysis & Mitigations
1. **Admin Privilege Escalation Attack**:
   - *Risk*: A rogue or compromised Admin caller with `staff:invite` invites themselves or another account with `role="ADMIN"`.
   - *Defense*: `backend/app/api/v1/users.py` checks `if payload.role == ROLE_ADMIN and not current_user.has_role(ROLE_SUPER_ADMIN): raise ForbiddenException("Only Super Administrators can invite administrators.", code="SUPER_ADMIN_REQUIRED")`.
2. **IDOR on Student Learning Records**:
   - *Risk*: Student A calls `GET /api/v1/users/{studentB_id}/learning-records` to scrape grades and submissions.
   - *Defense*: Endpoint checks `is_self = current_user.id == id`, `is_super = current_user.has_role(ROLE_SUPER_ADMIN)`, and `has_perm = current_user.has_permission(USERS_VIEW)`. Students can only inspect their own records.
3. **Sole Super Admin Lockout**:
   - *Risk*: Malicious or accidental suspension of platform owner.
   - *Defense*: Guarded with PostgreSQL row-level locks and HTTP 409 Conflict rejection.

---

## 14. Database Relational Integrity & Schema Preservation

### Invariant Compliance
* **Zero Migrations Executed**: All functionality utilizes existing production tables: `users`, `roles`, `user_roles`, `permissions`, `role_permissions`, `enrollments`, `courses`, `course_progress_summaries`, `quizzes`, `quiz_attempts`, `assignments`, `assignment_submissions`, `certificates`, `audit_logs`, `auth_sessions`.
* **Zero Schema Alterations**: No table definitions, indexes, constraints, or columns were modified or deleted.

---

## 15. Frontend State Management, Query Caching & Hydration

### TanStack Query v5 Patterns
* User directory is cached under `["control-users-directory", queryParams]`.
* Student profile is cached under `["control-user-learning-summary", userId]`.
* Mutating account status or roles invalidates both queries, guaranteeing instant UI synchronization across tabs and portals.
* 4-state lifecycle (loading skeleton, error alert, empty state, and success view) is strictly implemented in every page.

---

## 16. Automated Backend Unit Test Verification

### Test Suite Execution
File: `backend/tests/unit/test_sa02_user_management.py` and full suite `pytest backend/tests/unit`.

```bash
pytest backend/tests/unit
```

### Empirical Result
```text
============================== test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/priyansh/lms/backend
configfile: pyproject.toml
plugins: anyio-4.14.0, asyncio-1.4.0
collected 656 items

backend/tests/unit/test_sa02_user_management.py ......                   [100%]
...
====================== 656 passed, 122 warnings in 32.23s ======================
```
* **656 / 656 Tests Passed (100% Success Rate)**
* All 6 new SA-02 security and feature tests verified.
* All 650 pre-existing regression tests verified passing.

---

## 17. Automated Frontend Unit Test Verification

### Test Suite Execution
File: `src/tests/unit/sa02UserManagement.test.tsx` and full suite `npx vitest run`.

```bash
npx vitest run
```

### Empirical Result
```text
Test Files  31 passed (31)
     Tests  136 passed (136)
  Start at  17:17:55
  Duration  2.60s
```
* **136 / 136 Tests Passed across all 31 test files (100% Success Rate)**
* All 7 new SA-02 frontend integration tests verified passing.

---

## 18. Next.js 15 Production Build Verification

### Build Execution
```bash
npm run build
```

### Empirical Result
```text
   ▲ Next.js 15.5.29
   - Environments: .env

   Creating an optimized production build ...
 ✓ Compiled successfully in 2.5s
   Linting and checking validity of types     ✓ Linting and checking validity of types 
   Collecting page data     ✓ Collecting page data 
 ✓ Generating static pages (33/33)
   Collecting build traces     ✓ Collecting build traces 
   Finalizing page optimization     ✓ Finalizing page optimization 

Route (app)                                 Size  First Load JS
├ ƒ /control                             13.1 kB         135 kB
├ ƒ /control/admins                      5.21 kB         148 kB
├ ƒ /control/audit                        7.2 kB         125 kB
├ ƒ /control/permissions                 2.17 kB         105 kB
├ ƒ /control/staff                       4.62 kB         147 kB
├ ƒ /control/users                       6.12 kB         149 kB
├ ƒ /control/users/[id]                  7.11 kB         150 kB
+ 26 other application routes
```
* **33 / 33 Routes Compiled Cleanly**
* 0 TypeScript errors.
* 0 ESLint errors.
* Complete static generation and dynamic optimization verified.

---

## 19. Stop Condition & Non-Implementation of Future Phases

### Strict Governance Boundary
In compliance with project directives and instructions:
* **Task SA-02 is 100% complete and empirically verified.**
* **Task SA-03 (Security & Sessions) has NOT been implemented.**
* **Task SA-04 (Content Governance) has NOT been implemented.**
* **Task SA-05 (Commercial Governance) has NOT been implemented.**
* **All 17 reserved governance files remain completely untouched.**
* Engineering work is halted at the authorized boundary.
