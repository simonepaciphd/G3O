"""T-014 (RC-D-002 F): chrome text and links next to an unchanged main text.

The ``BASE_MAIN_TEXT`` strings were produced by ``g3o.scrape.html.extract_text``
at base commit ``2e4c102`` (``html.py`` unchanged since ``375f1ff``) on the
fixture pages below, and are pinned here byte for byte.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from g3o.common import config
from g3o.scrape import fetcher, unlocker
from g3o.scrape import html as html_mod
from g3o.scrape.render import FetchMetadata, RenderedPage

BASE_URL = "https://www.agency.gov.example/about/"

FIXTURES: dict[str, str] = {
    "main_with_chrome": """
<html><head><title>Agency</title><script>var x = 1;</script></head>
<body>
<header><a href="/">Home</a><nav><a href="/news">News</a>
<a href="../contact">Contact</a></nav></header>
<main>
<h1>Use of generative AI</h1>
<p>The agency piloted a generative AI assistant for caseworkers in 2025.
See the <a href="/ai/policy.pdf">AI policy</a>.</p>
<aside>Related: <a href="https://other.example/x">Other site</a></aside>
<p>Short</p>
</main>
<footer>
<p>Agency of Examples, 1 Main St, Springfield</p>
<p>E-mail: <a href="mailto:info@agency.gov.example">info@agency.gov.example</a></p>
<p>Tel 555-0100 <a href="tel:5550100">call</a></p>
<script>track()</script>
</footer>
</body></html>
""",
    "no_main_body_fallback": """
<html><body>
<nav><ul><li><a href="/a">Alpha</a></li><li><a href="/b">Beta</a></li></ul></nav>
<div><p>This page has no main element, so the body is used as the container.</p>
<p><a href="#top">Back to top</a> <a href="javascript:void(0)">js</a>
<a href="/b">Beta again</a></p></div>
<footer>Contact us: press@agency.gov.example</footer>
</body></html>
""",
    "article_nested_header": """
<html><body>
<article><header><h2>Press release 12/2025</h2></header>
<p>Ministry announces a large language model procurement framework.</p>
<form><nav><a href="/in-form">In form</a></nav><input name="q"></form>
</article>
</body></html>
""",
    "no_chrome": """
<html><body><main><p>Plain page with only main content and no chrome at all.</p>
</main></body></html>
""",
}

BASE_MAIN_TEXT: dict[str, str] = {
    "main_with_chrome": (
        "The agency piloted a generative AI assistant for caseworkers in 2025.\n"
        "."
    ),
    "no_main_body_fallback": (
        "This page has no main element, so the body is used as the container."
    ),
    "article_nested_header": (
        "Ministry announces a large language model procurement framework."
    ),
    "no_chrome": "Plain page with only main content and no chrome at all.",
}


def _soup(name: str) -> BeautifulSoup:
    return BeautifulSoup(FIXTURES[name], "html.parser")


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_extract_text_matches_base_byte_for_byte(name: str) -> None:
    assert html_mod.extract_text(_soup(name)) == BASE_MAIN_TEXT[name]


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_extract_parts_main_text_unchanged(name: str) -> None:
    parts = html_mod.extract_parts(_soup(name), BASE_URL)
    assert parts.text == BASE_MAIN_TEXT[name]


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_extract_chrome_text_does_not_mutate_soup(name: str) -> None:
    soup = _soup(name)
    before = str(soup)
    html_mod.extract_chrome_text(soup)
    assert str(soup) == before
    assert html_mod.extract_text(soup) == BASE_MAIN_TEXT[name]


def test_chrome_text_is_a_separate_field() -> None:
    parts = html_mod.extract_parts(_soup("main_with_chrome"), BASE_URL)
    assert parts.chrome_text == (
        "Home\nNews\nContact\n"
        "Related:\nOther site\n"
        "Agency of Examples, 1 Main St, Springfield\n"
        "E-mail:\ninfo@agency.gov.example\n"
        "Tel 555-0100\ncall"
    )
    # Chrome stays out of main text, and noise inside chrome is dropped.
    assert "Agency of Examples" not in parts.text
    assert "track()" not in parts.chrome_text


def test_chrome_text_keeps_short_lines_and_body_fallback_chrome() -> None:
    parts = html_mod.extract_parts(_soup("no_main_body_fallback"), BASE_URL)
    assert parts.chrome_text == "Alpha\nBeta\nContact us: press@agency.gov.example"


def test_chrome_inside_noise_is_not_chrome() -> None:
    parts = html_mod.extract_parts(_soup("article_nested_header"), BASE_URL)
    assert parts.chrome_text == "Press release 12/2025"


def test_no_chrome_gives_empty_string() -> None:
    assert html_mod.extract_parts(_soup("no_chrome"), BASE_URL).chrome_text == ""


def test_links_are_stored_from_the_intact_page() -> None:
    parts = html_mod.extract_parts(_soup("main_with_chrome"), BASE_URL)
    urls = [link["url"] for link in parts.links]
    # Nav, main, aside links are kept (read before chrome is stripped);
    # mailto/tel are skipped by extract_links, as before.
    assert urls == [
        "https://www.agency.gov.example/",
        "https://www.agency.gov.example/news",
        "https://www.agency.gov.example/contact",
        "https://www.agency.gov.example/ai/policy.pdf",
        "https://other.example/x",
    ]
    assert parts.links == html_mod.extract_links(_soup("main_with_chrome"), BASE_URL)


def test_links_dedupe_and_skip_fragments_and_js() -> None:
    parts = html_mod.extract_parts(_soup("no_main_body_fallback"), BASE_URL)
    assert [link["url"] for link in parts.links] == [
        "https://www.agency.gov.example/a",
        "https://www.agency.gov.example/b",
    ]


def test_record_stored_before_the_change_loads_without_new_fields() -> None:
    """A Stage 4 artifact written at base parses, with no chrome text or links.

    Guard for the storage half of T-014: whatever form the stored fields take,
    an artifact written before the change must keep loading and read as
    "absent" (no back-fill, R-035 / R-059).
    """
    stored_at_base = (
        '{"url":"https://www.agency.gov.example/about/","text":"Main text",'
        '"title":"About","content_type":"html","fetch_metadata":'
        '{"access_date":"2026-10-01","http_status":200,"final_url":null,'
        '"fetch_method":"html","elapsed_ms":120,"wait_for":null}}'
    )
    page = RenderedPage.model_validate_json(stored_at_base)
    assert page.text == "Main text"
    assert getattr(page, "chrome_text", None) is None
    assert getattr(page, "links", None) is None


# ---------------------------------------------------------------------------
# E-mail links (PI ruling 8a)
# ---------------------------------------------------------------------------


def test_email_links_strip_scheme_query_lowercase_dedupe() -> None:
    soup = BeautifulSoup(
        '<p><a href="mailto:Info@Agency.gov.example?subject=Hi">a</a>'
        '<a href="MAILTO:press@agency.gov.example">b</a>'
        '<a href="mailto:info@agency.gov.example">dup</a>'
        '<a href="mailto:">empty</a><a href="tel:5550100">tel</a>'
        '<a href="/x">web</a></p>',
        "html.parser",
    )
    assert html_mod.extract_email_links(soup) == [
        "info@agency.gov.example",
        "press@agency.gov.example",
    ]


def test_extract_parts_carries_email_links() -> None:
    parts = html_mod.extract_parts(_soup("main_with_chrome"), BASE_URL)
    assert parts.email_links == ["info@agency.gov.example"]
    assert parts.text == BASE_MAIN_TEXT["main_with_chrome"]


# ---------------------------------------------------------------------------
# Stored record: RenderedPage, the fetcher paths and its cache
# ---------------------------------------------------------------------------

STORED_AT_BASE = (
    '{"url":"https://www.agency.gov.example/about/","text":"Main text",'
    '"title":"About","content_type":"html","fetch_metadata":'
    '{"access_date":"2026-10-01","http_status":200,"final_url":null,'
    '"fetch_method":"html","elapsed_ms":120,"wait_for":null}}'
)


@pytest.fixture
def _tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")


def test_old_record_round_trips_byte_identical() -> None:
    page = RenderedPage.model_validate_json(STORED_AT_BASE)
    assert page.chrome_text is None
    assert page.links is None
    assert page.email_links is None
    # Unmeasured fields are omitted, so the re-serialised record is the
    # pre-change bytes exactly (artifacts, cache, hashes unchanged).
    assert page.model_dump_json() == STORED_AT_BASE
    assert "chrome_text" not in page.model_dump()


def test_new_record_round_trips_with_fields() -> None:
    page = RenderedPage.model_validate_json(STORED_AT_BASE).model_copy(
        update={
            "chrome_text": "Home\nContact",
            "links": [{"url": "https://a.example/", "anchor_text": "A",
                       "context": "", "source": "html"}],
            "email_links": ["info@agency.gov.example"],
        }
    )
    again = RenderedPage.model_validate_json(page.model_dump_json())
    assert again == page
    assert again.chrome_text == "Home\nContact"
    assert again.email_links == ["info@agency.gov.example"]


def test_measured_but_empty_fields_are_kept_not_dropped() -> None:
    page = RenderedPage.model_validate_json(STORED_AT_BASE).model_copy(
        update={"chrome_text": "", "links": [], "email_links": []}
    )
    dumped = page.model_dump_json()
    assert '"chrome_text":""' in dumped and '"links":[]' in dumped
    assert RenderedPage.model_validate_json(dumped) == page


def test_old_record_round_trips_through_fetcher_cache(_tmp_cache) -> None:
    page = RenderedPage.model_validate_json(STORED_AT_BASE)
    fetcher._save(page)
    cached = fetcher._load(page.url)
    assert cached == page
    assert cached.chrome_text is None and cached.links is None
    assert cached.email_links is None


def _html_download(content: bytes, final_url: str):
    def _f(url):
        return (content, "text/html", 200, final_url, 5)

    return _f


def test_html_path_stores_fields_and_cache_round_trips(_tmp_cache, monkeypatch) -> None:
    url = "https://www.agency.gov.example/about/"
    monkeypatch.setattr(
        fetcher, "_download",
        _html_download(FIXTURES["main_with_chrome"].encode("utf-8"), url),
    )
    page = fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)
    assert page.text == BASE_MAIN_TEXT["main_with_chrome"]
    assert page.chrome_text == html_mod.extract_chrome_text(_soup("main_with_chrome"))
    assert page.links == html_mod.extract_links(_soup("main_with_chrome"), url)
    assert page.email_links == ["info@agency.gov.example"]
    assert fetcher._load(url) == page


def test_html_path_resolves_links_against_final_url(_tmp_cache, monkeypatch) -> None:
    monkeypatch.setattr(
        fetcher, "_download",
        _html_download(
            b"<html><body><main><p>Long enough main text for the page here.</p>"
            b'<a href="next">n</a></main></body></html>',
            "https://new.example/dir/",
        ),
    )
    page = fetcher.scrape_url(
        "https://old.example/", force_refresh=True, prefer_render_on_empty=False
    )
    assert [link["url"] for link in page.links] == ["https://new.example/dir/next"]


def test_pdf_path_leaves_fields_absent(_tmp_cache, monkeypatch) -> None:
    monkeypatch.setattr(
        fetcher, "_download",
        lambda url: (b"%PDF-fake", "application/pdf", 200, url, 5),
    )
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda c: "PDF TEXT")
    page = fetcher.scrape_url(
        "https://x.example/a.pdf", force_refresh=True, prefer_render_on_empty=False
    )
    assert page.chrome_text is None and page.links is None
    assert page.email_links is None
    assert "chrome_text" not in page.model_dump_json()


def test_unlocker_html_path_stores_fields(_tmp_cache) -> None:
    result = unlocker.UnlockerResult(
        success=True, content=FIXTURES["main_with_chrome"].encode("utf-8"),
        inner_status=200, error=None, error_code=None, elapsed_ms=5,
    )
    url = "https://www.agency.gov.example/about/"
    page = fetcher._unlocker_page(url, result, cache_floor=1)
    assert page.text == BASE_MAIN_TEXT["main_with_chrome"]
    assert page.chrome_text and "Agency of Examples" in page.chrome_text
    assert page.email_links == ["info@agency.gov.example"]
    assert len(page.links) == 5
    assert fetcher._load(url) == page


def test_unlocker_pdf_path_leaves_fields_absent(_tmp_cache, monkeypatch) -> None:
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda c: "PDF TEXT")
    result = unlocker.UnlockerResult(
        success=True, content=b"%PDF-fake", inner_status=200, error=None,
        error_code=None, elapsed_ms=5,
    )
    page = fetcher._unlocker_page("https://x.example/a.pdf", result, cache_floor=1)
    assert page.chrome_text is None and page.links is None
    assert page.email_links is None


def test_render_page_leaves_fields_absent() -> None:
    page = RenderedPage(
        url="https://x.example/", text="t", title="r", content_type="render",
        fetch_metadata=FetchMetadata(
            access_date="2026-10-31", http_status=200, final_url=None,
            fetch_method="render", elapsed_ms=1, wait_for=None,
        ),
    )
    assert page.chrome_text is None
    assert set(page.model_dump()) == {
        "url", "text", "title", "content_type", "fetch_metadata",
    }
