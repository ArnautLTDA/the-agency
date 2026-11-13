"""Tests for Supabase Provisioning Client (TC-196)."""

import pytest
import respx

from supabase_client import SupabaseClient


@pytest.mark.asyncio
async def test_provision_database_success_tc196():
    """TC-196: Provisions a new PostgreSQL instance on Supabase."""
    with respx.mock(base_url="https://api.supabase.com") as mock:
        mock.post("/v1/projects").respond(
            201,
            json={
                "id": "prj_sb_vintage_001",
                "name": "vintage-db",
                "region": "sa-east-1",
                "status": "ACTIVE_HEALTHY",
            },
        )

        client = SupabaseClient(token="mock_sb_token")
        result = await client.provision_database(project_name="vintage-db", region="sa-east-1")

        assert result.project_id == "prj_sb_vintage_001"
        assert result.project_name == "vintage-db"
        assert result.region == "sa-east-1"
        assert "supabase.co" in result.db_host
        assert result.status == "ACTIVE_HEALTHY"
