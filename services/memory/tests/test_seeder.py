"""Tests for Knowledge-as-code seeder and MD5 caching (TC-199, TC-200)."""

from pathlib import Path
import pytest

from services.embedder import LocalEmbedder
from services.qdrant_service import QdrantVectorService
from services.seeder import KnowledgeSeeder


@pytest.mark.asyncio
async def test_seeder_scans_and_indexes_knowledge_dir_tc199_tc200(
    qdrant_service: QdrantVectorService,
    embedder: LocalEmbedder,
    sample_knowledge_dir: Path,
    tmp_path: Path,
):
    """TC-199, TC-200: Indexes knowledge base on initial run, and skips unchanged files on subsequent run."""
    cache_file = tmp_path / "cache.json"
    seeder = KnowledgeSeeder(
        qdrant_service=qdrant_service,
        embedder=embedder,
        knowledge_dir=str(sample_knowledge_dir),
        cache_file=str(cache_file),
    )

    # First run: should index both files
    res1 = await seeder.seed()
    assert res1["indexed"] == 2
    assert res1["skipped"] == 0

    # Second run without changes: should skip both files (TC-200)
    res2 = await seeder.seed()
    assert res2["indexed"] == 0
    assert res2["skipped"] == 2

    # Modify one file: should re-index only the modified file
    modified_file = sample_knowledge_dir / "dev" / "architecture.md"
    modified_file.write_text("# Arquitetura Atualizada\n\nNova versão 2026.\n", encoding="utf-8")

    res3 = await seeder.seed()
    assert res3["indexed"] == 1
    assert res3["skipped"] == 1
