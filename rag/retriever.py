"""Step B: Retrieve candidate chunks from the vector store using the query embedding."""

from langchain_core.documents import Document

from core.config import get_settings
from knowledge_base.embedder import get_embedding_model
from knowledge_base.vector_store import get_vector_store


def retrieve_candidates(query_embedding: list[float]) -> list[Document]:
    """Return the top-k most similar chunks for a pre-computed query embedding."""
    settings = get_settings()
    vector_store = get_vector_store(get_embedding_model())
    return vector_store.similarity_search_by_vector(
        embedding=query_embedding, k=settings.retrieval_top_k
    )
