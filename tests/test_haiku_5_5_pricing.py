"""The v2.7 extractor model ``claude-haiku-5-5`` has a priced rate row (T-030 C-4).

Without the row, ``pricing_for`` returned ``None``, spend came out null and the
budget ceiling could not limit extraction. Expected values are computed by hand
from the published rates (Anthropic pricing page, verified 2026-11-05), not from
the module under test.
"""

from __future__ import annotations

import json

import pytest

from g3o.common.cost_monitor import CostMonitor
from g3o.common.pricing import (
    HAIKU_5_5_PRICING,
    PRICING,
    anthropic_request_usd,
    pricing_for,
)
from g3o.extract.anthropic_client import EXTRACTOR_MODEL

MODEL = "claude-haiku-5-5"


def test_extractor_model_id_hits_the_row():
    assert EXTRACTOR_MODEL == MODEL
    row = pricing_for(EXTRACTOR_MODEL)
    assert row is not None
    assert row is PRICING[MODEL] is HAIKU_5_5_PRICING
    assert row["model"] == MODEL
    assert row["source"].startswith("https://platform.claude.com/")


def test_flat_keys_carry_published_up_to_100k_batch_rates():
    row = pricing_for(MODEL)
    assert row["batch_input_per_1m_usd"] == 0.05
    assert row["batch_output_per_1m_usd"] == 0.25
    assert row["batch_cached_input_per_1m_usd"] == 0.005
    assert row["standard_input_per_1m_usd"] == 0.10
    assert row["standard_output_per_1m_usd"] == 0.50
    assert row["batch_line_is_estimate"] is False


def test_no_prefix_mispricing():
    assert pricing_for("claude-haiku-5-5-turbo") is None


def test_cost_monitor_prices_known_usage(tmp_path):
    # 1,000,000 prompt tokens of which 200,000 cached, 100,000 output, batch:
    # 800k x 0.05 + 200k x 0.005 + 100k x 0.25 per 1M = 0.04 + 0.001 + 0.025
    done = tmp_path / "_state" / ".done"
    done.mkdir(parents=True)
    (done / "extract.json").write_text(json.dumps({
        "stage": "extract", "n_jobs": 1, "n_chunks": 1,
        "chunks": {"1": {"custom_ids": ["j1"], "usage": {
            "prompt_tokens": 1_000_000, "completion_tokens": 100_000,
            "cached_tokens": 200_000}}},
    }), encoding="utf-8")
    monitor = CostMonitor(budget_usd=1.0, model=MODEL)
    assert monitor.is_priced is True
    cost = monitor.record_stage(tmp_path, "extract")
    assert cost.total_usd is not None
    assert cost.total_usd == pytest.approx(0.066)


def test_request_under_threshold_batch():
    usage = {"input_tokens": 50_000, "output_tokens": 2_000,
             "cache_read_input_tokens": 10_000, "cache_creation_input_tokens": 0}
    # 50k x 0.05 + 10k x 0.005 + 2k x 0.25 per 1M
    expected = 0.0025 + 0.00005 + 0.0005
    assert anthropic_request_usd(usage, pricing_for(MODEL)) == pytest.approx(expected)


def test_request_over_threshold_pays_long_tier_including_cache():
    # 95k input + 10k cache read = 105k prompt > 100k: whole request at long tier.
    usage = {"input_tokens": 95_000, "output_tokens": 1_000,
             "cache_read_input_tokens": 10_000, "cache_creation_input_tokens": None}
    expected = 95_000 * 0.25 / 1e6 + 10_000 * 0.025 / 1e6 + 1_000 * 1.25 / 1e6
    assert anthropic_request_usd(usage, pricing_for(MODEL)) == pytest.approx(expected)


def test_request_exactly_at_threshold_is_base_tier():
    usage = {"input_tokens": 100_000, "output_tokens": 0}
    assert anthropic_request_usd(usage, pricing_for(MODEL)) == pytest.approx(0.005)


def test_request_standard_with_cache_writes():
    usage = {"input_tokens": 10_000, "output_tokens": 1_000,
             "cache_creation_input_tokens": 3_000,
             "cache_creation": {"ephemeral_5m_input_tokens": 2_000,
                                "ephemeral_1h_input_tokens": 1_000}}
    expected = (10_000 * 0.10 + 2_000 * 0.125 + 1_000 * 0.20 + 1_000 * 0.50) / 1e6
    got = anthropic_request_usd(usage, pricing_for(MODEL), batch=False)
    assert got == pytest.approx(expected)
