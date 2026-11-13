"""SearXNG anonymous meta-search client (:8888 / TC-130)."""

from typing import Any
import httpx
from loguru import logger
from pydantic import BaseModel

from config import settings


class SearchResultItem(BaseModel):
    """Normalized search result item."""

    title: str
    url: str
    content: str
    engine: str = "searxng"
    score: float | None = None


class SearXNGClient:
    """Client for local SearXNG meta-search engine."""

    def __init__(
        self,
        base_url: str = settings.SEARXNG_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client

    async def search(
        self,
        query: str,
        categories: str = "general",
        limit: int = 5,
    ) -> list[SearchResultItem]:
        """Executes anonymous meta-search across engines (TC-130)."""
        url = f"{self.base_url}/search"
        params = {
            "q": query,
            "format": "json",
            "categories": categories,
        }

        client = self._client or httpx.AsyncClient(timeout=15.0)
        should_close = self._client is None

        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            raw_results = data.get("results", [])

            items: list[SearchResultItem] = []
            for item in raw_results[:limit]:
                items.append(
                    SearchResultItem(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        content=item.get("content", ""),
                        engine=item.get("engine", "searxng"),
                        score=item.get("score"),
                    )
                )

            logger.info("SearXNG search for '{q}' returned {count} results", q=query, count=len(items))
            return items
        except httpx.HTTPError as exc:
            logger.error("SearXNG search request failed: {err}", err=exc)
            raise
        finally:
            if should_close:
                await client.aclose()
