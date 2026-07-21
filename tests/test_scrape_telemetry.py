"""Tests for ``g3o.common.scrape_telemetry`` — the per-attempt Stage 4 scrape
telemetry ledger (review F14b).

Covers the requirement-5 contract: one record per attempt regardless of outcome,
resume-safe dedup on ``(institution_id, url, outcome)``, and thread-safe writes.
"""

from __future__ import annotations

import threading
from pathlib import Path

from g3o.common import scrape_telemetry as st


def _fresh(tmp_path: Path) -> Path:
    st._reset_cache()
    return tmp_path / "run"


def test_record_writes_one_per_attempt(tmp_path: Path):
    run_dir = _fresh(tmp_path)
    st.record(run_dir, institution_id="I1", url="https://x/a", outcome=st.OUTCOME_SUCCEEDED)
    st.record(run_dir, institution_id="I1", url="https://x/b", outcome=st.OUTCOME_SCRAPE_FAILED)
    recs = st.read_records(run_dir)
    assert len(recs) == 2
    assert {r["outcome"] for r in recs} == {st.OUTCOME_SUCCEEDED, st.OUTCOME_SCRAPE_FAILED}
    assert all(r["stage"] == "scrape" for r in recs)


def test_record_dedups_on_inst_url_outcome(tmp_path: Path):
    run_dir = _fresh(tmp_path)
    assert st.record(run_dir, institution_id="I1", url="https://x/a", outcome=st.OUTCOME_SUCCEEDED) is True
    # Same key with a varying detail is deduped (detail is outside the key).
    assert st.record(
        run_dir, institution_id="I1", url="https://x/a",
        outcome=st.OUTCOME_SUCCEEDED, detail="ignored",
    ) is False
    assert len(st.read_records(run_dir)) == 1


def test_extra_fields_recorded_but_not_in_dedup_key(tmp_path: Path):
    run_dir = _fresh(tmp_path)
    st.record(
        run_dir, institution_id="I1", url="https://x/a",
        outcome=st.OUTCOME_SUCCEEDED, content_type="html", http_status=200,
    )
    rec = st.read_records(run_dir)[0]
    assert rec["content_type"] == "html"
    assert rec["http_status"] == 200


def test_dedup_survives_process_restart_via_disk_seed(tmp_path: Path):
    run_dir = _fresh(tmp_path)
    st.record(run_dir, institution_id="I1", url="https://x/a", outcome=st.OUTCOME_SKIPPED_CACHED)
    # Simulate a restart: drop the in-memory cache; the ledger reseeds from disk.
    st._reset_cache()
    assert st.record(run_dir, institution_id="I1", url="https://x/a", outcome=st.OUTCOME_SKIPPED_CACHED) is False
    assert len(st.read_records(run_dir)) == 1


def test_ensure_ledger_creates_empty_file(tmp_path: Path):
    run_dir = _fresh(tmp_path)
    path = st.ensure_ledger(run_dir)
    assert path.exists()
    assert st.read_records(run_dir) == []


def test_read_records_absent_is_empty(tmp_path: Path):
    assert st.read_records(tmp_path / "nope") == []


def test_record_thread_safe_no_lost_writes(tmp_path: Path):
    """Concurrent records for distinct keys all land exactly once (no loss)."""
    run_dir = _fresh(tmp_path)
    start = threading.Barrier(16)

    def worker(i: int) -> None:
        start.wait()
        st.record(
            run_dir, institution_id=f"I{i}", url=f"https://x/{i}",
            outcome=st.OUTCOME_SUCCEEDED,
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    recs = st.read_records(run_dir)
    assert len(recs) == 16
    assert {r["institution_id"] for r in recs} == {f"I{i}" for i in range(16)}
