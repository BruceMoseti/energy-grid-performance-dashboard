"""Tests for fetch -> validate -> transform, using a recorded EIA payload."""

from datetime import UTC, datetime

import pandas as pd
import pytest

from gridpulse.pipeline.fetch_eia import EIAError, fetch_region_data
from gridpulse.pipeline.transform import GRID_LOAD_COLUMNS, to_grid_load_frame
from gridpulse.pipeline.validate import validate_records

START = datetime(2026, 8, 27, 12, tzinfo=UTC)
END = datetime(2026, 8, 27, 16, tzinfo=UTC)


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Stands in for requests.Session so no network is touched."""

    def __init__(self, pages: list[dict]):
        self.pages = list(pages)
        self.calls: list[list[tuple[str, str]]] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        return FakeResponse(self.pages.pop(0))


def _page(records: list[dict], total: int) -> dict:
    return {"response": {"total": str(total), "data": records}}


def test_fetch_sends_documented_query(eia_payload):
    session = FakeSession([eia_payload])

    fetch_region_data(
        api_key="key123",
        regions=["PJM", "CISO"],
        start=START,
        end=END,
        base_url="https://api.eia.gov/v2/electricity/rto/region-data/data/",
        session=session,
    )

    params = dict(session.calls[0])
    assert params["api_key"] == "key123"
    assert params["frequency"] == "hourly"
    assert params["start"] == "2026-08-27T12"
    assert params["end"] == "2026-08-27T16"

    # Facets repeat their key, so check the raw pairs rather than the dict.
    pairs = session.calls[0]
    assert ("facets[respondent][]", "PJM") in pairs
    assert ("facets[respondent][]", "CISO") in pairs
    for series_type in ("D", "DF", "NG", "TI"):
        assert ("facets[type][]", series_type) in pairs


def test_fetch_follows_pagination():
    first = [{"period": "2026-08-27T14", "respondent": "PJM", "type": "D", "value": "1"}]
    second = [{"period": "2026-08-27T15", "respondent": "PJM", "type": "D", "value": "2"}]
    session = FakeSession([_page(first, 2), _page(second, 2)])

    records = fetch_region_data(
        api_key="key123",
        regions=["PJM"],
        start=START,
        end=END,
        base_url="https://example.test/",
        session=session,
        page_size=1,
    )

    assert len(records) == 2
    assert dict(session.calls[1])["offset"] == "1"


def test_fetch_without_api_key_is_rejected():
    with pytest.raises(EIAError, match="No EIA API key"):
        fetch_region_data(
            api_key="",
            regions=["PJM"],
            start=START,
            end=END,
            base_url="https://example.test/",
        )


def test_validate_parses_eia_records(eia_payload):
    observations, rejected = validate_records(eia_payload["response"]["data"])

    assert rejected == []
    assert len(observations) == 10

    first = observations[0]
    assert first.timestamp == datetime(2026, 8, 27, 14, tzinfo=UTC)
    assert first.region_code == "PJM"
    assert first.series_type == "D"
    assert first.value == 142821.0


def test_validate_drops_malformed_records_without_failing_the_run():
    observations, rejected = validate_records(
        [
            {"period": "2026-08-27T14", "respondent": "PJM", "type": "D", "value": "1"},
            {"period": "not-a-date", "respondent": "PJM", "type": "D", "value": "2"},
            {"respondent": "PJM", "type": "D", "value": "3"},
        ]
    )

    assert len(observations) == 1
    assert len(rejected) == 2


def test_transform_pivots_series_into_one_row_per_hour(eia_payload):
    observations, _ = validate_records(eia_payload["response"]["data"])
    frame = to_grid_load_frame(observations)

    assert list(frame.columns) == GRID_LOAD_COLUMNS
    assert len(frame) == 3

    pjm = frame[
        (frame["region_code"] == "PJM")
        & (frame["timestamp"] == datetime(2026, 8, 27, 14, tzinfo=UTC))
    ].iloc[0]
    assert pjm["actual_demand_mw"] == 142821.0
    assert pjm["forecast_demand_mw"] == 143500.0
    assert pjm["net_generation_mw"] == 140331.0
    assert pjm["interchange_mw"] == -2490.0

    # CISO reported demand but a null forecast and no generation/interchange.
    ciso = frame[frame["region_code"] == "CISO"].iloc[0]
    assert ciso["actual_demand_mw"] == 38210.0
    assert pd.isna(ciso["forecast_demand_mw"])
    assert pd.isna(ciso["net_generation_mw"])


def test_transform_collapses_restated_hours():
    observations, _ = validate_records(
        [
            {"period": "2026-08-27T14", "respondent": "PJM", "type": "D", "value": "100"},
            {"period": "2026-08-27T14", "respondent": "PJM", "type": "D", "value": "110"},
        ]
    )
    frame = to_grid_load_frame(observations)

    assert len(frame) == 1
    assert frame.iloc[0]["actual_demand_mw"] == 110.0


def test_transform_ignores_unmodelled_series_types():
    observations, _ = validate_records(
        [{"period": "2026-08-27T14", "respondent": "PJM", "type": "SUN", "value": "5"}]
    )

    assert to_grid_load_frame(observations).empty


def test_transform_of_nothing_is_an_empty_frame():
    frame = to_grid_load_frame([])

    assert frame.empty
    assert list(frame.columns) == GRID_LOAD_COLUMNS
