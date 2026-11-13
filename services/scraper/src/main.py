"""OSINT Scraper Gateway Main Application (Port :3009)."""

from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI
from loguru import logger

from agency_common.auth import AgencyKeyMiddleware
from config import settings
from mcp_server import create_scraper_mcp_server
from services.social_scraper import SocialScraper

mcp_server = create_scraper_mcp_server()
social_scraper = SocialScraper()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("OSINT Scraper Gateway Service starting on port {port}...", port=settings.SCRAPER_PORT)
    yield
    logger.info("OSINT Scraper Gateway Service shutting down...")


app = FastAPI(
    title="OSINT Scraper Gateway Microservice",
    description="SearXNG meta-search, Trafilatura markdown extractor, and Google Maps lead scraper",
    version="0.1.0",
    lifespan=lifespan,
)

# Apply X-Agency-Key middleware (exempting health, docs)
app.add_middleware(
    AgencyKeyMiddleware,
    exempt_paths={
        "/health",
        "/api/v1/health",
        "/api/v1/scraper/health",
        "/docs",
        "/openapi.json",
    },
)


@app.get("/api/v1/health")
@app.get("/api/v1/scraper/health")
async def health_check() -> dict[str, Any]:
    """Healthcheck endpoint for scraper gateway."""
    return {
        "status": "healthy",
        "service": "osint-scraper-gateway",
        "port": settings.SCRAPER_PORT,
    }


@app.post("/api/v1/session/cookies")
async def update_session_cookies(payload: dict[str, Any]) -> dict[str, Any]:
    """Updates session cookies in storage with hot reload (Section 6.2, 6.5)."""
    platform = payload.get("platform", "").lower()
    cookies = payload.get("cookies", {})
    if not platform or not cookies:
        return {"status": "error", "message": "platform and cookies are required"}

    social_scraper.save_cookies(platform, cookies)
    canary = await social_scraper.check_cookie_canary(platform)
    return {"status": "saved", "platform": platform, "canary": canary}


# Mount MCP SSE app at root
sse_app = mcp_server.sse_app()
app.mount("/", sse_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.SCRAPER_PORT, reload=False)
