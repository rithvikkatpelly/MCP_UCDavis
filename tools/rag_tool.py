"""RAG retrieval tool: semantic search over the UC Davis AI knowledge base.

Pipeline: embed query -> pgvector similarity search (top_k candidates) ->
cross-encoder rerank -> return the top N passages with citations.

Deliberately stops at retrieval + reranking: the calling AI application's
own model synthesizes the final answer from these passages, so this server
needs no LLM API key.
"""

import logging

from rag.reranker import rerank
from rag.retriever import retrieve_candidates
from knowledge_base.embedder import get_embedding_model

logger = logging.getLogger(__name__)


def search_knowledge_base(query: str, top_n: int | None = None) -> list[dict]:
    """Return the most relevant passages from the UC Davis AI documents.

    Args:
        query: A natural-language question or search phrase.
        top_n: How many passages to return (defaults to the server's
            configured rerank_top_n, usually 5).

    Returns:
        A list of passages, most relevant first, each a dict with:
          - content: the passage text
          - source: originating document filename
          - page: 1-indexed page number (or None)
          - relevance_score: cross-encoder score (higher is more relevant)
    """
    query = query.strip()
    if not query:
        return []

    embedding = get_embedding_model().embed_query(query)
    candidates = retrieve_candidates(embedding)
    if not candidates:
        return []

    ranked = rerank(query, candidates)
    if top_n is not None:
        ranked = ranked[: max(1, top_n)]

    results = []
    for document, score in ranked:
        page = document.metadata.get("page")
        results.append(
            {
                "content": document.page_content,
                "source": document.metadata.get("source", "unknown"),
                "page": (page + 1) if isinstance(page, int) else None,
                "relevance_score": round(float(score), 4),
            }
        )
    return results
