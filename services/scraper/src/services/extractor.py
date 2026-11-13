"""HTML to Markdown extraction using Trafilatura (TC-131, TC-191)."""

import re
from typing import Any
import httpx
from loguru import logger
from pydantic import BaseModel
import trafilatura

from config import settings


class PageMarkdownResult(BaseModel):
    """Result of webpage content extraction."""

    url: str
    markdown: str
    title: str | None = None
    length_bytes: int
    raw_html: str | None = None


class WebpageExtractor:
    """Extracts clean markdown from webpages with boilerplate removal."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch_page_markdown(
        self,
        url: str,
        strip_boilerplate: bool = True,
        max_bytes: int = settings.MAX_PAGE_BYTES,
    ) -> PageMarkdownResult:
        """Fetches webpage and converts to clean Markdown using Trafilatura (TC-131, TC-191)."""
        client = self._client or httpx.AsyncClient(
            timeout=settings.DEFAULT_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        should_close = self._client is None

        try:
            resp = await client.get(url)
            resp.raise_for_status()

            raw_bytes = resp.content
            if len(raw_bytes) > max_bytes:
                logger.warning("Page {u} exceeds size limit ({len} > {max}), truncating", u=url, len=len(raw_bytes), max=max_bytes)
                raw_bytes = raw_bytes[:max_bytes]

            html_text = raw_bytes.decode("utf-8", errors="replace")

            # Extract clean markdown via Trafilatura
            markdown_content = trafilatura.extract(
                html_text,
                include_links=True,
                include_images=False,
                output_format="markdown" if strip_boilerplate else "txt",
            )

            # Fallback if trafilatura extracts nothing
            if not markdown_content:
                # Basic tag stripping fallback
                cleaned = re.sub(r"<script.*?</script>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
                cleaned = re.sub(r"<style.*?</style>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
                cleaned = re.sub(r"<[^>]+>", " ", cleaned)
                markdown_content = " ".join(cleaned.split())[:5000]

            # Extract title tag if possible
            title_match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else None

            return PageMarkdownResult(
                url=url,
                markdown=markdown_content,
                title=title,
                length_bytes=len(markdown_content.encode("utf-8")),
                raw_html=html_text,
            )
        finally:
            if should_close:
                await client.aclose()
