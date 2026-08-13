"""Continuous cost monitoring tests.

Tests the runtime cost tracking and budget enforcement that aborts mid-run
if actual spend exceeds the configured budget. Complements the pre-flight
cost gate tests in test_cost_protection.py.

Coverage:
  - BatchResult.usage property extracts token counts correctly
  - CostMonitor.record_stage reads state files and computes cost
  - CostMonitor accumulates running totals across stages
  - CostMonitor.check_budget enforces limits correctly
  - CostMonitor.cost_report generates well-formed reports
  - Orchestrator raises BudgetExceededError when budget exceeded
  - CLI catches BudgetExceededError and exits with code 3
  - Cost report is persisted even on abort
  - Cached tokens are priced at the cached rate (not full input rate)
  - State files with missing usage are handled gracefully (backward compat)

These tests ensure the continuous cost monitor correctly tracks actual API
spend and aborts before budget overrun, complementing the pre-flight projection.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from g3o.common.batch_client import BatchResult
from g3o.common.cost_monitor import BudgetExceededError, CostMonitor, StageCost


# ---------------------------------------------------------------------------
# Test 1: BatchResult.usage property extracts token counts correctly
# ---------------------------------------------------------------------------


def test_batch_result_usage_property():
    """BatchResult.usage correctly extracts token counts from a mock response."""
    response = {
        "body": {
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 200,
                "total_tokens": 1200,
                "prompt_tokens_details": {
                    "cached_tokens": 500
                }
            }
        }
    }
    result = BatchResult(
        custom_id="test-job",
        success=True,
        response=response,
        error=None,
        status_code=200,
    )
    
    usage = result.usage
    assert usage is not None
    assert usage["prompt_tokens"] == 1000
    assert usage["completion_tokens"] == 200
    assert usage["total_tokens"] == 1200
    assert usage["cached_tokens"] == 500


# ---------------------------------------------------------------------------
# Test 2: BatchResult.usage returns None on failure
# ---------------------------------------------------------------------------


def test_batch_result_usage_none_on_failure():
    """BatchResult.usage returns None for failed/errored results."""
    result = BatchResult(
        custom_id="test-job",
        success=False,
        response=None,
        error={"message": "API error"},
        status_code=500,
    )
    
    assert result.usage is None


# ---------------------------------------------------------------------------
# Test 3: BatchResult.usage returns None when usage field is missing
# ---------------------------------------------------------------------------


def test_batch_result_usage_none_on_missing():
    """BatchResult.usage returns None when response body has no usage field."""
    response = {
        "body": {
            "choices": [{"message": {"content": "test"}}]
        }
    }
    result = BatchResult(
        custom_id="test-job",
        success=True,
        response=response,
        error=None,
        status_code=200,
    )
    
    assert result.usage is None


# ---------------------------------------------------------------------------
# Test 4: CostMonitor.record_stage reads state file and computes cost
# ---------------------------------------------------------------------------


def test_stage_cost_from_state_file(tmp_path):
    """CostMonitor.record_stage reads a .done/<stage>.json with usage data and computes correct cost."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state" / ".done"
    state_dir.mkdir(parents=True)
    
    # Write a mock state file with usage data
    state_data = {
        "stage": "extract",
        "n_jobs": 100,
        "n_chunks": 2,
        "chunks": {
            "1": {
                "custom_ids": ["job-1", "job-2"],
                "usage": {
                    "prompt_tokens": 50000,
                    "completion_tokens": 5000,
                    "total_tokens": 55000,
                    "cached_tokens": 30000,
                }
            },
            "2": {
                "custom_ids": ["job-3", "job-4"],
                "usage": {
                    "prompt_tokens": 60000,
                    "completion_tokens": 6000,
                    "total_tokens": 66000,
                    "cached_tokens": 40000,
                }
            }
        }
    }
    state_file = state_dir / "extract.json"
    state_file.write_text(json.dumps(state_data), encoding="utf-8")
    
    monitor = CostMonitor(budget_usd=10.0)
    stage_cost = monitor.record_stage(run_dir, "extract")
    
    assert stage_cost.stage == "extract"
    assert stage_cost.prompt_tokens == 110000  # 50k + 60k
    assert stage_cost.completion_tokens == 11000  # 5k + 6k
    assert stage_cost.cached_tokens == 70000  # 30k + 40k
    assert stage_cost.n_jobs == 100
    assert stage_cost.n_chunks == 2
    # Cost should be computed using the pricing from GPT5_NANO_PRICING
    assert stage_cost.total_usd > 0
    assert stage_cost.total_usd == stage_cost.input_usd + stage_cost.output_usd


# ---------------------------------------------------------------------------
# Test 5: CostMonitor handles missing usage gracefully (backward compat)
# ---------------------------------------------------------------------------


def test_stage_cost_missing_usage_treated_as_zero(tmp_path):
    """Backward compat: state file without usage field → 0 tokens."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state" / ".done"
    state_dir.mkdir(parents=True)
    
    # Write a state file without usage data (pre-existing run)
    state_data = {
        "stage": "extract",
        "n_jobs": 100,
        "n_chunks": 2,
        "chunks": {
            "1": {"custom_ids": ["job-1"]},
            "2": {"custom_ids": ["job-2"]},
        }
    }
    state_file = state_dir / "extract.json"
    state_file.write_text(json.dumps(state_data), encoding="utf-8")
    
    monitor = CostMonitor(budget_usd=10.0)
    stage_cost = monitor.record_stage(run_dir, "extract")
    
    assert stage_cost.prompt_tokens == 0
    assert stage_cost.completion_tokens == 0
    assert stage_cost.cached_tokens == 0
    assert stage_cost.total_usd == 0.0


# ---------------------------------------------------------------------------
# Test 6: CostMonitor accumulates running totals across stages
# ---------------------------------------------------------------------------


def test_running_total_accumulates(tmp_path):
    """After recording 3 stages, running_total_usd is the sum."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state" / ".done"
    state_dir.mkdir(parents=True)
    
    # Write state files for 3 stages
    for stage_name, tokens in [("stage2", 10000), ("stage3", 20000), ("stage5", 50000)]:
        state_data = {
            "stage": stage_name,
            "n_jobs": 10,
            "n_chunks": 1,
            "chunks": {
                "1": {
                    "custom_ids": ["job-1"],
                    "usage": {
                        "prompt_tokens": tokens,
                        "completion_tokens": tokens // 10,
                        "total_tokens": tokens + tokens // 10,
                        "cached_tokens": 0,
                    }
                }
            }
        }
        state_file = state_dir / f"{stage_name}.json"
        state_file.write_text(json.dumps(state_data), encoding="utf-8")
    
    monitor = CostMonitor(budget_usd=10.0)
    monitor.record_stage(run_dir, "stage2")
    total_after_stage2 = monitor.running_total_usd
    
    monitor.record_stage(run_dir, "stage3")
    total_after_stage3 = monitor.running_total_usd
    
    monitor.record_stage(run_dir, "stage5")
    total_after_stage5 = monitor.running_total_usd
    
    # Running total should accumulate
    assert total_after_stage2 > 0
    assert total_after_stage3 > total_after_stage2
    assert total_after_stage5 > total_after_stage3
    assert len(monitor.stages) == 3


# ---------------------------------------------------------------------------
# Test 7: CostMonitor.check_budget passes when under budget
# ---------------------------------------------------------------------------


def test_check_budget_passes_when_under(tmp_path):
    """Returns True when total < budget."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state" / ".done"
    state_dir.mkdir(parents=True)
    
    state_data = {
        "stage": "extract",
        "n_jobs": 10,
        "n_chunks": 1,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 100,
                    "total_tokens": 1100,
                    "cached_tokens": 0,
                }
            }
        }
    }
    state_file = state_dir / "extract.json"
    state_file.write_text(json.dumps(state_data), encoding="utf-8")
    
    monitor = CostMonitor(budget_usd=100.0)  # Very high budget
    monitor.record_stage(run_dir, "extract")
    
    assert monitor.check_budget() is True
    assert monitor.running_total_usd < monitor.budget_usd


# ---------------------------------------------------------------------------
# Test 8: CostMonitor.check_budget fails when over budget
# ---------------------------------------------------------------------------


def test_check_budget_fails_when_over(tmp_path):
    """Returns False when total > budget."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state" / ".done"
    state_dir.mkdir(parents=True)
    
    state_data = {
        "stage": "extract",
        "n_jobs": 1000,
        "n_chunks": 1,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 1000000,  # 1M tokens
                    "completion_tokens": 100000,
                    "total_tokens": 1100000,
                    "cached_tokens": 0,
                }
            }
        }
    }
    state_file = state_dir / "extract.json"
    state_file.write_text(json.dumps(state_data), encoding="utf-8")
    
    monitor = CostMonitor(budget_usd=0.01)  # Very low budget
    monitor.record_stage(run_dir, "extract")
    
    assert monitor.check_budget() is False
    assert monitor.running_total_usd > monitor.budget_usd


# ---------------------------------------------------------------------------
# Test 9: CostMonitor.check_budget passes when budget is None (no limit)
# ---------------------------------------------------------------------------


def test_check_budget_passes_when_none(tmp_path):
    """Returns True when budget is None (no limit)."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state" / ".done"
    state_dir.mkdir(parents=True)
    
    state_data = {
        "stage": "extract",
        "n_jobs": 1000,
        "n_chunks": 1,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 10000000,  # 10M tokens
                    "completion_tokens": 1000000,
                    "total_tokens": 11000000,
                    "cached_tokens": 0,
                }
            }
        }
    }
    state_file = state_dir / "extract.json"
    state_file.write_text(json.dumps(state_data), encoding="utf-8")
    
    monitor = CostMonitor(budget_usd=None)  # No budget limit
    monitor.record_stage(run_dir, "extract")
    
    assert monitor.check_budget() is True
    assert monitor.budget_usd is None


# ---------------------------------------------------------------------------
# Test 10: CostMonitor.cost_report generates well-formed report
# ---------------------------------------------------------------------------


def test_cost_report_structure(tmp_path):
    """cost_report() returns a complete, well-formed dict."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state" / ".done"
    state_dir.mkdir(parents=True)
    
    state_data = {
        "stage": "extract",
        "n_jobs": 100,
        "n_chunks": 2,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 50000,
                    "completion_tokens": 5000,
                    "total_tokens": 55000,
                    "cached_tokens": 30000,
                }
            }
        }
    }
    state_file = state_dir / "extract.json"
    state_file.write_text(json.dumps(state_data), encoding="utf-8")
    
    monitor = CostMonitor(budget_usd=10.0)
    monitor.record_stage(run_dir, "extract")
    
    report = monitor.cost_report()
    
    # Check top-level structure
    assert "budget_usd" in report
    assert "budget_exceeded" in report
    assert "stages" in report
    assert "total_prompt_tokens" in report
    assert "total_completion_tokens" in report
    assert "total_cached_tokens" in report
    assert "total_input_usd" in report
    assert "total_output_usd" in report
    assert "total_usd" in report
    assert "pricing" in report
    
    # Check stages structure
    assert len(report["stages"]) == 1
    stage = report["stages"][0]
    assert "stage" in stage
    assert "prompt_tokens" in stage
    assert "completion_tokens" in stage
    assert "cached_tokens" in stage
    assert "input_usd" in stage
    assert "output_usd" in stage
    assert "total_usd" in stage
    assert "n_jobs" in stage
    assert "n_chunks" in stage
    
    # Check pricing structure
    pricing = report["pricing"]
    assert "model" in pricing
    assert "batch_input_per_1m_usd" in pricing
    assert "batch_output_per_1m_usd" in pricing
    assert "batch_cached_input_per_1m_usd" in pricing
    assert "batch_line_is_estimate" in pricing
    
    # Check values
    assert report["budget_usd"] == 10.0
    assert report["budget_exceeded"] is False
    assert report["total_usd"] > 0


# ---------------------------------------------------------------------------
# Test 11: Orchestrator raises BudgetExceededError when budget exceeded
# ---------------------------------------------------------------------------


def test_orchestrator_aborts_on_budget_exceeded(tmp_path, monkeypatch):
    """Full integration: orchestrator raises BudgetExceededError when a stage pushes total over budget."""
    from g3o.common import config as g3o_config
    from g3o.run.presweep import PresweepConfig, run_presweep

    # Mock the stage runners to avoid actual API calls
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-openai")

    # Create a minimal master CSV
    master = tmp_path / "master.csv"
    master.write_text(
        "institution_id,name,country,government_level,institution_type,url\n"
        "inst-0001,Test Inst,TestCountry,national,university,https://example.edu\n",
        encoding="utf-8",
    )

    config = PresweepConfig(
        run_id="test-run",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=1,
        seed=22294,
        stratification="equal",
        discovery_languages=("en",),
        discovery_results_per_query=10,
        discovery_mode="chain",
        discovery_evidence_term="official",
        discovery_domain_quote_name=False,
        serper_autocorrect=False,
        dry_run=False,
        stop_after="classify_official_site",
        filter_mode="shadow",
        poll_interval=60,
        max_wait_per_stage=25 * 60 * 60,
        model="gpt-5-nano",
        max_workers=1,
        budget_usd=0.001,  # Very low budget
    )

    # Patch at the point of use in the orchestrator module (where it's imported)
    with patch("g3o.run.presweep.orchestrator._run_discovery_general") as mock_discovery:
        mock_discovery.return_value = {}

        with patch("g3o.run.presweep.orchestrator._run_classify_official_site") as mock_classify:
            mock_classify.return_value = {}

            # Mock the state file to have high usage
            state_dir = config.runs_dir / config.run_id / "_state" / ".done"
            state_dir.mkdir(parents=True, exist_ok=True)
            state_data = {
                "stage": "classify_official_site",
                "n_jobs": 1000,
                "n_chunks": 1,
                "chunks": {
                    "1": {
                        "custom_ids": ["job-1"],
                        "usage": {
                            "prompt_tokens": 1000000,
                            "completion_tokens": 100000,
                            "total_tokens": 1100000,
                            "cached_tokens": 0,
                        }
                    }
                }
            }
            state_file = state_dir / "classify_official_site.json"
            state_file.write_text(json.dumps(state_data), encoding="utf-8")

            # Should raise BudgetExceededError
            try:
                run_presweep(config)
                assert False, "Expected BudgetExceededError to be raised"
            except BudgetExceededError as exc:
                assert exc.stage == "classify_official_site"
                assert exc.spent > exc.budget
                assert exc.budget == 0.001


# ---------------------------------------------------------------------------
# Test 12: CLI exits with code 3 on BudgetExceededError
# ---------------------------------------------------------------------------


def test_cli_exits_3_on_budget_exceeded(tmp_path, monkeypatch, capsys):
    """CLI catches BudgetExceededError and exits with code 3."""
    from g3o import cli
    from g3o.common import config as g3o_config

    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-openai")
    monkeypatch.setattr(g3o_config, "BUDGET_LIMIT_USD", "1000.0")  # High so preflight passes

    master = tmp_path / "master.csv"
    master.write_text(
        "institution_id,name,country,government_level,institution_type,url\n"
        "inst-0001,Test Inst,TestCountry,national,university,https://example.edu\n",
        encoding="utf-8",
    )

    args = [
        "presweep",
        "--execute",
        "--run-id", "cli-budget-test",
        "--master-csv", str(master),
        "--sample-size", "1",
        "--cost-ceiling", "1000.0",  # High enough for preflight to pass
    ]

    # Mock run_presweep to raise BudgetExceededError (simulating mid-run abort)
    with patch("g3o.run.presweep.run_presweep") as mock_run:
        mock_run.side_effect = BudgetExceededError(
            spent=0.01, budget=0.001, stage="extract"
        )

        exit_code = cli.main(args)
        captured = capsys.readouterr()

    assert exit_code == 3
    assert "BUDGET EXCEEDED" in captured.err
    assert "Stage: extract" in captured.err
    assert "Actual spend so far: $0.0100" in captured.err
    assert "Budget limit:        $0.0010" in captured.err


# ---------------------------------------------------------------------------
# Test 13: Cost report is persisted even on abort
# ---------------------------------------------------------------------------


def test_cost_report_persisted_on_abort(tmp_path, monkeypatch):
    """_cost_report.json is written even when the run is aborted mid-stage."""
    from g3o.common import config as g3o_config
    from g3o.run.presweep import PresweepConfig, run_presweep

    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-openai")

    master = tmp_path / "master.csv"
    master.write_text(
        "institution_id,name,country,government_level,institution_type,url\n"
        "inst-0001,Test Inst,TestCountry,national,university,https://example.edu\n",
        encoding="utf-8",
    )

    config = PresweepConfig(
        run_id="test-run",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=1,
        seed=22294,
        stratification="equal",
        discovery_languages=("en",),
        discovery_results_per_query=10,
        discovery_mode="chain",
        discovery_evidence_term="official",
        discovery_domain_quote_name=False,
        serper_autocorrect=False,
        dry_run=False,
        stop_after="classify_official_site",
        filter_mode="shadow",
        poll_interval=60,
        max_wait_per_stage=25 * 60 * 60,
        model="gpt-5-nano",
        max_workers=1,
        budget_usd=0.001,
    )

    # Patch at the point of use in the orchestrator module (where it's imported)
    with patch("g3o.run.presweep.orchestrator._run_discovery_general") as mock_discovery:
        mock_discovery.return_value = {}

        with patch("g3o.run.presweep.orchestrator._run_classify_official_site") as mock_classify:
            mock_classify.return_value = {}

            # Mock state file with high usage
            state_dir = config.runs_dir / config.run_id / "_state" / ".done"
            state_dir.mkdir(parents=True, exist_ok=True)
            state_data = {
                "stage": "classify_official_site",
                "n_jobs": 1000,
                "n_chunks": 1,
                "chunks": {
                    "1": {
                        "custom_ids": ["job-1"],
                        "usage": {
                            "prompt_tokens": 1000000,
                            "completion_tokens": 100000,
                            "total_tokens": 1100000,
                            "cached_tokens": 0,
                        }
                    }
                }
            }
            state_file = state_dir / "classify_official_site.json"
            state_file.write_text(json.dumps(state_data), encoding="utf-8")

            # Should raise BudgetExceededError
            try:
                run_presweep(config)
            except BudgetExceededError:
                pass

            # Cost report should be persisted even on abort
            cost_report_path = config.runs_dir / config.run_id / "_cost_report.json"
            assert cost_report_path.exists()

            cost_report = json.loads(cost_report_path.read_text(encoding="utf-8"))
            assert cost_report["budget_exceeded"] is True
            assert cost_report["abort_stage"] == "classify_official_site"
            assert cost_report["budget_exceeded_stages"] == ["classify_official_site"]
            assert cost_report["total_usd"] > 0


# ---------------------------------------------------------------------------
# Test 14: Cached tokens are priced at the cached rate
# ---------------------------------------------------------------------------


def test_cached_tokens_get_lower_rate(tmp_path):
    """Cached tokens are priced at the cached rate, not the full input rate."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state" / ".done"
    state_dir.mkdir(parents=True)
    
    # Two state files: one with all cached, one with no cached
    state_cached = {
        "stage": "extract_cached",
        "n_jobs": 10,
        "n_chunks": 1,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 100000,
                    "completion_tokens": 10000,
                    "total_tokens": 110000,
                    "cached_tokens": 100000,  # All cached
                }
            }
        }
    }
    state_file = state_dir / "extract_cached.json"
    state_file.write_text(json.dumps(state_cached), encoding="utf-8")
    
    state_non_cached = {
        "stage": "extract_non_cached",
        "n_jobs": 10,
        "n_chunks": 1,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 100000,
                    "completion_tokens": 10000,
                    "total_tokens": 110000,
                    "cached_tokens": 0,  # None cached
                }
            }
        }
    }
    state_file = state_dir / "extract_non_cached.json"
    state_file.write_text(json.dumps(state_non_cached), encoding="utf-8")
    
    monitor = CostMonitor(budget_usd=100.0)
    cost_cached = monitor.record_stage(run_dir, "extract_cached")
    cost_non_cached = monitor.record_stage(run_dir, "extract_non_cached")
    
    # Cached should be cheaper than non-cached
    assert cost_cached.input_usd < cost_non_cached.input_usd
    # The ratio should be approximately the batch discount (0.5)
    # Cached rate is standard_cached * batch_discount = 0.005 * 0.5 = 0.0025
    # Non-cached rate is batch_input = 0.025
    # So cached should be ~10x cheaper (0.0025 / 0.025 = 0.1)
    ratio = cost_cached.input_usd / cost_non_cached.input_usd
    assert ratio < 0.2  # Cached should be significantly cheaper


# ---------------------------------------------------------------------------
# Test 15 (PR #17): --execute with --cost-ceiling flag exceeded
# ---------------------------------------------------------------------------


def test_cli_execute_with_cost_ceiling_flag_exceeded(tmp_path, monkeypatch, capsys):
    """CLI exits 3 when --execute is used with --cost-ceiling flag that is exceeded."""
    from g3o import cli
    from g3o.common import config as g3o_config

    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-openai")
    # No env var set - rely solely on CLI flag
    monkeypatch.setattr(g3o_config, "BUDGET_LIMIT_USD", None)

    master = tmp_path / "master.csv"
    master.write_text(
        "institution_id,name,country,government_level,institution_type,url\n"
        "inst-0001,Test Inst,TestCountry,national,university,https://example.edu\n",
        encoding="utf-8",
    )

    args = [
        "presweep",
        "--execute",
        "--run-id", "cli-cost-ceiling-test",
        "--master-csv", str(master),
        "--sample-size", "1",
        "--cost-ceiling", "0.0001",  # Very low ceiling to trigger abort
    ]

    # The preflight should run and compute a cost estimate, then abort because
    # the estimated cost exceeds the very low ceiling
    exit_code = cli.main(args)
    captured = capsys.readouterr()

    # Should exit with code 3 (budget abort)
    assert exit_code == 3
    assert "COST CIRCUIT BREAKER TRIGGERED" in captured.err


# ---------------------------------------------------------------------------
# Test 16 (PR #18): Cost report with vs_preflight_estimate
# ---------------------------------------------------------------------------


def test_cost_report_includes_vs_preflight_estimate(tmp_path, monkeypatch):
    """Orchestrator includes vs_preflight_estimate in cost report when preflight was run."""
    from g3o.common import config as g3o_config
    from g3o.run.presweep import PresweepConfig, run_presweep

    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-openai")

    master = tmp_path / "master.csv"
    master.write_text(
        "institution_id,name,country,government_level,institution_type,url\n"
        "inst-0001,Test Inst,TestCountry,national,university,https://example.edu\n",
        encoding="utf-8",
    )

    config = PresweepConfig(
        run_id="test-run",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=1,
        seed=22294,
        stratification="equal",
        discovery_languages=("en",),
        discovery_results_per_query=10,
        discovery_mode="chain",
        discovery_evidence_term="official",
        discovery_domain_quote_name=False,
        serper_autocorrect=False,
        dry_run=False,
        stop_after="classify_official_site",
        filter_mode="shadow",
        poll_interval=60,
        max_wait_per_stage=25 * 60 * 60,
        model="gpt-5-nano",
        max_workers=1,
        budget_usd=100.0,  # High budget so we don't abort
        preflight_estimate_usd=0.005,  # Simulate a preflight estimate
    )

    with patch("g3o.run.presweep.orchestrator._run_discovery_general") as mock_discovery:
        mock_discovery.return_value = {}

        with patch("g3o.run.presweep.orchestrator._run_classify_official_site") as mock_classify:
            mock_classify.return_value = {}

            # Mock state file with some usage
            state_dir = config.runs_dir / config.run_id / "_state" / ".done"
            state_dir.mkdir(parents=True, exist_ok=True)
            state_data = {
                "stage": "classify_official_site",
                "n_jobs": 10,
                "n_chunks": 1,
                "chunks": {
                    "1": {
                        "custom_ids": ["job-1"],
                        "usage": {
                            "prompt_tokens": 10000,
                            "completion_tokens": 1000,
                            "total_tokens": 11000,
                            "cached_tokens": 5000,
                        }
                    }
                }
            }
            state_file = state_dir / "classify_official_site.json"
            state_file.write_text(json.dumps(state_data), encoding="utf-8")

            # Run to completion (no abort)
            summary = run_presweep(config)

            # Cost report should include vs_preflight_estimate
            cost_report_path = config.runs_dir / config.run_id / "_cost_report.json"
            assert cost_report_path.exists()

            cost_report = json.loads(cost_report_path.read_text(encoding="utf-8"))
            assert "vs_preflight_estimate" in cost_report
            vs_est = cost_report["vs_preflight_estimate"]
            assert "preflight_est_usd" in vs_est
            assert "actual_usd" in vs_est
            assert "ratio" in vs_est
            assert vs_est["preflight_est_usd"] == 0.005
            assert vs_est["actual_usd"] > 0
            assert vs_est["ratio"] > 0


# ---------------------------------------------------------------------------
# Test 17 (PR #19): BatchResult.usage with missing prompt_tokens_details
# ---------------------------------------------------------------------------


def test_batch_result_usage_missing_prompt_tokens_details():
    """BatchResult.usage handles missing prompt_tokens_details gracefully."""
    # Case 1: prompt_tokens_details is None
    response1 = {
        "body": {
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 200,
                "total_tokens": 1200,
                "prompt_tokens_details": None
            }
        }
    }
    result1 = BatchResult(
        custom_id="test-job-1",
        success=True,
        response=response1,
        error=None,
        status_code=200,
    )
    usage1 = result1.usage
    assert usage1 is not None
    assert usage1["prompt_tokens"] == 1000
    assert usage1["completion_tokens"] == 200
    assert usage1.get("cached_tokens", 0) == 0  # Should default to 0 when details is None

    # Case 2: prompt_tokens_details is missing entirely
    response2 = {
        "body": {
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 200,
                "total_tokens": 1200,
            }
        }
    }
    result2 = BatchResult(
        custom_id="test-job-2",
        success=True,
        response=response2,
        error=None,
        status_code=200,
    )
    usage2 = result2.usage
    assert usage2 is not None
    assert usage2["prompt_tokens"] == 1000
    assert usage2["completion_tokens"] == 200
    # cached_tokens should be 0 or absent when prompt_tokens_details is missing
    assert usage2.get("cached_tokens", 0) == 0


# ---------------------------------------------------------------------------
# Test 18 (PR #25): PresweepConfig rejects non-positive budget_usd
# ---------------------------------------------------------------------------


def test_presweep_config_rejects_negative_budget(tmp_path):
    """PresweepConfig raises ValueError if budget_usd is zero or negative."""
    from g3o.run.presweep import PresweepConfig

    master = tmp_path / "master.csv"
    master.write_text(
        "institution_id,name,country,government_level,institution_type,url\n"
        "inst-0001,Test Inst,TestCountry,national,university,https://example.edu\n",
        encoding="utf-8",
    )

    # Test negative budget
    try:
        config = PresweepConfig(
            run_id="test-run",
            runs_dir=tmp_path / "runs",
            master_csv=master,
            sample_size=1,
            seed=22294,
            stratification="equal",
            discovery_languages=("en",),
            discovery_results_per_query=10,
            discovery_mode="chain",
            discovery_evidence_term="official",
            budget_usd=-10.0,  # Negative budget should be rejected
        )
        assert False, "Expected ValueError for negative budget_usd"
    except ValueError as exc:
        assert "budget_usd must be positive" in str(exc)

    # Test zero budget
    try:
        config = PresweepConfig(
            run_id="test-run",
            runs_dir=tmp_path / "runs",
            master_csv=master,
            sample_size=1,
            seed=22294,
            stratification="equal",
            discovery_languages=("en",),
            discovery_results_per_query=10,
            discovery_mode="chain",
            discovery_evidence_term="official",
            budget_usd=0.0,  # Zero budget should also be rejected
        )
        assert False, "Expected ValueError for zero budget_usd"
    except ValueError as exc:
        assert "budget_usd must be positive" in str(exc)


# ---------------------------------------------------------------------------
# Test 19: CostMonitor.record_and_check convenience method
# ---------------------------------------------------------------------------


def test_record_and_check_convenience_method(tmp_path):
    """record_and_check combines record_stage and check_budget."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state" / ".done"
    state_dir.mkdir(parents=True)

    # Low usage - should pass budget check
    state_data = {
        "stage": "extract",
        "n_jobs": 10,
        "n_chunks": 1,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 100,
                    "total_tokens": 1100,
                    "cached_tokens": 0,
                }
            }
        }
    }
    state_file = state_dir / "extract.json"
    state_file.write_text(json.dumps(state_data), encoding="utf-8")

    monitor = CostMonitor(budget_usd=100.0)
    stage_cost, within_budget = monitor.record_and_check(run_dir, "extract")

    assert stage_cost.stage == "extract"
    assert stage_cost.total_usd > 0
    assert within_budget is True
    assert len(monitor.stages) == 1


# ---------------------------------------------------------------------------
# Test 20: Shared pricing constants
# ---------------------------------------------------------------------------


def test_shared_pricing_constants():
    """Pricing constants are imported from a single source of truth."""
    from g3o.common.pricing import GPT5_NANO_PRICING
    from g3o.common.cost_monitor import CostMonitor
    from g3o.run.preflight import GPT5_NANO_PRICING as PREFLIGHT_PRICING

    # Both modules should use the same pricing
    assert GPT5_NANO_PRICING is PREFLIGHT_PRICING

    # CostMonitor should use the shared pricing by default
    monitor = CostMonitor(budget_usd=10.0)
    assert monitor.pricing["batch_input_per_1m_usd"] == GPT5_NANO_PRICING["batch_input_per_1m_usd"]
    assert monitor.pricing["batch_output_per_1m_usd"] == GPT5_NANO_PRICING["batch_output_per_1m_usd"]
    assert monitor.pricing["batch_cached_input_per_1m_usd"] == GPT5_NANO_PRICING["batch_cached_input_per_1m_usd"]


# ---------------------------------------------------------------------------
# Test 21 (Priority 2.2): Cost report with zero stages
# ---------------------------------------------------------------------------


def test_cost_report_zero_stages():
    """cost_report() returns valid dict even when no stages recorded."""
    monitor = CostMonitor(budget_usd=10.0)
    report = monitor.cost_report()
    
    assert report["stages"] == []
    assert report["total_usd"] == 0.0
    assert report["total_prompt_tokens"] == 0
    assert report["total_completion_tokens"] == 0
    assert report["total_cached_tokens"] == 0
    assert report["total_input_usd"] == 0.0
    assert report["total_output_usd"] == 0.0
    assert report["budget_usd"] == 10.0
    assert report["budget_exceeded"] is False
    assert "pricing" in report


# ---------------------------------------------------------------------------
# Test 22 (Priority 1.3): Dry run mode logs warning instead of raising
# ---------------------------------------------------------------------------


def test_orchestrator_dry_run_mode_continues(tmp_path, monkeypatch):
    """Orchestrator continues past budget limit in dry run mode."""
    from g3o.common import config as g3o_config
    from g3o.run.presweep import PresweepConfig, run_presweep

    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-openai")

    master = tmp_path / "master.csv"
    master.write_text(
        "institution_id,name,country,government_level,institution_type,url\n"
        "inst-0001,Test Inst,TestCountry,national,university,https://example.edu\n",
        encoding="utf-8",
    )

    config = PresweepConfig(
        run_id="test-run",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=1,
        seed=22294,
        stratification="equal",
        discovery_languages=("en",),
        discovery_results_per_query=10,
        discovery_mode="chain",
        discovery_evidence_term="official",
        discovery_domain_quote_name=False,
        serper_autocorrect=False,
        dry_run=False,
        stop_after="classify_official_site",
        filter_mode="shadow",
        poll_interval=60,
        max_wait_per_stage=25 * 60 * 60,
        model="gpt-5-nano",
        max_workers=1,
        budget_usd=0.001,  # Very low budget
        cost_monitor_dry_run=True,  # Dry run mode enabled
    )

    with patch("g3o.run.presweep.orchestrator._run_discovery_general") as mock_discovery:
        mock_discovery.return_value = {}

        with patch("g3o.run.presweep.orchestrator._run_classify_official_site") as mock_classify:
            mock_classify.return_value = {}

            # Mock state file with high usage that would exceed budget
            state_dir = config.runs_dir / config.run_id / "_state" / ".done"
            state_dir.mkdir(parents=True, exist_ok=True)
            state_data = {
                "stage": "classify_official_site",
                "n_jobs": 1000,
                "n_chunks": 1,
                "chunks": {
                    "1": {
                        "custom_ids": ["job-1"],
                        "usage": {
                            "prompt_tokens": 1000000,
                            "completion_tokens": 100000,
                            "total_tokens": 1100000,
                            "cached_tokens": 0,
                        }
                    }
                }
            }
            state_file = state_dir / "classify_official_site.json"
            state_file.write_text(json.dumps(state_data), encoding="utf-8")

            # Should NOT raise BudgetExceededError in dry run mode
            summary = run_presweep(config)
            
            # Run should complete successfully
            assert summary is not None
            assert "run_id" in summary

            # Cost report should be persisted with dry-run fields
            cost_report_path = config.runs_dir / config.run_id / "_cost_report.json"
            assert cost_report_path.exists()
            cost_report = json.loads(cost_report_path.read_text(encoding="utf-8"))
            assert cost_report["dry_run"] is True
            assert cost_report["abort_stage"] is None  # No actual abort in dry-run mode
            # Budget was exceeded (1M tokens >> 0.001 budget), so stages should be recorded
            assert cost_report["budget_exceeded"] is True
            assert "classify_official_site" in cost_report["budget_exceeded_stages"]


# ---------------------------------------------------------------------------
# Test 23 (Priority 1.3): Dry run mode includes dry_run field in cost report
# ---------------------------------------------------------------------------


def test_cost_report_includes_dry_run_field(tmp_path, monkeypatch):
    """Cost report includes dry_run field when cost_monitor_dry_run is True."""
    from g3o.common import config as g3o_config
    from g3o.run.presweep import PresweepConfig, run_presweep

    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-openai")

    master = tmp_path / "master.csv"
    master.write_text(
        "institution_id,name,country,government_level,institution_type,url\n"
        "inst-0001,Test Inst,TestCountry,national,university,https://example.edu\n",
        encoding="utf-8",
    )

    config = PresweepConfig(
        run_id="test-run",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=1,
        seed=22294,
        stratification="equal",
        discovery_languages=("en",),
        discovery_results_per_query=10,
        discovery_mode="chain",
        discovery_evidence_term="official",
        discovery_domain_quote_name=False,
        serper_autocorrect=False,
        dry_run=False,
        stop_after="classify_official_site",
        filter_mode="shadow",
        poll_interval=60,
        max_wait_per_stage=25 * 60 * 60,
        model="gpt-5-nano",
        max_workers=1,
        budget_usd=100.0,
        cost_monitor_dry_run=True,
    )

    with patch("g3o.run.presweep.orchestrator._run_discovery_general") as mock_discovery:
        mock_discovery.return_value = {}

        with patch("g3o.run.presweep.orchestrator._run_classify_official_site") as mock_classify:
            mock_classify.return_value = {}

            # Mock state file with some usage
            state_dir = config.runs_dir / config.run_id / "_state" / ".done"
            state_dir.mkdir(parents=True, exist_ok=True)
            state_data = {
                "stage": "classify_official_site",
                "n_jobs": 10,
                "n_chunks": 1,
                "chunks": {
                    "1": {
                        "custom_ids": ["job-1"],
                        "usage": {
                            "prompt_tokens": 10000,
                            "completion_tokens": 1000,
                            "total_tokens": 11000,
                            "cached_tokens": 5000,
                        }
                    }
                }
            }
            state_file = state_dir / "classify_official_site.json"
            state_file.write_text(json.dumps(state_data), encoding="utf-8")

            run_presweep(config)

            # Cost report should include dry_run field
            cost_report_path = config.runs_dir / config.run_id / "_cost_report.json"
            assert cost_report_path.exists()

            cost_report = json.loads(cost_report_path.read_text(encoding="utf-8"))
            assert "dry_run" in cost_report
            assert cost_report["dry_run"] is True
            # In dry-run mode, budget_exceeded_stages should be populated (not abort_stage)
            assert "budget_exceeded_stages" in cost_report
            assert cost_report["abort_stage"] is None  # No actual abort in dry-run mode
            # If budget was exceeded, the stage should be recorded
            if cost_report["budget_exceeded"]:
                assert len(cost_report["budget_exceeded_stages"]) > 0
