"""Tests for OSINT Scraper MCP Server tools and FastAPI endpoints."""

from fastapi.testclient import TestClient
import pytest
import respx

from main import app
from mcp_server import create_scraper_mcp_server
from services.extractor import WebpageExtractor
from services.maps_scraper import GoogleMapsScraper
from services.searxng import SearXNGClient


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoints_public(client: TestClient):
    """Health endpoints are exempt from X-Agency-Key."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert resp.json()["service"] == "osint-scraper-gateway"
    assert resp.json()["port"] == 3009


def test_protected_route_without_key_is_rejected(client: TestClient):
    """Non-exempt routes reject requests missing X-Agency-Key."""
    resp = client.get("/sse")
    assert resp.status_code == 401
    assert resp.json()["error"] == "missing_or_invalid_agency_key"


@pytest.mark.asyncio
async def test_mcp_scrape_google_maps_tool():
    """Executes scrape_google_maps via MCP server."""
    server = create_scraper_mcp_server(maps_scraper=GoogleMapsScraper())
    res = await server.call_tool("scrape_google_maps", {"query": "restaurante", "city": "Curitiba", "depth": 2})

    assert res is not None
    assert len(res.content) > 0


@pytest.mark.asyncio
async def test_mcp_all_tools_execution(sample_business_html: str):
    """Executes all registered MCP tools on scraper server."""
    with respx.mock(base_url="http://localhost:8888") as mock_searx, \
         respx.mock(base_url="https://site-teste.com") as mock_site:
        mock_searx.get("/search").respond(
            200,
            json={"results": [{"title": "T", "url": "https://site-teste.com", "content": "C"}]},
        )
        mock_site.get("/").respond(200, html=sample_business_html)

        server = create_scraper_mcp_server()

        res_search = await server.call_tool("search_web", {"query": "teste"})
        assert res_search is not None

        res_fetch = await server.call_tool("fetch_page_markdown", {"url": "https://site-teste.com"})
        assert res_fetch is not None

        res_enrich = await server.call_tool(
            "enrich_lead_profile",
            {"lead_id": "l1", "website": "https://site-teste.com"},
        )
        assert res_enrich is not None

        res_deep = await server.call_tool("deep_research", {"query": "teste", "top_n": 1})
        assert res_deep is not None
