"""SonarQube integration client for project Quality Gate verification."""

from typing import Any
import httpx
from loguru import logger

from config import settings
from scanners.base import Finding, ScanReport, SeverityLevel


class SonarQubeClient:
    """HTTP client communicating with SonarQube API (:9000)."""

    def __init__(
        self,
        base_url: str = settings.SONARQUBE_URL,
        token: str = settings.SONARQUBE_TOKEN,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = client

    @property
    def _auth(self) -> tuple[str, str]:
        return (self.token, "")

    async def get_project_status(self, project_key: str) -> dict[str, Any]:
        """Fetches Quality Gate status for a project."""
        url = f"{self.base_url}/api/qualitygates/project_status"
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            resp = await client.get(url, params={"projectKey": project_key}, auth=self._auth)
            resp.raise_for_status()
            return resp.json()
        finally:
            if self._client is None:
                await client.aclose()

    async def get_project_measures(self, project_key: str) -> dict[str, Any]:
        """Fetches component measures (bugs, vulnerabilities, hotspots, coverage)."""
        url = f"{self.base_url}/api/measures/component"
        client = self._client or httpx.AsyncClient(timeout=10.0)
        metric_keys = "bugs,vulnerabilities,security_hotspots,coverage,code_smells"
        try:
            resp = await client.get(
                url,
                params={"component": project_key, "metricKeys": metric_keys},
                auth=self._auth,
            )
            resp.raise_for_status()
            return resp.json()
        finally:
            if self._client is None:
                await client.aclose()


async def run_sonarqube_scan(
    project_key: str,
    repo_path: str = "",
    client: SonarQubeClient | None = None,
) -> ScanReport:
    """Verifies SonarQube Quality Gate status for a project (TC-169)."""
    sq_client = client or SonarQubeClient()
    try:
        data = await sq_client.get_project_status(project_key)
        project_status = data.get("projectStatus", {})
        status = project_status.get("status", "ERROR")  # "OK" or "ERROR"

        findings: list[Finding] = []
        conditions = project_status.get("conditions", [])
        for cond in conditions:
            if cond.get("status") == "ERROR":
                metric = cond.get("metricKey", "unknown")
                actual = cond.get("actualValue", "")
                threshold = cond.get("errorThreshold", "")
                findings.append(
                    Finding(
                        rule_id=f"sonar-qg-{metric}",
                        description=f"Quality gate condition failed: {metric} is {actual} (threshold: {threshold})",
                        file_path=repo_path,
                        severity=SeverityLevel.HIGH,
                        tool="sonarqube",
                    )
                )

        passed = status == "OK" and len(findings) == 0
        return ScanReport(
            tool="sonarqube",
            passed=passed,
            findings=findings,
            raw_output=f"SonarQube Quality Gate: {status}",
        )
    except httpx.HTTPError as exc:
        logger.warning("SonarQube connection error for project {k}: {err}", k=project_key, err=exc)
        return ScanReport(
            tool="sonarqube",
            passed=False,
            error=f"SonarQube service unavailable or returned error: {str(exc)}",
        )
    except Exception as exc:
        logger.error("Unexpected error querying SonarQube: {err}", err=exc)
        return ScanReport(
            tool="sonarqube",
            passed=False,
            error=str(exc),
        )
