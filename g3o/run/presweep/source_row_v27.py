"""T-015 source-row assembler for the v2.7 per-page stage (PI ruling 35 a, 2026-11-12).

Ruling 35 a: "A T-015 source-row assembler builds the whole source row after
coding (page-level fields from ``PageUpstream.page_fields`` included)." This
module is that assembler, plus the per-observation activity-row values the
signed rules let it derive. :func:`assemble` runs after a page is coded (in
:func:`g3o.run.presweep.stage_perpage_v27.produce_page`) on the stored page,
its :class:`~g3o.run.presweep.perpage_inputs_v27.PageSourceFields` and the
final page and activity values.

Every source-row and activity-row item that the T-021 / T-023 coders do not
produce is listed exactly once, either as produced here or in
:data:`REFUSED_SOURCE_ITEMS` / :data:`REFUSED_ACTIVITY_ITEMS` with the reason it
is refused. No value is invented: a refused item stays refused until its rule
is signed or its producer is wired, and while any item is refused the per-page
stage stops before it would publish a row (``MissingUpstreamError``, RC-D-033
C2 a) and :data:`g3o.run.presweep.perpage_inputs_v27.MISSING_PRODUCERS` keeps
the row-values entry, naming these items (PI ruling 36 a).

Produced here (source row, page-level, the same on every source row of a page):

- ``source_url``, ``source_access_date``, ``source_language``,
  ``syndication_group``: :class:`PageSourceFields` (X28, A3, A4; PI D1 a).
- ``source_title``: ``RenderedPage.title`` when it is not empty
  (``items/core.source_title/rules/0``); an empty title is refused, since the
  first-heading fallback stays unproduced (PI ruling 39 a).
- ``page_review_state``: ``reviewed``. A page reaches the assembler only after
  T-021 coded it; the signed non-``reviewed`` codes are fetch failures and
  links not followed (``rules/1``: "the review status keeps only failed
  downloads and links not followed"), and an unreadable page is ``reviewed``
  (SPEC R-015, RC-D-021 D-2 a).
- ``content_contact``: ``yes`` if ``content_contact_named`` or
  ``content_contact_details`` is ``yes`` (``items/core.content_contact/rules/0``),
  ``no`` if both are ``no``; any other pair (a missing token and no ``yes``)
  has no signed rule and is refused (:class:`~g3o.common.source_fields.UnruledError`).
- ``content_contact_emails``: :func:`g3o.common.support_check.extract_contact_emails`
  (CX-53, ``rules/0``-``2``; RC-D-019 E2 a) over the main text, the chrome text
  (header and footer, T-014) and the page's e-mail links.
- ``content_purpose``, ``content_users``, ``content_status_date``
  (``items/core.content_contact/rules/0``): ``no`` unless the final page
  verdict is one of the GenAI-bearing values (the ``content_data`` gate);
  else ``yes`` when any activity on the page has a value stated in the matching
  field (purpose: the function items; users: ``target_users`` or
  ``governed_population``; status or date: ``adoption_stage`` or a year
  field), otherwise ``no``. "Stated" is read as: ``yes`` for a yes/no item,
  any value other than a signed missing token for the others.
- ``content_human_oversight``, ``content_risk_assessment``,
  ``content_user_notification`` (``rules/2`` of each): ``yes`` if any activity
  on the page is ``yes`` on ``has_human_oversight`` / ``has_risk_assessment``
  / ``has_transparency_notice``, otherwise ``no``.

Produced here (activity row, per observation):

- ``unit_credit``: ``yes`` if and only if the ``relationship`` part of
  ``observed_actor_relationship`` is ``unit_of_institution`` (PI A8.7 a,
  2026-11-11).

Built but not yet usable (its input is refused): :func:`vendor_claim_only`
(PI A8.9 a) reads ``source_type``.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from g3o.common import source_fields as sf
from g3o.common import support_check as sc
from g3o.common.storage import METADATA_ITEMS, table_fields
from g3o.common.storage_fields import FIELDS

ASSEMBLER = "T-015 source-row assembler (PI ruling 35 a)"

#: Coders whose values the per-page stage itself produces (T-021 / T-023), never this assembler.
CODER_PRODUCED = frozenset({"classifier"})
#: The one classifier item T-015 owns (residual question, RC-D-023 B-Q3 a); it is a row value here.
T015_CLASSIFIER = sf.SOURCE_TYPE
#: Activity-row items the per-page stage produces itself or the activities table leaves to consolidation.
STAGE_ACTIVITY_ITEMS = frozenset({"core.uncertainty_flags", "core.confidence", "core.n_sources"})

REVIEWED = "reviewed"
YES, NO = "yes", "no"

#: content_* items derived from activity fields (items/core.content_contact/rules/0).
STATED_FIELDS: Mapping[str, Callable[[str], bool]] = {
    "core.content_purpose": lambda item: item.startswith("core.function_"),
    "core.content_users": lambda item: item in ("core.target_users", "core.governed_population"),
    "core.content_status_date": lambda item: item == "core.adoption_stage" or item.startswith("core.year_"),
}
#: Page safeguard items and their per-activity question (rules/0-2 of each content_* safeguard item).
SAFEGUARDS: Mapping[str, str] = {
    "core.content_human_oversight": "core.has_human_oversight",
    "core.content_risk_assessment": "core.has_risk_assessment",
    "core.content_user_notification": "core.has_transparency_notice",
}
CONTACT_PARTS = ("core.content_contact_named", "core.content_contact_details")
RELATIONSHIP = "core.observed_actor_relationship"
RELATIONSHIP_PART = "relationship"
UNIT_OF_INSTITUTION = "unit_of_institution"
VENDOR = "vendor"

_QUOTE_STEP_PLUMBING = (
    "a quote-step value needs its T-022 coder record (extractor model, response model, request id of "
    "the pass-1 response) and its T-024 support result; the pass-1 extraction "
    "(Pass1Extraction) stays inside the provider adapter (perpage_providers_v27) and is not passed to "
    "produce_page")

#: Source-row items refused here, with the reason (signed source text or the missing producer).
REFUSED_SOURCE_ITEMS: Mapping[str, str] = {
    sf.DISCOVERY: ("unruled: no signed value spellings ('searched / followed hop n / back-fill followed', "
                   "codebook items/core.discovery_path/rules/0, X18; SPEC R-034, R-036); also needs T-025 "
                   "follow provenance"),
    sf.TEXT_SOURCE: ("unruled: no signed value spellings ('stored / live re-fetch / new run', codebook "
                     "items/core.text_source/rules/0; SPEC R-059; RC-D-002 F)"),
    sf.OFFICIAL: ("the master official-site overlay (OfficialSiteOverlay, RC-D-025 P13) is not passed to "
                  "the v2.7 per-page stage"),
    sf.SOURCE_TYPE: ("rules/0 needs source_on_official_domain (refused); the residual source_type question "
                     "(T-015's own jev request, RC-D-023 B-Q3 a) is not wired into the per-page stage, and "
                     "T-022 has no source_type quote task for its support check"),
    sf.CREDIBILITY: "reads source_type and source_publication_date (both refused)",
    sf.CONFIDENCE: ("reads source_credibility (refused) and the claim's support records "
                    "(items/core.confidence/rules/1; association is T-026's, RC-D-025 P12)"),
    sf.DATE: ("quote_step item: the A1 metadata/URL date is in page_fields, but the row needs a support node "
              "for it and no signed support representation exists for a metadata date; a quote-step date "
              f"is Pass1Extraction.publication_date, and {_QUOTE_STEP_PLUMBING}"),
    sf.UPPER_BOUND: "reads source_publication_date (refused)",
    sf.SNIPPET: f"quote_step item: {_QUOTE_STEP_PLUMBING}",
    "core.content_tool_or_model": ("reads tool_name / model_name (activity quote-step values, refused); whether "
                                   "an extracted name that fails R-042 counts as 'stated' is not ruled"),
    "core.content_vendor": ("reads developer (PI A8.1 a needs codebook r16) and contracting_party (activity "
                            "quote-step value, refused)"),
}

#: Activity-row items refused here, with the reason.
REFUSED_ACTIVITY_ITEMS: Mapping[str, str] = {
    **{item: f"quote_step item: {_QUOTE_STEP_PLUMBING}" for item in (
        "core.activity_name", "core.observed_actor_name", "core.tool_name", "core.model_name",
        "core.contracting_party", "core.deployment_scale_number", "core.reported_outcomes",
        "core.reported_incidents")},
    "core.developer": ("PI A8.1 a (page-stated developer as a quote-step item) needs codebook r16 and a "
                       "re-signature; A8.2 a: no lookup table, looked_up never set"),
    "core.developer_basis": "reads developer (refused); PI A8.1 a / A8.2 a",
    "core.stage_as_of": ("PI A8.3 a / A8.4 a: reads source_publication_date (refused), then the activity's "
                         "latest supported year code, then the access date"),
    "core.stage_as_of_basis": "PI A8.5 a (three step codes) needs codebook r16 and a re-signature",
    "core.vendor_claim_only": "PI A8.9 a reads source_type (refused); vendor_claim_only() is built",
    "core.cx_display_rollup": ("PI A8.10 a: 'positive' for multi-value items is defined in the build and "
                               "shown to the PI first; not yet shown"),
    "core.date_upper_bound": "PI A8.11 a: reads stage_as_of (refused); A8.12 a: no archive lookup",
}


def source_row_items() -> frozenset[str]:
    """Source-row items that are row values (not produced by the coders), as ``produce_page`` reads them."""
    items = set(table_fields("sources")) - set(METADATA_ITEMS)
    return frozenset(i for i in items if FIELDS[i]["coder"] not in CODER_PRODUCED or i == T015_CLASSIFIER)


def activity_row_items() -> frozenset[str]:
    """Activity-row items that are row values (not produced by the coders or the per-page stage)."""
    items = set(table_fields("activities")) - set(METADATA_ITEMS) - STAGE_ACTIVITY_ITEMS
    return frozenset(i for i in items if FIELDS[i]["coder"] not in CODER_PRODUCED)


#: Source-row items produced by :func:`page_source_values`.
PRODUCED_SOURCE_ITEMS = (
    sf.URL, sf.ACCESS_DATE, sf.LANGUAGE, sf.SYNDICATION, sf.TITLE, sf.REVIEW_STATE,
    sc.CONTACT_ITEM, sc.CONTACT_EMAILS_ITEM, *STATED_FIELDS, *SAFEGUARDS,
)
#: Activity-row items produced by :func:`activity_row_values`.
PRODUCED_ACTIVITY_ITEMS = ("core.unit_credit",)


def unproduced_items() -> tuple[str, ...]:
    """Every row item no producer supplies yet (refused here), sorted."""
    return tuple(sorted({*REFUSED_SOURCE_ITEMS, *REFUSED_ACTIVITY_ITEMS}))


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RowValue:
    """One assembled row value and the rule or input that fixed it."""

    item_id: str
    value: Any
    basis: str


@lru_cache(maxsize=1)
def genai_verdicts() -> frozenset[str]:
    """The GenAI-bearing page verdicts: the signed gate of ``content_data`` (``content_contact/rules/0``)."""
    gate = sf.default_codebook().items["core.content_data"].get("gate") or {}
    values = gate.get("values") if isinstance(gate, Mapping) else None
    if gate.get("item") != "core.page_verdict" or not values:
        raise ValueError("the signed content_data gate does not name the page verdicts")
    return frozenset(str(v) for v in values)


def _missing_tokens(item: str) -> frozenset[str]:
    return frozenset(str(t) for t in (sf.default_codebook().items[item].get("missing_tokens") or ()))


def stated(item: str, value: Any) -> bool:
    """A value stated on the page: ``yes`` for a yes/no item, else any value but a signed missing token."""
    if value is None:
        return False
    if FIELDS[item]["answer_type"] == "yes_no":
        return value == YES
    return str(value) not in _missing_tokens(item)


def _row(item: str, value: Any, basis: str) -> RowValue:
    return RowValue(item, value, basis)


def _field(fv: sf.FieldValue | None, item: str) -> RowValue:
    if fv is None or fv.item_id != item:
        raise sf.MissingUpstreamError("perpage_inputs_v27.PageSourceFields", [item])
    return RowValue(item, fv.value, fv.basis)


def source_title(page: Any) -> RowValue:
    """``RenderedPage.title`` when not empty; the heading fallback stays unproduced (PI ruling 39 a)."""
    if page.title is None or not page.title.strip():
        raise sf.MissingUpstreamError("source_title first-heading fallback (unproduced, PI ruling 39 a)",
                                      [sf.TITLE])
    fv = sf.source_title(page.title, None)
    return RowValue(sf.TITLE, fv.value, fv.basis)


def content_contact(page_values: Mapping[str, Any]) -> RowValue:
    """``yes`` if either sub-item is ``yes``; ``no`` if both are ``no``; anything else is unruled."""
    pair = [page_values.get(i) for i in CONTACT_PARTS]
    if YES in pair:
        return _row(sc.CONTACT_ITEM, YES, "items/core.content_contact/rules/0: a sub-item is yes")
    if pair == [NO, NO]:
        return _row(sc.CONTACT_ITEM, NO, "items/core.content_contact/rules/0: both sub-items are no")
    raise sf.UnruledError(sc.CONTACT_ITEM, f"sub-items {dict(zip(CONTACT_PARTS, pair, strict=True))}: "
                                           "rules/0 states yes if either is yes, nothing else")


def content_contact_emails(contact: str, page: Any) -> RowValue:
    """CX-53 over the main text, the chrome text (header and footer) and the page's e-mail links.

    T-014 stores ``email_links`` as bare addresses (``mailto:`` stripped,
    :func:`g3o.scrape.html.extract_email_links`), while the T-024 helper reads
    ``mailto:`` hrefs; each address is passed back as ``mailto:<address>`` so the
    helper's signed regex reads it. The chrome text (T-014 header and footer, one
    field) is passed as the header text; ``None`` (not measured) is skipped.
    """
    links = tuple(f"mailto:{address}" for address in (page.email_links or ()))
    value = sc.extract_contact_emails(contact, page.text, header_text=page.chrome_text, email_links=links)
    return _row(sc.CONTACT_EMAILS_ITEM, value, "items/core.content_contact_emails/rules/0-2 (CX-53)")


def content_stated(item: str, verdict: Any, activities: Sequence[Mapping[str, Any]]) -> RowValue:
    """A derived page-description item: ``no`` off GenAI pages, else ``yes`` when any activity states it."""
    if verdict not in genai_verdicts():
        return _row(item, NO, f"items/core.content_contact/rules/0: page verdict {verdict!r} is not GenAI-bearing")
    matches = STATED_FIELDS[item]
    hits = sorted({k for values in activities for k, v in values.items() if matches(k) and stated(k, v)})
    if hits:
        return _row(item, YES, f"items/core.content_contact/rules/0: stated in {hits}")
    return _row(item, NO, "items/core.content_contact/rules/0: no activity states a matching field")


def content_safeguard(item: str, activities: Sequence[Mapping[str, Any]]) -> RowValue:
    """``yes`` if any activity on the page is ``yes`` on the safeguard question, otherwise ``no``."""
    question = SAFEGUARDS[item]
    value = YES if any(values.get(question) == YES for values in activities) else NO
    return _row(item, value, f"items/{item}/rules/2: from {question}")


def unit_credit(activity_values: Mapping[str, Any]) -> RowValue:
    """PI A8.7 a: ``yes`` if and only if ``observed_actor_relationship`` is ``unit_of_institution``."""
    parts = activity_values.get(RELATIONSHIP)
    if not isinstance(parts, Mapping) or RELATIONSHIP_PART not in parts:
        raise sf.MissingUpstreamError(f"T-023 final {RELATIONSHIP} ({RELATIONSHIP_PART} part)",
                                      ["core.unit_credit"])
    value = YES if parts[RELATIONSHIP_PART] == UNIT_OF_INSTITUTION else NO
    return _row("core.unit_credit", value, f"PI A8.7 a: {RELATIONSHIP}/{RELATIONSHIP_PART} = "
                                           f"{parts[RELATIONSHIP_PART]!r}")


def vendor_claim_only(source_type: str) -> RowValue:
    """PI A8.9 a for one source: ``yes`` when its type is ``vendor``; a missing type gives ``unknown``."""
    if source_type in _missing_tokens(sf.SOURCE_TYPE):
        return _row("core.vendor_claim_only", "unknown", f"PI A8.9 a: source_type {source_type!r} is missing")
    if source_type not in (sf.default_codebook().codes(sf.SOURCE_TYPE) or ()):
        raise ValueError(f"source_type {source_type!r} is not a signed code")
    value = YES if source_type == VENDOR else NO
    return _row("core.vendor_claim_only", value, f"PI A8.9 a: source_type {source_type!r}")


# ---------------------------------------------------------------------------
# The assembler
# ---------------------------------------------------------------------------


_REFUSALS = (sf.UnruledError, sf.MissingUpstreamError)


@dataclass
class AssembledRows:
    """What :func:`assemble` built for one coded page, and what it refused (item -> reason).

    ``source`` holds the page-level source-row values (the same on every source
    row of the page); ``activities`` the activity-row values per T-022 activity
    id. ``refused`` names every row item not produced: the standing refusals
    (:data:`REFUSED_SOURCE_ITEMS`, :data:`REFUSED_ACTIVITY_ITEMS`) and any
    producer that refused on this page's data.
    """

    source: dict[str, RowValue] = field(default_factory=dict)
    activities: dict[str, dict[str, RowValue]] = field(default_factory=dict)
    refused: dict[str, str] = field(default_factory=dict)


def _try(rows: AssembledRows, out: dict[str, RowValue], item: str, make: Callable[[], RowValue]) -> None:
    try:
        out[item] = make()
    except _REFUSALS as exc:
        rows.refused[item] = str(exc)


def page_source_values(page: Any, page_fields: Any, page_values: Mapping[str, Any],
                       activities: Mapping[str, Mapping[str, Any]], rows: AssembledRows) -> None:
    """The page-level source-row values (see the module docstring) into ``rows.source``."""
    out = rows.source
    for item, attr in ((sf.URL, "url"), (sf.ACCESS_DATE, "access_date"), (sf.LANGUAGE, "language"),
                       (sf.SYNDICATION, "syndication_group")):
        _try(rows, out, item, lambda item=item, attr=attr: _field(getattr(page_fields, attr, None), item))
    _try(rows, out, sf.TITLE, lambda: source_title(page))
    _try(rows, out, sf.REVIEW_STATE, lambda: RowValue(
        sf.REVIEW_STATE, sf.page_review_state(REVIEWED).value,
        "page coded by T-021 (items/core.page_review_state/rules/1; SPEC R-015, RC-D-021 D-2 a)"))
    _try(rows, out, sc.CONTACT_ITEM, lambda: content_contact(page_values))
    if sc.CONTACT_ITEM in out:
        _try(rows, out, sc.CONTACT_EMAILS_ITEM,
             lambda: content_contact_emails(out[sc.CONTACT_ITEM].value, page))
    else:
        rows.refused[sc.CONTACT_EMAILS_ITEM] = f"gated on {sc.CONTACT_ITEM} (refused)"
    acts = [activities[aid] for aid in activities]
    verdict = page_values.get("core.page_verdict")
    for item in STATED_FIELDS:
        _try(rows, out, item, lambda item=item: content_stated(item, verdict, acts))
    for item in SAFEGUARDS:
        _try(rows, out, item, lambda item=item: content_safeguard(item, acts))


def activity_row_values(activities: Mapping[str, Mapping[str, Any]], rows: AssembledRows) -> None:
    """The per-observation activity-row values (``unit_credit``) into ``rows.activities``."""
    for aid, values in activities.items():
        out = rows.activities.setdefault(aid, {})
        _try(rows, out, "core.unit_credit", lambda values=values: unit_credit(values))


def assemble(page: Any, page_fields: Any, page_values: Mapping[str, Any],
             activities: Mapping[str, Mapping[str, Any]]) -> AssembledRows:
    """Build every producible row value of one coded page and name every refused item.

    ``page`` is the :class:`~g3o.classify.jev_page_code.PageInput`,
    ``page_fields`` its :class:`~g3o.run.presweep.perpage_inputs_v27.PageSourceFields`,
    ``page_values`` the final page values and ``activities`` the final values of
    each coded activity (``{activity_id: values}``; empty on a page with no activity).
    """
    if page_fields is None:
        raise sf.MissingUpstreamError("perpage_inputs_v27.PageSourceFields (PageUpstream.page_fields)",
                                      [page.page_id])
    rows = AssembledRows()
    rows.refused.update(REFUSED_SOURCE_ITEMS)
    if activities:
        rows.refused.update(REFUSED_ACTIVITY_ITEMS)
    page_source_values(page, page_fields, page_values, activities, rows)
    activity_row_values(activities, rows)
    return rows


__all__ = [
    "ASSEMBLER", "PRODUCED_ACTIVITY_ITEMS", "PRODUCED_SOURCE_ITEMS", "REFUSED_ACTIVITY_ITEMS",
    "REFUSED_SOURCE_ITEMS", "AssembledRows", "RowValue", "activity_row_items", "activity_row_values", "assemble",
    "content_contact", "content_contact_emails", "content_safeguard", "content_stated", "genai_verdicts",
    "page_source_values", "source_row_items", "source_title", "stated", "unit_credit", "unproduced_items",
    "vendor_claim_only",
]
