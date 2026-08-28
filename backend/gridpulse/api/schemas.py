"""Response models for the GridPulse API."""

from datetime import datetime

from pydantic import BaseModel


class RegionOut(BaseModel):
    region_code: str
    region_name: str


class CurrentOut(BaseModel):
    region: str
    region_name: str
    timestamp: datetime
    window_hours: int

    demand_mw: float
    forecast_mw: float | None
    generation_mw: float | None
    interchange_mw: float | None

    forecast_error_pct: float | None
    ramp_mw: float | None
    peak_demand_mw: float | None
    load_factor_pct: float | None


class HistoryPoint(BaseModel):
    timestamp: datetime
    demand_mw: float | None
    forecast_mw: float | None


class HistoryOut(BaseModel):
    region: str
    window_hours: int
    points: list[HistoryPoint]
