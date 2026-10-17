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

import json
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

# Oversize fallback (PI ruling E1=b, 2026-10-17). Target UTF-8 size of one
# chunk's request, json(state) + json(questions). In production 5 of ~40k
# institutions failed with 400 max_tokens_exceeded at ~160k-430k bytes (or an
# 81k-byte state), while the largest request that succeeded was ~149k bytes;
# no single threshold separates the two, so the split is reactive and this
# budget sits well below the largest observed success.
CHUNK_BUDGET_BYTES = 100_000

# Split levels allowed in the oversize fallback, counting the first split of
# the institution: a chunk that still gets max_tokens_exceeded is re-split
# (half its own estimate as budget) at most until this depth.
MAX_SPLIT_DEPTH = 3


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


# ---------------------------------------------------------------------------
# Oversize fallback: chunked validation (PI ruling E1=b, 2026-10-17)
# ---------------------------------------------------------------------------


def is_max_tokens_exceeded(exc: BaseException) -> bool:
    """True if ``exc`` is a TypeSafe 400 whose error_type is ``max_tokens_exceeded``."""
    if getattr(exc, "status", None) != 400:
        return False
    body = getattr(exc, "body", None)
    body_text = body if isinstance(body, str) else json.dumps(body, default=str)
    return "max_tokens_exceeded" in body_text or "max_tokens_exceeded" in str(exc)


def estimate_request_bytes(state: Any, questions: dict[str, Any]) -> int:
    """UTF-8 byte size of json(state) + json(questions) for one jev request."""
    q_json = {
        qid: q.model_dump() if hasattr(q, "model_dump") else q
        for qid, q in questions.items()
    }
    return len(json.dumps(state, ensure_ascii=False, default=str).encode("utf-8")) + len(
        json.dumps(q_json, ensure_ascii=False, default=str).encode("utf-8")
    )


@dataclass
class ValidateChunk:
    """One chunk of an institution's input rows (whole source pages only)."""

    input_rows: list[dict[str, Any]]
    n_input_pages: int
    request_bytes: int


def chunk_input_rows(
    institution_row: dict[str, Any],
    input_rows: list[dict[str, Any]],
    *,
    budget_bytes: int | None = None,
) -> list[ValidateChunk]:
    """Split an institution's rows into chunks of whole source pages.

    Rows are grouped by ``source_url`` (a page's rows stay together, in their
    original order; pages ordered by first appearance). Pages are packed
    greedily in that order while the chunk's estimated request size — computed
    with :func:`build_validate_state` and :func:`build_validate_questions` —
    stays within ``budget_bytes``. A page that alone exceeds the budget is its
    own chunk. ``budget_bytes`` defaults to :data:`CHUNK_BUDGET_BYTES`.
    """
    if budget_bytes is None:
        budget_bytes = CHUNK_BUDGET_BYTES
    pages: dict[str, list[dict[str, Any]]] = {}
    for row in input_rows:
        pages.setdefault(row.get("source_url", ""), []).append(row)

    def _size(rows: list[dict[str, Any]], n_pages: int) -> int:
        state = build_validate_state(institution_row, rows, n_pages)
        return estimate_request_bytes(state, build_validate_questions(rows))

    chunks: list[ValidateChunk] = []
    cur_rows: list[dict[str, Any]] = []
    cur_pages = 0
    cur_bytes = 0
    for page_rows in pages.values():
        cand_rows = cur_rows + page_rows
        cand_bytes = _size(cand_rows, cur_pages + 1)
        if not cur_rows or cand_bytes <= budget_bytes:
            cur_rows, cur_pages, cur_bytes = cand_rows, cur_pages + 1, cand_bytes
            continue
        chunks.append(ValidateChunk(cur_rows, cur_pages, cur_bytes))
        cur_rows, cur_pages = list(page_rows), 1
        cur_bytes = _size(cur_rows, 1)
    if cur_rows:
        chunks.append(ValidateChunk(cur_rows, cur_pages, cur_bytes))
    return chunks


@dataclass
class ChunkedJevResult:
    """Stands in for one :class:`JevResult` when an institution was validated
    in chunks. Token fields are the sums over every chunk request, so stage
    usage and the per-response cost check see the whole institution."""

    chunks: list[tuple[ValidateChunk, JevResult]]
    input_tokens: int
    output_tokens: int
    response_model: str
    request_id: str | None


_HGA_RANK = {"yes": 2, "unclear": 1, "no": 0}

# Placeholder values a later chunk may fill, per Group D field. "unknown" and
# "" everywhere, plus the field's own "nothing found" default as used by
# _assemble_response (governance flags have no "unknown" member in the
# contract; their placeholder is "not_documented").
_FIELD_PLACEHOLDERS: dict[str, frozenset[str]] = {
    f: frozenset({"", "unknown", default})
    for f, default in {
        "activity_type": "unknown",
        "adoption_stage": "unknown",
        "access_type": "unknown",
        "interaction_type": "unknown",
        "tool_name": "unknown",
        "vendor": "unknown",
        "deployment_mode": "unknown",
        "target_users": "unknown",
        "year_announced": "unknown",
        "year_deployed": "unknown",
        "has_human_oversight": "not_documented",
        "has_transparency_notice": "not_documented",
        "has_data_classification": "not_documented",
        "has_risk_assessment": "not_documented",
        "reported_outcomes": "none_reported",
        "reported_incidents": "none_reported",
        "scope_notes": "none",
    }.items()
}


def merge_chunk_responses(
    chunk_responses: list[tuple[ConsolidatedInstitutionResponse, int]],
    *,
    n_input_pages: int,
    n_input_rows: int,
) -> ConsolidatedInstitutionResponse:
    """Merge per-chunk responses into one response (cross-chunk merge rule).

    ``chunk_responses`` is ``[(response, n_chunk_input_rows), ...]`` in chunk
    order. The rule (PI ruling E1=b, 2026-10-17):

    - **activities**: concatenated in chunk order. Activities with an
      identical ``activity_name`` (exact string match) in different chunks are
      merged into the first one: their sources are unioned; for each Group D
      field the first chunk's value is kept unless it is a placeholder
      ("unknown"/empty, or the field's "nothing found" default —
      "not_documented" for governance flags, "none_reported" for
      reported_outcomes/incidents, "none" for scope_notes), in which case the
      first non-placeholder later value is taken. ``confidence`` is the max
      and ``uncertainty_flags`` the union, as within a chunk; ``n_sources`` is
      recomputed from the merged source links. No semantic (jev) dedup is done
      across chunks.
    - **has_genai_activity**: "yes" if any chunk says yes; else "unclear" if
      any says unclear; else "no".
    - **institution_summary**: from the chunk with the highest
      has_genai_activity rank (yes > unclear > no); tie → the chunk with more
      input rows; tie → the earlier chunk.
    - **sources**: concatenated in chunk order; a source whose
      (source_url, source_snippet) already appeared in an *earlier* chunk is
      dropped (duplicates within one chunk are kept, exactly as the unsplit
      path keeps them); renumbered S1..Sn, and each ``activity_id`` remapped
      to its merged, renumbered activity (A1..Am). Chunks never split a
      source page, so a URL cannot recur in a later chunk and the dedup is a
      guard that does not fire on chunks from :func:`chunk_input_rows`.
    - **consolidation_metadata**: ``n_input_pages``/``n_input_rows`` are the
      institution totals; ``notes`` is the first chunk's notes with
      "; validate_oversize_split: N chunks" appended; ``model_label`` from the
      first chunk.
    """
    from datetime import datetime, timezone

    responses = [r for r, _ in chunk_responses]
    first = responses[0]

    # Activities: merged-by-name, in first-appearance order.
    merged: list[dict[str, Any]] = []  # activity dicts, keyed by position
    index_by_name: dict[str, int] = {}
    # (chunk index, local activity_id) -> merged position
    act_map: dict[tuple[int, str], int] = {}
    for c, resp in enumerate(responses):
        for act in resp.activities:
            data = act.model_dump()
            pos = index_by_name.get(data["activity_name"])
            if pos is None:
                pos = len(merged)
                index_by_name[data["activity_name"]] = pos
                merged.append(data)
            else:
                base = merged[pos]
                for fname, placeholders in _FIELD_PLACEHOLDERS.items():
                    if base[fname] in placeholders and data[fname] not in placeholders:
                        base[fname] = data[fname]
                base["confidence"] = _max_confidence(
                    [base["confidence"], data["confidence"]]
                )
                base["uncertainty_flags"] = _union_flags(
                    [base["uncertainty_flags"], data["uncertainty_flags"]]
                )
            act_map[(c, act.activity_id)] = pos

    # Sources: union, dedup on (url, snippet), remapped activity links.
    sources: list[SourceRecord] = []
    seen: set[tuple[str, str]] = set()
    n_by_pos: dict[int, int] = defaultdict(int)
    for c, resp in enumerate(responses):
        chunk_keys: set[tuple[str, str]] = set()
        for src in resp.sources:
            key = (src.source_url, src.source_snippet)
            if key in seen:
                continue
            chunk_keys.add(key)
            data = src.model_dump()
            data["source_id"] = f"S{len(sources) + 1}"
            if src.activity_id != "_NA_":
                pos = act_map[(c, src.activity_id)]
                data["activity_id"] = f"A{pos + 1}"
                n_by_pos[pos] += 1
            sources.append(SourceRecord(**data))
        seen |= chunk_keys

    activities = []
    for pos, data in enumerate(merged):
        data["activity_id"] = f"A{pos + 1}"
        data["n_sources"] = n_by_pos[pos]
        activities.append(ConsolidatedActivity(**data))

    ranks = [_HGA_RANK.get(r.institution.has_genai_activity, 0) for r in responses]
    has_genai_activity = {2: "yes", 1: "unclear", 0: "no"}[max(ranks)]
    best = max(
        range(len(responses)),
        key=lambda c: (ranks[c], chunk_responses[c][1], -c),
    )

    institution = first.institution.model_copy(
        update={
            "has_genai_activity": has_genai_activity,
            "institution_summary": responses[best].institution.institution_summary,
        }
    )
    metadata = first.consolidation_metadata.model_copy(
        update={
            "n_input_pages": n_input_pages,
            "n_input_rows": n_input_rows,
            "response_timestamp": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "notes": (
                f"{first.consolidation_metadata.notes}; "
                f"validate_oversize_split: {len(responses)} chunks"
            ),
        }
    )
    # Re-validate the merged whole: the contract's cross-field invariants
    # (yes/no/unclear, id sequences, FK links, n_sources) must hold.
    return ConsolidatedInstitutionResponse.model_validate(
        {
            "consolidation_metadata": metadata.model_dump(),
            "institution": institution.model_dump(),
            "activities": [a.model_dump() for a in activities],
            "sources": [s.model_dump() for s in sources],
        }
    )


def parse_chunked_validate_result(
    result: ChunkedJevResult,
    institution_row: dict[str, Any],
    n_input_pages: int,
    n_input_rows: int,
) -> ConsolidatedInstitutionResponse:
    """Parse each chunk with :func:`parse_validate_result`, then merge them."""
    chunk_responses = [
        (
            parse_validate_result(
                jev_result, institution_row, chunk.input_rows, chunk.n_input_pages
            ).response,
            len(chunk.input_rows),
        )
        for chunk, jev_result in result.chunks
    ]
    return merge_chunk_responses(
        chunk_responses, n_input_pages=n_input_pages, n_input_rows=n_input_rows
    )


__all__ = [
    "CHUNK_BUDGET_BYTES",
    "JEV_QUESTION_SET_VERSION",
    "MAX_SPLIT_DEPTH",
    "ChunkedJevResult",
    "JevValidateResult",
    "ValidateChunk",
    "build_validate_questions",
    "build_validate_state",
    "chunk_input_rows",
    "estimate_request_bytes",
    "is_max_tokens_exceeded",
    "merge_chunk_responses",
    "parse_chunked_validate_result",
    "parse_validate_result",
]
