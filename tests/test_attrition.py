"""Attrition ledger thread-safety (Stage-4 concurrency, 2026-07).

``attrition.record`` is called from worker threads once Stage 4 runs
institutions concurrently. These tests pin the two properties the module lock
guarantees under that concurrency: the dedup guard holds (a repeated key is
written exactly once, never double-counted by a check-then-act race), and
distinct keys are all written without torn JSONL lines (serialized appends).
"""

from __future__ import annotations

import threading
from pathlib import Path

from g3o.common import attrition


def test_record_dedups_under_concurrency(tmp_path: Path) -> None:
    """Many threads recording the SAME key → exactly one ledger line."""
    attrition._reset_cache()

    def rec() -> None:
        for _ in range(50):
            attrition.record(
                tmp_path, institution_id="I1", stage="scrape",
                reason="scrape_failed", url="https://x.gov/a", detail="d",
            )

    threads = [threading.Thread(target=rec) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    recs = attrition.read_records(tmp_path)  # json.loads per line: torn line → raise
    matching = [
        r for r in recs
        if r["reason"] == "scrape_failed" and r.get("url") == "https://x.gov/a"
    ]
    assert len(matching) == 1
    attrition._reset_cache()


def test_record_distinct_keys_all_written_under_concurrency(tmp_path: Path) -> None:
    """Distinct keys recorded concurrently → every one is written, no line torn
    (read_records parses each line, so a torn append would raise here)."""
    attrition._reset_cache()

    def rec(i: int) -> None:
        attrition.record(
            tmp_path, institution_id=f"I{i}", stage="scrape",
            reason="scrape_failed", url=f"https://x.gov/{i}",
        )

    threads = [threading.Thread(target=rec, args=(i,)) for i in range(60)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    recs = attrition.read_records(tmp_path)
    assert len({r["institution_id"] for r in recs}) == 60
    attrition._reset_cache()
