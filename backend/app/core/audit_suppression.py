"""Privacy-safe Redis-backed audit suppression for authentication abuse controls (SA-03.5).

Architecture Specifications:
- docs/SA-03_SECURITY_GOVERNANCE_SPECIFICATION.md (Section 11, SA-03.5)
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/18-SECURITY-ARCHITECTURE.md

Strict Invariants:
1. Privacy Preservation: Zero plaintext passwords, raw credentials, session tokens, or auth headers are logged or stored in Redis keys.
2. Keyed HMAC Identifiers: Email and IP addresses are derived via HMAC-SHA256 using settings.SECRET_KEY.
3. Bounded Database Load: High-frequency repeated failures are suppressed in Redis to prevent PostgreSQL storage exhaustion.
4. Window & TTL Lifecycle: 60-second suppression window with 300-second counter TTL.
5. Fail-Closed in Production: If Redis or secret fails in production, denies write load and emits structured error.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import socket
import ssl
import sys
from typing import Optional
from urllib.parse import unquote, urlparse

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_SUPPRESSION_LUA_SCRIPT = (
    "local suppressed = redis.call('EXISTS', KEYS[1]) "
    "if suppressed == 1 then "
    "local count = redis.call('INCR', KEYS[2]) "
    "redis.call('EXPIRE', KEYS[2], ARGV[2]) "
    "return {1, count} "
    "else "
    "redis.call('SET', KEYS[1], '1', 'EX', ARGV[1]) "
    "local prev = redis.call('GET', KEYS[2]) "
    "redis.call('SET', KEYS[2], '1', 'EX', ARGV[2]) "
    "local prev_count = prev and tonumber(prev) or 0 "
    "return {0, prev_count} "
    "end"
)


def _encode_resp(*parts: str) -> bytes:
    """Encode command arguments into Redis Serialization Protocol (RESP) format."""
    encoded = [f"*{len(parts)}\r\n".encode()]
    for part in parts:
        raw = part.encode("utf-8")
        encoded.extend((f"${len(raw)}\r\n".encode(), raw, b"\r\n"))
    return b"".join(encoded)


def _read_resp_response(stream):
    """Parse RESP wire protocol response from socket stream."""
    prefix = stream.read(1)
    if not prefix:
        raise OSError("Redis closed the connection")
    line = stream.readline().rstrip(b"\r\n")
    if prefix == b":":
        return int(line)
    if prefix == b"+":
        return line.decode("utf-8")
    if prefix == b"-":
        raise OSError(f"Redis error response: {line.decode('utf-8', errors='replace')}")
    if prefix == b"$":
        length = int(line)
        return None if length < 0 else stream.read(length + 2)[:-2]
    if prefix == b"*":
        return [_read_resp_response(stream) for _ in range(int(line))]
    raise OSError("Malformed Redis response")


def derive_email_hmac(email: str, settings: Settings) -> str:
    """Derive keyed HMAC-SHA256 hex digest for an email address."""
    secret_bytes = settings.SECRET_KEY.get_secret_value().encode("utf-8")
    normalized_email = email.strip().lower()
    return hmac.new(
        secret_bytes,
        f"email:{normalized_email}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def derive_ip_hmac(client_ip: Optional[str], settings: Settings) -> str:
    """Derive keyed HMAC-SHA256 hex digest for a client IP address."""
    secret_bytes = settings.SECRET_KEY.get_secret_value().encode("utf-8")
    clean_ip = (client_ip or "unknown").strip().lower()
    return hmac.new(
        secret_bytes,
        f"ip:{clean_ip}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def evaluate_login_failure_suppression(
    email: str,
    client_ip: Optional[str],
    *,
    settings: Optional[Settings] = None,
) -> tuple[bool, int, str, str]:
    """Evaluate Redis suppression state for a failed login attempt.

    Returns:
        tuple of (is_suppressed, prior_suppressed_count, email_hmac, ip_hmac).
        If is_suppressed is True, database audit log persistence should be skipped.
        If is_suppressed is False, database audit log should be written with prior_suppressed_count.
    """
    active_settings = settings or get_settings()
    email_hmac = derive_email_hmac(email, active_settings)
    ip_hmac = derive_ip_hmac(client_ip, active_settings)

    suppression_key = f"lms:audit:suppression:login_failed:{email_hmac}:{ip_hmac}"
    counter_key = f"lms:audit:counter:login_failed:{email_hmac}:{ip_hmac}"

    url = urlparse(active_settings.REDIS_URL or "")
    if url.scheme not in {"redis", "rediss"} or not url.hostname:
        # If REDIS_URL not configured: in dev/test write to DB; in prod suppress
        if active_settings.is_production:
            logger.error("REDIS_URL unconfigured in production during audit suppression evaluation")
            return True, 0, email_hmac, ip_hmac
        return False, 0, email_hmac, ip_hmac

    try:
        raw_socket = socket.create_connection((url.hostname, url.port or 6379), timeout=1.5)
        connection = (
            ssl.create_default_context().wrap_socket(raw_socket, server_hostname=url.hostname)
            if url.scheme == "rediss"
            else raw_socket
        )
        try:
            stream = connection.makefile("rwb")
            if url.password:
                stream.write(_encode_resp("AUTH", unquote(url.username or "default"), unquote(url.password)))
                stream.flush()
                _read_resp_response(stream)

            database = (url.path or "/0").strip("/") or "0"
            stream.write(_encode_resp("SELECT", database))
            stream.write(
                _encode_resp(
                    "EVAL",
                    _SUPPRESSION_LUA_SCRIPT,
                    "2",
                    suppression_key,
                    counter_key,
                    "60",   # 60s suppression window
                    "300",  # 300s counter TTL
                )
            )
            stream.flush()
            _read_resp_response(stream)  # SELECT response
            result = _read_resp_response(stream)  # EVAL response

            if not isinstance(result, list) or len(result) != 2:
                raise OSError("Unexpected Redis response format from suppression Lua script")

            is_suppressed = int(result[0]) == 1
            count_val = int(result[1])
            return is_suppressed, count_val, email_hmac, ip_hmac
        finally:
            connection.close()

    except OSError as exc:
        if active_settings.is_production:
            logger.error("Redis connection failed during audit suppression check: %s", exc)
            # In production: bypass DB write on Redis outage to prevent database saturation
            return True, 0, email_hmac, ip_hmac
        # In development or testing: bypass suppression so test suites pass without Redis
        return False, 0, email_hmac, ip_hmac
