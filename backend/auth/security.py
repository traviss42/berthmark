"""Cryptographic security utilities: password hashing and JWT token management."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any
import bcrypt
import jwt

DEFAULT_SECRET_KEY = "berthmark-dev-secret-key-replace-in-production-super-secure"
ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = 1440  # 24 hours


def get_jwt_secret_key() -> str:
    """Retrieve secret key from environment with secure fallback."""
    return os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY") or DEFAULT_SECRET_KEY


def get_token_expire_minutes() -> int:
    """Retrieve access token expiration in minutes from environment."""
    val = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return DEFAULT_EXPIRE_MINUTES


def hash_password(password: str) -> str:
    """Hash password using bcrypt with a freshly generated salt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash using constant-time comparison."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Generate signed JWT access token.

    Returns:
        (token_string, expires_in_seconds)
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta is not None:
        expire = now + expires_delta
        expires_in = int(expires_delta.total_seconds())
    else:
        expire_minutes = get_token_expire_minutes()
        expire = now + timedelta(minutes=expire_minutes)
        expires_in = expire_minutes * 60

    to_encode.update({
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    })

    secret_key = get_jwt_secret_key()
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate signature and expiration of JWT access token.

    Raises:
        jwt.PyJWTError: If token is expired, invalid, or tampered with.
    """
    secret_key = get_jwt_secret_key()
    return jwt.decode(token, secret_key, algorithms=[ALGORITHM])
