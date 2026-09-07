"""The draw itself: eligibility, tier 1 (uniform), tier 2 (recency-weighted).

Two properties are load-bearing here and both are asserted by tests.

**Determinism.** Every draw is a pure function of ``(pool order, size, seed)``.
The shuffles are written out longhand rather than delegated to
``random.sample``/``random.shuffle`` so the frame does not silently change shape
if CPython changes its selection algorithm — a frame is an input to a published
measurement, and "it reproduced on the interpreter I happened to have" is not
reproducibility. Only ``Random.randrange`` and ``Random.random`` are relied on,
both of which are pinned by the Mersenne Twister the seed feeds.

**Refusal.** :func:`draw` raises rather than short-drawing. A request for 10,000
answered with 9,412 rows looks identical downstream to a full frame with 588
failures, and the pipeline has already produced one class of defect that way.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Any

#: ``duplicate`` values that assert a NAME COLLISION. Everything else —
#: including ``''``, ``'0'`` and NULL — asserts none. The published master
#: carries all three of ``''``, ``'0'`` and ``'1'``, so a bare truthiness test on
#: this column would misread the 19,766 rows that are blank.
NAME_COLLISION_TRUE = frozenset({"1", "true", "t", "yes", "y"})

#: Recency weights are floored here (one hour) so an institution inspected at the
#: snapshot moment still carries a positive weight instead of being unselectable.
MIN_AGE_SECONDS = 3600.0


class FrameError(RuntimeError):
    """A frame could not be built as requested. Never raised for a short draw."""


def has_colliding_name(row: dict[str, Any]) -> bool:
    """True when ``row``'s ``duplicate`` column asserts a NAME collision.

    **The column does not mean the row is a duplicate row, and reading it that
    way was a defect** (PI ruling, 2026-08-30). The master's own schema
    (``docs/institution_master_schema.csv``) defines it as *"1 = duplicate name
    (needs disambiguation); 0 = unique"*, set by the subnational RA track when a
    unit's name collides within its ``(country, tier)``. The codebook's
    ``duplicate``/``disambiguation`` section is explicit about the consequence:
    *"two units with identical name but different disambiguation are both
    kept."*

    They are distinct institutions. G3O's own discovery layer already knows it —
    :func:`g3o.discovery.query_builder` builds a disambiguation-qualified query
    precisely for these rows — so excluding them here handed discovery a
    population it was written to serve and then never served it.

    Kept as a named predicate rather than deleted: which rows carry a collision
    is a real composition fact about a frame, it is reported in the sidecar, and
    a future caller may legitimately want to stratify on it. What it must never
    again be is an eligibility test.
    """
    return (row.get("duplicate") or "").strip().lower() in NAME_COLLISION_TRUE


def is_eligible(row: dict[str, Any]) -> bool:
    """True when ``row`` may be drawn into a wave frame. Today: every row.

    The function stays even though it has no rejecting branch left, because the
    two things it does *not* test are both mistakes someone has already made
    once, and a bare ``True`` records neither.

    **Not a website.** Deliberately *not* the same predicate as
    :func:`g3o.run.presweep.eval_frame.is_eligible`, which also requires a
    plausible ``website``. Only 2.0% of the master carries one, and Stage 1
    discovers from the institution name: on the published run the 605
    no-website institutions reached validate at 67.8% against 73.6% for the
    rest — six points worse, not a different regime. Requiring a website here
    would silently restrict every wave to 14,670 rows, 10,811 of them US school
    districts.

    **Not a name collision.** Until 2026-08-30 this returned
    ``not is_duplicate(row)``, which dropped **216,642 of the master's 719,588
    rows (30.1%)** — every one of them a real institution, 216,575 of them
    carrying the very ``disambiguation`` string that exists to tell them apart.
    The loss was concentrated exactly where a wave most needs depth: 29.7% of
    the ``local`` tier, **44.7% of ``second_subnational``**, and 34.0% of India,
    46.4% of Uganda, 71.4% of Rwanda. Nothing at ``national`` or
    ``first_subnational`` was touched, which is part of why it stayed invisible.

    It stayed invisible for a second and larger reason: **no master row has both
    ``duplicate=1`` and a ``website`` (0 of 719,588, verified 2026-08-30)**, so
    for as long as a frame required a website the exclusion removed nothing at
    all. It became load-bearing the moment this module started drawing
    website-free frames — which the paragraph above argues for on its own,
    entirely sound, grounds. Two correct decisions met and produced a wrong one.
    """
    return True


def draw_uniform(rng: random.Random, n_pool: int, size: int) -> list[int]:
    """``size`` distinct indices of ``range(n_pool)``, in draw order.

    A partial Fisher-Yates: each step swaps a uniformly chosen remaining index
    into position and emits it. Draw order is kept (rather than sorted) so that
    **any prefix of the frame is itself an unbiased sample** — a run that aborts
    or is truncated part-way still yields something measurable, where a
    master-ordered frame would have processed India first and nothing else.
    """
    if size < 0:
        raise ValueError(f"size must be >= 0, got {size}")
    if size > n_pool:
        raise ValueError(f"cannot draw {size} from a pool of {n_pool}")
    indices = list(range(n_pool))
    drawn: list[int] = []
    for i in range(size):
        j = i + rng.randrange(n_pool - i)
        indices[i], indices[j] = indices[j], indices[i]
        drawn.append(indices[i])
    return drawn


def draw_recency_weighted(
    rng: random.Random,
    weights: Sequence[float],
    size: int,
) -> list[int]:
    """``size`` distinct indices, sampled without replacement with probability
    proportional to ``weights`` — here, seconds since the last inspection.

    Efraimidis-Spirakis A-Res: draw ``u`` uniform per item and rank on
    ``log(u) / w``, largest first. Equivalent to ``u ** (1 / w)`` and stable for
    the large weights a multi-year gap produces. Ties break on the pool index, so
    equal weights degrade to a deterministic order rather than an arbitrary one.

    **This function is unexercised in production and will stay that way for a
    long time.** 715,977 of the master's 719,588 institutions have never been
    inspected, so tier 1 alone fills roughly the next 71 waves at n=10,000. It is
    written now because the PI ruled the sampler complete (2026-08-26, ruling 6),
    not because anything calls it. Treat its behaviour as tested-not-observed.
    """
    if size < 0:
        raise ValueError(f"size must be >= 0, got {size}")
    if size > len(weights):
        raise ValueError(f"cannot draw {size} from a pool of {len(weights)}")
    keyed: list[tuple[float, int]] = []
    for index, weight in enumerate(weights):
        w = max(float(weight), MIN_AGE_SECONDS)
        u = rng.random()
        # random() can return 0.0; log(0) is -inf, which sorts last — correct,
        # but it would also make the key independent of the weight. Nudge it
        # into the open interval instead.
        key = math.log(u if u > 0.0 else 5e-324) / w
        keyed.append((key, index))
    keyed.sort(key=lambda pair: (-pair[0], pair[1]))
    return [index for _key, index in keyed[:size]]


def draw(
    rng: random.Random,
    *,
    size: int,
    never_inspected: Sequence[int],
    reinspectable: Sequence[int],
    reinspectable_ages: Sequence[float],
) -> tuple[list[int], list[int]]:
    """The two-tier draw. Returns ``(tier1_indices, tier2_indices)``.

    Tier 1 is drawn uniformly from the never-inspected pool, which is what makes
    the frame proportional to the master. Tier 2 fires only for the shortfall,
    and never partially: if the two pools together cannot fill ``size``, this
    raises rather than returning what it has.
    """
    if size <= 0:
        raise FrameError(f"frame size must be positive, got {size}")
    available = len(never_inspected) + len(reinspectable)
    if size > available:
        raise FrameError(
            f"cannot build a frame of {size:,}: the eligible pool holds "
            f"{available:,} institutions ({len(never_inspected):,} never inspected, "
            f"{len(reinspectable):,} re-inspectable). Refusing rather than "
            f"short-drawing — a frame of {available:,} delivered as {size:,} is "
            f"indistinguishable downstream from a full frame that failed "
            f"{size - available:,} times."
        )
    if len(reinspectable) != len(reinspectable_ages):
        raise FrameError(
            f"re-inspectable pool and its ages disagree in length "
            f"({len(reinspectable)} vs {len(reinspectable_ages)})"
        )
    take_tier1 = min(size, len(never_inspected))
    tier1 = [never_inspected[i] for i in draw_uniform(rng, len(never_inspected), take_tier1)]
    shortfall = size - take_tier1
    if shortfall == 0:
        return tier1, []
    tier2 = [
        reinspectable[i]
        for i in draw_recency_weighted(rng, reinspectable_ages, shortfall)
    ]
    return tier1, tier2


__all__ = [
    "NAME_COLLISION_TRUE",
    "MIN_AGE_SECONDS",
    "FrameError",
    "draw",
    "draw_recency_weighted",
    "draw_uniform",
    "has_colliding_name",
    "is_eligible",
]
