"""Unit tests for tools/fetch_url.py.

`_download` (the only function that touches the network) is monkeypatched, so
these are hermetic. The SSRF-guard tests that use literal IPs / blocked names
hit `_validate_url` directly and need no network either.
"""

from __future__ import annotations

import pytest

from tools import fetch_url as mod
from tools.fetch_url import _Fetched, _validate_url, fetch_url

_HTML = b"""
<html><head><title>  AI Guidance | UC Davis  </title></head>
<body>
  <nav>home about</nav>
  <script>tracker()</script>
  <article><h1>AI Guidance</h1>
  <p>Use generative AI tools responsibly and follow the guidelines below.</p>
  <p>Do not enter protected data into public tools.</p></article>
  <footer>copyright</footer>
</body></html>
"""

_MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 20 100 Td (Hello policy) Tj ET\nendstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF"
)


# --- SSRF guard -------------------------------------------------------------


@pytest.mark.parametrize(
    "url, needle",
    [
        ("ftp://example.com/x", "scheme"),
        ("file:///etc/passwd", "scheme"),
        ("http://localhost/admin", "internal host"),
        ("http://metadata.google.internal/", "internal host"),
        ("http://foo.internal/", "internal host"),
        ("http://169.254.169.254/latest/meta-data/", "non-public"),
        ("http://127.0.0.1:8080/", "non-public"),
        ("http://10.1.2.3/", "non-public"),
        ("http://192.168.0.1/", "non-public"),
        ("http://[::1]/", "non-public"),
        ("https:///nohost", "no host"),
    ],
)
def test_validate_url_rejects_unsafe_targets(url, needle):
    err = _validate_url(url)
    assert err is not None and needle in err


def test_validate_url_allows_a_public_host(monkeypatch):
    monkeypatch.setattr(
        mod.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))]
    )
    assert _validate_url("https://example.com/page") is None


# --- fetch_url end to end (network stubbed) --------------------------------


@pytest.fixture
def download(monkeypatch):
    box = {"result": _Fetched("https://example.com/p", "text/html", _HTML)}
    monkeypatch.setattr(mod, "_download", lambda url: box["result"])
    return box


def test_blank_url_is_rejected():
    assert fetch_url("  ")["error"]


def test_download_error_is_passed_through(download):
    download["result"] = {"error": "HTTP 404 fetching https://example.com/x"}
    assert fetch_url("https://example.com/x") == {
        "error": "HTTP 404 fetching https://example.com/x"
    }


def test_html_is_reduced_to_readable_text(download):
    out = fetch_url("https://example.com/p")
    assert out["content_type"] == "text/html"
    assert "AI Guidance" in out["title"]
    assert "responsibly" in out["text"]
    assert "tracker()" not in out["text"] and "<p>" not in out["text"]
    assert out["truncated"] is False
    assert out["chars"] == len(out["text"])


def test_text_is_truncated_to_the_configured_limit(download, monkeypatch):
    monkeypatch.setenv("FETCH_URL_MAX_CHARS", "40")
    download["result"] = _Fetched("https://example.com/big", "text/plain", b"x" * 500)
    out = fetch_url("https://example.com/big")
    assert out["truncated"] is True and out["chars"] == 40 and len(out["text"]) == 40


def test_pdf_bodies_are_read_with_pymupdf(download):
    download["result"] = _Fetched("https://example.com/doc.pdf", "application/pdf", _MINIMAL_PDF)
    out = fetch_url("https://example.com/doc.pdf")
    assert out["content_type"] == "application/pdf"
    assert "Hello policy" in out["text"]


def test_unsupported_content_type_is_reported(download):
    download["result"] = _Fetched("https://example.com/a.png", "image/png", b"\x89PNG\r\n")
    assert "Unsupported content type" in fetch_url("https://example.com/a.png")["error"]


def test_page_with_no_text_is_reported(download):
    download["result"] = _Fetched("https://example.com/empty", "text/html", b"<html></html>")
    assert "no extractable text" in fetch_url("https://example.com/empty")["error"]
