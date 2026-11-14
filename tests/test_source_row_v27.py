"""T-015 source-row assembler (PI ruling 35 a): produced values, refusals and item coverage.

No network and no provider call: pages are declared ``PageInput`` records and the
page-level fields are declared ``FieldValue`` records (the producers of those are
tested in ``test_perpage_inputs_v27``).
"""
from __future__ import annotations

import pytest

from g3o.classify.jev_page_code import PageInput
from g3o.common import source_fields as sf
from g3o.common import support_check as sc
from g3o.common.storage_fields import FIELDS
from g3o.run.presweep import official_site_v27 as osv
from g3o.run.presweep import perpage_inputs_v27 as pin
from g3o.run.presweep import source_row_v27 as srow
from g3o.run.presweep import stage_perpage_v27 as pp

URL = "https://one.example.gov/news/ai-pilot"
TEXT = "The council runs a pilot. Write to ai@one.example.gov for details."


def _page(*, title="AI pilot", chrome="Contact: help@one.example.gov", emails=("info@one.example.gov",)):
    return PageInput("p1", "INST-0000001", "Council One", "Australia", "local", URL, title, TEXT, chrome,
                     email_links=emails)


def _fv(item, value):
    return sf.FieldValue(item, value, FIELDS[item]["coder"], "declared fixture")


FIELDS_P1 = pin.PageSourceFields(url=_fv(sf.URL, URL), access_date=_fv(sf.ACCESS_DATE, "2026-11-10"),
                                 publication_date=None, archive_address=False,
                                 language=_fv(sf.LANGUAGE, "en"), syndication_group=_fv(sf.SYNDICATION, "sg-1"),
                                 text_source=sf.text_source("new_run"))
GENAI = {"core.page_verdict": "confirms_activity", "core.content_contact_named": "yes",
         "core.content_contact_details": "no"}
NOGENAI = {"core.page_verdict": "no_genai", "core.content_contact_named": "no",
           "core.content_contact_details": "no"}


def _activity(**values):
    base = {"core.observed_actor_relationship": {"relationship": "this_institution",
                                                 "searched_institution_role": "contracting_authority"},
            **{f"core.function_{f}": "no" for f in ("drafting_writing", "summarization", "translation",
                                                     "search_retrieval", "code", "image_audio_video",
                                                     "extraction_classification", "analysis_recommendation")},
            "core.target_users": "not_documented", "core.governed_population": "_NA_",
            "core.adoption_stage": "not_documented", "core.year_announced": "not_documented",
            "core.year_pilot_start": "not_documented", "core.year_production_start": "not_documented",
            "core.has_human_oversight": "no", "core.has_risk_assessment": "unclear",
            "core.has_transparency_notice": "unknown"}
    base.update(values)
    return base


def _values(rows):
    return {k: v.value for k, v in rows.source.items()}


#: Read without the run's official sites (PI ruling 70 b): X37 and what reads it are refused.
TYPED = {sf.OFFICIAL, sf.SOURCE_TYPE, sf.CREDIBILITY}


def test_every_row_item_is_produced_or_refused_exactly_once():
    src, act = srow.source_row_items(), srow.activity_row_items()
    assert set(srow.PRODUCED_SOURCE_ITEMS) | set(srow.REFUSED_SOURCE_ITEMS) == src
    assert not set(srow.PRODUCED_SOURCE_ITEMS) & set(srow.REFUSED_SOURCE_ITEMS)
    assert set(srow.PRODUCED_ACTIVITY_ITEMS) | set(srow.REFUSED_ACTIVITY_ITEMS) == act
    assert not set(srow.PRODUCED_ACTIVITY_ITEMS) & set(srow.REFUSED_ACTIVITY_ITEMS)
    # The same item sets produce_page fills from row values (classifier items come from the coders).
    assert src == {i for i in pp.SOURCE_ITEMS if FIELDS[i]["coder"] != "classifier" or i == pp.T015_CLASSIFIER}
    assert act == {i for i in pp.ACTIVITY_ITEMS if FIELDS[i]["coder"] != "classifier"} - {"core.uncertainty_flags"}


def test_discovery_path_and_text_source_rulings_61a_62a():
    for item in (sf.DISCOVERY, sf.TEXT_SOURCE):
        assert item in srow.PRODUCED_SOURCE_ITEMS and item not in srow.unproduced_items()
    v = _values(srow.assemble(_page(), FIELDS_P1, GENAI, {}, followed=False))
    assert (v[sf.DISCOVERY], v[sf.TEXT_SOURCE]) == ("searched", "new_run")
    # A followed page carries its T-025 hop (followed_hop_<n>); without it, or with no follow
    # provenance, or no text source, the item is refused.
    assert _values(srow.assemble(_page(), FIELDS_P1, GENAI, {}, followed=True, hop=2))[sf.DISCOVERY] == \
        "followed_hop_2"
    for followed in (True, None):
        rows = srow.assemble(_page(), FIELDS_P1, GENAI, {}, followed=followed)
        assert sf.DISCOVERY not in rows.source and "T-025" in rows.refused[sf.DISCOVERY]
    from dataclasses import replace
    rows = srow.assemble(_page(), replace(FIELDS_P1, text_source=None), GENAI, {}, followed=False)
    assert sf.TEXT_SOURCE in rows.refused


def test_page_level_values_from_page_fields_and_page():
    rows = srow.assemble(_page(), FIELDS_P1, GENAI, {"a1": _activity()}, followed=False)
    v = _values(rows)
    assert (v[sf.URL], v[sf.ACCESS_DATE], v[sf.LANGUAGE], v[sf.SYNDICATION]) == (URL, "2026-11-10", "en", "sg-1")
    assert v[sf.TITLE] == "AI pilot" and v[sf.REVIEW_STATE] == "reviewed"
    assert v[sc.CONTACT_ITEM] == "yes"
    # CX-53: main text, then chrome (header/footer), then the page's e-mail links.
    assert v[sc.CONTACT_EMAILS_ITEM] == ["ai@one.example.gov", "help@one.example.gov", "info@one.example.gov"]
    # Without the pass-1 request and its provenance every quote-step item is refused as well.
    quote_items = {sf.SNIPPET, sf.DATE, sf.UPPER_BOUND, *srow.pass1_activity_fields(), *srow.REPORTED_GATES,
                   *srow.EXTRACTED_FIELDS}
    assert set(rows.refused) == \
        set(srow.REFUSED_SOURCE_ITEMS) | set(srow.REFUSED_ACTIVITY_ITEMS) | quote_items | TYPED
    assert all(srow.MISSING_EXTRACTION in rows.refused[i] for i in quote_items - {sf.UPPER_BOUND})
    assert not set(rows.source) & set(rows.refused)


def test_no_activity_page_refuses_only_source_items():
    rows = srow.assemble(_page(), FIELDS_P1, NOGENAI, {}, followed=False)
    assert set(rows.refused) == set(srow.REFUSED_SOURCE_ITEMS) | {sf.SNIPPET, sf.DATE, sf.UPPER_BOUND} | TYPED
    assert rows.activities == {}
    v = _values(rows)
    assert v[sc.CONTACT_ITEM] == "no" and v[sc.CONTACT_EMAILS_ITEM] == "not_asked"
    assert all(v[i] == "no" for i in (*srow.STATED_FIELDS, *srow.SAFEGUARDS))


def test_empty_title_is_refused_ruling_39a():
    for title in ("", "  ", None):
        rows = srow.assemble(_page(title=title), FIELDS_P1, GENAI, {})
        assert sf.TITLE not in rows.source and "39 a" in rows.refused[sf.TITLE]


def test_missing_page_fields_are_refused():
    with pytest.raises(sf.MissingUpstreamError, match="page_fields"):
        srow.assemble(_page(), None, GENAI, {})
    from dataclasses import replace
    rows = srow.assemble(_page(), replace(FIELDS_P1, language=None), GENAI, {})
    assert sf.LANGUAGE in rows.refused and sf.LANGUAGE not in rows.source


@pytest.mark.parametrize(("named", "details", "expected"), [
    ("yes", "no", "yes"), ("no", "yes", "yes"), ("yes", "unknown", "yes"), ("no", "no", "no")])
def test_content_contact_signed_cases(named, details, expected):
    value = srow.content_contact({"core.content_contact_named": named, "core.content_contact_details": details})
    assert value.value == expected


@pytest.mark.parametrize(("named", "details"), [("unknown", "no"), ("no", "not_documented"),
                                                ("unknown", "unknown")])
def test_content_contact_missing_token_without_yes_is_unknown_64b(named, details):
    """PI ruling 64 b: a sub-item that is a missing token, and neither yes, gives unknown."""
    value = srow.content_contact({"core.content_contact_named": named, "core.content_contact_details": details})
    assert value.value == "unknown"
    rows = srow.assemble(_page(), FIELDS_P1, {**GENAI, "core.content_contact_named": named,
                                              "core.content_contact_details": details}, {}, followed=False)
    assert rows.source[sc.CONTACT_ITEM].value == "unknown"
    assert rows.source[sc.CONTACT_EMAILS_ITEM].value == "not_asked"  # CX-53 gate is yes only


def test_content_contact_absent_sub_item_is_refused():
    with pytest.raises(sf.MissingUpstreamError):
        srow.content_contact({"core.content_contact_named": None, "core.content_contact_details": "no"})
    rows = srow.assemble(_page(), FIELDS_P1, {"core.page_verdict": "confirms_activity"}, {}, followed=False)
    assert sc.CONTACT_ITEM in rows.refused and sc.CONTACT_EMAILS_ITEM in rows.refused


def test_contact_emails_gate_open_with_no_address_is_not_documented():
    page = PageInput("p1", "I", "C", "Australia", "local", URL, "T", "No address here.", None, email_links=None)
    assert srow.content_contact_emails("yes", page).value == "not_documented"
    assert srow.content_contact_emails("no", page).value == "not_asked"
    # T-014 stores bare addresses (mailto: stripped); they still reach the signed search.
    linked = PageInput("p1", "I", "C", "Australia", "local", URL, "T", "No address here.", "",
                       email_links=("press@one.example.gov",))
    assert srow.content_contact_emails("yes", linked).value == ["press@one.example.gov"]


def test_content_stated_items():
    verdict = "confirms_activity"
    quiet = [_activity()]
    for item in srow.STATED_FIELDS:
        assert srow.content_stated(item, verdict, quiet).value == "no"
        assert srow.content_stated(item, verdict, []).value == "no"
    assert srow.content_stated("core.content_purpose", verdict, [_activity(**{"core.function_code": "yes"})]).value \
        == "yes"
    assert srow.content_stated("core.content_users", verdict, [_activity(**{"core.target_users": "public"})]).value \
        == "yes"
    assert srow.content_stated("core.content_users", verdict,
                               [_activity(**{"core.governed_population": "both"})]).value == "yes"
    assert srow.content_stated("core.content_status_date", verdict,
                               [_activity(**{"core.adoption_stage": "pilot"})]).value == "yes"
    assert srow.content_stated("core.content_status_date", verdict,
                               [_activity(**{"core.year_pilot_start": "2024"})]).value == "yes"
    # Off GenAI-bearing pages the derived items are no, whatever the activities state.
    loud = [_activity(**{"core.function_code": "yes", "core.target_users": "public", "core.adoption_stage": "pilot"})]
    for item in srow.STATED_FIELDS:
        assert srow.content_stated(item, "no_genai", loud).value == "no"


def test_genai_verdicts_are_the_content_data_gate():
    assert srow.genai_verdicts() == {"confirms_activity", "ambiguous_genai", "ambiguous_attribution",
                                     "other_body", "event_only"}


def test_safeguards_yes_if_any_activity_yes_otherwise_no():
    acts = [_activity(), _activity(**{"core.has_risk_assessment": "yes"})]
    assert srow.content_safeguard("core.content_risk_assessment", acts).value == "yes"
    assert srow.content_safeguard("core.content_human_oversight", acts).value == "no"
    assert srow.content_safeguard("core.content_user_notification", acts).value == "no"
    assert srow.content_safeguard("core.content_user_notification",
                                  [_activity(**{"core.has_transparency_notice": "yes"})]).value == "yes"


def test_unit_credit_a87():
    unit = {"relationship": "unit_of_institution", "searched_institution_role": "unit"}
    assert srow.unit_credit(_activity(**{"core.observed_actor_relationship": unit})).value == "yes"
    assert srow.unit_credit(_activity()).value == "no"
    with pytest.raises(sf.MissingUpstreamError):
        srow.unit_credit({})
    with pytest.raises(sf.MissingUpstreamError):  # absent part: missing
        srow.unit_credit({"core.observed_actor_relationship": {"searched_institution_role": "unit"}})
    # a non-object value or an unsigned part is malformed (a wiring error, not a refusal)
    for bad in ("not_asked", {"relationship": "subsidiary", "searched_institution_role": "unit"}):
        with pytest.raises(ValueError) as info:
            srow.unit_credit({"core.observed_actor_relationship": bad})
        assert not isinstance(info.value, sf.MissingUpstreamError)
    rows = srow.assemble(_page(), FIELDS_P1, GENAI, {"a1": _activity(**{"core.observed_actor_relationship": unit}),
                                                     "a2": _activity()})
    assert {a: r["core.unit_credit"].value for a, r in rows.activities.items()} == {"a1": "yes", "a2": "no"}


def test_vendor_claim_only_a89():
    assert srow.vendor_claim_only("vendor").value == "yes"
    assert srow.vendor_claim_only("news_major").value == "no"
    assert srow.vendor_claim_only("not_documented").value == "unknown"
    with pytest.raises(ValueError):
        srow.vendor_claim_only("press_release")


def test_every_produced_item_is_conditional_wiring_only_or_never_refused_m2():
    """Review M2: every produced item is in exactly one of CONDITIONAL_ITEMS (refused on some pages' data),
    WIRING_ONLY_ITEMS (refused only on a missing upstream input) or NEVER_REFUSED_ITEMS."""
    produced = set(srow.PRODUCED_SOURCE_ITEMS) | set(srow.PRODUCED_ACTIVITY_ITEMS)
    groups = (set(srow.CONDITIONAL_ITEMS), set(srow.WIRING_ONLY_ITEMS), set(srow.NEVER_REFUSED_ITEMS))
    assert set().union(*groups) == produced and sum(len(g) for g in groups) == len(produced)
    for item in (sf.TITLE, sf.DATE, sf.UPPER_BOUND, sf.CREDIBILITY, sc.CONTACT_ITEM, sc.CONTACT_EMAILS_ITEM,
                 sf.SNIPPET, "core.unit_credit", *srow.pass1_activity_fields(), *srow.REPORTED_GATES):
        assert item in srow.CONDITIONAL_ITEMS
    assert sf.DATE in srow.CONDITIONAL_ITEMS[sf.CREDIBILITY]  # a refused date refuses credibility


def test_conditional_refusals_happen_on_page_data_m2():
    """The M2 refusal points named in CONDITIONAL_ITEMS refuse on data, not only on wiring."""
    # No metadata/URL date and no pass-1 request: the date was never asked; its readers follow.
    rows = srow.assemble(_page(), FIELDS_P1, NOGENAI, {}, followed=False, extraction=None, sources=SOURCES,
                         verdict_support=_verdict(None), provenance=PROV, official_sites=OWN)
    assert "no request" in rows.refused[sf.DATE]
    assert sf.DATE in rows.refused[sf.UPPER_BOUND] and sf.DATE in rows.refused[sf.CREDIBILITY]
    # A stored relationship object without its relationship part: unit_credit refused. (A bare token is
    # not a storable shape: storage.validate_value requires the two-part object; it is malformed.)
    rows = srow.assemble(_page(), FIELDS_P1, GENAI, {"a1": _activity(**{"core.observed_actor_relationship":
                                                                         {"searched_institution_role": "unit"}})},
                         followed=False)
    assert "core.unit_credit" in rows.refused


@pytest.mark.parametrize("basis", [sf.AUTO_OFFICIAL, sf.AUTO_ARCHIVE])
def test_vendor_claim_only_automatic_type_is_typed_not_vendor_ruling_88a(basis):
    # Ruling 88 a: an official-domain / archive page stored not_asked (rule source_type_auto:<basis>) is no.
    fv = sf.auto_source_type(basis).field
    assert srow.vendor_claim_only(fv.value, fv.rule_name).value == "no"


def test_vendor_claim_only_not_asked_without_automatic_typing():
    assert srow.vendor_claim_only("not_asked", sf.READABILITY_RULE + "too_short").value == "unknown"
    with pytest.raises(sf.MissingUpstreamError):
        srow.vendor_claim_only("not_asked")  # the stored rule name is read, never re-derived
    with pytest.raises(ValueError, match="not a rules/0 or R-015 rule name"):
        srow.vendor_claim_only("not_asked", "source_type_auto:somewhere")


def test_missing_producers_names_the_refused_items():
    assert pin.MISSING_PRODUCERS == (pin.FOLLOW_ATTEMPTS_MISSING, pin.VALUES_MISSING)
    for item in srow.unproduced_items():
        assert item in pin.VALUES_MISSING


def test_entry_gate_keeps_the_values_entry_for_conditional_refusals(monkeypatch):
    """Review M2 (rulings 36 a / 40 a): items refused on some pages keep the entry refusal."""
    assert set(srow.entry_refused_items()) == set(srow.unproduced_items()) | set(srow.CONDITIONAL_ITEMS)
    for item in srow.CONDITIONAL_ITEMS:
        assert item in pin.VALUES_MISSING
    monkeypatch.setattr(srow, "REFUSED_SOURCE_ITEMS", {})
    monkeypatch.setattr(srow, "REFUSED_ACTIVITY_ITEMS", {})
    assert srow.unproduced_items() == () and srow.entry_refused_items() == tuple(sorted(srow.CONDITIONAL_ITEMS))
    monkeypatch.setattr(srow, "CONDITIONAL_ITEMS", {})
    assert srow.entry_refused_items() == ()
    assert "core.source_url" not in pin.VALUES_MISSING


# ---------------------------------------------------------------------------
# Quote-step values: T-022 pass-1 fields, T-024 support, quote-step coder records
# ---------------------------------------------------------------------------

PART = "p1#p0"
QTEXT = "The council runs Copilot Chat with Contoso Ltd for 300 staff, said the Digital Office."
SOURCES = sc.PageSources("p1", {PART: QTEXT}, None)
PROV = srow.Provenance("a" * 64, "qsv-1", "fake-extractor", "activity-coder-v1", "fake-extractor-response", "req-1")


def _span(*fields, aid="p1#a001"):
    from g3o.extract.parser_v27 import ActivitySpan, FieldValue
    return ActivitySpan(aid, PART, 0, len(QTEXT), "resolved", QTEXT[:20], QTEXT[-20:],
                        tuple(FieldValue(i, v, PART, q) for i, v, q in fields))


class _Extraction:
    def __init__(self, *spans, response_model="fake-extractor-response", request_id="req-1", date=None):
        self.activities, self.response_model, self.request_id = spans, response_model, request_id
        self.publication_date = date


def test_pass1_fields_are_the_signed_activity_quote_step_items():
    assert set(srow.pass1_activity_fields()) == {"core.activity_name", "core.observed_actor_name",
                                                 "core.tool_name", "core.model_name", "core.contracting_party",
                                                 "core.deployment_scale_number"}
    for item in srow.pass1_activity_fields():
        assert FIELDS[item]["coder"] == "quote_step"


def test_extracted_field_is_support_checked_and_recorded():
    span = _span(("core.tool_name", "Copilot Chat", "runs Copilot Chat"))
    acts = _activity(**{"core.activity_type": "internal_operational"})
    qv = srow.activity_quote_value("core.tool_name", "p1#a001", span, acts, SOURCES, PROV)
    assert qv.row.value == ["Copilot Chat"]  # a list item stores [value]
    (sr, rec), = qv.codes
    assert sr.support_status == "supported" and sr.original_value == "Copilot Chat" and sr.activity_id == "p1#a001"
    assert (rec.coder_type, rec.answer_type, rec.chosen_value, rec.chunk_id) == \
        ("quote_step", "extracted", "Copilot Chat", PART)
    assert (rec.configured_model, rec.actual_response_model, rec.request_id, rec.question_set_version) == \
        ("fake-extractor", "fake-extractor-response", "req-1", "qsv-1")
    assert rec.coder_version == srow.QUOTE_STEP_CODER_VERSION


def test_quote_not_on_the_page_downgrades_and_absent_field_is_not_documented():
    span = _span(("core.activity_name", "AI helpdesk", "a sentence that is not on the page at all"))
    qv = srow.activity_quote_value("core.activity_name", "p1#a001", span, _activity(), SOURCES, PROV)
    (sr, rec), = qv.codes
    assert qv.row.value == "unknown" and sr.support_status == "downgraded_no_quote"
    assert rec.chosen_value == "AI helpdesk"  # the record keeps the original code
    qv = srow.activity_quote_value("core.observed_actor_name", "p1#a001", span, _activity(), SOURCES, PROV)
    (sr, rec), = qv.codes
    assert qv.row.value == "not_documented" and sr.support_status == "not_required"
    assert rec.chosen_value == "not_documented" and rec.chunk_id == PART


def test_applicability_gate_and_unruled_cell():
    span = _span(("core.contracting_party", "Contoso Ltd", "with Contoso Ltd"))
    gated = srow.activity_quote_value("core.contracting_party", "p1#a001", span,
                                      _activity(**{"core.activity_type": "policy_guidance"}), SOURCES, PROV)
    (sr, rec), = gated.codes
    assert gated.row.value == "not_asked" and sr.support_status == "set_by_rule"
    assert sr.support_rule_name == rec.rule_reference == "gated_out:core.activity_type"
    assert rec.coder_type == "mechanical" and rec.coder_version == "activity-coder-v1"
    asked = srow.activity_quote_value("core.contracting_party", "p1#a001", span,
                                      _activity(**{"core.activity_type": "pilot_experiment"}), SOURCES, PROV)
    assert asked.row.value == "Contoso Ltd"
    with pytest.raises(sf.UnruledError):
        srow.activity_quote_value("core.contracting_party", "p1#a001", span,
                                  _activity(**{"core.activity_type": "_NA_"}), SOURCES, PROV)


def test_superseded_part_is_refused_not_looked_up():
    """A part id the coded page no longer has (e.g. after an extra-round halving) is refused."""
    from g3o.extract.parser_v27 import ActivitySpan, FieldValue
    span = ActivitySpan("p1#a001", "p1#p9", 0, 5, "resolved", "x", "y",
                        (FieldValue("core.activity_name", "AI helpdesk", "p1#p9", "AI helpdesk"),))
    for item in ("core.activity_name", "core.observed_actor_name"):
        with pytest.raises(sf.MissingUpstreamError, match="superseded"):
            srow.activity_quote_value(item, "p1#a001", span, _activity(), SOURCES, PROV)


class _Pass2:
    """A declared T-032 pass-2 page request (``Pass2Support`` shape: fields, response model, request id)."""

    def __init__(self, *fields, response_model="fake-extractor-response-2", request_id="req-2"):
        self.fields, self.response_model, self.request_id = fields, response_model, request_id


def _p2field(item, value=None, support=None, *, status="stated", aid="p1#a001", chunk=PART):
    from g3o.extract.pass2_support import ActivityField
    if status != "stated":
        return ActivityField("f001", aid, item, None, None, None, status)
    return ActivityField("f001", aid, item, value, chunk, support, status)


@pytest.mark.parametrize("item", list(srow.REPORTED_GATES))
def test_reported_lists_closed_gate_is_not_asked_73_2a(item):
    gate = srow.REPORTED_GATES[item]
    # PI ruling 73.2 a: none_reported and the missing tokens close the gate.
    for closed in ("none_reported", "unknown", "not_documented", "not_asked", "_NA_"):
        qv = srow.reported_value(item, "p1#a001", _activity(**{gate: closed}), SOURCES, PROV)
        (sr, rec), = qv.codes
        assert qv.row.value == "not_asked" and sr.support_status == "set_by_rule"
        assert sr.support_rule_name == rec.rule_reference == f"gated_out:{gate}"
        assert "73.2 a" in qv.row.basis
    with pytest.raises(sf.MissingUpstreamError):  # gate item absent
        srow.reported_value(item, "p1#a001", _activity(), SOURCES, PROV)
    with pytest.raises(ValueError, match="not a signed code"):
        srow.reported_value(item, "p1#a001", _activity(**{gate: "plenty"}), SOURCES, PROV)


@pytest.mark.parametrize("item", list(srow.REPORTED_GATES))
def test_open_gate_reads_the_pass2_field_task_73_1b(item):
    """PI ruling 73.1 b: the open gate's list is the page's pass-2 field task, support-checked by T-024."""
    gate = srow.REPORTED_GATES[item]
    for open_value in srow.reported_open(item):
        acts = _activity(**{gate: open_value})
        with pytest.raises(sf.MissingUpstreamError, match="page_pass2"):  # no pass-2 page request
            srow.reported_value(item, "p1#a001", acts, SOURCES, PROV)
        with pytest.raises(sf.MissingUpstreamError, match="field task"):  # no field task for the activity
            srow.reported_value(item, "p1#a001", acts, SOURCES, PROV,
                                _Pass2(_p2field(item, "300 staff", "for 300 staff", aid="p1#a002")))
        qv = srow.reported_value(item, "p1#a001", acts, SOURCES, PROV,
                                 _Pass2(_p2field(item, "300 staff", "for 300 staff")))
        (sr, rec), = qv.codes
        assert qv.row.value == ["300 staff"] and sr.support_status == "supported" and "73.1 b" in qv.row.basis
        assert (rec.coder_type, rec.answer_type, rec.chosen_value, rec.chunk_id) == \
            ("quote_step", "extracted", "300 staff", PART)
        assert (rec.coder_version, rec.actual_response_model, rec.request_id) == \
            (srow.PASS2_CODER_VERSION, "fake-extractor-response-2", "req-2")
        # A quote not on the page is downgraded; a field stated with nothing usable is not_documented.
        bad = srow.reported_value(item, "p1#a001", acts, SOURCES, PROV,
                                  _Pass2(_p2field(item, "300 staff", "no such sentence on this page at all")))
        assert bad.codes[0][0].support_status == "downgraded_no_quote" and bad.row.value != ["300 staff"]
        for status in ("not_stated", "no_supporting_text", "wrong_part", "no_entry"):
            qv = srow.reported_value(item, "p1#a001", acts, SOURCES, PROV, _Pass2(_p2field(item, status=status)))
            (sr, rec), = qv.codes
            assert qv.row.value == "not_documented" and rec.chosen_value == "not_documented"
            assert rec.request_id == "req-2"
        with pytest.raises(sf.MissingUpstreamError, match="superseded"):
            srow.reported_value(item, "p1#a001", acts, SOURCES, PROV,
                                _Pass2(_p2field(item, "300 staff", "for 300 staff", chunk="p1#p9")))
        with pytest.raises(sf.MissingUpstreamError, match="D-007"):
            srow.reported_value(item, "p1#a001", acts, SOURCES, PROV,
                                _Pass2(_p2field(item, "300 staff", "for 300 staff"), request_id=None))


def test_discontinuation_uncertain_opens_the_incidents_gate_86b():
    """PI ruling 86 b: discontinuation_uncertain (a signed incident gate value) opens the gate."""
    assert srow.reported_open("core.reported_incidents") == ("quantified", "qualitative", "discontinuation_uncertain")
    assert srow.reported_open("core.reported_outcomes") == ("quantified", "qualitative")
    acts = _activity(**{"core.incident_kind": "discontinuation_uncertain"})
    qv = srow.reported_value("core.reported_incidents", "p1#a001", acts, SOURCES, PROV,
                             _Pass2(_p2field("core.reported_incidents", "300 staff", "for 300 staff")))
    assert qv.row.value == ["300 staff"]
    with pytest.raises(sf.MissingUpstreamError, match="page_pass2"):
        srow.reported_value("core.reported_incidents", "p1#a001", acts, SOURCES, PROV)
    assert not hasattr(srow, "REPORTED_OPEN_REFUSAL")


def test_assemble_reads_pass2_for_an_open_gate_73_1b():
    span = _span(("core.tool_name", "Copilot Chat", "runs Copilot Chat"))
    acts = {"p1#a001": _activity(**{"core.activity_type": "internal_operational",
                                    "core.outcome_kind": "quantified", "core.incident_kind": "none_reported"})}
    rows = srow.assemble(_page(), FIELDS_P1, GENAI, acts, followed=False, extraction=_Extraction(span),
                         sources=SOURCES, verdict_support=_verdict("The council runs Copilot Chat"), provenance=PROV,
                         pass2=_Pass2(_p2field("core.reported_outcomes", "300 staff", "for 300 staff")))
    got = rows.activities["p1#a001"]
    assert got["core.reported_outcomes"].value == ["300 staff"] and got["core.reported_incidents"].value == "not_asked"
    assert "core.reported_outcomes" not in rows.refused
    assert [rec.request_id for sr, rec in rows.activity_codes["p1#a001"] if sr.item_id == "core.reported_outcomes"] \
        == ["req-2"]


def _verdict(quote):
    return sc.check_code(sc.CodeEvidence("core.page_verdict", "confirms_activity", PART, probability=0.95,
                                         quote=quote, quote_chunk_id=PART if quote else None,
                                         entailment=sc.Entailment("true", 0.95) if quote else None), SOURCES)


def test_snippet_is_the_verdict_quote_with_pass1_provenance():
    quote = "The council runs Copilot Chat with Contoso Ltd"
    qv = srow.snippet_value(_verdict(quote), SOURCES, PROV)
    (sr, rec), = qv.codes
    assert qv.row.value == quote and sr.item_id == sf.SNIPPET and sr.support_status == "supported"
    assert (rec.coder_type, rec.chosen_value, rec.request_id) == ("quote_step", quote, "req-1")
    with pytest.raises(sf.MissingUpstreamError):
        srow.snippet_value(None, SOURCES, PROV)


def test_snippet_without_verdict_quote_is_not_asked_by_rule_72a():
    """PI ruling 72 a: no quote on the verdict's support -> not_asked, set by a named rule."""
    ruled = sc.check_code(sc.CodeEvidence("core.page_verdict", "not_assessable", None,
                                          rule_name="readability_failure:low_letter_share"), SOURCES)
    for support in (_verdict(None), ruled):  # a classifier verdict with no quote; a rule-set verdict
        qv = srow.snippet_value(support, SOURCES, PROV)
        (sr, rec), = qv.codes
        assert qv.row.value == "not_asked" and sr.item_id == sf.SNIPPET
        assert sr.support_status == "set_by_rule"
        assert sr.support_rule_name == rec.rule_reference == srow.NO_VERDICT_QUOTE_RULE == "no_verdict_quote"
        assert (rec.coder_type, rec.answer_type, rec.chosen_value) == ("mechanical", "rule", "not_asked")
    # Review M2: a rule-set snippet never refuses; a quote at a superseded part still does.
    assert "superseded" in srow.CONDITIONAL_ITEMS[sf.SNIPPET]
    assert "verdict_support is None" in srow.CONDITIONAL_ITEMS[sf.SNIPPET]  # review L-2
    with pytest.raises(sf.MissingUpstreamError):
        srow.snippet_value(None, SOURCES, PROV)
    with pytest.raises(ValueError, match="page verdict"):
        srow.snippet_value(sc.check_code(sc.CodeEvidence("core.tool_name", "x", None, rule_name="r"), SOURCES),
                           SOURCES, PROV)


def test_quote_record_needs_actual_response_metadata():
    from dataclasses import replace
    span = _span(("core.tool_name", "Copilot Chat", "runs Copilot Chat"))
    for prov in (replace(PROV, request_id=None), replace(PROV, response_model=None)):
        with pytest.raises(sf.MissingUpstreamError, match="D-007"):
            srow.activity_quote_value("core.tool_name", "p1#a001", span,
                                      _activity(**{"core.activity_type": "unknown"}), SOURCES, prov)


def test_providers_hand_over_the_page_request(tmp_path):
    """The adapter hands the page's pass-1 page request to the per-page stage (after activity_input)."""
    from g3o.run.presweep import perpage_providers_v27 as ppv
    adapter = ppv._Adapter(None, tmp_path, lambda job: None, lambda q, t: None)
    with pytest.raises(KeyError):
        adapter.page_extraction("p1")
    ext = _Extraction()
    adapter._page_request["p1"] = ext
    assert adapter.page_extraction("p1") is ext
    adapter._page_request["p2"] = None  # the plan needed no request
    assert adapter.page_extraction("p2") is None
    providers = ppv._providers(adapter, "c" * 64, "fake-extractor", "fake-x35")
    assert providers.page_extraction("p1") is ext
    # PI ruling 73.1 b: the pass-2 page request is handed over the same way (None: no request needed).
    from types import SimpleNamespace
    sup = _Pass2()
    adapter._page_pass2["p1"], adapter._page_pass2["p2"] = sup, None
    inp = SimpleNamespace(page=SimpleNamespace(page_id="p1", institution_id="INST-0000001"))
    assert adapter.page_pass2(inp) is sup and providers.page_pass2(inp) is sup
    assert adapter.page_pass2(SimpleNamespace(page=SimpleNamespace(page_id="p2"))) is None


def test_provenance_from_instrument_and_extraction():
    instrument = {"instrument_id": "b" * 64,
                  "payload": {"question_set_version": "qsv-9", "extractor_model_id": "model-x"}}
    prov = srow.Provenance.of(instrument, _Extraction(), rule_coder_version="cv")
    assert prov == srow.Provenance("b" * 64, "qsv-9", "model-x", "cv", "fake-extractor-response", "req-1")
    assert srow.Provenance.of(instrument, None, rule_coder_version="cv").request_id is None


def test_assemble_with_extraction_builds_activity_quote_values_and_codes():
    span = _span(("core.activity_name", "Copilot Chat rollout", "runs Copilot Chat"),
                 ("core.tool_name", "Copilot Chat", "runs Copilot Chat"))
    acts = {"p1#a001": _activity(**{"core.activity_type": "internal_operational",
                                    "core.outcome_kind": "none_reported", "core.incident_kind": "none_reported"})}
    quote = "The council runs Copilot Chat with Contoso Ltd"
    rows = srow.assemble(_page(), FIELDS_P1, GENAI, acts, followed=False, extraction=_Extraction(span),
                         sources=SOURCES, verdict_support=_verdict(quote), provenance=PROV)
    got = {k: v.value for k, v in rows.activities["p1#a001"].items()}
    assert got["core.activity_name"] == "Copilot Chat rollout" and got["core.tool_name"] == ["Copilot Chat"]
    assert got["core.model_name"] == "not_documented"
    assert got["core.reported_outcomes"] == got["core.reported_incidents"] == "not_asked"
    assert rows.source[sf.SNIPPET].value == quote
    assert {sr.item_id for sr, _ in rows.activity_codes["p1#a001"]} == \
        {*srow.pass1_activity_fields(), *srow.REPORTED_GATES}
    # The snippet, then the T-022 date task's code: pass 1 returned no date, so not_documented with a
    # quote-step record (items/core.source_publication_date/rules/0; PI ruling 63 a covers metadata/URL dates).
    assert [sr.item_id for sr, _ in rows.source_codes] == [sf.SNIPPET, sf.DATE]
    assert rows.source[sf.DATE].value == "not_documented"
    assert [rec.coder_type for sr, rec in rows.source_codes if sr.item_id == sf.DATE] == ["quote_step"]
    # No official sites: X37 and source_type refused; the undated source's credibility is low (rules/0).
    # No contracting party extracted on a GenAI page: content_vendor reads the developer (ruling 65 a; r16).
    assert set(rows.refused) == set(srow.REFUSED_SOURCE_ITEMS) | set(srow.REFUSED_ACTIVITY_ITEMS) | \
        {sf.OFFICIAL, sf.SOURCE_TYPE, "core.content_vendor"}
    assert "r16" in rows.refused["core.content_vendor"]
    assert rows.source[sf.CREDIBILITY].value == "low"
    # An activity with no span in the page request is refused item by item.
    rows = srow.assemble(_page(), FIELDS_P1, GENAI, {"p1#a002": acts["p1#a001"]}, followed=False,
                         extraction=_Extraction(span), sources=SOURCES, verdict_support=_verdict(quote),
                         provenance=PROV)
    assert all(i in rows.refused for i in srow.pass1_activity_fields())


def test_assemble_reads_activity_fields_from_the_activity_only_request_87c():
    """PI ruling 87 c: when the page's activities came from its activity-only pass-1 request, their
    spans and pass-1 fields are read from that request, with its response model and request id; the
    snippet and the date still come from the first-round page request."""
    span = _span(("core.activity_name", "Copilot Chat rollout", "runs Copilot Chat"),
                 ("core.tool_name", "Copilot Chat", "runs Copilot Chat"))
    acts = {"p1#a001": _activity(**{"core.activity_type": "internal_operational",
                                    "core.outcome_kind": "none_reported", "core.incident_kind": "none_reported"})}
    quote = "The council runs Copilot Chat with Contoso Ltd"
    first = _Extraction()  # the first-round page request returned no activity
    only = _Extraction(span, response_model="activity-only-response", request_id="req-87c")
    rows = srow.assemble(_page(), FIELDS_P1, GENAI, acts, followed=False, extraction=first,
                         sources=SOURCES, verdict_support=_verdict(quote), provenance=PROV,
                         activity_extraction=only)
    got = {k: v.value for k, v in rows.activities["p1#a001"].items()}
    assert got["core.activity_name"] == "Copilot Chat rollout" and got["core.tool_name"] == ["Copilot Chat"]
    quoted = [rec for sr, rec in rows.activity_codes["p1#a001"]
              if rec.coder_type == "quote_step" and sr.item_id in srow.pass1_activity_fields()]
    assert quoted and {(r.actual_response_model, r.request_id) for r in quoted} == {
        ("activity-only-response", "req-87c")}
    page_level = [rec for sr, rec in rows.source_codes if rec.coder_type == "quote_step"]
    assert page_level and {(r.actual_response_model, r.request_id) for r in page_level} == {
        ("fake-extractor-response", "req-1")}
    # Without it, the first-round request (no span) refuses the activity fields, as before.
    rows = srow.assemble(_page(), FIELDS_P1, GENAI, acts, followed=False, extraction=first,
                         sources=SOURCES, verdict_support=_verdict(quote), provenance=PROV)
    assert all(i in rows.refused for i in srow.pass1_activity_fields())
    assert PROV.for_activity_only(only).request_id == "req-87c"


# ---------------------------------------------------------------------------
# Publication date (PI ruling 63 a) and date_upper_bound
# ---------------------------------------------------------------------------


def _meta_date(origin="metadata"):
    from g3o.common import date_signals
    tag = date_signals.TAG_ORDER[1] if origin == "metadata" else None
    dates = [sf.MetadataDate("2025-03-12", origin, "fixture", tag)]
    return sf.publication_date(dates, None, None), tag


def test_metadata_and_url_dates_get_a_deterministic_date_rule_63a():
    from dataclasses import replace
    for origin in ("metadata", "web_address"):
        date, tag = _meta_date(origin=origin)
        fields = replace(FIELDS_P1, publication_date=date)
        dv = srow.publication_date_value(_page(), fields, None, SOURCES, PROV)  # no request needed
        (sr, rec), = dv.quote.codes
        expected = f"deterministic_date:{origin}"  # PI ruling 92 b: the origin, not the tag
        assert dv.quote.row.value == "2025-03-12"
        if origin == "metadata":
            assert dv.field.detail["tag"] == tag  # the tag stays in the detail
        assert sr.support_status == "set_by_rule" and sr.support_rule_name == rec.rule_reference == expected
        assert rec.coder_type == "mechanical" and sf.date_upper_bound(dv.field).value == "no"


def test_quote_step_date_supported_failed_or_absent():
    from g3o.extract.parser_v27 import FieldValue
    text = "In 2024 the council runs Copilot Chat."
    sources = sc.PageSources("p1", {PART: text}, None)
    good = FieldValue(sf.DATE, "2024", PART, "In 2024 the council runs Copilot Chat")
    dv = srow.publication_date_value(_page(), FIELDS_P1, _Extraction(date=good), sources, PROV)
    (sr, rec), = dv.quote.codes
    assert dv.quote.row.value == "2024" and sr.support_status == "supported"
    assert (rec.coder_type, rec.chosen_value, rec.chunk_id) == ("quote_step", "2024", PART)
    bad = FieldValue(sf.DATE, "2024", PART, "no such sentence anywhere here at all")
    dv = srow.publication_date_value(_page(), FIELDS_P1, _Extraction(date=bad), sources, PROV)
    assert dv.quote.row.value == "unknown" and dv.quote.codes[0][0].support_status == "downgraded_no_quote"
    dv = srow.publication_date_value(_page(), FIELDS_P1, _Extraction(), sources, PROV)
    (sr, rec), = dv.quote.codes
    assert dv.quote.row.value == "not_documented" and sr.support_status == "not_required"
    assert sf.date_upper_bound(dv.field).value == "not_asked"
    with pytest.raises(sf.MissingUpstreamError, match="no request"):
        srow.publication_date_value(_page(), FIELDS_P1, None, sources, PROV)


# ---------------------------------------------------------------------------
# content_tool_or_model / content_vendor (PI ruling 65 a)
# ---------------------------------------------------------------------------


def test_content_extracted_items_65a():
    named = _span(("core.tool_name", "Copilot Chat", "a quote that fails R-042 still counts"))
    party = _span(("core.contracting_party", "Contoso Ltd", "with Contoso Ltd"))
    bare = _span()
    aid = "p1#a001"
    assert srow.content_extracted("core.content_tool_or_model", "confirms_activity", [aid], {aid: named}).value         == "yes"
    assert srow.content_extracted("core.content_tool_or_model", "confirms_activity", [aid], {aid: bare}).value         == "no"
    assert srow.content_extracted("core.content_vendor", "confirms_activity", [aid], {aid: party}).value == "yes"
    with pytest.raises(sf.MissingUpstreamError, match="r16"):  # no contracting party: reads the developer
        srow.content_extracted("core.content_vendor", "confirms_activity", [aid], {aid: bare})
    with pytest.raises(sf.MissingUpstreamError):  # an activity with no span in the page request
        srow.content_extracted("core.content_tool_or_model", "confirms_activity", [aid], {})
    for item in srow.EXTRACTED_FIELDS:
        assert srow.content_extracted(item, "no_genai", [aid], {aid: named}).value == "no"
        assert srow.content_extracted(item, "confirms_activity", [], {}).value == "no"


def test_to_upstream_shape_and_refusal():
    """The assembled rows in the PageUpstream shape (per source-row unit), refused while anything is."""
    span = _span(("core.tool_name", "Copilot Chat", "runs Copilot Chat"))
    acts = {"p1#a001": _activity(**{"core.activity_type": "internal_operational",
                                    "core.outcome_kind": "none_reported", "core.incident_kind": "none_reported"})}
    rows = srow.assemble(_page(), FIELDS_P1, GENAI, acts, followed=False, extraction=_Extraction(span),
                         sources=SOURCES, verdict_support=_verdict("The council runs Copilot Chat"), provenance=PROV)
    with pytest.raises(sf.MissingUpstreamError, match="core.source_type"):
        rows.to_upstream(["p1#a001"])
    rows.refused.clear()  # as if every standing refusal were lifted
    a_vals, s_vals, codes = rows.to_upstream(["p1#a001"])
    assert a_vals["p1#a001"]["core.tool_name"] == ["Copilot Chat"]
    assert s_vals["p1#a001"]["core.source_snippet"] == "The council runs Copilot Chat"
    assert codes["p1#a001"][:len(rows.source_codes)] == rows.source_codes
    assert {sr.item_id for sr, _ in codes["p1#a001"]} >= {"core.tool_name", "core.source_snippet"}
    _, s_na, c_na = rows.to_upstream(["_NA_"])
    assert c_na["_NA_"] == rows.source_codes and s_na["_NA_"] == s_vals["p1#a001"]


# ---------------------------------------------------------------------------
# PI ruling 70 b: official domain from this run's sites; source_type rules/0; credibility
# ---------------------------------------------------------------------------

INST = "INST-0000001"


def _sites(**hosts):
    return osv.RunOfficialSites("fixture: 2_official_site.json", hosts, frozenset())


OWN = _sites(**{INST: "one.example.gov"})
ELSEWHERE = _sites(**{INST: "council-one.gov.au"})


def _typed(page, fields, sites, date=None):
    return srow.assemble(page, fields, NOGENAI, {}, followed=False, extraction=_Extraction(date=date),
                         sources=SOURCES, verdict_support=_verdict("The council runs Copilot Chat"),
                         provenance=PROV, official_sites=sites)


def _dated():
    from dataclasses import replace
    return replace(FIELDS_P1, publication_date=_meta_date()[0])


def test_official_page_is_typed_automatically_70b():
    rows = _typed(_page(), FIELDS_P1, OWN)
    v = _values(rows)
    assert v[sf.OFFICIAL] == "own_official" and v[sf.SOURCE_TYPE] == "not_asked"
    (sr, rec), = [(sr, rec) for sr, rec in rows.source_codes if sr.item_id == sf.SOURCE_TYPE]
    assert sr.support_status == "set_by_rule"
    assert sr.support_rule_name == rec.rule_reference == "source_type_auto:official_domain"
    assert rec.coder_type == "mechanical" and rec.chosen_value == "not_asked"
    assert v[sf.CREDIBILITY] == "low"  # pass 1 returned no date: not_documented -> low (rules/0)
    dated = _values(_typed(_page(), _dated(), OWN))
    assert dated[sf.CREDIBILITY] == sf.signed_credibility_map().cells["official_domain"]
    assert not TYPED & set(rows.refused)
    # Another institution's site of this run: other_official, also typed automatically.
    other = _values(_typed(_page(), FIELDS_P1, _sites(**{INST: "council-one.gov.au", "X": "one.example.gov"})))
    assert (other[sf.OFFICIAL], other[sf.SOURCE_TYPE]) == ("other_official", "not_asked")


def test_archive_address_is_typed_automatically_70b():
    from dataclasses import replace
    rows = _typed(_page(), replace(_dated(), archive_address=True), ELSEWHERE)
    v = _values(rows)
    assert (v[sf.OFFICIAL], v[sf.SOURCE_TYPE]) == ("not_official", "not_asked")
    assert [sr.support_rule_name for sr, _ in rows.source_codes if sr.item_id == sf.SOURCE_TYPE] ==         ["source_type_auto:archive_address"]
    assert v[sf.CREDIBILITY] == sf.signed_credibility_map().cells["archive_address"]


def test_residual_page_routing_70b():
    # Readable residual page: refused (no residual question and quote wired); undated: credibility low.
    rows = _typed(_page(), FIELDS_P1, ELSEWHERE)
    assert _values(rows)[sf.OFFICIAL] == "not_official"
    assert sf.SOURCE_TYPE not in rows.source and srow.RESIDUAL_REFUSAL in rows.refused[sf.SOURCE_TYPE]
    assert _values(rows)[sf.CREDIBILITY] == "low"
    dated = _typed(_page(), _dated(), ELSEWHERE)
    assert sf.CREDIBILITY in dated.refused and sf.CREDIBILITY not in dated.source
    # No official site for the institution (P13): unknown, and the page is residual.
    rows = _typed(_page(), FIELDS_P1, osv.RunOfficialSites("fixture", {}, frozenset({INST})))
    assert _values(rows)[sf.OFFICIAL] == "unknown" and sf.SOURCE_TYPE in rows.refused
    # An unreadable residual page is not sent (R-015): not_asked by its readability rule.
    unreadable = PageInput("p1", INST, "Council One", "Australia", "local", URL, "AI pilot",
                           "0123456789 " * 40, None)
    rows = _typed(unreadable, _dated(), ELSEWHERE)
    v = _values(rows)
    assert v[sf.SOURCE_TYPE] == "not_asked"
    assert [sr.support_rule_name for sr, _ in rows.source_codes if sr.item_id == sf.SOURCE_TYPE] ==         ["readability_failure:low_letter_share"]
    assert v[sf.CREDIBILITY] == sf.signed_credibility_map().cells["not_asked"]


def test_unresolved_official_site_refuses_its_readers_70b():
    sites = osv.RunOfficialSites("fixture", {}, frozenset(), {INST: "the classify_official_site step failed for it"})
    rows = _typed(_page(), FIELDS_P1, sites)
    assert "step failed" in rows.refused[sf.OFFICIAL] and sf.OFFICIAL in rows.refused[sf.SOURCE_TYPE]
    assert _values(rows)[sf.CREDIBILITY] == "low"  # undated: low whatever the type
    rows = _typed(_page(), FIELDS_P1, None)
    assert srow.OFFICIAL_SITES in rows.refused[sf.OFFICIAL]
    assert TYPED - {sf.CREDIBILITY} <= set(rows.refused)


def test_residual_source_type_refused_before_any_call_83b():
    """PI ruling 83 b (replacing 71 b) is not wired on this branch (open PI question): still refused."""
    assert "83 b" in srow.RESIDUAL_REFUSAL
    rows = _typed(_page(), FIELDS_P1, ELSEWHERE)  # the assembler is handed no jev call at all
    assert rows.refused[sf.SOURCE_TYPE].endswith(f"{srow.RESIDUAL_REFUSAL}: {sf.SOURCE_TYPE}")
    assert sf.SOURCE_TYPE in srow.CONDITIONAL_ITEMS and sf.SOURCE_TYPE not in srow.unproduced_items()


def test_gated_out_contracting_party_still_counts_for_content_vendor_74a():
    """PI ruling 74 a: ruling 65 a read literally; the extracted value counts even when the item is gated out."""
    span = _span(("core.contracting_party", "Contoso Ltd", "with Contoso Ltd"))
    acts = {"p1#a001": _activity(**{"core.activity_type": "policy_guidance",  # contracting_party: not_asked cell
                                    "core.outcome_kind": "none_reported", "core.incident_kind": "none_reported"})}
    rows = srow.assemble(_page(), FIELDS_P1, GENAI, acts, followed=False, extraction=_Extraction(span),
                         sources=SOURCES, verdict_support=_verdict("The council runs Copilot Chat"), provenance=PROV)
    assert rows.activities["p1#a001"]["core.contracting_party"].value == "not_asked"
    assert rows.source["core.content_vendor"].value == "yes"
    assert "65 a" in rows.source["core.content_vendor"].basis
