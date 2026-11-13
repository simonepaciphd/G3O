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
- ``text_source``: :class:`PageSourceFields` (``new_run`` for a new run's
  rows, PI ruling 62 a).
- ``discovery_path``: from ``PageUpstream.followed`` (PI ruling 61 a): a page
  not followed is ``searched``; a followed page needs its hop from T-025 and is
  refused until T-025 passes it (the seam is ``discovery_path(hop=...)``).
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
  support with no quote is refused (no signed rule).

- ``source_publication_date`` (X26): the A1 metadata/URL date with
  ``set_by_rule`` support naming ``deterministic_date:<A1.1 a tag>`` or
  ``deterministic_date:web_address`` (PI ruling 63 a); otherwise the T-022
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
- ``reported_outcomes`` / ``reported_incidents``: ``not_asked`` by rule when
  their gate item is ``none_reported``; refused otherwise (see
  :func:`reported_value`).

Built but not yet usable (its input is refused): :func:`vendor_claim_only`
(PI A8.9 a) reads ``source_type``.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from g3o.classify.jev_activity_code import GATE_RULE
from g3o.common import source_fields as sf
from g3o.common import support_check as sc
from g3o.common.jev_record import CoderRecord
from g3o.common.storage import METADATA_ITEMS, table_fields
from g3o.common.storage_fields import FIELDS
from g3o.extract import request_v27

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

#: The pass-1 activity quote-step fields T-022 asks (request_v27.Pass1Rules.activity_fields).
REPORTED_GATES = {"core.reported_outcomes": "core.outcome_kind", "core.reported_incidents": "core.incident_kind"}
#: The gate value at which both readings of the reported_* gates agree it is closed.
NONE_REPORTED = "none_reported"
MISSING_EXTRACTION = "T-022 pass-1 page request of this page (PerPageProviders.page_extraction)"
#: coder_version of a quote-step coder record: the pass-1 parser and its prompt version (procedural label).
QUOTE_STEP_CODER_VERSION = f"g3o.extract.parser_v27/{request_v27.PROMPT_VERSION}"

#: Source-row items refused here, with the reason (signed source text or the missing producer).
REFUSED_SOURCE_ITEMS: Mapping[str, str] = {
    sf.OFFICIAL: ("the master official-site overlay (OfficialSiteOverlay, RC-D-025 P13) is not passed to "
                  "the v2.7 per-page stage"),
    sf.SOURCE_TYPE: ("rules/0 needs source_on_official_domain (refused); the residual source_type question "
                     "(T-015's own jev request, RC-D-023 B-Q3 a) is not wired into the per-page stage, and "
                     "T-022 has no source_type quote task for its support check"),
    sf.CREDIBILITY: "reads source_type and source_publication_date (both refused)",
    sf.CONFIDENCE: ("reads source_credibility (refused) and the claim's support records "
                    "(items/core.confidence/rules/1; association is T-026's, RC-D-025 P12)"),
}

#: Activity-row items refused here, with the reason.
REFUSED_ACTIVITY_ITEMS: Mapping[str, str] = {
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
    sf.URL, sf.ACCESS_DATE, sf.LANGUAGE, sf.SYNDICATION, sf.TITLE, sf.REVIEW_STATE, sf.DISCOVERY,
    sf.TEXT_SOURCE, sc.CONTACT_ITEM, sc.CONTACT_EMAILS_ITEM, *STATED_FIELDS, *SAFEGUARDS, sf.SNIPPET,
    sf.DATE, sf.UPPER_BOUND, *EXTRACTED_FIELDS,
)


def pass1_activity_fields() -> tuple[str, ...]:
    """The activity quote-step items T-022 pass 1 asks (``request_v27`` rules from the signed codebook)."""
    return tuple(request_v27.default_rules().activity_fields)


#: Activity-row items produced by :func:`activity_row_values` (the reported_* lists only when gated out).
PRODUCED_ACTIVITY_ITEMS = ("core.unit_credit", *pass1_activity_fields(), *REPORTED_GATES)
#: Items produced on some pages and refused on others, with when they refuse.
CONDITIONAL_ITEMS: Mapping[str, str] = {
    sf.SNIPPET: "refused when the page verdict's support carries no quote (no signed rule for that case)",
    "core.content_vendor": ("refused on a GenAI-bearing page whose activities state no contracting party: it then "
                            "reads developer (PI A8.1 a needs codebook r16)"),
    **{item: (f"refused when {gate} opens the gate (no extractor produces the list: pass 'none', not a "
              f"T-022 pass-1 field), and when {gate} is a value other than {NONE_REPORTED!r} or the gate "
              "values (the signed gate values and its 'as ruled: not none_reported' note disagree)")
       for item, gate in REPORTED_GATES.items()},
}


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


def _from(fv: sf.FieldValue) -> RowValue:
    return RowValue(fv.item_id, fv.value, fv.basis)


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
    extracted value counts, PI ruling 65 a). ``content_vendor`` with no extracted
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
    """

    setup_pointer: str
    question_set_version: str
    extractor_model: str
    rule_coder_version: str
    response_model: str | None = None
    request_id: str | None = None

    @classmethod
    def of(cls, instrument: Mapping[str, Any], extraction: Any, *, rule_coder_version: str) -> Provenance:
        payload = instrument["payload"]
        return cls(instrument["instrument_id"], payload["question_set_version"], payload["extractor_model_id"],
                   rule_coder_version, getattr(extraction, "response_model", None),
                   getattr(extraction, "request_id", None))

    def quote_record(self, item: str, value: Any, chunk_id: str | None) -> CoderRecord:
        if not self.response_model or not self.request_id:
            raise sf.MissingUpstreamError("actual response model and request id of the T-022 pass-1 response "
                                          "(D-007)", [item])
        return CoderRecord(item_id=item, item_part=None, question_id=None, support_id=None, observation_id=None,
                           chunk_id=chunk_id, coder_type="quote_step", coder_version=QUOTE_STEP_CODER_VERSION,
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
                   prov: Provenance) -> QuoteValue:
    """``reported_outcomes`` / ``reported_incidents``: produced only when their gate is closed.

    The gate item at ``none_reported`` closes the gate under both readings of the
    signed gate (its ``values`` list and its "as ruled: not none_reported" note).
    An open gate needs the list itself, which no extractor produces (pass ``none``,
    not a T-022 pass-1 field): refused. Any other gate value: the two readings
    disagree, unruled.
    """
    gate = sf.default_codebook().items[item]["gate"]
    if gate["item"] != REPORTED_GATES[item]:
        raise ValueError(f"{item}: signed gate item {gate['item']!r} is not {REPORTED_GATES[item]!r}")
    key = activity_values.get(gate["item"])
    if key == NONE_REPORTED:
        return _gated(item, gate, activity_id, sources, prov, f"{gate['item']} = {key!r}")
    if key in gate["values"]:
        raise sf.MissingUpstreamError(f"an extractor of {item} (pass 'none'; not a T-022 pass-1 field)", [item])
    raise sf.UnruledError(item, f"{gate['item']} = {key!r}: the gate values {gate['values']} and the note "
                                f"{gate.get('as_ruled')!r} disagree")


def snippet_value(verdict_support: sc.SupportResult | None, sources: sc.PageSources,
                  prov: Provenance) -> QuoteValue:
    """X25: the page verdict's supporting quote (:func:`g3o.common.source_fields.source_snippet`).

    The quote was copied by the page's T-022 pass-1 request, whose provenance the
    record carries. A verdict support with no quote is refused: no signed rule
    says what that page's snippet is.
    """
    if verdict_support is None:
        raise sf.MissingUpstreamError("T-024 support of the final page verdict at its deciding part", [sf.SNIPPET])
    if verdict_support.supporting_text is None:
        raise sf.UnruledError(sf.SNIPPET, "the page verdict's support carries no quote")
    chunk = _known_part(sources, verdict_support.quote_chunk_id or verdict_support.chunk_id, sf.SNIPPET)
    fv = sf.source_snippet(verdict_support, sources)
    return QuoteValue(RowValue(sf.SNIPPET, fv.value, fv.basis),
                      ((fv.support, prov.quote_record(sf.SNIPPET, verdict_support.supporting_text, chunk)),))


#: PI ruling 63 a (2026-11-13): the support rule of a metadata/URL publication date.
DETERMINISTIC_DATE_RULE = "deterministic_date:"


def deterministic_date_rule(date: sf.FieldValue) -> str:
    """``deterministic_date:<origin>``: the A1.1 a tag of a metadata date, ``web_address`` for a URL date."""
    if date.date_origin == "metadata":
        tag = date.detail.get("tag")
        if not tag:
            raise ValueError("metadata publication date without its A1.1 a tag")
        return DETERMINISTIC_DATE_RULE + str(tag)
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
    """

    source: dict[str, RowValue] = field(default_factory=dict)
    activities: dict[str, dict[str, RowValue]] = field(default_factory=dict)
    refused: dict[str, str] = field(default_factory=dict)
    source_codes: list[Code] = field(default_factory=list)
    activity_codes: dict[str, list[Code]] = field(default_factory=dict)

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
        rows.refused[item] = str(exc)


def _try_quote(rows: AssembledRows, out: dict[str, RowValue], codes: list[Code], item: str,
               make: Callable[[], QuoteValue]) -> None:
    try:
        qv = make()
    except _REFUSALS as exc:
        rows.refused[item] = str(exc)
        return
    out[item] = qv.row
    codes.extend(qv.codes)


def page_source_values(page: Any, page_fields: Any, page_values: Mapping[str, Any],
                       activities: Mapping[str, Mapping[str, Any]], rows: AssembledRows, *,
                       followed: bool | None = None, sources: sc.PageSources | None = None,
                       verdict_support: sc.SupportResult | None = None,
                       provenance: Provenance | None = None, extraction: Any = None) -> None:
    """The page-level source-row values (see the module docstring) into ``rows.source``."""
    out = rows.source
    for item, attr in ((sf.URL, "url"), (sf.ACCESS_DATE, "access_date"), (sf.LANGUAGE, "language"),
                       (sf.SYNDICATION, "syndication_group"), (sf.TEXT_SOURCE, "text_source")):
        _try(rows, out, item, lambda item=item, attr=attr: _field(getattr(page_fields, attr, None), item))
    # Ruling 61 a: from the follow provenance; a followed page waits for its T-025 hop (seam: ``hop``).
    _try(rows, out, sf.DISCOVERY, lambda: _from(sf.discovery_path(followed=followed)))
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
    spans = {s.activity_id: s for s in getattr(extraction, "activities", ())}
    for item in EXTRACTED_FIELDS:
        _try(rows, out, item, lambda item=item: content_extracted(item, verdict, list(activities), spans))
    _try_quote(rows, out, rows.source_codes, sf.SNIPPET,
               lambda: snippet_value(verdict_support, _need(sources, sf.SNIPPET),
                                     _need(provenance, sf.SNIPPET)))
    try:  # X26 and the date_upper_bound note on it (mechanical: no code)
        dated = publication_date_value(page, page_fields, extraction, _need(sources, sf.DATE),
                                       _need(provenance, sf.DATE))
    except _REFUSALS as exc:
        rows.refused[sf.DATE] = str(exc)
        rows.refused[sf.UPPER_BOUND] = f"reads {sf.DATE} (refused)"
    else:
        out[sf.DATE] = dated.quote.row
        rows.source_codes.extend(dated.quote.codes)
        _try(rows, out, sf.UPPER_BOUND, lambda: _from(sf.date_upper_bound(dated.field)))


def _need(value: Any, item: str) -> Any:
    if value is None:
        raise sf.MissingUpstreamError(MISSING_EXTRACTION, [item])
    return value


def activity_row_values(activities: Mapping[str, Mapping[str, Any]], rows: AssembledRows, *,
                        extraction: Any = None, sources: sc.PageSources | None = None,
                        provenance: Provenance | None = None) -> None:
    """The per-observation activity-row values into ``rows.activities`` and their codes.

    ``unit_credit``; the T-022 pass-1 fields (:func:`activity_quote_value`) from the
    activity's span in ``extraction`` (the page's pass-1 request); the reported
    lists when gated out (:func:`reported_value`).
    """
    spans = {s.activity_id: s for s in getattr(extraction, "activities", ())}
    for aid, values in activities.items():
        out = rows.activities.setdefault(aid, {})
        codes = rows.activity_codes.setdefault(aid, [])
        _try(rows, out, "core.unit_credit", lambda values=values: unit_credit(values))
        for item in pass1_activity_fields():
            _try_quote(rows, out, codes, item, lambda item=item, aid=aid, values=values: activity_quote_value(
                item, aid, _need(spans.get(aid), item), values, _need(sources, item), _need(provenance, item)))
        for item in REPORTED_GATES:
            _try_quote(rows, out, codes, item, lambda item=item, aid=aid, values=values: reported_value(
                item, aid, values, _need(sources, item), _need(provenance, item)))


def assemble(page: Any, page_fields: Any, page_values: Mapping[str, Any],
             activities: Mapping[str, Mapping[str, Any]], *, followed: bool | None = None,
             extraction: Any = None, sources: sc.PageSources | None = None,
             verdict_support: sc.SupportResult | None = None,
             provenance: Provenance | None = None) -> AssembledRows:
    """Build every producible row value of one coded page and name every refused item.

    ``page`` is the :class:`~g3o.classify.jev_page_code.PageInput`,
    ``page_fields`` its :class:`~g3o.run.presweep.perpage_inputs_v27.PageSourceFields`,
    ``page_values`` the final page values and ``activities`` the final values of
    each coded activity (``{activity_id: values}``; empty on a page with no activity).
    ``followed`` is ``PageUpstream.followed`` (T-025; None: no follow provenance).
    ``extraction`` is the page's T-022 pass-1 request
    (:class:`~g3o.extract.parser_v27.Pass1Extraction`, from
    ``PerPageProviders.page_extraction``), ``sources`` the coded page's parts,
    ``verdict_support`` the T-024 support of the final verdict and ``provenance``
    what the coder records carry (:meth:`Provenance.of`). Without them every
    quote-step item is refused.
    """
    if page_fields is None:
        raise sf.MissingUpstreamError("perpage_inputs_v27.PageSourceFields (PageUpstream.page_fields)",
                                      [page.page_id])
    rows = AssembledRows()
    rows.refused.update(REFUSED_SOURCE_ITEMS)
    if activities:
        rows.refused.update(REFUSED_ACTIVITY_ITEMS)
    page_source_values(page, page_fields, page_values, activities, rows, followed=followed, sources=sources,
                       verdict_support=verdict_support, provenance=provenance, extraction=extraction)
    activity_row_values(activities, rows, extraction=extraction, sources=sources, provenance=provenance)
    return rows


__all__ = [
    "ASSEMBLER", "PRODUCED_ACTIVITY_ITEMS", "PRODUCED_SOURCE_ITEMS", "REFUSED_ACTIVITY_ITEMS",
    "REFUSED_SOURCE_ITEMS", "AssembledRows", "RowValue", "activity_row_items", "activity_row_values", "assemble",
    "content_contact", "content_contact_emails", "content_safeguard", "content_stated", "genai_verdicts",
    "page_source_values", "source_row_items", "source_title", "stated", "unit_credit", "unproduced_items",
    "vendor_claim_only",
]
