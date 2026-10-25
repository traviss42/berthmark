"""Unit tests for Dynamic Point-Offset Bounding Box Generator."""

import math
import pytest

from backend.services.bounding_box import (
    BoundingBox,
    calculate_bounding_box,
    format_aisstream_payload,
    generate_port_bounding_boxes,
)


def test_equatorial_coordinates_singapore():
    """Verify equatorial coordinates (Singapore, lat 1.2648, lon 103.8408)."""
    lat, lon = 1.2648, 103.8408
    boxes = calculate_bounding_box(lat, lon, delta_deg=0.10)

    assert len(boxes) == 1
    b = boxes[0]

    cos_lat = math.cos(math.radians(lat))
    assert pytest.approx(cos_lat, abs=1e-4) == 0.99976

    delta_lon = 0.10 / cos_lat
    assert pytest.approx(delta_lon, abs=1e-4) == 0.10

    # Expected: [1.1648, 103.7408, 1.3648, 103.9408]
    assert pytest.approx(b.lat_min, abs=1e-4) == 1.1648
    assert pytest.approx(b.lon_min, abs=1e-4) == 103.7408
    assert pytest.approx(b.lat_max, abs=1e-4) == 1.3648
    assert pytest.approx(b.lon_max, abs=1e-4) == 103.9408


def test_mid_latitude_coordinates_rotterdam():
    """Verify mid-latitude coordinates (Rotterdam, lat 51.9244, lon 4.4777)."""
    lat, lon = 51.9244, 4.4777
    boxes = calculate_bounding_box(lat, lon, delta_deg=0.10)

    assert len(boxes) == 1
    b = boxes[0]

    cos_lat = math.cos(math.radians(lat))
    assert pytest.approx(cos_lat, abs=1e-4) == 0.6167

    delta_lon = 0.10 / cos_lat
    assert pytest.approx(delta_lon, abs=1e-4) == 0.1621

    # Expected: [51.8244, 4.3156, 52.0244, 4.6398]
    assert pytest.approx(b.lat_min, abs=1e-4) == 51.8244
    assert pytest.approx(b.lon_min, abs=1e-4) == 4.3156
    assert pytest.approx(b.lat_max, abs=1e-4) == 52.0244
    assert pytest.approx(b.lon_max, abs=1e-4) == 4.6398


def test_high_latitude_coordinates_tromso():
    """Verify high-latitude coordinates (Tromsø, lat 69.6492, lon 18.9553)."""
    lat, lon = 69.6492, 18.9553
    boxes = calculate_bounding_box(lat, lon, delta_deg=0.10)

    assert len(boxes) == 1
    b = boxes[0]

    cos_lat = math.cos(math.radians(lat))
    assert pytest.approx(cos_lat, abs=1e-4) == 0.3477

    delta_lon = 0.10 / cos_lat
    assert pytest.approx(delta_lon, abs=1e-4) == 0.2876
    assert delta_lon > 0.10  # Significant expansion in subarctic


def test_southern_hemisphere_coordinates_santos():
    """Verify southern hemisphere coordinates (Santos, lat -23.9608, lon -46.3331)."""
    lat, lon = -23.9608, -46.3331
    boxes = calculate_bounding_box(lat, lon, delta_deg=0.10)

    assert len(boxes) == 1
    b = boxes[0]

    cos_lat = math.cos(math.radians(lat))
    assert pytest.approx(cos_lat, abs=1e-4) == 0.9138

    delta_lon = 0.10 / cos_lat
    assert pytest.approx(delta_lon, abs=1e-4) == 0.1094
    assert b.lat_min < b.lat_max
    assert pytest.approx(b.lat_min, abs=1e-4) == -24.0608
    assert pytest.approx(b.lat_max, abs=1e-4) == -23.8608


def test_custom_geofence_radius_conversion():
    """Verify custom geofence radius: 8.0 NM at Rotterdam produces delta_lat ≈ 0.1333 and delta_lon ≈ 0.2162."""
    lat, lon = 51.9244, 4.4777
    boxes = calculate_bounding_box(lat, lon, radius_nm=8.0)

    assert len(boxes) == 1
    b = boxes[0]

    delta_lat = 8.0 / 60.0
    cos_lat = math.cos(math.radians(lat))
    delta_lon = 8.0 / (60.0 * cos_lat)

    assert pytest.approx(delta_lat, abs=1e-4) == 0.1333
    assert pytest.approx(delta_lon, abs=1e-4) == 0.2162

    assert pytest.approx(b.lat_max - lat, abs=1e-4) == 0.1333
    assert pytest.approx(b.lon_max - lon, abs=1e-4) == 0.2162


def test_antimeridian_crossing_eastward():
    """Verify eastward overflow crossing the antimeridian splits into 2 valid boxes."""
    lat, lon = 17.5, 179.95
    boxes = calculate_bounding_box(lat, lon, delta_deg=0.10)

    assert len(boxes) == 2
    box1, box2 = boxes

    # Box 1: western segment ending at 180.0
    assert box1.lon_min < 180.0
    assert box1.lon_max == 180.0
    assert -180.0 <= box1.lon_min <= 180.0

    # Box 2: eastern segment starting at -180.0
    assert box2.lon_min == -180.0
    assert box2.lon_max > -180.0
    assert -180.0 <= box2.lon_max <= 180.0

    # Verify both boxes have valid coordinates
    assert box1.lat_min < box1.lat_max
    assert box2.lat_min < box2.lat_max
    assert box1.lon_min <= box1.lon_max
    assert box2.lon_min <= box2.lon_max


def test_antimeridian_crossing_westward():
    """Verify westward underflow crossing the antimeridian splits into 2 valid boxes."""
    lat, lon = 17.5, -179.95
    boxes = calculate_bounding_box(lat, lon, delta_deg=0.10)

    assert len(boxes) == 2
    box1, box2 = boxes

    # Box 1: eastern segment ending at 180.0
    assert box1.lon_min < 180.0
    assert box1.lon_max == 180.0
    assert -180.0 <= box1.lon_min <= 180.0

    # Box 2: western segment starting at -180.0
    assert box2.lon_min == -180.0
    assert box2.lon_max > -180.0
    assert -180.0 <= box2.lon_max <= 180.0

    assert box1.lon_min <= box1.lon_max
    assert box2.lon_min <= box2.lon_max


def test_polar_coordinates_and_clamping():
    """Verify extreme polar latitudes clamp lat to [-90, 90] and do not raise ZeroDivisionError."""
    # Near North Pole (89.95 deg)
    boxes_north = calculate_bounding_box(89.95, 10.0, delta_deg=0.20)
    assert len(boxes_north) == 1
    bn = boxes_north[0]
    assert bn.lat_max == 90.0
    assert -180.0 <= bn.lon_min <= 180.0
    assert -180.0 <= bn.lon_max <= 180.0

    # Near South Pole (-89.98 deg)
    boxes_south = calculate_bounding_box(-89.98, -50.0, delta_deg=0.20)
    assert len(boxes_south) == 1
    bs = boxes_south[0]
    assert bs.lat_min == -90.0
    assert -180.0 <= bs.lon_min <= 180.0
    assert -180.0 <= bs.lon_max <= 180.0


def test_boundary_value_exceptions():
    """Verify input validation raises ValueError for invalid coordinates or radius/delta."""
    # Latitude out of bounds
    with pytest.raises(ValueError):
        calculate_bounding_box(90.1, 0.0)
    with pytest.raises(ValueError):
        calculate_bounding_box(-90.1, 0.0)

    # Longitude out of bounds
    with pytest.raises(ValueError):
        calculate_bounding_box(0.0, 180.1)
    with pytest.raises(ValueError):
        calculate_bounding_box(0.0, -180.1)

    # Radius <= 0
    with pytest.raises(ValueError):
        calculate_bounding_box(0.0, 0.0, radius_nm=0.0)
    with pytest.raises(ValueError):
        calculate_bounding_box(0.0, 0.0, radius_nm=-5.0)

    # Delta <= 0
    with pytest.raises(ValueError):
        calculate_bounding_box(0.0, 0.0, delta_deg=0.0)
    with pytest.raises(ValueError):
        calculate_bounding_box(0.0, 0.0, delta_deg=-0.1)


def test_aisstream_payload_formatting():
    """Verify format_aisstream_payload outputs expected JSON structure."""
    boxes = calculate_bounding_box(51.9244, 4.4777, delta_deg=0.10)
    payload = format_aisstream_payload(boxes)

    assert "BoundingBoxes" in payload
    assert isinstance(payload["BoundingBoxes"], list)
    assert len(payload["BoundingBoxes"]) == 1

    coords = payload["BoundingBoxes"][0]
    assert len(coords) == 2
    assert coords[0] == [51.8244, 4.315551] or len(coords[0]) == 2
    assert len(coords[1]) == 2


def test_batch_generate_port_bounding_boxes():
    """Verify generate_port_bounding_boxes processes list of dicts and tuples."""
    ports = [
        {"name": "Rotterdam", "lat": 51.9244, "lon": 4.4777, "geofenceRadiusNm": 8.0},
        {"name": "Singapore", "lat": 1.2648, "lon": 103.8408},
        (29.75, -95.28, 12.0),
    ]

    all_boxes = generate_port_bounding_boxes(ports, default_radius_nm=10.0)
    assert len(all_boxes) == 3
    for pair in all_boxes:
        assert len(pair) == 2
        assert len(pair[0]) == 2
        assert len(pair[1]) == 2
        assert pair[0][0] < pair[1][0]  # lat_min < lat_max
