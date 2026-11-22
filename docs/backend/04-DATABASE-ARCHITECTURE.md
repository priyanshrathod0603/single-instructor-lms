# Database Architecture & Relational Schema Specification

## 1. Relational Database Principles & Invariants

The Single-Instructor LMS persistence layer is engineered on **PostgreSQL 17** with strict adherence to data integrity, relational constraints, and auditability.

### 1.1 Fundamental Schema Directives
1. **Primary Keys**: Every table uses a globally unique UUIDv4 (`UUID DEFAULT gen_random_uuid()`) to prevent enumeration attacks, simplify sharding/migrations, and support offline ID generation.
2. **Timestamps**: All temporal columns use `TIMESTAMPTZ` (UTC with timezone offset). Local time calculations occur strictly in presentation layers.
3. **Case-Insensitive Text (`CITEXT`)**: Email addresses, course slugs, and username identifiers use PostgreSQL `CITEXT` to guarantee uniqueness regardless of letter casing.
4. **Monetary Precision**: All monetary values are represented as minor currency units (`BIGINT` paise for INR, where `100 paise = 1.00 INR`). Floating-point types (`FLOAT`, `DOUBLE PRECISION`) are strictly forbidden.
5. **Foreign Key Integrity (`RESTRICT`)**: All business-critical relations (enrollments, payments, submissions, course revisions) use `ON DELETE RESTRICT` to prevent accidental cascading data loss. Soft archiving or status flags are used instead of physical deletes.
6. **Immutable Course Revision Snapshots**: Published course snapshots are frozen as serialized `JSONB` trees within `course_revisions.snapshot`. Any subsequent edits spawn a new revision record (`revision_no = N + 1`).
7. **Single-Active-Session Guarantee**: Concurrency is enforced via a PostgreSQL partial unique index:
   ```sql
   CREATE UNIQUE INDEX idx_auth_sessions_unique_active_user 
   ON auth_sessions(user_id) 
   WHERE status = 'ACTIVE';
   ```
8. **Append-Only Auditing**: The `audit_logs` table disallows all `UPDATE` and `DELETE` operations via database-level privilege revoking and trigger enforcement.

---

## 2. PostgreSQL Extensions & Initial Setup

```sql
-- Required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "citext";
```

---

## 3. Comprehensive Table Catalog (35 Relational Tables)

### Module 1: Identity, Authentication & Permissions

#### 1. `roles`
System-defined and instructor-defined roles.
* `id` (VARCHAR(32), PRIMARY KEY) — 'VISITOR', 'STUDENT', 'STAFF', 'ADMIN', 'SUPER_ADMIN'
* `name` (VARCHAR(64), NOT NULL)
* `description` (TEXT)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 2. `permissions`
Granular permission keys for the RBAC engine.
* `id` (VARCHAR(64), PRIMARY KEY) — e.g., 'course:create', 'course:publish', 'assignment:grade'
* `module` (VARCHAR(32), NOT NULL) — e.g., 'courses', 'grading', 'users'
* `description` (TEXT, NOT NULL)

#### 3. `role_permissions`
Join table defining default permissions per role.
* `role_id` (VARCHAR(32), REFERENCES roles(id) ON DELETE CASCADE)
* `permission_id` (VARCHAR(64), REFERENCES permissions(id) ON DELETE CASCADE)
* PRIMARY KEY (role_id, permission_id)

#### 4. `users`
Core user entity for students, staff, admins, and instructor.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `email` (CITEXT, UNIQUE, NOT NULL)
* `password_hash` (VARCHAR(255), NULL) — Argon2id hash (null for OAuth-only users)
* `full_name` (VARCHAR(128), NOT NULL)
* `avatar_url` (VARCHAR(512), NULL)
* `is_verified` (BOOLEAN, DEFAULT FALSE) — Mandatory email verification flag
* `is_active` (BOOLEAN, DEFAULT TRUE) — Account suspension control
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())
* `updated_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 5. `user_roles`
Assigned roles for users (allows multi-role assignment, e.g., Staff + Student).
* `user_id` (UUID, REFERENCES users(id) ON DELETE RESTRICT)
* `role_id` (VARCHAR(32), REFERENCES roles(id) ON DELETE RESTRICT)
* `assigned_at` (TIMESTAMPTZ, DEFAULT NOW())
* `assigned_by` (UUID, REFERENCES users(id) ON DELETE SET NULL)
* PRIMARY KEY (user_id, role_id)

#### 6. `auth_sessions`
Active and historical browser/device authentication sessions.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `user_id` (UUID, REFERENCES users(id) ON DELETE CASCADE, NOT NULL)
* `session_token_hash` (VARCHAR(64), NOT NULL, UNIQUE) — SHA-256 of the raw session token
* `status` (VARCHAR(16), NOT NULL DEFAULT 'ACTIVE') — 'ACTIVE', 'REVOKED', 'EXPIRED'
* `ip_address` (INET, NULL)
* `user_agent` (TEXT, NULL)
* `last_active_at` (TIMESTAMPTZ, DEFAULT NOW())
* `expires_at` (TIMESTAMPTZ, NOT NULL)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())
* **Constraint**: Partial Unique Index:
  ```sql
  CREATE UNIQUE INDEX idx_auth_sessions_unique_active_user 
  ON auth_sessions(user_id) 
  WHERE status = 'ACTIVE';
  ```

#### 7. `auth_tokens`
Cryptographic one-time tokens for verification, reset, and onboarding.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `user_id` (UUID, REFERENCES users(id) ON DELETE CASCADE, NOT NULL)
* `token_hash` (VARCHAR(64), NOT NULL, UNIQUE) — SHA-256 hash
* `token_type` (VARCHAR(32), NOT NULL) — 'EMAIL_VERIFICATION', 'PASSWORD_RESET', 'STAFF_ONBOARDING'
* `is_used` (BOOLEAN, DEFAULT FALSE)
* `expires_at` (TIMESTAMPTZ, NOT NULL)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())

---

### Module 2: Course Catalog & Versioned Curriculum

#### 8. `courses`
Top-level course container.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `slug` (CITEXT, UNIQUE, NOT NULL)
* `title` (VARCHAR(255), NOT NULL)
* `headline` (VARCHAR(512), NULL)
* `description` (TEXT, NULL)
* `thumbnail_url` (VARCHAR(512), NULL)
* `live_revision_id` (UUID, NULL) — Foreign key to `course_revisions(id)`
* `status` (VARCHAR(16), NOT NULL DEFAULT 'DRAFT') — 'DRAFT', 'PUBLISHED', 'ARCHIVED'
* `price_inr` (BIGINT, NOT NULL DEFAULT 0) — Minor units (paise)
* `is_free` (BOOLEAN, NOT NULL DEFAULT FALSE)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())
* `updated_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 9. `course_revisions`
Versioned, immutable snapshots of course content and metadata.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `course_id` (UUID, REFERENCES courses(id) ON DELETE RESTRICT, NOT NULL)
* `revision_no` (INT, NOT NULL)
* `status` (VARCHAR(16), NOT NULL DEFAULT 'DRAFT') — 'DRAFT', 'PUBLISHED', 'ARCHIVED'
* `title` (VARCHAR(255), NOT NULL)
* `changelog` (TEXT, NULL)
* `snapshot` (JSONB, NULL) — Complete frozen course tree at moment of publication
* `published_at` (TIMESTAMPTZ, NULL)
* `created_by` (UUID, REFERENCES users(id) ON DELETE RESTRICT)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())
* **Constraint**: `UNIQUE (course_id, revision_no)`

#### 10. `course_tags`
Search and categorization tags.
* `course_id` (UUID, REFERENCES courses(id) ON DELETE CASCADE)
* `tag` (CITEXT, NOT NULL)
* PRIMARY KEY (course_id, tag)

#### 11. `curriculum_sections`
Logical modules or chapters within a course revision.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `course_revision_id` (UUID, REFERENCES course_revisions(id) ON DELETE CASCADE, NOT NULL)
* `title` (VARCHAR(255), NOT NULL)
* `description` (TEXT, NULL)
* `sort_order` (INT, NOT NULL DEFAULT 0)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())
* `updated_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 12. `curriculum_lessons`
Individual learning items (videos, text lessons, quizzes, assignments).
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `section_id` (UUID, REFERENCES curriculum_sections(id) ON DELETE CASCADE, NOT NULL)
* `title` (VARCHAR(255), NOT NULL)
* `lesson_type` (VARCHAR(16), NOT NULL) — 'VIDEO', 'ARTICLE', 'QUIZ', 'ASSIGNMENT'
* `sort_order` (INT, NOT NULL DEFAULT 0)
* `duration_seconds` (INT, NOT NULL DEFAULT 0)
* `is_preview` (BOOLEAN, NOT NULL DEFAULT FALSE)
* `content` (JSONB, NULL) — Rich article content, video player configuration, etc.
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())
* `updated_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 13. `lesson_resources`
Downloadable assets attached to a lesson (PDFs, source code zip files).
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `lesson_id` (UUID, REFERENCES curriculum_lessons(id) ON DELETE CASCADE, NOT NULL)
* `title` (VARCHAR(255), NOT NULL)
* `resource_type` (VARCHAR(16), NOT NULL) — 'PDF', 'SOURCE_CODE', 'LINK', 'ASSET'
* `file_url` (VARCHAR(512), NOT NULL)
* `file_size_bytes` (BIGINT, NOT NULL DEFAULT 0)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())

---

### Module 3: Assignments & Rubric Evaluations

#### 14. `assignments`
Configuration for project submissions.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `lesson_id` (UUID, REFERENCES curriculum_lessons(id) ON DELETE RESTRICT, NOT NULL, UNIQUE)
* `title` (VARCHAR(255), NOT NULL)
* `instructions` (TEXT, NOT NULL)
* `max_score` (NUMERIC(5,2), NOT NULL DEFAULT 100.00)
* `pass_score` (NUMERIC(5,2), NOT NULL DEFAULT 50.00)
* `allow_late` (BOOLEAN, NOT NULL DEFAULT FALSE)
* `due_date` (TIMESTAMPTZ, NULL)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())
* `updated_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 15. `assignment_submissions`
Student submitted files and notes.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `assignment_id` (UUID, REFERENCES assignments(id) ON DELETE RESTRICT, NOT NULL)
* `student_id` (UUID, REFERENCES users(id) ON DELETE RESTRICT, NOT NULL)
* `attempt_no` (INT, NOT NULL DEFAULT 1)
* `file_url` (VARCHAR(512), NOT NULL)
* `text_notes` (TEXT, NULL)
* `status` (VARCHAR(16), NOT NULL DEFAULT 'SUBMITTED') — 'SUBMITTED', 'GRADING', 'GRADED', 'REJECTED'
* `submitted_at` (TIMESTAMPTZ, DEFAULT NOW())
* `final_score` (NUMERIC(5,2), NULL)
* `graded_at` (TIMESTAMPTZ, NULL)
* `graded_by` (UUID, REFERENCES users(id) ON DELETE SET NULL)
* **Constraint**: `UNIQUE (assignment_id, student_id, attempt_no)`

#### 16. `rubrics`
Grading criteria templates attached to assignments.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `assignment_id` (UUID, REFERENCES assignments(id) ON DELETE CASCADE, NOT NULL)
* `title` (VARCHAR(255), NOT NULL)
* `version` (INT, NOT NULL DEFAULT 1)
* `is_active` (BOOLEAN, NOT NULL DEFAULT TRUE)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 17. `rubric_criteria`
Individual evaluation dimensions within a rubric.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `rubric_id` (UUID, REFERENCES rubrics(id) ON DELETE CASCADE, NOT NULL)
* `title` (VARCHAR(255), NOT NULL)
* `description` (TEXT, NULL)
* `max_points` (NUMERIC(5,2), NOT NULL)
* `weight` (NUMERIC(5,2), NOT NULL DEFAULT 1.00)
* `sort_order` (INT, NOT NULL DEFAULT 0)

#### 18. `rubric_scores`
Per-criteria scores awarded to a submission.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `submission_id` (UUID, REFERENCES assignment_submissions(id) ON DELETE CASCADE, NOT NULL)
* `criteria_id` (UUID, REFERENCES rubric_criteria(id) ON DELETE RESTRICT, NOT NULL)
* `points_awarded` (NUMERIC(5,2), NOT NULL)
* `feedback` (TEXT, NULL)
* **Constraint**: `UNIQUE (submission_id, criteria_id)`

#### 19. `grade_overrides`
Audit trail of manual score adjustments made by instructors.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `submission_id` (UUID, REFERENCES assignment_submissions(id) ON DELETE RESTRICT, NOT NULL)
* `original_score` (NUMERIC(5,2), NOT NULL)
* `overridden_score` (NUMERIC(5,2), NOT NULL)
* `reason` (TEXT, NOT NULL)
* `overridden_by` (UUID, REFERENCES users(id) ON DELETE RESTRICT, NOT NULL)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())

---

### Module 4: Quizzes & Question Banks

#### 20. `quizzes`
Assessment configurations.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `lesson_id` (UUID, REFERENCES curriculum_lessons(id) ON DELETE RESTRICT, NOT NULL, UNIQUE)
* `title` (VARCHAR(255), NOT NULL)
* `description` (TEXT, NULL)
* `pass_percentage` (INT, NOT NULL DEFAULT 70)
* `time_limit_minutes` (INT, NOT NULL DEFAULT 30) — 0 indicates no timer
* `shuffle_questions` (BOOLEAN, NOT NULL DEFAULT TRUE)
* `max_attempts` (INT, NOT NULL DEFAULT 3) — 0 indicates unlimited
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())
* `updated_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 21. `quiz_questions`
Question definitions.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `quiz_id` (UUID, REFERENCES quizzes(id) ON DELETE CASCADE, NOT NULL)
* `question_type` (VARCHAR(16), NOT NULL) — 'MCQ_SINGLE', 'MCQ_MULTI', 'TRUE_FALSE', 'TEXT_SHORT'
* `prompt` (TEXT, NOT NULL)
* `points` (NUMERIC(5,2), NOT NULL DEFAULT 1.00)
* `explanation` (TEXT, NULL)
* `sort_order` (INT, NOT NULL DEFAULT 0)

#### 22. `quiz_question_options`
Selectable answer options for multiple-choice questions.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `question_id` (UUID, REFERENCES quiz_questions(id) ON DELETE CASCADE, NOT NULL)
* `option_text` (TEXT, NOT NULL)
* `is_correct` (BOOLEAN, NOT NULL DEFAULT FALSE)
* `sort_order` (INT, NOT NULL DEFAULT 0)

#### 23. `quiz_attempts`
Student attempt sessions.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `quiz_id` (UUID, REFERENCES quizzes(id) ON DELETE RESTRICT, NOT NULL)
* `student_id` (UUID, REFERENCES users(id) ON DELETE RESTRICT, NOT NULL)
* `attempt_no` (INT, NOT NULL DEFAULT 1)
* `started_at` (TIMESTAMPTZ, DEFAULT NOW())
* `completed_at` (TIMESTAMPTZ, NULL)
* `score` (NUMERIC(5,2), NULL)
* `is_passed` (BOOLEAN, NULL)
* `status` (VARCHAR(16), NOT NULL DEFAULT 'IN_PROGRESS') — 'IN_PROGRESS', 'SUBMITTED', 'EXPIRED'
* **Constraint**: `UNIQUE (quiz_id, student_id, attempt_no)`

#### 24. `quiz_answers`
Individual answers recorded during an attempt (with autosave support).
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `attempt_id` (UUID, REFERENCES quiz_attempts(id) ON DELETE CASCADE, NOT NULL)
* `question_id` (UUID, REFERENCES quiz_questions(id) ON DELETE RESTRICT, NOT NULL)
* `selected_option_ids` (JSONB, NULL) — Array of option UUIDs selected
* `text_response` (TEXT, NULL) — For short text questions
* `is_correct` (BOOLEAN, NULL)
* `points_earned` (NUMERIC(5,2), NULL)
* `autosaved_at` (TIMESTAMPTZ, DEFAULT NOW())
* **Constraint**: `UNIQUE (attempt_id, question_id)`

---

### Module 5: Commerce, Orders & Payment Reconciliation

#### 25. `orders`
Commercial intent records before checkout.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `order_no` (VARCHAR(32), UNIQUE, NOT NULL) — e.g., 'ORD-202611-0001'
* `student_id` (UUID, REFERENCES users(id) ON DELETE RESTRICT, NOT NULL)
* `course_id` (UUID, REFERENCES courses(id) ON DELETE RESTRICT, NOT NULL)
* `amount_inr` (BIGINT, NOT NULL) — Amount in minor units (paise)
* `currency` (VARCHAR(3), NOT NULL DEFAULT 'INR')
* `status` (VARCHAR(16), NOT NULL DEFAULT 'PENDING') — 'PENDING', 'PAID', 'FAILED', 'EXPIRED'
* `razorpay_order_id` (VARCHAR(64), UNIQUE, NULL)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())
* `updated_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 26. `payment_transactions`
Payment gateway execution logs verified via cryptographic webhook.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `order_id` (UUID, REFERENCES orders(id) ON DELETE RESTRICT, NOT NULL)
* `gateway` (VARCHAR(32), NOT NULL DEFAULT 'RAZORPAY')
* `razorpay_payment_id` (VARCHAR(64), UNIQUE, NOT NULL)
* `razorpay_signature` (VARCHAR(255), NOT NULL)
* `status` (VARCHAR(16), NOT NULL) — 'SUCCESS', 'FAILED'
* `amount_inr` (BIGINT, NOT NULL)
* `raw_payload` (JSONB, NOT NULL) — Exact signed webhook payload for auditability
* `processed_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 27. `refunds`
Authorized payment refunds.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `order_id` (UUID, REFERENCES orders(id) ON DELETE RESTRICT, NOT NULL)
* `amount_inr` (BIGINT, NOT NULL)
* `reason` (TEXT, NOT NULL)
* `status` (VARCHAR(16), NOT NULL DEFAULT 'PENDING') — 'PENDING', 'PROCESSED', 'FAILED'
* `razorpay_refund_id` (VARCHAR(64), UNIQUE, NULL)
* `approved_by` (UUID, REFERENCES users(id) ON DELETE RESTRICT, NOT NULL)
* `processed_at` (TIMESTAMPTZ, DEFAULT NOW())

---

### Module 6: Enrollments, Progress & Certificates

#### 28. `enrollments`
Course access rights granted strictly upon verified payment or admin override.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `student_id` (UUID, REFERENCES users(id) ON DELETE RESTRICT, NOT NULL)
* `course_id` (UUID, REFERENCES courses(id) ON DELETE RESTRICT, NOT NULL)
* `order_id` (UUID, REFERENCES orders(id) ON DELETE RESTRICT, NULL) — Nullable for manual admin grant
* `status` (VARCHAR(16), NOT NULL DEFAULT 'ACTIVE') — 'ACTIVE', 'REVOKED', 'EXPIRED'
* `granted_at` (TIMESTAMPTZ, DEFAULT NOW())
* `expires_at` (TIMESTAMPTZ, NULL) — Null indicates lifetime access
* `revoked_at` (TIMESTAMPTZ, NULL)
* `revoked_reason` (TEXT, NULL)
* **Constraint**: `UNIQUE (student_id, course_id)`

#### 29. `lesson_progress`
Granular playback and completion tracking per student per lesson.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `student_id` (UUID, REFERENCES users(id) ON DELETE CASCADE, NOT NULL)
* `lesson_id` (UUID, REFERENCES curriculum_lessons(id) ON DELETE CASCADE, NOT NULL)
* `is_completed` (BOOLEAN, NOT NULL DEFAULT FALSE)
* `watch_position_seconds` (INT, NOT NULL DEFAULT 0)
* `completed_at` (TIMESTAMPTZ, NULL)
* `updated_at` (TIMESTAMPTZ, DEFAULT NOW())
* **Constraint**: `UNIQUE (student_id, lesson_id)`

#### 30. `course_progress_summaries`
Materialized summary of course completion to avoid expensive aggregation queries.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `student_id` (UUID, REFERENCES users(id) ON DELETE CASCADE, NOT NULL)
* `course_id` (UUID, REFERENCES courses(id) ON DELETE CASCADE, NOT NULL)
* `completed_lessons_count` (INT, NOT NULL DEFAULT 0)
* `total_lessons_count` (INT, NOT NULL DEFAULT 0)
* `progress_percentage` (NUMERIC(5,2), NOT NULL DEFAULT 0.00)
* `last_activity_at` (TIMESTAMPTZ, DEFAULT NOW())
* **Constraint**: `UNIQUE (student_id, course_id)`

#### 31. `certificates`
Digitally verifiable proof of course completion.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `certificate_no` (VARCHAR(32), UNIQUE, NOT NULL) — e.g., 'CERT-202611-9842'
* `student_id` (UUID, REFERENCES users(id) ON DELETE RESTRICT, NOT NULL)
* `course_id` (UUID, REFERENCES courses(id) ON DELETE RESTRICT, NOT NULL)
* `issued_at` (TIMESTAMPTZ, DEFAULT NOW())
* `verification_hash` (VARCHAR(64), UNIQUE, NOT NULL) — SHA-256 hash for public QR verification
* `pdf_url` (VARCHAR(512), NOT NULL)
* **Constraint**: `UNIQUE (student_id, course_id)`

---

### Module 7: Media, Notifications & System Auditing

#### 32. `media_assets`
Catalog of uploaded video and document assets stored in Cloudflare R2 / S3.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `uploader_id` (UUID, REFERENCES users(id) ON DELETE RESTRICT, NOT NULL)
* `filename` (VARCHAR(255), NOT NULL)
* `file_key` (VARCHAR(512), UNIQUE, NOT NULL) — Object storage key
* `bucket` (VARCHAR(128), NOT NULL)
* `mime_type` (VARCHAR(128), NOT NULL)
* `file_size_bytes` (BIGINT, NOT NULL)
* `status` (VARCHAR(16), NOT NULL DEFAULT 'UPLOADING') — 'UPLOADING', 'UPLOADED', 'PROCESSING', 'READY', 'FAILED'
* `transcode_output` (JSONB, NULL) — HLS manifest URLs, available resolutions (1080p, 720p)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 33. `notifications`
In-app notification messages delivered to users.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `user_id` (UUID, REFERENCES users(id) ON DELETE CASCADE, NOT NULL)
* `title` (VARCHAR(255), NOT NULL)
* `message` (TEXT, NOT NULL)
* `notification_type` (VARCHAR(32), NOT NULL) — 'ENROLLMENT', 'GRADE_RELEASED', 'ANNOUNCEMENT'
* `is_read` (BOOLEAN, NOT NULL DEFAULT FALSE)
* `data` (JSONB, NULL) — Deep-link metadata
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 34. `notification_outbox`
Transactional Outbox table guaranteeing reliable asynchronous email delivery.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `channel` (VARCHAR(16), NOT NULL) — 'EMAIL', 'WEBHOOK'
* `recipient` (VARCHAR(255), NOT NULL)
* `subject` (VARCHAR(255), NOT NULL)
* `payload` (JSONB, NOT NULL) — Template variables and body data
* `status` (VARCHAR(16), NOT NULL DEFAULT 'PENDING') — 'PENDING', 'SENT', 'FAILED'
* `retry_count` (INT, NOT NULL DEFAULT 0)
* `next_retry_at` (TIMESTAMPTZ, DEFAULT NOW())
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())

#### 35. `audit_logs`
Immutable, append-only security log recording state transitions across all sensitive entities.
* `id` (UUID, PRIMARY KEY DEFAULT gen_random_uuid())
* `actor_id` (UUID, REFERENCES users(id) ON DELETE SET NULL, NULL) — Null indicates system/cron execution
* `action` (VARCHAR(64), NOT NULL) — e.g., 'COURSE_PUBLISH', 'PAYMENT_VERIFIED', 'SESSION_REVOKED'
* `entity_type` (VARCHAR(32), NOT NULL) — 'course', 'enrollment', 'user', 'submission'
* `entity_id` (VARCHAR(64), NOT NULL)
* `before_state` (JSONB, NULL) — State prior to modification
* `after_state` (JSONB, NULL) — State following modification
* `ip_address` (INET, NULL)
* `user_agent` (TEXT, NULL)
* `created_at` (TIMESTAMPTZ, DEFAULT NOW())

---

## 4. Key Performance Indexes

```sql
-- Fast lookup of active sessions during request authentication
CREATE INDEX idx_auth_sessions_user_status ON auth_sessions(user_id, status);

-- Rapid verification of enrolled course access
CREATE INDEX idx_enrollments_student_course ON enrollments(student_id, course_id, status);

-- Efficient curriculum sequencing queries
CREATE INDEX idx_curriculum_sections_revision_order ON curriculum_sections(course_revision_id, sort_order);
CREATE INDEX idx_curriculum_lessons_section_order ON curriculum_lessons(section_id, sort_order);

-- Quick lookup for student progress calculation
CREATE INDEX idx_lesson_progress_student ON lesson_progress(student_id, is_completed);

-- High-throughput outbox queue polling
CREATE INDEX idx_notification_outbox_pending ON notification_outbox(status, next_retry_at) 
WHERE status = 'PENDING';

-- Audit trail filtering by actor and entity
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_actor ON audit_logs(actor_id, created_at DESC);
```
