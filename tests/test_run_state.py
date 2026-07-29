"""Tests for ``g3o.common.run_state`` (Session E 2026-05-09; chunked Session F.1 2026-06-10).

Covers the per-stage state-file primitives that gate crash-recovery and
``--resume`` (Q1=a, Q2=iii, Q3=e2, Q7=c) in their chunked v2 form, plus the
``run_chunked_stage`` orchestrator: chunk planning, metadata reconciliation
(adopt vs submit vs raise), per-chunk crash recovery, the Q3=d no-auto-resubmit
raise, and the truthful timed-out-while-in-flight raise (review F16). All
OpenAI traffic is stubbed at the ``g3o.common.batch_client`` boundary.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from g3o.common import batch_client
from g3o.common.batch_client import BatchHandle, BatchJob, BatchResult, BatchStatus
from g3o.common.run_state import (
    done_path,
    is_done,
    iter_chunks,
    load_state,
    mark_done,
    run_chunked_stage,
    state_path,
    update_chunk,
    write_active_chunked,
)


def _status(state: str, batch_id: str = "batch-test") -> BatchStatus:
    return BatchStatus(
        batch_id=batch_id,
        status=state,
        request_counts={},
        output_file_id=None,
        error_file_id=None,
    )


def _jobs(n: int, prefix: str = "J") -> list[BatchJob]:
    return [
        BatchJob(
            custom_id=f"{prefix}{i}",
            messages=[{"role": "user", "content": f"payload {i}"}],
        )
        for i in range(n)
    ]


def _install_stub(
    monkeypatch,
    *,
    run_dir: Path,
    statuses: dict[str, list[str]],
    found=None,
):
    """Stub the batch_client surface run_chunked_stage talks to.

    ``statuses`` maps batch_id → list of status strings consumed one per
    poll (the last repeats). ``found`` is an optional callable
    ``metadata -> list[BatchStatus]`` for reconciliation; default: nothing
    found. ``run_dir`` lets the fetch stub mirror a real completed batch by
    returning one result per *planned* custom_id for the chunk a batch backs
    (the canonical set on disk), rather than a single synthetic id. Returns
    (submits, fetches) recorders.
    """
    submits: list[dict[str, Any]] = []
    fetches: list[str] = []

    def _submit(jobs, *, model, completion_window, endpoint, metadata, client=None):
        batch_id = f"batch-{metadata['g3o_chunk']}"
        submits.append(
            {
                "batch_id": batch_id,
                "custom_ids": [j.custom_id for j in jobs],
                "metadata": dict(metadata),
                "model": model,
            }
        )
        statuses.setdefault(batch_id, ["completed"])
        return BatchHandle(
            batch_id=batch_id,
            input_file_id="file-x",
            submitted_at=datetime.now(timezone.utc),
            n_jobs=len(jobs),
        )

    def _poll(batch_id, *, client=None):
        seq = statuses[batch_id]
        status = seq.pop(0) if len(seq) > 1 else seq[0]
        return _status(status, batch_id)

    def _fetch(batch_id, *, client=None, status=None):
        fetches.append(batch_id)
        # Mirror a real completed batch: return one result per planned
        # custom_id for the chunk this batch backs. The plan on disk is the
        # canonical job set (Q4=ii), so this works uniformly whether the batch
        # was submitted through the stub, adopted, or pre-seeded by a resume test.
        state = load_state(run_dir, "extract")
        custom_ids: list[str] = []
        if state is not None:
            for entry in state["chunks"].values():
                if entry.get("batch_id") == batch_id:
                    custom_ids = list(entry["custom_ids"])
                    break
        for cid in custom_ids:
            yield BatchResult(
                custom_id=cid,
                success=True,
                response={"body": {"choices": [{"message": {"content": "ok"}}]}},
                error=None,
            )

    def _find(metadata, *, client=None, **kw):
        if found is None:
            return []
        return found(metadata)

    monkeypatch.setattr(batch_client, "submit_batch", _submit)
    monkeypatch.setattr(batch_client, "poll_batch", _poll)
    monkeypatch.setattr(batch_client, "fetch_results", _fetch)
    monkeypatch.setattr(batch_client, "find_batches_by_metadata", _find)
    return submits, fetches


# ---------------------------------------------------------------------------
# write_active_chunked / load_state / update_chunk
# ---------------------------------------------------------------------------


def test_write_active_chunked_persists_plan_before_submission(tmp_path: Path):
    p = write_active_chunked(
        tmp_path, "classify_official_site",
        run_id="run-1", model="gpt-5-nano",
        chunk_custom_ids=[["INST-0001", "INST-0002"], ["INST-0003"]],
    )
    assert p == state_path(tmp_path, "classify_official_site")
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["stage"] == "classify_official_site"
    assert payload["run_id"] == "run-1"
    assert payload["model"] == "gpt-5-nano"
    assert payload["n_jobs"] == 3
    assert payload["n_chunks"] == 2
    # The plan exists before any submission: no batch handles yet.
    for entry in payload["chunks"].values():
        assert entry["batch_id"] is None
        assert entry["submitted_at"] is None
        assert entry["fetched_at"] is None
        assert entry["last_status"] is None
    assert payload["chunks"]["1"]["custom_ids"] == ["INST-0001", "INST-0002"]
    assert payload["chunks"]["2"]["custom_ids"] == ["INST-0003"]
    assert "bypass_count" not in payload


def test_write_active_chunked_records_bypass_count_and_dedupes(tmp_path: Path):
    write_active_chunked(
        tmp_path, "classify_official_site",
        run_id="run-1", model="gpt-5-nano",
        chunk_custom_ids=[["B", "A", "B"]],
        bypass_count=7,
    )
    payload = load_state(tmp_path, "classify_official_site")
    assert payload is not None
    assert payload["bypass_count"] == 7
    assert payload["chunks"]["1"]["custom_ids"] == ["A", "B"]
    assert payload["chunks"]["1"]["n_jobs"] == 2


def test_load_state_returns_none_when_missing(tmp_path: Path):
    assert load_state(tmp_path, "extract") is None


def test_update_chunk_merges_fields(tmp_path: Path):
    write_active_chunked(
        tmp_path, "extract",
        run_id="r", model="gpt-5-nano", chunk_custom_ids=[["A"], ["B"]],
    )
    update_chunk(tmp_path, "extract", 2, batch_id="b2", last_status="in_progress")
    payload = load_state(tmp_path, "extract")
    assert payload is not None
    assert payload["chunks"]["2"]["batch_id"] == "b2"
    assert payload["chunks"]["2"]["last_status"] == "in_progress"
    # Sibling chunk untouched.
    assert payload["chunks"]["1"]["batch_id"] is None


def test_update_chunk_is_noop_after_done(tmp_path: Path):
    """update_chunk must not resurrect a state file the runner has finalized."""
    write_active_chunked(
        tmp_path, "extract",
        run_id="r", model="gpt-5-nano", chunk_custom_ids=[["A"]],
    )
    mark_done(tmp_path, "extract")
    update_chunk(tmp_path, "extract", 1, last_status="completed")
    assert not state_path(tmp_path, "extract").exists()


def test_iter_chunks_numeric_order(tmp_path: Path):
    write_active_chunked(
        tmp_path, "extract",
        run_id="r", model="gpt-5-nano",
        chunk_custom_ids=[[f"C{i}"] for i in range(11)],
    )
    state = load_state(tmp_path, "extract")
    assert state is not None
    keys = [k for k, _ in iter_chunks(state)]
    assert keys == [str(i) for i in range(1, 12)]  # "2" before "10"


# ---------------------------------------------------------------------------
# mark_done / is_done
# ---------------------------------------------------------------------------


def test_mark_done_moves_active_to_done_and_appends_fetched_at(tmp_path: Path):
    write_active_chunked(
        tmp_path, "classify_triage",
        run_id="r", model="gpt-5-nano", chunk_custom_ids=[["A", "B", "C"]],
    )
    src = state_path(tmp_path, "classify_triage")
    assert src.exists()
    dst = mark_done(tmp_path, "classify_triage")
    assert dst == done_path(tmp_path, "classify_triage")
    assert dst.exists()
    assert not src.exists()
    payload = json.loads(dst.read_text(encoding="utf-8"))
    assert payload["chunks"]["1"]["custom_ids"] == ["A", "B", "C"]
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
    write_active_chunked(
        tmp_path, "validate",
        run_id="r", model="gpt-5-nano", chunk_custom_ids=[["A"]],
    )
    mark_done(tmp_path, "validate")
    second = mark_done(tmp_path, "validate")
    assert second == done_path(tmp_path, "validate")


def test_mark_done_leaves_no_tmp_file(tmp_path: Path):
    """Atomic-write plumbing (review F8): no .tmp residue after a write."""
    write_active_chunked(
        tmp_path, "validate",
        run_id="r", model="gpt-5-nano", chunk_custom_ids=[["A"]],
    )
    mark_done(tmp_path, "validate")
    leftovers = list(tmp_path.rglob("*.tmp"))
    assert leftovers == []


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def test_state_and_done_paths_match_layout(tmp_path: Path):
    assert state_path(tmp_path, "extract") == tmp_path / "_state" / "extract.json"
    assert done_path(tmp_path, "extract") == tmp_path / "_state" / ".done" / "extract.json"


def test_is_done_false_when_only_active(tmp_path: Path):
    write_active_chunked(
        tmp_path, "extract",
        run_id="r", model="gpt-5-nano", chunk_custom_ids=[["A"]],
    )
    assert not is_done(tmp_path, "extract")


# ---------------------------------------------------------------------------
# run_chunked_stage — fresh runs
# ---------------------------------------------------------------------------


def _run(tmp_path, jobs, *, monkeypatch_args=None, **overrides):
    """Call run_chunked_stage with test-friendly defaults, collecting results."""
    received: list[str] = []

    def _collect(results):
        received.extend(r.custom_id for r in results)

    kwargs: dict[str, Any] = dict(
        run_id="run-1",
        model="gpt-5-nano",
        poll_interval=0,
        max_wait=10,
        process_chunk_results=_collect,
    )
    kwargs.update(overrides)
    run_chunked_stage(tmp_path, "extract", jobs, **kwargs)
    return received


def test_single_chunk_happy_path(tmp_path: Path, monkeypatch):
    submits, fetches = _install_stub(
        monkeypatch,
        run_dir=tmp_path,
        statuses={"batch-1": ["validating", "in_progress", "completed"]},
    )
    received = _run(tmp_path, _jobs(3))
    assert len(submits) == 1
    assert submits[0]["custom_ids"] == ["J0", "J1", "J2"]
    assert submits[0]["metadata"] == {
        "g3o_run_id": "run-1", "g3o_stage": "extract", "g3o_chunk": "1",
    }
    assert fetches == ["batch-1"]
    assert received == ["J0", "J1", "J2"]
    assert is_done(tmp_path, "extract")
    assert not state_path(tmp_path, "extract").exists()
    done = json.loads(done_path(tmp_path, "extract").read_text(encoding="utf-8"))
    assert done["chunks"]["1"]["batch_id"] == "batch-1"
    assert done["chunks"]["1"]["fetched_at"] is not None


def test_multi_chunk_split_and_distinct_metadata(tmp_path: Path, monkeypatch):
    submits, fetches = _install_stub(monkeypatch, run_dir=tmp_path, statuses={})
    received = _run(tmp_path, _jobs(3), max_chunk_requests=1)
    assert [s["custom_ids"] for s in submits] == [["J0"], ["J1"], ["J2"]]
    assert [s["metadata"]["g3o_chunk"] for s in submits] == ["1", "2", "3"]
    assert sorted(fetches) == ["batch-1", "batch-2", "batch-3"]
    assert sorted(received) == ["J0", "J1", "J2"]
    assert is_done(tmp_path, "extract")


def test_state_plan_written_before_first_submit(tmp_path: Path, monkeypatch):
    """The chunk plan must hit disk before submit_batch fires (F6 orphan window)."""
    seen_at_submit: list[dict[str, Any] | None] = []

    def _submit(jobs, *, model, completion_window, endpoint, metadata, client=None):
        seen_at_submit.append(load_state(tmp_path, "extract"))
        return BatchHandle(
            batch_id="batch-1", input_file_id="f",
            submitted_at=datetime.now(timezone.utc), n_jobs=len(jobs),
        )

    def _fetch(batch_id, *, client=None, status=None):
        # Return the chunk's complete planned set (J0, J1), as a real completed
        # batch would; this test is about plan-before-submit, not completeness.
        for cid in ("J0", "J1"):
            yield BatchResult(
                custom_id=cid,
                success=True,
                response={"body": {"choices": [{"message": {"content": "ok"}}]}},
                error=None,
            )

    monkeypatch.setattr(batch_client, "submit_batch", _submit)
    monkeypatch.setattr(batch_client, "find_batches_by_metadata", lambda md, **kw: [])
    monkeypatch.setattr(
        batch_client, "poll_batch", lambda b, client=None: _status("completed", b)
    )
    monkeypatch.setattr(batch_client, "fetch_results", _fetch)
    _run(tmp_path, _jobs(2))
    assert len(seen_at_submit) == 1
    plan = seen_at_submit[0]
    assert plan is not None and plan["schema_version"] == 2
    assert plan["chunks"]["1"]["custom_ids"] == ["J0", "J1"]


def test_oversized_single_job_refused_before_any_submit(tmp_path: Path, monkeypatch):
    def _explode(*a, **kw):
        raise AssertionError("submit_batch must not be called")

    monkeypatch.setattr(batch_client, "submit_batch", _explode)
    big = BatchJob(custom_id="big", messages=[{"role": "user", "content": "x" * 4096}])
    with pytest.raises(ValueError, match="F3"):
        _run(tmp_path, [big], max_chunk_bytes=1024)
    # Refused at planning: no state file was written either.
    assert load_state(tmp_path, "extract") is None


# ---------------------------------------------------------------------------
# run_chunked_stage — resume / crash recovery
# ---------------------------------------------------------------------------


def test_resume_fetched_inflight_unsubmitted_chunks(tmp_path: Path, monkeypatch):
    """The handoff's canonical scenario: chunks {1: fetched, 2: in-flight,
    3: not-submitted} must resume by skipping 1, rejoining 2, submitting 3."""
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano",
        chunk_custom_ids=[["J0"], ["J1"], ["J2"]],
    )
    update_chunk(tmp_path, "extract", 1, batch_id="batch-1", fetched_at="2026-06-10T00:00:00Z")
    update_chunk(tmp_path, "extract", 2, batch_id="batch-2", last_status="in_progress")
    submits, fetches = _install_stub(
        monkeypatch,
        run_dir=tmp_path,
        statuses={"batch-2": ["in_progress", "completed"], "batch-3": ["completed"]},
    )
    received = _run(tmp_path, _jobs(3))
    # Chunk 1: fetched exactly once (i.e. never again here).
    assert "batch-1" not in fetches
    # Chunk 2: rejoined polling, not resubmitted.
    assert [s["metadata"]["g3o_chunk"] for s in submits] == ["3"]
    # Chunk 3: submitted fresh after reconciliation found nothing.
    assert sorted(fetches) == ["batch-2", "batch-3"]
    assert sorted(received) == ["J1", "J2"]
    assert is_done(tmp_path, "extract")


def test_resume_adopts_orphaned_live_batch_by_metadata(tmp_path: Path, monkeypatch):
    """Crash between submit_batch returning and the chunk update: the live
    batch is found by metadata and adopted instead of resubmitted (F6b)."""
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano", chunk_custom_ids=[["J0"]],
    )

    def _found(metadata):
        assert metadata == {
            "g3o_run_id": "run-1", "g3o_stage": "extract", "g3o_chunk": "1",
        }
        return [_status("in_progress", "batch-orphan")]

    submits, fetches = _install_stub(
        monkeypatch,
        run_dir=tmp_path,
        statuses={"batch-orphan": ["completed"]},
        found=_found,
    )
    received = _run(tmp_path, _jobs(1))
    assert submits == []  # adopted, never resubmitted
    assert fetches == ["batch-orphan"]
    assert received == ["J0"]
    done = json.loads(done_path(tmp_path, "extract").read_text(encoding="utf-8"))
    assert done["chunks"]["1"]["adopted"] is True
    assert done["chunks"]["1"]["batch_id"] == "batch-orphan"


def test_reconciliation_ambiguous_matches_raise(tmp_path: Path, monkeypatch):
    submits, _ = _install_stub(
        monkeypatch,
        run_dir=tmp_path,
        statuses={},
        found=lambda md: [_status("in_progress", "b-1"), _status("in_progress", "b-2")],
    )
    with pytest.raises(RuntimeError, match="cancel the duplicates"):
        _run(tmp_path, _jobs(1))
    assert submits == []


def test_reconciliation_orphaned_failed_batch_raises(tmp_path: Path, monkeypatch):
    submits, _ = _install_stub(
        monkeypatch,
        run_dir=tmp_path,
        statuses={},
        found=lambda md: [_status("failed", "b-dead")],
    )
    with pytest.raises(RuntimeError, match="Q3=d"):
        _run(tmp_path, _jobs(1))
    assert submits == []


def test_resume_plan_custom_id_drift_raises(tmp_path: Path, monkeypatch):
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano", chunk_custom_ids=[["GONE"]],
    )
    _install_stub(monkeypatch, run_dir=tmp_path, statuses={})
    with pytest.raises(RuntimeError, match="cannot be rebuilt"):
        _run(tmp_path, _jobs(1))


def test_legacy_unchunked_state_file_fails_loudly(tmp_path: Path, monkeypatch):
    """A schema-v1 (single-batch) active state file must never be silently
    misinterpreted (handoff item A, backward-compatibility choice: fail loud)."""
    p = state_path(tmp_path, "extract")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "stage": "extract",
                "batch_id": "batch-v1",
                "model": "gpt-5-nano",
                "n_jobs": 1,
                "custom_ids": ["J0"],
                "submitted_at": "2026-05-09T00:00:00Z",
                "last_polled_at": None,
                "last_status": None,
            }
        ),
        encoding="utf-8",
    )
    _install_stub(monkeypatch, run_dir=tmp_path, statuses={})
    with pytest.raises(RuntimeError, match="Legacy un-chunked state file"):
        _run(tmp_path, _jobs(1))


# ---------------------------------------------------------------------------
# run_chunked_stage — terminal failure vs timeout (Q3=d, review F16)
# ---------------------------------------------------------------------------


def test_failed_chunk_raises_after_completed_chunks_are_fetched(
    tmp_path: Path, monkeypatch
):
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano",
        chunk_custom_ids=[["J0"], ["J1"]],
    )
    update_chunk(tmp_path, "extract", 1, batch_id="batch-1")
    update_chunk(tmp_path, "extract", 2, batch_id="batch-2")
    _, fetches = _install_stub(
        monkeypatch,
        run_dir=tmp_path,
        statuses={"batch-1": ["completed"], "batch-2": ["failed"]},
    )
    with pytest.raises(RuntimeError) as exc_info:
        _run(tmp_path, _jobs(2))
    msg = str(exc_info.value)
    assert "chunk 2 (failed)" in msg
    assert "Q3=d" in msg
    assert str(state_path(tmp_path, "extract")) in msg
    # Completed chunk's results were preserved before raising.
    assert fetches == ["batch-1"]
    # No .done marker; state file remains for the operator.
    assert not is_done(tmp_path, "extract")
    state = load_state(tmp_path, "extract")
    assert state is not None
    assert state["chunks"]["1"]["fetched_at"] is not None
    assert state["chunks"]["2"]["fetched_at"] is None


def test_timeout_message_is_truthful_and_state_preserved(tmp_path: Path, monkeypatch):
    """Deadline expiry with a healthy in-progress batch must NOT read as a
    terminal failure (review F16): say timed out, say rejoin, keep state."""
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano", chunk_custom_ids=[["J0"]],
    )
    update_chunk(tmp_path, "extract", 1, batch_id="batch-1")
    _install_stub(monkeypatch, run_dir=tmp_path, statuses={"batch-1": ["in_progress"]})
    with pytest.raises(RuntimeError) as exc_info:
        _run(tmp_path, _jobs(1), max_wait=0)
    msg = str(exc_info.value)
    assert "timed out" in msg
    assert "NOT ended" in msg
    assert "rejoin" in msg
    assert "non-completed" not in msg  # the old, misleading phrasing
    assert not is_done(tmp_path, "extract")
    state = load_state(tmp_path, "extract")
    assert state is not None
    assert state["chunks"]["1"]["last_status"] == "in_progress"
