"""`fetch_url` tool — fetch a public web page (or PDF) and return its readable text.

This server is **public and unauthenticated**, so this tool is deliberately
conservative about what it will fetch:

  * only ``http`` / ``https`` schemes
  * the host must resolve to a *public* IP — loopback, private (RFC1918),
    link-local (incl. ``169.254.169.254`` cloud metadata) and reserved ranges
    are refused, and every redirect hop is re-validated
  * responses are size- and time-bounded, and the extracted text is truncated

HTML goes through readability extraction (``trafilatura``); PDFs are read with
PyMuPDF (already a project dependency); ``text/*`` is returned as-is.

Failures are returned as ``{"error": "..."}`` — never raised — mirroring the
``web_search`` tool.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOST_SUFFIXES = (".internal", ".local", ".localdomain")
_BLOCKED_HOST_NAMES = {"localhost", "metadata.google.internal", "metadata"}
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.IGNORECASE | re.DOTALL)


@dataclass
class _Fetched:
    final_url: str
    content_type: str  # lower-cased, no charset parameter
    body: bytes


def _is_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_url(raw: str) -> str | None:
    """Return an error string if ``raw`` must not be fetched, else ``None``."""
    parsed = urlparse(raw.strip())
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return f"Unsupported URL scheme '{parsed.scheme or '(none)'}'. Only http and https."
    host = (parsed.hostname or "").lower()
    if not host:
        return "URL has no host."
    if host in _BLOCKED_HOST_NAMES or host.endswith(_BLOCKED_HOST_SUFFIXES):
        return f"Refusing to fetch internal host '{host}'."
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        return f"Could not resolve host '{host}': {exc}"
    ips = {info[4][0] for info in infos}
    if not ips:
        return f"Host '{host}' did not resolve to any address."
    bad = sorted(ip for ip in ips if not _is_public_ip(ip))
    if bad:
        return f"Host '{host}' resolves to a non-public address ({', '.join(bad)}); refused."
    return None


def _download(url: str) -> _Fetched | dict:
    """Fetch ``url`` with manual, re-validated redirect handling. Returns a
    `_Fetched` or an ``{"error": ...}`` dict. This is the only function that
    touches the network — tests monkeypatch it."""
    s = get_settings()
    headers = {
        "User-Agent": s.fetch_url_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.9,*/*;q=0.8",
    }
    current = url
    with httpx.Client(
        follow_redirects=False,
        timeout=s.fetch_url_timeout_seconds,
        headers=headers,
    ) as client:
        for _hop in range(s.fetch_url_max_redirects + 1):
            err = _validate_url(current)
            if err:
                return {"error": err}
            try:
                with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            return {"error": "Redirect response without a Location header."}
                        current = urljoin(current, location)
                        continue
                    if resp.status_code >= 400:
                        return {"error": f"HTTP {resp.status_code} fetching {current}"}
                    raw_ct = resp.headers.get("content-type", "")
                    content_type = raw_ct.split(";")[0].strip().lower()
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > s.fetch_url_max_bytes:
                            return {
                                "error": f"Response exceeds {s.fetch_url_max_bytes} bytes; aborted."
                            }
                        chunks.append(chunk)
                    return _Fetched(str(resp.url), content_type, b"".join(chunks))
            except httpx.HTTPError as exc:
                return {"error": f"Fetch failed: {exc}"}
    return {"error": f"Too many redirects (>{s.fetch_url_max_redirects})."}


def _extract_html(html: str, url: str) -> tuple[str, str]:
    """(title, text) from an HTML document."""
    title = ""
    m = _TITLE_RE.search(html)
    if m:
        title = _TAG_RE.sub("", m.group(1)).strip()

    try:
        import trafilatura

        extracted = trafilatura.extract(
            html, output_format="json", include_comments=False, include_tables=True, url=url
        )
        if extracted:
            data = json.loads(extracted)
            return (data.get("title") or title, (data.get("text") or "").strip())
    except Exception as exc:  # extractor bug / odd input — fall back, don't fail
        logger.debug("trafilatura extraction failed for %s: %s", url, exc)

    stripped = _SCRIPT_STYLE_RE.sub(" ", html)
    text = re.sub(r"\s+\n", "\n", _TAG_RE.sub(" ", stripped))
    return title, re.sub(r"[ \t]{2,}", " ", text).strip()


def _extract_pdf(body: bytes, url: str) -> tuple[str, str]:
    import fitz  # PyMuPDF, already a dependency

    with fitz.open(stream=body, filetype="pdf") as doc:
        title = (doc.metadata or {}).get("title") or ""
        text = "\n\n".join(page.get_text().strip() for page in doc)
    return title.strip(), text.strip()


def fetch_url(url: str) -> dict:
    """Fetch a public http(s) URL and return its main readable text.

    Args:
        url: An ``http://`` or ``https://`` URL. HTML pages and PDFs are
            supported; the host must resolve to a public address.

    Returns:
        On success a dict with:
          - ``url``: the final URL after redirects
          - ``title``: page/document title (may be empty)
          - ``content_type``: e.g. ``text/html`` or ``application/pdf``
          - ``text``: extracted readable text (truncated — see ``truncated``)
          - ``chars``: length of ``text`` returned
          - ``truncated``: whether the text was cut to the configured limit
        On failure: ``{"error": "..."}``.
    """
    if not url or not url.strip():
        return {"error": "No URL provided."}

    fetched = _download(url)
    if isinstance(fetched, dict):  # error
        return fetched

    ct = fetched.content_type
    final_url = fetched.final_url
    is_pdf = (
        ct == "application/pdf"
        or fetched.body[:5] == b"%PDF-"
        or final_url.lower().endswith(".pdf")
    )
    _HTML_CTS = {"text/html", "application/xhtml+xml", "application/xml", "text/xml", ""}
    try:
        if is_pdf:
            title, text = _extract_pdf(fetched.body, final_url)
            ct = "application/pdf"
        elif ct.startswith("text/") and ct != "text/html":
            title, text = "", fetched.body.decode("utf-8", errors="replace").strip()
        elif ct in _HTML_CTS:
            body = fetched.body.decode("utf-8", errors="replace")
            title, text = _extract_html(body, final_url)
        else:
            return {"error": f"Unsupported content type '{ct}'. Only HTML, plain text and PDF."}
    except Exception as exc:
        logger.warning("Extraction failed for %s: %s", final_url, exc)
        return {"error": f"Could not extract text: {exc}"}

    if not text:
        return {"error": "Fetched the page but found no extractable text."}

    limit = get_settings().fetch_url_max_chars
    truncated = len(text) > limit
    return {
        "url": fetched.final_url,
        "title": title,
        "content_type": ct,
        "text": text[:limit],
        "chars": min(len(text), limit),
        "truncated": truncated,
    }
