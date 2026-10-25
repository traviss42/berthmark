"""FastAPI router for Vessel Taxonomy endpoints."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db_session
from backend.taxonomy.schemas import VesselClassInfo
from backend.taxonomy.service import get_vessel_classes

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Vessel Taxonomy"])


class ErrorResponse(BaseModel):
    error: str
    message: str
    statusCode: int


@router.get(
    "/vessel-classes",
    response_model=list[VesselClassInfo],
    summary="List benchmark vessel classes",
    responses={
        200: {"description": "List of vessel classes.", "model": list[VesselClassInfo]},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def list_vessel_classes(
    session: AsyncSession = Depends(get_db_session),
) -> list[VesselClassInfo]:
    """Retrieve metadata and specifications for all commercial vessel classes."""
    try:
        return await get_vessel_classes(session)
    except Exception as exc:
        logger.exception("Failed to retrieve vessel classes: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": "Failed to retrieve vessel classes from database.",
                "statusCode": 500,
            },
        )
