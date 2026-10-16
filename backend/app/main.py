"""Main FastAPI application entry point for Berthmark backend."""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.models.error import ErrorResponse
from app.routers import notifications_router, ports_router, risk_router

settings = get_settings()

app = FastAPI(
    title="Berthmark API",
    description="Backend REST API for Berthmark: Port-Call Risk Tracking & Assessment Tool.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS middleware for React frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include endpoint routers
app.include_router(ports_router)
app.include_router(risk_router)
app.include_router(notifications_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "1.0.0", "environment": settings.ENVIRONMENT}
