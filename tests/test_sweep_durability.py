"""An unattended sweep survives a transient fault and a hostile page (PR B).

Three findings from the 2026-08-20 review, grouped because all three decide
whether an unattended n=1000 run finishes rather than needing a babysitter:

- **F5** — a 6th consecutive transient fault on ``poll_batch`` propagated out of
  ``run_chunked_stage`` and killed a multi-hour stage. Observed twice on run
  ``20260802-e2e-100``.
- **F3** — ``_download`` buffered whole response bodies with no cap, once per
  worker thread.
- **F13** — ``_download`` retried *every* exception three times, including the
  406/403 rejections that are ~95% of real scrape failures (issue #90).

The F5 tests assert both directions: the stage must **survive** a transient
fault *and* must still **stop** at ``max_wait``. A fix that removed the death by
removing the bound would pass one and fail the other.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import requests
from openai import APIConnectionError, APITimeoutError, RateLimitError

from g3o.common import batch_client
from g3o.common.batch_client import BatchJob
from g3o.common.run_state import is_done, run_chunked_stage
from tests.test_run_state import _install_stub

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _jobs(n: int = 2) -> list[BatchJob]:
    return [
        BatchJob(custom_id=f"job-{i}", messages=[{"role": "user", "content": "hi"}])
        for i in range(n)
    ]


def _run(tmp_path: Path, jobs: list[BatchJob], **overrides: Any) -> list[str]:
    received: list[str] = []

    def _collect(results):
        received.extend(r.custom_id for r in results)

    kwargs: dict[str, Any] = dict(
        run_id="run-1",
        model="gpt-5-nano",
        poll_interval=0,
        max_wait=10,
        process_chunk_results=_collect,
    )
    kwargs.update(overrides)
    run_chunked_stage(tmp_path, "extract", jobs, **kwargs)
    return received


def _timeout_error() -> APITimeoutError:
    return APITimeoutError(request=httpx.Request("GET", "https://api.test"))


def _connection_error() -> APIConnectionError:
    return APIConnectionError(request=httpx.Request("GET", "https://api.test"))


def _rate_limit_error() -> RateLimitError:
    request = httpx.Request("POST", "https://api.openai.com/v1/batches")
    return RateLimitError(
        message="slow down", response=httpx.Response(429, request=request), body=None
    )


# ---------------------------------------------------------------------------
# F5 — the poll loop absorbs transient faults
# ---------------------------------------------------------------------------


def test_stage_survives_a_transient_poll_fault(tmp_path: Path, monkeypatch) -> None:
    """The fault that used to kill the stage now costs one poll cycle.

    Stubbing ``batch_client.poll_batch`` replaces the decorated function, so
    tenacity is out of the picture here by design: this asserts what
    ``run_chunked_stage`` does when an error escapes the retry wrapper, which is
    exactly the case that killed the two live stages.
    """
    _install_stub(monkeypatch, run_dir=tmp_path, statuses={"batch-1": ["completed"]})
    real_poll = batch_client.poll_batch
    calls = {"n": 0}

    def _flaky_poll(batch_id, *, client=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _timeout_error()
        return real_poll(batch_id, client=client)

    monkeypatch.setattr(batch_client, "poll_batch", _flaky_poll)

    received = _run(tmp_path, _jobs())

    assert sorted(received) == ["job-0", "job-1"]
    assert is_done(tmp_path, "extract")
    assert calls["n"] >= 2, "the failed poll should have been retried, not fatal"


@pytest.mark.parametrize(
    "make_error", [_timeout_error, _connection_error, _rate_limit_error]
)
def test_every_transient_class_is_absorbed(tmp_path: Path, monkeypatch, make_error) -> None:
    """One shared definition of "transient" — batch_client.TRANSIENT_API_ERRORS.

    Parametrised so adding a class to that tuple without teaching the poll loop
    about it cannot pass silently.
    """
    _install_stub(monkeypatch, run_dir=tmp_path, statuses={"batch-1": ["completed"]})
    real_poll = batch_client.poll_batch
    calls = {"n": 0}

    def _flaky_poll(batch_id, *, client=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise make_error()
        return real_poll(batch_id, client=client)

    monkeypatch.setattr(batch_client, "poll_batch", _flaky_poll)
    assert sorted(_run(tmp_path, _jobs())) == ["job-0", "job-1"]


def test_a_permanently_failing_poll_still_stops_at_the_deadline(
    tmp_path: Path, monkeypatch
) -> None:
    """The fix removes the death, not the bound.

    A genuinely unreachable API must still end the stage — at ``max_wait``, with
    the F16 message that tells the operator the batch has *not* ended and a
    re-run will rejoin it. Before the fix the operator got an opaque
    ``APITimeoutError`` traceback instead, precisely when that guidance mattered.
    """
    _install_stub(monkeypatch, run_dir=tmp_path, statuses={"batch-1": ["in_progress"]})

    def _always_fails(batch_id, *, client=None):
        raise _timeout_error()

    monkeypatch.setattr(batch_client, "poll_batch", _always_fails)

    with pytest.raises(RuntimeError) as exc:
        _run(tmp_path, _jobs(), max_wait=0)
    assert "timed out" in str(exc.value)
    assert "have NOT ended" in str(exc.value)


def test_poll_timeout_telemetry_survives_a_failing_poll(
    tmp_path: Path, monkeypatch
) -> None:
    """The F16 telemetry fires on the deadline path even when polls are failing.

    A raise out of the loop used to skip the deadline check entirely, so this
    event — the one that records "the batch is still alive, go rejoin it" — was
    never emitted on exactly the runs that needed it.
    """
    _install_stub(monkeypatch, run_dir=tmp_path, statuses={"batch-1": ["in_progress"]})
    monkeypatch.setattr(
        batch_client, "poll_batch", lambda b, *, client=None: (_ for _ in ()).throw(_timeout_error())
    )

    events: list[dict[str, Any]] = []

    class _Telemetry:
        def emit(self, event: str, **fields: Any) -> None:
            events.append({"event": event, **fields})

    with pytest.raises(RuntimeError):
        _run(tmp_path, _jobs(), max_wait=0, telemetry=_Telemetry())

    assert any(e["event"] == "poll_timeout" for e in events)


def test_a_transient_fetch_failure_is_retried_not_fatal(
    tmp_path: Path, monkeypatch
) -> None:
    """Downloading results is a read too, and nothing is persisted before it.

    ``fetch_results`` is a generator whose inner file read is retryable but whose
    JSONL decode is not, so a truncated download surfaces as a bare
    ``JSONDecodeError``. The chunk's ``fetched_at`` is written only after the
    completeness gate, so abandoning the attempt costs one re-download and cannot
    half-commit.
    """
    _install_stub(monkeypatch, run_dir=tmp_path, statuses={"batch-1": ["completed"]})
    real_fetch = batch_client.fetch_results
    calls = {"n": 0}

    def _flaky_fetch(batch_id, *, client=None, status=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise json.JSONDecodeError("truncated", "", 0)
        yield from real_fetch(batch_id, client=client, status=status)

    monkeypatch.setattr(batch_client, "fetch_results", _flaky_fetch)

    assert sorted(_run(tmp_path, _jobs())) == ["job-0", "job-1"]
    assert is_done(tmp_path, "extract")


def test_the_completeness_gate_is_not_swallowed(tmp_path: Path, monkeypatch) -> None:
    """The new try/except must not soften a deliberate refusal.

    A batch whose results do not reconcile against the plan raises on purpose,
    and that raise sits outside the network accumulation the fix wraps. If the
    except clause were widened to cover it, a partial batch would quietly retry
    forever instead of failing loudly.
    """
    _install_stub(monkeypatch, run_dir=tmp_path, statuses={"batch-1": ["completed"]})

    def _short_fetch(batch_id, *, client=None, status=None):
        yield from ()  # a completed batch that returns nothing

    monkeypatch.setattr(batch_client, "fetch_results", _short_fetch)

    with pytest.raises(RuntimeError) as exc:
        _run(tmp_path, _jobs())
    assert "reconcile" in str(exc.value)


def test_submit_retry_policy_is_left_alone() -> None:
    """The asymmetry is the design: reads absorb, spend-bearing writes do not.

    A poll may be retried against the wall clock because it changes nothing
    server-side. ``submit_batch`` keeps five attempts because a lost response can
    double-create a live batch (review F6a). Pinned so a later "consistency"
    cleanup has to argue with a test.
    """
    assert batch_client._create_input_file.retry.stop.max_attempt_number == 5
    assert batch_client.poll_batch.retry.stop.max_attempt_number == 5


# ---------------------------------------------------------------------------
# F13 — retry transport faults and 5xx, never a rejection
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for requests.Response, enough for _download."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        body: bytes = b"<html><body>hi</body></html>",
        headers: dict[str, str] | None = None,
        chunk_size: int | None = None,
    ) -> None:
        self.status_code = status_code
        self.url = "https://example.gov/page"
        self._body = body
        self._chunk_size = chunk_size
        self.headers = headers if headers is not None else {"content-type": "text/html"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} error", response=self
            )

    def iter_content(self, chunk_size: int = 8192):
        step = self._chunk_size or chunk_size
        for i in range(0, len(self._body), step):
            yield self._body[i : i + step]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _install_session(monkeypatch, responder):
    """Patch fetcher._get_session, the established seam, not the thread-local."""
    from g3o.scrape import fetcher

    calls = {"n": 0}

    class _Session:
        def get(self, url, timeout=None, stream=False):
            calls["n"] += 1
            return responder(url)

    monkeypatch.setattr(fetcher, "_get_session", lambda: _Session())
    return calls


def _no_sleep(monkeypatch) -> None:
    """Neuter tenacity's backoff so a retry test is not a wall-clock test."""
    from tenacity import wait_none

    from g3o.scrape import fetcher

    monkeypatch.setattr(fetcher._download.retry, "wait", wait_none())


def test_a_rejection_is_attempted_once(tmp_path: Path, monkeypatch) -> None:
    """404/403/406 are decisions, not faults — retrying them buys nothing.

    Issue #90 measured 1,385 HTTPErrors on one n=1,000 run, ~95% of them 406/403
    rejections. Under the old predicate-less retry each cost three requests.
    """
    from g3o.scrape import fetcher

    _no_sleep(monkeypatch)
    for status in (403, 404, 406):
        calls = _install_session(
            monkeypatch, lambda url, s=status: _FakeResponse(status_code=s)
        )
        with pytest.raises(requests.exceptions.HTTPError):
            fetcher._download("https://example.gov/gone")
        assert calls["n"] == 1, f"HTTP {status} should not be retried"


def test_a_server_error_is_still_retried(tmp_path: Path, monkeypatch) -> None:
    """5xx is "not right now" — the one HTTP class worth trying again."""
    from g3o.scrape import fetcher

    _no_sleep(monkeypatch)
    calls = _install_session(
        monkeypatch, lambda url: _FakeResponse(status_code=503)
    )
    with pytest.raises(requests.exceptions.HTTPError):
        fetcher._download("https://example.gov/down")
    assert calls["n"] == 3


def test_a_connection_error_is_still_retried(tmp_path: Path, monkeypatch) -> None:
    from g3o.scrape import fetcher

    _no_sleep(monkeypatch)

    def _boom(url):
        raise requests.exceptions.ConnectionError("reset")

    calls = _install_session(monkeypatch, _boom)
    with pytest.raises(requests.exceptions.ConnectionError):
        fetcher._download("https://example.gov/flaky")
    assert calls["n"] == 3


def test_an_exhausted_retry_surfaces_the_real_exception(monkeypatch) -> None:
    """Not ``RetryError[...]`` — the ledger's detail has to name the actual fault.

    ``_download`` was the one retry in the codebase without ``reraise=True``, so
    an exhausted retry arrived at the attrition ledger wrapped. The class of the
    underlying exception is exactly what a scrape-failure diagnosis reads
    (issue #90 is a breakdown by exception class), so it must survive the retry.
    """
    from g3o.scrape import fetcher

    _no_sleep(monkeypatch)
    _install_session(monkeypatch, lambda url: _FakeResponse(status_code=503))
    with pytest.raises(requests.exceptions.HTTPError) as exc:
        fetcher._download("https://example.gov/down")
    assert "503" in str(exc.value)


# ---------------------------------------------------------------------------
# F3 — the body is bounded
# ---------------------------------------------------------------------------


def test_an_oversized_content_length_is_refused_before_reading(monkeypatch) -> None:
    """The header check is the cheap early exit: no bytes are read at all."""
    from g3o.scrape import fetcher

    huge = str(fetcher.MAX_RESPONSE_BYTES + 1)
    read = {"chunks": 0}

    class _Counting(_FakeResponse):
        def iter_content(self, chunk_size: int = 8192):
            read["chunks"] += 1
            yield b""

    _install_session(
        monkeypatch,
        lambda url: _Counting(
            headers={"content-type": "application/pdf", "content-length": huge}
        ),
    )
    with pytest.raises(fetcher.ResponseTooLarge):
        fetcher._download("https://example.gov/huge.pdf")
    assert read["chunks"] == 0


def test_an_unstated_oversized_body_is_stopped_mid_stream(monkeypatch) -> None:
    """A missing Content-Length is unknown, not zero — streaming is the real cap."""
    from g3o.scrape import fetcher

    monkeypatch.setattr(fetcher, "MAX_RESPONSE_BYTES", 1024)
    _install_session(
        monkeypatch,
        lambda url: _FakeResponse(
            body=b"x" * 8192,
            headers={"content-type": "text/html"},  # no content-length
            chunk_size=256,
        ),
    )
    with pytest.raises(fetcher.ResponseTooLarge):
        fetcher._download("https://example.gov/endless")


def test_a_normal_page_is_unaffected(monkeypatch) -> None:
    """The cap must be invisible to every real page."""
    from g3o.scrape import fetcher

    _install_session(monkeypatch, lambda url: _FakeResponse())
    content, ctype, status, final_url, _elapsed = fetcher._download(
        "https://example.gov/page"
    )
    assert content == b"<html><body>hi</body></html>"
    assert ctype == "text/html"
    assert status == 200
    assert final_url == "https://example.gov/page"


def test_a_size_cap_is_not_retried(monkeypatch) -> None:
    """The body will be the same size on attempt two."""
    from g3o.scrape import fetcher

    _no_sleep(monkeypatch)
    monkeypatch.setattr(fetcher, "MAX_RESPONSE_BYTES", 16)
    calls = _install_session(
        monkeypatch, lambda url: _FakeResponse(body=b"x" * 512, chunk_size=16)
    )
    with pytest.raises(fetcher.ResponseTooLarge):
        fetcher._download("https://example.gov/big")
    assert calls["n"] == 1


def test_size_cap_fires_its_own_hook_not_the_failure_hook(monkeypatch) -> None:
    """"Declined to read" must stay distinguishable from "could not read".

    Routing this through ``on_scrape_failure`` would book it as ``scrape_failed``
    and lose the distinction — and would disturb a failure contract PR #32 only
    recently stabilised (issue #46).
    """
    from g3o.scrape import fetcher

    monkeypatch.setattr(fetcher, "MAX_RESPONSE_BYTES", 16)
    monkeypatch.setattr(fetcher, "_load", lambda url, min_chars=1: None)
    monkeypatch.setattr(fetcher, "_save", lambda page, min_chars=1: None)
    _install_session(
        monkeypatch, lambda url: _FakeResponse(body=b"x" * 512, chunk_size=16)
    )

    capped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    page = fetcher.scrape_url(
        "https://example.gov/big",
        on_size_capped=lambda **kw: capped.append(kw),
        on_scrape_failure=lambda **kw: failed.append(kw),
    )

    assert len(capped) == 1
    assert not failed, "a size cap is not a fetch failure"
    assert isinstance(capped[0]["error"], fetcher.ResponseTooLarge)
    # Q10 still holds: a RenderedPage comes back on every path.
    assert page.text == ""
