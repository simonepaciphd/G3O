"""Stage 6 deterministic QC summary.

Counts only — no silent overwrites, no inferences. Surfaces anomalies that a
researcher can decide to investigate; the LLM does the consolidation, this
module just reports what landed.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from g3o.common.contract import ConsolidatedInstitutionResponse


def qc_per_institution(
    response: ConsolidatedInstitutionResponse,
) -> dict[str, Any]:
    """Deterministic counts for one consolidated institution."""
    activities = response.activities
    sources = response.sources

    cred_counter: Counter[str] = Counter(s.source_credibility for s in sources)
    type_counter: Counter[str] = Counter(s.source_type for s in sources)
    evidence_counter: Counter[str] = Counter(s.genai_evidence for s in sources)

    distinct_tools = sorted({a.tool_name for a in activities if a.tool_name != "unknown"})
    distinct_vendors = sorted({a.vendor for a in activities if a.vendor != "unknown"})
    activities_with_flags = [
        a.activity_id for a in activities if a.uncertainty_flags != "none"
    ]
    high_confidence_activities = [
        a.activity_id for a in activities if a.confidence == "high"
    ]

    return {
        "institution_id": response.institution.institution_id,
        "has_genai_activity": response.institution.has_genai_activity,
        "n_input_pages": response.consolidation_metadata.n_input_pages,
        "n_input_rows": response.consolidation_metadata.n_input_rows,
        "n_activities": len(activities),
        "n_sources": len(sources),
        "source_credibility": dict(cred_counter),
        "source_type": dict(type_counter),
        "genai_evidence": dict(evidence_counter),
        "distinct_tools": distinct_tools,
        "distinct_vendors": distinct_vendors,
        "activities_with_uncertainty_flags": activities_with_flags,
        "high_confidence_activities": high_confidence_activities,
    }


def _aggregate_credibility(per_inst: list[dict[str, Any]]) -> Counter[str]:
    out: Counter[str] = Counter()
    for q in per_inst:
        for k, v in q.get("source_credibility", {}).items():
            out[k] += v
    return out


def _aggregate_evidence(per_inst: list[dict[str, Any]]) -> Counter[str]:
    out: Counter[str] = Counter()
    for q in per_inst:
        for k, v in q.get("genai_evidence", {}).items():
            out[k] += v
    return out


def qc_per_run(run_dir: Path) -> dict[str, Any]:
    """Aggregate QC across every ``6_validate.json`` in a run directory.

    Walks ``run_dir/<institution_id>/6_validate.json``; institutions without
    a consolidated output are skipped (with a count surfaced). No exceptions
    raised on parse failure — failed institutions are counted, not surfaced
    as runtime errors.
    """
    if not run_dir.exists():
        raise FileNotFoundError(f"run_dir does not exist: {run_dir}")

    per_inst: list[dict[str, Any]] = []
    n_seen = 0
    n_consolidated = 0
    n_parse_failed = 0
    parse_failures: list[str] = []

    for institution_dir in sorted(run_dir.iterdir()):
        if not institution_dir.is_dir():
            continue
        n_seen += 1
        validate_path = institution_dir / "6_validate.json"
        if not validate_path.exists():
            continue
        try:
            payload = json.loads(validate_path.read_text(encoding="utf-8"))
            response = ConsolidatedInstitutionResponse.model_validate(payload)
        except Exception:
            n_parse_failed += 1
            parse_failures.append(institution_dir.name)
            continue
        per_inst.append(qc_per_institution(response))
        n_consolidated += 1

    hga_counter: Counter[str] = Counter(q["has_genai_activity"] for q in per_inst)
    cred_counter = _aggregate_credibility(per_inst)
    evidence_counter = _aggregate_evidence(per_inst)

    total_activities = sum(q["n_activities"] for q in per_inst)
    total_sources = sum(q["n_sources"] for q in per_inst)

    all_tools: Counter[str] = Counter()
    all_vendors: Counter[str] = Counter()
    for q in per_inst:
        for tool in q["distinct_tools"]:
            all_tools[tool] += 1
        for vendor in q["distinct_vendors"]:
            all_vendors[vendor] += 1

    return {
        "run_dir": str(run_dir),
        "n_institutions_in_dir": n_seen,
        "n_consolidated": n_consolidated,
        "n_missing_validate_json": n_seen - n_consolidated - n_parse_failed,
        "n_parse_failed": n_parse_failed,
        "parse_failures": parse_failures,
        "has_genai_activity": dict(hga_counter),
        "total_activities": total_activities,
        "total_sources": total_sources,
        "source_credibility": dict(cred_counter),
        "genai_evidence": dict(evidence_counter),
        "top_tools": all_tools.most_common(20),
        "top_vendors": all_vendors.most_common(20),
    }


__all__ = ["qc_per_institution", "qc_per_run"]
