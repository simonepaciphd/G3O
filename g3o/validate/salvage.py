"""Stage 6 pre-validation salvage: bookkeeping only.

Measured 2026-08-31 across five runs (``4cd7``, ``bb4e``, ``4fd3``, ``233a``,
``32ea``): Stage 6 discards **444 institutions** to
``ConsolidatedInstitutionResponse`` validation failures — 1.25%–2.90% of the
institutions that reach it. The discard is not random. On the 15k run, **80 of
the 126 rejected (63.5%)** carry at least one extract row tagged
``confirms_activity``, against **437 of 7,947 (5.50%)** among those that
consolidated: a **11.5×** enrichment. The mechanism is structural rather than
mysterious — every invariant that fails here (id sequencing, source back-link
counts, activity/source linkage, the yes/no/unclear consistency rules) is only
*reachable* once the model has activities and multiple sources to keep straight.
An institution with zero activities and one ``confirms_absence`` source cannot
trip any of them. **The gate can only fire on institutions that found
something**, and conversion among those is deterministic: 437 of 437
consolidated institutions with ≥1 ``confirms_activity`` extract row ended
``has_genai_activity=yes``.

So this module exists for the same reason :mod:`g3o.extract.salvage` does, one
stage later, and inherits that module's philosophy wholesale — read its docstring
first. What is added here is a narrower claim, and the narrowness is the point.

Repair, not relaxation — and the line is drawn at *derivability*
---------------------------------------------------------------

A repair belongs here only when the correct value is **recoverable from the
payload itself with no interpretive judgement**. Three qualify, and they are the
three implemented:

* ``source_id`` / ``activity_id`` **sequencing**. The contract requires
  ``S1, S2, …`` and ``A1, A2, …`` in order. A model that emits ``['S1', 'S1']``
  or ``['A1','A2','A3','A5','A4']`` has written every field correctly and
  labelled them wrongly. Renumbering positionally preserves every value, every
  field, and — because ``activity_id`` renumbering rewrites the sources that
  point at it through the same map — the entire activity↔source graph. Nothing
  in the schema references a ``source_id``, so source renumbering has no
  back-references to chase.
* ``n_sources``. Defined by the contract as the count of sources back-linking to
  the activity, so it is *redundant with the source list*. Recomputing it is
  derivation, not a decision. Dropping an institution's whole consolidation
  because a model miscounted a number the pipeline can count itself is the
  clearest case in the measured set: 20 of 126 on the 15k run.

Everything else in the measured failure set is left to fail, deliberately
---------------------------------------------------------------------

Named, with counts from the 15k run, because "we only fixed the easy ones" is a
criticism this module should answer in advance rather than absorb later:

* ``has_genai_activity=no`` with a non-``confirms_absence`` source (28). Either
  the institution-level verdict is wrong or the source's evidence tag is. Which
  one is a coding decision.
* ``activity_id=_NA_`` on a ``confirms_activity`` source (22). The repair is to
  link the source to an activity, and *which* activity is not in the payload.
* ``activity_id=Ax`` with ``genai_evidence != confirms_activity`` (16). Same
  shape, opposite direction: unlinking or retagging are both re-codings.
* Orphan activities — an activity with no supporting source (13). The mechanical
  repair is to drop the activity, and that is available here as
  :func:`salvage_orphan_activities`, but it is **not in**
  :data:`DEFAULT_REPAIRS`. Dropping an activity deletes a finding rather than
  restoring bookkeeping, and when it is the institution's *only* activity the
  honest consequence is a verdict of ``unclear``, not the ``no`` that a silent
  drop would produce. That is a re-coding, it is the PI's, and it is one line to
  enable once ruled on.
* ``has_genai_activity=yes`` inconsistencies (5), ``_NA_`` in ``activity_name``
  (3), empty assistant content (8). The first is a verdict question; the second
  is already ruled unsalvageable in :mod:`g3o.extract.salvage`
  (``activity_name`` has no sanctioned sentinel, so supplying one is a naming
  decision) and that ruling is honoured rather than re-litigated here; the third
  has no payload to repair.

How much this recovers, stated as the bound it actually is
---------------------------------------------------------

By reported error class on the 15k run, the default set addresses **32 of the
126** rejections (25.4%) — 20 ``n_sources``, 11 duplicate ``source_id``, 1
out-of-order ``activity_id`` — and 45 (35.7%) with
:func:`salvage_orphan_activities` enabled.

**That is an upper bound on institutions actually recovered, not a count of
them.** Pydantic reports the *first* failing invariant and stops, so a payload
booked as one class may carry another behind it. The declared validator order is
yes/no/unclear → activity_id sequence → source_id sequence → source/activity
links → ``n_sources``, which sharpens the bound in one direction worth knowing:
``n_sources`` runs **last**, so all 20 of those payloads had already passed every
other invariant and will recover in full. The 11 source_id cases had passed the
verdict and activity_id checks but may still fail on links, which this module
deliberately does not repair.

The true rate is measurable from the next run onward rather than estimable:
:func:`g3o.validate.consolidate.write_rejected_output` now retains every rejected
payload, so what survives repair can be counted instead of inferred. Before
2026-08-31 it could not — the payloads were discarded, which is why this figure
is a bound at all.

Marker lives in the attrition ledger, not in the record
-------------------------------------------------------

As at Stage 5. A salvaged consolidation is indistinguishable in
``6_validate.json`` from one the model got right first time; what it did is
recorded against the institution in ``_attrition.jsonl`` under
:data:`REASON_BOOKKEEPING_SALVAGED`, keyed by institution id, with the specific
repairs named. Marking it in-band would edit the schema-of-record.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "DEFAULT_REPAIRS",
    "REASON_BOOKKEEPING_SALVAGED",
    "BookkeepingSalvage",
    "salvage_activity_id_sequence",
    "salvage_consolidation_bookkeeping",
    "salvage_n_sources",
    "salvage_orphan_activities",
    "salvage_source_id_sequence",
]

#: One reason code for the whole module, with the specific repairs in ``detail``.
#: Stage 5 uses one code per repair kind because its repairs fire on different
#: units (a row, a page); these all fire on the one institution and are reported
#: together, so a reader sees the full set of what was touched in one ledger row
#: rather than having to join three.
REASON_BOOKKEEPING_SALVAGED = "consolidation_bookkeeping_salvaged"

#: The literal the contract uses for "this source supports no activity".
_NA = "_NA_"


@dataclass(frozen=True)
class BookkeepingSalvage:
    """One repair applied to one institution's consolidation payload.

    ``kind`` is the repair; ``detail`` says what changed, in a form short enough
    for a ledger row and specific enough to reconstruct the edit — an id remap,
    or the activity whose count was corrected and from what to what.
    """

    kind: str
    detail: str


def _sources(payload: object) -> list[dict[str, object]] | None:
    """The source list, or ``None`` when the payload is not the expected shape.

    Defensive in the same way :func:`g3o.extract.salvage.salvage_group_d_na` is:
    a structurally malformed payload is the validator's to reject with a good
    message, not this module's to guess at.
    """
    if not isinstance(payload, dict):
        return None
    sources = payload.get("sources")
    if not isinstance(sources, list):
        return None
    if not all(isinstance(s, dict) for s in sources):
        return None
    return sources  # type: ignore[return-value]


def _activities(payload: object) -> list[dict[str, object]] | None:
    if not isinstance(payload, dict):
        return None
    activities = payload.get("activities")
    if not isinstance(activities, list):
        return None
    if not all(isinstance(a, dict) for a in activities):
        return None
    return activities  # type: ignore[return-value]


def salvage_source_id_sequence(payload: object) -> list[BookkeepingSalvage]:
    """Renumber ``sources[i].source_id`` to ``S{i+1}``, in place.

    Safe positionally and without a link rewrite because **nothing in the schema
    references a source_id**: ``ConsolidatedActivity`` carries ``n_sources``, a
    count, not a list of ids. Asserted in the tests rather than assumed, since
    the day that stops being true this function becomes wrong silently.

    The observed failure is duplication — ``['S1', 'S1']``, 11 of 126 on the 15k
    run — where the model wrote two complete, distinct sources and labelled both
    ``S1``.
    """
    sources = _sources(payload)
    if not sources:
        return []
    seen = [s.get("source_id") for s in sources]
    expected = [f"S{i + 1}" for i in range(len(sources))]
    if seen == expected:
        return []
    for i, s in enumerate(sources):
        s["source_id"] = expected[i]
    return [
        BookkeepingSalvage(
            kind="source_id_sequence", detail=f"{seen!r} -> {expected!r}"
        )
    ]


def salvage_activity_id_sequence(payload: object) -> list[BookkeepingSalvage]:
    """Renumber ``activities[i].activity_id`` to ``A{i+1}`` and rewrite the
    sources that point at it, in place.

    **Refuses on duplicates**, and that is the whole subtlety. Given
    ``['A1','A2','A3','A5','A4']`` the positional remap sends ``A5 -> A4`` and
    ``A4 -> A5``; applying the same map to every source's ``activity_id``
    preserves the graph exactly. Given ``['A1','A1']`` there is no map — two
    activities claim one label, and a source pointing at ``A1`` cannot be
    assigned to either without a judgement. So a duplicated activity_id is left
    to fail validation, as it should.
    """
    activities = _activities(payload)
    if not activities:
        return []
    seen = [a.get("activity_id") for a in activities]
    expected = [f"A{i + 1}" for i in range(len(activities))]
    if seen == expected:
        return []
    if len(set(seen)) != len(seen):
        # Ambiguous: see the docstring. No repair, no event — the institution
        # fails validation and its payload is retained by the caller.
        return []
    remap = {old: new for old, new in zip(seen, expected, strict=True) if old != new}
    for i, a in enumerate(activities):
        a["activity_id"] = expected[i]
    sources = _sources(payload) or []
    n_relinked = 0
    for s in sources:
        current = s.get("activity_id")
        if current in remap:
            s["activity_id"] = remap[current]
            n_relinked += 1
    return [
        BookkeepingSalvage(
            kind="activity_id_sequence",
            detail=f"{seen!r} -> {expected!r}; {n_relinked} source link(s) rewritten",
        )
    ]


def salvage_n_sources(payload: object) -> list[BookkeepingSalvage]:
    """Recompute each activity's ``n_sources`` from its actual back-links, in place.

    Runs **last** in :data:`DEFAULT_REPAIRS`, so it counts against ids the
    sequence repairs have already settled; run earlier it would recount a graph
    about to be relabelled.

    An activity with **zero** back-links is skipped rather than set to 0. The
    field is ``Field(ge=1)``, so writing 0 would still fail validation but with a
    bounds error in place of ``_validate_n_sources``'s "activity Ax has no
    supporting sources" — trading an informative rejection for an obscure one.
    Orphans are :func:`salvage_orphan_activities`'s business, and that repair is
    off by default.
    """
    activities = _activities(payload)
    if not activities:
        return []
    sources = _sources(payload) or []
    counts: dict[object, int] = {}
    for s in sources:
        aid = s.get("activity_id")
        if aid != _NA:
            counts[aid] = counts.get(aid, 0) + 1
    events: list[BookkeepingSalvage] = []
    for a in activities:
        actual = counts.get(a.get("activity_id"), 0)
        if actual == 0:
            continue
        if a.get("n_sources") != actual:
            events.append(
                BookkeepingSalvage(
                    kind="n_sources",
                    detail=(
                        f"{a.get('activity_id')}: {a.get('n_sources')!r} -> {actual}"
                    ),
                )
            )
            a["n_sources"] = actual
    return events


def salvage_orphan_activities(payload: object) -> list[BookkeepingSalvage]:
    """Drop activities with no supporting source, in place. **Not on by default.**

    Mechanically correct — the contract requires every activity to be backed by
    ≥1 source, and an unsupported activity cannot be published as documented
    evidence — and substantively a re-coding, which is why it sits outside
    :data:`DEFAULT_REPAIRS`. Dropping the institution's *only* activity leaves
    ``has_genai_activity=yes`` with an empty list, which the contract then
    rejects on a different rule; the honest verdict in that case is ``unclear``,
    and choosing it is not this module's to do. Implemented, tested, and dormant
    until the PI rules.
    """
    activities = _activities(payload)
    if not activities:
        return []
    sources = _sources(payload) or []
    linked = {s.get("activity_id") for s in sources if s.get("activity_id") != _NA}
    orphans = [a for a in activities if a.get("activity_id") not in linked]
    if not orphans:
        return []
    kept = [a for a in activities if a.get("activity_id") in linked]
    assert isinstance(payload, dict)  # _activities already established this
    payload["activities"] = kept
    return [
        BookkeepingSalvage(
            kind="orphan_activities_dropped",
            detail=(
                f"dropped {[a.get('activity_id') for a in orphans]!r}; "
                f"{len(kept)} activity(ies) remain"
            ),
        )
    ]


#: Applied in order. ``n_sources`` last — see its docstring. Orphan-dropping is
#: absent by design, not by omission; adding it here is the one-line change that
#: enables it, and it is a substantive change requiring PI sign-off.
DEFAULT_REPAIRS = (
    salvage_source_id_sequence,
    salvage_activity_id_sequence,
    salvage_n_sources,
)


def salvage_consolidation_bookkeeping(
    payload: object, *, repairs: tuple[object, ...] = DEFAULT_REPAIRS
) -> list[BookkeepingSalvage]:
    """Run the enabled repairs against one raw Stage 6 payload, in place.

    Returns every repair applied, in application order, so the caller can write
    one ledger row naming all of them. An empty list means the payload was
    already conformant on these axes — which is the overwhelmingly common case
    and must not pay for a scan beyond the cheap sequence comparisons.
    """
    events: list[BookkeepingSalvage] = []
    for repair in repairs:
        events.extend(repair(payload))  # type: ignore[operator]
    return events
