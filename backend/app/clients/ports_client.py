"""Client for external UN/LOCODE and World Port Index registry with fallback data."""

import logging
from typing import List, Optional
import httpx
from app.config import get_settings
from app.models.port import Port

logger = logging.getLogger(__name__)

# Fallback reference ports catalog
FALLBACK_GLOBAL_PORTS: List[dict] = [
    {"id": "port-rotterdam", "name": "Port of Rotterdam", "locode": "NLRTM", "country": "Netherlands", "lat": 51.9244, "lon": 4.4777, "isDefault": True, "geofenceRadiusNm": 8.0, "addedByUserId": None},
    {"id": "port-singapore", "name": "Port of Singapore", "locode": "SGSIN", "country": "Singapore", "lat": 1.2648, "lon": 103.8408, "isDefault": True, "geofenceRadiusNm": 10.0, "addedByUserId": None},
    {"id": "port-shanghai", "name": "Port of Shanghai", "locode": "CNSHA", "country": "China", "lat": 31.2304, "lon": 121.4737, "isDefault": True, "geofenceRadiusNm": 10.0, "addedByUserId": None},
    {"id": "port-hamburg", "name": "Port of Hamburg", "locode": "DEHAM", "country": "Germany", "lat": 53.5399, "lon": 9.9472, "isDefault": True, "geofenceRadiusNm": 7.0, "addedByUserId": None},
    {"id": "port-losangeles", "name": "Port of Los Angeles", "locode": "USLAX", "country": "United States", "lat": 33.7291, "lon": -118.2639, "isDefault": True, "geofenceRadiusNm": 8.0, "addedByUserId": None},
    {"id": "port-jebelali", "name": "Port of Jebel Ali", "locode": "AEJEA", "country": "United Arab Emirates", "lat": 24.9857, "lon": 55.0273, "isDefault": True, "geofenceRadiusNm": 8.0, "addedByUserId": None},
    {"id": "port-antwerp", "name": "Port of Antwerp-Bruges", "locode": "BEANR", "country": "Belgium", "lat": 51.3, "lon": 4.3, "isDefault": False, "geofenceRadiusNm": 8.0, "addedByUserId": None},
    {"id": "port-hongkong", "name": "Port of Hong Kong", "locode": "HKHKG", "country": "Hong Kong", "lat": 22.3, "lon": 114.2, "isDefault": False, "geofenceRadiusNm": 8.0, "addedByUserId": None},
    {"id": "port-busan", "name": "Port of Busan", "locode": "KRPUS", "country": "South Korea", "lat": 35.1, "lon": 129.0, "isDefault": False, "geofenceRadiusNm": 8.0, "addedByUserId": None},
    {"id": "port-savannah", "name": "Port of Savannah", "locode": "USSAV", "country": "United States", "lat": 32.1, "lon": -81.1, "isDefault": False, "geofenceRadiusNm": 7.0, "addedByUserId": None},
    {"id": "port-longbeach", "name": "Port of Long Beach", "locode": "USLGB", "country": "United States", "lat": 33.8, "lon": -118.2, "isDefault": False, "geofenceRadiusNm": 7.0, "addedByUserId": None},
    {"id": "port-tanjungpelepas", "name": "Tanjung Pelepas", "locode": "MYTPP", "country": "Malaysia", "lat": 1.4, "lon": 103.5, "isDefault": False, "geofenceRadiusNm": 8.0, "addedByUserId": None},
    {"id": "port-jawaharnehru", "name": "Jawaharlal Nehru Port", "locode": "INNSA", "country": "India", "lat": 18.9, "lon": 72.9, "isDefault": False, "geofenceRadiusNm": 8.0, "addedByUserId": None},
    {"id": "port-suez", "name": "Suez Canal Port", "locode": "EGSUZ", "country": "Egypt", "lat": 30.0, "lon": 32.5, "isDefault": False, "geofenceRadiusNm": 10.0, "addedByUserId": None},
    {"id": "port-piraeus", "name": "Port of Piraeus", "locode": "GRPIR", "country": "Greece", "lat": 37.9, "lon": 23.6, "isDefault": False, "geofenceRadiusNm": 7.0, "addedByUserId": None},
    {"id": "port-valencia", "name": "Port of Valencia", "locode": "ESVLC", "country": "Spain", "lat": 39.4, "lon": -0.3, "isDefault": False, "geofenceRadiusNm": 7.0, "addedByUserId": None},
    {"id": "port-santos", "name": "Port of Santos", "locode": "BRSSZ", "country": "Brazil", "lat": -23.9, "lon": -46.3, "isDefault": False, "geofenceRadiusNm": 8.0, "addedByUserId": None},
    {"id": "port-durban", "name": "Port of Durban", "locode": "ZADUR", "country": "South Africa", "lat": -29.9, "lon": 31.0, "isDefault": False, "geofenceRadiusNm": 8.0, "addedByUserId": None},
]


class PortDirectoryClient:
    """Client for port reference and geocoding directory with fallback lookup."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        settings = get_settings()
        self.base_url = base_url or settings.PORTS_API_BASE_URL
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS

    def _fallback_search(self, query: str) -> List[Port]:
        q = query.lower().strip()
        if not q:
            return []
        results: List[Port] = []
        for item in FALLBACK_GLOBAL_PORTS:
            if (
                q in item["name"].lower()
                or q in item["locode"].lower()
                or q in item["country"].lower()
            ):
                results.append(Port(**item))
        return results

    async def search_ports(self, query: str) -> List[Port]:
        """Search global port registry by query."""
        if not query.strip():
            return []

        # If external registry URL is configured and network available
        if self.base_url.startswith("http"):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(
                        f"{self.base_url}/search", params={"query": query.strip()}
                    )
                    if resp.status_code == 200:
                        items = resp.json()
                        return [Port(**item) for item in items]
            except Exception as e:
                logger.debug("External port search failed: %s; falling back to local dataset.", str(e))

        return self._fallback_search(query)
