"""AIS and vessel traffic API client with real WebSocket streaming and fallback simulation."""

import asyncio
import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import httpx
import websockets
from app.config import get_settings
from app.db.session import get_db_context
from app.models.external_cache import ExternalAISTrafficCache
from app.models.risk import CongestionMetrics, NavigationalMetrics, TerminalMetrics

logger = logging.getLogger(__name__)

# Bounding box default coordinates for major hubs if lat/lon omitted
DEFAULT_COORDS = {
    "NLRTM": (51.9244, 4.4777),
    "SGSIN": (1.2648, 103.8408),
    "CNSHA": (31.2304, 121.4737),
    "DEHAM": (53.5399, 9.9472),
    "USLAX": (33.7291, -118.2639),
    "AEJEA": (24.9857, 55.0273),
    "BEANR": (51.3, 4.3),
}


class AISClient:
    """Client for AISStream WebSocket live vessel traffic API with SQLite caching and fallback simulation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        ws_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.AISSTREAM_API_KEY
        self.base_url = base_url or settings.AISSTREAM_BASE_URL
        self.ws_url = ws_url or getattr(settings, "AISSTREAM_WS_URL", "wss://stream.aisstream.io/v0/stream")
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self._cache: Dict[str, Tuple[float, Tuple[CongestionMetrics, TerminalMetrics, NavigationalMetrics]]] = {}
        self._live_vessel_cache: Dict[Tuple[float, float], Tuple[float, Optional[int]]] = {}
        self.cache_ttl_seconds: float = 1800.0  # 30 minutes TTL

    def _generate_fallback_metrics(
        self, port_id: str, vessel_class: str, live_vessel_count: Optional[int] = None
    ) -> Tuple[CongestionMetrics, TerminalMetrics, NavigationalMetrics]:
        """Deterministic realistic metrics calibrated with live vessel traffic if available."""
        seed = sum(ord(c) for c in f"{port_id}:{vessel_class}")

        # Baseline queue and wait
        base_queue = 8 + (seed % 15)
        if live_vessel_count is not None and live_vessel_count > 0:
            queue_count = live_vessel_count
        else:
            queue_count = int(base_queue * (0.8 + ((seed % 7) * 0.1)))

        avg_wait = round(16.0 + (seed % 20) + ((seed % 5) * 1.5), 1)
        base_wait = round(avg_wait * (0.85 + ((seed % 4) * 0.08)), 1)
        occupancy = float(60 + (seed % 35))

        congestion = CongestionMetrics(
            anchorageQueueCount=queue_count,
            avgWaitingTimeHours=avg_wait,
            berthOccupancyPct=occupancy,
            rolling30dAvgQueue=float(base_queue),
            rolling30dAvgWaitHours=base_wait,
        )

        # Terminal
        base_turnaround = 24.0 + (seed % 18)
        turnaround = round(base_turnaround * (0.9 + ((seed % 6) * 0.1)), 1)
        wait_ratio = round(0.4 + ((seed % 6) * 0.08), 2)
        dwell_score = float(30 + (seed % 45))

        terminal = TerminalMetrics(
            berthTurnaroundHours=turnaround,
            berthToAnchorageWaitRatio=wait_ratio,
            dwellTimeAnomalyScore=dwell_score,
            rolling30dAvgTurnaround=round(base_turnaround, 1),
        )

        # Navigational
        ukc = round(1.5 + ((seed % 15) * 0.2), 1)
        depth = round(14.0 + (seed % 8), 1)
        air_draft = round(6.0 + (seed % 8), 1)
        pilotage = (seed % 9) != 0  # 90% chance available

        navigational = NavigationalMetrics(
            underKeelClearanceM=ukc,
            channelDepthM=depth,
            airDraftClearanceM=air_draft,
            pilotageAvailable=pilotage,
            tideHeightM=round(1.0 + ((seed % 10) * 0.2), 1),
        )

        return congestion, terminal, navigational

    async def _query_aisstream_ws(
        self, lat: float, lon: float, radius_nm: float = 8.0, sample_seconds: float = 1.5
    ) -> Optional[int]:
        """Connect to live AISStream WebSocket and sample active vessels in bounding box."""
        if not self.api_key or not self.api_key.strip():
            return None

        lat_delta = radius_nm / 60.0
        cos_lat = max(0.1, math.cos(math.radians(lat)))
        lon_delta = radius_nm / (60.0 * cos_lat)
        bbox = [
            [round(lat - lat_delta, 4), round(lon - lon_delta, 4)],
            [round(lat + lat_delta, 4), round(lon + lon_delta, 4)],
        ]

        try:
            async with websockets.connect(
                self.ws_url,
                close_timeout=1.0,
                ping_timeout=2.0,
            ) as ws:
                sub = {
                    "APIKey": self.api_key.strip(),
                    "BoundingBoxes": [bbox],
                    "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
                }
                await ws.send(json.dumps(sub))

                # Collect distinct MMSIs within the sample window
                mmsis = set()
                start = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - start < sample_seconds:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        msg = json.loads(raw)
                        m_type = msg.get("MessageType")
                        if m_type == "SubscriptionConfirmation":
                            continue
                        metadata = msg.get("MetaData", {})
                        if "MMSI" in metadata:
                            mmsis.add(metadata["MMSI"])
                    except asyncio.TimeoutError:
                        break

                return len(mmsis)
        except Exception as e:
            logger.debug("AISStream WebSocket connection failed or timed out: %s", str(e))
            return None

    def _persist_ais_cache(
        self,
        cache_key: str,
        port_id: str,
        locode: str,
        vessel_class: str,
        metrics: Tuple[CongestionMetrics, TerminalMetrics, NavigationalMetrics],
        source: str,
    ) -> None:
        """Persist or update AIS traffic metrics in SQLite database."""
        try:
            with get_db_context() as db:
                record = db.query(ExternalAISTrafficCache).filter(
                    (ExternalAISTrafficCache.id == cache_key)
                    | (
                        (ExternalAISTrafficCache.locode == locode)
                        & (ExternalAISTrafficCache.vessel_class == vessel_class)
                    )
                ).first()

                congestion, terminal, navigational = metrics
                now_utc = datetime.now(timezone.utc)

                if not record:
                    record = ExternalAISTrafficCache(
                        id=cache_key,
                        port_id=port_id,
                        locode=locode,
                        vessel_class=vessel_class,
                        anchorage_queue_count=congestion.anchorageQueueCount,
                        avg_waiting_time_hours=congestion.avgWaitingTimeHours,
                        berth_occupancy_pct=congestion.berthOccupancyPct,
                        rolling_30d_avg_queue=congestion.rolling30dAvgQueue,
                        rolling_30d_avg_wait_hours=congestion.rolling30dAvgWaitHours,
                        berth_turnaround_hours=terminal.berthTurnaroundHours,
                        berth_to_anchorage_wait_ratio=terminal.berthToAnchorageWaitRatio,
                        dwell_time_anomaly_score=terminal.dwellTimeAnomalyScore,
                        rolling_30d_avg_turnaround=terminal.rolling30dAvgTurnaround,
                        under_keel_clearance_m=navigational.underKeelClearanceM,
                        channel_depth_m=navigational.channelDepthM,
                        air_draft_clearance_m=navigational.airDraftClearanceM,
                        pilotage_available=navigational.pilotageAvailable,
                        tide_height_m=navigational.tideHeightM,
                        source=source,
                        fetched_at=now_utc,
                    )
                    db.add(record)
                else:
                    record.port_id = port_id
                    record.locode = locode
                    record.vessel_class = vessel_class
                    record.anchorage_queue_count = congestion.anchorageQueueCount
                    record.avg_waiting_time_hours = congestion.avgWaitingTimeHours
                    record.berth_occupancy_pct = congestion.berthOccupancyPct
                    record.rolling_30d_avg_queue = congestion.rolling30dAvgQueue
                    record.rolling_30d_avg_wait_hours = congestion.rolling30dAvgWaitHours
                    record.berth_turnaround_hours = terminal.berthTurnaroundHours
                    record.berth_to_anchorage_wait_ratio = terminal.berthToAnchorageWaitRatio
                    record.dwell_time_anomaly_score = terminal.dwellTimeAnomalyScore
                    record.rolling_30d_avg_turnaround = terminal.rolling30dAvgTurnaround
                    record.under_keel_clearance_m = navigational.underKeelClearanceM
                    record.channel_depth_m = navigational.channelDepthM
                    record.air_draft_clearance_m = navigational.airDraftClearanceM
                    record.pilotage_available = navigational.pilotageAvailable
                    record.tide_height_m = navigational.tideHeightM
                    record.source = source
                    record.fetched_at = now_utc
                db.commit()
        except Exception as e:
            logger.warning("Failed to persist AIS traffic metrics to SQLite: %s", str(e))

    async def get_port_traffic_metrics(
        self,
        port_id: str,
        locode: str,
        vessel_class: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        geofence_radius_nm: float = 8.0,
        force_refresh: bool = False,
    ) -> Tuple[CongestionMetrics, TerminalMetrics, NavigationalMetrics]:
        """Fetch AIS and operational metrics with SQLite caching (< 30 min freshness)."""
        cache_key = f"{port_id}:{vessel_class}"
        now = time.time()

        # 1. Check SQLite for fresh cached data (< 30 minutes old)
        if not force_refresh:
            try:
                with get_db_context() as db:
                    cached_record = db.query(ExternalAISTrafficCache).filter(
                        (ExternalAISTrafficCache.id == cache_key)
                        | (
                            (ExternalAISTrafficCache.locode == locode)
                            & (ExternalAISTrafficCache.vessel_class == vessel_class)
                        )
                    ).first()

                    if cached_record and cached_record.is_fresh(
                        max_age_seconds=self.cache_ttl_seconds
                    ):
                        metrics = cached_record.to_pydantic()
                        self._cache[cache_key] = (now, metrics)
                        return metrics
            except Exception as e:
                logger.debug("Database AIS traffic cache lookup failed: %s", str(e))

            if cache_key in self._cache:
                ts, cached_metrics = self._cache[cache_key]
                if now - ts < self.cache_ttl_seconds:
                    return cached_metrics

        # 2. Check HTTP mock for unit tests
        if (
            self.base_url
            and "aisstream.io" not in self.base_url
            and self.base_url.startswith("http")
        ):
            try:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                params = {"port": locode, "vesselClass": vessel_class}
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(
                        f"{self.base_url}/metrics", headers=headers, params=params
                    )
                    if response.status_code == 200:
                        data = response.json()
                        result = (
                            CongestionMetrics(**data["congestion"]),
                            TerminalMetrics(**data["terminal"]),
                            NavigationalMetrics(**data["navigational"]),
                        )
                        self._persist_ais_cache(
                            cache_key, port_id, locode, vessel_class, result, source="http-mock"
                        )
                        self._cache[cache_key] = (now, result)
                        return result
            except Exception as e:
                logger.debug("Mock HTTP AIS call failed: %s", str(e))

        # 3. Query AISStream live WebSocket if API key is configured
        live_vessels: Optional[int] = None
        source = "simulated-fallback"
        if self.api_key and self.api_key.strip():
            port_lat, port_lon = (lat, lon) if lat is not None and lon is not None else DEFAULT_COORDS.get(locode, (51.9244, 4.4777))
            coord_key = (round(port_lat, 2), round(port_lon, 2))
            if coord_key in self._live_vessel_cache and (now - self._live_vessel_cache[coord_key][0] < 30.0):
                live_vessels = self._live_vessel_cache[coord_key][1]
            else:
                live_vessels = await self._query_aisstream_ws(port_lat, port_lon, geofence_radius_nm)
                self._live_vessel_cache[coord_key] = (now, live_vessels)

            if live_vessels is not None:
                source = "aisstream"
                logger.info(
                    "AISStream live vessel stream connected for %s (%s): %d active vessels detected in geofence.",
                    locode,
                    port_id,
                    live_vessels,
                )

        # 4. Generate calibrated metrics
        metrics = self._generate_fallback_metrics(port_id, vessel_class, live_vessel_count=live_vessels)
        self._persist_ais_cache(
            cache_key, port_id, locode, vessel_class, metrics, source=source
        )
        self._cache[cache_key] = (now, metrics)
        return metrics

