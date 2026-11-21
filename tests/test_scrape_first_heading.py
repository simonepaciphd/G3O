"""Def7 (PI ruling, calibration session 3: lift ruling 39 a): a render-time first-heading producer.

``RenderedPage.first_heading`` follows the T-014 / P15 A1 convention: ``None`` = not
measured (DOCX pages, a PDF read without pdfplumber, a render whose DOM could not be read, and every page
stored before the change: no back-fill), ``""`` = measured, no heading on the page.
An absent field is left out of the serialised record, so pages stored before the
change re-serialise byte for byte.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from g3o.common import config
from g3o.run.presweep import perpage_inputs_v27 as pin
from g3o.scrape import fetcher, unlocker
from g3o.scrape import html as html_mod
from g3o.scrape.render import RenderedPage
from tests.test_scrape_binary_route import _make_docx

# A record exactly as stored before the change (same bytes as the T-014 pin).
STORED_AT_BASE = (
    '{"url":"https://www.agency.gov.example/about/","text":"Main text",'
    '"title":"About","content_type":"html","fetch_metadata":'
    '{"access_date":"2026-10-01","http_status":200,"final_url":null,'
    '"fetch_method":"html","elapsed_ms":120,"wait_for":null}}'
)


def _h(html: str) -> str:
    return html_mod.extract_first_heading(BeautifulSoup(html, "html.parser"))


@pytest.fixture
def _tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def test_first_non_empty_h1_wins_over_earlier_lower_headings():
    assert _h("<body><h2>Section</h2><h1>  </h1><h1>Use of\n  generative <b>AI</b></h1>"
              "<h1>Second</h1></body>") == "Use of generative AI"


def test_h1_less_page_takes_first_h2_to_h6_in_document_order():
    assert _h("<body><p>x</p><h4>Minor</h4><h2>Major</h2></body>") == "Minor"


def test_main_region_is_read_before_the_rest_of_the_page():
    html = ("<body><header><h1>Site name</h1></header><main><h2>Press release</h2>"
            "<p>t</p></main></body>")
    assert _h(html) == "Press release"


def test_article_header_heading_counts():
    assert _h("<body><article><header><h2>Press release 12/2025</h2></header>"
              "<p>t</p></article></body>") == "Press release 12/2025"


def test_page_without_main_falls_back_to_the_whole_document():
    assert _h("<body><div><h1>Council AI policy</h1></div></body>") == "Council AI policy"


def test_main_without_heading_falls_back_to_the_whole_document():
    assert _h("<body><h1>Council AI policy</h1><main><p>text</p></main></body>") == "Council AI policy"


def test_headings_in_nav_aside_footer_and_noise_tags_are_skipped():
    html = ("<body><nav><h1>Menu</h1></nav><aside><h1>Related</h1></aside>"
            "<form><h1>Search</h1></form><footer><h1>Contact</h1></footer>"
            "<noscript><h1>Enable JS</h1></noscript><h3>Real heading</h3></body>")
    assert _h(html) == "Real heading"


def test_over_long_heading_is_skipped():
    long = "word " * 80  # 400 chars: a container misused as a heading
    assert _h(f"<body><h1>{long}</h1><h2>Short heading</h2></body>") == "Short heading"
    assert len(_h(f"<body><h1>{'x' * html_mod.FIRST_HEADING_MAX_CHARS}</h1></body>")) \
        == html_mod.FIRST_HEADING_MAX_CHARS


def test_no_heading_is_measured_empty():
    assert _h("<body><main><p>No heading here.</p></main></body>") == ""


def test_extract_first_heading_does_not_mutate_soup():
    html = "<body><nav><h1>Menu</h1></nav><main><h1>Title</h1><p>Body text long enough.</p></main></body>"
    soup = BeautifulSoup(html, "html.parser")
    before = str(soup)
    html_mod.extract_first_heading(soup)
    assert str(soup) == before


def test_extract_parts_carries_first_heading_and_leaves_text_unchanged():
    html = ("<html><body><header><h1>Site</h1></header><main><h1>Use of generative AI</h1>"
            "<p>The agency piloted a generative AI assistant for caseworkers.</p></main></body></html>")
    parts = html_mod.extract_parts(BeautifulSoup(html, "html.parser"), "https://x.example/")
    assert parts.first_heading == "Use of generative AI"
    assert parts.text == html_mod.extract_text(BeautifulSoup(html, "html.parser"))


# ---------------------------------------------------------------------------
# Storage shape: old records unchanged, new ones round-trip
# ---------------------------------------------------------------------------


def test_old_record_loads_without_heading_and_round_trips_byte_identical():
    page = RenderedPage.model_validate_json(STORED_AT_BASE)
    assert page.first_heading is None
    assert page.model_dump_json() == STORED_AT_BASE
    assert "first_heading" not in page.model_dump()


def test_old_record_round_trips_through_fetcher_cache(_tmp_cache):
    page = RenderedPage.model_validate_json(STORED_AT_BASE)
    fetcher._save(page)
    cached = fetcher._load(page.url)
    assert cached == page and cached.first_heading is None
    assert cached.model_dump_json() == STORED_AT_BASE


def test_measured_heading_and_measured_empty_round_trip():
    for heading in ("Use of generative AI", ""):
        page = RenderedPage.model_validate_json(STORED_AT_BASE).model_copy(
            update={"first_heading": heading})
        dumped = page.model_dump_json()
        assert f'"first_heading":"{heading}"' in dumped
        assert RenderedPage.model_validate_json(dumped) == page


# ---------------------------------------------------------------------------
# Which scrape paths measure it
# ---------------------------------------------------------------------------


def _serve(monkeypatch, content: bytes, ctype: str = "text/html"):
    monkeypatch.setattr(fetcher, "_download", lambda url, **_kw: (content, ctype, 200, url, 5))


def _scrape(url: str) -> RenderedPage:
    return fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)


UNTITLED = (b"<html><head><title>  </title></head><body><main><h2>Generative AI pilot</h2>"
            b"<p>The council runs a generative AI pilot for its caseworkers this year.</p>"
            b"</main></body></html>")


def test_html_path_measures_first_heading(_tmp_cache, monkeypatch):
    _serve(monkeypatch, UNTITLED)
    page = _scrape("https://x.example/news")
    assert page.title == "" and page.first_heading == "Generative AI pilot"
    assert fetcher._load(page.url) == page


def test_html_path_without_heading_is_measured_empty(_tmp_cache, monkeypatch):
    _serve(monkeypatch, b"<html><body><main><p>The council runs a generative AI pilot this year.</p>"
                        b"</main></body></html>")
    assert _scrape("https://x.example/news").first_heading == ""


def test_unlocker_html_path_measures_first_heading(_tmp_cache):
    result = unlocker.UnlockerResult(success=True, content=UNTITLED, inner_status=200,
                                     error=None, error_code=None, elapsed_ms=5)
    page = fetcher._unlocker_page("https://x.example/news", result, cache_floor=1)
    assert page.first_heading == "Generative AI pilot"


def test_pdf_path_measures_first_line_heading(_tmp_cache, monkeypatch):
    # D7-1 (b), PI ruling 2026-11-20: a newly scraped PDF measures its first non-empty text line.
    _serve(monkeypatch, b"%PDF-fake", "application/pdf")
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda c: "PDF TEXT long enough")
    page = _scrape("https://x.example/a.pdf")
    assert page.content_type == "pdf" and page.first_heading == "PDF TEXT long enough"
    assert fetcher._load(page.url) == page


def test_docx_path_leaves_heading_unmeasured(_tmp_cache, monkeypatch):
    _serve(monkeypatch, _make_docx(), "application/octet-stream")
    page = _scrape("https://x.example/a.docx")
    assert page.content_type == "docx" and page.first_heading is None


# ---------------------------------------------------------------------------
# Into the per-page input the source row reads
# ---------------------------------------------------------------------------


def _input(page: RenderedPage):
    return pin.rendered_page_input(page, institution_id="INST-0000001", institution="Council One",
                                   country="Australia", level_of_government="local")


def test_page_input_carries_the_stored_heading():
    page = RenderedPage.model_validate_json(STORED_AT_BASE).model_copy(update={"first_heading": "H"})
    assert _input(page).first_heading == "H"


def test_page_input_of_an_old_record_has_no_heading():
    assert _input(RenderedPage.model_validate_json(STORED_AT_BASE)).first_heading is None


# ---------------------------------------------------------------------------
# D7-1 (b) (PI ruling 2026-11-20, "2 b"): a PDF's first heading is the first
# non-empty line of its extracted text, length-bounded; newly scraped PDFs only
# ---------------------------------------------------------------------------

from g3o.common import source_fields as sf  # noqa: E402
from g3o.run.presweep import source_row_v27 as srow  # noqa: E402
from g3o.scrape import pdf as pdf_mod  # noqa: E402

# First text lines of the three study units (fix-def7 report); the following
# lines are invented fixture text, not the recorded documents.
STUDY_PDF_TEXTS = [
    ("Policy Committee Meeting\nNovember 17, 2025\nAgenda", "Policy Committee Meeting"),
    ("Greene County Tourist Promotion Agency\nBoard Meeting Minutes\n",
     "Greene County Tourist Promotion Agency"),
    ("Notice of Use of Artificial Intelligence in Employment Decisions\nThe city uses",
     "Notice of Use of Artificial Intelligence in Employment Decisions"),
]

# A PDF record exactly as stored before the change: untitled, no first_heading key.
STORED_PDF_AT_BASE = (
    '{"url":"https://www.agency.gov.example/a.pdf","text":"Policy Committee Meeting\\nAgenda",'
    '"title":"","content_type":"pdf","fetch_metadata":'
    '{"access_date":"2026-10-01","http_status":200,"final_url":null,'
    '"fetch_method":"pdf","elapsed_ms":120,"wait_for":null}}'
)


@pytest.mark.parametrize("text,expected", STUDY_PDF_TEXTS)
def test_pdf_first_line_of_the_study_texts(text, expected):
    assert pdf_mod.first_line_heading(text) == expected


def test_pdf_leading_blank_lines_and_whitespace_are_normalised():
    text = "\n\n   \n\t Policy   Committee\tMeeting  \r\nAgenda"
    assert pdf_mod.first_line_heading(text) == "Policy Committee Meeting"


def test_pdf_long_first_line_is_skipped_for_the_next_non_empty_line():
    bound = html_mod.FIRST_HEADING_MAX_CHARS
    assert pdf_mod.first_line_heading("x" * (bound + 1) + "\n\nBoard Meeting Minutes") \
        == "Board Meeting Minutes"
    assert pdf_mod.first_line_heading("y" * bound + "\nnext") == "y" * bound


def test_pdf_line_search_stops_after_a_fixed_number_of_non_empty_lines():
    long = "z" * (html_mod.FIRST_HEADING_MAX_CHARS + 1)
    n = pdf_mod.FIRST_LINE_MAX_LINES
    assert pdf_mod.first_line_heading("\n".join([long] * n + ["Too late"])) == ""
    assert pdf_mod.first_line_heading("\n".join([long] * (n - 1) + ["In time"])) == "In time"


@pytest.mark.parametrize("text", ["", "   ", "\n\n \t\n"])
def test_pdf_empty_text_is_measured_empty(text):
    assert pdf_mod.first_line_heading(text) == ""


def test_pdf_without_pdf_support_is_not_measured(monkeypatch):
    monkeypatch.setattr(pdf_mod, "PDF_SUPPORT", False)
    assert pdf_mod.first_line_heading("Policy Committee Meeting") is None


@pytest.mark.parametrize("text,expected", STUDY_PDF_TEXTS)
def test_untitled_study_pdf_gets_source_title_from_first_line(_tmp_cache, monkeypatch, text, expected):
    _serve(monkeypatch, b"%PDF-fake", "application/pdf")
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda c: text)
    monkeypatch.setattr(fetcher, "_pdf_title_and_dates", lambda c: ("", None))
    page = _scrape("https://x.example/a.pdf")
    assert page.title == "" and page.first_heading == expected
    rv = srow.source_title(_input(page))
    assert rv.value == expected and rv.basis == "first heading (title empty)"


def test_titled_pdf_keeps_its_metadata_title(_tmp_cache, monkeypatch):
    _serve(monkeypatch, b"%PDF-fake", "application/pdf")
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda c: "First line\nmore")
    monkeypatch.setattr(fetcher, "_pdf_title_and_dates", lambda c: ("Doc Title", None))
    page = _scrape("https://x.example/a.pdf")
    assert page.first_heading == "First line"
    rv = srow.source_title(_input(page))
    assert rv.value == "Doc Title" and rv.basis == "RenderedPage.title"


def test_pdf_with_empty_text_is_measured_empty_and_not_documented(_tmp_cache, monkeypatch):
    _serve(monkeypatch, b"%PDF-fake", "application/pdf")
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda c: "")
    monkeypatch.setattr(fetcher, "_pdf_title_and_dates", lambda c: ("", None))
    page = _scrape("https://x.example/a.pdf")
    assert page.first_heading == ""
    assert srow.source_title(_input(page)).value == "not_documented"


def test_unlocker_pdf_path_measures_first_line_heading(_tmp_cache, monkeypatch):
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda c: "\nGreene County Tourist Promotion Agency\n")
    monkeypatch.setattr(fetcher, "_pdf_title_and_dates", lambda c: ("", None))
    result = unlocker.UnlockerResult(success=True, content=b"%PDF-fake", inner_status=200,
                                     error=None, error_code=None, elapsed_ms=5)
    page = fetcher._unlocker_page("https://x.example/a.pdf", result, cache_floor=1)
    assert page.content_type == "pdf" and page.first_heading == "Greene County Tourist Promotion Agency"


def test_stored_pre_change_pdf_record_round_trips_and_still_refuses(_tmp_cache):
    page = RenderedPage.model_validate_json(STORED_PDF_AT_BASE)
    assert page.first_heading is None  # no back-fill from the stored text
    assert page.model_dump_json() == STORED_PDF_AT_BASE
    fetcher._save(page)
    cached = fetcher._load(page.url)
    assert cached.model_dump_json() == STORED_PDF_AT_BASE and cached.first_heading is None
    with pytest.raises(sf.MissingUpstreamError, match="not measured"):
        srow.source_title(_input(cached))


# Orchestrator follow-up: "" means the text was read and is empty; a pdfplumber
# error during extraction is "not measured" (None), like a missing pdfplumber.
# The recorded text itself is unchanged.


def _raising_open(*_a, **_kw):
    raise ValueError("broken xref")


class _OnePageThenRaise:
    def __init__(self, *_a, **_kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def pages(self):
        class _Page:
            def extract_text(self):
                return "Policy Committee Meeting\nAgenda"

            def flush_cache(self):
                pass

            class get_textmap:  # noqa: N801
                @staticmethod
                def cache_clear():
                    pass

        yield _Page()
        raise ValueError("page 2 unreadable")


def test_pdf_extraction_error_is_not_measured(monkeypatch):
    monkeypatch.setattr(pdf_mod.pdfplumber, "open", _raising_open)
    text = pdf_mod.extract_text(b"%PDF-fake")
    assert text == ""  # recorded text unchanged
    assert pdf_mod.first_line_heading(text) is None


def test_pdf_error_after_some_text_keeps_text_but_is_not_measured(monkeypatch):
    monkeypatch.setattr(pdf_mod.pdfplumber, "open", _OnePageThenRaise)
    text = pdf_mod.extract_text(b"%PDF-fake")
    assert text == "Policy Committee Meeting\nAgenda"
    assert pdf_mod.first_line_heading(text) is None


def test_scraped_pdf_with_extraction_error_is_not_measured_and_refuses(_tmp_cache, monkeypatch):
    _serve(monkeypatch, b"%PDF-fake", "application/pdf")
    monkeypatch.setattr(pdf_mod.pdfplumber, "open", _raising_open)
    page = _scrape("https://x.example/a.pdf")
    assert page.text == "" and page.first_heading is None
    assert "first_heading" not in page.model_dump_json()
    with pytest.raises(sf.MissingUpstreamError, match="not measured"):
        srow.source_title(_input(page))
