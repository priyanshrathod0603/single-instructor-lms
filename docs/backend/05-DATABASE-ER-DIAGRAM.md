# Database Entity-Relationship Diagram Specification

## 1. Relational Entity-Relationship Diagram

The following Mermaid ER diagram documents the entities, attributes, and foreign key relationships across the 35 tables in the Single-Instructor LMS database.

```mermaid
erDiagram
    %% Identity & Access
    users ||--o{ user_roles : "has"
    roles ||--o{ user_roles : "assigned to"
    roles ||--o{ role_permissions : "grants"
    permissions ||--o{ role_permissions : "granted to"
    users ||--o{ auth_sessions : "owns"
    users ||--o{ auth_tokens : "receives"

    %% Courses & Curriculum
    users ||--o{ courses : "authors"
    courses ||--o{ course_revisions : "versioned as"
    courses ||--o{ course_tags : "categorized by"
    course_revisions ||--o{ curriculum_sections : "contains"
    curriculum_sections ||--o{ curriculum_lessons : "contains"
    curriculum_lessons ||--o{ lesson_resources : "attaches"

    %% Assessments & Rubrics
    curriculum_lessons ||--o| assignments : "defines"
    assignments ||--o{ assignment_submissions : "receives"
    users ||--o{ assignment_submissions : "submits"
    assignments ||--o{ rubrics : "evaluated by"
    rubrics ||--o{ rubric_criteria : "composed of"
    assignment_submissions ||--o{ rubric_scores : "evaluated with"
    rubric_criteria ||--o{ rubric_scores : "scored under"
    assignment_submissions ||--o{ grade_overrides : "adjusted by"

    %% Quizzes & Attempts
    curriculum_lessons ||--o| quizzes : "defines"
    quizzes ||--o{ quiz_questions : "contains"
    quiz_questions ||--o{ quiz_question_options : "offers"
    quizzes ||--o{ quiz_attempts : "attempted via"
    users ||--o{ quiz_attempts : "takes"
    quiz_attempts ||--o{ quiz_answers : "records"
    quiz_questions ||--o{ quiz_answers : "answers"

    %% Commerce & Enrollment
    users ||--o{ orders : "places"
    courses ||--o{ orders : "purchased via"
    orders ||--o{ payment_transactions : "reconciled with"
    orders ||--o{ refunds : "refunded via"
    users ||--o{ enrollments : "holds"
    courses ||--o{ enrollments : "enrolled in"
    orders ||--o| enrollments : "grants"

    %% Progress & Certification
    users ||--o{ lesson_progress : "tracks"
    curriculum_lessons ||--o{ lesson_progress : "tracked for"
    users ||--o{ course_progress_summaries : "summarizes"
    courses ||--o{ course_progress_summaries : "summarized for"
    users ||--o{ certificates : "earns"
    courses ||--o{ certificates : "certifies"

    %% Media, Notifications & Audit
    users ||--o{ media_assets : "uploads"
    users ||--o{ notifications : "receives"
    users ||--o{ audit_logs : "triggers"

    users {
        uuid id PK
        citext email UK
        varchar password_hash
        varchar full_name
        boolean is_verified
        boolean is_active
        timestamptz created_at
    }

    auth_sessions {
        uuid id PK
        uuid user_id FK
        varchar session_token_hash UK
        varchar status
        inet ip_address
        timestamptz expires_at
    }

    courses {
        uuid id PK
        citext slug UK
        varchar title
        varchar status
        bigint price_inr
        boolean is_free
    }

    course_revisions {
        uuid id PK
        uuid course_id FK
        int revision_no
        varchar status
        jsonb snapshot
        timestamptz published_at
    }

    curriculum_sections {
        uuid id PK
        uuid course_revision_id FK
        varchar title
        int sort_order
    }

    curriculum_lessons {
        uuid id PK
        uuid section_id FK
        varchar title
        varchar lesson_type
        int sort_order
        int duration_seconds
        boolean is_preview
    }

    orders {
        uuid id PK
        varchar order_no UK
        uuid student_id FK
        uuid course_id FK
        bigint amount_inr
        varchar status
        varchar razorpay_order_id
    }

    payment_transactions {
        uuid id PK
        uuid order_id FK
        varchar razorpay_payment_id UK
        varchar razorpay_signature
        varchar status
        bigint amount_inr
        jsonb raw_payload
    }

    enrollments {
        uuid id PK
        uuid student_id FK
        uuid course_id FK
        uuid order_id FK
        varchar status
        timestamptz granted_at
        timestamptz expires_at
    }

    lesson_progress {
        uuid id PK
        uuid student_id FK
        uuid lesson_id FK
        boolean is_completed
        int watch_position_seconds
    }

    certificates {
        uuid id PK
        varchar certificate_no UK
        uuid student_id FK
        uuid course_id FK
        varchar verification_hash UK
        timestamptz issued_at
    }

    audit_logs {
        uuid id PK
        uuid actor_id FK
        varchar action
        varchar entity_type
        varchar entity_id
        jsonb before_state
        jsonb after_state
        timestamptz created_at
    }
```

---

## 2. Relational Cardinalities and Domain Invariants

### 2.1 Identity & Session Boundary
* **`users` to `auth_sessions` (1 to Many historical, 1 to 1 Active)**:
  - While one user record can link to many historical sessions (`REVOKED` or `EXPIRED`), PostgreSQL partial unique indexing enforces that a user has at most **one** session in `status = 'ACTIVE'`.
* **`users` to `roles` (Many to Many via `user_roles`)**:
  - Allows an instructor to test the student experience using secondary assigned roles while maintaining primary administrative access.

### 2.2 Course Revision Boundary
* **`courses` to `course_revisions` (1 to Many)**:
  - A course maintains an audit trail of immutable revisions.
  - Active student enrollments reference the live published revision, while unpublished drafts exist in isolation.
* **`course_revisions` to `curriculum_sections` (1 to Many)**:
  - Sections belong to a specific revision. Modifying the curriculum structure creates a new revision draft without affecting the currently active revision.

### 2.3 Financial & Enrollment Integrity
* **`orders` to `payment_transactions` (1 to Many)**:
  - An order may encounter multiple failed transaction attempts, but exactly one successful transaction marks the order as `PAID`.
* **`orders` to `enrollments` (1 to 1 for Direct Sales)**:
  - An enrollment record is created upon verified webhook execution. An enrollment's `order_id` is foreign-keyed to the paid order. Manual instructor grants set `order_id` to `NULL` and log an administrative audit record.
* **`enrollments` Unique Constraint**:
  - A student can have at most one active enrollment record per course (`UNIQUE (student_id, course_id)`).

### 2.4 Integrity Policies (Foreign Key Deletion Rules)
1. **`ON DELETE RESTRICT` (Business-Critical Tables)**:
   - `courses`, `course_revisions`, `orders`, `enrollments`, `assignment_submissions`, `certificates`.
   - Protects educational records, student financial transactions, and certificates from being deleted if parent entities are modified.
2. **`ON DELETE CASCADE` (Tightly-Coupled Composition Tables)**:
   - `curriculum_sections` $\rightarrow$ `curriculum_lessons` $\rightarrow$ `lesson_resources`.
   - `quizzes` $\rightarrow$ `quiz_questions` $\rightarrow$ `quiz_question_options`.
   - `rubrics` $\rightarrow$ `rubric_criteria`.
   - If a draft section or quiz question is deleted prior to publication, associated child options and resources are cleaned up automatically.
3. **`ON DELETE SET NULL`**:
   - `audit_logs.actor_id`: If a user account is deleted, audit logs are preserved with `actor_id = NULL` to maintain system audit continuity.
