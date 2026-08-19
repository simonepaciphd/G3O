"""Shared helpers for building orchestrator-visible run trees in tests.

The orchestrator reads four things off a run: the manifest, the event log,
``_state/``, and its own ``_orchestrator/`` records. Hand-building those in every
test would spread the on-disk shapes across a dozen files, so they are built
here — and built through the same writers production uses wherever one exists
(``run_state.mark_done`` for the markers, ``tests._layout.write_manifest`` for the
``layout_version`` gate).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.common import run_state
from g3o.run.orchestrate.status import (
    EVENTS_FILENAME,
    orchestrator_dir,
    write_json_atomic,
)
from tests._layout import write_manifest

__all__ = [
    "append_events",
    "event",
    "make_run",
    "write_final_csvs",
    "write_submit_record",
]


def event(seq: int, name: str, *, stage: str | None = None, ts: str | None = None, **payload: Any) -> dict[str, Any]:
    """One event in the §4.3 envelope shape the published fixture pins."""
    record: dict[str, Any] = {
        "ts": ts or f"2026-08-13T10:{seq:02d}:00Z",
        "run_id": "r20260813T100000Z-aaaa",
        "session_id": "test-session",
        "git_sha": "0" * 40,
        "seq": seq,
        "event": name,
    }
    if stage is not None:
        record["stage"] = stage
    record["payload"] = payload
    return record


def append_events(run_dir: Path, events: list[dict[str, Any]]) -> Path:
    path = run_dir / EVENTS_FILENAME
    with open(path, "a", encoding="utf-8") as handle:
        for record in events:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def write_submit_record(run_dir: Path, **fields: Any) -> Path:
    path = orchestrator_dir(run_dir) / "submit.json"
    write_json_atomic(path, {"leg": "submit", **fields})
    return path


def write_final_csvs(
    run_dir: Path,
    *,
    institutions: list[str] | None = None,
    uid_column: bool = False,
) -> Path:
    """Stage-7 outputs, enough for the archive preconditions and publish-verify.

    ``uid_column`` writes ``institution_uid`` alongside ``institution_id``, which
    is what the publish leg needs to be able to query the API at all — the split
    the leg refuses to guess across.
    """
    final = run_dir / "final"
    final.mkdir(parents=True, exist_ok=True)
    ids = institutions or ["INST-0000001", "INST-0000002"]
    header = "institution_id,institution_name"
    rows = [f"{i},Ministry {n}" for n, i in enumerate(ids)]
    if uid_column:
        header = "institution_uid," + header
        rows = [
            f"G3O-I-{n + 1:08d},{row}" for n, row in enumerate(rows)
        ]
    body = header + "\n" + "\n".join(rows) + "\n"
    for name in (
        "g3o_activities_v1.csv",
        "g3o_activity_sources_v1.csv",
        "g3o_institution_summary_v1.csv",
    ):
        (final / name).write_text(body, encoding="utf-8")
    return final


def make_run(
    runs_dir: Path,
    run_id: str = "r20260813T100000Z-aaaa",
    *,
    manifest: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    stages_done: list[str] | None = None,
    no_manifest: bool = False,
) -> Path:
    """A run directory shaped the way the pipeline leaves one. Returns its path."""
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if not no_manifest:
        payload: dict[str, Any] = {
            "run_id": run_id,
            "run_started_at": "2026-08-13T10:00:00Z",
            "session_id": "test-session",
            "operator": "tester",
            "code": {"git_sha": "0" * 40, "git_dirty": False},
            "config_hash": "c" * 64,
            "config": {"dry_run": False, "stop_after": "validate", **(config or {})},
        }
        payload.update(manifest or {})
        write_manifest(run_dir, payload)
    if events:
        append_events(run_dir, events)
    for stage in stages_done or []:
        run_state.mark_done(run_dir, stage, no_batch=True)
    return run_dir
