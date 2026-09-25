"""Stage 6 — Validation via jev decision model.

Converts the Stage 6 consolidation task into a hybrid approach:
- **Deterministic code** handles bookkeeping: ID sequencing, n_sources counts,
  uncertainty-flag union, confidence max, echo-back fields, FK integrity.
- **jev judgment** handles the three decisions that need semantic understanding:
  1. Near-duplicate activity grouping (pairwise Noul questions)
  2. Conflict resolution when tier/recency/snippet-size tie (Choice question)
  3. institution_summary selection (Choice over distinct input values)

The output is a ConsolidatedInstitutionResponse assembled by code — the contract
is unchanged, so Stage 7 and the CSVs are untouched.

Cost basis: state ≈ an institution's Stage 5 rows (~4–6k tokens) + a handful of
small questions ⇒ roughly $0.17–0.25 per 1k institutions, vs $1.39 today with
gpt-5-nano.

See jev-integration-plan.md §4 for the full design.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import typesafe_sdk as ts

from g3o.common.contract import (
    ConsolidatedActivity,
    ConsolidatedInstitution,
    ConsolidatedInstitutionResponse,
    ConsolidationMetadata,
    SourceRecord,
)
from g3o.common.jev_client import JevAnswer, JevResult

# Question-set version (jev-integration-plan.md §4). Pin in goldens.
JEV_QUESTION_SET_VERSION = "g3o.validate.jev.v1"


@dataclass
class JevValidateResult:
    """Result of jev validation for one institution."""

    response: ConsolidatedInstitutionResponse
    activity_groups: list[list[int]]  # indices into input rows per activity
    conflict_resolutions: dict[str, int]  # field_name → winning row index
    summary_choice: int  # index of chosen institution_summary
    response_model: str
    request_id: str | None
    input_tokens: int
    output_tokens: int


def build_validate_state(
    institution_row: dict[str, Any],
    input_rows: list[dict[str, Any]],
    n_input_pages: int,
) -> dict[str, Any]:
    """Build the jev state for Stage 6.

    The state carries the institution metadata and all Stage 5 input rows.
    """
    return {
        "institution": institution_row,
        "input_rows": input_rows,
        "n_input_pages": n_input_pages,
        "n_input_rows": len(input_rows),
    }


def build_validate_questions(
    input_rows: list[dict[str, Any]],
) -> dict[str, ts.Choice | ts.Noul]:
    """Build the jev questions for Stage 6.

    Questions:
    1. Pairwise Noul questions for activity dedup: "Are rows i and j the same activity?"
    2. Choice question for conflict resolution (if needed): "Which row wins for field X?"
    3. Choice question for institution_summary: "Which summary is most informative?"
    """
    questions: dict[str, ts.Choice | ts.Noul] = {}

    # 1. Activity dedup: pairwise Noul for rows with confirms_activity
    activity_rows = [
        (i, row)
        for i, row in enumerate(input_rows)
        if row.get("genai_evidence") == "confirms_activity"
    ]

    # Only ask pairwise questions if there are 2+ activity rows
    if len(activity_rows) >= 2:
        for idx_a, (i, row_a) in enumerate(activity_rows):
            for j, row_b in activity_rows[idx_a + 1 :]:
                name_a = row_a.get("activity_name", "")
                name_b = row_b.get("activity_name", "")
                # Skip if names are identical (already grouped)
                if name_a == name_b:
                    continue
                questions[f"same_activity_r{i}_r{j}"] = ts.Noul(
                    instructions=(
                        f"Are these two GenAI activities the same underlying activity?\n"
                        f"Activity A: {name_a}\n"
                        f"Activity B: {name_b}\n"
                        f"Consider: similar names, same tool/vendor, same deployment context. "
                        f"If ambiguous, prefer to keep them separate."
                    ),
                    criteria=ts.NoulCriteria(
                        true="These are the same underlying activity",
                        false="These are different activities",
                    ),
                )

    # 2. Conflict resolution: only if multiple rows for same activity disagree
    # Group rows by activity_name
    by_activity: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for i, row in enumerate(input_rows):
        if row.get("genai_evidence") == "confirms_activity":
            name = row.get("activity_name", "")
            by_activity[name].append((i, row))

    # For each activity with 2+ rows, check for conflicts
    group_d_fields = [
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
    ]

    for activity_name, rows in by_activity.items():
        if len(rows) < 2:
            continue
        # Check each field for disagreement
        for field in group_d_fields:
            values = [row.get(field, "unknown") for _, row in rows]
            unique_values = set(values)
            if len(unique_values) > 1:
                # Conflict: ask which row wins
                row_indices = [i for i, _ in rows]
                criteria = {
                    f"r{i}": f"Row {i}: {rows[idx][1].get(field, 'unknown')}"
                    for idx, i in enumerate(row_indices)
                }
                questions[f"conflict_{activity_name}_{field}"] = ts.Choice(
                    instructions=(
                        f"Multiple rows disagree on '{field}' for activity '{activity_name}'. "
                        f"Choose the row from the most credible source. "
                        f"Tier 1 (government/procurement/parliamentary) > "
                        f"Tier 2 (major news/vendor case studies) > "
                        f"Tier 3 (social/blogs/undated). "
                        f"Tie: most recent date. Tie: largest snippet."
                    ),
                    criteria=criteria,
                )

    # 3. institution_summary: Choice over distinct summaries
    # Blocker #4 fix: use dict.fromkeys to preserve insertion order while
    # deduplicating, so the s-index matches the assembly list.
    summaries = list(dict.fromkeys(
        row.get("institution_summary", "")
        for row in input_rows
        if row.get("institution_summary")
    ))
    if summaries:
        criteria = {f"s{i}": summary for i, summary in enumerate(summaries)}
        questions["institution_summary"] = ts.Choice(
            instructions=(
                "Choose the most informative institution_summary. "
                "Prefer summaries from Tier-1 sources. "
                "If has_genai_activity=no, prefer summaries that state what was reviewed."
            ),
            criteria=criteria,
        )
    return questions


def parse_validate_result(
    result: JevResult,
    institution_row: dict[str, Any],
    input_rows: list[dict[str, Any]],
    n_input_pages: int,
) -> JevValidateResult:
    """Parse jev results and assemble ConsolidatedInstitutionResponse.

    This is the main consolidation logic:
    1. Use jev's activity grouping decisions to cluster input rows
    2. Use jev's conflict resolution to pick winning values
    3. Use jev's summary choice
    4. Assemble the response with deterministic bookkeeping
    """
    # 1. Activity grouping: start with exact name matches, then merge by jev
    activity_rows = [
        (i, row)
        for i, row in enumerate(input_rows)
        if row.get("genai_evidence") == "confirms_activity"
    ]

    # Build union-find structure
    parent = {i: i for i, _ in activity_rows}

    def find(x: int) -> int:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # First, union rows with the same activity_name (exact match)
    by_name: dict[str, list[int]] = defaultdict(list)
    for i, row in activity_rows:
        by_name[row.get("activity_name", "")].append(i)
    for _name, indices in by_name.items():
        if len(indices) > 1:
            for i in indices[1:]:
                union(indices[0], i)

    # Apply jev's merge decisions (noul >= 0.5 → merge)
    for qid, answer in result.answers.items():
        if qid.startswith("same_activity_") and isinstance(answer, JevAnswer):
            if answer.type == "noul" and answer.noul is not None and answer.noul >= 0.5:
                # Parse row indices from question id
                # Format: same_activity_r{i}_r{j}
                parts = qid.replace("same_activity_r", "").split("_r")
                if len(parts) == 2:
                    try:
                        i, j = int(parts[0]), int(parts[1])
                        union(i, j)
                    except ValueError:
                        pass

    # Build final groups
    groups: dict[int, list[int]] = defaultdict(list)
    for i, _ in activity_rows:
        groups[find(i)].append(i)

    activity_groups = list(groups.values())

    # 2. Conflict resolution: parse jev's choices
    # Major #4 fix: key by (activity_name, field) to avoid collision
    conflict_resolutions: dict[tuple[str, str], int] = {}
    for qid, answer in result.answers.items():
        if qid.startswith("conflict_") and isinstance(answer, JevAnswer):
            if answer.type == "choice" and answer.choice:
                # Parse activity_name, field name and winning row index
                # Format: conflict_{activity_name}_{field}
                # Choice: r{i}
                if answer.choice.startswith("r"):
                    try:
                        winning_idx = int(answer.choice[1:])
                        # Extract activity_name and field from question id
                        # Split on first "conflict_" prefix, then split remainder
                        remainder = qid[len("conflict_"):]
                        # Find last underscore to split activity_name and field
                        last_underscore = remainder.rfind("_")
                        if last_underscore > 0:
                            activity_name = remainder[:last_underscore]
                            field = remainder[last_underscore + 1:]
                            conflict_resolutions[(activity_name, field)] = winning_idx
                    except ValueError:
                        pass

    # 3. institution_summary choice
    summary_choice = 0
    if "institution_summary" in result.answers:
        answer = result.answers["institution_summary"]
        if isinstance(answer, JevAnswer) and answer.type == "choice" and answer.choice:
            if answer.choice.startswith("s"):
                try:
                    summary_choice = int(answer.choice[1:])
                except ValueError:
                    pass

    # 4. Assemble the response
    response = _assemble_response(
        institution_row,
        input_rows,
        n_input_pages,
        activity_groups,
        conflict_resolutions,
        summary_choice,
        result.response_model,
    )

    return JevValidateResult(
        response=response,
        activity_groups=activity_groups,
        conflict_resolutions=conflict_resolutions,
        summary_choice=summary_choice,
        response_model=result.response_model,
        request_id=result.request_id,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


def _assemble_response(
    institution_row: dict[str, Any],
    input_rows: list[dict[str, Any]],
    n_input_pages: int,
    activity_groups: list[list[int]],
    conflict_resolutions: dict[str, int],
    summary_choice: int,
    model_label: str,
) -> ConsolidatedInstitutionResponse:
    """Assemble ConsolidatedInstitutionResponse from jev decisions + deterministic logic."""
    from datetime import datetime, timezone

    institution_id = institution_row.get("institution_id", "")
    institution_name = institution_row.get("institution_name", "")
    country = institution_row.get("country", "")
    branch = institution_row.get("branch_of_government", "")
    level = institution_row.get("level_of_government", "")
    search_languages = institution_row.get("institution_search_languages", "")

    # Build activities
    activities: list[ConsolidatedActivity] = []
    for group_idx, row_indices in enumerate(activity_groups):
        activity_id = f"A{group_idx + 1}"
        # Use the first row as the base, apply conflict resolutions
        base_row = input_rows[row_indices[0]]
        activity_name = base_row.get("activity_name", "")

        # Build Group D fields: use conflict_resolutions if available, else first row
        # Major #4 fix: key is now (activity_name, field) tuple
        def get_field(field: str, default: str = "unknown", _row_indices=row_indices, _base_row=base_row, _activity_name=activity_name) -> str:
            key = (_activity_name, field)
            if key in conflict_resolutions:
                winning_idx = conflict_resolutions[key]
                if winning_idx in _row_indices:
                    return input_rows[winning_idx].get(field, default)
            return _base_row.get(field, default)

        activity = ConsolidatedActivity(
            activity_id=activity_id,
            activity_name=activity_name,
            activity_type=get_field("activity_type", "unknown"),
            adoption_stage=get_field("adoption_stage", "unknown"),
            access_type=get_field("access_type", "unknown"),
            interaction_type=get_field("interaction_type", "unknown"),
            tool_name=get_field("tool_name", "unknown"),
            vendor=get_field("vendor", "unknown"),
            deployment_mode=get_field("deployment_mode", "unknown"),
            target_users=get_field("target_users", "unknown"),
            year_announced=get_field("year_announced", "unknown"),
            year_deployed=get_field("year_deployed", "unknown"),
            has_human_oversight=get_field("has_human_oversight", "not_documented"),
            has_transparency_notice=get_field("has_transparency_notice", "not_documented"),
            has_data_classification=get_field("has_data_classification", "not_documented"),
            has_risk_assessment=get_field("has_risk_assessment", "not_documented"),
            reported_outcomes=get_field("reported_outcomes", "none_reported"),
            reported_incidents=get_field("reported_incidents", "none_reported"),
            scope_notes=get_field("scope_notes", "none"),
            n_sources=len(row_indices),
            confidence=_max_confidence([input_rows[i].get("confidence", "low") for i in row_indices]),
            uncertainty_flags=_union_flags([input_rows[i].get("uncertainty_flags", "none") for i in row_indices]),
        )
        activities.append(activity)

    # Build sources
    sources: list[SourceRecord] = []
    for i, row in enumerate(input_rows):
        source_id = f"S{i + 1}"
        # Link to activity if confirms_activity, else _NA_
        activity_id = "_NA_"
        if row.get("genai_evidence") == "confirms_activity":
            # Find which activity group this row belongs to
            for group_idx, group in enumerate(activity_groups):
                if i in group:
                    activity_id = f"A{group_idx + 1}"
                    break

        source = SourceRecord(
            source_id=source_id,
            activity_id=activity_id,
            source_url=row.get("source_url", ""),
            source_title=row.get("source_title", ""),
            source_publication_date=row.get("source_publication_date", "unknown"),
            source_access_date=row.get("source_access_date", "unknown"),
            source_type=row.get("source_type", "unknown"),
            source_language=row.get("source_language", "unknown"),
            source_credibility=row.get("source_credibility", "unknown"),
            genai_evidence=row.get("genai_evidence", "unknown"),
            source_snippet=row.get("source_snippet", ""),
        )
        sources.append(source)

    # Determine has_genai_activity
    confirms = [s for s in sources if s.genai_evidence == "confirms_activity"]
    if activities and confirms:
        has_genai_activity = "yes"
    elif not activities and all(s.genai_evidence == "confirms_absence" for s in sources):
        has_genai_activity = "no"
    else:
        has_genai_activity = "unclear"

    # Choose institution_summary
    # Blocker #4 fix: use same dedup logic as build_validate_questions
    summaries = list(dict.fromkeys(
        row.get("institution_summary", "")
        for row in input_rows
        if row.get("institution_summary")
    ))
    # Reject negative indexes
    if summaries and 0 <= summary_choice < len(summaries):
        institution_summary = summaries[summary_choice]
    else:
        institution_summary = ""

    # Build institution
    institution = ConsolidatedInstitution(
        institution_id=institution_id,
        institution_name=institution_name,
        country=country,
        branch_of_government=branch,
        level_of_government=level,
        has_genai_activity=has_genai_activity,
        institution_summary=institution_summary,
        institution_search_languages=search_languages,
    )

    # Build metadata
    metadata = ConsolidationMetadata(
        institution_id=institution_id,
        n_input_pages=n_input_pages,
        n_input_rows=len(input_rows),
        response_timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        model_label=model_label,
        notes="Consolidated via jev decision model",
    )

    return ConsolidatedInstitutionResponse(
        consolidation_metadata=metadata,
        institution=institution,
        activities=activities,
        sources=sources,
    )


def _max_confidence(confidences: list[str]) -> str:
    """Return the highest confidence level from a list."""
    order = {"high": 3, "medium": 2, "low": 1}
    if not confidences:
        return "low"
    return max(confidences, key=lambda c: order.get(c, 0))


def _union_flags(flags_list: list[str]) -> str:
    """Union of uncertainty flags from multiple rows, sorted alphabetically."""
    all_flags: set[str] = set()
    for flags in flags_list:
        if flags and flags != "none":
            all_flags.update(f.strip() for f in flags.split(";") if f.strip())
    if not all_flags:
        return "none"
    return ";".join(sorted(all_flags))


__all__ = [
    "JEV_QUESTION_SET_VERSION",
    "JevValidateResult",
    "build_validate_questions",
    "build_validate_state",
    "parse_validate_result",
]
