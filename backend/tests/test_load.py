"""Database-backed tests for the loader's upsert semantics."""

from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import text

from gridpulse.config import REGIONS
from gridpulse.pipeline.load import ensure_regions, upsert_grid_load
from gridpulse.pipeline.transform import GRID_LOAD_COLUMNS

# Timestamps well outside any dashboard window, so these rows cannot disturb
# the API tests that query recent hours.
BASE_HOUR = datetime(2020, 1, 1, tzinfo=UTC)


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)[GRID_LOAD_COLUMNS]


def _row(session, timestamp: datetime) -> dict | None:
    result = session.execute(
        text(
            """
            SELECT gl.actual_demand_mw, gl.net_generation_mw
            FROM grid_load gl
            JOIN regions r ON r.region_id = gl.region_id
            WHERE r.region_code = 'PJM' AND gl.timestamp = :timestamp
            """
        ),
        {"timestamp": timestamp},
    ).mappings().first()
    return dict(result) if result else None


def test_ensure_regions_is_idempotent(session):
    first = ensure_regions(session)
    second = ensure_regions(session)

    assert set(first) == set(REGIONS)
    assert first == second


def test_upsert_writes_rows(session):
    timestamp = BASE_HOUR.replace(hour=1)
    written = upsert_grid_load(
        session,
        _frame(
            [
                {
                    "timestamp": timestamp,
                    "region_code": "PJM",
                    "actual_demand_mw": 100_000.0,
                    "forecast_demand_mw": 101_000.0,
                    "net_generation_mw": 99_000.0,
                    "interchange_mw": -1_000.0,
                }
            ]
        ),
    )

    assert written == 1
    assert _row(session, timestamp)["actual_demand_mw"] == 100_000.0


def test_reingesting_the_same_hour_updates_instead_of_duplicating(session):
    timestamp = BASE_HOUR.replace(hour=2)
    base = {
        "timestamp": timestamp,
        "region_code": "PJM",
        "actual_demand_mw": 100_000.0,
        "forecast_demand_mw": 101_000.0,
        "net_generation_mw": 99_000.0,
        "interchange_mw": -1_000.0,
    }

    upsert_grid_load(session, _frame([base]))
    upsert_grid_load(session, _frame([{**base, "actual_demand_mw": 105_000.0}]))

    count = session.execute(
        text("SELECT COUNT(*) FROM grid_load WHERE timestamp = :timestamp"),
        {"timestamp": timestamp},
    ).scalar()
    assert count == 1
    assert _row(session, timestamp)["actual_demand_mw"] == 105_000.0


def test_incoming_null_does_not_clobber_a_stored_value(session):
    timestamp = BASE_HOUR.replace(hour=3)
    base = {
        "timestamp": timestamp,
        "region_code": "PJM",
        "actual_demand_mw": 100_000.0,
        "forecast_demand_mw": 101_000.0,
        "net_generation_mw": 99_000.0,
        "interchange_mw": -1_000.0,
    }

    upsert_grid_load(session, _frame([base]))
    # A later fetch of the same hour before EIA publishes net generation.
    upsert_grid_load(session, _frame([{**base, "net_generation_mw": float("nan")}]))

    assert _row(session, timestamp)["net_generation_mw"] == 99_000.0


def test_missing_values_are_stored_as_sql_null(session):
    timestamp = BASE_HOUR.replace(hour=4)
    upsert_grid_load(
        session,
        _frame(
            [
                {
                    "timestamp": timestamp,
                    "region_code": "PJM",
                    "actual_demand_mw": 100_000.0,
                    "forecast_demand_mw": float("nan"),
                    "net_generation_mw": float("nan"),
                    "interchange_mw": float("nan"),
                }
            ]
        ),
    )

    is_null = session.execute(
        text(
            "SELECT net_generation_mw IS NULL FROM grid_load WHERE timestamp = :timestamp"
        ),
        {"timestamp": timestamp},
    ).scalar()
    assert is_null is True


def test_untracked_regions_are_skipped(session):
    written = upsert_grid_load(
        session,
        _frame(
            [
                {
                    "timestamp": BASE_HOUR.replace(hour=5),
                    "region_code": "NOTAREGION",
                    "actual_demand_mw": 1.0,
                    "forecast_demand_mw": 1.0,
                    "net_generation_mw": 1.0,
                    "interchange_mw": 1.0,
                }
            ]
        ),
    )

    assert written == 0


def test_empty_frame_writes_nothing(session):
    assert upsert_grid_load(session, pd.DataFrame(columns=GRID_LOAD_COLUMNS)) == 0
