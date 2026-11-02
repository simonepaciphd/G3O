"""Schema invariants asserted by `docs/replication.md`.

Both invariants are cheap to verify and the test suite is the right place
to fail loudly if they ever drift.

Note (Session C, 2026-05-09): The Stage 7 production summary schema migrated
from the original 13-column shape (preserved here as
``PILOT_V1_SUMMARY_COLUMNS``) to a 21-column normalized shape. The pilot v1
CSV remains a frozen historical artifact and is now checked against its own
schema, not the live ``SUMMARY_COLUMNS``.

Note (T-012, ruling N3 a): the same now holds for the full-database CSV. The
live ``DATA_COLUMNS`` gained the v2.7 version label (R-050), so pilot v1 is
checked against the frozen ``PILOT_V1_DATA_COLUMNS`` below. Pilot v1 stays
retired as evidence (C-006); this only pins its published shape.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from g3o.common.schema import (
    ACTIVITY_COLUMNS,
    ACTIVITY_SOURCE_COLUMNS,
    DATA_COLUMNS,
    DATA_COLUMNS_V25,
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

# Frozen historical schema for pilot v1's full-database CSV (N3 a). Do not edit
# unless the pilot v1 CSV is also regenerated. The live Stage 5 schema is
# `g3o.common.schema.DATA_COLUMNS`.
PILOT_V1_DATA_COLUMNS = [
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


def test_pilot_v1_full_header_matches_pilot_v1_schema():
    assert PILOT_FULL.exists(), f"Pilot v1 file missing: {PILOT_FULL}"
    with PILOT_FULL.open(encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == PILOT_V1_DATA_COLUMNS


def test_v25_data_columns_are_frozen():
    """``DATA_COLUMNS_V25`` is what ``g3o.codebook.checks`` reads as the v2.5
    column list (RC-D-008 H2). It is the 44-column shape pilot v1 also has."""
    assert list(DATA_COLUMNS_V25) == PILOT_V1_DATA_COLUMNS
    assert len(DATA_COLUMNS_V25) == 44


def test_data_columns_are_v25_plus_the_version_label():
    """The live list is the v2.5 list plus the R-050 version label, appended."""
    assert DATA_COLUMNS == [
        *DATA_COLUMNS_V25,
        "codebook_release",
        "setup_pointer",
        "evidence_channel",
    ]


def test_pilot_v1_summary_header_matches_pilot_v1_schema():
    """Pilot v1 froze the 13-column summary shape; the live SUMMARY_COLUMNS has
    since migrated to 21 normalized columns (Session C, 2026-05-09)."""
    assert PILOT_SUMMARY.exists(), f"Pilot v1 summary file missing: {PILOT_SUMMARY}"
    with PILOT_SUMMARY.open(encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == PILOT_V1_SUMMARY_COLUMNS


def test_contract_columns_are_subset_of_data_columns():
    for columns in (DATA_COLUMNS, DATA_COLUMNS_V25):
        missing = [c for c in CONTRACT_COLUMNS if c not in columns]
        assert not missing, f"Contract columns missing: {missing}"


RUN_PROVENANCE_COLUMNS = {
    "global_row_id",
    "run_id",
    "run_model",
    "run_tool",
    "run_date",
}
VERSION_LABEL_COLUMNS = {"codebook_release", "setup_pointer", "evidence_channel"}


def test_pipeline_extra_columns_are_exactly_five_in_v25():
    """Asserted against the frozen v2.5 list (N3 a, same treatment as pilot v1):
    the version label (R-050) adds three pipeline columns to the live list."""
    extras = [c for c in DATA_COLUMNS_V25 if c not in CONTRACT_COLUMNS]
    assert set(extras) == RUN_PROVENANCE_COLUMNS


def test_pipeline_extra_columns_are_provenance_plus_version_label():
    extras = [c for c in DATA_COLUMNS if c not in CONTRACT_COLUMNS]
    assert set(extras) == RUN_PROVENANCE_COLUMNS | VERSION_LABEL_COLUMNS
    assert len(extras) == 8


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
