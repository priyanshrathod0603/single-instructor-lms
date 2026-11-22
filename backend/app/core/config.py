"""Centralized application configuration and environment settings management.

Built with Python 3.14, Pydantic v2, and Pydantic Settings.
Enforces strict validation, production security guards, and credential masking.
"""

from functools import lru_cache
import json
from typing import Any, Literal, Optional
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file.
    
    Adheres strictly to the 12-factor application configuration principles.
    Sensitive credentials are typed as SecretStr to prevent accidental exposure
    in logs, tracebacks, or API serialization.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # 1. Application Metadata & Environment Mode
    # -------------------------------------------------------------------------
    PROJECT_NAME: str = Field(
        default="Single-Instructor LMS",
        description="Public brand and application name.",
    )
    VERSION: str = Field(
        default="2.0.0",
        description="Application semver version string.",
    )
    DESCRIPTION: str = Field(
        default="Proprietary direct-to-student educational application engine",
        description="Application description for OpenAPI documentation.",
    )
    API_V1_STR: str = Field(
        default="/api/v1",
        description="URL prefix for all version 1 REST API endpoints.",
    )
    ENVIRONMENT: Literal["development", "staging", "production", "testing"] = Field(
        default="development",
        description="Current runtime lifecycle stage.",
    )
    DEBUG: bool = Field(
        default=True,
        description="Debug mode toggle. Must be strictly False in production.",
    )

    # -------------------------------------------------------------------------
    # 2. Cryptography & Authentication Settings
    # -------------------------------------------------------------------------
    SECRET_KEY: SecretStr = Field(
        default=SecretStr("insecure-dev-secret-key-32-bytes-minimum-length-for-lms-jwt"),
        description="Master cryptographic key used for JWT signing and session integrity.",
    )
    ALGORITHM: str = Field(
        default="HS256",
        description="Cryptographic algorithm for signing short-lived tokens.",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=60 * 24 * 7,  # 7 days
        description="Lifespan of access tokens in minutes.",
    )
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = Field(
        default=60,  # 1 hour
        description="Lifespan of password reset tokens in minutes.",
    )
    EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = Field(
        default=60 * 24,  # 24 hours
        description="Lifespan of email verification tokens in minutes.",
    )

    # -------------------------------------------------------------------------
    # 3. Single-Active-Session & Cookie Security [ADR-002]
    # -------------------------------------------------------------------------
    SESSION_COOKIE_NAME: str = Field(
        default="__Host-lms_session",
        description="Cookie name for authenticated session tokens. Uses __Host- prefix in production.",
    )
    SESSION_COOKIE_SECURE: bool = Field(
        default=True,
        description="Enforces HTTPS-only transmission. Must be True in production.",
    )
    SESSION_COOKIE_HTTPONLY: bool = Field(
        default=True,
        description="Blocks client-side JavaScript access to prevent XSS session hijacking.",
    )
    SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = Field(
        default="lax",
        description="CSRF mitigation attribute for session cookies.",
    )
    SESSION_COOKIE_PATH: str = Field(
        default="/",
        description="Cookie scope path. Required by __Host- prefix specification.",
    )
    SESSION_MAX_AGE_SECONDS: int = Field(
        default=604800,  # 7 days
        description="Absolute maximum lifespan of an active session in seconds.",
    )
    SESSION_IDLE_TIMEOUT_SECONDS: int = Field(
        default=172800,  # 48 hours
        description="Maximum idle duration before an inactive session expires.",
    )

    # -------------------------------------------------------------------------
    # 4. CORS & Presentation Layer Settings
    # -------------------------------------------------------------------------
    FRONTEND_URL: str = Field(
        default="http://localhost:3000",
        description="Primary client application origin.",
    )
    BACKEND_URL: Optional[str] = Field(
        default=None,
        description="Public backend host URL for absolute callback and verification endpoints.",
    )
    CORS_ORIGINS: list[str] | str = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed origins for Cross-Origin Resource Sharing. Accepts comma-separated string, JSON array, or list.",
    )
    TRUSTED_PROXIES: str = Field(
        default="127.0.0.1,::1,testclient,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
        description="Comma-separated list of trusted proxy IPs or CIDR networks allowed to forward client IPs.",
    )

    # -------------------------------------------------------------------------
    # 5. Database Connection & Pooling [ADR-002, ADR-005]
    # -------------------------------------------------------------------------
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/lms_db",
        description="PostgreSQL connection string using psycopg driver.",
    )
    DB_POOL_SIZE: int = Field(
        default=20,
        description="Number of persistent database connections in the connection pool.",
    )
    DB_MAX_OVERFLOW: int = Field(
        default=10,
        description="Maximum number of connections that can be created beyond pool_size.",
    )
    DB_POOL_TIMEOUT: int = Field(
        default=30,
        description="Seconds to wait before raising an error if no connections are available.",
    )
    DB_POOL_PRE_PING: bool = Field(
        default=True,
        description="Enables liveness pre-ping before handing connections to workers.",
    )
    DB_ECHO: bool = Field(
        default=False,
        description="Enables verbose SQL logging. Useful for query debugging in development.",
    )

    # -------------------------------------------------------------------------
    # 6. Redis / Cache Settings
    # -------------------------------------------------------------------------
    REDIS_URL: Optional[str] = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for rate limiting, JWKS cache, and worker locks.",
    )

    # -------------------------------------------------------------------------
    # 7. Payment Gateway Settings (Razorpay) [ADR-004, ADR-005]
    # -------------------------------------------------------------------------
    RAZORPAY_KEY_ID: str = Field(
        default="",
        description="Public Razorpay API key identifier.",
    )
    RAZORPAY_KEY_SECRET: Optional[SecretStr] = Field(
        default=None,
        description="Private Razorpay API key secret.",
    )
    RAZORPAY_WEBHOOK_SECRET: Optional[SecretStr] = Field(
        default=None,
        description="Shared cryptographic secret for verifying incoming webhook signatures.",
    )

    # -------------------------------------------------------------------------
    # 8. Federated Identity (Google OAuth 2.0 / OIDC) [ADR-007]
    # -------------------------------------------------------------------------
    GOOGLE_CLIENT_ID: str = Field(
        default="",
        description="Google Identity OAuth 2.0 Client ID.",
    )
    GOOGLE_CLIENT_SECRET: Optional[SecretStr] = Field(
        default=None,
        description="Google Identity OAuth 2.0 Client Secret.",
    )

    # -------------------------------------------------------------------------
    # 9. Cloud Object Storage (Cloudflare R2 / AWS S3) [ADR-009]
    # -------------------------------------------------------------------------
    STORAGE_PROVIDER: Literal["s3", "r2", "local"] = Field(
        default="r2",
        description="Target object storage service provider.",
    )
    STORAGE_BUCKET_NAME: str = Field(
        default="lms-media",
        description="Bucket name for course videos, protected PDFs, and avatars.",
    )
    STORAGE_ENDPOINT_URL: Optional[str] = Field(
        default=None,
        description="Custom endpoint URL for S3-compatible providers like Cloudflare R2.",
    )
    STORAGE_ACCESS_KEY_ID: Optional[str] = Field(
        default=None,
        description="Object storage access key ID.",
    )
    STORAGE_SECRET_ACCESS_KEY: Optional[SecretStr] = Field(
        default=None,
        description="Object storage secret access key.",
    )
    STORAGE_REGION: str = Field(
        default="auto",
        description="Storage bucket region.",
    )
    CDN_STREAM_BASE_URL: str = Field(
        default="https://stream.instructor.com",
        description="CDN base URL for HLS video streaming.",
    )
    PLAYBACK_TOKEN_EXPIRE_MINUTES: int = Field(
        default=120,
        description="Lifespan of video playback tokens in minutes (2 hours).",
    )
    UPLOAD_INTENT_EXPIRE_MINUTES: int = Field(
        default=15,
        description="Lifespan of presigned upload URLs in minutes (15 minutes).",
    )
    FFMPEG_PATH: Optional[str] = Field(
        default=None,
        description="Path to FFmpeg binary executable. Defaults to auto-detection from PATH.",
    )
    FFPROBE_PATH: Optional[str] = Field(
        default=None,
        description="Path to ffprobe binary executable. Defaults to auto-detection from PATH.",
    )
    TRANSCODE_TEMP_DIR: str = Field(
        default="/tmp/lms_transcode",
        description="Temporary disk directory for staging video transcoding operations.",
    )
    TRANSCODE_TIMEOUT_SECONDS: int = Field(
        default=600,
        description="Maximum seconds permitted for FFmpeg process before aborting.",
    )
    TRANSCODE_MAX_RETRIES: int = Field(
        default=3,
        description="Maximum retries permitted for failed transcode jobs.",
    )
    TRANSCODE_SEGMENT_DURATION_SECONDS: int = Field(
        default=6,
        description="Target HLS segment duration in seconds.",
    )
    TRANSCODE_CONCURRENCY: int = Field(
        default=2,
        description="Maximum concurrent video transcoding jobs per worker instance.",
    )

    # -------------------------------------------------------------------------
    # 10. Transactional Email & Outbox Delivery [ADR-012]
    # -------------------------------------------------------------------------
    EMAIL_PROVIDER: Literal["console", "resend", "sendgrid", "smtp"] = Field(
        default="console",
        description="Email delivery driver. Uses console output in local development.",
    )
    EMAIL_FROM: str = Field(
        default="noreply@instructor.com",
        description="Sender email address for system notifications.",
    )
    EMAIL_FROM_NAME: str = Field(
        default="Single-Instructor LMS",
        description="Sender display name.",
    )
    EMAIL_API_KEY: Optional[SecretStr] = Field(
        default=None,
        description="API key for transactional email provider (Resend/SendGrid).",
    )
    SMTP_HOST: str = Field(
        default="smtp.gmail.com",
        description="SMTP server hostname.",
    )
    SMTP_PORT: int = Field(
        default=587,
        ge=1,
        le=65535,
        description="SMTP server port (587 for STARTTLS).",
    )
    SMTP_USERNAME: Optional[str] = Field(
        default=None,
        description="SMTP username (e.g. Gmail address).",
    )
    SMTP_PASSWORD: Optional[SecretStr] = Field(
        default=None,
        description="SMTP password or Google App Password. Wrapped as SecretStr to prevent credential leakage.",
    )
    SMTP_USE_TLS: bool = Field(
        default=True,
        description="Whether to negotiate STARTTLS encryption on the SMTP connection.",
    )
    SMTP_TIMEOUT_SECONDS: int = Field(
        default=10,
        ge=1,
        le=120,
        description="Connection and read timeout in seconds for SMTP operations.",
    )

    # -------------------------------------------------------------------------
    # 11. Transactional Outbox Background Worker Settings [ADR-012]
    # -------------------------------------------------------------------------
    OUTBOX_WORKER_ENABLED: bool = Field(
        default=False,
        description="Toggle for background outbox worker in FastAPI lifespan. Defaults to False so tests and development CLI do not spawn unmanaged tasks.",
    )
    OUTBOX_POLL_INTERVAL_SECONDS: float = Field(
        default=5.0,
        description="Polling interval in seconds between outbox processing batches when queue is idle.",
    )
    OUTBOX_BATCH_SIZE: int = Field(
        default=50,
        description="Maximum number of outbox events to process in a single batch.",
    )
    OUTBOX_MAX_RETRIES: int = Field(
        default=5,
        description="Maximum delivery attempts before transitioning an event to FAILED.",
    )
    OUTBOX_BASE_BACKOFF_SECONDS: int = Field(
        default=30,
        description="Base multiplier for exponential backoff (base * 2^retry_count).",
    )
    OUTBOX_STALE_THRESHOLD_SECONDS: int = Field(
        default=300,
        description="Seconds after which an event stuck in PROCESSING is considered stale and recovered.",
    )

    # -------------------------------------------------------------------------
    # Validators & Production Guardrails
    # -------------------------------------------------------------------------
    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        """Parses and normalizes CORS origins from comma-separated string, JSON array, or list.
        
        Guarantees that the resulting attribute on Settings is always a sanitized list[str].
        Handles inputs from environment variables, .env files, or direct constructor arguments.
        """
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("[") or value.endswith("]"):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return [str(origin).strip() for origin in parsed if str(origin).strip()]
                    raise ValueError("CORS_ORIGINS JSON string must be an array of origin strings.")
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON string for CORS_ORIGINS: {exc}") from exc
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        elif isinstance(value, (list, tuple, set)):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        return []

    @model_validator(mode="after")
    def validate_production_guards(self) -> "Settings":
        """Enforces mandatory security invariants in production environments.
        
        Guarantees that:
        1. DEBUG is strictly False in production.
        2. SECRET_KEY is non-default, non-insecure, and has minimum 32 characters entropy.
        3. Session cookies are HTTPS-only (SESSION_COOKIE_SECURE = True).
        4. Session cookies use the __Host- prefix to protect against subdomain tampering.
        5. In production, CORS origins must not include wildcards or insecure origins.
        6. In production, default development DATABASE_URL is disallowed.
        """
        if self.ENVIRONMENT == "production":
            if self.DEBUG:
                raise ValueError("DEBUG mode must be False in production.")
            
            raw_secret = self.SECRET_KEY.get_secret_value()
            if len(raw_secret) < 32:
                raise ValueError(
                    "SECRET_KEY must be at least 32 characters long in production."
                )
            if "insecure" in raw_secret.lower() or "dev-secret" in raw_secret.lower():
                raise ValueError(
                    "Default or insecure SECRET_KEY cannot be used in production."
                )

            if not self.SESSION_COOKIE_SECURE:
                raise ValueError(
                    "SESSION_COOKIE_SECURE must be True in production to enforce HTTPS."
                )

            if not self.SESSION_COOKIE_NAME.startswith("__Host-"):
                raise ValueError(
                    "SESSION_COOKIE_NAME must use the __Host- prefix in production."
                )

            for origin in self.CORS_ORIGINS:
                if origin == "*":
                    raise ValueError(
                        "Wildcard '*' in CORS_ORIGINS is strictly prohibited in production."
                    )
                if origin.startswith("http://"):
                    raise ValueError(
                        f"Insecure HTTP origin '{origin}' is not permitted in production CORS_ORIGINS."
                    )

            if self.DATABASE_URL == "postgresql+psycopg://postgres:postgres@localhost:5432/lms_db":
                raise ValueError(
                    "Default development DATABASE_URL cannot be used in production. Please set a production database connection string."
                )

            # Razorpay Payment Gateway Production Invariants (BUG-003)
            if not self.RAZORPAY_KEY_ID or self.RAZORPAY_KEY_ID.startswith("rzp_test_mock"):
                raise ValueError("RAZORPAY_KEY_ID must be configured with a live key in production.")
            if not self.RAZORPAY_KEY_SECRET or "mock" in self.RAZORPAY_KEY_SECRET.get_secret_value().lower():
                raise ValueError("RAZORPAY_KEY_SECRET must be configured with a valid secret in production.")
            if not self.RAZORPAY_WEBHOOK_SECRET or "mock" in self.RAZORPAY_WEBHOOK_SECRET.get_secret_value().lower():
                raise ValueError("RAZORPAY_WEBHOOK_SECRET must be configured with a valid secret in production.")

            # Public Certificate Verification & Application URL Invariants (BUG-013)
            if self.FRONTEND_URL == "http://localhost:3000" and not self.BACKEND_URL:
                for origin in self.CORS_ORIGINS:
                    if origin.startswith("https://") and "localhost" not in origin and "127.0.0.1" not in origin:
                        self.FRONTEND_URL = origin
                        break

            effective_public_url = self.BACKEND_URL or self.FRONTEND_URL
            if not effective_public_url or not effective_public_url.startswith("https://"):
                raise ValueError("BACKEND_URL or FRONTEND_URL must be configured with a valid HTTPS URL in production.")
            if "localhost" in effective_public_url or "127.0.0.1" in effective_public_url:
                raise ValueError("Localhost fallback is prohibited in production for public verification URLs.")

        return self

    @property
    def is_production(self) -> bool:
        """Returns True if the application is running in production mode."""
        return self.ENVIRONMENT == "production"

    @property
    def is_testing(self) -> bool:
        """Returns True if the application is running in automated test mode."""
        return self.ENVIRONMENT == "testing"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns a cached singleton instance of the application Settings.
    
    Uses lru_cache to avoid re-reading and re-parsing environment variables
    on every invocation. Tests can invoke get_settings.cache_clear() when
    manipulating environment variables.
    """
    return Settings()
