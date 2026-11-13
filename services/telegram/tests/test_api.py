"""Unit tests for Telegram Gateway FastAPI endpoints and webhook routing (TC-177)."""

from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import pytest

from main import app


def test_telegram_health_endpoint():
    """Verifies GET /api/v1/telegram/health responds without requiring X-Agency-Key."""
    client = TestClient(app)
    res = client.get("/api/v1/telegram/health")
    assert res.status_code == 200
    data = res.json()
    assert data["service"] == "telegram-gateway"
    assert data["status"] == "healthy"


def test_telegram_webhook_endpoint():
    """Verifies POST /api/v1/telegram/webhook receives and routes update without X-Agency-Key."""
    client = TestClient(app)
    with patch("main.bot_service.handle_update", new_callable=AsyncMock) as mock_handle:
        mock_handle.return_value = {"status": "ok"}
        res = client.post("/api/v1/telegram/webhook", json={"update_id": 12345})
        assert res.status_code == 200
        mock_handle.assert_called_once()
