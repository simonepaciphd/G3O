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
import requests
from tenacity import retry, stop_after_attempt, wait_none

from g3o.common import attrition, scrape_telemetry
from g3o.common import config as _config
from g3o.common.artifact_io import artifact_exists
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
    assert not artifact_exists(artifact)


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


# ---------------------------------------------------------------------------
# What refused us — the status code, recorded (2026-08-30)
# ---------------------------------------------------------------------------
#
# Across the anglophone 12k's 6,719 ``scrape_failed`` rows a 403/406 bot-block,
# a connect timeout, a DNS failure and a TLS error were indistinguishable: the
# hard-failure path wrote no telemetry row at all, and neither ledger carried an
# HTTP status. That is why the school-district census could only reach "91.7%
# bot-blocks" by re-probing 60 URLs by hand.


def _http_error(status: int) -> Exception:
    """A ``requests`` refusal, built the way ``raise_for_status`` builds one."""
    response = requests.Response()
    response.status_code = status
    response.url = _URL
    return requests.HTTPError(f"{status} Client Error", response=response)


def _download_raising_exc(exc: BaseException):
    def _f(url):
        raise exc

    return _f


def _failed_telemetry(run_dir) -> dict:
    recs = [
        r for r in scrape_telemetry.read_records(run_dir)
        if r["outcome"] == scrape_telemetry.OUTCOME_SCRAPE_FAILED
        and r.get("url") == _URL
    ]
    assert len(recs) == 1, f"expected one scrape_failed telemetry row; got {recs}"
    return recs[0]


def _scrape_once(run_dir, monkeypatch, exc: BaseException):
    monkeypatch.setattr(fetcher, "_download", _download_raising_exc(exc))
    monkeypatch.setattr(fetcher, "render_url", _boom)
    ps._run_scrape(
        run_dir, [{"master_row_id": "580"}], {_INST_ID: [_URL]},
        respect_robots=False, host_delay_seconds=0,
        render_on_download_failure=False,
    )


def test_a_refused_fetch_writes_a_telemetry_row_with_its_status(tmp_path, monkeypatch):
    """The regression: this path wrote NO telemetry row, so the ledger's own
    contract — one record per attempt regardless of outcome — did not hold on
    the one outcome the egress question turns on."""
    run_dir = tmp_path / "runs" / "r1"
    scrape_telemetry._reset_cache()

    _scrape_once(run_dir, monkeypatch, _http_error(403))

    rec = _failed_telemetry(run_dir)
    assert rec["http_status"] == 403
    assert rec["error_class"] == "HTTPError"


def test_a_timeout_records_a_null_status_rather_than_no_status(tmp_path, monkeypatch):
    """None is an answer, not a gap. A connect timeout never gets a status line,
    and recording that explicitly is what separates it from a 403."""
    run_dir = tmp_path / "runs" / "r1"
    scrape_telemetry._reset_cache()

    _scrape_once(run_dir, monkeypatch, requests.ConnectTimeout("timed out"))

    rec = _failed_telemetry(run_dir)
    assert "http_status" in rec and rec["http_status"] is None
    assert rec["error_class"] == "ConnectTimeout"


def test_the_four_failures_are_now_distinguishable(tmp_path, monkeypatch):
    """406, timeout, DNS and TLS: four rows that used to read identically."""
    cases = {
        "block": (_http_error(406), 406, "HTTPError"),
        "timeout": (requests.ReadTimeout("read timed out"), None, "ReadTimeout"),
        "dns": (requests.ConnectionError("NameResolutionError"), None, "ConnectionError"),
        "tls": (requests.exceptions.SSLError("CERTIFICATE_VERIFY_FAILED"), None, "SSLError"),
    }
    for name, (exc, status, klass) in cases.items():
        run_dir = tmp_path / "runs" / name
        scrape_telemetry._reset_cache()
        attrition._reset_cache()

        _scrape_once(run_dir, monkeypatch, exc)

        rec = _failed_telemetry(run_dir)
        assert rec["http_status"] == status, name
        assert rec["error_class"] == klass, name


def test_the_status_is_read_through_tenacitys_retry_wrapper(tmp_path, monkeypatch):
    """`_download` is `@retry` without `reraise`, so what escapes is a
    RetryError — a class name that says only that we gave up. Recording it
    would have replaced one useless answer with another."""
    run_dir = tmp_path / "runs" / "r1"
    scrape_telemetry._reset_cache()
    inner = _http_error(403)

    def _f(url):
        raise inner

    # The real decorator, so the wrapper under test is the one production makes.
    wrapped = retry(stop=stop_after_attempt(2), wait=wait_none())(_f)
    monkeypatch.setattr(fetcher, "_download", wrapped)
    monkeypatch.setattr(fetcher, "render_url", _boom)
    ps._run_scrape(
        run_dir, [{"master_row_id": "580"}], {_INST_ID: [_URL]},
        respect_robots=False, host_delay_seconds=0,
        render_on_download_failure=False,
    )

    rec = _failed_telemetry(run_dir)
    assert rec["http_status"] == 403
    assert rec["error_class"] == "HTTPError"


def test_a_double_failure_names_both_classes(tmp_path, monkeypatch):
    """Download and render both failed: the render's class is recorded too, so
    a render-fallback failure is not read as a bare download refusal."""
    run_dir = tmp_path / "runs" / "r1"
    scrape_telemetry._reset_cache()
    monkeypatch.setattr(fetcher, "_download", _download_raising_exc(_http_error(403)))

    def _render_raising(u, timeout, session=None):
        raise RuntimeError("RENDER-BOOM")

    monkeypatch.setattr(fetcher, "render_url", _render_raising)
    ps._run_scrape(
        run_dir, [{"master_row_id": "580"}], {_INST_ID: [_URL]},
        respect_robots=False, host_delay_seconds=0,
        render_on_download_failure=True,
    )

    rec = _failed_telemetry(run_dir)
    assert rec["http_status"] == 403
    assert rec["error_class"] == "HTTPError"
    assert rec["render_error_class"] == "RuntimeError"


def test_the_extractors_never_raise_inside_a_failure_handler(tmp_path):
    """They run on the run's worst path. A None, a bare exception and a
    response-less error must all come back as answers, not as a second fault."""
    assert fetcher.http_status_from_exception(None) is None
    assert fetcher.error_class_of(None) is None
    assert fetcher.http_status_from_exception(RuntimeError("no response")) is None
    assert fetcher.error_class_of(RuntimeError("x")) == "RuntimeError"

    # A cause chain: the status is on the exception two links down.
    outer = RuntimeError("wrapper")
    outer.__cause__ = _http_error(429)
    assert fetcher.http_status_from_exception(outer) == 429

    # A self-referential chain must terminate rather than spin.
    loop = RuntimeError("loop")
    loop.__cause__ = loop
    assert fetcher.http_status_from_exception(loop) is None
