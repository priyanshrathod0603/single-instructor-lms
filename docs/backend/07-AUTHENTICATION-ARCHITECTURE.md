# Authentication Architecture & Security Specification

## 1. Authentication Pillars & Cryptographic Standards

The Single-Instructor LMS platform enforces zero-trust identity authentication, robust password hashing, mandatory email verification, and seamless Google OIDC federated login.

---

## 2. Password Hashing Specification (Argon2id)

Passwords are never stored in plaintext. They are hashed using **Argon2id**, the winner of the Password Hashing Competition (PHC) and recommended by OWASP for password storage.

### 2.1 Cryptographic Parameters
* **Algorithm**: `argon2id` (hybrid of Argon2i and Argon2d providing side-channel and GPU-cracking defense)
* **Memory Cost ($m$)**: `65536` KiB (64 MiB RAM per hash)
* **Time Cost ($t$)**: `3` iterations
* **Parallelism Factor ($p$)**: `4` threads
* **Hash Output Length**: 32 bytes
* **Salt**: 16 bytes generated via `os.urandom()` (managed by `pwdlib` / `passlib`)

### 2.2 Password Complexity Policy
* Minimum Length: 12 characters
* Maximum Length: 128 characters (guards against DoS via oversized hashing inputs)
* Complexity Rules: At least one uppercase letter `[A-Z]`, one lowercase letter `[a-z]`, one digit `[0-9]`, and one special symbol `[!@#$%^&*(),.?":{}|<>]`.
* Common Password Rejection: Checked against standard breached password dictionaries.

---

## 3. Google OAuth 2.0 / OIDC Token Verification Flow

Federated authentication uses Google OpenID Connect (OIDC). Rather than fragile client-side redirects handling authorization codes, the backend accepts verified Google `id_token` credentials.

### 3.1 Verification Sequence

```mermaid
sequenceDiagram
    autonumber
    actor User as Student
    participant Browser as Client Browser (React)
    participant Google as Google Identity Services
    participant API as Backend (FastAPI /auth/oauth/google)
    participant DB as PostgreSQL

    User->>Browser: Click "Sign in with Google"
    Browser->>Google: Prompt Google One-Tap / OAuth Consent
    Google-->>Browser: Returns credential (id_token JWT)
    Browser->>API: POST /api/v1/auth/oauth/google { "id_token": "..." }
    API->>Google: Fetch Google JWKS Public Keys (cached in Redis)
    API->>API: Verify Signature, Audience (GOOGLE_CLIENT_ID), and Expiry
    API->>API: Extract verified email, full_name, avatar_url
    API->>DB: SELECT * FROM users WHERE email = :email
    alt User Does Not Exist
        API->>DB: INSERT INTO users (email, full_name, is_verified=TRUE, is_active=TRUE)
        API->>DB: INSERT INTO user_roles (user_id, role_id='STUDENT')
    else User Exists
        API->>DB: UPDATE users SET is_verified=TRUE WHERE id = :user_id
    end
    API->>API: Enforce Atomic Session Displacement
    API->>DB: UPDATE auth_sessions SET status='REVOKED' WHERE user_id=:user_id AND status='ACTIVE'
    API->>DB: INSERT INTO auth_sessions (user_id, session_token_hash, status='ACTIVE', expires_at)
    API-->>Browser: Set-Cookie: __Host-lms_session=...; HttpOnly; Secure; SameSite=Lax
    Browser-->>User: Navigate to Student Dashboard
```

1. **JWKS Key Caching**: Google's public JSON Web Key Set (`https://www.googleapis.com/oauth2/v3/certs`) is cached in memory/Redis with TTL matching `Cache-Control` headers (typically 6 hours).
2. **Audience Verification**: Backend verifies that `aud` matches `GOOGLE_CLIENT_ID` exactly.
3. **Issuer Verification**: Backend verifies that `iss` is `https://accounts.google.com` or `accounts.google.com`.
4. **Email Verified Claim**: Backend rejects tokens where `email_verified != true`.

---

## 4. Mandatory Email Verification Workflow

All student accounts registered via password must verify their email before accessing enrolled course lessons.

### 4.1 Token Lifecycle
* **Generation**: 32-byte cryptographic random string via `secrets.token_urlsafe(32)`.
* **Storage**: Stored in `auth_tokens` as a SHA-256 hash (`token_hash = sha256(raw_token)`).
* **Expiration (TTL)**: 24 hours from creation.
* **Single-Use**: Flag `is_used` set to `TRUE` immediately upon consumption within a serializable database transaction.
* **Guardrail**: If an unverified user attempts to access `/api/v1/lessons/{id}` or `/api/v1/orders`, the API rejects the request with HTTP `403 Forbidden` (`code: EMAIL_NOT_VERIFIED`).

---

## 5. Password Reset Flow

1. **Request (`POST /api/v1/auth/password-reset/request`)**:
   - Accepts `email`. Always returns HTTP `200 OK` regardless of whether the email exists (prevents account enumeration).
   - If account exists and is active: generates single-use token (1-hour TTL), hashes token, inserts into `auth_tokens`, and inserts email payload into `notification_outbox`.
2. **Confirmation (`POST /api/v1/auth/password-reset/confirm`)**:
   - Accepts `token` and `new_password`.
   - Hashes incoming token with SHA-256 and searches `auth_tokens` for `token_type='PASSWORD_RESET'`, `is_used=FALSE`, `expires_at > NOW()`.
   - If valid:
     - Updates `users.password_hash` with Argon2id hash of `new_password`.
     - Marks token `is_used = TRUE`.
     - **Security Invariant**: Atomically revokes **ALL** active sessions for the user (`UPDATE auth_sessions SET status='REVOKED' WHERE user_id=:user_id`).
     - Logs event in `audit_logs` (`action: PASSWORD_RESET_COMPLETED`).

---

## 6. Brute Force Protection & Credential Stuffing Defense

1. **Rate Limiting (Redis-backed)**:
   - Login attempts: Max 5 failed attempts per IP address per 15-minute sliding window.
   - Account-level lock: 5 consecutive failed attempts on a single email locks password login for 15 minutes while allowing OAuth or password reset.
2. **Constant-Time Comparison**:
   - Verification of tokens and password checks uses constant-time string comparison (`hmac.compare_digest`) to prevent timing side-channel analysis.
