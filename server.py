"""MCP server exposing the UC Davis AI knowledge base + web search.

Two tools:
  - search_uc_davis_ai_docs : RAG retrieval over the bundled UC Davis AI
    policy/guidance PDFs (pgvector similarity search + cross-encoder rerank).
  - web_search               : DuckDuckGo web search (no API key).

Transport: Streamable HTTP, so remote AI applications can connect over the
network. On Cloud Run the MCP endpoint is  https://<service-url>/mcp

Run locally:
    uv run python server.py
"""

import logging
import os
from contextlib import asynccontextmanager

import anyio
from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from core.config import get_settings
from knowledge_base.build_index import ensure_index_populated
from knowledge_base.embedder import get_embedding_model
from rag.reranker import get_reranker_model
from tools.rag_tool import search_knowledge_base
from tools.web_search import web_search as run_web_search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_server: MCPServer):
    """Warm the model caches and (optionally) seed the vector store on startup."""
    settings = get_settings()

    await anyio.to_thread.run_sync(get_embedding_model)
    await anyio.to_thread.run_sync(get_reranker_model)

    if settings.seed_on_startup:
        try:
            await anyio.to_thread.run_sync(ensure_index_populated)
        except Exception:
            logger.exception(
                "Could not verify/populate the vector store at startup; "
                "search_uc_davis_ai_docs will fail until this is resolved."
            )
    yield


mcp = MCPServer(
    "ucdavis-ai",
    title="UC Davis AI Knowledge Base",
    instructions=(
        "Tools for answering questions about UC Davis's AI policy and guidance. "
        "Use search_uc_davis_ai_docs to retrieve grounding passages from the "
        "official UC Davis AI documents (cite the returned source/page). Use "
        "web_search for anything outside those documents or for more recent "
        "information."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@mcp.tool(
    name="search_uc_davis_ai_docs",
    title="Search UC Davis AI documents",
    description=(
        "Semantic search over UC Davis's official AI policy and guidance "
        "documents (AI Council report, AI Steering Committee report, academic "
        "integrity guidance, GenAI literacy framework, and more). Returns the "
        "most relevant passages with their source document and page number so "
        "you can cite them. Does NOT synthesize an answer — read the passages "
        "and answer from them."
    ),
)
async def search_uc_davis_ai_docs(query: str, top_n: int = 5) -> list[dict]:
    """Retrieve relevant passages from the UC Davis AI knowledge base.

    Args:
        query: A natural-language question or search phrase.
        top_n: Number of passages to return (1-10, default 5).
    """
    top_n = max(1, min(top_n, 10))
    return await anyio.to_thread.run_sync(search_knowledge_base, query, top_n)


@mcp.tool(
    name="web_search",
    title="Web search",
    description=(
        "Search the public web via DuckDuckGo. Returns a list of results with "
        "title, URL, and a short snippet. Use for information not covered by "
        "the UC Davis AI documents, or for more recent developments."
    ),
)
async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web.

    Args:
        query: The search query.
        max_results: Maximum number of results (1-10, default 5).
    """
    max_results = max(1, min(max_results, 10))
    return await anyio.to_thread.run_sync(run_web_search, query, max_results)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    settings = get_settings()
    port = int(os.environ.get("PORT", settings.mcp_server_port))
    host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else settings.mcp_server_host)
    logger.info("Starting MCP server on %s:%s (endpoint /mcp)", host, port)
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        stateless_http=True,
        json_response=True,
    )
