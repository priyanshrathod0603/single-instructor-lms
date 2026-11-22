"""Unit tests for FastAPI application factory, ASGI lifespan, CORS, and health endpoints.

Verifies:
1. Application factory (create_app): metadata, route registration, custom settings.
2. Shallow liveness probe (GET /healthz): fast 200, no database queries, succeeds when DB is down.
3. Deep readiness probe (GET /api/v1/health): verifies DB connectivity, returns 200 or 503, never leaks credentials.
4. ASGI lifespan: startup database verification, shutdown engine disposal, and cleanup on failure.
5. CORS middleware: allowed origins, credentials, preflight OPTIONS, and rejection of unauthorized origins.
"""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI, status
from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings, get_settings
from app.main import app, create_app


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def client():
    """Create a test client against the default application instance."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def custom_settings():
    """Create isolated custom settings for testing."""
    return Settings(
        PROJECT_NAME="Custom LMS Brand",
        VERSION="3.0.0-beta",
        DESCRIPTION="Custom Brand API",
        API_V1_STR="/api/v1",
        DEBUG=True,
        FRONTEND_URL="https://custom.instructor.com",
        CORS_ORIGINS=["https://custom.instructor.com"],
        DATABASE_URL="sqlite:///:memory:",
    )


# -----------------------------------------------------------------------------
# 1. Application Factory Tests
# -----------------------------------------------------------------------------
class TestApplicationFactory:
    """Verifies that create_app configures metadata, routes, and settings correctly."""

    def test_default_application_creation(self):
        """create_app must return a configured FastAPI application instance."""
        test_app = create_app()
        assert isinstance(test_app, FastAPI)
        assert test_app.state.settings is not None

    def test_application_metadata_matches_settings(self):
        """Application metadata must reflect settings values."""
        settings = get_settings()
        test_app = create_app()

        assert test_app.title == settings.PROJECT_NAME
        assert test_app.version == settings.VERSION
        assert test_app.description == settings.DESCRIPTION
        assert test_app.debug == settings.DEBUG

    def test_custom_settings_injection(self, custom_settings):
        """Application factory must accept custom settings."""
        test_app = create_app(settings=custom_settings)

        assert test_app.title == "Custom LMS Brand"
        assert test_app.version == "3.0.0-beta"
        assert test_app.description == "Custom Brand API"
        assert test_app.state.settings.FRONTEND_URL == "https://custom.instructor.com"

    def test_route_registration(self, monkeypatch):
        """Application must register healthz and /api/v1 routes."""
        test_app = create_app()
        openapi_paths = test_app.openapi()["paths"]

        assert "/healthz" in openapi_paths
        assert "/api/v1/health" in openapi_paths

        # Verify client can reach all routes including aliases
        monkeypatch.setattr("app.main.check_db_connectivity", lambda: True)
        with TestClient(test_app) as client:
            assert client.get("/healthz").status_code == 200
            assert client.get("/api/v1/health").status_code == 200
            assert client.get("/api/v1/health/live").status_code == 200
            assert client.get("/api/v1/health/ready").status_code == 200

    def test_documentation_endpoints_disabled_in_production(self):
        """In production mode (DEBUG=False), docs, redoc, and openapi.json must return 404."""
        prod_settings = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            SECRET_KEY="a" * 32,
            FRONTEND_URL="https://learn.example.com",
            CORS_ORIGINS=["https://learn.example.com"],
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/lms_prod",
            RAZORPAY_KEY_ID="rzp_live_production123",
            RAZORPAY_KEY_SECRET="prod_secret_key_long_enough_123",
            RAZORPAY_WEBHOOK_SECRET="prod_webhook_secret_valid_123",
        )
        prod_app = create_app(settings=prod_settings)
        with TestClient(prod_app) as prod_client:
            # Root docs endpoints
            assert prod_client.get("/docs").status_code == 404
            assert prod_client.get("/redoc").status_code == 404
            assert prod_client.get("/openapi.json").status_code == 404
            # API v1 docs endpoints
            assert prod_client.get("/api/v1/docs").status_code == 404
            assert prod_client.get("/api/v1/redoc").status_code == 404
            assert prod_client.get("/api/v1/openapi.json").status_code == 404


# -----------------------------------------------------------------------------
# 2. Liveness Probe Tests
# -----------------------------------------------------------------------------
class TestLivenessProbe:
    """Verifies shallow liveness probe (GET /healthz)."""

    def test_healthz_successful_response(self, client):
        """GET /healthz must return HTTP 200 with status ok."""
        response = client.get("/healthz")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}

    def test_health_live_alias(self, client):
        """GET /api/v1/health/live must return HTTP 200 with status live."""
        response = client.get("/api/v1/health/live")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "live"}

    def test_liveness_does_not_execute_database_query(self, client, monkeypatch):
        """Liveness check must be shallow and never query the database."""
        mock_check_db = MagicMock()
        monkeypatch.setattr("app.main.check_db_connectivity", mock_check_db)

        response = client.get("/healthz")

        assert response.status_code == status.HTTP_200_OK
        mock_check_db.assert_not_called()

    def test_liveness_succeeds_even_when_database_is_down(self, client, monkeypatch):
        """Liveness probe must succeed even when database connectivity is unavailable."""
        monkeypatch.setattr("app.main.check_db_connectivity", lambda: False)

        response = client.get("/healthz")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}


# -----------------------------------------------------------------------------
# 3. Readiness Probe Tests
# -----------------------------------------------------------------------------
class TestReadinessProbe:
    """Verifies deep readiness probe (GET /api/v1/health)."""

    def test_readiness_success_when_database_connected(self, client, monkeypatch):
        """When database ping succeeds, readiness probe must return HTTP 200 ready."""
        monkeypatch.setattr("app.main.check_db_connectivity", lambda: True)

        response = client.get("/api/v1/health")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ready"
        assert data["dependencies"]["database"] == "connected"

    def test_readiness_failure_when_database_unreachable(self, client, monkeypatch):
        """When database ping fails, readiness probe must return HTTP 503 not_ready."""
        monkeypatch.setattr("app.main.check_db_connectivity", lambda: False)

        response = client.get("/api/v1/health")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["dependencies"]["database"] == "disconnected"

    def test_readiness_alias_route(self, client, monkeypatch):
        """GET /api/v1/health/ready must behave identically to /api/v1/health."""
        monkeypatch.setattr("app.main.check_db_connectivity", lambda: True)

        response = client.get("/api/v1/health/ready")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "ready"

    def test_readiness_response_never_leaks_sensitive_information(self, client, monkeypatch):
        """Readiness responses must never leak connection strings, passwords, or error traces."""
        # Simulate connection error
        monkeypatch.setattr("app.main.check_db_connectivity", lambda: False)

        response = client.get("/api/v1/health")
        raw_text = response.text.lower()

        # Sensitive keywords that must NEVER appear in the response payload
        prohibited_words = [
            "password",
            "postgres",
            "secret",
            "token",
            "5432",
            "psycopg",
            "select",
            "traceback",
            "exception",
            "localhost",
        ]
        for word in prohibited_words:
            assert word not in raw_text, f"Readiness response leaked sensitive token: {word}"


# -----------------------------------------------------------------------------
# 4. ASGI Lifespan Management Tests
# -----------------------------------------------------------------------------
class TestASGILifespanLifecycle:
    """Verifies startup database verification, shutdown disposal, and error handling."""

    def test_lifespan_startup_success(self, monkeypatch):
        """Lifespan startup must verify connectivity and record state."""
        mock_check = MagicMock(return_value=True)
        monkeypatch.setattr("app.main.check_db_connectivity", mock_check)

        test_app = create_app()
        with TestClient(test_app):
            assert test_app.state.db_connected is True
            mock_check.assert_called_once()

    def test_lifespan_startup_degraded_state(self, monkeypatch):
        """Lifespan startup must record degraded status when database is unreachable."""
        monkeypatch.setattr("app.main.check_db_connectivity", lambda: False)

        test_app = create_app()
        with TestClient(test_app):
            assert test_app.state.db_connected is False

    def test_lifespan_startup_failure_handling(self, monkeypatch):
        """When raise_on_startup_db_error is True and DB fails, startup must raise RuntimeError."""
        monkeypatch.setattr("app.main.check_db_connectivity", lambda: False)

        test_app = create_app(raise_on_startup_db_error=True)
        with pytest.raises(RuntimeError, match="Database connectivity check failed"):
            with TestClient(test_app):
                pass

    def test_lifespan_shutdown_disposes_resources(self, monkeypatch):
        """Lifespan shutdown must dispose sync and async database engines."""
        mock_dispose_sync = MagicMock()
        mock_dispose_async = MagicMock()

        # Async mock for dispose_async_engine
        async def fake_dispose_async():
            mock_dispose_async()

        monkeypatch.setattr("app.main.check_db_connectivity", lambda: True)
        monkeypatch.setattr("app.main.dispose_engine", mock_dispose_sync)
        monkeypatch.setattr("app.main.dispose_async_engine", fake_dispose_async)

        test_app = create_app()
        with TestClient(test_app):
            pass  # Normal lifespan execution

        mock_dispose_sync.assert_called_once()
        mock_dispose_async.assert_called_once()

    def test_lifespan_shutdown_disposes_resources_even_on_startup_failure(self, monkeypatch):
        """Even if lifespan startup raises an exception, shutdown disposal must still execute."""
        mock_dispose_sync = MagicMock()
        mock_dispose_async = MagicMock()

        async def fake_dispose_async():
            mock_dispose_async()

        monkeypatch.setattr("app.main.check_db_connectivity", lambda: False)
        monkeypatch.setattr("app.main.dispose_engine", mock_dispose_sync)
        monkeypatch.setattr("app.main.dispose_async_engine", fake_dispose_async)

        test_app = create_app(raise_on_startup_db_error=True)
        with pytest.raises(RuntimeError):
            with TestClient(test_app):
                pass

        mock_dispose_sync.assert_called_once()
        mock_dispose_async.assert_called_once()


# -----------------------------------------------------------------------------
# 5. CORS Integration Tests
# -----------------------------------------------------------------------------
class TestCORSIntegration:
    """Verifies Cross-Origin Resource Sharing policy enforcement."""

    def test_cors_allowed_origin(self, client):
        """Requests from allowed CORS origins must include CORS approval headers."""
        headers = {
            "Origin": "http://localhost:3000",
        }
        response = client.get("/healthz", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_cors_lan_origin_allowed_in_development(self, client):
        """In development with default settings, LAN origins like http://192.168.1.103:3000 are approved."""
        headers = {
            "Origin": "http://192.168.1.103:3000",
        }
        response = client.get("/healthz", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.headers.get("access-control-allow-origin") == "http://192.168.1.103:3000"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_cors_preflight_options_request(self, client):
        """OPTIONS preflight requests from allowed origins must return allowed methods."""
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type,Authorization",
        }
        response = client.options("/api/v1/health", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
        allowed_methods = response.headers.get("access-control-allow-methods", "")
        assert "GET" in allowed_methods
        assert "OPTIONS" in allowed_methods

    def test_cors_disallowed_origin_rejected(self, client):
        """Requests from unauthorized origins must not receive allow-origin header."""
        headers = {
            "Origin": "http://unauthorized-attacker.com",
        }
        response = client.get("/healthz", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        # Disallowed origin must not receive Access-Control-Allow-Origin matching its origin
        assert response.headers.get("access-control-allow-origin") != "http://unauthorized-attacker.com"

    def test_cors_custom_settings_origins(self, custom_settings):
        """CORS must respect custom origins configured in Settings."""
        test_app = create_app(settings=custom_settings)
        with TestClient(test_app) as custom_client:
            # Custom allowed origin
            res1 = custom_client.get("/healthz", headers={"Origin": "https://custom.instructor.com"})
            assert res1.headers.get("access-control-allow-origin") == "https://custom.instructor.com"

            # Old localhost origin is disallowed in this custom configuration
            res2 = custom_client.get("/healthz", headers={"Origin": "http://localhost:3000"})
            assert res2.headers.get("access-control-allow-origin") != "http://localhost:3000"

    def test_cors_fallback_to_frontend_url_when_cors_origins_empty(self):
        """When CORS_ORIGINS is an empty list, CORS must fall back to FRONTEND_URL."""
        fallback_settings = Settings(
            FRONTEND_URL="http://frontend-fallback.test",
            CORS_ORIGINS=[],
        )
        test_app = create_app(settings=fallback_settings)
        with TestClient(test_app) as fallback_client:
            res = fallback_client.get(
                "/healthz", headers={"Origin": "http://frontend-fallback.test"}
            )
            assert res.status_code == 200
            assert res.headers.get("access-control-allow-origin") == "http://frontend-fallback.test"
