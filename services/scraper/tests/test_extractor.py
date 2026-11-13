"""Tests for Webpage Markdown Extractor (TC-131, TC-191)."""

import pytest
import respx

from services.extractor import WebpageExtractor


@pytest.mark.asyncio
async def test_fetch_page_markdown_success_tc131(sample_business_html: str):
    """TC-131: Fetches HTML and converts to clean Markdown with Trafilatura."""
    with respx.mock(base_url="https://barbeariavintage.com.br") as mock:
        mock.get("/").respond(200, html=sample_business_html)

        extractor = WebpageExtractor()
        result = await extractor.fetch_page_markdown("https://barbeariavintage.com.br/")

        assert result.url == "https://barbeariavintage.com.br/"
        assert result.title == "Barbearia Vintage - Cortes Tradicionais"
        assert len(result.markdown) > 0
        assert "Barbearia Vintage" in result.markdown
        assert result.length_bytes > 0


@pytest.mark.asyncio
async def test_fetch_page_markdown_truncates_large_payload_tc191():
    """TC-191: Enforces 1MB size limit and truncates oversized pages."""
    huge_html = "<html><head><title>Big Page</title></head><body>" + ("<p>Text</p>" * 200000) + "</body></html>"
    with respx.mock(base_url="https://huge-page.com") as mock:
        mock.get("/").respond(200, html=huge_html)

        extractor = WebpageExtractor()
        # Test with 50 KB max limit to verify truncation logic
        result = await extractor.fetch_page_markdown("https://huge-page.com/", max_bytes=50000)

        assert result.title == "Big Page"
        assert result.length_bytes < 50000
