"""Corrective RAG (CRAG) Engine (TC-152, TC-153, TC-154)."""

from typing import Any
import httpx
from loguru import logger
from pydantic import BaseModel, Field

from config import settings
from services.qdrant_service import MemoryItem
from services.reranker import LocalReranker, RerankedItem


class CragResponse(BaseModel):
    """Result of Corrective RAG evaluation and synthesis."""

    eval_result: str  # "CORRECT", "AMBIGUOUS", "INCORRECT"
    top_score: float
    documents: list[dict[str, Any]]
    web_fallback_executed: bool = False
    details: str | None = None


class CragEngine:
    """Evaluates retrieved context and executes corrective web search when needed."""

    def __init__(
        self,
        reranker: LocalReranker | None = None,
        searxng_url: str = settings.SEARXNG_URL,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.reranker = reranker or LocalReranker()
        self.searxng_url = searxng_url.rstrip("/")
        self._http_client = http_client

    async def _search_web_fallback(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Queries SearXNG as corrective fallback."""
        url = f"{self.searxng_url}/search"
        client = self._http_client or httpx.AsyncClient(timeout=10.0)
        should_close = self._http_client is None

        try:
            resp = await client.get(url, params={"q": query, "format": "json"})
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                return [
                    {
                        "source": "web_fallback",
                        "content": r.get("content", ""),
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "relevance_score": 0.70,
                    }
                    for r in results[:limit]
                ]
            return []
        except Exception as exc:
            logger.warning("CRAG web search fallback failed: {err}", err=exc)
            return []
        finally:
            if should_close:
                await client.aclose()

    async def process_retrieval(
        self,
        query: str,
        retrieved_items: list[MemoryItem],
        allow_web_fallback: bool = True,
    ) -> CragResponse:
        """Processes candidate documents through CRAG evaluation loop (TC-152, TC-153, TC-154)."""
        candidates = [item.model_dump() for item in retrieved_items]
        reranked = self.reranker.rerank(query, candidates)

        top_score = reranked[0].relevance_score if reranked else 0.0

        # 1. High confidence local knowledge (CORRECT: score >= 0.80)
        if top_score >= 0.80:
            logger.info("CRAG result CORRECT (score={s:.2f}) -> Returning local knowledge directly", s=top_score)
            return CragResponse(
                eval_result="CORRECT",
                top_score=top_score,
                documents=[r.model_dump() for r in reranked],
                web_fallback_executed=False,
                details="Local knowledge meets high confidence threshold (>= 0.80)",
            )

        # 2. Ambiguous local knowledge (AMBIGUOUS: 0.50 <= score < 0.80)
        if 0.50 <= top_score < 0.80:
            logger.info("CRAG result AMBIGUOUS (score={s:.2f}) -> Augmenting with web search", s=top_score)
            web_docs: list[dict[str, Any]] = []
            if allow_web_fallback:
                web_docs = await self._search_web_fallback(query)

            combined_docs = [r.model_dump() for r in reranked] + web_docs
            return CragResponse(
                eval_result="AMBIGUOUS",
                top_score=top_score,
                documents=combined_docs,
                web_fallback_executed=len(web_docs) > 0,
                details="Local knowledge ambiguous (0.50-0.80); augmented with web search",
            )

        # 3. Poor or missing local knowledge (INCORRECT: score < 0.50)
        logger.info("CRAG result INCORRECT (score={s:.2f}) -> Executing full web search fallback", s=top_score)
        web_docs = []
        if allow_web_fallback:
            web_docs = await self._search_web_fallback(query)

        return CragResponse(
            eval_result="INCORRECT",
            top_score=top_score,
            documents=web_docs,
            web_fallback_executed=len(web_docs) > 0,
            details="Local knowledge below confidence threshold (< 0.50); replaced with web search",
        )
