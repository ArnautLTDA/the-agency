"""Tests for Security Audit MCP Server tools (:3015)."""

from pathlib import Path
import pytest
import respx

from mcp_server import create_security_mcp_server
from scanners.sonarqube import SonarQubeClient


@pytest.mark.asyncio
async def test_mcp_tools_registration():
    """Verifies all 6 security tools are properly registered on MCP server."""
    server = create_security_mcp_server()
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]

    expected = [
        "run_sonarqube_scan",
        "scan_secrets",
        "scan_sast_semgrep",
        "scan_dependencies",
        "run_dast_scan",
        "get_security_gate_status",
    ]
    for exp in expected:
        assert exp in tool_names


@pytest.mark.asyncio
async def test_mcp_all_tools_execution(tmp_path: Path):
    """Executes each tool registered on MCP server."""
    clean_dir = tmp_path / "clean_mcp_full"
    clean_dir.mkdir()
    (clean_dir / "index.js").write_text("console.log('clean');", encoding="utf-8")
    (clean_dir / "requirements.txt").write_text("pytest>=8.0.0\n", encoding="utf-8")

    with respx.mock(base_url="http://localhost:9000") as mock_sq, \
         respx.mock(base_url="https://preview.agency.dev") as mock_dast:
        mock_sq.get("/api/qualitygates/project_status").respond(
            200,
            json={"projectStatus": {"status": "OK", "conditions": []}},
        )
        mock_dast.get("/").respond(200, headers={"X-Frame-Options": "DENY", "Content-Security-Policy": "default-src 'self'"})
        mock_dast.get("/.env").respond(404)
        mock_dast.get("/.git/HEAD").respond(404)

        server = create_security_mcp_server(
            sonarqube_client=SonarQubeClient(base_url="http://localhost:9000", token="test")
        )

        res_sq = await server.call_tool("run_sonarqube_scan", {"project_key": "agency-test"})
        assert res_sq is not None

        res_sast = await server.call_tool("scan_sast_semgrep", {"target_path": str(clean_dir)})
        assert res_sast is not None

        res_dep = await server.call_tool("scan_dependencies", {"target_path": str(clean_dir)})
        assert res_dep is not None

        res_dast = await server.call_tool("run_dast_scan", {"target_url": "https://preview.agency.dev"})
        assert res_dast is not None


@pytest.mark.asyncio
async def test_mcp_get_security_gate_status_tool():
    """Executes get_security_gate_status via MCP server."""
    server = create_security_mcp_server()
    clean_reports = [
        {"tool": "gitleaks", "passed": True, "findings": []},
        {"tool": "semgrep", "passed": True, "findings": []},
    ]

    res = await server.call_tool("get_security_gate_status", {"reports": clean_reports})
    assert res is not None
    assert len(res.content) > 0
