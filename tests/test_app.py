import pytest

from app import chaos, release
from app.main import app


@pytest.fixture()
def client():
    chaos.reset()
    yield app.test_client()
    chaos.reset()


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.get_json()["service"] == "demo-deploy-app"


def test_health_and_ready(client):
    assert client.get("/healthz").get_json() == {"status": "ok"}
    assert client.get("/readyz").get_json() == {"status": "ready"}


def test_version(client):
    body = client.get("/version").get_json()
    assert {"version", "git_sha", "uptime_seconds"} <= body.keys()


def test_items_create_and_list(client):
    r = client.post("/api/items", json={"name": "demo"})
    assert r.status_code == 201
    names = [i["name"] for i in client.get("/api/items").get_json()["items"]]
    assert "demo" in names


def test_items_validation(client):
    assert client.post("/api/items", json={}).status_code == 400


def test_stats_has_required_metrics(client):
    client.get("/")
    body = client.get("/api/stats").get_json()
    assert {"cpu", "memory", "error_rate", "latency"} <= body.keys()


def test_prometheus_metrics(client):
    client.get("/")
    text = client.get("/metrics").get_data(as_text=True)
    assert "http_requests_total" in text
    assert "http_request_duration_seconds" in text


def test_injected_errors_show_in_error_rate(client):
    client.post("/chaos", json={"error_rate": 1.0})
    for _ in range(5):
        assert client.get("/").status_code == 500
    assert client.get("/healthz").status_code == 200  # infra paths stay up
    assert client.get("/api/stats").get_json()["error_rate"] > 0


def test_chaos_reset(client):
    client.post("/chaos", json={"error_rate": 1.0})
    client.post("/chaos/reset")
    assert client.get("/").status_code == 200


def test_release_is_healthy():
    """Fails when FAULTY_RELEASE is flipped on - simulates a bad commit."""
    assert release.FAULTY_RELEASE is False
