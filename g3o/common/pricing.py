"""Shared pricing constants for OpenAI API models, keyed by model id.

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

#: Model id -> its rate row. Every row carries the flat key set above; the shape
#: is unchanged from the pre-registry single dict, which is what keeps every
#: ``pricing[...]`` subscript in :mod:`g3o.common.cost_monitor` working.
PRICING: dict[str, dict[str, Any]] = {
    _GPT5_NANO["model"]: _GPT5_NANO,
}

#: Back-compatible alias for the row this pipeline runs on by default. Kept as a
#: live reference into :data:`PRICING` (not a copy) so the two cannot drift.
GPT5_NANO_PRICING: dict[str, Any] = PRICING["gpt-5-nano"]

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


__all__ = ["GPT5_NANO_PRICING", "PRICING", "pricing_for", "usd"]
