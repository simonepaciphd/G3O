"""Minimal per-run attrition ledger (Session F.2, 2026-06-10, review F4/F15).

A flat, append-only JSONL at ``runs/<run_id>/_attrition.jsonl`` recording one
record per (institution, stage, reason) wherever the pipeline drops or degrades
an institution or page: Serper request failures (review F1), scrape failures,
empty/near-empty page drops (review F5), Stage 2/3/5 parse failures (review
F15), and page-text truncations (review F3). Run-scoped and underscore-prefixed
like ``_state/`` (researcher-confirmed path, 2026-06-10).

This is the F4/F15 *accounting floor* only, and the ledger remains a side-table
rather than part of the public CSV contract.

What was Decision D2 (Phase 2) — how never-reached institutions are represented
in the output CSVs — was ruled by the PI on 2026-08-25 and is now asserted in
``docs/data_dictionary.md`` under "Grain": such an institution has **no row in
any of the three Stage-7 CSVs**, and is carried downstream by
``institution_report.csv``'s ``final_status`` instead. That makes this ledger the
explanation of *where* coverage was lost, not the record of *whether* it was —
which is the role the data dictionary points readers here for.

Idempotence (resume): records are deduplicated on the stable key
``(institution_id, stage, reason, url)``. A stage that re-runs on resume (e.g.
``build_extract_jobs`` rebuilding the job list for chunk reconciliation) re-emits
the same truncation/empty-drop records; the dedup guard makes the second write a
no-op so the ledger never double-counts. The per-record ``detail`` (free text,
e.g. an exception string) is intentionally outside the dedup key so a varying
message cannot defeat deduplication.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_NAME = "_attrition.jsonl"

# Per-run dedup cache: str(run_dir) -> set of (institution_id, stage, reason, url)
# keys already on disk. Lazily seeded from the existing file on first touch so
# the guard survives a process restart (resume).
_seen: dict[str, set[tuple[str, str, str, str]]] = {}

# Stage-4 concurrency thread-safety (2026-07): record() is called from worker
# threads. Without a lock two races corrupt the ledger — the lazy _load_seen
# seeding (two threads both build and assign _seen[key]) and record()'s
# check-then-act (two threads both pass `key not in seen`, both append →
# double-count). A single re-entrant module lock serializes the seed, the dedup
# check, the file append, and the seen.add so each record is atomic. Attrition
# writes are rare next to network I/O, so serializing them is free in practice.
_lock = threading.RLock()


def ledger_path(run_dir: Path) -> Path:
    return run_dir / LEDGER_NAME


def _dedup_key(institution_id: str, stage: str, reason: str, url: str | None) -> tuple[str, str, str, str]:
    return (institution_id, stage, reason, url or "")


def _load_seen(run_dir: Path) -> set[tuple[str, str, str, str]]:
    key = str(run_dir)
    with _lock:
        cached = _seen.get(key)
        if cached is not None:
            return cached
        seen: set[tuple[str, str, str, str]] = set()
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
                        rec.get("stage", ""),
                        rec.get("reason", ""),
                        rec.get("url"),
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
    stage: str,
    reason: str,
    url: str | None = None,
    detail: str | None = None,
    **extra: Any,
) -> bool:
    """Append one attrition record; return True if written, False if deduped.

    ``reason`` must be a stable short code (e.g. ``"serper_request_failed"``,
    ``"empty_page_dropped"``, ``"page_text_truncated"``, ``"parse_failed"``) —
    it participates in the dedup key. ``detail`` carries variable text (an
    exception string, the original length, etc.) and does not.

    Append-only: a single JSONL line written under ``open(..., "a")`` is atomic
    enough for this accounting side-table (it is never read back to drive resume
    correctness). The dedup guard prevents resume double-counting.
    """
    run_dir = Path(run_dir)
    key = _dedup_key(institution_id, stage, reason, url)
    # Hold the module lock across the whole check-then-act: dedup check, file
    # append, and seen.add must be atomic so concurrent workers cannot both pass
    # the `key not in seen` guard and double-write (see _lock).
    with _lock:
        seen = _load_seen(run_dir)
        if key in seen:
            return False
        rec: dict[str, Any] = {
            "ts": _utc_iso(),
            "institution_id": institution_id,
            "stage": stage,
            "reason": reason,
        }
        if url is not None:
            rec["url"] = url
        if detail is not None:
            rec["detail"] = detail
        rec.update(extra)
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(ledger_path(run_dir), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        seen.add(key)
        return True


def ensure_ledger(run_dir: Path) -> Path:
    """Create an empty ledger file if absent so its presence is guaranteed.

    A live run always has an attrition ledger; an empty file means "this run
    reached the ledger-aware code and dropped/degraded nothing", which is a
    different (and more trustworthy) signal than a missing file from pre-ledger
    code. Idempotent; seeds the dedup cache for the run.
    """
    run_dir = Path(run_dir)
    path = ledger_path(run_dir)
    if not path.exists():
        run_dir.mkdir(parents=True, exist_ok=True)
        path.touch()
    _load_seen(run_dir)
    return path


def read_records(run_dir: Path) -> list[dict[str, Any]]:
    """Read all ledger records (test/inspection helper). Empty list if absent."""
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


__all__ = ["LEDGER_NAME", "ledger_path", "record", "read_records", "ensure_ledger"]
