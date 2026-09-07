"""PR #65 review: repro for F1, and verification of the proposed F2-safe fix.

Test 1 (F1 repro) — the shipped ``return False`` contract was a no-op: all
chunks still submitted.  Now pinned as a regression test: ``return False``
stops further submission and leaves the stage incomplete.

Test 2/3 (proposed fix, option a) — a callback that *raises* needs no change
to ``run_chunked_stage`` and preserves the measurement invariant: no further
chunks submit, ``mark_done`` is never reached, and the un-submitted chunks
stay in the active state file so ``outcomes.py`` reads the institutions
behind them as PROCESSING_FAILED rather than NO_EVIDENCE_FOUND.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from g3o.common.batch_client import BatchJob
from g3o.common.cost_monitor import BudgetExceededError
from g3o.common.run_state import is_done, run_chunked_stage, state_path
from tests.test_run_state import _install_stub


def _jobs_forcing_one_chunk_each(n: int = 3) -> list[BatchJob]:
    # ~400 bytes each; a ~110-token enqueued budget admits exactly one per chunk.
    return [
        BatchJob(custom_id=f"J{i}", messages=[{"role": "user", "content": "x" * 380}])
        for i in range(n)
    ]


def _kwargs(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        run_id="run-1",
        model="gpt-5-nano",
        poll_interval=0,
        max_wait=10,
        process_chunk_results=lambda results: list(results),
        enqueued_budget=110,
    )
    base.update(over)
    return base


def test_f1_return_false_stops_submission(tmp_path: Path, monkeypatch):
    """REGRESSION PIN — ``return False`` halts further chunk submission."""
    submits, _ = _install_stub(monkeypatch, run_dir=tmp_path, statuses={})

    def _callback(stage: str, chunk_usage: dict[str, int]) -> bool:
        return False  # "over budget: stop submitting new chunks"

    run_chunked_stage(
        tmp_path, "extract", _jobs_forcing_one_chunk_each(),
        **_kwargs(cost_check_callback=_callback),
    )
    assert [s["custom_ids"] for s in submits] == [["J0"]]


def test_raising_callback_stops_submission_and_leaves_no_done_marker(
    tmp_path: Path, monkeypatch
):
    """PROPOSED FIX — the callback raises; run_state needs no change."""
    submits, _ = _install_stub(monkeypatch, run_dir=tmp_path, statuses={})

    def _callback(stage: str, chunk_usage: dict[str, int]) -> bool:
        raise BudgetExceededError(spent=9.99, budget=1.00, stage=stage)

    with pytest.raises(BudgetExceededError):
        run_chunked_stage(
            tmp_path, "extract", _jobs_forcing_one_chunk_each(),
            **_kwargs(cost_check_callback=_callback),
        )

    assert [s["custom_ids"] for s in submits] == [["J0"]], (
        "no chunk may be submitted after the budget stop"
    )
    assert not is_done(tmp_path, "extract"), (
        "the stage must NOT be marked done — the missing marker is what stops "
        "outcomes.py reading the un-processed institutions as NO_EVIDENCE_FOUND"
    )


def test_unsubmitted_chunks_survive_in_the_active_state_file(
    tmp_path: Path, monkeypatch
):
    """The truncation signal must be legible on disk, not just in the exception."""
    _install_stub(monkeypatch, run_dir=tmp_path, statuses={})

    def _callback(stage: str, chunk_usage: dict[str, int]) -> bool:
        raise BudgetExceededError(spent=9.99, budget=1.00, stage=stage)

    with pytest.raises(BudgetExceededError):
        run_chunked_stage(
            tmp_path, "extract", _jobs_forcing_one_chunk_each(),
            **_kwargs(cost_check_callback=_callback),
        )

    active = state_path(tmp_path, "extract")
    assert active.exists(), "the active state file must remain for resume"
    chunks = json.loads(active.read_text(encoding="utf-8"))["chunks"]
    unsubmitted = [k for k, e in chunks.items() if e["batch_id"] is None]
    fetched = [k for k, e in chunks.items() if e["fetched_at"] is not None]
    assert len(fetched) == 1 and len(unsubmitted) == 2, (
        f"expected 1 fetched / 2 never-submitted; got {fetched} / {unsubmitted}"
    )
