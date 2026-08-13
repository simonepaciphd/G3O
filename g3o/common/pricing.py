"""Shared pricing constants for OpenAI API models.

Single source of truth for pricing rates used by both preflight projections
and runtime cost monitoring. Import from here to avoid duplication.

Pricing verified 2026-06-10 against OpenAI docs.
"""

from __future__ import annotations

from typing import Any

# gpt-5-nano standard rates are published FACTS (model page below). The Batch
# API rates apply OpenAI's documented 50% Batch discount — shown verbatim on the
# same pricing page for the sibling gpt-5.4-nano ($0.20→$0.10 input) — so the
# batch line is labeled ESTIMATE-grade: the nano model page does not print the
# batch row itself.
GPT5_NANO_PRICING: dict[str, Any] = {
    "model": "gpt-5-nano",
    "source": "https://developers.openai.com/api/docs/models/gpt-5-nano",
    "verified_on": "2026-06-10",
    "standard_input_per_1m_usd": 0.05,
    "standard_cached_input_per_1m_usd": 0.005,
    "standard_output_per_1m_usd": 0.40,
    "batch_discount": 0.50,
    "batch_input_per_1m_usd": 0.025,  # estimate: 50% of standard input
    "batch_output_per_1m_usd": 0.20,  # estimate: 50% of standard output
    "batch_cached_input_per_1m_usd": 0.0025,  # estimate: standard_cached * batch_discount
    "batch_line_is_estimate": True,
}


__all__ = ["GPT5_NANO_PRICING", "usd"]


def usd(n_tokens: float, per_1m: float) -> float:
    """Convert token count to USD cost given per-1M-token rate.

    Single-source helper shared by :mod:`g3o.common.cost_monitor` and
    :mod:`g3o.run.preflight` so both compute cost identically.
    """
    return (n_tokens / 1_000_000) * per_1m
