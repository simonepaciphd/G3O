"""P15 A1: metadata/URL publication-date producer (PI rulings 2026-11-11 A1.1 a, A1.2 a, A1.3 a).

Synthetic HTML and PDF bytes only; ``_download`` / the unlocker result are
stubbed. No network.
"""

from __future__ import annotations

import json

import pytest
from bs4 import BeautifulSoup

from g3o.common import config
from g3o.common import date_signals as ds
from g3o.common import source_fields as sf
from g3o.common.support_check import PageSources
from g3o.extract.parser_v27 import FieldValue as ExtractedField
from g3o.scrape import fetcher, unlocker
from g3o.scrape import html as html_mod
from g3o.scrape import pdf as pdf_mod
from g3o.scrape.render import FetchMetadata, RenderedPage

P1 = "inst1:u1#p001"
SOURCES = PageSources("inst1:u1", {P1: "The council published its annual report on 12 March 2024."})
needs_pdfplumber = pytest.mark.skipif(not pdf_mod.PDF_SUPPORT, reason="pdfplumber missing")


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _md(value: str, tag: str) -> sf.MetadataDate:
    return sf.MetadataDate(value, "metadata", f"test {tag}", tag=tag)


def _web(value: str) -> sf.MetadataDate:
    return sf.MetadataDate(value, "web_address", f"/{value}/")


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,want", [
    ("2024", "2024"),
    ("2024-03", "2024-03"),
    ("2024-03-12", "2024-03-12"),
    (" 2024-03-12 ", "2024-03-12"),
    ("2024-03-12T10:15", "2024-03-12"),
    ("2024-03-12T10:15:30Z", "2024-03-12"),
    ("2024-03-12T10:15:30.123+01:00", "2024-03-12"),
    ("2024-03-12 10:15:30", "2024-03-12"),
    ("2024-03-12T23:30:00-05:00", "2024-03-12"),  # stated offset kept: not 2024-03-13 UTC
    ("2024-03-12T00:30:00+0900", "2024-03-12"),
    ("2024-03-12T00:30+09", "2024-03-12"),
])
def test_iso_accepted(raw, want):
    assert ds.normalise_iso(raw) == want


@pytest.mark.parametrize("raw", [
    "", "12/03/2024", "March 12, 2024", "20240312", "2024-13", "2024-02-30", "2024-3-12",
    "2024-03-12T25:00", "2024-03-12T10:61", "2024-03-12T", "0000", "2024-03-12Z", None,
])
def test_iso_rejected(raw):
    assert ds.normalise_iso(raw) is None


@pytest.mark.parametrize("raw,want", [
    ("D:20240312101500+01'00'", "2024-03-12"),
    ("D:20240312101500Z", "2024-03-12"),
    ("D:20240312101500Z00'00'", "2024-03-12"),
    ("D:20240312101500-05'00", "2024-03-12"),
    ("D:20240312101500+01'", "2024-03-12"),
    ("D:20240312", "2024-03-12"),
    ("D:202403", "2024-03"),
    ("D:2024", "2024"),
    ("20240312101500", "2024-03-12"),
])
def test_pdf_accepted(raw, want):
    assert ds.normalise_pdf(raw) == want


@pytest.mark.parametrize("raw", ["D:20241312", "D:20240230", "D:2024031225", "2024-03-12", "D:", "Tue Mar 12 2024"])
def test_pdf_rejected(raw):
    assert ds.normalise_pdf(raw) is None


# ---------------------------------------------------------------------------
# HTML capture, one test per signal
# ---------------------------------------------------------------------------


def _tags(cands):
    return [(c["tag"], c["value"]) for c in cands]


def test_citation_publication_date():
    c = ds.html_date_candidates(_soup('<meta name="citation_publication_date" content="2024-03-12">'))
    assert c == [{"tag": ds.TAG_CITATION, "found_as": "meta name=citation_publication_date",
                  "raw": "2024-03-12", "value": "2024-03-12"}]


def test_opengraph_published_time():
    c = ds.html_date_candidates(_soup('<meta property="article:published_time" content="2024-03-12T09:00:00+02:00">'
                                      '<meta property="article:modified_time" content="2025-01-01">'))
    assert _tags(c) == [(ds.TAG_OPENGRAPH, "2024-03-12")]


@pytest.mark.parametrize("name", ["DC.date.issued", "dcterms.issued", "DCTERMS.issued"])
def test_dublin_core_issued(name):
    c = ds.html_date_candidates(_soup(f'<meta name="{name}" content="2023-07">'
                                      '<meta name="DC.date.modified" content="2025-01-01">'))
    assert _tags(c) == [(ds.TAG_DC, "2023-07")]


def test_schema_org_json_ld():
    doc = {"@context": "https://schema.org", "@graph": [
        {"@type": "NewsArticle", "datePublished": "2024-03-12T08:00:00Z", "dateModified": "2025-01-01"},
        {"@type": "WebPage", "datePublished": {"@value": "2024-03-12"}}]}
    c = ds.html_date_candidates(_soup(f'<script type="application/ld+json">{json.dumps(doc)}</script>'
                                      '<script type="application/ld+json">{not json</script>'))
    assert _tags(c) == [(ds.TAG_SCHEMA, "2024-03-12"), (ds.TAG_SCHEMA, "2024-03-12")]
    assert {x["found_as"] for x in c} == {"json-ld"}


def test_schema_org_microdata():
    html = ('<div itemscope itemtype="https://schema.org/Article">'
            '<time itemprop="datePublished" datetime="2024-03-12">12 March</time>'
            '<meta itemprop="datePublished" content="2024-03-12">'
            '<span itemprop="datePublished">2024-03-12</span></div>'
            '<div itemscope itemtype="https://example.org/Thing">'
            '<meta itemprop="datePublished" content="1999-01-01"></div>'
            '<meta itemprop="datePublished" content="1998-01-01">')
    c = ds.html_date_candidates(_soup(html))
    assert _tags(c) == [(ds.TAG_SCHEMA, "2024-03-12")] * 3
    assert {x["found_as"] for x in c} == {"microdata"}


def test_unparseable_value_is_kept_but_not_a_candidate():
    c = ds.html_date_candidates(_soup('<meta name="citation_publication_date" content="12/03/2024">'))
    assert c[0]["raw"] == "12/03/2024" and c[0]["value"] is None
    inputs = ds.page_date_inputs(c, "https://x.example/a")
    assert inputs.metadata_dates == () and inputs.metadata_measured


def test_extract_parts_carries_candidates_and_keeps_text():
    html = ('<html><head><meta name="citation_publication_date" content="2024-03-12">'
            '<script type="application/ld+json">{"datePublished": "2024-03-11"}</script></head>'
            '<body><main><p>The agency piloted a generative AI assistant in 2025.</p></main></body></html>')
    parts = html_mod.extract_parts(_soup(html), "https://x.example/")
    assert _tags(parts.metadata_dates) == [(ds.TAG_CITATION, "2024-03-12"), (ds.TAG_SCHEMA, "2024-03-11")]
    assert parts.text == html_mod.extract_text(_soup(html))


# ---------------------------------------------------------------------------
# Signed selection (A1.2 a)
# ---------------------------------------------------------------------------


def test_priority_order():
    dates = [_md("2021", ds.TAG_PDF), _md("2022", ds.TAG_DC), _md("2023", ds.TAG_OPENGRAPH),
             _md("2024", ds.TAG_SCHEMA), _md("2025", ds.TAG_CITATION), _web("2020-01")]
    assert sf.publication_date(dates, None, SOURCES).value == "2025"
    assert sf.publication_date(dates[:4], None, SOURCES).value == "2024"
    assert sf.publication_date(dates[:3], None, SOURCES).value == "2023"
    assert sf.publication_date(dates[:2], None, SOURCES).value == "2022"
    d = sf.publication_date(dates[:1], None, SOURCES)
    assert (d.value, d.date_origin, d.provenance) == ("2021", "metadata", "from_metadata")
    assert ds.TAG_PDF in d.basis and d.detail["date_producer"] == ds.PRODUCER_VERSION


def test_same_tag_agreeing_values_are_one_value():
    d = sf.publication_date([_md("2024-03-12", ds.TAG_SCHEMA), _md("2024-03-12", ds.TAG_SCHEMA)], None, SOURCES)
    assert d.value == "2024-03-12" and "metadata_disagreed" not in d.detail


def test_top_tag_disagreeing_is_absent_and_lower_tag_does_not_settle_it():
    # "no higher tag settling it": tag 1 disagrees; tag 2's single value is LOWER, so it is not consulted.
    dates = [_md("2024", ds.TAG_CITATION), _md("2023", ds.TAG_CITATION), _md("2022-05", ds.TAG_SCHEMA),
             _web("2021-02")]
    d = sf.publication_date(dates, None, SOURCES)
    assert (d.value, d.date_origin) == ("2021-02", "web_address")
    assert d.detail["metadata_disagreed"] == {"tag": ds.TAG_CITATION, "values": ["2023", "2024"]}


def test_higher_tag_settles_lower_disagreement():
    dates = [_md("2024", ds.TAG_OPENGRAPH), _md("2023", ds.TAG_OPENGRAPH), _md("2022-05", ds.TAG_SCHEMA)]
    d = sf.publication_date(dates, None, SOURCES)
    assert d.value == "2022-05" and "metadata_disagreed" not in d.detail


def test_precision_difference_counts_as_disagreement():
    d = sf.publication_date([_md("2024-03", ds.TAG_DC), _md("2024-03-12", ds.TAG_DC)], None, SOURCES)
    assert d.value == "not_documented" and d.detail["metadata_disagreed"]["tag"] == ds.TAG_DC


def test_metadata_disagreement_with_no_url_goes_to_quote_step():
    q = ExtractedField(sf.DATE, "2024-03-12", P1, "published its annual report on 12 March 2024")
    d = sf.publication_date([_md("2024", ds.TAG_SCHEMA), _md("2023", ds.TAG_SCHEMA)], q, SOURCES)
    assert (d.value, d.date_origin) == ("2024-03-12", "page_text_quote")


def test_metadata_entry_needs_signed_tag():
    with pytest.raises(ValueError):
        sf.publication_date([sf.MetadataDate("2024", "metadata", "x")], None, SOURCES)
    with pytest.raises(ValueError):
        sf.publication_date([sf.MetadataDate("2024", "metadata", "x", tag="dateModified")], None, SOURCES)


# ---------------------------------------------------------------------------
# URL test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url,want", [
    ("https://x.example/news/2024/03/12/ai-pilot", ["2024-03-12"]),
    ("https://x.example/news/2024/03/ai-pilot", ["2024-03"]),
    ("https://x.example/2024/03/12/", ["2024-03-12"]),
    ("https://x.example/news/2024/03", []),  # no trailing slash: not the signed pattern
    ("https://x.example/news/2024/13/x", []),
    ("https://x.example/news/2024/02/30/x", []),
    ("https://x.example/a/2024/03/b/2023/05/c", ["2024-03", "2023-05"]),
    ("https://x.example/12024/03/x", []),
])
def test_url_dates(url, want):
    assert ds.url_dates(url) == want


def test_single_url_date_used():
    inputs = ds.page_date_inputs([], "https://x.example/news/2024/03/12/ai-pilot")
    d = sf.publication_date(inputs.metadata_dates, None, SOURCES)
    assert (d.value, d.date_origin, d.provenance) == ("2024-03-12", "web_address", "from_metadata")


def test_repeated_identical_url_date_used():
    d = sf.page_publication_date([], "https://x.example/2024/03/x/2024/03/y", None, SOURCES)
    assert d.value == "2024-03"


def test_several_distinct_url_dates_are_absent():
    q = ExtractedField(sf.DATE, "2024-03-12", P1, "published its annual report on 12 March 2024")
    d = sf.page_publication_date([], "https://x.example/a/2024/03/b/2023/05/c", q, SOURCES)
    assert (d.value, d.date_origin) == ("2024-03-12", "page_text_quote")
    assert d.detail["web_address_disagreed"] == ["2023-05", "2024-03"]
    assert not sf.page_has_metadata_date([], "https://x.example/a/2024/03/b/2023/05/c")


def test_metadata_beats_url():
    cands = ds.html_date_candidates(_soup('<meta property="article:published_time" content="2022-01-05">'))
    d = sf.page_publication_date(cands, "https://x.example/2024/03/x", None, SOURCES)
    assert (d.value, d.date_origin) == ("2022-01-05", "metadata")
    assert sf.page_has_metadata_date(cands, "https://x.example/none")


# ---------------------------------------------------------------------------
# A1.3 a: stored pages with metadata not measured
# ---------------------------------------------------------------------------


def test_not_measured_runs_url_test():
    d = sf.page_publication_date(None, "https://x.example/2024/03/x", None, SOURCES)
    assert (d.value, d.date_origin) == ("2024-03", "web_address")
    assert d.detail["metadata"] == ds.NOT_MEASURED == "not_measured"
    assert sf.page_has_metadata_date(None, "https://x.example/2024/03/x")


def test_not_measured_without_url_date_goes_to_quote_step():
    q = ExtractedField(sf.DATE, "2024-03-12", P1, "published its annual report on 12 March 2024")
    d = sf.page_publication_date(None, "https://x.example/about", q, SOURCES)
    assert (d.value, d.date_origin, d.detail["metadata"]) == ("2024-03-12", "page_text_quote", "not_measured")
    assert sf.page_publication_date(None, "https://x.example/about", None, SOURCES).value == "not_documented"
    assert not sf.page_has_metadata_date(None, "https://x.example/about")


def test_measured_is_recorded():
    assert sf.page_publication_date([], "https://x.example/a", None, SOURCES).detail["metadata"] == "measured"


def test_neither_step_ran_refuses():
    with pytest.raises(sf.MissingUpstreamError):
        sf.page_publication_date(None, None, None, SOURCES)
    with pytest.raises(sf.MissingUpstreamError):
        sf.page_publication_date(None, "  ", None, SOURCES)


def test_not_measured_with_metadata_entries_is_inconsistent():
    with pytest.raises(ValueError):
        sf.publication_date([_md("2024", ds.TAG_DC)], None, SOURCES, metadata_measured=False)


# ---------------------------------------------------------------------------
# Record shape: old JSON loads, serialisation
# ---------------------------------------------------------------------------

OLD_RECORD = {
    "url": "https://x.example/news/2024/03/x", "text": "Old page text that is long enough.", "title": "Old",
    "content_type": "html", "chrome_text": "Home", "links": [], "email_links": [],
    "fetch_metadata": {"access_date": "2026-09-01", "http_status": 200, "final_url": None,
                       "fetch_method": "html", "elapsed_ms": 5, "wait_for": None},
}


def test_old_json_loads_as_not_measured():
    page = RenderedPage.model_validate_json(json.dumps(OLD_RECORD))
    assert page.metadata_dates is None
    assert "metadata_dates" not in json.loads(page.model_dump_json())
    d = sf.page_publication_date(page.metadata_dates, page.url, None, SOURCES)
    assert (d.value, d.detail["metadata"]) == ("2024-03", "not_measured")


def test_measured_empty_round_trips():
    page = RenderedPage.model_validate({**OLD_RECORD, "metadata_dates": []})
    again = RenderedPage.model_validate_json(page.model_dump_json())
    assert again.metadata_dates == []


def test_cached_old_page_served_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    path = fetcher._legacy_cache_path(OLD_RECORD["url"])
    (tmp_path / "cache").mkdir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(OLD_RECORD, f)
    page = fetcher._load(OLD_RECORD["url"])
    assert page is not None and page.metadata_dates is None


# ---------------------------------------------------------------------------
# Capture at scrape (fetcher paths)
# ---------------------------------------------------------------------------

HTML_PAGE = (
    b'<html><head><title>Agency</title><meta name="DC.date.issued" content="2023-11-02">'
    b'<script type="application/ld+json">{"@type": "Article", "datePublished": "2023-11-01"}</script></head>'
    b"<body><main><p>Long enough main text about the agency's generative AI policy.</p></main></body></html>"
)
PLAIN_HTML = b"<html><body><main><p>Long enough main text about the agency's generative AI policy.</p></main></body></html>"


def _make_pdf(info: bytes | None) -> bytes:
    """A minimal one-page PDF, optionally with a document-info dictionary."""
    stream = b"BT /F1 12 Tf 72 720 Td (Council adopts generative AI policy) Tj ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    if info is not None:
        objs.append(info)
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    info_ref = b" /Info %d 0 R" % len(objs) if info is not None else b""
    out += b"trailer\n<< /Size %d /Root 1 0 R%s >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, info_ref, xref)
    return bytes(out)


PDF_INFO = b"<< /Title (AI policy) /CreationDate (D:20240312101500+01'00') /ModDate (D:20250101000000Z) >>"


@pytest.fixture
def _tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")


def _serve(monkeypatch, content: bytes, ctype: str = "text/html"):
    monkeypatch.setattr(fetcher, "_download", lambda url, **_kw: (content, ctype, 200, url, 5))


def _scrape(url: str) -> RenderedPage:
    return fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)


def _unlocked(content: bytes) -> unlocker.UnlockerResult:
    return unlocker.UnlockerResult(success=True, content=content, inner_status=200,
                                   error=None, error_code=None, elapsed_ms=5)


def test_html_path_captures(_tmp_cache, monkeypatch):
    _serve(monkeypatch, HTML_PAGE)
    page = _scrape("https://agency.example/about")
    assert _tags(page.metadata_dates) == [(ds.TAG_DC, "2023-11-02"), (ds.TAG_SCHEMA, "2023-11-01")]
    d = sf.page_publication_date(page.metadata_dates, page.url, None, SOURCES)
    assert (d.value, d.date_origin) == ("2023-11-01", "metadata")  # schema.org outranks DC
    cached = fetcher._load(page.url)
    assert cached is not None and cached.metadata_dates == page.metadata_dates


def test_html_path_measured_none(_tmp_cache, monkeypatch):
    _serve(monkeypatch, PLAIN_HTML)
    assert _scrape("https://agency.example/plain").metadata_dates == []


def test_unlocker_html_captures(_tmp_cache):
    page = fetcher._unlocker_page("https://agency.example/about", _unlocked(HTML_PAGE), cache_floor=1)
    assert _tags(page.metadata_dates) == [(ds.TAG_DC, "2023-11-02"), (ds.TAG_SCHEMA, "2023-11-01")]


@needs_pdfplumber
def test_pdf_creation_date(_tmp_cache, monkeypatch):
    _serve(monkeypatch, _make_pdf(PDF_INFO), ctype="application/pdf")
    page = _scrape("https://council.example/policy.pdf")
    assert page.content_type == "pdf" and page.title == "AI policy"
    assert page.metadata_dates == [{"tag": ds.TAG_PDF, "found_as": "pdf info",
                                    "raw": "D:20240312101500+01'00'", "value": "2024-03-12"}]
    d = sf.page_publication_date(page.metadata_dates, page.url, None, SOURCES)
    assert (d.value, d.date_origin) == ("2024-03-12", "metadata") and ds.TAG_PDF in d.basis


@needs_pdfplumber
def test_pdf_without_info_is_measured_none(_tmp_cache, monkeypatch):
    _serve(monkeypatch, _make_pdf(None), ctype="application/pdf")
    assert _scrape("https://council.example/plain.pdf").metadata_dates == []


@needs_pdfplumber
def test_unlocker_pdf_creation_date(_tmp_cache):
    page = fetcher._unlocker_page("https://x.example/get?f=1", _unlocked(_make_pdf(PDF_INFO)), cache_floor=1)
    assert page.fetch_metadata.fetch_method == "unlocker_pdf"
    assert _tags(page.metadata_dates) == [(ds.TAG_PDF, "2024-03-12")]


def test_pdf_without_pdfplumber_is_not_measured(_tmp_cache, monkeypatch):
    monkeypatch.setattr(fetcher.pdf_mod, "PDF_SUPPORT", False)
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda c: "Council adopts generative AI policy")
    _serve(monkeypatch, _make_pdf(PDF_INFO), ctype="application/pdf")
    assert _scrape("https://council.example/p.pdf").metadata_dates is None


def test_render_page_is_not_measured():
    page = RenderedPage(url="https://x.example/", text="t", title="", content_type="render",
                        fetch_metadata=FetchMetadata(access_date="2026-11-11", fetch_method="render"))
    assert page.metadata_dates is None
