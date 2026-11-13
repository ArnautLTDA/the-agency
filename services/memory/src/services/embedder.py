"""Local Fast Embedder producing 384-dimensional normalized vectors."""

import hashlib
import re
from typing import Sequence
import numpy as np


class LocalEmbedder:
    """Fast local embedding generator producing deterministic 384-dimensional vectors."""

    def __init__(self, vector_size: int = 384) -> None:
        self.vector_size = vector_size

    def embed_text(self, text: str) -> list[float]:
        """Converts text into normalized vector of dimension vector_size."""
        clean_text = text.lower().strip()
        tokens = re.findall(r"\w+", clean_text)
        if not tokens:
            return [0.0] * self.vector_size

        vec = np.zeros(self.vector_size, dtype=np.float32)

        for token in tokens:
            # Hash token to index and sign
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.vector_size
            sign = 1.0 if (h >> 16) % 2 == 0 else -1.0
            vec[idx] += sign

            # Bigram feature
            for i in range(len(token) - 2):
                tri = token[i : i + 3]
                h_tri = int(hashlib.md5(tri.encode("utf-8")).hexdigest(), 16)
                idx_tri = h_tri % self.vector_size
                sign_tri = 1.0 if (h_tri >> 16) % 2 == 0 else -1.0
                vec[idx_tri] += 0.5 * sign_tri

        # L2 Normalization
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        return vec.tolist()

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Batched embeddings generation."""
        return [self.embed_text(t) for t in texts]
