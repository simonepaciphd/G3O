"""Per-attempt Stage 4 scrape telemetry ledger (concurrent Stage 4, review F14b).

A flat, append-only JSONL at ``runs/<run_id>/_scrape_telemetry.jsonl`` recording
**one record per scrape attempt regardless of outcome** — success, robots skip,
fetch failure, or per-run cache hit. This is the telemetry floor the concurrent
Stage 4 runner writes so every ``(institution, url)`` the runner touched is
accounted for even when work fans out across a thread pool.

This is deliberately a *separate* ledger from ``_attrition.jsonl``. The attrition
ledger is a drops/degrades side-table consumed by ``g3o.report.health`` as its
``top_drop_reasons`` / ``attrition_top_reasons`` breakdown; writing success rows
into it would swamp and corrupt that breakdown and touches a sign-off-gated
schema. Successes and skips belong here; the attrition ledger keeps recording
``robots_disallowed`` / ``scrape_failed`` exactly as before (a scrape drop is
recorded in *both* — attrition for the health report, telemetry for the
per-attempt floor).

Thread-safe (the runner records from worker threads): a module-level lock guards
the dedup-set check/add and the file append so no attempt's record is lost or
interleaved under concurrency.

Idempotence (resume): records are deduplicated on the stable key
``(institution_id, url, outcome)`` — mirroring ``g3o.common.attrition``. A stage
that re-runs on resume re-emits ``skipped_cached`` for URLs already on disk; the
dedup guard makes the second write a no-op so the ledger never double-counts.
The per-record ``detail`` and any ``**extra`` fields are outside the dedup key.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_NAME = "_scrape_telemetry.jsonl"

# Stable outcome codes. One of these is written for every scrape attempt.
OUTCOME_SUCCEEDED = "succeeded"
OUTCOME_ROBOTS_DISALLOWED = "robots_disallowed"
OUTCOME_SCRAPE_FAILED = "scrape_failed"
OUTCOME_SKIPPED_CACHED = "skipped_cached"

# Per-run dedup cache: str(run_dir) -> set of (institution_id, url, outcome) keys
# already on disk. Lazily seeded from the existing file on first touch so the
# guard survives a process restart (resume). Guarded by ``_lock``.
_seen: dict[str, set[tuple[str, str, str]]] = {}
_lock = threading.Lock()


def ledger_path(run_dir: Path) -> Path:
    return run_dir / LEDGER_NAME


def _dedup_key(institution_id: str, url: str, outcome: str) -> tuple[str, str, str]:
    return (institution_id, url, outcome)


def _load_seen_locked(run_dir: Path) -> set[tuple[str, str, str]]:
    """Return the dedup set for ``run_dir``; seed from disk on first touch.

    Caller must hold ``_lock``.
    """
    key = str(run_dir)
    cached = _seen.get(key)
    if cached is not None:
        return cached
    seen: set[tuple[str, str, str]] = set()
    path = ledger_path(run_dir)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen.add(
                _dedup_key(
                    rec.get("institution_id", ""),
                    rec.get("url", ""),
                    rec.get("outcome", ""),
                )
            )
    _seen[key] = seen
    return seen


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(
    run_dir: Path,
    *,
    institution_id: str,
    url: str,
    outcome: str,
    detail: str | None = None,
    **extra: Any,
) -> bool:
    """Append one scrape-attempt telemetry record; return True if written.

    Returns False if the ``(institution_id, url, outcome)`` key was already on
    disk (resume dedup). ``outcome`` must be one of the ``OUTCOME_*`` codes; it
    participates in the dedup key. ``detail`` and ``**extra`` (e.g.
    ``content_type``, ``http_status``, ``elapsed_ms``) carry variable telemetry
    and do not.

    Thread-safe: the dedup check/add and the append run under a module lock, so
    concurrent worker threads never lose or interleave a record.
    """
    run_dir = Path(run_dir)
    key = _dedup_key(institution_id, url, outcome)
    rec: dict[str, Any] = {
        "ts": _utc_iso(),
        "institution_id": institution_id,
        "stage": "scrape",
        "url": url,
        "outcome": outcome,
    }
    if detail is not None:
        rec["detail"] = detail
    rec.update(extra)
    with _lock:
        seen = _load_seen_locked(run_dir)
        if key in seen:
            return False
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(ledger_path(run_dir), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        seen.add(key)
    return True


def ensure_ledger(run_dir: Path) -> Path:
    """Create an empty ledger file if absent so its presence is guaranteed.

    An empty file means "this run reached the telemetry-aware scrape code and
    attempted nothing", a different signal than a missing file. Idempotent;
    seeds the dedup cache for the run.
    """
    run_dir = Path(run_dir)
    path = ledger_path(run_dir)
    with _lock:
        if not path.exists():
            run_dir.mkdir(parents=True, exist_ok=True)
            path.touch()
        _load_seen_locked(run_dir)
    return path


def read_records(run_dir: Path) -> list[dict[str, Any]]:
    """Read all telemetry records (test/inspection helper). Empty if absent."""
    path = ledger_path(Path(run_dir))
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _reset_cache() -> None:
    """Clear the dedup cache (test isolation only)."""
    with _lock:
        _seen.clear()


__all__ = [
    "LEDGER_NAME",
    "OUTCOME_ROBOTS_DISALLOWED",
    "OUTCOME_SCRAPE_FAILED",
    "OUTCOME_SKIPPED_CACHED",
    "OUTCOME_SUCCEEDED",
    "ensure_ledger",
    "ledger_path",
    "read_records",
    "record",
]
