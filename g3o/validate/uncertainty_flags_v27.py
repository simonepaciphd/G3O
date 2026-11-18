"""v2.7 per-code uncertainty flags (T-024 derived field ``core.uncertainty_flags``). No I/O, no calls.

Signed rule (codebook ``core.uncertainty_flags``): "Compute each flag from codes
...; add ``identity_unresolved`` for Stage 6 relations; drop
``source_language_barrier``; ``discontinued_uncertain`` becomes a pass-2 jev
yes/no" (X24); "keep 'identity unresolved' and 'stage ambiguous'" (r2#38);
"AI-text flags fold into the main list" (r2#39). The v2.7 flag list is
therefore :data:`SIGNED_FLAGS`.

Triggers (PI rulings 2026-11-11, A6.1-A6.4, all option a):

- **A6.1** ``stage_ambiguous``: the ``core.adoption_stage`` answers differ across
  parts or pooled observations before combining (:func:`stage_ambiguous`).
  Missing answers (the item's signed missing tokens, :data:`STAGE_MISSING`) are
  ignored: the flag fires only on conflicting stated stages (PI ruling 1 b on
  the build questions, 2026-11-11).
- **A6.2** ``identity_unresolved``: a Stage 6 relation
  (``core.activity_relation_cross_page``) is ``unresolved``. The within-page
  relation (``core.activity_segment``, a pass-2 per-page item) is not a Stage 6
  relation and sets no flag.
- **A6.3** Per-code scope: a support node carries only the flags of its own
  code (:func:`code_flags`); otherwise ``[]``.
- **A6.4** Merged activity: the union, alphabetical (:func:`union_flags`).

Implementation reading (not a separate ruling; reported with the build): an
"answer" is a classifier's chosen value as jev returned it (before the
check-then-combine downgrade), the temporary part answer "not covered by this
part" excluded (it never votes, R-044); a pooled observation's answer is its
final per-page ``core.adoption_stage`` value.

Row value (:func:`row_flags`): an activity row's ``core.uncertainty_flags`` is
the union of the flags its stored support nodes carry (ruling 11), with one
exception (PI ruling R1 a, 2026-11-12): ``identity_unresolved`` is a row flag
of the left-hand activity of an unresolved cross-page relation, where the
relation is filed, wherever that relation's support node is stored (W4 b: with
the record whose quote was copied, which may be the right-hand one). So a row's
value is the union of its own nodes' flags without ``identity_unresolved``, plus
``identity_unresolved`` iff an unresolved cross-page relation is filed on that
row. Node flags are unchanged (A6.3 a): the relation node keeps
``identity_unresolved`` wherever it is stored. Per-page rows hold no cross-page
relation, so there the value is the plain union.

Still refused: the AI-text flags r2#39 folds into the list have no signed names
or triggers; :func:`check_pipeline` refuses the ``ai_text`` pipeline.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from g3o.common.part_combine import NOT_COVERED
from g3o.common.storage_fields import FIELDS
from g3o.common.support_check import SupportResult
from g3o.persist.stage6_adapters import MissingUpstreamError

STAGE_AMBIGUOUS = "stage_ambiguous"
IDENTITY_UNRESOLVED = "identity_unresolved"
#: The signed v2.7 list, alphabetical.
SIGNED_FLAGS: tuple[str, ...] = (IDENTITY_UNRESOLVED, STAGE_AMBIGUOUS)
STAGE_ITEM = "core.adoption_stage"
#: The adoption stage's signed missing tokens; never a stated stage (ruling 1 b).
STAGE_MISSING: frozenset[str] = frozenset(FIELDS[STAGE_ITEM]["missing_tokens"])
STAGE6_RELATION_ITEM = "core.activity_relation_cross_page"
UNRESOLVED = "unresolved"
ITEM = "core.uncertainty_flags"
AI_TEXT_PIPELINE = "ai_text"
AI_TEXT_FLAGS_PRODUCER = ("AI-text uncertainty flags (codebook core.uncertainty_flags r2#39 'AI-text flags fold "
                          "into the main list'): no signed flag names or triggers")


def check_pipeline(pipeline: str) -> None:
    """Refuse a pipeline whose flags have no signed trigger (the AI-text flags)."""
    if pipeline == AI_TEXT_PIPELINE:
        raise MissingUpstreamError(AI_TEXT_FLAGS_PRODUCER, [pipeline])


def stage_ambiguous(answers: Iterable[str]) -> bool:
    """A6.1 a: the stated adoption-stage answers before combining are not all the same.

    "Not covered by this part" never votes (R-044), and missing answers are
    ignored (ruling 1 b): ``pilot`` beside ``not_documented`` is not ambiguous.
    """
    return len({a for a in answers if a != NOT_COVERED and a not in STAGE_MISSING}) > 1


def code_flags(sr: SupportResult, *, stage_answers: Sequence[str] = ()) -> list[str]:
    """A6.3 a: the flags of this node's own code, sorted; ``[]`` when none applies.

    ``stage_answers`` are the ``core.adoption_stage`` answers of the node's
    activity (parts, or pooled observations and pool parts); read only for an
    adoption-stage node.
    """
    flags: set[str] = set()
    if sr.item_id == STAGE_ITEM and stage_ambiguous(stage_answers):
        flags.add(STAGE_AMBIGUOUS)
    if sr.item_id == STAGE6_RELATION_ITEM and sr.value == UNRESOLVED:
        flags.add(IDENTITY_UNRESOLVED)
    return sorted(flags)


def union_flags(lists: Iterable[Iterable[str]]) -> list[str]:
    """A6.4 a: the union, alphabetical; a member outside the signed list is refused."""
    out = {f for flags in lists for f in flags}
    unknown = sorted(out - set(SIGNED_FLAGS))
    if unknown:
        raise ValueError(f"uncertainty flag(s) outside the signed v2.7 list {list(SIGNED_FLAGS)}: {unknown}")
    return sorted(out)


def row_flags(nodes: Iterable[Mapping[str, Any]], *, unresolved_relation: bool = False) -> list[str]:
    """An activity row's value (ruling 11 with the R1 a exception; see the module docstring).

    The union of the flags its stored support nodes carry, ``identity_unresolved``
    excluded, plus ``identity_unresolved`` iff ``unresolved_relation``: an
    unresolved cross-page relation is filed on this row (its left-hand activity).
    """
    own = [f for f in union_flags(n["uncertainty_flags"] for n in nodes) if f != IDENTITY_UNRESOLVED]
    return union_flags([own, [IDENTITY_UNRESOLVED] if unresolved_relation else []])


def classifier_answers(records: Iterable[Any], item_id: str = STAGE_ITEM) -> list[str]:
    """The classifier answers to ``item_id`` among coder records (``chosen_value``), in record order."""
    return [str(r.chosen_value) for r in records
            if r.item_id == item_id and r.coder_type == "classifier" and r.chosen_value != NOT_COVERED]


__all__ = [
    "AI_TEXT_FLAGS_PRODUCER", "IDENTITY_UNRESOLVED", "ITEM", "SIGNED_FLAGS", "STAGE6_RELATION_ITEM", "STAGE_AMBIGUOUS",
    "STAGE_ITEM", "STAGE_MISSING", "UNRESOLVED", "check_pipeline", "classifier_answers", "code_flags", "row_flags",
    "stage_ambiguous", "union_flags",
]
