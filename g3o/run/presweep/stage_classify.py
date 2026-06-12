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
from g3o.classify.url_triage import build_triage_job, parse_triage_result
from g3o.common import attrition
from g3o.common.batch_client import BatchResult
from g3o.common.run_state import is_done, load_state, mark_done, run_chunked_stage
from g3o.run.presweep.records import (
    _dedupe_key,
    institution_record,
    synth_institution_id,
)

logger = logging.getLogger(__name__)


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
        path = run_dir / inst_id / "2_official_site.json"
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
        path = run_dir / inst_id / "3_triage.json"
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
    for row in sample:
        institution = institution_record(row)
        inst_id = institution["institution_id"]
        bypass_url = institution.get("official_site_url")
        if bypass_url:
            out[inst_id] = bypass_url
            bypass_count += 1
            inst_dir = run_dir / inst_id
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
            inst_dir = run_dir / result.custom_id
            if inst_dir.exists():
                (inst_dir / "2_official_site.json").write_text(
                    json.dumps(parsed.model_dump(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    run_chunked_stage(
        run_dir, stage, jobs,
        run_id=run_id, model=model,
        poll_interval=poll_interval, max_wait=max_wait,
        process_chunk_results=_persist, bypass_count=bypass_count,
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
    # Always rebuild the candidates_by_inst lookup so parse_triage_result can
    # validate expected_urls round-trip; it's cheap (in-memory dedup union).
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
            try:
                parsed = parse_triage_result(
                    result, expected_urls=candidates_by_inst.get(result.custom_id)
                )
            except Exception as exc:
                logger.warning("Stage 3 parse failed for %s: %s", result.custom_id, exc)
                attrition.record(
                    run_dir, institution_id=result.custom_id, stage=stage,
                    reason="parse_failed", detail=str(exc),
                )
                continue
            kept_urls = [d.url for d in parsed.decisions if d.decision == "keep"]
            kept[result.custom_id] = kept_urls
            inst_dir = run_dir / result.custom_id
            if inst_dir.exists():
                (inst_dir / "3_triage.json").write_text(
                    json.dumps(parsed.model_dump(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    run_chunked_stage(
        run_dir, stage, jobs,
        run_id=run_id, model=model,
        poll_interval=poll_interval, max_wait=max_wait,
        process_chunk_results=_persist,
    )
    # Disk covers chunks fetched by a prior invocation (resume).
    return {**_read_existing_triaged(run_dir, sample), **kept}
