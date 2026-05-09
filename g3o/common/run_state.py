"""Per-stage state files for crash-recovery and ``--resume`` (Session E, 2026-05-09).

Layout under ``runs/<run_id>/_state/``::

    {stage}.json        — active state (batch in-flight or terminal-but-not-fetched)
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
    Stages 2/3/5/6 share :func:`wait_for_terminal_with_state`; Stages
    1a/1b/4 (deterministic) write a no-batch ``.done`` marker at end.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.common.batch_client import BatchStatus, poll_batch

logger = logging.getLogger(__name__)


_STATE_DIR = "_state"
_DONE_DIR = ".done"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def write_active(
    run_dir: Path,
    stage: str,
    *,
    batch_id: str,
    model: str,
    n_jobs: int,
    custom_ids: Iterable[str],
    bypass_count: int | None = None,
) -> Path:
    """Persist a fresh active state file at submission time (Q1=a, Q2 schema).

    Called between ``submit_batch`` and the first ``poll_batch`` so a process
    crash mid-poll does not lose the batch handle. Atomic on POSIX via
    write-then-rename; Windows is best-effort (single ``write_text``).
    """
    state_dir(run_dir).mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "stage": stage,
        "batch_id": batch_id,
        "model": model,
        "n_jobs": n_jobs,
        "custom_ids": sorted(set(custom_ids)),
        "submitted_at": _utc_iso(),
        "last_polled_at": None,
        "last_status": None,
    }
    if bypass_count is not None:
        payload["bypass_count"] = bypass_count
    p = state_path(run_dir, stage)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def update_polled(run_dir: Path, stage: str, *, status: str) -> None:
    """Refresh ``last_polled_at`` + ``last_status`` on each poll tick.

    No-op if the active state file has been moved away (e.g. by ``mark_done``)
    so the helper stays safe to call after stage completion.
    """
    p = state_path(run_dir, stage)
    if not p.exists():
        return
    payload = json.loads(p.read_text(encoding="utf-8"))
    payload["last_polled_at"] = _utc_iso()
    payload["last_status"] = status
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_done(run_dir: Path, stage: str, *, no_batch: bool = False) -> Path:
    """Move the active state file to ``.done/{stage}.json`` (Q2=iii).

    For deterministic stages (1a, 1b, scrape) and the all-bypassed Stage 2
    case, no active state file exists; pass ``no_batch=True`` to write a
    minimal completion marker. Idempotent: re-marking an already-done stage
    is a no-op.
    """
    src = state_path(run_dir, stage)
    dst = done_path(run_dir, stage)
    done_dir(run_dir).mkdir(parents=True, exist_ok=True)
    if dst.exists() and not src.exists():
        return dst
    if src.exists():
        payload = json.loads(src.read_text(encoding="utf-8"))
        payload["fetched_at"] = _utc_iso()
        dst.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        src.unlink()
        return dst
    payload = {"stage": stage, "fetched_at": _utc_iso(), "no_batch": no_batch}
    dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dst


def wait_for_terminal_with_state(
    batch_id: str,
    *,
    poll_interval: int,
    max_wait: int,
    run_dir: Path | None = None,
    stage: str | None = None,
) -> BatchStatus:
    """Poll a batch to terminal state, refreshing the active state file each tick.

    Single shared polling primitive across Stages 2/3/5/6 (Q8=ii convergence).
    Replaces ``presweep._wait_for_terminal``, ``presweep._run_extract`` inline
    poll loop, and ``consolidate.run_consolidate`` inline poll loop.

    When ``run_dir`` and ``stage`` are both supplied, the helper refreshes
    ``last_polled_at`` + ``last_status`` on each tick (Q2 schema). When either
    is None, it polls without state-file side effects (used by the standalone
    classifier CLI subcommands that operate outside a run directory).
    """
    deadline = time.monotonic() + max_wait
    status = poll_batch(batch_id)
    if run_dir is not None and stage is not None:
        update_polled(run_dir, stage, status=status.status)
    while not status.is_terminal:
        if time.monotonic() >= deadline:
            return status
        time.sleep(poll_interval)
        status = poll_batch(batch_id)
        if run_dir is not None and stage is not None:
            update_polled(run_dir, stage, status=status.status)
    return status


__all__ = [
    "done_path",
    "done_dir",
    "is_done",
    "load_state",
    "mark_done",
    "state_dir",
    "state_path",
    "update_polled",
    "wait_for_terminal_with_state",
    "write_active",
]
