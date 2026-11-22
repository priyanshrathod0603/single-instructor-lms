# Backend Folder & File Structure Specification

## 1. Architectural Layout Overview

The Single-Instructor LMS backend follows a layered, modular domain-driven architecture built on FastAPI, SQLAlchemy 2.0, Pydantic v2, and Alembic. The design enforces clean separation of concerns, strict dependency directions, and transactional boundaries.

```
backend/
├── alembic.ini                   # Alembic database migration configuration
├── pyproject.toml                # Project metadata, dependencies, and tool settings
├── Dockerfile                    # Production container image definition
├── docker-compose.yml            # Local development orchestration (PostgreSQL, Redis, MinIO/LocalStack)
├── .env.example                  # Environment variable contract and defaults
├── .gitignore                    # Backend-specific ignore patterns
├── app/
│   ├── __init__.py               # Package marker
│   ├── main.py                   # FastAPI application factory, lifespan, CORS, middleware, global routers
│   ├── api/                      # Presentation layer: HTTP routers, parameters, route dependencies
│   │   ├── __init__.py
│   │   ├── deps.py               # Shared FastAPI dependencies (get_db, get_current_user, require_permissions)
│   │   └── v1/                   # API Version 1 endpoints
│   │       ├── __init__.py
│   │       ├── router.py         # Aggregator router mounting all v1 sub-routers
│   │       ├── auth.py           # Login, logout, token refresh, email verification, password reset, OAuth
│   │       ├── users.py          # User management, profile updates, staff management
│   │       ├── courses.py        # Course CRUD, revision controls, publishing checklist
│   │       ├── sections.py       # Curriculum sections management, optimistic reordering
│   │       ├── lessons.py        # Lesson CRUD, video/article/resource content attachments
│   │       ├── assignments.py    # Assignment creation, submissions, rubric evaluations, overrides
│   │       ├── quizzes.py        # Quiz creation, questions, bulk CSV import, attempts, autosave
│   │       ├── enrollments.py    # Student enrollments, access checks, course completion verification
│   │       ├── payments.py       # Order initialization, payment history, refund management
│   │       ├── webhooks.py       # Cryptographic webhook ingestion (Razorpay HMAC-SHA256)
│   │       ├── progress.py       # Lesson progress tracking, video watch position, completion toggles
│   │       ├── certificates.py   # Certificate generation, verification, public certificate rendering
│   │       ├── media.py          # Presigned upload URLs, media metadata, secure streaming token generation
│   │       ├── notifications.py  # In-app notification feeds, mark-as-read, preference settings
│   │       ├── audit.py          # Super Admin audit log viewer and query filters
│   │       └── health.py         # Liveness and readiness probes (DB, Redis ping)
│   ├── core/                     # Infrastructure & cross-cutting foundations
│   │   ├── __init__.py
│   │   ├── config.py             # Pydantic Settings management (.env parsing, validation)
│   │   ├── database.py           # SQLAlchemy engine, async/sync session factories, connection pools
│   │   ├── security.py           # Argon2id password hashing, JWT creation/validation, HMAC signature verification
│   │   ├── session.py            # Single-Active-Session lifecycle, cookie management, atomic revocation
│   │   ├── permissions.py        # Granular permission definitions, role hierarchy, RBAC evaluator
│   │   ├── exceptions.py         # Custom application exceptions, domain error definitions
│   │   ├── error_handlers.py     # FastAPI exception handlers returning standard error envelopes
│   │   ├── constants.py          # Enums for roles, statuses, payment states, mime types
│   │   └── logging.py            # Structured JSON logger configuration with request_id propagation
│   ├── models/                   # Data Access layer: SQLAlchemy 2.0 Declarative Models
│   │   ├── __init__.py           # Exports all models for Alembic auto-discovery
│   │   ├── base.py               # DeclarativeBase, UUID primary key mixin, TimestampMixin
│   │   ├── user.py               # User, Role, UserRole models
│   │   ├── auth_session.py       # AuthSession model with partial unique active index
│   │   ├── auth_token.py         # Email verification, password reset, onboarding tokens
│   │   ├── course.py             # Course, CourseRevision, CourseTag models
│   │   ├── curriculum.py         # Section, Lesson, LessonResource models
│   │   ├── assignment.py         # Assignment, AssignmentSubmission, Rubric, RubricCriteria, RubricScore
│   │   ├── quiz.py               # Quiz, QuizQuestion, QuizQuestionOption, QuizAttempt, QuizAnswer
│   │   ├── enrollment.py         # Enrollment model with status, validity window, access flags
│   │   ├── payment.py            # Order, PaymentTransaction, Refund models
│   │   ├── progress.py           # LessonProgress, CourseProgressSummary models
│   │   ├── certificate.py        # Certificate, CertificateTemplate models
│   │   ├── media.py              # MediaAsset, TranscodedStream models
│   │   ├── notification.py       # Notification, NotificationOutbox, NotificationPreference models
│   │   └── audit_log.py          # Immutable AuditLog model
│   ├── schemas/                  # Presentation / DTO layer: Pydantic v2 validation models
│   │   ├── __init__.py
│   │   ├── common.py             # Standard APIResponse, ErrorEnvelope, PaginationParams, PaginatedResponse
│   │   ├── auth.py               # LoginRequest, RegisterRequest, TokenResponse, PasswordResetRequest
│   │   ├── user.py               # UserResponse, UserCreate, UserUpdate, UserFilter
│   │   ├── course.py             # CourseCreate, CourseUpdate, CourseResponse, CourseRevisionResponse
│   │   ├── curriculum.py         # SectionCreate, SectionReorder, LessonCreate, LessonResponse
│   │   ├── assignment.py         # AssignmentCreate, SubmissionCreate, GradeSubmissionRequest
│   │   ├── quiz.py               # QuizCreate, QuestionCreate, QuizAttemptStart, QuizAnswerSubmit
│   │   ├── enrollment.py         # EnrollmentResponse, EnrollmentFilter
│   │   ├── payment.py            # OrderCreateRequest, OrderResponse, WebhookPayload, RefundRequest
│   │   ├── progress.py           # ProgressUpdateRequest, ProgressResponse
│   │   ├── certificate.py        # CertificateResponse, CertificateVerifyResponse
│   │   ├── media.py              # UploadIntentRequest, UploadIntentResponse, PlaybackTokenResponse
│   │   ├── notification.py       # NotificationResponse, NotificationMarkReadRequest
│   │   └── audit.py              # AuditLogResponse, AuditLogFilter
│   ├── repositories/             # Persistence abstraction: Database queries, row-level locks, transactions
│   │   ├── __init__.py
│   │   ├── base.py               # Generic CRUD repository with generic query filters
│   │   ├── user_repo.py          # User queries, email lookups, credential retrieval
│   │   ├── session_repo.py       # Atomic session displacement (FOR UPDATE, update active to revoked)
│   │   ├── course_repo.py        # Course revision cloning, published snapshot retrieval
│   │   ├── curriculum_repo.py    # Section/lesson bulk reordering, position swapping
│   │   ├── assignment_repo.py    # Submissions, rubric score insertions, grade overrides
│   │   ├── quiz_repo.py          # Quiz attempts, autosave updates, randomized question selection
│   │   ├── enrollment_repo.py    # Enrollment grant, revocation, active enrollment lookups
│   │   ├── payment_repo.py       # Order state transitions, idempotent transaction recording
│   │   ├── progress_repo.py      # Watch time UPSERT, lesson completion tracking
│   │   ├── media_repo.py         # Media asset status transitions
│   │   └── audit_repo.py         # Append-only audit log insertions
│   ├── services/                 # Domain Business Logic layer
│   │   ├── __init__.py
│   │   ├── auth_service.py       # Login coordination, OAuth token exchange, email verification
│   │   ├── session_service.py    # Single-active-session orchestration, token issuance, revocation
│   │   ├── user_service.py       # User onboarding, profile management, role assignment
│   │   ├── course_service.py     # Revision management, publishing validation checklist, archiving
│   │   ├── curriculum_service.py # Optimistic reordering validation, lesson content attachment
│   │   ├── assignment_service.py # Rubric validation, submission evaluation, grade release
│   │   ├── quiz_service.py       # Server-side timer validation, question shuffling, score calculation
│   │   ├── payment_service.py    # Razorpay order generation, HMAC verification, refund processing
│   │   ├── enrollment_service.py # Webhook-driven enrollment provisioning, access revocation
│   │   ├── progress_service.py   # Completion rule evaluation, certificate issuance trigger
│   │   ├── certificate_service.py# Cryptographic certificate generation, public URL verification
│   │   ├── media_service.py      # S3/Cloudflare R2 presigned URL issuance, HLS playback token creation
│   │   ├── notification_service.py # Transactional outbox queuing, event dispatching
│   │   └── audit_service.py      # Actor context capture, diff generation, audit dispatching
│   └── workers/                  # Background task workers (Transactional Outbox processor, transcode hook)
│       ├── __init__.py
│       ├── outbox_worker.py      # Polls notification_outbox table, delivers emails via Resend/SendGrid
│       └── transcode_worker.py   # Processes video transcode webhook callbacks from external encoder
├── migrations/                   # Alembic database migrations
│   ├── env.py                    # Alembic migration engine and target metadata wiring
│   ├── script.py.mako            # Migration template
│   └── versions/                 # Versioned migration scripts (001_initial_schema.py, etc.)
└── tests/                        # Comprehensive automated test suite
    ├── conftest.py               # Pytest fixtures, test database engine, client, mock services
    ├── unit/                     # Unit tests for core security, schemas, and isolated service logic
    │   ├── test_security.py      # Argon2id hashing, JWT, HMAC verification
    │   ├── test_permissions.py   # RBAC evaluator, deny-overrides-allow logic
    │   └── test_schemas.py       # Pydantic input/output validation checks
    ├── integration/              # Integration tests verifying database transactions and repository operations
    │   ├── test_session_repo.py  # Single-active session concurrency and atomic displacement
    │   ├── test_course_repo.py   # Revision immutability and draft cloning
    │   ├── test_payment_repo.py  # Idempotent order and transaction state machine
    │   └── test_audit_repo.py    # Audit log append-only enforcement
    ├── api/                      # End-to-end HTTP API route tests
    │   ├── test_auth_api.py      # Login, session revocation, verification flows
    │   ├── test_courses_api.py   # Course CRUD, revision publication, reordering conflicts
    │   ├── test_webhooks_api.py  # Razorpay webhook verification, payment success, enrollment grant
    │   ├── test_assignments_api.py # Submissions and rubric grading
    │   ├── test_quizzes_api.py   # Quiz attempts, autosave, server timer enforcement
    │   └── test_progress_api.py  # Progress tracking and completion verification
    └── security/                 # Penetration and security vulnerability tests
        ├── test_session_hijack.py# Concurrent login displacement verification
        ├── test_idor.py          # Indirect Object Reference checks on submissions and enrollments
        └── test_tamper_webhook.py# Invalid HMAC signature rejection
```

---

## 2. Layer Responsibilities & Strict Dependency Rules

### 2.1 Layer Boundaries
1. **Presentation Layer (`app/api/`)**:
   - Parses HTTP requests and deserializes JSON payloads into Pydantic models.
   - Enforces authentication and authorization dependencies (`deps.py`).
   - Delegates all business logic to the appropriate Domain Service.
   - Serializes domain results into standardized API response envelopes (`APIResponse[T]`).
   - **Rule**: Routers must NOT directly execute raw SQL, construct database transactions, or contain business logic.

2. **Domain Business Logic Layer (`app/services/`)**:
   - Encapsulates all domain workflows, invariant validations, and state machines.
   - Coordinates multi-step transactions across multiple repositories.
   - Emits transactional outbox events (notifications, audit log entries).
   - **Rule**: Services must NOT accept raw FastAPI `Request` objects or return HTTP response objects directly. Services deal exclusively with domain models, primitives, and Pydantic DTOs.

3. **Data Access & Persistence Layer (`app/repositories/`)**:
   - Executes concrete database queries using SQLAlchemy 2.0 select, insert, update constructs.
   - Manages row-level locking (`with_for_update()`) for critical atomic operations.
   - Isolates SQLAlchemy query syntax from domain business rules.
   - **Rule**: Repositories must NOT make HTTP calls, evaluate business permissions, or trigger external side effects.

4. **Data Models Layer (`app/models/`)**:
   - Defines SQLAlchemy 2.0 declarative database entities, column constraints, indexes, and relationships.
   - **Rule**: Models must NOT contain application state logic or API formatting logic.

5. **Transfer & Validation Layer (`app/schemas/`)**:
   - Pure Pydantic v2 schemas defining input contracts, output representations, and filtering criteria.
   - **Rule**: Schemas must NOT import database models or execute database queries.

6. **Infrastructure & Cross-Cutting Layer (`app/core/`)**:
   - Provides reusable utilities: configuration, cryptographic functions, session tokens, error envelopes, and logging.
   - **Rule**: Core utilities must be framework-agnostic where possible and have zero circular dependencies on `app/services` or `app/api`.

---

## 3. Direction of Dependencies (Unidirectional Flow)

The system strictly enforces unidirectional downward dependencies:

$$\text{API (Routers)} \longrightarrow \text{Services (Domain Logic)} \longrightarrow \text{Repositories (Data Access)} \longrightarrow \text{Database (PostgreSQL)}$$

* **Allowed**:
  - `api` imports `services`, `schemas`, `core`
  - `services` imports `repositories`, `models`, `schemas`, `core`
  - `repositories` imports `models`, `core`
  - `models` imports `core`
* **Strictly Prohibited**:
  - `repositories` importing `services` or `api`
  - `models` importing `repositories` or `services`
  - `services` importing `api` routes or HTTP-specific constructs
  - Circular imports across any module boundaries
