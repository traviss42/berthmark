"""Risk evaluation endpoints implementing openapi.yaml specifications."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from app.auth.dependencies import get_optional_current_user
from app.models.common import VesselClass
from app.models.risk import BulkRiskAssessmentRequest, RiskAssessment
from app.services.risk_service import RiskService, risk_service

router = APIRouter(tags=["Risk"])


@router.get(
    "/api/v1/ports/{portId}/risk",
    response_model=RiskAssessment,
    summary="Get real-time risk assessment for a port and vessel class",
    description="Calculates composite risk score and sub-risk breakdown based on vessel class limits.",
)
async def get_port_risk_assessment(
    portId: str,
    vesselClass: VesselClass = Query(..., description="Target vessel class"),
    portName: Optional[str] = Query(None, description="Optional port name"),
    forceRefresh: bool = Query(False, description="Bypass cache and force fresh data fetch"),
    current_user: Optional[str] = Depends(get_optional_current_user),
    service: RiskService = Depends(lambda: risk_service),
) -> RiskAssessment:
    return await service.get_risk_assessment(
        port_id=portId,
        port_name=portName,
        vessel_class=vesselClass,
        user_id=current_user,
        force_refresh=forceRefresh,
    )


@router.post(
    "/api/v1/risk/bulk-assessments",
    response_model=List[RiskAssessment],
    summary="Bulk evaluate risk assessments for multiple ports",
    description="Computes risk assessments across an array of ports for a given vessel class.",
)
async def get_bulk_risk_assessments(
    request: BulkRiskAssessmentRequest,
    current_user: Optional[str] = Depends(get_optional_current_user),
    service: RiskService = Depends(lambda: risk_service),
) -> List[RiskAssessment]:
    return await service.get_bulk_assessments(
        ports=request.ports,
        vessel_class=request.vesselClass,
        user_id=current_user,
        force_refresh=request.forceRefresh,
    )


@router.get(
    "/api/v1/ports/{portId}/risk/trend",
    response_model=List[RiskAssessment],
    summary="Get historical risk assessments trend",
    description="Returns time-series evaluations over past N days on a 6-hour evaluation cycle.",
)
async def get_historical_risk_trend(
    portId: str,
    vesselClass: VesselClass = Query(..., description="Target vessel class"),
    days: int = Query(7, ge=1, le=30, description="Number of historical days"),
    forceRefresh: bool = Query(False, description="Bypass cache and force fresh data fetch"),
    current_user: Optional[str] = Depends(get_optional_current_user),
    service: RiskService = Depends(lambda: risk_service),
) -> List[RiskAssessment]:
    return await service.get_historical_trend(
        port_id=portId,
        vessel_class=vesselClass,
        days=days,
        user_id=current_user,
        force_refresh=forceRefresh,
    )
