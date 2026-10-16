"""Port management endpoints implementing openapi.yaml specifications."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from app.auth.dependencies import get_current_user, get_optional_current_user
from app.models.port import CreatePortRequest, Port
from app.services.port_service import PortService, port_service

router = APIRouter(prefix="/api/v1/ports", tags=["Ports"])


@router.get(
    "",
    response_model=List[Port],
    summary="Get monitored ports for the authenticated user",
    description="Returns global default ports plus custom ports added by the authenticated user.",
)
async def get_monitored_ports(
    current_user: str = Depends(get_current_user),
    service: PortService = Depends(lambda: port_service),
) -> List[Port]:
    return await service.get_ports(user_id=current_user)


@router.post(
    "",
    response_model=Port,
    status_code=status.HTTP_201_CREATED,
    summary="Add a custom monitored port",
    description="Adds a new private monitored port for the authenticated user.",
)
async def add_monitored_port(
    port_data: CreatePortRequest,
    current_user: str = Depends(get_current_user),
    service: PortService = Depends(lambda: port_service),
) -> Port:
    return await service.add_port(request=port_data, user_id=current_user)


@router.get(
    "/defaults",
    response_model=List[Port],
    summary="Get global default ports",
    description="Returns pre-configured global default maritime hubs.",
)
async def get_default_ports(
    service: PortService = Depends(lambda: port_service),
) -> List[Port]:
    return await service.get_default_ports()


@router.get(
    "/search",
    response_model=List[Port],
    summary="Search ports directory",
    description="Search the port registry by name, UN/LOCODE, or country.",
)
async def search_ports(
    q: str = Query(..., min_length=1, description="Search query string"),
    service: PortService = Depends(lambda: port_service),
) -> List[Port]:
    return await service.search_ports(query=q)


@router.get(
    "/{portId}",
    response_model=Port,
    summary="Get port details by ID",
    description="Retrieve a specific port by its ID.",
)
async def get_port_by_id(
    portId: str,
    current_user: Optional[str] = Depends(get_optional_current_user),
    service: PortService = Depends(lambda: port_service),
) -> Port:
    return await service.get_port_by_id(port_id=portId, user_id=current_user)


@router.delete(
    "/{portId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a custom monitored port",
    description="Removes a custom port from the authenticated user's portfolio.",
)
async def remove_monitored_port(
    portId: str,
    current_user: str = Depends(get_current_user),
    service: PortService = Depends(lambda: port_service),
) -> None:
    await service.remove_port(port_id=portId, user_id=current_user)
