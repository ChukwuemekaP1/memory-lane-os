"""Health probes: liveness always, readiness against the test database."""

import pytest


async def test_liveness(bare_client):
    response = await bare_client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.needs_pg
async def test_readiness_reports_database_ok(client):
    response = await client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["components"]["database"] == "ok"
