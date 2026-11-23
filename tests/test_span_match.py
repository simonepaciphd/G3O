"""The passage matcher of the v2.7 parser (``parser_v27._find`` / ``resolve_span``).

Two defects found on the C2 recording (PI ruling 2026-11-22, RULINGS-1122 item 15):

1. the matcher ignored Unicode form, so anchors copied in NFC were not found in a page stored in NFD;
2. the matcher was stricter than the quote check (R-042), so one miscopied word dropped the activity.

Every offset is checked against the ORIGINAL page text. All texts are made up.
"""

from __future__ import annotations

import random
import re
import unicodedata

import pytest

from g3o.common.page_chunks import chunk_page
from g3o.extract import parser_v27
from g3o.extract.request_v27 import Pass1Page


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def nfd(s: str) -> str:
    return unicodedata.normalize("NFD", s)


def canon(s: str) -> str:
    """NFKC with whitespace runs as one space: what a located passage is compared under."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def make_page(text: str, *, limit: int | None = None) -> Pass1Page:
    chunks = tuple(chunk_page("P1", text, limit_tokens=limit) if limit else chunk_page("P1", text))
    return Pass1Page(page_id="P1", institution_id="inst-1", institution_name="Town of Example",
                     url="https://example.gov/x", title="x", text=text, chunks=chunks, codes=(),
                     verdict="confirms_activity", page_complete=None)


# --- the matcher of 1f2451e, verbatim: the reference for "unchanged where it already matched" --------------------
def _old_ws_index(text: str) -> tuple[str, list[int]]:
    out: list[str] = []
    idx: list[int] = []
    prev_ws = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_ws:
                continue
            out.append(" ")
            idx.append(i)
            prev_ws = True
        else:
            out.append(ch)
            idx.append(i)
            prev_ws = False
    return "".join(out), idx


def _old_find(text: str, needle: str, lo: int, hi: int | None = None) -> tuple[int, int] | None:
    hi = len(text) if hi is None else hi
    i = text.find(needle, lo)
    if i != -1 and i < hi:
        return i, i + len(needle)
    collapsed, idx = _old_ws_index(text)
    n = re.sub(r"\s+", " ", needle.strip())
    if not n:
        return None
    start_c = next((k for k, o in enumerate(idx) if o >= lo), len(collapsed))
    j = collapsed.find(n, start_c)
    if j == -1 or idx[j] >= hi:
        return None
    return idx[j], idx[j + len(n) - 1] + 1


# ---------------------------------------------------------------------------
# Unchanged where the old matcher already found the anchor
# ---------------------------------------------------------------------------

_WORDS = ["the", "city", "council", "uses", "a", "chatbot", "für", "Bürger", nfd("für"), nfd("Bürger"),
          "trợ", "lý", "ảo", nfd("trợ"), nfd("lý"), "인공지능", nfd("인공지능"), "AI", "ai", "pilot,", "pilot",
          "2025", "and", "and", "the", "the"]
_GAPS = [" ", " ", " ", "  ", "\n", " \n ", "\t", " "]


def _random_text(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(_WORDS) + rng.choice(_GAPS) for _ in range(n))


@pytest.mark.parametrize("seed", range(40))
def test_result_is_unchanged_wherever_the_old_matcher_found_the_anchor(seed):
    rng = random.Random(seed)
    text = _random_text(rng, 60)
    for _ in range(60):
        a = rng.randrange(len(text))
        b = min(len(text), a + rng.randrange(1, 40))
        needle = text[a:b]
        if rng.random() < 0.4:  # the extractor's copy: whitespace runs rewritten
            needle = re.sub(r"\s+", lambda m: rng.choice([" ", "\n", "  "]), needle)
        lo = rng.randrange(len(text))
        hi = rng.choice([None, rng.randrange(lo, len(text) + 1)])
        old = _old_find(text, needle, lo, hi)
        if old is not None:
            for edge in ("start", "end"):
                assert parser_v27._find(text, needle, lo, hi, edge=edge) == old, (needle, lo, hi)


def test_exact_substring_returns_its_own_offsets():
    text = "Alpha. The office runs an AI assistant for residents. Omega."
    for a in range(len(text)):
        for b in range(a + 1, len(text) + 1):
            if text[a:b].strip():
                assert parser_v27._find(text, text[a:b], a) == (text.find(text[a:b], a), text.find(text[a:b], a) + b - a)


# ---------------------------------------------------------------------------
# Defect 1: Unicode form
# ---------------------------------------------------------------------------

# (name, passage). Each passage has at least one character whose NFC and NFD forms differ.
SCRIPTS = [
    ("vietnamese", "Công an tỉnh triển khai trợ lý ảo hỗ trợ người dân."),
    ("german", "Die Behörde führt einen KI-Assistenten für Bürgeranfragen ein."),
    ("korean", "시청은 인공지능 챗봇을 도입했습니다."),
    ("arabic", "أعلنت الوزارة إطلاق مساعد ذكي آلي لخدمة المواطنين."),
    ("bengali", "পৌরসভা একটি চ্যাটবট চালু করেছে, যা নাগরিকদের প্রশ্নের উত্তর দেবে ও সহায়তা করবো।"),
    ("devanagari", "नगर निगम ने नागरिकों के लिए एक चैटबॉट शुरू किया है, जो ज़रूरी सवालों के जवाब देता है।"),
]


@pytest.mark.parametrize("name,passage", SCRIPTS)
def test_script_samples_really_differ_between_forms(name, passage):
    # Devanagari nukta letters are composition exclusions: the stored (precomposed) text is the non-NFC one.
    stored = nfc(passage).replace("ज़", "ज़") if name == "devanagari" else nfd(passage)
    assert stored != nfc(passage)


@pytest.mark.parametrize("name,passage", SCRIPTS)
@pytest.mark.parametrize("text_form,needle_form", [("NFD", "NFC"), ("NFC", "NFD"), ("NFD", "NFD"), ("NFC", "NFC")])
def test_anchor_is_found_across_unicode_forms_with_original_offsets(name, passage, text_form, needle_form):
    form = {"NFC": nfc, "NFD": nfd}
    prefix, suffix = "Intro line about the office.\n", "\nClosing line."
    text = form[text_form](prefix) + form[text_form](passage) + form[text_form](suffix)
    want = (len(form[text_form](prefix)), len(form[text_form](prefix)) + len(form[text_form](passage)))
    got = parser_v27._find(text, form[needle_form](passage), 0)
    assert got == want
    assert canon(text[got[0]:got[1]]) == canon(passage)


def test_precomposed_devanagari_page_and_nfc_anchor():
    passage = nfc("नगर निगम ने ज़रूरी सवालों के लिए चैटबॉट शुरू किया।")
    stored = passage.replace("ज़", "ज़")  # one code point on the page, two in NFC
    assert stored != passage
    text = "पहली पंक्ति। " + stored + " अंतिम पंक्ति।"
    got = parser_v27._find(text, nfc(passage), 0)
    assert got == (len("पहली पंक्ति। "), len("पहली पंक्ति। ") + len(stored))
    assert text[got[0]:got[1]] == stored


def test_compatibility_forms_are_matched_as_the_quote_check_does():
    # The quote check normalises with NFKC: full-width letters and ligatures equal their plain forms.
    text = "Notice. The ＡＩ ofﬁce opened a pilot. End."
    got = parser_v27._find(text, "The AI office opened a pilot.", 0)
    assert got is not None and text[got[0]:got[1]] == "The ＡＩ ofﬁce opened a pilot."


def test_unicode_form_and_whitespace_differ_together():
    passage = "Công an tỉnh triển khai trợ lý ảo"
    stored = nfd("Công an tỉnh  triển khai\n trợ lý ảo")
    text = nfd("Mở đầu. ") + stored + nfd(" hỗ trợ người dân.")
    got = parser_v27._find(text, nfc(passage), 0)
    assert got == (len(nfd("Mở đầu. ")), len(nfd("Mở đầu. ")) + len(stored))
    assert canon(text[got[0]:got[1]]) == canon(passage)


def test_bounds_hold_on_the_unicode_form_path():
    passage = "trợ lý ảo của tỉnh"
    one = nfd("Mở đầu: " + passage + ". ")
    text = one + nfd("Lần hai: " + passage + ". Hết.")
    first = len(nfd("Mở đầu: "))
    second = len(one) + len(nfd("Lần hai: "))
    needle = nfc(passage)
    assert parser_v27._find(text, needle, 0) == (first, first + len(nfd(passage)))
    assert parser_v27._find(text, needle, first + 1) == (second, second + len(nfd(passage)))
    # the match must START before hi (it may run past it, as on the exact path)
    assert parser_v27._find(text, needle, 0, first) is None
    assert parser_v27._find(text, needle, 0, first + 1) == (first, first + len(nfd(passage)))
    assert parser_v27._find(text, needle, first + 1, second) is None
    assert parser_v27._find(text, needle, second + 1) is None


def test_lo_inside_a_decomposed_character_does_not_match_from_its_base():
    text = nfd("ảo thuật và trợ lý ảo")
    # lo = 1 points at the combining mark of the first letter: the first "ảo" starts before lo
    got = parser_v27._find(text, nfc("ảo"), 1)
    assert got is not None and got[0] >= 1 and canon(text[got[0]:got[1]]) == nfc("ảo")
    assert got[0] == len(nfd("ảo thuật và trợ lý "))


def test_a_match_never_starts_or_ends_inside_an_original_character():
    # "ﬁ" is one page character; an anchor that begins at its second letter names no page offset.
    text = "The ﬁnance office uses a drafting tool."
    assert parser_v27._find(text, "inance office", 0) is None
    assert parser_v27._find(text, "The f", 0) is None


def test_resolve_span_on_a_decomposed_page():
    passage = "Công an tỉnh triển khai trợ lý ảo dùng mô hình ngôn ngữ lớn để hỗ trợ người dân."
    text = nfd("Tin tức. ") + nfd(passage) + nfd(" Liên hệ: văn phòng.")
    page = make_page(text)
    s, e, status = parser_v27.resolve_span(page, "P1#p001", nfc("Công an tỉnh triển khai trợ lý ảo"),
                                           nfc("để hỗ trợ người dân."))
    assert status == "resolved"
    assert (s, e) == (len(nfd("Tin tức. ")), len(nfd("Tin tức. ")) + len(nfd(passage)))
    assert canon(text[s:e]) == canon(passage)


def test_resolve_span_offsets_are_whole_page_offsets_on_a_chunked_decomposed_page():
    filler = nfd("Câu mở đầu về hội đồng thành phố. " * 40)
    passage = "Thành phố đã triển khai trợ lý ảo cho cán bộ."
    text = filler + "\n\n" + nfd(passage) + " " + nfd("Câu kết về trí tuệ nhân tạo. " * 40)
    page = make_page(text, limit=150)
    part = next(c for c in page.chunks if nfd("trợ lý ảo") in c.text)
    assert part.start > 0
    s, e, status = parser_v27.resolve_span(page, part.chunk_id, nfc("Thành phố đã triển khai"),
                                           nfc("trợ lý ảo cho cán bộ."))
    assert status == "resolved" and s >= part.start
    assert text[s:e] == nfd(passage)


# ---------------------------------------------------------------------------
# Zero-width characters and soft hyphens: the quote check does not ignore them, so neither does the matcher
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hidden", ["­", "​", "‌", "‍", "﻿"])
def test_hidden_characters_inside_a_word_are_not_skipped(hidden):
    from g3o.common.support_check import word_tokens

    text = f"The office fights enve{hidden}lope wages with a new AI tool today."
    # the quote check's own words: the hidden character splits the word in two
    assert "envelope" not in word_tokens(text)
    assert parser_v27._find(text, "fights envelope wages", 0) is None
    assert parser_v27._find(text, "The office fights envelope wages with a new AI tool", 0) is None
    # an anchor copied with the hidden character is an exact match, as before
    assert parser_v27._find(text, f"fights enve{hidden}lope wages", 0) == (11, 11 + len(f"fights enve{hidden}lope wages"))


# ---------------------------------------------------------------------------
# Defect 2: no stricter than the quote check's word rule (R-042, 80% of the words), where the place is unique
# ---------------------------------------------------------------------------

PAGE = ("Morning notes. Some years ago the revenue board began its fight against undeclared wage with a "
        "local vendor's AI tools and called the result fruitful. A wider use of AI is not ruled out. Contact us.")
START = "Some years ago the revenue board began its fight against undeclared wage"
SLIP = "Some years ago the revenue board began its fight against undeclared wages"  # last word miscopied


def test_the_quote_check_accepts_the_miscopied_anchor():
    from g3o.common.support_check import WORD_RULE_CUTOFF, word_presence

    assert SLIP not in PAGE
    assert word_presence(SLIP, PAGE) >= WORD_RULE_CUTOFF


def test_one_miscopied_word_in_the_start_anchor_is_located_at_the_same_start():
    got = parser_v27._find(PAGE, SLIP, 0, edge="start")
    assert got is not None and got[0] == PAGE.index(START)
    assert PAGE[got[0]:got[1]] == START


def test_resolve_span_with_a_miscopied_word():
    s, e, status = parser_v27.resolve_span(make_page(PAGE), "P1#p001", SLIP, "and called the result fruitful.")
    assert status == "resolved"
    assert PAGE[s:e] == PAGE[PAGE.index("Some years"):PAGE.index("fruitful.") + len("fruitful.")]


def test_case_and_punctuation_differences_are_located_when_the_place_is_unique():
    got = parser_v27._find(PAGE, "some years ago, the Revenue Board began its fight", 0)
    assert got is not None and PAGE[got[0]:got[1]] == "Some years ago the revenue board began its fight"


@pytest.mark.parametrize("anchor,found", [
    ("ago the revenue boards", False),  # 3 of 4 words: under 80%
    ("years ago the revenue boards", True),  # 4 of 5
    ("Some years ago the revenue office began its struggle", False),  # 7 of 9
    ("Some years ago the revenue office began its struggle against", True),  # 8 of 10
    ("nothing like this is anywhere on that page", False),
])
def test_the_bar_is_the_quote_checks_eighty_percent(anchor, found):
    assert (parser_v27._find(PAGE, anchor, 0) is not None) is found


def test_the_offset_that_is_used_must_sit_on_a_matching_word():
    # start anchor: its first word fixes the span start; end anchor: its last word fixes the span end
    first_wrong = "Many years ago the revenue board began"
    last_wrong = "years ago the revenue board began his"
    assert parser_v27._find(PAGE, first_wrong, 0, edge="start") is None
    got = parser_v27._find(PAGE, first_wrong, 0, edge="end")
    assert got is not None and PAGE[:got[1]].endswith("revenue board began")
    assert parser_v27._find(PAGE, last_wrong, 0, edge="end") is None
    got = parser_v27._find(PAGE, last_wrong, 0, edge="start")
    assert got is not None and got[0] == PAGE.index("years ago")


def test_two_qualifying_places_are_refused():
    text = ("In 2024 the board began a pilot of AI tools for staff in the north office. "
            "In 2025 the board began a pilot of AI tools for staff in the south office.")
    slip = "the board began a pilot of AI tool for staff"  # "tool" for "tools": both sentences qualify
    assert parser_v27._find(text, slip, 0) is None
    # ... but the exact anchor still takes the first place at or after lo, as before
    exact = "the board began a pilot of AI tools for staff"
    assert parser_v27._find(text, exact, 0) == (text.index(exact), text.index(exact) + len(exact))
    # and one qualifying place inside the bounds is accepted
    second = text.index("In 2025")
    got = parser_v27._find(text, slip, second)
    assert got is not None and got[0] == text.index(exact, second)
    assert parser_v27._find(text, slip, 0, second) is not None
    assert parser_v27._find(text, slip, 0, 5) is None


def test_bounds_hold_on_the_word_path():
    at = PAGE.index(START)
    assert parser_v27._find(PAGE, SLIP, at) is not None
    assert parser_v27._find(PAGE, SLIP, at + 1) is None  # the place starts before lo
    assert parser_v27._find(PAGE, SLIP, 0, at) is None  # the place starts at hi
    assert parser_v27._find(PAGE, SLIP, 0, at + 1) is not None


def test_an_unresolved_end_stays_unresolved_and_empty_anchors_name_no_place():
    page = make_page(PAGE)
    assert parser_v27.resolve_span(page, "P1#p001", START, "words that are nowhere on it at all") == (
        None, None, "unresolved_end")
    assert parser_v27.resolve_span(page, "P1#p001", " ", "fruitful.") == (None, None, "unresolved_start")
    assert parser_v27.resolve_span(page, "P1#p001", "?!", "fruitful.") == (None, None, "unresolved_start")
    assert parser_v27._find(PAGE, "…", 0) is None


def test_a_miscopied_word_on_a_decomposed_page():
    passage = "Cách đây vài năm cơ quan thuế bắt đầu dùng trí tuệ nhân tạo để chống trốn thuế"
    text = nfd("Tin. ") + nfd(passage) + nfd(" và đánh giá tốt.")
    slip = nfc("Cách đây vài năm cơ quan thuế bắt đầu dùng trí tuệ nhân tạo để chống trốn thuê")
    got = parser_v27._find(text, slip, 0)
    assert got == (len(nfd("Tin. ")), len(nfd("Tin. ")) + len(nfd(passage)))


def test_page_words_are_the_quote_checks_words():
    # "㎏" is one page character and no letter; under NFKC it is "kg", and the quote check reads "5kg".
    from g3o.common.support_check import word_tokens

    text = "Note. 5㎏ of rice was handed out after the office AI tool sorted the list. End."
    assert "5kg" in word_tokens(text)
    slip = "5kg of rice was handed out after the office AI tools"  # last word miscopied
    got = parser_v27._find(text, slip, 0)
    assert got is not None and text[got[0]:got[1]] == "5㎏ of rice was handed out after the office AI tool"
