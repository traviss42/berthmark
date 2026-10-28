"""AISStream WebSocket ingestion worker and real-time traffic classification engine.

Subscribes to AISStream.io position reports partitioned across three regional worker pools,
classifies vessels into anchored (SOG <= 0.5 kts) and underway (SOG > 0.5 kts), buffers
updates via asyncio.Queue, and writes traffic counts to port_risk_snapshots.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
import websockets
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.database import get_session_factory
from backend.models import Port, PortRiskSnapshot, UserWatchlist, utc_now
from backend.services.bounding_box import calculate_bounding_box
from backend.services.congestion import update_port_traffic_baseline_from_observation

logger = logging.getLogger(__name__)

# Constants
AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"
DEFAULT_WINDOW_SECONDS = 1200.0  # 20 minutes sliding window
SOG_ANCHORED_THRESHOLD = 0.5  # SOG <= 0.5 is anchored, > 0.5 is underway
SOG_INVALID_VALUE = 102.3  # AIS specification "not available" marker
MAX_RECONNECT_DELAY = 60.0
INITIAL_RECONNECT_DELAY = 1.0


def assign_regional_worker(longitude: float) -> int:
    """Assign longitude to regional worker partition (1, 2, or 3).

    Partitions:
        Worker 1 (Americas & Atlantic): -180.0 <= lon < -30.0
        Worker 2 (Europe, Africa & Middle East): -30.0 <= lon < +60.0
        Worker 3 (Asia-Pacific & Oceania): +60.0 <= lon <= +180.0

    Boundaries:
        -30.0 -> Worker 2
        +60.0 -> Worker 3
        -180.0 -> Worker 1
        +180.0 -> Worker 3
    """
    if longitude < -30.0:
        return 1
    elif longitude < 60.0:
        return 2
    else:
        return 3


@dataclass(frozen=True, slots=True)
class MonitoredPortInfo:
    """Active monitored port metadata and bounding box bounds."""

    unlocode: str
    lat: float
    lon: float
    radius_nm: float
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def contains_point(self, lat: float, lon: float) -> bool:
        """Check if coordinates fall within this port's bounding box."""
        return (
            self.lat_min <= lat <= self.lat_max
            and self.lon_min <= lon <= self.lon_max
        )


@dataclass
class PortTrafficTracker:
    """In-memory sliding window traffic classifier for a monitored port."""

    unlocode: str
    window_seconds: float = DEFAULT_WINDOW_SECONDS
    anchored_vessels: dict[int, float] = field(default_factory=dict)
    underway_vessels: dict[int, float] = field(default_factory=dict)

    def update_vessel(self, mmsi: int, sog: float, timestamp: float | None = None) -> bool:
        """Classify and record a vessel ping.

        Returns:
            True if vessel was updated, False if SOG was invalid.
        """
        if sog < 0.0 or sog >= SOG_INVALID_VALUE:
            return False

        ts = timestamp if timestamp is not None else time.time()

        if sog <= SOG_ANCHORED_THRESHOLD:
            # Stationary / Anchored: strictly SOG <= 0.5 kts
            self.underway_vessels.pop(mmsi, None)
            self.anchored_vessels[mmsi] = ts
        else:
            # Underway: SOG > 0.5 kts
            self.anchored_vessels.pop(mmsi, None)
            self.underway_vessels[mmsi] = ts

        return True

    def evict_inactive(self, current_time: float | None = None) -> int:
        """Purge vessels with no reports within the sliding window. Returns purged count."""
        now = current_time if current_time is not None else time.time()
        cutoff = now - self.window_seconds

        purged = 0
        for mmsi, ts in list(self.anchored_vessels.items()):
            if ts < cutoff:
                del self.anchored_vessels[mmsi]
                purged += 1

        for mmsi, ts in list(self.underway_vessels.items()):
            if ts < cutoff:
                del self.underway_vessels[mmsi]
                purged += 1

        return purged

    @property
    def anchored_count(self) -> int:
        return len(self.anchored_vessels)

    @property
    def underway_count(self) -> int:
        return len(self.underway_vessels)

    @property
    def total_count(self) -> int:
        return len(self.anchored_vessels) + len(self.underway_vessels)


@dataclass(frozen=True, slots=True)
class TrafficSnapshotUpdate:
    """Snapshot update item transferred from ingestion queue to DB consumer."""

    unlocode: str
    anchored_count: int
    underway_count: int
    total_count: int


def parse_ais_position_report(raw_data: str | bytes | bytearray | dict[str, Any]) -> dict[str, Any] | None:
    """Parse and validate incoming WebSocket message into normalized position report.

    Returns:
        Dict with keys {'mmsi', 'lat', 'lon', 'sog'} or None if invalid or non-position report.
    """
    try:
        if isinstance(raw_data, (bytes, bytearray)):
            raw_data = raw_data.decode("utf-8", errors="ignore")
        data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    msg_type = data.get("MessageType")
    if msg_type != "PositionReport":
        return None

    meta = data.get("MetaData") or {}
    msg_body = data.get("Message", {}).get("PositionReport") or {}

    mmsi = meta.get("MMSI") or msg_body.get("UserID")
    lat = meta.get("Latitude") if meta.get("Latitude") is not None else msg_body.get("Latitude")
    lon = meta.get("Longitude") if meta.get("Longitude") is not None else msg_body.get("Longitude")
    sog = msg_body.get("Sog")

    if mmsi is None or lat is None or lon is None or sog is None:
        return None

    try:
        mmsi_int = int(mmsi)
        lat_float = float(lat)
        lon_float = float(lon)
        sog_float = float(sog)
    except (ValueError, TypeError):
        return None

    # Validate coordinate boundaries
    if not (-90.0 <= lat_float <= 90.0) or not (-180.0 <= lon_float <= 180.0):
        return None

    # Ignore invalid SOG error codes
    if sog_float < 0.0 or sog_float >= SOG_INVALID_VALUE:
        return None

    return {
        "mmsi": mmsi_int,
        "lat": lat_float,
        "lon": lon_float,
        "sog": sog_float,
    }


async def get_active_monitored_ports(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[MonitoredPortInfo]:
    """Query user_watchlists joined with ports for active ports and compute bounding boxes."""
    async with session_factory() as session:
        stmt = (
            select(
                Port.unlocode,
                Port.latitude,
                Port.longitude,
                func.coalesce(UserWatchlist.geofence_radius_nm, 8.0).label("radius_nm"),
            )
            .join(UserWatchlist, UserWatchlist.unlocode == Port.unlocode)
            .distinct()
        )
        result = await session.execute(stmt)
        rows = result.all()

    monitored: list[MonitoredPortInfo] = []
    for row in rows:
        unlocode, lat, lon, radius = row[0], float(row[1]), float(row[2]), float(row[3])
        boxes = calculate_bounding_box(lat, lon, radius_nm=radius)
        # Use primary bounding box
        b = boxes[0]
        monitored.append(
            MonitoredPortInfo(
                unlocode=unlocode,
                lat=lat,
                lon=lon,
                radius_nm=radius,
                lat_min=b.lat_min,
                lat_max=b.lat_max,
                lon_min=b.lon_min,
                lon_max=b.lon_max,
            )
        )

    return monitored


class AISStreamWorker:
    """Regional worker managing WebSocket streaming, in-memory traffic classification, and DB sync."""

    def __init__(
        self,
        worker_id: int,
        api_key: str | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        queue_maxsize: int = 10000,
    ) -> None:
        self.worker_id = worker_id
        self.api_key = api_key if api_key is not None else os.getenv("AISSTREAM_API_KEY", "").strip()
        self.session_factory = session_factory or get_session_factory()
        self.window_seconds = window_seconds
        self.queue: asyncio.Queue[TrafficSnapshotUpdate] = asyncio.Queue(maxsize=queue_maxsize)
        self.ports: list[MonitoredPortInfo] = []
        self.trackers: dict[str, PortTrafficTracker] = {}
        self.stop_event = asyncio.Event()
        self.ports_updated_event = asyncio.Event()
        self.is_connected = False
        self._consumer_task: asyncio.Task | None = None
        self._worker_task: asyncio.Task | None = None

    def set_monitored_ports(self, all_ports: list[MonitoredPortInfo]) -> None:
        """Filter ports belonging to this worker's regional partition (or all if worker_id=0)."""
        if self.worker_id == 0:
            self.ports = list(all_ports)
        else:
            self.ports = [p for p in all_ports if assign_regional_worker(p.lon) == self.worker_id]
        for p in self.ports:
            if p.unlocode not in self.trackers:
                self.trackers[p.unlocode] = PortTrafficTracker(
                    unlocode=p.unlocode, window_seconds=self.window_seconds
                )
        self.ports_updated_event.set()

    def build_subscription_payload(self) -> dict[str, Any]:
        """Construct AISStream.io subscription message with bounding boxes for active ports."""
        bounding_boxes: list[list[list[float]]] = []
        for port in self.ports:
            boxes = calculate_bounding_box(port.lat, port.lon, radius_nm=port.radius_nm)
            for b in boxes:
                bounding_boxes.append(b.to_aisstream())

        return {
            "APIKey": self.api_key,
            "BoundingBoxes": bounding_boxes,
            "FilterMessageTypes": ["PositionReport"],
        }

    def process_incoming_report(self, parsed: dict[str, Any], timestamp: float | None = None) -> None:
        """Match incoming report to monitored port geofences and enqueue traffic updates."""
        lat = parsed["lat"]
        lon = parsed["lon"]
        mmsi = parsed["mmsi"]
        sog = parsed["sog"]

        for port in self.ports:
            if port.contains_point(lat, lon):
                tracker = self.trackers.get(port.unlocode)
                if tracker:
                    changed = tracker.update_vessel(mmsi, sog, timestamp=timestamp)
                    if changed:
                        update = TrafficSnapshotUpdate(
                            unlocode=port.unlocode,
                            anchored_count=tracker.anchored_count,
                            underway_count=tracker.underway_count,
                            total_count=tracker.total_count,
                        )
                        try:
                            self.queue.put_nowait(update)
                        except asyncio.QueueFull:
                            logger.warning("AIS update queue full for worker %s", self.worker_id)

    async def _db_consumer_loop(self) -> None:
        """Background loop dequeuing traffic updates and writing to port_risk_snapshots."""
        while not self.stop_event.is_set():
            try:
                update = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            # Attempt database write with retries on SQLite locking
            for attempt in range(5):
                try:
                    async with self.session_factory() as session:
                        stmt = select(PortRiskSnapshot).where(
                            PortRiskSnapshot.unlocode == update.unlocode
                        )
                        result = await session.execute(stmt)
                        snapshots = result.scalars().all()
                        if snapshots:
                            for s in snapshots:
                                s.anchored_vessel_count = update.anchored_count
                                s.underway_vessel_count = update.underway_count
                                s.total_active_geofence_count = update.total_count
                                s.updated_at = utc_now()
                        else:
                            # Query watched vessel classes for this port
                            w_stmt = select(UserWatchlist.vessel_class_id).where(
                                UserWatchlist.unlocode == update.unlocode
                            )
                            w_res = await session.execute(w_stmt)
                            vessel_classes = set(w_res.scalars().all())
                            vessel_classes.update({"panamax", "neoPanamax"})

                            for vc in vessel_classes:
                                new_snapshot = PortRiskSnapshot(
                                    snapshot_id=uuid.uuid4(),
                                    unlocode=update.unlocode,
                                    vessel_class_id=vc,
                                    anchored_vessel_count=update.anchored_count,
                                    underway_vessel_count=update.underway_count,
                                    total_active_geofence_count=update.total_count,
                                    updated_at=utc_now(),
                                )
                                session.add(new_snapshot)
                        await session.commit()

                        # Accumulate real observation into rolling baseline
                        await update_port_traffic_baseline_from_observation(
                            session,
                            update.unlocode,
                            anchored_count=update.anchored_count,
                            underway_count=update.underway_count,
                            total_count=update.total_count,
                        )
                    self.queue.task_done()
                    break
                except Exception as exc:
                    if "locked" in str(exc).lower() and attempt < 4:
                        await asyncio.sleep(0.05 * (2 ** attempt))
                        continue
                    logger.warning("DB write failed for %s (attempt %s): %s", update.unlocode, attempt, exc)
                    self.queue.task_done()
                    break

    async def _websocket_client_loop(self, ws_url: str = AISSTREAM_URL) -> None:
        """Manage WebSocket connection, subscription, ping/pong, and reconnection backoff."""
        reconnect_delay = INITIAL_RECONNECT_DELAY

        while not self.stop_event.is_set():
            # If no active ports in partition or no API key, remain idle
            if not self.ports or not self.api_key:
                await asyncio.sleep(2.0)
                continue

            try:
                subscription_payload = self.build_subscription_payload()
                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                ) as ws:
                    self.is_connected = True
                    reconnect_delay = INITIAL_RECONNECT_DELAY
                    logger.info("Worker %s connected to AISStream.io", self.worker_id)

                    # Send subscription
                    await ws.send(json.dumps(subscription_payload))

                    while not self.stop_event.is_set():
                        if self.ports_updated_event.is_set():
                            self.ports_updated_event.clear()
                            try:
                                payload = self.build_subscription_payload()
                                await ws.send(json.dumps(payload))
                                logger.info("Worker %s updated AIS subscription for %d ports", self.worker_id, len(self.ports))
                            except Exception as exc:
                                logger.warning("Failed to send updated subscription: %s", exc)

                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                            parsed = parse_ais_position_report(msg)
                            if parsed:
                                self.process_incoming_report(parsed)
                        except asyncio.TimeoutError:
                            # Periodic sliding window cleanup
                            for tracker in self.trackers.values():
                                tracker.evict_inactive()
                            continue

            except (websockets.ConnectionClosed, OSError, Exception) as exc:
                self.is_connected = False
                if self.stop_event.is_set():
                    break
                logger.warning("Worker %s disconnected (%s). Reconnecting in %.1fs...", self.worker_id, exc, reconnect_delay)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, MAX_RECONNECT_DELAY)

    async def start(self) -> None:
        """Start worker background loops."""
        self.stop_event.clear()
        self._consumer_task = asyncio.create_task(self._db_consumer_loop())
        self._worker_task = asyncio.create_task(self._websocket_client_loop())

    async def stop(self) -> None:
        """Gracefully stop worker and drain pending queue items."""
        self.stop_event.set()
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
