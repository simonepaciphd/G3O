"""A8 producers of a merged activity's derived values (Stage 6; PI A8 rulings, 2026-11-11).

RC-D-030 X1 a R1 asks Stage 6 to re-derive these values for a merged activity;
RC-D-032 B1 a kept them refused until per-source producers existed. The PI
ruled the A8 questions on 2026-11-11 ("All recs accepted";
``agent-workspace/2026-11-10-build/QUESTIONS-overnight.md`` section A8,
``RULINGS-overnight-2026-11-11.md``) and ruling 66 a on 2026-11-13
(``RULINGS-builds-2026-11-11.md``). Every function reads the pooled
(confirmed) observations' stored activity rows (``observation_inputs``) and the
institution's stored source rows (``sources``); nothing is looked up.

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
  stored four-digit year is a supported one); else the source's
  ``core.source_access_date``. A8.6 a: a merged activity takes the latest
  date among its pooled observations (:func:`merged_stage_as_of`). Dates of
  different precision are compared as calendar spans; when no date is
  strictly later than every other distinct date (e.g. ``2024`` beside
  ``2024-03-12``) the latest is not determined by the signed rule and the
  value is refused (:class:`UnruledMergeError`, a PI question).
- ``core.date_upper_bound`` at activity level (A8.11 a: its target is
  ``stage_as_of``; A8.12 a: no archive first-capture lookup). When the chosen
  date is a source's publication date, the source row's stored
  ``core.date_upper_bound`` (the source-level producer,
  :func:`g3o.common.source_fields.date_upper_bound`) is used; a year code or
  an access date is not an archive bound, so ``no`` (the same rule: ``yes``
  only for the ``archive_upper_bound`` origin).
- ``core.unit_credit`` (A8.7 a, ruling 66 a): ``yes`` iff the observation's
  ``core.observed_actor_relationship`` relationship part is
  ``unit_of_institution``, read literally (any other value, a missing token
  included, gives ``no``). A8.8 a: merged ``yes`` if any pooled observation is.
- ``core.vendor_claim_only`` (r2#28, A8.9 a): ``yes`` only if every
  supporting source (the pooled observations' source claims) has
  ``source_type`` ``vendor``; any missing type gives ``unknown``. A page typed
  automatically (official domain or archive address, ``items/core.source_type/rules/0``,
  stored as ``not_asked``) has a type and is not ``vendor``: the signed
  credibility map (``items/core.source_credibility/rules/1``) counts as
  missing only ``not_documented``, ``unknown`` and ``not_asked`` on an
  unreadable page. Automatic typing is recognised by re-running rule 0 on
  the stored row (:func:`g3o.common.source_fields.route_source_type`).

Built but not used (:func:`cx_display_rollup`, A8.10 a): the "positive" of each
CX item is defined in :data:`CX_POSITIVE` and must be approved by the PI
before Stage 6 relies on it (RULINGS-overnight-2026-11-11 follow-up 5); until
then ``core.cx_display_rollup`` stays an explicit input.

A stored value an A8 rule reads that is absent raises
:class:`~g3o.persist.stage6_adapters.MissingUpstreamError`; a value outside its
signed form raises ``ValueError``. Nothing is guessed.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from g3o.common.source_fields import FieldValue, route_source_type, source_archive_address
from g3o.common.storage import table_fields
from g3o.common.storage_fields import FIELDS
from g3o.persist.stage6_adapters import MissingUpstreamError

STAGE_AS_OF = "core.stage_as_of"
UPPER_BOUND = "core.date_upper_bound"
UNIT_CREDIT = "core.unit_credit"
VENDOR_CLAIM_ONLY = "core.vendor_claim_only"
CX_ROLLUP = "core.cx_display_rollup"
#: The A8 values Stage 6 produces for a merged activity (order of the activities table is not implied).
PRODUCED = (STAGE_AS_OF, UPPER_BOUND, UNIT_CREDIT, VENDOR_CLAIM_ONLY)

PUBLICATION_DATE = "core.source_publication_date"
ACCESS_DATE = "core.source_access_date"
SOURCE_TYPE = "core.source_type"
OFFICIAL = "core.source_on_official_domain"
SOURCE_URL = "core.source_url"
RELATIONSHIP = "core.observed_actor_relationship"
#: The three year items (codebook ``family: dates``; X35 label_rules "the three year items").
YEAR_ITEMS = ("core.year_announced", "core.year_pilot_start", "core.year_production_start")
UNIT_OF_INSTITUTION = "unit_of_institution"
VENDOR = "vendor"
NOT_ASKED = "not_asked"
UNKNOWN = "unknown"

PRODUCER = "Stage 6 merged-activity A8 producer"
_DATE = re.compile(r"^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$")
_YEAR = re.compile(r"^[0-9]{4}$")

# Step names (internal: core.stage_as_of_basis stays refused until codebook r16, A8.5 a).
STEP_PUBLICATION = "publication"
STEP_STATED = "stated"
STEP_ACCESS = "access"


class UnruledMergeError(ValueError):
    """A merged value the signed rules do not determine for these inputs (a PI question)."""

    def __init__(self, item: str, detail: str) -> None:
        super().__init__(f"{item}: {detail}; not determined by the signed rule (PI question)")
        self.item, self.detail = item, detail


def _yes_no(item: str) -> tuple[str, str]:
    yes, no = FIELDS[item]["codes"]
    return yes, no


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
    """True for a real date of ``item``, False for one of its missing tokens; anything else refuses."""
    if isinstance(value, str) and value in _tokens(item):
        return False
    if isinstance(value, str) and _DATE.fullmatch(value):
        return True
    raise ValueError(f"{item} {value!r} of {where} is neither a date nor a missing token")


@dataclass(frozen=True)
class DatedObservation:
    """One observation's ``stage_as_of`` with the rule step that fixed it and its source claim."""

    observation_id: str
    source_id: str
    date: str
    step: str


def observation_stage_as_of(inst: Any, oid: str) -> DatedObservation:
    """``items/core.stage_as_of/rules/0`` for one observation (A8.3 a, A8.4 a)."""
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
            raise ValueError(f"{item} {value!r} of observation {oid} is neither a year code nor a missing token")
        years.append(value)
    if years:
        return DatedObservation(oid, sid, max(years, key=int), STEP_STATED)
    access = _get(src, ACCESS_DATE, where)
    if not _real_date(ACCESS_DATE, access, where):
        raise MissingUpstreamError(f"{PRODUCER}: access date of {where} (last step of stage_as_of)", [ACCESS_DATE])
    return DatedObservation(oid, sid, access, STEP_ACCESS)


def _span(date: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """First and last day a ``YYYY`` / ``YYYY-MM`` / ``YYYY-MM-DD`` date can mean (31 days as an upper bound)."""
    parts = [int(p) for p in date.split("-")]
    year = parts[0]
    month = parts[1] if len(parts) > 1 else None
    day = parts[2] if len(parts) > 2 else None
    return (year, month or 1, day or 1), (year, month or 12, day or 31)


def latest(dated: Sequence[DatedObservation]) -> list[DatedObservation]:
    """A8.6 a: the observations carrying the latest date; refused when the latest is not determined."""
    if not dated:
        raise ValueError("no pooled observation to date")
    distinct = sorted({d.date for d in dated}, key=_span)
    best = max(distinct, key=lambda d: _span(d)[0])
    start = _span(best)[0]
    overlapping = [d for d in distinct if d != best and _span(d)[1] >= start]
    if overlapping:
        raise UnruledMergeError(STAGE_AS_OF, f"latest of {sorted(distinct)} is not determined ({best!r} "
                                             f"overlaps {sorted(overlapping)})")
    return [d for d in dated if d.date == best]


def merged_stage_as_of(inst: Any, order: Sequence[str]) -> tuple[str, list[DatedObservation]]:
    """``core.stage_as_of`` of a merged activity and the pooled observations that carry it."""
    chosen = latest([observation_stage_as_of(inst, k) for k in order])
    return chosen[0].date, chosen


def merged_date_upper_bound(inst: Any, chosen: Sequence[DatedObservation]) -> str:
    """A8.11 a / A8.12 a: whether the merged ``stage_as_of`` is an upper bound."""
    yes, no = _yes_no(UPPER_BOUND)
    values = set()
    for d in chosen:
        if d.step != STEP_PUBLICATION:
            values.add(no)  # a year code or an access date has no archive_upper_bound origin
            continue
        bound = _get(_source_row(inst, d.source_id), UPPER_BOUND, f"source {d.source_id}")
        if bound not in (yes, no):
            raise ValueError(f"{UPPER_BOUND} {bound!r} of source {d.source_id} is not yes/no beside the real "
                             f"publication date {d.date!r}")
        values.add(bound)
    if len(values) != 1:
        raise UnruledMergeError(UPPER_BOUND, f"observations dated {chosen[0].date!r} disagree on the upper bound")
    return values.pop()


def observation_unit_credit(inst: Any, oid: str) -> str:
    """A8.7 a / ruling 66 a: ``yes`` iff the relationship part is ``unit_of_institution``, read literally."""
    yes, no = _yes_no(UNIT_CREDIT)
    value = _get(inst.observation_inputs[oid].row, RELATIONSHIP, f"observation {oid}")
    part = next(iter(FIELDS[RELATIONSHIP]["parts"]))  # the relationship part (codebook part order)
    if isinstance(value, Mapping):
        if part not in value:
            raise MissingUpstreamError(f"{PRODUCER}: observation {oid}", [f"{RELATIONSHIP}#{part}"])
        value = value[part]
    if not isinstance(value, str):
        raise ValueError(f"{RELATIONSHIP} {value!r} of observation {oid} is not a code")
    return yes if value == UNIT_OF_INSTITUTION else no


def merged_unit_credit(inst: Any, order: Sequence[str]) -> str:
    """A8.8 a: ``yes`` if any pooled observation is ``yes``."""
    yes, no = _yes_no(UNIT_CREDIT)
    return yes if any(observation_unit_credit(inst, k) == yes for k in order) else no


def source_type_of(inst: Any, sid: str) -> str | None:
    """The source's type: a ``source_type`` code, ``official_domain`` / ``archive_address`` (typed
    automatically by rule 0, stored ``not_asked``), or None when the type is missing."""
    row = _source_row(inst, sid)
    where = f"source {sid}"
    value = _get(row, SOURCE_TYPE, where)
    if value in FIELDS[SOURCE_TYPE]["codes"]:
        return str(value)
    if value not in _tokens(SOURCE_TYPE):
        raise ValueError(f"{SOURCE_TYPE} {value!r} of {where} is not a signed code or missing token")
    if value != NOT_ASKED:
        return None
    official = _get(row, OFFICIAL, where)
    url = _get(row, SOURCE_URL, where)
    auto = route_source_type(FieldValue(OFFICIAL, str(official), "mechanical", "stored source row"),
                             source_archive_address(str(url)))
    return auto  # None: not_asked without automatic typing (an unreadable page) is a missing type


def supporting_sources(inst: Any, order: Sequence[str]) -> list[str]:
    """The pooled observations' source claims, in pool order, each once."""
    out: list[str] = []
    for k in order:
        sid = inst.observation_inputs[k].source_id
        if sid not in out:
            out.append(sid)
    return out


def merged_vendor_claim_only(inst: Any, order: Sequence[str]) -> str:
    """A8.9 a: ``yes`` only if every supporting source is ``vendor``; any missing type gives ``unknown``."""
    yes, no = _yes_no(VENDOR_CLAIM_ONLY)
    types = [source_type_of(inst, sid) for sid in supporting_sources(inst, order)]
    if any(t is None for t in types):
        return UNKNOWN
    return yes if all(t == VENDOR for t in types) else no


def merged_values_a8(inst: Any, order: Sequence[str]) -> dict[str, Any]:
    """The A8 values of a merged activity (:data:`PRODUCED`) from its pooled observations in pool order."""
    date, chosen = merged_stage_as_of(inst, order)
    return {STAGE_AS_OF: date, UPPER_BOUND: merged_date_upper_bound(inst, chosen),
            UNIT_CREDIT: merged_unit_credit(inst, order), VENDOR_CLAIM_ONLY: merged_vendor_claim_only(inst, order)}


# ---------------------------------------------------------------------------
# A8.10 a: cx_display_rollup (mechanism only; NOT used until the PI approves CX_POSITIVE)
# ---------------------------------------------------------------------------

#: How a CX item's positive is read: ``yes`` (yes/no item: the code ``yes``), ``non_empty`` (list
#: item: at least one entry), ``codes`` (single item: one of the listed codes; the display value is
#: the first of them, in codebook value order, among the sources' positives).
CX_YES, CX_NON_EMPTY, CX_CODES = "yes", "non_empty", "codes"

#: A8.10 a: every CX item stored per source claim (codebook CX-01.3 items whose storage target is
#: ``sources``), with the build's definition of "positive". DRAFT: shown to the PI, not approved.
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
#: The PI has not approved :data:`CX_POSITIVE` (A8.10 a); Stage 6 does not call :func:`cx_display_rollup`.
CX_POSITIVE_APPROVED = False


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
CX_RULE_REF = "items/core.cx_display_rollup/rules/0 (A8.10 a; positive table CX_POSITIVE, draft)"


def cx_display_rollup(inst: Any, order: Sequence[str]) -> dict[str, dict[str, Any]]:
    """A8.10 a mechanism: one entry per CX item with a positive in any supporting source.

    The D-007 named object (validated by :mod:`g3o.common.storage`): ``{item_id: {"value",
    "input_support_ids", "source_ids", "observation_ids", "combining_rule_ref"}}``, in
    :data:`CX_POSITIVE` order. ``value``: ``yes`` for a yes/no item; for a single item the first
    positive in codebook value order; for a list item the first non-empty list in pool order.
    ``source_ids`` / ``observation_ids``: the supporting sources holding that value and their pooled
    observations; ``input_support_ids``: those sources' stored support nodes of the item. A stored
    positive is taken as supported (the ``support_required`` items store their downgrade target when
    unsupported). Refused while :data:`CX_POSITIVE_APPROVED` is False.
    """
    if not CX_POSITIVE_APPROVED:
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
    return out


__all__ = [
    "CX_CODES", "CX_NON_EMPTY", "CX_POSITIVE", "CX_POSITIVE_APPROVED", "CX_YES", "PRODUCED", "YEAR_ITEMS",
    "DatedObservation", "UnruledMergeError", "cx_display_rollup", "latest", "merged_date_upper_bound",
    "merged_stage_as_of", "merged_unit_credit", "merged_values_a8", "merged_vendor_claim_only",
    "observation_stage_as_of", "observation_unit_credit", "source_type_of", "supporting_sources",
]
