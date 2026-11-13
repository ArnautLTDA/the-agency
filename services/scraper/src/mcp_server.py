"""Native MCP Server registering OSINT and Web Scraping tools (:3009)."""

from typing import Any
from mcp.server.mcpserver import MCPServer

from services.deep_research import DeepResearcher
from services.enricher import LeadEnricher
from services.extractor import WebpageExtractor
from services.maps_scraper import GoogleMapsScraper
from services.searxng import SearXNGClient
from services.social_scraper import SocialScraper


def create_scraper_mcp_server(
    searxng_client: SearXNGClient | None = None,
    extractor: WebpageExtractor | None = None,
    maps_scraper: GoogleMapsScraper | None = None,
    enricher: LeadEnricher | None = None,
    deep_researcher: DeepResearcher | None = None,
    social_scraper: SocialScraper | None = None,
) -> MCPServer:
    """Builds and configures the osint-scraper-gateway MCP server instance."""
    server = MCPServer(
        name="osint-scraper-gateway",
        version="0.1.0",
        instructions="Official Agency OSINT & Web Scraping Gateway MCP Server",
    )

    searxng = searxng_client or SearXNGClient()
    page_extractor = extractor or WebpageExtractor()
    maps = maps_scraper or GoogleMapsScraper()
    lead_enricher = enricher or LeadEnricher(extractor=page_extractor)
    researcher = deep_researcher or DeepResearcher(searxng_client=searxng, extractor=page_extractor)
    social = social_scraper or SocialScraper()

    @server.tool(
        name="search_web",
        description="Performs an anonymous meta-search via SearXNG on port 8888 (TC-130).",
    )
    async def search_web(query: str, categories: str = "general", limit: int = 5) -> list[dict[str, Any]]:
        results = await searxng.search(query=query, categories=categories, limit=limit)
        return [r.model_dump() for r in results]

    @server.tool(
        name="fetch_page_markdown",
        description="Fetches webpage and converts HTML to clean markdown via Trafilatura with anti-bot headers (TC-131, TC-191).",
    )
    async def fetch_page_markdown(url: str, strip_boilerplate: bool = True) -> dict[str, Any]:
        result = await page_extractor.fetch_page_markdown(url=url, strip_boilerplate=strip_boilerplate)
        return result.model_dump()

    @server.tool(
        name="scrape_google_maps",
        description="Scrapes local businesses from Google Maps with E.164 phone normalization (TC-132, TC-147).",
    )
    async def scrape_google_maps(query: str, city: str, depth: int = 5) -> list[dict[str, Any]]:
        leads = await maps.scrape(query=query, city=city, depth=depth)
        return [l.model_dump() for l in leads]

    @server.tool(
        name="enrich_lead_profile",
        description="Crawls a lead's website to extract emails, WhatsApp links, and Instagram handles (TC-133).",
    )
    async def enrich_lead_profile(lead_id: str, website: str, business_name: str = "") -> dict[str, Any]:
        enriched = await lead_enricher.enrich(lead_id=lead_id, website=website, business_name=business_name)
        return enriched.model_dump()

    @server.tool(
        name="deep_research",
        description="Runs deep multi-source research combining SearXNG and page extractions into a dossier (TC-134).",
    )
    async def deep_research(query: str, top_n: int = 3) -> dict[str, Any]:
        dossier = await researcher.research(query=query, top_n=top_n)
        return dossier.model_dump()

    @server.tool(
        name="scrape_social_profile",
        description="Extracts structured profile data from LinkedIn, Instagram, etc. via session cookies (TC-143, TC-144).",
    )
    async def scrape_social_profile(
        platform: str,
        profile_url: str,
        auth_mode: str = "cookie",
        extract_posts: bool = False,
        posts_limit: int = 5,
    ) -> dict[str, Any]:
        profile = await social.scrape_profile(
            platform=platform,
            profile_url=profile_url,
            auth_mode=auth_mode,
            extract_posts=extract_posts,
            posts_limit=posts_limit,
        )
        return profile.model_dump()

    return server
