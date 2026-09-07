"""Stratified draws: per-country caps and per-level floors, allocated then drawn.

The proportional draw in :mod:`g3o.run.frame.build` answers "what does the master
look like". This module answers a different question — "what does the PI want the
wave to look like" — and the two are deliberately separate calls rather than one
call with a flag, because a frame built under a quota is not a sample of the
master and nothing downstream should be able to mistake it for one.

**Why quotas exist here at all.** PI ruling, 2026-08-26 evening: wave 2 is 5,000
Anglophone + 5,000 mix, with the mix weighted for representation on two axes —
"not ~37% india, not ~90% local". A cap bounds the first axis and a floor bounds
the second. Neither can be expressed by drawing uniformly from a pool, which is
the only thing the proportional builder does.

**The allocation is two-dimensional and the two dimensions fight.** A country cap
concentrates a stratum into few countries; a level floor disperses it across many,
because the national and first-subnational tiers hold only a few dozen rows per
country. Filling a floor by reaching across every country in the pool would put
nearly every language on earth into the run, which is the phase-3 sourcing bill.
So floors are filled **inside the stratum's own country list**, and that list is
part of the ruled spec rather than something this code infers.

**Order matters and is fixed.** Levels are allocated scarcest-first (by total
availability, ties by name), each level decrementing the per-country cap budget
that later levels see. Allocating ``local`` first would spend every country's cap
on the abundant tier and leave the floors unfillable — the same 5,000 rows, and a
refusal instead of a frame.

**Refusal, not short-drawing**, exactly as :func:`g3o.run.frame.sampler.draw`:
an unfillable quota raises with the numbers that made it unfillable, because a
stratum delivered 40 rows light is indistinguishable downstream from a stratum
that was drawn correctly and lost 40 institutions in the pipeline.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from g3o.run.frame.sampler import FrameError, draw_uniform

#: Levels named in ``government_level``, scarcest first as it happens — but the
#: allocator sorts by measured availability rather than trusting this order.
KNOWN_LEVELS: tuple[str, ...] = (
    "national",
    "first_subnational",
    "second_subnational",
    "local",
)

#: Spec shape version, recorded in the sidecar. Bump when a field changes meaning.
QUOTA_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class StratumSpec:
    """One ruled stratum: which countries, how many, and under what bounds.

    ``countries`` is an explicit ISO3 list rather than a rule, because "which
    countries are Anglophone" is a substantive definition the master cannot
    supply — there is no language column — and a published measurement should
    carry the list it actually used, not a predicate that reproduces it.

    ``country_cap`` is a maximum across *all* levels, not per level. A per-level
    cap reads more symmetric and is stricter than the ruling: at 10% it makes the
    650-row second-subnational floor unfillable in a twelve-country mix, because
    two of those countries hold no second-subnational rows at all.
    """

    name: str
    countries: tuple[str, ...]
    size: int
    country_cap: int
    level_floors: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.size <= 0:
            raise FrameError(f"stratum {self.name!r}: size must be positive, got {self.size}")
        if not self.countries:
            raise FrameError(f"stratum {self.name!r}: no countries listed")
        if len(set(self.countries)) != len(self.countries):
            raise FrameError(f"stratum {self.name!r}: duplicate country in the list")
        if self.country_cap <= 0:
            raise FrameError(
                f"stratum {self.name!r}: country_cap must be positive, got {self.country_cap}"
            )
        floor_total = sum(self.level_floors.values())
        if floor_total > self.size:
            raise FrameError(
                f"stratum {self.name!r}: level floors sum to {floor_total:,}, which "
                f"exceeds the stratum size of {self.size:,}."
            )
        if self.country_cap * len(self.countries) < self.size:
            raise FrameError(
                f"stratum {self.name!r}: a cap of {self.country_cap:,} across "
                f"{len(self.countries)} countries can supply at most "
                f"{self.country_cap * len(self.countries):,}, short of {self.size:,}. "
                f"Raise the cap or widen the country list."
            )

    def as_dict(self) -> dict[str, Any]:
        """The sidecar rendering — what was asked for, before anything was drawn."""
        return {
            "name": self.name,
            "size": self.size,
            "country_cap": self.country_cap,
            "level_floors": dict(self.level_floors),
            "countries": list(self.countries),
        }


def level_targets(
    availability: Mapping[str, int],
    *,
    size: int,
    level_floors: Mapping[str, int],
) -> dict[str, int]:
    """How many institutions each level owes, before countries are considered.

    Floored levels take their floor exactly — a floor is a quota, not a minimum
    that the residual is then allowed to overshoot, because "at least 200
    national" and "as many national as fall out" are different instruments and
    only the first is reproducible. The remainder goes to the unfloored levels in
    proportion to what the pool holds, by largest remainder.
    """
    unknown = set(level_floors) - set(availability)
    if unknown:
        raise FrameError(
            f"level floors name levels absent from the pool: {sorted(unknown)}. "
            f"Available levels: {sorted(availability)}."
        )
    for level, floor in level_floors.items():
        if floor > availability[level]:
            raise FrameError(
                f"level floor {level}={floor:,} exceeds the {availability[level]:,} "
                f"rows this stratum's countries hold at that level."
            )
    targets = {level: int(floor) for level, floor in level_floors.items()}
    residual = size - sum(targets.values())
    rest = {lv: n for lv, n in availability.items() if lv not in targets and n > 0}
    if residual < 0:  # pragma: no cover - StratumSpec.__post_init__ rejects this
        raise FrameError(f"level floors exceed the stratum size by {-residual:,}")
    if residual == 0:
        return {lv: targets.get(lv, 0) for lv in availability}
    if not rest:
        raise FrameError(
            f"{residual:,} institutions remain after the level floors, and every "
            f"other level is empty in this stratum's countries."
        )
    total = sum(rest.values())
    exact = {lv: residual * n / total for lv, n in rest.items()}
    share = {lv: int(v) for lv, v in exact.items()}
    leftover = residual - sum(share.values())
    for lv in sorted(rest, key=lambda lv: (-(exact[lv] - share[lv]), lv))[:leftover]:
        share[lv] += 1
    for lv, n in share.items():
        if n > availability[lv]:
            raise FrameError(
                f"level {lv} was allocated {n:,} but this stratum's countries hold "
                f"only {availability[lv]:,} there."
            )
        targets[lv] = targets.get(lv, 0) + n
    return {lv: targets.get(lv, 0) for lv in availability}


def allocate_level(
    headroom: Mapping[str, int],
    weights: Mapping[str, int],
    target: int,
) -> dict[str, int]:
    """Spread ``target`` across countries in proportion to ``weights``, capped.

    **Capped-proportional, ruled by the PI 2026-08-26 over the alternative.** The
    two differ only in what the shares track, and the difference is the whole
    character of the stratum:

    * ``weights`` = the country's *uncapped* pool at this level — shares track
      the world's distribution and the cap clips only the top. India, Indonesia,
      France and Germany land on the ceiling; Uzbekistan lands at 5.5%.
    * ``weights`` = the country's *headroom* — the cap collapses every large
      country to the same value, so the allocation converges on equal-per-country
      and Uzbekistan lands at 8.8%, indistinguishable from India.

    The second reading was built first and rejected: it turns a ceiling into an
    equalisation, which is a stronger claim than the ruling makes. Passing
    ``weights`` explicitly is what keeps that choice visible at every call site
    instead of buried in a default.

    Water-filling, and here the loop genuinely fires: a pool-proportional share
    routinely exceeds a capped country's headroom, so the excess is clipped and
    redistributed among the countries that still have room. Each pass places at
    least one institution, so it terminates. Fractions settle by largest
    remainder with ISO3 as the tiebreak — no rng touches the allocation, only the
    draw that follows it.
    """
    if target < 0:
        raise ValueError(f"target must be >= 0, got {target}")
    missing = {c for c, n in headroom.items() if n > 0} - set(weights)
    if missing:
        raise ValueError(f"no weight given for {sorted(missing)}")
    alloc: dict[str, int] = {c: 0 for c in headroom}
    left = {c: int(n) for c, n in headroom.items() if n > 0}
    if target > sum(left.values()):
        raise FrameError(
            f"cannot place {target:,} institutions: the countries in this stratum "
            f"offer {sum(left.values()):,} here once their caps are applied."
        )
    remaining = target
    while remaining > 0:
        active = {c: max(int(weights[c]), 1) for c, n in left.items() if n > 0}
        if not active:  # pragma: no cover - the size check above forecloses this
            raise FrameError(f"cannot place {remaining:,} more institutions.")
        capacity = sum(left[c] for c in active)
        if capacity <= remaining:
            for country in active:
                alloc[country] += left[country]
                remaining -= left[country]
                left[country] = 0
            continue
        total_w = sum(active.values())
        exact = {c: remaining * w / total_w for c, w in active.items()}
        take = {c: int(v) for c, v in exact.items()}
        leftover = remaining - sum(take.values())
        for country in sorted(active, key=lambda c: (-(exact[c] - int(exact[c])), c))[:leftover]:
            take[country] += 1
        for country, want in take.items():
            placed = min(want, left[country])
            alloc[country] += placed
            left[country] -= placed
            remaining -= placed
    return alloc


def allocate_stratum(
    spec: StratumSpec,
    availability: Mapping[tuple[str, str], int],
) -> dict[tuple[str, str], int]:
    """Turn one ruled stratum into a per-``(country, level)`` draw plan.

    ``availability`` counts never-inspected rows per cell; cells outside
    ``spec.countries`` are ignored rather than rejected, so one pool scan can
    serve every stratum.

    It said "never-inspected, **non-duplicate**" until 2026-08-30. That half was
    wrong from the moment PR #99 landed and is corrected rather than softened,
    because it is precisely the sentence that would re-seed the defect that PR
    removed: the master's ``duplicate`` column flags a *name* collision that
    ``disambiguation`` resolves, not a repeated row, and reading it as an
    eligibility test cost every wave 30% of the master. Behaviour here was always
    correct — :func:`classify_master_cells` builds ``availability`` and has never
    consulted that column — so this is a comment fix and nothing else.
    """
    countries = list(spec.countries)
    cells = {
        (c, lv): int(n)
        for (c, lv), n in availability.items()
        if c in spec.countries and n > 0
    }
    by_level: dict[str, int] = {}
    for (_c, lv), n in cells.items():
        by_level[lv] = by_level.get(lv, 0) + n
    if not by_level:
        raise FrameError(
            f"stratum {spec.name!r}: none of its {len(countries)} countries hold a "
            f"never-inspected institution."
        )
    pool_total = sum(by_level.values())
    if pool_total < spec.size:
        raise FrameError(
            f"stratum {spec.name!r}: its countries hold {pool_total:,} "
            f"never-inspected institutions, short of the {spec.size:,} requested. "
            f"Refusing rather than short-drawing."
        )
    targets = level_targets(by_level, size=spec.size, level_floors=spec.level_floors)
    cap_left = {c: spec.country_cap for c in countries}
    plan: dict[tuple[str, str], int] = {}
    # Scarcest level first: a floor on a thin tier has to claim its share of the
    # cap budget before `local` spends it.
    for level in sorted(by_level, key=lambda lv: (by_level[lv], lv)):
        want = targets.get(level, 0)
        if want <= 0:
            continue
        headroom = {
            c: min(cells.get((c, level), 0), cap_left[c])
            for c in countries
            if cells.get((c, level), 0) > 0 and cap_left[c] > 0
        }
        # Weights are the UNCAPPED pool: shares track the world, the cap clips
        # the top. See allocate_level for the alternative and why it was refused.
        weights = {c: cells[(c, level)] for c in headroom}
        try:
            placed = allocate_level(headroom, weights, want)
        except FrameError as exc:
            raise FrameError(
                f"stratum {spec.name!r}, level {level!r}: {exc} "
                f"(wanted {want:,}; {sum(headroom.values()):,} placeable under a "
                f"cap of {spec.country_cap:,}/country)"
            ) from exc
        for country, n in placed.items():
            if n:
                plan[(country, level)] = n
                cap_left[country] -= n
    drawn = sum(plan.values())
    if drawn != spec.size:  # pragma: no cover - allocate_level raises first
        raise FrameError(
            f"stratum {spec.name!r}: allocation produced {drawn:,} of {spec.size:,}."
        )
    return plan


def draw_plan(
    rng: random.Random,
    plan: Mapping[tuple[str, str], int],
    cell_rows: Mapping[tuple[str, str], Sequence[int]],
) -> list[int]:
    """Draw the planned count out of each cell, then shuffle the frame as a whole.

    Cells are visited in sorted order so the rng sees the same call sequence on
    every run. The final shuffle is what keeps :mod:`g3o.run.frame.build`'s
    promise that **any prefix of the frame is itself an unbiased sample** — of
    the frame, which under a quota is not the same thing as a sample of the
    master, and the sidecar says so.
    """
    picked: list[int] = []
    for cell in sorted(plan):
        rows = cell_rows.get(cell, ())
        want = plan[cell]
        if want > len(rows):  # pragma: no cover - allocate_stratum clips to availability
            raise FrameError(
                f"cell {cell} was planned for {want:,} rows but holds {len(rows):,}."
            )
        picked.extend(rows[i] for i in draw_uniform(rng, len(rows), want))
    order = draw_uniform(rng, len(picked), len(picked))
    return [picked[i] for i in order]


__all__ = [
    "KNOWN_LEVELS",
    "QUOTA_SCHEMA_VERSION",
    "StratumSpec",
    "allocate_level",
    "allocate_stratum",
    "draw_plan",
    "level_targets",
]
