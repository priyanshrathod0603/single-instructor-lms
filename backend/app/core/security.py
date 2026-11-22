"""Cryptographic security utilities, password hashing, and token operations.

Architecture Specifications:
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md (Section 2, 4, 6)
- docs/backend/08-SESSION-MANAGEMENT.md (Section 4)
- docs/backend/18-SECURITY-ARCHITECTURE.md (Section 2)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK101)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-006)

Strict Invariants:
1. Passwords are never stored in plaintext and never logged.
2. Hashing algorithm: Argon2id with exact approved parameters:
   m=65536 KiB (64 MiB), t=3 iterations, p=4 parallelism threads,
   hash_len=32, salt_len=16.
3. Password complexity enforced: 12-128 chars, uppercase, lowercase, digit, symbol.
4. JWT verification strictly restricts algorithm to settings.ALGORITHM (HS256).
5. Cryptographic one-time tokens generated via secrets.token_urlsafe(32) and stored
   exclusively as SHA-256 hashes.
6. Constant-time comparisons (hmac.compare_digest) prevent timing side channels.
"""

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
import re
import secrets
from typing import Any, Optional, Union
import uuid

import argon2
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import jwt

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException, ValidationException

# -----------------------------------------------------------------------------
# 1. Argon2id Password Hasher
# -----------------------------------------------------------------------------
# Approved Parameters: m=65536 KiB, t=3, p=4, hash_len=32, salt_len=16 [ADR-006]
ARGON2_MEMORY_COST = 65536
ARGON2_TIME_COST = 3
ARGON2_PARALLELISM = 4
ARGON2_HASH_LEN = 32
ARGON2_SALT_LEN = 16

password_hasher = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST,
    parallelism=ARGON2_PARALLELISM,
    hash_len=ARGON2_HASH_LEN,
    salt_len=ARGON2_SALT_LEN,
    type=argon2.Type.ID,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id with approved parameters.

    Args:
        password: The plaintext password string to hash.

    Returns:
        The Argon2id hash string starting with '$argon2id$v=19$m=65536,t=3,p=4$'.
    """
    if not password or not isinstance(password, str):
        raise ValidationException(message="Password must be a non-empty string.")
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash in constant time.

    Args:
        plain_password: The plaintext password candidate.
        hashed_password: The stored Argon2id hash.

    Returns:
        True if the password matches, False otherwise.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Check if the password hash needs to be recomputed due to updated parameters.

    Args:
        hashed_password: Stored Argon2id hash.

    Returns:
        True if the hash parameters differ from current security parameters.
    """
    if not hashed_password:
        return True
    try:
        return password_hasher.check_needs_rehash(hashed_password)
    except Exception:
        return True


# -----------------------------------------------------------------------------
# 2. Password Complexity Validator
# -----------------------------------------------------------------------------
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
PASSWORD_SPECIAL_CHARS = set("!@#$%^&*(),.?\":{}|<>-=_+[]\\/;~`'")


def validate_password_complexity(password: str) -> None:
    """Validate that a plaintext password satisfies strict security complexity criteria.

    Rules:
    - Minimum length: 12 characters
    - Maximum length: 128 characters (guards against DoS via hashing oversized inputs)
    - At least one uppercase letter [A-Z]
    - At least one lowercase letter [a-z]
    - At least one digit [0-9]
    - At least one special symbol

    Args:
        password: The plaintext candidate password.

    Raises:
        ValidationException: With descriptive violation details if any rule fails.
    """
    if not password or not isinstance(password, str):
        raise ValidationException(
            message="Password is required and must be a string.",
            details={"rule": "non_empty_string"},
        )

    errors = []
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    if len(password) > MAX_PASSWORD_LENGTH:
        errors.append(f"Password cannot exceed {MAX_PASSWORD_LENGTH} characters.")
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter [A-Z].")
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter [a-z].")
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one numerical digit [0-9].")
    if not any(c in PASSWORD_SPECIAL_CHARS for c in password):
        errors.append("Password must contain at least one special symbol.")

    if errors:
        raise ValidationException(
            message=f"Password does not satisfy complexity requirements: {'; '.join(errors)}",
            details={"violations": errors},
        )


# -----------------------------------------------------------------------------
# 3. JWT Access Token Utilities
# -----------------------------------------------------------------------------

def create_access_token(
    subject: Union[str, uuid.UUID],
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Generate a signed JSON Web Token (JWT) using the configured algorithm and secret.

    Args:
        subject: Unique identifier of the authenticated user (UUID or string).
        expires_delta: Optional custom token lifespan. Defaults to settings.ACCESS_TOKEN_EXPIRE_MINUTES.
        extra_claims: Optional dictionary of additional token claims (e.g. roles, token_type).

    Returns:
        Encoded JWT string.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
    }

    if extra_claims:
        payload.update(extra_claims)

    encoded_jwt = jwt.encode(
        payload,
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a signed JWT token against configured algorithms and secret.

    Guards against:
    - Signature tampering
    - Expired tokens
    - Algorithm substitution attacks (strictly restricts to settings.ALGORITHM)

    Args:
        token: Raw JWT string.

    Returns:
        Verified claims dictionary.

    Raises:
        UnauthorizedException: If token is expired, invalid, or tampered with.
    """
    settings = get_settings()
    try:
        decoded = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
        return decoded
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedException(message="Authentication token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedException(message="Invalid authentication token.") from exc


# -----------------------------------------------------------------------------
# 4. Cryptographic One-Time Token Utilities
# -----------------------------------------------------------------------------

def generate_secure_token(nbytes: int = 32) -> str:
    """Generate a cryptographically secure random token string for email verification or reset.

    Args:
        nbytes: Number of random bytes of entropy (default 32 bytes).

    Returns:
        URL-safe high-entropy token string.
    """
    return secrets.token_urlsafe(nbytes)


def hash_token(raw_token: str) -> str:
    """Compute the SHA-256 hexadecimal hash of a token for secure database persistence.

    Raw tokens are never persisted directly in PostgreSQL.

    Args:
        raw_token: Plaintext random token string.

    Returns:
        64-character lowercase hexadecimal SHA-256 digest.
    """
    if not raw_token or not isinstance(raw_token, str) or not raw_token.strip():
        raise ValidationException(message="Token must be a non-empty string.")
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def constant_time_compare(val1: str, val2: str) -> bool:
    """Compare two strings in constant time to prevent timing side-channel attacks.

    Args:
        val1: First string candidate.
        val2: Second string candidate.

    Returns:
        True if strings are identical, False otherwise.
    """
    if not isinstance(val1, str) or not isinstance(val2, str):
        return False
    return hmac.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))


# -----------------------------------------------------------------------------
# 7. Sensitive Outbox Payload Encryption (P0-06)
# -----------------------------------------------------------------------------
_PAYLOAD_CIPHER: Optional[Fernet] = None


def get_payload_cipher() -> Fernet:
    """Derive deterministic Fernet cipher from platform SECRET_KEY using HKDF-SHA256."""
    global _PAYLOAD_CIPHER
    if _PAYLOAD_CIPHER is None:
        settings = get_settings()
        secret = settings.SECRET_KEY.get_secret_value().encode("utf-8")
        salt = b"lms-outbox-payload-encryption-salt-v1"
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"outbox-payload-encryption",
        )
        key = base64.urlsafe_b64encode(hkdf.derive(secret))
        _PAYLOAD_CIPHER = Fernet(key)
    return _PAYLOAD_CIPHER


def encrypt_payload(data: Union[dict[str, Any], str]) -> str:
    """Encrypt sensitive payload string or dictionary using Fernet encryption.

    Args:
        data: Plaintext dictionary or string to encrypt.

    Returns:
        URL-safe base64-encoded ciphertext string.
    """
    if isinstance(data, dict):
        raw = json.dumps(data)
    else:
        raw = str(data)
    cipher = get_payload_cipher()
    return cipher.encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_payload(ciphertext: str) -> dict[str, Any]:
    """Decrypt Fernet-encrypted payload string back to structured dictionary.

    Args:
        ciphertext: URL-safe base64-encoded ciphertext.

    Returns:
        Decrypted JSON-parsed dictionary.
    """
    cipher = get_payload_cipher()
    decrypted_bytes = cipher.decrypt(ciphertext.encode("utf-8"))
    return json.loads(decrypted_bytes.decode("utf-8"))
