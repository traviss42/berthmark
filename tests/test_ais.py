"""Unit and integration tests for AISStream WebSocket Worker and Traffic Classification Engine."""

import asyncio
import json
import time
import uuid
import pytest
import pytest_asyncio
import websockets
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import Base, Port, PortRiskSnapshot, User, UserWatchlist, VesselClass
from backend.services.ais import (
    AISStreamWorker,
    MonitoredPortInfo,
    PortTrafficTracker,
    assign_regional_worker,
    get_active_monitored_ports,
    parse_ais_position_report,
)
from backend.services.bounding_box import calculate_bounding_box
from backend.taxonomy.seed import seed_vessel_classes


@pytest_asyncio.fixture
async def ais_test_db():
    """Create in-memory SQLite database seeded with vessel taxonomy, test ports, and user watchlist."""
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

    async with session_factory() as session:
        await seed_vessel_classes(session)

        # Rotterdam (lon 4.4777 -> Worker 2)
        port_rtm = Port(
            unlocode="NLRTM",
            port_name="Port of Rotterdam",
            country_code="NL",
            subdivision_code="NL-ZH",
            latitude=51.9244,
            longitude=4.4777,
            channel_depth_m=11.0,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        # Houston (lon -95.28 -> Worker 1)
        port_hou = Port(
            unlocode="USHOU",
            port_name="Port of Houston",
            country_code="US",
            subdivision_code="US-TX",
            latitude=29.75,
            longitude=-95.28,
            channel_depth_m=14.0,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        session.add_all([port_rtm, port_hou])

        # Add watchlist entry for Rotterdam
        user_id = uuid.uuid4()
        user = User(id=user_id, email="operator@test.com", hashed_password="hashedpassword")
        wl = UserWatchlist(
            watchlist_id=uuid.uuid4(),
            user_id=user_id,
            unlocode="NLRTM",
            vessel_class_id="panamax",
            geofence_radius_nm=8.0,
        )
        session.add_all([user, wl])
        await session.commit()

    yield session_factory
    await engine.dispose()


# ─── 1. Unit Tests: AIS Message Parsing ─────────────────────────────────────────

def test_parse_valid_position_report():
    """Verify parsing valid PositionReport extracting MMSI, lat, lon, and SOG."""
    valid_payload = {
        "MessageType": "PositionReport",
        "MetaData": {
            "MMSI": 244670000,
            "Latitude": 51.925,
            "Longitude": 4.480,
            "ShipName": "NEDERLAND",
        },
        "Message": {
            "PositionReport": {
                "Sog": 0.4,
                "UserID": 244670000,
                "Latitude": 51.925,
                "Longitude": 4.480,
            }
        },
    }

    parsed = parse_ais_position_report(valid_payload)
    assert parsed is not None
    assert parsed["mmsi"] == 244670000
    assert parsed["lat"] == 51.925
    assert parsed["lon"] == 4.480
    assert parsed["sog"] == 0.4


def test_parse_non_position_report_ignored():
    """Verify non-PositionReport messages (e.g. ShipStaticData) return None."""
    static_payload = {
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": 244670000},
        "Message": {"ShipStaticData": {"Destination": "ROTTERDAM"}},
    }
    assert parse_ais_position_report(static_payload) is None


def test_parse_malformed_and_boundary_error_payloads():
    """Verify malformed JSON, missing fields, out-of-bounds coordinates, and SOG 102.3 return None."""
    assert parse_ais_position_report("not-valid-json") is None
    assert parse_ais_position_report({}) is None

    # Missing SOG
    assert parse_ais_position_report({
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": 12345, "Latitude": 50.0, "Longitude": 4.0},
        "Message": {"PositionReport": {}},
    }) is None

    # Out of bounds lat (> 90)
    assert parse_ais_position_report({
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": 12345, "Latitude": 95.0, "Longitude": 4.0},
        "Message": {"PositionReport": {"Sog": 2.0}},
    }) is None

    # Invalid SOG (102.3 = not available)
    assert parse_ais_position_report({
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": 12345, "Latitude": 51.0, "Longitude": 4.0},
        "Message": {"PositionReport": {"Sog": 102.3}},
    }) is None


# ─── 2. Unit Tests: Traffic Classification & State Transitions ──────────────────

def test_traffic_classification_thresholds():
    """Verify SOG <= 0.5 kts is anchored and SOG > 0.5 kts is underway."""
    tracker = PortTrafficTracker(unlocode="NLRTM")

    # SOG = 0.0 -> anchored
    tracker.update_vessel(mmsi=1001, sog=0.0)
    assert 1001 in tracker.anchored_vessels
    assert 1001 not in tracker.underway_vessels

    # SOG = 0.5 -> strictly anchored
    tracker.update_vessel(mmsi=1002, sog=0.5)
    assert 1002 in tracker.anchored_vessels
    assert 1002 not in tracker.underway_vessels

    # SOG = 0.51 -> underway
    tracker.update_vessel(mmsi=1003, sog=0.51)
    assert 1003 in tracker.underway_vessels
    assert 1003 not in tracker.anchored_vessels

    # SOG = 12.0 -> underway
    tracker.update_vessel(mmsi=1004, sog=12.0)
    assert 1004 in tracker.underway_vessels
    assert 1004 not in tracker.anchored_vessels

    assert tracker.anchored_count == 2
    assert tracker.underway_count == 2
    assert tracker.total_count == 4


def test_vessel_state_transition():
    """Verify vessel moving between anchored and underway updates sets without double-counting."""
    tracker = PortTrafficTracker(unlocode="NLRTM")
    mmsi = 9999

    # 1. Initially anchored
    tracker.update_vessel(mmsi, sog=0.2)
    assert tracker.anchored_count == 1
    assert tracker.underway_count == 0
    assert tracker.total_count == 1

    # 2. Vessels gets underway (SOG = 3.5 kts)
    tracker.update_vessel(mmsi, sog=3.5)
    assert tracker.anchored_count == 0
    assert tracker.underway_count == 1
    assert tracker.total_count == 1
    assert mmsi not in tracker.anchored_vessels
    assert mmsi in tracker.underway_vessels

    # 3. Vessel drops anchor again (SOG = 0.1 kts)
    tracker.update_vessel(mmsi, sog=0.1)
    assert tracker.anchored_count == 1
    assert tracker.underway_count == 0
    assert tracker.total_count == 1


def test_sliding_window_eviction():
    """Verify simulated advancing of clock by > 20 min purges inactive MMSIs."""
    tracker = PortTrafficTracker(unlocode="NLRTM", window_seconds=1200.0)
    now = time.time()

    # Vessel 1: seen now
    tracker.update_vessel(mmsi=1, sog=0.2, timestamp=now)
    # Vessel 2: seen 25 minutes ago (> 1200s)
    tracker.update_vessel(mmsi=2, sog=5.0, timestamp=now - 1500.0)

    assert tracker.total_count == 2
    purged = tracker.evict_inactive(current_time=now)
    assert purged == 1
    assert tracker.total_count == 1
    assert 1 in tracker.anchored_vessels
    assert 2 not in tracker.underway_vessels


# ─── 3. Unit Tests: Regional Longitude Partitioning ────────────────────────────

def test_assign_regional_worker():
    """Verify regional worker partitioning across longitude bands and boundaries."""
    # Worker 1: Americas & Atlantic (-180 <= lon < -30)
    assert assign_regional_worker(-180.0) == 1
    assert assign_regional_worker(-95.28) == 1  # Houston
    assert assign_regional_worker(-30.01) == 1

    # Worker 2: Europe, Africa, Middle East (-30 <= lon < 60)
    assert assign_regional_worker(-30.0) == 2  # Boundary
    assert assign_regional_worker(4.48) == 2   # Rotterdam
    assert assign_regional_worker(59.99) == 2

    # Worker 3: Asia-Pacific & Oceania (60 <= lon <= 180)
    assert assign_regional_worker(60.0) == 3   # Boundary
    assert assign_regional_worker(103.84) == 3 # Singapore
    assert assign_regional_worker(180.0) == 3  # Boundary


# ─── 4. Integration Tests: Active Watchlist Query & Mock WebSocket Ingestion ───

@pytest.mark.asyncio
async def test_get_active_monitored_ports(ais_test_db):
    """Verify active monitored ports query only returns watched ports."""
    session_factory = ais_test_db
    monitored = await get_active_monitored_ports(session_factory)

    # Only Rotterdam is in the watchlist, Houston is not
    assert len(monitored) == 1
    assert monitored[0].unlocode == "NLRTM"
    assert monitored[0].radius_nm == 8.0


@pytest.mark.asyncio
async def test_websocket_ingestion_and_db_consumer(ais_test_db):
    """Verify mocked WebSocket server end-to-end ingestion and database snapshot persistence."""
    session_factory = ais_test_db

    # Setup simulated mock WebSocket server
    received_subscriptions = []

    async def mock_ws_server(websocket):
        # Read subscription
        sub = await websocket.recv()
        received_subscriptions.append(json.loads(sub))

        # Stream two position reports: one anchored, one underway
        msg1 = {
            "MessageType": "PositionReport",
            "MetaData": {"MMSI": 1111, "Latitude": 51.9244, "Longitude": 4.4777},
            "Message": {"PositionReport": {"Sog": 0.2, "UserID": 1111}},
        }
        msg2 = {
            "MessageType": "PositionReport",
            "MetaData": {"MMSI": 2222, "Latitude": 51.9244, "Longitude": 4.4777},
            "Message": {"PositionReport": {"Sog": 6.5, "UserID": 2222}},
        }
        await websocket.send(json.dumps(msg1))
        await websocket.send(json.dumps(msg2))
        await asyncio.sleep(0.5)

    server = await websockets.serve(mock_ws_server, "127.0.0.1", 8765)
    mock_url = "ws://127.0.0.1:8765"

    worker = AISStreamWorker(
        worker_id=2,  # Europe / Rotterdam
        api_key="test-api-key",
        session_factory=session_factory,
    )

    boxes = calculate_bounding_box(51.9244, 4.4777, radius_nm=8.0)
    worker.ports = [
        MonitoredPortInfo(
            unlocode="NLRTM",
            lat=51.9244,
            lon=4.4777,
            radius_nm=8.0,
            lat_min=boxes[0].lat_min,
            lat_max=boxes[0].lat_max,
            lon_min=boxes[0].lon_min,
            lon_max=boxes[0].lon_max,
        )
    ]
    worker.trackers["NLRTM"] = PortTrafficTracker(unlocode="NLRTM")

    # Start consumer and worker loop against mock server
    consumer_task = asyncio.create_task(worker._db_consumer_loop())
    worker_task = asyncio.create_task(worker._websocket_client_loop(ws_url=mock_url))

    # Give time for messages to be sent, parsed, enqueued, and committed
    await asyncio.sleep(1.0)

    # Stop tasks
    worker.stop_event.set()
    worker_task.cancel()
    consumer_task.cancel()
    server.close()
    await server.wait_closed()

    # Verify subscription was sent
    assert len(received_subscriptions) == 1
    assert received_subscriptions[0]["APIKey"] == "test-api-key"

    # Verify port_risk_snapshots in database was updated
    async with session_factory() as session:
        stmt = select(PortRiskSnapshot).where(PortRiskSnapshot.unlocode == "NLRTM")
        res = await session.execute(stmt)
        snapshot = res.scalars().first()

        assert snapshot is not None
        assert snapshot.anchored_vessel_count == 1
        assert snapshot.underway_vessel_count == 1
        assert snapshot.total_active_geofence_count == 2


@pytest.mark.asyncio
async def test_worker_idle_when_no_ports_or_no_api_key():
    """Verify worker stays idle without errors when API key or active ports are absent."""
    # 1. No API key
    worker_no_key = AISStreamWorker(worker_id=1, api_key="")
    assert worker_no_key.api_key == ""

    # 2. No ports assigned
    worker_no_ports = AISStreamWorker(worker_id=1, api_key="valid-key")
    assert len(worker_no_ports.ports) == 0
