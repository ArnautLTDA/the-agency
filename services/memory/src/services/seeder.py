"""Knowledge-as-code seeder with MD5 incremental cache (TC-199, TC-200)."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any
from loguru import logger

from config import settings
from services.chunker import chunk_markdown_by_headers
from services.embedder import LocalEmbedder
from services.qdrant_service import QdrantVectorService


class KnowledgeSeeder:
    """Indexes markdown knowledge base into Qdrant tracking MD5 hashes incrementally."""

    def __init__(
        self,
        qdrant_service: QdrantVectorService,
        embedder: LocalEmbedder,
        knowledge_dir: str = settings.KNOWLEDGE_DIR,
        cache_file: str = settings.HASH_CACHE_FILE,
    ) -> None:
        self.qdrant = qdrant_service
        self.embedder = embedder
        self.knowledge_dir = Path(knowledge_dir)
        self.cache_file = Path(cache_file)

    def _compute_file_md5(self, path: Path) -> str:
        content = path.read_bytes()
        return hashlib.md5(content).hexdigest()

    def _load_cache(self) -> dict[str, str]:
        if self.cache_file.exists():
            try:
                return json.loads(self.cache_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to load hash cache {p}: {err}", p=self.cache_file, err=exc)
        return {}

    def _save_cache(self, cache: dict[str, str]) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to persist hash cache {p}: {err}", p=self.cache_file, err=exc)

    async def seed(self) -> dict[str, int]:
        """Scans knowledge directory and indexes new or modified markdown documents (TC-199, TC-200)."""
        if not self.knowledge_dir.exists():
            logger.warning("Knowledge directory does not exist: {p}", p=self.knowledge_dir)
            return {"indexed": 0, "skipped": 0}

        cache = self._load_cache()
        indexed_count = 0
        skipped_count = 0

        for root, _, files in os.walk(self.knowledge_dir):
            for file_name in files:
                if not file_name.endswith(".md"):
                    continue

                file_path = Path(root) / file_name
                rel_path = str(file_path.relative_to(self.knowledge_dir))
                current_md5 = self._compute_file_md5(file_path)

                # Incremental check (TC-200)
                if cache.get(rel_path) == current_md5:
                    skipped_count += 1
                    continue

                # Parse scope and role from path (e.g. knowledge/dev/arch.md)
                parts = file_path.relative_to(self.knowledge_dir).parts
                role = parts[0] if len(parts) > 1 else "general"

                content = file_path.read_text(encoding="utf-8")
                chunks = chunk_markdown_by_headers(content)

                for idx, chunk in enumerate(chunks):
                    chunk_id = f"doc_{rel_path}_{idx}"
                    vector = self.embedder.embed_text(chunk)
                    await self.qdrant.upsert(
                        memory_id=chunk_id,
                        content=chunk,
                        vector=vector,
                        scope="public",
                        namespace=role,
                        agent_role=role,
                        tags=["knowledge_base", role],
                    )

                cache[rel_path] = current_md5
                indexed_count += 1
                logger.info("Indexed knowledge document: {p} ({c} chunks)", p=rel_path, c=len(chunks))

        self._save_cache(cache)
        return {"indexed": indexed_count, "skipped": skipped_count}
