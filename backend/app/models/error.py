"""Standard error response model."""

from typing import Optional
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Human-readable error explanation", examples=["Port not found or access denied."])
    code: Optional[str] = Field(default=None, description="Application error code", examples=["NOT_FOUND"])
