"""Berthmark API server main application entry point."""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="Berthmark Maritime Port-Call Risk Intelligence API",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)


class HealthResponse(BaseModel):
    status: str = "healthy"


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """System health check endpoint."""
    return HealthResponse(status="healthy")


@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
async def api_v1_health_check():
    """API v1 health check endpoint."""
    return HealthResponse(status="healthy")
