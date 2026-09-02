"""Shared Hugging Face embedding model.

Used both while building the index (embedding chunks and by the semantic
chunker itself) and at query time (embedding the user's question), so the
same model/config lives in one place.
"""

from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from core.config import get_settings


@lru_cache
def get_embedding_model() -> HuggingFaceEmbeddings:
    """Return a cached HuggingFace sentence-embedding model."""
    settings = get_settings()
    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
