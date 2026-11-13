"""Tests for Vercel Client (TC-136, TC-195)."""

import pytest
import respx

from vercel_client import VercelClient


@pytest.mark.asyncio
async def test_create_preview_deployment_tc136():
    """TC-136: Creates sales demo preview deployment on Vercel."""
    with respx.mock(base_url="https://api.vercel.com") as mock:
        mock.post("/v13/deployments").respond(
            200,
            json={
                "id": "dep_prev_999",
                "url": "barbearia-vintage-demo.vercel.app",
                "readyState": "READY",
            },
        )

        client = VercelClient(token="mock_token")
        result = await client.create_deployment(project_name="barbearia-vintage-demo", target="preview")

        assert result.id == "dep_prev_999"
        assert "barbearia-vintage-demo.vercel.app" in result.url
        assert result.target == "preview"
        assert result.ready_state == "READY"


@pytest.mark.asyncio
async def test_get_deployment_status():
    """Queries deployment status by ID."""
    with respx.mock(base_url="https://api.vercel.com") as mock:
        mock.get("/v13/deployments/dep_123").respond(
            200,
            json={"id": "dep_123", "url": "app.vercel.app", "readyState": "READY", "target": "production"},
        )

        client = VercelClient(token="mock_token")
        dep = await client.get_deployment("dep_123")
        assert dep.id == "dep_123"
        assert dep.ready_state == "READY"


@pytest.mark.asyncio
async def test_set_project_env_vars():
    """Sets encrypted environment variables in Vercel project."""
    with respx.mock(base_url="https://api.vercel.com") as mock:
        mock.post("/v10/projects/barbearia/env").respond(200, json={})

        client = VercelClient(token="mock_token")
        res = await client.set_project_env_vars(
            project_name="barbearia",
            env_vars={"DATABASE_URL": "postgres://user:pass@host/db", "NEXT_PUBLIC_APP": "true"},
            target="preview",
        )

        assert res["created_count"] == 2
        assert "DATABASE_URL" in res["keys"]


@pytest.mark.asyncio
async def test_vercel_api_error_handling_tc195():
    """TC-195: Handles Vercel API errors (e.g. 403 Forbidden or 500)."""
    with respx.mock(base_url="https://api.vercel.com") as mock:
        mock.post("/v13/deployments").respond(403)

        client = VercelClient(token="bad_token")
        with pytest.raises(Exception):
            await client.create_deployment(project_name="error-proj")
