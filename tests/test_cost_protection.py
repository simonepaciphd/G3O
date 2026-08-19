"""Cost gate / circuit breaker tests.

Tests the cost ceiling abort logic that prevents budget overrun:
1. Preflight correctly detects when projected cost exceeds budget
2. CLI aborts with exit code 3 when ceiling exceeded in --preflight mode
3. CLI aborts with exit code 3 when ceiling exceeded in --execute mode
4. CLI proceeds when under budget
5. Edge cases: exact match, None ceiling (no limit)

These tests ensure operators cannot accidentally spend beyond their budget.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from g3o.common import config as g3o_config
from g3o.run import preflight as pf
from g3o.run.presweep import PresweepConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_master(path: Path, n: int = 5) -> Path:
    """Write a minimal master CSV with n institutions."""
    rows = [
        "institution_id,name,country,government_level,institution_type,url"
    ]
    for i in range(n):
        rows.append(
            f"inst-{i:04d},Test Institution {i},TestCountry,national,university,"
            f"https://example{i}.edu"
        )
    path.write_text("\n".join(rows), encoding="utf-8")
    return path


def _config(
    tmp_path: Path,
    master: Path,
    *,
    sample_size: int = 5,
    run_id: str = "test-run",
    execute: bool = False,
) -> PresweepConfig:
    """Build a minimal PresweepConfig for testing."""
    return PresweepConfig(
        run_id=run_id,
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=sample_size,
        seed=22294,
        stratification="equal",
        discovery_languages=("en",),
        discovery_results_per_query=10,
        discovery_mode="chain",
        discovery_evidence_term="official",
        discovery_domain_quote_name=False,
        serper_autocorrect=False,
        dry_run=not execute,
        stop_after="extract",
        filter_mode="shadow",
        poll_interval=60,
        max_wait_per_stage=25 * 60 * 60,
        model="gpt-5-nano",
        max_workers=1,
    )


# ---------------------------------------------------------------------------
# Test 1: Preflight returns cost_ceiling_exceeded=True when over budget
# ---------------------------------------------------------------------------


def test_preflight_detects_cost_ceiling_exceeded(tmp_path, monkeypatch):
    """When projected cost > budget limit, preflight returns cost_ceiling_exceeded=True."""
    master = _write_master(tmp_path / "m.csv", n=5)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    config = _config(tmp_path, master, sample_size=5, run_id="cost-test-1")

    # Set a very low ceiling that will definitely be exceeded
    # With 5 institutions × 12 pages = 60 jobs, cost will be > $0.001
    summary = pf.run_preflight(
        config,
        verify_model_live=False,
        cost_ceiling_usd=0.001,
    )

    assert summary["cost_ceiling_usd"] == 0.001
    assert summary["cost_ceiling_exceeded"] is True
    assert summary["cost_preview"]["est_openai_batch_total_usd"] > 0.001


# ---------------------------------------------------------------------------
# Test 2: Preflight returns cost_ceiling_exceeded=False when under budget
# ---------------------------------------------------------------------------


def test_preflight_allows_under_budget(tmp_path, monkeypatch):
    """When projected cost < budget limit, preflight returns cost_ceiling_exceeded=False."""
    master = _write_master(tmp_path / "m.csv", n=3)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    config = _config(tmp_path, master, sample_size=3, run_id="cost-test-2")

    # Set a very high ceiling that will definitely not be exceeded
    summary = pf.run_preflight(
        config,
        verify_model_live=False,
        cost_ceiling_usd=1000.0,
    )

    assert summary["cost_ceiling_usd"] == 1000.0
    assert summary["cost_ceiling_exceeded"] is False
    assert summary["cost_preview"]["est_openai_batch_total_usd"] < 1000.0


# ---------------------------------------------------------------------------
# Test 3: Preflight handles None ceiling (no limit) gracefully
# ---------------------------------------------------------------------------


def test_preflight_none_ceiling_means_no_limit(tmp_path, monkeypatch):
    """When cost_ceiling_usd=None, no ceiling check is performed."""
    master = _write_master(tmp_path / "m.csv", n=5)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    config = _config(tmp_path, master, sample_size=5, run_id="cost-test-3")

    summary = pf.run_preflight(
        config,
        verify_model_live=False,
        cost_ceiling_usd=None,
    )

    assert summary["cost_ceiling_usd"] is None
    # cost_ceiling_exceeded should not be present when no ceiling is set
    assert "cost_ceiling_exceeded" not in summary or summary["cost_ceiling_exceeded"] is False


# ---------------------------------------------------------------------------
# Test 4: CLI aborts with exit code 3 when --preflight exceeds ceiling
# ---------------------------------------------------------------------------


def test_cli_preflight_aborts_on_ceiling_exceeded(tmp_path, monkeypatch, capsys):
    """CLI returns exit code 3 when --preflight detects cost ceiling exceeded."""
    from g3o import cli

    master = _write_master(tmp_path / "master.csv", n=5)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    args = [
        "presweep",
        "--preflight",
        "--run-id", "cli-cost-test-1",
        "--master-csv", str(master),
        "--sample-size", "5",
        "--cost-ceiling", "0.001",  # Very low, will be exceeded
    ]

    exit_code = cli.main(args)
    captured = capsys.readouterr()

    # Should abort with exit code 3
    assert exit_code == 3

    # Should print circuit breaker message to stderr
    assert "COST CIRCUIT BREAKER TRIGGERED" in captured.err
    assert "Budget limit: $0.00" in captured.err
    assert "Aborting before batch submission" in captured.err


# ---------------------------------------------------------------------------
# Test 5: CLI proceeds when --preflight is under budget
# ---------------------------------------------------------------------------


def test_cli_preflight_proceeds_under_budget(tmp_path, monkeypatch, capsys):
    """CLI returns exit code 0 when --preflight is under budget."""
    from g3o import cli

    master = _write_master(tmp_path / "master.csv", n=3)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    args = [
        "presweep",
        "--preflight",
        "--run-id", "cli-cost-test-2",
        "--master-csv", str(master),
        "--sample-size", "3",
        "--cost-ceiling", "1000.0",  # Very high, won't be exceeded
    ]

    exit_code = cli.main(args)
    captured = capsys.readouterr()

    # Should proceed with exit code 0
    assert exit_code == 0

    # Should NOT print circuit breaker message
    assert "COST CIRCUIT BREAKER TRIGGERED" not in captured.err

    # Should output JSON summary to stdout
    summary = json.loads(captured.out)
    assert summary["cost_ceiling_exceeded"] is False


# ---------------------------------------------------------------------------
# Test 6: CLI --execute aborts when G3O_BUDGET_LIMIT_USD is exceeded
# ---------------------------------------------------------------------------


def test_cli_execute_aborts_on_budget_limit_exceeded(tmp_path, monkeypatch, capsys):
    """CLI --execute aborts with exit code 3 when G3O_BUDGET_LIMIT_USD is exceeded."""
    from g3o import cli

    master = _write_master(tmp_path / "master.csv", n=5)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setattr(g3o_config, "BUDGET_LIMIT_USD", "0.001")  # Very low

    args = [
        "presweep",
        "--execute",
        "--run-id", "cli-cost-test-3",
        "--master-csv", str(master),
        "--sample-size", "5",
    ]

    # Mock run_presweep to avoid actual execution
    with patch("g3o.run.presweep.run_presweep") as mock_run:
        exit_code = cli.main(args)
        captured = capsys.readouterr()

    # Should abort before calling run_presweep
    assert exit_code == 3
    mock_run.assert_not_called()

    # Should print circuit breaker message
    assert "COST CIRCUIT BREAKER TRIGGERED" in captured.err
    assert "G3O_BUDGET_LIMIT_USD" in captured.err


# ---------------------------------------------------------------------------
# Test 7: CLI --execute proceeds when under budget limit
# ---------------------------------------------------------------------------


def test_cli_execute_proceeds_under_budget_limit(tmp_path, monkeypatch, capsys):
    """CLI --execute proceeds when G3O_BUDGET_LIMIT_USD is not exceeded."""
    from g3o import cli

    master = _write_master(tmp_path / "master.csv", n=2)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setattr(g3o_config, "BUDGET_LIMIT_USD", "1000.0")  # Very high

    args = [
        "presweep",
        "--execute",
        "--run-id", "cli-cost-test-4",
        "--master-csv", str(master),
        "--sample-size", "2",
    ]

    # Mock run_presweep to return immediately
    with patch("g3o.run.presweep.run_presweep") as mock_run:
        mock_run.return_value = {"status": "completed"}
        exit_code = cli.main(args)
        captured = capsys.readouterr()

    # Should proceed and call run_presweep
    assert exit_code == 0
    mock_run.assert_called_once()

    # Should NOT print circuit breaker message
    assert "COST CIRCUIT BREAKER TRIGGERED" not in captured.err


# ---------------------------------------------------------------------------
# Test 8: CLI --cost-ceiling flag overrides G3O_BUDGET_LIMIT_USD
# ---------------------------------------------------------------------------


def test_cli_cost_ceiling_flag_overrides_env_var(tmp_path, monkeypatch, capsys):
    """--cost-ceiling CLI flag takes precedence over G3O_BUDGET_LIMIT_USD env var."""
    from g3o import cli

    master = _write_master(tmp_path / "master.csv", n=3)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setattr(g3o_config, "BUDGET_LIMIT_USD", "1000.0")  # High env var

    args = [
        "presweep",
        "--preflight",
        "--run-id", "cli-cost-test-5",
        "--master-csv", str(master),
        "--sample-size", "3",
        "--cost-ceiling", "0.001",  # Low CLI flag should override
    ]

    exit_code = cli.main(args)
    captured = capsys.readouterr()

    # Should abort because CLI flag (0.001) overrides env var (1000.0)
    assert exit_code == 3
    assert "Budget limit: $0.00" in captured.err


# ---------------------------------------------------------------------------
# Test 9: Malformed G3O_BUDGET_LIMIT_USD raises SystemExit
# ---------------------------------------------------------------------------


def test_malformed_budget_limit_raises_systemexit(tmp_path, monkeypatch):
    """Malformed G3O_BUDGET_LIMIT_USD env var raises SystemExit with clear message."""
    from g3o import cli

    master = _write_master(tmp_path / "master.csv", n=3)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setattr(g3o_config, "BUDGET_LIMIT_USD", "not-a-number")

    args = [
        "presweep",
        "--preflight",
        "--run-id", "cli-cost-test-6",
        "--master-csv", str(master),
        "--sample-size", "3",
    ]

    # Should raise SystemExit before even running preflight
    import pytest
    with pytest.raises(SystemExit, match="G3O_BUDGET_LIMIT_USD='not-a-number' is not a valid number"):
        cli.main(args)


# ---------------------------------------------------------------------------
# Test 10: NaN budget limit is rejected
# ---------------------------------------------------------------------------


def test_nan_budget_limit_is_rejected(tmp_path, monkeypatch):
    """float('nan') in G3O_BUDGET_LIMIT_USD is rejected to prevent silent gate bypass."""
    from g3o import cli

    master = _write_master(tmp_path / "master.csv", n=3)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setattr(g3o_config, "BUDGET_LIMIT_USD", "nan")

    args = [
        "presweep",
        "--preflight",
        "--run-id", "cli-cost-test-7",
        "--master-csv", str(master),
        "--sample-size", "3",
    ]

    # Should raise SystemExit because NaN would silently disable the gate
    import pytest
    with pytest.raises(SystemExit, match="G3O_BUDGET_LIMIT_USD='nan' is not a finite number"):
        cli.main(args)


# ---------------------------------------------------------------------------
# Test 11: --cost-ceiling flag overrides env var on --execute path
# ---------------------------------------------------------------------------


def test_cli_cost_ceiling_flag_overrides_env_var_on_execute(tmp_path, monkeypatch, capsys):
    """--cost-ceiling CLI flag takes precedence over G3O_BUDGET_LIMIT_USD on --execute path."""
    from unittest.mock import patch

    from g3o import cli

    master = _write_master(tmp_path / "master.csv", n=3)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setattr(g3o_config, "BUDGET_LIMIT_USD", "1000.0")  # High env var

    args = [
        "presweep",
        "--execute",
        "--run-id", "cli-cost-test-8",
        "--master-csv", str(master),
        "--sample-size", "3",
        "--cost-ceiling", "0.001",  # Low CLI flag should override
    ]

    # Mock run_presweep to avoid actual execution
    with patch("g3o.run.presweep.run_presweep") as mock_run:
        exit_code = cli.main(args)
        captured = capsys.readouterr()

    # Should abort before calling run_presweep because CLI flag (0.001) overrides env var (1000.0)
    assert exit_code == 3
    mock_run.assert_not_called()
    assert "COST CIRCUIT BREAKER TRIGGERED" in captured.err
    assert "Budget limit: $0.00" in captured.err


# ---------------------------------------------------------------------------
# Test 12: the projection that cleared real spend is emitted, not discarded
# ---------------------------------------------------------------------------


def test_cli_execute_emits_the_projection_that_cleared_it(tmp_path, monkeypatch, capsys):
    """A run that passes the gate still records what the gate saw.

    The --preflight path dumps its summary to stdout; without this, the
    --execute path computed the same projection, tested one key, and threw it
    away — so the run that actually spends money kept no record of the estimate
    that authorized it. Emitted on stderr so stdout stays a single JSON
    document (the presweep summary).
    """
    from g3o import cli

    master = _write_master(tmp_path / "master.csv", n=2)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setattr(g3o_config, "BUDGET_LIMIT_USD", "1000.0")

    args = [
        "presweep",
        "--execute",
        "--run-id", "cli-cost-test-9",
        "--master-csv", str(master),
        "--sample-size", "2",
    ]

    with patch("g3o.run.presweep.run_presweep") as mock_run:
        mock_run.return_value = {"status": "completed"}
        exit_code = cli.main(args)
        captured = capsys.readouterr()

    assert exit_code == 0
    mock_run.assert_called_once()
    assert "COST CIRCUIT BREAKER TRIGGERED" not in captured.err

    # The projection is on stderr and is parseable, with the cost preview intact.
    assert "cost gate — preflight projection:" in captured.err
    payload = json.loads(captured.err.split("projection:", 1)[1])
    assert payload["cost_ceiling_exceeded"] is False
    assert "est_openai_batch_total_usd" in payload["cost_preview"]

    # stdout carries exactly one JSON document. Since the Run API (spec §1.1) the
    # CLI prints what `launch()` returned — the receipt, with the stage summary
    # merged in — so this asserts the invariant the gate depends on (one
    # parseable document, summary keys intact) rather than a fixed key set.
    stdout_payload = json.loads(captured.out)
    assert stdout_payload["status"] == "completed"  # the summary, merged in
    assert stdout_payload["run_id"] == "cli-cost-test-9"
    # Live run stopping at the default `extract`, i.e. short of the full roster.
    assert stdout_payload["outcome"] == "stopped"


# ---------------------------------------------------------------------------
# Test 13: no budget set on --execute ⇒ no preflight, presweep proceeds
# ---------------------------------------------------------------------------


def test_cli_execute_without_budget_skips_preflight(tmp_path, monkeypatch, capsys):
    """The gate is opt-in. With neither the env var nor the flag set, --execute
    must not pay the cost of a projection it has no limit to compare against."""
    from g3o import cli

    master = _write_master(tmp_path / "master.csv", n=2)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setattr(g3o_config, "BUDGET_LIMIT_USD", None)

    args = [
        "presweep",
        "--execute",
        "--run-id", "cli-cost-test-10",
        "--master-csv", str(master),
        "--sample-size", "2",
    ]

    with (
        patch("g3o.run.presweep.run_presweep") as mock_run,
        patch("g3o.run.preflight.run_preflight") as mock_preflight,
    ):
        mock_run.return_value = {"status": "completed"}
        exit_code = cli.main(args)
        captured = capsys.readouterr()

    assert exit_code == 0
    mock_run.assert_called_once()
    mock_preflight.assert_not_called()
    assert "cost gate" not in captured.err
