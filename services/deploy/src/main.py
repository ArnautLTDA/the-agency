"""Cloud Deploy Gateway Microservice Main Application (Port :3012)."""

from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI
from loguru import logger

from agency_common.auth import AgencyKeyMiddleware
from config import settings
from mcp_server import create_deploy_mcp_server

mcp_server = create_deploy_mcp_server()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Cloud Deploy Gateway Service starting on port {port}...", port=settings.DEPLOY_PORT)
    yield
    logger.info("Cloud Deploy Gateway Service shutting down...")


app = FastAPI(
    title="Cloud Deploy Gateway Microservice",
    description="Vercel cloud deployments, Supabase provisioning, and Triple Gate enforcement",
    version="0.1.0",
    lifespan=lifespan,
)

# Apply X-Agency-Key middleware (exempting health, docs)
app.add_middleware(
    AgencyKeyMiddleware,
    exempt_paths={
        "/health",
        "/api/v1/health",
        "/api/v1/deploy/health",
        "/docs",
        "/openapi.json",
    },
)


@app.get("/api/v1/health")
@app.get("/api/v1/deploy/health")
async def health_check() -> dict[str, Any]:
    """Healthcheck endpoint for deploy gateway."""
    return {
        "status": "healthy",
        "service": "deploy-cloud-gateway",
        "port": settings.DEPLOY_PORT,
    }


# Mount MCP SSE app at root
sse_app = mcp_server.sse_app()
app.mount("/", sse_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.DEPLOY_PORT, reload=False)
