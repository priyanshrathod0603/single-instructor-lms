"""Regression tests for shared authentication abuse controls."""

from types import SimpleNamespace

import pytest

from app.core.exceptions import RateLimitException
from app.core.rate_limit import (
    RateLimitBackendUnavailable,
    RedisFixedWindowLimiter,
    enforce_auth_rate_limit,
)


def test_auth_rate_limit_enforces_identifier_limit(monkeypatch):
    settings = SimpleNamespace(is_production=False, REDIS_URL="redis://localhost:6379/0")
    monkeypatch.setattr(RedisFixedWindowLimiter, "consume", lambda self, key, policy: (policy.limit + 1, 42))
    with pytest.raises(RateLimitException) as exc_info:
        enforce_auth_rate_limit("login", identifier="student@example.test", client_ip="203.0.113.9", settings=settings)
    assert exc_info.value.headers["Retry-After"] == "42"


def test_auth_rate_limit_fails_closed_when_production_redis_is_down(monkeypatch):
    settings = SimpleNamespace(is_production=True, REDIS_URL="redis://127.0.0.1:1/0")
    monkeypatch.setattr(RedisFixedWindowLimiter, "consume", lambda self, key, policy: (_ for _ in ()).throw(OSError("down")))
    with pytest.raises(RateLimitBackendUnavailable):
        enforce_auth_rate_limit("password_reset", identifier="student@example.test", client_ip="203.0.113.9", settings=settings)
