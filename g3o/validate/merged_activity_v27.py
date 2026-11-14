"""A8 producers of an activity's derived values (Stage 6; PI A8 rulings, 2026-11-11, and later rulings).

RC-D-030 X1 a R1 asks Stage 6 to re-derive these values for a merged activity;
RC-D-032 B1 a kept them refused until per-source producers existed. The PI
ruled the A8 questions on 2026-11-11 ("All recs accepted", section A8), ruling
66 a on 2026-11-13, and rulings 76 b, 77 a, 78 a, 88 a, 89 a and 90 c on
2026-11-13. Ruling 78 a: Stage 6 runs these producers for every published
activity, a single-observation one included (its pool is that observation).
Every function reads the pooled (confirmed) observations' stored activity rows
(``observation_inputs``) and the institution's stored source rows
(``sources``); nothing is looked up.

Built here:

- ``core.stage_as_of`` (codebook ``items/core.stage_as_of/rules/0``:
  "source_publication_date if supported, else the page's latest stated date
  for the activity, else the access date"). Per observation
  (:func:`observation_stage_as_of`): A8.3 a, a supported date is a real date,
  and the stored ``core.source_publication_date`` is real only when it came
  from metadata/URL (A1) or from a quote that passed R-042 (a failed check
  stores the downgrade target ``unknown``,
  :func:`g3o.common.source_fields.publication_date`); A8.4 a, the latest
  stated date is the activity's latest supported year code (the three year
  items are ``support_required`` with downgrade target ``unknown``, so a
  stored four-digit year is a supported one), future years excluded (ruling
  90 c, :func:`is_future_year`, PROVISIONAL definition); else the source's
  ``core.source_access_date``. A8.6 a: the activity takes the latest date
  among its pooled observations (:func:`merged_stage_as_of`); ruling 90 c: an
  observation's access date counts only when no pooled observation has a
  real (publication or stated) date, and is required only then or for the
  future-year test of a stated year. Ruling 76 b (:func:`latest`): dates that
  agree on their shared prefix (``2024-03`` and ``2024-03-12``) are the same
  date and the more precise one is taken; any other overlap is refused
  (:class:`UnruledMergeError`).
- ``core.date_upper_bound`` at activity level (A8.11 a: its target is
  ``stage_as_of``; A8.12 a: no archive first-capture lookup). When the chosen
  date is a source's publication date, the source row's stored
  ``core.date_upper_bound`` (the source-level producer,
  :func:`g3o.common.source_fields.date_upper_bound`) is used; a year code or
  an access date is not an archive bound, so ``no`` (the same rule: ``yes``
  only for the ``archive_upper_bound`` origin).
- ``core.unit_credit`` (A8.7 a, ruling 66 a): ``yes`` iff the relationship part
  of the observation's stored ``core.observed_actor_relationship`` (the
  two-part object storage holds, as the T-015 assembler reads it) is
  ``unit_of_institution``, read literally (any other signed value or missing
  token gives ``no``). A8.8 a: ``yes`` if any pooled observation is.
- ``core.vendor_claim_only`` (r2#28, A8.9 a, rulings 88 a and 89 a): ``yes``
  only if every supporting source (the pooled observations' source claims,
  89 a) has ``source_type`` ``vendor``; any missing type gives ``unknown``. A
  page typed automatically (official domain or archive address,
  ``items/core.source_type/rules/0``) is stored ``not_asked`` with a
  ``set_by_rule`` support node naming ``source_type_auto:<basis>``; that
  stored rule name is read (not re-derived from the URL), and such a page has a
  type and is not ``vendor`` (ruling 88 a). One rule for this producer and the
  per-page one: :func:`g3o.common.source_fields.vendor_claim_type`.
- ``core.cx_display_rollup`` (A8.10 a, :func:`cx_display_rollup`): the
  positive of each CX item is defined in :data:`CX_POSITIVE`, approved as
  drafted by PI ruling 77 a.

Errors. A stored value an A8 rule reads that is absent raises
:class:`~g3o.persist.stage6_adapters.MissingUpstreamError` (ruling B1 a: the
institution is held). A stored value outside its signed form, or a produced
value that is not a signed code, raises :class:`MalformedA8Value` (ruling 32 b:
a wiring error; Stage 6 stops). An input the signed rules do not determine
raises :class:`UnruledMergeError` (a PI question; the institution is held).
Nothing is guessed.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from g3o.common import source_fields as sf
from g3o.common.storage import table_fields, validate_value
from g3o.common.storage_fields import FIELDS
from g3o.persist.stage6_adapters import MissingUpstreamError

STAGE_AS_OF = "core.stage_as_of"
UPPER_BOUND = "core.date_upper_bound"
UNIT_CREDIT = "core.unit_credit"
VENDOR_CLAIM_ONLY = "core.vendor_claim_only"
CX_ROLLUP = "core.cx_display_rollup"
#: The A8 values Stage 6 produces for every published activity (rulings 77 a, 78 a; order not implied).
PRODUCED = (STAGE_AS_OF, UPPER_BOUND, UNIT_CREDIT, VENDOR_CLAIM_ONLY, CX_ROLLUP)

PUBLICATION_DATE = "core.source_publication_date"
ACCESS_DATE = "core.source_access_date"
SOURCE_TYPE = "core.source_type"
RELATIONSHIP = "core.observed_actor_relationship"
#: The part of ``core.observed_actor_relationship`` A8.7 a reads (as the T-015 assembler does).
RELATIONSHIP_PART = "relationship"
#: The three year items (codebook ``family: dates``; X35 label_rules "the three year items").
YEAR_ITEMS = ("core.year_announced", "core.year_pilot_start", "core.year_production_start")
UNIT_OF_INSTITUTION = "unit_of_institution"
NOT_ASKED = "not_asked"
SET_BY_RULE = "set_by_rule"
YES, NO = "yes", "no"

PRODUCER = "Stage 6 A8 producer"
_DATE = re.compile(r"^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$")
_YEAR = re.compile(r"^[0-9]{4}$")

# Step names (internal: core.stage_as_of_basis stays refused until codebook r16, A8.5 a).
STEP_PUBLICATION = "publication"
STEP_STATED = "stated"
STEP_ACCESS = "access"

if RELATIONSHIP_PART not in FIELDS[RELATIONSHIP]["parts"]:  # pragma: no cover - signed codebook drift
    raise RuntimeError(f"{RELATIONSHIP} has no {RELATIONSHIP_PART!r} part")
for _item in (UPPER_BOUND, UNIT_CREDIT, VENDOR_CLAIM_ONLY):
    if not {YES, NO} <= set(FIELDS[_item]["codes"]):  # pragma: no cover - signed codebook drift
        raise RuntimeError(f"{_item} codes are not yes/no")


class UnruledMergeError(ValueError):
    """A value the signed rules do not determine for these inputs (a PI question; the institution is held)."""

    def __init__(self, item: str, detail: str) -> None:
        super().__init__(f"{item}: {detail}; not determined by the signed rule (PI question)")
        self.item, self.detail = item, detail


class MalformedA8Value(Exception):  # noqa: N818 - names the wiring defect, as MissingUpstreamError does
    """Ruling 32 b (A8 review M1): a stored value an A8 rule reads is outside its signed form, or a
    produced value is not a signed code. A wiring or programming error, never institution data: Stage 6
    stops (``stage_validate_v27`` raises ``UpstreamRowMalformed``). Not a ``ValueError``, so no
    per-institution hold catches it."""

    def __init__(self, item: str, where: str, detail: str) -> None:
        super().__init__(f"{item} of {where}: {detail}")
        self.item, self.where, self.detail = item, where, detail


def _tokens(item: str) -> tuple[str, ...]:
    tokens = FIELDS[item]["missing_tokens"]
    return tuple(tokens) if isinstance(tokens, list) else ()


def _get(row: Mapping[str, Any], item: str, where: str) -> Any:
    values = row.get("values")
    if not isinstance(values, Mapping) or item not in values:
        raise MissingUpstreamError(f"{PRODUCER}: {where}", [item])
    return values[item]


def _source_row(inst: Any, sid: str) -> Mapping[str, Any]:
    if sid not in inst.sources:
        raise MissingUpstreamError(f"{PRODUCER}: source row {sid}", [sid])
    return inst.sources[sid]


def _real_date(item: str, value: Any, where: str) -> bool:
    """True for a real date of ``item``, False for one of its missing tokens; anything else is malformed."""
    if isinstance(value, str) and value in _tokens(item):
        return False
    if isinstance(value, str) and _DATE.fullmatch(value):
        return True
    raise MalformedA8Value(item, where, f"{value!r} is neither a date nor a missing token")


def _signed(item: str, value: Any) -> Any:
    """The produced ``value`` if storage accepts it as a signed value of ``item``; otherwise malformed."""
    try:
        validate_value(item, value)
    except ValueError as exc:
        raise MalformedA8Value(item, PRODUCER, f"produced {value!r} is not a signed value ({exc})") from exc
    if item == STAGE_AS_OF and not _DATE.fullmatch(value):
        raise MalformedA8Value(item, PRODUCER, f"produced {value!r} is not a date")
    return value


# ---------------------------------------------------------------------------
# stage_as_of (A8.3 a, A8.4 a, A8.6 a; rulings 76 b, 90 c)
# ---------------------------------------------------------------------------


def is_future_year(year: str, access_date: str) -> bool:
    """Ruling 90 c: whether a stated year code is a future year, excluded from ``stage_as_of``.

    PROVISIONAL, pending PI confirmation: the PI has not defined "future". The
    procedural default is "a year later than the observation's access-date
    year" (``year > access year``). This function is the only place that
    definition lives.
    """
    return int(year) > int(access_date[:4])


@dataclass(frozen=True)
class DatedObservation:
    """One observation's ``stage_as_of`` with the rule step that fixed it and its source claim.

    ``future_years``: stated year codes excluded as future (ruling 90 c).
    """

    observation_id: str
    source_id: str
    date: str
    step: str
    future_years: tuple[str, ...] = ()


def _missing_access(inst: Any, oid: str) -> MissingUpstreamError:
    where = f"source {inst.observation_inputs[oid].source_id}"
    return MissingUpstreamError(f"{PRODUCER}: access date of {where} (stage_as_of)", [ACCESS_DATE])


def _dated(inst: Any, oid: str) -> DatedObservation | None:
    """One observation's ``stage_as_of``, or None when it would fall to an access date it lacks.

    The access date is required here only when a stated year needs ruling 90 c's
    future test (:func:`is_future_year`). An observation with no real
    publication date and no stated year returns None when its access date is
    absent or a missing token: that date is used only if no pooled observation
    has a real date (:func:`merged_stage_as_of`). A present access date is still
    checked for its signed form (a malformed one is a wiring error).
    """
    obs = inst.observation_inputs[oid]
    sid = obs.source_id
    src = _source_row(inst, sid)
    where = f"source {sid}"
    pub = _get(src, PUBLICATION_DATE, where)
    if _real_date(PUBLICATION_DATE, pub, where):
        return DatedObservation(oid, sid, pub, STEP_PUBLICATION)
    years: list[str] = []
    for item in YEAR_ITEMS:
        value = _get(obs.row, item, f"observation {oid}")
        if isinstance(value, str) and value in _tokens(item):
            continue
        if not (isinstance(value, str) and _YEAR.fullmatch(value)):
            raise MalformedA8Value(item, f"observation {oid}", f"{value!r} is neither a year code nor a missing token")
        years.append(value)
    values = src.get("values")
    if not years and not (isinstance(values, Mapping) and ACCESS_DATE in values):
        return None  # absent, but needed only if no pooled observation has a real date
    access = _get(src, ACCESS_DATE, where)
    if not _real_date(ACCESS_DATE, access, where):
        if years:  # the reference year of ruling 90 c's future test
            raise _missing_access(inst, oid)
        return None
    future = tuple(y for y in years if is_future_year(y, access))
    current = [y for y in years if y not in future]
    if current:
        return DatedObservation(oid, sid, max(current, key=int), STEP_STATED, future)
    return DatedObservation(oid, sid, access, STEP_ACCESS, future)


def observation_stage_as_of(inst: Any, oid: str) -> DatedObservation:
    """``items/core.stage_as_of/rules/0`` for one observation alone (A8.3 a, A8.4 a, ruling 90 c).

    Alone, an observation without a real date falls to its access date, so a
    missing access date holds it (:class:`MissingUpstreamError`).
    """
    dated = _dated(inst, oid)
    if dated is None:
        raise _missing_access(inst, oid)
    return dated


def _span(date: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """First and last day a ``YYYY`` / ``YYYY-MM`` / ``YYYY-MM-DD`` date can mean (31 days as an upper bound)."""
    parts = [int(p) for p in date.split("-")]
    year = parts[0]
    month = parts[1] if len(parts) > 1 else None
    day = parts[2] if len(parts) > 2 else None
    return (year, month or 1, day or 1), (year, month or 12, day or 31)


def _extends(precise: str, coarse: str) -> bool:
    """Ruling 76 b: ``precise`` agrees with ``coarse`` on their shared prefix and is more precise."""
    return precise.startswith(coarse + "-")


def latest(dated: Sequence[DatedObservation]) -> list[DatedObservation]:
    """A8.6 a with ruling 76 b: the observations carrying the latest date.

    A date another pooled date extends (``2024`` beside ``2024-03-12``,
    ``2024-03`` beside ``2024-03-12``) is the same date, and the more precise
    one is taken. The remaining dates are compared as calendar spans; any other
    overlap is refused (:class:`UnruledMergeError`). The observations returned
    are those carrying the date taken.
    """
    if not dated:
        raise MalformedA8Value(STAGE_AS_OF, PRODUCER, "no pooled observation to date")
    distinct = {d.date for d in dated}
    kept = sorted(d for d in distinct if not any(_extends(e, d) for e in distinct))
    best = max(kept, key=lambda d: _span(d)[0])
    start = _span(best)[0]
    overlapping = [d for d in kept if d != best and _span(d)[1] >= start]
    if overlapping:
        raise UnruledMergeError(STAGE_AS_OF, f"latest of {sorted(distinct)} is not determined ({best!r} "
                                             f"overlaps {sorted(overlapping)})")
    return [d for d in dated if d.date == best]


def merged_stage_as_of(inst: Any, order: Sequence[str]) -> tuple[str, list[DatedObservation]]:
    """``core.stage_as_of`` of an activity and the pooled observations that carry it.

    Ruling 90 c: an access date counts only when no pooled observation has a real
    (publication or stated) date, so an access date is required only then (an
    observation's absent or missing-token access date holds the institution only
    when it would be used; a stated year still requires it for 90 c's future test).
    """
    pairs = [(k, _dated(inst, k)) for k in order]
    real = [d for _, d in pairs if d is not None and d.step != STEP_ACCESS]
    if not real:
        for k, d in pairs:
            if d is None:
                raise _missing_access(inst, k)
    chosen = latest(real or [d for _, d in pairs if d is not None])
    return _signed(STAGE_AS_OF, chosen[0].date), chosen


def merged_date_upper_bound(inst: Any, chosen: Sequence[DatedObservation]) -> str:
    """A8.11 a / A8.12 a: whether the activity's ``stage_as_of`` is an upper bound."""
    values = set()
    for d in chosen:
        if d.step != STEP_PUBLICATION:
            values.add(NO)  # a year code or an access date has no archive_upper_bound origin
            continue
        where = f"source {d.source_id}"
        bound = _get(_source_row(inst, d.source_id), UPPER_BOUND, where)
        if bound not in (YES, NO):
            raise MalformedA8Value(UPPER_BOUND, where, f"{bound!r} is not yes/no beside the real publication "
                                                       f"date {d.date!r}")
        values.add(bound)
    if len(values) != 1:
        raise UnruledMergeError(UPPER_BOUND, f"observations dated {chosen[0].date!r} disagree on the upper bound")
    return _signed(UPPER_BOUND, values.pop())


# ---------------------------------------------------------------------------
# unit_credit (A8.7 a, A8.8 a, ruling 66 a)
# ---------------------------------------------------------------------------


def observation_unit_credit(inst: Any, oid: str) -> str:
    """A8.7 a / ruling 66 a: ``yes`` iff the relationship part is ``unit_of_institution``, read literally.

    Reads the stored two-part object as the T-015 assembler
    (:func:`g3o.run.presweep.source_row_v27.unit_credit`) does; an absent part
    is a missing input, a non-object value or an unsigned part value is malformed.
    """
    where = f"observation {oid}"
    value = _get(inst.observation_inputs[oid].row, RELATIONSHIP, where)
    if not isinstance(value, Mapping):
        raise MalformedA8Value(RELATIONSHIP, where, f"{value!r} is not the stored two-part object")
    if RELATIONSHIP_PART not in value:
        raise MissingUpstreamError(f"{PRODUCER}: {where}", [f"{RELATIONSHIP}#{RELATIONSHIP_PART}"])
    part = value[RELATIONSHIP_PART]
    if part not in [*FIELDS[RELATIONSHIP]["parts"][RELATIONSHIP_PART], *_tokens(RELATIONSHIP)]:
        raise MalformedA8Value(RELATIONSHIP, where, f"{RELATIONSHIP_PART} part {part!r} is not a signed code "
                                                    "or missing token")
    return _signed(UNIT_CREDIT, YES if part == UNIT_OF_INSTITUTION else NO)


def merged_unit_credit(inst: Any, order: Sequence[str]) -> str:
    """A8.8 a: ``yes`` if any pooled observation is ``yes``."""
    return YES if any(observation_unit_credit(inst, k) == YES for k in order) else NO


# ---------------------------------------------------------------------------
# vendor_claim_only (A8.9 a, rulings 88 a, 89 a)
# ---------------------------------------------------------------------------


def _not_asked_rule(row: Mapping[str, Any], where: str) -> str:
    """The stored ``set_by_rule`` rule name of a ``not_asked`` ``source_type`` (its support node).

    A stored ``not_asked`` type is always written with its ``set_by_rule`` node
    (``stage6_adapters.support_nodes``), so a row without a support list, or a
    ``not_asked`` type without that node, is structurally broken: a wiring error
    (ruling 32 b), not an absent value.
    """
    nodes = row.get("item_support")
    if isinstance(nodes, (str, bytes)) or not isinstance(nodes, Sequence):
        raise MalformedA8Value(SOURCE_TYPE, where, f"no item_support list ({type(nodes).__name__}) beside a "
                                                   "not_asked type")
    rules = {n.get("support_rule_name") for n in nodes
             if isinstance(n, Mapping) and n.get("item_id") == SOURCE_TYPE and n.get("value_json") == NOT_ASKED
             and n.get("support_status") == SET_BY_RULE}
    if not rules:
        raise MalformedA8Value(SOURCE_TYPE, where, "not_asked type without its set_by_rule support node")
    if len(rules) > 1 or not all(isinstance(r, str) and r for r in rules):
        raise MalformedA8Value(SOURCE_TYPE, where, f"not_asked set by several or empty rule names {sorted(map(str, rules))}")
    return rules.pop()


def source_type_of(inst: Any, sid: str) -> str | None:
    """The source's type for ``vendor_claim_only``: a ``source_type`` code, ``official_domain`` /
    ``archive_address`` (typed automatically by rule 0, stored ``not_asked`` with that rule name), or
    None when the type is missing (:func:`g3o.common.source_fields.vendor_claim_type`)."""
    row = _source_row(inst, sid)
    where = f"source {sid}"
    value = _get(row, SOURCE_TYPE, where)
    rule = _not_asked_rule(row, where) if value == NOT_ASKED else None
    try:
        return sf.vendor_claim_type(value, rule)
    except sf.MissingUpstreamError:
        raise
    except ValueError as exc:
        raise MalformedA8Value(SOURCE_TYPE, where, str(exc)) from exc


def supporting_sources(inst: Any, order: Sequence[str]) -> list[str]:
    """Ruling 89 a: the pooled observations' source claims only, in pool order, each once."""
    out: list[str] = []
    for k in order:
        sid = inst.observation_inputs[k].source_id
        if sid not in out:
            out.append(sid)
    return out


def merged_vendor_claim_only(inst: Any, order: Sequence[str]) -> str:
    """A8.9 a: ``yes`` only if every supporting source is ``vendor``; any missing type gives ``unknown``."""
    types = [source_type_of(inst, sid) for sid in supporting_sources(inst, order)]
    return _signed(VENDOR_CLAIM_ONLY, sf.vendor_claim_only_value(types))


# ---------------------------------------------------------------------------
# A8.10 a: cx_display_rollup (table approved as drafted, PI ruling 77 a)
# ---------------------------------------------------------------------------

#: How a CX item's positive is read: ``yes`` (yes/no item: the code ``yes``), ``non_empty`` (list
#: item: at least one entry), ``codes`` (single item: one of the listed codes; the display value is
#: the first of them, in codebook value order, among the sources' positives).
CX_YES, CX_NON_EMPTY, CX_CODES = "yes", "non_empty", "codes"

#: A8.10 a: every CX item stored per source claim (codebook CX-01.3 items whose storage target is
#: ``sources``), with the definition of "positive". Approved as drafted by PI ruling 77 a.
CX_POSITIVE: dict[str, tuple[str, tuple[str, ...]]] = {
    "core.content_contact_named": (CX_YES, ()),
    "core.content_contact_details": (CX_YES, ()),
    "core.content_contact": (CX_YES, ()),
    "core.content_contact_emails": (CX_NON_EMPTY, ()),
    "core.content_purpose": (CX_YES, ()),
    "core.content_tool_or_model": (CX_YES, ()),
    "core.content_vendor": (CX_YES, ()),
    "core.content_data": (CX_YES, ()),
    "core.content_users": (CX_YES, ()),
    "core.content_status_date": (CX_YES, ()),
    "core.content_human_oversight": (CX_YES, ()),
    "core.content_risk_assessment": (CX_YES, ()),
    "core.content_user_notification": (CX_YES, ()),
    "core.disclosure_form": (CX_CODES, ("register_cross_institution", "register_single_institution",
                                        "mandated_report", "formal_record", "informal_official", "third_party")),
    "core.disclosure_scope": (CX_CODES, ("whole_of_government", "multi_institution", "single_institution")),
    # `unclear` maps to the reserved "unknown" (codebook CX missing-answer map), so it is not positive.
    "core.evaluation_documented": (CX_CODES, ("results_reported", "conducted_no_results", "required_or_planned")),
    "core.evaluation_type_pre_deployment_testing": (CX_YES, ()),
    "core.evaluation_type_pilot_evaluation": (CX_YES, ()),
    "core.evaluation_type_independent_audit": (CX_YES, ()),
    "core.evaluation_type_ongoing_monitoring": (CX_YES, ()),
    "core.evaluation_type_user_feedback": (CX_YES, ()),
    "core.evaluation_type_bias_or_safety_testing": (CX_YES, ()),
}
#: PI ruling 77 a (2026-11-13): :data:`CX_POSITIVE` and its assumptions are approved as drafted.
CX_POSITIVE_APPROVED = True


def _check_cx_table() -> None:
    sources = table_fields("sources")
    for item, (kind, codes) in CX_POSITIVE.items():
        if item not in sources:
            raise RuntimeError(f"CX item {item} is not stored per source claim")
        signed = FIELDS[item]["codes"]
        if kind == CX_YES and "yes" not in signed:
            raise RuntimeError(f"CX item {item} has no yes code")
        if kind == CX_NON_EMPTY and FIELDS[item]["answer_type"] != "list":
            raise RuntimeError(f"CX item {item} is not a list item")
        if kind == CX_CODES and [c for c in signed if c in codes] != list(codes):
            raise RuntimeError(f"CX item {item}: positive codes are not signed codes in codebook order")


_check_cx_table()


def _cx_positive(item: str, value: Any) -> Any:
    """The source's positive of ``item`` (its value when positive), or None."""
    kind, codes = CX_POSITIVE[item]
    if kind == CX_YES:
        return value if value == "yes" else None
    if kind == CX_NON_EMPTY:
        return list(value) if isinstance(value, list) and len(value) > 0 else None
    return value if value in codes else None


#: ``combining_rule_ref`` of each roll-up entry (the D-007 named object shape, :mod:`g3o.common.storage`).
CX_RULE_REF = "items/core.cx_display_rollup/rules/0 (A8.10 a; positive table CX_POSITIVE, PI ruling 77 a)"


def cx_display_rollup(inst: Any, order: Sequence[str]) -> dict[str, dict[str, Any]]:
    """A8.10 a: one entry per CX item with a positive in any supporting source.

    The D-007 named object (validated by :mod:`g3o.common.storage`): ``{item_id: {"value",
    "input_support_ids", "source_ids", "observation_ids", "combining_rule_ref"}}``, in
    :data:`CX_POSITIVE` order. ``value``: ``yes`` for a yes/no item; for a single item the first
    positive in codebook value order; for a list item the first non-empty list in pool order.
    ``source_ids`` / ``observation_ids``: the supporting sources holding that value and their pooled
    observations; ``input_support_ids``: those sources' stored support nodes of the item. A stored
    positive is taken as supported (the ``support_required`` items store their downgrade target when
    unsupported). Refused while :data:`CX_POSITIVE_APPROVED` is False.
    """
    if not CX_POSITIVE_APPROVED:  # pragma: no cover - approved by PI ruling 77 a
        raise UnruledMergeError(CX_ROLLUP, "the per-item positive table (A8.10 a) is not approved by the PI")
    return _cx_rollup(inst, order)


def _cx_rollup(inst: Any, order: Sequence[str]) -> dict[str, dict[str, Any]]:
    sids = supporting_sources(inst, order)
    rows = {sid: _source_row(inst, sid) for sid in sids}
    out: dict[str, dict[str, Any]] = {}
    for item, (kind, codes) in CX_POSITIVE.items():
        positives = {sid: p for sid in sids
                     if (p := _cx_positive(item, _get(rows[sid], item, f"source {sid}"))) is not None}
        if not positives:
            continue
        if kind == CX_CODES:
            value: Any = next(c for c in codes if c in positives.values())
        else:
            value = next(iter(positives.values()))  # yes, or the first non-empty list in pool order
        holders = [sid for sid, p in positives.items() if p == value]
        out[item] = {
            "value": value,
            "input_support_ids": [n["support_id"] for sid in holders for n in rows[sid].get("item_support", ())
                                  if n.get("item_id") == item],
            "source_ids": holders,
            "observation_ids": [k for k in order if inst.observation_inputs[k].source_id in holders],
            "combining_rule_ref": CX_RULE_REF,
        }
    return _signed(CX_ROLLUP, out)


# ---------------------------------------------------------------------------
# All A8 values of one activity
# ---------------------------------------------------------------------------


def merged_values_a8(inst: Any, order: Sequence[str]) -> dict[str, Any]:
    """The A8 values (:data:`PRODUCED`) of an activity from its pooled observations in pool order
    (ruling 78 a: a single-observation activity's pool is that observation)."""
    date, chosen = merged_stage_as_of(inst, order)
    return {STAGE_AS_OF: date, UPPER_BOUND: merged_date_upper_bound(inst, chosen),
            UNIT_CREDIT: merged_unit_credit(inst, order), VENDOR_CLAIM_ONLY: merged_vendor_claim_only(inst, order),
            CX_ROLLUP: cx_display_rollup(inst, order)}


__all__ = [
    "CX_CODES", "CX_NON_EMPTY", "CX_POSITIVE", "CX_POSITIVE_APPROVED", "CX_YES", "PRODUCED", "YEAR_ITEMS",
    "DatedObservation", "MalformedA8Value", "UnruledMergeError", "cx_display_rollup", "is_future_year", "latest",
    "merged_date_upper_bound", "merged_stage_as_of", "merged_unit_credit", "merged_values_a8",
    "merged_vendor_claim_only", "observation_stage_as_of", "observation_unit_credit", "source_type_of",
    "supporting_sources",
]
