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
from g3o.common.credentials import ResolvedCredentials

logger = logging.getLogger(__name__)


_STATE_DIR = "_state"
_DONE_DIR = ".done"
_RECONCILE_DIR = ".reconcile"

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


def reconcile_dir(run_dir: Path) -> Path:
    return state_dir(run_dir) / _RECONCILE_DIR


def reconcile_path(run_dir: Path, stage: str, chunk: int | str) -> Path:
    """Durable per-chunk completeness-mismatch incident record.

    Written when a completed chunk's fetched results fail to reconcile
    one-to-one against its plan (Data Validation Team brief 2026-07-28,
    item 1). Distinct from the ``.done`` marker: the chunk is NOT done — the
    active state file stays put so a re-run rejoins the same batch.
    """
    return reconcile_dir(run_dir) / f"{stage}.chunk-{chunk}.json"


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
            "response_models": None,
            "system_fingerprints": None,
            # Batch ids an operator has explicitly adjudicated as disregardable
            # (see `abandon_chunk_batch`). Additive and read defensively, so
            # state files written before 2026-08-03 stay loadable unchanged.
            "abandoned_batch_ids": [],
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


def abandon_chunk_batch(
    run_dir: Path,
    stage: str,
    chunk: int | str,
    batch_id: str,
    *,
    reason: str,
) -> None:
    """Record an operator decision to disregard one batch for a chunk.

    Reconciliation raises when it finds a batch matching a chunk's metadata in
    a terminal non-completed state, because a prior attempt going bad is an
    operator decision, not something to paper over by resubmitting (Q3=d). That
    guard has no release valve, so a batch that failed *at submission* — zero
    requests run, zero spend, no results anywhere — blocks the chunk forever:
    the batch cannot be deleted server-side and keeps matching the metadata.

    This records the adjudication in the state file instead of weakening the
    guard: the named batch is thereafter ignored for that chunk, every other
    batch still raises, and the decision plus its reason stay in the run's
    audit trail. Clears ``batch_id`` if it names the abandoned batch, so the
    chunk returns to the un-submitted pool.

    First use (2026-08-03): Stage 5 of run ``20260802-e2e-100``, whose single
    681-job chunk was rejected with ``token_limit_exceeded`` before any job
    ran, then replanned into token-sized chunks.
    """
    payload = load_state(run_dir, stage)
    if payload is None:
        raise FileNotFoundError(f"no active state for stage {stage!r} in {run_dir}")
    entry = payload["chunks"][str(chunk)]
    abandoned = list(entry.get("abandoned_batch_ids") or [])
    if batch_id not in abandoned:
        abandoned.append(batch_id)
    entry["abandoned_batch_ids"] = abandoned
    entry["abandon_reasons"] = {
        **(entry.get("abandon_reasons") or {}),
        batch_id: reason,
    }
    if entry.get("batch_id") == batch_id:
        entry["batch_id"] = None
        entry["submitted_at"] = None
        entry["last_status"] = None
        entry["last_polled_at"] = None
    _write_json_atomic(state_path(run_dir, stage), payload)
    logger.warning(
        "Stage %s chunk %s: batch %s abandoned by operator decision (%s)",
        stage, chunk, batch_id, reason,
    )


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
    """Unique batch identity carried as OpenAI batch metadata (review F6).

    Identity only — the three keys of ``batch_client.CHUNK_METADATA_KEYS``. This
    is what reconciliation matches on, so it must never grow a field that can
    change between the submit and a later resume (see :func:`_submit_metadata`).
    """
    return {"g3o_run_id": run_id, "g3o_stage": stage, "g3o_chunk": str(chunk)}


def _submit_metadata(
    identity: dict[str, str], key_fingerprint: str | None
) -> dict[str, str]:
    """Batch identity plus the submitting key's fingerprint (Run API spec §3.5).

    Server-side reconciliation lists batches **per API key**, so an operator
    holding two keys cannot otherwise tell which key paid for a batch they are
    looking at. ``g3o_key_fingerprint`` (``sha256(key)[:8]``, never key material —
    §3.3) makes that attributable.

    It is deliberately *stored* but not *matched on*: a resumed run reconciles
    against batches submitted by an earlier process, which — for any batch
    submitted before this field existed — carries no fingerprint at all. Folding
    it into the match key would make those batches unfindable and a reconcile
    miss means a **double submit**, i.e. double spend. Identity is what makes a
    batch unique; the key that paid for it is provenance.

    Omitted entirely when no fingerprint is known (no credentials threaded down):
    batch metadata values are strings, and a null fingerprint would be
    indistinguishable from a real one in a server-side listing.
    """
    if not key_fingerprint:
        return dict(identity)
    return {**identity, "g3o_key_fingerprint": key_fingerprint}


def _reconcile_custom_ids(
    planned: list[str], observed: list[str]
) -> dict[str, list[str]]:
    """Categorize how a chunk's fetched result ids diverge from its plan.

    ``planned`` is the chunk's canonical job set (``entry["custom_ids"]``,
    deduplicated + sorted on disk). ``observed`` is the ordered list of
    ``custom_id``s actually yielded by :func:`batch_client.fetch_results`
    (order-preserving, so a value returned twice — e.g. a job present in both
    the output and error files — is caught as a duplicate).

    Returns a dict with only the non-empty categories among ``missing``,
    ``duplicate``, and ``unexpected`` (each a sorted id list). An empty dict
    means an exact one-to-one match — the only case in which the chunk may be
    persisted and marked fetched. An empty ``observed`` for a non-empty
    ``planned`` (an "empty completed batch") surfaces here as every planned id
    ``missing``.
    """
    planned_set = set(planned)
    seen: set[str] = set()
    duplicate: set[str] = set()
    for cid in observed:
        if cid in seen:
            duplicate.add(cid)
        seen.add(cid)
    problems: dict[str, list[str]] = {}
    missing = sorted(planned_set - seen)
    unexpected = sorted(seen - planned_set)
    if missing:
        problems["missing"] = missing
    if duplicate:
        problems["duplicate"] = sorted(duplicate)
    if unexpected:
        problems["unexpected"] = unexpected
    return problems


def _write_reconcile_record(
    run_dir: Path,
    stage: str,
    chunk: int | str,
    *,
    batch_id: str | None,
    planned: list[str],
    observed: list[str],
    problems: dict[str, list[str]],
) -> Path:
    """Persist a durable accounting record naming the affected ids (atomic)."""
    d = reconcile_dir(run_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = reconcile_path(run_dir, stage, chunk)
    payload: dict[str, Any] = {
        "stage": stage,
        "chunk": str(chunk),
        "batch_id": batch_id,
        "recorded_at": _utc_iso(),
        "n_planned": len(planned),
        "n_observed": len(observed),
        "empty_result_stream": not observed,
        "missing": problems.get("missing", []),
        "duplicate": problems.get("duplicate", []),
        "unexpected": problems.get("unexpected", []),
        "planned": planned,
        "observed": observed,
    }
    _write_json_atomic(path, payload)
    return path


def _reconcile_detail(problems: dict[str, list[str]], *, empty: bool) -> str:
    """One-line human summary of a mismatch for the raised error message."""
    parts: list[str] = []
    if empty:
        parts.append("the result stream was empty")
    labels = {
        "missing": "missing",
        "duplicate": "duplicate",
        "unexpected": "unexpected (not in the plan)",
    }
    for key, label in labels.items():
        ids = problems.get(key)
        if ids:
            parts.append(f"{len(ids)} {label} custom_id(s) (first: {ids[0]!r})")
    return "; ".join(parts)


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
    enqueued_budget: int | None = None,
    client: Any | None = None,
    credentials: ResolvedCredentials | None = None,
) -> None:
    """Submit, poll, and fetch one LLM stage as size-capped batch chunks.

    Single orchestration path shared by presweep Stages 2/3/5 and the Stage 6
    consolidate driver. ``jobs`` must be the complete, deterministically
    rebuilt job list for the stage — on resume, jobs for chunks that still
    need submission are selected from it by ``custom_id`` (Q4=ii: the state
    file's plan is canonical; a plan ``custom_id`` that cannot be rebuilt is
    an error, not a silent drop).

    Fresh run: split jobs into chunks, persist the full plan (atomic), then
    release chunks in waves under ``enqueued_budget`` (see below). Resume:
    chunks with ``fetched_at`` are skipped (their results were fetched and
    persisted exactly once); chunks with a ``batch_id`` rejoin polling without
    resubmitting; chunks without one go through reconciliation before any fresh
    submit.

    **Enqueued-token waves (2026-08-03).** OpenAI caps the tokens an org may
    have enqueued at once per model, counting each queued request's full prompt
    whether or not it prompt-caches. Chunking alone does not satisfy that cap,
    because the cap is on concurrent enqueue: releasing every chunk up front
    put ~10.6M tokens in the queue against a 2M ceiling and Stage 5 at n=100
    died with ``token_limit_exceeded`` before running a single job. So chunks
    are sized by estimated tokens (:func:`batch_client.split_jobs_into_chunks`)
    and released only while the in-flight estimate stays inside
    ``enqueued_budget``; capacity frees as chunks reach a terminal state. A
    chunk larger than the entire budget is released alone rather than raising,
    so it cannot deadlock the stage. Estimates are offline and conservative
    (:data:`batch_client.BYTES_PER_TOKEN`) — an overestimate costs one extra
    wave, an underestimate costs a failed submit.

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
    that completes has its full result stream buffered and reconciled
    one-to-one against the chunk plan (``entry["custom_ids"]``) *before*
    ``process_chunk_results`` runs — any missing, duplicate, empty, or
    unexpected id keeps the chunk active (no ``fetched_at``, no persist),
    writes a durable :func:`reconcile_path` incident record naming the
    affected ids, and raises (Data Validation Team brief 2026-07-28, item 1).
    Only a clean match is handed to ``process_chunk_results`` and then marked
    ``fetched_at`` — a crash mid-persist re-fetches that chunk, never a
    fetched one. A chunk that ends failed/cancelled/expired
    is recorded and reported *after* the remaining chunks finish fetching
    (maximizes preserved work), then raises per Q3=d — no auto-resubmit; the
    active state file remains, naming the failed chunk. If ``max_wait``
    elapses with chunks still in flight, the raise says so truthfully
    (review F16): the batches have NOT ended; re-running the same command
    rejoins polling without resubmitting.

    On success (every chunk fetched), the state file moves to
    ``.done/{stage}.json`` — the stage-complete signal is unchanged (Q3=e2).

    **Credentials (Run API spec §3.2/§3.5).** ``credentials``, when the caller
    threads it down, is the run's resolved key bundle: it builds the one OpenAI
    client this stage uses and supplies the ``g3o_key_fingerprint`` recorded on
    every submit. An explicit ``client`` still wins (test injection). With
    neither, nothing changes from the pre-spec path — each ``batch_client`` call
    constructs its own client from the environment — so a caller that never
    passes credentials behaves exactly as it did, and no submit carries a
    fingerprint the run cannot account for.
    """
    state = load_state(run_dir, stage)
    if state is not None:
        assert_chunked_state(state, path=state_path(run_dir, stage))

    if client is None and credentials is not None:
        client = batch_client.client_from_credentials(credentials)
    key_fingerprint = credentials.openai_fingerprint if credentials else None

    if enqueued_budget is None:
        enqueued_budget = batch_client.enqueued_token_budget()

    jobs_by_id: dict[str, BatchJob] = {}
    for job in jobs:
        if job.custom_id in jobs_by_id:
            raise ValueError(f"duplicate custom_id in stage jobs: {job.custom_id!r}")
        jobs_by_id[job.custom_id] = job

    # Per-job token estimates, keyed by custom_id, for scheduling against the
    # enqueued-token budget. Costs one extra serialization pass and no API calls.
    job_tokens = batch_client.job_token_estimates(
        jobs, model=model, endpoint=endpoint
    )

    def chunk_tokens(key: str) -> int:
        """Estimated enqueued tokens of a planned chunk, from its custom_ids.

        Reads the plan rather than the chunking pass, so it is correct on resume
        too — where the plan is canonical and chunks may already be in flight.
        """
        entry = state["chunks"][key] if state else {}
        return sum(job_tokens.get(cid, 0) for cid in entry.get("custom_ids", ()))

    if state is None:
        chunked = batch_client.split_jobs_into_chunks(
            jobs,
            model=model,
            endpoint=endpoint,
            max_bytes=max_chunk_bytes,
            max_requests=max_chunk_requests,
            max_tokens=enqueued_budget,
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

    def _submit_one(key: str, entry: dict[str, Any]) -> bool:
        """Reconcile-then-submit one chunk. True if it is now in flight."""
        # Identity is the match key; the fingerprint rides along on the submit
        # only (see _submit_metadata for why the two must not be the same dict).
        metadata = _chunk_metadata(run_id, stage, key)
        existing = batch_client.find_batches_by_metadata(metadata, client=client)
        # Drop batches an operator has explicitly adjudicated for this chunk
        # (see `abandon_chunk_batch`); every other match still counts.
        abandoned = set(entry.get("abandoned_batch_ids") or ())
        if abandoned:
            existing = [s for s in existing if s.batch_id not in abandoned]
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
            return True
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
            metadata=_submit_metadata(metadata, key_fingerprint),
            client=client,
        )
        logger.info(
            "Stage %s chunk %s submitted: %s (n_jobs=%d, ~%s est. enqueued tokens)",
            stage, key, handle.batch_id, handle.n_jobs, f"{chunk_tokens(key):,}",
        )
        update_chunk(
            run_dir, stage, key,
            batch_id=handle.batch_id, submitted_at=_utc_iso(),
        )
        return True

    # --- Submit + poll, interleaved under the enqueued-token budget.
    #
    # Submitting every chunk up front (the pre-2026-08-03 shape) breaks the
    # moment a stage's total enqueued tokens exceed the org/model ceiling: the
    # ceiling is on what is enqueued *concurrently*, so chunking alone does not
    # help — Stage 5 at n=100 needs ~10.6M against a 2M ceiling and failed with
    # `token_limit_exceeded` before a single job ran. Chunks are therefore
    # released in waves: submit while the budget allows, then wait for in-flight
    # chunks to finish and free capacity before releasing more.
    #
    # Resume semantics are unchanged. The chunk plan is still persisted in full
    # before the first submit, chunks with `fetched_at` are still skipped, and
    # chunks already carrying a `batch_id` still rejoin polling without
    # resubmitting — they simply count against the budget while in flight.
    deadline = time.monotonic() + max_wait
    failed: dict[str, str] = {}
    budget = enqueued_budget
    logger.info(
        "Stage %s: %d chunk(s) to release under a %s-token enqueued budget",
        stage, state["n_chunks"], f"{budget:,}",
    )
    while True:
        state = load_state(run_dir, stage)
        assert state is not None
        in_flight_tokens = sum(
            chunk_tokens(key)
            for key, entry in iter_chunks(state)
            if entry["batch_id"] is not None
            and entry["fetched_at"] is None
            and key not in failed
        )
        # Release as many un-submitted chunks as the remaining budget allows.
        # A chunk larger than the whole budget goes out alone, once nothing else
        # is in flight, so an oversized chunk cannot deadlock the stage.
        for key, entry in iter_chunks(state):
            if entry["fetched_at"] is not None or entry["batch_id"] is not None:
                continue
            need = chunk_tokens(key)
            if in_flight_tokens and in_flight_tokens + need > budget:
                continue
            if _submit_one(key, entry):
                in_flight_tokens += need
        state = load_state(run_dir, stage)
        assert state is not None
        pending = [
            (key, entry)
            for key, entry in iter_chunks(state)
            if entry["fetched_at"] is None
            and key not in failed
            and entry["batch_id"] is not None
        ]
        unsubmitted = [
            key
            for key, entry in iter_chunks(state)
            if entry["fetched_at"] is None
            and key not in failed
            and entry["batch_id"] is None
        ]
        if not pending and not unsubmitted:
            break
        for key, entry in pending:
            status = batch_client.poll_batch(entry["batch_id"], client=client)
            update_chunk(
                run_dir, stage, key,
                last_polled_at=_utc_iso(), last_status=status.status,
            )
            if status.is_completed:
                # Completeness gate (Data Validation Team brief 2026-07-28,
                # item 1; disposition (a)): buffer the whole result stream and
                # reconcile the fetched custom_ids one-to-one against the chunk
                # plan BEFORE the persistence callback runs or fetched_at is
                # written. The callback commits per result (e.g. Stage 5 writes
                # one extract file + ledger row each), so a batch that is
                # missing, duplicating, empty, or returning unexpected ids must
                # never reach it — otherwise a partial batch persists silently
                # and the chunk is marked done. Response provenance (T1) is
                # collected in the same pass; recorded only on a clean match.
                models: set[str] = set()
                fingerprints: set[str] = set()
                fetched: list[BatchResult] = []
                for result in batch_client.fetch_results(
                    entry["batch_id"], client=client, status=status
                ):
                    if result.response_model:
                        models.add(result.response_model)
                    if result.system_fingerprint:
                        fingerprints.add(result.system_fingerprint)
                    fetched.append(result)
                planned = entry["custom_ids"]
                observed = [r.custom_id for r in fetched]
                problems = _reconcile_custom_ids(planned, observed)
                if problems:
                    record_path = _write_reconcile_record(
                        run_dir, stage, key,
                        batch_id=entry["batch_id"],
                        planned=planned, observed=observed, problems=problems,
                    )
                    raise RuntimeError(
                        f"Stage {stage} chunk {key}: batch {entry['batch_id']} "
                        f"results do not reconcile one-to-one against the chunk "
                        f"plan — {_reconcile_detail(problems, empty=not observed)}. "
                        f"Refusing to persist the batch or mark the chunk "
                        f"fetched/done; it stays active (re-run rejoins the same "
                        f"batch, no resubmit). Durable accounting naming the "
                        f"affected id(s): {record_path}. State file: "
                        f"{state_path(run_dir, stage)}."
                    )
                process_chunk_results(iter(fetched))
                update_chunk(
                    run_dir, stage, key,
                    fetched_at=_utc_iso(),
                    response_models=sorted(models),
                    system_fingerprints=sorted(fingerprints),
                )
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
            if entry["fetched_at"] is None
            and key not in failed
            and entry["batch_id"] is not None
        ]
        waiting = [
            key
            for key, entry in iter_chunks(state)
            if entry["fetched_at"] is None
            and key not in failed
            and entry["batch_id"] is None
        ]
        if not in_flight and not waiting:
            break
        if time.monotonic() >= deadline:
            detail = ", ".join(
                f"chunk {key} (batch {state['chunks'][key]['batch_id']}, "
                f"last status {state['chunks'][key]['last_status']})"
                for key in in_flight
            )
            held = (
                f" {len(waiting)} further chunk(s) were still held behind the "
                f"{budget:,}-token enqueued budget and were never submitted."
                if waiting
                else ""
            )
            raise RuntimeError(
                f"Stage {stage}: timed out after {max_wait}s with {detail or 'no batch'} "
                f"still in flight.{held} The batch(es) have NOT ended — an "
                f"in-progress batch is healthy; do not cancel it. Re-run the same "
                f"command to rejoin polling without re-submitting. State file: "
                f"{state_path(run_dir, stage)}."
            )
        # Only sleep when something is genuinely in flight. If chunks are merely
        # waiting on budget and none is in flight, the loop above will release
        # one immediately on the next pass rather than idling a poll interval.
        if in_flight:
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
    "abandon_chunk_batch",
    "assert_chunked_state",
    "done_path",
    "done_dir",
    "is_done",
    "iter_chunks",
    "load_state",
    "mark_done",
    "reconcile_dir",
    "reconcile_path",
    "run_chunked_stage",
    "state_dir",
    "state_path",
    "update_chunk",
    "write_active_chunked",
]
