"""AISStream WebSocket stream worker runner for background container deployment."""

import asyncio
import logging
import os
import signal
from typing import Any
from dotenv import load_dotenv

load_dotenv()

from backend.database import get_session_factory
from backend.services.ais import (
    AISStreamWorker,
    MonitoredPortInfo,
    get_active_monitored_ports,
)
from backend.services.bounding_box import calculate_bounding_box

logger = logging.getLogger("backend.ais.stream_worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

DUMMY_KEYS = {"", "your_aisstream_api_key_here", "none", "null", "undefined"}


async def run_worker() -> None:
    """Run AIS stream workers or enter idle standby if API key is not configured."""
    api_key = os.getenv("AISSTREAM_API_KEY", "").strip()
    stop_event = asyncio.Event()

    # Register OS signal handlers for graceful shutdown if in main thread
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            # Not supported on Windows or non-main threads
            pass

    if not api_key or api_key.lower() in DUMMY_KEYS:
        logger.warning(
            "AISSTREAM_API_KEY is not configured or empty. Stream worker entering idle standby mode without exiting."
        )
        try:
            while not stop_event.is_set():
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        logger.info("Stream worker stopped cleanly from standby.")
        return

    logger.info("AISSTREAM_API_KEY detected. Initializing regional stream workers...")
    session_factory = get_session_factory()

    # Query active monitored ports; fallback to default benchmark ports if empty
    monitored_ports = await get_active_monitored_ports(session_factory)
    if not monitored_ports:
        logger.info("No active user watchlists found. Loading default benchmark ports...")
        from sqlalchemy import select
        from backend.models import Port
        async with session_factory() as session:
            stmt = select(Port.unlocode, Port.latitude, Port.longitude)
            rows = (await session.execute(stmt)).all()
            for r in rows:
                unlocode, lat, lon = r[0], float(r[1]), float(r[2])
                boxes = calculate_bounding_box(lat, lon, radius_nm=8.0)
                b = boxes[0]
                monitored_ports.append(
                    MonitoredPortInfo(
                        unlocode=unlocode,
                        lat=lat,
                        lon=lon,
                        radius_nm=8.0,
                        lat_min=b.lat_min,
                        lat_max=b.lat_max,
                        lon_min=b.lon_min,
                        lon_max=b.lon_max,
                    )
                )

    worker = AISStreamWorker(worker_id=0, api_key=api_key, session_factory=session_factory)
    worker.set_monitored_ports(monitored_ports)
    logger.info("AIS Stream Worker initialized with %d monitored ports", len(worker.ports))
    await worker.start()

    async def poll_watchlist_updates():
        while not stop_event.is_set():
            await asyncio.sleep(15)
            try:
                latest = await get_active_monitored_ports(session_factory)
                current_locodes = {p.unlocode for p in worker.ports}
                latest_locodes = {p.unlocode for p in latest}
                if latest_locodes != current_locodes:
                    logger.info("Watchlist updated (%s ports). Updating stream subscription...", len(latest_locodes))
                    worker.set_monitored_ports(latest)
            except Exception as e:
                logger.warning("Error checking watchlist updates: %s", e)

    poll_task = asyncio.create_task(poll_watchlist_updates())

    logger.info("AIS stream worker running. Waiting for shutdown signal...")
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass

    poll_task.cancel()
    logger.info("Shutdown signal received. Stopping worker...")
    await worker.stop()
    logger.info("AIS stream worker stopped cleanly.")


def main() -> None:
    """Entrypoint function for stream worker."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    try:
        asyncio.run(run_worker())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker process exited.")


if __name__ == "__main__":
    main()
