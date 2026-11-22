# Audit Log & Security Trail Architecture Specification

## 1. Immutable Append-Only Invariant

To guarantee non-repudiation and forensic auditability for financial transactions, course state changes, and administrative actions, the `audit_logs` table is strictly **append-only**.

### 1.1 Database-Level Enforcement
No application user or role (except PostgreSQL superusers during migration maintenance) possesses permissions to alter or remove historical audit records:

```sql
-- Revoke mutating operations from the application role
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM lms_app;

-- Enforce immutability via database trigger
CREATE OR REPLACE FUNCTION enforce_audit_log_immutability()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Security Policy Violation: audit_logs records are strictly immutable. UPDATE and DELETE are prohibited.'
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_logs_prevent_mutation
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION enforce_audit_log_immutability();
```

---

## 2. Audited Entity Actions Catalog

The audit logger captures high-fidelity state transitions across 6 core domains:

| Domain | Action Key | Entity Type | Description |
| :--- | :--- | :--- | :--- |
| **Auth** | `AUTH_LOGIN_SUCCESS` | `user` | Successful password or OAuth authentication |
| | `AUTH_SESSION_DISPLACED` | `auth_session` | Prior active session displaced by new login |
| | `AUTH_PASSWORD_RESET` | `user` | Password changed via reset token |
| | `AUTH_EMAIL_VERIFIED` | `user` | Email address verified |
| **Courses** | `COURSE_CREATED` | `course` | New course record created |
| | `COURSE_REVISION_SPAWNED`| `course_revision`| New working draft revision cloned from live |
| | `COURSE_PUBLISHED` | `course_revision`| Revision frozen into snapshot and set live |
| | `COURSE_ARCHIVED` | `course` | Course removed from public catalog |
| **Commerce**| `PAYMENT_WEBHOOK_RECEIVED`| `payment_transaction`| Razorpay HMAC-verified payment captured |
| | `REFUND_PROCESSED` | `refund` | Super Admin authorizes payment refund |
| **Enroll** | `ENROLLMENT_GRANTED` | `enrollment` | Access granted via payment or admin grant |
| | `ENROLLMENT_REVOKED` | `enrollment` | Access terminated via refund or admin action |
| **Grading** | `GRADE_RECORDED` | `assignment_submission`| Rubric criteria scores submitted by staff |
| | `GRADE_OVERRIDDEN` | `grade_override` | Super Admin manually adjusts finalized score |
| **Admin** | `USER_SUSPENDED` | `user` | Account locked and active sessions revoked |
| | `ROLE_ASSIGNED` | `user_role` | New role assigned to user identity |

---

## 3. Audit Log Entry Structure & Masking

```json
{
  "id": "7f8a9b2c-3d4e-5f6a-7b8c-9d0e1f2a3b4c",
  "actor_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "action": "GRADE_OVERRIDDEN",
  "entity_type": "assignment_submission",
  "entity_id": "sub_98421034",
  "before_state": {
    "final_score": 65.0,
    "status": "GRADED"
  },
  "after_state": {
    "final_score": 85.0,
    "override_reason": "Curriculum errata in Question 3 granted credit to all submissions.",
    "status": "GRADED"
  },
  "ip_address": "198.51.100.42",
  "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...",
  "created_at": "2026-11-13T21:40:00.000Z"
}
```

### 3.1 Sensitive Data Masking Policy
To comply with security and privacy regulations:
* **Passwords**: Never logged under any circumstance.
* **Secrets / Webhook Signatures**: Masked to first 6 and last 4 characters (`sha256:a1b2...9f8e`).
* **Payment Credentials**: Credit card numbers and bank details are handled entirely by Razorpay; the backend never sees or logs raw financial credentials.
