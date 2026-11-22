"""Small Redis-backed fixed-window limiter for authentication abuse controls.

It deliberately uses the Redis RESP protocol over the standard library: the
project has an approved Redis deployment but no approved third-party client.
Production never falls back to process-local state; a Redis outage denies the
sensitive request rather than disabling brute-force protection.
"""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass
from hashlib import sha256
from time import time
from typing import Optional
from urllib.parse import unquote, urlparse

from app.core.config import Settings, get_settings
from app.core.exceptions import AppException, RateLimitException


class RateLimitBackendUnavailable(AppException):
    def __init__(self) -> None:
        super().__init__(
            message="Authentication protection is temporarily unavailable. Please retry shortly.",
            status_code=503,
            code="RATE_LIMIT_BACKEND_UNAVAILABLE",
        )


@dataclass(frozen=True)
class RateLimit:
    limit: int
    window_seconds: int


class RedisFixedWindowLimiter:
    """Atomic Redis Lua limiter; Redis is the shared source of truth per worker."""

    _SCRIPT = (
        "local count = redis.call('INCR', KEYS[1]) "
        "if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end "
        "local ttl = redis.call('TTL', KEYS[1]) return {count, ttl}"
    )

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    @staticmethod
    def _read_response(stream):
        prefix = stream.read(1)
        if not prefix:
            raise OSError("Redis closed the connection")
        line = stream.readline().rstrip(b"\r\n")
        if prefix == b":":
            return int(line)
        if prefix == b"+":
            return line.decode("utf-8")
        if prefix == b"-":
            raise OSError("Redis error response")
        if prefix == b"$":
            length = int(line)
            return None if length < 0 else stream.read(length + 2)[:-2]
        if prefix == b"*":
            return [RedisFixedWindowLimiter._read_response(stream) for _ in range(int(line))]
        raise OSError("Malformed Redis response")

    @staticmethod
    def _encode(*parts: str) -> bytes:
        encoded = [f"*{len(parts)}\r\n".encode()]
        for part in parts:
            raw = part.encode("utf-8")
            encoded.extend((f"${len(raw)}\r\n".encode(), raw, b"\r\n"))
        return b"".join(encoded)

    def consume(self, key: str, policy: RateLimit) -> tuple[int, int]:
        url = urlparse(self.settings.REDIS_URL or "")
        if url.scheme not in {"redis", "rediss"} or not url.hostname:
            raise OSError("REDIS_URL is not configured")
        raw_socket = socket.create_connection((url.hostname, url.port or 6379), timeout=1.5)
        connection = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=url.hostname) if url.scheme == "rediss" else raw_socket
        try:
            stream = connection.makefile("rwb")
            if url.password:
                stream.write(self._encode("AUTH", unquote(url.username or "default"), unquote(url.password)))
                stream.flush()
                self._read_response(stream)
            database = (url.path or "/0").strip("/") or "0"
            stream.write(self._encode("SELECT", database))
            stream.write(self._encode("EVAL", self._SCRIPT, "1", key, str(policy.window_seconds)))
            stream.flush()
            self._read_response(stream)
            response = self._read_response(stream)
            if not isinstance(response, list) or len(response) != 2:
                raise OSError("Unexpected Redis limiter response")
            return int(response[0]), max(1, int(response[1]))
        finally:
            connection.close()


_AUTH_POLICIES = {
    "login": (RateLimit(5, 900), RateLimit(20, 900)),
    "register": (RateLimit(3, 3600), RateLimit(10, 3600)),
    "password_reset": (RateLimit(3, 3600), RateLimit(10, 3600)),
    "email_verify": (RateLimit(10, 900), RateLimit(30, 900)),
    "resend_verification": (RateLimit(1, 180), RateLimit(10, 3600)),
}


def enforce_auth_rate_limit(action: str, *, identifier: str, client_ip: Optional[str], settings: Optional[Settings] = None) -> None:
    """Apply both identifier and IP limits before a sensitive auth operation."""
    active_settings = settings or get_settings()
    policies = _AUTH_POLICIES[action]
    limiter = RedisFixedWindowLimiter(active_settings)
    subjects = (("id", identifier.strip().lower(), policies[0]), ("ip", client_ip or "unknown", policies[1]))
    for scope, subject, policy in subjects:
        digest = sha256(subject.encode("utf-8")).hexdigest()
        key = f"lms:rate-limit:auth:{action}:{scope}:{digest}:{int(time() // policy.window_seconds)}"
        try:
            count, retry_after = limiter.consume(key, policy)
        except OSError as exc:
            if active_settings.is_production:
                raise RateLimitBackendUnavailable() from exc
            # Development/testing has no security posture claim and avoids a Redis dependency.
            continue
        if count > policy.limit:
            raise RateLimitException(retry_after=retry_after)
