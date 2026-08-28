"""CLI entry point: fetch a window of EIA data and load it into PostgreSQL.

    python -m gridpulse.pipeline.run --hours 48
"""

import argparse
import logging
from datetime import UTC, datetime, timedelta

from gridpulse.config import REGIONS, get_settings
from gridpulse.db import get_sessionmaker, init_db
from gridpulse.pipeline.fetch_eia import fetch_region_data
from gridpulse.pipeline.load import upsert_grid_load
from gridpulse.pipeline.transform import to_grid_load_frame
from gridpulse.pipeline.validate import validate_records

logger = logging.getLogger("gridpulse.pipeline")


def ingest(hours: int) -> int:
    """Run one fetch -> validate -> transform -> load cycle."""
    settings = get_settings()
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=hours)

    logger.info("Fetching EIA data for %s from %s to %s", list(REGIONS), start, end)
    records = fetch_region_data(
        api_key=settings.eia_api_key,
        regions=list(REGIONS),
        start=start,
        end=end,
        base_url=settings.eia_base_url,
    )
    logger.info("Fetched %d records", len(records))

    observations, rejected = validate_records(records)
    if rejected:
        logger.warning("Rejected %d malformed records, first: %s", len(rejected), rejected[0])

    frame = to_grid_load_frame(observations)
    with get_sessionmaker()() as session:
        written = upsert_grid_load(session, frame)

    logger.info("Wrote %d grid_load rows", written)
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hours", type=int, default=48, help="Size of the lookback window (default: 48)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    ingest(args.hours)


if __name__ == "__main__":
    main()
