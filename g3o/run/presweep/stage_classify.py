"""Stage 2/3 runners — official-site classifier + URL triage (Batch API)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from g3o.classify.official_site import (
    build_official_site_job,
    parse_official_site_result,
)
from g3o.classify.url_triage import (
    build_triage_job,
    match_triage_decisions,
    parse_triage_result,
)
from g3o.common import attrition
from g3o.common.batch_client import BatchResult
from g3o.common.credentials import ResolvedCredentials
from g3o.common.paths import institution_dir
from g3o.common.run_state import is_done, load_state, mark_done, run_chunked_stage
from g3o.common.timing import llm_stage_timer
from g3o.report.discovery_yield import registrable_domain
from g3o.run.presweep.records import (
    _dedupe_key,
    institution_record,
    synth_institution_id,
)

logger = logging.getLogger(__name__)


def ground_truth_block(
    master_website: str | None, picked_url: str | None
) -> dict[str, Any] | None:
    """Compare Stage 2's pick against the master's ``website``, or ``None``.

    This exists to give the health report its only accuracy signal. The Stage
    1a gauge cannot provide one: it reads ~100% whatever leg 1 returns,
    because leg 1 nearly always yields *some* non-aggregator host — just not
    always the right one (see docs/pipeline-status.md §5.1). Recording the
    comparison here, at run time, is what keeps :mod:`g3o.report.health`
    disk-only; the report must never import the master.

    Compared at the registrable domain rather than the exact URL, so a pick of
    ``https://www.example.gov/en/`` still matches a master value of
    ``example.gov`` — the question is whether Stage 2 identified the right
    *institution*, not whether it landed on the same path.

    Coverage is the master's ``website`` column: ~2% of the registry, and
    national-institution-heavy. This is a **regression canary, not an accuracy
    estimate** for the registry, and the health report labels it as such.
    """
    if not master_website:
        return None
    master_domain = registrable_domain(master_website)
    if not master_domain:
        return None
    picked_domain = registrable_domain(picked_url or "")
    return {
        "master_website": master_website,
        "master_domain": master_domain,
        "picked_domain": picked_domain or None,
        "domain_match": bool(picked_domain) and picked_domain == master_domain,
    }


def _read_existing_official_sites(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, str | None]:
    """Reconstruct Stage 2 output from per-institution ``2_official_site.json``.

    Both bypass envelopes (``{"bypassed": true, ..., "url": ...}``) and parsed
    classifier results (``{"url": ..., "confidence": ..., "rationale": ...}``)
    expose ``url`` at the top level, so the caller treats them uniformly.
    """
    out: dict[str, str | None] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        path = institution_dir(run_dir, inst_id) / "2_official_site.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        out[inst_id] = payload.get("url")
    return out


def _read_existing_triaged(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        path = institution_dir(run_dir, inst_id) / "3_triage.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        decisions = payload.get("decisions", [])
        out[inst_id] = [d["url"] for d in decisions if d.get("decision") == "keep"]
    return out


def _run_classify_official_site(
    run_dir: Path,
    sample: list[dict[str, Any]],
    discovery: dict[str, list[dict[str, Any]]],
    *,
    run_id: str,
    model: str,
    poll_interval: int,
    max_wait: int,
    credentials: ResolvedCredentials | None = None,
) -> dict[str, str | None]:
    """Stage 2 — official-site classifier batch, with master-CSV bypass guard.

    Bypass (revision 2026-05-09, D1+D4): when the institution row's
    ``official_site_url`` is non-null (WS3 round-2 column), skip the LLM submit/
    poll path entirely and write a ``2_official_site.json`` envelope of the form
    ``{"bypassed": true, "source": "master_csv", "url": "<from master>"}``. Per
    Q4 (2026-05-09) no plausibility check is applied; the runner trusts the
    master. Pre-rollout the column is null everywhere, so every row falls
    through to the LLM path (current production behavior).

    Resume (Session E; chunked Session F.1):
      - ``.done/classify_official_site.json`` present → reconstruct ``out`` from
        per-institution ``2_official_site.json`` files and return.
      - Otherwise the jobs are rebuilt deterministically and handed to
        :func:`run_chunked_stage`, which owns chunking, reconciliation,
        polling, and resume (bypass envelopes rewritten idempotently).
      - All-bypassed sample → no batch submitted; ``mark_done(no_batch=True)``.
      - Mixed bypass + LLM → state file covers the LLM subset only;
        ``bypass_count`` recorded.
    """
    stage = "classify_official_site"
    if is_done(run_dir, stage):
        logger.info("Stage 2: .done marker present — skipping (resume from disk)")
        return _read_existing_official_sites(run_dir, sample)

    out: dict[str, str | None] = {}
    jobs = []
    bypass_count = 0
    # Ground truth for the accuracy canary, read off the RAW master row.
    # Deliberately not routed through institution_record(): that dict is
    # serialised to institution.json and fed to the Stage 2/3/5/6 prompts, so
    # adding a key there would change model input as a side effect of a
    # telemetry change.
    truth_by_inst: dict[str, str] = {
        synth_institution_id(row): (row.get("website") or "").strip()
        for row in sample
    }
    for row in sample:
        institution = institution_record(row)
        inst_id = institution["institution_id"]
        bypass_url = institution.get("official_site_url")
        if bypass_url:
            out[inst_id] = bypass_url
            bypass_count += 1
            inst_dir = institution_dir(run_dir, inst_id)
            if inst_dir.exists():
                (inst_dir / "2_official_site.json").write_text(
                    json.dumps(
                        {"bypassed": True, "source": "master_csv", "url": bypass_url},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            continue
        candidate_urls = [r.get("link", "") for r in discovery.get(inst_id, [])]
        candidate_urls = [u for u in candidate_urls if u]
        if not candidate_urls:
            continue
        jobs.append(
            build_official_site_job(
                institution, candidate_urls, custom_id=inst_id
            )
        )
    if not jobs and load_state(run_dir, stage) is None:
        mark_done(run_dir, stage, no_batch=True)
        return out

    def _persist(results: Iterator[BatchResult]) -> None:
        for result in results:
            try:
                parsed = parse_official_site_result(result)
            except Exception as exc:
                logger.warning("Stage 2 parse failed for %s: %s", result.custom_id, exc)
                attrition.record(
                    run_dir, institution_id=result.custom_id, stage=stage,
                    reason="parse_failed", detail=str(exc),
                )
                continue
            out[result.custom_id] = parsed.url
            inst_dir = institution_dir(run_dir, result.custom_id)
            if inst_dir.exists():
                payload = parsed.model_dump()
                # Additive; every reader of this artifact uses .get(). Recorded
                # only on the LLM path — a master-bypassed pick would match the
                # master by construction and would inflate the canary.
                truth = ground_truth_block(
                    truth_by_inst.get(result.custom_id), parsed.url
                )
                if truth is not None:
                    payload["ground_truth"] = truth
                (inst_dir / "2_official_site.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    # custom_id == institution_id for this stage, so the identity fallback in
    # llm_stage_timer needs no explicit mapping.
    with llm_stage_timer(run_dir, stage, {}):
        run_chunked_stage(
            run_dir, stage, jobs,
            run_id=run_id, model=model,
            poll_interval=poll_interval, max_wait=max_wait,
            process_chunk_results=_persist, bypass_count=bypass_count,
            credentials=credentials,
        )
    # Disk is authoritative for chunks fetched by a prior (crashed) invocation;
    # this invocation's parses and bypasses override with identical content.
    return {**_read_existing_official_sites(run_dir, sample), **out}


def _candidate_urls_union(
    discovery_general: dict[str, list[dict[str, Any]]],
    discovery_site_restricted: dict[str, list[dict[str, Any]]],
    inst_id: str,
) -> list[str]:
    """Path-aware deduped union of 1a + 1b URLs for one institution (Q3=c)."""
    seen: set[str] = set()
    out: list[str] = []
    for source in (
        discovery_general.get(inst_id, []),
        discovery_site_restricted.get(inst_id, []),
    ):
        for r in source:
            url = r.get("link", "")
            if not url:
                continue
            key = _dedupe_key(url)
            if key in seen:
                continue
            seen.add(key)
            out.append(url)
    return out


def persist_triage_result(
    run_dir: Path,
    result: BatchResult,
    candidate_urls: list[str],
    *,
    stage: str = "classify_triage",
) -> list[str] | None:
    """Parse + URL-match one Stage 3 result, salvaging valid decisions per-URL.

    A structural parse failure (bad JSON, schema violation) is unrecoverable:
    one institution-level ``parse_failed`` record is written and ``None`` is
    returned so the caller leaves the institution out of the kept map. On a
    structurally-valid result, decisions are matched to ``candidate_urls`` by
    URL (:func:`match_triage_decisions`); each drifted/duplicate/missing entry
    gets one per-URL attrition record, the salvaged decisions are written to
    ``3_triage.json``, and the ``keep`` URLs are returned. The list may be
    empty (every decision was a casualty) — the institution is still represented
    rather than dropped wholesale, which is the behaviour this fix restores.
    """
    try:
        parsed = parse_triage_result(result)
    except Exception as exc:
        logger.warning("Stage 3 parse failed for %s: %s", result.custom_id, exc)
        attrition.record(
            run_dir, institution_id=result.custom_id, stage=stage,
            reason="parse_failed", detail=str(exc),
        )
        return None
    match = match_triage_decisions(candidate_urls, parsed)
    for casualty in match.attrition:
        attrition.record(
            run_dir, institution_id=result.custom_id, stage=stage,
            reason=casualty.reason, url=casualty.url, detail=casualty.detail,
        )
    inst_dir = institution_dir(run_dir, result.custom_id)
    if inst_dir.exists():
        (inst_dir / "3_triage.json").write_text(
            json.dumps(
                {"decisions": [d.model_dump() for d in match.decisions]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return match.kept_urls


def _run_classify_triage(
    run_dir: Path,
    sample: list[dict[str, Any]],
    discovery_general: dict[str, list[dict[str, Any]]],
    discovery_site_restricted: dict[str, list[dict[str, Any]]],
    official_sites: dict[str, str | None],
    *,
    run_id: str,
    model: str,
    poll_interval: int,
    max_wait: int,
    credentials: ResolvedCredentials | None = None,
) -> dict[str, list[str]]:
    """Stage 3 — URL triage batch over the dedup'd 1a+1b union.

    Per Q3=c (2026-05-09), the candidate set is the path-aware deduped union of
    Stage 1a and Stage 1b records (lowercase scheme + netloc, fold ``www.``,
    strip trailing slash on non-root paths, drop fragment; query string left
    intact). When 1b skipped (no official site), only 1a URLs are seen.

    Resume (Session E; chunked Session F.1): same shape as Stage 2 —
    done-marker short-circuit, then :func:`run_chunked_stage` owns chunking,
    reconciliation, polling, and no-auto-resubmit semantics.
    """
    stage = "classify_triage"
    if is_done(run_dir, stage):
        logger.info("Stage 3: .done marker present — skipping (resume from disk)")
        return _read_existing_triaged(run_dir, sample)

    candidates_by_inst: dict[str, list[str]] = {}
    # Always rebuild the candidates_by_inst lookup: it is the per-institution
    # candidate authority that persist_triage_result matches returned decisions
    # against by URL. Cheap (in-memory dedup union).
    for row in sample:
        institution = institution_record(row)
        inst_id = institution["institution_id"]
        candidate_urls = _candidate_urls_union(
            discovery_general, discovery_site_restricted, inst_id
        )
        if candidate_urls:
            candidates_by_inst[inst_id] = candidate_urls

    jobs = []
    for row in sample:
        institution = institution_record(row)
        inst_id = institution["institution_id"]
        candidate_urls = candidates_by_inst.get(inst_id)
        if not candidate_urls:
            continue
        jobs.append(
            build_triage_job(
                institution,
                candidate_urls,
                official_site=official_sites.get(inst_id),
                custom_id=inst_id,
            )
        )
    if not jobs and load_state(run_dir, stage) is None:
        mark_done(run_dir, stage, no_batch=True)
        return {}

    kept: dict[str, list[str]] = {}

    def _persist(results: Iterator[BatchResult]) -> None:
        for result in results:
            kept_urls = persist_triage_result(
                run_dir,
                result,
                candidates_by_inst.get(result.custom_id) or [],
                stage=stage,
            )
            if kept_urls is not None:
                kept[result.custom_id] = kept_urls

    # custom_id == institution_id for this stage, so the identity fallback in
    # llm_stage_timer needs no explicit mapping.
    with llm_stage_timer(run_dir, stage, {}):
        run_chunked_stage(
            run_dir, stage, jobs,
            run_id=run_id, model=model,
            poll_interval=poll_interval, max_wait=max_wait,
            process_chunk_results=_persist,
            credentials=credentials,
        )
    # Disk covers chunks fetched by a prior invocation (resume).
    return {**_read_existing_triaged(run_dir, sample), **kept}
