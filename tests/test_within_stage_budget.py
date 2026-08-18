"""Tests for within-stage budget checking (Gap 1).

Tests that budget is checked after each chunk completes, not just after each stage.
This prevents a single large stage from spending significantly more than the
remaining budget before the check triggers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from g3o.common.cost_monitor import CostMonitor


def test_accumulate_chunk_usage_tracks_tokens():
    """accumulate_chunk_usage correctly accumulates token counts."""
    monitor = CostMonitor(budget_usd=10.0)
    
    monitor.accumulate_chunk_usage("extract", {
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "cached_tokens": 500,
    })
    
    assert "extract" in monitor._partial_stage_usage
    usage = monitor._partial_stage_usage["extract"]
    assert usage["prompt_tokens"] == 1000
    assert usage["completion_tokens"] == 200
    assert usage["cached_tokens"] == 500


def test_accumulate_chunk_usage_accumulates_across_chunks():
    """accumulate_chunk_usage accumulates across multiple chunks."""
    monitor = CostMonitor(budget_usd=10.0)
    
    monitor.accumulate_chunk_usage("extract", {
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "cached_tokens": 500,
    })
    monitor.accumulate_chunk_usage("extract", {
        "prompt_tokens": 1500,
        "completion_tokens": 300,
        "cached_tokens": 700,
    })
    
    usage = monitor._partial_stage_usage["extract"]
    assert usage["prompt_tokens"] == 2500
    assert usage["completion_tokens"] == 500
    assert usage["cached_tokens"] == 1200


def test_check_budget_with_partial_passes_when_within_budget():
    """check_budget_with_partial returns True when within budget."""
    monitor = CostMonitor(budget_usd=10.0)
    
    # Small usage that should pass
    monitor.accumulate_chunk_usage("extract", {
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "cached_tokens": 500,
    })
    
    assert monitor.check_budget_with_partial("extract") is True


def test_check_budget_with_partial_fails_when_over_budget():
    """check_budget_with_partial returns False when over budget."""
    monitor = CostMonitor(budget_usd=0.0001)  # Very low budget
    
    # Large usage that should exceed budget
    monitor.accumulate_chunk_usage("extract", {
        "prompt_tokens": 10000000,  # 10M tokens
        "completion_tokens": 1000000,
        "cached_tokens": 0,
    })
    
    assert monitor.check_budget_with_partial("extract") is False


def test_check_budget_with_partial_passes_when_no_budget():
    """check_budget_with_partial returns True when budget is None."""
    monitor = CostMonitor(budget_usd=None)
    
    monitor.accumulate_chunk_usage("extract", {
        "prompt_tokens": 1000000000,  # Huge usage
        "completion_tokens": 100000000,
        "cached_tokens": 0,
    })
    
    assert monitor.check_budget_with_partial("extract") is True


def test_check_budget_with_partial_includes_recorded_stages():
    """check_budget_with_partial includes already-recorded stage costs."""
    monitor = CostMonitor(budget_usd=1.0)
    
    # Record a stage that uses most of the budget
    run_dir = Path("/tmp/test-run")
    state_dir = run_dir / "_state" / ".done"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_data = {
        "stage": "classify_official_site",
        "n_jobs": 10,
        "n_chunks": 1,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 20000000,  # Uses ~$0.50
                    "completion_tokens": 2000000,
                    "total_tokens": 22000000,
                    "cached_tokens": 0,
                }
            }
        }
    }
    (state_dir / "classify_official_site.json").write_text(json.dumps(state_data))
    monitor.record_stage(run_dir, "classify_official_site")
    
    # Now add partial usage for extract stage
    monitor.accumulate_chunk_usage("extract", {
        "prompt_tokens": 10000000,  # Uses ~$0.25
        "completion_tokens": 1000000,
        "cached_tokens": 0,
    })
    
    # Should fail because combined spend exceeds budget
    assert monitor.check_budget_with_partial("extract") is False


def test_callback_pattern_in_run_chunked_stage(tmp_path):
    """Test that cost_check_callback parameter is accepted by run_chunked_stage."""
    import inspect

    from g3o.common.run_state import run_chunked_stage

    # This test verifies the signature accepts the callback parameter
    # A full integration test would require mocking the batch client
    # For now, we just verify the parameter is in the signature
    sig = inspect.signature(run_chunked_stage)
    assert "cost_check_callback" in sig.parameters


def test_callback_raises_nothing_when_within_budget():
    """Simulated callback (raise-based pattern) does not raise when within budget."""
    from g3o.common.cost_monitor import BudgetExceededError
    monitor = CostMonitor(budget_usd=10.0)
    
    def callback(stage: str, chunk_usage: dict) -> None:
        monitor.accumulate_chunk_usage(stage, chunk_usage)
        if not monitor.check_budget_with_partial(stage):
            raise BudgetExceededError(
                spent=monitor.running_total_usd, budget=monitor.budget_usd, stage=stage
            )
    
    # Small usage should not raise
    callback("extract", {
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "cached_tokens": 500,
    })
    # If we got here without raising, the test passed


def test_callback_raises_when_over_budget():
    """Simulated callback (raise-based pattern) raises BudgetExceededError when over budget."""
    from g3o.common.cost_monitor import BudgetExceededError
    monitor = CostMonitor(budget_usd=0.0001)  # Very low budget
    
    def callback(stage: str, chunk_usage: dict) -> None:
        monitor.accumulate_chunk_usage(stage, chunk_usage)
        if not monitor.check_budget_with_partial(stage):
            raise BudgetExceededError(
                spent=monitor.running_total_usd, budget=monitor.budget_usd, stage=stage
            )
    
    # Large usage should raise BudgetExceededError
    with pytest.raises(BudgetExceededError):
        callback("extract", {
            "prompt_tokens": 10000000,
            "completion_tokens": 1000000,
            "cached_tokens": 0,
        })


def test_callback_stops_submissions_integration(tmp_path, monkeypatch):
    """Integration test: callback raising BudgetExceededError stops new submissions.
    
    The exception propagates past mark_done, so no .done marker is written,
    leaving un-submitted chunks in the active state file as a truncation signal.
    """
    from datetime import datetime, timezone

    from g3o.common import batch_client
    from g3o.common.batch_client import BatchHandle, BatchJob, BatchResult, BatchStatus
    from g3o.common.cost_monitor import BudgetExceededError
    from g3o.common.run_state import run_chunked_stage
    
    # Mock batch_client functions
    submitted_chunks = []
    
    def mock_submit_batch(jobs, **kwargs):
        chunk_id = jobs[0].custom_id
        submitted_chunks.append(chunk_id)
        return BatchHandle(
            batch_id=f"batch-{chunk_id}",
            input_file_id=f"file-{chunk_id}",
            submitted_at=datetime.now(timezone.utc),
            n_jobs=len(jobs)
        )
    
    def mock_poll_batch(batch_id, **kwargs):
        # All batches complete immediately
        return BatchStatus(
            batch_id=batch_id,
            status="completed",
            request_counts={"total": 1, "completed": 1, "failed": 0},
            output_file_id=f"output-{batch_id}",
            error_file_id=None
        )
    
    def mock_fetch_results(batch_id, **kwargs):
        # Extract the job id from the batch_id (format: "batch-J0")
        job_id = batch_id.replace("batch-", "")
        # Return a result for each job in the batch
        return iter([
            BatchResult(
                custom_id=job_id,
                success=True,
                response={"body": {"usage": {"prompt_tokens": 100, "completion_tokens": 50}}},
                error=None,
            )
        ])
    
    def mock_find_batches_by_metadata(metadata, **kwargs):
        return []  # No existing batches
    
    monkeypatch.setattr(batch_client, "submit_batch", mock_submit_batch)
    monkeypatch.setattr(batch_client, "poll_batch", mock_poll_batch)
    monkeypatch.setattr(batch_client, "fetch_results", mock_fetch_results)
    monkeypatch.setattr(batch_client, "find_batches_by_metadata", mock_find_batches_by_metadata)
    monkeypatch.setattr(batch_client, "split_jobs_into_chunks", 
                       lambda jobs, **kwargs: [[jobs[0]], [jobs[1]], [jobs[2]]])
    monkeypatch.setattr(batch_client, "job_token_estimates", 
                       lambda jobs, **kwargs: {j.custom_id: 1000 for j in jobs})
    monkeypatch.setattr(batch_client, "enqueued_token_budget", lambda: 1000)
    
    # Create 3 jobs
    jobs = [
        BatchJob(custom_id="J0", messages=[{"role": "user", "content": "test"}]),
        BatchJob(custom_id="J1", messages=[{"role": "user", "content": "test"}]),
        BatchJob(custom_id="J2", messages=[{"role": "user", "content": "test"}]),
    ]
    
    # Callback raises BudgetExceededError immediately after first chunk completes
    callback_calls = []
    def callback(stage, chunk_usage):
        callback_calls.append((stage, chunk_usage))
        raise BudgetExceededError(spent=10.0, budget=5.0, stage=stage)
    
    # Run the stage - exception propagates past mark_done
    with pytest.raises(BudgetExceededError) as exc_info:
        run_chunked_stage(
            tmp_path, "extract", jobs,
            run_id="test-run", model="gpt-5-nano",
            poll_interval=0, max_wait=10,
            process_chunk_results=lambda results: None,
            cost_check_callback=callback,
            enqueued_budget=1000,
        )
    
    # Verify only 1 chunk was submitted (exception halted before submitting more)
    assert len(submitted_chunks) == 1
    assert submitted_chunks == ["J0"]
    
    # Verify exception details
    assert exc_info.value.stage == "extract"
    assert exc_info.value.spent == 10.0
    assert exc_info.value.budget == 5.0
    
    # Verify stage was NOT marked done (exception propagated past mark_done)
    assert not (tmp_path / "_state" / ".done" / "extract.json").exists()
    
    # Verify active state file remains (un-submitted chunks preserved as truncation signal)
    assert (tmp_path / "_state" / "extract.json").exists()
