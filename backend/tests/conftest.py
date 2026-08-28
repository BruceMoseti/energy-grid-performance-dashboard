import json
import os
from pathlib import Path

# Point every test at the throwaway database before gridpulse reads its settings.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://gridpulse:gridpulse@localhost:5432/gridpulse_test",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from gridpulse.api.main import app  # noqa: E402
from gridpulse.db import get_engine, get_sessionmaker, init_db  # noqa: E402
from gridpulse.models import Base  # noqa: E402
from gridpulse.pipeline.load import upsert_grid_load  # noqa: E402
from gridpulse.seed import build_frame  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"

# Only these are given grid_load rows, so a tracked-but-empty region stays
# available for the "no data yet" case.
SEEDED_REGIONS = ["PJM", "CISO"]


@pytest.fixture(scope="session")
def eia_payload() -> dict:
    return json.loads((FIXTURES / "eia_region_data.json").read_text())


@pytest.fixture(scope="session")
def engine():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    init_db()
    return engine


@pytest.fixture
def session(engine):
    with get_sessionmaker()() as session:
        yield session


@pytest.fixture(scope="session")
def seed_frame(engine):
    frame = build_frame(days=2)
    frame = frame[frame["region_code"].isin(SEEDED_REGIONS)].reset_index(drop=True)
    with get_sessionmaker()() as session:
        upsert_grid_load(session, frame)
    return frame


@pytest.fixture(scope="session")
def client(seed_frame):
    with TestClient(app) as client:
        yield client
