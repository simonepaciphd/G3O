"""Stage 6 deterministic QC summary.

Counts only — no silent overwrites, no inferences. Surfaces anomalies that a
researcher can decide to investigate; the LLM does the consolidation, this
module just reports what landed.

Batch 2 (definition-adherence enforcement, 2026-07) adds two heuristic,
audit-only flags that surface candidate over-coding for human review. They
are keyword screens over free-text ``source_snippet`` fields — deliberately
crude, definitely both under- and over-inclusive — and they never change a
persisted value or reject a response. They exist to make it cheap to sample
the institutions most likely to carry the two failure modes named in the
June validation report (automation/RPA coded as GenAI; speculative "might
adopt" language coded as a confirmed activity), not to redefine what counts
as GenAI. The definition and enum values remain exactly as specified in
``output_contract.md`` / ``g3o.common.contract``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from g3o.common.contract import ConsolidatedInstitutionResponse

# ---------------------------------------------------------------------------
# Heuristic keyword screens (audit-only — see module docstring)
# ---------------------------------------------------------------------------

# Mirrors the "positive generative signal" list in
# g3o/extract/prompts/system_prompt.md. Presence of any of these in a
# confirms_activity source's snippet is treated as a real generative-AI
# signal; absence across every supporting source is a flag for review, not
# a rejection — the LLM may have correctly seen a signal not on this list.
GENERATIVE_SIGNAL_KEYWORDS: frozenset[str] = frozenset(
    {
        "generative",
        "genai",
        "gen ai",
        "gen-ai",
        "gpt",
        "chatgpt",
        "copilot",
        "gemini",
        "claude",
        "llama",
        "mistral",
        "large language model",
        "llm",
        "foundation model",
        "albert",
        "codewhisperer",
        "text-to-image",
        "image generation",
        "code generation",
    }
)

# Mirrors the "exploratory/aspirational language" list added to the extract
# and validate system prompts. Presence — without an accompanying firm
# commitment marker — is a flag for review on `announced` activities.
SPECULATIVE_LANGUAGE_MARKERS: frozenset[str] = frozenset(
    {
        "is considering",
        "are considering",
        "is exploring",
        "are exploring",
        "studying the feasibility",
        "may adopt",
        "might adopt",
        "may explore",
        "might explore",
        "in early discussions",
        "potential use case",
        "potential use cases",
        "eager to",
        "looking into",
        "anticipated",
    }
)

FIRM_COMMITMENT_MARKERS: frozenset[str] = frozenset(
    {
        "plans to introduce",
        "will deploy",
        "will launch",
        "signed a memorandum",
        "signed an mou",
        "budget of",
        "allocated $",
        "allocated €",
        "procurement",
        "contract award",
        "contract was awarded",
        "policy was adopted",
        "strategy was published",
        "launched in",
    }
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _compile_keyword_pattern(keywords: frozenset[str]) -> re.Pattern[str]:
    """One alternation over the list, bounded only at word-character edges.

    Bare substring matching let short keywords fire inside unrelated words
    ('llm' in "Wellman", 'albert' in "Alberta", 'claude' in personal names),
    silently suppressing audit flags. A blanket ``\\b`` is wrong for keywords
    whose edge is already a non-word character ('allocated $' must still match
    "allocated $5M"), so boundaries are asserted per-edge, with an optional
    plural 's' so "LLMs" / "foundation models" keep matching.
    """
    parts: list[str] = []
    for kw in sorted(keywords):
        p = re.escape(kw)
        if kw[0].isalnum() or kw[0] == "_":
            p = r"(?<!\w)" + p
        if kw[-1].isalnum() or kw[-1] == "_":
            p = p + r"s?(?!\w)"
        parts.append(p)
    return re.compile("|".join(parts))


_GENERATIVE_SIGNAL_PATTERN = _compile_keyword_pattern(GENERATIVE_SIGNAL_KEYWORDS)
_SPECULATIVE_LANGUAGE_PATTERN = _compile_keyword_pattern(SPECULATIVE_LANGUAGE_MARKERS)
_FIRM_COMMITMENT_PATTERN = _compile_keyword_pattern(FIRM_COMMITMENT_MARKERS)


def _has_generative_signal(snippet: str) -> bool:
    return _GENERATIVE_SIGNAL_PATTERN.search(_normalize(snippet)) is not None


def _has_speculative_language(snippet: str) -> bool:
    return _SPECULATIVE_LANGUAGE_PATTERN.search(_normalize(snippet)) is not None


def _has_firm_commitment(snippet: str) -> bool:
    return _FIRM_COMMITMENT_PATTERN.search(_normalize(snippet)) is not None


def weak_generative_signal_activities(
    response: ConsolidatedInstitutionResponse,
) -> list[str]:
    """``activity_id``s whose confirming sources never use a generative-AI term.

    Candidate automation-coded-as-GenAI cases (failure mode (a)): every
    `confirms_activity` source backing this activity lacks any keyword in
    ``GENERATIVE_SIGNAL_KEYWORDS`` in its snippet, and the activity has not
    already been flagged ``genai_vs_traditional_ai``. Audit-only — a real
    generative signal may be present in text this keyword list doesn't cover.
    """
    by_activity: dict[str, list[str]] = {}
    for s in response.sources:
        if s.genai_evidence == "confirms_activity" and s.activity_id != "_NA_":
            by_activity.setdefault(s.activity_id, []).append(s.source_snippet)

    flagged: list[str] = []
    for activity in response.activities:
        snippets = by_activity.get(activity.activity_id, [])
        if not snippets:
            continue
        if "genai_vs_traditional_ai" in activity.uncertainty_flags.split(";"):
            continue
        if not any(_has_generative_signal(sn) for sn in snippets):
            flagged.append(activity.activity_id)
    return flagged


def speculative_adoption_activities(
    response: ConsolidatedInstitutionResponse,
) -> list[str]:
    """``activity_id``s coded ``announced`` on hedged/exploratory language only.

    Candidate ``proposed``-coded-as-``announced`` cases (failure mode (b),
    recast after the ``proposed`` stage landed 2026-07): the activity's
    `adoption_stage` is `announced`, every supporting source's snippet
    contains a speculative marker, and none contains a firm-commitment
    marker — i.e. downgrade-to-`proposed` review candidates. Audit-only — a
    firm commitment may be documented in language this keyword list doesn't
    cover.
    """
    by_activity: dict[str, list[str]] = {}
    for s in response.sources:
        if s.genai_evidence == "confirms_activity" and s.activity_id != "_NA_":
            by_activity.setdefault(s.activity_id, []).append(s.source_snippet)

    flagged: list[str] = []
    for activity in response.activities:
        if activity.adoption_stage != "announced":
            continue
        snippets = by_activity.get(activity.activity_id, [])
        if not snippets:
            continue
        if any(_has_firm_commitment(sn) for sn in snippets):
            continue
        if all(_has_speculative_language(sn) for sn in snippets):
            flagged.append(activity.activity_id)
    return flagged


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
    weak_generative_signal = weak_generative_signal_activities(response)
    speculative_adoption = speculative_adoption_activities(response)

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
        "weak_generative_signal_activities": weak_generative_signal,
        "speculative_adoption_activities": speculative_adoption,
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

    weak_generative_signal_flags = [
        (q["institution_id"], activity_id)
        for q in per_inst
        for activity_id in q["weak_generative_signal_activities"]
    ]
    speculative_adoption_flags = [
        (q["institution_id"], activity_id)
        for q in per_inst
        for activity_id in q["speculative_adoption_activities"]
    ]

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
        "n_weak_generative_signal_flags": len(weak_generative_signal_flags),
        "weak_generative_signal_flags": weak_generative_signal_flags,
        "n_speculative_adoption_flags": len(speculative_adoption_flags),
        "speculative_adoption_flags": speculative_adoption_flags,
    }


__all__ = [
    "GENERATIVE_SIGNAL_KEYWORDS",
    "SPECULATIVE_LANGUAGE_MARKERS",
    "FIRM_COMMITMENT_MARKERS",
    "weak_generative_signal_activities",
    "speculative_adoption_activities",
    "qc_per_institution",
    "qc_per_run",
]
