"""Pydantic schemas for Vessel Benchmark Taxonomy API."""

from pydantic import BaseModel, ConfigDict


class VesselClassInfo(BaseModel):
    """Schema representing vessel benchmark class metadata matching OpenAPI."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    sector: str
    criteria: str
    significance: str
