"""Ingestion entry point: run the full RAG pipeline end to end.

    load -> preprocess -> semantically chunk -> embed -> store in Postgres (pgvector)

Usage:
    uv run python -m knowledge_base.build_index
"""

import logging

from sqlalchemy import text

from core.config import get_settings
from db.session import get_engine
from knowledge_base.chunker import chunk_documents
from knowledge_base.embedder import get_embedding_model
from knowledge_base.loader import load_documents
from knowledge_base.preprocessor import preprocess_documents
from knowledge_base.vector_store import build_vector_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def index_row_count() -> int:
    """How many chunks are already in the collection, or 0 if it doesn't exist yet."""
    settings = get_settings()
    query = text(
        "SELECT COUNT(*) FROM langchain_pg_embedding e "
        "JOIN langchain_pg_collection c ON e.collection_id = c.uuid "
        "WHERE c.name = :name"
    )
    try:
        with get_engine().connect() as conn:
            return conn.execute(query, {"name": settings.vector_collection_name}).scalar_one()
    except Exception:
        # Tables don't exist yet on a brand-new database.
        return 0


def main() -> None:
    settings = get_settings()

    raw_documents = load_documents(settings.source_documents_dir)
    clean_documents = preprocess_documents(raw_documents)

    embedding_model = get_embedding_model()
    chunks = chunk_documents(clean_documents, embedding_model)

    build_vector_store(chunks, embedding_model)
    logger.info("Knowledge base build complete.")


def ensure_index_populated() -> None:
    """Run the bulk ingestion once, only if the collection is currently empty.

    Called at MCP server startup so a fresh database gets seeded with the
    bundled UC Davis PDFs automatically, without re-embedding on every
    container restart once it's already populated.
    """
    if index_row_count() > 0:
        logger.info("Vector store already populated; skipping bulk ingestion.")
        return
    logger.info("Vector store is empty; running initial bulk ingestion of bundled PDFs.")
    main()


if __name__ == "__main__":
    main()
