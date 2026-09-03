"""Stage 4 runner — polite scrape per (institution × kept URL)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from g3o.common import attrition, scrape_telemetry
from g3o.common import config as _config
from g3o.common.artifact_io import (
    artifact_exists,
    glob_artifacts,
    quarantine_artifact,
    read_artifact,
    write_artifact,
)
from g3o.common.paths import institution_dir
from g3o.common.run_state import is_done, mark_done
from g3o.common.timing import stage_timer
from g3o.extract.batch import EMPTY_PAGE_MIN_CHARS
from g3o.run.presweep.concurrency import run_concurrent
from g3o.run.presweep.records import institution_record, synth_institution_id
from g3o.scrape import egress
from g3o.scrape.fetcher import (
    error_class_of,
    http_status_from_exception,
    scrape_url,
)
from g3o.scrape.politeness import (
    DEFAULT_HOST_DELAY_SECONDS,
    HostThrottle,
    RobotsCache,
)
from g3o.scrape.render import RenderedPage, RenderSession

logger = logging.getLogger(__name__)

#: Attrition reason for an existing scrape artifact that would not parse. Not a
#: member of ``g3o.report.outcomes._FAILURE_REASONS``: the page is refetched in
#: the same pass, so this records a *recovered* degradation. A refetch that then
#: fails records ``scrape_failed`` on its own and counts as the failure.
REASON_ARTIFACT_CORRUPT = "scrape_artifact_corrupt"

#: Attrition reason for a URL the per-institution scrape budget never reached
#: (issue #96, PI ruling 2026-08-26). **Is** a member of
#: ``g3o.report.outcomes._FAILURE_REASONS``, and that membership is the point:
#: the ruling was budget-then-skip *plus a named reason*, precisely so an
#: institution we ran out of time on reports PROCESSING_FAILED instead of
#: publishing as NO_EVIDENCE_FOUND — "could not reach" laundered into "searched
#: and found nothing" is the #17 defect class, and the post-#17 tightening of
#: ``none`` would now vouch for it. A reason outside that frozenset is on the
#: ledger and invisible to the report's failure tally, which is the silent
#: outcome the PI rejected.
#:
#: Named for the condition that produces it in practice — every budget expiry in
#: the measured run was driven by an honoured robots ``Crawl-delay`` — and kept
#: as the vocabulary of issue #96 and the ruling. The budget is nonetheless a
#: plain wall-clock budget and can expire for another reason (many slow URLs, a
#: large PDF), so the per-record ``detail`` carries the elapsed time, the budget,
#: and the wait that was refused, and the row is legible without the name.
REASON_CRAWL_DELAY_EXCEEDED = "crawl_delay_exceeded"


def _read_existing_scraped(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[RenderedPage]]:
    """Load Stage 4 output from disk for a stage already marked ``.done``.

    Unlike the per-URL resume guard in :func:`_scrape_one`, this path cannot
    repair anything: the stage is complete, so there is no refetch to fall back
    on. An unparseable artifact therefore still raises and aborts, which is the
    loud failure the situation deserves — silently dropping the page here would
    shrink Stage 5's input with nothing but a ledger line to show for it.
    """
    out: dict[str, list[RenderedPage]] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        scrape_dir = institution_dir(run_dir, inst_id) / "scrape"
        if not scrape_dir.is_dir():
            continue
        pages: list[RenderedPage] = []
        for path in glob_artifacts(scrape_dir):
            pages.append(RenderedPage.model_validate_json(read_artifact(path)))
        out[inst_id] = pages
    return out


class _ThreadLocalRenderSessions:
    """One :class:`RenderSession` per worker thread (Playwright thread-affinity).

    Playwright's sync API is bound to the thread that created it, so a single
    shared browser context cannot be driven from multiple pool workers. Each
    worker thread instead owns one session, created in the pool ``initializer``
    (cheap — the object is constructed here but Chromium is not launched until a
    render actually fires, so threads that never render never start a browser)
    and **reused across every institution that thread handles** — the browser
    launch is amortized over the thread's whole workload, not paid per
    institution. Teardown runs on the owning thread (``close_own`` via the
    executor's per-thread finalizer), because closing a Playwright object from a
    foreign thread violates its affinity.
    """

    def __init__(self) -> None:
        self._local = threading.local()

    def init_thread(self) -> None:
        """Executor ``initializer``: give this worker thread its own session."""
        self._local.session = RenderSession()

    def session(self) -> RenderSession:
        return self._local.session

    def close_own(self) -> None:
        """Executor per-thread finalizer: close this thread's own session."""
        session = getattr(self._local, "session", None)
        if session is not None:
            session.close()
            self._local.session = None


def _resume_cached_page(
    run_dir: Path,
    output_path: Path,
    *,
    inst_id: str,
    url: str,
    stage: str,
) -> RenderedPage | None:
    """The existing artifact for this URL, or None when it is unusable.

    Review F7. The Q5=a resume guard used to assume that "the file exists"
    means "this URL is done", and read it with no error handling — so one
    truncated artifact (a crash mid-write, before writes became atomic) raised
    out of the worker and took down every remaining institution in the pass.

    An artifact that will not parse is treated as corrupt rather than as
    completed work: it is quarantined (moved to ``.corrupt``, out of the glob
    but still on disk for diagnosis), recorded once in the attrition ledger, and
    reported as a miss so the caller refetches the URL. Returning None is the
    signal to refetch; the exception is never re-raised.
    """
    try:
        return RenderedPage.model_validate_json(read_artifact(output_path))
    except Exception as exc:
        quarantined = quarantine_artifact(output_path)
        logger.warning(
            "Stage 4: existing scrape artifact for %s (%s) is unparseable — "
            "quarantined to %s and refetching: %s",
            inst_id, url, quarantined.name, exc,
        )
        attrition.record(
            run_dir, institution_id=inst_id, stage=stage,
            reason=REASON_ARTIFACT_CORRUPT, url=url,
            detail=f"quarantined={quarantined.name}; error={exc}",
        )
        return None


def _scrape_one(
    run_dir: Path,
    row: dict[str, Any],
    urls: list[str],
    *,
    stage: str,
    robots: RobotsCache | None,
    throttle: HostThrottle,
    render_on_download_failure: bool,
    empty_page_min_chars: int,
    sessions: _ThreadLocalRenderSessions,
    budget_seconds: float | None = None,
) -> tuple[str, list[RenderedPage]]:
    """Scrape one institution's kept URLs. Factored out of :func:`_run_scrape`
    (institution-level Stage-4 concurrency, 2026-07) so it can run in a worker
    thread.

    The render fallback reuses the calling worker thread's own thread-local
    :class:`RenderSession` (see :class:`_ThreadLocalRenderSessions`), so a
    browser launch is capped at ``max_workers`` and amortized across every
    institution a thread handles — not launched per institution. ``robots`` /
    ``throttle`` remain stage-scoped and shared across workers (``HostThrottle``
    is lock-protected per host).

    ``budget_seconds`` (issue #96) is this institution's wall-clock ceiling. It
    is checked **before** each throttle sleep and against the sleep that sleep
    would be, not after it: the projected wake time, not the elapsed time alone.
    That distinction is the fix. An elapsed-time check alone passes at the first
    URL of ``www.riigikohus.ee`` (elapsed 0), then sleeps the declared
    ``Crawl-delay: 8640`` — 2h24m — and only trips on the *next* URL, so the
    institution still holds a worker for the exact duration the budget exists to
    prevent. Refusing the sleep instead costs that institution one fetch and then
    stops.

    The budget gates network work, not the loop. A URL already on disk from an
    earlier pass is served from its artifact even after the budget is spent: that
    costs nothing, and refusing free pages would make each resume recover less
    than the pass before it. Everything the budget does stop — the robots
    consult, the throttle sleep, the fetch — is recorded per URL under
    ``REASON_CRAWL_DELAY_EXCEEDED``, every one of them, because a partial ledger
    is the same silence in a smaller box.
    """
    from g3o.extract.batch import url_hash

    institution = institution_record(row)
    inst_id = institution["institution_id"]
    scrape_dir = institution_dir(run_dir, inst_id) / "scrape"
    scrape_dir.mkdir(parents=True, exist_ok=True)
    pages: list[RenderedPage] = []
    render_session = sessions.session()

    def _record_render_attempt(
        *, url: str, trigger: str, outcome: str, result_len: int | None,
        _inst: str = inst_id,
    ) -> None:
        # Telemetry for every render attempt (download-failure- or
        # empty-after-strip-triggered): one record per (inst, url) — attrition
        # dedups on (institution_id, stage, reason, url), so a still-empty render
        # is recorded exactly once, never a silent drop and never a duplicate.
        # trigger/outcome/stripped_len stay out of the dedup key so the render
        # rate + cost are queryable.
        detail = f"trigger={trigger};outcome={outcome}"
        if result_len is not None:
            detail += f";stripped_len={result_len}"
        attrition.record(
            run_dir, institution_id=_inst, stage=stage,
            reason="render_attempted", url=url, detail=detail,
            trigger=trigger, outcome=outcome,
        )

    # Per-URL hard-failure sink. ``scrape_url`` keeps returning a no-text Q10
    # failure page on a failed fetch; this hook fires alongside it so we record
    # a durable scrape_failed entry (carrying both underlying exception
    # messages) and can drop the page rather than writing it as a normal
    # successful scrape. ``failed`` is reset per URL in the loop below.
    fetch_failure = {"failed": False}

    def _record_scrape_failure(
        *, url: str, download_error: BaseException,
        render_error: BaseException | None,
        _inst: str = inst_id,
    ) -> None:
        fetch_failure["failed"] = True
        # Redacted, because these two strings are the one place a *third-party*
        # exception reaches an artifact. The rule that made
        # ``run_failed(error_message=str(exc))`` safe — this pipeline's own
        # exceptions name variables and paths, never values — does not bind
        # ``requests``: a malformed ``G3O_SCRAPE_PROXY`` (a trailing space, a
        # non-numeric port) raises ``InvalidURL("Failed to parse: <the whole
        # proxy URL>")``, credentials included, and Stage 4 writes it here once
        # per URL. Measured 2026-08-27; connection-level ``ProxyError``s are
        # clean, so this is narrow, but it is on the run's worst path — the one
        # where the proxy is misconfigured and every fetch fails.
        detail = f"download_error={egress.redact(str(download_error))}"
        if render_error is not None:
            detail += f"; render_error={egress.redact(str(render_error))}"
        attrition.record(
            run_dir, institution_id=_inst, stage=stage,
            reason="scrape_failed", url=url, detail=detail,
        )
        # This ledger is the per-attempt floor: its contract is that every
        # (institution, url) the runner touched is accounted for, and until
        # 2026-08-30 the commonest failure path — a hard fetch failure, which
        # reaches the runner through this hook rather than as an exception —
        # wrote nothing here at all. So a scrape_failed appeared in the attrition
        # ledger and vanished from the telemetry one, and neither carried a
        # status. Across the anglophone 12k's 6,719 scrape_failed rows a 403
        # refusal, a timeout, a DNS failure and a TLS error were one row.
        scrape_telemetry.record(
            run_dir, institution_id=_inst, url=url,
            outcome=scrape_telemetry.OUTCOME_SCRAPE_FAILED,
            detail=detail,
            # Always written, both of them, including as null: an explicit null
            # is "this fetch never got a status line", which is the answer for a
            # timeout and is not the same as a ledger that predates the field.
            http_status=http_status_from_exception(download_error),
            error_class=error_class_of(download_error),
            render_error_class=error_class_of(render_error),
        )

    def _record_budget_expiry(
        *, url: str, elapsed: float, crawl_delay: float | None,
        _inst: str = inst_id,
    ) -> None:
        # One row per unreached URL, in both ledgers — attrition because
        # _FAILURE_REASONS reads it and turns the institution PROCESSING_FAILED,
        # telemetry because its contract is that every (institution, url) the
        # runner touched is accounted for. Attrition dedups on
        # (institution_id, stage, reason, url), so "exactly one" is structural.
        #
        # Only reachable with a budget set: ``budget_expired`` is raised solely
        # by the two checks below, both of which require one, and a ``max_wait``
        # of None never refuses. Asserted rather than left implicit so a
        # reordering of those checks fails here instead of formatting None.
        assert budget_seconds is not None
        detail = f"budget={budget_seconds:.0f}s;elapsed={elapsed:.1f}s"
        if crawl_delay is not None:
            detail += f";crawl_delay={crawl_delay:.0f}s"
        attrition.record(
            run_dir, institution_id=_inst, stage=stage,
            reason=REASON_CRAWL_DELAY_EXCEEDED, url=url, detail=detail,
        )
        scrape_telemetry.record(
            run_dir, institution_id=_inst, url=url,
            outcome=scrape_telemetry.OUTCOME_CRAWL_DELAY_EXCEEDED,
            detail=detail,
        )

    # Measured on the throttle's own clock so the budget and the waits it caps
    # share one source of truth (see HostThrottle.now).
    started = throttle.now()
    budget_expired = False

    with stage_timer(run_dir, inst_id, stage):
        for url in urls:
            fetch_failure["failed"] = False
            output_path = scrape_dir / f"{url_hash(url)}.json"
            if artifact_exists(output_path):
                # Q5=a per-run skip: load existing RenderedPage; no refetch.
                # artifact_exists/read_artifact accept either suffix, so a run
                # part-written before Phase 2 resumes off its plain artifacts
                # instead of re-scraping every URL.
                cached = _resume_cached_page(
                    run_dir, output_path, inst_id=inst_id, url=url, stage=stage
                )
                if cached is not None:
                    pages.append(cached)
                    scrape_telemetry.record(
                        run_dir, institution_id=inst_id, url=url,
                        outcome=scrape_telemetry.OUTCOME_SKIPPED_CACHED,
                    )
                    continue
                # Corrupt: quarantined and recorded (F7). Fall through to
                # refetch this URL rather than aborting the worker.
            if budget_expired:
                # Placed after the cached-artifact branch and before the robots
                # consult: a cache hit is free and still worth taking, a robots
                # fetch for an unseen host is not.
                _record_budget_expiry(
                    url=url, elapsed=throttle.now() - started, crawl_delay=None,
                )
                continue
            if robots is not None and not robots.allowed(url):
                logger.info("Stage 4: robots.txt disallows %s — skipping", url)
                attrition.record(
                    run_dir, institution_id=inst_id, stage=stage,
                    reason="robots_disallowed", url=url,
                )
                scrape_telemetry.record(
                    run_dir, institution_id=inst_id, url=url,
                    outcome=scrape_telemetry.OUTCOME_ROBOTS_DISALLOWED,
                )
                continue
            elapsed = throttle.now() - started
            remaining = None if budget_seconds is None else budget_seconds - elapsed
            if remaining is not None and remaining <= 0:
                budget_expired = True
                _record_budget_expiry(url=url, elapsed=elapsed, crawl_delay=None)
                continue
            crawl_delay = robots.crawl_delay(url) if robots is not None else None
            if not throttle.wait(url, extra_delay=crawl_delay, max_wait=remaining):
                # The sleep this URL needs would outlast the budget, so it was
                # not slept. Before-not-after: see the docstring.
                budget_expired = True
                logger.warning(
                    "Stage 4: per-institution budget (%.0fs) would be exceeded by "
                    "the courtesy delay for %s (%s) — skipping it and every "
                    "remaining URL, recorded as %s",
                    budget_seconds, inst_id, url, REASON_CRAWL_DELAY_EXCEEDED,
                )
                _record_budget_expiry(
                    url=url, elapsed=elapsed, crawl_delay=crawl_delay,
                )
                continue
            try:
                page = scrape_url(
                    url,
                    render_session=render_session,
                    # Explicit (not relying on the fetcher default): the
                    # empty-after-strip render is the point of this stage's
                    # render-on-empty behavior; pin it on at the call site so a
                    # future change to the fetcher default can't silently disable
                    # it. The tunable surface is empty_page_min_chars.
                    prefer_render_on_empty=True,
                    prefer_render_on_download_failure=render_on_download_failure,
                    empty_page_min_chars=empty_page_min_chars,
                    on_render_attempt=_record_render_attempt,
                    on_scrape_failure=_record_scrape_failure,
                )
            except Exception as exc:
                # Same redaction, same reason, and applied once here so the log
                # line and both ledgers cannot drift apart.
                safe = egress.redact(str(exc))
                logger.warning("Stage 4 scrape failed for %s (%s): %s", inst_id, url, safe)
                attrition.record(
                    run_dir, institution_id=inst_id, stage=stage,
                    reason="scrape_failed", url=url, detail=safe,
                )
                scrape_telemetry.record(
                    run_dir, institution_id=inst_id, url=url,
                    outcome=scrape_telemetry.OUTCOME_SCRAPE_FAILED,
                    detail=safe,
                    # Same two fields as the hook path above, so a query over the
                    # ledger does not have to know which of the two produced a
                    # row. `render_error_class` is absent rather than null here:
                    # this path is everything that escaped `scrape_url`, and no
                    # render was attempted and lost.
                    http_status=http_status_from_exception(exc),
                    error_class=error_class_of(exc),
                )
                continue
            if fetch_failure["failed"]:
                # A hard fetch failure already recorded a scrape_failed entry via
                # the hook; drop the Q10 no-text failure page rather than writing
                # it as a normal successful scrape (no artifact, not counted).
                logger.warning("Stage 4 fetch failed for %s (%s) — dropped", inst_id, url)
                continue
            # Gzipped, compact (no indent=2), atomic, deterministic — see
            # g3o.common.artifact_io. Writes <url_hash>.json.gz.
            write_artifact(output_path, page.model_dump_json())
            scrape_telemetry.record(
                run_dir, institution_id=inst_id, url=url,
                outcome=scrape_telemetry.OUTCOME_SUCCEEDED,
                content_type=page.content_type,
                http_status=page.fetch_metadata.http_status,
                fetch_method=page.fetch_metadata.fetch_method,
                elapsed_ms=page.fetch_metadata.elapsed_ms,
            )
            pages.append(page)
    return inst_id, pages


def _run_scrape(
    run_dir: Path,
    sample: list[dict[str, Any]],
    triaged: dict[str, list[str]],
    *,
    respect_robots: bool = True,
    host_delay_seconds: float = DEFAULT_HOST_DELAY_SECONDS,
    render_on_download_failure: bool = False,
    empty_page_min_chars: int = EMPTY_PAGE_MIN_CHARS,
    robots: RobotsCache | None = None,
    throttle: HostThrottle | None = None,
    max_institution_seconds: float | None = None,
    max_workers: int = 1,
) -> dict[str, list[RenderedPage]]:
    """Stage 4 — scrape per (institution × kept URL).

    Per-URL idempotency (Q5=a, Session E 2026-05-09): when the per-run output
    file ``runs/<run_id>/institutions/<shard>/<inst_id>/scrape/<url_hash>.json.gz``
    already exists (or its pre-Phase-2 plain ``.json`` form — see
    :mod:`g3o.common.artifact_io`), the runner loads the cached
    :class:`RenderedPage` and skips ``scrape_url`` for that URL. The fetcher's
    global ``page_v2_<md5>`` cache continues to handle cross-run reuse below this
    layer; the runner-side guard protects partial crash-recovery within a run. An
    existing artifact that will not parse is quarantined and refetched rather
    than trusted or fatal (review F7, :func:`_resume_cached_page`).

    Politeness (review F14 / Decision D4, 2026-06-10): when ``respect_robots``
    is True, each URL is checked against its host's robots.txt for the G3O
    user-agent; a ``Disallow`` skips the URL and records a ``robots_disallowed``
    attrition entry. A per-host courtesy delay (``host_delay_seconds``, raised by
    any robots ``Crawl-delay``) throttles same-host requests via a shared,
    lock-protected :class:`HostThrottle`. ``robots`` may be injected (tests);
    otherwise a run-scoped :class:`RobotsCache` is built when ``respect_robots``.
    The throttle spaces same-host request *starts*; it does not serialize them,
    so two workers on a shared host may have requests in flight concurrently
    (PI ruling 2026-08-01 on review F14b: spacing, not serialization, is the D4
    bar — the standard ``Crawl-delay`` reading).

    Telemetry (review F14b): every scrape attempt writes one record to
    ``runs/<run_id>/_scrape_telemetry.jsonl`` regardless of outcome (succeeded /
    skipped_cached / robots_disallowed / scrape_failed), so every
    ``(institution, url)`` the runner touched is accounted for even when work
    fans out. ``_attrition.jsonl`` keeps recording drops exactly as before —
    the two ledgers are separate on purpose (see
    :mod:`g3o.common.scrape_telemetry`).

    Empty-page render (render-on-empty): ``empty_page_min_chars`` is handed to
    ``scrape_url`` so a page whose deterministic text strips below the floor — a
    JS-shell page returning 200 + near-zero chars — triggers a render instead of
    passing through to Stage 5 as a silent ``empty_page_dropped``. It shares the
    threshold Stage 5 uses to drop empty pages. Every render attempt writes a
    ``render_attempted`` attrition record via the ``on_render_attempt`` hook, so
    the render rate stays auditable and no render is a silent retry.

    Per-institution budget (issue #96, PI ruling 2026-08-26):
    ``max_institution_seconds`` caps the wall clock any one institution may
    spend here. On expiry the institution **completes with the pages it has**
    and every URL it did not reach is recorded under ``crawl_delay_exceeded``
    in both ledgers — a member of ``g3o.report.outcomes._FAILURE_REASONS``, so
    the institution reports PROCESSING_FAILED and is never published as a clean
    negative. The check is made before each throttle sleep, against the sleep
    that sleep would be (:meth:`HostThrottle.wait`'s ``max_wait``), so the host
    that motivated the issue costs one fetch rather than one 2h24m sleep per
    URL. ``None`` (the default here; :class:`PresweepConfig` supplies 3600 s)
    leaves the pre-#96 unbounded behaviour. ``throttle`` may be injected
    alongside ``robots`` so the suite drives the budget on a fake clock instead
    of sleeping.

    Concurrency (2026-07): institutions run through
    :func:`g3o.run.presweep.concurrency.run_concurrent`, up to ``max_workers`` at
    a time (default 1 = one worker thread, effectively sequential). Each worker
    thread owns one thread-local :class:`RenderSession`
    (:class:`_ThreadLocalRenderSessions`), created in the pool initializer and
    reused across every institution that thread handles, so browser launches are
    bounded by ``max_workers`` — not by institution count. Sessions are closed on
    their owning thread via the executor's per-thread finalizer. Per-URL failures
    are non-fatal (caught and recorded inside :func:`_scrape_one`); only an
    unexpected exception aborts the stage, with the cancel-pending/drain-running/
    re-raise contract of :func:`run_concurrent`.
    """
    stage = "scrape"
    if is_done(run_dir, stage):
        logger.info("Stage 4: .done marker present — skipping (resume from disk)")
        return _read_existing_scraped(run_dir, sample)
    if respect_robots and robots is None:
        robots = RobotsCache(_config.USER_AGENT)
    if throttle is None:
        throttle = HostThrottle(host_delay_seconds)
    scrape_telemetry.ensure_ledger(run_dir)
    sessions = _ThreadLocalRenderSessions()
    out: dict[str, list[RenderedPage]] = {}
    results = run_concurrent(
        sample,
        lambda row: _scrape_one(
            run_dir, row, triaged.get(synth_institution_id(row), []),
            stage=stage, robots=robots, throttle=throttle,
            render_on_download_failure=render_on_download_failure,
            empty_page_min_chars=empty_page_min_chars,
            sessions=sessions,
            budget_seconds=max_institution_seconds,
        ),
        max_workers=max_workers,
        initializer=sessions.init_thread,
        finalizer=sessions.close_own,
    )
    for inst_id, pages in results:
        out[inst_id] = pages
    mark_done(run_dir, stage, no_batch=True)
    return out
