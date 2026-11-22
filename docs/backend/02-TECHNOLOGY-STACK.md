# 02 — Backend Technology Stack & Evaluation Matrix

This document formalizes the complete technology stack selections for the Single-Instructor LMS backend, rigorously analyzing each decision across seven criteria: **Selected Technology**, **Reason for Selection**, **Alternatives Considered**, **Advantages**, **Disadvantages**, **Security Implications**, and **Operational Implications**.

---

## 1. Primary Language & Runtime

* **1. Selected Technology**: **Python 3.14+**
* **2. Reason for Selection**: Standardized ecosystem for backend services, mature data/AI libraries, rich pedagogical tooling, and first-class async concurrency support (`asyncio`).
* **3. Alternatives Considered**: Node.js/TypeScript (V8), Go (Golang), Rust.
* **4. Advantages**: Clean, readable syntax; vast ecosystem for scientific computing, grading algorithms, and document parsing; native type hinting support.
* **5. Disadvantages**: Slower raw CPU performance compared to Go/Rust (mitigated by async I/O and compiled extensions like CFFI/psycopg).
* **6. Security Implications**: Strong memory safety; mature security patching and vulnerability scanner ecosystem (Dependabot, Snyk).
* **7. Operational Implications**: Standardized container images (`python:3.14-slim`); straightforward dependency locking via `requirements.txt` and wheels.

---

## 2. Web Framework

* **1. Selected Technology**: **FastAPI (v0.115+)** [Approved in DEC-008]
* **2. Reason for Selection**: Native asynchronous request handling, automatic OpenAPI/Swagger documentation generation, tight integration with Pydantic v2 schemas for high-speed serialization and input validation.
* **3. Alternatives Considered**: Django REST Framework (DRF) [Proposed baseline in Blueprint v2.0], Flask, NestJS.
* **4. Advantages**: Sub-millisecond routing overhead; automatic request validation eliminating manual parsing; dependency injection system for database sessions and auth contexts.
* **5. Disadvantages**: Unlike Django, lacks built-in admin UI; requires explicit architectural composition for migrations and models.
* **6. Security Implications**: Strong type validation with Pydantic eliminates injection of unexpected attributes; automatic serialization prevents accidental leak of private model columns.
* **7. Operational Implications**: Runs on standard ASGI servers (`uvicorn`, `gunicorn`); horizontal scaling with minimal memory footprint.

---

## 3. Object-Relational Mapper (ORM)

* **1. Selected Technology**: **SQLAlchemy 2.0 (v2.0.30+)**
* **2. Reason for Selection**: Enterprise-grade relational toolkit offering declarative mapping, explicit transaction boundaries, robust connection pooling, and full support for PostgreSQL advanced features (partial indexes, UUIDs, JSONB).
* **3. Alternatives Considered**: Tortoise ORM, SQLModel, Peewee, raw asyncpg.
* **4. Advantages**: Modern typed declarative mapping (`Mapped[T]`); fine-grained control over query compilation and locking (`with_for_update()`); battle-tested across decades.
* **5. Disadvantages**: Steeper learning curve than Active Record patterns; requires discipline to prevent accidental N+1 query patterns.
* **6. Security Implications**: Complete protection against SQL injection via parameterized expression trees; explicit commit/rollback controls.
* **7. Operational Implications**: Built-in connection pool recycling (`pool_pre_ping=True`) mitigates stale connections during network blips.

---

## 4. Relational Database Engine

* **1. Selected Technology**: **PostgreSQL 15+** [Source: LMS Blueprint v2.0, Pages 8–11]
* **2. Reason for Selection**: Native support for UUID generation (`gen_random_uuid()`), case-insensitive email (`CITEXT`), JSON document snapshotting (`JSONB`), and partial unique indexes essential for the single-active-session invariant.
* **3. Alternatives Considered**: MySQL 8.0, MariaDB, MongoDB.
* **4. Advantages**: Strict ACID compliance; rich constraint options (`CHECK`, `UNIQUE`, foreign key `RESTRICT`); superior JSONB indexing (GIN).
* **5. Disadvantages**: Requires dedicated database administration and tuning for large connection pools.
* **6. Security Implications**: Role-based table permissions allow enforcing append-only policies (e.g., revoking `UPDATE` and `DELETE` on `audit_logs`).
* **7. Operational Implications**: Supported by all major cloud providers (AWS RDS, GCP Cloud SQL, Supabase); established backup and point-in-time recovery tooling.

---

## 5. Schema Migration System

* **1. Selected Technology**: **Alembic (v1.13+)**
* **2. Reason for Selection**: The official migration tool for SQLAlchemy; programmatic revision generation; reversible multi-stage migration support.
* **3. Alternatives Considered**: Flyway, Liquibase, raw manual SQL scripts.
* **4. Advantages**: Autogenerate inspection compares models against live schemas; migrations are versioned Python scripts committed to Git.
* **5. Disadvantages**: Autogenerate requires manual review for column renames or complex index conditions.
* **6. Security Implications**: DDL operations can be audited in version control before production deployment; supports non-destructive expand-and-contract rollouts.
* **7. Operational Implications**: Can be executed automatically in CI/CD release pipelines or via isolated CLI commands.

---

## 6. Authentication & Session Strategy

* **1. Selected Technology**: **Opaque Random Session Tokens (Cryptographically Hashed) in HttpOnly Cookies** [Source: LMS Blueprint v2.0, Page 8]
* **2. Reason for Selection**: Eliminates credential pooling and password sharing; permits instantaneous server-side revocation across devices upon new login or security compromise.
* **3. Alternatives Considered**: Stateless JWTs in localStorage, Bearer token headers, distributed OAuth2 access tokens.
* **4. Advantages**: Token cannot be stolen via JavaScript XSS attacks (`HttpOnly`); server controls exact lifecycle without waiting for token expiration.
* **5. Disadvantages**: Requires database or cache lookup per protected request.
* **6. Security Implications**: Cookie declared with `Secure`, `HttpOnly`, `SameSite=Lax`, and `Path=/`; CSRF tokens protect all state-changing endpoints.
* **7. Operational Implications**: Clean session revocation; session table maintenance requires background purges of expired sessions.

---

## 7. Password Hashing Algorithm

* **1. Selected Technology**: **Argon2id (via `argon2-cffi`)**
* **2. Reason for Selection**: Winner of the Password Hashing Competition; superior resistance to GPU/ASIC brute-force attacks and side-channel timing attacks compared to legacy algorithms.
* **3. Alternatives Considered**: bcrypt, PBKDF2-HMAC-SHA256, scrypt.
* **4. Advantages**: Highly configurable memory, time, and parallelism parameters; future-proof cryptographic baseline.
* **5. Disadvantages**: Higher CPU and memory utilization during authentication compared to lightweight hashes (deliberate security property).
* **6. Security Implications**: Completely eliminates rainbow table lookups and offline brute-force cracking viability.
* **7. Operational Implications**: Cost parameters can be adjusted as server hardware scales.

---

## 8. API Architecture & Serialization

* **1. Selected Technology**: **RESTful JSON API with Versioned Base Path (`/api/v1/`)** [Source: LMS Blueprint v2.0, Page 11]
* **2. Reason for Selection**: Universal client compatibility across web, mobile, and third-party webhooks; intuitive resource mapping; deterministic caching.
* **3. Alternatives Considered**: GraphQL, gRPC, tRPC.
* **4. Advantages**: Standard HTTP status codes; clear caching semantics; human-readable debugging; simple webhook ingress.
* **5. Disadvantages**: Potential over-fetching on complex dashboard views (mitigated by field filtering and tailored DTOs).
* **6. Security Implications**: Predictable endpoint attack surfaces; standard rate limiting and WAF rules apply cleanly.
* **7. Operational Implications**: Extensive tooling ecosystem for automated contract testing and mock servers.

---

## 9. Asynchronous Task Queue & Distributed Mutex

* **1. Selected Technology**: **Celery + Redis** (or Python Async Background Worker)
* **2. Reason for Selection**: Proven distributed task broker capable of handling asynchronous video transcoding poller tasks, outbox notification mailers, and CSV import parsing without stalling HTTP threads.
* **3. Alternatives Considered**: BullMQ, AWS SQS, RQ (Redis Queue).
* **4. Advantages**: Robust retry mechanics, exponential backoff, rate limiting, and dead-letter queueing.
* **5. Disadvantages**: Introduces Redis infrastructure dependency.
* **6. Security Implications**: Redis instance must be private and password/TLS-protected.
* **7. Operational Implications**: Requires separate worker process monitoring in production.

---

## 10. Transactional Email Service

* **1. Selected Technology**: **Transactional SMTP / API (Postmark / Resend / AWS SES)**
* **2. Reason for Selection**: High inbox deliverability for critical transactional events (mandatory email verification, receipts, grade releases, password resets).
* **3. Alternatives Considered**: Self-hosted Postfix, SendGrid, Mailgun.
* **4. Advantages**: Dedicated transactional IP pools; delivery webhooks and bounce tracking.
* **5. Disadvantages**: Per-message vendor costs.
* **6. Security Implications**: API keys stored strictly in environment variables; zero email credentials committed to Git.
* **7. Operational Implications**: Templating managed via code or remote dashboard with template versioning.

---

## 11. Cloud Object Storage

* **1. Selected Technology**: **Private Cloud Storage (AWS S3 / Cloudflare R2 / GCS)** [Source: LMS Blueprint v2.0, Page 5]
* **2. Reason for Selection**: S3-compatible API standards; presigned upload intent support; immutable private object storage.
* **3. Alternatives Considered**: Local disk storage, NFS, GridFS.
* **4. Advantages**: Infinite scalability; zero storage bottleneck on application servers; direct client-to-storage upload intents.
* **5. Disadvantages**: Requires egress bandwidth management.
* **6. Security Implications**: Public bucket access is permanently disabled; files accessible exclusively via short-lived signed URLs after active session and entitlement validation.
* **7. Operational Implications**: Lifecycle policies automatically archive raw uploaded source files after transcoding.

---

## 12. Payment Gateway

* **1. Selected Technology**: **Razorpay** [Source: LMS Blueprint v2.0, Pages 2, 10, 13]
* **2. Reason for Selection**: Market leader for direct course commercialization in India; native support for UPI, domestic/international cards, net banking, EMI; robust HMAC-SHA256 signed webhook events.
* **3. Alternatives Considered**: Stripe, Cashfree, PayPal.
* **4. Advantages**: Seamless INR paise precision; built-in automated refund APIs; recurring subscription capabilities.
* **5. Disadvantages**: Geographic concentration in India (Stripe required for global-first models).
* **6. Security Implications**: Strict HMAC signature verification on all incoming webhook callbacks; zero trust on browser redirects.
* **7. Operational Implications**: Webhook secret rotation supported via Super Admin governance portal.

---

## 13. Automated Testing Framework

* **1. Selected Technology**: **pytest + pytest-asyncio + Starlette TestClient (httpx)**
* **2. Reason for Selection**: Rich fixture architecture, expressive assertions, fast execution, seamless testing of async endpoints and isolated transactional database rollbacks.
* **3. Alternatives Considered**: Python `unittest`, Nose2.
* **4. Advantages**: Parameterized testing; comprehensive plugin ecosystem; sub-second test execution.
* **5. Disadvantages**: Requires discipline with async event loops.
* **6. Security Implications**: Enables automated regression testing of security invariants (IDOR, CSRF, session races, SQL injection).
* **7. Operational Implications**: Runs as a gating step in pre-commit hooks and CI/CD pipelines.

---

## 14. Structured Logging & Telemetry

* **1. Selected Technology**: **Structured JSON Logging with Redaction Filter**
* **2. Reason for Selection**: Machine-readable log formatting for centralized ingestion (Datadog, CloudWatch, Loki) with automated masking of sensitive secrets.
* **3. Alternatives Considered**: Plaintext stdout logging, ELK stack logstash forwarders.
* **4. Advantages**: Native JSON parsing; searchable by `request_id`, `actor_id`, and `level`.
* **5. Disadvantages**: Slightly more verbose in local terminal debugging.
* **6. Security Implications**: Eliminates accidental leaks of passwords, authorization tokens, or payment card numbers in log files.
* **7. Operational Implications**: Seamless correlation across distributed tracing systems.
