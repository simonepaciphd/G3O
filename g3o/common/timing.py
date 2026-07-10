"""Per-institution, per-stage timing instrumentation (single reusable mechanism).

Every stage runner calls into this module to time its work; results are
persisted per institution to ``runs/<run_id>/<institution_id>/timing.json``.
Follows :mod:`g3o.common.run_state`'s single-owner-module convention (this
module owns ``timing.json``) and its atomic-write discipline (temp-file +
``os.replace``).

Two distinct timing shapes exist because of a real architectural constraint,
not an implementation gap:

- Deterministic stages (``discovery_general``, ``discovery_site_restricted``,
  ``scrape``) loop synchronously per institution, so a true wall-clock window
  per institution exists. Use :func:`stage_timer` —
  ``timing_type="per_institution"``.
- LLM/Batch stages (``classify_official_site``, ``classify_triage``,
  ``extract``, ``validate``) submit many institutions' jobs in one
  size-capped Batch API chunk (:func:`g3o.common.run_state.run_chunked_stage`);
  there is no true per-institution wall-clock inside a chunk. Use
  :func:`llm_stage_timer`, which derives each chunk's real submit→fetch
  window from the chunk state that :mod:`run_state` already records
  (``submitted_at`` / ``fetched_at``) rather than re-instrumenting, and
  records that shared window identically for every institution in the
  chunk — ``timing_type="shared_chunk"``.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from g3o.common.run_state import done_path, state_path

TimingType = Literal["per_institution", "shared_chunk"]

TIMING_FILENAME = "timing.json"


def timing_path(run_dir: Path, institution_id: str) -> Path:
    return run_dir / institution_id / TIMING_FILENAME


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_to_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _iso_diff_seconds(start: str, end: str) -> float:
    return max(0.0, (_iso_to_dt(end) - _iso_to_dt(start)).total_seconds())


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def record_stage_timing(
    run_dir: Path,
    institution_id: str,
    stage: str,
    *,
    start_time: str,
    end_time: str,
    duration_seconds: float,
    status: str,
    timing_type: TimingType,
    error: str | None = None,
) -> Path:
    """Merge one stage's timing entry into ``<institution_id>/timing.json``.

    Read-modify-write, atomic via temp-file + ``os.replace``. Safe to call
    more than once for the same (institution, stage) — the latest call wins,
    and ``total_duration_seconds`` is recomputed as the sum of every recorded
    stage's ``duration_seconds`` after each write.
    """
    path = timing_path(run_dir, institution_id)
    payload: dict[str, Any] = {"institution_id": institution_id, "stages": {}}
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("stages", {})
    entry: dict[str, Any] = {
        "start_time": start_time,
        "end_time": end_time,
        "duration_seconds": round(duration_seconds, 6),
        "status": status,
        "timing_type": timing_type,
    }
    if error is not None:
        entry["error"] = error
    payload["institution_id"] = institution_id
    payload["stages"][stage] = entry
    payload["total_duration_seconds"] = round(
        sum(e["duration_seconds"] for e in payload["stages"].values()), 6
    )
    _write_json_atomic(path, payload)
    return path


@contextmanager
def stage_timer(
    run_dir: Path,
    institution_id: str,
    stage: str,
) -> Iterator[None]:
    """Time one (institution, stage) unit of synchronous, per-institution work.

    On an unhandled exception inside the block, records ``status="failed"``
    with the exception's ``str()`` as ``error`` and re-raises; the caller's
    own error handling (e.g. ``attrition.record``) is unaffected — this only
    adds a timing side-record.
    """
    start_wall = time.monotonic()
    start_time = _utc_iso()
    try:
        yield
    except BaseException as exc:
        record_stage_timing(
            run_dir, institution_id, stage,
            start_time=start_time, end_time=_utc_iso(),
            duration_seconds=time.monotonic() - start_wall,
            status="failed", timing_type="per_institution", error=str(exc),
        )
        raise
    else:
        record_stage_timing(
            run_dir, institution_id, stage,
            start_time=start_time, end_time=_utc_iso(),
            duration_seconds=time.monotonic() - start_wall,
            status="completed", timing_type="per_institution",
        )


def _load_stage_chunks(run_dir: Path, stage: str) -> dict[str, Any] | None:
    """Read the chunk map from ``.done/{stage}.json`` (preferred) or the
    active ``_state/{stage}.json`` (mid-flight / failed). ``None`` if neither
    exists or the payload carries no chunk data (e.g. a no-batch marker)."""
    for path in (done_path(run_dir, stage), state_path(run_dir, stage)):
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            chunks = payload.get("chunks")
            if isinstance(chunks, dict) and chunks:
                return chunks
    return None


@contextmanager
def llm_stage_timer(
    run_dir: Path,
    stage: str,
    custom_id_to_institution: dict[str, str],
) -> Iterator[None]:
    """Wrap one stage runner's call into ``run_chunked_stage`` for an LLM stage.

    Derives each chunk's true submit→fetch window from the chunk state
    :mod:`g3o.common.run_state` already records (``submitted_at`` /
    ``fetched_at``) rather than re-timing, and records that window identically
    for every institution whose ``custom_id`` fell in that chunk
    (``timing_type="shared_chunk"``). No-op (records nothing) when the stage
    had no batch to submit (e.g. every institution bypassed) — there is no
    LLM wall-clock to attribute in that case.

    On failure, best-effort records ``status="failed"`` for every institution
    in every chunk that never reached ``fetched_at``, using ``submitted_at``
    (or the wrapper's own start) through "now" as the window, then re-raises.
    """
    start_wall_time = _utc_iso()
    try:
        yield
    except BaseException as exc:
        end_time = _utc_iso()
        chunks = _load_stage_chunks(run_dir, stage) or {}
        for entry in chunks.values():
            if entry.get("fetched_at") is not None:
                continue  # already succeeded before the failure; leave it alone
            chunk_start = entry.get("submitted_at") or start_wall_time
            inst_ids = {
                custom_id_to_institution.get(cid, cid)
                for cid in entry.get("custom_ids", [])
            }
            for inst_id in inst_ids:
                record_stage_timing(
                    run_dir, inst_id, stage,
                    start_time=chunk_start, end_time=end_time,
                    duration_seconds=_iso_diff_seconds(chunk_start, end_time),
                    status="failed", timing_type="shared_chunk", error=str(exc),
                )
        raise
    else:
        chunks = _load_stage_chunks(run_dir, stage)
        if not chunks:
            return
        for entry in chunks.values():
            chunk_start = entry.get("submitted_at") or start_wall_time
            chunk_end = entry.get("fetched_at") or _utc_iso()
            duration = _iso_diff_seconds(chunk_start, chunk_end)
            inst_ids = {
                custom_id_to_institution.get(cid, cid)
                for cid in entry.get("custom_ids", [])
            }
            for inst_id in inst_ids:
                record_stage_timing(
                    run_dir, inst_id, stage,
                    start_time=chunk_start, end_time=chunk_end,
                    duration_seconds=duration,
                    status="completed", timing_type="shared_chunk",
                )


def read_timing(run_dir: Path, institution_id: str) -> dict[str, Any] | None:
    """Read one institution's ``timing.json``, or ``None`` if absent."""
    path = timing_path(run_dir, institution_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "TIMING_FILENAME",
    "TimingType",
    "llm_stage_timer",
    "read_timing",
    "record_stage_timing",
    "stage_timer",
    "timing_path",
]
