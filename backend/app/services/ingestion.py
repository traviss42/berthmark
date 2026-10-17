"""Background ingestion service utilizing APScheduler to periodically fetch and update external data in SQLite."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
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


def get_monitored_ports_for_ingestion() -> List[Dict[str, Any]]:
    """Gather all global default ports plus user-monitored ports for continuous telemetry ingestion."""
    ports_to_ingest: List[Dict[str, Any]] = []
    seen_locodes = set()

    # 1. Global default ports from UN/LOCODE reference database
    try:
        from app.clients.unlocode_db import UnlocodeDatabase
        db_ref = UnlocodeDatabase()
        for dp in db_ref.get_default_ports():
            code = dp.locode.upper()
            seen_locodes.add(code)
            ports_to_ingest.append({
                "id": dp.id,
                "name": dp.name,
                "locode": dp.locode,
                "lat": dp.lat,
                "lon": dp.lon,
                "geofence": dp.geofenceRadiusNm or 8.0,
                "vessel_class": dp.vesselClass or "neoPanamax",
            })
    except Exception as e:
        logger.warning("Failed to query default ports for ingestion: %s", str(e))

    # 2. User-monitored custom ports from SQLite
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


async def initialize_startup_stream(warmup_seconds: float = 20.0) -> None:
    """Initialize persistent AISStream WebSocket listener and execute warm-up initialization."""
    ports = get_monitored_ports_for_ingestion()
    stream_mgr = get_stream_manager()
    await stream_mgr.start(ports, warmup_seconds=warmup_seconds)

    if stream_mgr.is_warming_up:
        logger.info("Stream warm-up active: waiting %.1fs for initial fleet aggregation...", warmup_seconds)
        while stream_mgr.is_warming_up:
            await asyncio.sleep(1.0)
        logger.info("Stream warm-up complete. Flushing initial baseline snapshot to SQLite...")
        try:
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
            import asyncio
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
        import asyncio
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
        import asyncio
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
