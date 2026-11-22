# 01 — System Architecture & Multi-Tier Topology

## 1. Multi-Tier Layered Architecture

The Single-Instructor LMS backend is designed following a **Clean Layered Architecture** pattern with strict boundary separation between HTTP transport, domain business logic, data persistence, and external third-party integrations.

```mermaid
flowchart TB
    subgraph ClientTier ["1. Client Presentation Tier"]
        PublicWeb["Public Catalog & Storefront (Next.js SSR)"]
        StudentPortal["Student Learning Player (Next.js CSR)"]
        StaffPortal["Staff Grading & Review Queue"]
        AdminPortal["Course Builder & Operations"]
        SuperAdminPortal["Platform Governance & Audit"]
    end

    subgraph IngressTier ["2. Ingress & Edge Gateway Tier"]
        ReverseProxy["Edge Reverse Proxy / CDN (TLS Termination, Rate Limiting)"]
        APIGateway["REST API Base: /api/v1 (FastAPI Application)"]
    end

    subgraph MiddlewareTier ["3. Security & Context Middleware Tier"]
        ReqContext["Request ID & Latency Telemetry Middleware"]
        CORSMiddleware["CORS Allowlist Middleware"]
        AuthFilter["Session Validator & Single-Active-Session Verifier"]
        RBACFilter["Permission Key & Record Scope Evaluator"]
    end

    subgraph ServiceTier ["4. Core Domain Service Tier"]
        AuthService["Identity & Authentication Service"]
        SessionService["Atomic Session Management Service"]
        RBACService["Access Control & Governance Service"]
        CourseService["Course Revision & Curriculum Service"]
        MediaService["Protected Asset & Transcode Service"]
        PaymentService["Commerce & Webhook Reconciliation Service"]
        AssignmentService["Assignment & Rubric Grading Service"]
        QuizService["Server-Authoritative Quiz Engine"]
        ProgressService["Learning Progress & Completion Service"]
        AuditService["Append-Only Audit Service"]
    end

    subgraph DataTier ["5. Persistence & Storage Tier"]
        Postgres[(PostgreSQL 15+ Relational DB\nTables, Partial Unique Indexes, Triggers)]
        PrivateStorage[(Private Cloud Object Store\nRaw Video, Transcoded HLS, Protected PDFs)]
        RedisCache[(Redis Cache & Distributed Mutex Store)]
    end

    subgraph AsyncTier ["6. Asynchronous Worker & Outbox Tier"]
        WorkerQueue["Background Task Worker (Celery / Background Processors)"]
        OutboxProcessor["Transactional Outbox Mailer & Push Notifications"]
        TranscodeCoordinator["Video Transcode Poller & Completion Handler"]
    end

    ClientTier --> ReverseProxy --> APIGateway
    APIGateway --> ReqContext --> CORSMiddleware --> AuthFilter --> RBACFilter --> ServiceTier
    ServiceTier --> Postgres
    ServiceTier --> RedisCache
    ServiceTier --> WorkerQueue
    MediaService <--> PrivateStorage
    WorkerQueue --> OutboxProcessor
    WorkerQueue --> TranscodeCoordinator
```

---

## 2. Layer Responsibilities & Isolation Boundaries

### Layer 1: Ingress & Edge Gateway
* **TLS Termination & Security Headers**: Enforces HTTPS, `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, and `X-Frame-Options: DENY`.
* **Rate Limiting**: Throttles unauthenticated endpoints (`POST /auth/login`, `POST /auth/signup`, `POST /checkout/orders`) to mitigate brute force attacks and credential stuffing.
* **Routing**: Maps external requests to `/api/v1/` prefix.

### Layer 2: Security & Context Middleware
* **Request Correlation**: Attaches a unique, trace-friendly `X-Request-ID` to request state and response headers.
* **Session & Token Verification**: Extracts `__Host-lms_session` cookie, hashes token via SHA-256, validates active state in `auth_sessions`, and checks `auth_version`.
* **RBAC & Scope Enforcement**: Evaluates required permission keys against user's granted roles and resource ownership (`own`, `assigned`, `all`).

### Layer 3: Domain Service Layer (Pure Business Logic)
* Encapsulates all domain invariants: course revision immutability, rubric score totals, server quiz countdown timers, and atomic single-active-session revocation.
* **Stateless Operation**: Services maintain no in-memory state, ensuring horizontal scalability.

### Layer 4: Data Persistence Layer (PostgreSQL)
* PostgreSQL 15+ operates as the single source of relational truth.
* Strict referential constraints (`ON DELETE RESTRICT`) guard financial, submission, and audit history.
* Partial unique indexes enforce critical single-active-session invariants.

### Layer 5: Asynchronous Worker & Outbox Tier
* **Transactional Outbox Pattern**: Decouples external network calls (sending emails, webhook retries) from database transactions. Side effects are saved to `notifications` in the same transaction as business events and flushed asynchronously.

---

## 3. Data Flow Architecture

### Flow A: Payment Webhook to Course Enrollment (Zero Trust Redirect)
```mermaid
sequenceDiagram
    autonumber
    participant Gateway as Payment Gateway (Razorpay)
    participant Edge as Edge Proxy / Ingress
    participant WebhookAPI as /api/v1/webhooks/razorpay
    participant DB as PostgreSQL Database
    participant Outbox as Background Outbox Worker

    Gateway->>Edge: POST Webhook Payload + HMAC Signature
    Edge->>WebhookAPI: Forward Raw Request
    WebhookAPI->>WebhookAPI: Verify HMAC-SHA256 Signature with Webhook Secret
    alt Invalid Signature
        WebhookAPI-->>Gateway: 400 Bad Request (Halt)
    else Valid Signature
        WebhookAPI->>DB: Check provider_event_id in payment_webhook_events
        alt Duplicate Delivery (Idempotent)
            WebhookAPI-->>Gateway: 200 OK (Acknowledge Duplicate)
        else Fresh Event
            Note over WebhookAPI,DB: Single Atomic Transaction Boundary
            WebhookAPI->>DB: BEGIN TRANSACTION
            WebhookAPI->>DB: Lock Order & Payment Rows (SELECT FOR UPDATE)
            WebhookAPI->>DB: UPDATE payments SET status = 'CAPTURED'
            WebhookAPI->>DB: UPDATE orders SET status = 'PAID'
            WebhookAPI->>DB: INSERT INTO enrollments (user_id, course_id, status='ACTIVE')
            WebhookAPI->>DB: INSERT INTO audit_logs (Payment Success & Enrollment)
            WebhookAPI->>DB: INSERT INTO notifications (Receipt & Welcome Email)
            WebhookAPI->>DB: COMMIT TRANSACTION
            WebhookAPI-->>Gateway: 200 OK
            Outbox->>DB: Poll Unsent Notifications
            Outbox->>Outbox: Deliver Transactional Email
        end
    end
```

### Flow B: Concurrent Login & Atomic Session Revocation
```mermaid
sequenceDiagram
    autonumber
    participant DeviceB as New Device B
    participant DeviceA as Prior Device A
    participant AuthAPI as /api/v1/auth/login
    participant DB as PostgreSQL Database

    DeviceB->>AuthAPI: POST Credentials + Display Name
    AuthAPI->>DB: SELECT id, password_hash FROM users WHERE email = :email
    AuthAPI->>AuthAPI: Verify Password Hash (Argon2id)
    Note over AuthAPI,DB: Atomic Session Transaction
    AuthAPI->>DB: BEGIN TRANSACTION
    AuthAPI->>DB: SELECT id FROM users WHERE id = :uid FOR UPDATE
    AuthAPI->>DB: UPDATE auth_sessions SET status='REVOKED', revoked_at=NOW(), revoke_reason='NEW_LOGIN' WHERE user_id=:uid AND status='ACTIVE'
    AuthAPI->>DB: INSERT INTO auth_sessions (token_hash, status='ACTIVE', ...)
    AuthAPI->>DB: UPDATE users SET auth_version = auth_version + 1 WHERE id = :uid
    AuthAPI->>DB: COMMIT TRANSACTION
    AuthAPI-->>DeviceB: 200 OK + Set-Cookie: __Host-lms_session (Active)

    Note over DeviceA,AuthAPI: Subsequent Protected Request from Prior Device
    DeviceA->>AuthAPI: GET /api/v1/student/dashboard (with Old Cookie)
    AuthAPI->>DB: SELECT status, auth_version FROM auth_sessions WHERE token_hash = :old_hash
    DB-->>AuthAPI: Row Found (status='REVOKED', reason='NEW_LOGIN')
    AuthAPI-->>DeviceA: 401 Unauthorized (error: SESSION_REVOKED)
    DeviceA->>DeviceA: Clear Cookie & Display "You signed in on another device"
```

---

## 4. Scalability, Resilience & Disaster Recovery

1. **Stateless API Replicas**: The application container carries zero persistent file state, allowing seamless scaling behind a round-robin load balancer.
2. **Database Connection Pooling**: SQLAlchemy connection pools maintain bounded concurrency (`pool_size=10`, `max_overflow=20`), preventing PostgreSQL socket starvation.
3. **Graceful Degradation**: If external payment webhooks or email providers experience downtime, incoming events queue safely, retrying with exponential backoff and dead-letter queueing.
