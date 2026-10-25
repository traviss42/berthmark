"""Unit and integration tests for health endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from backend.main import app


@pytest.mark.asyncio
async def test_root_health():
    """Verify GET /health returns 200 and {'status': 'healthy'}."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_api_v1_health():
    """Verify GET /api/v1/health returns 200 and {'status': 'healthy'}."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
