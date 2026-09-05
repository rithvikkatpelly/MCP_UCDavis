"""Unit tests for tools/rag_tool.py — `search_knowledge_base`.

The embedder, pgvector retriever and cross-encoder reranker are all
monkeypatched, so no model download / database is needed. What's under test is
purely the tool's orchestration and output shaping.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tools import rag_tool

_MISSING = object()


def _doc(text: str, source: str | None = "doc.pdf", page: object = 0):
    meta: dict = {}
    if source is not None:
        meta["source"] = source
    if page is not _MISSING:
        meta["page"] = page
    return SimpleNamespace(page_content=text, metadata=meta)


@pytest.fixture
def wired(monkeypatch):
    """Wire the pipeline to controllable fakes. Returns a dict the test tweaks."""
    state = {
        "candidates": [_doc("a"), _doc("b")],
        "ranked": [(_doc("a", "x.pdf", 2), 1.23456), (_doc("b", "y.pdf", 0), 0.5)],
    }
    monkeypatch.setattr(
        rag_tool, "get_embedding_model", lambda: SimpleNamespace(embed_query=lambda q: [0.0])
    )
    monkeypatch.setattr(rag_tool, "retrieve_candidates", lambda emb: state["candidates"])
    monkeypatch.setattr(rag_tool, "rerank", lambda q, cands: state["ranked"])
    return state


def test_blank_query_short_circuits(wired):
    assert rag_tool.search_knowledge_base("   ") == []


def test_no_candidates_returns_empty(wired):
    wired["candidates"] = []
    assert rag_tool.search_knowledge_base("anything") == []


def test_shapes_passages_with_1indexed_page_and_rounded_score(wired):
    out = rag_tool.search_knowledge_base("q")
    assert out == [
        {"content": "a", "source": "x.pdf", "page": 3, "relevance_score": 1.2346},
        {"content": "b", "source": "y.pdf", "page": 1, "relevance_score": 0.5},
    ]


def test_missing_source_and_nonint_page_are_tolerated(wired):
    wired["ranked"] = [(_doc("c", source=None, page=_MISSING), 0.1)]
    assert rag_tool.search_knowledge_base("q") == [
        {"content": "c", "source": "unknown", "page": None, "relevance_score": 0.1}
    ]


def test_top_n_truncates_ranked_results(wired):
    wired["ranked"] = [(_doc(str(i), "d.pdf", i), float(i)) for i in range(5)]
    out = rag_tool.search_knowledge_base("q", top_n=2)
    assert [r["content"] for r in out] == ["0", "1"]
