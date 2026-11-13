"""Deep research pipeline combining SearXNG and Trafilatura (TC-134)."""

from typing import Any
from loguru import logger
from pydantic import BaseModel

from services.extractor import WebpageExtractor
from services.searxng import SearXNGClient


class ResearchResult(BaseModel):
    """Aggregated research dossier."""

    query: str
    sources_count: int
    dossier_markdown: str
    sources: list[dict[str, str]]


class DeepResearcher:
    """Performs multi-source anonymous web research and content synthesis."""

    def __init__(
        self,
        searxng_client: SearXNGClient | None = None,
        extractor: WebpageExtractor | None = None,
    ) -> None:
        self.searxng = searxng_client or SearXNGClient()
        self.extractor = extractor or WebpageExtractor()

    async def research(self, query: str, top_n: int = 3) -> ResearchResult:
        """Executes search and page extractions returning structured markdown dossier (TC-134)."""
        logger.info("Conducting deep research on '{q}' (top {n} sources)", q=query, n=top_n)
        search_items = await self.searxng.search(query=query, limit=top_n)

        dossier_parts: list[str] = [f"# Relatório de Pesquisa OSINT: {query}\n"]
        sources: list[dict[str, str]] = []

        for item in search_items:
            try:
                page_data = await self.extractor.fetch_page_markdown(item.url)
                title = page_data.title or item.title
                dossier_parts.append(f"## Fonte: {title}\nURL: {item.url}\n\n{page_data.markdown[:2500]}\n---")
                sources.append({"title": title, "url": item.url})
            except Exception as exc:
                logger.debug("Failed extracting source {u}: {err}", u=item.url, err=exc)
                dossier_parts.append(f"## Fonte: {item.title}\nURL: {item.url}\n\nResumo SearXNG: {item.content}\n---")
                sources.append({"title": item.title, "url": item.url})

        return ResearchResult(
            query=query,
            sources_count=len(sources),
            dossier_markdown="\n\n".join(dossier_parts),
            sources=sources,
        )
