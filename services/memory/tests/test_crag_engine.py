"""Tests for Corrective RAG (CRAG) Engine (TC-152, TC-153, TC-154)."""

import pytest
import respx

from services.crag_engine import CragEngine
from services.qdrant_service import MemoryItem
from services.reranker import LocalReranker


@pytest.mark.asyncio
async def test_crag_correct_local_knowledge_tc152():
    """TC-152: High confidence match (score >= 0.80) returns local knowledge without web search."""
    reranker = LocalReranker()
    # Mock reranker to return high relevance score >= 0.80
    reranker.compute_relevance_score = lambda q, d, s: 0.92

    engine = CragEngine(reranker=reranker, searxng_url="http://localhost:8888")
    items = [
        MemoryItem(
            id="mem_1",
            content="Instruções completas sobre o deploy na Vercel",
            score=0.95,
        )
    ]

    res = await engine.process_retrieval("deploy vercel", items, allow_web_fallback=True)

    assert res.eval_result == "CORRECT"
    assert res.top_score >= 0.80
    assert not res.web_fallback_executed
    assert len(res.documents) == 1


@pytest.mark.asyncio
async def test_crag_ambiguous_local_knowledge_augments_web_tc153():
    """TC-153: Medium confidence match (0.50 <= score < 0.80) augments local knowledge with web search."""
    reranker = LocalReranker()
    reranker.compute_relevance_score = lambda q, d, s: 0.65

    with respx.mock(base_url="http://localhost:8888") as mock:
        mock.get("/search").respond(
            200,
            json={"results": [{"title": "Web Info", "content": "Dados atualizados da web", "url": "https://web.com"}]},
        )

        engine = CragEngine(reranker=reranker, searxng_url="http://localhost:8888")
        items = [
            MemoryItem(
                id="mem_1",
                content="Fragmento parcial de documentação",
                score=0.60,
            )
        ]

        res = await engine.process_retrieval("consulta ambígua", items, allow_web_fallback=True)

        assert res.eval_result == "AMBIGUOUS"
        assert 0.50 <= res.top_score < 0.80
        assert res.web_fallback_executed is True
        assert len(res.documents) == 2  # 1 local + 1 web


@pytest.mark.asyncio
async def test_crag_incorrect_local_knowledge_full_web_fallback_tc154():
    """TC-154: Low confidence match (score < 0.50) executes full web search fallback."""
    reranker = LocalReranker()
    reranker.compute_relevance_score = lambda q, d, s: 0.30

    with respx.mock(base_url="http://localhost:8888") as mock:
        mock.get("/search").respond(
            200,
            json={"results": [{"title": "Web Solution", "content": "Solução completa da internet", "url": "https://solucao.com"}]},
        )

        engine = CragEngine(reranker=reranker, searxng_url="http://localhost:8888")
        items = [
            MemoryItem(
                id="mem_1",
                content="Conteúdo irrelevante sobre outro tópico",
                score=0.20,
            )
        ]

        res = await engine.process_retrieval("novo framework 2026", items, allow_web_fallback=True)

        assert res.eval_result == "INCORRECT"
        assert res.top_score < 0.50
        assert res.web_fallback_executed is True
        assert len(res.documents) == 1
        assert res.documents[0]["source"] == "web_fallback"
