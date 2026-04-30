"""G3O data schema constants.

Source of truth for column ordering in the production database. The
extraction layer (Push #2) consumes the same schema described in
`g3o/extract/prompts/output_contract.md` (G3O Output Contract v2.0).

These constants are deliberately minimal in Push #1 — column lists only.
Validators live with the extract module once it is implemented.
"""

from __future__ import annotations

DATA_COLUMNS: list[str] = [
    "global_row_id",
    "run_id",
    "row_id",
    "batch_id",
    "institution_id",
    "institution_name",
    "country",
    "branch_of_government",
    "level_of_government",
    "has_genai_activity",
    "institution_summary",
    "institution_search_languages",
    "activity_name",
    "activity_type",
    "adoption_stage",
    "access_type",
    "interaction_type",
    "tool_name",
    "vendor",
    "deployment_mode",
    "target_users",
    "year_announced",
    "year_deployed",
    "has_human_oversight",
    "has_transparency_notice",
    "has_data_classification",
    "has_risk_assessment",
    "reported_outcomes",
    "reported_incidents",
    "scope_notes",
    "source_url",
    "source_title",
    "source_publication_date",
    "source_access_date",
    "source_type",
    "source_language",
    "source_credibility",
    "genai_evidence",
    "source_snippet",
    "confidence",
    "uncertainty_flags",
    "run_model",
    "run_tool",
    "run_date",
]

SUMMARY_COLUMNS: list[str] = [
    "institution_id",
    "institution_name",
    "country",
    "branch_of_government",
    "level_of_government",
    "has_genai_activity",
    "n_total_rows",
    "n_runs_covered",
    "runs",
    "n_activity_source_rows",
    "activities_found",
    "tools_found",
    "best_summary",
]
