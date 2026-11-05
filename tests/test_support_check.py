"""T-024 self-checks: support check, downgrade and deterministic extraction.

Synthetic pages only; no provider call. Rules as SPEC v001.20 / codebook r13 state them
(R-041, R-042, R-043, R-044, R-081; RC-D-010, RC-D-011, RC-D-014 S1, RC-D-017).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from g3o.codebook.loader import load_codebook
from g3o.common import support_check as sc
from g3o.common.page_chunks import chunk_page
from g3o.common.support_check import (
    LOW_CONFIDENCE,
    NO_QUOTE,
    NOT_REQUIRED,
    NOT_STATING,
    SET_BY_RULE,
    SUPPORTED,
    CodeEvidence,
    Entailment,
    PageSources,
    SupportGateError,
    check_code,
    match_quote,
)

REPO = Path(__file__).resolve().parents[1]

TEXT = (
    "Town of Example. The council launched the CivicBot chatbot pilot for residents in March 2024. "
    "CivicBot answered 12,000 questions in its first month and cut waiting times by half. "
    "Separately, the council adopted a policy on staff use of generative AI tools."
)
P = "P1#p001"
SRC = PageSources("P1", {P: TEXT}, chrome_text="Contact: Digital Office, digital@example.gov")
QUOTE = "The council launched the CivicBot chatbot pilot for residents"
YES = Entailment("true", 0.95)


def ev(item="core.activity_type", value="pilot_experiment", p=0.9, quote=QUOTE, ent=YES, **kw):
    return CodeEvidence(item_id=item, value=value, chunk_id=kw.pop("chunk_id", P), probability=p,
                        quote=quote, entailment=ent, **kw)


# ---------------------------------------------------------------------------
# Pins and parity with the T-003 calibration
# ---------------------------------------------------------------------------


def test_signed_codebook_and_pins():
    cb = load_codebook()
    assert cb.sha256 == sc.SIGNED_CODEBOOK_SHA256
    assert (sc.MATCH_METRIC, sc.MATCH_THRESHOLD, sc.PINNED_RAPIDFUZZ) == ("token_set_ratio_norm", 93, "3.14.3")
    assert sc.WORD_RULE_CUTOFF == 0.80 and sc.QUOTE_MAX_CHARS == 200
    assert '"rapidfuzz==3.14.3"' in (REPO / "pyproject.toml").read_text(encoding="utf-8")
    import rapidfuzz
    assert rapidfuzz.__version__ == sc.PINNED_RAPIDFUZZ
    rules = sc.default_rules()
    assert rules.bar("core.activity_type") == 0.8 and rules.entailment_bar == 0.8
    assert rules.not_required_values == {"not_documented", "unknown", "no", "none_reported", "none_documented",
                                         "none", "unclear", "unresolved", "not_an_activity"}
    assert rules.rule_values == {"not_asked", "_NA_"}
    assert rules.negative_verdicts == {"confirms_absence", "no_genai", "background_only", "event_only",
                                       "other_body"}


def test_other_codebook_refused():
    cb = load_codebook()
    cb.sha256 = "0" * 64
    with pytest.raises(ValueError, match="not the signed r13"):
        sc.rules_from_codebook(cb)


def test_cap_constants_match_extract_modules():
    from g3o.extract import parser_v27, request_v27
    assert request_v27.QUOTE_MAX_CHARS == sc.QUOTE_MAX_CHARS
    assert parser_v27.OVER_CAP_FLAG == sc.OVER_CAP_FLAG


def _spike(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / "spikes" / "t003" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SAMPLES = [
    "The Council's GenAI pilot — launched in 2024 (phase 1)!",
    "ＦＵＬＬ-width Ｔｅｘｔ and Straße",
    "市政府于2024年推出生成式人工智能试点。",
    "กรุงเทพมหานครเปิดตัวโครงการนำร่อง AI สร้างสรรค์",
    "l’administration a lancé l'outil",
]


@pytest.mark.parametrize("s", SAMPLES)
def test_normalization_is_the_calibrations(s):
    wp = _spike("word_presence")
    assert sc.word_tokens(s) == wp.word_tokens(s)
    assert sc.norm_text(s) == " ".join(wp.word_tokens(s))
    assert sc.word_presence(s, TEXT + s) == wp.presence(wp.word_tokens(s), wp.word_tokens(TEXT + s))


# ---------------------------------------------------------------------------
# R-042 match (both rules) and the 200-character cap
# ---------------------------------------------------------------------------


def test_verbatim_and_trimmed_quotes_match():
    m = match_quote(QUOTE, TEXT)
    assert m.matched and m.score == 100 and m.rule_80 and m.presence_word == 1.0
    # removal for conciseness keeps the match (RC-D-014 S1)
    assert match_quote("The council launched the CivicBot pilot", TEXT).matched


def test_off_page_quote_fails_both_rules():
    m = match_quote("The ministry deployed a translation model for border officers", TEXT)
    assert not m.matched and m.rule_80 is False and m.score < sc.MATCH_THRESHOLD


def test_quote_with_no_words_does_not_match():
    m = match_quote(" -- !! ", TEXT)
    assert not m.matched and m.presence_word is None and m.rule_80 is None


def test_threshold_is_inclusive_at_93(monkeypatch):
    for score, expected in ((93, True), (92.99, False)):
        monkeypatch.setattr(sc, "_token_set_ratio", lambda s=score: lambda a, b: s)
        m = match_quote("anything", TEXT)  # word rule fails: only the matcher can decide
        assert m.matcher_pass is expected and m.matched is expected


def test_either_rule_matches_and_the_deciding_rule_is_recorded(monkeypatch):
    """RC-D-019 E1 c: matcher OR 80% word rule; both results kept."""
    assert sc.MATCH_DECISION == "either"
    assert match_quote(QUOTE, TEXT).decided_by == sc.BOTH
    monkeypatch.setattr(sc, "_token_set_ratio", lambda: lambda a, b: 95)
    m = match_quote("words that are absent entirely", TEXT)
    assert (m.matched, m.matcher_pass, m.rule_80, m.decided_by) == (True, True, False, sc.MATCHER)
    monkeypatch.setattr(sc, "_token_set_ratio", lambda: lambda a, b: 50)
    m = match_quote("CivicBot answered questions council", TEXT)
    assert (m.matched, m.matcher_pass, m.rule_80, m.decided_by) == (True, False, True, sc.WORD_RULE)
    m = match_quote("The ministry deployed a translation model", TEXT)
    assert (m.matched, m.decided_by) == (False, None)


def test_word_rule_alone_supports_a_code(monkeypatch):
    monkeypatch.setattr(sc, "_token_set_ratio", lambda: lambda a, b: 10)
    r = check_code(ev(quote="CivicBot answered questions council pilot"), SRC)
    assert r.support_status == SUPPORTED and r.match.decided_by == sc.WORD_RULE


def test_entailment_window_200_each_side_clipped_to_part():
    pre, post = "a" * 300, "b" * 300
    text = pre + QUOTE + post
    win, located = sc.entailment_window(QUOTE, text)
    assert located and win == "a" * 200 + QUOTE + "b" * 200
    win, located = sc.entailment_window(QUOTE, "x" * 50 + QUOTE + "y" * 10)
    assert located and win == "x" * 50 + QUOTE + "y" * 10
    # case/whitespace variants are located; a quote none of whose words is in the text is the state alone
    win, located = sc.entailment_window("the  COUNCIL launched", TEXT)
    assert located and "Town of Example" in win
    assert sc.entailment_window("mayor robot", TEXT) == ("mayor robot", False)
    assert sc.ENTAILMENT_WINDOW_CHARS == 200


def test_entailment_window_quote_with_words_left_out():
    """E3 ruling (b): passage from the first to the last matched quote word, widened 200 each side."""
    pre, post = "a" * 300 + " ", " " + "b" * 300
    passage = "The council launched the CivicBot chatbot pilot for residents"
    text = pre + passage + post
    trimmed = "The council launched the CivicBot pilot for residents"  # "chatbot" left out
    assert text.find(trimmed) == -1 and sc.match_quote(trimmed, text).matched
    win, located = sc.entailment_window(trimmed, text)
    lo = text.index(passage)
    assert located and win == text[lo - 200:lo + len(passage) + 200]
    # punctuation dropped by the extractor (lane B probe p04 D)
    page = "x" * 250 + " The council, after review, launched CivicBot in 2024. " + "y" * 250
    win, located = sc.entailment_window("The council after review launched CivicBot in 2024", page)
    s, e = page.index("The council"), page.index("2024.") + 4
    assert located and win == page[s - 200:e + 200]
    # clipped to the source text
    win, located = sc.entailment_window("council CivicBot", TEXT)
    assert located and win == TEXT[:TEXT.index("CivicBot") + len("CivicBot") + 200]


def test_entailment_window_word_alignment_prefers_most_words_then_shortest():
    filler = " ".join(["filler"] * 60)
    text = ("the pilot started. " + filler + " The council launched CivicBot widely, the pilot. "
            + filler + " council pilot")
    s = text.index("council launched")
    e = text.index("pilot.", s) + len("pilot")
    assert sc._locate_by_words("council launched CivicBot the pilot", text) == (s, e)
    # one shared word: the earliest occurrence, the shortest passage
    assert sc._locate_by_words("pilot", text) == (4, 9)
    assert sc._locate_by_words("no such words", text) is None


def test_entailment_window_uses_the_producing_part_or_chrome():
    src, chunks = chunked()
    last = chunks[-1].chunk_id
    q = "the council launched the CivicBot chatbot pilot"
    win, located = sc.entailment_window_for(ev(quote=q, chunk_id=last), src)
    assert located and win in chunks[-1].text
    win, _ = sc.entailment_window_for(ev(item="core.content_contact_named", value="yes",
                                         quote="Digital Office", quote_chunk_id="P1#chrome"), SRC)
    assert win == SRC.chrome_text
    with pytest.raises(ValueError, match="may not supply"):
        sc.entailment_window_for(ev(quote=q, quote_chunk_id="P1#chrome"), SRC)


def test_over_cap_quote_kept_whole_and_flagged():
    long_quote = TEXT[:250]
    assert len(long_quote) > 200
    r = check_code(ev(quote=long_quote), SRC)
    assert r.support_status == SUPPORTED and r.supporting_text == long_quote
    assert sc.OVER_CAP_FLAG in r.flags and r.match.over_cap
    at_cap = check_code(ev(quote=TEXT[:200]), SRC)
    assert sc.OVER_CAP_FLAG not in at_cap.flags


def test_display_cap():
    assert sc.display_cap("short") == ("short", False)
    shown, marker = sc.display_cap("x" * 201)
    assert shown == "x" * 200 and marker


# ---------------------------------------------------------------------------
# R-041 statuses and downgrades
# ---------------------------------------------------------------------------


def test_supported_positive_code():
    r = check_code(ev(), SRC)
    assert (r.support_status, r.value, r.support_status_second_reason, r.support_rule_name) == (
        SUPPORTED, "pilot_experiment", None, None)
    assert not r.downgraded and r.quote_chunk_id == P


def test_no_quote_downgrades_to_unknown():
    for quote in (None, "", "   "):
        r = check_code(ev(quote=quote, ent=None), SRC)
        assert (r.support_status, r.value, r.original_value) == (NO_QUOTE, "unknown", "pilot_experiment")
        assert r.supporting_text is None


def test_quote_below_threshold_counts_as_no_quote():
    r = check_code(ev(quote="The ministry deployed a translation model for border officers", ent=None), SRC)
    assert r.support_status == NO_QUOTE and r.value == "unknown" and r.match is not None


def test_low_confidence_positive_downgrades():
    r = check_code(ev(p=0.79), SRC)
    assert (r.support_status, r.value, r.support_status_second_reason) == (LOW_CONFIDENCE, "unknown", None)


def test_two_reasons_quote_first_then_bar():
    r = check_code(ev(quote=None, ent=None, p=0.5), SRC)
    assert (r.support_status, r.support_status_second_reason) == (NO_QUOTE, LOW_CONFIDENCE)
    r = check_code(ev(ent=Entailment("false", 0.9), p=0.5), SRC)
    assert (r.support_status, r.support_status_second_reason) == (NOT_STATING, LOW_CONFIDENCE)


def test_entailment_false_or_unsure_fails_quote_check():
    for ent in (Entailment("false", 0.99), Entailment("true", 0.79)):
        r = check_code(ev(ent=ent), SRC)
        assert (r.support_status, r.value) == (NOT_STATING, "unknown")
    r = check_code(ev(ent=Entailment("true", None)), SRC)
    assert r.support_status == NOT_STATING and sc.ENTAILMENT_PROBABILITY_UNAVAILABLE in r.flags
    with pytest.raises(ValueError, match="true' or 'false"):
        check_code(ev(ent=Entailment("yes", 0.9)), SRC)


def test_matched_quote_without_entailment_answer_is_refused():
    with pytest.raises(ValueError, match="X35"):
        check_code(ev(ent=None), SRC)


def test_negative_codes_need_no_quote_but_meet_the_bar():
    r = check_code(ev(item="core.has_human_oversight", value="no", quote=None, ent=None, p=0.95), SRC)
    assert (r.support_status, r.value) == (NOT_REQUIRED, "no")
    # R-081: a negative code below 0.8 is downgraded too
    r = check_code(ev(item="core.has_human_oversight", value="no", quote=None, ent=None, p=0.6), SRC)
    assert (r.support_status, r.value, r.original_value) == (LOW_CONFIDENCE, "unknown", "no")
    r = check_code(ev(value="not_documented", quote=None, ent=None, p=0.6), SRC)
    assert (r.support_status, r.value) == (LOW_CONFIDENCE, "unknown")


def test_missing_probability_downgrades_and_is_recorded():
    r = check_code(ev(p=None), SRC)
    assert (r.support_status, r.value, r.original_value) == (LOW_CONFIDENCE, "unknown", "pilot_experiment")
    assert sc.PROBABILITY_UNAVAILABLE in r.flags and r.chosen_answer_probability is None


def test_page_verdict_is_never_rewritten():
    neg = check_code(ev(item="core.page_verdict", value="no_genai", quote=None, ent=None, p=0.5), SRC)
    assert (neg.support_status, neg.value) == (LOW_CONFIDENCE, "no_genai") and neg.downgraded
    ok = check_code(ev(item="core.page_verdict", value="background_only", quote=None, ent=None, p=0.9), SRC)
    assert (ok.support_status, ok.value) == (NOT_REQUIRED, "background_only")
    pos = check_code(ev(item="core.page_verdict", value="confirms_activity", quote=None, ent=None), SRC)
    assert (pos.support_status, pos.value) == (NO_QUOTE, "confirms_activity")


def test_rule_set_values():
    r = check_code(ev(value="not_asked", quote=None, ent=None, p=None,
                      rule_name="core.rule.applicability_table"), SRC)
    assert (r.support_status, r.support_rule_name, r.value) == (
        SET_BY_RULE, "core.rule.applicability_table", "not_asked")
    assert not r.flags  # a rule-set value is not a provider omission (RC-D-010)
    with pytest.raises(ValueError, match="rule name"):
        check_code(ev(value="_NA_", quote=None, ent=None), SRC)
    r = check_code(ev(item="core.content_data", value="no", quote=None, ent=None, p=None,
                      rule_name="non_genai_page_no"), SRC)
    assert r.support_status == SET_BY_RULE


def test_free_text_quote_step_field():
    r = check_code(ev(item="core.activity_name", value="CivicBot", p=None, ent=None,
                      quote="the CivicBot chatbot pilot", activity_id="P1#a001"), SRC)
    assert (r.support_status, r.value) == (SUPPORTED, "CivicBot") and not r.flags
    r = check_code(ev(item="core.activity_name", value="CivicBot", p=None, ent=None, quote=None), SRC)
    assert (r.support_status, r.value) == (NO_QUOTE, "unknown")


def test_temporary_answer_is_not_checked():
    with pytest.raises(ValueError, match="temporary"):
        check_code(ev(value=sc.default_rules().temporary_answer), SRC)


# ---------------------------------------------------------------------------
# R-044 chunked pages and chrome text (r2#48, RC-D-017 P3)
# ---------------------------------------------------------------------------


def chunked():
    text = ("Alpha section on staff training and the council budget. " * 40) + "\n\n" + \
           ("Beta section: the council launched the CivicBot chatbot pilot. " * 40)
    chunks = chunk_page("P2", text, limit_tokens=200)
    assert len(chunks) >= 2
    return PageSources("P2", {c.chunk_id: c.text for c in chunks}), chunks


def test_quote_is_matched_in_the_producing_part():
    src, chunks = chunked()
    first, last = chunks[0].chunk_id, chunks[-1].chunk_id
    q = "the council launched the CivicBot chatbot pilot"
    assert check_code(ev(quote=q, chunk_id=last), src).support_status == SUPPORTED
    # the same words exist elsewhere on the page, but not in the part that produced the code
    assert check_code(ev(quote=q, chunk_id=first, ent=None), src).support_status == NO_QUOTE
    # a quote copied from a different part does not count
    r = check_code(ev(quote=q, chunk_id=first, quote_chunk_id=last, ent=None), src)
    assert r.support_status == NO_QUOTE and r.match is None


def test_chrome_quote_only_for_main_plus_chrome_items():
    q = "Contact: Digital Office"
    r = check_code(ev(item="core.content_contact_named", value="yes", quote=q, quote_chunk_id="P1#chrome"), SRC)
    assert r.support_status == SUPPORTED and r.quote_chunk_id == "P1#chrome"
    r = check_code(ev(quote=q, quote_chunk_id="P1#chrome", ent=None), SRC)
    assert r.support_status == NO_QUOTE
    no_chrome = PageSources("P1", {P: TEXT})
    r = check_code(ev(item="core.content_contact_named", value="yes", quote=q, quote_chunk_id="P1#chrome",
                      ent=None), no_chrome)
    assert r.support_status == NO_QUOTE


def test_unknown_part_is_an_error():
    with pytest.raises(ValueError, match="unknown part"):
        check_code(ev(chunk_id="P1#p009"), SRC)


# ---------------------------------------------------------------------------
# Quotes from both passes, joined on task_id
# ---------------------------------------------------------------------------


def _ok(payload):
    from g3o.extract.anthropic_client import ExtractorResult
    return ExtractorResult("x27-test", True, json.dumps(payload), None, response_model="claude-haiku-5-5")


def test_pass1_and_pass2_quotes_are_checked():
    from g3o.extract import pass2_support as p2
    from g3o.extract.parser_v27 import parse_pass1_result
    from g3o.extract.request_v27 import PageCode, Pass1Page, select_requests

    page = Pass1Page(page_id="P1", institution_id="i", institution_name="Town of Example",
                     url="https://example.gov/x", title="t", text=TEXT, chunks=tuple(chunk_page("P1", TEXT)),
                     codes=(PageCode("core.source_type", P, "vendor"),),
                     verdict="confirms_activity", page_complete=None)
    plan1 = select_requests(page)
    item, task = "core.source_type", next(t for t in plan1.quote_tasks if t.item_id == "core.source_type")
    out1 = parse_pass1_result(_ok({"quotes": [{"task_id": task.task_id, "part_id": P, "quote": QUOTE}],
                                   "links": [], "activities": [], "publication_date": None}), page, plan1)
    q1 = sc.pass1_quotes(plan1, out1)[(item, P)]
    src = PageSources.from_page(page)
    r1 = check_code(CodeEvidence(item, "vendor", P, probability=0.9, quote=q1.quote,
                                 quote_chunk_id=q1.chunk_id, entailment=YES), src)
    assert r1.support_status == SUPPORTED

    act = p2.Pass2Activity("P1#a001", 0, TEXT.index(" Separately"), codes=(
        p2.ActivityCode("core.activity_type", P, "pilot_experiment"),))
    page2 = p2.Pass2Page(page, (act,))
    plan2 = p2.select_requests(page2)
    t2 = plan2.quote_tasks[0]
    out2 = p2.parse_pass2_result(_ok({"quotes": [{"task_id": t2.task_id, "part_id": P,
                                                  "quote": "[[A1]]The council launched the CivicBot chatbot pilot"}],
                                      "fields": []}), page2, plan2)
    q2 = sc.pass2_quotes(plan2, out2)[("P1#a001", "core.activity_type", P, "pilot_experiment")]
    r2 = check_code(CodeEvidence("core.activity_type", "pilot_experiment", P, probability=0.85,
                                 quote=q2.quote, quote_chunk_id=q2.chunk_id, entailment=YES,
                                 activity_id="P1#a001"), src)
    assert r2.support_status == SUPPORTED and r2.activity_id == "P1#a001"


# ---------------------------------------------------------------------------
# X35 question labels
# ---------------------------------------------------------------------------


def test_entailment_question_forms():
    q = sc.entailment_question("core.activity_type", "pilot_experiment", activity_name="CivicBot")
    assert q == 'Does this text state or clearly show that the kind of activity of the activity "CivicBot" ' \
                'is "a pilot or trial"?'
    q = sc.entailment_question("core.page_verdict", "confirms_activity")
    assert q.startswith("Does this text state or clearly show that the generative-AI content of the page is")
    q = sc.entailment_question("core.year_pilot_start", "2024", activity_name="CivicBot")
    assert q.endswith('is "2024"?')
    # codebook r13: four ASCII digits after conversion (lane B F4)
    for bad in ("\uff12\uff10\uff12\uff14", "\u0e52\u0e50\u0e52\u0e54", "FY24", "24", "\u0662\u0660\u0662\u0664"):
        with pytest.raises(ValueError, match="four ASCII digits"):
            sc.entailment_question("core.year_pilot_start", bad, activity_name="CivicBot")
    role = sc.entailment_question("core.observed_actor_relationship", "beneficiary",
                                  part="searched_institution_role", activity_name="CivicBot")
    assert "named institution's part" in role
    with pytest.raises(ValueError, match="part explicitly"):
        sc.entailment_question("core.observed_actor_relationship", "beneficiary", activity_name="CivicBot")
    with pytest.raises(ValueError, match="no X35 label"):
        sc.entailment_question("core.activity_name", "CivicBot", activity_name="CivicBot")
    with pytest.raises(ValueError, match="value label"):
        sc.entailment_question("core.activity_type", "made_up", activity_name="CivicBot")


def test_entailment_call_is_gated():
    with pytest.raises(SupportGateError, match="jev binding"):
        sc.run_entailment()


# ---------------------------------------------------------------------------
# Deterministic extraction: contact e-mails, year candidates
# ---------------------------------------------------------------------------


def test_contact_emails_gate_closed():
    assert sc.extract_contact_emails("no", "write to a@example.gov") == "not_asked"


def test_contact_emails_all_surfaces_rcd011():
    emails = sc.extract_contact_emails(
        "yes", "Write to AI.Team@Example.gov or ai.team@example.gov.",
        header_text="Help: help+genai@example.gov", footer_text=None,
        email_links=("mailto:Press@Example.GOV?subject=Hi", "https://example.gov/contact"))
    assert emails == ["ai.team@example.gov", "help+genai@example.gov", "press@example.gov"]
    from g3o.common.storage import email_domain_counts
    assert email_domain_counts(emails) == [{"domain": "example.gov", "count": 3}]


def test_contact_emails_gate_open_none_found_is_not_documented():
    """RC-D-019 E2 a."""
    assert sc.extract_contact_emails("yes", "Call 555-0100.") == "not_documented"


def test_year_candidates_context_default_200_pending_w05():
    """RC-D-019 E4: 200 characters each side by default (W-05-P1: keep 200)."""
    assert sc.YEAR_CONTEXT_CHARS == 200
    far = "In 2019 the town was founded. " + "x" * 250 + " " + TEXT
    s0 = far.index("The council")
    assert [c.year for c in sc.activity_year_candidates(far, s0, s0 + 90)] == [2024]
    near = "In 2019 the town was founded. " + TEXT
    s1 = near.index("The council")
    assert [c.year for c in sc.activity_year_candidates(near, s1, s1 + 90)] == [2019, 2024]
    text = "Budget FY2024/25. " + TEXT
    start = text.index("The council")
    got = sc.activity_year_candidates(text, start, start + 90, context_chars=30)
    assert [c.year for c in got] == [2024, 2025]
    assert all(text[s.start:s.end] == s.text for c in got for s in c.sources)
    assert [c.year for c in sc.activity_year_candidates(text, start, start + 90, context_chars=0)] == [2024]


def test_year_candidates_read_on_whole_part_not_the_cut_slice():
    """W-05-P3: years are read on the whole part; sources overlapping the window are kept."""
    act = " The council launched CivicBot. "
    # a cut cannot create a year: "Ref 12024" with the window starting at the "2"
    text = "Ref 12024" + " " * 200 + act
    s = text.index("The council")
    lo = text.index("2024")
    got = sc.activity_year_candidates(text, s, s + 29, context_chars=s - lo)
    assert got == []
    # a cut cannot lose a year: "2010 to 2012" with the window starting at " to 2012"
    text = "Plan 2010 to 2012" + act
    s = text.index("The council")
    cut = text.index(" to 2012")
    got = sc.activity_year_candidates(text, s, s + 29, context_chars=s - cut)
    assert [c.year for c in got] == [2010, 2012]
    assert all(text[x.start:x.end] == x.text for c in got for x in c.sources)
    # a source wholly outside the window is not kept, even when the year also occurs inside it
    text = "In 2024 x" + "x" * 300 + act + "Launched 2024."
    s = text.index("The council")
    (c,) = sc.activity_year_candidates(text, s, s + 29)
    assert [x.start for x in c.sources] == [text.rindex("2024")]


def test_year_candidates_reference_year_passed_through():
    """B1 c: the two-digit pivot follows an explicit reference year; sources keep rule and reference year."""
    from dataclasses import fields

    from g3o.extract.years import YearSource, default_reference_year, extract_year_candidates

    text = "Budget FY60. " + TEXT
    start = text.index("The council")
    got_2026 = sc.activity_year_candidates(text, start, start + 90, context_chars=30, reference_year=2026)
    assert [c.year for c in got_2026] == [1960, 2024]  # 60 >= 26 + 25 -> 19xx
    got_2040 = sc.activity_year_candidates(text, start, start + 90, context_chars=30, reference_year=2040)
    assert [c.year for c in got_2040] == [2024, 2060]  # 60 < 40 + 25 -> 20xx
    assert {s.reference_year for c in got_2040 for s in c.sources} == {2040}
    assert all(s.rule for c in got_2040 for s in c.sources)
    assert all(text[s.start:s.end] == s.text for c in got_2040 for s in c.sources)
    # every field but the offsets matches a direct call on the same window
    lo = start - 30
    direct = extract_year_candidates(text[lo:start + 120], reference_year=2040)
    keep = [f.name for f in fields(YearSource) if f.name not in ("start", "end")]
    assert [[tuple(getattr(s, k) for k in keep) for s in c.sources] for c in got_2040] == \
        [[tuple(getattr(s, k) for k in keep) for s in c.sources] for c in direct]
    default = sc.activity_year_candidates(text, start, start + 90, context_chars=30)
    assert {s.reference_year for c in default for s in c.sources} == {default_reference_year()}
