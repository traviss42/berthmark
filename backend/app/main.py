from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.db import init_db
from app.models.error import ErrorResponse
from app.routers import auth_router, notifications_router, ports_router, risk_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager initializing database tables on startup."""
    init_db()
    yield


app = FastAPI(
    title="Berthmark API",
    description="Backend REST API for Berthmark: Port-Call Risk Tracking & Assessment Tool.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
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
app.include_router(auth_router)
app.include_router(ports_router)
app.include_router(risk_router)
app.include_router(notifications_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "1.0.0", "environment": settings.ENVIRONMENT}


@app.get("/api/v1/system/diagnostics", tags=["System"])
async def run_diagnostics():
    """Live diagnostic check verifying connectivity and auth to UN/LOCODE DB, Open-Meteo, and AISStream."""
    import asyncio
    import json
    import time
    import httpx
    import websockets
    from app.clients.unlocode_db import UnlocodeDatabase

    results = {}

    # 1. UN/LOCODE Database
    t0 = time.time()
    try:
        db = UnlocodeDatabase()
        count = db.count_ports()
        results["unlocode_database"] = {
            "status": "healthy",
            "port_count": count,
            "latency_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as e:
        results["unlocode_database"] = {"status": "error", "detail": str(e)}

    # 2. Open-Meteo Weather API
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": 51.9244,
                    "longitude": 4.4777,
                    "current": "wind_speed_10m,wind_gusts_10m",
                    "wind_speed_unit": "kn",
                },
            )
            if resp.status_code == 200:
                data = resp.json().get("current", {})
                results["weather_api"] = {
                    "status": "healthy",
                    "endpoint": "https://api.open-meteo.com/v1/forecast",
                    "wind_speed_knots": data.get("wind_speed_10m"),
                    "gust_speed_knots": data.get("wind_gusts_10m"),
                    "latency_ms": round((time.time() - t0) * 1000, 1),
                }
            else:
                results["weather_api"] = {"status": "error", "code": resp.status_code}
    except Exception as e:
        results["weather_api"] = {"status": "error", "detail": str(e)}

    # 3. AISStream WebSocket API
    t0 = time.time()
    api_key = settings.AISSTREAM_API_KEY.strip()
    if not api_key:
        results["aisstream_api"] = {"status": "unconfigured", "detail": "Missing AISSTREAM_API_KEY"}
    else:
        try:
            ws_url = "wss://stream.aisstream.io/v0/stream"
            async with websockets.connect(ws_url, close_timeout=2.0, ping_timeout=3.0) as ws:
                sub = {
                    "APIKey": api_key,
                    "BoundingBoxes": [[[51.8, 3.8], [52.1, 4.6]]],
                    "FilterMessageTypes": ["PositionReport"],
                }
                await ws.send(json.dumps(sub))
                resp_raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                resp = json.loads(resp_raw)
                results["aisstream_api"] = {
                    "status": "healthy",
                    "authenticated": True,
                    "subscription_response": resp.get("MessageType"),
                    "latency_ms": round((time.time() - t0) * 1000, 1),
                }
        except Exception as e:
            results["aisstream_api"] = {"status": "error", "detail": str(e)}

    all_healthy = all(r.get("status") == "healthy" for r in results.values())
    return {
        "status": "ok" if all_healthy else "degraded",
        "all_healthy": all_healthy,
        "apis": results,
    }
