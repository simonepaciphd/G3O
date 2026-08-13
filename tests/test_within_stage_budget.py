"""Tests for within-stage budget checking (Gap 1).

Tests that budget is checked after each chunk completes, not just after each stage.
This prevents a single large stage from spending significantly more than the
remaining budget before the check triggers.
"""

from __future__ import annotations

import json
from pathlib import Path

from g3o.common.cost_monitor import BudgetExceededError, CostMonitor


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
    from g3o.common.run_state import run_chunked_stage
    from unittest.mock import MagicMock
    
    # This test verifies the signature accepts the callback parameter
    # A full integration test would require mocking the batch client
    # For now, we just verify the parameter is in the signature
    import inspect
    sig = inspect.signature(run_chunked_stage)
    assert "cost_check_callback" in sig.parameters


def test_callback_returns_true_when_within_budget():
    """Simulated callback should return True when within budget."""
    monitor = CostMonitor(budget_usd=10.0)
    
    def callback(stage: str, chunk_usage: dict) -> bool:
        monitor.accumulate_chunk_usage(stage, chunk_usage)
        return monitor.check_budget_with_partial(stage)
    
    # Small usage should return True
    result = callback("extract", {
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "cached_tokens": 500,
    })
    assert result is True


def test_callback_returns_false_when_over_budget():
    """Simulated callback should return False when over budget."""
    monitor = CostMonitor(budget_usd=0.0001)  # Very low budget
    
    def callback(stage: str, chunk_usage: dict) -> bool:
        monitor.accumulate_chunk_usage(stage, chunk_usage)
        return monitor.check_budget_with_partial(stage)
    
    # Large usage should return False
    result = callback("extract", {
        "prompt_tokens": 10000000,
        "completion_tokens": 1000000,
        "cached_tokens": 0,
    })
    assert result is False
