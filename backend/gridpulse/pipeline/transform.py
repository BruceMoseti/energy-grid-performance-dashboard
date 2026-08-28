"""Reshape validated EIA observations into grid_load rows."""

import pandas as pd

from gridpulse.config import EIA_TYPE_TO_COLUMN
from gridpulse.pipeline.validate import EIAObservation

GRID_LOAD_COLUMNS = ["timestamp", "region_code", *EIA_TYPE_TO_COLUMN.values()]


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=GRID_LOAD_COLUMNS)


def to_grid_load_frame(observations: list[EIAObservation]) -> pd.DataFrame:
    """Pivot one-row-per-series EIA data into one-row-per-hour-per-region.

    EIA reports demand, forecast, net generation and interchange as separate
    records sharing a (period, respondent) key, so the wide shape our table
    wants is a pivot away.
    """
    if not observations:
        return _empty_frame()

    long_frame = pd.DataFrame(
        [
            {
                "timestamp": observation.timestamp,
                "region_code": observation.region_code,
                "column": EIA_TYPE_TO_COLUMN.get(observation.series_type),
                "value": observation.value,
            }
            for observation in observations
        ]
    )

    # Series types we do not model (EIA publishes several) fall out here.
    long_frame = long_frame.dropna(subset=["column"])
    if long_frame.empty:
        return _empty_frame()

    # "last" both collapses EIA's occasional restatements of an hour and, since
    # groupby skips nulls, prefers a real reading over a null one.
    wide = long_frame.pivot_table(
        index=["timestamp", "region_code"],
        columns="column",
        values="value",
        aggfunc="last",
    )
    if wide.empty:
        return _empty_frame()

    for column in EIA_TYPE_TO_COLUMN.values():
        if column not in wide.columns:
            wide[column] = float("nan")

    return (
        wide.reset_index()[GRID_LOAD_COLUMNS]
        .sort_values(["timestamp", "region_code"])
        .reset_index(drop=True)
    )
