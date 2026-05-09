"""Tests for ``g3o.common.run_state`` (Session E, 2026-05-09).

Covers the per-stage state-file primitives that gate crash-recovery and
``--resume`` (Q1=a, Q2=iii, Q3=e2, Q7=c). The shared polling helper
``wait_for_terminal_with_state`` is exercised against a mock ``poll_batch``
that returns a scripted sequence of ``BatchStatus`` objects.
"""

from __future__ import annotations

import json
from pathlib import Path

from g3o.common import run_state
from g3o.common.batch_client import BatchStatus
from g3o.common.run_state import (
    done_path,
    is_done,
    load_state,
    mark_done,
    state_path,
    update_polled,
    wait_for_terminal_with_state,
    write_active,
)


def _status(state: str, batch_id: str = "batch-test") -> BatchStatus:
    return BatchStatus(
        batch_id=batch_id,
        status=state,
        request_counts={},
        output_file_id=None,
        error_file_id=None,
    )


# ---------------------------------------------------------------------------
# write_active / load_state / state_path
# ---------------------------------------------------------------------------


def test_write_active_persists_required_fields(tmp_path: Path):
    p = write_active(
        tmp_path, "classify_official_site",
        batch_id="batch_abc", model="gpt-5-nano", n_jobs=42,
        custom_ids=["INST-0001", "INST-0002", "INST-0003"],
    )
    assert p == state_path(tmp_path, "classify_official_site")
    assert p.exists()
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["stage"] == "classify_official_site"
    assert payload["batch_id"] == "batch_abc"
    assert payload["model"] == "gpt-5-nano"
    assert payload["n_jobs"] == 42
    assert payload["custom_ids"] == ["INST-0001", "INST-0002", "INST-0003"]
    assert payload["last_polled_at"] is None
    assert payload["last_status"] is None
    assert "submitted_at" in payload
    # bypass_count omitted by default.
    assert "bypass_count" not in payload


def test_write_active_records_bypass_count_when_supplied(tmp_path: Path):
    write_active(
        tmp_path, "classify_official_site",
        batch_id="batch_xyz", model="gpt-5-nano", n_jobs=10,
        custom_ids=["INST-0001"], bypass_count=7,
    )
    payload = load_state(tmp_path, "classify_official_site")
    assert payload is not None
    assert payload["bypass_count"] == 7


def test_write_active_dedupes_custom_ids(tmp_path: Path):
    write_active(
        tmp_path, "extract",
        batch_id="batch_e", model="gpt-5-nano", n_jobs=2,
        custom_ids=["A", "B", "A"],
    )
    payload = load_state(tmp_path, "extract")
    assert payload is not None
    assert payload["custom_ids"] == ["A", "B"]


def test_load_state_returns_none_when_missing(tmp_path: Path):
    assert load_state(tmp_path, "extract") is None


# ---------------------------------------------------------------------------
# update_polled
# ---------------------------------------------------------------------------


def test_update_polled_refreshes_status_fields(tmp_path: Path):
    write_active(
        tmp_path, "extract",
        batch_id="batch_e", model="gpt-5-nano", n_jobs=1,
        custom_ids=["A"],
    )
    update_polled(tmp_path, "extract", status="in_progress")
    payload = load_state(tmp_path, "extract")
    assert payload is not None
    assert payload["last_status"] == "in_progress"
    assert payload["last_polled_at"] is not None


def test_update_polled_is_noop_after_done(tmp_path: Path):
    """update_polled must not resurrect a state file the runner has finalized."""
    write_active(
        tmp_path, "extract",
        batch_id="batch_e", model="gpt-5-nano", n_jobs=1, custom_ids=["A"],
    )
    mark_done(tmp_path, "extract")
    # Active file is gone; update_polled should be a silent no-op.
    update_polled(tmp_path, "extract", status="completed")
    assert not state_path(tmp_path, "extract").exists()


# ---------------------------------------------------------------------------
# mark_done / is_done
# ---------------------------------------------------------------------------


def test_mark_done_moves_active_to_done_and_appends_fetched_at(tmp_path: Path):
    write_active(
        tmp_path, "classify_triage",
        batch_id="b1", model="gpt-5-nano", n_jobs=3, custom_ids=["A", "B", "C"],
    )
    src = state_path(tmp_path, "classify_triage")
    assert src.exists()
    dst = mark_done(tmp_path, "classify_triage")
    assert dst == done_path(tmp_path, "classify_triage")
    assert dst.exists()
    assert not src.exists()
    payload = json.loads(dst.read_text(encoding="utf-8"))
    assert payload["batch_id"] == "b1"
    assert "fetched_at" in payload
    assert is_done(tmp_path, "classify_triage")


def test_mark_done_no_batch_writes_minimal_marker(tmp_path: Path):
    """Deterministic stages (1a/1b/scrape) and all-bypassed Stage 2 use no_batch=True."""
    dst = mark_done(tmp_path, "discovery_general", no_batch=True)
    assert dst.exists()
    payload = json.loads(dst.read_text(encoding="utf-8"))
    assert payload == {
        "stage": "discovery_general",
        "fetched_at": payload["fetched_at"],
        "no_batch": True,
    }
    assert is_done(tmp_path, "discovery_general")


def test_mark_done_idempotent(tmp_path: Path):
    """Re-marking a done stage is a no-op (does not crash, does not duplicate)."""
    write_active(
        tmp_path, "validate",
        batch_id="b1", model="gpt-5-nano", n_jobs=1, custom_ids=["A"],
    )
    mark_done(tmp_path, "validate")
    # Second mark_done on a stage that's already done must not raise.
    second = mark_done(tmp_path, "validate")
    assert second == done_path(tmp_path, "validate")


# ---------------------------------------------------------------------------
# wait_for_terminal_with_state
# ---------------------------------------------------------------------------


def test_wait_for_terminal_with_state_updates_state_each_tick(tmp_path: Path, monkeypatch):
    write_active(
        tmp_path, "extract",
        batch_id="b1", model="gpt-5-nano", n_jobs=1, custom_ids=["A"],
    )
    statuses = iter([
        _status("validating"),
        _status("in_progress"),
        _status("completed"),
    ])
    monkeypatch.setattr(run_state, "poll_batch", lambda batch_id: next(statuses))
    final = wait_for_terminal_with_state(
        "b1", poll_interval=0, max_wait=10,
        run_dir=tmp_path, stage="extract",
    )
    assert final.is_completed
    payload = load_state(tmp_path, "extract")
    assert payload is not None
    assert payload["last_status"] == "completed"


def test_wait_for_terminal_with_state_returns_status_on_deadline(tmp_path: Path, monkeypatch):
    """If the deadline elapses before terminal, return the last non-terminal status."""
    write_active(
        tmp_path, "extract",
        batch_id="b1", model="gpt-5-nano", n_jobs=1, custom_ids=["A"],
    )
    monkeypatch.setattr(run_state, "poll_batch", lambda batch_id: _status("in_progress"))
    final = wait_for_terminal_with_state(
        "b1", poll_interval=0, max_wait=0,
        run_dir=tmp_path, stage="extract",
    )
    assert not final.is_completed
    assert final.status == "in_progress"


def test_wait_for_terminal_without_state_does_not_touch_disk(tmp_path: Path, monkeypatch):
    """When run_dir/stage are None, the helper polls but writes no state."""
    monkeypatch.setattr(run_state, "poll_batch", lambda batch_id: _status("completed"))
    final = wait_for_terminal_with_state(
        "b1", poll_interval=0, max_wait=10,
    )
    assert final.is_completed
    assert not state_path(tmp_path, "extract").exists()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def test_state_and_done_paths_match_layout(tmp_path: Path):
    assert state_path(tmp_path, "extract") == tmp_path / "_state" / "extract.json"
    assert done_path(tmp_path, "extract") == tmp_path / "_state" / ".done" / "extract.json"


def test_is_done_false_when_only_active(tmp_path: Path):
    write_active(
        tmp_path, "extract",
        batch_id="b1", model="gpt-5-nano", n_jobs=1, custom_ids=["A"],
    )
    assert not is_done(tmp_path, "extract")
