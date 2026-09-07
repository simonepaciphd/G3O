"""Stage-4 dead-host cost (PI-approved 2026-09-06, options A and B).

Measured on ``r20260903T120740Z-362c``: scrape was 51.3 h of a 56.1 h run with
12 saturated workers, and 67% of the stage's 2.21M worker-seconds were connect
timeouts retried three times at 30 s each against hosts that never answered
anywhere in the run (57 of 15,462 events on a host with any success).

A. The fetcher retries only what a retry can change (connection errors,
   timeouts, 429, 5xx), splits the timeout into connect/read, and records how
   many attempts each fetch took so the retry-recovery rate is measurable.
B. A run-scoped per-host circuit breaker skips a host's remaining URLs after
   ``scrape_host_failure_threshold`` connect-level failures, recording each
   skipped URL under ``host_unreachable`` — a member of ``_FAILURE_REASONS``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests
from tenacity import RetryError, wait_none

from g3o.common import attrition, config, scrape_telemetry
from g3o.report import outcomes
from g3o.scrape import fetcher
from g3o.scrape.breaker import TRIPPING_ERROR_CLASSES, HostBreaker
from tests.test_presweep import (
    _build_master,
    _f14b_page,
    _make_config,
    _write_master_csv,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    attrition._reset_cache()
    scrape_telemetry._reset_cache()
    yield
    attrition._reset_cache()
    scrape_telemetry._reset_cache()


# --------------------------------------------------------------------------
# A. retry predicate, timeout split, attempt count
# --------------------------------------------------------------------------


def _http_error(status: int) -> requests.exceptions.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    return requests.exceptions.HTTPError(f"{status}", response=resp)


@pytest.mark.parametrize(
    "exc, retryable",
    [
        (_http_error(403), False),
        (_http_error(404), False),
        (_http_error(406), False),
        (_http_error(429), True),
        (_http_error(503), True),
        (requests.exceptions.ConnectTimeout("x"), True),
        (requests.exceptions.ReadTimeout("x"), True),
        (requests.exceptions.ConnectionError("x"), True),
        (requests.exceptions.SSLError("x"), False),
        (requests.exceptions.MissingSchema("x"), False),
    ],
)
def test_is_retryable_matches_the_approved_policy(exc, retryable):
    assert fetcher._is_retryable(exc) is retryable


class _FakeSession:
    def __init__(self, exc: BaseException | None = None):
        self.exc = exc
        self.calls: list[dict[str, Any]] = []

    def get(self, url, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b"<html><body>" + b"x" * 200 + b"</body></html>"
        resp.headers["content-type"] = "text/html"
        resp.url = url
        return resp


def _download_no_sleep():
    # Same predicate, same stop, no wall-clock backoff.
    return fetcher._download.retry_with(wait=wait_none())


def test_a_refusal_is_fetched_once_and_raises_as_itself(monkeypatch):
    session = _FakeSession(_http_error(403))
    monkeypatch.setattr(fetcher, "_get_session", lambda: session)
    with pytest.raises(requests.exceptions.HTTPError):
        _download_no_sleep()("https://blocked.example/")
    assert len(session.calls) == 1
    assert fetcher.download_attempts() == 1


def test_a_connect_timeout_is_still_retried_three_times(monkeypatch):
    session = _FakeSession(requests.exceptions.ConnectTimeout("x"))
    monkeypatch.setattr(fetcher, "_get_session", lambda: session)
    with pytest.raises(RetryError):
        _download_no_sleep()("https://dead.example/")
    assert len(session.calls) == 3
    assert fetcher.download_attempts() == 3


def test_download_passes_a_connect_read_timeout_tuple(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(fetcher, "_get_session", lambda: session)
    _download_no_sleep()("https://live.example/")
    assert session.calls[0]["timeout"] == (config.CONNECT_TIMEOUT, config.REQUEST_TIMEOUT)
    assert config.CONNECT_TIMEOUT < config.REQUEST_TIMEOUT


def test_attempt_count_is_reset_per_scrape_and_zero_on_cache_hit(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(fetcher, "_get_session", lambda: session)
    url = "https://live.example/page"
    fetcher.scrape_url(url, empty_page_min_chars=1)
    assert fetcher.download_attempts() == 1
    # Second call is served from the disk cache: no GET, so 0 — not a stale 1.
    fetcher.scrape_url(url, empty_page_min_chars=1)
    assert fetcher.download_attempts() == 0
    assert len(session.calls) == 1


# --------------------------------------------------------------------------
# B. the breaker, in isolation
# --------------------------------------------------------------------------


def test_breaker_opens_at_threshold_on_connect_level_failures_only():
    b = HostBreaker(threshold=2)
    u = "https://dead.example/a"
    assert b.record_failure(u, "HTTPError") is False        # a refusal never trips
    assert b.record_failure(u, "SSLError") is False
    assert b.record_failure(u, "ReadTimeout") is False
    assert b.failures(u) == 0
    assert b.record_failure(u, "ConnectTimeout") is False   # 1 of 2
    assert not b.is_open(u)
    assert b.record_failure(u, "ConnectionError") is True   # 2 of 2: trips
    assert b.is_open("http://dead.example/other")           # scheme-agnostic host key
    assert b.record_failure(u, "ConnectTimeout") is False   # already open: no re-trip
    assert not b.is_open("https://alive.example/")
    assert b.open_hosts() == frozenset({"dead.example"})


def test_breaker_success_resets_the_count():
    b = HostBreaker(threshold=2)
    u = "https://flaky.example/a"
    b.record_failure(u, "ConnectTimeout")
    b.record_success(u)
    assert b.failures(u) == 0
    b.record_failure(u, "ConnectTimeout")
    assert not b.is_open(u)


def test_breaker_rejects_a_zero_threshold():
    with pytest.raises(ValueError):
        HostBreaker(threshold=0)
    assert TRIPPING_ERROR_CLASSES == {"ConnectTimeout", "ConnectionError"}


# --------------------------------------------------------------------------
# B. the breaker, through the Stage 4 runner
# --------------------------------------------------------------------------


def _two_institution_plan(tmp_path: Path):
    from g3o.run import presweep as ps

    rows = _build_master(n_strata=1, rows_per_stratum=2)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    cfg = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=2)
    plan = ps.plan_run(cfg)
    return plan, list(plan.manifest["institutions"])


def _dead_host_scrape(calls: list[str]):
    """A ``scrape_url`` stand-in: ``dead.example`` times out at connect level
    (through the failure hook, as the real fetcher reports it), everything else
    returns a page."""

    def _fake(url: str, **kwargs: Any):
        calls.append(url)
        if "dead.example" in url:
            kwargs["on_scrape_failure"](
                url=url,
                download_error=requests.exceptions.ConnectTimeout("connect"),
                render_error=None,
            )
            return fetcher._failure_page(url, attempted_method="html")
        return _f14b_page(url)

    return _fake


def _run(plan, triaged, *, scrape, threshold, workers=1):
    from g3o.run import presweep as ps

    class _Robots:
        def allowed(self, url: str) -> bool:
            return True

        def crawl_delay(self, url: str):
            return None

    saved = ps.stage_scrape.scrape_url
    ps.stage_scrape.scrape_url = scrape  # type: ignore[assignment]
    try:
        return ps._run_scrape(
            plan.run_dir, plan.sample, triaged,
            respect_robots=True, robots=_Robots(), host_delay_seconds=0.0,
            host_failure_threshold=threshold, max_workers=workers,
        )
    finally:
        ps.stage_scrape.scrape_url = saved  # type: ignore[assignment]


def _rows(run_dir: Path, reason: str) -> list[dict[str, Any]]:
    return [r for r in attrition.read_records(run_dir) if r["reason"] == reason]


def test_stage4_skips_a_dead_host_after_the_threshold_and_records_every_skip(tmp_path):
    from g3o.run.presweep.stage_scrape import REASON_HOST_UNREACHABLE

    plan, (inst_a, inst_b) = _two_institution_plan(tmp_path)
    dead = [f"https://dead.example/{i}" for i in range(5)]
    alive = ["https://alive.example/x"]
    calls: list[str] = []
    out = _run(
        plan, {inst_a: dead + alive, inst_b: dead[:2]},
        scrape=_dead_host_scrape(calls), threshold=2,
    )

    # Two attempts on the dead host, then nothing — across BOTH institutions.
    assert [u for u in calls if "dead.example" in u] == dead[:2]
    assert alive[0] in calls
    assert [p.url for p in out[inst_a]] == alive
    assert out[inst_b] == []

    skipped = _rows(plan.run_dir, REASON_HOST_UNREACHABLE)
    assert sorted(r["url"] for r in skipped) == sorted(dead[2:] + dead[:2])
    assert {r["institution_id"] for r in skipped} == {inst_a, inst_b}
    assert all("threshold=2" in r["detail"] for r in skipped)
    # The two attempted URLs are on the ledger as real failures, not skips.
    failed = _rows(plan.run_dir, "scrape_failed")
    assert sorted(r["url"] for r in failed) == dead[:2]

    tel = {(r["institution_id"], r["url"]): r for r in scrape_telemetry.read_records(plan.run_dir)}
    for u in dead[2:]:
        assert tel[(inst_a, u)]["outcome"] == scrape_telemetry.OUTCOME_HOST_UNREACHABLE
    for u in dead[:2]:
        assert tel[(inst_b, u)]["outcome"] == scrape_telemetry.OUTCOME_HOST_UNREACHABLE
        assert tel[(inst_a, u)]["outcome"] == scrape_telemetry.OUTCOME_SCRAPE_FAILED
        assert tel[(inst_a, u)]["error_class"] == "ConnectTimeout"
        assert "attempts" in tel[(inst_a, u)]
    assert tel[(inst_a, alive[0])]["outcome"] == scrape_telemetry.OUTCOME_SUCCEEDED
    assert "attempts" in tel[(inst_a, alive[0])]
    assert REASON_HOST_UNREACHABLE == scrape_telemetry.OUTCOME_HOST_UNREACHABLE


def test_stage4_threshold_none_attempts_every_url(tmp_path):
    from g3o.run.presweep.stage_scrape import REASON_HOST_UNREACHABLE

    plan, (inst_a, _) = _two_institution_plan(tmp_path)
    dead = [f"https://dead.example/{i}" for i in range(4)]
    calls: list[str] = []
    _run(plan, {inst_a: dead}, scrape=_dead_host_scrape(calls), threshold=None)
    assert calls == dead
    assert _rows(plan.run_dir, REASON_HOST_UNREACHABLE) == []


def test_host_unreachable_is_a_failure_reason_and_reports_processing_failed(tmp_path):
    """The membership is the point of the reason's existence: without it the
    skip is on the ledger and the institution publishes NO_EVIDENCE_FOUND."""
    from tests.test_outcomes import ALL_STAGES, _discovery, _make_run, _only, _triage

    assert "host_unreachable" in outcomes._FAILURE_REASONS

    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=ALL_STAGES)
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=2)
    for i in range(2):
        attrition.record(
            run_dir, institution_id="INST-0000001", stage="scrape",
            reason="host_unreachable", url=f"https://dead.example/{i}",
            detail="failures=2;threshold=2",
        )
    rec = _only(run_dir)
    assert rec["final_status"] == "PROCESSING_FAILED"
    assert "scrape:host_unreachable" in rec["reason"]


def test_presweep_config_rejects_a_zero_threshold(tmp_path):
    from g3o.run.presweep import PresweepConfig

    rows = _build_master(n_strata=1, rows_per_stratum=1)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    with pytest.raises(ValueError, match="scrape_host_failure_threshold"):
        PresweepConfig(
            run_id="t", runs_dir=tmp_path / "runs", master_csv=master,
            sample_size=1, seed=1, dry_run=True, scrape_host_failure_threshold=0,
        )
