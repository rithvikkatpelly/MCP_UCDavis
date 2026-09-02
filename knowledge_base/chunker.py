"""Step 3: Semantic chunking.

Splits preprocessed documents into chunks based on embedding-similarity
breakpoints (LangChain's SemanticChunker) rather than a fixed character
count, so each chunk stays topically coherent.
"""

import logging

from langchain_core.documents import Document
from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings

from core.config import get_settings

logger = logging.getLogger(__name__)


def chunk_documents(
    documents: list[Document], embedding_model: HuggingFaceEmbeddings
) -> list[Document]:
    """Split documents into semantically coherent chunks."""
    settings = get_settings()

    splitter = SemanticChunker(
        embeddings=embedding_model,
        buffer_size=settings.semantic_chunker_buffer_size,
        breakpoint_threshold_type=settings.semantic_chunker_breakpoint_threshold_type,
        min_chunk_size=settings.semantic_chunker_min_chunk_size,
        add_start_index=True,
    )
    chunks = splitter.split_documents(documents)

    logger.info("Split %d documents into %d semantic chunks", len(documents), len(chunks))
    return chunks
