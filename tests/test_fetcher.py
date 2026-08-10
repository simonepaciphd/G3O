"""Stage 4 fetcher dispatch tests (review F19, Opus-side mechanical backfill).

``scrape_url`` is the single scrape entrypoint; its dispatch policy — cache
short-circuit, force-render, HTML/PDF content-type routing, render fallback on
download failure or empty text, and the F17 "don't cache empty pages" rule —
was previously exercised only by a single live ``@network`` test. These tests
mock ``_download`` and ``render_url`` so the routing logic is covered without
the network. Extraction internals (``html``/``pdf`` parsing) are mocked to
sentinels so each test isolates *dispatch*, not parsing.
"""

from __future__ import annotations

import gzip
import hashlib
import os
from pathlib import Path

import pytest

from g3o.common import config
from g3o.scrape import fetcher
from g3o.scrape.render import FetchMetadata, RenderedPage, utc_today_iso

HTML_BYTES = b"<html><head><title>T</title></head><body>hi</body></html>"


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Point the on-disk cache at a tmp dir so tests never read/write the real
    ``cache/`` and can assert on cache-file presence."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    yield


def _download_returning(
    *, content=HTML_BYTES, ctype="text/html", status=200, final_url="https://x.gov", ms=5
):
    def _f(url):
        return (content, ctype, status, final_url, ms)

    return _f


def _download_raising():
    def _f(url):
        raise RuntimeError("simulated download failure")

    return _f


def _rendered_page(url, text="RENDERED"):
    return RenderedPage(
        url=url,
        text=text,
        title="r",
        content_type="html",
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
    raise AssertionError("should not be called on this path")


# ---------------------------------------------------------------------------
# Cache short-circuit + force flags
# ---------------------------------------------------------------------------


def test_cache_hit_short_circuits_download(monkeypatch):
    url = "https://cached.gov/p"
    fetcher._save(_rendered_page(url, text="FROM_CACHE"))
    monkeypatch.setattr(fetcher, "_download", _boom)

    page = fetcher.scrape_url(url)

    assert page.text == "FROM_CACHE"


def test_force_refresh_bypasses_cache(monkeypatch):
    url = "https://cached.gov/p"
    fetcher._save(_rendered_page(url, text="FROM_CACHE"))
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "FRESH")

    page = fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)

    assert page.text == "FRESH"


def test_force_render_uses_renderer_not_download(monkeypatch):
    url = "https://js.gov/p"
    monkeypatch.setattr(fetcher, "_download", _boom)
    monkeypatch.setattr(
        fetcher, "render_url", lambda u, timeout, session=None: _rendered_page(u)
    )

    page = fetcher.scrape_url(url, force_refresh=True, force_render=True)

    assert page.text == "RENDERED"
    assert page.fetch_metadata.fetch_method == "render"


# ---------------------------------------------------------------------------
# Content-type routing
# ---------------------------------------------------------------------------


def test_html_routing(monkeypatch):
    monkeypatch.setattr(fetcher, "_download", _download_returning(ctype="text/html"))
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "HTMLTEXT")
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", _boom)

    page = fetcher.scrape_url("https://x.gov", force_refresh=True, prefer_render_on_empty=False)

    assert page.content_type == "html"
    assert page.fetch_metadata.fetch_method == "html"
    assert page.text == "HTMLTEXT"


def test_pdf_routing_by_content_type(monkeypatch):
    monkeypatch.setattr(
        fetcher, "_download", _download_returning(content=b"%PDF-1.4", ctype="application/pdf")
    )
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda content: "PDFTEXT")
    monkeypatch.setattr(fetcher.html_mod, "extract_text", _boom)

    page = fetcher.scrape_url("https://x.gov/doc", force_refresh=True, prefer_render_on_empty=False)

    assert page.content_type == "pdf"
    assert page.fetch_metadata.fetch_method == "pdf"
    assert page.text == "PDFTEXT"


def test_pdf_routing_by_url_suffix(monkeypatch):
    # Empty content-type but a .pdf URL still routes to the PDF path.
    monkeypatch.setattr(
        fetcher, "_download", _download_returning(content=b"%PDF-1.4", ctype="")
    )
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda content: "PDFTEXT")
    monkeypatch.setattr(fetcher.html_mod, "extract_text", _boom)

    page = fetcher.scrape_url(
        "https://x.gov/report.PDF", force_refresh=True, prefer_render_on_empty=False
    )

    assert page.content_type == "pdf"
    assert page.text == "PDFTEXT"


# ---------------------------------------------------------------------------
# Render fallback
# ---------------------------------------------------------------------------


def test_download_failure_falls_back_to_render(monkeypatch):
    # Review F14: render-on-download-failure is now opt-in via
    # prefer_render_on_download_failure (default off). With it enabled, a failed
    # GET still falls back to a render.
    url = "https://blocked.gov"
    monkeypatch.setattr(fetcher, "_download", _download_raising())
    monkeypatch.setattr(
        fetcher, "render_url", lambda u, timeout, session=None: _rendered_page(u)
    )

    page = fetcher.scrape_url(
        url, force_refresh=True, prefer_render_on_download_failure=True
    )

    assert page.text == "RENDERED"
    assert page.fetch_metadata.fetch_method == "render"


def test_download_failure_no_render_by_default(monkeypatch):
    # Review F14: with the default (prefer_render_on_download_failure=False), a
    # failed GET must NOT launch a render — it returns the failure page even
    # when prefer_render_on_empty is True.
    url = "https://blocked.gov"
    monkeypatch.setattr(fetcher, "_download", _download_raising())
    monkeypatch.setattr(fetcher, "render_url", _boom)

    page = fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=True)

    assert page.text == ""
    assert page.content_type == "unknown"
    assert page.fetch_metadata.fetch_method == "html"


def test_download_failure_returns_failure_page_when_render_disabled(monkeypatch):
    url = "https://blocked.gov"
    monkeypatch.setattr(fetcher, "_download", _download_raising())
    monkeypatch.setattr(fetcher, "render_url", _boom)

    page = fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)

    assert page.text == ""
    assert page.content_type == "unknown"
    assert page.fetch_metadata.fetch_method == "html"
    assert page.fetch_metadata.http_status is None


def test_empty_text_triggers_render_fallback(monkeypatch):
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "")
    monkeypatch.setattr(
        fetcher, "render_url", lambda u, timeout, session=None: _rendered_page(u)
    )

    page = fetcher.scrape_url("https://x.gov", force_refresh=True, prefer_render_on_empty=True)

    assert page.text == "RENDERED"


def test_empty_text_render_failure_surfaces_deterministic_empty(monkeypatch):
    # Deterministic path empty + render fallback itself fails → surface the
    # deterministic empty result (not a failure page).
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "")
    monkeypatch.setattr(fetcher, "render_url", _boom)

    page = fetcher.scrape_url("https://x.gov", force_refresh=True, prefer_render_on_empty=True)

    assert page.text == ""
    assert page.content_type == "html"
    assert page.fetch_metadata.fetch_method == "html"


# ---------------------------------------------------------------------------
# Caching policy (F17) + redirect attribution
# ---------------------------------------------------------------------------


def test_successful_page_is_cached(monkeypatch):
    url = "https://x.gov/keep"
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "TEXT")

    fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)

    assert os.path.exists(fetcher._cache_path(url))


def test_empty_text_page_is_not_cached(monkeypatch):
    # Review F17: an empty-text page must not be frozen into the shared cache.
    url = "https://x.gov/empty"
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "")

    page = fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)

    assert page.text == ""
    assert not os.path.exists(fetcher._cache_path(url))


def test_url_preserved_despite_redirect(monkeypatch):
    # pipeline-spec §1: "do not silently redirect-and-attribute".
    url = "https://x.gov/start"
    monkeypatch.setattr(
        fetcher, "_download", _download_returning(final_url="https://x.gov/redirected")
    )
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "TEXT")

    page = fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)

    assert page.url == url
    assert page.fetch_metadata.final_url == "https://x.gov/redirected"


# ---------------------------------------------------------------------------
# Stage-4 concurrency thread-safety (2026-07)
# ---------------------------------------------------------------------------


def test_get_session_is_thread_local():
    """Each thread gets its own requests.Session (not the shared, unsafe one),
    with identical headers."""
    import threading

    main_session = fetcher._get_session()
    other: dict[str, object] = {}

    def grab() -> None:
        other["session"] = fetcher._get_session()

    t = threading.Thread(target=grab)
    t.start()
    t.join()

    assert fetcher._get_session() is main_session  # stable within a thread
    assert other["session"] is not main_session  # distinct across threads
    assert other["session"].headers["user-agent"] == main_session.headers["user-agent"]


def test_cache_write_is_sharded_and_gzipped():
    """Writes land at ``cache/<md5[:2]>/page_v2_<md5>.json.gz`` (storage-layout-v2
    §B3) — 256-way fanout over the unchanged cache key, gzip-encoded — and never
    at the pre-fanout flat path."""
    url = "https://x.gov/sharded"
    fetcher._save(_rendered_page(url, text="SHARDED BODY TEXT"))

    digest = hashlib.md5(url.encode("utf-8")).hexdigest()
    expected = Path(config.CACHE_DIR) / digest[:2] / f"page_v2_{digest}.json.gz"

    assert Path(fetcher._cache_path(url)) == expected
    assert expected.exists()
    # Real gzip member, not a plain file with a .gz name.
    assert expected.read_bytes()[:2] == b"\x1f\x8b"
    with gzip.open(expected, "rt", encoding="utf-8") as f:
        assert "SHARDED BODY TEXT" in f.read()
    # Writes go sharded-gzipped only — nothing is written to the legacy path.
    assert not Path(fetcher._legacy_cache_path(url)).exists()


def test_cache_bytes_are_deterministic_for_identical_input():
    """Identical input must produce byte-identical gzip output (§A1): the header's
    mtime and filename fields are both pinned. Without the filename pin GzipFile
    infers it from the temp file's name, which carries pid + thread id and would
    make the cached bytes vary by writer."""
    url = "https://x.gov/deterministic"
    page = _rendered_page(url, text="STABLE BODY TEXT FOR HASHING")

    fetcher._save(page)
    first = Path(fetcher._cache_path(url)).read_bytes()
    os.remove(fetcher._cache_path(url))
    fetcher._save(page)
    second = Path(fetcher._cache_path(url)).read_bytes()

    assert first == second
    # mtime field (header bytes 4:8) pinned to zero rather than "now".
    assert first[4:8] == b"\x00\x00\x00\x00"


def test_legacy_flat_cache_entry_still_reads(monkeypatch):
    """A cache entry written before the §B3 fanout — flat path, uncompressed —
    must still be served, so an existing warm cache is not invalidated. There is
    no migration script by design."""
    url = "https://x.gov/legacy"
    legacy = Path(fetcher._legacy_cache_path(url))
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        _rendered_page(url, text="FROM_LEGACY_FLAT").model_dump_json(), encoding="utf-8"
    )

    assert not Path(fetcher._cache_path(url)).exists()
    assert fetcher._load(url).text == "FROM_LEGACY_FLAT"

    # And through the real entrypoint: a legacy hit short-circuits the download.
    monkeypatch.setattr(fetcher, "_download", _boom)
    assert fetcher.scrape_url(url).text == "FROM_LEGACY_FLAT"


def test_legacy_read_fallback_is_not_a_write_path():
    """Serving a legacy hit must not rewrite it into the sharded layout — the
    fallback is read-only (the flat remainder ages out naturally)."""
    url = "https://x.gov/legacy-noconvert"
    legacy = Path(fetcher._legacy_cache_path(url))
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        _rendered_page(url, text="FROM_LEGACY_FLAT").model_dump_json(), encoding="utf-8"
    )

    fetcher._load(url)

    assert not Path(fetcher._cache_path(url)).exists()
    assert legacy.exists()


def test_sharded_entry_wins_over_legacy_flat():
    """With both present the sharded-gzipped entry is authoritative — it is the
    only one writes can have refreshed."""
    url = "https://x.gov/both"
    legacy = Path(fetcher._legacy_cache_path(url))
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        _rendered_page(url, text="STALE_LEGACY").model_dump_json(), encoding="utf-8"
    )
    fetcher._save(_rendered_page(url, text="FRESH_SHARDED"))

    assert fetcher._load(url).text == "FRESH_SHARDED"


def test_legacy_flat_entry_respects_min_chars_floor():
    """The F17 below-floor rule applies to legacy hits too: a short cached page
    must read as a miss so the render path re-runs, rather than the fallback
    becoming a way for pre-floor entries to freeze cross-run."""
    url = "https://x.gov/legacy-short"
    legacy = Path(fetcher._legacy_cache_path(url))
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        _rendered_page(url, text="tiny").model_dump_json(), encoding="utf-8"
    )

    assert fetcher._load(url, min_chars=1) is not None
    assert fetcher._load(url, min_chars=500) is None


def test_save_atomic_write_survives_concurrent_readers(monkeypatch):
    """The shared page cache must never let a reader observe a torn/partial file
    under concurrent writers (else model_validate_json raises and is swallowed
    upstream as scrape_failed — silent evidence loss). Atomic temp+os.replace."""
    import threading

    url = "https://x.gov/concurrent"
    page = _rendered_page(url, text="stable body text well above the floor")
    errors: list[Exception] = []

    def writer() -> None:
        for _ in range(25):
            fetcher._save(page)

    def reader() -> None:
        for _ in range(25):
            try:
                cached = fetcher._load(url)
                if cached is not None:
                    assert cached.text == "stable body text well above the floor"
            except Exception as exc:  # noqa: BLE001 - a torn read is the failure
                errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(4)] + [
        threading.Thread(target=reader) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    # No leftover temp files after every writer finished. rglob, not glob: under
    # the §B3 fanout the temp file is created in the shard dir alongside its
    # destination, so a root-level glob would pass vacuously and stop testing
    # anything.
    assert list(Path(config.CACHE_DIR).rglob("*.tmp.*")) == []
