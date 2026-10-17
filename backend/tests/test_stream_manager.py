"""Unit tests for persistent AISStream WebSocket manager and warm-up lifecycle."""

import asyncio
import json
import time
import pytest
from app.clients.ais_stream_manager import AISStreamManager, calculate_bounding_box


def test_calculate_bounding_box():
    """Verify bounding box calculation generates valid min/max coordinates."""
    bbox = calculate_bounding_box(lat=51.92, lon=4.48, radius_nm=8.0)
    assert len(bbox) == 2
    sw, ne = bbox
    assert sw[0] < ne[0]
    assert sw[1] < ne[1]
    assert sw[0] < 51.92 < ne[0]
    assert sw[1] < 4.48 < ne[1]


def test_stream_manager_register_and_unregister():
    """Verify ports are registered, geofenced, and aliased by LOCODE."""
    mgr = AISStreamManager(api_key="mock-key")
    ports = [
        {"id": "port-nlrtm", "locode": "NLRTM", "lat": 51.92, "lon": 4.48, "geofence": 8.0},
        {"id": "port-sgkep", "locode": "SGKEP", "lat": 1.26, "lon": 103.83, "geofence": 8.0},
    ]
    mgr.register_ports(ports)

    assert mgr.ports_monitored_count == 2
    assert "port-nlrtm" in mgr._ports
    assert "NLRTM" in mgr._ports
    assert "port-sgkep" in mgr._ports
    assert "SGKEP" in mgr._ports

    mgr.unregister_port("port-nlrtm", "NLRTM")
    assert mgr.ports_monitored_count == 1
    assert "port-nlrtm" not in mgr._ports
    assert "NLRTM" not in mgr._ports
    assert "port-sgkep" in mgr._ports


def test_stream_manager_warmup_lifecycle():
    """Verify warm-up state and remaining seconds calculation."""
    mgr = AISStreamManager(api_key="mock-key")
    mgr._is_warming_up = True
    mgr._warmup_start_time = time.time() - 5.0
    mgr._warmup_duration_sec = 20.0

    assert mgr.is_warming_up is True
    assert 14 <= mgr.warmup_seconds_remaining <= 15

    status = mgr.get_status()
    assert status["isWarmingUp"] is True
    assert "Initializing live AIS vessel telemetry" in status["message"]

    # Fast-forward past warm-up duration
    mgr._warmup_start_time = time.time() - 25.0
    assert mgr.is_warming_up is False
    assert mgr.warmup_seconds_remaining == 0

    status_ready = mgr.get_status()
    assert status_ready["isWarmingUp"] is False
    assert status_ready["message"] == "Live AIS vessel telemetry active"


def test_stream_manager_message_routing_and_counting():
    """Verify incoming AIS messages update in-memory stationary and moving vessel counts."""
    mgr = AISStreamManager(api_key="mock-key")
    mgr.register_ports([
        {"id": "port-nlrtm", "locode": "NLRTM", "lat": 51.92, "lon": 4.48, "geofence": 8.0},
    ])

    # 1. Vessel 1001: Stationary (SOG = 0.2 kn)
    raw_stationary = json.dumps({
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": 1001, "latitude": 51.92, "longitude": 4.48},
        "Message": {"PositionReport": {"Latitude": 51.92, "Longitude": 4.48, "Sog": 0.2, "NavigationalStatus": 1}},
    })
    mgr._process_raw_message(raw_stationary)

    # 2. Vessel 2002: Moving (SOG = 11.5 kn)
    raw_moving = json.dumps({
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": 2002, "latitude": 51.91, "longitude": 4.49},
        "Message": {"PositionReport": {"Latitude": 51.91, "Longitude": 4.49, "Sog": 11.5, "NavigationalStatus": 0}},
    })
    mgr._process_raw_message(raw_moving)

    counts = mgr.get_port_counts("port-nlrtm", "NLRTM")
    assert counts is not None
    active, stationary, moving = counts
    assert active == 2
    assert stationary == 1
    assert moving == 1

    # 3. Message outside geofence (should not affect Rotterdam)
    raw_outside = json.dumps({
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": 3003, "latitude": 30.0, "longitude": 120.0},
        "Message": {"PositionReport": {"Latitude": 30.0, "Longitude": 120.0, "Sog": 5.0}},
    })
    mgr._process_raw_message(raw_outside)

    counts_after = mgr.get_port_counts("port-nlrtm")
    assert counts_after == (2, 1, 1)


def test_stream_manager_departed_vessel_timeout():
    """Verify vessels that have stopped transmitting inside geofence > timeout are pruned."""
    mgr = AISStreamManager(api_key="mock-key", departed_timeout_seconds=60.0)
    mgr.register_ports([
        {"id": "port-nlrtm", "locode": "NLRTM", "lat": 51.92, "lon": 4.48, "geofence": 8.0},
    ])

    now = time.time()
    # Add active vessel (seen 10s ago)
    mgr._vessels["port-nlrtm"][111] = {"mmsi": 111, "sog": 0.1, "last_seen": now - 10.0}
    # Add departed vessel (seen 90s ago, > 60s timeout)
    mgr._vessels["port-nlrtm"][222] = {"mmsi": 222, "sog": 0.1, "last_seen": now - 90.0}

    # Verify counts before explicit prune only counts active (< 60s)
    counts = mgr.get_port_counts("port-nlrtm")
    assert counts == (1, 1, 0)

    # Run prune and check physical dict removal
    mgr._prune_departed_vessels()
    assert 111 in mgr._vessels["port-nlrtm"]
    assert 222 not in mgr._vessels["port-nlrtm"]
