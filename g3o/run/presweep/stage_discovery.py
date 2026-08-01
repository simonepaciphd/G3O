"""Stage 1a/1b runners — general + site-restricted Serper discovery."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from g3o.common import attrition
from g3o.common.run_state import is_done, mark_done
from g3o.common.timing import stage_timer
from g3o.discovery.query_builder import build_queries
from g3o.discovery.serper_client import (
    SerperRequestError,
    build_site_query,
    search_google,
)
from g3o.run.presweep.concurrency import run_concurrent
from g3o.run.presweep.records import (
    _site_domain,
    institution_record,
    synth_institution_id,
)

logger = logging.getLogger(__name__)


def _read_existing_discovery_general(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        path = run_dir / inst_id / "1a_discovery_general.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        out[inst_id] = payload.get("records", [])
    return out


def _read_existing_discovery_site_restricted(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        path = run_dir / inst_id / "1b_discovery_site_restricted.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        out[inst_id] = payload.get("records", [])
    return out


def _discover_general_one(
    run_dir: Path,
    row: dict[str, Any],
    *,
    stage: str,
    languages: tuple[str, ...],
    num_results: int,
) -> tuple[str, list[dict[str, Any]]]:
    """Process Stage 1a general discovery for one institution.

    Factored out of :func:`_run_discovery_general` so it can be called either
    from a plain loop or submitted to a thread pool unchanged (Stage 1a/1b/4
    concurrency, 2026-07). Behavior is identical to the original inline loop
    body — same skip-if-exists check, same file written, same exception on a
    Serper failure.
    """
    institution = institution_record(row)
    inst_id = institution["institution_id"]
    path = run_dir / inst_id / "1a_discovery_general.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return inst_id, payload.get("records", [])
    if not institution["country"]:
        logger.warning(
            "Stage 1a: %s (%r) has no country — discovery query is unscoped and "
            "may false-negative against a more prominent same-named institution",
            inst_id, institution["institution_name"],
        )
    with stage_timer(run_dir, inst_id, stage):
        # `disambiguation` is read off the raw master row, not the projected
        # institution record: that projection is serialized to institution.json
        # and fed to the Stage 2/3/5 LLM prompts, so adding a key there would
        # change model input as a side effect of a query change. `.get` keeps
        # pre-rollout masters (no such column) working.
        queries = build_queries(
            institution["institution_name"], list(languages),
            country=institution["country"],
            disambiguation=row.get("disambiguation") or "",
        )
        seen: set[str] = set()
        records: list[dict[str, Any]] = []
        for query, lang in queries:
            try:
                hits = search_google(query, num_results=num_results)
            except SerperRequestError as exc:
                # Honest failure (review F1): record and abort rather than
                # persist a partial artifact that looks like "found nothing".
                # The institution's 1a file is NOT written, so resume (or,
                # under concurrency, the stage-level abort) retries it.
                attrition.record(
                    run_dir, institution_id=inst_id, stage=stage,
                    reason="serper_request_failed", url=query, detail=str(exc),
                )
                raise
            for r in hits:
                url = r.get("link", "")
                if url and url not in seen:
                    seen.add(url)
                    records.append({**r, "query": query, "language": lang})
        path.write_text(
            json.dumps(
                {
                    "queries": [{"query": q, "language": lang} for q, lang in queries],
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return inst_id, records


def _run_discovery_general(
    run_dir: Path,
    sample: list[dict[str, Any]],
    *,
    languages: tuple[str, ...],
    num_results: int,
    max_workers: int = 1,
) -> dict[str, list[dict[str, Any]]]:
    """Stage 1a — general Serper queries. One ``1a_discovery_general.json`` per institution.

    Resume (Session E): when ``.done/discovery_general.json`` is present, skip
    Serper entirely and reconstruct the records dict from disk. Without a done
    marker, per-institution skip-if-exists protects partial recovery (each
    institution whose ``1a_discovery_general.json`` already exists is loaded
    instead of re-querying Serper — a paid call).

    Concurrency (2026-07): institutions run through
    :func:`g3o.run.presweep.concurrency.run_concurrent`, up to ``max_workers``
    at a time (default 1 = sequential, matching pre-concurrency behavior for
    any direct caller that doesn't pass it). On the first
    :class:`~g3o.discovery.serper_client.SerperRequestError`, in-flight
    institutions finish naturally and not-yet-started ones are cancelled,
    then that exception is re-raised — the stage is not marked done, so
    resume picks up exactly the institutions that never completed.
    """
    stage = "discovery_general"
    if is_done(run_dir, stage):
        logger.info("Stage 1a: .done marker present — skipping (resume from disk)")
        return _read_existing_discovery_general(run_dir, sample)
    out: dict[str, list[dict[str, Any]]] = {}
    results = run_concurrent(
        sample,
        lambda row: _discover_general_one(
            run_dir, row, stage=stage, languages=languages, num_results=num_results,
        ),
        max_workers=max_workers,
    )
    for inst_id, records in results:
        out[inst_id] = records
    mark_done(run_dir, stage, no_batch=True)
    return out


def _discover_site_restricted_one(
    run_dir: Path,
    row: dict[str, Any],
    official_sites: dict[str, str | None],
    *,
    stage: str,
    languages: tuple[str, ...],
    num_results: int,
) -> tuple[str, list[dict[str, Any]]] | None:
    """Process Stage 1b site-restricted discovery for one institution.

    Factored out of :func:`_run_discovery_site_restricted` (Stage 1a/1b/4
    concurrency, 2026-07); behavior identical to the original inline loop
    body. Returns ``None`` for the Q2=a skip case (no usable official site)
    so the caller writes nothing for that institution — same as today.
    """
    institution = institution_record(row)
    inst_id = institution["institution_id"]
    path = run_dir / inst_id / "1b_discovery_site_restricted.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return inst_id, payload.get("records", [])
    site_url = official_sites.get(inst_id)
    if not site_url:
        return None
    domain = _site_domain(site_url)
    if not domain:
        logger.warning(
            "Stage 1b: %s skipped — official_site_url=%r unparseable", inst_id, site_url
        )
        attrition.record(
            run_dir, institution_id=inst_id, stage=stage,
            reason="official_site_unparseable", url=site_url,
        )
        return None
    with stage_timer(run_dir, inst_id, stage):
        base_queries = build_queries(
            institution["institution_name"], list(languages),
            country=institution["country"],
            disambiguation=row.get("disambiguation") or "",
        )
        wrapped = [(build_site_query(q, domain), lang) for q, lang in base_queries]
        seen: set[str] = set()
        records: list[dict[str, Any]] = []
        for query, lang in wrapped:
            try:
                hits = search_google(query, num_results=num_results)
            except SerperRequestError as exc:
                attrition.record(
                    run_dir, institution_id=inst_id, stage=stage,
                    reason="serper_request_failed", url=query, detail=str(exc),
                )
                raise
            for r in hits:
                url = r.get("link", "")
                if url and url not in seen:
                    seen.add(url)
                    records.append(
                        {**r, "query": query, "language": lang, "site_domain": domain}
                    )
        path.write_text(
            json.dumps(
                {
                    "site_domain": domain,
                    "queries": [{"query": q, "language": lang} for q, lang in wrapped],
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return inst_id, records


def _run_discovery_site_restricted(
    run_dir: Path,
    sample: list[dict[str, Any]],
    official_sites: dict[str, str | None],
    *,
    languages: tuple[str, ...],
    num_results: int,
    max_workers: int = 1,
) -> dict[str, list[dict[str, Any]]]:
    """Stage 1b — site-restricted Serper queries (revision 2026-05-09, D1–D2).

    For each institution with a known official site (from Stage 2 LLM output or
    the Stage 2 bypass envelope), reuse :func:`build_queries` with the same
    multilingual GenAI-term roster (Q1=a, 2026-05-09) and wrap each query with
    the ``site:<domain>`` operator from :func:`build_site_query`. Per Q1, the
    query count matches Stage 1a one-for-one.

    Per Q2=a (2026-05-09), institutions with no usable official site (Stage 2
    returned ``None`` and no master bypass) are skipped: no 1b queries are
    issued and no ``1b_discovery_site_restricted.json`` is written. Stage 3
    triage will see only the 1a URL set for those institutions.

    Resume (Session E): same shape as Stage 1a — done-marker short-circuit +
    per-institution skip-if-exists protect Serper spend on partial recovery.

    Concurrency (2026-07): same ``max_workers``/failure-propagation contract
    as :func:`_run_discovery_general`, via
    :func:`g3o.run.presweep.concurrency.run_concurrent`.
    """
    stage = "discovery_site_restricted"
    if is_done(run_dir, stage):
        logger.info("Stage 1b: .done marker present — skipping (resume from disk)")
        return _read_existing_discovery_site_restricted(run_dir, sample)
    out: dict[str, list[dict[str, Any]]] = {}
    results = run_concurrent(
        sample,
        lambda row: _discover_site_restricted_one(
            run_dir, row, official_sites,
            stage=stage, languages=languages, num_results=num_results,
        ),
        max_workers=max_workers,
    )
    for inst_id, records in results:
        out[inst_id] = records
    mark_done(run_dir, stage, no_batch=True)
    return out
