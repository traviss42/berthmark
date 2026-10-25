"""FastAPI router for Risk Assessment endpoints."""

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.schemas import ErrorResponse
from backend.database import get_db_session
from backend.models import Port
from backend.ports.service import BENCHMARK_PORTS_METADATA
from backend.schemas.risk import RiskAssessment
from backend.services.risk_engine import (
    VALID_VESSEL_CLASSES,
    calculate_port_risk,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Risk Assessment"])


async def resolve_port_entity(session: AsyncSession, port_id: str) -> tuple[Port, str, str]:
    """Resolve port entity from database or benchmark metadata by port ID or UN/LOCODE.

    Returns:
        tuple[Port, canonical_port_id, canonical_port_name]
    """
    clean_id = port_id.strip()
    if not clean_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "Not Found",
                "message": f"Port with ID '{port_id}' not found.",
                "statusCode": 404,
            },
        )

    # 1. Check benchmark ports metadata
    locode_match = None
    canonical_id = clean_id
    canonical_name = None
    for locode, meta in BENCHMARK_PORTS_METADATA.items():
        if meta["id"].lower() == clean_id.lower() or locode.lower() == clean_id.lower():
            locode_match = locode
            canonical_id = meta["id"]
            canonical_name = meta["name"]
            break

    if locode_match:
        res = await session.execute(select(Port).where(Port.unlocode == locode_match))
        port = res.scalar_one_or_none()
        if port:
            return port, canonical_id, canonical_name or port.port_name

        # Benchmark port not yet inserted in DB (e.g. isolated test environment)
        meta = BENCHMARK_PORTS_METADATA[locode_match]
        port = Port(
            unlocode=meta["locode"],
            port_name=meta["name"],
            country_code=meta["country"],
            subdivision_code=meta["subdivision"],
            latitude=meta["lat"],
            longitude=meta["lon"],
            wpi_number=meta.get("wpiNumber"),
            channel_depth_m=meta.get("channelDepthM"),
            cargo_pier_depth_m=meta.get("pierDepthM"),
            anchorage_depth_m=meta.get("anchorageDepthM"),
            is_depth_available=meta.get("channelDepthM") is not None,
            reconciliation_method="EXACT_UNLOCODE",
        )
        session.add(port)
        await session.flush()
        return port, canonical_id, canonical_name or port.port_name

    # 2. Check general ports table by UN/LOCODE or port-<locode>
    candidate_locode = clean_id[5:].upper() if clean_id.lower().startswith("port-") else clean_id.upper()
    res = await session.execute(
        select(Port).where(func.upper(Port.unlocode) == candidate_locode)
    )
    port = res.scalar_one_or_none()
    if port:
        return port, clean_id, port.port_name

    # 3. Not found
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "Not Found",
            "message": f"Port with ID '{port_id}' not found.",
            "statusCode": 404,
        },
    )


@router.get(
    "/ports/{portId}/risk",
    response_model=RiskAssessment,
    summary="Get live risk assessment for a port and vessel class",
    responses={
        200: {"description": "Composite risk assessment details.", "model": RiskAssessment},
        400: {"description": "Invalid query parameters.", "model": ErrorResponse},
        404: {"description": "Port not found.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def get_port_risk(
    portId: str,
    vesselClass: str = Query(..., description="Target vessel benchmark class."),
    portName: str | None = Query(None, description="Optional human-readable port name."),
    session: AsyncSession = Depends(get_db_session),
) -> RiskAssessment:
    """Calculate and return composite risk assessment conforming strictly to openapi.yaml."""
    if vesselClass not in VALID_VESSEL_CLASSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Bad Request",
                "message": f"Invalid vesselClass '{vesselClass}'. Must be one of: {sorted(list(VALID_VESSEL_CLASSES))}",
                "statusCode": 400,
            },
        )

    port, canonical_port_id, canonical_port_name = await resolve_port_entity(session, portId)

    display_name = portName if portName is not None else canonical_port_name

    try:
        return await calculate_port_risk(
            session=session,
            port=port,
            vessel_class=vesselClass,
            port_id=canonical_port_id,
            port_name=display_name,
            persist=True,
        )
    except Exception as exc:
        logger.exception("Failed to calculate port risk for port %s, vessel %s: %s", portId, vesselClass, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": f"Failed to calculate risk assessment: {str(exc)}",
                "statusCode": 500,
            },
        )
