"""GridPulse REST API.

The dashboard talks to these endpoints instead of querying PostgreSQL directly.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from gridpulse import __version__
from gridpulse.api.schemas import CurrentOut, HistoryOut, HistoryPoint, RegionOut
from gridpulse.config import REGIONS, get_settings
from gridpulse.db import session_scope
from gridpulse.kpi import demand_history, latest_reading, window_kpis

app = FastAPI(title="GridPulse API", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

WindowHours = Query(24, ge=1, le=720, description="Lookback window in hours")


def get_session() -> Iterator[Session]:
    yield from session_scope()


def resolve_region(region: str = Query("PJM", description="EIA respondent code")) -> str:
    code = region.upper()
    if code not in REGIONS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown region '{region}'. Tracked regions: {', '.join(REGIONS)}",
        )
    return code


@app.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    session.execute(text("SELECT 1"))
    return {"status": "ok", "version": __version__}


@app.get("/api/grid/regions", response_model=list[RegionOut])
def list_regions() -> list[RegionOut]:
    return [
        RegionOut(region_code=code, region_name=name) for code, name in REGIONS.items()
    ]


@app.get("/api/grid/current", response_model=CurrentOut)
def current(
    region: str = Depends(resolve_region),
    hours: int = WindowHours,
    session: Session = Depends(get_session),
) -> CurrentOut:
    latest = latest_reading(session, region)
    if latest is None:
        raise HTTPException(
            status_code=404,
            detail=f"No data stored for {region}. Run the pipeline or `python -m gridpulse.seed`.",
        )

    window = window_kpis(session, region, datetime.now(UTC) - timedelta(hours=hours))

    return CurrentOut(
        region=region,
        region_name=REGIONS[region],
        timestamp=latest["timestamp"],
        window_hours=hours,
        demand_mw=latest["actual_demand_mw"],
        forecast_mw=latest["forecast_demand_mw"],
        generation_mw=latest["net_generation_mw"],
        interchange_mw=latest["interchange_mw"],
        forecast_error_pct=latest["forecast_error_pct"],
        ramp_mw=latest["ramp_mw"],
        peak_demand_mw=window["peak_demand_mw"],
        load_factor_pct=window["load_factor_pct"],
    )


@app.get("/api/grid/history", response_model=HistoryOut)
def history(
    region: str = Depends(resolve_region),
    hours: int = WindowHours,
    session: Session = Depends(get_session),
) -> HistoryOut:
    rows = demand_history(session, region, datetime.now(UTC) - timedelta(hours=hours))
    return HistoryOut(
        region=region,
        window_hours=hours,
        points=[
            HistoryPoint(
                timestamp=row["timestamp"],
                demand_mw=row["actual_demand_mw"],
                forecast_mw=row["forecast_demand_mw"],
            )
            for row in rows
        ],
    )
