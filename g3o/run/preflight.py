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
  5. A cost preview covering every paid API (2026-10-02): each LLM stage at its
     own model's rates (jev or OpenAI), Serper credits, and Web Unlocker bytes.
  6. Which paid services the run will actually use, the deployed commit against
     ``origin/main``, and a ``warnings`` list naming every silent degradation
     (a missing optional key, a stale checkout) — see
     :mod:`g3o.common.deployment`.

No state files are written and no production batches are submitted. Job counts
beyond Stage 1 depend on discovery/scrape outputs that do not exist pre-run, so
the projections are explicitly labeled ESTIMATES built on stated assumptions
(per review F20's caution to separate estimate from fact).

The cost ceiling (Decision D7, superseded by PR #52) is now an abort gate: a
projection over the limit exits 3 rather than merely printing. This module
computes and reports it as `cost_ceiling_exceeded`; the abort itself lives in
`g3o.cli._cmd_presweep`, on both the `--preflight` and `--execute` paths. The
limit is read from `G3O_BUDGET_LIMIT_USD` (env var) or `--cost-ceiling` (CLI
flag, takes precedence).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from typing import Any

from g3o.common import deployment
from g3o.common.batch_client import (
    CHUNK_MAX_BYTES,
    CHUNK_MAX_REQUESTS,
    DEFAULT_ENDPOINT,
    _serialize_job_line,
)
from g3o.common.cost_monitor import UnpricedModelError
from g3o.common.credentials import Credentials, resolve
from g3o.common.pricing import (
    GPT5_NANO_PRICING,
    pricing_for,
    serper_usd,
    unlocker_usd,
    usd,
)
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
    # Serper credits per institution (2026-10-02). None = derived from the
    # discovery config by :func:`_serper_credits_per_institution`.
    serper_credits_per_institution: float | None = None
    # Web Unlocker requests per institution. Measured 2026-10-02 on sweep 4
    # (r20260912T001021Z-f4fb, n=20,293): 6,066 fetches failed with a status the
    # unlocker escalates on (None/401/403) + 3,412 empty-page renders = 9,478,
    # i.e. 0.467 per institution.
    unlocker_requests_per_institution: float = 0.47
    # Billable bytes per unlocker request. ASSUMPTION, about twice the measured
    # mean: 12 sweep-4 blocked URLs through the unlocker on 2026-10-02 gave 8
    # successes, mean 128,270 B, max 284,492 B. Doubled for PDF-heavy samples,
    # and every request is counted as billed.
    unlocker_bytes_per_request: int = 250_000


def _serper_credits_per_institution(config: PresweepConfig) -> tuple[float, str]:
    """Projected Serper credits per institution, and where the figure comes from.

    One credit per query at ``num=10``. Measured as queries persisted per
    institution, i.e. with no cache discount, which is the conservative reading.
    """
    if config.discovery_mode == "legacy":
        return 8.52, "measured 2026-08-01 (200 institutions, legacy mode)"
    if config.discovery_leg1_multilingual or config.discovery_evidence_open:
        return 4.52, (
            "sweep 4 (n=20,293, chain + leg-1 fallback + open evidence leg): "
            "91,697 persisted queries, cache hits counted as live"
        )
    return 1.84, "measured 2026-08-01 (200 institutions, chain mode, legs 1a+1b only)"


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

    Replicates **two of the three** caps in
    :func:`batch_client.split_jobs_into_chunks` — ``CHUNK_MAX_BYTES`` and
    ``CHUNK_MAX_REQUESTS``. It does **not** model the third, ``max_tokens``
    (defaulting to :func:`batch_client.enqueued_token_budget`), so the chunk
    count below can understate what the submit path will actually produce.

    That gap used to matter a great deal and no longer does: the enqueued-token
    ceiling was 2M, which is what rejected Stage 5's first submit at n=100 (681
    jobs needing ~10.6M). PR #89 raised it to 15e9 on the move to a Tier-5
    project, so at any n this project contemplates ``CHUNK_MAX_BYTES`` binds
    first and the token cap does not bind at all. Correcting the docstring
    rather than the arithmetic is therefore deliberate (PI call, 2026-08-24) —
    the stale *claim* was the durable hazard, since the next reader would have
    trusted it. Folding the real chunker in, so the two cannot drift again, is
    the better fix and belongs to whoever does it with a measurement attached.

    Analytic rather than materialized: a 12k-job Stage 5 would serialize to
    hundreds of MB, so the preflight must not build every job. Jobs are
    near-uniform because the ~39k-char system message dominates and page text is
    capped (review F3), so the greedy packer's result equals the ceiling
    division below.
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


def _unpriced_cost_preview(
    model: str,
    *,
    total_in_tokens: float,
    total_out_tokens: float,
    output_tokens_per_job: int,
) -> dict[str, Any]:
    """A cost preview for a model with no rate row (review F2, ruling half 2).

    Same shape as the priced preview so a consumer needs no special case, but
    every USD slot is ``None`` and ``priced`` is False. The token projection is
    unaffected — it never depended on the rates — so this still answers "how big
    is this run", just not "what will it cost".

    Only reachable without a cost ceiling; with one, :func:`run_preflight`
    raises instead.
    """
    return {
        "is_estimate": True,
        "pricing": {"model": model, "priced": False},
        "chars_per_token_assumption": _CHARS_PER_TOKEN,
        "assumes_output_tokens_per_job": output_tokens_per_job,
        "est_input_tokens": round(total_in_tokens),
        "est_output_tokens": round(total_out_tokens),
        "est_openai_batch_input_usd": None,
        "est_openai_batch_output_usd": None,
        "est_openai_batch_total_usd": None,
        "stage_estimates": None,
        "note": (
            f"no rate row is registered for model {model!r}, so this run cannot "
            f"be priced and every USD figure above is null. The token projection "
            f"is unaffected. Add a row to g3o.common.pricing.PRICING to price it; "
            f"a run with a --cost-ceiling is refused outright rather than "
            f"projected this way."
        ),
    }


def run_preflight(
    config: PresweepConfig,
    *,
    assumptions: PreflightAssumptions | None = None,
    verify_model_live: bool = False,
    cost_ceiling_usd: float | None = None,
    client: Any | None = None,
    credentials: Credentials | None = None,
    check_deployment: bool = False,
) -> dict[str, Any]:
    """Run the no-submit pre-flight checks and return a structured summary.

    ``check_deployment`` adds the deployed-commit check (a ``git ls-remote``
    against ``origin``). The CLI turns it on; it is off by default so library
    and test callers do not touch the network.

    ``verify_model_live`` opts into a real 1-job ``verify-model`` batch (off by
    default — it submits and can block on the Batch SLA).

    ``cost_ceiling_usd`` only *reports*: this function returns
    ``cost_ceiling_exceeded`` in the summary and never aborts. The abort gate
    lives one layer up, in ``g3o.cli._cmd_presweep``, which exits 3 on that
    flag and enforces it on both the ``--preflight`` and ``--execute`` paths
    (supersedes Decision D7; PR #52). The limit is sourced from
    ``G3O_BUDGET_LIMIT_USD`` or ``--cost-ceiling``, the flag taking precedence.
    A programmatic caller that bypasses the CLI therefore gets the projection
    and no gate, and must check the flag itself.

    ``client`` is threaded into ``verify_model`` for test injection. It genuinely
    is, as of 2026-08-11: the parameter existed and was documented but never
    passed, which left the one live-submitting branch of this function untestable.

    ``credentials`` (Run API spec §3.1) are the keys the projected run would use;
    omitted, they resolve from the environment. The key-readiness check reports on
    the resolved bundle, so ``keys_ok`` answers "could *this* run authenticate",
    not "was some key present when the process started" — and ``--verify-model``
    now spends on that same resolved key rather than on the ambient one, so the
    report and the submit can no longer disagree about which key is in play.
    """
    a = assumptions or PreflightAssumptions()
    # ``run_id or None``: since the id may be minted at launch (spec §2), a
    # preflight can legitimately run before one exists. Reporting null says "no run
    # yet" honestly; reporting "" would read as a run whose id went missing.
    summary: dict[str, Any] = {"run_id": config.run_id or None, "mode": "preflight"}

    # --- 1. Keys. Resolved through the credential resolver (Run API spec §3.1),
    # so the readiness check reports on the keys this run would actually spend —
    # an explicitly-passed key included — rather than on whatever the process
    # environment held at import time. The names stay the env-var names because
    # that is what an operator reading the report has to go fix.
    resolved = resolve(credentials)
    stage_models = {
        stage: config.model_for_stage(stage)
        for stage in ("classify_official_site", "classify_triage", "extract", "validate")
    }
    keys = [_key_check("SERPER_API_KEY", resolved.serper_api_key)]
    if any(not m.startswith("jev-") for m in stage_models.values()):
        keys.append(_key_check("OPENAI_API_KEY", resolved.openai_api_key, prefix="sk-"))
    if any(m.startswith("jev-") for m in stage_models.values()):
        # Jev is the default for Stages 2/3/6, and a live run refuses to start
        # without its key (orchestrator._assert_live_keys); the preflight did not
        # check it, so a ready-looking preflight could precede a refused run.
        keys.append(_key_check("TYPESAFE_API_KEY", resolved.typesafe_api_key))
    summary["keys"] = keys
    summary["keys_ok"] = all(k["well_formed"] for k in keys)
    services = deployment.services_status(config, resolved)
    summary["services"] = services
    deploy = deployment.deployment_status() if check_deployment else None
    summary["deployment"] = deploy
    summary["warnings"] = deployment.warnings_for(services, deploy)

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
            client=client,
            credentials=resolved,
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
    extract_in_tokens = n_extract_jobs * in_tok_per_extract_job
    extract_out_tokens = n_extract_jobs * a.output_tokens_per_job
    per_inst_stage_jobs = n + n + n  # stages 2, 3, 6 ≈ one job/institution each
    # Use a conservative per-job input proxy for the smaller stages (their system
    # prompts are shorter than Stage 5's; reuse the Stage-5 figure as an upper
    # bound rather than under-count).
    other_in_tokens = per_inst_stage_jobs * in_tok_per_extract_job
    other_out_tokens = per_inst_stage_jobs * a.output_tokens_per_job

    total_in_tokens = extract_in_tokens + other_in_tokens
    total_out_tokens = extract_out_tokens + other_out_tokens
    # Rates per stage, for the model each stage will actually submit (review F2,
    # 2026-08-24; per-stage since 2026-10-02). Pricing every stage at the
    # run-wide model priced the jev stages at OpenAI rates.
    stage_pricing = {stage: pricing_for(model) for stage, model in stage_models.items()}
    unpriced = [stage_models[s] for s, row in stage_pricing.items() if row is None]
    if unpriced:
        # PI ruling half 1: a ceiling cannot be enforced for a model we cannot
        # price, so refuse here — before verify-model spends anything, and on
        # both cost gates at once, since each only runs a preflight when a
        # ceiling is set.
        if cost_ceiling_usd is not None:
            raise UnpricedModelError(unpriced[0], budget_usd=cost_ceiling_usd)
        # Half 2: no ceiling, so the run may proceed — but it is projected in
        # tokens with null USD rather than being quietly priced as nano.
        summary["cost_preview"] = _unpriced_cost_preview(
            unpriced[0],
            total_in_tokens=total_in_tokens,
            total_out_tokens=total_out_tokens,
            output_tokens_per_job=a.output_tokens_per_job,
        )
        summary["cost_ceiling_usd"] = None
        return summary

    # Per-stage token volumes (Gap 2). Stages 2, 3, 6 are ~one job per
    # institution each and split the "other" volume equally; Stage 5 is
    # n_institutions × pages_per_institution jobs.
    other_per_stage = (other_in_tokens / 3, other_out_tokens / 3)
    stage_tokens = {
        "classify_official_site": other_per_stage,
        "classify_triage": other_per_stage,
        "extract": (extract_in_tokens, extract_out_tokens),
        "validate": other_per_stage,
    }
    stage_estimates: dict[str, float] = {}
    stage_in_usd: dict[str, float] = {}
    stage_out_usd: dict[str, float] = {}
    for stage, (tin, tout) in stage_tokens.items():
        row = stage_pricing[stage]
        stage_in_usd[stage] = usd(tin, row["batch_input_per_1m_usd"])
        stage_out_usd[stage] = usd(tout, row["batch_output_per_1m_usd"])
        stage_estimates[stage] = stage_in_usd[stage] + stage_out_usd[stage]
    openai_stages = [s for s, m in stage_models.items() if not m.startswith("jev-")]
    input_usd = sum(stage_in_usd[s] for s in openai_stages)
    output_usd = sum(stage_out_usd[s] for s in openai_stages)
    openai_usd = input_usd + output_usd
    typesafe_usd = sum(stage_estimates[s] for s in stage_models if s not in openai_stages)
    llm_usd = openai_usd + typesafe_usd

    # Metered APIs (PI ruling 2026-10-02: one ceiling covers every paid API).
    credits_per_inst, credits_source = (
        (a.serper_credits_per_institution, "operator assumption")
        if a.serper_credits_per_institution is not None
        else _serper_credits_per_institution(config)
    )
    est_credits = n * credits_per_inst
    serper_est = serper_usd(est_credits)
    unlocker_on = services["brightdata_unlocker"]["active"]
    est_unlocker_requests = n * a.unlocker_requests_per_institution if unlocker_on else 0.0
    est_unlocker_bytes = est_unlocker_requests * a.unlocker_bytes_per_request
    unlocker_est = unlocker_usd(est_unlocker_bytes)
    total_usd = llm_usd + serper_est + unlocker_est

    summary["cost_preview"] = {
        "is_estimate": True,
        # Copied, not aliased: this was a direct reference to the module-level
        # rate table, so any consumer mutating the summary would have mutated
        # the pricing registry for the rest of the process.
        # The run-wide model's row, as before; per-stage rows beside it.
        "pricing": dict(pricing_for(config.model) or stage_pricing["extract"]),
        "stage_pricing": {stage: dict(row) for stage, row in stage_pricing.items()},
        "stage_models": stage_models,
        "chars_per_token_assumption": _CHARS_PER_TOKEN,
        "assumes_output_tokens_per_job": a.output_tokens_per_job,
        "est_input_tokens": round(total_in_tokens),
        "est_output_tokens": round(total_out_tokens),
        # OpenAI-vendor stages only (the name says so); jev is in est_by_api.
        "est_openai_batch_input_usd": round(input_usd, 2),
        "est_openai_batch_output_usd": round(output_usd, 2),
        "est_openai_batch_total_usd": round(openai_usd, 2),
        "est_by_api": {
            "openai": round(openai_usd, 2),
            "typesafe": round(typesafe_usd, 2),
            "serper": round(serper_est, 2),
            "brightdata_unlocker": round(unlocker_est, 2),
        },
        # The figure the ceiling is compared against: every paid API.
        "est_total_usd": round(total_usd, 2),
        "stage_estimates": {k: round(v, 6) for k, v in stage_estimates.items()},
        "serper": {
            "est_credits": round(est_credits),
            "credits_per_institution": credits_per_inst,
            "credits_source": credits_source,
            "usd_per_credit": serper_usd(1),
        },
        "brightdata_unlocker": {
            "active": unlocker_on,
            "est_requests": round(est_unlocker_requests),
            "assumes_requests_per_institution": a.unlocker_requests_per_institution,
            "assumes_bytes_per_request": a.unlocker_bytes_per_request,
        },
        "note": (
            "Every paid API (PI ruling 2026-10-02). LLM stages at their own "
            "model's rates, with the Stage-5 per-job size as an upper bound for "
            "the smaller stages; Serper at the credits-per-institution shown, "
            "cache hits counted as live; Web Unlocker at the measured sweep-4 "
            "escalation rate and an assumed 250 KB per request. The residential "
            "proxy, if set, is not priced. Runtime enforcement counts actual "
            "spend; this projection only gates the start."
        ),
    }
    summary["cost_ceiling_usd"] = cost_ceiling_usd
    if cost_ceiling_usd is not None:
        over = total_usd > cost_ceiling_usd
        summary["cost_ceiling_exceeded"] = over  # abort gate wiring lives in the CLI

    return summary


__all__ = [
    "GPT5_NANO_PRICING",
    "PreflightAssumptions",
    "UnpricedModelError",
    "pricing_for",
    "run_preflight",
]
