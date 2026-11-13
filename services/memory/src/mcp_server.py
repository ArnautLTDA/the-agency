"""Native MCP Server registering Vector Memory and CRAG tools (:3013)."""

from pathlib import Path
from typing import Any
import uuid
from mcp.server.mcpserver import MCPServer

from services.chunker import chunk_markdown_by_headers
from services.crag_engine import CragEngine
from services.embedder import LocalEmbedder
from services.qdrant_service import QdrantVectorService


def create_memory_mcp_server(
    qdrant_service: QdrantVectorService | None = None,
    embedder: LocalEmbedder | None = None,
    crag_engine: CragEngine | None = None,
) -> MCPServer:
    """Builds and configures the knowledge-memory-gateway MCP server instance."""
    server = MCPServer(
        name="knowledge-memory-gateway",
        version="0.1.0",
        instructions="Official Agency Knowledge & Memory Gateway MCP Server",
    )

    qdrant = qdrant_service or QdrantVectorService()
    emb = embedder or LocalEmbedder()
    crag = crag_engine or CragEngine()

    @server.tool(
        name="recall",
        description="Searches vector memory with multi-tenancy filters and evaluates via Corrective RAG (TC-151, TC-152).",
    )
    async def recall(
        query: str,
        scope: str = "private",
        namespace: str | None = None,
        limit: int = 3,
        allow_web_fallback: bool = True,
    ) -> dict[str, Any]:
        query_vector = emb.embed_text(query)
        candidates = await qdrant.search(
            query_vector=query_vector,
            scope=scope,
            namespace=namespace,
            limit=limit,
        )
        response = await crag.process_retrieval(
            query=query,
            retrieved_items=candidates,
            allow_web_fallback=allow_web_fallback,
        )
        return response.model_dump()

    @server.tool(
        name="remember",
        description="Stores content into vector memory with scope and namespace isolation (TC-157).",
    )
    async def remember(
        content: str,
        scope: str = "private",
        namespace: str | None = None,
        agent_role: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        vector = emb.embed_text(content)
        await qdrant.upsert(
            memory_id=memory_id,
            content=content,
            vector=vector,
            scope=scope,
            namespace=namespace,
            agent_role=agent_role,
            tags=tags or [],
        )
        return {"id": memory_id, "status": "saved"}

    @server.tool(
        name="forget",
        description="Removes a memory item by ID (TC-157).",
    )
    async def forget(memory_id: str) -> dict[str, Any]:
        deleted = await qdrant.delete(memory_id)
        return {"id": memory_id, "deleted": deleted}

    @server.tool(
        name="ingest_document",
        description="Reads a markdown file, chunks it by headers, and indexes chunks into vector memory (TC-156).",
    )
    async def ingest_document(
        file_path: str,
        scope: str = "private",
        namespace: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        p = Path(file_path)
        if not p.exists():
            return {"error": f"File not found: {file_path}", "chunks_count": 0}

        content = p.read_text(encoding="utf-8")
        chunks = chunk_markdown_by_headers(content)

        for idx, chunk in enumerate(chunks):
            cid = f"doc_{p.stem}_{idx}_{uuid.uuid4().hex[:6]}"
            vec = emb.embed_text(chunk)
            await qdrant.upsert(
                memory_id=cid,
                content=chunk,
                vector=vec,
                scope=scope,
                namespace=namespace,
                tags=tags or [],
            )

        return {"file_path": file_path, "chunks_count": len(chunks), "status": "ingested"}

    @server.tool(
        name="get_project_context",
        description="Retrieves all stored context and memory items for a specific client/project slug (TC-203).",
    )
    async def get_project_context(client_slug: str) -> dict[str, Any]:
        items = await qdrant.search(
            query_vector=[0.0] * emb.vector_size,
            namespace=client_slug,
            limit=20,
            score_threshold=-1.0,
        )
        return {
            "client_slug": client_slug,
            "items_count": len(items),
            "items": [it.model_dump() for it in items],
        }

    return server
