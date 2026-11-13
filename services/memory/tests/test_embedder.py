"""Tests for Local Embedder."""

import numpy as np
import pytest

from services.embedder import LocalEmbedder


def test_embed_text_dimensions_and_normalization():
    """Generates 384-dimensional vector with unit length L2 norm."""
    embedder = LocalEmbedder(vector_size=384)
    vec = embedder.embed_text("Microsserviços autônomos com FastAPI e Docker")

    assert len(vec) == 384
    norm = float(np.linalg.norm(vec))
    assert abs(norm - 1.0) < 1e-4


def test_embed_empty_text():
    """Empty text produces zero vector."""
    embedder = LocalEmbedder(vector_size=384)
    vec = embedder.embed_text("")
    assert len(vec) == 384
    assert all(v == 0.0 for v in vec)


def test_embed_batch():
    """Generates batch embeddings."""
    embedder = LocalEmbedder(vector_size=384)
    batch = embedder.embed_batch(["Primeiro texto", "Segundo texto"])
    assert len(batch) == 2
    assert len(batch[0]) == 384
    assert len(batch[1]) == 384
