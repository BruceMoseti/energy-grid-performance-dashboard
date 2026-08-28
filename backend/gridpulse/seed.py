"""Generate synthetic grid data for local development.

The EIA API needs a personal key and outbound network access, so this module
produces a plausible diurnal load curve instead. It writes through the same
loader the real pipeline uses, so what you see locally exercises the production
path. Data is synthetic: do not read anything into the numbers.

    python -m gridpulse.seed --days 3
"""

import argparse
import logging
import math
import random
from datetime import UTC, datetime, timedelta

import pandas as pd

from gridpulse.db import get_sessionmaker, init_db
from gridpulse.pipeline.load import upsert_grid_load
from gridpulse.pipeline.transform import GRID_LOAD_COLUMNS

logger = logging.getLogger("gridpulse.seed")

# region -> (mean demand MW, peak-to-trough swing MW, approximate UTC offset)
REGION_PROFILES: dict[str, tuple[int, int, int]] = {
    "PJM": (115_000, 50_000, -4),
    "MISO": (80_000, 32_000, -5),
    "ERCO": (60_000, 28_000, -5),
    "CISO": (30_000, 12_000, -7),
    "NYIS": (20_000, 8_000, -4),
    "ISNE": (14_000, 6_000, -4),
}


def _demand_shape(local_hour: float) -> float:
    """Return -1 at the 05:00 trough and +1 at the 17:00 peak."""
    return -math.cos(2 * math.pi * (local_hour - 5) / 24)


def build_frame(days: int, seed: int = 7) -> pd.DataFrame:
    rng = random.Random(seed)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    hours = [end - timedelta(hours=offset) for offset in range(days * 24, -1, -1)]

    rows = []
    for region_code, (mean_mw, swing_mw, utc_offset) in REGION_PROFILES.items():
        for timestamp in hours:
            local_hour = (timestamp.hour + utc_offset) % 24
            weekday_factor = 0.92 if timestamp.weekday() >= 5 else 1.0

            demand = (
                mean_mw + swing_mw / 2 * _demand_shape(local_hour)
            ) * weekday_factor * rng.gauss(1, 0.01)
            # EIA reports interchange as positive when a region is a net exporter.
            interchange = demand * rng.gauss(0, 0.02)

            rows.append(
                {
                    "timestamp": timestamp,
                    "region_code": region_code,
                    "actual_demand_mw": round(demand, 1),
                    "forecast_demand_mw": round(demand * rng.gauss(1, 0.015), 1),
                    "net_generation_mw": round(demand + interchange, 1),
                    "interchange_mw": round(interchange, 1),
                }
            )

    return pd.DataFrame(rows)[GRID_LOAD_COLUMNS]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days", type=int, default=3, help="Days of history to generate (default: 3)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    with get_sessionmaker()() as session:
        written = upsert_grid_load(session, build_frame(args.days))
    logger.info("Seeded %d synthetic grid_load rows", written)


if __name__ == "__main__":
    main()
