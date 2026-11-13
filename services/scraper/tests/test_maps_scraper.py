"""Tests for Google Maps Lead Scraper and E.164 normalization (TC-132, TC-147, TC-148)."""

import pytest

from services.maps_scraper import GoogleMapsScraper, normalize_to_e164


def test_normalize_to_e164_tc147():
    """TC-147: Normalizes Brazilian local and national phone numbers to E.164 format."""
    # Standard SP cell phone with DDD
    assert normalize_to_e164("(11) 98765-4321") == "+5511987654321"

    # Landline with DDD
    assert normalize_to_e164("11 3456-7890") == "+551134567890"

    # Already with country code 55
    assert normalize_to_e164("+55 11 98765-4321") == "+5511987654321"
    assert normalize_to_e164("5511987654321") == "+5511987654321"

    # Empty string
    assert normalize_to_e164("") == ""


@pytest.mark.asyncio
async def test_scrape_google_maps_returns_structured_leads_tc132():
    """TC-132: Scrapes business leads with rating, address, and E.164 phone."""
    scraper = GoogleMapsScraper()
    leads = await scraper.scrape(query="barbearia", city="São Paulo", depth=3)

    assert len(leads) == 3
    for lead in leads:
        assert lead.niche == "barbearia"
        assert lead.city == "São Paulo"
        assert lead.phone.startswith("+5511")
        assert lead.rating >= 4.0
        assert lead.reviews_count > 0
        assert lead.website.startswith("https://")
        assert "maps.google.com" in lead.google_maps_url
