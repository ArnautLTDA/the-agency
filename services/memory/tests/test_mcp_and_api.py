"""Tests for Memory Gateway MCP Server and FastAPI endpoints."""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from main import app
from mcp_server import create_memory_mcp_server
from services.embedder import LocalEmbedder
from services.qdrant_service import QdrantVectorService


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoints_public(client: TestClient):
    """Health endpoints are exempt from X-Agency-Key."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert resp.json()["service"] == "knowledge-memory-gateway"
    assert resp.json()["port"] == 3013


def test_protected_route_without_key_is_rejected(client: TestClient):
    """Non-exempt routes reject requests missing X-Agency-Key."""
    resp = client.get("/sse")
    assert resp.status_code == 401
    assert resp.json()["error"] == "missing_or_invalid_agency_key"


@pytest.mark.asyncio
async def test_mcp_all_tools_execution(tmp_path: Path):
    """Executes all registered MCP tools on memory server."""
    qdrant = QdrantVectorService()
    embedder = LocalEmbedder()
    server = create_memory_mcp_server(qdrant_service=qdrant, embedder=embedder)

    # 1. Remember
    res_rem = await server.call_tool(
        "remember",
        {
            "content": "Cliente Barbearia Vintage contratou landing page",
            "scope": "private",
            "namespace": "barbearia-vintage",
            "tags": ["contrato", "vendas"],
        },
    )
    assert res_rem is not None

    # 2. Recall
    res_rec = await server.call_tool(
        "recall",
        {
            "query": "barbearia vintage contrato",
            "namespace": "barbearia-vintage",
            "allow_web_fallback": False,
        },
    )
    assert res_rec is not None

    # 3. Get Project Context (TC-203)
    res_ctx = await server.call_tool("get_project_context", {"client_slug": "barbearia-vintage"})
    assert res_ctx is not None

    # 4. Ingest Document
    sample_doc = tmp_path / "doc.md"
    sample_doc.write_text("# Guia de Deploy\n\nInstruções detalhadas.\n", encoding="utf-8")
    res_ing = await server.call_tool("ingest_document", {"file_path": str(sample_doc), "namespace": "dev"})
    assert res_ing is not None

    # 5. Forget
    res_for = await server.call_tool("forget", {"memory_id": "mem_non_existing"})
    assert res_for is not None
