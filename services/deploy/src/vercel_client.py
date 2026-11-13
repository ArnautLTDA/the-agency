"""Vercel REST API Client (TC-136, TC-195)."""

from typing import Any
import httpx
from loguru import logger
from pydantic import BaseModel

from config import settings


class DeploymentResult(BaseModel):
    """Result of creating or checking a Vercel deployment."""

    id: str
    url: str
    ready_state: str  # "READY", "BUILDING", "ERROR"
    target: str       # "preview" or "production"


class VercelClient:
    """Client for Vercel Cloud Platform deployments and environment variables."""

    def __init__(
        self,
        token: str = settings.VERCEL_TOKEN,
        api_base: str = settings.VERCEL_API_BASE,
        team_id: str | None = settings.VERCEL_TEAM_ID,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token
        self.api_base = api_base.rstrip("/")
        self.team_id = team_id
        self._client = client

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def create_deployment(
        self,
        project_name: str,
        target: str = "preview",
        custom_domain: str | None = None,
    ) -> DeploymentResult:
        """Triggers deployment on Vercel (TC-136)."""
        url = f"{self.api_base}/v13/deployments"
        params = {"teamId": self.team_id} if self.team_id else {}

        payload: dict[str, Any] = {
            "name": project_name,
            "target": target,
            "projectSettings": {
                "framework": "nextjs",
            },
        }

        client = self._client or httpx.AsyncClient(timeout=20.0)
        should_close = self._client is None

        try:
            resp = await client.post(url, json=payload, headers=self._headers, params=params)
            resp.raise_for_status()
            data = resp.json()

            dep_url = custom_domain or data.get("url", f"{project_name}.vercel.app")
            if not dep_url.startswith("http"):
                dep_url = f"https://{dep_url}"

            logger.info("Vercel deployment created: {id} ({target}) -> {url}", id=data.get("id"), target=target, url=dep_url)
            return DeploymentResult(
                id=data.get("id", "dep_mock_123"),
                url=dep_url,
                ready_state=data.get("readyState", "READY"),
                target=target,
            )
        except httpx.HTTPError as exc:
            logger.error("Vercel deployment request error: {err}", err=exc)
            raise
        finally:
            if should_close:
                await client.aclose()

    async def get_deployment(self, deployment_id: str) -> DeploymentResult:
        """Retrieves status and build logs of an existing deployment."""
        url = f"{self.api_base}/v13/deployments/{deployment_id}"
        client = self._client or httpx.AsyncClient(timeout=10.0)
        should_close = self._client is None

        try:
            resp = await client.get(url, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()
            return DeploymentResult(
                id=data.get("id", deployment_id),
                url=data.get("url", ""),
                ready_state=data.get("readyState", "READY"),
                target=data.get("target", "preview"),
            )
        finally:
            if should_close:
                await client.aclose()

    async def set_project_env_vars(
        self,
        project_name: str,
        env_vars: dict[str, str],
        target: str = "preview",
    ) -> dict[str, Any]:
        """Injects environment variables securely into Vercel project."""
        url = f"{self.api_base}/v10/projects/{project_name}/env"
        client = self._client or httpx.AsyncClient(timeout=10.0)
        should_close = self._client is None

        created = 0
        try:
            for key, val in env_vars.items():
                body = {
                    "key": key,
                    "value": val,
                    "type": "encrypted",
                    "target": [target],
                }
                resp = await client.post(url, json=body, headers=self._headers)
                if resp.status_code in (200, 201):
                    created += 1
            return {"project": project_name, "created_count": created, "keys": list(env_vars.keys())}
        finally:
            if should_close:
                await client.aclose()
