"""Browser Gateway Microservice Main Application (Port :3014)."""

from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI
from loguru import logger

from agency_common.auth import AgencyKeyMiddleware
from config import settings
from mcp_server import create_browser_mcp_server

mcp_server = create_browser_mcp_server()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Browser Gateway Service starting on port {port}...", port=settings.BROWSER_PORT)
    yield
    logger.info("Browser Gateway Service shutting down...")


app = FastAPI(
    title="Browser Automation Gateway Microservice",
    description="Playwright headless automation, high-res screenshots and E2E testing",
    version="0.1.0",
    lifespan=lifespan,
)

# Apply X-Agency-Key middleware (exempting health, docs)
app.add_middleware(
    AgencyKeyMiddleware,
    exempt_paths={
        "/health",
        "/api/v1/health",
        "/api/v1/browser/health",
        "/docs",
        "/openapi.json",
    },
)


@app.get("/api/v1/health")
@app.get("/api/v1/browser/health")
async def health_check() -> dict[str, Any]:
    """Healthcheck endpoint for browser gateway."""
    return {
        "status": "healthy",
        "service": "browser-gateway",
        "port": settings.BROWSER_PORT,
    }


# Mount MCP SSE app at root
sse_app = mcp_server.sse_app()
app.mount("/", sse_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.BROWSER_PORT, reload=False)
