"""Stage 4 runner — synchronous polite scrape per (institution × kept URL)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from g3o.common import attrition
from g3o.common import config as _config
from g3o.common.run_state import is_done, mark_done
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


def _run_scrape(
    run_dir: Path,
    sample: list[dict[str, Any]],
    triaged: dict[str, list[str]],
    *,
    respect_robots: bool = True,
    host_delay_seconds: float = DEFAULT_HOST_DELAY_SECONDS,
    render_on_download_failure: bool = False,
    robots: RobotsCache | None = None,
) -> dict[str, list[RenderedPage]]:
    """Stage 4 — synchronous scrape per (institution × kept URL).

    Per-URL idempotency (Q5=a, Session E 2026-05-09): when the per-run output
    file ``runs/<run_id>/<inst_id>/scrape/<url_hash>.json`` already exists, the
    runner loads the cached :class:`RenderedPage` and skips ``scrape_url`` for
    that URL. The fetcher's global ``page_v2_<md5>`` cache continues to handle
    cross-run reuse below this layer; the runner-side guard protects partial
    crash-recovery within a run, where a partial scrape loop may have written
    some files before crashing.

    Politeness (review F14 / Decision D4, 2026-06-10): the runner owns the
    scrape-ethics policy that the low-level fetcher stays agnostic of. When
    ``respect_robots`` is True, each URL is checked against its host's
    robots.txt for the G3O user-agent; a ``Disallow`` skips the URL and records
    a ``robots_disallowed`` attrition entry (so coverage stays auditable). A
    per-host courtesy delay (``host_delay_seconds``, raised by any robots
    ``Crawl-delay``) throttles same-host requests, and a single reused
    :class:`RenderSession` serves every render fallback in the loop instead of
    launching a browser per URL. ``robots`` may be injected (tests); otherwise
    a run-scoped :class:`RobotsCache` is built when ``respect_robots``.
    """
    from g3o.extract.batch import url_hash

    stage = "scrape"
    if is_done(run_dir, stage):
        logger.info("Stage 4: .done marker present — skipping (resume from disk)")
        return _read_existing_scraped(run_dir, sample)
    if respect_robots and robots is None:
        robots = RobotsCache(_config.USER_AGENT)
    throttle = HostThrottle(host_delay_seconds)
    out: dict[str, list[RenderedPage]] = {}
    with RenderSession() as render_session:
        for row in sample:
            institution = institution_record(row)
            inst_id = institution["institution_id"]
            urls = triaged.get(inst_id, [])
            scrape_dir = run_dir / inst_id / "scrape"
            scrape_dir.mkdir(parents=True, exist_ok=True)
            pages: list[RenderedPage] = []
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
                        prefer_render_on_download_failure=render_on_download_failure,
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
            out[inst_id] = pages
    mark_done(run_dir, stage, no_batch=True)
    return out
