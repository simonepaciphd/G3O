"""T-065: binary documents fetched as HTML are routed to a document extractor.

Synthetic bytes only: the PDF and DOCX fixtures are built in this module, and
``_download`` / the unlocker result are stubbed. No network.
"""

from __future__ import annotations

import importlib.util
import io
import logging
import zipfile
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from g3o.common import config
from g3o.scrape import docx as docx_mod
from g3o.scrape import fetcher, readability, unlocker
from g3o.scrape import html as html_mod
from g3o.scrape import pdf as pdf_mod
from g3o.scrape.render import RenderedPage

# ---- synthetic fixtures -------------------------------------------------------------------------

PDF_TEXT = "Council adopts generative AI policy"


def _make_pdf(text: str = PDF_TEXT) -> bytes:
    """A minimal one-page PDF with real text, xref offsets computed."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1, xref,
    )
    return bytes(out)


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"

DOCX_BODY = (
    f'<w:document xmlns:w="{_W_NS}" xmlns:mc="{_MC_NS}"><w:body>'
    "<w:p><w:r><w:t>Municipal AI</w:t></w:r><w:r><w:t xml:space=\"preserve\"> strategy</w:t></w:r></w:p>"
    "<w:p><w:r><w:t>Item</w:t><w:tab/><w:t>Chatbot pilot</w:t><w:br/><w:t>Second line</w:t></w:r></w:p>"
    "<w:p/>"
    "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cell A</w:t></w:r></w:p></w:tc>"
    "<w:tc><w:p><w:r><w:t>Cell B</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    "<w:p><w:r><w:t>Before box</w:t></w:r><w:r><mc:AlternateContent><mc:Choice>"
    "<w:txbxContent><w:p><w:r><w:t>Box text</w:t></w:r></w:p></w:txbxContent>"
    "</mc:Choice><mc:Fallback><w:txbxContent><w:p><w:r><w:t>Box text</w:t></w:r></w:p>"
    "</w:txbxContent></mc:Fallback></mc:AlternateContent></w:r></w:p>"
    "<w:p><w:del><w:r><w:delText>deleted words</w:delText></w:r></w:del>"
    "<w:ins><w:r><w:t>inserted words</w:t></w:r></w:ins></w:p>"
    "</w:body></w:document>"
)
DOCX_TEXT = (
    "Municipal AI strategy\nItem\tChatbot pilot\nSecond line\n\nCell A\nCell B\n"
    "Before box\nBox text\ninserted words"
)
DOCX_TITLE = "AI Strategy 2025"
_CORE = (
    '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
    'metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
    f"<dc:title>{DOCX_TITLE}</dc:title></cp:coreProperties>"
)


def _make_zip(parts: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in parts.items():
            zf.writestr(name, body)
    return buf.getvalue()


def _make_docx(body: str = DOCX_BODY, *, title: bool = True) -> bytes:
    parts = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        "word/document.xml": body,
    }
    if title:
        parts["docProps/core.xml"] = _CORE
    return _make_zip(parts)


HTML_PAGE = (
    b"<html><head><title>Agency</title></head><body><main>"
    b"<p>This page explains the %PDF-1.7 format and zip files (PK\\x03\\x04).</p>"
    b"<p>Long enough main text about the agency's generative AI policy.</p>"
    b"</main></body></html>"
)

needs_pdfplumber = pytest.mark.skipif(not pdf_mod.PDF_SUPPORT, reason="pdfplumber missing")


@pytest.fixture
def _tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")


def _serve(monkeypatch, content: bytes, ctype: str = "text/html"):
    monkeypatch.setattr(
        fetcher, "_download",
        lambda url, **_kw: (content, ctype, 200, url, 5),
    )


def _scrape(url: str) -> RenderedPage:
    return fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)


def _unlocked(content: bytes) -> unlocker.UnlockerResult:
    return unlocker.UnlockerResult(
        success=True, content=content, inner_status=200,
        error=None, error_code=None, elapsed_ms=5,
    )


def _old_html_text(content: bytes) -> str:
    """What the pre-T-065 fetcher stored for these bytes (the HTML branch)."""
    return html_mod.extract_parts(BeautifulSoup(content, "html.parser"), "https://x.example/").text


# ---- sniffing -----------------------------------------------------------------------------------

def test_sniff_recognises_pdf_and_docx_bytes():
    assert fetcher._sniff_document(_make_pdf()) == "pdf"
    assert fetcher._sniff_document(b"\n\r\n%PDF-1.7 rest") == "pdf"
    assert fetcher._sniff_document(_make_docx()) == "docx"


def test_sniff_leaves_html_and_other_zips_alone():
    assert fetcher._sniff_document(HTML_PAGE) is None
    assert fetcher._sniff_document(b"<!doctype html><p>%PDF-1.4</p>") is None
    xlsx = _make_zip({"[Content_Types].xml": "<Types/>", "xl/workbook.xml": "<workbook/>"})
    assert fetcher._sniff_document(xlsx) is None
    assert fetcher._sniff_document(b"PK\x03\x04 not really a zip") is None
    assert fetcher._sniff_document(b"") is None


def test_route_keeps_header_and_suffix_rules_without_a_signature():
    assert fetcher._route(b"junk", ctype="application/pdf", url="https://x/a") == "pdf"
    assert fetcher._route(b"junk", ctype="", url="https://x/a.PDF") == "pdf"
    assert fetcher._route(HTML_PAGE, ctype="text/html", url="https://x/pdf-forms.html") == "html"
    # The sniffed kind wins over the header.
    assert fetcher._route(_make_docx(), ctype="application/pdf", url="https://x/a.pdf") == "docx"


# ---- deterministic path -------------------------------------------------------------------------

def test_pdf_served_as_html_routes_to_pdf_extractor(_tmp_cache, monkeypatch):
    seen: list[bytes] = []
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda c: seen.append(c) or PDF_TEXT)
    pdf = _make_pdf()
    _serve(monkeypatch, pdf)
    page = _scrape("https://council.example/document?id=42")
    assert seen == [pdf]
    assert page.content_type == "pdf"
    assert page.fetch_metadata.fetch_method == "pdf"
    assert page.text == PDF_TEXT
    assert page.chrome_text is None and page.links is None and page.email_links is None


@needs_pdfplumber
def test_pdf_served_as_html_extracts_real_text(_tmp_cache, monkeypatch):
    _serve(monkeypatch, _make_pdf())
    page = _scrape("https://council.example/download/7")
    assert PDF_TEXT in page.text
    assert readability.readability_failure(page.text) is None


def test_docx_served_as_html_routes_to_docx_extractor(_tmp_cache, monkeypatch):
    _serve(monkeypatch, _make_docx())
    page = _scrape("https://council.example/files/strategy")
    assert page.content_type == "docx"
    assert page.fetch_metadata.fetch_method == "docx"
    assert page.text == DOCX_TEXT
    assert page.title == DOCX_TITLE
    assert page.chrome_text is None and page.links is None and page.email_links is None
    assert readability.readability_failure(page.text) is None


def test_real_html_page_is_unaffected(_tmp_cache, monkeypatch):
    url = "https://agency.example/about"
    _serve(monkeypatch, HTML_PAGE)
    page = _scrape(url)
    soup = BeautifulSoup(HTML_PAGE, "html.parser")
    parts = html_mod.extract_parts(soup, url)
    assert page.content_type == "html"
    assert page.fetch_metadata.fetch_method == "html"
    assert page.text == parts.text
    assert page.links == parts.links and page.chrome_text == parts.chrome_text
    assert page.title == "Agency"


# ---- unlocker path ------------------------------------------------------------------------------

def test_unlocker_pdf_without_suffix_routes_to_pdf(_tmp_cache, monkeypatch):
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda c: PDF_TEXT)
    page = fetcher._unlocker_page("https://x.example/get?f=1", _unlocked(_make_pdf()), cache_floor=1)
    assert page.content_type == "pdf"
    assert page.fetch_metadata.fetch_method == "unlocker_pdf"
    assert page.text == PDF_TEXT


def test_unlocker_docx_without_suffix_routes_to_docx(_tmp_cache):
    page = fetcher._unlocker_page("https://x.example/get?f=2", _unlocked(_make_docx()), cache_floor=1)
    assert page.content_type == "docx"
    assert page.fetch_metadata.fetch_method == "unlocker_docx"
    assert page.text == DOCX_TEXT


def test_unlocker_html_unaffected(_tmp_cache):
    url = "https://agency.example/about"
    page = fetcher._unlocker_page(url, _unlocked(HTML_PAGE), cache_floor=1)
    assert page.content_type == "html"
    assert page.fetch_metadata.fetch_method == "unlocker"
    assert page.text == html_mod.extract_parts(BeautifulSoup(HTML_PAGE, "html.parser"), url).text


# ---- record shape -------------------------------------------------------------------------------

def test_cache_record_shape_unchanged_for_docx(_tmp_cache, monkeypatch):
    url = "https://council.example/files/strategy"
    _serve(monkeypatch, _make_docx())
    page = _scrape(url)
    dumped = page.model_dump()
    assert set(dumped) == {"url", "text", "title", "content_type", "fetch_metadata"}
    assert set(dumped["fetch_metadata"]) == {
        "access_date", "http_status", "final_url", "fetch_method", "elapsed_ms", "wait_for",
    }
    assert RenderedPage.model_config["extra"] == "forbid"
    assert fetcher._load(url) == page
    with pytest.raises(ValueError):
        RenderedPage.model_validate({**dumped, "raw_bytes": "x"})


# ---- DOCX extractor -----------------------------------------------------------------------------

def test_docx_extractor_defensive_failures():
    assert docx_mod.extract_text(b"not a zip") == ""
    assert docx_mod.extract_text(_make_zip({"other.xml": "<a/>"})) == ""
    bomb = _make_docx(
        '<!DOCTYPE w [<!ENTITY a "aaaa">]>'
        f'<w:document xmlns:w="{_W_NS}"><w:body><w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>'
    )
    assert docx_mod.extract_text(bomb) == ""
    assert docx_mod.extract_text(_make_docx("<w:document")) == ""
    assert docx_mod.extract_title(_make_docx(title=False)) == ""
    assert not docx_mod.is_docx(b"<html></html>")


def test_docx_part_size_cap(monkeypatch):
    monkeypatch.setattr(docx_mod, "MAX_XML_BYTES", 100)
    assert docx_mod.extract_text(_make_docx()) == ""


# ---- readability check (R-015, RC-D-018 "1 c") --------------------------------------------------

_SPIKE = Path(__file__).resolve().parents[1] / "scripts" / "spikes" / "f4" / "readability.py"


def _spike():
    spec = importlib.util.spec_from_file_location("f4_readability_spike", _SPIKE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_old_path_text_of_fixtures_is_flagged_new_path_is_not():
    """Self-check: the F4 binary flags fire on the pre-T-065 text and not after."""
    pdf_old = _old_html_text(_make_pdf())
    assert readability.readability_failure(pdf_old).startswith("binary_marker:")
    assert "pdf_header" in readability.binary_markers(pdf_old)
    docx_old = _old_html_text(_make_docx())
    assert readability.readability_failure(docx_old).startswith("binary_marker:")
    assert "zip" in readability.binary_markers(docx_old)
    assert readability.readability_failure(docx_mod.extract_text(_make_docx())) is None


@pytest.mark.parametrize("text", [
    "Council AI policy.\n人工智能政策 นโยบาย",
    "%PDF-1.7\n1 0 obj\n<<>>\nstream\n\x00\x01 endstream endobj",
    "PK\x03\x04word/document.xml",
    "12 34 56 78 90 / 12.5 % 33 ; 2024 2025 2026 a",
    "\x89PNG header",
    "",
])
def test_production_check_matches_spike_measures(text):
    spike = _spike()
    m = spike.measures(text)
    assert ";".join(readability.binary_markers(text)) == m["signatures"]
    share = readability.letter_share(text)
    if m["letter_share"] is None:
        assert share is None
    else:
        assert round(share, 5) == m["letter_share"]
    spike_flags = spike.flags(m)
    expected = (
        "binary_signature" in spike_flags or "letters<10%" in spike_flags
    ) and m["n_chars"] > 0
    assert (readability.readability_failure(text) is not None) == expected


def test_readability_reasons():
    assert readability.readability_failure("12 34 56 78 90 2024 2025 a") == "low_letter_share"
    assert readability.readability_failure("Plain readable sentence.") is None
    assert readability.readability_failure("   \n ") is None
    assert readability.readability_failure("ok\x00") == "binary_marker:null"
    # A number-heavy page just above the cut stays readable.
    assert readability.readability_failure("abc 1234567890 12345678") is None


def test_fetch_logs_unreadable_text(_tmp_cache, monkeypatch, caplog):
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda c: "1 2 3 4 5 6 7 8 9 0 x")
    _serve(monkeypatch, _make_pdf())
    with caplog.at_level(logging.WARNING, logger="g3o.scrape.fetcher"):
        _scrape("https://council.example/doc")
    assert any("low_letter_share" in r.getMessage() for r in caplog.records)
