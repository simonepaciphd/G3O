"""Tests for the T-015 source-level field coder.

Expected values come from the signed codebook r14 rules (RC-D-025 A1, C5, C6 a, C7 a,
C8 b; PI-signed 2026-11-10) and the PI-approved procedural points P10-P14, not from the
implementation. Expected map cells are restated here from the PI's chat reply recorded in
RC-D-025 ("vendor medium, academic high, social media low, other medium, archive medium,
5f low") and the r14 rules/1 text, so a codebook drift fails the test. jev is mocked; no
network.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from g3o.classify import jev_page_code as jpc
from g3o.classify.questions.v27 import SIGNED_CODEBOOK_SHA256, load_set
from g3o.codebook.loader import default_codebook_path, load_codebook
from g3o.common import source_fields as sf
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.common.jev_record import load_classifier_rules
from g3o.common.part_combine import NOT_COVERED
from g3o.common.support_check import (
    CodeEvidence,
    Entailment,
    PageSources,
    SupportResult,
    check_code,
)
from g3o.extract.parser_v27 import FieldValue as ExtractedField

PAGE_TEXT = ("The ministry published its annual report on 12 March 2024. "
             "Staff use a generative AI assistant to draft letters.")
SOURCES = PageSources("inst1:u1", {"inst1:u1#p001": PAGE_TEXT})
P1 = "inst1:u1#p001"


@pytest.fixture(scope="module")
def vocab():
    return sf.default_vocab()


# ---------------------------------------------------------------------------
# Codebook coverage
# ---------------------------------------------------------------------------


def test_every_source_level_item_is_named(vocab):
    cb = load_codebook()
    assert cb.sha256 == "7972b8c1989af5e182c19d9d73c4ab20cb2440b06c7be33dff1701071658123b"
    expected = {k for k, v in cb.items.items() if "source" in (v.get("level") or [])}
    assert set(vocab.source_items) == expected
    assert {"core.source_type", "core.source_credibility", "core.confidence", "core.source_publication_date",
            "core.source_snippet", "core.source_language", "core.source_on_official_domain",
            "core.syndication_group", "core.date_upper_bound"} <= expected


def test_values_read_from_signed_slots(vocab):
    # items/core.source_on_official_domain/rules/0 and items/core.page_review_state/rules/0
    assert vocab.official_values == ("own_official", "other_official", "not_official")
    assert vocab.review_states == ("reviewed", "fetch_failed", "no_usable_text", "link_not_followed_cap",
                                   "link_not_followed_hops")
    assert vocab.credibility_values == ("high", "medium", "low")
    assert "official_gov" not in vocab.source_type_codes and "archive" not in vocab.source_type_codes


# ---------------------------------------------------------------------------
# X37 official domain
# ---------------------------------------------------------------------------

OVERLAY = sf.OfficialSiteOverlay("overlay-test-v1", {"inst1": "https://www.ministry.example/",
                                                     "inst2": "https://agency.example/"})


@pytest.mark.parametrize(("url", "uid", "expected"), [
    ("https://ministry.example/report", "inst1", "own_official"),
    ("http://WWW.ministry.example/a", "inst1", "own_official"),
    ("https://agency.example/news", "inst1", "other_official"),
    ("https://news.example/story", "inst1", "not_official"),
    ("https://news.example/story", "inst9", "unknown"),
    ("https://agency.example/x", "inst9", "other_official"),
])
def test_official_domain(url, uid, expected):
    fv = sf.source_on_official_domain(url, uid, OVERLAY)
    assert fv.value == expected and fv.coder == "mechanical" and "overlay-test-v1" in fv.basis


def test_official_domain_needs_overlay():
    with pytest.raises(sf.MissingUpstreamError):
        sf.source_on_official_domain("https://a.example/", "inst1", None)


# ---------------------------------------------------------------------------
# X21 source_type: automatic typing (rule 0)
# ---------------------------------------------------------------------------


def _official(value):
    return sf.FieldValue(sf.OFFICIAL, value, "mechanical", "test")


@pytest.mark.parametrize(("official", "archive", "route"), [
    ("own_official", False, sf.AUTO_OFFICIAL),
    ("other_official", False, sf.AUTO_OFFICIAL),
    ("own_official", True, sf.AUTO_OFFICIAL),
    ("not_official", True, sf.AUTO_ARCHIVE),
    ("not_official", False, None),
    ("unknown", False, None),
])
def test_route_source_type(official, archive, route):
    assert sf.route_source_type(_official(official), archive) == route


def test_route_needs_archive_test():
    with pytest.raises(sf.MissingUpstreamError):
        sf.route_source_type(_official("not_official"), None)


@pytest.mark.parametrize("basis", [sf.AUTO_OFFICIAL, sf.AUTO_ARCHIVE])
def test_auto_typed_pages_are_not_asked(basis):
    t = sf.auto_source_type(basis)
    # "pages typed that way are not asked" + R-045 not_asked; a rule fixed it -> rule name
    assert t.field.value == "not_asked" and t.field.rule_name == "source_type_auto:" + basis
    assert t.typed_by == basis and t.records == ()
    with pytest.raises(sf.UnruledError):
        sf.source_type_label(t)


# ---------------------------------------------------------------------------
# X21 source_type: the residual classifier question
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rules():
    return load_classifier_rules(default_codebook_path().read_bytes(), expected_sha256=SIGNED_CODEBOOK_SHA256)


def cfg(rules):
    return jpc.PageCoderConfig(rules=rules, setup_pointer="a" * 64, configured_model="jev-test-1",
                               reserved_tokens=0)


def page(text=PAGE_TEXT):
    return jpc.PageInput(page_id="inst1:u1", institution_id="inst1", institution="Ministry", country="X",
                         level_of_government="national", url="https://news.example/story", title="Story",
                         text=text)


@dataclass
class FakeJev:
    answers: dict  # marker in page_text -> (choice, probability); "" = default

    def __post_init__(self):
        self.calls = []

    def __call__(self, state, questions):
        self.calls.append((state, questions))
        choice, p = self.answers[""]
        for marker, ans in self.answers.items():
            if marker and marker in state["page_text"]:
                choice, p = ans
        out = {}
        for qid, q in questions.items():
            assert choice in q["criteria"]
            rest = [c for c in q["criteria"] if c != choice]
            out[qid] = JevAnswer(qid, "choice", choice=choice, confidence=p,
                                 probabilities={choice: p, **{c: (1 - p) / len(rest) for c in rest}})
        return JevResult(out, "jev-test-1-20261101", f"req{len(self.calls)}", 10, 1)


def test_residual_question_uses_signed_question_and_approved_state(rules):
    fake = FakeJev({"": ("vendor", 0.95)})
    t = sf.code_source_type(page(), fake, cfg(rules))
    assert t.typed_by == "classifier" and t.field.value == "vendor" and t.field.coder == "classifier"
    state, questions = fake.calls[0]
    assert list(questions) == ["core.source_type"]
    q = questions["core.source_type"]
    assert q["instructions"] == "What kind of source is this page?"
    # the eight signed codes plus the offered missing label (jev_missing_choice); never `unknown`
    assert list(q["criteria"]) == ["news_major", "news_trade", "vendor", "academic", "policy_org",
                                   "social_media", "procurement_tender", "other", "not_documented"]
    assert state["coder_instructions"] == load_set("page")["system_prompt"]
    assert state["page_text"] == PAGE_TEXT
    assert all(r.item_id == "core.source_type" for r in t.records)
    assert t.result.question_set_version == sf.RESIDUAL_SET_VERSION
    assert sf.source_type_label(t) == "a vendor's page"


def test_residual_question_below_bar_is_flagged(rules):
    t = sf.code_source_type(page(), FakeJev({"": ("news_trade", 0.5)}), cfg(rules))
    assert t.outcome.failed is True and t.field.detail["failed"] is True


def test_residual_question_long_page_first_section(rules):
    para = "Background text about digital services in the administration. " * 120
    text = "\n\n".join(f"{m} {para}" for m in ("ALPHA", "BRAVO", "CHARLIE"))
    fake = FakeJev({"": (NOT_COVERED, 0.9), "BRAVO": ("academic", 0.9), "CHARLIE": ("vendor", 0.9)})
    c = jpc.PageCoderConfig(rules=rules, setup_pointer="a" * 64, configured_model="jev-test-1",
                            reserved_tokens=0, limit_tokens=6000)
    t = sf.code_source_type(page(text), fake, c)
    assert len(t.result.chunks) > 1
    # first_section: the first part with a real answer (all-06 a); silent parts skipped
    assert t.field.value == "academic"


def test_unreadable_page_is_not_sent(rules):
    fake = FakeJev({"": ("vendor", 0.95)})
    t = sf.code_source_type(page(text="%PDF-1.7 " + "x" * 50), fake, cfg(rules))
    assert fake.calls == [] and t.field.value == "not_asked"
    assert t.field.rule_name.startswith("readability_failure:")


def test_source_type_evidence_goes_through_t024(rules):
    t = sf.code_source_type(page(), FakeJev({"": ("vendor", 0.95)}), cfg(rules))
    ev = sf.source_type_evidence(t, quote="Staff use a generative AI assistant", quote_chunk_id=P1,
                                 entailment=Entailment("true", 0.9))
    assert ev.chunk_id == P1 and ev.probability == pytest.approx(0.95)
    assert check_code(ev, SOURCES).support_status == "supported"
    with pytest.raises(ValueError):
        sf.source_type_evidence(sf.auto_source_type(sf.AUTO_OFFICIAL), quote=None, quote_chunk_id=None,
                                entailment=None)


# ---------------------------------------------------------------------------
# X26 publication date, date_upper_bound
# ---------------------------------------------------------------------------


def test_date_metadata_first():
    d = sf.publication_date([sf.MetadataDate("2024-03-12", "metadata", "meta article:published_time"),
                             sf.MetadataDate("2023", "web_address", "/2023/")],
                            ExtractedField(sf.DATE, "2020", P1, "12 March 2024"), SOURCES)
    assert (d.value, d.date_origin, d.provenance) == ("2024-03-12", "metadata", "from_metadata")
    assert sf.date_upper_bound(d).value == "no"


def test_date_web_address_when_no_metadata():
    d = sf.publication_date([sf.MetadataDate("2024-03", "web_address", "/2024/03/")], None, SOURCES)
    assert (d.value, d.date_origin, d.provenance) == ("2024-03", "web_address", "from_metadata")


def test_date_metadata_disagreement_is_unruled():
    with pytest.raises(sf.UnruledError):
        sf.publication_date([sf.MetadataDate("2024", "metadata", "a"), sf.MetadataDate("2023", "metadata", "b")],
                            None, SOURCES)


def test_metadata_less_date_uses_quote_step():
    d = sf.publication_date([], ExtractedField(sf.DATE, "2024-03-12", P1, "published its annual report on 12 March 2024"),
                            SOURCES)
    assert (d.value, d.date_origin, d.provenance) == ("2024-03-12", "page_text_quote", "quoted_by_quote_step")
    assert d.support.support_status == "supported"


def test_quote_step_date_failing_r042_is_unknown():
    d = sf.publication_date([], ExtractedField(sf.DATE, "2019", P1, "first released in the spring of 2019"),
                            SOURCES)
    assert d.value == "unknown" and d.support.support_status == "downgraded_no_quote"
    assert d.support.original_value == "2019"


def test_no_date_anywhere():
    d = sf.publication_date([], None, SOURCES)
    assert d.value == "not_documented" and d.date_origin == "unknown"
    ub = sf.date_upper_bound(d)
    assert ub.value == "not_asked" and ub.rule_name


def test_date_producer_absent_refuses():
    with pytest.raises(sf.MissingUpstreamError):
        sf.publication_date(None, None, SOURCES)


def test_date_format_checked():
    with pytest.raises(ValueError):
        sf.publication_date([sf.MetadataDate("12/03/2024", "metadata", "x")], None, SOURCES)


# ---------------------------------------------------------------------------
# X25 snippet
# ---------------------------------------------------------------------------


def _verdict(quote, chunk=P1):
    ev = CodeEvidence(item_id="core.page_verdict", value="confirms_activity", chunk_id=chunk, probability=0.95,
                      quote=quote, quote_chunk_id=chunk, entailment=Entailment("true", 0.95) if quote else None)
    return check_code(ev, SOURCES)


def test_snippet_is_the_verdict_quote_verbatim_and_whole():
    long_text = PAGE_TEXT * 4
    sources = PageSources("inst1:u1", {P1: long_text})
    ev = CodeEvidence(item_id="core.page_verdict", value="confirms_activity", chunk_id=P1, probability=0.95,
                      quote=long_text[:260], quote_chunk_id=P1, entailment=Entailment("true", 0.95))
    s = sf.source_snippet(check_code(ev, sources), sources)
    assert s.value == long_text[:260] and len(s.value) > 200
    assert s.support.support_status == "supported" and s.provenance == "quoted_by_quote_step"


def test_snippet_without_verdict_quote_is_unknown():
    s = sf.source_snippet(_verdict(None), SOURCES)
    assert s.value == "unknown" and s.support.support_status == "downgraded_no_quote"


def test_snippet_quote_not_on_page_is_unknown():
    s = sf.source_snippet(_verdict("an entirely different sentence that is nowhere"), SOURCES)
    assert s.value == "unknown" and s.support.support_status == "downgraded_no_quote"


def test_snippet_needs_verdict_record():
    with pytest.raises(sf.MissingUpstreamError):
        sf.source_snippet(None, SOURCES)


# ---------------------------------------------------------------------------
# X28 url, title, access date; X39 review state; refusals
# ---------------------------------------------------------------------------


def test_url_title_access_date():
    assert sf.source_url("https://x.example/A?b=1").value == "https://x.example/A?b=1"
    assert sf.source_title("Home", "AI pilot").value == "Home"
    assert sf.source_title("  ", "AI pilot").value == "AI pilot"
    assert sf.source_title(None, None).value == "not_documented"
    a = sf.source_access_date("2026-11-10")
    assert a.value == "2026-11-10" and a.provenance == "from_metadata"
    with pytest.raises(sf.MissingUpstreamError):
        sf.source_url(None)
    with pytest.raises(sf.MissingUpstreamError):
        sf.source_access_date(None)


def test_review_state():
    assert sf.page_review_state("link_not_followed_cap").value == "link_not_followed_cap"
    with pytest.raises(ValueError):
        sf.page_review_state("followed")
    with pytest.raises(sf.MissingUpstreamError):
        sf.page_review_state(None)


def test_unproduced_items_refuse():
    with pytest.raises(sf.MissingUpstreamError):
        sf.source_language(PAGE_TEXT)
    with pytest.raises(sf.MissingUpstreamError):
        sf.syndication_group(None)
    with pytest.raises(sf.UnruledError):
        sf.discovery_path("searched")
    with pytest.raises(sf.UnruledError):
        sf.text_source("stored")


# ---------------------------------------------------------------------------
# X22 credibility
# ---------------------------------------------------------------------------

#: X22 cells as items/core.source_credibility/rules/1 (r14) states them in words.
EXPECTED_CELLS = {
    "official_domain": "high", "procurement_tender": "high", "news_major": "medium", "news_trade": "medium",
    "policy_org": "medium", "vendor": "medium", "academic": "high", "social_media": "low", "other": "medium",
    "archive_address": "medium", "not_documented": "low", "unknown": "low",
}


def _date(value):
    return sf.FieldValue(sf.DATE, value, "quote_step", "test")


def _typed(value):
    return sf.SourceTyping(sf.FieldValue(sf.SOURCE_TYPE, value, "classifier", "test"), typed_by="classifier")


def test_signed_map_is_read_from_r14():
    m = sf.signed_credibility_map()
    assert dict(m.cells) == EXPECTED_CELLS
    assert m.auto_keys == {sf.AUTO_OFFICIAL, sf.AUTO_ARCHIVE}
    assert m.missing_keys == {"not_documented", "unknown"}
    assert "credibility_map" in m.signed_by and sf.SIGNED_CODEBOOK_SHA256 in m.signed_by


@pytest.mark.parametrize("code", ["news_major", "news_trade", "vendor", "academic", "policy_org",
                                  "social_media", "procurement_tender", "other"])
def test_every_answer_code_cell(code):
    fv = sf.source_credibility(_typed(code), _date("2024"))
    assert fv.value == EXPECTED_CELLS[code] and fv.coder == "derived"


@pytest.mark.parametrize(("basis", "expected"), [(sf.AUTO_OFFICIAL, "high"), (sf.AUTO_ARCHIVE, "medium")])
def test_auto_key_cells(basis, expected):
    assert sf.source_credibility(sf.auto_source_type(basis), _date("2024-03-12")).value == expected


@pytest.mark.parametrize("missing", ["not_documented", "unknown"])
def test_missing_source_type_is_low(missing):
    # 5f: source_type missing (not_documented, unknown) -> low
    assert sf.source_credibility(_typed(missing), _date("2024")).value == "low"


@pytest.mark.parametrize("dv", ["unknown", "not_documented"])
@pytest.mark.parametrize("basis", [sf.AUTO_OFFICIAL, "academic", "procurement_tender"])
def test_unknown_or_undated_date_makes_credibility_low(dv, basis):
    # rules/0 (C6 a): "plus `low` when `source_publication_date` = unknown or not_documented"
    t = sf.auto_source_type(basis) if basis == sf.AUTO_OFFICIAL else _typed(basis)
    fv = sf.source_credibility(t, _date(dv))
    assert fv.value == "low" and dv in fv.basis


def test_readability_not_asked_has_no_cell():
    t = sf.SourceTyping(sf.FieldValue(sf.SOURCE_TYPE, "not_asked", "classifier", "test",
                                      rule_name="readability_failure:binary"), typed_by="readability")
    with pytest.raises(sf.UnruledError):
        sf.source_credibility(t, _date("2024"))


def test_other_date_missing_token_refused():
    with pytest.raises(sf.UnruledError):
        sf.source_credibility(_typed("vendor"), _date("not_asked"))


def test_bad_cell_value_refused():
    bad = sf.CredibilityMap({"vendor": "excellent"}, "test-only", frozenset(), frozenset())
    with pytest.raises(ValueError):
        sf.source_credibility(_typed("vendor"), _date("2024"), bad)


# ---------------------------------------------------------------------------
# Source confidence (r14 items/core.confidence/rules/1; C7 a; P10-P12)
# ---------------------------------------------------------------------------


def _check(item, value, prob=0.95, quote="Staff use a generative AI assistant", ent=("true", 0.95), rule=None):
    ev = CodeEvidence(item_id=item, value=value, chunk_id=P1, probability=prob, quote=quote, quote_chunk_id=P1,
                      entailment=None if ent is None else Entailment(*ent), rule_name=rule)
    return check_code(ev, SOURCES)


def supported():
    r = _check("core.page_verdict", "confirms_activity")
    assert r.support_status == "supported"
    return r


def no_quote():
    r = _check("core.source_type", "vendor", quote=None, ent=None)
    assert r.support_status == "downgraded_no_quote"
    return r


def not_stating():
    r = _check("core.source_type", "vendor", ent=("false", 0.9))
    assert r.support_status == "downgraded_quote_not_stating_value"
    return r


def low_conf():
    r = _check("core.source_type", "vendor", prob=0.5)
    assert r.support_status == "downgraded_low_confidence"
    return r


def not_required():
    r = _check("core.source_type", "not_documented", quote=None, ent=None)
    assert r.support_status == "not_required"
    return r


def set_by_rule():
    r = _check("core.source_type", "not_asked", quote=None, ent=None, rule="source_type_auto:official_domain")
    assert r.support_status == "set_by_rule"
    return r


@pytest.mark.parametrize("cred", ["high", "medium", "low"])
def test_all_checks_passed_keeps_credibility(cred):
    c = sf.source_confidence_rule("S1", cred, [supported(), supported()])
    assert c.value == cred and c.finished


@pytest.mark.parametrize("failed", [no_quote, not_stating, low_conf])
def test_one_failed_check_of_each_kind_is_low(failed):
    c = sf.source_confidence_rule("S1", "high", [supported(), failed()])
    assert c.value == "low" and len(c.failures) == 1


def test_neutral_exemptions_only_keep_credibility():
    assert sf.source_confidence_rule("S1", "medium", [not_required(), set_by_rule()]).value == "medium"
    assert sf.source_confidence_rule("S1", "high", [supported(), not_required(), set_by_rule()]).value == "high"


def test_pending_check_is_unfinished_never_a_grade():
    c = sf.source_confidence_rule("S1", "high", [supported(), sf.PendingCheck("core.source_type", "vendor", "X35")])
    assert c.value == sf.UNFINISHED and not c.finished and c.pending
    with pytest.raises(sf.UnfinishedConfidenceError):
        sf.confidence_field(c)
    with pytest.raises(sf.UnfinishedConfidenceError):
        sf.confidence_seam([c])


def test_failure_with_pending_is_low():
    # P10: failure + pending -> low
    c = sf.source_confidence_rule("S1", "high", [low_conf(), sf.PendingCheck("core.page_verdict", "x", "pending")])
    assert c.value == "low" and c.finished and c.failures and c.pending and "P10" in c.basis


@pytest.mark.parametrize("cred", [None, "unknown"])
def test_credibility_missing_without_failure_is_unknown(cred):
    assert sf.source_confidence_rule("S1", cred, [supported()]).value == "unknown"


@pytest.mark.parametrize("cred", [None, "unknown"])
def test_credibility_missing_with_failure_is_low(cred):
    assert sf.source_confidence_rule("S1", cred, [supported(), no_quote()]).value == "low"


def test_downgraded_final_value_still_counts_original_failure():
    r = low_conf()
    # T-024 replaced the value with `unknown`; the original substantive code failed
    assert r.value == "unknown" and r.original_value == "vendor"
    assert sf.source_confidence_rule("S1", "high", [r]).value == "low"


def test_tag_only_verdict_downgrade_counts():
    r = _check("core.page_verdict", "confirms_activity", prob=0.5)
    assert r.value == "confirms_activity" and r.support_status == "downgraded_low_confidence"
    assert sf.source_confidence_rule("S1", "high", [r]).value == "low"


def test_second_reason_is_a_failure_too():
    r = _check("core.source_type", "vendor", prob=0.5, ent=("false", 0.9))
    assert r.support_status_second_reason == "downgraded_low_confidence"
    assert sf.source_confidence_rule("S1", "high", [r]).value == "low"


def test_negative_verdict_downgraded_below_bar_is_low():
    # C7 a: "on any associated original code, including a `no` or negative value
    # downgraded below the 0.8 bar, makes it `low`"
    r = _check("core.page_verdict", "no_genai", prob=0.5, quote=None, ent=None)
    assert r.support_status == "downgraded_low_confidence"
    c = sf.source_confidence_rule("S1", "high", [supported(), r])
    assert c.value == "low" and c.failures == ("core.page_verdict=no_genai downgraded_low_confidence",)


def test_no_value_downgraded_below_bar_is_low():
    r = _check("core.permanent_pilot", "no", prob=0.5, quote=None, ent=None)
    assert r.original_value == "no" and r.support_status == "downgraded_low_confidence"
    assert sf.source_confidence_rule("S1", "medium", [r]).value == "low"


def test_c7a_failure_with_missing_credibility_is_low():
    r = _check("core.page_verdict", "no_genai", prob=0.5, quote=None, ent=None)
    assert sf.source_confidence_rule("S1", None, [r]).value == "low"


def test_no_records_refused_p11():
    with pytest.raises(ValueError, match="P11"):
        sf.source_confidence_rule("S1", "high", [])


def test_illegitimate_neutral_records_refused():
    good = supported()
    fake_nr = SupportResult(**{**good.__dict__, "support_status": "not_required"})
    with pytest.raises(ValueError):
        sf.source_confidence_rule("S1", "high", [fake_nr])
    fake_rule = SupportResult(**{**good.__dict__, "support_status": "set_by_rule", "support_rule_name": None})
    with pytest.raises(ValueError):
        sf.source_confidence_rule("S1", "high", [fake_rule])
    with pytest.raises(ValueError):
        sf.source_confidence_rule("S1", "high", [])
    with pytest.raises(ValueError):
        sf.source_confidence_rule("S1", "excellent", [good])


def test_seam_mapping_and_field():
    a = sf.source_confidence_rule("S1", "high", [supported()])
    b = sf.source_confidence_rule("S2", "medium", [supported(), no_quote()])
    assert sf.confidence_seam([a, b]) == {"S1": "high", "S2": "low"}
    f = sf.confidence_field(a)
    assert f.item_id == "core.confidence" and f.coder == "derived" and "rules/1" in f.basis


def test_seam_emits_unknown():
    u = sf.source_confidence_rule("S3", "unknown", [supported()])
    h = sf.source_confidence_rule("S4", "high", [supported()])
    assert sf.confidence_seam([u, h]) == {"S3": "unknown", "S4": "high"}
    assert sf.confidence_field(u).value == "unknown"


# ---------------------------------------------------------------------------
# C8 b aggregation value (helper for T-026)
# ---------------------------------------------------------------------------


def test_aggregation_rule_read_from_codebook(vocab):
    path, text = vocab.aggregation_rule
    assert path == "items/core.confidence/rules/2"
    assert text == ("At consolidation, when an activity's confidence is aggregated from its sources, "
                    "a source whose confidence is `unknown` counts as `low`.")
    assert dict(vocab.aggregation_map) == {"unknown": "low"}


@pytest.mark.parametrize(("value", "expected"), [("unknown", "low"), ("high", "high"), ("medium", "medium"),
                                                 ("low", "low")])
def test_aggregation_value(value, expected):
    assert sf.aggregation_value(value) == expected


def test_aggregation_value_of_scored_source():
    u = sf.source_confidence_rule("S3", None, [supported()])
    assert u.value == "unknown" and sf.aggregation_value(u) == "low"


def test_aggregation_value_refuses_unfinished_and_junk():
    c = sf.source_confidence_rule("S1", "high", [sf.PendingCheck("core.source_type", "vendor", "X35")])
    with pytest.raises(sf.UnfinishedConfidenceError):
        sf.aggregation_value(c)
    with pytest.raises(sf.UnfinishedConfidenceError):
        sf.aggregation_value(sf.UNFINISHED)
    with pytest.raises(ValueError):
        sf.aggregation_value("not_documented")


# ---------------------------------------------------------------------------
# Row assembly
# ---------------------------------------------------------------------------


def test_source_values_and_missing_items():
    fields = [sf.source_url("https://x.example/"), sf.source_title("T", None)]
    assert sf.source_values(fields) == {"core.source_url": "https://x.example/", "core.source_title": "T"}
    missing = sf.missing_source_items(fields)
    assert "core.source_credibility (derived)" in missing and "core.source_url (mechanical)" not in missing
    with pytest.raises(ValueError):
        sf.source_values([sf.source_url("https://x.example/")] * 2)
