"""Tests for g3o.validate.salvage — Stage 6 bookkeeping repair.

Two things are under test and the second matters more than the first: that the
three enabled repairs restore a valid payload, and that they restore it *without
changing what the institution says*. A salvage module's failure mode is not
"fails to repair", it is "repairs by quietly deciding something", so most of
what follows checks that values, links and verdicts survive untouched.

The reference payloads are shaped after real rejections on
``r20260830T114940Z-32ea``: ``['S1','S1']`` (11 of 126),
``['A1','A2','A3','A5','A4']`` (1), and n_sources counter drift (20).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from g3o.common.contract import ConsolidatedInstitutionResponse
from g3o.validate import salvage
from g3o.validate.consolidate import (
    REJECTED_FILENAME,
    write_rejected_output,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _activity(aid: str, *, n_sources: int = 1) -> dict[str, Any]:
    return {
        "activity_id": aid,
        "activity_name": f"Activity {aid}",
        "activity_type": "internal_operational",
        "adoption_stage": "pilot",
        "access_type": "proprietary_vendor",
        "interaction_type": "document_processing",
        "tool_name": "Tool",
        "vendor": "Vendor",
        "deployment_mode": "integrated",
        "target_users": "internal_staff",
        "year_announced": "2025",
        "year_deployed": "2025",
        "has_human_oversight": "yes",
        "has_transparency_notice": "no",
        "has_data_classification": "yes",
        "has_risk_assessment": "yes",
        "reported_outcomes": "none_reported",
        "reported_incidents": "none_reported",
        "scope_notes": "fixture",
        "n_sources": n_sources,
        "confidence": "high",
        "uncertainty_flags": "none",
    }


def _source(sid: str, aid: str, *, url: str | None = None) -> dict[str, Any]:
    return {
        "source_id": sid,
        "activity_id": aid,
        "source_url": url or f"https://example.gov/{sid.lower()}",
        "source_title": f"Page {sid}",
        "source_publication_date": "2025-01",
        "source_access_date": "2026-08-30",
        "source_type": "official_gov",
        "source_language": "en",
        "source_credibility": "high",
        "genai_evidence": (
            "confirms_absence" if aid == "_NA_" else "confirms_activity"
        ),
        "source_snippet": f"snippet {sid}",
    }


def _payload(
    *,
    activities: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    has_genai: str = "yes",
) -> dict[str, Any]:
    return {
        "consolidation_metadata": {
            "institution_id": "INST-0000001",
            "n_input_pages": 2,
            "n_input_rows": 2,
            "response_timestamp": "2026-08-30T12:00:00Z",
            "model_label": "gpt-5-nano",
            "notes": "fixture",
        },
        "institution": {
            "institution_id": "INST-0000001",
            "institution_name": "Fixture Institution",
            "country": "TESTLAND",
            "branch_of_government": "executive",
            "level_of_government": "local",
            "has_genai_activity": has_genai,
            "institution_summary": "summary",
            "institution_search_languages": "en",
        },
        "activities": activities,
        "sources": sources,
    }


def _validates(payload: dict[str, Any]) -> ConsolidatedInstitutionResponse:
    return ConsolidatedInstitutionResponse.model_validate(payload)


# ---------------------------------------------------------------------------
# The premise: these payloads really are rejected without salvage
#
# Without these, every repair test could pass against payloads that were valid
# all along, and the module would be measuring nothing.
# ---------------------------------------------------------------------------


def test_duplicate_source_ids_are_rejected_unsalvaged() -> None:
    p = _payload(
        activities=[_activity("A1", n_sources=2)],
        sources=[_source("S1", "A1"), _source("S1", "A1", url="https://b.gov/")],
    )
    with pytest.raises(ValidationError, match="source_id sequence"):
        _validates(p)


def test_out_of_order_activity_ids_are_rejected_unsalvaged() -> None:
    p = _payload(
        activities=[_activity("A1"), _activity("A3"), _activity("A2")],
        sources=[
            _source("S1", "A1"),
            _source("S2", "A3"),
            _source("S3", "A2"),
        ],
    )
    with pytest.raises(ValidationError, match="activity_id sequence"):
        _validates(p)


def test_a_miscounted_n_sources_is_rejected_unsalvaged() -> None:
    p = _payload(
        activities=[_activity("A1", n_sources=1)],
        sources=[_source("S1", "A1"), _source("S2", "A1")],
    )
    with pytest.raises(ValidationError, match="n_sources=1 but 2"):
        _validates(p)


# ---------------------------------------------------------------------------
# source_id renumbering
# ---------------------------------------------------------------------------


def test_duplicate_source_ids_are_renumbered_and_the_payload_validates() -> None:
    p = _payload(
        activities=[_activity("A1", n_sources=2)],
        sources=[_source("S1", "A1"), _source("S1", "A1", url="https://b.gov/")],
    )
    events = salvage.salvage_consolidation_bookkeeping(p)
    assert [e.kind for e in events] == ["source_id_sequence"]
    assert [s["source_id"] for s in p["sources"]] == ["S1", "S2"]
    _validates(p)


def test_renumbering_sources_preserves_every_other_field() -> None:
    """The repair relabels; it must not touch content.

    Two sources with identical ids and different everything else: after the
    repair each source's payload minus ``source_id`` must be byte-identical to
    what it was, in the same order.
    """
    p = _payload(
        activities=[_activity("A1", n_sources=2)],
        sources=[
            _source("S1", "A1", url="https://first.gov/"),
            _source("S1", "A1", url="https://second.gov/"),
        ],
    )
    before = [
        {k: v for k, v in s.items() if k != "source_id"} for s in p["sources"]
    ]
    salvage.salvage_source_id_sequence(p)
    after = [{k: v for k, v in s.items() if k != "source_id"} for s in p["sources"]]
    assert after == before


def test_nothing_in_the_schema_references_a_source_id() -> None:
    """The assumption that makes positional source renumbering safe.

    ``salvage_source_id_sequence`` rewrites source ids without chasing
    back-references, which is only correct while no other field holds one. If a
    ``source_id``-shaped foreign key is ever added, this fails and the repair
    must grow a remap — the same one ``salvage_activity_id_sequence`` already
    has.
    """
    fields = set(ConsolidatedInstitutionResponse.model_fields)
    from g3o.common.contract import ConsolidatedActivity, SourceRecord

    referencing = {
        name
        for name in ConsolidatedActivity.model_fields
        if "source_id" in name
    }
    assert not referencing, f"ConsolidatedActivity now references {referencing}"
    # SourceRecord owns the id itself; that is the definition, not a reference.
    assert "source_id" in SourceRecord.model_fields
    assert "sources" in fields


def test_an_already_ordered_source_list_is_left_alone() -> None:
    p = _payload(
        activities=[_activity("A1")],
        sources=[_source("S1", "A1")],
    )
    snapshot = copy.deepcopy(p)
    assert salvage.salvage_source_id_sequence(p) == []
    assert p == snapshot


# ---------------------------------------------------------------------------
# activity_id renumbering — the one with a link rewrite
# ---------------------------------------------------------------------------


def test_out_of_order_activity_ids_are_renumbered_and_links_follow() -> None:
    """The measured case: ['A1','A2','A3','A5','A4'], all five present.

    The remap sends A5->A4 and A4->A5, so a repair that renumbered the
    activities and left the sources pointing at the old labels would swap two
    activities' evidence. This asserts the graph, not just the ids.
    """
    p = _payload(
        activities=[_activity(a) for a in ("A1", "A2", "A3", "A5", "A4")],
        sources=[
            _source("S1", "A1"),
            _source("S2", "A2"),
            _source("S3", "A3"),
            _source("S4", "A5"),
            _source("S5", "A4"),
        ],
    )
    # Remember which activity_name each source supported, by name not by id.
    by_name = {
        s["source_id"]: next(
            a["activity_name"] for a in p["activities"]
            if a["activity_id"] == s["activity_id"]
        )
        for s in p["sources"]
    }

    events = salvage.salvage_consolidation_bookkeeping(p)
    assert "activity_id_sequence" in [e.kind for e in events]
    assert [a["activity_id"] for a in p["activities"]] == [
        "A1", "A2", "A3", "A4", "A5"
    ]
    _validates(p)

    after = {
        s["source_id"]: next(
            a["activity_name"] for a in p["activities"]
            if a["activity_id"] == s["activity_id"]
        )
        for s in p["sources"]
    }
    assert after == by_name, "the activity<->source graph was not preserved"


def test_duplicate_activity_ids_are_refused_not_guessed() -> None:
    """The boundary. Two activities labelled A1 leave a source ambiguous.

    A repair here would have to decide which activity a source supports, which
    is the judgement this module exists not to make. The payload stays broken
    and the institution stays rejected — with its payload retained.
    """
    p = _payload(
        activities=[_activity("A1"), _activity("A1")],
        sources=[_source("S1", "A1"), _source("S2", "A1")],
    )
    snapshot = copy.deepcopy(p)
    assert salvage.salvage_activity_id_sequence(p) == []
    assert p == snapshot
    with pytest.raises(ValidationError):
        _validates(p)


def test_activity_renumbering_leaves_NA_sources_alone() -> None:
    """``_NA_`` is not an activity id and must not be remapped onto one."""
    p = _payload(
        activities=[_activity("A2")],
        sources=[_source("S1", "A2"), _source("S2", "_NA_")],
        has_genai="yes",
    )
    salvage.salvage_consolidation_bookkeeping(p)
    assert [a["activity_id"] for a in p["activities"]] == ["A1"]
    assert [s["activity_id"] for s in p["sources"]] == ["A1", "_NA_"]
    _validates(p)


# ---------------------------------------------------------------------------
# n_sources
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stated", [1, 3, 7])
def test_n_sources_is_recomputed_from_the_actual_back_links(stated: int) -> None:
    p = _payload(
        activities=[_activity("A1", n_sources=stated)],
        sources=[_source("S1", "A1"), _source("S2", "A1")],
    )
    events = salvage.salvage_n_sources(p)
    assert [e.kind for e in events] == ["n_sources"]
    assert p["activities"][0]["n_sources"] == 2
    _validates(p)


def test_n_sources_runs_after_the_id_repairs() -> None:
    """Ordering, asserted rather than trusted to the tuple's shape.

    Both an id fault and a count fault at once: if ``n_sources`` ran first it
    would count against labels about to change, and could write a number that is
    wrong for the repaired graph.
    """
    p = _payload(
        activities=[_activity("A2", n_sources=9), _activity("A1", n_sources=9)],
        sources=[
            _source("S1", "A2"),
            _source("S1", "A2"),
            _source("S3", "A1"),
        ],
    )
    salvage.salvage_consolidation_bookkeeping(p)
    _validates(p)
    counts = {a["activity_id"]: a["n_sources"] for a in p["activities"]}
    actual: dict[str, int] = {}
    for s in p["sources"]:
        actual[s["activity_id"]] = actual.get(s["activity_id"], 0) + 1
    assert counts == actual


def test_an_orphan_activity_is_skipped_not_set_to_zero() -> None:
    """``n_sources`` is ``Field(ge=1)``; writing 0 would trade a good error for a bad one.

    The institution must still fail, and it must fail on
    ``_validate_n_sources``'s "no supporting sources" message rather than on a
    bounds check, because that message is what tells a reader what happened.
    """
    p = _payload(
        activities=[_activity("A1", n_sources=1), _activity("A2", n_sources=1)],
        sources=[_source("S1", "A1")],
    )
    salvage.salvage_consolidation_bookkeeping(p)
    assert p["activities"][1]["n_sources"] == 1  # untouched, not zeroed
    with pytest.raises(ValidationError, match="no supporting sources"):
        _validates(p)


# ---------------------------------------------------------------------------
# The verdict is never touched
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", ["yes", "no", "unclear"])
def test_no_repair_ever_changes_has_genai_activity(verdict: str) -> None:
    """The one invariant that would make this module a coding instrument.

    Every repair here is bookkeeping; none may move the institution-level
    verdict, in any direction, under any input.
    """
    activities = [_activity("A2", n_sources=5)] if verdict == "yes" else []
    sources = (
        [_source("S1", "A2"), _source("S1", "A2")]
        if verdict == "yes"
        else [_source("S1", "_NA_"), _source("S1", "_NA_")]
    )
    p = _payload(activities=activities, sources=sources, has_genai=verdict)
    salvage.salvage_consolidation_bookkeeping(p)
    assert p["institution"]["has_genai_activity"] == verdict


def test_no_repair_ever_adds_or_removes_an_activity_by_default() -> None:
    """Orphan-dropping is the only repair that changes the activity count, and
    it is not in the default set. This is the guard on that."""
    p = _payload(
        activities=[_activity("A1"), _activity("A2")],
        sources=[_source("S1", "A1")],
    )
    n_before = len(p["activities"])
    salvage.salvage_consolidation_bookkeeping(p)
    assert len(p["activities"]) == n_before


def test_salvage_orphan_activities_is_absent_from_the_default_set() -> None:
    """Substantive, PI-gated, and dormant. Asserted so enabling it is a visible diff."""
    assert salvage.salvage_orphan_activities not in salvage.DEFAULT_REPAIRS


def test_salvage_orphan_activities_works_when_explicitly_enabled() -> None:
    """Implemented and tested, so that ruling on it does not also mean writing it."""
    p = _payload(
        activities=[_activity("A1"), _activity("A2")],
        sources=[_source("S1", "A1")],
    )
    events = salvage.salvage_consolidation_bookkeeping(
        p,
        repairs=(
            salvage.salvage_orphan_activities,
            salvage.salvage_activity_id_sequence,
            salvage.salvage_n_sources,
        ),
    )
    assert "orphan_activities_dropped" in [e.kind for e in events]
    assert [a["activity_id"] for a in p["activities"]] == ["A1"]
    _validates(p)


# ---------------------------------------------------------------------------
# Defensive shapes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [None, [], "text", 3, {}, {"sources": None}, {"sources": [1, 2]},
     {"activities": "no"}],
)
def test_a_malformed_payload_is_left_for_the_validator(payload: object) -> None:
    """Structurally broken input is the validator's to reject with a good
    message, not this module's to guess at — and must not raise here."""
    assert salvage.salvage_consolidation_bookkeeping(payload) == []


def test_a_clean_payload_produces_no_events() -> None:
    p = _payload(
        activities=[_activity("A1", n_sources=1)],
        sources=[_source("S1", "A1")],
    )
    snapshot = copy.deepcopy(p)
    assert salvage.salvage_consolidation_bookkeeping(p) == []
    assert p == snapshot
    _validates(p)


# ---------------------------------------------------------------------------
# Rejected-payload retention (1c)
# ---------------------------------------------------------------------------


def test_a_rejected_payload_is_retained_with_its_error(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "institutions").mkdir(parents=True)
    raw = json.dumps({"institution": {"has_genai_activity": "yes"}})
    out = write_rejected_output(
        run_dir, "INST-0000001", raw_content=raw, error="1 validation error"
    )
    assert out is not None
    kept = json.loads(out.read_text(encoding="utf-8"))
    assert kept["institution_id"] == "INST-0000001"
    assert kept["rejected_at_stage"] == "validate"
    assert kept["validation_error"] == "1 validation error"
    assert json.loads(kept["raw_assistant_content"])["institution"][
        "has_genai_activity"
    ] == "yes"


def test_the_retained_file_is_not_named_like_a_consolidated_record() -> None:
    """Every downstream reader tests for the exact string ``6_validate.json``.

    A retained rejection that matched it would be read as a finding — the worst
    possible outcome of a change whose whole purpose is to stop discarding
    evidence quietly.
    """
    assert REJECTED_FILENAME != "6_validate.json"
    assert not REJECTED_FILENAME.endswith("/6_validate.json")
    assert REJECTED_FILENAME == "6_validate.rejected.json"


def test_retention_writes_nothing_when_there_was_no_content(tmp_path: Path) -> None:
    """8 of the 126 rejections on the 15k run were empty assistant responses.

    An empty file would falsely suggest something was kept.
    """
    run_dir = tmp_path / "run"
    (run_dir / "institutions").mkdir(parents=True)
    assert (
        write_rejected_output(
            run_dir, "INST-0000001", raw_content=None, error="empty content"
        )
        is None
    )
    assert not list(run_dir.rglob(REJECTED_FILENAME))


def test_retention_does_not_raise_when_the_run_dir_is_unwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It runs on a path already handling a failure; it must not replace it."""
    import pathlib

    def _boom(*_a: object, **_k: object) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(pathlib.Path, "mkdir", _boom)
    assert (
        write_rejected_output(
            tmp_path / "run", "INST-0000001", raw_content="{}", error="e"
        )
        is None
    )
