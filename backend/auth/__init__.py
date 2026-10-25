"""Authentication package for Berthmark."""

from backend.auth.dependencies import get_current_user
from backend.auth.router import router as auth_router
from backend.auth.schemas import AuthResponse, ErrorResponse, LoginRequest, UserResponse
from backend.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.auth.seed import seed_default_user

__all__ = [
    "AuthResponse",
    "ErrorResponse",
    "LoginRequest",
    "UserResponse",
    "auth_router",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "hash_password",
    "seed_default_user",
    "verify_password",
]
