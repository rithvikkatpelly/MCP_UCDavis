"""Web search tool, backed by DuckDuckGo (no API key required).

Returns lightweight result rows (title, url, snippet). Fetching and parsing
full page content is left to the caller.
"""

import logging

from ddgs import DDGS

from core.config import get_settings

logger = logging.getLogger(__name__)


def web_search(query: str, max_results: int | None = None) -> list[dict]:
    """Search the public web via DuckDuckGo.

    Args:
        query: The search query.
        max_results: Maximum number of results (defaults to the server's
            configured web_search_max_results, usually 5).

    Returns:
        A list of results, each a dict with:
          - title: page title
          - url: page URL
          - snippet: a short text excerpt
    """
    query = query.strip()
    if not query:
        return []

    settings = get_settings()
    limit = max_results or settings.web_search_max_results

    try:
        with DDGS() as ddgs:
            rows = ddgs.text(
                query,
                region=settings.web_search_region,
                max_results=limit,
            )
    except Exception as exc:  # network / rate-limit / upstream errors
        logger.warning("Web search failed: %s", exc)
        return [{"error": f"Web search failed: {exc}"}]

    return [
        {
            "title": row.get("title", ""),
            "url": row.get("href", ""),
            "snippet": row.get("body", ""),
        }
        for row in rows
    ]
