"""Port management service implementing multi-tenant isolation and UN/LOCODE directory discovery."""

import time
import uuid
from typing import Dict, List, Optional
from fastapi import HTTPException, status
from app.clients.ports_client import PortDirectoryClient
from app.models.port import CreatePortRequest, Port


class PortService:
    """Service for managing default and user-monitored ports using real UN/LOCODE database."""

    def __init__(self, directory_client: Optional[PortDirectoryClient] = None):
        self.directory_client = directory_client or PortDirectoryClient()

        # In-memory index of default ports from UN/LOCODE SQLite database
        self._default_ports: Dict[str, Port] = {}
        for p in self.directory_client.get_default_ports():
            self._default_ports[p.id] = p

        # In-memory store for custom user ports: user_id -> dict of port_id -> Port
        self._user_ports: Dict[str, Dict[str, Port]] = {}

    async def get_ports(self, user_id: str) -> List[Port]:
        """Return ports monitored by this user (not prepopulated; user selects their own)."""
        return list(self._user_ports.get(user_id, {}).values())

    async def get_default_ports(self) -> List[Port]:
        """Return only default global ports from the UN/LOCODE database."""
        return list(self._default_ports.values())

    async def search_ports(self, query: str) -> List[Port]:
        """Search global UN/LOCODE database."""
        return await self.directory_client.search_ports(query)

    async def get_port_by_id(self, port_id: str, user_id: Optional[str] = None) -> Port:
        """Find a port by ID in user monitored ports, default hubs, or global database."""
        if user_id and user_id in self._user_ports:
            user_port = self._user_ports[user_id].get(port_id)
            if user_port:
                return user_port

        if port_id in self._default_ports:
            return self._default_ports[port_id]

        # Search database directly
        db_port = self.directory_client.get_port_by_id(port_id)
        if db_port:
            return db_port

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Port with ID '{port_id}' not found.",
        )

    async def add_port(self, request: CreatePortRequest, user_id: str) -> Port:
        """Add a custom monitored port scoped privately to the user."""
        if user_id not in self._user_ports:
            self._user_ports[user_id] = {}

        # Check if already added by this user
        for existing in self._user_ports[user_id].values():
            if existing.locode.upper() == request.locode.upper():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Port with UN/LOCODE '{request.locode}' is already monitored by this user.",
                )

        port_id = f"port-user-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        new_port = Port(
            id=port_id,
            name=request.name,
            locode=request.locode.upper(),
            country=request.country,
            lat=request.lat,
            lon=request.lon,
            isDefault=False,
            geofenceRadiusNm=request.geofenceRadiusNm,
            addedByUserId=user_id,
        )

        self._user_ports[user_id][port_id] = new_port
        return new_port

    async def remove_port(self, port_id: str, user_id: str) -> None:
        """Remove a port from the user's monitored portfolio."""
        user_dict = self._user_ports.get(user_id, {})
        if port_id not in user_dict:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Port with ID '{port_id}' not found in user's monitored list.",
            )

        del user_dict[port_id]


# Singleton instance for the application
port_service = PortService()
