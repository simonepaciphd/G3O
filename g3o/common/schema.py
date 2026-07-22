"""G3O data schema constants.

Source of truth for column ordering in the production database. Two layers:

1. **Stage 5 row-level surface** — ``DATA_COLUMNS`` (44 columns). Mirrors the
   per-page extract output (one row per ``(institution × activity × source)``
   triple). Used by ``g3o.common.contract.PersistedRow.to_csv_dict()`` for
   debug / inspection persistence of raw Stage 5 outputs. **Legacy as of
   Session C**: the canonical Stage 7 database now ships as the normalized
   pair below.

2. **Stage 7 normalized surface** (Session C, Push #2):
   - ``ACTIVITY_COLUMNS`` (35) → ``g3o_activities_v{N}.csv``: one row per
     ``(institution × activity)`` triple from the Stage 6 consolidator.
   - ``ACTIVITY_SOURCE_COLUMNS`` (18) → ``g3o_activity_sources_v{N}.csv``:
     one row per source page, keyed back to the activity it supports
     (``activity_id = "_NA_"`` for absence/ambiguous/background_only sources).
     The final column, ``group_d_salvaged_fields``, is a deterministic persist-
     time annotation (from the attrition ledger, not the LLM): the ``;``-joined
     Group-D field names whose illegal ``_NA_`` was salvage-imputed to a contract
     default on this source page, or ``""`` when none — so a salvage-imputed
     ``unknown`` is distinguishable from a model-asserted one.
   - ``SUMMARY_COLUMNS`` (21) → ``g3o_institution_summary_v{N}.csv``: one row
     per institution per run.

Validators live with the extract module (Stage 5 contract) and the validate
module (Stage 6 contract) in ``g3o.common.contract``.
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

ACTIVITY_COLUMNS: list[str] = [
    # Provenance (5)
    "global_row_id",
    "run_id",
    "run_model",
    "run_tool",
    "run_date",
    # Institution identity + level-shared verdict (8)
    "institution_id",
    "institution_name",
    "country",
    "branch_of_government",
    "level_of_government",
    "has_genai_activity",
    "institution_summary",
    "institution_search_languages",
    # Activity primary key (1)
    "activity_id",
    # Group D activity fields (18)
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
    # Aggregates (3)
    "n_sources",
    "confidence",
    "uncertainty_flags",
]

ACTIVITY_SOURCE_COLUMNS: list[str] = [
    # Provenance (5)
    "global_row_id",
    "run_id",
    "run_model",
    "run_tool",
    "run_date",
    # Foreign keys (3) — source_id is unique per (run_id, institution_id);
    # activity_id is "_NA_" for confirms_absence / ambiguous / background_only.
    "institution_id",
    "activity_id",
    "source_id",
    # Source fields (9)
    "source_url",
    "source_title",
    "source_publication_date",
    "source_access_date",
    "source_type",
    "source_language",
    "source_credibility",
    "genai_evidence",
    "source_snippet",
    # Salvage provenance (1) — deterministic persist-time annotation from the
    # attrition ledger; ``;``-joined Group-D fields salvage-imputed on this page.
    "group_d_salvaged_fields",
]

INSTITUTION_REPORT_COLUMNS: list[str] = [
    # Identity + final verdict (5)
    "institution_id",
    "final_status",
    "stage_reached",
    "stopped_after_stage",
    "reason",
    # Failure detail, nullable (1)
    "error",
    # Funnel counts (5) -- extracted_row_count / consolidated_row_count are
    # flattened ROW counts (ContractRow / ConsolidatedActivity), distinct from
    # g3o.report.health's n_extracts (a FILE count).
    "urls_discovered",
    "urls_kept",
    "pages_scraped",
    "extracted_row_count",
    "consolidated_row_count",
    # Stage 6 outcome (1)
    "validation_status",
    # Timing (3) -- derived from g3o.common.timing's per-institution timing.json
    "start_timestamp",
    "end_timestamp",
    "total_runtime_seconds",
]

SUMMARY_COLUMNS: list[str] = [
    # Identity (5)
    "institution_id",
    "institution_name",
    "country",
    "branch_of_government",
    "level_of_government",
    # Run scope (2) — current-run-only per Session C decision (2026-05-09)
    "run_id",
    "run_date",
    # Institution-level verdict (3)
    "has_genai_activity",
    "institution_summary",
    "institution_search_languages",
    # Counts (6)
    "n_pages_extracted",
    "n_activities",
    "n_sources",
    "n_high_credibility_sources",
    "n_medium_credibility_sources",
    "n_low_credibility_sources",
    # Pipe-delimited distinct lists (3)
    "activities_found",
    "tools_found",
    "vendors_found",
    # Aggregated confidence + flags (2)
    "best_confidence",
    "consolidated_uncertainty_flags",
]
