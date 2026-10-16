"""Port directory client querying the local UN/LOCODE SQLite database."""

import logging
from typing import List, Optional
from app.clients.unlocode_db import UnlocodeDatabase
from app.config import get_settings
from app.models.port import Port

logger = logging.getLogger(__name__)


class PortDirectoryClient:
    """Client for port reference and UN/LOCODE directory search using UN/LOCODE SQLite database."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        db: Optional[UnlocodeDatabase] = None,
    ):
        settings = get_settings()
        self.base_url = base_url or settings.PORTS_API_BASE_URL
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self._db = db

    @property
    def db(self) -> UnlocodeDatabase:
        if self._db is None:
            self._db = UnlocodeDatabase()
        return self._db

    async def search_ports(self, query: str) -> List[Port]:
        """Search global UN/LOCODE port registry by LOCODE, port name, or country."""
        q = query.strip()
        if not q:
            return []
        return self.db.search_ports(q, limit=50)

    def get_port_by_locode(self, locode: str) -> Optional[Port]:
        """Retrieve port by UN/LOCODE directly from the database."""
        return self.db.get_port_by_locode(locode)

    def get_port_by_id(self, port_id: str) -> Optional[Port]:
        """Retrieve port by ID directly from the database."""
        return self.db.get_port_by_id(port_id)

    def get_default_ports(self) -> List[Port]:
        """Retrieve all default monitored ports from the database."""
        return self.db.get_default_ports()
