"""Stage-4 fetcher failure semantics (fix/fetcher-failure-semantics).

Two failure modes that previously produced an empty page indistinguishable
from a normal successful scrape — with no ``scrape_failed`` attrition and, in
the double-failure case, both underlying exceptions discarded:

  1. The HTTP GET fails after all retries and render-on-download-failure is off
     (the Stage 4 default): ``scrape_url`` returns a no-text Q10 failure page,
     and the runner used to write it as a normal artifact with no attrition.
  2. The GET fails, render fallback is enabled, and the render also raises:
     both exceptions were consumed and only a bare ``render_attempted`` record
     survived, carrying neither message.

Decision Q10 is preserved — ``scrape_url`` still returns a ``RenderedPage`` on
every path — so accounting flows through the new ``on_scrape_failure`` hook:
the runner records a ``scrape_failed`` entry (with both exception messages) and
drops the page. These exercise the full Stage 4 path (``_run_scrape`` ->
``_scrape_one`` -> ``scrape_url``), not ``scrape_url`` in isolation.

Fixtures mirror test_scrape_render_on_empty.py.
"""

from __future__ import annotations

import json

import pytest

from g3o.common import attrition
from g3o.common import config as _config
from g3o.extract.batch import url_hash
from g3o.run import presweep as ps
from g3o.scrape import fetcher
from tests._layout import inst_dir as inst_dir_of

_INST_ID = "INST-0000580"
_URL = "https://www.mcit.gov.qa/en/about-us"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Isolate the fetcher's on-disk cache and reset the attrition dedup cache."""
    monkeypatch.setattr(_config, "CACHE_DIR", tmp_path / "cache")
    attrition._reset_cache()
    yield
    attrition._reset_cache()


def _download_raising(msg: str):
    def _f(url):
        raise RuntimeError(msg)

    return _f


def _boom(*_a, **_k):
    raise AssertionError("render_url must not be called on this path")


def test_download_failure_records_scrape_failed_not_phantom_success(tmp_path, monkeypatch):
    """Issue 1: a failed download with render off (Stage 4 default) produces a
    durable scrape_failed attrition record and is NOT surfaced as a successful
    scrape (no phantom page, no artifact on disk)."""
    run_dir = tmp_path / "runs" / "r1"
    monkeypatch.setattr(fetcher, "_download", _download_raising("DOWNLOAD-BOOM"))
    # render_on_download_failure is off here, so the renderer must never run.
    monkeypatch.setattr(fetcher, "render_url", _boom)

    sample = [{"master_row_id": "580"}]
    triaged = {_INST_ID: [_URL]}
    out = ps._run_scrape(
        run_dir, sample, triaged,
        respect_robots=False, host_delay_seconds=0,
        render_on_download_failure=False,
    )

    recs = attrition.read_records(run_dir)
    failed = [
        r for r in recs
        if r["reason"] == "scrape_failed" and r.get("url") == _URL
    ]
    assert len(failed) == 1, f"expected one scrape_failed record; ledger: {recs}"
    assert "DOWNLOAD-BOOM" in failed[0]["detail"]

    # Not surfaced as a normal successful scrape.
    assert out[_INST_ID] == []
    artifact = inst_dir_of(run_dir, _INST_ID) / "scrape" / f"{url_hash(_URL)}.json"
    assert not artifact.exists()


def test_download_then_render_both_fail_preserve_both_exceptions(tmp_path, monkeypatch):
    """Issue 2: download fails, render fallback is enabled and also raises —
    both underlying exceptions are preserved in the durable failure record and
    the double failure is not surfaced as a successful scrape."""
    run_dir = tmp_path / "runs" / "r1"
    monkeypatch.setattr(fetcher, "_download", _download_raising("DOWNLOAD-BOOM"))

    def _render_raising(u, timeout, session=None):
        raise RuntimeError("RENDER-BOOM")

    monkeypatch.setattr(fetcher, "render_url", _render_raising)

    sample = [{"master_row_id": "580"}]
    triaged = {_INST_ID: [_URL]}
    out = ps._run_scrape(
        run_dir, sample, triaged,
        respect_robots=False, host_delay_seconds=0,
        render_on_download_failure=True,
    )

    recs = attrition.read_records(run_dir)
    failed = [
        r for r in recs
        if r["reason"] == "scrape_failed" and r.get("url") == _URL
    ]
    assert len(failed) == 1, f"expected one scrape_failed record; ledger: {recs}"
    # Both underlying exceptions are captured in the durable failure record.
    assert "DOWNLOAD-BOOM" in failed[0]["detail"]
    assert "RENDER-BOOM" in failed[0]["detail"]

    # A render_attempted telemetry record still exists (render-rate accounting),
    # marked render_failed — the two records are complementary, not duplicated.
    renders = [r for r in recs if r["reason"] == "render_attempted" and r.get("url") == _URL]
    assert len(renders) == 1
    assert renders[0]["outcome"] == "render_failed"

    # The double failure is not surfaced as a successful scrape.
    assert out[_INST_ID] == []
    assert json.dumps(recs)  # ledger is well-formed JSONL
