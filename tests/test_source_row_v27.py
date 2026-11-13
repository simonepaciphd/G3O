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
    assert set(rows.refused) == set(srow.REFUSED_SOURCE_ITEMS) | set(srow.REFUSED_ACTIVITY_ITEMS) | quote_items
    assert all(srow.MISSING_EXTRACTION in rows.refused[i] for i in quote_items - {sf.UPPER_BOUND})
    assert not set(rows.source) & set(rows.refused)


def test_no_activity_page_refuses_only_source_items():
    rows = srow.assemble(_page(), FIELDS_P1, NOGENAI, {}, followed=False)
    assert set(rows.refused) == set(srow.REFUSED_SOURCE_ITEMS) | {sf.SNIPPET, sf.DATE, sf.UPPER_BOUND}
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
    rows = srow.assemble(_page(), FIELDS_P1, GENAI, {"a1": _activity(**{"core.observed_actor_relationship": unit}),
                                                     "a2": _activity()})
    assert {a: r["core.unit_credit"].value for a, r in rows.activities.items()} == {"a1": "yes", "a2": "no"}


def test_vendor_claim_only_a89():
    assert srow.vendor_claim_only("vendor").value == "yes"
    assert srow.vendor_claim_only("news_major").value == "no"
    assert srow.vendor_claim_only("not_documented").value == "unknown"
    with pytest.raises(ValueError):
        srow.vendor_claim_only("press_release")


def test_missing_producers_names_the_refused_items():
    assert pin.MISSING_PRODUCERS == (pin.FOLLOW_ATTEMPTS_MISSING, pin.VALUES_MISSING)
    for item in srow.unproduced_items():
        assert item in pin.VALUES_MISSING
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


@pytest.mark.parametrize("item", list(srow.REPORTED_GATES))
def test_reported_lists_only_when_gated_out(item):
    gate = srow.REPORTED_GATES[item]
    qv = srow.reported_value(item, "p1#a001", _activity(**{gate: "none_reported"}), SOURCES, PROV)
    (sr, rec), = qv.codes
    assert qv.row.value == "not_asked" and sr.support_rule_name == f"gated_out:{gate}"
    with pytest.raises(sf.MissingUpstreamError, match="extractor"):
        srow.reported_value(item, "p1#a001", _activity(**{gate: "quantified"}), SOURCES, PROV)
    with pytest.raises(sf.UnruledError):
        srow.reported_value(item, "p1#a001", _activity(**{gate: "unknown"}), SOURCES, PROV)


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
    with pytest.raises(sf.UnruledError):  # a verdict support with no quote: no signed rule
        srow.snippet_value(_verdict(None), SOURCES, PROV)
    with pytest.raises(sf.MissingUpstreamError):
        srow.snippet_value(None, SOURCES, PROV)


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
    assert [sr.item_id for sr, _ in rows.source_codes] == [sf.SNIPPET]
    assert set(rows.refused) == set(srow.REFUSED_SOURCE_ITEMS) | set(srow.REFUSED_ACTIVITY_ITEMS)
    # An activity with no span in the page request is refused item by item.
    rows = srow.assemble(_page(), FIELDS_P1, GENAI, {"p1#a002": acts["p1#a001"]}, followed=False,
                         extraction=_Extraction(span), sources=SOURCES, verdict_support=_verdict(quote),
                         provenance=PROV)
    assert all(i in rows.refused for i in srow.pass1_activity_fields())


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
        expected = f"deterministic_date:{tag if origin == 'metadata' else 'web_address'}"
        assert dv.quote.row.value == "2025-03-12"
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
