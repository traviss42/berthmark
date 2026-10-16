"""Ingestion service forwarding for backend.services namespace."""

try:
    from app.services.ingestion import (
        DEFAULT_INGESTION_HUBS,
        INGESTION_VESSEL_CLASSES,
        get_ingestion_scheduler,
        is_ingestion_running,
        run_ingestion_cycle,
        start_ingestion_scheduler,
        stop_ingestion_scheduler,
    )
except ImportError:
    from backend.app.services.ingestion import (
        DEFAULT_INGESTION_HUBS,
        INGESTION_VESSEL_CLASSES,
        get_ingestion_scheduler,
        is_ingestion_running,
        run_ingestion_cycle,
        start_ingestion_scheduler,
        stop_ingestion_scheduler,
    )

__all__ = [
    "DEFAULT_INGESTION_HUBS",
    "INGESTION_VESSEL_CLASSES",
    "get_ingestion_scheduler",
    "is_ingestion_running",
    "run_ingestion_cycle",
    "start_ingestion_scheduler",
    "stop_ingestion_scheduler",
]
