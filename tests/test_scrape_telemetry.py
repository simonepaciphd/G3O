"""Per-request scrape telemetry ledger (politeness audit, 2026-07-27).

``g3o.common.scrape_telemetry`` is the ledger a per-host politeness audit
(``scrape_host_delay_seconds``) is reconstructed from after the fact, since
``HostThrottle`` itself only ever compares against an in-memory
``time.monotonic()`` clock and keeps no record. These tests pin: the record
shape (real timestamp, hostname, request id), that concurrent writers never
tear a line (mirrors ``test_attrition.py``), and that
``g3o.scrape.fetcher.scrape_url``'s ``on_request`` hook fires exactly once per
real outbound attempt — never on a cache hit — matching the ``on_render_attempt``
convention in ``test_scrape_render_on_empty.py``.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

from g3o.common import config as _config
from g3o.common import scrape_telemetry
from g3o.run import presweep as ps
from g3o.scrape import fetcher
from g3o.scrape.render import FetchMetadata, RenderedPage, utc_today_iso

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def test_record_shape(tmp_path: Path) -> None:
    scrape_telemetry.record(
        tmp_path, institution_id="INST-0001", stage="scrape",
        url="https://example.gov/a",
    )
    recs = scrape_telemetry.read_records(tmp_path)
    assert len(recs) == 1
    rec = recs[0]
    assert _TS_RE.match(rec["ts"]), rec["ts"]
    assert rec["hostname"] == "example.gov"
    assert rec["url"] == "https://example.gov/a"
    assert rec["institution_id"] == "INST-0001"
    assert rec["stage"] == "scrape"
    assert isinstance(rec["request_id"], str) and rec["request_id"]


def test_record_never_dedups_same_url(tmp_path: Path) -> None:
    """Unlike attrition, every call is a distinct real request — no dedup."""
    for _ in range(3):
        scrape_telemetry.record(
            tmp_path, institution_id="INST-0001", stage="scrape",
            url="https://example.gov/a",
        )
    recs = scrape_telemetry.read_records(tmp_path)
    assert len(recs) == 3
    assert len({r["request_id"] for r in recs}) == 3


def test_record_distinct_writers_all_written_under_concurrency(tmp_path: Path) -> None:
    """Mirrors test_attrition.py: concurrent appends never tear a JSONL line."""

    def rec(i: int) -> None:
        scrape_telemetry.record(
            tmp_path, institution_id=f"I{i}", stage="scrape",
            url=f"https://x.gov/{i}",
        )

    threads = [threading.Thread(target=rec, args=(i,)) for i in range(60)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    recs = scrape_telemetry.read_records(tmp_path)  # torn line → json.loads raises
    assert len({r["institution_id"] for r in recs}) == 60


# ---------------------------------------------------------------------------
# fetcher.scrape_url on_request hook
# ---------------------------------------------------------------------------

HTML_BYTES = b"<html><head><title>T</title></head><body>hi</body></html>"


def _isolate_cache(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(_config, "CACHE_DIR", tmp_path / "cache")


def _download_returning():
    def _f(url):
        return (HTML_BYTES, "text/html", 200, "https://x.gov", 5)

    return _f


def test_on_request_fires_once_for_deterministic_fetch(monkeypatch, tmp_path):
    _isolate_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "A" * 60)
    events: list[str] = []

    fetcher.scrape_url(
        "https://x.gov", force_refresh=True, on_request=events.append
    )

    assert events == ["https://x.gov"]


def test_on_request_not_fired_on_cache_hit(monkeypatch, tmp_path):
    _isolate_cache(monkeypatch, tmp_path)
    url = "https://cached.gov/p"
    fetcher._save(
        RenderedPage(
            url=url, text="FROM_CACHE", title="t", content_type="html",
            fetch_metadata=FetchMetadata(
                access_date=utc_today_iso(), http_status=200, final_url=url,
                fetch_method="html", elapsed_ms=1, wait_for=None,
            ),
        )
    )
    monkeypatch.setattr(fetcher, "_download", lambda u: (_ for _ in ()).throw(
        AssertionError("_download must not be called on a cache hit")
    ))
    events: list[str] = []

    page = fetcher.scrape_url(url, on_request=events.append)

    assert page.text == "FROM_CACHE"
    assert events == []


def test_on_request_fires_for_render_fallback(monkeypatch, tmp_path):
    _isolate_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "short")

    def _rendered(u, timeout, session=None):
        return RenderedPage(
            url=u, text="RENDERED " * 10, title="r", content_type="render",
            fetch_metadata=FetchMetadata(
                access_date=utc_today_iso(), http_status=200, final_url=u,
                fetch_method="render", elapsed_ms=1, wait_for=None,
            ),
        )

    monkeypatch.setattr(fetcher, "render_url", _rendered)
    events: list[str] = []

    fetcher.scrape_url(
        "https://x.gov", force_refresh=True, empty_page_min_chars=50,
        on_request=events.append,
    )

    # Once for the deterministic GET, once for the render fallback it triggers.
    assert events == ["https://x.gov", "https://x.gov"]


# ---------------------------------------------------------------------------
# _run_scrape wiring — the ledger lands under the run dir
# ---------------------------------------------------------------------------

_INST_ID = "INST-0000580"
_URL = "https://www.mcit.gov.qa/en/about-us"


def test_run_scrape_writes_telemetry_ledger(tmp_path, monkeypatch):
    _isolate_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "B" * 200)
    monkeypatch.setattr(fetcher, "render_url", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("render must not fire on real content")
    ))
    run_dir = tmp_path / "runs" / "r1"
    sample = [{"master_row_id": "580"}]
    triaged = {_INST_ID: [_URL]}

    ps._run_scrape(run_dir, sample, triaged, respect_robots=False, host_delay_seconds=0)

    recs = scrape_telemetry.read_records(run_dir)
    assert len(recs) == 1
    assert recs[0]["url"] == _URL
    assert recs[0]["institution_id"] == _INST_ID
    assert recs[0]["stage"] == "scrape"
    assert recs[0]["hostname"] == "www.mcit.gov.qa"
