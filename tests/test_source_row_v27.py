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
    # A followed page waits for its T-025 hop; no follow provenance, or no text source, refuses.
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
    assert set(rows.refused) == set(srow.REFUSED_SOURCE_ITEMS) | set(srow.REFUSED_ACTIVITY_ITEMS)
    assert not set(rows.source) & set(rows.refused)


def test_no_activity_page_refuses_only_source_items():
    rows = srow.assemble(_page(), FIELDS_P1, NOGENAI, {}, followed=False)
    assert set(rows.refused) == set(srow.REFUSED_SOURCE_ITEMS) and rows.activities == {}
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


@pytest.mark.parametrize(("named", "details"), [("unknown", "no"), ("no", "not_documented"), (None, "no")])
def test_content_contact_without_a_rule_is_refused(named, details):
    with pytest.raises(sf.UnruledError):
        srow.content_contact({"core.content_contact_named": named, "core.content_contact_details": details})
    rows = srow.assemble(_page(), FIELDS_P1, {**GENAI, "core.content_contact_named": named,
                                              "core.content_contact_details": details}, {})
    assert sc.CONTACT_ITEM in rows.refused and sc.CONTACT_EMAILS_ITEM in rows.refused
    assert sc.CONTACT_EMAILS_ITEM not in rows.source


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
    assert pin.MISSING_PRODUCERS == (pp.FOLLOW_PRODUCER, pin.VALUES_MISSING)
    for item in srow.unproduced_items():
        assert item in pin.VALUES_MISSING
    assert "core.source_url" not in pin.VALUES_MISSING
