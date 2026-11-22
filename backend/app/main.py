"""FastAPI application factory, ASGI lifespan management, and health endpoints.

Follows the backend architecture defined in:
- docs/backend/01-SYSTEM-ARCHITECTURE.md
- docs/backend/03-BACKEND-FOLDER-STRUCTURE.md
- docs/backend/06-API-ARCHITECTURE.md
- docs/backend/18-SECURITY-ARCHITECTURE.md
- docs/backend/21-DEPLOYMENT-ARCHITECTURE.md

Configures:
1. Centralized Pydantic Settings integration.
2. ASGI Lifespan: startup database verification & shutdown resource disposal.
3. Strict Cross-Origin Resource Sharing (CORS) middleware.
4. Liveness probe (GET /healthz) — shallow process check without database query.
5. Readiness probe (GET /api/v1/health) — deep dependency check verifying database link.
"""

from contextlib import asynccontextmanager
import logging
from typing import Any, Optional

from fastapi import APIRouter, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.core.database import (
    check_db_connectivity,
    dispose_async_engine,
    dispose_engine,
)
from app.core.error_handlers import register_error_handlers
from app.core.logging import RequestIDMiddleware, setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """ASGI lifespan context manager managing startup and shutdown lifecycles."""
    settings: Settings = getattr(app.state, "settings", None) or get_settings()
    logger.info("Initializing %s application runtime (v%s)...", settings.PROJECT_NAME, settings.VERSION)

    worker: Optional[Any] = None
    try:
        # 1. Startup: Verify database connectivity
        is_connected = check_db_connectivity()
        app.state.db_connected = is_connected

        if is_connected:
            logger.info("Database connectivity established successfully.")
        else:
            logger.warning(
                "Database connectivity check failed during startup. "
                "Application started in degraded state; readiness probes will fail closed."
            )
            if getattr(app.state, "raise_on_startup_db_error", False):
                raise RuntimeError("Database connectivity check failed during application startup.")

        # 2. Startup: Outbox background worker (if enabled in settings or app state)
        if settings.OUTBOX_WORKER_ENABLED or getattr(app.state, "outbox_worker_enabled", False):
            from app.workers.outbox_worker import OutboxWorker
            worker = getattr(app.state, "outbox_worker", None)
            if worker is None:
                worker = OutboxWorker(
                    batch_size=settings.OUTBOX_BATCH_SIZE,
                    poll_interval=settings.OUTBOX_POLL_INTERVAL_SECONDS,
                    base_backoff_seconds=settings.OUTBOX_BASE_BACKOFF_SECONDS,
                    max_retries=settings.OUTBOX_MAX_RETRIES,
                    stale_threshold_seconds=settings.OUTBOX_STALE_THRESHOLD_SECONDS,
                )
                app.state.outbox_worker = worker
            await worker.start()
            logger.info("OutboxWorker background task started via lifespan.")

        yield
    finally:
        # 3. Shutdown: Stop outbox worker if running
        active_worker = getattr(app.state, "outbox_worker", None) or worker
        if active_worker is not None:
            logger.info("Stopping OutboxWorker background task...")
            await active_worker.stop()
            logger.info("OutboxWorker background task stopped.")

        # 4. Shutdown: Clean up database resources deterministically
        logger.info("Shutting down %s application and disposing database connection pools...", settings.PROJECT_NAME)
        dispose_engine()
        await dispose_async_engine()


def create_app(settings: Optional[Settings] = None, **kwargs: Any) -> FastAPI:
    """FastAPI application factory.

    Args:
        settings: Optional custom Settings instance. Defaults to centralized get_settings().
        **kwargs: Additional state parameters (e.g. raise_on_startup_db_error).

    Returns:
        Configured FastAPI application instance.
    """
    app_settings = settings or get_settings()

    # -------------------------------------------------------------------------
    # Structured JSON Logging Configuration [18-SECURITY-ARCHITECTURE.md, TASK005]
    # -------------------------------------------------------------------------
    setup_logging(settings=app_settings)

    app = FastAPI(
        title=app_settings.PROJECT_NAME,
        version=app_settings.VERSION,
        description=app_settings.DESCRIPTION,
        debug=app_settings.DEBUG,
        docs_url=f"{app_settings.API_V1_STR}/docs" if app_settings.DEBUG else None,
        redoc_url=f"{app_settings.API_V1_STR}/redoc" if app_settings.DEBUG else None,
        openapi_url=f"{app_settings.API_V1_STR}/openapi.json" if app_settings.DEBUG else None,
        lifespan=lifespan,
    )

    # Store settings and additional state on app.state
    app.state.settings = app_settings
    for key, val in kwargs.items():
        setattr(app.state, key, val)

    # -------------------------------------------------------------------------
    # Request ID Correlation Middleware [06-API-ARCHITECTURE.md, TASK005]
    # -------------------------------------------------------------------------
    app.add_middleware(RequestIDMiddleware)

    # -------------------------------------------------------------------------
    # CORS Middleware Integration [ADR-002, 18-SECURITY-ARCHITECTURE.md]
    # -------------------------------------------------------------------------
    origins = (
        list(app_settings.CORS_ORIGINS)
        if (isinstance(app_settings.CORS_ORIGINS, list) and app_settings.CORS_ORIGINS)
        else [app_settings.FRONTEND_URL]
    )

    cors_kwargs: dict[str, Any] = {
        "allow_origins": origins,
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": [
            "Content-Type",
            "Idempotency-Key",
            "X-Requested-With",
            "Authorization",
            "Accept",
            "Origin",
            "X-Request-ID",
        ],
        "expose_headers": ["X-Request-ID"],
        "max_age": 3600,
    }

    # In non-production environments, allow private LAN IP addresses and local dev ports
    # when development/localhost origins are configured.
    if not app_settings.is_production:
        has_localhost = any("localhost" in o or "127.0.0.1" in o for o in origins)
        if has_localhost:
            cors_kwargs["allow_origin_regex"] = (
                r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?$"
            )
            cors_kwargs["allow_private_network"] = True

    app.add_middleware(
        CORSMiddleware,
        **cors_kwargs,
    )

    # -------------------------------------------------------------------------
    # Shallow Liveness Probe (GET /healthz)
    # Process liveness check: does NOT execute database query or depend on PostgreSQL.
    # -------------------------------------------------------------------------
    @app.get(
        "/healthz",
        tags=["Health"],
        summary="Shallow liveness probe",
        response_model=dict[str, str],
        status_code=status.HTTP_200_OK,
    )
    async def liveness_probe() -> dict[str, str]:
        """Process liveness probe confirming the ASGI runtime is responsive."""
        return {"status": "ok"}

    # -------------------------------------------------------------------------
    # API Version 1 Router & Deep Readiness Probes
    # -------------------------------------------------------------------------
    api_v1_router = APIRouter(prefix=app_settings.API_V1_STR)

    @api_v1_router.get(
        "/health",
        tags=["Health"],
        summary="Deep readiness probe",
        responses={
            status.HTTP_200_OK: {"description": "All required dependencies healthy"},
            status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Required dependencies unavailable"},
        },
    )
    async def readiness_probe():
        """Deep readiness probe verifying database connectivity."""
        if check_db_connectivity():
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "ready",
                    "dependencies": {
                        "database": "connected",
                    },
                },
            )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "dependencies": {
                    "database": "disconnected",
                },
            },
        )

    # Aliases for deployment orchestration standards (Kubernetes / Docker)
    @api_v1_router.get("/health/live", tags=["Health"], include_in_schema=False)
    async def readiness_liveness_alias():
        return {"status": "live"}

    @api_v1_router.get("/health/ready", tags=["Health"], include_in_schema=False)
    async def readiness_alias():
        return await readiness_probe()

    # Authentication & Session Management Router [06-API-ARCHITECTURE.md, TASK104-TASK106]
    from app.api.v1.auth import router as auth_router
    api_v1_router.include_router(auth_router)

    # User Management & Staff Onboarding Router [06-API-ARCHITECTURE.md, TASK203-TASK204]
    from app.api.v1.users import router as users_router
    api_v1_router.include_router(users_router)

    # In-App Notification Feed Router [06-API-ARCHITECTURE.md, TASK205]
    from app.api.v1.notifications import router as notifications_router
    api_v1_router.include_router(notifications_router)

    # Super Admin Immutable Audit Trail Router [06-API-ARCHITECTURE.md, TASK206]
    from app.api.v1.audit import router as audit_router
    api_v1_router.include_router(audit_router)

    # Super Admin Control Dashboard & Analytics Router [SA-01]
    from app.api.v1.control import router as control_router
    api_v1_router.include_router(control_router)

    # Course Catalog, Revision Control & Publishing Router [06-API-ARCHITECTURE.md, TASK301-TASK305]
    from app.api.v1.courses import router as courses_router
    api_v1_router.include_router(courses_router)

    # Curriculum Sections Router [06-API-ARCHITECTURE.md, TASK303]
    from app.api.v1.sections import router as sections_router
    api_v1_router.include_router(sections_router)

    # Curriculum Lessons Router [06-API-ARCHITECTURE.md, TASK303]
    from app.api.v1.lessons import router as lessons_router
    api_v1_router.include_router(lessons_router)

    # Media Storage & Video Protection Router [06-API-ARCHITECTURE.md, TASK401-TASK404]
    from app.api.v1.media import router as media_router
    api_v1_router.include_router(media_router)

    # Commerce, Orders & Checkout Router [06-API-ARCHITECTURE.md, TASK501-TASK504]
    from app.api.v1.orders import router as orders_router
    api_v1_router.include_router(orders_router)

    # Payment Gateway Webhooks Router [06-API-ARCHITECTURE.md, TASK503]
    from app.api.v1.webhooks import router as webhooks_router
    api_v1_router.include_router(webhooks_router)

    # Student Enrollment & Access Control Router [06-API-ARCHITECTURE.md, TASK601-TASK604]
    from app.api.v1.enrollments import router as enrollments_router
    api_v1_router.include_router(enrollments_router)

    # Assignments & Rubric Grading Router [06-API-ARCHITECTURE.md, TASK701-TASK704]
    from app.api.v1.assignments import router as assignments_router
    api_v1_router.include_router(assignments_router)

    # Quizzes & Question Banks Router [06-API-ARCHITECTURE.md, TASK801-TASK805]
    from app.api.v1.quizzes import router as quizzes_router
    api_v1_router.include_router(quizzes_router)

    # Student Progress & Completion Tracking Router [06-API-ARCHITECTURE.md, TASK901-TASK902]
    from app.api.v1.progress import router as progress_router
    api_v1_router.include_router(progress_router)

    # Certificates & Public Verification Router [06-API-ARCHITECTURE.md, TASK903-TASK904]
    from app.api.v1.certificates import router as certificates_router
    api_v1_router.include_router(certificates_router)

    # -------------------------------------------------------------------------
    # Centralized Error Envelope Handlers [06-API-ARCHITECTURE.md, TASK006]
    # -------------------------------------------------------------------------
    register_error_handlers(app)

    app.include_router(api_v1_router)

    return app


# Default ASGI application instance for production Uvicorn runner
app = create_app()
