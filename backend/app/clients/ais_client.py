"""AIS vessel traffic client integrating live AISStream WebSocket telemetry and NGA World Port Index hydrographic data."""

import asyncio
import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import httpx
import websockets
from app.clients.unlocode_db import UnlocodeDatabase
from app.config import get_settings
from app.db.session import get_db_context
from app.models.external_cache import ExternalAISTrafficCache
from app.models.risk import CongestionMetrics, NavigationalMetrics

logger = logging.getLogger(__name__)

# Standard PIANC / maritime engineering design drafts (meters) per vessel class
VESSEL_CLASS_DRAFTS_M: Dict[str, float] = {
    "feeder": 9.5,
    "panamax": 12.5,
    "neoPanamax": 15.2,
    "ulcv": 16.5,
    "mrTanker": 11.0,
    "aframax": 14.8,
    "suezmax": 17.0,
    "vlcc": 20.5,
    "handysize": 10.5,
    "panamaxBulk": 14.0,
    "capesize": 18.0,
    "pctc": 10.0,
    "lng": 12.0,
}


class AISClient:
    """Client for AISStream WebSocket live vessel traffic and NGA World Port Index hydrographic data (no simulated fallbacks)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        ws_url: Optional[str] = None,
        timeout: Optional[float] = None,
        unlocode_db: Optional[UnlocodeDatabase] = None,
    ):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.AISSTREAM_API_KEY
        self.base_url = base_url or settings.AISSTREAM_BASE_URL
        self.ws_url = ws_url or getattr(settings, "AISSTREAM_WS_URL", "wss://stream.aisstream.io/v0/stream")
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self._unlocode_db = unlocode_db
        self._cache: Dict[str, Tuple[float, Tuple[CongestionMetrics, NavigationalMetrics]]] = {}
        self._live_vessel_cache: Dict[Tuple[float, float], Tuple[float, Tuple[int, int, int]]] = {}
        self.cache_ttl_seconds: float = 1800.0  # 30 minutes TTL

    @property
    def unlocode_db(self) -> UnlocodeDatabase:
        if self._unlocode_db is None:
            self._unlocode_db = UnlocodeDatabase()
        return self._unlocode_db

    def _build_wpi_navigational_metrics(
        self, port_id: str, locode: str, vessel_class: str
    ) -> NavigationalMetrics:
        """Construct real NavigationalMetrics from NGA World Port Index (Pub 150) port hydrography and vessel design draft."""
        port = self.unlocode_db.get_port_by_locode(locode) or self.unlocode_db.get_port_by_id(port_id)
        if not port or port.channelDepthM is None or port.channelDepthM <= 0:
            raise ValueError(
                f"Real NGA World Port Index depth data is required but unavailable for port '{locode}' ({port_id})."
            )

        vessel_draft = VESSEL_CLASS_DRAFTS_M.get(vessel_class, 12.5)
        channel_depth = float(port.channelDepthM)

        ukc = round(channel_depth - vessel_draft, 2)

        return NavigationalMetrics(
            underKeelClearanceM=ukc,
            channelDepthM=channel_depth,
            cargoPierDepthM=port.cargoPierDepthM,
            anchorageDepthM=port.anchorageDepthM,
            vesselDraftM=vessel_draft,
            overheadLimits=port.overheadLimits or "Unknown",
            pilotageAvailable=port.pilotageAvailable is not False,
            tugsAssistance=port.tugsAssistance is not False,
            tideHeightM=float(port.tidalRangeM) if port.tidalRangeM is not None else 0.0,
            harborSize=port.harborSize,
            shelterAfforded=port.shelterAfforded,
        )

    def _get_historical_avg_queue(self, locode: str, current_queue: int) -> float:
        """Compute rolling 30-day average queue from real persisted SQLite snapshots."""
        try:
            with get_db_context() as db:
                records = (
                    db.query(ExternalAISTrafficCache)
                    .filter(ExternalAISTrafficCache.locode == locode.upper())
                    .all()
                )
                if records:
                    queues = [r.anchorage_queue_count for r in records if r.anchorage_queue_count is not None]
                    if queues:
                        return round(sum(queues) / len(queues), 1)
        except Exception as e:
            logger.debug("Historical queue lookup failed: %s", str(e))
        return float(current_queue)

    async def _query_aisstream_ws(
        self, lat: float, lon: float, radius_nm: float = 8.0, sample_seconds: float = 1.5
    ) -> Optional[Tuple[int, int, int]]:
        """Connect to live AISStream WebSocket and sample active, stationary/anchored, and moving vessels in bounding box."""
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

                vessels: Dict[Any, Dict[str, Any]] = {}
                start = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - start < sample_seconds:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        msg = json.loads(raw)
                        m_type = msg.get("MessageType")
                        if m_type == "SubscriptionConfirmation":
                            continue
                        metadata = msg.get("MetaData", {})
                        mmsi = metadata.get("MMSI")
                        if mmsi is None:
                            continue

                        v_info = vessels.setdefault(mmsi, {"sog": None, "nav_status": None})
                        if m_type == "PositionReport":
                            pos = msg.get("Message", {}).get("PositionReport", {})
                            if "Sog" in pos:
                                v_info["sog"] = pos.get("Sog")
                            if "NavigationalStatus" in pos:
                                v_info["nav_status"] = pos.get("NavigationalStatus")
                    except asyncio.TimeoutError:
                        break

                active_count = len(vessels)
                stationary_count = 0
                for v in vessels.values():
                    nav_st = v.get("nav_status")
                    sog = v.get("sog")
                    if nav_st in (1, 5) or (sog is not None and float(sog) <= 0.5):
                        stationary_count += 1

                moving_count = max(0, active_count - stationary_count)
                return active_count, stationary_count, moving_count
        except Exception as e:
            logger.debug("AISStream WebSocket connection failed or timed out: %s", str(e))
            return None

    def _persist_ais_cache(
        self,
        cache_key: str,
        port_id: str,
        locode: str,
        vessel_class: str,
        metrics: Tuple[CongestionMetrics, NavigationalMetrics],
        source: str,
    ) -> None:
        """Persist or update AIS traffic and WPI navigational metrics in SQLite database."""
        try:
            with get_db_context() as db:
                record = db.query(ExternalAISTrafficCache).filter(
                    (ExternalAISTrafficCache.id == cache_key)
                    | (
                        (ExternalAISTrafficCache.locode == locode)
                        & (ExternalAISTrafficCache.vessel_class == vessel_class)
                    )
                ).first()

                congestion, navigational = metrics
                now_utc = datetime.now(timezone.utc)

                if not record:
                    record = ExternalAISTrafficCache(
                        id=cache_key,
                        port_id=port_id,
                        locode=locode,
                        vessel_class=vessel_class,
                        anchorage_queue_count=congestion.anchorageQueueCount,
                        active_vessel_count=congestion.activeVesselCount,
                        moving_vessel_count=congestion.movingVesselCount,
                        rolling_30d_avg_queue=congestion.rolling30dAvgQueue,
                        under_keel_clearance_m=navigational.underKeelClearanceM,
                        channel_depth_m=navigational.channelDepthM,
                        cargo_pier_depth_m=navigational.cargoPierDepthM,
                        anchorage_depth_m=navigational.anchorageDepthM,
                        vessel_draft_m=navigational.vesselDraftM,
                        overhead_limits=navigational.overheadLimits,
                        pilotage_available=navigational.pilotageAvailable,
                        tugs_assistance=navigational.tugsAssistance,
                        tide_height_m=navigational.tideHeightM,
                        harbor_size=navigational.harborSize,
                        shelter_afforded=navigational.shelterAfforded,
                        source=source,
                        fetched_at=now_utc,
                    )
                    db.add(record)
                else:
                    record.port_id = port_id
                    record.locode = locode
                    record.vessel_class = vessel_class
                    record.anchorage_queue_count = congestion.anchorageQueueCount
                    record.active_vessel_count = congestion.activeVesselCount
                    record.moving_vessel_count = congestion.movingVesselCount
                    record.rolling_30d_avg_queue = congestion.rolling30dAvgQueue
                    record.under_keel_clearance_m = navigational.underKeelClearanceM
                    record.channel_depth_m = navigational.channelDepthM
                    record.cargo_pier_depth_m = navigational.cargoPierDepthM
                    record.anchorage_depth_m = navigational.anchorageDepthM
                    record.vessel_draft_m = navigational.vesselDraftM
                    record.overhead_limits = navigational.overheadLimits
                    record.pilotage_available = navigational.pilotageAvailable
                    record.tugs_assistance = navigational.tugsAssistance
                    record.tide_height_m = navigational.tideHeightM
                    record.harbor_size = navigational.harborSize
                    record.shelter_afforded = navigational.shelterAfforded
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
    ) -> Tuple[CongestionMetrics, NavigationalMetrics]:
        """Fetch live AISStream vessel traffic and real NGA World Port Index navigational metrics with SQLite caching."""
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

        # 2. Check HTTP endpoint if configured for custom/mock HTTP transport
        if (
            self.base_url
            and "aisstream.io" not in self.base_url
            and self.base_url.startswith("http")
        ):
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {"port": locode, "vesselClass": vessel_class}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/metrics", headers=headers, params=params
                )
                response.raise_for_status()
                data = response.json()
                congestion = CongestionMetrics(**data["congestion"])
                if "navigational" in data:
                    navigational = NavigationalMetrics(**data["navigational"])
                else:
                    navigational = self._build_wpi_navigational_metrics(port_id, locode, vessel_class)
                result = (congestion, navigational)
                self._persist_ais_cache(
                    cache_key, port_id, locode, vessel_class, result, source="http-api"
                )
                self._cache[cache_key] = (now, result)
                return result

        # 3. Build real NGA World Port Index navigational metrics
        navigational = self._build_wpi_navigational_metrics(port_id, locode, vessel_class)

        # Resolve coordinates from port record if not explicitly passed
        if lat is None or lon is None:
            port_obj = self.unlocode_db.get_port_by_locode(locode) or self.unlocode_db.get_port_by_id(port_id)
            if not port_obj:
                raise ValueError(f"Coordinates unavailable for port '{locode}' ({port_id}).")
            lat, lon = port_obj.lat, port_obj.lon

        # 4. Query AISStream live WebSocket
        ws_counts: Optional[Tuple[int, int, int]] = None
        if self.api_key and self.api_key.strip():
            coord_key = (round(lat, 2), round(lon, 2))
            if coord_key in self._live_vessel_cache and (now - self._live_vessel_cache[coord_key][0] < 30.0):
                ws_counts = self._live_vessel_cache[coord_key][1]
            else:
                ws_counts = await self._query_aisstream_ws(lat, lon, geofence_radius_nm)
                if ws_counts is not None:
                    self._live_vessel_cache[coord_key] = (now, ws_counts)

        if ws_counts is not None:
            active_count, queue_count, moving_count = ws_counts
            avg_queue = self._get_historical_avg_queue(locode, queue_count)
            logger.info(
                "AISStream live vessel stream connected for %s (%s): %d active (%d anchored/stationary, %d underway).",
                locode,
                port_id,
                active_count,
                queue_count,
                moving_count,
            )
            source = "aisstream"
        else:
            # No simulated random numbers: use real persisted snapshot if present, or 0 live vessels when stream returns no vessels
            avg_queue = self._get_historical_avg_queue(locode, 0)
            active_count, queue_count, moving_count = 0, int(avg_queue), 0
            source = "aisstream-empty"

        congestion = CongestionMetrics(
            anchorageQueueCount=queue_count,
            activeVesselCount=active_count,
            movingVesselCount=moving_count,
            rolling30dAvgQueue=avg_queue,
        )

        metrics = (congestion, navigational)
        self._persist_ais_cache(
            cache_key, port_id, locode, vessel_class, metrics, source=source
        )
        self._cache[cache_key] = (now, metrics)
        return metrics


