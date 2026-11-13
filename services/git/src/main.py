"""Git & GitHub VCS Gateway Microservice Main Application (Port :3011)."""

from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI
from loguru import logger

from agency_common.auth import AgencyKeyMiddleware
from config import settings
from mcp_server import create_git_mcp_server

mcp_server = create_git_mcp_server()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Git VCS Gateway Service starting on port {port}...", port=settings.GIT_PORT)
    yield
    logger.info("Git VCS Gateway Service shutting down...")


app = FastAPI(
    title="Git & GitHub VCS Gateway Microservice",
    description="Git operations, Conventional Commits, Granular Agent Attribution, and GitHub REST v3",
    version="0.1.0",
    lifespan=lifespan,
)

# Enforce X-Agency-Key header authentication across all endpoints
app.add_middleware(
    AgencyKeyMiddleware,
    exempt_paths={
        "/health",
        "/api/v1/health",
        "/api/v1/git/health",
        "/docs",
        "/openapi.json",
    },
)


@app.get("/api/v1/health")
@app.get("/api/v1/git/health")
async def health_check() -> dict[str, Any]:
    """Healthcheck endpoint reporting status of git CLI and GitHub API connectivity."""
    return {
        "status": "healthy",
        "service": "git-vcs-gateway",
        "port": settings.GIT_PORT,
    }


# Mount MCP SSE transport at root
sse_app = mcp_server.sse_app()
app.mount("/", sse_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.GIT_PORT, reload=False)
