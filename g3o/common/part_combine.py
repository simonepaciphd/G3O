"""Long-page part combination (R-044; PI 2026-11-08 Q1 b). No provider calls, no I/O.

A long page (or a pooled Stage 6 evidence set) is coded part by part; this
module turns the parts' answers to one item into the page's answer. It is
item-agnostic: every item-specific fact comes from the item's signed
``long_page_rule`` in the codebook (:func:`rule_from_item`,
:func:`rules_from_codebook`). Consumers: T-021 (page items), T-023 (activity
items, grouped by linked passage by the caller), T-026 (pooled evidence).

Interface
---------
- :class:`PartAnswer`: one part's answer to one item. ``value`` is the answer
  jev chose (or the temporary answer :data:`NOT_COVERED`); ``probability`` is
  the chosen answer's probability (``None`` when not returned); ``failed`` is
  the caller's check result. The caller decides what "failed" means at each
  step: on the pass rounds it is the 0.8 bar only (the T-027 record's
  ``downgraded``); after the T-024 support check it is "any downgrade"
  (quote, entailment or bar). ``ref`` is opaque and carried through (e.g. a
  record index). ``part_index`` orders parts (page order, or pool order).
- :class:`ItemRule`: the configuration of one item's rule.
- :func:`combine`: check-then-combine for one item; returns a
  :class:`CombinedAnswer` with the producing part.

Signed conventions applied (codebook ``combining_conventions``; SPEC R-044, R-045)
-------------------------------------------------------------------------------
- Check-then-combine (all-03 a): a failed answer enters as the item's
  downgrade target (``unknown``); a ``tag_only`` item (the page verdict) keeps
  its value and the failure tag.
- The temporary answer "not covered by this part" never votes. If every part
  gives it, the answer is ``not_documented``, or the rule's
  ``all_parts_not_covered`` value (page verdict: ``not_assessable``, RC-D-005 9 a).
- Missing rank (all-04 b): real answers, then ``not_documented``, then
  ``unknown``. ``not_asked`` and ``_NA_`` never compete (applicability is
  applied after the gating item is combined) and are refused here.
- Producing part (all-05 a): among parts giving the winning value, the one
  with the highest chosen-answer probability; ties go to the earliest part.
  A missing probability ranks below every number.

Rule types (RC-D-002 row 41)
----------------------------
- ``first_section``: the first part (by ``part_index``) with a real, not failed
  answer; silent and failed parts are skipped (all-06 a).
- ``any_yes``: a priority order, ``yes`` then ``no`` unless the item states its
  own order (``content_data``).
- ``priority_order``: the item's order; with ``tier_order: [supported, failed]``
  the not-failed answers rank before all failed ones (page-02 b). Optional
  mapping step (``governance_direction``, activity-11 a): when every value of a
  mapped set is given by some not-failed part (e.g. a ban in one part and a
  permission in another), the result is the mapped value; its inputs are listed
  in ``mapped_from``/``elements`` (RC-D-005).
- ``earliest_year``: the smallest four-digit year among real answers.
- ``highest_probability``: the real answer with the highest probability. With a
  ``first_step: {same_part_as: <item>}`` (``observed_actor_role``) the real answer
  from the part that produced ``reference`` comes first.
- ``combined_list``: every real, not-failed value any part gives (several per part
  allowed, e.g. a multi-select); each value's producing part is its most-sure
  part. ``value`` is the tuple of values in first-appearance order. Optional
  mapping step (``target_users``, ``governed_population``, activity-22 b): the
  list maps to one value; ``both`` present, or both members of the pair present,
  gives ``both``; one real value gives that value; no real value falls back on
  the missing rank. A list value may itself be a tuple (``(number, unit)`` pairs
  of the scale items: the caller pairs them within a part).

Known limits stated in the codebook and not applied here (``ItemRule.notes``):
``permanent_pilot_across_parts`` (within-part only, by design), ``split_rule``
and ``pairs`` (the caller builds the parts / pairs), ``role_part`` (the caller
takes the role from the producing part via ``reference``).

Unexpected configuration raises :class:`CombineError`; callers stop that field
and report it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

NOT_COVERED = "not covered by this part"
NOT_DOCUMENTED = "not_documented"
UNKNOWN = "unknown"
NOT_ASKED = "not_asked"
NA = "_NA_"
TAG_ONLY = "tag_only"
MISSING_RANK = (NOT_DOCUMENTED, UNKNOWN)
_NEVER_COMPETE = (NOT_ASKED, NA)

FIRST_SECTION = "first_section"
ANY_YES = "any_yes"
PRIORITY_ORDER = "priority_order"
EARLIEST_YEAR = "earliest_year"
COMBINED_LIST = "combined_list"
HIGHEST_PROBABILITY = "highest_probability"
RULE_TYPES = frozenset({FIRST_SECTION, ANY_YES, PRIORITY_ORDER, EARLIEST_YEAR,
                        COMBINED_LIST, HIGHEST_PROBABILITY})

#: Rule keys that only carry signed text (no behaviour).
_TEXT_KEYS = frozenset({"text", "source", "tiers"})
#: Rule keys that state a limit or a caller duty; recorded in ``ItemRule.notes``.
_NOTE_KEYS = frozenset({"permanent_pilot_across_parts", "split_rule", "pairs", "role_part",
                        "multi_select_vs_single_winner", "per_value_producing_part",
                        "replaces_rule", "then", "rank_of_requires_vs_promotes"})


class CombineError(ValueError):
    """The configuration cannot combine this item's answers; stop the field and report."""

    def __init__(self, item_id: str, reason: str) -> None:
        super().__init__(f"{item_id}: {reason}")
        self.item_id = item_id
        self.reason = reason


@dataclass(frozen=True)
class ItemRule:
    item_id: str
    rule: str
    order: tuple[str, ...] | None = None
    two_tier: bool = False
    all_not_covered: str = NOT_DOCUMENTED
    downgrade_target: str = UNKNOWN
    values: frozenset[str] | None = None
    pair_to_both: tuple[str, str, str] | None = None
    set_maps: tuple[tuple[frozenset[str], str], ...] = ()
    same_part_as: str | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.rule not in RULE_TYPES:
            raise CombineError(self.item_id, f"rule type {self.rule!r} is not one of {sorted(RULE_TYPES)}")
        if self.downgrade_target not in (UNKNOWN, TAG_ONLY):
            raise CombineError(self.item_id, f"downgrade target {self.downgrade_target!r} not supported")
        order = self.order
        if self.rule == ANY_YES and order is None:
            order = ("yes", "no")
        if self.rule == PRIORITY_ORDER and order is None:
            raise CombineError(self.item_id, "priority_order without an order")
        if order is not None:
            order = _normalise_order(self.item_id, order)
            if self.two_tier:
                order = tuple(v for v in order if v not in MISSING_RANK)
            object.__setattr__(self, "order", order)
            if self.values is not None:
                gaps = sorted(v for v in self.values if v not in order)
                if gaps:
                    raise CombineError(self.item_id, f"values {gaps} have no place in the order")
        if self.two_tier and self.downgrade_target != TAG_ONLY:
            raise CombineError(self.item_id, "two tiers need a tag_only item (failed answers keep their value)")
        if self.pair_to_both is not None and self.rule != COMBINED_LIST:
            raise CombineError(self.item_id, "pair mapping only on combined_list")
        if self.set_maps and self.rule != PRIORITY_ORDER:
            raise CombineError(self.item_id, "set mapping only on priority_order")
        if self.same_part_as is not None and self.rule != HIGHEST_PROBABILITY:
            raise CombineError(self.item_id, "same_part_as only on highest_probability")


def _normalise_order(item_id: str, order: Sequence[str]) -> tuple[str, ...]:
    order = tuple(order)
    if len(set(order)) != len(order):
        raise CombineError(item_id, "order repeats a value")
    seen_missing = False
    for v in order:
        if v in _NEVER_COMPETE:
            raise CombineError(item_id, f"order contains {v!r}, which never competes (all-04)")
        if v in MISSING_RANK:
            seen_missing = True
        elif seen_missing:
            raise CombineError(item_id, f"real answer {v!r} ranked after a missing token (all-04 b)")
    present = [v for v in order if v in MISSING_RANK]
    if present != [v for v in MISSING_RANK if v in present]:
        raise CombineError(item_id, "unknown ranked before not_documented (all-04 b)")
    # The signed cross-page order deliberately omits not_documented.
    if item_id == "core.activity_relation_cross_page":
        return order
    return tuple(v for v in order if v not in MISSING_RANK) + MISSING_RANK


def _map_members(item_id: str, key: str) -> list[str]:
    key = re.sub(r"\(.*?\)", "", key)
    parts = [p.strip() for p in key.split("+")]
    if len(parts) < 2 or not all(re.fullmatch(r"[a-z_]+", p) for p in parts):
        raise CombineError(item_id, f"cannot read mapping key {key!r}")
    return parts


def rule_from_item(item_id: str, item: Mapping[str, Any], *,
                   codes: Sequence[str] | None = None) -> ItemRule | None:
    """Build the rule of one raw codebook item (``items[item_id]``); None for no rule.

    ``codes`` are the item's value codes (``Codebook.codes``), used to validate
    answers and the order; pass None for computed value lists (years).
    """
    lp = item.get("long_page_rule")
    if lp is None or lp == "none":
        return None
    lp_map: Mapping[str, Any] = lp if isinstance(lp, Mapping) else {"rule": lp}
    rule = lp_map.get("rule")
    if rule == "none":
        return None
    unknown_keys = set(lp_map) - _TEXT_KEYS - _NOTE_KEYS - {
        "rule", "order", "tier_order", "all_parts_not_covered", "mapping", "first_step"}
    if unknown_keys:
        raise CombineError(item_id, f"long_page_rule keys {sorted(unknown_keys)} not understood")
    order = lp_map.get("order")
    if order is not None and not isinstance(order, list):
        raise CombineError(item_id, f"cannot read order {order!r}")
    tier = lp_map.get("tier_order")
    if tier not in (None, ["supported", "failed"]):
        raise CombineError(item_id, f"cannot read tier_order {tier!r}")
    anc = lp_map.get("all_parts_not_covered")
    all_not_covered = NOT_DOCUMENTED
    if anc is not None:
        if not isinstance(anc, Mapping) or not isinstance(anc.get("value"), str):
            raise CombineError(item_id, f"cannot read all_parts_not_covered {anc!r}")
        all_not_covered = anc["value"]
    pair_to_both = None
    set_maps: list[tuple[frozenset[str], str]] = []
    mapping = lp_map.get("mapping")
    if mapping is not None:
        if not isinstance(mapping, Mapping) or not isinstance(mapping.get("map"), Mapping):
            raise CombineError(item_id, f"cannot read mapping {mapping!r}")
        for key, result in mapping["map"].items():
            members = _map_members(item_id, str(key))
            if rule == COMBINED_LIST:
                if len(members) != 2 or pair_to_both is not None:
                    raise CombineError(item_id, f"list mapping {key!r} is not one pair")
                pair_to_both = (members[0], members[1], str(result))
            elif rule == PRIORITY_ORDER:
                set_maps.append((frozenset(members), str(result)))
            else:
                raise CombineError(item_id, f"mapping step on rule {rule!r}")
    same_part_as = None
    first_step = lp_map.get("first_step")
    if first_step is not None:
        if not isinstance(first_step, Mapping) or set(first_step) != {"same_part_as"}:
            raise CombineError(item_id, f"cannot read first_step {first_step!r}")
        same_part_as = str(first_step["same_part_as"])
    downgrade = item.get("downgrade_target") or UNKNOWN
    values = frozenset(codes) if codes else None
    if values is not None and downgrade == TAG_ONLY and anc is not None:
        values = values | {all_not_covered}
    return ItemRule(
        item_id=item_id, rule=str(rule), order=tuple(order) if order else None,
        two_tier=tier is not None, all_not_covered=all_not_covered,
        downgrade_target=downgrade, values=values, pair_to_both=pair_to_both,
        set_maps=tuple(set_maps), same_part_as=same_part_as,
        notes=tuple(sorted(k for k in lp_map if k in _NOTE_KEYS)),
    )


def rules_from_codebook(cb: Any) -> dict[str, ItemRule]:
    """Every item rule of a loaded :class:`g3o.codebook.loader.Codebook`.

    Checks that the codebook's temporary part answer is :data:`NOT_COVERED`.
    """
    temp = cb.combining_conventions["not_covered_by_this_part"]["temporary_value"]
    if temp != NOT_COVERED:
        raise CombineError("combining_conventions", f"temporary value {temp!r} != {NOT_COVERED!r}")
    rules = {}
    for item_id, item in cb.items.items():
        r = rule_from_item(item_id, item, codes=cb.codes(item_id))
        if r is not None:
            rules[item_id] = r
    return rules


@dataclass(frozen=True)
class PartAnswer:
    part_id: str
    part_index: int
    value: Any
    probability: float | None
    failed: bool = False
    cause: str | None = None
    ref: Any = None


@dataclass(frozen=True)
class CombinedAnswer:
    """The combined answer and its producing part.

    ``part_id``/``probability``/``ref`` come from the producing part; they are
    None when a mapping step formed the value from several parts (then
    ``mapped_from`` and ``elements`` name the inputs) or when no part voted.
    ``failed`` is True only for a ``tag_only`` value whose producing part failed.
    ``contributors`` lists every part giving the winning value, in part order.
    """

    item_id: str
    value: Any
    part_id: str | None
    part_index: int | None
    probability: float | None
    failed: bool = False
    cause: str | None = None
    ref: Any = None
    contributors: tuple[str, ...] = ()
    elements: tuple[CombinedAnswer, ...] = ()
    mapped_from: tuple[Any, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class _Vote:
    answer: PartAnswer
    entered: Any
    failed: bool


def _hashable(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(_hashable(x) for x in v)
    return v


def _is_missing(v: Any) -> bool:
    return isinstance(v, str) and v in MISSING_RANK


def _sure_key(v: _Vote) -> tuple[float, int]:
    p = v.answer.probability
    return (-(p if p is not None else -1.0), v.answer.part_index)


def _from(item_id: str, winners: Sequence[_Vote], value: Any = None, note: str | None = None) -> CombinedAnswer:
    best = min(winners, key=_sure_key)
    order = sorted(winners, key=lambda v: v.answer.part_index)
    return CombinedAnswer(
        item_id=item_id, value=best.entered if value is None else value,
        part_id=best.answer.part_id, part_index=best.answer.part_index,
        probability=best.answer.probability, failed=best.failed,
        cause=best.answer.cause if best.failed else None, ref=best.answer.ref,
        contributors=tuple(dict.fromkeys(v.answer.part_id for v in order)), note=note,
    )


def _nobody(rule: ItemRule) -> CombinedAnswer:
    return CombinedAnswer(rule.item_id, rule.all_not_covered, None, None, None,
                          note="every part answered 'not covered by this part' (all-03 a)")


def _missing_fallback(rule: ItemRule, votes: Sequence[_Vote]) -> CombinedAnswer:
    if not votes:
        return _nobody(rule)
    for tok in MISSING_RANK:
        winners = [v for v in votes if v.entered == tok]
        if winners:
            return _from(rule.item_id, winners)
    raise CombineError(rule.item_id, "no real or missing answer to combine")


def _real(votes: Sequence[_Vote]) -> list[_Vote]:
    return [v for v in votes if not _is_missing(v.entered) and not v.failed]


def _rank(rule: ItemRule, value: Any) -> int:
    assert rule.order is not None
    try:
        return rule.order.index(value)
    except ValueError:
        raise CombineError(rule.item_id, f"value {value!r} has no place in the order") from None


def _priority(rule: ItemRule, votes: Sequence[_Vote]) -> CombinedAnswer:
    if not votes:
        return _nobody(rule)
    if rule.set_maps:
        given = {v.entered for v in _real(votes)}
        for needed, result in rule.set_maps:
            if needed <= given and result not in given:
                inputs = sorted(needed, key=lambda x: _rank(rule, x))
                elements = tuple(_from(rule.item_id, [v for v in _real(votes) if v.entered == x])
                                 for x in inputs)
                parts = sorted((v for v in _real(votes) if v.entered in needed),
                               key=lambda v: v.answer.part_index)
                return CombinedAnswer(
                    rule.item_id, result, None, None, None,
                    contributors=tuple(dict.fromkeys(v.answer.part_id for v in parts)),
                    elements=elements, mapped_from=tuple(inputs),
                    note="mapping step (activity-11 a)")

    def key(v: _Vote) -> tuple[int, int]:
        return (1 if (rule.two_tier and v.failed) else 0, _rank(rule, v.entered))

    best = min(key(v) for v in votes)
    return _from(rule.item_id, [v for v in votes if key(v) == best])


def _first_section(rule: ItemRule, votes: Sequence[_Vote]) -> CombinedAnswer:
    real = _real(votes)
    if not real:
        return _missing_fallback(rule, votes)
    first = min(real, key=lambda v: v.answer.part_index)
    return _from(rule.item_id, [v for v in real if v.entered == first.entered])


def _year(item_id: str, v: Any) -> int:
    if isinstance(v, str) and re.fullmatch(r"[0-9]{4}", v):
        return int(v)
    if type(v) is int and 1000 <= v <= 9999:
        return v
    raise CombineError(item_id, f"{v!r} is not a four-digit year")


def _earliest_year(rule: ItemRule, votes: Sequence[_Vote]) -> CombinedAnswer:
    real = _real(votes)
    if not real:
        return _missing_fallback(rule, votes)
    y = min(_year(rule.item_id, v.entered) for v in real)
    return _from(rule.item_id, [v for v in real if _year(rule.item_id, v.entered) == y])


def _highest(rule: ItemRule, votes: Sequence[_Vote], reference: CombinedAnswer | None) -> CombinedAnswer:
    real = _real(votes)
    if not real:
        return _missing_fallback(rule, votes)
    if rule.same_part_as is not None:
        if reference is None:
            raise CombineError(rule.item_id, f"needs the combined {rule.same_part_as} answer")
        same = [v for v in real if reference.part_id is not None and v.answer.part_id == reference.part_id]
        if same:
            return _from(rule.item_id, same, note=f"same part as {rule.same_part_as}")
    best = min(real, key=_sure_key)
    return _from(rule.item_id, [v for v in real if v.entered == best.entered])


def _list(rule: ItemRule, votes: Sequence[_Vote]) -> CombinedAnswer:
    real = sorted(_real(votes), key=lambda v: v.answer.part_index)
    if not real:
        return _missing_fallback(rule, votes)
    groups: dict[Any, list[_Vote]] = {}
    for v in real:
        groups.setdefault(v.entered, []).append(v)
    elements = tuple(_from(rule.item_id, vs) for vs in groups.values())
    contributors = tuple(dict.fromkeys(v.answer.part_id for v in real))
    if rule.pair_to_both is None:
        return CombinedAnswer(rule.item_id, tuple(groups), None, None, None,
                              contributors=contributors, elements=elements)
    a, b, both = rule.pair_to_both
    stray = [x for x in groups if x not in (a, b, both)]
    if stray:
        raise CombineError(rule.item_id, f"mapping step cannot place {stray!r}")
    if both in groups:
        return replace(_from(rule.item_id, groups[both]), elements=elements,
                       note="mapping step (activity-22 b): 'both' given")
    if a in groups and b in groups:
        return CombinedAnswer(rule.item_id, both, None, None, None, contributors=contributors,
                              elements=elements, mapped_from=(a, b), note="mapping step (activity-22 b)")
    return replace(_from(rule.item_id, real), elements=elements)


def combine(rule: ItemRule, answers: Sequence[PartAnswer], *,
            reference: CombinedAnswer | None = None) -> CombinedAnswer:
    """Check-then-combine one item's part answers by its rule.

    ``reference`` is the combined answer of ``rule.same_part_as`` when the rule
    has that first step. Raises :class:`CombineError` for values the rule cannot
    place and :class:`ValueError` for malformed input.
    """
    if not answers:
        raise ValueError(f"{rule.item_id}: no part answers")
    if rule.rule != COMBINED_LIST:
        ids = [a.part_id for a in answers]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{rule.item_id}: several answers from one part")
    votes: list[_Vote] = []
    for a in answers:
        v = _hashable(a.value)
        if v == NOT_COVERED:
            continue
        if isinstance(v, str) and v in _NEVER_COMPETE:
            raise ValueError(f"{rule.item_id}: {v!r} never competes; apply applicability after combining")
        if a.failed and rule.downgrade_target != TAG_ONLY:
            votes.append(_Vote(a, rule.downgrade_target, True))
            continue
        if rule.values is not None and not _is_missing(v) and v not in rule.values:
            raise CombineError(rule.item_id, f"{v!r} is not a value of the item")
        votes.append(_Vote(a, v, a.failed))
    if rule.rule in (PRIORITY_ORDER, ANY_YES):
        return _priority(rule, votes)
    if rule.rule == FIRST_SECTION:
        return _first_section(rule, votes)
    if rule.rule == EARLIEST_YEAR:
        return _earliest_year(rule, votes)
    if rule.rule == HIGHEST_PROBABILITY:
        return _highest(rule, votes, reference)
    return _list(rule, votes)


__all__ = [
    "ANY_YES", "COMBINED_LIST", "EARLIEST_YEAR", "FIRST_SECTION", "HIGHEST_PROBABILITY",
    "MISSING_RANK", "NA", "NOT_ASKED", "NOT_COVERED", "NOT_DOCUMENTED", "PRIORITY_ORDER",
    "RULE_TYPES", "TAG_ONLY", "UNKNOWN", "CombineError", "CombinedAnswer", "ItemRule",
    "PartAnswer", "combine", "rule_from_item", "rules_from_codebook",
]
