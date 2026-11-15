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
is refused (or, PI ruling 94 a, in :data:`STAGE6_ACTIVITY_ITEMS`: Stage 6 only).
No value is invented: a refused item stays refused until its rule is signed or
its producer is wired, and while any item is refused the per-page stage stops
before it would publish a row (``MissingUpstreamError``, RC-D-033 C2 a) and
:data:`g3o.run.presweep.perpage_inputs_v27.MISSING_PRODUCERS` keeps the
row-values entry, naming these items (PI ruling 36 a). PI ruling 97 b: an item
refused on a page's own data (:data:`CONDITIONAL_ITEMS`, not for a missing
wiring input) holds that institution instead (:attr:`AssembledRows.stops`).

Produced here (source row, page-level, the same on every source row of a page):

- ``source_url``, ``source_access_date``, ``source_language``,
  ``syndication_group``: :class:`PageSourceFields` (X28, A3, A4; PI D1 a).
- ``text_source``: :class:`PageSourceFields` (``new_run`` for a new run's
  rows, PI ruling 62 a).
- ``discovery_path``: from ``PageUpstream.followed`` and ``PageUpstream.hop``
  (PI ruling 61 a): a page not followed is ``searched``; a followed page is
  ``followed_hop_<n>`` with the hop the T-025 follow leg
  (:mod:`g3o.run.presweep.follow_v27`) gives it, and is refused without one.
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
  ``no`` if both are ``no``; a missing token and no ``yes`` gives ``unknown``
  (PI ruling 64 b, 2026-11-13).
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
- ``content_tool_or_model``, ``content_vendor``: the same GenAI gate; ``yes``
  when any activity's T-022 span has an extracted ``tool_name`` /
  ``model_name`` (resp. ``contracting_party``), any extracted value counting (PI
  ruling 65 a); otherwise ``no``, except that ``content_vendor`` then reads the
  developer (no producer, PI A8.1 a needs codebook r16) and is refused.
- ``content_human_oversight``, ``content_risk_assessment``,
  ``content_user_notification`` (``rules/2`` of each): ``yes`` if any activity
  on the page is ``yes`` on ``has_human_oversight`` / ``has_risk_assessment``
  / ``has_transparency_notice``, otherwise ``no``.

- ``source_snippet`` (X25): the final page verdict's supporting quote
  (:func:`g3o.common.source_fields.source_snippet`, R-042), with a quote-step
  coder record carrying the page's T-022 pass-1 request provenance. A verdict
  support with no quote (including a verdict set by rule, e.g. an unreadable
  page) gives ``not_asked``, set by rule :data:`NO_VERDICT_QUOTE_RULE` (PI
  ruling 72 a).

- ``source_publication_date`` (X26): the A1 metadata/URL date with
  ``set_by_rule`` support naming ``deterministic_date:metadata`` or
  ``deterministic_date:web_address`` (PI rulings 63 a, 92 b); otherwise the T-022
  quote-step date checked under R-042 (``unknown`` when it fails), or
  ``not_documented`` when pass 1 returned none. ``date_upper_bound``:
  :func:`g3o.common.source_fields.date_upper_bound` on it.

Produced here (activity row, per observation):

- ``unit_credit``: ``yes`` if and only if the ``relationship`` part of
  ``observed_actor_relationship`` is ``unit_of_institution`` (PI A8.7 a,
  2026-11-11).
- The T-022 pass-1 activity fields (``activity_name``, ``observed_actor_name``,
  ``tool_name``, ``model_name``, ``contracting_party``,
  ``deployment_scale_number``), from the activity's span in the page's pass-1
  request (``PerPageProviders.page_extraction``): the signed applicability gate
  first (a ``not_asked`` cell sets ``not_asked`` by rule ``gated_out:<gate
  item>``, the T-023 convention); then the extracted value with its quote,
  checked by T-024 (no X35: none of these items has an entailment label); no
  value returned gives ``not_documented``. Each code carries a quote-step coder
  record (``answer_type`` ``extracted``; the instrument's extractor model and
  question-set version; the response's actual model and request id, refused
  when absent, D-007). A part id the coded page no longer has (superseded, e.g.
  after an extra-round halving) is refused, never looked up.
- ``reported_outcomes`` / ``reported_incidents``: the gate opens at the item's
  signed gate values (PI ruling 86 b: ``discontinuation_uncertain`` opens the
  incidents gate), and the list is then the T-032 pass-2 field task of the
  page's pass-2 page request, support-checked by T-024 (PI ruling 73.1 b,
  :func:`reported_field_value`). Any other gate value (``none_reported``, a
  missing token such as ``unknown``: PI ruling 73.2 a) closes it, giving
  ``not_asked`` by rule ``gated_out:<gate item>``.

Produced here (source row, page-level), PI ruling 70 b (2026-11-13):

- ``source_on_official_domain`` (X37): the page URL's host against the
  official sites this run found
  (:class:`g3o.run.presweep.official_site_v27.RunOfficialSites`, read from
  each institution's ``2_official_site.json``; no official site: ``unknown``,
  RC-D-025 P13; a bypassed institution's master site counts, PI ruling 84 a).
  Refused without that map, and for an institution whose site is unresolved
  (see that module).
- ``source_type`` (X21) by ``items/core.source_type/rules/0``: an official page
  (``own_official`` / ``other_official``) or an archive address is typed
  automatically, ``not_asked`` set by rule ``source_type_auto:<basis>``; a
  residual page that fails the R-015 readability check is not sent,
  ``not_asked`` set by rule ``readability_failure:<reason>``. A residual
  readable page takes the residual classifier question's answer (PI ruling 95
  a, building 83 b): asked by the per-page stage before T-022 on the page's
  T-021 parts, its quote task in the page's first pass-1 request, checked by
  T-024 (no first request: checked with no quote, ``downgraded_no_quote``);
  :func:`residual_source_type_value`. Without that input it is refused
  (:data:`RESIDUAL_PRODUCER`), a wiring gap that stops the stage (PI ruling 111 a,
  :data:`WIRING_PRODUCERS`). A deciding part that failed with no answer never reaches this
  assembler: the per-page stage holds the institution before T-022 and asks the question again on
  the next run (PI ruling 110 b, :func:`residual_deciding_part_failed`).
- ``source_credibility`` (X22, :func:`g3o.common.source_fields.source_credibility`):
  ``low`` when the publication date is ``unknown`` / ``not_documented``
  whatever the type; otherwise the signed map cell of the automatic basis or of
  the (missing) type. Refused when the publication date is refused, and when
  it needs a refused ``source_type``.

Every item refused on some pages is listed in :data:`CONDITIONAL_ITEMS` (review
M2); the other produced items are in :data:`WIRING_ONLY_ITEMS` or
:data:`NEVER_REFUSED_ITEMS`.

Built but not wired: :func:`vendor_claim_only` (PI A8.9 a) reads ``source_type``
and, for a ``not_asked`` type, its stored ``set_by_rule`` rule name: a page typed
automatically counts as typed and not ``vendor`` (ruling 88 a), the same rule as
the Stage 6 producer (:mod:`g3o.validate.merged_activity_v27`). PI ruling 78 a:
Stage 6 produces the A8 values (``stage_as_of``, ``date_upper_bound``,
``unit_credit``, ``vendor_claim_only``, ``cx_display_rollup``) for every
published activity, single-observation ones included. PI ruling 94 a: Stage 6 is
the only producer of the activity-level ``stage_as_of``, ``date_upper_bound``,
``vendor_claim_only`` and ``cx_display_rollup`` (:data:`STAGE6_ACTIVITY_ITEMS`); a
per-page activity fragment carries none of them (``unit_credit`` stays produced
here too, and Stage 6 checks it against its own value).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Any

from g3o.classify.jev_activity_code import GATE_RULE
from g3o.common import source_fields as sf
from g3o.common import support_check as sc
from g3o.common.jev_record import CoderRecord
from g3o.common.part_combine import NOT_COVERED
from g3o.common.storage import METADATA_ITEMS, table_fields
from g3o.common.storage_fields import FIELDS
from g3o.extract import pass2_support, request_v27

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
#: content_* items derived from extracted activity fields (rules/0; PI ruling 65 a: any extracted value
#: counts as stated, whatever its T-024 check).
EXTRACTED_FIELDS: Mapping[str, tuple[str, ...]] = {
    "core.content_tool_or_model": ("core.tool_name", "core.model_name"),
    "core.content_vendor": ("core.contracting_party",),
}
CONTACT_PARTS = ("core.content_contact_named", "core.content_contact_details")
RELATIONSHIP = "core.observed_actor_relationship"
RELATIONSHIP_PART = "relationship"
UNIT_OF_INSTITUTION = "unit_of_institution"
VENDOR = "vendor"

#: The reported_* lists and their signed gate items (CX-61).
REPORTED_GATES = {"core.reported_outcomes": "core.outcome_kind", "core.reported_incidents": "core.incident_kind"}
#: The gate value at which both readings of the reported_* gates agree it is closed.
NONE_REPORTED = "none_reported"


def reported_open(item: str) -> tuple[str, ...]:
    """PI ruling 86 b (2026-11-13): the values that open a reported_* gate are the signed gate values of that
    item (incidents: ``quantified`` / ``qualitative`` / ``discontinuation_uncertain``; outcomes: ``quantified``
    / ``qualitative``). Ruling 73.2 a's "closed" covers every other value: ``none_reported`` and the missing
    tokens."""
    gate = sf.default_codebook().items[item]["gate"]
    return tuple(str(v) for v in gate["values"])


#: PI ruling 73.1 b (2026-11-13): an open gate's list is the T-032 pass-2 field task (RC-D-017, PI 2026-11-04
#: "5 a") of the page's pass-2 page request, read here.
MISSING_PASS2 = "T-032 pass-2 page request of this page (PerPageProviders.page_pass2)"
#: An open gate whose field task is not in the page's pass-2 page request (e.g. the gate opened only in an
#: extra round, whose request is not rebuilt on a resume): refused.
PASS2_NO_FIELD_TASK = ("the T-032 pass-2 field task of this activity in the page's pass-2 page request (PI ruling "
                       "73.1 b; a gate opened only in an extra round has none)")
MISSING_EXTRACTION = "T-022 pass-1 page request of this page (PerPageProviders.page_extraction)"
#: coder_version of a quote-step coder record: the pass-1 parser and its prompt version (procedural label).
QUOTE_STEP_CODER_VERSION = f"g3o.extract.parser_v27/{request_v27.PROMPT_VERSION}"
#: coder_version of a pass-2 field record (PI ruling 73.1 b): the pass-2 parser and its prompt version.
PASS2_CODER_VERSION = f"g3o.extract.pass2_support/{pass2_support.PROMPT_VERSION}"

#: Source-row items refused here, with the reason (signed source text or the missing producer).
REFUSED_SOURCE_ITEMS: Mapping[str, str] = {
    sf.CONFIDENCE: ("reads source_credibility (refused on some pages) and the claim's support records "
                    "(items/core.confidence/rules/1; association is T-026's, RC-D-025 P12)"),
}

#: Activity-row items refused here, with the reason.
REFUSED_ACTIVITY_ITEMS: Mapping[str, str] = {
    "core.developer": ("PI A8.1 a (page-stated developer as a quote-step item) needs codebook r16 and a "
                       "re-signature; A8.2 a: no lookup table, looked_up never set"),
    "core.developer_basis": "reads developer (refused); PI A8.1 a / A8.2 a",
    "core.stage_as_of_basis": "PI A8.5 a (three step codes) needs codebook r16 and a re-signature",
}

#: PI ruling 94 a (2026-11-14): activity-row items whose only producer is Stage 6
#: (:mod:`g3o.validate.merged_activity_v27`, ruling 78 a: every published activity, single-observation ones
#: included). A per-page activity fragment carries no value for them, so they are neither produced nor refused
#: here, and they do not block the run's entry. (``core.date_upper_bound`` here is the activity-level item;
#: the source row's ``core.date_upper_bound`` stays this assembler's, :data:`PRODUCED_SOURCE_ITEMS`.)
STAGE6_ACTIVITY_ITEMS: Mapping[str, str] = {
    item: "PI ruling 94 a: produced by Stage 6 only (merged_activity_v27, ruling 78 a)"
    for item in ("core.stage_as_of", "core.date_upper_bound", "core.vendor_claim_only", "core.cx_display_rollup")
}


def source_row_items() -> frozenset[str]:
    """Source-row items that are row values (not produced by the coders), as ``produce_page`` reads them."""
    items = set(table_fields("sources")) - set(METADATA_ITEMS)
    return frozenset(i for i in items if FIELDS[i]["coder"] not in CODER_PRODUCED or i == T015_CLASSIFIER)


def activity_row_items() -> frozenset[str]:
    """Activity-row items that are per-page row values (not produced by the coders, the per-page stage or,
    PI ruling 94 a, Stage 6 alone: :data:`STAGE6_ACTIVITY_ITEMS`)."""
    items = set(table_fields("activities")) - set(METADATA_ITEMS) - STAGE_ACTIVITY_ITEMS - set(STAGE6_ACTIVITY_ITEMS)
    return frozenset(i for i in items if FIELDS[i]["coder"] not in CODER_PRODUCED)


#: Source-row items produced by :func:`page_source_values`.
PRODUCED_SOURCE_ITEMS = (
    sf.URL, sf.ACCESS_DATE, sf.LANGUAGE, sf.SYNDICATION, sf.TITLE, sf.REVIEW_STATE, sf.DISCOVERY,
    sf.TEXT_SOURCE, sc.CONTACT_ITEM, sc.CONTACT_EMAILS_ITEM, *STATED_FIELDS, *SAFEGUARDS, sf.SNIPPET,
    sf.DATE, sf.UPPER_BOUND, *EXTRACTED_FIELDS, sf.OFFICIAL, sf.SOURCE_TYPE, sf.CREDIBILITY,
)

#: A readable residual page. PI ruling 95 a (building 83 b): the residual jev source_type question runs before
#: T-022 (the per-page stage) and its quote task rides in the page's first pass-1 request; the instrument binds
#: the residual set as its second accepted question-set version. The per-page stage hands the answers and their
#: checks to the assembler; their absence is a wiring gap (the stage stops, ruling 32 b; PI ruling 111 a: it is
#: in :data:`WIRING_PRODUCERS`).
RESIDUAL_PRODUCER = ("the residual source_type answers and their T-024 checks (PI ruling 95 a: the per-page "
                     "stage's residual question, PerPageProviders.source_type_codes)")


def pass1_activity_fields() -> tuple[str, ...]:
    """The activity quote-step items T-022 pass 1 asks (``request_v27`` rules from the signed codebook)."""
    return tuple(request_v27.default_rules().activity_fields)


#: Activity-row items produced by :func:`activity_row_values`.
PRODUCED_ACTIVITY_ITEMS = ("core.unit_credit", *pass1_activity_fields(), *REPORTED_GATES)
#: A part id the coded page no longer has (e.g. after an extra-round halving): every quote read at a part.
SUPERSEDED = "a quote or value at a part the coded page no longer has (superseded, e.g. after a halving)"
#: Items produced on some pages and refused on others, with when they refuse (review M2: every refusal point of
#: this assembler that depends on the page's data). PI ruling 97 b: such a refusal holds that institution (the
#: per-page stage), unless its cause is a missing wiring input (:data:`WIRING_PRODUCERS`), which stops the stage;
#: they are no longer in :func:`entry_refused_items`.
CONDITIONAL_ITEMS: Mapping[str, str] = {
    sf.TITLE: "refused when RenderedPage.title is empty (the first-heading fallback is unproduced, PI ruling 39 a)",
    sc.CONTACT_ITEM: ("refused when a final content_contact_named / content_contact_details value is absent or is "
                      "neither yes, no nor a signed missing token"),
    sc.CONTACT_EMAILS_ITEM: f"reads {sc.CONTACT_ITEM} (refused on some pages)",
    sf.SNIPPET: (f"refused when the final page verdict has no T-024 support at its deciding part (verdict_support "
                 f"is None), at {SUPERSEDED}, and when a quote-step record has no actual response model or "
                 "request id"),
    sf.DATE: (f"refused when the page has no metadata or URL date and pass 1 sent no request for it (the date was "
              f"never asked), and at {SUPERSEDED}"),
    sf.UPPER_BOUND: f"reads {sf.DATE} (refused on some pages)",
    sf.OFFICIAL: ("refused without the run's official sites (official_site_v27.load_run_official_sites) and for "
                  "an institution whose site is unresolved (failed or unfinished official-site step, a url "
                  "with no host, an unreadable file)"),
    sf.SOURCE_TYPE: f"refused when it reads a refused {sf.OFFICIAL}",
    sf.CREDIBILITY: (f"refused when {sf.DATE} is refused, and when {sf.SOURCE_TYPE} is refused and the "
                     "publication date is not unknown/not_documented"),
    "core.content_vendor": ("refused on a GenAI-bearing page whose activities state no contracting party: it then "
                            "reads developer (PI A8.1 a needs codebook r16)"),
    "core.unit_credit": ("refused when the final observed_actor_relationship object has no relationship part "
                         "(a bare token is not a storable shape: malformed)"),
    **{item: ("refused when the signed applicability table has no ask/not_asked cell for the activity's gate value "
              f"(e.g. _NA_), at {SUPERSEDED}, and when a quote-step record has no actual response model or "
              "request id")
       for item in pass1_activity_fields()},
    **{item: (f"refused when {gate} opens the gate (PI ruling 86 b: {' / '.join(reported_open(item))}) and the "
              f"page's pass-2 page request has no field task for the activity ({PASS2_NO_FIELD_TASK}), at "
              f"{SUPERSEDED}, and when a quote-step record has no actual response model or request id")
       for item, gate in REPORTED_GATES.items()},
}
#: Produced items whose only refusal is a missing upstream input that is wiring, never page data: an absent
#: ``PageSourceFields`` value, a followed page with no hop, or no pass-1 span for a coded activity.
WIRING_ONLY_ITEMS = frozenset({sf.URL, sf.ACCESS_DATE, sf.LANGUAGE, sf.SYNDICATION, sf.TEXT_SOURCE, sf.DISCOVERY,
                               "core.content_tool_or_model"})
#: Produced items that never refuse.
NEVER_REFUSED_ITEMS = frozenset({sf.REVIEW_STATE, *STATED_FIELDS, *SAFEGUARDS})


def unproduced_items() -> tuple[str, ...]:
    """Every row item no producer supplies yet (refused here), sorted."""
    return tuple(sorted({*REFUSED_SOURCE_ITEMS, *REFUSED_ACTIVITY_ITEMS}))


def entry_refused_items() -> tuple[str, ...]:
    """The items a run is refused on before any spend (PI rulings 36 a / 40 a), sorted: the unproduced items.

    PI ruling 97 b (2026-11-14): a refusal caused by a page's own data (:data:`CONDITIONAL_ITEMS`) holds
    that institution (:attr:`AssembledRows.stops` leaves it out), so the entry gate covers only what no
    page's data can supply: the unproduced items here, and the wiring gaps checked where they are wired."""
    return unproduced_items()


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


def _from(fv: sf.FieldValue) -> RowValue:
    return RowValue(fv.item_id, fv.value, fv.basis)


def _field(fv: sf.FieldValue | None, item: str) -> RowValue:
    if fv is None or fv.item_id != item:
        raise sf.MissingUpstreamError(PAGE_FIELDS, [item])
    return RowValue(item, fv.value, fv.basis)


def source_title(page: Any) -> RowValue:
    """``RenderedPage.title`` when not empty; the heading fallback stays unproduced (PI ruling 39 a)."""
    if page.title is None or not page.title.strip():
        raise sf.MissingUpstreamError("source_title first-heading fallback (unproduced, PI ruling 39 a)",
                                      [sf.TITLE])
    fv = sf.source_title(page.title, None)
    return RowValue(sf.TITLE, fv.value, fv.basis)


def content_contact(page_values: Mapping[str, Any]) -> RowValue:
    """``yes`` if either sub-item is ``yes``; ``no`` if both are ``no``; otherwise ``unknown``.

    A sub-item that is a signed missing token with neither ``yes`` gives ``unknown``
    (PI ruling 64 b, 2026-11-13). An absent sub-item value is refused.
    """
    pair = [page_values.get(i) for i in CONTACT_PARTS]
    if YES in pair:
        return _row(sc.CONTACT_ITEM, YES, "items/core.content_contact/rules/0: a sub-item is yes")
    if pair == [NO, NO]:
        return _row(sc.CONTACT_ITEM, NO, "items/core.content_contact/rules/0: both sub-items are no")
    if all(v == NO or (v is not None and str(v) in _missing_tokens(i)) for i, v in zip(CONTACT_PARTS, pair,
                                                                                         strict=True)):
        return _row(sc.CONTACT_ITEM, "unknown", "PI ruling 64 b: a sub-item is a missing token, neither is yes")
    raise sf.MissingUpstreamError(f"T-021 final {' / '.join(CONTACT_PARTS)}", [sc.CONTACT_ITEM])


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


def content_extracted(item: str, verdict: Any, activities: Sequence[str], spans: Mapping[str, Any]) -> RowValue:
    """``content_tool_or_model`` / ``content_vendor`` (rules/0, PI ruling 65 a).

    ``no`` off GenAI-bearing pages and on a page with no activity; ``yes`` when
    any activity's T-022 span has an extracted value in a matching field (any
    extracted value counts, PI ruling 65 a, even when the activity-row item is
    gated out to ``not_asked``: PI ruling 74 a). ``content_vendor`` with no extracted
    contracting party still reads the developer, which has no producer (PI A8.1 a
    needs codebook r16): refused. ``content_tool_or_model`` with none: ``no``.
    """
    if verdict not in genai_verdicts():
        return _row(item, NO, f"items/core.content_contact/rules/0: page verdict {verdict!r} is not GenAI-bearing")
    if not activities:
        return _row(item, NO, "items/core.content_contact/rules/0: no activity on the page")
    fields = EXTRACTED_FIELDS[item]
    missing = [aid for aid in activities if aid not in spans]
    if missing:
        raise sf.MissingUpstreamError(MISSING_EXTRACTION, [item])
    hits = sorted({f.item_id for aid in activities for f in spans[aid].fields if f.item_id in fields})
    if hits:
        return _row(item, YES, f"items/core.content_contact/rules/0, PI ruling 65 a: extracted {hits}")
    if item == "core.content_vendor":
        raise sf.MissingUpstreamError("core.developer (PI A8.1 a needs codebook r16)", [item])
    return _row(item, NO, "items/core.content_contact/rules/0: no activity has an extracted tool or model name")


def content_safeguard(item: str, activities: Sequence[Mapping[str, Any]]) -> RowValue:
    """``yes`` if any activity on the page is ``yes`` on the safeguard question, otherwise ``no``."""
    question = SAFEGUARDS[item]
    value = YES if any(values.get(question) == YES for values in activities) else NO
    return _row(item, value, f"items/{item}/rules/2: from {question}")


def unit_credit(activity_values: Mapping[str, Any]) -> RowValue:
    """PI A8.7 a: ``yes`` if and only if ``observed_actor_relationship`` is ``unit_of_institution``.

    The same input rule as the Stage 6 producer
    (:func:`g3o.validate.merged_activity_v27.observation_unit_credit`): an absent
    value or an absent ``relationship`` part is missing (refused); a value that is
    not the two-part object, or a part that is not a signed code or missing
    token, is malformed (``ValueError``, this module's wiring error).
    """
    if RELATIONSHIP not in activity_values:
        raise sf.MissingUpstreamError(f"T-023 final {RELATIONSHIP}", ["core.unit_credit"])
    parts = activity_values[RELATIONSHIP]
    if not isinstance(parts, Mapping):
        raise ValueError(f"{RELATIONSHIP} = {parts!r} is not the stored two-part object")
    if RELATIONSHIP_PART not in parts:
        raise sf.MissingUpstreamError(f"T-023 final {RELATIONSHIP} ({RELATIONSHIP_PART} part)",
                                      ["core.unit_credit"])
    part = parts[RELATIONSHIP_PART]
    if not isinstance(part, str) or part not in {*FIELDS[RELATIONSHIP]["parts"][RELATIONSHIP_PART],
                                                 *_missing_tokens(RELATIONSHIP)}:
        raise ValueError(f"{RELATIONSHIP} {RELATIONSHIP_PART} part {part!r} is not a signed code or missing token")
    value = YES if part == UNIT_OF_INSTITUTION else NO
    return _row("core.unit_credit", value, f"PI A8.7 a: {RELATIONSHIP}/{RELATIONSHIP_PART} = "
                                           f"{parts[RELATIONSHIP_PART]!r}")


def vendor_claim_only(source_type: str, rule_name: str | None = None) -> RowValue:
    """PI A8.9 a for one source: ``yes`` when its type is ``vendor``; a missing type gives ``unknown``.

    Ruling 88 a: a page typed automatically (``not_asked`` set by rule
    ``source_type_auto:<basis>``, ``rule_name``) has a type and is not ``vendor``:
    ``no``. The same rule as the Stage 6 producer
    (:func:`g3o.common.source_fields.vendor_claim_type` /
    :func:`~g3o.common.source_fields.vendor_claim_only_value`).
    """
    typed = sf.vendor_claim_type(source_type, rule_name)
    value = sf.vendor_claim_only_value([typed])
    why = "missing" if typed is None else f"typed {typed!r}"
    return _row("core.vendor_claim_only", value, f"PI A8.9 a / ruling 88 a: source_type {source_type!r} "
                                                 f"(rule {rule_name!r}) is {why}")


# ---------------------------------------------------------------------------
# Quote-step codes: T-022 values, their T-024 support, their T-027 coder records
# ---------------------------------------------------------------------------


NOT_DOCUMENTED = "not_documented"
Code = tuple[sc.SupportResult, CoderRecord]


@dataclass(frozen=True)
class Provenance:
    """What this page's quote-step and rule coder records carry.

    ``extractor_model`` / ``question_set_version`` / ``setup_pointer`` come from the
    instrument (``CoderRecord.storage_projection`` checks them against it);
    ``response_model`` / ``request_id`` from the actual pass-1 response (D-007: "Setup
    configuration is not proof of a response model or request ID"), so a record
    without them is refused. ``rule_coder_version`` is the coder version of the
    gated-out (mechanical) records, the activity coder's, as ``produce_page`` uses.
    ``coder_version`` is the quote-step records' (the pass-1 parser; :meth:`for_pass2` gives the
    pass-2 one, with that response's model and request id).
    """

    setup_pointer: str
    question_set_version: str
    extractor_model: str
    rule_coder_version: str
    response_model: str | None = None
    request_id: str | None = None
    coder_version: str = QUOTE_STEP_CODER_VERSION
    response: str = "T-022 pass-1"

    @classmethod
    def of(cls, instrument: Mapping[str, Any], extraction: Any, *, rule_coder_version: str) -> Provenance:
        payload = instrument["payload"]
        return cls(instrument["instrument_id"], payload["question_set_version"], payload["extractor_model_id"],
                   rule_coder_version, getattr(extraction, "response_model", None),
                   getattr(extraction, "request_id", None))

    def for_pass2(self, support: Any) -> Provenance:
        """The provenance of a value read from the page's T-032 pass-2 page request (PI ruling 73.1 b)."""
        return replace(self, response_model=getattr(support, "response_model", None),
                       request_id=getattr(support, "request_id", None), coder_version=PASS2_CODER_VERSION,
                       response="T-032 pass-2")

    def for_activity_only(self, extraction: Any) -> Provenance:
        """The provenance of a value read from the page's activity-only pass-1 request (PI ruling 87 c):
        that response's model and request id (D-007), the same quote-step coder."""
        return replace(self, response_model=getattr(extraction, "response_model", None),
                       request_id=getattr(extraction, "request_id", None),
                       response="T-022 pass-1 activity-only (PI ruling 87 c)")

    def quote_record(self, item: str, value: Any, chunk_id: str | None) -> CoderRecord:
        if not self.response_model or not self.request_id:
            raise sf.MissingUpstreamError(f"actual response model and request id of the {self.response} response "
                                          "(D-007)", [item])
        return CoderRecord(item_id=item, item_part=None, question_id=None, support_id=None, observation_id=None,
                           chunk_id=chunk_id, coder_type="quote_step", coder_version=self.coder_version,
                           configured_model=self.extractor_model, actual_response_model=self.response_model,
                           request_id=self.request_id, question_set_version=self.question_set_version,
                           setup_pointer=self.setup_pointer, answer_type="extracted", chosen_value=value,
                           confidence=None, probability_distribution=None)

    def rule_record(self, item: str, value: Any, rule: str) -> CoderRecord:
        return CoderRecord(item_id=item, item_part=None, question_id=None, support_id=None, observation_id=None,
                           chunk_id=None, coder_type="mechanical", coder_version=self.rule_coder_version,
                           configured_model=None, actual_response_model=None, request_id=None,
                           question_set_version=self.question_set_version, setup_pointer=self.setup_pointer,
                           answer_type="rule", chosen_value=value, confidence=None, probability_distribution=None,
                           rule_reference=rule)


@dataclass(frozen=True)
class QuoteValue:
    """A row value with the codes (support result, coder record) that carry it."""

    row: RowValue
    codes: tuple[Code, ...]


def _known_part(sources: sc.PageSources, chunk_id: str | None, item: str) -> str:
    """A part id the stored page still has; a superseded or unknown part (e.g. after an
    extra-round halving re-split the page) is refused, never looked up."""
    if chunk_id is None or chunk_id not in sources.parts:
        raise sf.MissingUpstreamError(f"part {chunk_id!r} among the coded page's parts (superseded or unknown)",
                                      [item])
    return chunk_id


def rule_code(item: str, value: Any, rule: str, activity_id: str | None, sources: sc.PageSources,
              prov: Provenance) -> Code:
    """A value fixed by a rule: ``set_by_rule`` support naming it and a mechanical record (R-045)."""
    sr = sc.check_code(sc.CodeEvidence(item, str(value), None, rule_name=rule, activity_id=activity_id), sources)
    return sr, prov.rule_record(item, value, rule)


def _gated(item: str, gate: Mapping[str, Any], activity_id: str, sources: sc.PageSources, prov: Provenance,
           why: str) -> QuoteValue:
    """Gated out: the gate's value (``not_asked`` unless it names one), rule ``gated_out:<gate item>``,
    the convention of the T-023 gated-out records (``jev_activity_code._gated``)."""
    value = gate["gated_out_value"] if isinstance(gate.get("gated_out_value"), str) else "not_asked"
    rule = GATE_RULE + str(gate["item"])
    return QuoteValue(RowValue(item, value, f"{rule}: {why}"), (rule_code(item, value, rule, activity_id,
                                                                           sources, prov),))


def activity_quote_value(item: str, activity_id: str, span: Any, activity_values: Mapping[str, Any],
                         sources: sc.PageSources, prov: Provenance) -> QuoteValue:
    """One T-022 pass-1 activity field: gate, then the extracted value checked by T-024 (R-042).

    Applicability gate (the signed table on ``activity_type``): a ``not_asked`` cell
    gates the item out; a value with no cell is unruled. Asked: the span's field
    value with its quote, checked by :func:`~g3o.common.support_check.check_code`
    (a failed check takes the item's ``downgrade_target``); a list item stores
    ``[value]``. No field value (pass 1 returned none): ``not_documented``.
    """
    gate = sf.default_codebook().items[item].get("gate")
    if isinstance(gate, Mapping):
        if not isinstance(gate.get("cells"), Mapping):
            raise ValueError(f"{item}: gate is not an applicability table")
        key = activity_values.get(str(gate["item"]))
        cell = None if key is None else gate["cells"].get(str(key))
        if cell == "not_asked":
            return _gated(item, gate, activity_id, sources, prov, f"applicability cell for {gate['item']} = {key!r}")
        if cell != "ask":
            raise sf.UnruledError(item, f"applicability table has no ask/not_asked cell for {gate['item']} = {key!r}")
    elif gate != "none":
        raise ValueError(f"{item}: unexpected gate {gate!r} on a pass-1 field")
    found = [f for f in span.fields if f.item_id == item]
    if len(found) > 1:
        raise ValueError(f"{item}: pass 1 returned {len(found)} values for activity {activity_id}")
    if found:
        f = found[0]
        chunk = _known_part(sources, f.chunk_id, item)
        sr = sc.check_code(sc.CodeEvidence(item, f.value, chunk, quote=f.supporting_text, quote_chunk_id=chunk,
                                           activity_id=activity_id), sources)
        listed = FIELDS[item]["answer_type"] == "list" and sr.value == f.value
        value = [f.value] if listed else sr.value
        return QuoteValue(RowValue(item, value, f"T-022 pass-1 field, T-024 {sr.support_status}"),
                          ((sr, prov.quote_record(item, f.value, chunk)),))
    chunk = _known_part(sources, span.chunk_id, item)
    sr = sc.check_code(sc.CodeEvidence(item, NOT_DOCUMENTED, chunk, activity_id=activity_id), sources)
    return QuoteValue(RowValue(item, NOT_DOCUMENTED, "T-022 pass 1 returned no value for the field"),
                      ((sr, prov.quote_record(item, NOT_DOCUMENTED, chunk)),))


def reported_value(item: str, activity_id: str, activity_values: Mapping[str, Any], sources: sc.PageSources,
                   prov: Provenance, pass2: Any = None) -> QuoteValue:
    """``reported_outcomes`` / ``reported_incidents`` (CX-61 gate on ``outcome_kind`` / ``incident_kind``).

    PI ruling 86 b: the gate opens at the item's signed gate values (:func:`reported_open`;
    ``discontinuation_uncertain`` opens the incidents gate). Open: the list from the page's
    T-032 pass-2 page request (:func:`reported_field_value`, PI ruling 73.1 b). Every other
    value of the gate item (``none_reported``, or a missing token such as ``unknown``)
    closes it (PI ruling 73.2 a): ``not_asked`` by rule ``gated_out:<gate item>``. A value
    that is neither a signed code nor a missing token of the gate item is an error.
    """
    gate = sf.default_codebook().items[item]["gate"]
    if gate["item"] != REPORTED_GATES[item]:
        raise ValueError(f"{item}: signed gate item {gate['item']!r} is not {REPORTED_GATES[item]!r}")
    key = activity_values.get(gate["item"])
    if key is None:
        raise sf.MissingUpstreamError(f"T-023 final {gate['item']}", [item])
    if key in reported_open(item):
        return reported_field_value(item, activity_id, pass2, sources, prov)
    known = {*(sf.default_codebook().codes(gate["item"]) or ()), *_missing_tokens(gate["item"])}
    if key not in known:
        raise ValueError(f"{gate['item']} = {key!r} is not a signed code or missing token")
    return _gated(item, gate, activity_id, sources, prov, f"{gate['item']} = {key!r} (PI rulings 73.2 a, 86 b)")


#: Pass-2 field status of a value returned with its supporting text (``pass2_support.ActivityField.status``).
PASS2_STATED = "stated"


def reported_field_value(item: str, activity_id: str, pass2: Any, sources: sc.PageSources,
                         prov: Provenance) -> QuoteValue:
    """An open gate's list: the activity's T-032 pass-2 field task in the page request (PI ruling 73.1 b).

    ``pass2`` is the page's pass-2 page request (:class:`~g3o.extract.pass2_support.Pass2Support`,
    from ``PerPageProviders.page_pass2``; None: no request, refused). A ``stated`` field is the
    value with its supporting text, checked by T-024 (R-042; no X35: the item has no entailment
    label; a failed check takes the item's ``downgrade_target``); a list item stores ``[value]``.
    Any other status (the extractor stated nothing, or its answer was rejected: no supporting
    text, a part the task did not name, no entry) gives ``not_documented``, as pass 1 treats a
    field it returns no usable value for. The record carries the pass-2 response's provenance.
    """
    if pass2 is None:
        raise sf.MissingUpstreamError(MISSING_PASS2, [item])
    found = [f for f in pass2.fields if f.activity_id == activity_id and f.item_id == item]
    if not found:
        raise sf.MissingUpstreamError(PASS2_NO_FIELD_TASK, [item])
    if len(found) > 1:
        raise ValueError(f"{item}: the pass-2 page request has {len(found)} field tasks for activity {activity_id}")
    f = found[0]
    p2 = prov.for_pass2(pass2)
    if f.status == PASS2_STATED:
        chunk = _known_part(sources, f.chunk_id, item)
        sr = sc.check_code(sc.CodeEvidence(item, f.value, chunk, quote=f.supporting_text, quote_chunk_id=chunk,
                                           activity_id=activity_id), sources)
        listed = FIELDS[item]["answer_type"] == "list" and sr.value == f.value
        value = [f.value] if listed else sr.value
        return QuoteValue(RowValue(item, value, f"PI ruling 73.1 b: T-032 pass-2 field, T-024 {sr.support_status}"),
                          ((sr, p2.quote_record(item, f.value, chunk)),))
    sr = sc.check_code(sc.CodeEvidence(item, NOT_DOCUMENTED, None, activity_id=activity_id), sources)
    return QuoteValue(RowValue(item, NOT_DOCUMENTED, f"PI ruling 73.1 b: T-032 pass 2 gave no usable value "
                                                     f"({f.status})"),
                      ((sr, p2.quote_record(item, NOT_DOCUMENTED, None)),))


#: PI ruling 72 a (2026-11-13): the rule that sets ``source_snippet`` to ``not_asked`` when the page verdict's
#: support carries no quote.
NO_VERDICT_QUOTE_RULE = "no_verdict_quote"


def snippet_value(verdict_support: sc.SupportResult | None, sources: sc.PageSources,
                  prov: Provenance) -> QuoteValue:
    """X25: the page verdict's supporting quote (:func:`g3o.common.source_fields.source_snippet`).

    The quote was copied by the page's T-022 pass-1 request, whose provenance the
    record carries. A verdict support with no quote (a rule-set verdict's support
    included): ``not_asked``, ``set_by_rule`` support naming
    :data:`NO_VERDICT_QUOTE_RULE` and a mechanical record (PI ruling 72 a).
    """
    if verdict_support is None:
        raise sf.MissingUpstreamError("T-024 support of the final page verdict at its deciding part", [sf.SNIPPET])
    if verdict_support.item_id != sc.PAGE_VERDICT:
        raise ValueError("source_snippet needs the page verdict's support record")
    if verdict_support.supporting_text is None:
        value = "not_asked"
        return QuoteValue(RowValue(sf.SNIPPET, value, f"PI ruling 72 a: {NO_VERDICT_QUOTE_RULE}"),
                          (rule_code(sf.SNIPPET, value, NO_VERDICT_QUOTE_RULE, None, sources, prov),))
    chunk = _known_part(sources, verdict_support.quote_chunk_id or verdict_support.chunk_id, sf.SNIPPET)
    fv = sf.source_snippet(verdict_support, sources)
    return QuoteValue(RowValue(sf.SNIPPET, fv.value, fv.basis),
                      ((fv.support, prov.quote_record(sf.SNIPPET, verdict_support.supporting_text, chunk)),))


#: PI ruling 63 a (2026-11-13): the support rule of a metadata/URL publication date.
DETERMINISTIC_DATE_RULE = "deterministic_date:"


def deterministic_date_rule(date: sf.FieldValue) -> str:
    """``deterministic_date:<origin>`` (PI ruling 92 b): ``metadata`` for a page-metadata date,
    ``web_address`` for a URL date. The deciding A1.1 a tag stays in the field's ``detail``."""
    if date.date_origin == "metadata":
        return DETERMINISTIC_DATE_RULE + "metadata"
    if date.date_origin == "web_address":
        return DETERMINISTIC_DATE_RULE + "web_address"
    raise ValueError(f"date origin {date.date_origin!r} is not deterministic")


@dataclass(frozen=True)
class DateValue:
    """The publication date with its codes, and the field ``date_upper_bound`` reads."""

    quote: QuoteValue
    field: sf.FieldValue


def publication_date_value(page: Any, page_fields: Any, extraction: Any, sources: sc.PageSources,
                           prov: Provenance) -> DateValue:
    """X26 (``items/core.source_publication_date/rules/0``) with its support.

    A1 metadata or URL date (``PageSourceFields.publication_date``): that value,
    ``set_by_rule`` support naming ``deterministic_date:<origin>`` (PI ruling 63 a).
    Otherwise the T-022 quote step's date
    (``Pass1Extraction.publication_date``) checked under R-042
    (:func:`g3o.common.source_fields.publication_date`: supported, or ``unknown``
    when the check fails), with a quote-step record; no date returned:
    ``not_documented``. Pass 1 asks the date only when it sends a request for the
    page (``request_v27.select_requests``); with no request the date was never
    asked, and that is refused.
    """
    date = getattr(page_fields, "publication_date", None)
    if date is not None:
        rule = deterministic_date_rule(date)
        return DateValue(QuoteValue(RowValue(sf.DATE, date.value, f"{date.basis}; PI ruling 63 a"),
                                    (rule_code(sf.DATE, date.value, rule, None, sources, prov),)), date)
    if page.has_metadata_date:
        raise ValueError("PageInput.has_metadata_date is set but page_fields has no publication date")
    if extraction is None:
        raise sf.MissingUpstreamError("T-022 date task (pass 1 sent no request for this page)", [sf.DATE])
    quote = extraction.publication_date
    if quote is None:
        fv = sf.publication_date([], None, sources)
        sr = sc.check_code(sc.CodeEvidence(sf.DATE, fv.value, None), sources)
        return DateValue(QuoteValue(RowValue(sf.DATE, fv.value, fv.basis),
                                    ((sr, prov.quote_record(sf.DATE, fv.value, None)),)), fv)
    chunk = _known_part(sources, quote.chunk_id, sf.DATE)
    fv = sf.publication_date([], quote, sources)
    return DateValue(QuoteValue(RowValue(sf.DATE, fv.value, fv.basis),
                                ((fv.support, prov.quote_record(sf.DATE, quote.value, chunk)),)), fv)


# ---------------------------------------------------------------------------
# PI ruling 70 b: official domain, source_type rules/0 routing, credibility
# ---------------------------------------------------------------------------


OFFICIAL_SITES = ("official sites this run found (PI ruling 70 b; "
                  "official_site_v27.load_run_official_sites)")
#: The A2 seam ``source_type`` reads (absent: wiring).
ARCHIVE_TEST = "A2 archive-address test (PageSourceFields.archive_address)"
#: The page-level inputs every source row reads (absent: wiring).
PAGE_FIELDS = "perpage_inputs_v27.PageSourceFields"
#: PI ruling 97 b (2026-11-14): producers whose absence is a wiring gap, never a page's data. A refusal naming
#: one of them stops the per-page stage even for a :data:`CONDITIONAL_ITEMS` item (PI 32 b); any other
#: refusal of a conditional item is the page's own data and holds that institution only. PI ruling 111 a
#: (2026-11-14): a readable residual page handed no residual ``source_type`` answers
#: (:data:`RESIDUAL_PRODUCER`) is a wiring gap too: the stage stops.
WIRING_PRODUCERS = frozenset({MISSING_EXTRACTION, OFFICIAL_SITES, ARCHIVE_TEST, PAGE_FIELDS, RESIDUAL_PRODUCER})


def official_value(page: Any, official_sites: Any) -> sf.FieldValue:
    """X37 of the page from the run's official sites (:class:`~g3o.run.presweep.official_site_v27.RunOfficialSites`)."""
    if official_sites is None:
        raise sf.MissingUpstreamError(OFFICIAL_SITES, [sf.OFFICIAL])
    return official_sites.official(page.url, page.institution_id)


def residual_deciding_part_failed(typing: Any) -> str | None:
    """PI ruling 110 b (2026-11-14): the deciding part of a residual ``source_type`` typing when that part
    failed with no answer, else None.

    "No answer" is no live classifier record of the item at the part (the temporary part answer aside, as
    the per-page provider adapter's checked records): the request raised, came back with no request id, or
    returned no answer to the question (``jev_page_code`` records a failure, no record). ``first_section``
    skips failed parts, so such a part decides only when no part gave a real answer. The per-page stage never
    saves or codes such a typing: it holds the institution before T-022 and asks the question again on the
    next run (answered parts replayed from the journal); it is never coded ``unknown`` from a failure."""
    if typing is None or getattr(typing, "typed_by", None) != "classifier" or typing.outcome is None:
        return None
    deciding = typing.outcome.part_id
    if deciding is None:
        return None
    if typing.result is None:
        raise TypeError("a residual source_type typing without its stored result (wiring error)")
    answered = any(r.coder_type == "classifier" and r.item_id == sf.SOURCE_TYPE and r.chunk_id == deciding
                   and r.chosen_value != NOT_COVERED for r in typing.result.records)
    return None if answered else str(deciding)


def residual_source_type_value(typing: Any, codes: Any) -> tuple[QuoteValue, sf.SourceTyping]:
    """A readable residual page's ``source_type`` (PI ruling 95 a, building 83 b): the residual question's
    answers (``typing``, asked before T-022 on the page's T-021 parts) with their T-024 checks (``codes``:
    (support, record) per answer; the quote task rode in the page's first pass-1 request, or the answer was
    checked with no quote, ``downgraded_no_quote``, when the page had no such request). The value is the
    check of the deciding part's answer (:func:`g3o.common.source_fields.checked_source_type`); a combined
    missing token with no deciding part is the combined value. Every checked answer is a code of the row."""
    if typing is None or codes is None:
        raise sf.MissingUpstreamError(RESIDUAL_PRODUCER, [sf.SOURCE_TYPE])
    if typing.typed_by != "classifier" or typing.outcome is None:
        raise TypeError("the residual source_type input is not a classifier typing (wiring error)")
    pairs = tuple(codes)
    if any(rec.item_id != sf.SOURCE_TYPE or sr.item_id != sf.SOURCE_TYPE for sr, rec in pairs):
        raise TypeError("residual source_type codes carry another item (wiring error)")
    deciding = typing.outcome.part_id
    found = [sr for sr, rec in pairs if rec.chunk_id == deciding] if deciding is not None else []
    if deciding is not None and len(found) != 1:
        why = ""
        if not found and getattr(typing.outcome, "failed", False):  # PI ruling 110 b: held by the stage instead
            why = ("; the deciding part failed with no answer: the per-page stage holds such a page before T-022 "
                   "and asks it again (PI ruling 110 b)")
        raise TypeError(f"residual source_type: {len(found)} checked answers at the deciding part {deciding!r}"
                        f"{why} (wiring error)")
    checked = sf.checked_source_type(typing, found[0]) if found else typing
    fv = checked.field
    return QuoteValue(RowValue(sf.SOURCE_TYPE, fv.value, fv.basis), pairs), checked


def source_type_value(page: Any, official: sf.FieldValue, archive_address: Any, sources: sc.PageSources,
                      prov: Provenance, *, source_typing: Any = None,
                      source_type_codes: Any = None) -> tuple[QuoteValue, sf.SourceTyping]:
    """``items/core.source_type/rules/0``: typed automatically (official domain, then archive address), or
    a residual page; an unreadable residual page is not sent (R-015). Each is ``not_asked`` set by its rule
    (R-045) with a mechanical record. A readable residual page takes the residual question's checked answer
    (:func:`residual_source_type_value`, PI ruling 95 a); without it the item is refused
    (:data:`RESIDUAL_PRODUCER`)."""
    if not isinstance(archive_address, bool):
        raise sf.MissingUpstreamError(ARCHIVE_TEST, [sf.SOURCE_TYPE])
    basis = sf.route_source_type(official, archive_address)
    typing = sf.auto_source_type(basis) if basis is not None else sf.readability_source_type(page)
    if typing is None:
        return residual_source_type_value(source_typing, source_type_codes)
    if source_typing is not None:
        raise TypeError(f"page {page.page_id}: a residual source_type answer for a page typed by rule "
                        f"({typing.field.rule_name}; wiring error)")
    fv = typing.field
    code = rule_code(sf.SOURCE_TYPE, fv.value, str(fv.rule_name), None, sources, prov)
    return QuoteValue(RowValue(sf.SOURCE_TYPE, fv.value, f"{fv.basis} ({fv.rule_name})"), (code,)), typing


def credibility_value(typing: sf.SourceTyping | None, date: sf.FieldValue) -> RowValue:
    """X22: ``low`` for an undated source whatever its type (rules/0); otherwise the map cell of its type."""
    dated = sf.credibility_from_date(date)
    if dated is not None:
        return _from(dated)
    if typing is None:
        raise sf.MissingUpstreamError(f"{sf.SOURCE_TYPE} (refused)", [sf.CREDIBILITY])
    return _from(sf.source_credibility(typing, date))


def typed_source_values(page: Any, page_fields: Any, rows: AssembledRows, date: sf.FieldValue | None, *,
                        official_sites: Any, sources: sc.PageSources | None, provenance: Provenance | None,
                        source_typing: Any = None, source_type_codes: Any = None) -> None:
    """``source_on_official_domain``, ``source_type`` and ``source_credibility`` into ``rows`` (ruling 70 b;
    the residual ``source_type`` answer of PI ruling 95 a)."""
    out = rows.source
    try:
        official = official_value(page, official_sites)
    except _REFUSALS as exc:
        rows.refuse(sf.OFFICIAL, exc)
        rows.refuse_reading(sf.SOURCE_TYPE, sf.OFFICIAL, f"rules/0 reads {sf.OFFICIAL} (refused)")
        official = None
    else:
        out[sf.OFFICIAL] = _from(official)
    typing = None
    if official is not None:
        try:
            qv, typing = source_type_value(page, official, getattr(page_fields, "archive_address", None),
                                           _need(sources, sf.SOURCE_TYPE), _need(provenance, sf.SOURCE_TYPE),
                                           source_typing=source_typing, source_type_codes=source_type_codes)
        except _REFUSALS as exc:
            rows.refuse(sf.SOURCE_TYPE, exc)
        else:
            out[sf.SOURCE_TYPE] = qv.row
            rows.source_codes.extend(qv.codes)
    if date is None:
        rows.refuse_reading(sf.CREDIBILITY, sf.DATE, f"reads {sf.DATE} (refused)")
        return
    _try(rows, out, sf.CREDIBILITY, lambda: credibility_value(typing, date))
    if sf.CREDIBILITY in rows.refused and sf.SOURCE_TYPE in rows.stops:  # it read a type refused on wiring
        rows.stops.add(sf.CREDIBILITY)


# ---------------------------------------------------------------------------
# The assembler
# ---------------------------------------------------------------------------


_REFUSALS = (sf.UnruledError, sf.MissingUpstreamError)


@dataclass
class AssembledRows:
    """What :func:`assemble` built for one coded page, and what it refused (item -> reason).

    ``source`` holds the page-level source-row values (the same on every source
    row of the page) and ``source_codes`` their codes; ``activities`` the
    activity-row values per T-022 activity id and ``activity_codes`` theirs.
    ``refused`` names every row item not produced: the standing refusals
    (:data:`REFUSED_SOURCE_ITEMS`, :data:`REFUSED_ACTIVITY_ITEMS`) and any
    producer that refused on this page's data.

    ``stops`` (PI ruling 97 b) names the refused items whose refusal stops the stage: the standing
    refusals, every item outside :data:`CONDITIONAL_ITEMS`, a conditional item refused for a missing
    wiring input (:data:`WIRING_PRODUCERS`), and an item that reads one of these. Every other refused item
    was refused on the page's own data (:meth:`data_refusals`): the per-page stage holds that institution.
    """

    source: dict[str, RowValue] = field(default_factory=dict)
    activities: dict[str, dict[str, RowValue]] = field(default_factory=dict)
    refused: dict[str, str] = field(default_factory=dict)
    source_codes: list[Code] = field(default_factory=list)
    activity_codes: dict[str, list[Code]] = field(default_factory=dict)
    stops: set[str] = field(default_factory=set)

    def refuse(self, item: str, exc: Exception) -> None:
        """Record ``item`` refused by ``exc``; a wiring cause, or an item that is never refused on data,
        stops the stage (ruling 97 b)."""
        self.refused[item] = str(exc)
        if item not in CONDITIONAL_ITEMS or getattr(exc, "producer", None) in WIRING_PRODUCERS:
            self.stops.add(item)

    def refuse_reading(self, item: str, upstream: str, reason: str) -> None:
        """Record ``item`` refused because it reads the refused ``upstream``: it stops the stage when that
        refusal does (or when ``item`` is never refused on data)."""
        self.refused[item] = reason
        if item not in CONDITIONAL_ITEMS or upstream in self.stops:
            self.stops.add(item)

    def data_refusals(self) -> dict[str, str]:
        """The refused items refused on the page's own data alone (ruling 97 b), with their reasons."""
        return {item: reason for item, reason in self.refused.items() if item not in self.stops}

    def to_upstream(self, keys: Sequence[str]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]],
                                                         dict[str, list[Code]]]:
        """``(activity_values, source_values, codes)`` in the ``PageUpstream`` shape.

        ``keys`` are the page's source-row units (one per activity, or the
        no-activity key): each gets the page-level source values and codes, plus
        its activity's codes. Refused while anything is refused.
        """
        if self.refused:
            raise sf.MissingUpstreamError(ASSEMBLER, sorted(self.refused))
        activity_values = {aid: {i: v.value for i, v in row.items()} for aid, row in self.activities.items()}
        source = {i: v.value for i, v in self.source.items()}
        source_values = {key: dict(source) for key in keys}
        codes = {key: [*self.source_codes, *self.activity_codes.get(key, ())] for key in keys}
        return activity_values, source_values, codes


def _try(rows: AssembledRows, out: dict[str, RowValue], item: str, make: Callable[[], RowValue]) -> None:
    try:
        out[item] = make()
    except _REFUSALS as exc:
        rows.refuse(item, exc)


def _try_quote(rows: AssembledRows, out: dict[str, RowValue], codes: list[Code], item: str,
               make: Callable[[], QuoteValue]) -> None:
    try:
        qv = make()
    except _REFUSALS as exc:
        rows.refuse(item, exc)
        return
    out[item] = qv.row
    codes.extend(qv.codes)


def page_source_values(page: Any, page_fields: Any, page_values: Mapping[str, Any],
                       activities: Mapping[str, Mapping[str, Any]], rows: AssembledRows, *,
                       followed: bool | None = None, sources: sc.PageSources | None = None,
                       verdict_support: sc.SupportResult | None = None,
                       provenance: Provenance | None = None, extraction: Any = None,
                       hop: int | None = None, official_sites: Any = None,
                       activity_extraction: Any = None, source_typing: Any = None,
                       source_type_codes: Any = None) -> None:
    """The page-level source-row values (see the module docstring) into ``rows.source``.

    The activity spans the content_* extracted fields read come from ``activity_extraction`` (the
    activity-only request, PI ruling 87 c) when given, else from ``extraction``. ``source_typing`` /
    ``source_type_codes``: a readable residual page's ``source_type`` answers and their checks (PI ruling
    95 a), passed on to :func:`typed_source_values`."""
    out = rows.source
    for item, attr in ((sf.URL, "url"), (sf.ACCESS_DATE, "access_date"), (sf.LANGUAGE, "language"),
                       (sf.SYNDICATION, "syndication_group"), (sf.TEXT_SOURCE, "text_source")):
        _try(rows, out, item, lambda item=item, attr=attr: _field(getattr(page_fields, attr, None), item))
    # Ruling 61 a: from the T-025 follow provenance (a followed page with no hop is refused).
    _try(rows, out, sf.DISCOVERY, lambda: _from(sf.discovery_path(followed=followed, hop=hop)))
    _try(rows, out, sf.TITLE, lambda: source_title(page))
    _try(rows, out, sf.REVIEW_STATE, lambda: RowValue(
        sf.REVIEW_STATE, sf.page_review_state(REVIEWED).value,
        "page coded by T-021 (items/core.page_review_state/rules/1; SPEC R-015, RC-D-021 D-2 a)"))
    _try(rows, out, sc.CONTACT_ITEM, lambda: content_contact(page_values))
    if sc.CONTACT_ITEM in out:
        _try(rows, out, sc.CONTACT_EMAILS_ITEM,
             lambda: content_contact_emails(out[sc.CONTACT_ITEM].value, page))
    else:
        rows.refuse_reading(sc.CONTACT_EMAILS_ITEM, sc.CONTACT_ITEM, f"gated on {sc.CONTACT_ITEM} (refused)")
    acts = [activities[aid] for aid in activities]
    verdict = page_values.get("core.page_verdict")
    for item in STATED_FIELDS:
        _try(rows, out, item, lambda item=item: content_stated(item, verdict, acts))
    for item in SAFEGUARDS:
        _try(rows, out, item, lambda item=item: content_safeguard(item, acts))
    span_source = extraction if activity_extraction is None else activity_extraction
    spans = {s.activity_id: s for s in getattr(span_source, "activities", ())}
    for item in EXTRACTED_FIELDS:
        _try(rows, out, item, lambda item=item: content_extracted(item, verdict, list(activities), spans))
    _try_quote(rows, out, rows.source_codes, sf.SNIPPET,
               lambda: snippet_value(verdict_support, _need(sources, sf.SNIPPET),
                                     _need(provenance, sf.SNIPPET)))
    try:  # X26 and the date_upper_bound note on it (mechanical: no code)
        dated = publication_date_value(page, page_fields, extraction, _need(sources, sf.DATE),
                                       _need(provenance, sf.DATE))
    except _REFUSALS as exc:
        rows.refuse(sf.DATE, exc)
        rows.refuse_reading(sf.UPPER_BOUND, sf.DATE, f"reads {sf.DATE} (refused)")
        date = None
    else:
        out[sf.DATE] = dated.quote.row
        rows.source_codes.extend(dated.quote.codes)
        _try(rows, out, sf.UPPER_BOUND, lambda: _from(sf.date_upper_bound(dated.field)))
        date = dated.field
    typed_source_values(page, page_fields, rows, date, official_sites=official_sites, sources=sources,
                        provenance=provenance, source_typing=source_typing,
                        source_type_codes=source_type_codes)


def _need(value: Any, item: str) -> Any:
    if value is None:
        raise sf.MissingUpstreamError(MISSING_EXTRACTION, [item])
    return value


def activity_row_values(activities: Mapping[str, Mapping[str, Any]], rows: AssembledRows, *,
                        extraction: Any = None, sources: sc.PageSources | None = None,
                        provenance: Provenance | None = None, pass2: Any = None,
                        activity_extraction: Any = None, span_provenance: Provenance | None = None) -> None:
    """The per-observation activity-row values into ``rows.activities`` and their codes.

    ``unit_credit``; the T-022 pass-1 fields (:func:`activity_quote_value`) from the
    activity's span in ``extraction`` (the page's pass-1 request), or in
    ``activity_extraction`` (the activity-only request, PI ruling 87 c) with
    ``span_provenance`` when it is given; the reported lists (:func:`reported_value`;
    an open gate reads ``pass2``, the page's T-032 pass-2 page request, PI ruling 73.1 b).
    """
    span_source = extraction if activity_extraction is None else activity_extraction
    span_prov = provenance if activity_extraction is None else span_provenance
    spans = {s.activity_id: s for s in getattr(span_source, "activities", ())}
    for aid, values in activities.items():
        out = rows.activities.setdefault(aid, {})
        codes = rows.activity_codes.setdefault(aid, [])
        _try(rows, out, "core.unit_credit", lambda values=values: unit_credit(values))
        for item in pass1_activity_fields():
            _try_quote(rows, out, codes, item, lambda item=item, aid=aid, values=values: activity_quote_value(
                item, aid, _need(spans.get(aid), item), values, _need(sources, item), _need(span_prov, item)))
        for item in REPORTED_GATES:
            _try_quote(rows, out, codes, item, lambda item=item, aid=aid, values=values: reported_value(
                item, aid, values, _need(sources, item), _need(provenance, item), pass2))


def assemble(page: Any, page_fields: Any, page_values: Mapping[str, Any],
             activities: Mapping[str, Mapping[str, Any]], *, followed: bool | None = None,
             extraction: Any = None, sources: sc.PageSources | None = None,
             verdict_support: sc.SupportResult | None = None,
             provenance: Provenance | None = None, hop: int | None = None,
             official_sites: Any = None, pass2: Any = None, activity_extraction: Any = None,
             source_typing: Any = None, source_type_codes: Any = None) -> AssembledRows:
    """Build every producible row value of one coded page and name every refused item.

    ``page`` is the :class:`~g3o.classify.jev_page_code.PageInput`,
    ``page_fields`` its :class:`~g3o.run.presweep.perpage_inputs_v27.PageSourceFields`,
    ``page_values`` the final page values and ``activities`` the final values of
    each coded activity (``{activity_id: values}``; empty on a page with no activity).
    ``followed`` / ``hop`` are ``PageUpstream.followed`` / ``.hop`` (T-025; followed None: no
    follow provenance; a followed page's hop is >= 1).
    ``extraction`` is the page's T-022 pass-1 request
    (:class:`~g3o.extract.parser_v27.Pass1Extraction`, from
    ``PerPageProviders.page_extraction``), ``sources`` the coded page's parts,
    ``verdict_support`` the T-024 support of the final verdict and ``provenance``
    what the coder records carry (:meth:`Provenance.of`). Without them every
    quote-step item is refused. ``official_sites`` is the run's
    :class:`~g3o.run.presweep.official_site_v27.RunOfficialSites` (PI ruling 70 b);
    without it ``source_on_official_domain`` and what reads it are refused. ``pass2`` is the page's
    T-032 pass-2 page request (:class:`~g3o.extract.pass2_support.Pass2Support`, from
    ``PerPageProviders.page_pass2``; PI ruling 73.1 b), read for an open reported_* gate.
    ``activity_extraction`` is the page's activity-only pass-1 request (PI ruling 87 c, from
    ``PerPageProviders.activity_extraction``) when the activities came from it: their spans and
    pass-1 fields are read from it, with its response's model and request id
    (:meth:`Provenance.for_activity_only`); the date and snippet still come from ``extraction``.
    ``source_typing`` / ``source_type_codes`` are a readable residual page's ``source_type`` answers
    and their T-024 checks (PI ruling 95 a; ``PerPageProviders.source_type_codes``); without them such a
    page's ``source_type`` is refused (:data:`RESIDUAL_PRODUCER`).
    """
    if page_fields is None:
        raise sf.MissingUpstreamError("perpage_inputs_v27.PageSourceFields (PageUpstream.page_fields)",
                                      [page.page_id])
    rows = AssembledRows()
    rows.refused.update(REFUSED_SOURCE_ITEMS)
    rows.stops.update(REFUSED_SOURCE_ITEMS)  # unproduced: a stage stop, never a hold (ruling 97 b)
    if activities:
        rows.refused.update(REFUSED_ACTIVITY_ITEMS)
        rows.stops.update(REFUSED_ACTIVITY_ITEMS)
    page_source_values(page, page_fields, page_values, activities, rows, followed=followed, sources=sources,
                       verdict_support=verdict_support, provenance=provenance, extraction=extraction, hop=hop,
                       official_sites=official_sites, activity_extraction=activity_extraction,
                       source_typing=source_typing, source_type_codes=source_type_codes)
    span_prov = provenance
    if activity_extraction is not None and provenance is not None:  # PI ruling 87 c
        span_prov = provenance.for_activity_only(activity_extraction)
    activity_row_values(activities, rows, extraction=extraction, sources=sources, provenance=provenance,
                        pass2=pass2, activity_extraction=activity_extraction, span_provenance=span_prov)
    return rows


__all__ = [
    "ASSEMBLER", "CONDITIONAL_ITEMS", "NEVER_REFUSED_ITEMS", "WIRING_ONLY_ITEMS", "reported_field_value",
    "reported_open", "reported_value", "PRODUCED_ACTIVITY_ITEMS", "PRODUCED_SOURCE_ITEMS", "REFUSED_ACTIVITY_ITEMS",
    "REFUSED_SOURCE_ITEMS", "STAGE6_ACTIVITY_ITEMS", "WIRING_PRODUCERS", "AssembledRows", "RowValue", "activity_row_items",
    "activity_row_values", "assemble",
    "content_contact", "content_contact_emails", "content_safeguard", "content_stated", "genai_verdicts",
    "entry_refused_items", "page_source_values", "residual_deciding_part_failed", "source_row_items", "source_title",
    "stated", "unit_credit",
    "unproduced_items",
    "vendor_claim_only",
]
