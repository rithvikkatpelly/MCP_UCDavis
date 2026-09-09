"""Smoke test: the server module imports and registers exactly the two tools
the MCP contract promises. Importing `server` does NOT start the server or run
its lifespan (no model load / DB call)."""

from __future__ import annotations

import asyncio
import json

import server


def test_server_identity():
    assert server.mcp.name == "ucdavis-ai"


def test_exactly_the_contract_tools_are_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == {"search_uc_davis_ai_docs", "web_search", "fetch_url"}


def test_tools_expose_their_primary_parameter():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    expected_param = {
        "search_uc_davis_ai_docs": "query",
        "web_search": "query",
        "fetch_url": "url",
    }
    for name, param in expected_param.items():
        props = (tools[name].input_schema or {}).get("properties", {})
        assert param in props, f"{name} must take a `{param}` argument"


def _body(response) -> dict:
    return json.loads(response.body)


def test_health_route_reports_service_and_version():
    payload = _body(asyncio.run(server.health(None)))
    assert payload == {
        "status": "ok",
        "service": server.SERVICE_NAME,
        "version": server.SERVICE_VERSION,
    }


def test_root_route_describes_the_mcp_endpoint():
    payload = _body(asyncio.run(server.root(None)))
    assert payload["service"] == server.SERVICE_NAME
    assert payload["mcp_endpoint"] == "/mcp"
    assert payload["repository"].startswith("https://github.com/")
