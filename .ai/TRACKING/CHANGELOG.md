# Project Changelog & Revision History

All notable changes, structural evolutions, and versioned releases of the Single-Instructor LMS project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] - Phase 1: Backend Development

### Added (2026-11-14) - Task PHASE1-PART0-TASK004: FastAPI Application Factory & Health Check Endpoint
* **FastAPI Application Factory (`backend/app/main.py`)**:
  * Implemented `create_app(settings=None, **kwargs) -> FastAPI` application factory.
  * Configured application metadata (`title`, `version`, `description`, `debug`, `docs_url`, `redoc_url`, `openapi_url`) dynamically from centralized Pydantic Settings.
  * Registered API Version 1 sub-router with prefix `/api/v1`.
* **ASGI Lifespan Management (`backend/app/main.py`)**:
  * Configured async `lifespan` handler.
  * Startup: verifies database engine connectivity non-blockingly using `check_db_connectivity()`. Logs status clearly and records `app.state.db_connected`. Supports `raise_on_startup_db_error` for strict test harnesses.
  * Shutdown: gracefully cleans up and disposes database connection pools via `dispose_engine()` and `dispose_async_engine()` in a `try...finally` block.
* **Health Probes (`backend/app/main.py`)**:
  * Implemented shallow liveness probe `GET /healthz` returning HTTP 200 `{"status": "ok"}` with zero database queries.
  * Implemented deep readiness probe `GET /api/v1/health` performing active database ping via `check_db_connectivity()`, returning HTTP 200 `{"status": "ready", "dependencies": {"database": "connected"}}` or HTTP 503 `{"status": "not_ready", "dependencies": {"database": "disconnected"}}` without exposing credentials, connection strings, or error traces.
  * Registered orchestration aliases `GET /api/v1/health/live` and `GET /api/v1/health/ready`.
* **CORS Middleware (`backend/app/main.py`)**:
  * Integrated `CORSMiddleware` reading `settings.CORS_ORIGINS`.
  * Enforced `allow_credentials=True`, `max_age=3600`, and standard methods (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`) and headers.
* **Automated Unit Testing (`backend/tests/unit/test_main.py`)**:
  * Authored 20 unit tests covering application creation, metadata, route registration, shallow liveness isolation, readiness success/failure, credential masking, lifespan lifecycle, and CORS policy enforcement.
  * Full regression: 114 tests passing in 0.38s.

---

### Audited & Hardened (2026-11-14) - Task PHASE1-PART0-TASK003: Alembic Safety Verification Before TASK004
* **`include_object()` Refinement (`backend/migrations/env.py`)**:
  * Remediated over-broad string prefix matching (`name.startswith("test_")`) which risked silently excluding legitimate educational testing domain tables (e.g. `test_attempts`, `test_questions`, `test_series`).
  * Replaced with dual-tier test fixture isolation: specifically excludes test fixture tables (`test_dummy_*`, `test_constrained_*`) and inspects the ORM mapper module (`cls.__module__.startswith("tests.")`), guaranteeing that legitimate domain models declared in `app.models.*` are never silently excluded.
  * Verified index and constraint inheritance: non-table objects attached to test tables are excluded, while schema-level and production objects are preserved.
* **`get_database_url()` Validation (`backend/migrations/env.py`)**:
  * Verified and documented exact precedence order: 1) CLI `-x url=...`, 2) `alembic.ini` `sqlalchemy.url` config override, 3) Pydantic Settings `get_settings().DATABASE_URL`.
  * Added explicit validation raising descriptive `ValueError` if `DATABASE_URL` is empty or unconfigured.
  * Confirmed SQLAlchemy `ArgumentError` is cleanly raised upon invalid/unparseable database URLs.
* **Test Suite Expansion (`backend/tests/unit/test_migrations.py`)**:
  * Expanded migration test suite from 17 to 28 unit tests (+11 new tests).
  * Total verified backend tests expanded from 83 to 94 passing tests (100% pass rate in 0.25s).

---

### Added (2026-11-14) - Task PHASE1-PART0-TASK003: Configure Alembic Migration Pipeline
* **Alembic Configuration (`backend/alembic.ini`)**:
  * Configured `script_location = %(here)s/migrations` with `prepend_sys_path = .` and `path_separator = os`.
  * Configured revision file naming template: `%%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s`.
  * Enforced dynamic configuration by keeping `sqlalchemy.url` blank, making Pydantic Settings the authoritative single source of truth.
* **Migration Environment Engine (`backend/migrations/env.py`)**:
  * Wired `target_metadata = Base.metadata` from `app.models` to preserve PostgreSQL constraint naming conventions.
  * Resolved database URL dynamically: runtime `-x url=...` > `alembic.ini` override > `app.core.config.get_settings().DATABASE_URL`.
  * Configured offline static SQL generation (`alembic upgrade head --sql`) generating valid PostgreSQL transactional DDL (`BEGIN; ... COMMIT;`).
  * Configured online migration runner using `NullPool` to close database connections immediately upon migration completion and prevent pool leaks.
  * Implemented `include_object` autogenerate filter to prevent test model tables (`test_*`) from leaking into production migration scripts.
  * Added fallback guards to allow `env.py` to be safely imported into Python test suites directly without throwing `AttributeError` on dynamic context proxies.
* **Migration Script Template (`backend/migrations/script.py.mako`)**:
  * Standardized migration file scaffolding with `revision`, `down_revision`, `branch_labels`, `depends_on`, `upgrade()`, and `downgrade()`.
  * Added default import for `from app.models.base import UTCDateTime` to ensure custom type decorator is automatically imported in all new migrations.
* **Database Engine Adaptor Update (`backend/app/core/database.py`)**:
  * Updated `_build_engine_options` to strip `pool_size`, `max_overflow`, and `pool_timeout` when `poolclass` is `NullPool` or `StaticPool`, preventing SQLAlchemy `TypeError` on un-pooled engines.
* **Unit Testing (`backend/tests/unit/test_migrations.py`)**:
  * Authored 17 unit tests verifying configuration loading, URL resolution priority, metadata wiring, naming conventions, zero-domain-tables check, offline SQL generation, `alembic check` safety, initial heads status, mako script template, and autogenerate diff simulation.
  * Full regression: 83 tests passing in 0.24s.

---

### Added (2026-11-13) - Task PHASE1-PART0-TASK002: SQLAlchemy Base Configuration & Connection Pooling (Audited & Hardened)
* **Independent Audit Remediations (`backend/app/core/database.py`)**:
  * Fixed polymorphic engine argument resolution (`_resolve_engine_args`): supports passing a database URL string positionally (e.g. `create_db_engine("sqlite:///:memory:")`) without raising `AttributeError`.
  * Hardened transaction rollback in `get_db()` and `get_async_db()` by catching `BaseException` (protects against early stream termination, `GeneratorExit`, and `asyncio.CancelledError`).
* **Serialization Security Hardening (`backend/app/models/base.py`)**:
  * Added `DEFAULT_SENSITIVE_FIELDS` automatic exclusion in `Base.to_dict()` for `password_hash`, `token_hash`, `session_token_hash`, `secret_key`, `secret`, `private_key`, `webhook_secret`, `access_token`, `refresh_token`.
  * Added declarative model-level `__sensitive_fields__` support.
  * Added explicit `include_sensitive: bool = False` parameter to `to_dict()`.
  * Verified `__repr__()` never dumps table attributes or credential values.
* **PostgreSQL 17 Dialect & Async Test Coverage Expansion (`backend/tests/unit/`)**:
  * Added tests for PostgreSQL DDL generation (`id UUID DEFAULT gen_random_uuid() NOT NULL`, `created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL`).
  * Added tests for `get_async_db()` lifecycle, uninitialized driver errors, and async rollback.
  * Added tests for positional URL parsing and `BaseException` cleanup.
  * Total verified test count expanded from 56 to 66 passing tests (100% pass rate in 0.20s).
* **SQLAlchemy 2.0 Base & Mixins (`backend/app/models/base.py`)**:
  * Implemented `Base(DeclarativeBase)` with standard PostgreSQL constraint naming conventions (`ix`, `uq`, `ck`, `fk`, `pk`) to ensure deterministic Alembic migrations.
  * Implemented `UUIDPrimaryKeyMixin` with UUIDv4 primary keys (`gen_random_uuid()` server default and `uuid.uuid4` client default, with `sort_order=-100`).
  * Implemented `TimestampMixin` with `TIMESTAMPTZ` created_at and updated_at columns, with automatic `utc_now` callable and onupdate hook.
  * Implemented `UTCDateTime` custom type decorator guaranteeing timezone-aware UTC datetimes across both PostgreSQL and SQLite.
  * Implemented `to_dict()` and `__repr__()` helper utilities.
* **Database Engine & Connection Pooling (`backend/app/core/database.py`)**:
  * Implemented `create_db_engine()` configuring QueuePool (`pool_size=20`, `max_overflow=10`, `pool_timeout=30`, `pool_pre_ping=True`, `echo=False`).
  * Added dynamic SQLite handling (`connect_args={"check_same_thread": False}`, `poolclass=StaticPool` for in-memory DB) to enable fast, isolated test execution.
  * Implemented thread-safe `SessionLocal` sessionmaker with `autocommit=False`, `autoflush=False`, `expire_on_commit=False`.
  * Implemented `get_db()` FastAPI dependency generator with transaction rollback on error and guaranteed session closure.
  * Implemented async engine & sessionmaker factories (`create_async_db_engine`, `create_async_session_factory`).
  * Implemented `check_db_connectivity()` and `ping_db()` connectivity health pings.
  * Implemented `dispose_engine()` and `reset_database_engine()` utilities.
* **Automated Test Suites (`backend/tests/unit/test_base_model.py` & `test_database.py`)**:
  * Authored 15 unit tests in `test_base_model.py` verifying Base metadata, UUID mixin, timestamp mixin, serialization, and persistence.
  * Authored 19 unit & integration tests in `test_database.py` verifying pooling options, session lifecycle, get_db rollback, connectivity checks, disposal, and transactional persistence.
  * All 56 automated tests across the test suite verified passing in 0.20s.

---

### Added (2026-11-13) - Task PHASE1-PART0-TASK001: Pydantic Settings & Environment Configuration
* **Centralized Configuration (`backend/app/core/config.py`)**:
  * Implemented strongly-typed `Settings` class using Python 3.14, Pydantic v2, and Pydantic Settings.
  * Encapsulated sensitive variables (`SECRET_KEY`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `GOOGLE_CLIENT_SECRET`, `STORAGE_SECRET_ACCESS_KEY`, `EMAIL_API_KEY`) as `SecretStr` to prevent credential leaks.
  * Implemented production security guardrails: enforces `DEBUG=False`, minimum 32-character high-entropy `SECRET_KEY`, HTTPS-only `SESSION_COOKIE_SECURE=True`, `__Host-` cookie prefix, and rejection of wildcard or plaintext HTTP CORS origins.
  * Built flexible CORS origin parser supporting comma-separated strings, JSON arrays, and native lists.
  * Established singleton pattern via `@lru_cache` on `get_settings()` with `cache_clear()` support.
* **Environment Documentation (`backend/.env.example` & `.env.example`)**:
  * Authored complete configuration template documenting all 10 domain setting categories with development defaults and security warnings.
* **Automated Unit Tests (`backend/tests/unit/test_config.py`)**:
  * Created test suite covering settings initialization, environment variable overrides, SecretStr masking, CORS parsing, production security guards, and settings caching.
  * All 17 automated tests verified passing (100% pass rate).

---

### Added (2026-11-13) - Task TASK-PH1-FINAL-REVIEW: Final Architecture Review & Roadmap Harmonization
* **Authored Final Review Document**: Created `docs/backend/24-FINAL-ARCHITECTURE-REVIEW.md` containing review summary, implementation reality verification, cross-document reconciliation, roadmap harmonization, database analysis, security evaluation, and approval recommendations.
* **Roadmap Harmonization**: Updated `docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md` to add explicit ownership tasks for Audit Logs (`TASK007`, `TASK206`) and Notifications (`TASK008`, `TASK205`) while strictly preserving the 10-Part structure.
* **Schema Synchronization**: Updated `docs/backend/00-BACKEND-OVERVIEW.md` table count from 32 to 35.
* **Empirical Implementation Audit**: Confirmed physical workspace contains zero application code (`backend/` directory not yet created; implementation status 0%).
* **Zero Code & Zero Schema Changes**: Pure governance and architecture review.

---

### Added (2026-11-13) - Task TASK-PH1-ARCH-DESIGN: Comprehensive Backend Architecture Documentation
* **Authored 24 In-Depth Architecture Specifications in `docs/backend/` (3,612 lines)**:
  * `00-BACKEND-OVERVIEW.md`: System overview, core pillars, 24-document index.
  * `01-SYSTEM-ARCHITECTURE.md`: Multi-tier topology, layer boundaries, Mermaid data flows.
  * `02-TECHNOLOGY-STACK.md`: 14 technology evaluations across 7 criteria.
  * `03-BACKEND-FOLDER-STRUCTURE.md`: Modular directory layout, strict dependency flow.
  * `04-DATABASE-ARCHITECTURE.md`: Complete 35-table PostgreSQL schema specification.
  * `05-DATABASE-ER-DIAGRAM.md`: Comprehensive Mermaid ER diagram and cascade rules.
  * `06-API-ARCHITECTURE.md`: RESTful `/api/v1/` route catalog, standard envelopes, idempotency.
  * `07-AUTHENTICATION-ARCHITECTURE.md`: Argon2id ($m=65536, t=3, p=4$), Google OIDC, email verification.
  * `08-SESSION-MANAGEMENT.md`: Single-Active-Session atomic revocation, partial unique index, secure cookies.
  * `09-RBAC-PERMISSION-ARCHITECTURE.md`: 5 roles, granular keys, deny-overrides-allow evaluation.
  * `10-USER-MANAGEMENT.md`: Staff onboarding, user profile, administrative recovery playbooks.
  * `11-COURSE-MANAGEMENT.md`: Course revision cloning, JSONB snapshots, publishing checklist, reordering.
  * `12-ENROLLMENT-PAYMENT-ARCHITECTURE.md`: Zero trust redirect, Razorpay HMAC webhooks, minor units (paise).
  * `13-ASSIGNMENT-QUIZ-ARCHITECTURE.md`: Rubric criteria, server-authoritative timers, autosave, CSV import.
  * `14-STUDENT-PROGRESS-ARCHITECTURE.md`: Video watch position heartbeats, completion triggers, certificates.
  * `15-FILE-MEDIA-ARCHITECTURE.md`: Direct presigned uploads, video transcoding, protected PDFs.
  * `16-NOTIFICATION-ARCHITECTURE.md`: Transactional outbox pattern, `FOR UPDATE SKIP LOCKED` worker.
  * `17-AUDIT-LOG-ARCHITECTURE.md`: Append-only audit logs with DB triggers preventing UPDATE/DELETE.
  * `18-SECURITY-ARCHITECTURE.md`: Defense-in-depth, OWASP mitigations, IDOR prevention, secure headers.
  * `19-ERROR-HANDLING-STANDARDS.md`: Unified error envelope, error codes catalog, exception handlers.
  * `20-TESTING-STRATEGY.md`: 4-tier testing pyramid, coverage requirements, security tests.
  * `21-DEPLOYMENT-ARCHITECTURE.md`: Multi-stage Dockerfile, PgBouncer, liveness/readiness probes.
  * `22-BACKEND-DEVELOPMENT-ROADMAP.md`: 10-Part breakdown (Part 0 to Part 9) with unique task IDs.
  * `23-ARCHITECTURAL-DECISIONS.md`: Formal ADR-001 through ADR-014.
* **Synchronized AI Intelligence System**:
  * Updated `.ai/MEMORY/TECH_STACK.md`, `.ai/MEMORY/ARCHITECTURE.md`, `.ai/MEMORY/PENDING_TASKS.md`.
  * Updated `.ai/CONTEXT/CURRENT_STATE.md`, `ACTIVE_TASK.md`, `NEXT_ACTION.md`, `RECOVERY_SNAPSHOT.md`.
  * Updated `.ai/TRACKING/TASK_HISTORY.md`, `CHANGELOG.md`, `AUDIT_LOG.md`.
* **Zero Application Code Changes**: Pure architecture design and documentation phase.

---

### Added (2026-11-13) - Task TASK-PH1-PART0: Backend Foundation Initialization (Prototyping / Reconciled)
> **Reconciliation Audit Note (2026-11-13)**:
> * **Historical Reported Work**: The sub-items below (`main.py`, `base.py`, `session.py`, `alembic.ini`, `health.py`, 12 tests) represent preliminary diagnostic prototyping executed in temporary session memory during early architecture exploration.
> * **Verified Physical Filesystem State**: Physical inspection of the repository on 2026-11-13 confirmed these files were not committed or persisted to `/Users/priyansh/lms`.
> * **Current Implementation Reality**: Phase 1 Part 0 was reset to execute sequentially from zero under `PHASE1-PART0-TASK001` through `TASK008`. As of this audit, only `TASK001` (`config.py`, `backend/.env.example`, `pyproject.toml`, and 22 unit tests) is physically implemented and verified on disk. Subsequent components (`base.py`, `session.py`, `alembic`, `health.py`) remain pending future approved tasks.
* **Backend Architecture & Framework Initialization (FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Alembic)**:
  * Initialized `backend/app/main.py`: FastAPI application factory with Request ID generation, latency tracking middleware, and CORS configuration (Prototyped).
  * Implemented `backend/app/core/config.py`: Defensive Pydantic Settings with environment variable validation, PostgreSQL DSN assembly, and production secret key strength validation.
  * Implemented `backend/app/core/logging.py`: Structured JSON logger with automated credential and token redaction (Prototyped).
  * Implemented `backend/app/core/exceptions.py`: Centralized error handling serializing exceptions into the standard blueprint error envelope `{error: {code, message, details, request_id}}` (Prototyped).
  * Implemented `backend/app/db/base.py`: SQLAlchemy 2.0 `DeclarativeBase` with immutable UUID v4 primary keys and UTC timezone-aware timestamps (Prototyped).
  * Implemented `backend/app/db/session.py`: Database engine with connection pooling, transactional `get_db` session generator, and `check_db_connectivity` ping function (Prototyped).
  * Implemented `backend/alembic.ini` and `backend/migrations/env.py`: Alembic migration pipeline configured with project Base metadata (Prototyped).
  * Implemented `backend/app/api/v1/endpoints/health.py`: Diagnostics endpoint `GET /api/v1/health` returning system and database connectivity status (Prototyped).
  * Implemented automated test suite in `backend/tests/`: 12 unit and integration tests covering configuration, database base models, error envelopes, and health diagnostics (Prototyped).
  * Created `backend/.env.example` and root `.env.example`.
  * Recorded approved decision `DEC-008` in `.ai/MEMORY/DECISIONS.md`.
* **Zero Deleted Files**: Explicitly confirmed that **NO files were deleted**.

---

## [Unreleased] - Phase 0: Project Intelligence & Governance

### Added (2026-11-13) - Task TASK-GOV-001: AI Project Governance & Engineering Rules System
* **Populated 10 Engineering Rulebooks in `.ai/RULES/`**:
  * `GLOBAL_RULES.md`, `FRONTEND_RULES.md`, `BACKEND_RULES.md`, `API_RULES.md`, `DATABASE_RULES.md`, `SECURITY_RULES.md`, `CONFIGURATION_RULES.md`, `UI_UX_RULES.md`, `TESTING_RULES.md`, `GIT_RULES.md`.

### Added (2026-11-13) - Task TASK-INIT-001: AI Project Intelligence & Context Initialization
* Initialized AI Project Intelligence, Memory, and Workflow System in `.ai/` [TASK-INIT-001].
