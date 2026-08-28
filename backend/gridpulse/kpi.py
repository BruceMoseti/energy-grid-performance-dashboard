"""Grid performance KPIs, expressed as SQL against grid_load."""

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

# Only the two most recent readings are needed for a 1-hour ramp, and LIMIT 2
# lets the (region_id, timestamp) primary key satisfy the whole scan.
_LATEST_SQL = text(
    """
    WITH last_two AS (
        SELECT gl.timestamp,
               gl.actual_demand_mw,
               gl.forecast_demand_mw,
               gl.net_generation_mw,
               gl.interchange_mw
        FROM grid_load gl
        JOIN regions r ON r.region_id = gl.region_id
        WHERE r.region_code = :region_code
          AND gl.actual_demand_mw IS NOT NULL
        ORDER BY gl.timestamp DESC
        LIMIT 2
    )
    SELECT timestamp,
           actual_demand_mw,
           forecast_demand_mw,
           net_generation_mw,
           interchange_mw,
           actual_demand_mw
               - LEAD(actual_demand_mw) OVER (ORDER BY timestamp DESC) AS ramp_mw,
           ABS(actual_demand_mw - forecast_demand_mw)
               / NULLIF(actual_demand_mw, 0) * 100 AS forecast_error_pct
    FROM last_two
    ORDER BY timestamp DESC
    LIMIT 1
    """
)

_WINDOW_SQL = text(
    """
    SELECT MAX(gl.actual_demand_mw) AS peak_demand_mw,
           AVG(gl.actual_demand_mw) AS avg_demand_mw,
           AVG(gl.actual_demand_mw) / NULLIF(MAX(gl.actual_demand_mw), 0) * 100
               AS load_factor_pct,
           AVG(ABS(gl.actual_demand_mw - gl.forecast_demand_mw)
               / NULLIF(gl.actual_demand_mw, 0) * 100) AS forecast_error_pct,
           COUNT(*) AS sample_hours
    FROM grid_load gl
    JOIN regions r ON r.region_id = gl.region_id
    WHERE r.region_code = :region_code
      AND gl.timestamp >= :since
      AND gl.actual_demand_mw IS NOT NULL
    """
)

_HISTORY_SQL = text(
    """
    SELECT gl.timestamp,
           gl.actual_demand_mw,
           gl.forecast_demand_mw
    FROM grid_load gl
    JOIN regions r ON r.region_id = gl.region_id
    WHERE r.region_code = :region_code
      AND gl.timestamp >= :since
    ORDER BY gl.timestamp
    """
)


def latest_reading(session: Session, region_code: str) -> dict | None:
    """Most recent hour with a demand figure, plus its 1-hour ramp."""
    row = session.execute(_LATEST_SQL, {"region_code": region_code}).mappings().first()
    return dict(row) if row else None


def window_kpis(session: Session, region_code: str, since: datetime) -> dict:
    """Peak, average, load factor and mean absolute forecast error over a window."""
    row = session.execute(
        _WINDOW_SQL, {"region_code": region_code, "since": since}
    ).mappings().one()
    return dict(row)


def demand_history(session: Session, region_code: str, since: datetime) -> list[dict]:
    """Hourly actual-vs-forecast demand series for charting."""
    rows = session.execute(
        _HISTORY_SQL, {"region_code": region_code, "since": since}
    ).mappings()
    return [dict(row) for row in rows]
