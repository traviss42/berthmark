"""Dynamic point-offset bounding box generation for AISStream.io geofencing."""

import math
from dataclasses import dataclass
from typing import Any

POLAR_LATITUDE_CAP = 89.9
MAX_LONGITUDE_DELTA = 180.0


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Bounding box defined by minimum and maximum latitude/longitude coordinates."""

    lat_min: float
    lon_min: float
    lat_max: float
    lon_max: float

    def to_aisstream(self) -> list[list[float]]:
        """Return coordinate pair matching AISStream API specification: [[lat_min, lon_min], [lat_max, lon_max]]."""
        return [
            [round(self.lat_min, 6), round(self.lon_min, 6)],
            [round(self.lat_max, 6), round(self.lon_max, 6)],
        ]


def calculate_bounding_box(
    lat: float,
    lon: float,
    radius_nm: float | None = None,
    delta_deg: float = 0.10,
) -> list[BoundingBox]:
    """Calculate point-offset bounding box(es) around (lat, lon) with antimeridian and polar safety.

    Args:
        lat: Latitude in degrees [-90.0, 90.0].
        lon: Longitude in degrees [-180.0, 180.0].
        radius_nm: Optional geofence radius in nautical miles.
        delta_deg: Base angular offset in degrees (default 0.10 deg ≈ 6 NM).

    Returns:
        List of 1 or 2 BoundingBox objects (split into 2 if crossing the antimeridian).

    Raises:
        ValueError: If coordinates or radius/delta parameters are invalid.
    """
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitude must be within [-90.0, 90.0], got {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Longitude must be within [-180.0, 180.0], got {lon}")
    if delta_deg <= 0.0:
        raise ValueError(f"delta_deg must be > 0.0, got {delta_deg}")
    if radius_nm is not None and radius_nm <= 0.0:
        raise ValueError(f"radius_nm must be > 0.0, got {radius_nm}")

    # Prevent division by zero near poles by capping cosine evaluation latitude at 89.9 deg
    clamped_lat_for_cos = min(abs(lat), POLAR_LATITUDE_CAP)
    cos_lat = math.cos(math.radians(clamped_lat_for_cos))

    if radius_nm is not None:
        delta_lat = radius_nm / 60.0
        delta_lon = radius_nm / (60.0 * cos_lat)
    else:
        delta_lat = delta_deg
        delta_lon = delta_deg / cos_lat

    # Cap delta_lon at 180.0 to prevent full-globe wrap-around at extreme poles
    delta_lon = min(delta_lon, MAX_LONGITUDE_DELTA)

    # Latitude clamping to [-90.0, 90.0]
    lat_min = max(-90.0, lat - delta_lat)
    lat_max = min(90.0, lat + delta_lat)

    raw_lon_min = lon - delta_lon
    raw_lon_max = lon + delta_lon

    # Case 1: Eastward overflow across antimeridian (+180 deg)
    if raw_lon_max > 180.0:
        box1 = BoundingBox(
            lat_min=lat_min,
            lon_min=raw_lon_min,
            lat_max=lat_max,
            lon_max=180.0,
        )
        box2 = BoundingBox(
            lat_min=lat_min,
            lon_min=-180.0,
            lat_max=lat_max,
            lon_max=raw_lon_max - 360.0,
        )
        return [box1, box2]

    # Case 2: Westward underflow across antimeridian (-180 deg)
    if raw_lon_min < -180.0:
        box1 = BoundingBox(
            lat_min=lat_min,
            lon_min=raw_lon_min + 360.0,
            lat_max=lat_max,
            lon_max=180.0,
        )
        box2 = BoundingBox(
            lat_min=lat_min,
            lon_min=-180.0,
            lat_max=lat_max,
            lon_max=raw_lon_max,
        )
        return [box1, box2]

    # Normal case: entirely within [-180.0, 180.0]
    return [
        BoundingBox(
            lat_min=lat_min,
            lon_min=raw_lon_min,
            lat_max=lat_max,
            lon_max=raw_lon_max,
        )
    ]


def format_aisstream_payload(
    bounding_boxes: list[BoundingBox] | list[list[BoundingBox]],
) -> dict[str, list[list[list[float]]]]:
    """Format bounding boxes into the JSON subscription payload required by AISStream.io."""
    flattened: list[list[list[float]]] = []
    for item in bounding_boxes:
        if isinstance(item, BoundingBox):
            flattened.append(item.to_aisstream())
        elif isinstance(item, list):
            for sub_item in item:
                if isinstance(sub_item, BoundingBox):
                    flattened.append(sub_item.to_aisstream())
                elif isinstance(sub_item, list):
                    flattened.append(sub_item)
    return {"BoundingBoxes": flattened}


def generate_port_bounding_boxes(
    ports: list[dict[str, Any] | tuple[float, float] | tuple[float, float, float]],
    default_radius_nm: float | None = None,
) -> list[list[list[float]]]:
    """Generate flattened list of AISStream bounding box coordinate pairs for multiple ports."""
    boxes: list[list[list[float]]] = []
    for p in ports:
        if isinstance(p, dict):
            lat = float(p.get("lat") or p.get("latitude"))
            lon = float(p.get("lon") or p.get("longitude"))
            radius = p.get("geofenceRadiusNm") or p.get("geofence_radius_nm") or default_radius_nm
            if radius is not None:
                radius = float(radius)
        elif isinstance(p, (tuple, list)):
            lat = float(p[0])
            lon = float(p[1])
            radius = float(p[2]) if len(p) > 2 else default_radius_nm
        else:
            continue

        calculated = calculate_bounding_box(lat, lon, radius_nm=radius)
        for box in calculated:
            boxes.append(box.to_aisstream())

    return boxes
