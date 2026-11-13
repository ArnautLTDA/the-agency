"""Tests for Lead Profile Enrichment (TC-133)."""

import pytest
import respx

from services.enricher import LeadEnricher
from services.extractor import WebpageExtractor


@pytest.mark.asyncio
async def test_enrich_lead_profile_extracts_contacts_tc133(sample_business_html: str):
    """TC-133: Crawls website and extracts emails, socials, WhatsApp, and CNPJ."""
    with respx.mock(base_url="https://barbeariavintage.com.br") as mock:
        mock.get("/").respond(200, html=sample_business_html)

        enricher = LeadEnricher(extractor=WebpageExtractor())
        profile = await enricher.enrich(
            lead_id="barbearia-vintage",
            website="https://barbeariavintage.com.br/",
            business_name="Barbearia Vintage",
        )

        assert profile.lead_id == "barbearia-vintage"
        assert "contato@barbeariavintage.com.br" in profile.emails
        assert "financeiro@barbeariavintage.com.br" in profile.emails
        assert any("instagram.com/barbearia_vintage_oficial" in ig for ig in profile.instagram_urls)
        assert any("wa.me/5511999998888" in wa for wa in profile.whatsapp_links)
        assert "12.345.678/0001-99" in profile.cnpjs
