"""Persistent background AISStream WebSocket stream manager with live vessel tracking.

Maintains a continuous connection to AISStream.io, route position reports
to monitored port geofences, tracks live stationary/moving vessels in memory,
and manages the initial warm-up lifecycle.
"""

import asyncio
import json
import logging
import math
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import websockets

from app.config import get_settings

logger = logging.getLogger(__name__)


def calculate_bounding_box(lat: float, lon: float, radius_nm: float = 8.0) -> List[List[float]]:
    """Calculate [[lat_min, lon_min], [lat_max, lon_max]] for an AIS geofence."""
    lat_delta = radius_nm / 60.0
    cos_lat = max(0.1, math.cos(math.radians(lat)))
    lon_delta = radius_nm / (60.0 * cos_lat)
    return [
        [round(lat - lat_delta, 4), round(lon - lon_delta, 4)],
        [round(lat + lat_delta, 4), round(lon + lon_delta, 4)],
    ]


class AISStreamManager:
    """Manages a single persistent WebSocket connection to AISStream for all monitored ports."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        ws_url: Optional[str] = None,
        departed_timeout_seconds: float = 1800.0,  # 30 minutes without ping = departed port
    ):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.AISSTREAM_API_KEY
        self.ws_url = ws_url or getattr(settings, "AISSTREAM_WS_URL", "wss://stream.aisstream.io/v0/stream")
        self.departed_timeout_seconds = departed_timeout_seconds

        # Monitored ports: port_key -> metadata with bounding box limits
        self._ports: Dict[str, Dict[str, Any]] = {}
        # Live vessel tracking: port_key -> { mmsi -> {sog, lat, lon, last_seen, nav_status} }
        self._vessels: Dict[str, Dict[int, Dict[str, Any]]] = {}

        # Connection and lifecycle state for 3 concurrent WebSocket workers
        self._running: bool = False
        self._worker_connected: Dict[int, bool] = {i: False for i in range(3)}
        self._is_warming_up: bool = False
        self._warmup_start_time: float = 0.0
        self._warmup_duration_sec: float = 20.0
        self._warmup_task: Optional[asyncio.Task] = None
        self._listen_tasks: List[asyncio.Task] = []
        self._resubscribe_events: List[asyncio.Event] = [asyncio.Event() for _ in range(3)]

    @property
    def is_warming_up(self) -> bool:
        if not self._is_warming_up:
            return False
        elapsed = time.time() - self._warmup_start_time
        if elapsed >= self._warmup_duration_sec:
            self._is_warming_up = False
            return False
        return True

    @property
    def warmup_seconds_remaining(self) -> int:
        if not self.is_warming_up:
            return 0
        elapsed = time.time() - self._warmup_start_time
        return max(0, int(self._warmup_duration_sec - elapsed))

    @property
    def is_connected(self) -> bool:
        return any(self._worker_connected.values())

    @property
    def ports_monitored_count(self) -> int:
        unique_locodes = {p.get("locode") or p.get("id") for p in self._ports.values()}
        return len(unique_locodes)

    @property
    def total_vessels_tracked(self) -> int:
        now = time.time()
        total_mmsis: Set[int] = set()
        for port_vessels in self._vessels.values():
            for mmsi, data in port_vessels.items():
                if now - data.get("last_seen", 0) <= self.departed_timeout_seconds:
                    total_mmsis.add(mmsi)
        return len(total_mmsis)

    def register_ports(self, ports: List[Dict[str, Any]]) -> None:
        """Register or update a list of monitored ports and their geofences."""
        was_empty = len(self._ports) == 0

        for p in ports:
            key = p.get("id") or p.get("locode")
            if not key:
                continue
            lat = p.get("lat")
            lon = p.get("lon")
            if lat is None or lon is None:
                continue

            radius = float(p.get("geofence") or p.get("geofence_radius_nm") or 8.0)
            if p.get("locode") == "MOMFM" or key == "port-momfm":
                radius = max(radius, 25.0)

            bbox = calculate_bounding_box(float(lat), float(lon), radius)
            lat_min = min(bbox[0][0], bbox[1][0])
            lat_max = max(bbox[0][0], bbox[1][0])
            lon_min = min(bbox[0][1], bbox[1][1])
            lon_max = max(bbox[0][1], bbox[1][1])

            entry = {
                "id": p.get("id", key),
                "locode": p.get("locode", ""),
                "name": p.get("name", ""),
                "lat": float(lat),
                "lon": float(lon),
                "radius_nm": radius,
                "bbox": bbox,
                "lat_min": lat_min,
                "lat_max": lat_max,
                "lon_min": lon_min,
                "lon_max": lon_max,
            }

            self._ports[key] = entry
            if p.get("locode"):
                self._ports[p["locode"].upper()] = entry
            if key not in self._vessels:
                self._vessels[key] = {}
            if p.get("locode") and p["locode"].upper() not in self._vessels:
                self._vessels[p["locode"].upper()] = self._vessels[key]

        for ev in self._resubscribe_events:
            ev.set()

        # If stream is running and transitioning from 0 ports to monitored ports, activate warm-up
        if self._running and was_empty and self._ports and self.api_key and self.api_key.strip():
            self._is_warming_up = True
            self._warmup_start_time = time.time()
            self._warmup_duration_sec = 20.0
            logger.info(
                "First monitored port registered to live AIS stream. Initiating 20.0s warm-up aggregation..."
            )

    def unregister_port(self, port_id: str, locode: Optional[str] = None) -> None:
        """Remove a port from continuous monitoring."""
        if port_id in self._ports:
            del self._ports[port_id]
        if locode and locode.upper() in self._ports:
            del self._ports[locode.upper()]
        for ev in self._resubscribe_events:
            ev.set()

    async def start(self, initial_ports: List[Dict[str, Any]], warmup_seconds: float = 20.0) -> None:
        """Start the persistent WebSocket listeners across 3 connections and initialize the warm-up cycle."""
        if self._running:
            return

        self._running = True
        self.register_ports(initial_ports)

        # Trigger warm-up if monitored ports exist and API key is present
        if self._ports and self.api_key and self.api_key.strip():
            self._is_warming_up = True
            self._warmup_start_time = time.time()
            self._warmup_duration_sec = warmup_seconds
            logger.info(
                "Starting AISStream persistent stream across 3 connections with %d monitored ports. Warm-up initialization for %.1fs...",
                self.ports_monitored_count,
                warmup_seconds,
            )
        else:
            self._is_warming_up = False
            logger.info("Starting AISStream persistent stream (no monitored ports or API key yet).")

        self._listen_tasks = [
            asyncio.create_task(self._listen_worker(i, 3))
            for i in range(3)
        ]

    async def stop(self) -> None:
        """Stop all background listeners and clean up resources."""
        self._running = False
        self._worker_connected = {i: False for i in range(3)}
        self._is_warming_up = False
        for task in self._listen_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._listen_tasks.clear()
        logger.info("AISStream persistent background stream stopped.")

    def get_port_counts(self, port_id: str, locode: Optional[str] = None) -> Optional[Tuple[int, int, int]]:
        """Return (active_vessels, stationary_vessels, moving_vessels) for a port from memory.

        Returns None if this port has never received any data or is untracked.
        """
        vessels_dict = self._vessels.get(port_id)
        if not vessels_dict and locode:
            vessels_dict = self._vessels.get(locode.upper())

        if vessels_dict is None:
            return None

        now = time.time()
        active = 0
        stationary = 0
        moving = 0

        for mmsi, info in list(vessels_dict.items()):
            # Check if vessel has pinged within the departed timeout window
            if now - info.get("last_seen", 0) <= self.departed_timeout_seconds:
                active += 1
                sog = info.get("sog", 0.0)
                if sog <= 0.5:
                    stationary += 1
                else:
                    moving += 1

        return active, stationary, moving

    def get_status(self) -> Dict[str, Any]:
        """Return high-level stream telemetry and warm-up status for the API and frontend."""
        warming = self.is_warming_up
        remaining = self.warmup_seconds_remaining
        return {
            "isWarmingUp": warming,
            "warmupSecondsRemaining": remaining,
            "message": (
                f"Initializing live AIS vessel telemetry (~{remaining}s)..."
                if warming
                else "Live AIS vessel telemetry active"
            ),
            "isConnected": self.is_connected,
            "portsMonitored": self.ports_monitored_count,
            "vesselsTracked": self.total_vessels_tracked,
        }

    async def _listen_worker(self, worker_id: int, total_workers: int = 3) -> None:
        """Continuous background listener worker maintaining an open WebSocket for 1/Nth of the ports."""
        backoff_delay = 2.0
        max_backoff = 30.0
        event = self._resubscribe_events[worker_id]
        # Stagger initial connection handshakes so workers do not connect at the exact same millisecond
        if worker_id > 0:
            await asyncio.sleep(worker_id * 1.5)

        while self._running:
            if not self.api_key or not self.api_key.strip():
                # No API key configured; idle and recheck periodically
                await asyncio.sleep(5.0)
                continue

            unique_ports = sorted(
                list({p["id"]: p for p in self._ports.values()}.values()),
                key=lambda x: x["id"],
            )
            worker_ports = [p for idx, p in enumerate(unique_ports) if idx % total_workers == worker_id]

            if not worker_ports:
                # No ports assigned to this worker; wait until ports are registered
                try:
                    await asyncio.wait_for(event.wait(), timeout=10.0)
                    event.clear()
                except asyncio.TimeoutError:
                    pass
                continue

            # Build bounding box subscription list for this worker's partition
            bboxes = [p["bbox"] for p in worker_ports]
            sub_payload = {
                "APIKey": self.api_key.strip(),
                "BoundingBoxes": bboxes,
                "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
            }

            try:
                logger.info(
                    "Worker %d/%d: Connecting persistent AISStream WebSocket with %d port bounding boxes...",
                    worker_id + 1,
                    total_workers,
                    len(bboxes),
                )
                async with websockets.connect(
                    self.ws_url,
                    close_timeout=3.0,
                    ping_timeout=10.0,
                    ping_interval=20.0,
                ) as ws:
                    await ws.send(json.dumps(sub_payload))
                    self._worker_connected[worker_id] = True
                    backoff_delay = 2.0
                    logger.info(
                        "Worker %d/%d: Persistent AISStream WebSocket connected successfully.",
                        worker_id + 1,
                        total_workers,
                    )

                    last_prune_time = time.time()

                    while self._running:
                        # Check if monitored ports changed and we need to re-subscribe
                        if event.is_set():
                            event.clear()
                            fresh_unique = sorted(
                                list({p["id"]: p for p in self._ports.values()}.values()),
                                key=lambda x: x["id"],
                            )
                            fresh_worker_ports = [
                                p for idx, p in enumerate(fresh_unique) if idx % total_workers == worker_id
                            ]
                            if fresh_worker_ports:
                                new_sub = {
                                    "APIKey": self.api_key.strip(),
                                    "BoundingBoxes": [p["bbox"] for p in fresh_worker_ports],
                                    "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
                                }
                                await ws.send(json.dumps(new_sub))
                                logger.info(
                                    "Worker %d/%d: Sent updated subscription with %d bounding boxes.",
                                    worker_id + 1,
                                    total_workers,
                                    len(new_sub["BoundingBoxes"]),
                                )

                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            # Periodic check for departed vessel pruning on worker 0 (every 60s)
                            if worker_id == 0 and time.time() - last_prune_time > 60.0:
                                self._prune_departed_vessels()
                                last_prune_time = time.time()
                            continue

                        self._process_raw_message(raw)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._worker_connected[worker_id] = False
                logger.warning(
                    "Worker %d/%d: AISStream WebSocket dropped: %s. Reconnecting in %.1fs...",
                    worker_id + 1,
                    total_workers,
                    str(e),
                    backoff_delay,
                )
                await asyncio.sleep(backoff_delay)
                backoff_delay = min(backoff_delay * 1.5, max_backoff)

        self._worker_connected[worker_id] = False

    def _process_raw_message(self, raw_str: str) -> None:
        """Parse incoming AISStream JSON message and update in-memory vessel registry."""
        try:
            msg = json.loads(raw_str)
        except Exception:
            return

        m_type = msg.get("MessageType")
        if m_type == "SubscriptionConfirmation":
            return

        metadata = msg.get("MetaData", {})
        mmsi = metadata.get("MMSI")
        if mmsi is None:
            return

        v_lat = metadata.get("latitude")
        v_lon = metadata.get("longitude")
        if v_lat is None or v_lon is None:
            pos = msg.get("Message", {}).get("PositionReport", {})
            v_lat = pos.get("Latitude")
            v_lon = pos.get("Longitude")

        if v_lat is None or v_lon is None:
            return

        try:
            v_lat_f = float(v_lat)
            v_lon_f = float(v_lon)
        except (ValueError, TypeError):
            return

        pos_report = msg.get("Message", {}).get("PositionReport", {})
        sog = float(pos_report.get("Sog", 0.0))
        nav_status = int(pos_report.get("NavigationalStatus", 0))
        now = time.time()

        # Match vessel coordinates against all registered port geofences
        for port_key, info in self._ports.items():
            if info["lat_min"] <= v_lat_f <= info["lat_max"] and info["lon_min"] <= v_lon_f <= info["lon_max"]:
                if port_key not in self._vessels:
                    self._vessels[port_key] = {}
                self._vessels[port_key][int(mmsi)] = {
                    "mmsi": int(mmsi),
                    "sog": sog,
                    "lat": v_lat_f,
                    "lon": v_lon_f,
                    "last_seen": now,
                    "nav_status": nav_status,
                }

    def _prune_departed_vessels(self) -> None:
        """Prune vessels that have stopped transmitting inside the geofence for longer than departed_timeout_seconds."""
        now = time.time()
        for port_key, vessels in list(self._vessels.items()):
            departed = [
                mmsi
                for mmsi, info in vessels.items()
                if now - info.get("last_seen", 0) > self.departed_timeout_seconds
            ]
            for mmsi in departed:
                del vessels[mmsi]


# Application-level singleton stream manager
_global_stream_manager: Optional[AISStreamManager] = None


def get_stream_manager() -> AISStreamManager:
    """Retrieve or initialize the global singleton AISStreamManager instance."""
    global _global_stream_manager
    if _global_stream_manager is None:
        _global_stream_manager = AISStreamManager()
    return _global_stream_manager
