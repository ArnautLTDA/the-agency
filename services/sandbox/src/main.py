"""Workspace Sandbox Service Main Application (Port :3010)."""

import os
from contextlib import asynccontextmanager
from typing import Any

import docker
from fastapi import FastAPI
from loguru import logger

from agency_common.auth import AgencyKeyMiddleware
from mcp_server import create_sandbox_mcp_server


mcp_server = create_sandbox_mcp_server()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Workspace Sandbox Service starting on port 3010...")
    yield
    logger.info("Workspace Sandbox Service shutting down...")


app = FastAPI(
    title="Workspace Sandbox Service",
    description="MCP Server exposing filesystem and Docker DooD sandbox execution",
    version="0.1.0",
    lifespan=lifespan,
)

# Enforce X-Agency-Key on all internal routes
app.add_middleware(AgencyKeyMiddleware)


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    """Healthcheck endpoint reporting Docker daemon status and workspace root."""
    docker_status = "unavailable"
    try:
        client = docker.from_env()
        client.ping()
        docker_status = "connected"
    except Exception as e:
        docker_status = f"error: {str(e)}"

    return {
        "status": "healthy" if docker_status == "connected" else "degraded",
        "service": "workspace-sandbox-service",
        "port": 3010,
        "docker_status": docker_status,
        "workspaces_root": os.environ.get("WORKSPACES_ROOT", "workspaces/clients"),
    }


# Mount the MCP SSE application exposing /sse and /messages
app.mount("", mcp_server.sse_app())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3010, reload=True)
