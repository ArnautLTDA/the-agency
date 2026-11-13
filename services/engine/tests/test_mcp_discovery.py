"""Tests for MCP Dynamic Discovery and Unified Tool Registry (Onda 8)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.tools.mcp_client import MCPClientHost
from src.tools.mcp_discovery import (
    OFFICIAL_MCP_SERVICES,
    MCPDiscoveryService,
    set_discovery_service,
)
from src.tools.registry import execute_tool


@pytest.fixture
def mock_clients():
    clients: dict[str, MagicMock] = {}
    for name in OFFICIAL_MCP_SERVICES:
        client = MagicMock(spec=MCPClientHost)
        client.base_url = f"http://mock/{name}"
        client.list_tools = AsyncMock()
        client.call_tool = AsyncMock()
        clients[name] = client
    return clients


@pytest.mark.asyncio
async def test_mcp_discovery_all_online(mock_clients):
    """All 11 MCP services return tools successfully and populate catalog."""
    mock_clients["whatsapp-gateway"].list_tools.return_value = ["send_whatsapp_message", "check_whatsapp_numbers"]
    mock_clients["payment-gateway"].list_tools.return_value = ["create_pix_charge", "get_account_balance"]
    mock_clients["deploy-cloud-gateway"].list_tools.return_value = ["deploy_production", "provision_database"]
    mock_clients["workspace-sandbox"].list_tools.return_value = ["read_file", "write_file", "patch_file"]
    mock_clients["knowledge-memory-gateway"].list_tools.return_value = ["recall", "remember"]
    mock_clients["browser-gateway"].list_tools.return_value = ["browser_screenshot", "browser_interact"]
    mock_clients["security-audit-gateway"].list_tools.return_value = ["run_sonarqube_scan", "scan_secrets"]
    mock_clients["osint-scraper-gateway"].list_tools.return_value = ["search_web", "enrich_lead_profile"]
    mock_clients["telegram-gateway"].list_tools.return_value = ["send_telegram_alert"]
    mock_clients["guardrail-gateway"].list_tools.return_value = ["inspect_prompt_safety"]
    mock_clients["git-vcs-gateway"].list_tools.return_value = ["git_commit", "git_push"]

    discovery = MCPDiscoveryService(clients=mock_clients)
    catalog = await discovery.discover_all(timeout_per_service=1.0)

    assert len(catalog) == 11
    assert discovery.is_tool_available("create_pix_charge")
    assert discovery.get_service_for_tool("create_pix_charge") == "payment-gateway"
    assert discovery.is_tool_available("browser_screenshot")
    assert discovery.get_service_for_tool("browser_screenshot") == "browser-gateway"


@pytest.mark.asyncio
async def test_mcp_discovery_graceful_degradation(mock_clients):
    """If one service is offline, discovery marks it OFFLINE without crashing."""
    mock_clients["browser-gateway"].list_tools.side_effect = RuntimeError("Connection refused")
    mock_clients["whatsapp-gateway"].list_tools.return_value = ["send_whatsapp_message"]

    discovery = MCPDiscoveryService(clients=mock_clients)
    catalog = await discovery.discover_all(timeout_per_service=0.5)

    assert discovery.service_status["browser-gateway"] == "OFFLINE"
    assert catalog["browser-gateway"] == []
    assert discovery.service_status["whatsapp-gateway"] == "ONLINE"
    assert discovery.is_tool_available("send_whatsapp_message")


@pytest.mark.asyncio
async def test_mcp_discovery_call_remote_tool(mock_clients):
    """call_tool routes dynamically to the service hosting the requested tool."""
    mock_clients["payment-gateway"].list_tools.return_value = ["create_pix_charge"]
    mock_clients["payment-gateway"].call_tool.return_value = '{"txid": "pix_abc", "status": "ATIVA"}'

    discovery = MCPDiscoveryService(clients=mock_clients)
    await discovery.discover_all()

    result = await discovery.call_tool("create_pix_charge", {"lead_id": "lead-1", "amount_cents": 100000})

    assert "pix_abc" in result
    mock_clients["payment-gateway"].call_tool.assert_called_once_with(
        "create_pix_charge", {"lead_id": "lead-1", "amount_cents": 100000}
    )


@pytest.mark.asyncio
async def test_mcp_discovery_call_unknown_tool_raises(mock_clients):
    """Calling an undiscovered tool raises KeyError."""
    discovery = MCPDiscoveryService(clients=mock_clients)
    await discovery.discover_all()

    with pytest.raises(KeyError, match="not found on any registered MCP service"):
        await discovery.call_tool("non_existent_tool", {})


@pytest.mark.asyncio
async def test_registry_integration_with_discovered_tool(tmp_path: Path, mock_clients):
    """execute_tool in registry dynamically delegates to MCP discovery for remote tools."""
    mock_clients["deploy-cloud-gateway"].list_tools.return_value = ["deploy_preview_demo"]
    mock_clients["deploy-cloud-gateway"].call_tool.return_value = "https://preview.vercel.app"

    discovery = MCPDiscoveryService(clients=mock_clients)
    await discovery.discover_all()
    set_discovery_service(discovery)

    res = await execute_tool(
        name="deploy_preview_demo",
        arguments={"workspace_id": "ws-1", "project_name": "client-preview"},
        workspace_dir=tmp_path,
    )

    assert "https://preview.vercel.app" in res
    mock_clients["deploy-cloud-gateway"].call_tool.assert_called_once()

    # Reset singleton
    set_discovery_service(None)


@pytest.mark.asyncio
async def test_mcp_discovery_timeout_and_catalog(mock_clients):
    """Discovery handles TimeoutError and returns catalog snapshot."""
    import asyncio
    from src.tools.mcp_discovery import get_discovery_service

    async def slow_tools():
        await asyncio.sleep(0.5)
        return ["delayed_tool"]

    mock_clients["osint-scraper-gateway"].list_tools.side_effect = slow_tools

    discovery = MCPDiscoveryService(clients=mock_clients)
    catalog_res = await discovery.discover_all(timeout_per_service=0.05)

    assert discovery.service_status["osint-scraper-gateway"] == "TIMEOUT"
    assert catalog_res["osint-scraper-gateway"] == []

    # Telemetry snapshot
    cat = discovery.get_catalog()
    assert "total_tools" in cat
    assert "services" in cat
    assert "osint-scraper-gateway" in cat["services"]

    # Singleton
    ds = get_discovery_service()
    assert ds is not None
    set_discovery_service(None)
