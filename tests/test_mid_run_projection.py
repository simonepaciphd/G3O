"""Tests for mid-run projection updates (Gap 2).

Tests that the pipeline can abort mid-run based on projected total spend,
not just actual spend. If actual spend so far scales to a total that exceeds
budget × safety_factor, the run should abort before the next stage starts.
"""

from __future__ import annotations

import json
from pathlib import Path

from g3o.common.cost_monitor import CostMonitor, ProjectedBudgetExceededError


def test_check_projection_returns_within_projection_when_no_estimates():
    """check_projection returns (True, 0.0, inf) when no preflight estimates."""
    monitor = CostMonitor(budget_usd=10.0)
    monitor.preflight_stage_estimates = None
    
    within, projected, threshold = monitor.check_projection()
    
    assert within is True
    assert projected == 0.0
    assert threshold == float("inf")


def test_check_projection_returns_within_projection_when_no_budget():
    """check_projection returns (True, 0.0, inf) when budget is None."""
    monitor = CostMonitor(budget_usd=None)
    monitor.preflight_stage_estimates = {
        "classify_official_site": 0.01,
        "classify_triage": 0.01,
        "extract": 0.05,
        "validate": 0.01,
    }
    
    within, projected, threshold = monitor.check_projection()
    
    assert within is True
    assert projected == 0.0
    assert threshold == float("inf")


def test_check_projection_scales_remaining_by_actual_ratio():
    """check_projection scales remaining estimates by actual/estimated ratio."""
    monitor = CostMonitor(budget_usd=1.0)
    monitor.preflight_stage_estimates = {
        "classify_official_site": 0.1,  # Completed stage
        "classify_triage": 0.1,  # Completed stage
        "extract": 0.5,  # Remaining stage
        "validate": 0.1,  # Remaining stage
    }
    
    # Record two completed stages with higher actual spend than estimated
    run_dir = Path("/tmp/test-run")
    state_dir = run_dir / "_state" / ".done"
    state_dir.mkdir(parents=True, exist_ok=True)
    
    # Stage 1: estimated 0.1, actual ~0.2 (2x ratio)
    state_data1 = {
        "stage": "classify_official_site",
        "n_jobs": 10,
        "n_chunks": 1,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 8000000,  # ~$0.20
                    "completion_tokens": 1000000,
                    "total_tokens": 9000000,
                    "cached_tokens": 0,
                }
            }
        }
    }
    (state_dir / "classify_official_site.json").write_text(json.dumps(state_data1))
    monitor.record_stage(run_dir, "classify_official_site")
    
    # Stage 2: estimated 0.1, actual ~0.2 (2x ratio)
    state_data2 = {
        "stage": "classify_triage",
        "n_jobs": 10,
        "n_chunks": 1,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 8000000,  # ~$0.20
                    "completion_tokens": 1000000,
                    "total_tokens": 9000000,
                    "cached_tokens": 0,
                }
            }
        }
    }
    (state_dir / "classify_triage.json").write_text(json.dumps(state_data2))
    monitor.record_stage(run_dir, "classify_triage")
    
    # Actual spend: ~$0.40, estimated so far: 0.2, ratio: 2.0
    # Remaining estimate: 0.6, projected remaining: 1.2
    # Projected total: 0.4 + 1.2 = 1.6
    # Threshold: 1.0 * 1.2 = 1.2
    # Should fail: 1.6 > 1.2
    
    within, projected, threshold = monitor.check_projection(safety_factor=1.2)
    
    assert within is False
    assert projected > 1.2  # Should exceed threshold
    assert threshold == 1.2


def test_check_projection_passes_when_actual_cheaper_than_estimated():
    """check_projection passes when actual spend is cheaper than estimated."""
    monitor = CostMonitor(budget_usd=1.0)
    monitor.preflight_stage_estimates = {
        "classify_official_site": 0.2,  # Completed stage
        "extract": 0.5,  # Remaining stage
    }
    
    run_dir = Path("/tmp/test-run")
    state_dir = run_dir / "_state" / ".done"
    state_dir.mkdir(parents=True, exist_ok=True)
    
    # Stage 1: estimated 0.2, actual ~0.1 (0.5x ratio)
    state_data = {
        "stage": "classify_official_site",
        "n_jobs": 10,
        "n_chunks": 1,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 2000000,  # ~$0.05
                    "completion_tokens": 250000,
                    "total_tokens": 2250000,
                    "cached_tokens": 0,
                }
            }
        }
    }
    (state_dir / "classify_official_site.json").write_text(json.dumps(state_data))
    monitor.record_stage(run_dir, "classify_official_site")
    
    # Actual spend: ~$0.05, estimated so far: 0.2, ratio: 0.25
    # Remaining estimate: 0.5, projected remaining: 0.125
    # Projected total: 0.05 + 0.125 = 0.175
    # Threshold: 1.0 * 1.2 = 1.2
    # Should pass: 0.175 < 1.2
    
    within, projected, threshold = monitor.check_projection(safety_factor=1.2)
    
    assert within is True
    assert projected < 1.2


def test_projected_budget_exceeded_error_has_correct_attributes():
    """ProjectedBudgetExceededError has projected_total and safety_factor attributes."""
    exc = ProjectedBudgetExceededError(
        spent=0.5,
        budget=1.0,
        stage="extract",
        projected_total=1.5,
        safety_factor=1.2,
    )
    
    assert exc.spent == 0.5
    assert exc.budget == 1.0
    assert exc.stage == "extract"
    assert exc.projected_total == 1.5
    assert exc.safety_factor == 1.2
    assert "Projected budget exceeded" in str(exc)


def test_projection_safety_factor_configurable():
    """projection_safety_factor is configurable in PresweepConfig."""
    from pathlib import Path

    from g3o.run.presweep.config import PresweepConfig
    
    config = PresweepConfig(
        run_id="test",
        runs_dir=Path("/tmp"),
        master_csv=Path("/tmp/master.csv"),
        projection_safety_factor=1.5,
    )
    
    assert config.projection_safety_factor == 1.5


def test_projection_safety_factor_validates_minimum():
    """projection_safety_factor must be >= 1.0."""
    from pathlib import Path

    import pytest

    from g3o.run.presweep.config import PresweepConfig
    
    with pytest.raises(ValueError, match="must be >= 1.0"):
        PresweepConfig(
            run_id="test",
            runs_dir=Path("/tmp"),
            master_csv=Path("/tmp/master.csv"),
            projection_safety_factor=0.9,
        )


def test_projection_safety_factor_rejects_nan():
    """projection_safety_factor rejects NaN values."""
    import math
    from pathlib import Path

    import pytest

    from g3o.run.presweep.config import PresweepConfig
    
    with pytest.raises(ValueError, match="must be a finite number"):
        PresweepConfig(
            run_id="test",
            runs_dir=Path("/tmp"),
            master_csv=Path("/tmp/master.csv"),
            projection_safety_factor=math.nan,
        )


def test_projection_safety_factor_rejects_inf():
    """projection_safety_factor rejects Inf values."""
    import math
    from pathlib import Path

    import pytest

    from g3o.run.presweep.config import PresweepConfig
    
    with pytest.raises(ValueError, match="must be a finite number"):
        PresweepConfig(
            run_id="test",
            runs_dir=Path("/tmp"),
            master_csv=Path("/tmp/master.csv"),
            projection_safety_factor=math.inf,
        )


def test_preflight_includes_stage_estimates(tmp_path):
    """run_preflight includes per-stage cost estimates in output."""
    from unittest.mock import patch

    from g3o.common import config as g3o_config
    from g3o.run.preflight import run_preflight
    from g3o.run.presweep.config import PresweepConfig
    
    # Create minimal master CSV
    master_csv = tmp_path / "master.csv"
    master_csv.write_text(
        "institution_id,name,country,government_level,institution_type,url\n"
        "inst-0001,Test Inst,TestCountry,national,university,https://example.edu\n"
    )
    
    config = PresweepConfig(
        run_id="test",
        runs_dir=tmp_path / "runs",
        master_csv=master_csv,
        sample_size=1,
    )
    
    with patch.object(g3o_config, "SERPER_API_KEY", "test-key"):
        with patch.object(g3o_config, "OPENAI_API_KEY", "sk-test"):
            summary = run_preflight(config, cost_ceiling_usd=10.0)
    
    # Check that stage_estimates is present
    assert "cost_preview" in summary
    assert "stage_estimates" in summary["cost_preview"]
    
    stage_estimates = summary["cost_preview"]["stage_estimates"]
    assert "classify_official_site" in stage_estimates
    assert "classify_triage" in stage_estimates
    assert "extract" in stage_estimates
    assert "validate" in stage_estimates
    
    # All estimates should be positive
    for _stage, estimate in stage_estimates.items():
        assert estimate > 0
