"""Stage 4 runner — polite scrape per (institution × kept URL)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from g3o.common import attrition
from g3o.common import config as _config
from g3o.common.run_state import is_done, mark_done
from g3o.common.timing import stage_timer
from g3o.extract.batch import EMPTY_PAGE_MIN_CHARS
from g3o.run.presweep.concurrency import run_concurrent
from g3o.run.presweep.records import institution_record, synth_institution_id
from g3o.scrape.fetcher import scrape_url
from g3o.scrape.politeness import (
    DEFAULT_HOST_DELAY_SECONDS,
    HostThrottle,
    RobotsCache,
)
from g3o.scrape.render import RenderedPage, RenderSession

logger = logging.getLogger(__name__)


def _read_existing_scraped(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[RenderedPage]]:
    out: dict[str, list[RenderedPage]] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        scrape_dir = run_dir / inst_id / "scrape"
        if not scrape_dir.is_dir():
            continue
        pages: list[RenderedPage] = []
        for path in sorted(scrape_dir.glob("*.json")):
            pages.append(RenderedPage.model_validate_json(path.read_text(encoding="utf-8")))
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
    """
    from g3o.extract.batch import url_hash

    institution = institution_record(row)
    inst_id = institution["institution_id"]
    scrape_dir = run_dir / inst_id / "scrape"
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

    with stage_timer(run_dir, inst_id, stage):
        for url in urls:
            output_path = scrape_dir / f"{url_hash(url)}.json"
            if output_path.exists():
                # Q5=a per-run skip: load existing RenderedPage; no refetch.
                pages.append(
                    RenderedPage.model_validate_json(
                        output_path.read_text(encoding="utf-8")
                    )
                )
                continue
            if robots is not None and not robots.allowed(url):
                logger.info("Stage 4: robots.txt disallows %s — skipping", url)
                attrition.record(
                    run_dir, institution_id=inst_id, stage=stage,
                    reason="robots_disallowed", url=url,
                )
                continue
            throttle.wait(
                url,
                extra_delay=robots.crawl_delay(url) if robots is not None else None,
            )
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
                )
            except Exception as exc:
                logger.warning("Stage 4 scrape failed for %s (%s): %s", inst_id, url, exc)
                attrition.record(
                    run_dir, institution_id=inst_id, stage=stage,
                    reason="scrape_failed", url=url, detail=str(exc),
                )
                continue
            output_path.write_text(page.model_dump_json(indent=2), encoding="utf-8")
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
    max_workers: int = 1,
) -> dict[str, list[RenderedPage]]:
    """Stage 4 — scrape per (institution × kept URL).

    Per-URL idempotency (Q5=a, Session E 2026-05-09): when the per-run output
    file ``runs/<run_id>/<inst_id>/scrape/<url_hash>.json`` already exists, the
    runner loads the cached :class:`RenderedPage` and skips ``scrape_url`` for
    that URL. The fetcher's global ``page_v2_<md5>`` cache continues to handle
    cross-run reuse below this layer; the runner-side guard protects partial
    crash-recovery within a run.

    Politeness (review F14 / Decision D4, 2026-06-10): when ``respect_robots``
    is True, each URL is checked against its host's robots.txt for the G3O
    user-agent; a ``Disallow`` skips the URL and records a ``robots_disallowed``
    attrition entry. A per-host courtesy delay (``host_delay_seconds``, raised by
    any robots ``Crawl-delay``) throttles same-host requests via a shared,
    lock-protected :class:`HostThrottle`. ``robots`` may be injected (tests);
    otherwise a run-scoped :class:`RobotsCache` is built when ``respect_robots``.

    Empty-page render (render-on-empty): ``empty_page_min_chars`` is handed to
    ``scrape_url`` so a page whose deterministic text strips below the floor — a
    JS-shell page returning 200 + near-zero chars — triggers a render instead of
    passing through to Stage 5 as a silent ``empty_page_dropped``. It shares the
    threshold Stage 5 uses to drop empty pages. Every render attempt writes a
    ``render_attempted`` attrition record via the ``on_render_attempt`` hook, so
    the render rate stays auditable and no render is a silent retry.

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
    throttle = HostThrottle(host_delay_seconds)
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
        ),
        max_workers=max_workers,
        initializer=sessions.init_thread,
        finalizer=sessions.close_own,
    )
    for inst_id, pages in results:
        out[inst_id] = pages
    mark_done(run_dir, stage, no_batch=True)
    return out
