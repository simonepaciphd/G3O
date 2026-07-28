"""Tests for `g3o.report.cost_report` — the automatic end-of-run cost report.

Covers: the normal case (preflight estimate + full actual usage present),
a missing preflight_estimate.json, a stage with partial/missing usage data,
and an unpriced model — each of which must degrade to an explicit
``"available": False`` marker rather than a silently wrong number.
"""

from __future__ import annotations

import json
from pathlib import Path

from g3o.report.cost_report import (
    compute_cost_report,
    render_cost_report_text,
    write_cost_report,
)

_CONFIG = {
    "max_workers": 5,
    "seed": 22294,
    "model": "gpt-5-nano",
    "dry_run": False,
    "stop_after": "validate",
    "scrape_respect_robots": True,
    "scrape_render_on_download_failure": False,
}


def _write_manifest(run_dir: Path, *, config: dict, llm_provenance: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "config": config,
                "llm_provenance": llm_provenance,
            }
        ),
        encoding="utf-8",
    )


def _write_preflight_estimate(run_dir: Path, *, total_usd: float, by_stage: dict) -> None:
    (run_dir / "preflight_estimate.json").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "sample": {"n_institutions": 5},
                "cost_preview": {
                    "est_openai_batch_total_usd": total_usd,
                    "by_stage": by_stage,
                },
            }
        ),
        encoding="utf-8",
    )


def _full_llm_provenance() -> dict:
    """One stage's worth of complete, usage-available provenance per stage."""
    per_stage = {
        "n_requests_total": 5, "n_requests_failed": 0,
        "total_prompt_tokens": 1_000_000, "total_completion_tokens": 200_000,
        "total_cached_tokens": 0, "usage_available": True,
    }
    return {
        stage: dict(per_stage)
        for stage in ("classify_official_site", "classify_triage", "extract", "validate")
    }


def _full_by_stage_estimate() -> dict:
    return {
        stage: {"n_jobs": 5, "est_input_tokens": 1_000_000, "est_output_tokens": 200_000, "est_usd": 0.10}
        for stage in ("classify_official_site", "classify_triage", "extract", "validate")
    }


def test_normal_case_computes_actual_and_comparison(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r1"
    _write_manifest(run_dir, config=_CONFIG, llm_provenance=_full_llm_provenance())
    _write_preflight_estimate(run_dir, total_usd=0.40, by_stage=_full_by_stage_estimate())

    report = compute_cost_report(run_dir)
    assert report["run_id"] == "r1"

    est = report["estimated"]
    assert est["available"] is True
    assert est["sample_size"] == 5
    assert est["configuration"]["max_workers"] == 5
    assert est["configuration"]["seed"] == 22294
    assert est["configuration"]["flags"]["dry_run"] is False
    assert est["total_estimated_usd"] == 0.40

    ob = report["actual"]["openai_batch"]
    assert ob["available"] is True
    assert ob["pricing_model"] == "gpt-5-nano"
    # 1,000,000 standard input tokens @ $0.025/1M + 200,000 output @ $0.20/1M,
    # per stage, times 4 stages.
    expected_per_stage = round((1_000_000 / 1_000_000) * 0.025 + (200_000 / 1_000_000) * 0.20, 4)
    assert ob["by_stage"]["extract"]["usd"] == expected_per_stage
    assert ob["total_usd"] == round(expected_per_stage * 4, 2)

    assert report["actual"]["serper"]["available"] is False
    assert report["actual"]["infra"]["available"] is False
    assert report["actual"]["total_actual_usd"] == ob["total_usd"]
    assert report["actual"]["total_actual_components_excluded"] == ["serper", "infra"]

    cmp_ = report["comparison"]
    assert cmp_["available"] is True
    assert cmp_["estimated_total_usd"] == 0.40
    assert cmp_["actual_total_usd"] == ob["total_usd"]
    assert cmp_["absolute_difference_usd"] == round(ob["total_usd"] - 0.40, 2)
    assert "extract" in cmp_["by_stage"]
    assert cmp_["by_stage"]["extract"]["available"] is True


def test_missing_preflight_estimate_marks_unavailable_but_actual_still_computes(
    tmp_path: Path,
):
    run_dir = tmp_path / "runs" / "r2"
    _write_manifest(run_dir, config=_CONFIG, llm_provenance=_full_llm_provenance())
    # No preflight_estimate.json written.

    report = compute_cost_report(run_dir)
    assert report["estimated"]["available"] is False
    assert "preflight_estimate.json" in report["estimated"]["reason"]
    # Configuration is still visible even though the estimate itself is not.
    assert report["estimated"]["configuration"]["max_workers"] == 5
    # Actual cost is independent of the estimate and still computes.
    assert report["actual"]["openai_batch"]["available"] is True
    # Comparison needs both sides.
    assert report["comparison"]["available"] is False
    assert "estimate unavailable" in report["comparison"]["reason"]


def test_stage_without_usage_data_marked_unavailable_individually(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r3"
    provenance = _full_llm_provenance()
    provenance["validate"]["usage_available"] = False
    _write_manifest(run_dir, config=_CONFIG, llm_provenance=provenance)
    _write_preflight_estimate(run_dir, total_usd=0.40, by_stage=_full_by_stage_estimate())

    report = compute_cost_report(run_dir)
    ob = report["actual"]["openai_batch"]
    assert ob["available"] is True  # other 3 stages still available
    assert ob["by_stage"]["validate"]["available"] is False
    assert ob["by_stage"]["validate"]["reason"] == "no usage data captured for this stage"
    assert ob["by_stage"]["extract"]["available"] is True
    # Total excludes the unavailable stage rather than treating it as $0.
    assert ob["total_usd"] == round(ob["by_stage"]["extract"]["usd"] * 3, 2)

    assert report["comparison"]["by_stage"]["validate"]["available"] is False


def test_stage_not_reached_marked_unavailable(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r4"
    provenance = _full_llm_provenance()
    del provenance["validate"]  # e.g. stop_after=extract, validate never ran
    _write_manifest(run_dir, config={**_CONFIG, "stop_after": "extract"}, llm_provenance=provenance)

    report = compute_cost_report(run_dir)
    ob = report["actual"]["openai_batch"]
    assert ob["by_stage"]["validate"]["available"] is False
    assert "not reached" in ob["by_stage"]["validate"]["reason"]


def test_unpriced_model_marks_actual_openai_unavailable(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r5"
    config = {**_CONFIG, "model": "some-future-model"}
    _write_manifest(run_dir, config=config, llm_provenance=_full_llm_provenance())
    _write_preflight_estimate(run_dir, total_usd=0.40, by_stage=_full_by_stage_estimate())

    report = compute_cost_report(run_dir)
    ob = report["actual"]["openai_batch"]
    assert ob["available"] is False
    assert "no pricing data" in ob["reason"]
    for stage_entry in ob["by_stage"].values():
        assert stage_entry["available"] is False
    assert report["actual"]["total_actual_usd"] is None
    assert report["actual"]["total_actual_components_excluded"] == [
        "openai_batch", "serper", "infra",
    ]
    assert report["comparison"]["available"] is False


def test_cached_tokens_priced_at_cached_rate(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r6"
    provenance = _full_llm_provenance()
    # extract: 1,000,000 prompt tokens, half of them cached.
    provenance["extract"]["total_cached_tokens"] = 500_000
    _write_manifest(run_dir, config=_CONFIG, llm_provenance=provenance)

    report = compute_cost_report(run_dir)
    extract = report["actual"]["openai_batch"]["by_stage"]["extract"]
    # 500k standard input @ $0.025/1M + 500k cached @ $0.0025/1M + 200k output @ $0.20/1M
    expected = round(
        (500_000 / 1_000_000) * 0.025 + (500_000 / 1_000_000) * 0.0025 + (200_000 / 1_000_000) * 0.20,
        4,
    )
    assert extract["usd"] == expected


def test_write_cost_report_persists_json(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r7"
    _write_manifest(run_dir, config=_CONFIG, llm_provenance=_full_llm_provenance())
    _write_preflight_estimate(run_dir, total_usd=0.40, by_stage=_full_by_stage_estimate())

    report = write_cost_report(run_dir)
    path = run_dir / "cost_report.json"
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_render_cost_report_text_handles_unavailable_sections(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r8"
    _write_manifest(run_dir, config=_CONFIG, llm_provenance={})
    report = compute_cost_report(run_dir)
    text = render_cost_report_text(report)
    assert "G3O Cost Report" in text
    assert "unavailable" in text
    assert "r8" in text


def test_no_manifest_returns_fully_unavailable_report(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r9"  # never created
    report = compute_cost_report(run_dir)
    assert report["estimated"]["available"] is False
    assert report["actual"]["openai_batch"]["available"] is False
    assert report["comparison"]["available"] is False
