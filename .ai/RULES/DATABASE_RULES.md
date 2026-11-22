# Database Engineering & Schema Integrity Rules (DATABASE_RULES)

## 1. Database Engine & Relational Baseline

This document governs all database schemas, table definitions, column types, relationships, constraints, indexes, migrations, and transactional boundaries for the Single-Instructor LMS.

The authoritative database engine is **PostgreSQL 15+** [Source: LMS Blueprint v2.0, Pages 8–11]. All database activities must strictly adhere to the universal directives in [.ai/RULES/GLOBAL_RULES.md](file:///Users/priyansh/lms/.ai/RULES/GLOBAL_RULES.md).

---

## 2. Absolute Prohibitions (Zero Destructive Operations)

The AI agent is **STRICTLY PROHIBITED** from independently executing any of the following actions without explicit written owner authorization:
* **NEVER** execute `DROP TABLE` or `DROP SCHEMA`.
* **NEVER** drop or delete existing columns.
* **NEVER** rename existing columns or tables in-place (causes downtime and breaking changes).
* **NEVER** remove or weaken existing foreign key, unique, or check constraints.
* **NEVER** alter column data types in a narrowing or lossy manner.
* **NEVER** execute hard `DELETE` queries on core business entities (users, courses, orders, grades, submissions, audit logs).
* **NEVER** flush, reset, or drop the development, staging, or production database.

---

## 3. PostgreSQL Type & Column Conventions [Source: LMS Blueprint v2.0, Page 8]

Every table defined in the project must comply with these architectural standards:

| Entity Attribute | Mandatory PostgreSQL Type | Semantic Purpose & Usage Rules |
| :--- | :--- | :--- |
| **Primary Keys** | `UUID` (`gen_random_uuid()`) | High collision resistance; eliminates sequential enumeration attacks across all endpoints. |
| **Timestamps** | `TIMESTAMPTZ` | All timestamps must be stored in UTC. Include `created_at` and `updated_at` where mutable. |
| **Email Addresses**| `CITEXT` | Case-insensitive text with `UNIQUE` constraint to eliminate duplicate email bypasses. |
| **Monetary Values**| `BIGINT` | Stored in minor currency units (e.g., paise for INR). Floating-point currency types are prohibited. |
| **Document State** | `JSONB` | Reserved for flexible configuration, snapshot archives, or rubric criterion definitions. |
| **Foreign Keys** | `UUID` | Must declare explicit referential integrity actions (`RESTRICT` vs `CASCADE`). |

---

## 4. Referential Integrity & Foreign Key Policies

* **Financial & Audit Immutability (`RESTRICT`)**:
  * Foreign keys referencing `orders`, `payments`, `refunds`, and `audit_logs` **MUST** use `ON DELETE RESTRICT`. Under no circumstances may financial or audit history be orphaned or cascade-deleted.
* **Business Record Soft-Deletion**:
  * Core entities (courses, sections, lessons, assignments, quizzes, questions) must use status enums (`draft`, `published`, `archived`) rather than physical deletion.
  * If a question is referenced by historical quiz attempts, it must be archived, never deleted [Source: LMS Blueprint v2.0, Page 7].

---

## 5. Critical Constraints & Partial Unique Indexes

1. **Single-Active-Session Partial Unique Index** [Source: LMS Blueprint v2.0, Page 8]:
   ```sql
   CREATE UNIQUE INDEX idx_auth_sessions_unique_active_user 
       ON auth_sessions (user_id) 
    WHERE status = 'ACTIVE';
   ```
   *Guarantees at the database level that no user account can ever possess more than one active session simultaneously.*

2. **Course Revision Uniqueness** [Source: LMS Blueprint v2.0, Page 9]:
   ```sql
   ALTER TABLE course_revisions 
   ADD CONSTRAINT uq_course_revision_no UNIQUE (course_id, revision_no);
   ```

3. **Curriculum Position Uniqueness** [Source: LMS Blueprint v2.0, Page 9]:
   ```sql
   ALTER TABLE course_sections 
   ADD CONSTRAINT uq_section_revision_position UNIQUE (revision_id, position);

   ALTER TABLE lessons 
   ADD CONSTRAINT uq_lesson_section_position UNIQUE (section_id, position);
   ```

4. **One Entitlement per Course** [Source: LMS Blueprint v2.0, Page 9]:
   ```sql
   CREATE UNIQUE INDEX idx_enrollments_user_course_unique 
       ON enrollments (user_id, course_id);
   ```

5. **Append-Only Audit Log Protection** [Source: LMS Blueprint v2.0, Page 11]:
   * The `audit_logs` table must be append-only. Revoke `UPDATE` and `DELETE` grants at the database role level:
   ```sql
   REVOKE UPDATE, DELETE ON audit_logs FROM public, app_user;
   ```

---

## 6. Migration Safety & Multi-Phase Rollout

* **Reversible Migrations**: Every migration script must include a fully tested, non-destructive rollback (`down`) procedure.
* **Expand-and-Contract Pattern for Schema Evolution**:
  * When renaming or refactoring a column:
    1. **Phase 1 (Expand)**: Add the new column as nullable; duplicate writes in application layer.
    2. **Phase 2 (Backfill)**: Backfill historical data in background batches.
    3. **Phase 3 (Contract)**: Switch application reads to the new column; mark old column deprecated.
    4. **Phase 4 (Cleanup)**: Drop old column only after verified zero dependencies and explicit owner sign-off.
* **Lock Timeout Enforcement**: All DDL migration scripts must set a short lock timeout (e.g., `SET lock_timeout = '3s';`) to prevent connection pool exhaustion during table locks.

---

## 7. Query Optimization & Transaction Boundaries

* **No N+1 Queries**:
  * All relational fetches across parent/child models (e.g., courses with sections and lessons) must use explicit joins, `select_related`, or `prefetch_related`.
* **Row-Level Locking (`FOR UPDATE`)**:
  * Must be explicitly applied inside transactions for:
    * Login authentication session transitions.
    * Webhook order payment reconciliation.
    * Quiz attempt initiation and quota checks.
    * Assignment attempt counters.
* **Explicit Transaction Boundaries**: Never mix external network HTTP calls (e.g., Razorpay API, S3 uploads) inside active database transactions. Execute network calls outside the transaction or via outbox workers.
