"""Shared test setup.

The unit tests here are deliberately hermetic: no FRED... (wrong project) —
no Postgres, no HuggingFace model downloads, no network. The RAG pipeline's
heavy pieces (embedder, retriever, reranker) and the DuckDuckGo client are
monkeypatched by the individual tests. `pythonpath = ["."]` in pyproject puts
the repo root on the import path.
"""

from __future__ import annotations

import pytest

from core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """`get_settings()` is `lru_cache`d process-wide; reset it around each test
    so env/monkeypatch changes take effect and don't leak."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
