"""Smoke test: the server module imports and registers exactly the two tools
the MCP contract promises. Importing `server` does NOT start the server or run
its lifespan (no model load / DB call)."""

from __future__ import annotations

import asyncio

import server


def test_server_identity():
    assert server.mcp.name == "ucdavis-ai"


def test_exactly_the_two_contract_tools_are_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == {"search_uc_davis_ai_docs", "web_search"}


def test_each_tool_exposes_a_query_parameter():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    for name in ("search_uc_davis_ai_docs", "web_search"):
        props = (tools[name].input_schema or {}).get("properties", {})
        assert "query" in props, f"{name} must take a `query` argument"
