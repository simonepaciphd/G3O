"""Schema invariants asserted by `docs/replication.md`.

Both invariants are cheap to verify and the test suite is the right place
to fail loudly if they ever drift.
"""

from __future__ import annotations

import csv
from pathlib import Path

from g3o.common.schema import DATA_COLUMNS, SUMMARY_COLUMNS

REPO_ROOT = Path(__file__).resolve().parent.parent
PILOT_FULL = REPO_ROOT / "data" / "pilot_v1" / "g3o_full_database_v1.csv"
PILOT_SUMMARY = REPO_ROOT / "data" / "pilot_v1" / "g3o_institution_summary_v1.csv"

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


def test_pilot_v1_summary_header_matches_summary_columns():
    assert PILOT_SUMMARY.exists(), f"Pilot v1 summary file missing: {PILOT_SUMMARY}"
    with PILOT_SUMMARY.open(encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == SUMMARY_COLUMNS


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
