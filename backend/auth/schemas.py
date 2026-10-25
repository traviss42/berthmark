"""Pydantic request and response schemas for authentication."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    """Payload for user login."""

    email: EmailStr
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    """User profile response payload matching OpenAPI schema."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    email: EmailStr
    name: str | None = None
    createdAt: str = Field(alias="createdAt")


class AuthResponse(BaseModel):
    """Authentication response payload containing JWT access token."""

    model_config = ConfigDict(populate_by_name=True)

    accessToken: str = Field(alias="accessToken")
    tokenType: str = Field(default="Bearer", alias="tokenType")
    expiresIn: int = Field(default=86400, alias="expiresIn")
    user: UserResponse


class ErrorResponse(BaseModel):
    """Standard API error response payload."""

    error: str
    message: str
    statusCode: int = Field(alias="statusCode")
