"""
Secure password hashing and verification utilities using Argon2id.

Designed for future local authentication flows.
Plaintext passwords and password hashes are never logged.
Invalid or malformed stored hashes fail verification safely.
"""

import hashlib
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

# Argon2id password hasher with RFC 9106 / OWASP recommended defaults
_hasher = PasswordHasher()


def generate_session_token() -> str:
    """Generate an opaque cryptographically secure random session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """
    Return the SHA-256 hex digest of an opaque session token.
    Only the hash is stored in the database.
    """
    if not token or not isinstance(token, str):
        raise ValueError("Session token must be a non-empty string.")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_invitation_token() -> str:
    """Generate an opaque cryptographically secure random invitation token."""
    return secrets.token_urlsafe(32)


def hash_invitation_token(token: str) -> str:
    """
    Return the SHA-256 hex digest of an opaque invitation token.
    Only the hash is stored in the database.
    """
    if not token or not isinstance(token, str):
        raise ValueError("Invitation token must be a non-empty string.")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using Argon2id.

    Args:
        password: The plaintext password string to hash.

    Returns:
        The Argon2id hash string.

    Raises:
        ValueError: If the password is empty or not a string.
    """
    if not password or not isinstance(password, str):
        raise ValueError("Password must be a non-empty string.")

    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    """
    Verify a candidate password against an Argon2id stored hash.

    Safely fails without raising exceptions or logging when given
    invalid, malformed, empty, or mismatched hashes.

    Args:
        password: The candidate plaintext password string.
        stored_hash: The previously stored Argon2id hash string.

    Returns:
        True if the password matches the stored hash, False otherwise.
    """
    if not password or not stored_hash:
        return False

    if not isinstance(password, str) or not isinstance(stored_hash, str):
        return False

    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False
    except Exception:
        return False
