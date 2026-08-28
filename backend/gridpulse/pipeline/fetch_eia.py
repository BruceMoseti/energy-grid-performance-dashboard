"""Client for the EIA v2 hourly electric grid monitor (region-data) endpoint.

Docs: https://www.eia.gov/opendata/documentation.php

The endpoint returns one record per (period, respondent, type), so a single
request covers demand, forecast, net generation and interchange for every
region we track.
"""

from datetime import datetime

import requests

from gridpulse.config import EIA_TYPE_TO_COLUMN

# EIA expects hourly periods as YYYY-MM-DDTHH in UTC.
EIA_PERIOD_FORMAT = "%Y-%m-%dT%H"

# The API caps a single page at 5000 records.
MAX_PAGE_SIZE = 5000


class EIAError(RuntimeError):
    pass


def format_period(moment: datetime) -> str:
    return moment.strftime(EIA_PERIOD_FORMAT)


def _page_params(
    *,
    api_key: str,
    regions: list[str],
    series_types: tuple[str, ...],
    start: datetime,
    end: datetime,
    offset: int,
    length: int,
) -> list[tuple[str, str]]:
    """Build EIA's query string, which repeats keys for multi-valued facets."""
    params = [
        ("api_key", api_key),
        ("frequency", "hourly"),
        ("data[0]", "value"),
        ("start", format_period(start)),
        ("end", format_period(end)),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "asc"),
        ("offset", str(offset)),
        ("length", str(length)),
    ]
    params += [("facets[respondent][]", region) for region in regions]
    params += [("facets[type][]", series_type) for series_type in series_types]
    return params


def fetch_region_data(
    *,
    api_key: str,
    regions: list[str],
    start: datetime,
    end: datetime,
    base_url: str,
    series_types: tuple[str, ...] = tuple(EIA_TYPE_TO_COLUMN),
    session: requests.Session | None = None,
    page_size: int = MAX_PAGE_SIZE,
) -> list[dict]:
    """Return every raw EIA record in the window, following pagination."""
    if not api_key:
        raise EIAError(
            "No EIA API key configured. Request a free key at "
            "https://www.eia.gov/opendata/register.php and set EIA_API_KEY."
        )

    http = session or requests.Session()
    records: list[dict] = []
    offset = 0

    while True:
        response = http.get(
            base_url,
            params=_page_params(
                api_key=api_key,
                regions=regions,
                series_types=series_types,
                start=start,
                end=end,
                offset=offset,
                length=page_size,
            ),
            timeout=30,
        )
        response.raise_for_status()
        body = response.json().get("response", {})
        page = body.get("data", [])
        records.extend(page)

        if not page:
            break
        offset += len(page)
        if offset >= int(body.get("total", offset)):
            break

    return records
