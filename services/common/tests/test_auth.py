"""Unit tests for X-Agency-Key authentication middleware and exceptions (SEC-026 / TC-177)."""

import os
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from agency_common.auth import (
    AgencyKeyMiddleware,
    HEADER_AGENCY_KEY,
    get_agency_secret_key,
    verify_agency_key,
)


def create_test_app() -> FastAPI:
    """Creates a sample FastAPI app wrapped in AgencyKeyMiddleware."""
    app = FastAPI()
    app.add_middleware(AgencyKeyMiddleware)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/health")
    def api_health():
        return {"status": "healthy"}

    @app.post("/api/v1/inter/webhook")
    def inter_webhook():
        return {"received": True}

    @app.post("/api/v1/telegram/webhook")
    def telegram_webhook():
        return {"ok": True}

    @app.get("/api/v1/protected/resource")
    def protected_resource():
        return {"secret_data": "agency_alpha"}

    return app


def test_missing_agency_key_returns_401():
    """Verifies that requests without X-Agency-Key receive 401 Unauthorized (TC-177)."""
    app = create_test_app()
    client = TestClient(app)

    response = client.get("/api/v1/protected/resource")
    assert response.status_code == 401
    assert response.json() == {"error": "missing_or_invalid_agency_key"}


def test_invalid_agency_key_returns_401():
    """Verifies that requests with an incorrect X-Agency-Key receive 401."""
    app = create_test_app()
    client = TestClient(app)

    response = client.get(
        "/api/v1/protected/resource",
        headers={HEADER_AGENCY_KEY: "wrong-fake-token"},
    )
    assert response.status_code == 401
    assert response.json() == {"error": "missing_or_invalid_agency_key"}


def test_valid_agency_key_returns_200():
    """Verifies that requests with the valid X-Agency-Key succeed."""
    os.environ["AGENCY_SECRET_KEY"] = "super-secret-key-test"
    try:
        app = create_test_app()
        client = TestClient(app)

        response = client.get(
            "/api/v1/protected/resource",
            headers={HEADER_AGENCY_KEY: "super-secret-key-test"},
        )
        assert response.status_code == 200
        assert response.json() == {"secret_data": "agency_alpha"}
    finally:
        os.environ.pop("AGENCY_SECRET_KEY", None)


def test_exempt_endpoints_succeed_without_key():
    """Verifies healthchecks and external webhooks are exempt from X-Agency-Key."""
    app = create_test_app()
    client = TestClient(app)

    # Health endpoints
    r_health = client.get("/health")
    assert r_health.status_code == 200

    r_api_health = client.get("/api/v1/health")
    assert r_api_health.status_code == 200

    # External webhooks
    r_inter = client.post("/api/v1/inter/webhook")
    assert r_inter.status_code == 200

    r_tg = client.post("/api/v1/telegram/webhook")
    assert r_tg.status_code == 200


def test_verify_agency_key_dependency_function():
    """Verifies direct call to verify_agency_key helper function."""
    mock_request_valid = Request(
        scope={
            "type": "http",
            "path": "/api/v1/tools/call",
            "headers": [(HEADER_AGENCY_KEY.lower().encode("utf-8"), b"agency_dev_secret_key_12345")],
        }
    )
    assert verify_agency_key(mock_request_valid) is True

    mock_request_exempt = Request(
        scope={
            "type": "http",
            "path": "/health",
            "headers": [],
        }
    )
    assert verify_agency_key(mock_request_exempt) is True

    mock_request_invalid = Request(
        scope={
            "type": "http",
            "path": "/api/v1/tools/call",
            "headers": [],
        }
    )
    with pytest.raises(Exception) as exc_info:
        verify_agency_key(mock_request_invalid)
    assert exc_info.value.status_code == 401
