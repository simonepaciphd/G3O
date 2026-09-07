"""Tests for partial-stage cost reporting (Gap 3).

Tests that the cost report includes information about in-progress stages
that were interrupted by a budget abort or other failure. This provides
visibility into how much was spent on incomplete work.
"""

from __future__ import annotations

import json

from g3o.common.cost_monitor import CostMonitor


def test_record_partial_stage_computes_cost_from_active_state(tmp_path):
    """record_partial_stage computes cost from active state file."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state"
    state_dir.mkdir(parents=True)
    
    # Create an active state file with partial usage
    state_data = {
        "stage": "extract",
        "n_jobs": 100,
        "n_chunks": 5,
        "chunks": {
            "1": {
                "custom_ids": ["job-1", "job-2"],
                "usage": {
                    "prompt_tokens": 100000,
                    "completion_tokens": 10000,
                    "total_tokens": 110000,
                    "cached_tokens": 50000,
                }
            },
            "2": {
                "custom_ids": ["job-3", "job-4"],
                "usage": {
                    "prompt_tokens": 120000,
                    "completion_tokens": 12000,
                    "total_tokens": 132000,
                    "cached_tokens": 60000,
                }
            },
            "3": {
                "custom_ids": ["job-5", "job-6"],
                # No usage yet - chunk still in progress
            },
            "4": {
                "custom_ids": ["job-7", "job-8"],
                # No usage yet - chunk not started
            },
            "5": {
                "custom_ids": ["job-9", "job-10"],
                # No usage yet - chunk not started
            },
        }
    }
    (state_dir / "extract.json").write_text(json.dumps(state_data))
    
    monitor = CostMonitor(budget_usd=10.0)
    partial_cost = monitor.record_partial_stage(run_dir, "extract")
    
    assert partial_cost is not None
    assert partial_cost.stage == "extract"
    # Should sum usage from chunks 1 and 2 only
    assert partial_cost.prompt_tokens == 220000  # 100k + 120k
    assert partial_cost.completion_tokens == 22000  # 10k + 12k
    assert partial_cost.cached_tokens == 110000  # 50k + 60k
    assert partial_cost.n_chunks == 2  # Only 2 chunks completed
    assert partial_cost.n_jobs == 100  # Total jobs in stage
    assert partial_cost.total_usd > 0
    
    # Should be added to partial_stages list
    assert len(monitor.partial_stages) == 1
    assert monitor.partial_stages[0] is partial_cost


def test_record_partial_stage_returns_none_when_no_active_state(tmp_path):
    """record_partial_stage returns None when no active state file exists."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state"
    state_dir.mkdir(parents=True)
    
    monitor = CostMonitor(budget_usd=10.0)
    partial_cost = monitor.record_partial_stage(run_dir, "extract")
    
    assert partial_cost is None
    assert len(monitor.partial_stages) == 0


def test_cost_report_includes_partial_stages(tmp_path):
    """cost_report includes partial_stages section."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state"
    state_dir.mkdir(parents=True)
    
    # Create an active state file
    state_data = {
        "stage": "extract",
        "n_jobs": 50,
        "n_chunks": 3,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 50000,
                    "completion_tokens": 5000,
                    "total_tokens": 55000,
                    "cached_tokens": 25000,
                }
            },
            "2": {
                "custom_ids": ["job-2"],
                # No usage yet
            },
            "3": {
                "custom_ids": ["job-3"],
                # No usage yet
            },
        }
    }
    (state_dir / "extract.json").write_text(json.dumps(state_data))
    
    monitor = CostMonitor(budget_usd=10.0)
    monitor.record_partial_stage(run_dir, "extract")
    
    report = monitor.cost_report()
    
    assert "partial_stages" in report
    assert len(report["partial_stages"]) == 1
    
    partial = report["partial_stages"][0]
    assert partial["stage"] == "extract"
    assert partial["n_chunks_completed"] == 1
    assert partial["n_chunks_total"] == 3
    assert partial["total_usd"] > 0


def test_cost_report_partial_stages_empty_when_none(tmp_path):
    """cost_report includes empty partial_stages list when no partial stages."""
    monitor = CostMonitor(budget_usd=10.0)
    
    report = monitor.cost_report()
    
    assert "partial_stages" in report
    assert report["partial_stages"] == []


def test_partial_stage_cost_not_in_running_total(tmp_path):
    """Partial stage cost is NOT included in running_total_usd."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state"
    state_dir.mkdir(parents=True)
    
    # Record a completed stage
    done_dir = state_dir / ".done"
    done_dir.mkdir(parents=True)
    done_data = {
        "stage": "classify_official_site",
        "n_jobs": 10,
        "n_chunks": 1,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 100000,
                    "completion_tokens": 10000,
                    "total_tokens": 110000,
                    "cached_tokens": 50000,
                }
            }
        }
    }
    (done_dir / "classify_official_site.json").write_text(json.dumps(done_data))
    
    monitor = CostMonitor(budget_usd=10.0)
    monitor.record_stage(run_dir, "classify_official_site")
    total_before = monitor.running_total_usd
    
    # Record a partial stage
    active_data = {
        "stage": "extract",
        "n_jobs": 50,
        "n_chunks": 2,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 500000,  # Large usage
                    "completion_tokens": 50000,
                    "total_tokens": 550000,
                    "cached_tokens": 250000,
                }
            },
            "2": {
                "custom_ids": ["job-2"],
            }
        }
    }
    (state_dir / "extract.json").write_text(json.dumps(active_data))
    monitor.record_partial_stage(run_dir, "extract")
    total_after = monitor.running_total_usd
    
    # Running total should not change
    assert total_before == total_after
    assert len(monitor.stages) == 1  # Only the completed stage
    assert len(monitor.partial_stages) == 1  # The partial stage is separate


def test_partial_stage_handles_missing_usage_gracefully(tmp_path):
    """record_partial_stage handles chunks with no usage field."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state"
    state_dir.mkdir(parents=True)
    
    # Create state with chunks that have no usage
    state_data = {
        "stage": "extract",
        "n_jobs": 20,
        "n_chunks": 2,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                # No usage field at all
            },
            "2": {
                "custom_ids": ["job-2"],
                "usage": None,  # Explicit None
            },
        }
    }
    (state_dir / "extract.json").write_text(json.dumps(state_data))
    
    monitor = CostMonitor(budget_usd=10.0)
    partial_cost = monitor.record_partial_stage(run_dir, "extract")
    
    assert partial_cost is not None
    assert partial_cost.prompt_tokens == 0
    assert partial_cost.completion_tokens == 0
    assert partial_cost.cached_tokens == 0
    assert partial_cost.total_usd == 0.0
    assert partial_cost.n_chunks == 0  # No chunks with usage


def test_partial_stage_handles_cached_tokens_clamping(tmp_path):
    """record_partial_stage clamps cached_tokens when it exceeds prompt_tokens."""
    run_dir = tmp_path / "test-run"
    state_dir = run_dir / "_state"
    state_dir.mkdir(parents=True)
    
    # Create state with inconsistent cached > prompt
    state_data = {
        "stage": "extract",
        "n_jobs": 10,
        "n_chunks": 1,
        "chunks": {
            "1": {
                "custom_ids": ["job-1"],
                "usage": {
                    "prompt_tokens": 100000,
                    "completion_tokens": 10000,
                    "total_tokens": 110000,
                    "cached_tokens": 150000,  # Exceeds prompt_tokens
                }
            }
        }
    }
    (state_dir / "extract.json").write_text(json.dumps(state_data))
    
    monitor = CostMonitor(budget_usd=10.0)
    partial_cost = monitor.record_partial_stage(run_dir, "extract")
    
    assert partial_cost is not None
    # Should not crash, and should handle the inconsistency gracefully
    assert partial_cost.total_usd >= 0


def test_persisted_report_carries_partial_stages(tmp_path, monkeypatch):
    """The *file* on disk carries partial stages, not just the in-memory monitor.

    Regression test for an ordering bug found while reviewing finding F2
    (2026-08-24). The orchestrator built ``monitor.cost_report()`` — a plain
    snapshot — *before* the loop that calls ``record_partial_stage``, so the
    persisted ``_cost_report.json`` always carried ``"partial_stages": []``.
    That emptied the report exactly on the budget-abort path this scan exists to
    serve: the truncated stage's partial spend never reached the file.

    Every other test in this module calls ``record_partial_stage`` before
    ``cost_report()`` and so cannot see the bug. This one asserts against the
    persisted artifact, which is the only place the ordering is observable.
    """
    from unittest.mock import patch

    from g3o.common.cost_monitor import BudgetExceededError
    from g3o.run.presweep import PresweepConfig, run_presweep

    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    master = tmp_path / "master.csv"
    master.write_text(
        "institution_uid,institution_id,name,country,government_level,institution_type,url\n"
        "G3O-I-00000001,inst-0001,Test Inst,TestCountry,national,university,https://example.edu\n",
        encoding="utf-8",
    )
    config = PresweepConfig(
        run_id="partial-run",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=1,
        seed=22294,
        dry_run=False,
        stop_after="classify_official_site",
        model="gpt-5-nano",
        budget_usd=0.001,
    )

    run_dir = config.runs_dir / config.run_id
    done_dir = run_dir / "_state" / ".done"
    done_dir.mkdir(parents=True, exist_ok=True)
    # A completed stage expensive enough to trip the ceiling...
    (done_dir / "classify_official_site.json").write_text(
        json.dumps(
            {
                "stage": "classify_official_site",
                "n_jobs": 1,
                "n_chunks": 1,
                "chunks": {
                    "1": {
                        "custom_ids": ["job-1"],
                        "usage": {
                            "prompt_tokens": 1_000_000,
                            "completion_tokens": 100_000,
                            "total_tokens": 1_100_000,
                            "cached_tokens": 0,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    # ...and an *active* extract stage, which is what the scan must pick up.
    (run_dir / "_state" / "extract.json").write_text(
        json.dumps(
            {
                "stage": "extract",
                "n_jobs": 10,
                "n_chunks": 4,
                "chunks": {
                    "1": {
                        "custom_ids": ["e-1"],
                        "usage": {
                            "prompt_tokens": 50_000,
                            "completion_tokens": 5_000,
                            "total_tokens": 55_000,
                            "cached_tokens": 0,
                        },
                    },
                    "2": {"custom_ids": ["e-2"]},
                    "3": {"custom_ids": ["e-3"]},
                    "4": {"custom_ids": ["e-4"]},
                },
            }
        ),
        encoding="utf-8",
    )

    with patch("g3o.run.presweep.orchestrator._run_discovery_general") as discovery:
        discovery.return_value = {}
        with patch("g3o.run.presweep.orchestrator._run_classify_official_site") as classify:
            classify.return_value = {}
            try:
                run_presweep(config)
            except BudgetExceededError:
                pass

    report = json.loads((run_dir / "_cost_report.json").read_text(encoding="utf-8"))
    assert report["abort_stage"] == "classify_official_site"
    partial = report["partial_stages"]
    assert partial, "the persisted report dropped the in-flight stage"
    assert partial[0]["stage"] == "extract"
    assert partial[0]["n_chunks_completed"] == 1
    assert partial[0]["n_chunks_total"] == 4
    assert partial[0]["total_usd"] > 0
