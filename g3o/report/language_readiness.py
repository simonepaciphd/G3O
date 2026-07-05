"""Language-readiness bar (Batch 5): is language X "as good as English" yet?

Proposed by the RA per the working agreement's "KPI thresholds proposed for
PI review" decision authority -- every value here is a default Simone can
tune or reject. Layered on top of :func:`g3o.report.compute_language_breakdown`
rather than the absolute :class:`g3o.report.HealthThresholds` floors, because
"as good as English" (batch-5-multilingual.md) is a *relative* bar -- the
measured gap to the English reference run -- not a fixed pass/fail percentage.
A language can have a legitimately smaller raw institution count and still be
judged ready if its per-stage yield tracks English's.

Funnel percentages alone cannot certify readiness: a language can look
"green" on every stage while its search terms are simply wrong and it never
surfaces the activity that is actually there. That is why
:func:`assess_language_readiness` also requires a measured recall figure from
a small hand-picked known-positive smoke set (see the Batch 5 deliverable for
the English baseline methodology) -- funnel coverage plus recall, not either
alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Metric name in a compute_language_breakdown() row -> the bar field naming
# its max allowed shortfall (percentage points, 0-1 scale) vs the reference.
_GAP_FIELDS: dict[str, str] = {
    "pct_institutions_with_urls_1a": "max_gap_pct_institutions_with_urls_1a",
    "pct_institutions_with_kept_url": "max_gap_pct_institutions_with_kept_url",
    "pct_scrape_success": "max_gap_pct_scrape_success",
    "pct_extracted_of_eligible": "max_gap_pct_extracted_of_eligible",
}


@dataclass
class LanguageReadinessBar:
    """Max allowed shortfall vs the English reference per funnel stage, plus
    a recall floor on the known-positive smoke set. All PI-tunable."""

    max_gap_pct_institutions_with_urls_1a: float = 0.15
    max_gap_pct_institutions_with_kept_url: float = 0.15
    max_gap_pct_scrape_success: float = 0.15
    max_gap_pct_extracted_of_eligible: float = 0.15
    min_known_positive_recall: float = 0.80


def assess_language_readiness(
    breakdown: dict[str, Any],
    language: str,
    *,
    reference: str = "en",
    bar: LanguageReadinessBar | None = None,
    known_positive_recall: float | None = None,
) -> dict[str, Any]:
    """Compare ``language`` against ``reference`` in a language-breakdown table.

    Parameters
    ----------
    breakdown:
        Output of :func:`g3o.report.compute_language_breakdown`.
    known_positive_recall:
        The RA's/PI's measured recall (0-1) on a hand-picked known-positive
        smoke set for ``language``. This function does not compute it --
        readiness cannot be certified from funnel percentages alone, so
        omitting it always fails the check (see module docstring).
    """
    bar = bar or LanguageReadinessBar()
    langs = breakdown.get("languages", {})
    if reference not in langs:
        raise ValueError(f"reference language {reference!r} not in breakdown")
    if language not in langs:
        raise ValueError(f"language {language!r} not in breakdown")

    ref_row = langs[reference]
    row = langs[language]

    gaps: dict[str, Any] = {}
    failures: list[str] = []
    for metric, bar_field in _GAP_FIELDS.items():
        ref_val = ref_row.get(metric)
        val = row.get(metric)
        max_gap = getattr(bar, bar_field)
        if ref_val is None and val is None:
            # Neither language reached this stage (e.g. Stage 4 with zero
            # attempted URLs on both sides) -- nothing to compare, not a gap.
            gaps[metric] = {"reference": None, "value": None, "gap": None, "ok": None}
            continue
        # A `None` percentage means the stage never ran for that side (a
        # denominator of zero -- see health.py's `_pct`), which for a
        # candidate language is the worst case, not "no data": treat it as 0%
        # rather than skipping the comparison, so a language that discovered
        # nothing at all cannot pass by omission.
        ref_v = ref_val if ref_val is not None else 0.0
        val_v = val if val is not None else 0.0
        gap = ref_v - val_v
        ok = gap <= max_gap
        gaps[metric] = {"reference": ref_val, "value": val, "gap": round(gap, 4), "ok": ok}
        if not ok:
            failures.append(
                f"{metric}: {language}={val_v:.2%} vs {reference}={ref_v:.2%} "
                f"(gap {gap:.2%} > allowed {max_gap:.0%})"
            )

    recall_ok: bool | None = None
    if known_positive_recall is not None:
        recall_ok = known_positive_recall >= bar.min_known_positive_recall
        if not recall_ok:
            failures.append(
                f"known_positive_recall: {known_positive_recall:.2%} < required "
                f"{bar.min_known_positive_recall:.0%}"
            )
    else:
        failures.append(
            "known_positive_recall: not measured -- funnel percentages alone "
            "cannot certify readiness (see g3o.report.language_readiness docstring)"
        )

    return {
        "language": language,
        "reference": reference,
        "ready": not failures,
        "gaps": gaps,
        "known_positive_recall": known_positive_recall,
        "recall_ok": recall_ok,
        "failures": failures,
        "bar_used": bar.__dict__,
    }


__all__ = ["LanguageReadinessBar", "assess_language_readiness"]
