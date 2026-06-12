"""Stratified sampling (Q2/Q3, 2026-05-09): equal-per-stratum, deterministic seed."""

from __future__ import annotations

import random
from typing import Any

from g3o.run.presweep.config import STRATIFY_KEYS


def stratified_sample(
    rows: list[dict[str, Any]],
    *,
    sample_size: int,
    seed: int,
    stratify_keys: tuple[str, ...] = STRATIFY_KEYS,
) -> list[dict[str, Any]]:
    """Equal-per-stratum stratified random sample with deterministic seeding.

    When ``n_strata >= sample_size`` the sample takes one row from each of
    ``sample_size`` randomly-chosen strata. Otherwise each stratum gets a
    quota of ``sample_size // n_strata`` (with remainder distributed to a
    randomly-chosen subset), and any deficit (strata too small to fill their
    quota) is redistributed round-robin to strata that still have rows.
    """
    if sample_size <= 0:
        return []
    rng = random.Random(seed)
    strata: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for r in rows:
        key = tuple(r.get(k, "") for k in stratify_keys)
        strata.setdefault(key, []).append(r)
    if not strata:
        return []
    keys = sorted(strata.keys())
    rng.shuffle(keys)
    for k in keys:
        rng.shuffle(strata[k])
    n_strata = len(keys)
    if n_strata >= sample_size:
        return [strata[k][0] for k in keys[:sample_size]]
    base, rem = divmod(sample_size, n_strata)
    quotas = {k: base + (1 if i < rem else 0) for i, k in enumerate(keys)}
    picked: list[dict[str, Any]] = []
    deficit = 0
    for k in keys:
        avail = strata[k]
        take = min(quotas[k], len(avail))
        picked.extend(avail[:take])
        deficit += quotas[k] - take
        strata[k] = avail[take:]
    while deficit > 0:
        progressed = False
        for k in keys:
            if deficit == 0:
                break
            if strata[k]:
                picked.append(strata[k][0])
                strata[k] = strata[k][1:]
                deficit -= 1
                progressed = True
        if not progressed:
            break
    return picked
