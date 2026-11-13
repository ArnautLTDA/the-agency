"""Tests for Qdrant Vector Service and Multi-Tenancy Isolation (TC-151, TC-155, TC-157)."""

import pytest

from services.embedder import LocalEmbedder
from services.qdrant_service import QdrantVectorService


@pytest.mark.asyncio
async def test_upsert_and_search_vector_tc151(qdrant_service: QdrantVectorService, embedder: LocalEmbedder):
    """TC-151: Stored vectors are retrieved by cosine similarity."""
    v1 = embedder.embed_text("Microsserviço de pagamentos PIX com Banco Inter")
    v2 = embedder.embed_text("Configuração de logs no Grafana e Loki")

    await qdrant_service.upsert("mem_1", "PIX Inter", v1, scope="public")
    await qdrant_service.upsert("mem_2", "Grafana Logs", v2, scope="public")

    q_vec = embedder.embed_text("pagamento pix banco inter")
    results = await qdrant_service.search(q_vec, limit=2)

    assert len(results) == 2
    assert results[0].id == "mem_1"
    assert results[0].score > results[1].score


@pytest.mark.asyncio
async def test_multi_tenancy_isolation_tc155(qdrant_service: QdrantVectorService, embedder: LocalEmbedder):
    """TC-155: Multi-tenancy filtering isolates data between scopes and client namespaces."""
    v_common = embedder.embed_text("Informações do projeto")

    # Client A private memory
    await qdrant_service.upsert("mem_a", "Dados confidenciais Cliente A", v_common, scope="private", namespace="client_a")
    # Client B private memory
    await qdrant_service.upsert("mem_b", "Dados confidenciais Cliente B", v_common, scope="private", namespace="client_b")

    # Query for Client A
    results_a = await qdrant_service.search(v_common, namespace="client_a")
    assert len(results_a) == 1
    assert results_a[0].id == "mem_a"
    assert "Cliente A" in results_a[0].content

    # Query for Client B
    results_b = await qdrant_service.search(v_common, namespace="client_b")
    assert len(results_b) == 1
    assert results_b[0].id == "mem_b"
    assert "Cliente B" in results_b[0].content


@pytest.mark.asyncio
async def test_delete_memory_item_tc157(qdrant_service: QdrantVectorService, embedder: LocalEmbedder):
    """TC-157: Deleting memory removes item from search results."""
    vec = embedder.embed_text("Memória temporária")
    await qdrant_service.upsert("mem_temp", "temporário", vec)

    deleted = await qdrant_service.delete("mem_temp")
    assert deleted is True

    # Searching should return empty
    results = await qdrant_service.search(vec)
    assert len(results) == 0
