"""Service layer for port directory lookups, default benchmark ports, and search."""

from typing import Any
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Port
from backend.ports.schemas import PortResponse

# Canonical country code to country name mapping for common maritime jurisdictions
COUNTRY_NAMES: dict[str, str] = {
    "NL": "Netherlands",
    "SG": "Singapore",
    "US": "United States",
    "BE": "Belgium",
    "CN": "China",
    "DE": "Germany",
    "FR": "France",
    "GB": "United Kingdom",
    "ES": "Spain",
    "IT": "Italy",
    "JP": "Japan",
    "KR": "South Korea",
    "AE": "United Arab Emirates",
    "SA": "Saudi Arabia",
    "BR": "Brazil",
    "AU": "Australia",
    "IN": "India",
}

# System default benchmark ports
BENCHMARK_PORTS_METADATA: dict[str, dict[str, Any]] = {
    "NLRTM": {
        "id": "port-rotterdam",
        "name": "Port of Rotterdam",
        "locode": "NLRTM",
        "country": "Netherlands",
        "country_code": "NL",
        "lat": 51.9244,
        "lon": 4.4777,
        "geofenceRadiusNm": 8.0,
    },
    "SGSIN": {
        "id": "port-singapore",
        "name": "Port of Singapore",
        "locode": "SGSIN",
        "country": "Singapore",
        "country_code": "SG",
        "lat": 1.2648,
        "lon": 103.8408,
        "geofenceRadiusNm": 10.0,
    },
    "USHOU": {
        "id": "port-houston",
        "name": "Port of Houston",
        "locode": "USHOU",
        "country": "United States",
        "country_code": "US",
        "lat": 29.75,
        "lon": -95.28,
        "geofenceRadiusNm": 12.0,
    },
    "BEANR": {
        "id": "port-antwerp",
        "name": "Port of Antwerp-Bruges",
        "locode": "BEANR",
        "country": "Belgium",
        "country_code": "BE",
        "lat": 51.22,
        "lon": 4.40,
        "geofenceRadiusNm": 8.0,
    },
    "CNSHA": {
        "id": "port-shanghai",
        "name": "Port of Shanghai",
        "locode": "CNSHA",
        "country": "China",
        "country_code": "CN",
        "lat": 31.23,
        "lon": 121.47,
        "geofenceRadiusNm": 15.0,
    },
}


def port_to_response(port: Port, is_default: bool = False) -> PortResponse:
    """Format SQLAlchemy Port entity into API PortResponse schema."""
    locode_upper = port.unlocode.upper()
    benchmark_meta = BENCHMARK_PORTS_METADATA.get(locode_upper)

    if benchmark_meta:
        port_id = benchmark_meta["id"]
        display_name = benchmark_meta["name"]
        country = benchmark_meta["country"]
        radius = float(benchmark_meta["geofenceRadiusNm"])
    else:
        port_id = f"port-{locode_upper.lower()}"
        display_name = port.port_name
        country = COUNTRY_NAMES.get(port.country_code.upper(), port.country_code)
        radius = 8.0

    return PortResponse(
        id=port_id,
        name=display_name,
        locode=locode_upper,
        country=country,
        lat=round(float(port.latitude), 6),
        lon=round(float(port.longitude), 6),
        isDefault=is_default or (benchmark_meta is not None),
        geofenceRadiusNm=radius,
        addedByUserId=None,
    )


async def get_default_ports(session: AsyncSession) -> list[PortResponse]:
    """Retrieve system benchmark ports, querying database for actual records."""
    locodes = list(BENCHMARK_PORTS_METADATA.keys())
    result = await session.execute(select(Port).where(Port.unlocode.in_(locodes)))
    db_ports = {p.unlocode.upper(): p for p in result.scalars().all()}

    responses: list[PortResponse] = []
    for locode, meta in BENCHMARK_PORTS_METADATA.items():
        if locode in db_ports:
            responses.append(port_to_response(db_ports[locode], is_default=True))
        else:
            responses.append(
                PortResponse(
                    id=meta["id"],
                    name=meta["name"],
                    locode=meta["locode"],
                    country=meta["country"],
                    lat=meta["lat"],
                    lon=meta["lon"],
                    isDefault=True,
                    geofenceRadiusNm=meta["geofenceRadiusNm"],
                    addedByUserId=None,
                )
            )
    return responses


async def search_ports(
    session: AsyncSession, query_str: str, limit: int = 50
) -> list[PortResponse]:
    """Search ports directory by name, UN/LOCODE, or country."""
    clean_q = query_str.strip().lower()
    if not clean_q:
        return []

    # Match country codes corresponding to query
    matched_country_codes = [
        code.lower()
        for code, name in COUNTRY_NAMES.items()
        if clean_q in name.lower() or clean_q == code.lower()
    ]

    filters = [
        func.lower(Port.unlocode).like(f"%{clean_q}%"),
        func.lower(Port.port_name).like(f"%{clean_q}%"),
    ]
    if matched_country_codes:
        filters.append(func.lower(Port.country_code).in_(matched_country_codes))
    else:
        filters.append(func.lower(Port.country_code) == clean_q)

    stmt = select(Port).where(or_(*filters)).limit(limit)
    result = await session.execute(stmt)
    records = result.scalars().all()

    return [port_to_response(p) for p in records]


async def get_port_by_id(session: AsyncSession, port_id: str) -> PortResponse | None:
    """Lookup port by 5-character UN/LOCODE or designated port ID."""
    clean_id = port_id.strip()
    if not clean_id:
        return None

    # Check designated benchmark ID
    locode_match = None
    for locode, meta in BENCHMARK_PORTS_METADATA.items():
        if meta["id"].lower() == clean_id.lower() or locode.lower() == clean_id.lower():
            locode_match = locode
            break

    if locode_match:
        result = await session.execute(select(Port).where(Port.unlocode == locode_match))
        port = result.scalar_one_or_none()
        if port:
            return port_to_response(port)
        # Fallback to metadata if unseeded
        meta = BENCHMARK_PORTS_METADATA[locode_match]
        return PortResponse(
            id=meta["id"],
            name=meta["name"],
            locode=meta["locode"],
            country=meta["country"],
            lat=meta["lat"],
            lon=meta["lon"],
            isDefault=True,
            geofenceRadiusNm=meta["geofenceRadiusNm"],
            addedByUserId=None,
        )

    # If format is port-<locode>
    if clean_id.lower().startswith("port-"):
        candidate_locode = clean_id[5:].upper()
    else:
        candidate_locode = clean_id.upper()

    result = await session.execute(
        select(Port).where(func.upper(Port.unlocode) == candidate_locode)
    )
    port = result.scalar_one_or_none()
    if port:
        return port_to_response(port)

    return None
