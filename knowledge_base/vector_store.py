"""Step 4: Persist chunk embeddings in Postgres (pgvector).

Backed by the same Cloud SQL Postgres instance as the rest of the app's
data, rather than a local Chroma file — Cloud Run containers have ephemeral
local disks, so a file-based store can't survive redeploys or scale-out, and
can't be durably updated by the admin document-upload feature at runtime.
"""

import logging

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector

from core.config import get_settings

logger = logging.getLogger(__name__)

# Dimensionality of sentence-transformers/all-MiniLM-L6-v2. Update this if
# EMBEDDING_MODEL_NAME ever changes to a model with a different output size.
EMBEDDING_DIMENSIONS = 384


def get_vector_store(embedding_model: HuggingFaceEmbeddings) -> PGVector:
    """Return a handle to the pgvector-backed collection.

    The `vector` extension is created once, manually, with superuser
    privileges when the database is provisioned (see DEPLOYMENT.md) — the
    app's own DB user isn't granted CREATE EXTENSION, hence create_extension=False.
    """
    settings = get_settings()
    return PGVector(
        embeddings=embedding_model,
        connection=settings.sqlalchemy_database_url,
        collection_name=settings.vector_collection_name,
        embedding_length=EMBEDDING_DIMENSIONS,
        create_extension=False,
        use_jsonb=True,
    )


def build_vector_store(chunks: list[Document], embedding_model: HuggingFaceEmbeddings) -> PGVector:
    """Embed ``chunks`` and persist them, replacing whatever's already in the collection.

    Used for the initial bulk ingestion of the bundled source PDFs. Admin
    uploads of additional documents use `add_chunks` instead, which doesn't
    wipe the existing collection.
    """
    vector_store = get_vector_store(embedding_model)
    # Drop and redeclare the collection so repeated bulk-ingestion runs don't
    # accumulate duplicate chunks.
    vector_store.delete_collection()
    vector_store.create_collection()
    vector_store.add_documents(chunks)

    logger.info(
        "Persisted %d chunks to Postgres collection '%s'",
        len(chunks),
        get_settings().vector_collection_name,
    )
    return vector_store


def add_chunks(chunks: list[Document], embedding_model: HuggingFaceEmbeddings) -> None:
    """Add chunks to the existing collection without touching what's already there."""
    vector_store = get_vector_store(embedding_model)
    vector_store.add_documents(chunks)
    logger.info("Added %d chunks to Postgres collection", len(chunks))


def store_precomputed_embeddings(
    chunks: list[Document], embeddings: list[list[float]], embedding_model: HuggingFaceEmbeddings
) -> None:
    """Insert chunks whose embeddings were already computed (see embedder step),
    instead of recomputing them — keeps the embed and store pipeline stages
    genuinely separate work rather than one hiding inside the other."""
    vector_store = get_vector_store(embedding_model)
    vector_store.add_embeddings(
        texts=[chunk.page_content for chunk in chunks],
        embeddings=embeddings,
        metadatas=[chunk.metadata for chunk in chunks],
    )
    logger.info("Stored %d precomputed embeddings in Postgres collection", len(chunks))
