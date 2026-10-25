"""Berthmark API server main application entry point."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from backend.auth.router import router as auth_router
from backend.ports.router import router as ports_router
from backend.routers.notifications import router as notifications_router
from backend.routers.risk import router as risk_router
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


@app.exception_handler(RequestValidationError)
async def custom_validation_exception_handler(request: Request, exc: RequestValidationError):
    """Normalize validation errors to HTTP 400 matching OpenAPI ErrorResponse schema."""
    if "/auth" in request.url.path:
        return await request_validation_exception_handler(request, exc)

    errors = exc.errors()
    first_error = errors[0] if errors else {}
    msg = first_error.get("msg", "Validation error")
    loc = " -> ".join(str(l) for l in first_error.get("loc", []))
    full_msg = f"{loc}: {msg}" if loc else msg
    return JSONResponse(
        status_code=400,
        content={
            "error": "Bad Request",
            "message": full_msg,
            "statusCode": 400,
        },
    )


# Mount routes under /api/v1 and root
app.include_router(taxonomy_router, prefix="/api/v1")
app.include_router(taxonomy_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(auth_router)
app.include_router(ports_router, prefix="/api/v1")
app.include_router(ports_router)
app.include_router(risk_router, prefix="/api/v1")
app.include_router(risk_router)
app.include_router(notifications_router, prefix="/api/v1")
import asyncio
import os
import urllib.parse
from backend.database import ping_database

app.include_router(notifications_router)


class HealthResponse(BaseModel):
    status: str = "healthy"


async def check_redis_health() -> bool:
    """Test connectivity to Redis if CACHE_URL is configured."""
    cache_url = os.getenv("CACHE_URL", "").strip()
    if not cache_url:
        return True
    try:
        parsed = urllib.parse.urlparse(cache_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=2.0
        )
        writer.write(b"PING\r\n")
        await writer.drain()
        reply = await asyncio.wait_for(reader.readline(), timeout=2.0)
        writer.close()
        await writer.wait_closed()
        return reply.startswith(b"+PONG")
    except Exception:
        return False


async def check_system_health() -> tuple[bool, str]:
    """Perform health checks on database and cache dependencies."""
    try:
        db_ok = await ping_database()
    except Exception:
        db_ok = False

    if not db_ok:
        return False, "Database connectivity unavailable"

    redis_ok = await check_redis_health()
    if not redis_ok:
        return False, "Cache connectivity unavailable"

    return True, "healthy"


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """System health check endpoint."""
    healthy, detail = await check_system_health()
    if not healthy:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "message": detail})
    return HealthResponse(status="healthy")


@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
async def api_v1_health_check():
    """API v1 health check endpoint."""
    healthy, detail = await check_system_health()
    if not healthy:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "message": detail})
    return HealthResponse(status="healthy")
