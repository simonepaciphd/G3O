"""Per-request scrape telemetry ledger (politeness audit, 2026-07-27).

A flat, append-only JSONL at ``runs/<run_id>/_scrape_telemetry.jsonl`` recording
one record per actual outbound network request Stage 4 makes: a
millisecond-precision UTC timestamp, the target hostname, the URL, the
institution/stage context, and a per-request id.

This is the ledger a per-host politeness audit (``scrape_host_delay_seconds``,
enforced in-memory by :class:`g3o.scrape.politeness.HostThrottle`) is verified
against after the fact. ``HostThrottle`` only ever compares against
``time.monotonic()`` and discards each timestamp once the wait is computed —
nothing was previously written to disk, so a run's actual per-host request
spacing could not be reconstructed post hoc. This module exists to close that
gap; it does not change throttling behavior.

Recorded only for real network attempts (see call sites in
``g3o.scrape.fetcher``): a fetcher-cache hit or a robots-disallowed skip is not
a request and must not be logged, or the ledger would overstate actual outbound
traffic.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

LEDGER_NAME = "_scrape_telemetry.jsonl"

# Stage-4 concurrency: record() is called from worker threads. A single lock
# serializes the file append, mirroring g3o.common.attrition.
_lock = threading.RLock()


def ledger_path(run_dir: Path) -> Path:
    return run_dir / LEDGER_NAME


def _utc_iso_ms() -> str:
    """Millisecond-precision UTC timestamp.

    Second-precision (as used by ``g3o.common.attrition``) is too coarse for a
    politeness audit gated at a 1.0s floor: two requests 1.02s apart can land
    in the same or adjacent whole second depending on where they fall, which
    would make a real pass look like a spurious sub-second violation.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def hostname(url: str) -> str:
    return urlsplit(url).netloc


def record(
    run_dir: Path,
    *,
    institution_id: str,
    stage: str,
    url: str,
) -> None:
    """Append one request-telemetry record for a real outbound fetch.

    Call exactly once per actual network request (not per URL considered) —
    see ``g3o.scrape.fetcher`` for the call sites right before each
    network-touching branch (``_download`` and each ``render_url`` fallback).
    """
    run_dir = Path(run_dir)
    rec: dict[str, Any] = {
        "ts": _utc_iso_ms(),
        "request_id": uuid.uuid4().hex,
        "institution_id": institution_id,
        "stage": stage,
        "hostname": hostname(url),
        "url": url,
    }
    with _lock:
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(ledger_path(run_dir), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


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
    """No-op placeholder for test-isolation symmetry with other ledgers.

    Unlike ``g3o.common.attrition``, this ledger has no in-memory dedup cache
    to reset — every call is a distinct request and is always appended.
    """


__all__ = ["LEDGER_NAME", "ledger_path", "record", "read_records", "hostname"]
