"""Step 1: Extract raw text from source documents using LangChain document loaders."""

import logging
from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyMuPDFLoader
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


def load_single_file(file_path: Path) -> list[Document]:
    """Load one PDF or DOCX file, dispatching to the right LangChain loader by extension."""
    extension = file_path.suffix.lower()
    if extension == ".pdf":
        loader = PyMuPDFLoader(str(file_path))
    elif extension == ".docx":
        loader = Docx2txtLoader(str(file_path))
    else:
        raise ValueError(f"Unsupported file type: {extension} (expected .pdf or .docx)")

    pages = loader.load()
    for page in pages:
        page.metadata["source"] = file_path.name
        page.metadata.setdefault("page", 0)
    return pages


def load_documents(source_dir: Path) -> list[Document]:
    """Load every PDF in ``source_dir`` into a list of LangChain Documents.

    Each page of every PDF becomes its own Document, with metadata (source
    file name, page number) preserved for downstream citation.
    """
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source documents directory not found: {source_dir}")

    pdf_paths = sorted(source_dir.glob("*.pdf"))
    if not pdf_paths:
        raise FileNotFoundError(f"No PDF files found in: {source_dir}")

    documents: list[Document] = []
    for pdf_path in pdf_paths:
        logger.info("Loading document: %s", pdf_path.name)
        loader = PyMuPDFLoader(str(pdf_path))
        pages = loader.load()
        for page in pages:
            page.metadata["source"] = pdf_path.name
        documents.extend(pages)

    logger.info("Loaded %d pages from %d PDF files", len(documents), len(pdf_paths))
    return documents
