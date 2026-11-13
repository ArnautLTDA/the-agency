"""Pytest fixtures for Knowledge & Memory Gateway test suite."""

from pathlib import Path
import pytest

from services.embedder import LocalEmbedder
from services.qdrant_service import QdrantVectorService


@pytest.fixture
def embedder():
    return LocalEmbedder(vector_size=384)


@pytest.fixture
def qdrant_service():
    return QdrantVectorService(collection_name="test_agency_knowledge", vector_size=384)


@pytest.fixture
def sample_knowledge_dir(tmp_path: Path):
    """Creates a temporary knowledge directory structure."""
    k_dir = tmp_path / "knowledge"
    (k_dir / "dev").mkdir(parents=True)
    (k_dir / "sales").mkdir(parents=True)

    doc_dev = k_dir / "dev" / "architecture.md"
    doc_dev.write_text(
        "# Arquitetura da Agência\n\nNossos microsserviços usam barramento AMQP e portas isoladas.\n\n## Banco de Dados\n\nUsamos SQLite em modo WAL.\n",
        encoding="utf-8",
    )

    doc_sales = k_dir / "sales" / "pitch.md"
    doc_sales.write_text(
        "# Pitch de Vendas\n\nOferecemos desenvolvimento ágil para pequenas e médias empresas.\n",
        encoding="utf-8",
    )

    return k_dir
