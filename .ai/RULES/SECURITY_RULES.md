# Security Engineering, Cryptography & Access Control Rules (SECURITY_RULES)

## 1. Security Baseline & Philosophy

This document defines the mandatory security policies, cryptographic standards, vulnerability mitigations, and access control invariants for the Single-Instructor LMS.

**The Golden Security Principle**: Under **NO** circumstances may an AI agent remove a security check, relax an authentication guard, disable input sanitization, or weaken an authorization boundary to make a feature work, make tests pass, or resolve an error.

All code must strictly adhere to the universal directives in [.ai/RULES/GLOBAL_RULES.md](file:///Users/priyansh/lms/.ai/RULES/GLOBAL_RULES.md).

---

## 2. Authentication & Session Security Invariants

### 1. Atomic Single-Active-Session Rule [Source: LMS Blueprint v2.0, Pages 2, 8]
* At most **one** active session per user account across all devices.
* A newly authenticated login atomically transitions prior sessions to `status='REVOKED'`, `revoked_at=NOW()`, `revoke_reason='NEW_LOGIN'`.
* The displaced session receives `401 SESSION_REVOKED` and displays: *"You signed in on another device"*.
* Partial unique index `auth_sessions(user_id) WHERE status='ACTIVE'` must remain enforced.

### 2. Cookie Security Attributes
* Session cookies must declare:
  ```http
  Set-Cookie: __Host-lms_session=<hash>; Secure; HttpOnly; SameSite=Lax; Path=/
  ```
* **NEVER** store long-lived JWTs or authentication bearer tokens in browser `localStorage` or `sessionStorage` [Source: LMS Blueprint v2.0, Page 8].

### 3. Password & Secret Storage
* Passwords must be hashed using Argon2id or bcrypt with strong work factors. Raw passwords must **never** be logged, cached, or emailed.
* Account recovery tokens and one-time invitation links must be stored solely as SHA-256 hashes in the database.

### 4. Multi-Factor Authentication (MFA)
* TOTP-based MFA is required for all privileged roles (Staff, Admin, Super Admin) [Source: LMS Blueprint v2.0, Page 7].
* Pending MFA verification challenges must **not** invalidate an existing active session until the second factor is verified [Source: LMS Blueprint v2.0, Page 8].

---

## 3. Authorization, RBAC & Scope Evaluation

### Multi-Stage Authorization Pipeline [Source: LMS Blueprint v2.0, Page 3]
Every protected endpoint must execute the following sequential evaluation:
$$\text{Authenticate} \longrightarrow \text{Active Account Check} \longrightarrow \text{Validate Session \& auth\_version} \longrightarrow \text{Check Action Permission Key} \longrightarrow \text{Check Record Scope} \longrightarrow \text{Check Business Rules} \longrightarrow \text{Append Audit}$$

### Explicit Denials & Governance Guardrails:
* **Deny-Overrides-Allow**: Any explicit `DENY` override assigned to a user supersedes all role grants [Source: LMS Blueprint v2.0, Page 3].
* **No Self-Assignment of Privileged Roles**: Public registration strictly creates `Student` role. Any client payload attempting to pass a role parameter must be rejected or stripped [Source: LMS Blueprint v2.0, Page 2].
* **Last Super Admin Lockout Prevention**: Database check constraints or service logic must prohibit deleting, demoting, or suspending the final active Super Admin account [Source: LMS Blueprint v2.0, Pages 2, 7].

---

## 4. Web Application Vulnerability Mitigations

### 1. Cross-Site Scripting (XSS)
* Rich text fields (course descriptions, assignment instructions, notes) must be sanitized server-side using an allowlist parser (e.g., Bleach or DOMPurify) before persisting to the database.
* React/Next.js default escaping must be preserved; never bypass escaping with `dangerouslySetInnerHTML` unless explicitly sanitized.

### 2. Cross-Site Request Forgery (CSRF)
* All state-changing requests (`POST`, `PUT`, `PATCH`, `DELETE`) authenticated via cookies must require a cryptographically valid `X-CSRF-Token` header.

### 3. Insecure Direct Object References (IDOR)
* Verifying that a record exists is insufficient. The service layer **MUST** verify that `record.user_id == authenticated_user.id` or that the requesting user possesses an explicitly granted staff/admin scope [Source: LMS Blueprint v2.0, Pages 2–3].
* Changing UUID parameters in the URL must never yield another student's submission, grade, or order details.

### 4. SQL Injection
* All database interactions must use parameterized queries or trusted ORM expression builders. Raw string interpolation in SQL is strictly forbidden.

---

## 5. Media & Asset Protection Pipeline

### 1. Private Cloud Storage
* Cloud storage buckets (S3, GCS, R2) must have public read access completely disabled. All bucket objects must be private.

### 2. File Upload Validation & Malware Defense [Source: LMS Blueprint v2.0, Pages 5, 14]
* Upload flow must use presigned upload intents.
* Server must validate:
  1. Magic byte file signatures (never trust client MIME headers alone).
  2. Maximum size caps and file extension allowlists.
  3. Antivirus/malware scanning prior to releasing files to graders. Unscanned or infected files cannot be released [Source: LMS Blueprint v2.0, Page 10].

### 3. Signed Video & Protected PDF Delivery [Source: LMS Blueprint v2.0, Page 5]
* Video playback requires active enrollment entitlement and session validity. Playback URLs or tokens must have short TTLs (e.g., 60 seconds).
* PDFs must be streamed via protected viewers with download controls disabled by default (`is_downloadable: false`).

---

## 6. Commerce & Webhook Security

1. **Cryptographic HMAC Signature Verification**:
   * Every incoming Razorpay webhook must verify the `X-Razorpay-Signature` against the configured raw body and webhook secret.
2. **Zero Trust on Browser Redirect**:
   * Course access must **NEVER** be granted upon frontend client redirection. Access is granted strictly upon verified webhook execution [Source: LMS Blueprint v2.0, Page 14].
3. **Secret Redaction**:
   * Secret keys, card data, and webhook secrets must be redacted from application logs. Use masked values in UI (`****-****-****-1234`).

---

## 7. Append-Only Audit Logging & Non-Repudiation

* All sensitive actions (role grants, course publishing, price updates, grade overrides, refunds, session revocations, password resets) must write to `audit_logs` [Source: LMS Blueprint v2.0, Pages 3, 11].
* The `audit_logs` table must be append-only. No application role may possess `UPDATE` or `DELETE` grants on this table.
