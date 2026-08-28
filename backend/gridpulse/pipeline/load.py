"""Load transformed rows into PostgreSQL."""

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from gridpulse.config import EIA_TYPE_TO_COLUMN, REGIONS
from gridpulse.models import GridLoad, Region

VALUE_COLUMNS = list(EIA_TYPE_TO_COLUMN.values())


def ensure_regions(session: Session, regions: dict[str, str] = REGIONS) -> dict[str, int]:
    """Insert any tracked region that is not in the table yet; return code -> id."""
    existing = {
        region.region_code: region.region_id for region in session.scalars(select(Region))
    }

    missing = [code for code in regions if code not in existing]
    if missing:
        session.add_all(
            [Region(region_code=code, region_name=regions[code]) for code in missing]
        )
        session.commit()
        existing = {
            region.region_code: region.region_id
            for region in session.scalars(select(Region))
        }

    return existing


def _to_db_value(value: object) -> float | None:
    """Convert pandas' NaN to NULL so Postgres stores a real null, not float NaN."""
    if value is None or pd.isna(value):
        return None
    return float(value)


def upsert_grid_load(session: Session, frame: pd.DataFrame) -> int:
    """Insert or update grid_load rows. Returns the number of rows written."""
    if frame.empty:
        return 0

    region_ids = ensure_regions(session)
    records = [
        {
            "region_id": region_ids[row["region_code"]],
            "timestamp": row["timestamp"],
            **{column: _to_db_value(row[column]) for column in VALUE_COLUMNS},
        }
        for row in frame.to_dict("records")
        if row["region_code"] in region_ids
    ]
    if not records:
        return 0

    statement = insert(GridLoad).values(records)
    # EIA publishes the four series on different lags, so an incoming null must
    # not clobber a value we already stored for that hour.
    statement = statement.on_conflict_do_update(
        index_elements=[GridLoad.region_id, GridLoad.timestamp],
        set_={
            column: func.coalesce(statement.excluded[column], getattr(GridLoad, column))
            for column in VALUE_COLUMNS
        },
    )
    session.execute(statement)
    session.commit()

    return len(records)
