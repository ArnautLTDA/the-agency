"""Tests for Security Gateway FastAPI endpoints and AgencyKeyMiddleware."""

from fastapi.testclient import TestClient
import pytest

from config import settings
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint_is_public(client: TestClient):
    """Health endpoints are exempt from X-Agency-Key requirement."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "security-audit-gateway"
    assert data["port"] == 3015


def test_protected_route_without_key_is_rejected(client: TestClient):
    """Non-exempt routes reject requests missing X-Agency-Key header."""
    response = client.get("/sse")
    assert response.status_code == 401
    assert response.json()["error"] == "missing_or_invalid_agency_key"


def test_protected_route_with_invalid_key_is_rejected(client: TestClient):
    """Non-exempt routes reject requests with invalid X-Agency-Key."""
    response = client.get("/sse", headers={"X-Agency-Key": "invalid-wrong-key"})
    assert response.status_code == 401
    assert response.json()["error"] == "missing_or_invalid_agency_key"
