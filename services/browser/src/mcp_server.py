"""Native MCP Server registering Browser automation and screenshot tools (:3014)."""

from typing import Any
from mcp.server.mcpserver import MCPServer

from browser_pool import BrowserPool


def create_browser_mcp_server(browser_pool: BrowserPool | None = None) -> MCPServer:
    """Builds and configures the browser-gateway MCP server instance."""
    server = MCPServer(
        name="browser-gateway",
        version="0.1.0",
        instructions="Official Agency Browser Automation & Screenshot Gateway MCP Server",
    )
    pool = browser_pool or BrowserPool()

    @server.tool(
        name="browser_screenshot",
        description="Captures high-resolution screenshot (e.g. mobile 375x812 DPR 3 for WhatsApp, or desktop 1280x800) (TC-158).",
    )
    async def browser_screenshot(
        url: str,
        viewport_width: int = 1280,
        viewport_height: int = 800,
        device_scale_factor: float = 1.0,
        full_page: bool = False,
        wait_for_selector: str | None = None,
    ) -> dict[str, Any]:
        result = await pool.capture_screenshot(
            url=url,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            device_scale_factor=device_scale_factor,
            full_page=full_page,
            wait_for_selector=wait_for_selector,
        )
        return result.model_dump()

    @server.tool(
        name="browser_inspect_console",
        description="Inspects page for console runtime errors, failed HTTP assets, and React hydration errors (TC-159).",
    )
    async def browser_inspect_console(url: str) -> dict[str, Any]:
        report = await pool.inspect_console(url)
        return report.model_dump()

    @server.tool(
        name="browser_interact",
        description="Performs automated sequence of UI actions (click, fill, wait) on a page (TC-160).",
    )
    async def browser_interact(url: str, actions: list[dict[str, Any]]) -> dict[str, Any]:
        res = await pool.interact(url, actions)
        return res.model_dump()

    @server.tool(
        name="browser_run_e2e_tests",
        description="Executes automated Playwright E2E journey tests against a workspace (TC-161).",
    )
    async def browser_run_e2e_tests(workspace_id: str, test_filter: str | None = None) -> dict[str, Any]:
        result = await pool.run_e2e_tests(workspace_id, test_filter)
        return result.model_dump()

    return server
