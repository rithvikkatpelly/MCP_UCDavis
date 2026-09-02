"""Step C: Rerank retrieved candidates with a Hugging Face cross-encoder.

Bi-encoder similarity search (used for retrieval) is fast but approximate.
A cross-encoder scores each (query, passage) pair jointly, giving a much
more accurate relevance ranking for the final top-N selection.
"""

from functools import lru_cache

from langchain_core.documents import Document
from sentence_transformers import CrossEncoder

from core.config import get_settings


@lru_cache
def get_reranker_model() -> CrossEncoder:
    """Return a cached cross-encoder reranking model."""
    settings = get_settings()
    return CrossEncoder(settings.reranker_model_name)


def rerank(question: str, candidates: list[Document]) -> list[tuple[Document, float]]:
    """Score each candidate against the question and return the top-N, sorted by relevance."""
    if not candidates:
        return []

    settings = get_settings()
    model = get_reranker_model()

    pairs = [(question, candidate.page_content) for candidate in candidates]
    scores = model.predict(pairs)

    scored_candidates = sorted(
        zip(candidates, scores), key=lambda item: item[1], reverse=True
    )
    return [
        (document, float(score))
        for document, score in scored_candidates[: settings.rerank_top_n]
    ]
