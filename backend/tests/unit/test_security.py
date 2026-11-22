"""Unit tests for cryptographic security utilities, password hashing, and token operations.

Architecture Specifications:
- docs/backend/07-AUTHENTICATION-ARCHITECTURE.md (Section 2, 4, 6)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK101)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-006)
"""

from datetime import timedelta
import time
import uuid
import pytest
import jwt

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException, ValidationException
from app.core.security import (
    ARGON2_HASH_LEN,
    ARGON2_MEMORY_COST,
    ARGON2_PARALLELISM,
    ARGON2_SALT_LEN,
    ARGON2_TIME_COST,
    constant_time_compare,
    create_access_token,
    decode_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    needs_rehash,
    validate_password_complexity,
    verify_password,
)


class TestArgon2idPasswordHashing:
    """Verifies Argon2id password hashing parameters, verification, and invariants."""

    def test_approved_argon2_parameter_compliance(self):
        """Argon2id parameters must match approved ADR-006 specification."""
        assert ARGON2_MEMORY_COST == 65536  # 64 MiB
        assert ARGON2_TIME_COST == 3
        assert ARGON2_PARALLELISM == 4
        assert ARGON2_HASH_LEN == 32
        assert ARGON2_SALT_LEN == 16

    def test_hash_format_and_verification_success(self):
        """Valid password must generate compliant Argon2id hash and verify successfully."""
        password = "SecurePassword123!"
        hashed = hash_password(password)

        assert isinstance(hashed, str)
        assert hashed.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
        assert verify_password(password, hashed) is True

    def test_verify_password_rejection_on_mismatch(self):
        """Incorrect password candidate must return False."""
        hashed = hash_password("CorrectPassword123!")
        assert verify_password("WrongPassword456!", hashed) is False

    def test_verify_password_handles_invalid_hash_strings(self):
        """Malformed or non-Argon2 hash strings must return False without raising exceptions."""
        assert verify_password("Test1234!", "not-a-valid-argon-hash") is False
        assert verify_password("Test1234!", "$argon2id$invalid$syntax") is False
        assert verify_password("Test1234!", "") is False
        assert verify_password("", "some_hash") is False

    def test_hash_password_rejects_empty_inputs(self):
        """Empty or non-string password inputs must raise ValidationException."""
        with pytest.raises(ValidationException):
            hash_password("")
        with pytest.raises(ValidationException):
            hash_password(None)  # type: ignore

    def test_needs_rehash_detection(self):
        """needs_rehash must return False for current parameters, True for empty/corrupted."""
        hashed = hash_password("ValidPassword123!")
        assert needs_rehash(hashed) is False
        assert needs_rehash("") is True
        assert needs_rehash("corrupted") is True


class TestPasswordComplexityValidation:
    """Verifies strict password complexity enforcement."""

    def test_valid_passwords_pass(self):
        """Passwords satisfying all 6 rules must pass validation without exceptions."""
        valid_samples = [
            "StrongPass123!",
            "Correct-Horse-Battery-Staple-99#",
            "Super$ecretP@ssw0rd2026",
            "Priyansh_LMS_2026!",
        ]
        for pwd in valid_samples:
            validate_password_complexity(pwd)

    def test_too_short_rejected(self):
        """Passwords under 12 characters must be rejected."""
        with pytest.raises(ValidationException) as exc:
            validate_password_complexity("Short1!")
        assert "at least 12 characters" in str(exc.value)

    def test_too_long_rejected(self):
        """Passwords exceeding 128 characters must be rejected to prevent DoS."""
        oversized = "Aa1!" + "x" * 130
        with pytest.raises(ValidationException) as exc:
            validate_password_complexity(oversized)
        assert "cannot exceed 128 characters" in str(exc.value)

    def test_missing_uppercase_rejected(self):
        """Passwords without uppercase [A-Z] must be rejected."""
        with pytest.raises(ValidationException) as exc:
            validate_password_complexity("lowercase1234!@#$")
        assert "uppercase" in str(exc.value)

    def test_missing_lowercase_rejected(self):
        """Passwords without lowercase [a-z] must be rejected."""
        with pytest.raises(ValidationException) as exc:
            validate_password_complexity("UPPERCASE1234!@#$")
        assert "lowercase" in str(exc.value)

    def test_missing_digit_rejected(self):
        """Passwords without numerical digits [0-9] must be rejected."""
        with pytest.raises(ValidationException) as exc:
            validate_password_complexity("NoDigitsHere!@#$")
        assert "numerical digit" in str(exc.value)

    def test_missing_special_symbol_rejected(self):
        """Passwords without symbols must be rejected."""
        with pytest.raises(ValidationException) as exc:
            validate_password_complexity("NoSpecialChars12345")
        assert "special symbol" in str(exc.value)


class TestJWTAccessTokens:
    """Verifies JWT encoding, decoding, expiration, and tampering defenses."""

    def test_create_and_decode_access_token(self):
        """Access token must encode claims and decode cleanly."""
        user_id = uuid.uuid4()
        token = create_access_token(
            subject=user_id,
            extra_claims={"roles": ["STUDENT"], "email": "test@example.com"},
        )

        assert isinstance(token, str)
        claims = decode_access_token(token)

        assert claims["sub"] == str(user_id)
        assert claims["roles"] == ["STUDENT"]
        assert claims["email"] == "test@example.com"
        assert "exp" in claims
        assert "iat" in claims
        assert "jti" in claims

    def test_expired_token_raises_unauthorized(self):
        """Expired access tokens must raise UnauthorizedException."""
        user_id = str(uuid.uuid4())
        # Generate token expired 10 seconds ago
        expired_token = create_access_token(
            subject=user_id,
            expires_delta=timedelta(seconds=-10),
        )

        with pytest.raises(UnauthorizedException, match="expired"):
            decode_access_token(expired_token)

    def test_tampered_token_signature_raises_unauthorized(self):
        """Tokens with modified payloads or tampered signatures must raise UnauthorizedException."""
        token = create_access_token(subject="user-123")
        # Tamper payload part of JWT
        parts = token.split(".")
        tampered_token = f"{parts[0]}.{parts[1]}tampered.{parts[2]}"

        with pytest.raises(UnauthorizedException, match="Invalid authentication token"):
            decode_access_token(tampered_token)

    def test_token_signed_with_wrong_key_rejected(self):
        """Tokens signed with a different key must be rejected."""
        payload = {"sub": "user-123", "exp": int(time.time()) + 3600, "iat": int(time.time())}
        forged = jwt.encode(payload, "completely-wrong-cryptographic-key-32-chars", algorithm="HS256")

        with pytest.raises(UnauthorizedException, match="Invalid authentication token"):
            decode_access_token(forged)

    def test_none_algorithm_attack_rejected(self):
        """Tokens using algorithm 'none' must be strictly rejected."""
        payload = {"sub": "user-123", "exp": int(time.time()) + 3600, "iat": int(time.time())}
        forged = jwt.encode(payload, "", algorithm="none")

        with pytest.raises(UnauthorizedException):
            decode_access_token(forged)


class TestCryptographicTokensAndComparisons:
    """Verifies token generation, hashing, and constant-time comparison."""

    def test_generate_secure_token_entropy(self):
        """generate_secure_token must produce URL-safe high-entropy strings."""
        t1 = generate_secure_token(32)
        t2 = generate_secure_token(32)

        assert isinstance(t1, str)
        assert len(t1) >= 40
        assert t1 != t2

    def test_hash_token_sha256(self):
        """hash_token must return lowercase 64-char hexadecimal SHA-256 digest."""
        token = "test_verification_token_123"
        digest1 = hash_token(token)
        digest2 = hash_token(token)

        assert len(digest1) == 64
        assert digest1 == digest2
        # Verify against standard hashlib calculation
        import hashlib
        expected = hashlib.sha256(token.encode("utf-8")).hexdigest()
        assert digest1 == expected

    def test_hash_token_rejects_empty_inputs(self):
        """Empty token strings must raise ValidationException."""
        with pytest.raises(ValidationException):
            hash_token("")
        with pytest.raises(ValidationException):
            hash_token("   ")

    def test_constant_time_compare(self):
        """constant_time_compare must verify equality and reject mismatches."""
        assert constant_time_compare("exact_match", "exact_match") is True
        assert constant_time_compare("string_a", "string_b") is False
        assert constant_time_compare("prefix", "prefix_longer") is False
        assert constant_time_compare("", "") is True
        assert constant_time_compare(None, "str") is False  # type: ignore
