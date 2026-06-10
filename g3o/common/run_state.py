"""Per-stage state files for crash-recovery and ``--resume`` (Session E, 2026-05-09).

Layout under ``runs/<run_id>/_state/``::

    {stage}.json        — active state (chunk plan + per-chunk batch handles)
    .done/{stage}.json  — terminal completion marker; presence ⇒ stage done

Session E decisions (2026-05-09):
  - Q1=a: batch-level state files (one per stage), not per-institution.
  - Q2=iii: post-fetch disposition is "move state to ``.done/``".
  - Q3=e2: an explicit ``.done/{stage}.json`` marker is the
    "stage fully complete" signal.
  - Q3=d: failed/cancelled/expired batches do NOT auto-resubmit; the active
    state file remains and the runner raises with a pointer to the path.
  - Q4=ii: the state file's ``custom_ids`` list is the canonical job set
    for the in-flight batch; re-projecting the master CSV at resume time
    is ignored for the LLM subset (bypass envelopes already on disk are
    authoritative).
  - Q7=c: resume is auto-inferred from the presence of state files; no
    explicit ``--resume`` flag.
  - Q8=ii: Stage 6 (validate) is folded into ``g3o.run.presweep.STAGES``.

Session F.1 revisions (2026-06-10, review F2/F6/F8/F16):
  - State schema v2: a stage's jobs are split into size-capped chunks
    (:func:`g3o.common.batch_client.split_jobs_into_chunks`); the active
    state file records the full chunk plan *before* the first submission,
    so a crash between ``submit_batch`` returning and the state write can
    no longer orphan a live batch — resume reconciles by metadata instead.
  - Every submit carries ``{g3o_run_id, g3o_stage, g3o_chunk}`` metadata;
    before any fresh submit the orchestrator reconciles against the server
    (:func:`run_chunked_stage` docstring has the decision tree).
  - All state writes are atomic via temp-file + ``os.replace`` (review F8).
  - Deadline expiry while a batch is still in flight raises a "timed out;
    re-run to rejoin" error, distinct from terminal failure (review F16).
  - Legacy (un-chunked, schema v1) active state files fail loudly: the
    pipeline has never executed live, so none can legitimately exist.

Stages 1a/1b/4 (deterministic) write a no-batch ``.done`` marker at end.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.common import batch_client
from g3o.common.batch_client import BatchJob, BatchResult

logger = logging.getLogger(__name__)


_STATE_DIR = "_state"
_DONE_DIR = ".done"

STATE_SCHEMA_VERSION = 2


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON via temp-file + ``os.replace`` (atomic on Windows and POSIX)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def state_dir(run_dir: Path) -> Path:
    return run_dir / _STATE_DIR


def done_dir(run_dir: Path) -> Path:
    return state_dir(run_dir) / _DONE_DIR


def state_path(run_dir: Path, stage: str) -> Path:
    return state_dir(run_dir) / f"{stage}.json"


def done_path(run_dir: Path, stage: str) -> Path:
    return done_dir(run_dir) / f"{stage}.json"


def is_done(run_dir: Path, stage: str) -> bool:
    """Return True iff the stage's ``.done`` marker is present (Q3=e2)."""
    return done_path(run_dir, stage).exists()


def load_state(run_dir: Path, stage: str) -> dict[str, Any] | None:
    """Read the active state file for a stage, or None if not present."""
    p = state_path(run_dir, stage)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def assert_chunked_state(state: dict[str, Any], *, path: Path) -> None:
    """Refuse to interpret a legacy (schema v1, un-chunked) state file.

    The chunked machinery landed 2026-06-10 before any live ``--execute``
    run, so no legitimate v1 active state file can exist; one showing up
    means something outside the pipeline wrote it. Failing loudly beats
    silently misreading a single-batch layout as an empty chunk plan.
    """
    if state.get("schema_version") != STATE_SCHEMA_VERSION or "chunks" not in state:
        raise RuntimeError(
            f"Legacy un-chunked state file at {path}: this layout predates the "
            f"chunked-state machinery (2026-06-10) and no live run should have "
            f"produced it. Refusing to interpret it; investigate (and archive "
            f"the file) before retrying."
        )


def write_active_chunked(
    run_dir: Path,
    stage: str,
    *,
    run_id: str,
    model: str,
    chunk_custom_ids: list[list[str]],
    bypass_count: int | None = None,
) -> Path:
    """Persist the full chunk plan at planning time, before any submission.

    Writing the plan first (rather than per-batch after ``submit_batch``, as
    in schema v1) closes the F6 orphan window: every subsequent submit is
    preceded by a state file naming the chunk, so a crash at any point leaves
    enough on disk for resume to reconcile against the server by metadata.
    Atomic via temp-file + ``os.replace``.

    ``custom_ids`` are deduplicated and sorted per chunk (canonical storage;
    submission order within a batch is semantically irrelevant — results
    round-trip by ``custom_id``).
    """
    state_dir(run_dir).mkdir(parents=True, exist_ok=True)
    chunks: dict[str, dict[str, Any]] = {}
    total = 0
    for i, ids in enumerate(chunk_custom_ids, start=1):
        ids_sorted = sorted(set(ids))
        chunks[str(i)] = {
            "custom_ids": ids_sorted,
            "n_jobs": len(ids_sorted),
            "batch_id": None,
            "submitted_at": None,
            "adopted": False,
            "last_polled_at": None,
            "last_status": None,
            "fetched_at": None,
        }
        total += len(ids_sorted)
    payload: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "stage": stage,
        "run_id": run_id,
        "model": model,
        "n_jobs": total,
        "n_chunks": len(chunks),
        "created_at": _utc_iso(),
        "chunks": chunks,
    }
    if bypass_count is not None:
        payload["bypass_count"] = bypass_count
    p = state_path(run_dir, stage)
    _write_json_atomic(p, payload)
    return p


def update_chunk(run_dir: Path, stage: str, chunk: int | str, **fields: Any) -> None:
    """Merge ``fields`` into one chunk entry of the active state file.

    No-op if the active state file has been moved away (e.g. by
    ``mark_done``) so the helper stays safe to call after stage completion.
    Atomic via temp-file + ``os.replace``.
    """
    p = state_path(run_dir, stage)
    if not p.exists():
        return
    payload = json.loads(p.read_text(encoding="utf-8"))
    payload["chunks"][str(chunk)].update(fields)
    _write_json_atomic(p, payload)


def iter_chunks(state: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(chunk_key, entry)`` in ascending numeric chunk order."""
    chunks = state.get("chunks", {})
    for key in sorted(chunks, key=int):
        yield key, chunks[key]


def mark_done(run_dir: Path, stage: str, *, no_batch: bool = False) -> Path:
    """Move the active state file to ``.done/{stage}.json`` (Q2=iii).

    For deterministic stages (1a, 1b, scrape) and the all-bypassed Stage 2
    case, no active state file exists; pass ``no_batch=True`` to write a
    minimal completion marker. Idempotent: re-marking an already-done stage
    is a no-op. Writes are atomic via temp-file + ``os.replace``.
    """
    src = state_path(run_dir, stage)
    dst = done_path(run_dir, stage)
    done_dir(run_dir).mkdir(parents=True, exist_ok=True)
    if dst.exists() and not src.exists():
        return dst
    if src.exists():
        payload = json.loads(src.read_text(encoding="utf-8"))
        payload["fetched_at"] = _utc_iso()
        _write_json_atomic(dst, payload)
        src.unlink()
        return dst
    payload = {"stage": stage, "fetched_at": _utc_iso(), "no_batch": no_batch}
    _write_json_atomic(dst, payload)
    return dst


def _chunk_metadata(run_id: str, stage: str, chunk: int | str) -> dict[str, str]:
    """Unique batch identity carried as OpenAI batch metadata (review F6)."""
    return {"g3o_run_id": run_id, "g3o_stage": stage, "g3o_chunk": str(chunk)}


def run_chunked_stage(
    run_dir: Path,
    stage: str,
    jobs: list[BatchJob],
    *,
    run_id: str,
    model: str,
    poll_interval: int,
    max_wait: int,
    process_chunk_results: Callable[[Iterator[BatchResult]], None],
    bypass_count: int | None = None,
    completion_window: str = batch_client.DEFAULT_COMPLETION_WINDOW,
    endpoint: str = batch_client.DEFAULT_ENDPOINT,
    max_chunk_bytes: int = batch_client.CHUNK_MAX_BYTES,
    max_chunk_requests: int = batch_client.CHUNK_MAX_REQUESTS,
    client: Any | None = None,
) -> None:
    """Submit, poll, and fetch one LLM stage as size-capped batch chunks.

    Single orchestration path shared by presweep Stages 2/3/5 and the Stage 6
    consolidate driver. ``jobs`` must be the complete, deterministically
    rebuilt job list for the stage — on resume, jobs for chunks that still
    need submission are selected from it by ``custom_id`` (Q4=ii: the state
    file's plan is canonical; a plan ``custom_id`` that cannot be rebuilt is
    an error, not a silent drop).

    Fresh run: split jobs into chunks, persist the full plan (atomic), then
    for each chunk reconcile-then-submit. Resume: chunks with ``fetched_at``
    are skipped (their results were fetched and persisted exactly once);
    chunks with a ``batch_id`` rejoin polling without resubmitting; chunks
    without one go through reconciliation before any fresh submit.

    Reconciliation decision tree, per (run_id, stage, chunk), evaluated
    before every fresh submit (review F6b — orphaned live batches):

    1. List recent batches; keep those whose metadata exactly matches
       ``{g3o_run_id, g3o_stage, g3o_chunk}``.
    2. No match → submit fresh.
    3. Exactly one match, terminal non-completed (failed/cancelled/expired)
       → raise. A prior attempt exists and went bad; silently submitting a
       replacement would repeat the spend without an operator decision
       (extends Q3=d to orphans).
    4. Exactly one match, alive or completed → adopt: record its batch_id in
       the chunk state and rejoin polling. No resubmit, no double spend.
    5. More than one match → raise naming the batch ids. A double-submit
       already exists server-side; the operator must cancel the duplicates.

    Polling: all in-flight chunks are polled round-robin each cycle. A chunk
    that completes is fetched and handed to ``process_chunk_results``, and
    only then marked ``fetched_at`` — a crash mid-persist re-fetches that
    chunk, never a fetched one. A chunk that ends failed/cancelled/expired
    is recorded and reported *after* the remaining chunks finish fetching
    (maximizes preserved work), then raises per Q3=d — no auto-resubmit; the
    active state file remains, naming the failed chunk. If ``max_wait``
    elapses with chunks still in flight, the raise says so truthfully
    (review F16): the batches have NOT ended; re-running the same command
    rejoins polling without resubmitting.

    On success (every chunk fetched), the state file moves to
    ``.done/{stage}.json`` — the stage-complete signal is unchanged (Q3=e2).
    """
    state = load_state(run_dir, stage)
    if state is not None:
        assert_chunked_state(state, path=state_path(run_dir, stage))

    jobs_by_id: dict[str, BatchJob] = {}
    for job in jobs:
        if job.custom_id in jobs_by_id:
            raise ValueError(f"duplicate custom_id in stage jobs: {job.custom_id!r}")
        jobs_by_id[job.custom_id] = job

    if state is None:
        chunked = batch_client.split_jobs_into_chunks(
            jobs,
            model=model,
            endpoint=endpoint,
            max_bytes=max_chunk_bytes,
            max_requests=max_chunk_requests,
        )
        write_active_chunked(
            run_dir, stage,
            run_id=run_id, model=model,
            chunk_custom_ids=[[j.custom_id for j in c] for c in chunked],
            bypass_count=bypass_count,
        )
        state = load_state(run_dir, stage)
        assert state is not None
        logger.info(
            "Stage %s: %d jobs split into %d chunk(s)",
            stage, len(jobs), state["n_chunks"],
        )

    # --- Submit phase: reconcile-then-submit every chunk without a batch_id.
    for key, entry in iter_chunks(state):
        if entry["fetched_at"] is not None or entry["batch_id"] is not None:
            continue
        metadata = _chunk_metadata(run_id, stage, key)
        existing = batch_client.find_batches_by_metadata(metadata, client=client)
        if len(existing) > 1:
            raise RuntimeError(
                f"Stage {stage} chunk {key}: found {len(existing)} batches matching "
                f"metadata {metadata}: {[s.batch_id for s in existing]}. A "
                f"double-submit already exists server-side; cancel the duplicates "
                f"before retrying. State file: {state_path(run_dir, stage)}."
            )
        if len(existing) == 1:
            found = existing[0]
            if found.is_terminal and not found.is_completed:
                raise RuntimeError(
                    f"Stage {stage} chunk {key}: reconciliation found orphaned "
                    f"batch {found.batch_id} in terminal state {found.status!r} "
                    f"(submitted by a prior crashed attempt). Auto-resubmit is "
                    f"disabled (Q3=d); investigate before retrying. State file: "
                    f"{state_path(run_dir, stage)}."
                )
            logger.warning(
                "Stage %s chunk %s: adopted existing batch %s (status=%s) found "
                "by metadata reconciliation — no resubmit",
                stage, key, found.batch_id, found.status,
            )
            update_chunk(
                run_dir, stage, key,
                batch_id=found.batch_id, submitted_at=_utc_iso(),
                adopted=True, last_status=found.status,
            )
            continue
        missing = [cid for cid in entry["custom_ids"] if cid not in jobs_by_id]
        if missing:
            raise RuntimeError(
                f"Stage {stage} chunk {key}: {len(missing)} custom_id(s) in the "
                f"state plan cannot be rebuilt from the run inputs (first: "
                f"{missing[0]!r}). The run directory has drifted since the plan "
                f"was written; investigate before retrying. State file: "
                f"{state_path(run_dir, stage)}."
            )
        chunk_jobs = [jobs_by_id[cid] for cid in entry["custom_ids"]]
        handle = batch_client.submit_batch(
            chunk_jobs,
            model=model,
            completion_window=completion_window,
            endpoint=endpoint,
            metadata=metadata,
            client=client,
        )
        logger.info(
            "Stage %s chunk %s submitted: %s (n_jobs=%d)",
            stage, key, handle.batch_id, handle.n_jobs,
        )
        update_chunk(
            run_dir, stage, key,
            batch_id=handle.batch_id, submitted_at=_utc_iso(),
        )

    # --- Poll phase: round-robin all unfetched chunks to terminal state.
    deadline = time.monotonic() + max_wait
    failed: dict[str, str] = {}
    while True:
        state = load_state(run_dir, stage)
        assert state is not None
        pending = [
            (key, entry)
            for key, entry in iter_chunks(state)
            if entry["fetched_at"] is None and key not in failed
        ]
        if not pending:
            break
        for key, entry in pending:
            status = batch_client.poll_batch(entry["batch_id"], client=client)
            update_chunk(
                run_dir, stage, key,
                last_polled_at=_utc_iso(), last_status=status.status,
            )
            if status.is_completed:
                process_chunk_results(
                    batch_client.fetch_results(
                        entry["batch_id"], client=client, status=status
                    )
                )
                update_chunk(run_dir, stage, key, fetched_at=_utc_iso())
            elif status.is_terminal:
                failed[key] = status.status
                logger.warning(
                    "Stage %s chunk %s: batch %s ended in terminal state %s; "
                    "will raise after the remaining chunks are fetched "
                    "(no auto-resubmit, Q3=d)",
                    stage, key, entry["batch_id"], status.status,
                )
        state = load_state(run_dir, stage)
        assert state is not None
        in_flight = [
            key
            for key, entry in iter_chunks(state)
            if entry["fetched_at"] is None and key not in failed
        ]
        if not in_flight:
            break
        if time.monotonic() >= deadline:
            detail = ", ".join(
                f"chunk {key} (batch {state['chunks'][key]['batch_id']}, "
                f"last status {state['chunks'][key]['last_status']})"
                for key in in_flight
            )
            raise RuntimeError(
                f"Stage {stage}: timed out after {max_wait}s with {detail} still "
                f"in flight. The batch(es) have NOT ended — an in-progress batch "
                f"is healthy; do not cancel it. Re-run the same command to rejoin "
                f"polling without re-submitting. State file: "
                f"{state_path(run_dir, stage)}."
            )
        time.sleep(poll_interval)

    if failed:
        detail = ", ".join(
            f"chunk {key} ({failed[key]})" for key in sorted(failed, key=int)
        )
        raise RuntimeError(
            f"Stage {stage}: batch {detail} ended in a terminal non-completed "
            f"state. Auto-resubmit is disabled (Q3=d); the active state file "
            f"remains at {state_path(run_dir, stage)} naming the failed "
            f"chunk(s). Investigate before retrying."
        )

    mark_done(run_dir, stage)


__all__ = [
    "STATE_SCHEMA_VERSION",
    "assert_chunked_state",
    "done_path",
    "done_dir",
    "is_done",
    "iter_chunks",
    "load_state",
    "mark_done",
    "run_chunked_stage",
    "state_dir",
    "state_path",
    "update_chunk",
    "write_active_chunked",
]
