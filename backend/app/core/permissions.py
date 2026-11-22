"""Granular permission key registry and default role mappings for RBAC.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 1, Tables 2, 3)
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md (Sections 1, 2)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK201, TASK202)
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf [Pages 2-3, 14]

Strict Invariants:
1. Standardized hierarchical permission strings: domain:action.
2. Canonical 5 system roles: VISITOR, STUDENT, STAFF, ADMIN, SUPER_ADMIN.
3. Least-privilege: Visitors/Students cannot access administrative endpoints.
4. Staff scope: Grader/teaching assistant scope only; zero payment, order, refund,
   or role modification capabilities.
5. Super Admin possesses all platform permissions.
"""

from typing import Final

# Courses module permissions
COURSE_VIEW_PUBLIC: Final[str] = "course:view_public"
COURSE_VIEW_ALL: Final[str] = "course:view_all"
COURSE_CREATE: Final[str] = "course:create"
COURSE_EDIT: Final[str] = "course:edit"
COURSE_REVISION_CREATE: Final[str] = "course:revision_create"
COURSE_PUBLISH: Final[str] = "course:publish"
COURSE_ARCHIVE: Final[str] = "course:archive"

# Curriculum module permissions
CURRICULUM_MANAGE: Final[str] = "curriculum:manage"
CURRICULUM_REORDER: Final[str] = "curriculum:reorder"

# Media module permissions
MEDIA_UPLOAD: Final[str] = "media:upload"
MEDIA_VIEW_PROTECTED: Final[str] = "media:view_protected"

# Assignments module permissions
ASSIGNMENT_MANAGE: Final[str] = "assignment:manage"
ASSIGNMENT_SUBMIT: Final[str] = "assignment:submit"
ASSIGNMENT_VIEW_ALL: Final[str] = "assignment:view_all"
ASSIGNMENT_GRADE: Final[str] = "assignment:grade"
ASSIGNMENT_OVERRIDE: Final[str] = "assignment:override"

# Quizzes module permissions
QUIZ_MANAGE: Final[str] = "quiz:manage"
QUIZ_IMPORT_CSV: Final[str] = "quiz:import_csv"
QUIZ_ATTEMPT: Final[str] = "quiz:attempt"
QUIZ_VIEW_ATTEMPTS: Final[str] = "quiz:view_attempts"

# Enrollments module permissions
ENROLLMENT_VIEW_OWN: Final[str] = "enrollment:view_own"
ENROLLMENT_VIEW_ALL: Final[str] = "enrollment:view_all"
ENROLLMENT_GRANT: Final[str] = "enrollment:grant"
ENROLLMENT_REVOKE: Final[str] = "enrollment:revoke"

# Commerce & Orders module permissions
ORDERS_CREATE: Final[str] = "orders:create"
ORDERS_VIEW_OWN: Final[str] = "orders:view_own"
ORDERS_VIEW_ALL: Final[str] = "orders:view_all"
PAYMENTS_REFUND: Final[str] = "payments:refund"

# Auditing module permissions
AUDIT_VIEW: Final[str] = "audit:view"

# Session & Security Governance permissions (SA-03)
SESSIONS_VIEW_ALL: Final[str] = "sessions:view_all"
SESSIONS_REVOKE: Final[str] = "sessions:revoke"
SECURITY_METRICS_VIEW: Final[str] = "security:metrics_view"
CONTROL_REVOKE_OTHERS: Final[str] = "control:revoke_others"

# Content & Course Governance permissions (SA-04)
COURSES_GOVERN: Final[str] = "courses:govern"
BLOG_MANAGE: Final[str] = "blog:manage"
NOTES_MANAGE: Final[str] = "notes:manage"

# Commercial Governance permissions (SA-05)
OFFERS_MANAGE: Final[str] = "offers:manage"
PAYMENTS_VIEW_ALL: Final[str] = "payments:view_all"
SETTINGS_MANAGE: Final[str] = "settings:manage"

# Users & Staff module permissions
USERS_VIEW_ALL: Final[str] = "users:view_all"
USERS_VIEW: Final[str] = "users:view"
USERS_EDIT: Final[str] = "users:edit"
USERS_MANAGE_STATUS: Final[str] = "users:manage_status"
STAFF_INVITE: Final[str] = "staff:invite"
ROLES_ASSIGN: Final[str] = "roles:assign"

# Full permission metadata definitions: (key, module, description)
CANONICAL_PERMISSIONS: Final[list[tuple[str, str, str]]] = [
    # Courses
    (COURSE_VIEW_PUBLIC, "courses", "View published course catalog and public previews"),
    (COURSE_VIEW_ALL, "courses", "View all draft, published, and archived courses"),
    (COURSE_CREATE, "courses", "Create new course containers"),
    (COURSE_EDIT, "courses", "Edit course draft content, metadata, and configuration"),
    (COURSE_REVISION_CREATE, "courses", "Spawn new working draft revision from live published course"),
    (COURSE_PUBLISH, "courses", "Freeze snapshot and publish course revision as live"),
    (COURSE_ARCHIVE, "courses", "Archive course from active sales catalog"),
    # Curriculum
    (CURRICULUM_MANAGE, "curriculum", "Add, edit, and delete sections and lessons in draft revision"),
    (CURRICULUM_REORDER, "curriculum", "Update drag-and-drop sort ordering of sections and lessons"),
    # Media
    (MEDIA_UPLOAD, "media", "Request presigned upload intents for video and asset storage"),
    (MEDIA_VIEW_PROTECTED, "media", "Request signed playback tokens for protected video and PDFs"),
    # Assignments
    (ASSIGNMENT_MANAGE, "assignments", "Create and configure assignments and rubrics"),
    (ASSIGNMENT_SUBMIT, "assignments", "Submit student assignment project work"),
    (ASSIGNMENT_VIEW_ALL, "assignments", "View submissions across all students"),
    (ASSIGNMENT_GRADE, "assignments", "Grade student submissions against rubric criteria"),
    (ASSIGNMENT_OVERRIDE, "assignments", "Override finalized assignment grades with justification"),
    # Quizzes
    (QUIZ_MANAGE, "quizzes", "Create quizzes, question banks, and answer options"),
    (QUIZ_IMPORT_CSV, "quizzes", "Bulk upload quiz questions via CSV format"),
    (QUIZ_ATTEMPT, "quizzes", "Start and submit quiz attempts"),
    (QUIZ_VIEW_ATTEMPTS, "quizzes", "Inspect all student quiz attempt scores and answers"),
    # Enrollments
    (ENROLLMENT_VIEW_OWN, "enrollments", "View own active course enrollments and progress"),
    (ENROLLMENT_VIEW_ALL, "enrollments", "View all platform enrollments"),
    (ENROLLMENT_GRANT, "enrollments", "Manually grant student course enrollment"),
    (ENROLLMENT_REVOKE, "enrollments", "Revoke or expire student course access"),
    # Commerce
    (ORDERS_CREATE, "commerce", "Initiate checkout order and payment"),
    (ORDERS_VIEW_OWN, "commerce", "View own order history and payment receipts"),
    (ORDERS_VIEW_ALL, "commerce", "Inspect all commercial platform orders"),
    (PAYMENTS_REFUND, "commerce", "Authorize and execute payment refunds"),
    # Auditing
    (AUDIT_VIEW, "auditing", "Inspect append-only immutable security audit logs"),
    # Sessions & Security Governance (SA-03)
    (SESSIONS_VIEW_ALL, "sessions", "Inspect live sessions, IP addresses, and user-agent details"),
    (SESSIONS_REVOKE, "sessions", "Revoke specific or user-level sessions"),
    (SECURITY_METRICS_VIEW, "security", "Inspect technical security surveillance metrics"),
    (CONTROL_REVOKE_OTHERS, "control", "Emergency platform-wide revocation of other sessions"),
    # Users
    (USERS_VIEW_ALL, "users", "Search and inspect all user directory records"),
    (USERS_VIEW, "users", "View user profile details"),
    (USERS_EDIT, "users", "Update user profile information"),
    (USERS_MANAGE_STATUS, "users", "Suspend or restore user accounts"),
    (STAFF_INVITE, "users", "Send onboarding invitation tokens to new staff members"),
    (ROLES_ASSIGN, "users", "Assign or revoke system roles for users"),
    # Content & Course Governance (SA-04)
    (COURSES_GOVERN, "courses", "Super Admin course governance and lifecycle management"),
    (BLOG_MANAGE, "blog", "Create, edit, publish, and delete blog posts"),
    (NOTES_MANAGE, "notes", "Create, edit, upload PDFs, publish, and delete study notes"),
    # Commercial Governance (SA-05)
    (OFFERS_MANAGE, "commerce", "Create, edit, activate, deactivate, and delete commercial promotional offers"),
    (PAYMENTS_VIEW_ALL, "commerce", "View platform financial overview, payment transactions, and reconciliation metrics"),
    (SETTINGS_MANAGE, "governance", "View and update platform general and branding settings"),
]

ALL_PERMISSION_KEYS: Final[frozenset[str]] = frozenset(p[0] for p in CANONICAL_PERMISSIONS)

# Canonical Role-Permission Mappings according to 09-RBAC-PERMISSION-ARCHITECTURE.md
DEFAULT_ROLE_PERMISSIONS: Final[dict[str, frozenset[str]]] = {
    "VISITOR": frozenset({
        COURSE_VIEW_PUBLIC,
    }),
    "STUDENT": frozenset({
        COURSE_VIEW_PUBLIC,
        MEDIA_VIEW_PROTECTED,
        ASSIGNMENT_SUBMIT,
        QUIZ_ATTEMPT,
        ENROLLMENT_VIEW_OWN,
        ORDERS_CREATE,
        ORDERS_VIEW_OWN,
    }),
    "STAFF": frozenset({
        COURSE_VIEW_PUBLIC,
        MEDIA_VIEW_PROTECTED,
        ASSIGNMENT_VIEW_ALL,
        ASSIGNMENT_GRADE,
        QUIZ_VIEW_ATTEMPTS,
    }),
    "ADMIN": frozenset({
        COURSE_VIEW_PUBLIC,
        COURSE_VIEW_ALL,
        COURSE_CREATE,
        COURSE_EDIT,
        COURSE_REVISION_CREATE,
        CURRICULUM_MANAGE,
        CURRICULUM_REORDER,
        MEDIA_UPLOAD,
        MEDIA_VIEW_PROTECTED,
        ASSIGNMENT_MANAGE,
        ASSIGNMENT_VIEW_ALL,
        ASSIGNMENT_GRADE,
        QUIZ_MANAGE,
        QUIZ_IMPORT_CSV,
        QUIZ_VIEW_ATTEMPTS,
        ENROLLMENT_VIEW_ALL,
        ENROLLMENT_GRANT,
        ORDERS_VIEW_ALL,
        USERS_VIEW_ALL,
        USERS_VIEW,
        USERS_EDIT,
        STAFF_INVITE,
    }),
    "SUPER_ADMIN": ALL_PERMISSION_KEYS,
}
