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
    abandon_chunk_batch,
    done_path,
    is_done,
    iter_chunks,
    load_state,
    mark_done,
    reconcile_path,
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
    """The chunk plan must hit disk before submit_batch fires (F6 orphan window).

    Reworked (Data Validation Team brief 2026-07-28): the prior version carried
    a bespoke ``_fetch`` hand-fed the planned ids purely so the run would finish
    — which quietly encoded "a completed batch is trusted as-is" as correct.
    Now it leans on the shared stub, whose fetch mirrors the on-disk plan, so
    the run genuinely passes reconciliation; the assertions cover both halves:
    the plan is on disk at submit time AND the fetched batch reconciled and
    persisted the full planned set.
    """
    submits, fetches = _install_stub(monkeypatch, run_dir=tmp_path, statuses={})
    seen_at_submit: list[dict[str, Any] | None] = []
    stub_submit = batch_client.submit_batch

    def _capturing_submit(jobs, **kwargs):
        seen_at_submit.append(load_state(tmp_path, "extract"))
        return stub_submit(jobs, **kwargs)

    monkeypatch.setattr(batch_client, "submit_batch", _capturing_submit)
    received = _run(tmp_path, _jobs(2))
    # Plan-before-submit: the state file already carried the full chunk plan
    # when submit_batch was first called.
    assert len(seen_at_submit) == 1
    plan = seen_at_submit[0]
    assert plan is not None and plan["schema_version"] == 2
    assert plan["chunks"]["1"]["custom_ids"] == ["J0", "J1"]
    # Reconciled + persisted: both planned ids came back and the stage completed.
    assert sorted(received) == ["J0", "J1"]
    assert is_done(tmp_path, "extract")


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


# ---------------------------------------------------------------------------
# run_chunked_stage — completeness reconciliation
# (Data Validation Team brief 2026-07-28, item 1; disposition (a))
#
# A completed chunk's fetched result ids must reconcile one-to-one against the
# chunk plan BEFORE the persist callback runs or fetched_at is written. On any
# mismatch the chunk stays active, a durable record naming the affected ids is
# written, and the runner raises — the persist callback (which commits per
# result) must never see a missing/duplicate/empty/unexpected batch.
# ---------------------------------------------------------------------------


def _result(custom_id: str, *, success: bool = True) -> BatchResult:
    return BatchResult(
        custom_id=custom_id,
        success=success,
        response=(
            {"body": {"choices": [{"message": {"content": "ok"}}]}}
            if success
            else None
        ),
        error=None if success else {"message": "boom"},
    )


def _install_mismatch(monkeypatch, tmp_path, batch_id, results):
    """Pre-seed a single completed chunk whose fetch yields ``results``.

    Returns ``persisted`` — the custom_ids the persist callback actually saw
    (must stay empty on a mismatch: reconciliation gates the callback).
    """
    _install_stub(monkeypatch, run_dir=tmp_path, statuses={batch_id: ["completed"]})
    monkeypatch.setattr(
        batch_client, "fetch_results",
        lambda b, *, client=None, status=None: iter(results),
    )
    persisted: list[str] = []

    def _run_it(jobs):
        run_chunked_stage(
            tmp_path, "extract", jobs,
            run_id="run-1", model="gpt-5-nano",
            poll_interval=0, max_wait=10,
            process_chunk_results=lambda rs: persisted.extend(r.custom_id for r in rs),
        )

    return persisted, _run_it


def test_missing_id_keeps_chunk_active_and_records(tmp_path: Path, monkeypatch):
    """A planned id that never comes back: raise, no persist, name the id."""
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano", chunk_custom_ids=[["J0", "J1", "J2"]],
    )
    update_chunk(tmp_path, "extract", 1, batch_id="batch-1")
    persisted, run_it = _install_mismatch(
        monkeypatch, tmp_path, "batch-1", [_result("J0"), _result("J1")]
    )
    with pytest.raises(RuntimeError) as exc:
        run_it(_jobs(3))
    msg = str(exc.value)
    assert "reconcile" in msg
    assert "missing" in msg
    assert "J2" in msg
    # Persist callback never ran — no partial write reached disk.
    assert persisted == []
    # Chunk stays active: no fetched_at, no .done marker, batch_id retained.
    assert not is_done(tmp_path, "extract")
    state = load_state(tmp_path, "extract")
    assert state is not None
    assert state["chunks"]["1"]["fetched_at"] is None
    assert state["chunks"]["1"]["batch_id"] == "batch-1"
    # Durable accounting names the affected id.
    rec_path = reconcile_path(tmp_path, "extract", 1)
    assert str(rec_path) in msg
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    assert rec["missing"] == ["J2"]
    assert rec["batch_id"] == "batch-1"
    assert rec["empty_result_stream"] is False


def test_empty_completed_batch_raises(tmp_path: Path, monkeypatch):
    """Zero results for a nonzero-job chunk: raise, record the empty stream."""
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano", chunk_custom_ids=[["J0"]],
    )
    update_chunk(tmp_path, "extract", 1, batch_id="batch-1")
    persisted, run_it = _install_mismatch(monkeypatch, tmp_path, "batch-1", [])
    with pytest.raises(RuntimeError) as exc:
        run_it(_jobs(1))
    msg = str(exc.value)
    assert "reconcile" in msg
    assert "empty" in msg
    assert persisted == []
    assert not is_done(tmp_path, "extract")
    rec = json.loads(reconcile_path(tmp_path, "extract", 1).read_text(encoding="utf-8"))
    assert rec["empty_result_stream"] is True
    assert rec["missing"] == ["J0"]
    assert rec["n_observed"] == 0


def test_duplicate_id_raises(tmp_path: Path, monkeypatch):
    """A planned id returned twice: raise, name it as a duplicate."""
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano", chunk_custom_ids=[["J0", "J1"]],
    )
    update_chunk(tmp_path, "extract", 1, batch_id="batch-1")
    persisted, run_it = _install_mismatch(
        monkeypatch, tmp_path, "batch-1",
        [_result("J0"), _result("J1"), _result("J1")],
    )
    with pytest.raises(RuntimeError) as exc:
        run_it(_jobs(2))
    msg = str(exc.value)
    assert "duplicate" in msg
    assert "J1" in msg
    assert persisted == []
    assert not is_done(tmp_path, "extract")
    rec = json.loads(reconcile_path(tmp_path, "extract", 1).read_text(encoding="utf-8"))
    assert rec["duplicate"] == ["J1"]


def test_unknown_id_not_in_plan_raises(tmp_path: Path, monkeypatch):
    """An id not in the plan at all: raise, name it as unexpected."""
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano", chunk_custom_ids=[["J0"]],
    )
    update_chunk(tmp_path, "extract", 1, batch_id="batch-1")
    persisted, run_it = _install_mismatch(
        monkeypatch, tmp_path, "batch-1", [_result("J0"), _result("STRAY")]
    )
    with pytest.raises(RuntimeError) as exc:
        run_it(_jobs(1))
    msg = str(exc.value)
    assert "unexpected" in msg
    assert "STRAY" in msg
    assert persisted == []
    assert not is_done(tmp_path, "extract")
    rec = json.loads(reconcile_path(tmp_path, "extract", 1).read_text(encoding="utf-8"))
    assert rec["unexpected"] == ["STRAY"]
    assert rec["missing"] == []


def test_output_error_file_overlap_raises(tmp_path: Path, monkeypatch):
    """Same custom_id in both the output and error files (fetch_results yields
    it twice): a contradictory success+failure for one job — caught as a
    duplicate, never silently collapsed to one outcome."""
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano", chunk_custom_ids=[["J0"]],
    )
    update_chunk(tmp_path, "extract", 1, batch_id="batch-1")
    # fetch_results streams the output file first, then the error file; a job
    # present in both surfaces as the same id yielded success then failure.
    persisted, run_it = _install_mismatch(
        monkeypatch, tmp_path, "batch-1",
        [_result("J0", success=True), _result("J0", success=False)],
    )
    with pytest.raises(RuntimeError) as exc:
        run_it(_jobs(1))
    msg = str(exc.value)
    assert "duplicate" in msg
    assert "J0" in msg
    assert persisted == []
    assert not is_done(tmp_path, "extract")
    rec = json.loads(reconcile_path(tmp_path, "extract", 1).read_text(encoding="utf-8"))
    assert rec["duplicate"] == ["J0"]


def test_regression_silent_completeness_loss_now_raises(tmp_path: Path, monkeypatch):
    """Repro moved from scratchpad now that disposition (a) is confirmed.

    The original defect: a completed batch that returned fewer results than
    planned was handed straight to the persist callback and then marked done,
    so the missing institution(s) vanished silently. Exercised over the full
    fresh submit→poll→fetch path (not a pre-seeded batch_id): the server drops
    J1, and the run must raise with all-or-nothing semantics — the good
    results (J0, J2) are NOT persisted either, and no .done marker is written.
    """
    _install_stub(monkeypatch, run_dir=tmp_path, statuses={})
    # Server returns only J0 and J2 for a 3-job chunk (J1 dropped).
    monkeypatch.setattr(
        batch_client, "fetch_results",
        lambda b, *, client=None, status=None: iter([_result("J0"), _result("J2")]),
    )
    persisted: list[str] = []
    with pytest.raises(RuntimeError, match="reconcile") as exc:
        run_chunked_stage(
            tmp_path, "extract", _jobs(3),
            run_id="run-1", model="gpt-5-nano",
            poll_interval=0, max_wait=10,
            process_chunk_results=lambda rs: persisted.extend(r.custom_id for r in rs),
        )
    assert "J1" in str(exc.value)
    # All-or-nothing: the good results were withheld from the persist callback.
    assert persisted == []
    assert not is_done(tmp_path, "extract")
    state = load_state(tmp_path, "extract")
    assert state is not None
    assert state["chunks"]["1"]["fetched_at"] is None
    # batch_id retained so a re-run rejoins the same batch rather than resubmits.
    assert state["chunks"]["1"]["batch_id"] == "batch-1"
    rec = json.loads(reconcile_path(tmp_path, "extract", 1).read_text(encoding="utf-8"))
    assert rec["missing"] == ["J1"]
# Enqueued-token waves (2026-08-03)
#
# OpenAI caps concurrently-enqueued tokens per org+model. Releasing every chunk
# up front put ~10.6M tokens in the queue against a 2M ceiling and killed
# Stage 5 at n=100 with `token_limit_exceeded` before a single job ran, so
# chunks are now sized by estimated tokens and released in waves.
# ---------------------------------------------------------------------------


def test_token_cap_splits_chunks_that_byte_cap_would_not(tmp_path: Path, monkeypatch):
    """The token cap must bind where the byte and request caps are miles away."""
    submits, _ = _install_stub(monkeypatch, run_dir=tmp_path, statuses={})
    # Three jobs of ~400 bytes each; a budget of ~100 tokens (=400 bytes at the
    # 4.0 bytes/token estimate) admits exactly one job per chunk.
    jobs = [
        BatchJob(custom_id=f"J{i}", messages=[{"role": "user", "content": "x" * 380}])
        for i in range(3)
    ]
    _run(tmp_path, jobs, enqueued_budget=110)
    assert [s["custom_ids"] for s in submits] == [["J0"], ["J1"], ["J2"]], (
        "each job should have become its own chunk under the token budget"
    )


def test_waves_hold_chunks_until_capacity_frees(tmp_path: Path):
    """A second chunk must not be submitted while the first is still in flight.

    The budget admits one chunk at a time, so the submit of chunk 2 may only
    happen after chunk 1 reaches a terminal state — that is the whole point of
    the change, and the assertion is on the interleaving, not just the outcome.
    """
    events: list[str] = []
    poll_counts: dict[str, int] = {}
    # batch_id -> the custom_ids actually submitted in it. The fetch stub replays
    # exactly these, so results reconcile one-to-one against the chunk plan; a
    # synthetic id here would trip the completeness gate before the interleaving
    # assertion below ever runs, and the test would pass on the raise instead of
    # on the guarantee.
    submitted_ids: dict[str, list[str]] = {}

    def _submit(jobs, *, model, completion_window, endpoint, metadata, client=None):
        batch_id = f"batch-{metadata['g3o_chunk']}"
        submitted_ids[batch_id] = [j.custom_id for j in jobs]
        events.append(f"submit:{batch_id}")
        return BatchHandle(
            batch_id=batch_id,
            input_file_id="file-x",
            submitted_at=datetime.now(timezone.utc),
            n_jobs=len(jobs),
        )

    def _poll(batch_id, *, client=None):
        # Each batch needs two polls before completing, giving the scheduler a
        # window in which it could wrongly release the next chunk.
        poll_counts[batch_id] = poll_counts.get(batch_id, 0) + 1
        state = "completed" if poll_counts[batch_id] >= 2 else "in_progress"
        return _status(state, batch_id)

    def _fetch(batch_id, *, client=None, status=None):
        events.append(f"fetch:{batch_id}")
        for custom_id in submitted_ids[batch_id]:
            yield BatchResult(
                custom_id=custom_id, success=True,
                response={"body": {"choices": [{"message": {"content": "ok"}}]}},
                error=None,
            )

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(batch_client, "submit_batch", _submit)
        monkeypatch.setattr(batch_client, "poll_batch", _poll)
        monkeypatch.setattr(batch_client, "fetch_results", _fetch)
        monkeypatch.setattr(
            batch_client, "find_batches_by_metadata", lambda md, **kw: []
        )
        jobs = [
            BatchJob(custom_id=f"J{i}", messages=[{"role": "user", "content": "x" * 380}])
            for i in range(3)
        ]
        _run(tmp_path, jobs, enqueued_budget=110)
    finally:
        monkeypatch.undo()

    assert events == [
        "submit:batch-1", "fetch:batch-1",
        "submit:batch-2", "fetch:batch-2",
        "submit:batch-3", "fetch:batch-3",
    ], f"chunks were not released one wave at a time: {events}"
    assert is_done(tmp_path, "extract")


def test_chunk_larger_than_budget_is_released_alone(tmp_path: Path, monkeypatch):
    """An oversized chunk must go out rather than deadlock the stage.

    Unlike the byte cap, the enqueued ceiling is not a limit on one request, so
    a solo oversized chunk is submittable — and refusing it would strand the
    stage forever with nothing in flight and nothing releasable.
    """
    submits, _ = _install_stub(monkeypatch, run_dir=tmp_path, statuses={})
    jobs = [BatchJob(custom_id="BIG", messages=[{"role": "user", "content": "x" * 8000}])]
    _run(tmp_path, jobs, enqueued_budget=10)
    assert [s["custom_ids"] for s in submits] == [["BIG"]]
    assert is_done(tmp_path, "extract")


def test_resume_counts_in_flight_chunk_against_the_budget(tmp_path: Path, monkeypatch):
    """On resume, an already-live chunk occupies budget and must gate the rest.

    Without this the wave logic would happily pile a fresh submit on top of a
    batch a crashed attempt left running — reintroducing the overrun.
    """
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano",
        chunk_custom_ids=[["J0"], ["J1"]],
    )
    update_chunk(tmp_path, "extract", 1, batch_id="batch-1")
    submits, _ = _install_stub(
        monkeypatch,
        run_dir=tmp_path,
        statuses={"batch-1": ["in_progress", "completed"], "batch-2": ["completed"]},
    )
    jobs = [
        BatchJob(custom_id=f"J{i}", messages=[{"role": "user", "content": "x" * 380}])
        for i in range(2)
    ]
    _run(tmp_path, jobs, enqueued_budget=110)
    # Chunk 1 was adopted from state (never re-submitted); only chunk 2 submits,
    # and only once chunk 1 had finished.
    assert [s["metadata"]["g3o_chunk"] for s in submits] == ["2"]
    assert is_done(tmp_path, "extract")


def test_estimate_is_conservative_relative_to_serialized_bytes():
    """The estimator must never read below the bytes/BYTES_PER_TOKEN floor."""
    assert batch_client.estimate_job_tokens(0) == 0
    assert batch_client.estimate_job_tokens(1) == 1  # rounds up, never to zero
    assert batch_client.estimate_job_tokens(400) == 100
    assert batch_client.estimate_job_tokens(401) == 101


def test_enqueued_budget_leaves_headroom_under_the_ceiling():
    """The pipeline must not plan to occupy the whole org ceiling."""
    budget = batch_client.enqueued_token_budget()
    assert budget < batch_client.ENQUEUED_TOKEN_LIMIT
    assert budget == int(
        batch_client.ENQUEUED_TOKEN_LIMIT * batch_client.ENQUEUED_BUDGET_UTILISATION
    )


def test_abandoned_batch_is_ignored_by_reconciliation(tmp_path: Path, monkeypatch):
    """An adjudicated failed batch must stop blocking its chunk.

    A batch rejected at submission (zero requests run, zero spend) cannot be
    deleted server-side and keeps matching the chunk metadata, so without an
    explicit release valve the chunk is unrecoverable.
    """
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano", chunk_custom_ids=[["J0"]],
    )
    update_chunk(tmp_path, "extract", 1, batch_id="batch-dead")
    dead = _status("failed", "batch-dead")

    # Before adjudication: reconciliation finds the corpse and refuses.
    submits, _ = _install_stub(
        monkeypatch,
        run_dir=tmp_path,
        statuses={"batch-1": ["completed"]},
        found=lambda md, **kw: [dead],
    )
    update_chunk(tmp_path, "extract", 1, batch_id=None)
    with pytest.raises(RuntimeError, match="orphaned batch batch-dead"):
        _run(tmp_path, _jobs(1))
    assert submits == []

    # After adjudication: the chunk submits fresh, and the record persists.
    abandon_chunk_batch(
        tmp_path, "extract", 1, "batch-dead",
        reason="token_limit_exceeded at submit; 0 requests ran, 0 spend",
    )
    received = _run(tmp_path, _jobs(1))
    assert [s["metadata"]["g3o_chunk"] for s in submits] == ["1"]
    # The planned id for chunk 1, not a synthetic one: the fetch stub now mirrors
    # a real batch by replaying the chunk plan, which is what reconciliation checks.
    assert received == ["J0"]
    done = json.loads(done_path(tmp_path, "extract").read_text(encoding="utf-8"))
    assert done["chunks"]["1"]["abandoned_batch_ids"] == ["batch-dead"]
    assert "token_limit_exceeded" in done["chunks"]["1"]["abandon_reasons"]["batch-dead"]


def test_abandoning_does_not_excuse_other_failed_batches(tmp_path: Path, monkeypatch):
    """Adjudicating one batch must not blanket-disable the guard for a chunk."""
    write_active_chunked(
        tmp_path, "extract",
        run_id="run-1", model="gpt-5-nano", chunk_custom_ids=[["J0"]],
    )
    abandon_chunk_batch(tmp_path, "extract", 1, "batch-dead", reason="adjudicated")
    other = _status("expired", "batch-other")
    submits, _ = _install_stub(
        monkeypatch, run_dir=tmp_path, statuses={}, found=lambda md, **kw: [other]
    )
    with pytest.raises(RuntimeError, match="orphaned batch batch-other"):
        _run(tmp_path, _jobs(1))
    assert submits == []
