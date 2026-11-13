"""Tests for social scraper, cookie injection, and session expiry detection (TC-143, TC-144, TC-220)."""

import httpx
import pytest
import respx

from services.social_scraper import SocialScraper


@pytest.mark.asyncio
async def test_tc143_scrape_social_profile_success():
    """TC-143: Extracts commercial profile with cookie injection."""
    with respx.mock(base_url="https://www.linkedin.com") as mock_li:
        mock_li.get("/in/socio-x").respond(200, text="<html><body><h1>Socio X</h1></body></html>")

        scraper = SocialScraper(storage_dir="/tmp/test_cookies")
        scraper.save_cookies("linkedin", {"li_at": "valid_session_token"})

        profile = await scraper.scrape_profile(
            platform="linkedin",
            profile_url="https://www.linkedin.com/in/socio-x",
            auth_mode="cookie",
            extract_posts=True,
            posts_limit=3,
        )

        assert profile.is_active is True
        assert profile.session_valid is True
        assert profile.handle == "socio-x"
        assert len(profile.posts) > 0


@pytest.mark.asyncio
async def test_tc144_detect_expired_social_session():
    """TC-144: Detects expired session when redirected to login screen."""
    with respx.mock(base_url="https://www.instagram.com") as mock_ig:
        mock_ig.get("/barbearia_vintage/").respond(
            302,
            headers={"Location": "https://www.instagram.com/accounts/login/"},
        )

        scraper = SocialScraper(storage_dir="/tmp/test_cookies")
        scraper.save_cookies("instagram", {"sessionid": "expired_token"})

        profile = await scraper.scrape_profile(
            platform="instagram",
            profile_url="https://www.instagram.com/barbearia_vintage/",
            auth_mode="cookie",
        )

        assert profile.session_valid is False
        assert profile.is_active is False
        assert "Session expired" in (profile.error or "")


@pytest.mark.asyncio
async def test_tc220_canary_cookie_check():
    """TC-220: Performs synthetic canary check on cookies."""
    with respx.mock(base_url="https://www.linkedin.com") as mock_li:
        mock_li.get("/feed/").respond(200, text="ok")

        scraper = SocialScraper(storage_dir="/tmp/test_cookies")
        scraper.save_cookies("linkedin", {"li_at": "active_token"})

        canary = await scraper.check_cookie_canary("linkedin")
        assert canary["valid"] is True
        assert canary["status"] == "active"
