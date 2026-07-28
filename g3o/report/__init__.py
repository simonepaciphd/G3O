"""Pipeline health report — stage-by-stage funnel KPIs for a presweep run."""

from g3o.report.diff import compute_run_diff, render_run_diff_text
from g3o.report.health import (
    compute_health_report,
    compute_language_breakdown,
    detect_languages,
)
from g3o.report.language_readiness import (
    LanguageReadinessBar,
    assess_language_readiness,
)
from g3o.report.politeness import (
    compute_politeness_report,
    render_politeness_report_text,
    write_politeness_report,
)
from g3o.report.render import render_text_report
from g3o.report.thresholds import HealthThresholds

__all__ = [
    "compute_health_report",
    "compute_language_breakdown",
    "detect_languages",
    "render_text_report",
    "compute_run_diff",
    "render_run_diff_text",
    "HealthThresholds",
    "LanguageReadinessBar",
    "assess_language_readiness",
    "compute_politeness_report",
    "render_politeness_report_text",
    "write_politeness_report",
]
