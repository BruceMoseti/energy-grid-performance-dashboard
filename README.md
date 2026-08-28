# GridPulse — Real-Time Energy Grid Performance Dashboard

Ingests hourly electricity demand, day-ahead forecast, net generation and interchange
data for U.S. balancing authorities from the [EIA open data API][eia], stores it as a
time series in PostgreSQL, serves grid performance KPIs over a FastAPI REST API, and
charts actual demand against the day-ahead forecast in a Next.js dashboard.

![Phase 1](https://img.shields.io/badge/phase%201-complete-brightgreen) ![Tests](https://img.shields.io/badge/tests-25%20passing-brightgreen)

## Architecture

```
        EIA API  (hourly, per balancing authority)
           │
           ▼
   Python ingestion pipeline
   fetch → validate → transform → load
   requests / Pydantic / pandas / SQLAlchemy
           │
           ▼
       PostgreSQL
   regions · grid_load
           │
           ▼
       FastAPI
   /api/grid/current · /history · /regions
           │
           ▼
   Next.js dashboard
   demand vs forecast · grid KPIs
```

## What's built

| Layer | Status |
| --- | --- |
| EIA v2 ingestion pipeline with pagination and validation | Done |
| PostgreSQL time-series schema with idempotent upserts | Done |
| Grid KPIs in SQL (peak, forecast error, ramp rate, load factor) | Done |
| FastAPI REST API | Done |
| Next.js + TypeScript dashboard with Plotly chart | Done |
| Redis caching, Prometheus, Grafana, k6 load tests | Planned |
| Generation mix and renewable share | Planned |
| Docker Compose, GitHub Actions, cloud deployment | Planned |

## Grid KPIs

All computed in SQL from the `grid_load` table:

| KPI | Definition |
| --- | --- |
| Grid load | Demand in the most recent hour reported |
| Peak load | Highest demand in the selected window |
| Forecast error | `abs(actual − day-ahead forecast) / actual`, as a percentage |
| 1-hour ramp | Change in demand versus the previous hour |
| Load factor | Average demand ÷ peak demand in the window |
| Net generation | Generation reported for the latest hour |
| Net interchange | Positive when the region is a net exporter |

## Data model

```
regions                      grid_load
────────                     ─────────
region_id   PK               region_id           PK, FK → regions
region_code UNIQUE           timestamp           PK  (UTC, hourly)
region_name                  actual_demand_mw        EIA series D
                             forecast_demand_mw      EIA series DF
                             net_generation_mw       EIA series NG
                             interchange_mw          EIA series TI
```

The `grid_load` primary key is ordered `(region_id, timestamp)` rather than the reverse,
so the primary key index alone satisfies the "latest N hours for one region" access
pattern that every endpoint uses. Value columns are nullable because EIA publishes the
four series on different lags.

Tracked balancing authorities, by EIA respondent code: `PJM`, `MISO`, `ERCO` (ERCOT),
`CISO` (California ISO), `NYIS` (New York ISO), `ISNE` (ISO New England).

## Running it locally

### 1. PostgreSQL

```bash
createuser gridpulse --pwprompt      # password: gridpulse
createdb gridpulse --owner gridpulse
createdb gridpulse_test --owner gridpulse   # only needed to run the tests
```

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Load some data. Either ingest real EIA data, which needs a [free API key][key] in
`EIA_API_KEY`:

```bash
python -m gridpulse.pipeline.run --hours 48
```

…or generate a synthetic diurnal load curve, which needs no key or network:

```bash
python -m gridpulse.seed --days 3
```

Then start the API:

```bash
uvicorn gridpulse.api.main:app --reload
```

```bash
curl "http://localhost:8000/api/grid/current?region=PJM"
```

```json
{
  "region": "PJM",
  "region_name": "PJM Interconnection",
  "timestamp": "2026-08-28T01:00:00Z",
  "window_hours": 24,
  "demand_mw": 128009.5,
  "forecast_mw": 130886.0,
  "generation_mw": 129059.1,
  "interchange_mw": 1049.6,
  "forecast_error_pct": 2.25,
  "ramp_mw": -6534.5,
  "peak_demand_mw": 141359.8,
  "load_factor_pct": 81.64
}
```

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open <http://localhost:3000>.

## API

| Endpoint | Description |
| --- | --- |
| `GET /api/grid/current?region=PJM&hours=24` | Latest reading plus window KPIs |
| `GET /api/grid/history?region=PJM&hours=24` | Hourly actual-vs-forecast series |
| `GET /api/grid/regions` | Tracked balancing authorities |
| `GET /health` | Liveness plus a database round trip |

`region` accepts any tracked EIA respondent code and is case-insensitive. `hours`
accepts 1–720. Unknown regions return `404` with the list of tracked codes.

Interactive docs are at <http://localhost:8000/docs>.

## Pipeline design notes

- **Validation is non-fatal.** A malformed EIA record is dropped and counted rather
  than failing the run, so one bad hour cannot block ingesting the rest of a window.
- **Restatements collapse.** EIA occasionally republishes an hour. The pandas pivot
  uses `aggfunc="last"` and, because groupby skips nulls, prefers a real reading over
  a null one.
- **Upserts never lose data.** The `ON CONFLICT` update coalesces incoming values
  against stored ones, so re-ingesting a window before EIA has published net
  generation cannot null out a value already recorded.
- **Re-running is safe.** Ingestion is idempotent on `(region_id, timestamp)`, so the
  pipeline can run on a cron schedule over overlapping windows.

## Tests

```bash
cd backend
pytest
```

25 tests, run against a real PostgreSQL instance:

- Pipeline tests use a recorded EIA payload (`backend/tests/fixtures/eia_region_data.json`)
  and an injected fake HTTP session, so no network is required. They cover the query
  sent to EIA, pagination, rejection of malformed records, the pivot, restatement
  collapsing and null handling.
- Loader tests cover upsert idempotency, the coalesce behaviour, pandas `NaN` becoming
  SQL `NULL` rather than float `NaN`, and untracked regions being skipped.
- API tests run against a seeded database and include a tracked-but-empty region
  returning a `404` that explains how to load data.

Frontend checks:

```bash
cd frontend
npm run typecheck
npm run build
```

## Tech stack

Python · pandas · Pydantic · SQLAlchemy · PostgreSQL · FastAPI · TypeScript · React ·
Next.js · Plotly

## Roadmap

1. **Generation mix** — add the fuel-type endpoint, a `generation_mix` table, renewable
   share KPI, a stacked generation chart and the generation-source filter.
2. **Performance monitoring** — instrument FastAPI with Prometheus, then build Grafana
   dashboards for API latency percentiles, database query time and data freshness.
3. **Optimization** — load test with k6, then add Redis caching and query tuning, and
   record the before/after latency difference.
4. **DevOps** — Docker Compose for the whole stack, GitHub Actions for tests and image
   builds, and a deployment with a public URL.
5. **Dashboard polish** — regional map with demand-based status colours, region
   comparison, and a grid events feed.

[eia]: https://www.eia.gov/opendata/
[key]: https://www.eia.gov/opendata/register.php
