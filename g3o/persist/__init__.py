"""Persist layer (Stage 7): assemble validated rows into the canonical CSV outputs.

Deterministic writer that walks ``runs/<run_id>/<inst>/6_validate.json`` for all
institutions in a run and produces three CSVs at ``runs/<run_id>/final/``:

- ``g3o_activities_v{N}.csv`` — one row per ``(institution × activity)``;
  columns in ``g3o.common.schema.ACTIVITY_COLUMNS`` order.
- ``g3o_activity_sources_v{N}.csv`` — one row per source page; columns in
  ``ACTIVITY_SOURCE_COLUMNS`` order; ``activity_id`` FK to the activity row
  or ``"_NA_"`` for absence/ambiguous/background-only sources.
- ``g3o_institution_summary_v{N}.csv`` — one row per institution; columns in
  ``SUMMARY_COLUMNS`` order.

Post-persist referential integrity validation runs automatically after CSV write
(via ``g3o.persist.integrity.validate_run_csvs``) to catch disk-level corruption
and cross-file FK violations.

A Postgres-backed adapter is post-Push-#2; CSV is the Stage 7 deliverable.
"""

from __future__ import annotations

from g3o.persist.integrity import (
    FKViolation,
    IntegrityError,
    IntegrityReport,
    validate_run_csvs,
)
from g3o.persist.writer import (
    DEFAULT_RUN_TOOL_ACTIVITY,
    DEFAULT_RUN_TOOL_SOURCE,
    LoadedInstitution,
    build_activity_rows,
    build_source_rows,
    build_summary_row,
    load_consolidated_outputs,
    write_run_csvs,
)

__all__ = [
    "DEFAULT_RUN_TOOL_ACTIVITY",
    "DEFAULT_RUN_TOOL_SOURCE",
    "FKViolation",
    "IntegrityError",
    "IntegrityReport",
    "LoadedInstitution",
    "build_activity_rows",
    "build_source_rows",
    "build_summary_row",
    "load_consolidated_outputs",
    "validate_run_csvs",
    "write_run_csvs",
]
