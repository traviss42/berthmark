"""User authentication and profile management endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from app.auth.dependencies import get_current_user
from app.models.auth import LoginRequest, LoginResponse, UserResponse

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


def _format_display_name(email: str) -> str:
    """Format user display name from email address."""
    username = email.split("@")[0]
    parts = username.replace(".", " ").replace("_", " ").replace("-", " ").split()
    return " ".join(p.capitalize() for p in parts) if parts else "User"


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="User log in",
    description="Authenticate a user by email address. The login email will receive risk notifications and alerts.",
)
async def login(credentials: LoginRequest) -> LoginResponse:
    email = credentials.email.strip().lower()
    name = _format_display_name(email)
    user = UserResponse(id=email, email=email, name=name)
    return LoginResponse(accessToken=email, tokenType="bearer", user=user)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Retrieve the profile and notification email for the authenticated user.",
)
async def get_current_profile(current_user: str = Depends(get_current_user)) -> UserResponse:
    name = _format_display_name(current_user)
    return UserResponse(id=current_user, email=current_user, name=name)


@router.post(
    "/logout",
    summary="Log out",
    description="Log out of the current session.",
)
async def logout():
    return {"success": True, "message": "Logged out successfully."}
