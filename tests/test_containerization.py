"""Automated unit and integration tests for Berthmark containerization stack."""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from backend.ais.stream_worker import run_worker
from backend.main import app
from backend.seed import run_seeders

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_root_dockerfile_structure():
    """Verify backend multi-stage Dockerfile directives."""
    dockerfile_path = PROJECT_ROOT / "Dockerfile"
    assert dockerfile_path.is_file(), "Dockerfile must exist in project root"
    content = dockerfile_path.read_text()

    assert "FROM ghcr.io/astral-sh/uv:" in content
    assert "FROM python:3.12-slim" in content
    assert "uv sync" in content
    assert "EXPOSE 8000" in content
    assert "ENTRYPOINT [\"/app/docker-entrypoint.sh\"]" in content
    assert "uvicorn" in content
    assert "HEALTHCHECK" in content


def test_docker_entrypoint_script():
    """Verify docker-entrypoint.sh exists, is executable, and contains migration hooks."""
    entrypoint_path = PROJECT_ROOT / "docker-entrypoint.sh"
    assert entrypoint_path.is_file(), "docker-entrypoint.sh must exist in project root"
    assert os.access(entrypoint_path, os.X_OK), "docker-entrypoint.sh must be executable"
    content = entrypoint_path.read_text()

    assert "alembic upgrade head" in content
    assert "python -m backend.seed" in content
    assert 'exec "$@"' in content


def test_frontend_dockerfile_structure():
    """Verify frontend multi-stage Dockerfile directives."""
    dockerfile_path = PROJECT_ROOT / "frontend" / "Dockerfile"
    assert dockerfile_path.is_file(), "frontend/Dockerfile must exist"
    content = dockerfile_path.read_text()

    assert "FROM node:20-alpine AS builder" in content
    assert "npm run build" in content
    assert "FROM nginx:alpine" in content
    assert "/usr/share/nginx/html" in content
    assert "nginx.conf" in content
    assert "EXPOSE 80" in content
    assert "HEALTHCHECK" in content


def test_nginx_configuration_file():
    """Verify frontend/nginx.conf handles SPA routing and reverse proxies API requests."""
    nginx_path = PROJECT_ROOT / "frontend" / "nginx.conf"
    assert nginx_path.is_file(), "frontend/nginx.conf must exist"
    content = nginx_path.read_text()

    assert "listen 80;" in content
    assert "proxy_pass http://backend:8000/api/;" in content
    assert "try_files $uri $uri/ /index.html;" in content
    assert "proxy_set_header Host $host;" in content
    assert "proxy_set_header X-Real-IP $remote_addr;" in content


def test_docker_compose_specification():
    """Verify docker-compose.yml configuration and service definitions."""
    compose_path = PROJECT_ROOT / "docker-compose.yml"
    assert compose_path.is_file(), "docker-compose.yml must exist"
    content = compose_path.read_text()

    # Core services
    assert "db:" in content
    assert "redis:" in content
    assert "backend:" in content
    assert "worker:" in content
    assert "frontend:" in content

    # PostGIS database specifications
    assert "image: postgis/postgis:16-3.4" in content
    assert '"5432:5432"' in content
    assert "postgres_data:/var/lib/postgresql/data" in content

    # Redis cache specifications
    assert "image: redis:7-alpine" in content
    assert '"6379:6379"' in content
    assert "redis_data:/data" in content

    # Worker specifications
    assert "backend.ais.stream_worker" in content

    # Networks and volumes
    assert "berthmark-net:" in content
    assert "postgres_data:" in content
    assert "redis_data:" in content


def test_dockerignore_and_env_templates():
    """Verify .dockerignore and .env.example files exist and document essential keys."""
    root_dockerignore = PROJECT_ROOT / ".dockerignore"
    frontend_dockerignore = PROJECT_ROOT / "frontend" / ".dockerignore"
    env_example = PROJECT_ROOT / ".env.example"

    assert root_dockerignore.is_file(), ".dockerignore must exist"
    assert frontend_dockerignore.is_file(), "frontend/.dockerignore must exist"
    assert env_example.is_file(), ".env.example must exist"

    root_ignore_text = root_dockerignore.read_text()
    assert ".git" in root_ignore_text
    assert ".venv" in root_ignore_text
    assert "__pycache__" in root_ignore_text

    frontend_ignore_text = frontend_dockerignore.read_text()
    assert "node_modules" in frontend_ignore_text
    assert "dist" in frontend_ignore_text

    env_text = env_example.read_text()
    assert "DATABASE_URL" in env_text
    assert "CACHE_URL" in env_text
    assert "AISSTREAM_API_KEY" in env_text
    assert "JWT_SECRET_KEY" in env_text
    assert "PORT" in env_text
    assert "NODE_ENV" in env_text


@pytest.mark.asyncio
async def test_seeder_execution():
    """Verify that unified seeder executes idempotently without errors."""
    stats = await run_seeders()
    assert "vessel_classes" in stats
    assert "default_user" in stats
    assert stats["default_user"] == "operator@maritimerisk.com"
    assert "baselines" in stats


@pytest.mark.asyncio
async def test_stream_worker_missing_api_key_standby():
    """Verify stream worker handles missing API key by entering standby rather than crashing."""
    with patch.dict(os.environ, {"AISSTREAM_API_KEY": ""}, clear=False):
        # Patch asyncio.sleep to interrupt after 1 tick
        call_count = 0

        async def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=fake_sleep):
            # run_worker should catch CancelledError and terminate gracefully
            await run_worker()

        assert call_count == 1


@pytest.mark.asyncio
async def test_health_check_unhealthy_when_database_down():
    """Verify health endpoint returns HTTP 503 when database connectivity is lost."""
    with patch("backend.main.ping_database", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
            assert "Database connectivity" in data["message"]


@pytest.mark.asyncio
async def test_health_check_unhealthy_when_redis_down():
    """Verify health endpoint returns HTTP 503 when cache connectivity is lost."""
    with patch("backend.main.ping_database", new_callable=AsyncMock, return_value=True):
        with patch("backend.main.check_redis_health", new_callable=AsyncMock, return_value=False):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/health")
                assert response.status_code == 503
                data = response.json()
                assert data["status"] == "unhealthy"
                assert "Cache connectivity" in data["message"]


@pytest.mark.asyncio
async def test_health_check_healthy_when_all_dependencies_up():
    """Verify health endpoint returns HTTP 200 when all dependencies are healthy."""
    with patch("backend.main.ping_database", new_callable=AsyncMock, return_value=True):
        with patch("backend.main.check_redis_health", new_callable=AsyncMock, return_value=True):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "healthy"
