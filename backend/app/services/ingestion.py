"""Background ingestion service utilizing APScheduler to periodically fetch and update external data in SQLite."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.clients.ais_client import AISClient
from app.clients.weather_client import MarineWeatherClient
from app.db.models import MonitoredPort
from app.db.session import get_db_context

logger = logging.getLogger(__name__)

# Default major maritime hubs used for baseline ingestion if no user ports exist
DEFAULT_INGESTION_HUBS = [
    {"id": "port-nlrtm", "name": "Port of Rotterdam", "locode": "NLRTM", "lat": 51.9167, "lon": 4.4},
    {"id": "port-sgkep", "name": "Port of Keppel", "locode": "SGKEP", "lat": 1.2667, "lon": 103.8333},
    {"id": "port-cnsgh", "name": "Port of Shanghai", "locode": "CNSGH", "lat": 31.2333, "lon": 121.4667},
    {"id": "port-deham", "name": "Port of Hamburg", "locode": "DEHAM", "lat": 53.55, "lon": 9.9833},
    {"id": "port-uslax", "name": "Port of Los Angeles", "locode": "USLAX", "lat": 33.7333, "lon": -118.2667},
    {"id": "port-momfm", "name": "Port of Macau", "locode": "MOMFM", "lat": 22.2, "lon": 113.5333, "geofence": 25.0},
]

INGESTION_VESSEL_CLASSES = ["neoPanamax", "panamax", "feeder"]

_scheduler: Optional[AsyncIOScheduler] = None
_weather_client = MarineWeatherClient()
_ais_client = AISClient()


async def run_ingestion_cycle() -> Dict[str, Any]:
    """Execute a single ingestion cycle to fetch and persist external API data into SQLite."""
    logger.info("Starting background ingestion cycle for external weather and AIS telemetry...")
    ports_to_ingest: List[Dict[str, Any]] = []

    # 1. Gather all user-monitored ports from the database
    try:
        with get_db_context() as db:
            monitored = db.query(MonitoredPort).all()
            for mp in monitored:
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

    # 2. Add default hubs if not already present
    existing_locodes = {p["locode"] for p in ports_to_ingest}
    for hub in DEFAULT_INGESTION_HUBS:
        if hub["locode"] not in existing_locodes:
            ports_to_ingest.append({
                "id": hub["id"],
                "name": hub["name"],
                "locode": hub["locode"],
                "lat": hub["lat"],
                "lon": hub["lon"],
                "geofence": 8.0,
                "vessel_class": "neoPanamax",
            })

    # 3. Deduplicate unique ports for concurrent batch AISStream sampling
    unique_ports_map: Dict[str, Dict[str, Any]] = {}
    for p in ports_to_ingest:
        key = p.get("locode") or p.get("id")
        if key not in unique_ports_map:
            unique_ports_map[key] = p
    unique_ports = list(unique_ports_map.values())

    # Concurrently sample live AISStream traffic for all bounding boxes in one connection
    try:
        logger.info(
            "Batch querying AISStream WebSocket with %d bounding boxes...",
            len(unique_ports),
        )
        batch_counts = await _ais_client.batch_query_ports_ws(unique_ports, sample_seconds=20.0)
        logger.info("Batch AISStream query returned data for %d ports.", len(batch_counts))
    except Exception as e:
        logger.warning("Batch AISStream query failed, falling back to per-port lookup: %s", str(e))

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

    return scheduler


def stop_ingestion_scheduler() -> None:
    """Stop the APScheduler background ingestion job."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler background ingestion service stopped.")
        _scheduler = None


def is_ingestion_running() -> bool:
    """Return True if the background ingestion scheduler is actively running."""
    return _scheduler is not None and _scheduler.running
