"""Unit and integration tests for Vessel Benchmark Taxonomy API and seeder."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import get_db_session
from backend.main import app
from backend.models import Base, VesselClass
from backend.taxonomy.seed import BENCHMARK_VESSEL_CLASSES, seed_vessel_classes
from backend.taxonomy.service import clear_vessel_classes_cache, get_vessel_classes


@pytest_asyncio.fixture
async def test_db():
    """Create an isolated test engine and session factory with schema loaded."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_vessel_classes_and_idempotency(test_db):
    """Verify seeding all 13 commercial vessel classes and idempotent re-execution."""
    async with test_db() as session:
        # First execution: 13 new records
        count1 = await seed_vessel_classes(session)
        assert count1 == 13

        result = await session.execute(select(VesselClass))
        classes = result.scalars().all()
        assert len(classes) == 13

        by_id = {vc.class_id: vc for vc in classes}

        # Check sectors and dimensions
        # Containerized
        assert by_id["feeder"].draft_m == 8.5
        assert by_id["feeder"].beam_m == 24.0
        assert by_id["feeder"].loa_m == 140.0
        assert by_id["feeder"].sector == "containerized"

        assert by_id["panamax"].draft_m == 12.0
        assert by_id["neoPanamax"].draft_m == 15.2
        assert by_id["ulcv"].draft_m == 16.0

        # Liquid Bulk
        assert by_id["mrTanker"].draft_m == 11.0
        assert by_id["aframax"].draft_m == 14.8
        assert by_id["suezmax"].draft_m == 16.0
        assert by_id["vlcc"].draft_m == 21.0
        assert by_id["vlcc"].sector == "liquidBulk"

        # Dry Bulk
        assert by_id["handysize"].draft_m == 10.5
        assert by_id["panamaxBulk"].draft_m == 14.5
        assert by_id["capesize"].draft_m == 18.0
        assert by_id["capesize"].sector == "dryBulk"

        # Specialized
        assert by_id["pctc"].draft_m == 10.0
        assert by_id["lng"].draft_m == 12.0
        assert by_id["lng"].sector == "specialized"

        # Second execution: idempotent (no new inserts)
        count2 = await seed_vessel_classes(session)
        assert count2 == 0
        result2 = await session.execute(select(VesselClass))
        assert len(result2.scalars().all()) == 13


@pytest.mark.asyncio
async def test_empty_database_returns_empty_list(test_db):
    """Verify unseeded database returns HTTP 200 with empty list."""
    clear_vessel_classes_cache()

    async def override_get_db():
        async with test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/vessel-classes")
        assert response.status_code == 200
        assert response.json() == []

    app.dependency_overrides.clear()
    clear_vessel_classes_cache()


@pytest.mark.asyncio
async def test_get_vessel_classes_api_and_caching(test_db):
    """Verify GET /api/v1/vessel-classes returns 13 items with OpenAPI schema and caching."""
    clear_vessel_classes_cache()

    # Seed the database
    async with test_db() as session:
        await seed_vessel_classes(session)

    async def override_get_db():
        async with test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # First call: populates cache
        response = await client.get("/api/v1/vessel-classes")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 13

        # Validate schema fields
        for item in data:
            assert "id" in item
            assert "label" in item
            assert "sector" in item
            assert "criteria" in item
            assert "significance" in item
            assert item["sector"] in [
                "containerized",
                "liquidBulk",
                "dryBulk",
                "specialized",
            ]

        # Validate sector grouping in deterministic ordering
        sectors = [item["sector"] for item in data]
        sector_indices = {
            "containerized": 0,
            "liquidBulk": 1,
            "dryBulk": 2,
            "specialized": 3,
        }
        order_numbers = [sector_indices[s] for s in sectors]
        assert order_numbers == sorted(order_numbers)

        # Also test root path /vessel-classes
        root_res = await client.get("/vessel-classes")
        assert root_res.status_code == 200
        assert len(root_res.json()) == 13

    app.dependency_overrides.clear()
    clear_vessel_classes_cache()
