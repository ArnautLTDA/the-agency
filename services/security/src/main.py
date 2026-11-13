"""Security Audit Gateway Microservice Main Application (Port :3015)."""

from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI
from loguru import logger

from agency_common.auth import AgencyKeyMiddleware
from config import settings
from mcp_server import create_security_mcp_server

mcp_server = create_security_mcp_server()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Security Audit Gateway Service starting on port {port}...", port=settings.SECURITY_GATEWAY_PORT)
    yield
    logger.info("Security Audit Gateway Service shutting down...")


app = FastAPI(
    title="Security Audit Gateway Microservice",
    description="Security scanning and gatekeeper MCP server (SonarQube, Gitleaks, Semgrep, Trivy, Nuclei)",
    version="0.1.0",
    lifespan=lifespan,
)

# Apply X-Agency-Key middleware (exempting health, docs)
app.add_middleware(
    AgencyKeyMiddleware,
    exempt_paths={
        "/health",
        "/api/v1/health",
        "/api/v1/security/health",
        "/docs",
        "/openapi.json",
    },
)


@app.get("/api/v1/health")
@app.get("/api/v1/security/health")
async def health_check() -> dict[str, Any]:
    """Healthcheck endpoint for security gateway."""
    return {
        "status": "healthy",
        "service": "security-audit-gateway",
        "port": settings.SECURITY_GATEWAY_PORT,
    }


# Mount MCP SSE app at root
sse_app = mcp_server.sse_app()
app.mount("/", sse_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.SECURITY_GATEWAY_PORT, reload=False)
