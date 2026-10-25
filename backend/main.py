"""Berthmark API server main application entry point."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from backend.auth.router import router as auth_router
from backend.taxonomy.router import router as taxonomy_router

app = FastAPI(
    title="Berthmark Maritime Port-Call Risk Intelligence API",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """Normalize HTTPException responses to match ErrorResponse schema."""
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "Error",
            "message": str(exc.detail),
            "statusCode": exc.status_code,
        },
    )


# Mount routes under /api/v1 and root
app.include_router(taxonomy_router, prefix="/api/v1")
app.include_router(taxonomy_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(auth_router)


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
