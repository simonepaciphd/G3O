"""Stage 4 render-on-empty trigger + telemetry (fix/render-empty-pages).

JS-shell government pages return a 200 with near-zero stripped text. Before
this fix the scrape render fired only on *truly* empty text, so those pages
passed through Stage 4 and were silently dropped in Stage 5 as
``empty_page_dropped``. The fix extends the existing render trigger to fire
whenever the deterministic text strips below ``empty_page_min_chars`` (the same
floor Stage 5 uses to drop), reusing the existing Playwright adapter, and writes
a ``render_attempted`` attrition record for every render attempt so the render
rate and its cost stay auditable.

Two layers are exercised:
  • the trigger itself, in ``scrape_url`` (mock ``_download`` / ``render_url``);
  • the artifact + attrition-ledger behavior, in ``_run_scrape``.

Conventions mirror test_health_report.py / test_fetcher.py: cache is isolated to
a tmp dir, the network and Playwright are never touched, and flags are asserted
against the known threshold.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from g3o.common import attrition
from g3o.common import config as _config
from g3o.common.artifact_io import artifact_exists, read_artifact
from g3o.extract.batch import url_hash
from g3o.run import presweep as ps
from g3o.scrape import fetcher
from g3o.scrape.render import FetchMetadata, RenderedPage, utc_today_iso
from tests._layout import inst_dir as inst_dir_of

HTML_BYTES = b"<html><head><title>T</title></head><body>hi</body></html>"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Isolate the fetcher's on-disk cache and reset the attrition dedup cache
    so each test starts from a clean ledger and never touches the real cache."""
    monkeypatch.setattr(_config, "CACHE_DIR", tmp_path / "cache")
    attrition._reset_cache()
    yield
    attrition._reset_cache()


def _download_returning(*, content=HTML_BYTES, ctype="text/html", status=200, final_url="https://x.gov", ms=5):
    def _f(url):
        return (content, ctype, status, final_url, ms)

    return _f


def _download_raising():
    def _f(url):
        raise RuntimeError("simulated download failure")

    return _f


def _rendered_page(url, text="RENDERED CONTENT " * 5):
    return RenderedPage(
        url=url,
        text=text,
        title="r",
        content_type="render",
        fetch_metadata=FetchMetadata(
            access_date=utc_today_iso(),
            http_status=200,
            final_url=url,
            fetch_method="render",
            elapsed_ms=1,
            wait_for=None,
        ),
    )


def _boom(*_a, **_k):
    raise AssertionError("render_url must not be called on this path")


# ---------------------------------------------------------------------------
# Trigger layer — scrape_url
# ---------------------------------------------------------------------------


def test_near_empty_download_triggers_render_attempt(monkeypatch):
    """A page that downloads fine but strips to below empty_page_min_chars
    triggers a render attempt (not just a *truly* empty page)."""
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    # 5 non-whitespace chars — non-empty, but under the 50-char floor.
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "short")
    rendered = []
    monkeypatch.setattr(
        fetcher, "render_url",
        lambda u, timeout, session=None: (rendered.append(u) or _rendered_page(u)),
    )
    events: list[dict[str, Any]] = []

    page = fetcher.scrape_url(
        "https://x.gov", force_refresh=True,
        empty_page_min_chars=50,
        on_render_attempt=lambda **kw: events.append(kw),
    )

    assert rendered == ["https://x.gov"]  # the render actually fired
    assert page.text.startswith("RENDERED CONTENT")  # rendered result surfaced
    assert len(events) == 1
    assert events[0]["trigger"] == "empty_after_strip"
    assert events[0]["outcome"] == "rendered"


def test_real_content_never_triggers_render(monkeypatch):
    """Happy path (no regression): a page with real content above the floor is
    returned as-is and the renderer is never launched."""
    real_text = "A" * 60  # comfortably above the 50-char floor
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: real_text)
    monkeypatch.setattr(fetcher, "render_url", _boom)
    events: list[dict[str, Any]] = []

    page = fetcher.scrape_url(
        "https://x.gov", force_refresh=True,
        empty_page_min_chars=50,
        prefer_render_on_empty=True,
        on_render_attempt=lambda **kw: events.append(kw),
    )

    assert page.text == real_text
    assert page.fetch_metadata.fetch_method == "html"
    assert events == []  # no render attempt recorded


def test_download_failure_trigger_unchanged_and_records_telemetry(monkeypatch):
    """No regression: the download-failure render trigger still fires when
    opted in, and now also emits a render-attempt telemetry event."""
    monkeypatch.setattr(fetcher, "_download", _download_raising())
    monkeypatch.setattr(
        fetcher, "render_url", lambda u, timeout, session=None: _rendered_page(u)
    )
    events: list[dict[str, Any]] = []

    page = fetcher.scrape_url(
        "https://blocked.gov", force_refresh=True,
        prefer_render_on_download_failure=True,
        on_render_attempt=lambda **kw: events.append(kw),
    )

    assert page.fetch_metadata.fetch_method == "render"
    assert page.text.startswith("RENDERED CONTENT")
    assert len(events) == 1
    assert events[0]["trigger"] == "download_failure"
    assert events[0]["outcome"] == "rendered"


# ---------------------------------------------------------------------------
# Cache-bypass regression — below-floor pages must not freeze cross-run
# (render-on-empty fix, 2026-07-21)
# ---------------------------------------------------------------------------


def test_below_floor_render_failure_not_cached_and_reattempted(monkeypatch):
    """A near-empty page whose render fallback FAILS must not be frozen into the
    shared cache: the next run re-downloads and re-renders rather than serving
    the short deterministic text from disk (F17 retry-next-run). Regression for
    the _load-before-threshold / _save-caches-short-page bypass."""
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "short")  # 5 chars

    calls = {"render": 0}

    def _failing_render(u, timeout, session=None):
        calls["render"] += 1
        raise RuntimeError("render down")

    monkeypatch.setattr(fetcher, "render_url", _failing_render)

    # Run 1: render fails, the 5-char deterministic text surfaces but is NOT cached.
    page1 = fetcher.scrape_url("https://x.gov", empty_page_min_chars=50)
    assert page1.text == "short"
    assert not os.path.exists(fetcher._cache_path("https://x.gov"))
    assert calls["render"] == 1

    # Run 2 (no force_refresh): cache miss → the render is attempted again,
    # not short-circuited by a frozen below-floor cache entry.
    page2 = fetcher.scrape_url("https://x.gov", empty_page_min_chars=50)
    assert page2.text == "short"
    assert calls["render"] == 2


def test_pre_existing_below_floor_cache_entry_treated_as_miss(monkeypatch):
    """A cache entry written before the floor existed (a short page cached at
    min_chars=1) must be ignored on load when the caller's floor is higher, so
    the page re-fetches instead of serving stale near-empty text."""
    url = "https://y.gov"
    fetcher._save(_rendered_page(url, text="tiny"), min_chars=1)  # 4 chars, cached
    assert os.path.exists(fetcher._cache_path(url))

    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "A" * 60)
    monkeypatch.setattr(fetcher, "render_url", _boom)  # real content; no render needed

    page = fetcher.scrape_url(url, empty_page_min_chars=50)
    # The stale 4-char entry is bypassed; fresh above-floor content is returned.
    assert page.text == "A" * 60
    assert page.fetch_metadata.fetch_method == "html"


# ---------------------------------------------------------------------------
# Artifact + attrition layer — _run_scrape
# ---------------------------------------------------------------------------

_INST_ID = "INST-0000580"
_URL = "https://www.mcit.gov.qa/en/about-us"


def _run_one(monkeypatch, run_dir, *, extract_text, render_text):
    """Drive ``_run_scrape`` for a single (institution × URL) with the
    deterministic HTML path stubbed to ``extract_text`` and the render adapter
    stubbed to return a page carrying ``render_text``. Returns the run output."""
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: extract_text)
    monkeypatch.setattr(
        fetcher, "render_url",
        lambda u, timeout, session=None: _rendered_page(u, text=render_text),
    )
    sample = [{"master_row_id": "580"}]
    triaged = {_INST_ID: [_URL]}
    return ps._run_scrape(
        run_dir, sample, triaged,
        respect_robots=False, host_delay_seconds=0,
    )


def test_empty_then_rendered_writes_artifact_not_drop(tmp_path, monkeypatch):
    """A page empty-after-strip that renders successfully produces a scrape
    artifact with the rendered content — not a dropped record."""
    run_dir = tmp_path / "runs" / "r1"
    out = _run_one(monkeypatch, run_dir, extract_text="", render_text="RENDERED BODY " * 5)

    # The page is kept, carrying the rendered content.
    pages = out[_INST_ID]
    assert len(pages) == 1
    assert pages[0].text.startswith("RENDERED BODY")
    assert pages[0].content_type == "render"

    # A real scrape artifact is on disk (not silently dropped).
    artifact = inst_dir_of(run_dir, _INST_ID) / "scrape" / f"{url_hash(_URL)}.json"
    assert artifact_exists(artifact)
    assert "RENDERED BODY" in read_artifact(artifact)

    # Exactly one render-attempt telemetry record, with the rendered outcome.
    renders = [r for r in attrition.read_records(run_dir) if r["reason"] == "render_attempted"]
    assert len(renders) == 1
    assert renders[0]["url"] == _URL
    assert renders[0]["trigger"] == "empty_after_strip"
    assert renders[0]["outcome"] == "rendered"


def test_still_empty_after_render_records_exactly_one_attrition(tmp_path, monkeypatch):
    """A page that is still empty after rendering gets exactly one attrition
    record — not a silent drop, and not a duplicate."""
    run_dir = tmp_path / "runs" / "r1"
    # Render "succeeds" but still yields whitespace-only text.
    out = _run_one(monkeypatch, run_dir, extract_text="", render_text="   ")

    # The page is not silently dropped — it is still emitted as an artifact.
    assert len(out[_INST_ID]) == 1
    artifact = inst_dir_of(run_dir, _INST_ID) / "scrape" / f"{url_hash(_URL)}.json"
    assert artifact_exists(artifact)

    # Exactly one render_attempted record for this URL — no duplicate.
    renders = [r for r in attrition.read_records(run_dir) if r["reason"] == "render_attempted"]
    assert len(renders) == 1
    assert renders[0]["url"] == _URL
    assert renders[0]["outcome"] == "rendered"
    assert "stripped_len=0" in renders[0]["detail"]


def test_real_content_run_writes_no_render_record(tmp_path, monkeypatch):
    """Happy path through the runner (no regression): a page with real content
    above the floor writes no render_attempted record to the ledger, and the
    render adapter is never invoked."""
    run_dir = tmp_path / "runs" / "r1"
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "B" * 200)
    monkeypatch.setattr(fetcher, "render_url", _boom)  # a render here is a failure
    sample = [{"master_row_id": "580"}]
    triaged = {_INST_ID: [_URL]}

    out = ps._run_scrape(
        run_dir, sample, triaged,
        respect_robots=False, host_delay_seconds=0,
    )

    # Real deterministic content is kept as-is.
    assert out[_INST_ID][0].text == "B" * 200
    assert out[_INST_ID][0].fetch_metadata.fetch_method == "html"

    # No render telemetry written for this URL.
    renders = [r for r in attrition.read_records(run_dir) if r["reason"] == "render_attempted"]
    assert renders == []
