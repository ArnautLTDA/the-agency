"""MCP Dynamic Auto-Discovery Module for the 11 Microservice Servers (Onda 8)."""

import asyncio
import os
from typing import Any
from loguru import logger

from agency_common.auth import get_agency_secret_key
from src.tools.mcp_client import MCPClientHost


# Standard topology map for all 11 MCP microservices
OFFICIAL_MCP_SERVICES: dict[str, str] = {
    "workspace-sandbox": os.environ.get("SANDBOX_MCP_URL", "http://127.0.0.1:3010/sse"),
    "whatsapp-gateway": os.environ.get("WHATSAPP_MCP_URL", "http://127.0.0.1:3005/sse"),
    "payment-gateway": os.environ.get("PAYMENT_MCP_URL", "http://127.0.0.1:3006/sse"),
    "guardrail-gateway": os.environ.get("GUARDRAIL_MCP_URL", "http://127.0.0.1:3007/sse"),
    "telegram-gateway": os.environ.get("TELEGRAM_MCP_URL", "http://127.0.0.1:3008/sse"),
    "osint-scraper-gateway": os.environ.get("SCRAPER_MCP_URL", "http://127.0.0.1:3009/sse"),
    "git-vcs-gateway": os.environ.get("GIT_MCP_URL", "http://127.0.0.1:3011/sse"),
    "deploy-cloud-gateway": os.environ.get("DEPLOY_MCP_URL", "http://127.0.0.1:3012/sse"),
    "knowledge-memory-gateway": os.environ.get("MEMORY_MCP_URL", "http://127.0.0.1:3013/sse"),
    "browser-gateway": os.environ.get("BROWSER_MCP_URL", "http://127.0.0.1:3014/sse"),
    "security-audit-gateway": os.environ.get("SECURITY_MCP_URL", "http://127.0.0.1:3015/sse"),
}


class MCPDiscoveryService:
    """Discovers and catalogs tools exposed across all 11 MCP microservices via SSE."""

    def __init__(
        self,
        services_map: dict[str, str] | None = None,
        api_key: str | None = None,
        clients: dict[str, MCPClientHost] | None = None,
    ) -> None:
        self.services_map = dict(services_map or OFFICIAL_MCP_SERVICES)
        self.api_key = api_key or get_agency_secret_key()
        self.clients: dict[str, MCPClientHost] = dict(clients or {})

        # Populate clients for unconfigured services
        for name, url in self.services_map.items():
            if name not in self.clients:
                self.clients[name] = MCPClientHost(base_url=url, api_key=self.api_key)

        self.service_tools: dict[str, list[str]] = {}
        self.tool_to_service: dict[str, str] = {}
        self.service_status: dict[str, str] = {name: "PENDING" for name in self.services_map}

    async def _discover_single(
        self,
        name: str,
        client: MCPClientHost,
        timeout: float,
    ) -> tuple[str, list[str], str]:
        """Discovers tools on a single service with strict timeout."""
        try:
            tools = await asyncio.wait_for(client.list_tools(), timeout=timeout)
            return (name, tools, "ONLINE")
        except asyncio.TimeoutError:
            logger.warning(f"MCP discovery timed out for {name} ({client.base_url})")
            return (name, [], "TIMEOUT")
        except Exception as exc:
            logger.warning(f"MCP discovery failed for {name} ({client.base_url}): {exc}")
            return (name, [], "OFFLINE")

    async def discover_all(self, timeout_per_service: float = 2.0) -> dict[str, list[str]]:
        """Queries tools/list via SSE across all 11 MCP servers concurrently."""
        logger.info(f"Initiating MCP auto-discovery across {len(self.clients)} services...")

        tasks = [
            self._discover_single(name, client, timeout_per_service)
            for name, client in self.clients.items()
        ]
        results = await asyncio.gather(*tasks)

        self.service_tools.clear()
        self.tool_to_service.clear()

        for name, tools, status in results:
            self.service_tools[name] = tools
            self.service_status[name] = status
            for tool_name in tools:
                self.tool_to_service[tool_name] = name

        total_tools = len(self.tool_to_service)
        online_count = sum(1 for st in self.service_status.values() if st == "ONLINE")
        logger.info(
            f"MCP auto-discovery complete: {online_count}/{len(self.clients)} services ONLINE, "
            f"{total_tools} tools registered in unified catalog."
        )
        return dict(self.service_tools)

    def is_tool_available(self, tool_name: str) -> bool:
        """Returns True if the tool was discovered on an online MCP service."""
        return tool_name in self.tool_to_service

    def get_service_for_tool(self, tool_name: str) -> str | None:
        """Returns the service name hosting a specific tool."""
        return self.tool_to_service.get(tool_name)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Routes tool execution dynamically to the responsible MCP microservice."""
        service_name = self.tool_to_service.get(tool_name)
        if not service_name or service_name not in self.clients:
            raise KeyError(f"Tool '{tool_name}' not found on any registered MCP service.")

        client = self.clients[service_name]
        logger.info(f"Routing MCP tool '{tool_name}' invocation to service '{service_name}'.")
        return await client.call_tool(tool_name, arguments)

    def get_catalog(self) -> dict[str, Any]:
        """Returns unified catalog snapshot for cockpit telemetry and debugging."""
        return {
            "total_tools": len(self.tool_to_service),
            "services": {
                name: {
                    "url": self.services_map.get(name, ""),
                    "status": self.service_status.get(name, "UNKNOWN"),
                    "tools": self.service_tools.get(name, []),
                }
                for name in self.services_map
            },
        }


# Global singleton instance
_discovery_service: MCPDiscoveryService | None = None


def get_discovery_service() -> MCPDiscoveryService:
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = MCPDiscoveryService()
    return _discovery_service


def set_discovery_service(service: MCPDiscoveryService | None) -> None:
    global _discovery_service
    _discovery_service = service
