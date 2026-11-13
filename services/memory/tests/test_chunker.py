"""Tests for Semantic Markdown Chunker (TC-156)."""

import pytest

from services.chunker import chunk_markdown_by_headers


def test_chunk_markdown_by_headers_tc156():
    """TC-156: Splits markdown cleanly across H1, H2, and H3 header boundaries."""
    doc = (
        "# Seção Principal\n\n"
        "Esta é a introdução do sistema.\n\n"
        "## Subseção 1: Banco de Dados\n\n"
        "Detalhes sobre SQLite WAL mode.\n\n"
        "## Subseção 2: Mensageria\n\n"
        "Topologia RabbitMQ com exchanges duráveis.\n"
    )

    chunks = chunk_markdown_by_headers(doc, max_chunk_chars=1000)

    assert len(chunks) == 3
    assert chunks[0].startswith("# Seção Principal")
    assert chunks[1].startswith("## Subseção 1: Banco de Dados")
    assert chunks[2].startswith("## Subseção 2: Mensageria")


def test_chunk_markdown_handles_single_paragraph():
    """Single short paragraph returns single chunk."""
    doc = "Apenas um texto simples sem cabeçalhos."
    chunks = chunk_markdown_by_headers(doc)
    assert len(chunks) == 1
    assert chunks[0] == doc
