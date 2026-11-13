# Knowledge & Vector Memory Gateway (Port :3013)

Microservice for persistent vector storage and Corrective RAG (CRAG):
- Qdrant Vector Store (:6333) with multi-tenancy payload isolation
- Local fast embeddings and cross-encoder reranker
- Corrective RAG (CRAG) with automatic web fallback to SearXNG
- Semantic Markdown header chunking
- Knowledge-as-code seeder with MD5 incremental cache
- Native MCP Server exposing tools
