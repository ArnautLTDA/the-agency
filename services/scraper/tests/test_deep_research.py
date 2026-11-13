"""Tests for Deep Research Pipeline (TC-134)."""

import pytest
import respx

from services.deep_research import DeepResearcher
from services.extractor import WebpageExtractor
from services.searxng import SearXNGClient


@pytest.mark.asyncio
async def test_deep_research_pipeline_tc134(sample_business_html: str):
    """TC-134: Executes composed search and markdown extractions into research dossier."""
    with respx.mock(base_url="http://localhost:8888") as mock_searx, \
         respx.mock(base_url="https://barbeariavintage.com.br") as mock_site:

        mock_searx.get("/search").respond(
            200,
            json={
                "results": [
                    {
                        "title": "Barbearia Vintage",
                        "url": "https://barbeariavintage.com.br/",
                        "content": "Site oficial da Barbearia Vintage.",
                    }
                ]
            },
        )
        mock_site.get("/").respond(200, html=sample_business_html)

        researcher = DeepResearcher(
            searxng_client=SearXNGClient(base_url="http://localhost:8888"),
            extractor=WebpageExtractor(),
        )

        dossier = await researcher.research("melhor barbearia pinheiros", top_n=1)

        assert dossier.query == "melhor barbearia pinheiros"
        assert dossier.sources_count == 1
        assert "Barbearia Vintage" in dossier.dossier_markdown
        assert "# Relatório de Pesquisa OSINT" in dossier.dossier_markdown
