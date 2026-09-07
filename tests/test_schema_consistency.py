"""Schema invariants asserted by `docs/replication.md`.

Both invariants are cheap to verify and the test suite is the right place
to fail loudly if they ever drift.

Note (Session C, 2026-05-09): The Stage 7 production summary schema migrated
from the original 13-column shape (preserved here as
``PILOT_V1_SUMMARY_COLUMNS``) to a 21-column normalized shape. The pilot v1
CSV remains a frozen historical artifact and is now checked against its own
schema, not the live ``SUMMARY_COLUMNS``.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from g3o.common.schema import (
    ACTIVITY_COLUMNS,
    ACTIVITY_SOURCE_COLUMNS,
    DATA_COLUMNS,
    SUMMARY_COLUMNS,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PILOT_FULL = REPO_ROOT / "data" / "pilot_v1" / "g3o_full_database_v1.csv"
PILOT_SUMMARY = REPO_ROOT / "data" / "pilot_v1" / "g3o_institution_summary_v1.csv"
DATA_DICTIONARY = REPO_ROOT / "docs" / "data_dictionary.md"

# Frozen historical schema for pilot v1's institution-summary CSV. Do not edit
# unless the pilot v1 CSV is also regenerated. The live Stage 7 summary schema
# is `g3o.common.schema.SUMMARY_COLUMNS`.
PILOT_V1_SUMMARY_COLUMNS = [
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

CONTRACT_COLUMNS = [
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
]


def test_pilot_v1_full_header_matches_data_columns():
    assert PILOT_FULL.exists(), f"Pilot v1 file missing: {PILOT_FULL}"
    with PILOT_FULL.open(encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == DATA_COLUMNS


def test_pilot_v1_summary_header_matches_pilot_v1_schema():
    """Pilot v1 froze the 13-column summary shape; the live SUMMARY_COLUMNS has
    since migrated to 21 normalized columns (Session C, 2026-05-09)."""
    assert PILOT_SUMMARY.exists(), f"Pilot v1 summary file missing: {PILOT_SUMMARY}"
    with PILOT_SUMMARY.open(encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == PILOT_V1_SUMMARY_COLUMNS


def test_contract_columns_are_subset_of_data_columns():
    missing = [c for c in CONTRACT_COLUMNS if c not in DATA_COLUMNS]
    assert not missing, f"Contract columns missing from DATA_COLUMNS: {missing}"


def test_pipeline_extra_columns_are_exactly_five():
    extras = [c for c in DATA_COLUMNS if c not in CONTRACT_COLUMNS]
    assert set(extras) == {
        "global_row_id",
        "run_id",
        "run_model",
        "run_tool",
        "run_date",
    }


def test_data_dictionary_column_counts_match_the_schema():
    """``docs/data_dictionary.md`` states each CSV's column count in two places:
    the summary table at the top and the per-CSV section heading. Both drifted
    silently once (17 vs the shipped 18 on the sources CSV, 2026-07-21 →
    2026-08-02), so pin them here rather than trusting a reader to notice.
    """
    text = DATA_DICTIONARY.read_text(encoding="utf-8")
    for constant, columns in (
        ("ACTIVITY_COLUMNS", ACTIVITY_COLUMNS),
        ("ACTIVITY_SOURCE_COLUMNS", ACTIVITY_SOURCE_COLUMNS),
        ("SUMMARY_COLUMNS", SUMMARY_COLUMNS),
    ):
        n = len(columns)
        # Summary table row: | ... | `CONSTANT` | N | ... |
        row = re.search(rf"\|\s*`{constant}`\s*\|\s*(\d+)\s*\|", text)
        assert row, f"no summary-table row for {constant} in {DATA_DICTIONARY.name}"
        assert int(row.group(1)) == n, (
            f"{DATA_DICTIONARY.name} summary table says {constant} has "
            f"{row.group(1)} columns; g3o.common.schema ships {n}"
        )
        # Section heading: ## `...csv` — `CONSTANT` (N)
        heading = re.search(rf"^##.*`{constant}`\s*\((\d+)\)", text, re.MULTILINE)
        assert heading, f"no section heading for {constant} in {DATA_DICTIONARY.name}"
        assert int(heading.group(1)) == n, (
            f"{DATA_DICTIONARY.name} heading says {constant} has "
            f"{heading.group(1)} columns; g3o.common.schema ships {n}"
        )


def test_data_dictionary_names_every_shipped_source_column():
    """The 18th column, ``group_d_salvaged_fields``, is the only imputation
    trace on the analysis surface and was the one the dictionary omitted."""
    text = DATA_DICTIONARY.read_text(encoding="utf-8")
    missing = [c for c in ACTIVITY_SOURCE_COLUMNS if f"`{c}`" not in text]
    assert not missing, f"undocumented columns in {DATA_DICTIONARY.name}: {missing}"
