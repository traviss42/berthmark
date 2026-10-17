"""Background ingestion service utilizing APScheduler to periodically fetch and update external data in SQLite."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.clients.ais_client import AISClient
from app.clients.ais_stream_manager import get_stream_manager
from app.clients.weather_client import MarineWeatherClient
from app.db.models import MonitoredPort
from app.db.session import get_db_context

logger = logging.getLogger(__name__)

INGESTION_VESSEL_CLASSES = ["neoPanamax", "panamax", "feeder"]

_scheduler: Optional[AsyncIOScheduler] = None
_weather_client = MarineWeatherClient()
_ais_client = AISClient()


def get_all_maritime_ports_for_stream() -> List[Dict[str, Any]]:
    """Gather all maritime ports with valid coordinates from UN/LOCODE reference database for stream monitoring."""
    try:
        from app.clients.unlocode_db import UnlocodeDatabase
        db_ref = UnlocodeDatabase()
        with db_ref._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, locode, name, lat, lon, geofence_radius_nm FROM unlocode_ports;")
            rows = cursor.fetchall()
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "locode": r["locode"],
                    "lat": r["lat"],
                    "lon": r["lon"],
                    "geofence": r["geofence_radius_nm"] or 8.0,
                    "vessel_class": "neoPanamax",
                }
                for r in rows
            ]
    except Exception as e:
        logger.warning("Failed to query maritime ports for stream subscription: %s", str(e))
        return []


def get_monitored_ports_for_ingestion() -> List[Dict[str, Any]]:
    """Gather user-monitored ports from SQLite for continuous periodic telemetry ingestion."""
    ports_to_ingest: List[Dict[str, Any]] = []
    seen_locodes = set()
    try:
        with get_db_context() as db:
            monitored = db.query(MonitoredPort).all()
            for mp in monitored:
                code = mp.locode.upper()
                if code not in seen_locodes:
                    seen_locodes.add(code)
                    ports_to_ingest.append({
                        "id": mp.id,
                        "name": mp.name,
                        "locode": mp.locode,
                        "lat": mp.lat,
                        "lon": mp.lon,
                        "geofence": mp.geofence_radius_nm,
                        "vessel_class": mp.vessel_class,
                    })
    except Exception as e:
        logger.warning("Failed to query monitored ports for ingestion: %s", str(e))

    return ports_to_ingest


def flush_stream_snapshot_to_cache() -> int:
    """Flush tracked vessel metrics from in-memory stream manager to SQLite ExternalAISTrafficCache."""
    stream_mgr = get_stream_manager()
    persisted = 0
    seen_port_ids: Set[str] = set()
    now_utc = datetime.now(timezone.utc)
    try:
        from app.clients.unlocode_db import UnlocodeDatabase
        from app.models.external_cache import ExternalAISTrafficCache
        db_ref = UnlocodeDatabase()
        with get_db_context() as db:
            for port_key, vessels in stream_mgr._vessels.items():
                if not vessels:
                    continue
                counts = stream_mgr.get_port_counts(port_key)
                if not counts:
                    continue
                active, stationary, moving = counts
                port = db_ref.get_port_by_id(port_key) or db_ref.get_port_by_locode(port_key)
                if not port or port.channelDepthM is None or port.channelDepthM <= 0:
                    continue
                if port.id in seen_port_ids:
                    continue
                seen_port_ids.add(port.id)

                cache_key = f"{port.id}:neoPanamax"
                rec = db.query(ExternalAISTrafficCache).filter(
                    (ExternalAISTrafficCache.id == cache_key)
                    | (
                        (ExternalAISTrafficCache.locode == port.locode)
                        & (ExternalAISTrafficCache.vessel_class == "neoPanamax")
                    )
                ).first()
                vessel_draft = 15.2
                channel_depth = float(port.channelDepthM)
                ukc = round(channel_depth - vessel_draft, 2)
                if not rec:
                    rec = ExternalAISTrafficCache(
                        id=cache_key,
                        port_id=port.id,
                        locode=port.locode,
                        vessel_class="neoPanamax",
                        anchorage_queue_count=stationary,
                        active_vessel_count=active,
                        moving_vessel_count=moving,
                        rolling_30d_avg_queue=float(stationary),
                        under_keel_clearance_m=ukc,
                        channel_depth_m=channel_depth,
                        cargo_pier_depth_m=port.cargoPierDepthM,
                        anchorage_depth_m=port.anchorageDepthM,
                        vessel_draft_m=vessel_draft,
                        overhead_limits=port.overheadLimits or "Unknown",
                        pilotage_available=port.pilotageAvailable is not False,
                        tugs_assistance=port.tugsAssistance is not False,
                        tide_height_m=float(port.tidalRangeM) if port.tidalRangeM is not None else 0.0,
                        harbor_size=port.harborSize,
                        shelter_afforded=port.shelterAfforded,
                        source="aisstream-stream",
                        fetched_at=now_utc,
                    )
                    db.add(rec)
                else:
                    rec.anchorage_queue_count = stationary
                    rec.active_vessel_count = active
                    rec.moving_vessel_count = moving
                    rec.fetched_at = now_utc
                persisted += 1
            db.commit()
        logger.info("Flushed stream vessel counts for %d active ports.", persisted)
    except Exception as e:
        logger.warning("Failed flushing stream snapshot to cache: %s", str(e))
    return persisted


async def initialize_startup_stream(warmup_seconds: float = 20.0) -> None:
    """Initialize persistent AISStream WebSocket listener with every port bounding box and execute warm-up."""
    ports = get_all_maritime_ports_for_stream()
    stream_mgr = get_stream_manager()
    await stream_mgr.start(ports, warmup_seconds=warmup_seconds)

    if stream_mgr.is_warming_up:
        logger.info(
            "Stream warm-up active: waiting %.1fs for initial fleet aggregation across all %d ports...",
            warmup_seconds,
            len(ports),
        )
        while stream_mgr.is_warming_up:
            await asyncio.sleep(1.0)
        logger.info("Stream warm-up complete. Flushing initial baseline snapshot to SQLite...")
        try:
            flush_stream_snapshot_to_cache()
            await run_ingestion_cycle()
        except Exception as e:
            logger.warning("Initial snapshot flush encountered error: %s", str(e))


async def run_ingestion_cycle() -> Dict[str, Any]:
    """Execute a single ingestion cycle to fetch and persist external API data into SQLite."""
    logger.info("Starting background ingestion cycle for external weather and AIS telemetry...")
    ports_to_ingest = get_monitored_ports_for_ingestion()
    if not ports_to_ingest:
        logger.info("No monitored ports found in database; ingestion idle.")
        return {
            "status": "idle",
            "ports_processed": 0,
            "weather_records_updated": 0,
            "ais_records_updated": 0,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    weather_updated = 0
    ais_updated = 0

    # 4. Ingest fresh data for each target port with force_refresh=True
    for port in ports_to_ingest:
        port_id = port["id"]
        locode = port["locode"]
        lat = port["lat"]
        lon = port["lon"]
        geofence = port.get("geofence", 8.0)

        # Ingest fresh Marine Weather
        try:
            await _weather_client.get_marine_weather(
                lat=lat,
                lon=lon,
                port_id=port_id,
                force_refresh=True,
            )
            weather_updated += 1
        except Exception as e:
            logger.warning("Ingestion failed for weather at %s (%s): %s", port["name"], port_id, str(e))

        # Ingest fresh AIS Traffic for primary and subscribed vessel classes
        target_classes = set(INGESTION_VESSEL_CLASSES)
        if port.get("vessel_class"):
            target_classes.add(port["vessel_class"])
        for vc in target_classes:
            try:
                await _ais_client.get_port_traffic_metrics(
                    port_id=port_id,
                    locode=locode,
                    vessel_class=vc,
                    lat=lat,
                    lon=lon,
                    geofence_radius_nm=geofence,
                    force_refresh=True,
                )
                ais_updated += 1
            except Exception as e:
                logger.warning(
                    "Ingestion failed for AIS traffic at %s (%s, %s): %s",
                    port["name"],
                    locode,
                    vc,
                    str(e),
                )

    result = {
        "status": "success",
        "ports_processed": len(ports_to_ingest),
        "weather_records_updated": weather_updated,
        "ais_records_updated": ais_updated,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("Background ingestion cycle completed: %s", result)
    return result


def get_ingestion_scheduler() -> AsyncIOScheduler:
    """Retrieve or create singleton AsyncIOScheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def start_ingestion_scheduler(interval_minutes: int = 30) -> AsyncIOScheduler:
    """Start the APScheduler background ingestion job if not already running."""
    scheduler = get_ingestion_scheduler()
    job_id = "external_api_ingestion_job"

    if not scheduler.get_job(job_id):
        scheduler.add_job(
            run_ingestion_cycle,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            name="Periodic External API Telemetry Ingestion",
            replace_existing=True,
        )
        logger.info(
            "Scheduled background ingestion job '%s' every %d minutes.",
            job_id,
            interval_minutes,
        )

    if not scheduler.running:
        try:
            scheduler.start()
            logger.info("APScheduler background ingestion service started.")
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            scheduler._eventloop = loop
            scheduler.start()
            logger.info("APScheduler background ingestion service started.")

    # Spawn persistent AISStream manager startup and warm-up task
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(initialize_startup_stream(warmup_seconds=20.0))
        logger.info("Spawned AISStream persistent stream initialization and 20s warm-up task.")
    except RuntimeError:
        pass

    return scheduler


def stop_ingestion_scheduler() -> None:
    """Stop the APScheduler background ingestion job and stream manager."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler background ingestion service stopped.")
        _scheduler = None

    try:
        from app.clients.ais_stream_manager import get_stream_manager
        stream_mgr = get_stream_manager()
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(stream_mgr.stop())
        except RuntimeError:
            asyncio.run(stream_mgr.stop())
    except Exception as e:
        logger.debug("Stream manager stop on shutdown: %s", str(e))


def is_ingestion_running() -> bool:
    """Return True if the background ingestion scheduler is actively running."""
    return _scheduler is not None and _scheduler.running
