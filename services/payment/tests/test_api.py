"""Tests for Payment Gateway FastAPI endpoints."""

from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import pytest

from config import settings
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoints_public(client: TestClient):
    """Health endpoints are exempt from X-Agency-Key."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert resp.json()["service"] == "payment-gateway"
    assert resp.json()["port"] == 3006


def test_protected_route_without_key_is_rejected(client: TestClient):
    """Non-exempt routes reject requests missing X-Agency-Key."""
    resp = client.get("/sse")
    assert resp.status_code == 401
    assert resp.json()["error"] == "missing_or_invalid_agency_key"


def test_inter_webhook_endpoint_success(client: TestClient):
    """Webhook accepts Banco Inter payload with valid x-webhook-key."""
    payload = {
        "pix": [
            {
                "txid": "AGY_WEBHOOK_TEST_1",
                "valor": "100.00",
                "horario": "2026-11-13T15:00:00Z",
            }
        ]
    }

    with patch("main.webhook_handler.handle_pix_payment_event", new_callable=AsyncMock) as mock_handle:
        mock_handle.return_value = {"status": "processed", "txid": "AGY_WEBHOOK_TEST_1"}

        resp = client.post(
            "/api/v1/inter/webhook",
            json=payload,
            headers={"x-webhook-key": settings.INTER_WEBHOOK_KEY},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["processed_count"] == 1
        mock_handle.assert_called_once()
