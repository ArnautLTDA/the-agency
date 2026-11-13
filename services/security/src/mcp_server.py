"""Native MCP Server registering security audit and gate tools (:3015)."""

from typing import Any
from mcp.server.mcpserver import MCPServer

from gate import evaluate_security_gate
from scanners.base import ScanReport
from scanners.gitleaks import scan_secrets as _scan_secrets
from scanners.nuclei import run_dast_scan as _run_dast_scan
from scanners.semgrep import scan_sast_semgrep as _scan_sast_semgrep
from scanners.sonarqube import SonarQubeClient, run_sonarqube_scan as _run_sonarqube_scan
from scanners.trivy import scan_dependencies as _scan_dependencies


def create_security_mcp_server(sonarqube_client: SonarQubeClient | None = None) -> MCPServer:
    """Builds and configures the security-audit-gateway MCP server instance."""
    server = MCPServer(
        name="security-audit-gateway",
        version="0.1.0",
        instructions="Official Agency Security Audit Gateway MCP Server",
    )

    @server.tool(
        name="run_sonarqube_scan",
        description="Checks SonarQube Quality Gate status and metrics on port 9000 (TC-169).",
    )
    async def run_sonarqube_scan(project_key: str, repo_path: str = "") -> dict[str, Any]:
        report = await _run_sonarqube_scan(project_key=project_key, repo_path=repo_path, client=sonarqube_client)
        return report.model_dump()

    @server.tool(
        name="scan_secrets",
        description="Scans directory or repository for hardcoded secrets and credentials using Gitleaks (TC-166).",
    )
    async def scan_secrets(target_path: str) -> dict[str, Any]:
        report = await _scan_secrets(target_path)
        return report.model_dump()

    @server.tool(
        name="scan_sast_semgrep",
        description="Scans codebase for OWASP Top 10 SAST vulnerabilities using Semgrep (TC-167).",
    )
    async def scan_sast_semgrep(target_path: str, rules: str = "p/owasp-top-10") -> dict[str, Any]:
        report = await _scan_sast_semgrep(target_path, rules=rules)
        return report.model_dump()

    @server.tool(
        name="scan_dependencies",
        description="Scans dependencies for known CVEs and vulnerabilities using Trivy (TC-168).",
    )
    async def scan_dependencies(target_path: str) -> dict[str, Any]:
        report = await _scan_dependencies(target_path)
        return report.model_dump()

    @server.tool(
        name="run_dast_scan",
        description="Runs DAST probe against deployed preview URL using Nuclei (TC-210).",
    )
    async def run_dast_scan(target_url: str) -> dict[str, Any]:
        report = await _run_dast_scan(target_url)
        return report.model_dump()

    @server.tool(
        name="get_security_gate_status",
        description="Evaluates all security scan reports against zero-critical/high policy (TC-170, TC-211).",
    )
    async def get_security_gate_status(reports: list[dict[str, Any]]) -> dict[str, Any]:
        parsed_reports = [ScanReport.model_validate(r) for r in reports]
        decision = evaluate_security_gate(parsed_reports)
        return decision.model_dump()

    return server
