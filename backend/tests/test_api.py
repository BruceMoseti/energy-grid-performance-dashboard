"""API tests against a seeded PostgreSQL database."""

from datetime import UTC, datetime, timedelta


def test_health_reports_database_connectivity(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_regions_lists_tracked_balancing_authorities(client):
    payload = client.get("/api/grid/regions").json()

    assert {"region_code": "PJM", "region_name": "PJM Interconnection"} in payload
    assert len(payload) == 6


def test_current_returns_latest_reading_and_window_kpis(client):
    payload = client.get("/api/grid/current", params={"region": "PJM"}).json()

    assert payload["region"] == "PJM"
    assert payload["region_name"] == "PJM Interconnection"
    assert payload["window_hours"] == 24
    assert payload["demand_mw"] > 0
    assert payload["forecast_mw"] > 0
    assert payload["generation_mw"] > 0

    # The latest hour cannot exceed the peak of the window that contains it.
    assert payload["peak_demand_mw"] >= payload["demand_mw"]
    assert 0 < payload["load_factor_pct"] <= 100
    assert payload["forecast_error_pct"] >= 0
    assert payload["ramp_mw"] is not None


def test_current_accepts_a_lowercase_region_code(client):
    assert client.get("/api/grid/current", params={"region": "pjm"}).status_code == 200


def test_current_honours_the_window_size(client):
    day = client.get("/api/grid/current", params={"region": "PJM", "hours": 24}).json()
    two_days = client.get("/api/grid/current", params={"region": "PJM", "hours": 48}).json()

    assert two_days["window_hours"] == 48
    assert two_days["peak_demand_mw"] >= day["peak_demand_mw"]


def test_unknown_region_is_a_404(client):
    response = client.get("/api/grid/current", params={"region": "NOPE"})

    assert response.status_code == 404
    assert "Tracked regions" in response.json()["detail"]


def test_tracked_region_without_data_explains_how_to_load_it(client):
    response = client.get("/api/grid/current", params={"region": "ISNE"})

    assert response.status_code == 404
    assert "gridpulse.seed" in response.json()["detail"]


def test_history_returns_an_ascending_series_inside_the_window(client):
    payload = client.get(
        "/api/grid/history", params={"region": "PJM", "hours": 24}
    ).json()
    points = payload["points"]

    assert payload["window_hours"] == 24
    assert len(points) >= 24

    timestamps = [datetime.fromisoformat(point["timestamp"]) for point in points]
    assert timestamps == sorted(timestamps)
    assert timestamps[0] >= datetime.now(UTC) - timedelta(hours=25)
    assert all(point["demand_mw"] > 0 for point in points)


def test_history_rejects_an_out_of_range_window(client):
    assert client.get("/api/grid/history", params={"hours": 0}).status_code == 422
    assert client.get("/api/grid/history", params={"hours": 5000}).status_code == 422
