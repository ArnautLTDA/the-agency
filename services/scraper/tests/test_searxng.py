"""Tests for SearXNG Meta-Search Client (TC-130)."""

import pytest
import respx

from services.searxng import SearXNGClient


@pytest.mark.asyncio
async def test_searxng_search_success_tc130():
    """TC-130: Queries SearXNG on :8888 and normalizes search results."""
    with respx.mock(base_url="http://localhost:8888") as mock:
        mock.get("/search").respond(
            200,
            json={
                "results": [
                    {
                        "title": "Barbearias em Pinheiros",
                        "url": "https://guia.sp.gov.br/barbearias",
                        "content": "Lista das melhores barbearias de Pinheiros e região.",
                        "engine": "google",
                        "score": 0.95,
                    },
                    {
                        "title": "Barbearia Vintage Instagram",
                        "url": "https://instagram.com/barbeariavintage",
                        "content": "Perfil oficial da Barbearia Vintage.",
                        "engine": "bing",
                        "score": 0.88,
                    },
                ]
            },
        )

        client = SearXNGClient(base_url="http://localhost:8888")
        items = await client.search("barbearia pinheiros", limit=5)

        assert len(items) == 2
        assert items[0].title == "Barbearias em Pinheiros"
        assert items[0].url == "https://guia.sp.gov.br/barbearias"
        assert items[0].engine == "google"
        assert items[0].score == 0.95


@pytest.mark.asyncio
async def test_searxng_search_error_handling():
    """Handles SearXNG service unreachable or returning 500."""
    with respx.mock(base_url="http://localhost:8888") as mock:
        mock.get("/search").respond(503)

        client = SearXNGClient(base_url="http://localhost:8888")
        with pytest.raises(Exception):
            await client.search("test query")
