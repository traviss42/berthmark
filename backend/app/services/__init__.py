"""Services package."""

from app.services.external_client import (
    ais_client,
    fetch_ais_traffic,
    fetch_marine_weather,
    get_marine_weather,
    get_port_traffic_metrics,
    weather_client,
)
from app.services.ingestion import (
    get_ingestion_scheduler,
    is_ingestion_running,
    run_ingestion_cycle,
    start_ingestion_scheduler,
    stop_ingestion_scheduler,
)
from app.services.email_service import EmailService, email_service, is_demo_account
from app.services.notification_service import NotificationService, notification_service
from app.services.port_service import PortService, port_service
from app.services.risk_service import RiskService, risk_service

__all__ = [
    "PortService",
    "port_service",
    "RiskService",
    "risk_service",
    "NotificationService",
    "notification_service",
    "EmailService",
    "email_service",
    "is_demo_account",
    "weather_client",
    "ais_client",
    "get_marine_weather",
    "get_port_traffic_metrics",
    "fetch_marine_weather",
    "fetch_ais_traffic",
    "run_ingestion_cycle",
    "start_ingestion_scheduler",
    "stop_ingestion_scheduler",
    "get_ingestion_scheduler",
    "is_ingestion_running",
]
