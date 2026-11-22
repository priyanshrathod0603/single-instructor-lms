"""Comprehensive unit tests for Pydantic Settings and Environment Configuration (TASK001).

Tests both direct instantiation and real environment loading via EnvSettingsSource.
"""

import pytest
from pydantic import SecretStr, ValidationError
from app.core.config import Settings, get_settings


class TestSettingsDefaults:
    """Tests default configuration initialization and metadata."""

    def test_default_settings_initialization(self):
        """Verifies safe default settings for development environment."""
        settings = Settings()

        assert settings.PROJECT_NAME == "Single-Instructor LMS"
        assert settings.VERSION == "2.0.0"
        assert settings.API_V1_STR == "/api/v1"
        assert settings.ENVIRONMENT == "development"
        assert settings.DEBUG is True
        assert settings.is_production is False
        assert settings.is_testing is False
        assert settings.SESSION_COOKIE_NAME == "__Host-lms_session"
        assert settings.SESSION_COOKIE_SECURE is True
        assert settings.SESSION_COOKIE_HTTPONLY is True
        assert settings.SESSION_COOKIE_SAMESITE == "lax"
        assert settings.DB_POOL_SIZE == 20
        assert settings.DB_MAX_OVERFLOW == 10
        assert settings.DB_POOL_PRE_PING is True


class TestRealEnvironmentVariableLoading:
    """Tests loading from real environment variables via EnvSettingsSource (monkeypatch.setenv)."""

    def test_env_var_general_overrides(self, monkeypatch):
        """Verifies that scalar environment variables override defaults with correct type coercion."""
        monkeypatch.setenv("PROJECT_NAME", "Expert Architecture Academy")
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.setenv("DEBUG", "false")
        monkeypatch.setenv("DB_POOL_SIZE", "45")
        monkeypatch.setenv("DB_MAX_OVERFLOW", "15")
        monkeypatch.setenv("FRONTEND_URL", "https://staging.instructor.com")

        settings = Settings()

        assert settings.PROJECT_NAME == "Expert Architecture Academy"
        assert settings.ENVIRONMENT == "staging"
        assert settings.DEBUG is False
        assert settings.DB_POOL_SIZE == 45
        assert settings.DB_MAX_OVERFLOW == 15
        assert settings.FRONTEND_URL == "https://staging.instructor.com"

    def test_cors_origins_env_comma_separated(self, monkeypatch):
        """Exercises EnvSettingsSource with standard comma-separated CORS_ORIGINS."""
        monkeypatch.setenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000, https://staging.instructor.com",
        )

        settings = Settings()

        assert isinstance(settings.CORS_ORIGINS, list)
        assert settings.CORS_ORIGINS == [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://staging.instructor.com",
        ]

    def test_cors_origins_env_json_array(self, monkeypatch):
        """Exercises EnvSettingsSource with valid JSON array CORS_ORIGINS."""
        monkeypatch.setenv(
            "CORS_ORIGINS",
            '["https://app.instructor.com", "https://learn.instructor.com"]',
        )

        settings = Settings()

        assert isinstance(settings.CORS_ORIGINS, list)
        assert settings.CORS_ORIGINS == [
            "https://app.instructor.com",
            "https://learn.instructor.com",
        ]

    def test_cors_origins_env_empty_string(self, monkeypatch):
        """Exercises EnvSettingsSource with empty string CORS_ORIGINS."""
        monkeypatch.setenv("CORS_ORIGINS", "")

        settings = Settings()

        assert isinstance(settings.CORS_ORIGINS, list)
        assert settings.CORS_ORIGINS == []

    def test_cors_origins_env_whitespace_string(self, monkeypatch):
        """Exercises EnvSettingsSource with whitespace-only CORS_ORIGINS."""
        monkeypatch.setenv("CORS_ORIGINS", "   ")

        settings = Settings()

        assert isinstance(settings.CORS_ORIGINS, list)
        assert settings.CORS_ORIGINS == []

    def test_cors_origins_env_single_origin(self, monkeypatch):
        """Exercises EnvSettingsSource with a single unbracketed origin string."""
        monkeypatch.setenv("CORS_ORIGINS", "https://learn.instructor.com")

        settings = Settings()

        assert isinstance(settings.CORS_ORIGINS, list)
        assert settings.CORS_ORIGINS == ["https://learn.instructor.com"]

    def test_cors_origins_env_invalid_json_rejected(self, monkeypatch):
        """Exercises EnvSettingsSource with malformed JSON array; must raise ValidationError."""
        monkeypatch.setenv("CORS_ORIGINS", "[broken-json-array")

        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "Invalid JSON string for CORS_ORIGINS" in str(exc_info.value)


class TestSecretHandling:
    """Tests cryptographic key protection, SecretStr masking, and retrieval."""

    def test_secret_str_masking_in_repr_and_str(self):
        """Verifies that sensitive credentials are never exposed in string representations."""
        raw_secret = "my-super-secret-cryptographic-signing-key-at-least-32"
        settings = Settings(SECRET_KEY=SecretStr(raw_secret))

        # String representation and repr must mask the secret
        assert raw_secret not in str(settings.SECRET_KEY)
        assert raw_secret not in repr(settings.SECRET_KEY)
        assert "**********" in repr(settings.SECRET_KEY)
        assert raw_secret not in repr(settings)

        # Raw secret is only accessible via get_secret_value()
        assert settings.SECRET_KEY.get_secret_value() == raw_secret

    def test_optional_third_party_secrets_default_none(self):
        """Verifies that optional vendor secrets default to None without crashing."""
        settings = Settings(_env_file=None)
        assert settings.RAZORPAY_KEY_SECRET is None
        assert settings.RAZORPAY_WEBHOOK_SECRET is None
        assert settings.GOOGLE_CLIENT_SECRET is None
        assert settings.STORAGE_SECRET_ACCESS_KEY is None
        assert settings.EMAIL_API_KEY is None

    def test_secret_str_loaded_from_env(self, monkeypatch):
        """Verifies that secrets loaded via environment variables are wrapped as SecretStr."""
        raw_key = "razorpay_webhook_secret_key_12345"
        monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", raw_key)

        settings = Settings()

        assert isinstance(settings.RAZORPAY_WEBHOOK_SECRET, SecretStr)
        assert raw_key not in repr(settings.RAZORPAY_WEBHOOK_SECRET)
        assert settings.RAZORPAY_WEBHOOK_SECRET.get_secret_value() == raw_key


class TestProductionSecurityGuards:
    """Tests enforcement of mandatory production security invariants."""

    def test_production_rejects_debug_true(self):
        """Production environment must strictly reject DEBUG=True."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                ENVIRONMENT="production",
                DEBUG=True,
                SECRET_KEY=SecretStr("valid-production-secret-key-with-64-characters-for-testing-prod-01"),
                DATABASE_URL="postgresql+psycopg://prod_user:p@prod-db.internal:5432/lms_prod",
            )
        assert "DEBUG mode must be False in production" in str(exc_info.value)

    def test_production_rejects_short_secret(self):
        """Production environment must reject secrets under 32 characters."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY=SecretStr("too-short-secret"),
                DATABASE_URL="postgresql+psycopg://prod_user:p@prod-db.internal:5432/lms_prod",
            )
        assert "SECRET_KEY must be at least 32 characters long" in str(exc_info.value)

    def test_production_rejects_insecure_default_secret(self):
        """Production environment must reject default dev secrets."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY=SecretStr("insecure-dev-secret-key-32-bytes-minimum-length-for-lms-jwt"),
                DATABASE_URL="postgresql+psycopg://prod_user:p@prod-db.internal:5432/lms_prod",
            )
        assert "Default or insecure SECRET_KEY cannot be used in production" in str(exc_info.value)

    def test_production_rejects_insecure_cookies(self):
        """Production environment must require HTTPS-only session cookies."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY=SecretStr("a" * 40),
                SESSION_COOKIE_SECURE=False,
                DATABASE_URL="postgresql+psycopg://prod_user:p@prod-db.internal:5432/lms_prod",
            )
        assert "SESSION_COOKIE_SECURE must be True in production" in str(exc_info.value)

    def test_production_rejects_missing_host_prefix(self):
        """Production environment must enforce the __Host- prefix on session cookies."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY=SecretStr("a" * 40),
                SESSION_COOKIE_NAME="regular_session",
                DATABASE_URL="postgresql+psycopg://prod_user:p@prod-db.internal:5432/lms_prod",
            )
        assert "SESSION_COOKIE_NAME must use the __Host- prefix" in str(exc_info.value)

    def test_production_rejects_cors_wildcard(self):
        """Production environment must strictly reject wildcard '*' CORS origin."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY=SecretStr("a" * 40),
                CORS_ORIGINS=["*"],
                DATABASE_URL="postgresql+psycopg://prod_user:p@prod-db.internal:5432/lms_prod",
            )
        assert "Wildcard '*' in CORS_ORIGINS is strictly prohibited in production" in str(exc_info.value)

    def test_production_rejects_insecure_http_cors(self):
        """Production environment must reject plaintext HTTP origins in CORS."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY=SecretStr("a" * 40),
                CORS_ORIGINS=["http://insecure.instructor.com"],
                DATABASE_URL="postgresql+psycopg://prod_user:p@prod-db.internal:5432/lms_prod",
            )
        assert "Insecure HTTP origin" in str(exc_info.value)

    def test_production_rejects_default_dev_database_url(self):
        """Production environment must reject the default development DATABASE_URL."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY=SecretStr("a" * 40),
                DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/lms_db",
                CORS_ORIGINS=["https://learn.instructor.com"],
            )
        assert "Default development DATABASE_URL cannot be used in production" in str(exc_info.value)

    def test_valid_production_configuration(self):
        """Valid production configuration initializes without error."""
        prod_settings = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            SECRET_KEY=SecretStr("68f9a2b8e4c7d1e0f3b5a6c9d8e7f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8"),
            CORS_ORIGINS=["https://learn.instructor.com", "https://instructor.com"],
            DATABASE_URL="postgresql+psycopg://lms_prod_user:prod_password@aws-rds-cluster.internal:5432/lms_prod",
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_NAME="__Host-lms_session",
            RAZORPAY_KEY_ID="rzp_live_production123",
            RAZORPAY_KEY_SECRET=SecretStr("prod_secret_key_long_enough_123"),
            RAZORPAY_WEBHOOK_SECRET=SecretStr("prod_webhook_secret_valid_123"),
        )
        assert prod_settings.is_production is True
        assert prod_settings.DEBUG is False


class TestSettingsCaching:
    """Tests the lru_cache behavior and test isolation of get_settings()."""

    def test_get_settings_singleton(self):
        """get_settings returns identical cached instance."""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_get_settings_cache_clear(self, monkeypatch):
        """Clearing cache reloads settings from environment."""
        s1 = get_settings()
        monkeypatch.setenv("PROJECT_NAME", "Brand New Academy")
        get_settings.cache_clear()
        s2 = get_settings()
        assert s2.PROJECT_NAME == "Brand New Academy"
        assert s1 is not s2
