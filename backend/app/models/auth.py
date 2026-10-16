"""Authentication and user session models."""

import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(..., description="User login email address", examples=["captain@maritime.com"])
    password: Optional[str] = Field(default=None, description="Optional user password")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean or "@" not in clean or "." not in clean.split("@")[-1]:
            raise ValueError("Please provide a valid email address.")
        return clean


class UserResponse(BaseModel):
    id: str = Field(..., description="User unique identifier (email)", examples=["captain@maritime.com"])
    email: str = Field(..., description="User email address", examples=["captain@maritime.com"])
    name: str = Field(..., description="Display name", examples=["Captain"])


class LoginResponse(BaseModel):
    accessToken: str = Field(..., description="Bearer authentication access token", examples=["captain@maritime.com"])
    tokenType: str = Field(default="bearer", description="Token type")
    user: UserResponse
