"""End-of-run timing aggregation + human-readable summary (Feature 3).

Combines ``runs/<run_id>/institution_report.jsonl`` (Feature 1) and every
``runs/<run_id>/<institution_id>/timing.json`` (Feature 2) into:

- :func:`compute_timing_summary` -> ``runs/<run_id>/timing_summary.json``
- :func:`compute_run_summary`    -> ``runs/<run_id>/run_summary.json``
  (persisted so run-level outcomes are not print-only, closing the gap noted
  in Phase 1)
- :func:`render_run_summary_text` -- the stdout renderer, following
  :mod:`g3o.report.render`'s text-renderer convention.

Read-only from disk. No network calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.common.institution_report import read_institution_report
from g3o.common.timing import iso_to_dt, read_timing

# Canonical stage order (matches g3o.run.presweep.config.STAGES).
_STAGE_ORDER: tuple[str, ...] = (
    "discovery_general",
    "classify_official_site",
    "discovery_site_restricted",
    "filter_eligibility",
    "classify_triage",
    "scrape",
    "extract",
    "validate",
)

# Must stay in sync with the statuses g3o.report.outcomes can emit: a status
# missing here is silently dropped from the breakdown (see compute_run_summary).
_FINAL_STATUSES: tuple[str, ...] = (
    "EVIDENCE_FOUND",
    "NO_EVIDENCE_FOUND",
    "PROCESSING_FAILED",
    "PROCESSING_INCOMPLETE",
    "RUN_TRUNCATED",
)


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    p = run_dir / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def compute_timing_summary(run_dir: str | Path, *, top_n: int = 10) -> dict[str, Any]:
    """Aggregate every institution's ``timing.json`` into run-level totals.

    ``slowest_institutions`` ranks only over ``timing_type="per_institution"``
    stages (discovery_general, discovery_site_restricted, scrape) -- the four
    Batch/LLM stages share one wall-clock window across many institutions, so
    including them would rank institutions by which chunk they happened to
    land in, not by real per-institution cost.

    ``stage_totals`` sums *every* stage (including the shared-chunk ones) for
    capacity planning. For a shared_chunk stage, entries with byte-identical
    (start_time, end_time, duration_seconds) are the same chunk recorded once
    per institution in it; they are de-duplicated before summing so a chunk's
    wall-clock time is counted once, not once per institution.

    Each stage entry also carries ``wall_clock_seconds`` -- the true elapsed
    time the pipeline spent on that stage overall, from the earliest
    ``start_time`` to the latest ``end_time`` across every institution that
    hit it -- and ``institutions``, that same stage's own per-institution
    ``duration_seconds`` list (sorted slowest-first) so a caller can see both
    "how long did institution X take at this stage" and "how long did the
    whole stage take" side by side. For the per_institution stages
    (discovery_general, discovery_site_restricted, scrape), which run
    concurrently (Stage 1a/1b/4, 2026-07), ``total_seconds`` sums each
    institution's own duration and so overstates real elapsed time whenever
    ``max_workers`` > 1 -- N institutions each taking 2s, run 5-way
    concurrent, sum to 2*N seconds of ``total_seconds`` but only
    ~2*ceil(N/5) seconds of ``wall_clock_seconds``. Use ``total_seconds`` for
    total compute/API cost, ``wall_clock_seconds`` for how long the stage
    actually took on the clock. Both start/end timestamps are parsed via
    :func:`g3o.common.timing.iso_to_dt`, which keeps microsecond precision --
    fast per-institution stages (sub-second work) get a sub-second-accurate
    ``wall_clock_seconds`` instead of collapsing to whole-second buckets.
    """
    run_dir = Path(run_dir)
    manifest = _load_manifest(run_dir)
    institution_ids: list[str] = manifest.get("institutions", [])

    per_institution_totals: dict[str, float] = {}
    total_durations: list[float] = []
    stage_entries: dict[str, list[tuple[str, str, str, float]]] = {}
    stage_timing_type: dict[str, str] = {}
    all_starts: list[str] = []
    all_ends: list[str] = []

    for inst_id in institution_ids:
        timing = read_timing(run_dir, inst_id)
        if not timing:
            continue
        if timing.get("total_duration_seconds") is not None:
            total_durations.append(timing["total_duration_seconds"])
        per_inst_total = 0.0
        for stage, entry in timing.get("stages", {}).items():
            start, end, duration, ttype = (
                entry["start_time"], entry["end_time"],
                entry["duration_seconds"], entry["timing_type"],
            )
            stage_entries.setdefault(stage, []).append((inst_id, start, end, duration))
            stage_timing_type[stage] = ttype
            all_starts.append(start)
            all_ends.append(end)
            if ttype == "per_institution":
                per_inst_total += duration
        per_institution_totals[inst_id] = per_inst_total

    stage_totals: dict[str, Any] = {}
    for stage, entries in stage_entries.items():
        ttype = stage_timing_type[stage]
        if ttype == "shared_chunk":
            unique = {(s, e, d) for _, s, e, d in entries}
            total = sum(d for _, _, d in unique)
        else:
            total = sum(d for _, _, _, d in entries)
        wall_clock = round(
            (
                iso_to_dt(max(e for _, _, e, _ in entries))
                - iso_to_dt(min(s for _, s, _, _ in entries))
            ).total_seconds(),
            6,
        )
        stage_totals[stage] = {
            "timing_type": ttype,
            "total_seconds": round(total, 6),
            "wall_clock_seconds": wall_clock,
            "institutions": [
                {"institution_id": iid, "duration_seconds": round(d, 6)}
                for iid, _, _, d in sorted(entries, key=lambda e: e[3], reverse=True)
            ],
        }

    slowest = sorted(per_institution_totals.items(), key=lambda kv: kv[1], reverse=True)[:top_n]

    total_run_duration_seconds = None
    if all_starts and all_ends:
        total_run_duration_seconds = round(
            (iso_to_dt(max(all_ends)) - iso_to_dt(min(all_starts))).total_seconds(), 6
        )

    avg_runtime = round(sum(total_durations) / len(total_durations), 6) if total_durations else None

    return {
        "run_id": manifest.get("run_id", run_dir.name),
        "n_institutions_with_timing": len(per_institution_totals),
        "total_run_duration_seconds": total_run_duration_seconds,
        "average_institution_runtime_seconds": avg_runtime,
        "slowest_institutions": [
            {"institution_id": iid, "per_institution_duration_seconds": round(d, 6)}
            for iid, d in slowest
        ],
        "slowest_institutions_note": (
            "Ranked only over timing_type=\"per_institution\" stages "
            "(discovery_general, discovery_site_restricted, scrape); the four "
            "Batch/LLM stages share one wall-clock window across many "
            "institutions and are excluded from this per-institution ranking."
        ),
        "stage_totals": stage_totals,
    }


def compute_run_summary(run_dir: str | Path) -> dict[str, Any]:
    """Build the run-level summary: final-status breakdown + per-stage
    completion counts + per-stage timing totals."""
    run_dir = Path(run_dir)
    manifest = _load_manifest(run_dir)
    institution_ids: list[str] = manifest.get("institutions", [])
    n_institutions = len(institution_ids)

    report_records = read_institution_report(run_dir)
    final_status_counts = {status: 0 for status in _FINAL_STATUSES}
    stage_reached_by_inst: dict[str, str | None] = {}
    for r in report_records:
        status = r.get("final_status")
        if status in final_status_counts:
            final_status_counts[status] += 1
        stage_reached_by_inst[r["institution_id"]] = r.get("stage_reached")

    stage_index = {s: i for i, s in enumerate(_STAGE_ORDER)}
    per_stage_completion = {s: 0 for s in _STAGE_ORDER}
    for stage_reached in stage_reached_by_inst.values():
        idx = stage_index.get(stage_reached) if stage_reached else None
        if idx is None:
            continue
        for s in _STAGE_ORDER[: idx + 1]:
            per_stage_completion[s] += 1

    timing_summary = compute_timing_summary(run_dir)

    return {
        "run_id": manifest.get("run_id", run_dir.name),
        "n_institutions": n_institutions,
        "stopped_after_stage": manifest.get("config", {}).get("stop_after"),
        "final_status_counts": final_status_counts,
        "per_stage_completion": {
            s: {"completed": c, "total": n_institutions}
            for s, c in per_stage_completion.items()
        },
        "stage_totals_seconds": timing_summary["stage_totals"],
        "total_run_duration_seconds": timing_summary["total_run_duration_seconds"],
        "average_institution_runtime_seconds": timing_summary["average_institution_runtime_seconds"],
    }


def render_run_summary_text(summary: dict[str, Any]) -> str:
    """Render a run summary dict as a human-readable text block."""
    lines: list[str] = []
    w = lines.append
    w("=" * 70)
    w("  G3O Run Summary")
    w("=" * 70)
    w(f"  Run ID              : {summary.get('run_id', '?')}")
    w(f"  Institutions started: {summary.get('n_institutions', '?')}")
    stopped = summary.get("stopped_after_stage")
    if stopped:
        w(f"  Stopped after stage : {stopped}")
    w("")
    w("Final status breakdown")
    w("-" * 70)
    counts = summary.get("final_status_counts", {})
    for status in _FINAL_STATUSES:
        w(f"  {status:<20} {counts.get(status, 0)}")
    w("")
    w("Per-stage completion (institutions reaching this stage / total)")
    w("-" * 70)
    for stage in _STAGE_ORDER:
        d = summary.get("per_stage_completion", {}).get(stage, {"completed": 0, "total": 0})
        w(f"  {stage:<28} {d['completed']}/{d['total']}")
    w("")
    w("Per-stage timing (per institution, stage total next to it)")
    w("-" * 70)
    for stage in _STAGE_ORDER:
        d = summary.get("stage_totals_seconds", {}).get(stage)
        if d is None:
            w(f"  {stage} — not_run")
            continue
        w(
            f"  {stage} — stage total: {d['total_seconds']:.3f}s sum, "
            f"{d['wall_clock_seconds']:.3f}s wall  ({d['timing_type']})"
        )
        for inst in d.get("institutions", []):
            w(f"      {inst['institution_id']:<28} {inst['duration_seconds']:>10.3f}s")
        w("")
    total_dur = summary.get("total_run_duration_seconds")
    avg_dur = summary.get("average_institution_runtime_seconds")
    w(f"  Total run duration      : {total_dur}")
    w(f"  Avg institution runtime : {avg_dur}")
    return "\n".join(lines)


def write_run_summary(run_dir: str | Path) -> dict[str, Any]:
    """Compute the run summary and persist it to ``run_summary.json``.

    Also computes and persists ``timing_summary.json`` (Feature 2's run-level
    aggregate) since both are derived from the same per-institution timing
    data and are naturally produced together at end of run.
    """
    run_dir = Path(run_dir)
    timing_summary = compute_timing_summary(run_dir)
    (run_dir / "timing_summary.json").write_text(
        json.dumps(timing_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = compute_run_summary(run_dir)
    (run_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


__all__ = [
    "compute_run_summary",
    "compute_timing_summary",
    "render_run_summary_text",
    "write_run_summary",
]
