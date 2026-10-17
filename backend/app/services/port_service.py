"""Port management service implementing multi-tenant isolation and database persistence."""

import logging
import time
import uuid
from typing import Dict, List, Optional, Set
from fastapi import HTTPException, status
from app.clients.ports_client import PortDirectoryClient
from app.db.models import MonitoredPort
from app.db.session import get_db_context
from app.models.port import CreatePortRequest, Port

logger = logging.getLogger(__name__)


class PortService:
    """Service for managing user-monitored ports backed by SQLAlchemy database."""

    def __init__(self, directory_client: Optional[PortDirectoryClient] = None):
        self.directory_client = directory_client or PortDirectoryClient()

    def _enrich_with_wpi(self, port: Port) -> Port:
        """Enrich a user-monitored Port with NGA World Port Index hydrographic fields if available in UN/LOCODE DB."""
        if port.channelDepthM is not None:
            return port
        ref = self.directory_client.get_port_by_locode(port.locode)
        if not ref:
            return port
        return port.model_copy(
            update={
                "channelDepthM": ref.channelDepthM,
                "cargoPierDepthM": ref.cargoPierDepthM,
                "anchorageDepthM": ref.anchorageDepthM,
                "oilTerminalDepthM": ref.oilTerminalDepthM,
                "lngTerminalDepthM": ref.lngTerminalDepthM,
                "maxVesselDraftM": ref.maxVesselDraftM,
                "tidalRangeM": ref.tidalRangeM,
                "overheadLimits": ref.overheadLimits,
                "pilotageAvailable": ref.pilotageAvailable,
                "tugsAssistance": ref.tugsAssistance,
                "harborSize": ref.harborSize,
                "shelterAfforded": ref.shelterAfforded,
            }
        )

    async def get_ports(
        self, user_id: str, vessel_class: Optional[str] = None
    ) -> List[Port]:
        """Return monitored ports for the authenticated user (starts empty, user adds ports)."""
        with get_db_context() as db:
            query = db.query(MonitoredPort).filter(MonitoredPort.user_id == user_id)
            if vessel_class:
                query = query.filter(MonitoredPort.vessel_class == vessel_class)
            records = query.order_by(MonitoredPort.created_at.asc()).all()
            return [self._enrich_with_wpi(r.to_pydantic()) for r in records]

    async def get_default_ports(self) -> List[Port]:
        """Return benchmark ports from the UN/LOCODE database."""
        return self.directory_client.get_default_ports()

    async def search_ports(self, query: str) -> List[Port]:
        """Search global UN/LOCODE database."""
        return await self.directory_client.search_ports(query)

    async def get_port_by_id(self, port_id: str, user_id: Optional[str] = None) -> Port:
        """Find a port by ID in user monitored ports or global database."""
        if user_id:
            with get_db_context() as db:
                user_port = (
                    db.query(MonitoredPort)
                    .filter(MonitoredPort.id == port_id, MonitoredPort.user_id == user_id)
                    .first()
                )
                if user_port:
                    return self._enrich_with_wpi(user_port.to_pydantic())

        # Search directory database directly by ID or UN/LOCODE
        db_port = self.directory_client.get_port_by_id(port_id)
        if db_port:
            return db_port

        locode_port = self.directory_client.get_port_by_locode(port_id)
        if locode_port:
            return locode_port

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Port with ID or UN/LOCODE '{port_id}' not found.",
        )

    async def add_port(self, request: CreatePortRequest, user_id: str) -> Port:
        """Add a custom monitored port scoped privately to the user in the database."""
        with get_db_context() as db:
            # Check if already added by this user for the same vessel class
            existing = (
                db.query(MonitoredPort)
                .filter(
                    MonitoredPort.user_id == user_id,
                    MonitoredPort.locode == request.locode.upper(),
                    MonitoredPort.vessel_class == request.vesselClass,
                )
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Port with UN/LOCODE '{request.locode}' is already monitored for vessel class '{request.vesselClass}' by this user.",
                )

            port_id = f"port-user-{int(time.time())}-{uuid.uuid4().hex[:6]}"
            db_port = MonitoredPort(
                id=port_id,
                user_id=user_id,
                name=request.name,
                locode=request.locode.upper(),
                country=request.country,
                lat=request.lat,
                lon=request.lon,
                is_default=False,
                geofence_radius_nm=request.geofenceRadiusNm,
                vessel_class=request.vesselClass,
                notifications_enabled=getattr(request, "notificationsEnabled", True),
            )
            db.add(db_port)
            db.commit()
            db.refresh(db_port)

            try:
                from app.clients.ais_stream_manager import get_stream_manager
                get_stream_manager().register_ports([{
                    "id": db_port.id,
                    "locode": db_port.locode,
                    "name": db_port.name,
                    "lat": db_port.lat,
                    "lon": db_port.lon,
                    "geofence": db_port.geofence_radius_nm,
                    "vessel_class": db_port.vessel_class,
                }])
            except Exception as e:
                logger.debug("Stream manager registration: %s", str(e))

            return db_port.to_pydantic()

    async def update_port_notifications(
        self, port_id: str, user_id: str, notifications_enabled: bool
    ) -> Port:
        """Update notification opt-in/opt-out status for a monitored port in the database."""
        with get_db_context() as db:
            db_port = (
                db.query(MonitoredPort)
                .filter(MonitoredPort.id == port_id, MonitoredPort.user_id == user_id)
                .first()
            )
            if db_port:
                db_port.notifications_enabled = notifications_enabled
                db.commit()
                db.refresh(db_port)
                return self._enrich_with_wpi(db_port.to_pydantic())

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Port with ID '{port_id}' not found in user's monitored list.",
        )

    async def remove_port(self, port_id: str, user_id: str) -> None:
        """Remove a port from the user's monitored portfolio in the database."""
        with get_db_context() as db:
            db_port = (
                db.query(MonitoredPort)
                .filter(MonitoredPort.id == port_id, MonitoredPort.user_id == user_id)
                .first()
            )
            if db_port:
                locode = db_port.locode
                db.delete(db_port)
                db.commit()

                try:
                    from app.clients.ais_stream_manager import get_stream_manager
                    still_monitored = db.query(MonitoredPort).filter(MonitoredPort.locode == locode).first()
                    if not still_monitored:
                        get_stream_manager().unregister_port(port_id, locode)
                except Exception as e:
                    logger.debug("Stream manager unregister: %s", str(e))
                return

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Port with ID '{port_id}' not found in user's monitored list.",
        )


# Singleton instance for the application
port_service = PortService()
