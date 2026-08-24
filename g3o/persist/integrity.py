"""Post-persist referential integrity validation.

Validates foreign key relationships across all persisted artifacts (CSVs, JSON
files) to ensure zero orphaned records and correct FK relationships throughout
the data lifecycle.

Catches disk-level corruption, partial writes, and cross-file inconsistencies
that in-memory Stage 6 validation cannot detect.

Four constraint classes:
- Hard constraints (violations): source→activity links, activity→source coverage,
  institution consistency, summary count integrity, run_id consistency
- Soft constraints (warnings): global_row_id uniqueness, activity/source sequence
  gaplessness

Phase 1 of the foreign-key-integrity plan.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from g3o.common.paths import iter_institution_dirs
from g3o.common.schema import ACTIVITY_COLUMNS, ACTIVITY_SOURCE_COLUMNS, SUMMARY_COLUMNS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class FKViolation:
    """A single foreign key constraint violation.

    Attributes:
        constraint: Constraint identifier (e.g., "source_activity_link")
        entity_type: "source", "activity", or "institution"
        entity_id: The specific source_id, activity_id, or institution_id
        detail: Human-readable description of the violation
    """

    constraint: str
    entity_type: str
    entity_id: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.constraint}] {self.entity_type} {self.entity_id}: {self.detail}"


@dataclass
class IntegrityReport:
    """Validation result for a run's persisted artifacts.

    Attributes:
        n_institutions: Number of institutions loaded
        n_activities: Number of activity rows
        n_sources: Number of source rows
        violations: List of hard constraint violations
        warnings: List of soft constraint warnings

    The report is valid when violations is empty.
    """

    n_institutions: int
    n_activities: int
    n_sources: int
    violations: list[FKViolation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True when no hard constraint violations exist."""
        return len(self.violations) == 0

    def summary(self) -> str:
        """Human-readable summary of validation results."""
        status = "VALID" if self.is_valid else "INVALID"
        return (
            f"{status}: {self.n_institutions} institutions, "
            f"{self.n_activities} activities, {self.n_sources} sources; "
            f"{len(self.violations)} violations, {len(self.warnings)} warnings"
        )


class IntegrityError(Exception):
    """Raised when post-persist validation detects FK violations."""

    def __init__(self, report: IntegrityReport) -> None:
        self.report = report
        violation_details = "\n  ".join(str(v) for v in report.violations)
        super().__init__(
            f"Referential integrity validation failed:\n  {violation_details}"
        )


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------


def _load_csv(path: Path) -> list[dict[str, str]]:
    """Load CSV as list of dicts. Raises if file doesn't exist."""
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _load_activities_csv(run_dir: Path, version: int = 1) -> list[dict[str, str]]:
    """Load g3o_activities_v{N}.csv."""
    path = run_dir / "final" / f"g3o_activities_v{version}.csv"
    return _load_csv(path)


def _load_sources_csv(run_dir: Path, version: int = 1) -> list[dict[str, str]]:
    """Load g3o_activity_sources_v{N}.csv."""
    path = run_dir / "final" / f"g3o_activity_sources_v{version}.csv"
    return _load_csv(path)


def _load_summary_csv(run_dir: Path, version: int = 1) -> list[dict[str, str]]:
    """Load g3o_institution_summary_v{N}.csv."""
    path = run_dir / "final" / f"g3o_institution_summary_v{version}.csv"
    return _load_csv(path)


# ---------------------------------------------------------------------------
# FK constraint validators
# ---------------------------------------------------------------------------


def _validate_source_activity_link(
    activities: list[dict[str, str]],
    sources: list[dict[str, str]],
) -> list[FKViolation]:
    """Constraint 1: Every source.activity_id must be _NA_ or match an activity.

    For each (run_id, institution_id) pair, every source's activity_id must either:
    - Be "_NA_" (for absence/ambiguous/background_only sources), OR
    - Match an existing activity_id in the activities CSV
    """
    violations: list[FKViolation] = []

    # Build lookup: (run_id, institution_id) -> set of activity_ids
    activities_by_inst: dict[tuple[str, str], set[str]] = {}
    for act in activities:
        key = (act["run_id"], act["institution_id"])
        activities_by_inst.setdefault(key, set()).add(act["activity_id"])

    # Check each source
    for src in sources:
        activity_id = src["activity_id"]
        if activity_id == "_NA_":
            continue  # Valid for absence/ambiguous sources

        key = (src["run_id"], src["institution_id"])
        valid_ids = activities_by_inst.get(key, set())
        if activity_id not in valid_ids:
            violations.append(
                FKViolation(
                    constraint="source_activity_link",
                    entity_type="source",
                    entity_id=src["source_id"],
                    detail=(
                        f"activity_id={activity_id!r} does not exist for "
                        f"institution {src['institution_id']!r} in run {src['run_id']!r}"
                    ),
                )
            )

    return violations


def _validate_activity_source_coverage(
    activities: list[dict[str, str]],
    sources: list[dict[str, str]],
) -> list[FKViolation]:
    """Constraint 2: Every activity must have at least one supporting source.

    For each (run_id, institution_id, activity_id), there must be at least one
    source with matching activity_id.
    """
    violations: list[FKViolation] = []

    # Count sources per activity: (run_id, institution_id, activity_id) -> count
    source_counts: dict[tuple[str, str, str], int] = {}
    for src in sources:
        if src["activity_id"] != "_NA_":
            key = (src["run_id"], src["institution_id"], src["activity_id"])
            source_counts[key] = source_counts.get(key, 0) + 1

    # Check each activity has sources
    for act in activities:
        key = (act["run_id"], act["institution_id"], act["activity_id"])
        count = source_counts.get(key, 0)
        if count == 0:
            violations.append(
                FKViolation(
                    constraint="activity_source_coverage",
                    entity_type="activity",
                    entity_id=act["activity_id"],
                    detail=(
                        f"activity at institution {act['institution_id']!r} in run "
                        f"{act['run_id']!r} has no supporting sources"
                    ),
                )
            )

    return violations


def _validate_institution_consistency(
    activities: list[dict[str, str]],
    sources: list[dict[str, str]],
    summary: list[dict[str, str]],
) -> list[FKViolation]:
    """Constraint 3: Every institution_id in activities/sources must have a summary row.

    Every institution_id appearing in activities or sources must have a corresponding
    row in the institution summary CSV.
    """
    violations: list[FKViolation] = []

    # Collect all institution_ids from activities and sources
    inst_ids_in_details: set[str] = set()
    for act in activities:
        inst_ids_in_details.add(act["institution_id"])
    for src in sources:
        inst_ids_in_details.add(src["institution_id"])

    # Collect institution_ids from summary
    inst_ids_in_summary = {row["institution_id"] for row in summary}

    # Check for missing summary rows
    missing = inst_ids_in_details - inst_ids_in_summary
    for inst_id in sorted(missing):
        violations.append(
            FKViolation(
                constraint="institution_consistency",
                entity_type="institution",
                entity_id=inst_id,
                detail="institution appears in activities/sources but has no summary row",
            )
        )

    return violations


def _validate_summary_counts(
    activities: list[dict[str, str]],
    sources: list[dict[str, str]],
    summary: list[dict[str, str]],
) -> list[FKViolation]:
    """Constraint 4: Summary n_activities and n_sources must match actual row counts.

    For each institution, the summary's n_activities must equal the number of activity
    rows, and n_sources must equal the number of source rows.
    """
    violations: list[FKViolation] = []

    # Count actual activities per institution
    activity_counts: dict[str, int] = {}
    for act in activities:
        inst_id = act["institution_id"]
        activity_counts[inst_id] = activity_counts.get(inst_id, 0) + 1

    # Count actual sources per institution
    source_counts: dict[str, int] = {}
    for src in sources:
        inst_id = src["institution_id"]
        source_counts[inst_id] = source_counts.get(inst_id, 0) + 1

    # Check each summary row
    for row in summary:
        inst_id = row["institution_id"]
        actual_activities = activity_counts.get(inst_id, 0)
        actual_sources = source_counts.get(inst_id, 0)

        summary_activities = int(row["n_activities"])
        summary_sources = int(row["n_sources"])

        if summary_activities != actual_activities:
            violations.append(
                FKViolation(
                    constraint="summary_count_integrity",
                    entity_type="institution",
                    entity_id=inst_id,
                    detail=(
                        f"n_activities={summary_activities} but activity CSV has "
                        f"{actual_activities} rows"
                    ),
                )
            )

        if summary_sources != actual_sources:
            violations.append(
                FKViolation(
                    constraint="summary_count_integrity",
                    entity_type="institution",
                    entity_id=inst_id,
                    detail=(
                        f"n_sources={summary_sources} but source CSV has "
                        f"{actual_sources} rows"
                    ),
                )
            )

    return violations


def _validate_run_id_consistency(
    activities: list[dict[str, str]],
    sources: list[dict[str, str]],
    summary: list[dict[str, str]],
) -> list[FKViolation]:
    """Constraint 5: All records in a run must share the same run_id.

    This is implicitly enforced by CSV loading (all rows come from the same run),
    but we check for defensive programming.
    """
    violations: list[FKViolation] = []

    # Collect unique run_ids
    run_ids: set[str] = set()
    for act in activities:
        run_ids.add(act["run_id"])
    for src in sources:
        run_ids.add(src["run_id"])
    for row in summary:
        run_ids.add(row["run_id"])

    if len(run_ids) > 1:
        violations.append(
            FKViolation(
                constraint="run_id_consistency",
                entity_type="run",
                entity_id="multiple",
                detail=f"CSVs contain multiple run_ids: {sorted(run_ids)}",
            )
        )

    return violations


# ---------------------------------------------------------------------------
# Soft constraint validators (warnings)
# ---------------------------------------------------------------------------


def _validate_global_row_id_uniqueness(
    activities: list[dict[str, str]],
    sources: list[dict[str, str]],
) -> list[str]:
    """Warning: global_row_id should be unique across activity and source records."""
    warnings: list[str] = []

    # Only check activities and sources - summary rows don't have global_row_id
    all_ids: list[str] = []
    for act in activities:
        all_ids.append(act["global_row_id"])
    for src in sources:
        all_ids.append(src["global_row_id"])

    # Use Counter for O(n) duplicate detection
    counts = Counter(all_ids)
    unique_dupes = sorted(gid for gid, count in counts.items() if count > 1)

    if unique_dupes:
        warnings.append(
            f"global_row_id not unique: {len(unique_dupes)} duplicates found "
            f"(e.g., {unique_dupes[0]})"
        )

    return warnings


def _validate_activity_sequence(
    activities: list[dict[str, str]],
) -> list[str]:
    """Warning: activity_id values should follow gapless sequence A1, A2, ... per institution."""
    warnings: list[str] = []

    # Group activities by institution
    by_inst: dict[str, list[str]] = {}
    for act in activities:
        inst_id = act["institution_id"]
        by_inst.setdefault(inst_id, []).append(act["activity_id"])

    # Check each institution's sequence
    for inst_id, activity_ids in by_inst.items():
        # Extract numeric part and sort numerically (A1, A2, ..., A10, A11, ...)
        sorted_ids = sorted(activity_ids, key=lambda x: int(x[1:]))
        expected = [f"A{i + 1}" for i in range(len(sorted_ids))]
        if sorted_ids != expected:
            warnings.append(
                f"institution {inst_id!r}: activity_id sequence has gaps: "
                f"expected {expected}, got {sorted_ids}"
            )

    return warnings


def _validate_source_sequence(
    sources: list[dict[str, str]],
) -> list[str]:
    """Warning: source_id values should follow gapless sequence S1, S2, ... per institution."""
    warnings: list[str] = []

    # Group sources by institution
    by_inst: dict[str, list[str]] = {}
    for src in sources:
        inst_id = src["institution_id"]
        by_inst.setdefault(inst_id, []).append(src["source_id"])

    # Check each institution's sequence
    for inst_id, source_ids in by_inst.items():
        # Extract numeric part and sort numerically (S1, S2, ..., S10, S11, ...)
        sorted_ids = sorted(source_ids, key=lambda x: int(x[1:]))
        expected = [f"S{i + 1}" for i in range(len(sorted_ids))]
        if sorted_ids != expected:
            warnings.append(
                f"institution {inst_id!r}: source_id sequence has gaps: "
                f"expected {expected}, got {sorted_ids}"
            )

    return warnings


# ---------------------------------------------------------------------------
# Phase 2: Institution metadata consistency
# ---------------------------------------------------------------------------


def _validate_institution_metadata(
    run_dir: Path,
) -> list[FKViolation]:
    """Validate that institution.json matches 6_validate.json.

    For each institution, compare institution_id, institution_name, country,
    branch_of_government, level_of_government across institution.json and
    6_validate.json.
    """
    violations: list[FKViolation] = []

    for inst_dir in iter_institution_dirs(run_dir):
        inst_json_path = inst_dir / "institution.json"
        validate_json_path = inst_dir / "6_validate.json"

        if not inst_json_path.exists() or not validate_json_path.exists():
            continue

        try:
            inst_json = json.loads(inst_json_path.read_text(encoding="utf-8"))
            validate_json = json.loads(validate_json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load institution metadata for %s: %s", inst_dir.name, exc)
            continue

        # Compare key fields
        inst_id = inst_dir.name
        fields_to_check = [
            "institution_id",
            "institution_name",
            "country",
            "branch_of_government",
            "level_of_government",
        ]

        for field_name in fields_to_check:
            inst_value = inst_json.get(field_name)
            validate_value = validate_json.get("institution", {}).get(field_name)

            if inst_value != validate_value:
                violations.append(
                    FKViolation(
                        constraint="institution_metadata_consistency",
                        entity_type="institution",
                        entity_id=inst_id,
                        detail=(
                            f"{field_name} mismatch: institution.json={inst_value!r}, "
                            f"6_validate.json={validate_value!r}"
                        ),
                    )
                )

    return violations


def _validate_institution_id_uniqueness(
    summary: list[dict[str, str]],
) -> list[FKViolation]:
    """Validate no duplicate institution_id across the run."""
    violations: list[FKViolation] = []

    inst_ids = [row["institution_id"] for row in summary]
    # Use Counter for O(n) duplicate detection
    counts = Counter(inst_ids)
    unique_dupes = sorted(iid for iid, count in counts.items() if count > 1)

    for inst_id in unique_dupes:
        violations.append(
            FKViolation(
                constraint="institution_id_uniqueness",
                entity_type="institution",
                entity_id=inst_id,
                detail=f"institution_id appears {counts[inst_id]} times in summary CSV",
            )
        )

    return violations


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------


def validate_run_csvs(
    run_dir: Path,
    *,
    version: int = 1,
    check_metadata: bool = True,
) -> IntegrityReport:
    """Validate referential integrity across all persisted artifacts in a run.

    Reads all three CSVs (activities, sources, summary) and validates all FK
    constraints. Optionally validates institution metadata consistency.

    Args:
        run_dir: Path to runs/<run_id>/
        version: CSV version suffix (default 1)
        check_metadata: Validate institution.json vs 6_validate.json (default True)

    Returns:
        IntegrityReport with violations and warnings

    Raises:
        FileNotFoundError: if any of the three expected CSVs is missing.
    """
    run_dir = Path(run_dir)

    # Load CSVs (raises FileNotFoundError if any CSV is missing)
    activities = _load_activities_csv(run_dir, version)
    sources = _load_sources_csv(run_dir, version)
    summary = _load_summary_csv(run_dir, version)

    # Warn on empty CSVs (suspicious: may indicate partial write or corruption)
    warnings: list[str] = []
    if len(activities) == 0:
        warnings.append("activities CSV is empty (0 rows)")
    if len(sources) == 0:
        warnings.append("sources CSV is empty (0 rows)")
    if len(summary) == 0:
        warnings.append("summary CSV is empty (0 rows)")

    # Validate CSV schema (ensure expected columns exist)
    if activities and len(activities) > 0:
        actual_cols = set(activities[0].keys())
        expected_cols = set(ACTIVITY_COLUMNS)
        missing = expected_cols - actual_cols
        if missing:
            raise ValueError(
                f"activities CSV missing required columns: {sorted(missing)}"
            )
    if sources and len(sources) > 0:
        actual_cols = set(sources[0].keys())
        expected_cols = set(ACTIVITY_SOURCE_COLUMNS)
        missing = expected_cols - actual_cols
        if missing:
            raise ValueError(
                f"sources CSV missing required columns: {sorted(missing)}"
            )
    if summary and len(summary) > 0:
        actual_cols = set(summary[0].keys())
        expected_cols = set(SUMMARY_COLUMNS)
        missing = expected_cols - actual_cols
        if missing:
            raise ValueError(
                f"summary CSV missing required columns: {sorted(missing)}"
            )

    # Validate hard constraints
    violations: list[FKViolation] = []
    violations.extend(_validate_source_activity_link(activities, sources))
    violations.extend(_validate_activity_source_coverage(activities, sources))
    violations.extend(_validate_institution_consistency(activities, sources, summary))
    violations.extend(_validate_summary_counts(activities, sources, summary))
    violations.extend(_validate_run_id_consistency(activities, sources, summary))

    # Phase 2: Institution metadata consistency
    if check_metadata:
        violations.extend(_validate_institution_metadata(run_dir))
        violations.extend(_validate_institution_id_uniqueness(summary))

    # Validate soft constraints (warnings)
    warnings.extend(
        _validate_global_row_id_uniqueness(activities, sources)
    )
    warnings.extend(_validate_activity_sequence(activities))
    warnings.extend(_validate_source_sequence(sources))

    report = IntegrityReport(
        n_institutions=len(summary),
        n_activities=len(activities),
        n_sources=len(sources),
        violations=violations,
        warnings=warnings,
    )

    logger.info(
        "Integrity validation for %s: %s",
        run_dir.name,
        report.summary(),
    )

    return report


__all__ = [
    "FKViolation",
    "IntegrityError",
    "IntegrityReport",
    "validate_run_csvs",
]
