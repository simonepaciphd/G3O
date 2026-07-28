"""End-of-run cost report: preflight estimate vs. actual OpenAI Batch spend.

Combines ``runs/<run_id>/preflight_estimate.json`` (written automatically at
run start by :func:`g3o.run.preflight.write_preflight_estimate`) with the
``llm_provenance`` block :func:`g3o.run.presweep.planning.update_manifest_llm_provenance`
folds into ``manifest.json`` (actual per-stage token usage, collected from
real OpenAI Batch responses) into:

- :func:`compute_cost_report` -> the report dict
- :func:`write_cost_report`   -> persists it to ``runs/<run_id>/cost_report.json``
- :func:`render_cost_report_text` -- the stdout renderer, following
  :mod:`g3o.report.render`'s text-renderer convention.

Serper and infrastructure (DigitalOcean) costs have no tracking mechanism
anywhere in this codebase — no call counter, no billing API integration — so
they are always reported as unavailable with a reason, per the requirement to
mark missing components explicitly rather than silently estimate them.

Read-only from disk except for the ``cost_report.json`` write. No network
calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.common.pricing import get_pricing, usd_for_tokens
from g3o.run.preflight import PREFLIGHT_ESTIMATE_NAME

# The four OpenAI-Batch stages, in pipeline order. Matches the keys
# preflight.py's cost_preview["by_stage"] and manifest.json's llm_provenance
# use, so the two sides of the comparison line up stage-for-stage.
_LLM_STAGES: tuple[str, ...] = (
    "classify_official_site",
    "classify_triage",
    "extract",
    "validate",
)

_UNAVAILABLE_SERPER = {
    "available": False,
    "reason": "no Serper call counter or pricing constant exists in this codebase",
}
_UNAVAILABLE_INFRA = {
    "available": False,
    "reason": "no infra/runtime cost telemetry exists in this codebase",
}


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    p = run_dir / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _configuration_from_manifest(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_workers": config.get("max_workers"),
        "seed": config.get("seed"),
        "flags": {
            "dry_run": config.get("dry_run"),
            "stop_after": config.get("stop_after"),
            "scrape_respect_robots": config.get("scrape_respect_robots"),
            "scrape_render_on_download_failure": config.get(
                "scrape_render_on_download_failure"
            ),
        },
    }


def _compute_estimated_section(
    run_dir: Path, run_id: str, config: dict[str, Any]
) -> dict[str, Any]:
    configuration = _configuration_from_manifest(config)
    path = run_dir / PREFLIGHT_ESTIMATE_NAME
    if not path.exists():
        return {
            "available": False,
            "reason": f"{PREFLIGHT_ESTIMATE_NAME} not found for this run",
            "configuration": configuration,
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    cost_preview = data.get("cost_preview") or {}
    sample = data.get("sample") or {}
    return {
        "available": True,
        "run_id": data.get("run_id", run_id),
        "sample_size": sample.get("n_institutions"),
        "configuration": configuration,
        "cost_preview": cost_preview,
        "total_estimated_usd": cost_preview.get("est_openai_batch_total_usd"),
    }


def _stage_actual(
    entry: dict[str, Any], pricing: dict[str, Any] | None
) -> dict[str, Any]:
    n_requests_total = entry.get("n_requests_total") or 0
    n_requests_failed = entry.get("n_requests_failed") or 0
    prompt_tokens = entry.get("total_prompt_tokens") or 0
    completion_tokens = entry.get("total_completion_tokens") or 0
    cached_tokens = entry.get("total_cached_tokens") or 0
    base = {
        "n_requests_total": n_requests_total,
        "n_requests_failed": n_requests_failed,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
    }
    if not entry.get("usage_available"):
        return {
            **base, "available": False, "usd": None,
            "reason": "no usage data captured for this stage",
        }
    if pricing is None:
        return {
            **base, "available": False, "usd": None,
            "reason": "no pricing data for this model",
        }
    non_cached_prompt = max(prompt_tokens - cached_tokens, 0)
    cached_rate = pricing.get("batch_cached_input_per_1m_usd", pricing["batch_input_per_1m_usd"])
    usd = (
        usd_for_tokens(non_cached_prompt, pricing["batch_input_per_1m_usd"])
        + usd_for_tokens(cached_tokens, cached_rate)
        + usd_for_tokens(completion_tokens, pricing["batch_output_per_1m_usd"])
    )
    return {**base, "available": True, "usd": round(usd, 4)}


def _compute_actual_openai(
    config: dict[str, Any], llm_provenance: dict[str, Any]
) -> dict[str, Any]:
    model = config.get("model")
    pricing = get_pricing(model) if model else None
    by_stage: dict[str, Any] = {}
    for stage in _LLM_STAGES:
        entry = llm_provenance.get(stage)
        if entry is None:
            by_stage[stage] = {
                "available": False,
                "reason": "stage not reached / no batch state recorded",
                "usd": None,
            }
            continue
        by_stage[stage] = _stage_actual(entry, pricing)

    available_usds = [s["usd"] for s in by_stage.values() if s.get("available")]
    any_available = bool(available_usds)
    result: dict[str, Any] = {
        "available": any_available,
        "pricing_model": model,
        "by_stage": by_stage,
        "total_prompt_tokens": sum(s.get("prompt_tokens") or 0 for s in by_stage.values()),
        "total_completion_tokens": sum(s.get("completion_tokens") or 0 for s in by_stage.values()),
        "total_cached_tokens": sum(s.get("cached_tokens") or 0 for s in by_stage.values()),
        "total_usd": round(sum(available_usds), 2) if any_available else None,
    }
    if not any_available:
        result["reason"] = (
            f"no pricing data for model {model!r}" if pricing is None
            else "no stage reported usable usage data"
        )
    return result


def _compute_actual_section(
    run_id: str, config: dict[str, Any], llm_provenance: dict[str, Any]
) -> dict[str, Any]:
    openai_batch = _compute_actual_openai(config, llm_provenance)
    included = ["openai_batch"] if openai_batch["available"] else []
    total_actual_usd = openai_batch["total_usd"] if openai_batch["available"] else None
    return {
        "run_id": run_id,
        "openai_batch": openai_batch,
        "serper": dict(_UNAVAILABLE_SERPER),
        "infra": dict(_UNAVAILABLE_INFRA),
        "total_actual_usd": total_actual_usd,
        "total_actual_components_included": included,
        "total_actual_components_excluded": [
            name for name in ("openai_batch", "serper", "infra") if name not in included
        ],
    }


def _compute_comparison(
    estimated: dict[str, Any], actual: dict[str, Any]
) -> dict[str, Any]:
    if not estimated.get("available"):
        return {"available": False, "reason": f"estimate unavailable: {estimated.get('reason')}"}
    openai_batch = actual["openai_batch"]
    if not openai_batch.get("available"):
        return {
            "available": False,
            "reason": f"actual cost unavailable: {openai_batch.get('reason')}",
        }
    est_total = estimated.get("total_estimated_usd")
    act_total = openai_batch.get("total_usd")
    if est_total is None or act_total is None:
        return {"available": False, "reason": "estimated or actual total missing"}

    abs_diff = round(act_total - est_total, 2)
    pct_diff = round((abs_diff / est_total) * 100, 1) if est_total else None

    est_by_stage = (estimated.get("cost_preview") or {}).get("by_stage") or {}
    act_by_stage = openai_batch.get("by_stage") or {}
    by_stage: dict[str, Any] = {}
    for stage in _LLM_STAGES:
        est_stage = est_by_stage.get(stage)
        act_stage = act_by_stage.get(stage)
        if est_stage is None or not act_stage or not act_stage.get("available"):
            by_stage[stage] = {
                "available": False,
                "reason": (
                    "no preflight estimate for this stage" if est_stage is None
                    else (act_stage or {}).get("reason", "actual cost unavailable for this stage")
                ),
            }
            continue
        est_usd = est_stage.get("est_usd")
        act_usd = act_stage.get("usd")
        stage_diff = round(act_usd - est_usd, 2)
        by_stage[stage] = {
            "available": True,
            "estimated_usd": est_usd,
            "actual_usd": act_usd,
            "absolute_difference_usd": stage_diff,
            "percentage_difference": round((stage_diff / est_usd) * 100, 1) if est_usd else None,
        }

    return {
        "available": True,
        "estimated_total_usd": est_total,
        "actual_total_usd": act_total,
        "absolute_difference_usd": abs_diff,
        "percentage_difference": pct_diff,
        "by_stage": by_stage,
        "note": (
            "Comparison covers OpenAI Batch cost only (the only component "
            "priced on the estimate side and tracked on the actual side); "
            "Serper and infra costs are excluded from both totals."
        ),
    }


def compute_cost_report(run_dir: str | Path) -> dict[str, Any]:
    """Build the cost report: estimated vs. actual vs. comparison."""
    run_dir = Path(run_dir)
    manifest = _load_manifest(run_dir)
    run_id = manifest.get("run_id", run_dir.name)
    config = manifest.get("config", {})
    llm_provenance = manifest.get("llm_provenance", {})

    estimated = _compute_estimated_section(run_dir, run_id, config)
    actual = _compute_actual_section(run_id, config, llm_provenance)
    comparison = _compute_comparison(estimated, actual)

    return {
        "run_id": run_id,
        "estimated": estimated,
        "actual": actual,
        "comparison": comparison,
    }


def render_cost_report_text(report: dict[str, Any]) -> str:
    """Render a cost report dict as a human-readable text block."""
    lines: list[str] = []
    w = lines.append
    w("=" * 70)
    w("  G3O Cost Report")
    w("=" * 70)
    w(f"  Run ID: {report.get('run_id', '?')}")
    w("")

    est = report.get("estimated", {})
    w("Estimated cost (preflight)")
    w("-" * 70)
    if est.get("available"):
        cfg = est.get("configuration", {})
        w(f"  Sample size           : {est.get('sample_size')}")
        w(f"  Max workers           : {cfg.get('max_workers')}")
        w(f"  Seed                  : {cfg.get('seed')}")
        w(f"  Flags                 : {cfg.get('flags')}")
        w(f"  Est. total (OpenAI)   : ${est.get('total_estimated_usd')}")
    else:
        w(f"  unavailable — {est.get('reason')}")
    w("")

    act = report.get("actual", {})
    ob = act.get("openai_batch", {})
    w("Actual cost")
    w("-" * 70)
    if ob.get("available"):
        w(f"  OpenAI Batch total    : ${ob.get('total_usd')}")
        w(f"    prompt tokens       : {ob.get('total_prompt_tokens')}")
        w(f"    completion tokens   : {ob.get('total_completion_tokens')}")
        w(f"    cached tokens       : {ob.get('total_cached_tokens')}")
        for stage, s in (ob.get("by_stage") or {}).items():
            if s.get("available"):
                w(f"    {stage:<24} ${s.get('usd'):<10} ({s.get('n_requests_total')} requests)")
            else:
                w(f"    {stage:<24} unavailable — {s.get('reason')}")
    else:
        w(f"  OpenAI Batch          : unavailable — {ob.get('reason')}")
    serper = act.get("serper", {})
    w(f"  Serper                : unavailable — {serper.get('reason')}")
    infra = act.get("infra", {})
    w(f"  Infra/runtime         : unavailable — {infra.get('reason')}")
    total = act.get("total_actual_usd")
    w(f"  Total actual cost     : {'$' + str(total) if total is not None else 'unavailable'}")
    if act.get("total_actual_components_excluded"):
        w(f"    (excludes: {', '.join(act['total_actual_components_excluded'])})")
    w("")

    cmp_ = report.get("comparison", {})
    w("Cost comparison (OpenAI Batch only)")
    w("-" * 70)
    if cmp_.get("available"):
        w(f"  Estimated total       : ${cmp_.get('estimated_total_usd')}")
        w(f"  Actual total          : ${cmp_.get('actual_total_usd')}")
        w(f"  Absolute difference   : ${cmp_.get('absolute_difference_usd')}")
        pct = cmp_.get("percentage_difference")
        w(f"  Percentage difference : {pct}%" if pct is not None else "  Percentage difference : n/a")
        w("  By stage:")
        for stage, s in (cmp_.get("by_stage") or {}).items():
            if s.get("available"):
                w(
                    f"    {stage:<24} est ${s.get('estimated_usd'):<8} "
                    f"act ${s.get('actual_usd'):<8} diff ${s.get('absolute_difference_usd')}"
                )
            else:
                w(f"    {stage:<24} unavailable — {s.get('reason')}")
    else:
        w(f"  unavailable — {cmp_.get('reason')}")

    return "\n".join(lines)


def write_cost_report(run_dir: str | Path) -> dict[str, Any]:
    """Compute the cost report and persist it to ``cost_report.json``."""
    run_dir = Path(run_dir)
    report = compute_cost_report(run_dir)
    (run_dir / "cost_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


__all__ = [
    "compute_cost_report",
    "render_cost_report_text",
    "write_cost_report",
]
