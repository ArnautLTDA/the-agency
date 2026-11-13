"""Local Reranker scoring relevance between query and retrieved documents."""

import re
from pydantic import BaseModel


class RerankedItem(BaseModel):
    """Candidate document with cross-encoder relevance score."""

    content: str
    relevance_score: float  # 0.0 to 1.0
    original_score: float
    metadata: dict


class LocalReranker:
    """Evaluates relevance between user query and retrieved candidate documents (TC-152 to TC-154)."""

    def compute_relevance_score(self, query: str, document: str, vector_score: float) -> float:
        """Calculates a normalized cross-score (0.0 to 1.0) assessing semantic match."""
        q_tokens = set(re.findall(r"\w+", query.lower()))
        d_tokens = set(re.findall(r"\w+", document.lower()))

        if not q_tokens or not d_tokens:
            return 0.0

        overlap = len(q_tokens.intersection(d_tokens))
        jaccard = overlap / len(q_tokens.union(d_tokens))
        query_coverage = overlap / len(q_tokens)

        # Blended score: 50% vector similarity + 50% exact query term coverage
        blended = (0.5 * max(0.0, vector_score)) + (0.5 * query_coverage)
        return min(1.0, max(0.0, round(blended, 4)))

    def rerank(self, query: str, candidates: list[dict]) -> list[RerankedItem]:
        """Reranks candidates and assigns normalized relevance scores."""
        reranked: list[RerankedItem] = []
        for item in candidates:
            content = item.get("content", "")
            orig_score = item.get("score", 0.0)
            score = self.compute_relevance_score(query, content, orig_score)
            reranked.append(
                RerankedItem(
                    content=content,
                    relevance_score=score,
                    original_score=orig_score,
                    metadata=item,
                )
            )

        reranked.sort(key=lambda x: x.relevance_score, reverse=True)
        return reranked
