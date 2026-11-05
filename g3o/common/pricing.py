"""Shared pricing constants for LLM API models, keyed by model id.

Single source of truth for the rates used by both preflight projections
(:mod:`g3o.run.preflight`) and runtime cost monitoring
(:mod:`g3o.common.cost_monitor`). Import from here.

**Why this is a registry rather than one dict** (review F2, 2026-08-24). Until
today every USD figure in the pipeline — the preflight projection that gates
spend, the running total that trips ``BudgetExceededError``, and the persisted
``_cost_report.json`` — came from a single hard-coded ``gpt-5-nano`` table,
while the model actually submitted is freely settable three ways (``--model``,
``OPENAI_MODEL`` in the environment or ``.env``, or ``PresweepConfig.model``).
Nothing compared the two. So a one-word config change silently priced a whole
run at nano rates and the cost report labelled the result ``"gpt-5-nano"``
regardless of what had run.

The sharp version, worth keeping because it explains how this survived a
codebase otherwise careful about exactly this: ``g3o verify-model`` already
submits a live one-job batch to confirm a model id, so the system *did* validate
the model — it validated that **OpenAI would accept it**, and never that **we
could price it**. A check that exists is what makes the missing one invisible.

**The rule the callers implement** (PI ruling, 2026-08-24), stated here because
this module deliberately does not implement it — :func:`pricing_for` returns
``None`` for an unknown model and lets each caller decide:

1. A run with a **budget ceiling set** and a model with no row **refuses to
   start**. An unpriceable model cannot be gated, and pricing it as nano is the
   defect above.
2. A run **without** a ceiling proceeds, but records the **real model id and
   null USD** — never a fabricated total. Attesting to a number that was never
   incurred is the half that contaminates the cost evidence.

There is deliberately no "assume nano" fallback and no ``--allow-unpriced-model``
escape hatch: the first is the defect, and the second buys nothing when a ceiling
is normally set while putting a flag in the argv of precisely the runs we would
least like to find a flag in.

**Adding a model** means adding a row with its own verified rates and its own
``verified_on``. Do not copy a sibling's numbers across — the whole point is that
a row asserts what was checked, on what date, against ``source``.
"""

from __future__ import annotations

import re
from typing import Any

# gpt-5-nano standard rates are published FACTS (model page in `source` below).
# The Batch API rates apply OpenAI's documented 50% Batch discount — shown
# verbatim on the same pricing page for the sibling gpt-5.4-nano ($0.20→$0.10
# input) — so the batch line is labeled ESTIMATE-grade: the nano model page does
# not print the batch row itself.
#
# Provenance note: the gpt-5-nano model page publishes standard rates but does
# not list a Batch API row. The batch discount is inferred from the sibling
# gpt-5.4-nano model, where OpenAI explicitly documents the 50% discount on the
# same pricing page. This inference is why the batch rates are labeled as
# estimates — trustworthy by analogy to a sibling model's published discount,
# but not independently confirmed for gpt-5-nano. Reconcile against the first
# live invoice.
#
# Re-verified 2026-08-24 against `source`: the three standard rates are
# unchanged from the 2026-06-10 reading, and the page still publishes no Batch
# row — so `batch_line_is_estimate` remains true rather than being a stale
# caveat nobody rechecked. The cached-rate reconciliation still needs a live
# invoice and has not happened.
_GPT5_NANO: dict[str, Any] = {
    "model": "gpt-5-nano",
    "source": "https://developers.openai.com/api/docs/models/gpt-5-nano",
    "verified_on": "2026-08-24",
    "standard_input_per_1m_usd": 0.05,
    "standard_cached_input_per_1m_usd": 0.005,
    "standard_output_per_1m_usd": 0.40,
    "batch_discount": 0.50,
    "batch_input_per_1m_usd": 0.025,  # estimate: 50% of standard input
    "batch_output_per_1m_usd": 0.20,  # estimate: 50% of standard output
    "batch_cached_input_per_1m_usd": 0.0025,  # estimate: standard_cached * batch_discount; reconcile against first live invoice
    "batch_line_is_estimate": True,
}

# TypeSafe jev-1.13.0 rates (docs.typesafe.ai/models, verified 2026-09-20).
# Jev is a decision model with input-only pricing: $0.042 per Mtok input;
# output tokens are free. No batch discount (the API is synchronous only,
# no batch endpoint). No cached tokens (the API does not expose prompt caching).
# The shape differs from the OpenAI row (no batch_* keys, no cached rate)
# because jev's pricing model is simpler; pricing_for() and CostMonitor
# handle both shapes.
_JEV_1_13_0: dict[str, Any] = {
    "model": "jev-1.13.0",
    "source": "https://docs.typesafe.ai/models",
    "verified_on": "2026-09-20",
    "standard_input_per_1m_usd": 0.042,
    "standard_output_per_1m_usd": 0.00,
    # Jev has no batch API (synchronous only) and no prompt caching; the
    # batch_* keys mirror the standard rates so CostMonitor's arithmetic
    # works unchanged. No batch discount, no cached rate.
    "batch_input_per_1m_usd": 0.042,
    "batch_output_per_1m_usd": 0.00,
    "batch_cached_input_per_1m_usd": 0.042,
    "batch_discount": 1.0,
    "batch_line_is_estimate": False,
}

# Claude Haiku 5.5 rates, the v2.7 extractor (RC-D-001 A). Published FACTS on
# https://platform.claude.com/docs/en/about-claude/pricing (verified 2026-11-05;
# docs.claude.com redirects there). The model id is from the "Claude API ID" row
# of https://platform.claude.com/docs/en/about-claude/models/overview: it is
# dateless and is its own pinned snapshot, so no dated alias exists to match.
#
# Haiku 5.5 is priced by prompt length. Verbatim from the pricing page:
#   "Claude Haiku 5.5 (for prompts up to 100,000 tokens) | $0.10 / MTok |
#    $0.125 / MTok | $0.20 / MTok | $0.01 / MTok | $0.50 / MTok"
#   "Claude Haiku 5.5 (for prompts over 100,000 tokens) | $0.50 / MTok |
#    $0.625 / MTok | $1 / MTok | $0.05 / MTok | $2.50 / MTok"
# (columns: base input, 5m cache write, 1h cache write, cache hit, output), and
# the batch table: "$0.05 / MTok | $0.25 / MTok" (up to 100k) and
# "$0.25 / MTok | $1.25 / MTok" (over 100k). "A request's prompt length counts
# all of its input tokens, including cache reads and cache writes. Each request
# is priced on its own."
#
# The flat batch_* keys (the only keys CostMonitor reads) carry the up-to-100k
# tier, the tier a request pays unless its own prompt exceeds the threshold.
# CostMonitor sums tokens across requests, so it cannot see per-request prompt
# length and would under-price any request over 100k tokens; pricing each
# request with :func:`anthropic_request_usd` (which applies the tier) is the
# exact method. The batch cache rates are not printed as a row: they apply the
# page's statement that cache multipliers "stack with other pricing modifiers,
# including the Batch API discount" (cache hit 0.01 x 0.5 = 0.005). US-only
# inference (``inference_geo``) adds a 1.1x multiplier not modelled here; the
# extractor does not set it.
_HAIKU_5_5_TIERS: dict[str, dict[str, float]] = {
    "up_to_threshold": {
        "standard_input_per_1m_usd": 0.10,
        "standard_cache_write_5m_per_1m_usd": 0.125,
        "standard_cache_write_1h_per_1m_usd": 0.20,
        "standard_cached_input_per_1m_usd": 0.01,
        "standard_output_per_1m_usd": 0.50,
        "batch_input_per_1m_usd": 0.05,
        "batch_cache_write_5m_per_1m_usd": 0.0625,
        "batch_cache_write_1h_per_1m_usd": 0.10,
        "batch_cached_input_per_1m_usd": 0.005,
        "batch_output_per_1m_usd": 0.25,
    },
    "over_threshold": {
        "standard_input_per_1m_usd": 0.50,
        "standard_cache_write_5m_per_1m_usd": 0.625,
        "standard_cache_write_1h_per_1m_usd": 1.00,
        "standard_cached_input_per_1m_usd": 0.05,
        "standard_output_per_1m_usd": 2.50,
        "batch_input_per_1m_usd": 0.25,
        "batch_cache_write_5m_per_1m_usd": 0.3125,
        "batch_cache_write_1h_per_1m_usd": 0.50,
        "batch_cached_input_per_1m_usd": 0.025,
        "batch_output_per_1m_usd": 1.25,
    },
}
_HAIKU_5_5: dict[str, Any] = {
    "model": "claude-haiku-5-5",
    "source": "https://platform.claude.com/docs/en/about-claude/pricing",
    "verified_on": "2026-11-05",
    **_HAIKU_5_5_TIERS["up_to_threshold"],
    "batch_discount": 0.50,
    "batch_line_is_estimate": False,
    # Strictly "over 100,000 tokens" pays the higher tier.
    "long_prompt_threshold_tokens": 100_000,
    "tiers": _HAIKU_5_5_TIERS,
}

#: Model id -> its rate row. Every row carries the flat key set above; the shape
#: is unchanged from the pre-registry single dict, which is what keeps every
#: ``pricing[...]`` subscript in :mod:`g3o.common.cost_monitor` working.
PRICING: dict[str, dict[str, Any]] = {
    _GPT5_NANO["model"]: _GPT5_NANO,
    _JEV_1_13_0["model"]: _JEV_1_13_0,
    _HAIKU_5_5["model"]: _HAIKU_5_5,
}

#: Back-compatible alias for the row this pipeline runs on by default. Kept as a
#: live reference into :data:`PRICING` (not a copy) so the two cannot drift.
GPT5_NANO_PRICING: dict[str, Any] = PRICING["gpt-5-nano"]
#: Back-compatible alias for the jev-1.13.0 rate row. Kept as a live reference
#: into :data:`PRICING` (not a copy) so the two cannot drift.
JEV_1_13_0_PRICING: dict[str, Any] = PRICING["jev-1.13.0"]
#: Live reference to the Claude Haiku 5.5 rate row (v2.7 extractor).
HAIKU_5_5_PRICING: dict[str, Any] = PRICING["claude-haiku-5-5"]

# ── Metered (non-token) APIs (PI ruling 2026-10-02) ─────────────────────────
# Serper and the Bright Data Web Unlocker bill per unit, not per token, so they
# are not rows in PRICING (which is keyed by model id and read by token
# arithmetic). Until 2026-10-02 neither was priced anywhere in code, so
# ``G3O_BUDGET_LIMIT_USD`` capped only LLM spend while Stage 1 and Stage 4
# spent on separate bills. The PI ruled that one combined ceiling covers every
# paid API; these two rows are what make that ceiling enforceable.
#
# Serper: $0.001 per credit (PI, 2026-10-02: "depends on how much I pre-buy,
# for now let's keep $0.001"). The rate varies with the pre-bought package, so
# ``G3O_SERPER_USD_PER_CREDIT`` overrides it without a code change. One credit
# per query at ``num=10``; the live response carries a ``credits`` field
# (verified 2026-10-02), which the client meters rather than assuming 1.
SERPER_PRICING: dict[str, Any] = {
    "api": "serper",
    "unit": "credit",
    "usd_per_unit": 0.001,
    "source": "PI ruling 2026-10-02; package-dependent, see docs/budget/cost-model.md",
    "verified_on": "2026-10-02",
    "is_estimate": True,
}

# Bright Data Web Unlocker: $8 per GB, billed on successful requests only (PI,
# 2026-10-02). Bytes are the response body the API returned; Bright Data's own
# byte count (headers, compression) is not visible to us, so this is an
# estimate to reconcile against the first invoice. 1 GB = 10^9 bytes, the
# reading that prices higher of the two and so keeps the ceiling conservative.
UNLOCKER_PRICING: dict[str, Any] = {
    "api": "brightdata_unlocker",
    "unit": "GB",
    "usd_per_unit": 8.0,
    "bytes_per_unit": 1_000_000_000,
    "billing": "successful requests only",
    "source": "PI ruling 2026-10-02 (Bright Data account rate)",
    "verified_on": "2026-10-02",
    "is_estimate": True,
}


def serper_usd(credits: float) -> float:
    """USD for ``credits`` Serper credits, honouring the env override."""
    from g3o.common import config

    rate = config.SERPER_USD_PER_CREDIT
    if rate is None:
        rate = SERPER_PRICING["usd_per_unit"]
    return credits * rate


def unlocker_usd(n_bytes: float) -> float:
    """USD for ``n_bytes`` of billable Web Unlocker response body."""
    return (n_bytes / UNLOCKER_PRICING["bytes_per_unit"]) * UNLOCKER_PRICING["usd_per_unit"]


#: A dated model snapshot, e.g. ``gpt-5-nano-2025-08-07`` — the form
#: ``BatchResult.response_model`` actually returns. Matched against a known base
#: id so a run pinned to a snapshot prices off its base row.
_SNAPSHOT_SUFFIX = r"-\d{4}-\d{2}-\d{2}"


def pricing_for(model: str) -> dict[str, Any] | None:
    """The rate row for ``model``, or ``None`` when we cannot price it.

    Resolution is exact-match first, then a **dated snapshot** of a known base id
    (``gpt-5-nano-2025-08-07`` -> ``gpt-5-nano``). The snapshot rule is
    deliberately narrow — a bare prefix test would price a genuinely different
    model like ``gpt-5-nano-turbo`` off the nano row, which is the same class of
    silent mispricing this registry exists to remove. Longest base id wins, so a
    more specific row always beats a more general one.

    Returns ``None`` rather than raising, and never falls back to a default row:
    the caller decides what an unpriced model means, and the two answers differ
    (see the module docstring). ``None`` means "we do not know", which is a fact
    worth propagating — not zero, and not nano.
    """
    row = PRICING.get(model)
    if row is not None:
        return row
    matches = [
        base
        for base in PRICING
        if re.fullmatch(re.escape(base) + _SNAPSHOT_SUFFIX, model)
    ]
    if not matches:
        return None
    return PRICING[max(matches, key=len)]


def usd(n_tokens: float, per_1m: float) -> float:
    """Convert token count to USD cost given per-1M-token rate.

    Single-source helper shared by :mod:`g3o.common.cost_monitor` and
    :mod:`g3o.run.preflight` so both compute cost identically.
    """
    return (n_tokens / 1_000_000) * per_1m


def anthropic_request_usd(
    usage: dict[str, Any], row: dict[str, Any], *, batch: bool = True
) -> float:
    """USD for one Anthropic Messages request from its response ``usage``.

    ``usage`` is the response usage dict (``input_tokens``, ``output_tokens``,
    ``cache_read_input_tokens``, ``cache_creation_input_tokens``, optionally a
    ``cache_creation`` breakdown with ``ephemeral_5m_input_tokens`` /
    ``ephemeral_1h_input_tokens``). In Anthropic usage, ``input_tokens``
    excludes cache reads and writes. Missing or ``None`` counts are 0.

    A row with ``tiers`` is priced on this request's own prompt length (input
    + cache reads + cache writes) against ``long_prompt_threshold_tokens``. Cache
    writes without a breakdown are priced at the 5-minute write rate.
    """

    def n(value: Any) -> int:
        return int(value or 0)

    inp = n(usage.get("input_tokens"))
    out = n(usage.get("output_tokens"))
    read = n(usage.get("cache_read_input_tokens"))
    write = n(usage.get("cache_creation_input_tokens"))
    breakdown = usage.get("cache_creation") or {}
    write_1h = n(breakdown.get("ephemeral_1h_input_tokens"))
    write_5m = max(0, write - write_1h)

    rates = row
    tiers = row.get("tiers")
    if tiers is not None:
        prompt = inp + read + write
        over = prompt > row["long_prompt_threshold_tokens"]
        rates = tiers["over_threshold" if over else "up_to_threshold"]
    p = "batch_" if batch else "standard_"
    return (
        usd(inp, rates[f"{p}input_per_1m_usd"])
        + usd(read, rates[f"{p}cached_input_per_1m_usd"])
        + usd(write_5m, rates[f"{p}cache_write_5m_per_1m_usd"])
        + usd(write_1h, rates[f"{p}cache_write_1h_per_1m_usd"])
        + usd(out, rates[f"{p}output_per_1m_usd"])
    )


__all__ = [
    "GPT5_NANO_PRICING",
    "HAIKU_5_5_PRICING",
    "JEV_1_13_0_PRICING",
    "PRICING",
    "SERPER_PRICING",
    "UNLOCKER_PRICING",
    "anthropic_request_usd",
    "pricing_for",
    "serper_usd",
    "unlocker_usd",
    "usd",
]
