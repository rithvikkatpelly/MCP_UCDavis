"""Unit tests for tools/web_search.py — the DuckDuckGo-backed `web_search` tool.

The `ddgs` client is monkeypatched, so these never hit the network.
"""

from __future__ import annotations

import pytest

from tools import web_search as web_search_mod
from tools.web_search import web_search

_ROWS = [
    {"title": "Aggie AI", "href": "https://iet.ucdavis.edu/aggie-ai", "body": "AI at UC Davis."},
    {"title": "AI Guidance", "href": "https://iet.ucdavis.edu/aggie-ai/ai-guidance", "body": "..."},
]


class _FakeDDGS:
    """Stands in for `ddgs.DDGS` — a context manager exposing `.text()`."""

    last_kwargs: dict = {}
    rows: list[dict] = _ROWS
    raises: Exception | None = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def text(self, query, **kwargs):
        _FakeDDGS.last_kwargs = {"query": query, **kwargs}
        if _FakeDDGS.raises is not None:
            raise _FakeDDGS.raises
        return list(_FakeDDGS.rows)


@pytest.fixture(autouse=True)
def _patch_ddgs(monkeypatch):
    _FakeDDGS.last_kwargs = {}
    _FakeDDGS.rows = _ROWS
    _FakeDDGS.raises = None
    monkeypatch.setattr(web_search_mod, "DDGS", _FakeDDGS)


def test_blank_query_returns_empty_without_calling_ddgs():
    assert web_search("   ") == []
    assert _FakeDDGS.last_kwargs == {}


def test_maps_ddgs_fields_to_stable_shape():
    out = web_search("uc davis ai")
    assert out == [
        {
            "title": "Aggie AI",
            "url": "https://iet.ucdavis.edu/aggie-ai",
            "snippet": "AI at UC Davis.",
        },
        {
            "title": "AI Guidance",
            "url": "https://iet.ucdavis.edu/aggie-ai/ai-guidance",
            "snippet": "...",
        },
    ]


def test_missing_row_keys_become_empty_strings():
    _FakeDDGS.rows = [{"href": "https://example.com"}]
    assert web_search("x") == [{"title": "", "url": "https://example.com", "snippet": ""}]


def test_explicit_max_results_is_passed_through():
    web_search("x", max_results=3)
    assert _FakeDDGS.last_kwargs["max_results"] == 3


def test_default_max_results_comes_from_settings(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_MAX_RESULTS", "7")
    web_search("x")
    assert _FakeDDGS.last_kwargs["max_results"] == 7


def test_upstream_error_is_returned_as_structured_row_not_raised():
    _FakeDDGS.raises = RuntimeError("rate limited")
    out = web_search("x")
    assert len(out) == 1 and out[0]["error"].startswith("Web search failed")
    assert "rate limited" in out[0]["error"]
