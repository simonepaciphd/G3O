"""Rates are keyed by the model the run actually submits (review F2, 2026-08-24).

Before this change every USD figure in the pipeline came from one hard-coded
``gpt-5-nano`` table while ``--model`` / ``OPENAI_MODEL`` were freely settable and
never compared against it. So the budget circuit breaker — the mechanism whose
whole job is to stop a run at a number — silently priced any other model at nano
rates, and the persisted cost report labelled the result ``"gpt-5-nano"``
regardless of what had run.

The PI ruling these tests pin has two halves:

1. a **ceiling set** + a model with no rate row **refuses to start**;
2. **no ceiling** + no rate row **proceeds**, recording the real model id and
   **null USD** — never a fabricated total.

``test_report_prices_a_non_nano_model_at_its_own_rates`` is the regression test
for the finding itself. Note what it can and cannot claim: it cannot be *run*
against the pre-fix code, because ``CostMonitor`` took no ``model`` at all then —
that absence was the defect. What it pins is that the same tokens under a
non-nano model now produce that model's cost and carry its id, and it asserts
explicitly that the total is *not* the nano arithmetic the old code returned.
"""

from __future__ import annotations

import json

import pytest

from g3o.common import pricing as pricing_mod
from g3o.common.cost_monitor import CostMonitor, UnpricedModelError
from g3o.common.pricing import GPT5_NANO_PRICING, PRICING, pricing_for

# A second, deliberately-not-nano rate row. Registered by monkeypatch rather than
# shipped: the registry must only ever carry rates someone actually verified, and
# inventing one to make a test convenient is the habit this whole finding is about.
OTHER_MODEL = "g3o-test-model"
OTHER_PRICING = {
    "model": OTHER_MODEL,
    "source": "test fixture",
    "verified_on": "2026-08-24",
    "batch_input_per_1m_usd": 2.5,      # 100x nano
    "batch_output_per_1m_usd": 20.0,    # 100x nano
    "batch_cached_input_per_1m_usd": 0.25,
    "batch_line_is_estimate": False,
}


@pytest.fixture
def registered_other_model(monkeypatch):
    """Add OTHER_MODEL to the rate registry for one test."""
    monkeypatch.setitem(PRICING, OTHER_MODEL, OTHER_PRICING)
    return OTHER_MODEL


def _write_done_state(run_dir, stage, *, prompt=1_000_000, completion=100_000, cached=0):
    """A completed-stage state file, in the shape record_stage reads."""
    done_dir = run_dir / "_state" / ".done"
    done_dir.mkdir(parents=True, exist_ok=True)
    (done_dir / f"{stage}.json").write_text(
        json.dumps(
            {
                "stage": stage,
                "n_jobs": 1,
                "n_chunks": 1,
                "chunks": {
                    "1": {
                        "custom_ids": ["job-1"],
                        "usage": {
                            "prompt_tokens": prompt,
                            "completion_tokens": completion,
                            "total_tokens": prompt + completion,
                            "cached_tokens": cached,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# pricing_for resolution
# ---------------------------------------------------------------------------


def test_exact_model_id_resolves() -> None:
    assert pricing_for("gpt-5-nano") is GPT5_NANO_PRICING


def test_dated_snapshot_resolves_to_its_base_row() -> None:
    """`BatchResult.response_model` returns dated snapshots, not bare ids."""
    assert pricing_for("gpt-5-nano-2025-08-07") is GPT5_NANO_PRICING


def test_unknown_model_is_none_not_a_default() -> None:
    """The absence of a fallback is the fix; assert it directly."""
    assert pricing_for("some-model-nobody-registered") is None


def test_a_different_model_sharing_a_prefix_does_not_borrow_the_rates() -> None:
    """Only a *dated snapshot* resolves — a bare prefix test would mis-price.

    ``gpt-5-nano-turbo`` is a hypothetical different model, not a snapshot of
    gpt-5-nano, and pricing it off nano's row would reproduce the finding in
    miniature.
    """
    assert pricing_for("gpt-5-nano-turbo") is None
    assert pricing_for("gpt-5-nano-2025-08") is None  # not a full date


def test_longest_matching_base_wins(monkeypatch) -> None:
    monkeypatch.setitem(PRICING, "gpt-5", dict(OTHER_PRICING, model="gpt-5"))
    assert pricing_for("gpt-5-nano-2025-08-07") is GPT5_NANO_PRICING


def test_alias_and_registry_cannot_drift() -> None:
    assert GPT5_NANO_PRICING is PRICING["gpt-5-nano"]


# ---------------------------------------------------------------------------
# Ruling half 1 — a ceiling plus an unpriceable model refuses
# ---------------------------------------------------------------------------


def test_monitor_refuses_a_budget_it_cannot_enforce() -> None:
    with pytest.raises(UnpricedModelError) as exc:
        CostMonitor(budget_usd=10.0, model="some-model-nobody-registered")
    assert "some-model-nobody-registered" in str(exc.value)
    assert "cannot be enforced" in str(exc.value)


def test_preflight_refuses_a_ceiling_it_cannot_enforce(tmp_path, monkeypatch) -> None:
    """The backstop in CostMonitor is not the only gate — preflight refuses first.

    This is the one that matters operationally: both cost gates (the CLI's and
    the orchestrator's) run a preflight whenever a ceiling is set, so refusing
    here binds on both paths without either needing to know about pricing.
    """
    from g3o.run.preflight import run_preflight

    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    config = _preflight_config(tmp_path, model="some-model-nobody-registered")

    with pytest.raises(UnpricedModelError):
        run_preflight(config, cost_ceiling_usd=5.0)


def test_monitor_allows_an_unpriced_model_without_a_budget() -> None:
    """Ruling half 2: no ceiling, so nothing needs enforcing."""
    monitor = CostMonitor(budget_usd=None, model="some-model-nobody-registered")
    assert monitor.is_priced is False
    assert monitor.check_budget() is True


# ---------------------------------------------------------------------------
# Ruling half 2 — unpriced runs report tokens, and null dollars
# ---------------------------------------------------------------------------


def test_unpriced_run_reports_real_tokens_and_null_usd(tmp_path) -> None:
    run_dir = tmp_path / "run"
    _write_done_state(run_dir, "extract")
    monitor = CostMonitor(budget_usd=None, model="some-model-nobody-registered")

    cost = monitor.record_stage(run_dir, "extract")
    # The tokens were measured and are exact.
    assert cost.prompt_tokens == 1_000_000
    assert cost.completion_tokens == 100_000
    # The dollars were not.
    assert cost.input_usd is None
    assert cost.output_usd is None
    assert cost.total_usd is None
    assert monitor.running_total_usd is None

    report = monitor.cost_report()
    assert report["total_usd"] is None
    assert report["total_input_usd"] is None
    assert report["total_prompt_tokens"] == 1_000_000
    assert report["stages"][0]["total_usd"] is None
    assert report["stages"][0]["prompt_tokens"] == 1_000_000
    assert report["pricing"]["model"] == "some-model-nobody-registered"
    assert report["pricing"]["priced"] is False
    # Rates are present-and-null rather than absent, so a consumer's
    # .get(key, 0) cannot read a missing rate as a free one.
    assert "batch_input_per_1m_usd" in report["pricing"]
    assert report["pricing"]["batch_input_per_1m_usd"] is None


def test_unpriced_report_is_json_serializable(tmp_path) -> None:
    """It is persisted to _cost_report.json, so null must survive the round trip."""
    run_dir = tmp_path / "run"
    _write_done_state(run_dir, "extract")
    monitor = CostMonitor(budget_usd=None, model="some-model-nobody-registered")
    monitor.record_stage(run_dir, "extract")
    round_tripped = json.loads(json.dumps(monitor.cost_report()))
    assert round_tripped["total_usd"] is None


# ---------------------------------------------------------------------------
# The regression test for the finding itself
# ---------------------------------------------------------------------------


def test_report_prices_a_non_nano_model_at_its_own_rates(
    tmp_path, registered_other_model
) -> None:
    """A registered non-nano model is priced — and named — as itself.

    The pre-fix code priced these same tokens at gpt-5-nano's rates and reported
    ``"model": "gpt-5-nano"``, with nothing anywhere to contradict it. The
    ``!= nano_total`` assertion below is what makes that contrast a test rather
    than a comment.
    """
    run_dir = tmp_path / "run"
    _write_done_state(run_dir, "extract", prompt=1_000_000, completion=1_000_000)
    monitor = CostMonitor(budget_usd=None, model=registered_other_model)

    cost = monitor.record_stage(run_dir, "extract")
    # 1M input at $2.50/1M + 1M output at $20.00/1M.
    assert cost.input_usd == pytest.approx(2.5)
    assert cost.output_usd == pytest.approx(20.0)

    report = monitor.cost_report()
    assert report["pricing"]["model"] == registered_other_model
    assert report["pricing"]["batch_input_per_1m_usd"] == 2.5
    # The number the old code would have produced, spelled out so the contrast
    # is legible: nano rates on the same tokens.
    nano_total = (
        GPT5_NANO_PRICING["batch_input_per_1m_usd"]
        + GPT5_NANO_PRICING["batch_output_per_1m_usd"]
    )
    assert report["total_usd"] != pytest.approx(nano_total)
    assert report["total_usd"] == pytest.approx(22.5)


def test_budget_is_enforced_against_the_real_rates(tmp_path, registered_other_model) -> None:
    """The breaker trips on the model that ran, not on nano's cheaper arithmetic.

    At nano rates these tokens cost $0.225 and would sit inside a $1 ceiling;
    at the model's real rates they cost $22.50 and must trip it.
    """
    run_dir = tmp_path / "run"
    _write_done_state(run_dir, "extract", prompt=1_000_000, completion=1_000_000)
    monitor = CostMonitor(budget_usd=1.0, model=registered_other_model)
    monitor.record_stage(run_dir, "extract")
    assert monitor.check_budget() is False


# ---------------------------------------------------------------------------
# Preflight, unpriced but uncapped
# ---------------------------------------------------------------------------


def _preflight_config(tmp_path, *, model: str):
    from g3o.run.presweep import PresweepConfig

    master = tmp_path / "master.csv"
    master.write_text(
        "institution_uid,institution_id,name,country,government_level,institution_type,url\n"
        "G3O-I-00000001,inst-0001,Test Inst,TestCountry,national,university,https://example.edu\n",
        encoding="utf-8",
    )
    return PresweepConfig(
        run_id="preflight-run",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=1,
        seed=22294,
        model=model,
    )


def test_preflight_without_a_ceiling_projects_tokens_and_null_usd(
    tmp_path, monkeypatch
) -> None:
    from g3o.run.preflight import run_preflight

    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    config = _preflight_config(tmp_path, model="some-model-nobody-registered")

    summary = run_preflight(config)
    preview = summary["cost_preview"]
    assert preview["pricing"]["model"] == "some-model-nobody-registered"
    assert preview["pricing"]["priced"] is False
    assert preview["est_openai_batch_total_usd"] is None
    # The token projection never depended on the rates, so it still answers
    # "how big is this run" — just not "what will it cost".
    assert preview["est_input_tokens"] > 0
    assert "cost_ceiling_exceeded" not in summary


def test_preflight_pricing_block_is_a_copy_not_the_registry(tmp_path, monkeypatch) -> None:
    """Mutating a summary must not mutate the process-wide rate table."""
    from g3o.run.preflight import run_preflight

    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    summary = run_preflight(_preflight_config(tmp_path, model="gpt-5-nano"))

    summary["cost_preview"]["pricing"]["batch_input_per_1m_usd"] = 999.0
    assert pricing_mod.GPT5_NANO_PRICING["batch_input_per_1m_usd"] == 0.025
