"""Tests for Supervisor REST API Endpoints (/status, /pausar, /retomar)."""

from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
import pytest
import respx

from src.config import get_settings
from src.main import app
from src.services.queue import get_queue_service
from src.services.supervisor import EngineOperationalState, SupervisorService, set_supervisor


@pytest.fixture
def client():
    return TestClient(app)


def test_get_status_endpoint(client: TestClient):
    """GET /api/v1/status returns operational state and gateway telemetry."""
    supervisor = SupervisorService()
    set_supervisor(supervisor)

    resp = client.get("/api/v1/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["engine_state"] == "OPERACIONAL"
    assert data["is_paused"] is False

    set_supervisor(None)


def test_post_pausar_and_retomar_endpoints(client: TestClient):
    """POST /api/v1/agent/pause and /retomar commands."""
    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get("http://127.0.0.1:3005/api/v1/session/status").respond(200, json={"status": "ready"})
        respx_mock.get("http://127.0.0.1:3006/api/v1/health").respond(200, json={"status": "healthy"})
        respx_mock.get("http://127.0.0.1:3007/api/v1/health").respond(200, json={"status": "healthy"})

        supervisor = SupervisorService()
        set_supervisor(supervisor)

        # 1. Pause
        pause_resp = client.post("/api/v1/agent/pause")
        assert pause_resp.status_code == 200
        assert pause_resp.json()["state"] == "PAUSA_EMERGENCIAL"
        assert supervisor.is_paused()

        # 2. Resume
        resume_resp = client.post("/api/v1/agent/resume")
        assert resume_resp.status_code == 200
        assert resume_resp.json()["state"] == "OPERACIONAL"
        assert not supervisor.is_paused()

        set_supervisor(None)


def test_retomar_rejected_if_vital_unhealthy(client: TestClient):
    """POST /api/v1/retomar returns 503 if vital gateway is down."""
    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get("http://127.0.0.1:3005/api/v1/session/status").respond(503, json={"status": "down"})
        respx_mock.get("http://127.0.0.1:3006/api/v1/health").respond(200, json={"status": "healthy"})
        respx_mock.get("http://127.0.0.1:3007/api/v1/health").respond(200, json={"status": "healthy"})

        supervisor = SupervisorService()
        supervisor._state = EngineOperationalState.PAUSA_EMERGENCIAL
        supervisor._manually_paused = True
        set_supervisor(supervisor)

        resume_resp = client.post("/api/v1/retomar")
        assert resume_resp.status_code == 503
        assert "vital gateways are unhealthy" in resume_resp.json()["detail"]

        set_supervisor(None)


def test_agent_run_prospecting_blocked_during_pause(client: TestClient):
    """POST /api/v1/agent/run with prospecting task returns 503 during PAUSA_EMERGENCIAL."""
    supervisor = SupervisorService()
    supervisor._state = EngineOperationalState.PAUSA_EMERGENCIAL
    set_supervisor(supervisor)

    settings = get_settings()
    headers = {"X-Engine-Key": settings.ENGINE_API_KEY}

    resp = client.post(
        "/api/v1/agent/run",
        headers=headers,
        json={
            "agent_id": "homologation_agent",
            "task": "prospect and qualify new clients in Campinas",
            "workspace_slug": "test_client",
        },
    )

    assert resp.status_code == 503
    assert "PAUSA_EMERGENCIAL" in resp.json()["detail"]

    set_supervisor(None)
