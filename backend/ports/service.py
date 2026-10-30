"""Service layer for port directory lookups, default benchmark ports, search, and user watchlist management."""

import re
import uuid
from typing import Any
from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from backend.models import Port, UserWatchlist, VesselClass
from backend.ports.schemas import PortCreate, PortResponse

# Canonical country code to country name mapping for common maritime jurisdictions
COUNTRY_NAMES: dict[str, str] = {
    "NL": "Netherlands",
    "SG": "Singapore",
    "US": "United States",
    "CA": "Canada",
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


async def seed_benchmark_ports(session: AsyncSession) -> int:
    """Idempotently seed the default benchmark ports in the ports table without fake traffic baselines."""
    seeded = 0
    for locode, meta in BENCHMARK_PORTS_METADATA.items():
        stmt = select(Port).where(Port.unlocode == locode)
        port = (await session.execute(stmt)).scalar_one_or_none()
        if port is None:
            port = Port(
                unlocode=locode,
                port_name=meta["name"],
                country_code=meta["country_code"],
                subdivision_code="",
                latitude=meta["lat"],
                longitude=meta["lon"],
                channel_depth_m=12.0,
                is_depth_available=True,
                reconciliation_method="BENCHMARK_DEFAULT",
            )
            session.add(port)
            seeded += 1
    await session.commit()
    return seeded


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

    stmt = (
        select(Port)
        .where(
            Port.latitude.isnot(None),
            Port.longitude.isnot(None),
            or_(*filters),
        )
        .limit(limit)
    )
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

    # Check if format is user-watchlist specific ID: port-user-<watchlist_uuid>
    if clean_id.lower().startswith("port-user-"):
        try:
            w_uuid = uuid.UUID(clean_id[10:])
            uw_res = await session.execute(
                select(UserWatchlist).options(selectinload(UserWatchlist.port)).where(UserWatchlist.watchlist_id == w_uuid)
            )
            uw = uw_res.scalar_one_or_none()
            if uw and uw.port:
                country = COUNTRY_NAMES.get(uw.port.country_code.upper(), uw.port.country_code)
                return PortResponse(
                    id=clean_id,
                    name=uw.port.port_name,
                    locode=uw.port.unlocode.upper(),
                    country=country,
                    lat=round(float(uw.port.latitude), 6),
                    lon=round(float(uw.port.longitude), 6),
                    isDefault=False,
                    geofenceRadiusNm=float(uw.geofence_radius_nm) if uw.geofence_radius_nm is not None else 8.0,
                    addedByUserId=str(uw.user_id),
                    vesselClass=uw.vessel_class_id,
                )
        except ValueError:
            pass

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


async def get_user_monitored_ports(
    session: AsyncSession, user_id: uuid.UUID
) -> list[PortResponse]:
    """Retrieve user's custom watchlist ports."""
    stmt = (
        select(UserWatchlist)
        .options(selectinload(UserWatchlist.port))
        .where(UserWatchlist.user_id == user_id)
        .order_by(UserWatchlist.created_at)
    )
    res = await session.execute(stmt)
    watchlist_entries = res.scalars().all()

    custom_ports: list[PortResponse] = []
    for uw in watchlist_entries:
        port = uw.port
        country = COUNTRY_NAMES.get(port.country_code.upper(), port.country_code)
        custom_ports.append(
            PortResponse(
                id=f"port-user-{uw.watchlist_id}",
                name=port.port_name,
                locode=port.unlocode.upper(),
                country=country,
                lat=round(float(port.latitude), 6),
                lon=round(float(port.longitude), 6),
                isDefault=False,
                geofenceRadiusNm=float(uw.geofence_radius_nm) if uw.geofence_radius_nm is not None else 8.0,
                addedByUserId=str(user_id),
                vesselClass=uw.vessel_class_id,
            )
        )

    return custom_ports


async def add_user_watchlist_port(
    session: AsyncSession, user_id: uuid.UUID, port_data: PortCreate
) -> PortResponse:
    """Add a custom monitored port to the authenticated user's watchlist."""
    locode_clean = port_data.locode.strip().upper()

    vessel_class_input = (port_data.vesselClass or "panamax").strip()
    vc_result = await session.execute(
        select(VesselClass).where(func.lower(VesselClass.class_id) == vessel_class_input.lower())
    )
    matched_vc = vc_result.scalar_one_or_none()
    effective_vc_id = matched_vc.class_id if matched_vc else vessel_class_input

    # Check if this (port, vessel_class) pair is already in the user's watchlist
    stmt = select(UserWatchlist).where(
        UserWatchlist.user_id == user_id,
        UserWatchlist.unlocode == locode_clean,
        UserWatchlist.vessel_class_id == effective_vc_id,
    )
    existing_entry = (await session.execute(stmt)).scalar_one_or_none()
    if existing_entry:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "Conflict",
                "message": f"Port with LOCODE '{locode_clean}' is already in your watchlist."
                if not port_data.vesselClass
                else f"Port with LOCODE '{locode_clean}' and vessel class '{effective_vc_id}' is already in your watchlist.",
                "statusCode": 409,
            },
        )

    # Ensure Port record exists in database
    port_stmt = select(Port).where(Port.unlocode == locode_clean)
    port = (await session.execute(port_stmt)).scalar_one_or_none()
    if port is None:
        port = Port(
            unlocode=locode_clean,
            port_name=port_data.name.strip(),
            country_code=locode_clean[:2],
            subdivision_code="",
            latitude=port_data.lat,
            longitude=port_data.lon,
            wpi_number=None,
            channel_depth_m=15.0,
            cargo_pier_depth_m=None,
            anchorage_depth_m=None,
            is_depth_available=True,
            reconciliation_method="USER_CUSTOM",
        )
        session.add(port)
        await session.flush()

    new_watchlist_id = uuid.uuid4()
    watchlist_entry = UserWatchlist(
        watchlist_id=new_watchlist_id,
        user_id=user_id,
        unlocode=locode_clean,
        vessel_class_id=effective_vc_id,
        geofence_radius_nm=port_data.geofenceRadiusNm,
    )
    session.add(watchlist_entry)
    await session.commit()

    return PortResponse(
        id=f"port-user-{new_watchlist_id}",
        name=port_data.name.strip(),
        locode=locode_clean,
        country=port_data.country.strip(),
        lat=round(float(port_data.lat), 6),
        lon=round(float(port_data.lon), 6),
        isDefault=False,
        geofenceRadiusNm=port_data.geofenceRadiusNm,
        addedByUserId=str(user_id),
        vesselClass=effective_vc_id,
    )


async def remove_user_watchlist_port(
    session: AsyncSession, user_id: uuid.UUID, port_id: str
) -> None:
    """Remove a custom monitored port from the user's watchlist."""
    clean_id = port_id.strip()

    # Reject removal of system default benchmark ports
    for locode, meta in BENCHMARK_PORTS_METADATA.items():
        if clean_id.lower() == meta["id"].lower() or clean_id.upper() == locode:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Bad Request",
                    "message": "System default ports cannot be removed.",
                    "statusCode": 400,
                },
            )

    # Attempt lookup by watchlist UUID
    target_uuid = None
    if clean_id.lower().startswith("port-user-"):
        try:
            target_uuid = uuid.UUID(clean_id[10:])
        except ValueError:
            pass
    else:
        try:
            target_uuid = uuid.UUID(clean_id)
        except ValueError:
            pass

    if target_uuid:
        stmt = select(UserWatchlist).where(UserWatchlist.watchlist_id == target_uuid)
        entry = (await session.execute(stmt)).scalar_one_or_none()
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "Not Found",
                    "message": f"Port '{port_id}' not found.",
                    "statusCode": 404,
                },
            )
        if entry.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Forbidden",
                    "message": "You do not have permission to delete this port.",
                    "statusCode": 403,
                },
            )
        await session.delete(entry)
        await session.commit()
        return

    # Attempt lookup by LOCODE
    locode_candidate = clean_id[5:].upper() if clean_id.lower().startswith("port-") else clean_id.upper()
    stmt = select(UserWatchlist).where(UserWatchlist.unlocode == locode_candidate)
    entries = (await session.execute(stmt)).scalars().all()
    if not entries:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "Not Found",
                "message": f"Port '{port_id}' not found.",
                "statusCode": 404,
            },
        )

    user_entry = next((e for e in entries if e.user_id == user_id), None)
    if user_entry:
        await session.delete(user_entry)
        await session.commit()
        return

    # If entries exist but belong to other users
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "Forbidden",
            "message": "You do not have permission to delete this port.",
            "statusCode": 403,
        },
    )
