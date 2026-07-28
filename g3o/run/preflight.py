"""Pre-flight checks for a live ``--execute`` pre-sweep (P0-8, Session F.2 2026-06-10).

``g3o presweep --preflight ...`` runs the cheap, no-submit checks an operator
wants before committing real spend and ~4 days of wall-clock to a live run:

  1. API keys present and well-formed (Serper + OpenAI).
  2. Optionally a live ``verify-model`` round-trip (opt-in: it submits a real
     1-job batch and can block on the Batch SLA, so it is off by default).
  3. The planned sample (drawn deterministically, NOT written to disk).
  4. Projected Stage-5 job/chunk counts and input-file sizes, reusing the exact
     serializer (:func:`g3o.common.batch_client._serialize_job_line`) and the
     chunk caps from Session 1 — this is the F2 size blocker's early-warning.
  5. A cost preview from current gpt-5-nano Batch pricing.

No state files are written and no production batches are submitted. Job counts
beyond Stage 1 depend on discovery/scrape outputs that do not exist pre-run, so
the projections are explicitly labeled ESTIMATES built on stated assumptions
(per review F20's caution to separate estimate from fact). The cost ceiling
(Decision D7) is print-only for now: no abort gate is wired (researcher,
2026-06-10).
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.common import config as _config
from g3o.common.batch_client import (
    CHUNK_MAX_BYTES,
    CHUNK_MAX_REQUESTS,
    DEFAULT_ENDPOINT,
    _serialize_job_line,
)
from g3o.common.pricing import GPT5_NANO_PRICING, usd_for_tokens
from g3o.extract.batch import build_extract_jobs
from g3o.run.presweep import (
    PresweepConfig,
    institution_record,
    stratified_sample,
)
from g3o.scrape.render import FetchMetadata, RenderedPage

# Rough chars→tokens heuristic for cost estimation (English-ish text). Stated as
# an assumption in the output; not a billing-grade tokenizer.
_CHARS_PER_TOKEN = 4


@dataclass
class PreflightAssumptions:
    """Operator-visible assumptions behind the ESTIMATE projections."""

    pages_per_institution: int = 12  # review: "~12 kept URLs × 1,000 institutions"
    page_chars: int = 8_000  # typical extracted gov page; cap is 60k (worst case)
    output_tokens_per_job: int = 600  # mean contract response, rough
    official_site_rate: float = 0.7  # fraction of institutions reaching Stage 1b


def _key_check(name: str, value: str | None, *, prefix: str | None = None) -> dict[str, Any]:
    present = bool(value)
    well_formed = present and (prefix is None or value.startswith(prefix))
    return {
        "name": name,
        "present": present,
        "well_formed": well_formed,
        "note": (
            "ok" if well_formed
            else "missing" if not present
            else f"present but does not start with {prefix!r}"
        ),
    }


def _representative_extract_job_bytes(
    sample: list[dict[str, Any]], *, page_chars: int, model: str
) -> int:
    """Serialized byte size of one representative Stage-5 job (review F2 sizing).

    Reuses the production job builder and the exact JSONL serializer the chunker
    uses, so the per-job byte count is the real uploaded size — not a guess. The
    page text is synthetic filler of ``page_chars`` chars (the system message,
    ~39k chars, dominates regardless of the specific text).
    """
    institution = institution_record(sample[0])
    page = RenderedPage(
        url="https://example.gov/preflight-representative-page",
        text="x" * page_chars,
        title="Preflight representative page",
        content_type="html",
        fetch_metadata=FetchMetadata(
            access_date="2026-06-10", http_status=200,
            final_url=None, fetch_method="html", elapsed_ms=10, wait_for=None,
        ),
    )
    jobs = build_extract_jobs(
        [(institution, page)],
        batch_id="preflight",
        institution_search_languages="en",
    )
    return len(
        _serialize_job_line(
            jobs[0], model=model, response_format=jobs[0].response_format,
            endpoint=DEFAULT_ENDPOINT,
        )
    )


def _project_chunks(n_jobs: int, per_job_bytes: int) -> dict[str, Any]:
    """Project chunk count for ``n_jobs`` near-uniform jobs.

    Replicates the two caps in :func:`batch_client.split_jobs_into_chunks`
    (``CHUNK_MAX_BYTES`` and ``CHUNK_MAX_REQUESTS``). Analytic rather than
    materialized: a 12k-job Stage 5 would serialize to hundreds of MB, so the
    preflight must not build every job. Jobs are near-uniform because the ~39k-
    char system message dominates and page text is capped (review F3), so the
    greedy packer's result equals the ceiling division below.
    """
    total_bytes = n_jobs * per_job_bytes
    by_bytes = math.ceil(total_bytes / CHUNK_MAX_BYTES) if n_jobs else 0
    by_requests = math.ceil(n_jobs / CHUNK_MAX_REQUESTS) if n_jobs else 0
    n_chunks = max(by_bytes, by_requests)
    jobs_per_chunk = math.ceil(n_jobs / n_chunks) if n_chunks else 0
    return {
        "n_jobs": n_jobs,
        "per_job_bytes": per_job_bytes,
        "total_bytes": total_bytes,
        "n_chunks": n_chunks,
        "chunk_cap_bytes": CHUNK_MAX_BYTES,
        "chunk_cap_requests": CHUNK_MAX_REQUESTS,
        "approx_jobs_per_chunk": jobs_per_chunk,
        "approx_chunk_bytes": jobs_per_chunk * per_job_bytes,
        "single_job_exceeds_cap": per_job_bytes > CHUNK_MAX_BYTES,
    }


def run_preflight(
    config: PresweepConfig,
    *,
    assumptions: PreflightAssumptions | None = None,
    verify_model_live: bool = False,
    cost_ceiling_usd: float | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Run the no-submit pre-flight checks and return a structured summary.

    ``verify_model_live`` opts into a real 1-job ``verify-model`` batch (off by
    default — it submits and can block on the Batch SLA). ``cost_ceiling_usd``
    is print/return only unless set; D7 left it unset (no abort gate) for now.
    ``client`` is threaded into ``verify_model`` for test injection.
    """
    a = assumptions or PreflightAssumptions()
    summary: dict[str, Any] = {"run_id": config.run_id, "mode": "preflight"}

    # --- 1. Keys.
    keys = [
        _key_check("SERPER_API_KEY", _config.SERPER_API_KEY),
        _key_check("OPENAI_API_KEY", _config.OPENAI_API_KEY, prefix="sk-"),
    ]
    summary["keys"] = keys
    summary["keys_ok"] = all(k["well_formed"] for k in keys)

    # --- 2. Planned sample (drawn, not written).
    with open(config.master_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    sample = stratified_sample(
        rows,
        sample_size=config.sample_size,
        seed=config.seed,
        stratify_keys=config.stratify_keys,
    )
    n = len(sample)
    n_bypass = sum(1 for r in sample if institution_record(r).get("official_site_url"))
    n_strata = len({tuple(r.get(k, "") for k in config.stratify_keys) for r in rows})
    summary["sample"] = {
        "n_institutions": n,
        "n_strata_in_master": n_strata,
        "n_stage2_bypass": n_bypass,
        "n_stage2_llm": n - n_bypass,
    }
    if n == 0:
        summary["error"] = "planned sample is empty; nothing to project"
        return summary

    # --- 3. Model verification (opt-in).
    if verify_model_live:
        from g3o.run.verify_model import verify_model

        summary["verify_model"] = verify_model(
            model=config.model,
            poll_interval=config.poll_interval,
            max_wait=config.max_wait_per_stage,
        )
    else:
        summary["verify_model"] = {
            "skipped": True,
            "note": "pass --verify-model to run a live 1-job round-trip (submits a batch)",
        }

    # --- 4. Stage-5 job/chunk/size projection (the F2 blocker early-warning).
    per_job_bytes = _representative_extract_job_bytes(
        sample, page_chars=min(a.page_chars, config.extract_text_cap_chars),
        model=config.model,
    )
    n_extract_jobs = n * a.pages_per_institution
    summary["stage5_projection"] = {
        **_project_chunks(n_extract_jobs, per_job_bytes),
        "is_estimate": True,
        "assumes_pages_per_institution": a.pages_per_institution,
        "assumes_page_chars": min(a.page_chars, config.extract_text_cap_chars),
        "page_text_cap_chars": config.extract_text_cap_chars,
    }

    # --- 5. Cost preview (ESTIMATE).
    # Input tokens per job from the representative serialized size; output tokens
    # from the assumption. Stages 2/3/6 are ~one job per institution and far
    # smaller than Stage 5, so Stage 5 dominates; they are folded in at the
    # representative per-job input size as an order-of-magnitude add.
    in_tok_per_extract_job = (per_job_bytes / _CHARS_PER_TOKEN)
    # Jobs per stage: Stage 5 (extract) gets one job per kept page; Stages 2, 3, 6
    # get ~one job per institution. Use the same per-job input proxy for all
    # stages (their system prompts are shorter than Stage 5's; reusing the
    # Stage-5 figure is a conservative upper bound rather than an under-count).
    stage_jobs = {
        "classify_official_site": n,
        "classify_triage": n,
        "extract": n_extract_jobs,
        "validate": n,
    }
    p = GPT5_NANO_PRICING
    by_stage: dict[str, Any] = {}
    for stage, n_jobs_stage in stage_jobs.items():
        stage_in_tokens = n_jobs_stage * in_tok_per_extract_job
        stage_out_tokens = n_jobs_stage * a.output_tokens_per_job
        stage_input_usd = usd_for_tokens(stage_in_tokens, p["batch_input_per_1m_usd"])
        stage_output_usd = usd_for_tokens(stage_out_tokens, p["batch_output_per_1m_usd"])
        by_stage[stage] = {
            "n_jobs": n_jobs_stage,
            "est_input_tokens": round(stage_in_tokens),
            "est_output_tokens": round(stage_out_tokens),
            "est_usd": round(stage_input_usd + stage_output_usd, 2),
        }

    total_in_tokens = sum(n_jobs_stage * in_tok_per_extract_job for n_jobs_stage in stage_jobs.values())
    total_out_tokens = sum(n_jobs_stage * a.output_tokens_per_job for n_jobs_stage in stage_jobs.values())
    input_usd = usd_for_tokens(total_in_tokens, p["batch_input_per_1m_usd"])
    output_usd = usd_for_tokens(total_out_tokens, p["batch_output_per_1m_usd"])
    total_usd = input_usd + output_usd
    summary["cost_preview"] = {
        "is_estimate": True,
        "pricing": p,
        "chars_per_token_assumption": _CHARS_PER_TOKEN,
        "assumes_output_tokens_per_job": a.output_tokens_per_job,
        "est_input_tokens": round(total_in_tokens),
        "est_output_tokens": round(total_out_tokens),
        "est_openai_batch_input_usd": round(input_usd, 2),
        "est_openai_batch_output_usd": round(output_usd, 2),
        "est_openai_batch_total_usd": round(total_usd, 2),
        "by_stage": by_stage,
        "note": (
            "OpenAI Batch cost only. Serper (Stage 1) is billed separately and is "
            "order-of-magnitude ~$10 per the review; not priced here. Estimate "
            "scales with the pages-per-institution and page-chars assumptions."
        ),
    }
    summary["cost_ceiling_usd"] = cost_ceiling_usd
    if cost_ceiling_usd is not None:
        over = total_usd > cost_ceiling_usd
        summary["cost_ceiling_exceeded"] = over  # abort gate wiring lives in the CLI

    return summary


PREFLIGHT_ESTIMATE_NAME = "preflight_estimate.json"


def write_preflight_estimate(run_dir: Path, config: PresweepConfig) -> dict[str, Any]:
    """Compute the preflight cost estimate for ``config`` and persist it.

    Called automatically at the start of every run (not just standalone
    ``--preflight`` invocations) so ``runs/<run_id>/preflight_estimate.json``
    is always available for the end-of-run cost report to compare against,
    regardless of whether the operator ran a manual preflight check first.
    Reuses :func:`run_preflight` with ``verify_model_live=False`` (no submits)
    and the run's own assumption fields, so the estimate matches what a
    manual ``--preflight`` check with the same assumptions would produce.
    """
    assumptions = PreflightAssumptions(
        pages_per_institution=config.assume_pages_per_institution,
        page_chars=config.assume_page_chars,
        output_tokens_per_job=config.assume_output_tokens_per_job,
    )
    full_summary = run_preflight(
        config, assumptions=assumptions, verify_model_live=False, cost_ceiling_usd=None,
    )
    estimate = {
        "run_id": config.run_id,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "sample": full_summary.get("sample"),
        "stage5_projection": full_summary.get("stage5_projection"),
        "cost_preview": full_summary.get("cost_preview"),
    }
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / PREFLIGHT_ESTIMATE_NAME).write_text(
        json.dumps(estimate, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return estimate


__all__ = [
    "GPT5_NANO_PRICING",
    "PREFLIGHT_ESTIMATE_NAME",
    "PreflightAssumptions",
    "run_preflight",
    "write_preflight_estimate",
]
