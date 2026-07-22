"""Stage 3 per-URL salvage (fix: index-based triage matching).

These tests exercise the end-to-end persistence path
(:func:`g3o.run.presweep.stage_classify.persist_triage_result`) on a temp run
directory — parse → index-match → write ``3_triage.json`` + per-URL attrition —
so they assert the observable contract the fix restores: a single drifted or
duplicate decision no longer discards the whole institution's Stage 3 output.

Fixture conventions mirror ``tests/test_health_report.py``: a ``tmp_path`` run
dir, ``_attrition._reset_cache()`` for per-test ledger isolation, and
``_attrition.read_records`` for assertions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.common import attrition as _attrition
from g3o.common.batch_client import BatchResult
from g3o.run.presweep.stage_classify import persist_triage_result

INST_ID = "INST-0000001"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_result(custom_id: str, content: dict[str, Any] | str) -> BatchResult:
    """A successful BatchResult whose assistant content is ``content``."""
    content_str = content if isinstance(content, str) else json.dumps(content)
    return BatchResult(
        custom_id=custom_id,
        success=True,
        response={
            "status_code": 200,
            "body": {"choices": [{"message": {"content": content_str}}]},
        },
        error=None,
        status_code=200,
    )


def _candidates(n: int) -> list[str]:
    return [f"https://inst.gov/p{i}" for i in range(n)]


def _payload(urls: list[str], *, keep: bool = True) -> dict[str, Any]:
    decision = "keep" if keep else "drop"
    return {
        "decisions": [
            {"url": u, "decision": decision, "rationale": "r"} for u in urls
        ]
    }


def _run_with_inst(tmp_path: Path, tag: str = "run") -> Path:
    _attrition._reset_cache()
    run_dir = tmp_path / tag
    (run_dir / INST_ID).mkdir(parents=True)
    return run_dir


def _inst_records(run_dir: Path) -> list[dict[str, Any]]:
    return [r for r in _attrition.read_records(run_dir) if r["institution_id"] == INST_ID]


def _triage_decisions(run_dir: Path) -> list[dict[str, Any]]:
    payload = json.loads((run_dir / INST_ID / "3_triage.json").read_text(encoding="utf-8"))
    return payload["decisions"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_one_corrupted_url_salvages_the_other_nine(tmp_path: Path) -> None:
    """9 clean decisions + 1 drifted URL → keep 9, institution NOT dropped.

    Under URL-keyed matching the drift surfaces as two per-URL casualties: the
    real candidate is now ``missing_decision`` (no decision echoed its URL) and
    the drifted URL is a ``url_mismatch`` (not in the candidate set)."""
    run_dir = _run_with_inst(tmp_path)
    candidates = _candidates(10)
    echoed = list(candidates)
    echoed[4] = echoed[4] + "-CORRUPT"  # one URL drifts at position 4
    kept = persist_triage_result(run_dir, _make_result(INST_ID, _payload(echoed)), candidates)

    assert kept is not None  # institution represented, not discarded
    assert len(kept) == 9
    assert candidates[4] not in kept
    assert len(_triage_decisions(run_dir)) == 9

    recs = _inst_records(run_dir)
    assert {(r["reason"], r["url"]) for r in recs} == {
        ("missing_decision", candidates[4]),
        ("url_mismatch", candidates[4] + "-CORRUPT"),
    }


def test_duplicate_url_salvages_the_others(tmp_path: Path) -> None:
    """A duplicated returned URL among otherwise valid decisions → same salvage.

    Under URL-keyed matching the over-echoed candidate (p0) records a
    ``duplicate_url`` (positional winner accepted) and the starved candidate
    (p3, echoed by nobody) records a ``missing_decision``; the rest survive."""
    run_dir = _run_with_inst(tmp_path)
    candidates = _candidates(5)
    echoed = list(candidates)
    echoed[3] = echoed[0]  # position 3 echoes p0 again → p0 duplicated, p3 starved
    kept = persist_triage_result(run_dir, _make_result(INST_ID, _payload(echoed)), candidates)

    assert kept is not None
    assert len(kept) == 4
    assert candidates[3] not in kept
    assert len(_triage_decisions(run_dir)) == 4

    recs = _inst_records(run_dir)
    assert {(r["reason"], r["url"]) for r in recs} == {
        ("duplicate_url", candidates[0]),
        ("missing_decision", candidates[3]),
    }


def test_reordered_response_fully_salvaged(tmp_path: Path) -> None:
    """A same-URL reorder (every candidate decided, but out of input order) is
    salvaged in full with zero attrition — the URL-keyed matcher's advantage
    over positional matching, which would have dropped every displaced decision.
    """
    run_dir = _run_with_inst(tmp_path)
    candidates = _candidates(6)
    echoed = list(reversed(candidates))  # every URL present, order scrambled
    kept = persist_triage_result(run_dir, _make_result(INST_ID, _payload(echoed)), candidates)

    assert kept is not None
    assert set(kept) == set(candidates)  # all six salvaged
    assert len(_triage_decisions(run_dir)) == 6
    assert _inst_records(run_dir) == []  # no casualties


def test_fully_clean_response_no_attrition(tmp_path: Path) -> None:
    """No drift → no attrition, all decisions kept (regression guard)."""
    run_dir = _run_with_inst(tmp_path)
    candidates = _candidates(6)
    payload = {
        "decisions": [
            {"url": u, "decision": "keep" if i % 2 == 0 else "drop", "rationale": "r"}
            for i, u in enumerate(candidates)
        ]
    }
    kept = persist_triage_result(run_dir, _make_result(INST_ID, payload), candidates)

    assert kept == [candidates[0], candidates[2], candidates[4]]
    assert len(_triage_decisions(run_dir)) == 6
    assert _inst_records(run_dir) == []


def test_all_corrupted_yields_per_url_records_not_blanket_failure(tmp_path: Path) -> None:
    """Every decision drifted → per-URL casualties, NOT a single institution-
    level ``parse_failed``; institution still represented (empty).

    Under URL-keyed matching each candidate is ``missing_decision`` (no decision
    echoed it) and each drifted URL is a ``url_mismatch`` — two casualties per
    drifted candidate, none of them a blanket parse_failed."""
    run_dir = _run_with_inst(tmp_path)
    candidates = _candidates(4)
    echoed = [u + "-X" for u in candidates]  # every URL drifts
    kept = persist_triage_result(run_dir, _make_result(INST_ID, _payload(echoed)), candidates)

    assert kept == []  # nothing salvaged, but not None → institution represented
    assert _triage_decisions(run_dir) == []

    recs = _inst_records(run_dir)
    missing = {r["url"] for r in recs if r["reason"] == "missing_decision"}
    mismatch = {r["url"] for r in recs if r["reason"] == "url_mismatch"}
    assert missing == set(candidates)
    assert mismatch == {u + "-X" for u in candidates}
    assert not any(r["reason"] == "parse_failed" for r in recs)


def test_salvage_output_is_deterministic(tmp_path: Path) -> None:
    """Same input twice → byte-identical salvage output (``3_triage.json``).

    (The attrition ledger carries wall-clock timestamps, so the deterministic
    artifact is the salvage output itself; we also confirm the per-run casualty
    (reason, url, detail) sequence is identical.)"""
    candidates = _candidates(10)
    echoed = list(candidates)
    echoed[4] = echoed[4] + "-CORRUPT"  # a mismatch
    echoed[7] = echoed[2]  # and a duplicate

    def run_once(tag: str) -> tuple[bytes, list[tuple[str, str, str | None]]]:
        run_dir = _run_with_inst(tmp_path, tag=tag)
        persist_triage_result(run_dir, _make_result(INST_ID, _payload(echoed)), candidates)
        triage_bytes = (run_dir / INST_ID / "3_triage.json").read_bytes()
        casualties = [
            (r["reason"], r["url"], r.get("detail")) for r in _inst_records(run_dir)
        ]
        return triage_bytes, casualties

    bytes_a, casualties_a = run_once("a")
    bytes_b, casualties_b = run_once("b")
    assert bytes_a == bytes_b
    assert casualties_a == casualties_b
