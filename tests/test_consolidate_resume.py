"""Stage 6 cached-replay batch-id reporting (report §12).

``run_consolidate``'s ``is_done`` short-circuit used to hardcode
``batch_ids: None`` on a resumed/replayed run, even though ``mark_done``
preserves the full chunk plan — including each chunk's adopted ``batch_id``
— when it moves the active state file into ``.done/``. A replay should
report the same batch ids a fresh completion would.
"""

from __future__ import annotations

from g3o.common.run_state import mark_done, update_chunk, write_active_chunked
from g3o.validate.consolidate import run_consolidate


def test_cached_replay_reports_adopted_batch_ids(tmp_path):
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)

    write_active_chunked(
        run_dir, "validate",
        run_id="r1", model="gpt-5-nano",
        chunk_custom_ids=[["INST-0001", "INST-0002"]],
    )
    update_chunk(run_dir, "validate", 1, batch_id="batch-validate-1", adopted=True)
    mark_done(run_dir, "validate")

    summary = run_consolidate(run_dir, institution_ids=["INST-0001", "INST-0002"])

    assert summary["skipped"] is True
    assert summary["batch_ids"] == ["batch-validate-1"]


def test_cached_replay_multi_chunk_reports_batch_ids_in_chunk_order(tmp_path):
    run_dir = tmp_path / "runs" / "r2"
    run_dir.mkdir(parents=True)

    write_active_chunked(
        run_dir, "validate",
        run_id="r2", model="gpt-5-nano",
        chunk_custom_ids=[["INST-0001"], ["INST-0002"]],
    )
    update_chunk(run_dir, "validate", 1, batch_id="batch-validate-1", adopted=True)
    update_chunk(run_dir, "validate", 2, batch_id="batch-validate-2", adopted=True)
    mark_done(run_dir, "validate")

    summary = run_consolidate(run_dir, institution_ids=["INST-0001", "INST-0002"])

    assert summary["skipped"] is True
    assert summary["batch_ids"] == ["batch-validate-1", "batch-validate-2"]


def test_cached_replay_no_batch_marker_still_reports_none(tmp_path):
    run_dir = tmp_path / "runs" / "r3"
    run_dir.mkdir(parents=True)

    mark_done(run_dir, "validate", no_batch=True)

    summary = run_consolidate(run_dir, institution_ids=[])

    assert summary["skipped"] is True
    assert summary["batch_ids"] is None
