"""Berthmark API server main application entry point."""

from fastapi import FastAPI
from pydantic import BaseModel
from backend.taxonomy.router import router as taxonomy_router

app = FastAPI(
    title="Berthmark Maritime Port-Call Risk Intelligence API",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Mount taxonomy routes under /api/v1 and root
app.include_router(taxonomy_router, prefix="/api/v1")
app.include_router(taxonomy_router)


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
