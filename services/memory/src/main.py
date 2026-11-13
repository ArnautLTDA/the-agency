"""Knowledge & Memory Gateway Main Application (Port :3013)."""

from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI
from loguru import logger

from agency_common.auth import AgencyKeyMiddleware
from config import settings
from mcp_server import create_memory_mcp_server
from services.embedder import LocalEmbedder
from services.qdrant_service import QdrantVectorService
from services.seeder import KnowledgeSeeder

embedder = LocalEmbedder()
qdrant_service = QdrantVectorService()
seeder = KnowledgeSeeder(qdrant_service=qdrant_service, embedder=embedder)
mcp_server = create_memory_mcp_server(qdrant_service=qdrant_service, embedder=embedder)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Knowledge & Memory Gateway Service starting on port {port}...", port=settings.MEMORY_PORT)
    # Perform initial incremental knowledge seeding
    try:
        res = await seeder.seed()
        logger.info("Knowledge seeder completed on boot: {r}", r=res)
    except Exception as exc:
        logger.warning("Knowledge boot seeding error: {err}", err=exc)

    yield
    logger.info("Knowledge & Memory Gateway Service shutting down...")


app = FastAPI(
    title="Knowledge & Memory Gateway Microservice",
    description="Vector memory (Qdrant), fast embeddings, and Corrective RAG (CRAG)",
    version="0.1.0",
    lifespan=lifespan,
)

# Apply X-Agency-Key middleware (exempting health, docs)
app.add_middleware(
    AgencyKeyMiddleware,
    exempt_paths={
        "/health",
        "/api/v1/health",
        "/api/v1/memory/health",
        "/docs",
        "/openapi.json",
    },
)


@app.get("/api/v1/health")
@app.get("/api/v1/memory/health")
async def health_check() -> dict[str, Any]:
    """Healthcheck endpoint for memory gateway."""
    return {
        "status": "healthy",
        "service": "knowledge-memory-gateway",
        "port": settings.MEMORY_PORT,
    }


# Mount MCP SSE app at root
sse_app = mcp_server.sse_app()
app.mount("/", sse_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.MEMORY_PORT, reload=False)
