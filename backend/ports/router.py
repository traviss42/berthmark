"""FastAPI router for Port Directory, Search, and User Watchlist endpoints."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.auth.schemas import ErrorResponse
from backend.database import get_db_session
from backend.models import User
from backend.ports.schemas import PortCreate, PortResponse
from backend.ports.service import (
    add_user_watchlist_port,
    get_default_ports,
    get_port_by_id,
    get_user_monitored_ports,
    remove_user_watchlist_port,
    search_ports,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ports", tags=["Ports"])


@router.get(
    "",
    response_model=list[PortResponse],
    summary="Get monitored ports for the user",
    responses={
        200: {"description": "List of monitored ports.", "model": list[PortResponse]},
        401: {"description": "Unauthorized.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def list_monitored_ports(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[PortResponse]:
    """Retrieve all ports monitored by the authenticated user (defaults + watchlist)."""
    try:
        return await get_user_monitored_ports(session, current_user.id)
    except Exception as exc:
        logger.exception("Failed to retrieve monitored ports for user %s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": "Failed to retrieve monitored ports.",
                "statusCode": 500,
            },
        )


@router.post(
    "",
    response_model=PortResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a custom monitored port",
    responses={
        201: {"description": "Port successfully added to user watchlist.", "model": PortResponse},
        400: {"description": "Bad Request.", "model": ErrorResponse},
        401: {"description": "Unauthorized.", "model": ErrorResponse},
        409: {"description": "Port with LOCODE already exists in user watchlist.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def add_monitored_port(
    port_data: PortCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortResponse:
    """Add a new private monitored port to the authenticated user's watchlist."""
    return await add_user_watchlist_port(session, current_user.id, port_data)


@router.get(
    "/default",
    response_model=list[PortResponse],
    summary="Get system default benchmark ports",
    responses={
        200: {"description": "List of system default ports.", "model": list[PortResponse]},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def list_default_ports(
    session: AsyncSession = Depends(get_db_session),
) -> list[PortResponse]:
    """Retrieve global default commercial benchmark ports."""
    try:
        return await get_default_ports(session)
    except Exception as exc:
        logger.exception("Failed to retrieve default ports: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": "Failed to retrieve default ports.",
                "statusCode": 500,
            },
        )


@router.get(
    "/search",
    response_model=list[PortResponse],
    summary="Search ports directory",
    responses={
        200: {"description": "List of matching ports.", "model": list[PortResponse]},
        400: {"description": "Missing or empty query parameter.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def search_ports_directory(
    q: str | None = Query(None, description="Search query string"),
    session: AsyncSession = Depends(get_db_session),
) -> list[PortResponse]:
    """Search ports directory by name, UN/LOCODE, or country."""
    if q is None or not q.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Bad Request",
                "message": "Search query parameter 'q' must not be empty.",
                "statusCode": 400,
            },
        )

    try:
        return await search_ports(session, q.strip())
    except Exception as exc:
        logger.exception("Failed searching ports: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": "Search query failed.",
                "statusCode": 500,
            },
        )


@router.get(
    "/{portId}",
    response_model=PortResponse,
    summary="Get port by ID",
    responses={
        200: {"description": "Port details.", "model": PortResponse},
        404: {"description": "Port not found.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def get_port(
    portId: str,
    session: AsyncSession = Depends(get_db_session),
) -> PortResponse:
    """Retrieve details of a specific port by its unique ID or UN/LOCODE."""
    try:
        port = await get_port_by_id(session, portId)
    except Exception as exc:
        logger.exception("Failed looking up port '%s': %s", portId, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": "Database query failed.",
                "statusCode": 500,
            },
        )

    if port is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "Not Found",
                "message": f"Port '{portId}' was not found.",
                "statusCode": 404,
            },
        )

    return port


@router.delete(
    "/{portId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a custom monitored port",
    responses={
        204: {"description": "Port successfully removed from user watchlist."},
        400: {"description": "Attempted to remove a system default port.", "model": ErrorResponse},
        401: {"description": "Unauthorized.", "model": ErrorResponse},
        403: {"description": "Port belongs to another user.", "model": ErrorResponse},
        404: {"description": "Port not found.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def delete_monitored_port(
    portId: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Remove a custom port from the authenticated user's watchlist."""
    await remove_user_watchlist_port(session, current_user.id, portId)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
