"""Stage 4 runner — polite scrape per (institution × kept URL).

Sequential by default (``scrape_pool_size <= 1``); a :class:`ThreadPoolExecutor`
fans out across URLs when ``scrape_pool_size > 1`` while a per-host serialization
+ spacing gate (:class:`g3o.scrape.politeness.HostScheduler`) preserves the
research-ethics politeness rules under concurrency (review F14b / Decision D4).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from g3o.common import attrition, scrape_telemetry
from g3o.common import config as _config
from g3o.common.run_state import is_done, mark_done
from g3o.run.presweep.records import institution_record, synth_institution_id
from g3o.scrape.fetcher import scrape_url
from g3o.scrape.politeness import (
    DEFAULT_HOST_DELAY_SECONDS,
    HostScheduler,
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
    worker thread instead owns its own session, created eagerly in the pool
    ``initializer`` (cheap — the object is constructed here but Chromium is not
    launched until an actual render fires, so threads that never render never
    start a browser).

    Teardown must also run *on the owning thread*: closing a session from a
    foreign thread violates Playwright's affinity. :meth:`close_all` returns a
    cleanup callable that each worker runs exactly once (fanned out across every
    started worker via a barrier), closing that thread's own session.
    """

    def __init__(self) -> None:
        self._local = threading.local()
        self._lock = threading.Lock()
        self._started = 0

    def init_thread(self) -> None:
        """Executor ``initializer``: give this worker thread its own session."""
        self._local.session = RenderSession()
        with self._lock:
            self._started += 1

    def session(self) -> RenderSession:
        return self._local.session

    def started_count(self) -> int:
        with self._lock:
            return self._started

    def _close_own(self) -> None:
        session = getattr(self._local, "session", None)
        if session is not None:
            session.close()
            self._local.session = None

    def close_all(self, executor: ThreadPoolExecutor) -> None:
        """Close every worker's session on its own thread.

        Submits exactly ``started_count`` cleanup tasks gated on a barrier so
        each of the (now idle) worker threads picks up exactly one and closes
        its own session. The barrier has a timeout so a lost worker degrades to
        a best-effort leak rather than a hang.
        """
        n = self.started_count()
        if n == 0:
            return
        barrier = threading.Barrier(n)

        def _cleanup() -> None:
            try:
                barrier.wait(timeout=30)
            except threading.BrokenBarrierError:
                pass
            self._close_own()

        futures = [executor.submit(_cleanup) for _ in range(n)]
        for future in futures:
            try:
                future.result(timeout=60)
            except Exception as exc:  # pragma: no cover - best-effort teardown
                logger.warning("Stage 4 render-session cleanup failed: %s", exc)


def _scrape_one_url(
    run_dir: Path,
    inst_id: str,
    url: str,
    *,
    scrape_dir: Path,
    url_hash: Callable[[str], str],
    robots: RobotsCache | None,
    scheduler: HostScheduler,
    render_session: RenderSession | None,
    render_on_download_failure: bool,
    stage: str,
) -> RenderedPage | None:
    """Scrape a single URL. Returns the page, or ``None`` if skipped/failed.

    Records exactly one telemetry entry per attempt regardless of outcome
    (review F14b), and preserves the drop paths' attrition records so the health
    report is unchanged. Identical logic on the sequential and concurrent paths.
    """
    output_path = scrape_dir / f"{url_hash(url)}.json"
    if output_path.exists():
        # Q5=a per-run skip: load existing RenderedPage; no refetch.
        page = RenderedPage.model_validate_json(
            output_path.read_text(encoding="utf-8")
        )
        scrape_telemetry.record(
            run_dir, institution_id=inst_id, url=url,
            outcome=scrape_telemetry.OUTCOME_SKIPPED_CACHED,
        )
        return page

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
        return None

    extra_delay = robots.crawl_delay(url) if robots is not None else None
    # The host slot serializes same-host requests AND enforces the >=1.0s
    # spacing; the fetch happens while the slot (this host's lock) is held.
    with scheduler.slot(url, extra_delay=extra_delay):
        try:
            page = scrape_url(
                url,
                render_session=render_session,
                prefer_render_on_download_failure=render_on_download_failure,
            )
        except Exception as exc:
            logger.warning("Stage 4 scrape failed for %s (%s): %s", inst_id, url, exc)
            attrition.record(
                run_dir, institution_id=inst_id, stage=stage,
                reason="scrape_failed", url=url, detail=str(exc),
            )
            scrape_telemetry.record(
                run_dir, institution_id=inst_id, url=url,
                outcome=scrape_telemetry.OUTCOME_SCRAPE_FAILED, detail=str(exc),
            )
            return None

    output_path.write_text(page.model_dump_json(indent=2), encoding="utf-8")
    scrape_telemetry.record(
        run_dir, institution_id=inst_id, url=url,
        outcome=scrape_telemetry.OUTCOME_SUCCEEDED,
        content_type=page.content_type,
        http_status=page.fetch_metadata.http_status,
        fetch_method=page.fetch_metadata.fetch_method,
        elapsed_ms=page.fetch_metadata.elapsed_ms,
    )
    return page


def _run_scrape(
    run_dir: Path,
    sample: list[dict[str, Any]],
    triaged: dict[str, list[str]],
    *,
    respect_robots: bool = True,
    host_delay_seconds: float = DEFAULT_HOST_DELAY_SECONDS,
    render_on_download_failure: bool = False,
    scrape_pool_size: int = 1,
    robots: RobotsCache | None = None,
) -> dict[str, list[RenderedPage]]:
    """Stage 4 — polite scrape per (institution × kept URL).

    Per-URL idempotency (Q5=a, Session E 2026-05-09): when the per-run output
    file ``runs/<run_id>/<inst_id>/scrape/<url_hash>.json`` already exists, the
    runner loads the cached :class:`RenderedPage` and skips ``scrape_url`` for
    that URL. The fetcher's global ``page_v2_<md5>`` cache continues to handle
    cross-run reuse below this layer; the runner-side guard protects partial
    crash-recovery within a run.

    Politeness (review F14 / Decision D4, 2026-06-10): when ``respect_robots``
    is True each URL is checked against its host's robots.txt for the G3O
    user-agent; a ``Disallow`` skips the URL and records a ``robots_disallowed``
    attrition entry. A per-host courtesy delay (``host_delay_seconds``, raised
    by any robots ``Crawl-delay``) throttles same-host requests. ``robots`` may
    be injected (tests); otherwise a run-scoped :class:`RobotsCache` is built.

    Concurrency (review F14b): ``scrape_pool_size`` sets the thread-pool width.

    - ``<= 1`` runs the sequential loop in the calling thread with one shared
      :class:`RenderSession` — behaviorally identical to the pre-pool runner.
    - ``> 1`` fans out across URLs with a :class:`ThreadPoolExecutor`. A
      :class:`HostScheduler` serializes same-host requests (only one in flight
      per host) and holds the >=1.0s spacing while different hosts proceed
      concurrently; robots.txt is respected under concurrency; each worker
      thread owns its own :class:`RenderSession`. Results are reassembled in the
      input triage order per institution, so the output is independent of
      completion order and matches the sequential path.

    Telemetry (review F14b): every scrape attempt writes one record to
    ``_scrape_telemetry.jsonl`` regardless of outcome (succeeded / skipped_cached
    / robots_disallowed / scrape_failed). The ``_attrition.jsonl`` drop ledger
    is unchanged.

    Sharding (700k+ scale): all politeness state is instance-local, so this
    composes with a future host-keyed shard runner — one scheduler/robots cache
    per shard, no distributed lock — without changing this function.
    """
    from g3o.extract.batch import url_hash

    stage = "scrape"
    if is_done(run_dir, stage):
        logger.info("Stage 4: .done marker present — skipping (resume from disk)")
        return _read_existing_scraped(run_dir, sample)

    if respect_robots and robots is None:
        robots = RobotsCache(_config.USER_AGENT)
    scheduler = HostScheduler(HostThrottle(host_delay_seconds))
    scrape_telemetry.ensure_ledger(run_dir)

    # Deterministic work list: (inst_id, url_index, url) in triage order. The
    # url_index drives reassembly so the concurrent path's output ordering is
    # identical to the sequential path's regardless of completion order.
    inst_urls: dict[str, list[str]] = {}
    tasks: list[tuple[str, int, str]] = []
    for row in sample:
        institution = institution_record(row)
        inst_id = institution["institution_id"]
        urls = triaged.get(inst_id, [])
        inst_urls[inst_id] = urls
        (run_dir / inst_id / "scrape").mkdir(parents=True, exist_ok=True)
        for url_index, url in enumerate(urls):
            tasks.append((inst_id, url_index, url))

    # (inst_id, url_index) -> page, for order-independent reassembly.
    results: dict[tuple[str, int], RenderedPage] = {}

    if scrape_pool_size <= 1:
        # Sequential fast-path: one shared RenderSession on the calling thread.
        with RenderSession() as render_session:
            for inst_id, url_index, url in tasks:
                page = _scrape_one_url(
                    run_dir, inst_id, url,
                    scrape_dir=run_dir / inst_id / "scrape",
                    url_hash=url_hash, robots=robots, scheduler=scheduler,
                    render_session=render_session,
                    render_on_download_failure=render_on_download_failure,
                    stage=stage,
                )
                if page is not None:
                    results[(inst_id, url_index)] = page
    else:
        render_sessions = _ThreadLocalRenderSessions()
        executor = ThreadPoolExecutor(
            max_workers=scrape_pool_size,
            initializer=render_sessions.init_thread,
        )
        try:
            def _work(inst_id: str, url_index: int, url: str) -> tuple[tuple[str, int], RenderedPage | None]:
                page = _scrape_one_url(
                    run_dir, inst_id, url,
                    scrape_dir=run_dir / inst_id / "scrape",
                    url_hash=url_hash, robots=robots, scheduler=scheduler,
                    render_session=render_sessions.session(),
                    render_on_download_failure=render_on_download_failure,
                    stage=stage,
                )
                return (inst_id, url_index), page

            futures = [executor.submit(_work, *task) for task in tasks]
            for future in futures:
                key, page = future.result()
                if page is not None:
                    results[key] = page
            render_sessions.close_all(executor)
        finally:
            executor.shutdown(wait=True)

    out: dict[str, list[RenderedPage]] = {}
    for inst_id, urls in inst_urls.items():
        out[inst_id] = [
            results[(inst_id, i)]
            for i in range(len(urls))
            if (inst_id, i) in results
        ]

    mark_done(run_dir, stage, no_batch=True)
    return out
