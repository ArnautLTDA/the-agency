"""Supabase Cloud Provisioning Client (TC-196)."""

from typing import Any
import httpx
from loguru import logger
from pydantic import BaseModel

from config import settings


class DatabaseProvisionResult(BaseModel):
    """Result of Supabase database provisioning."""

    project_id: str
    project_name: str
    region: str
    db_host: str
    status: str


class SupabaseClient:
    """Client for Supabase Management API to provision PostgreSQL databases."""

    def __init__(
        self,
        token: str = settings.SUPABASE_ACCESS_TOKEN,
        api_base: str = settings.SUPABASE_API_BASE,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token
        self.api_base = api_base.rstrip("/")
        self._client = client

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def provision_database(
        self,
        project_name: str,
        region: str = "sa-east-1",
    ) -> DatabaseProvisionResult:
        """Provisions a new PostgreSQL database instance in Supabase (TC-196)."""
        url = f"{self.api_base}/v1/projects"
        payload = {
            "name": project_name,
            "organization_id": "org_agency_default",
            "region": region,
            "plan": "free",
        }

        client = self._client or httpx.AsyncClient(timeout=20.0)
        should_close = self._client is None

        try:
            resp = await client.post(url, json=payload, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()

            project_id = data.get("id", f"sb_{project_name}")
            db_host = f"db.{project_id}.supabase.co"

            logger.info("Supabase database provisioned: {id} in {r}", id=project_id, r=region)
            return DatabaseProvisionResult(
                project_id=project_id,
                project_name=project_name,
                region=region,
                db_host=db_host,
                status=data.get("status", "ACTIVE_HEALTHY"),
            )
        except httpx.HTTPError as exc:
            logger.error("Supabase provisioning error: {err}", err=exc)
            raise
        finally:
            if should_close:
                await client.aclose()
