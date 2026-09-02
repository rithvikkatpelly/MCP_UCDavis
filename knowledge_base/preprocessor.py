"""Step 2: Clean and normalize extracted text before chunking.

Raw PDF extraction tends to contain broken hyphenation, stray control
characters, and irregular whitespace. Cleaning this up before semantic
chunking keeps sentence boundaries intact, which the chunker relies on.
"""

import logging
import re
import unicodedata

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# Words split across a line break by a hyphen, e.g. "informa-\ntion".
_HYPHENATED_LINEBREAK_RE = re.compile(r"(\w)-\n(\w)")
# Any remaining single newline (not a paragraph break) is treated as a
# mid-sentence wrap and collapsed to a space.
_SINGLE_LINEBREAK_RE = re.compile(r"(?<!\n)\n(?!\n)")
_MULTI_WHITESPACE_RE = re.compile(r"[ \t]+")
_MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

MIN_DOCUMENT_LENGTH = 20


def clean_text(text: str) -> str:
    """Normalize and de-noise a single block of extracted text."""
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_CHARS_RE.sub("", text)
    text = _HYPHENATED_LINEBREAK_RE.sub(r"\1\2", text)
    text = _SINGLE_LINEBREAK_RE.sub(" ", text)
    text = _MULTI_WHITESPACE_RE.sub(" ", text)
    text = _MULTI_BLANK_LINE_RE.sub("\n\n", text)
    return text.strip()


def preprocess_documents(documents: list[Document]) -> list[Document]:
    """Clean each document's page content and drop near-empty pages."""
    cleaned: list[Document] = []
    for document in documents:
        text = clean_text(document.page_content)
        if len(text) < MIN_DOCUMENT_LENGTH:
            continue
        cleaned.append(Document(page_content=text, metadata=document.metadata))

    logger.info(
        "Preprocessed %d documents -> %d retained after cleaning",
        len(documents),
        len(cleaned),
    )
    return cleaned
