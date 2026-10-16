"""Routers package forwarding for backend.routers namespace."""

try:
    from app.routers import (
        auth_router,
        notifications_router,
        ports_router,
        risk_router,
    )
except ImportError:
    from backend.app.routers import (
        auth_router,
        notifications_router,
        ports_router,
        risk_router,
    )

__all__ = [
    "auth_router",
    "ports_router",
    "risk_router",
    "notifications_router",
]
