"""Shared OpenAI Batch pricing tables.

Single source of truth for both the pre-run cost *estimate*
(:mod:`g3o.run.preflight`) and the post-run *actual* cost computation
(:mod:`g3o.report.cost_report`), keyed by model name so a run using a model
with no pricing entry here degrades to "unavailable" rather than a silently
wrong number.
"""

from __future__ import annotations

from typing import Any

# gpt-5-nano standard rates are published FACTS (model page below). The Batch
# API rates apply OpenAI's documented 50% Batch discount — shown verbatim on
# the same pricing page for the sibling gpt-5.4-nano ($0.20→$0.10 input) — so
# the batch lines are labeled ESTIMATE-grade: the nano model page does not
# print the batch row itself. Verified 2026-06-10 against the OpenAI docs.
PRICING_TABLES: dict[str, dict[str, Any]] = {
    "gpt-5-nano": {
        "model": "gpt-5-nano",
        "source": "https://developers.openai.com/api/docs/models/gpt-5-nano",
        "verified_on": "2026-06-10",
        "standard_input_per_1m_usd": 0.05,
        "standard_cached_input_per_1m_usd": 0.005,
        "standard_output_per_1m_usd": 0.40,
        "batch_discount": 0.50,
        "batch_input_per_1m_usd": 0.025,  # estimate: 50% of standard input
        "batch_cached_input_per_1m_usd": 0.0025,  # estimate: 50% of standard cached input
        "batch_output_per_1m_usd": 0.20,  # estimate: 50% of standard output
        "batch_line_is_estimate": True,
    },
}

# Back-compat alias for existing importers.
GPT5_NANO_PRICING = PRICING_TABLES["gpt-5-nano"]


def get_pricing(model: str) -> dict[str, Any] | None:
    """Return the pricing table for ``model``, or ``None`` if unpriced."""
    return PRICING_TABLES.get(model)


def usd_for_tokens(n_tokens: float, per_1m_usd: float) -> float:
    return (n_tokens / 1_000_000) * per_1m_usd


__all__ = [
    "GPT5_NANO_PRICING",
    "PRICING_TABLES",
    "get_pricing",
    "usd_for_tokens",
]
