import importlib.util
import json
from pathlib import Path

import pytest

_P = Path(__file__).resolve().parents[1] / "scripts" / "spikes" / "t003" / "word_presence.py"
_spec = importlib.util.spec_from_file_location("word_presence", _P)
wp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wp)

PAGE = "The council adopted an AI policy in 2025. Staff use ChatGPT for drafting minutes."


def test_verbatim_quote_is_full_presence():
    s = wp.score("Staff use ChatGPT for drafting minutes", PAGE, "latin")
    assert s["presence_word"] == 1.0 and s["rule_80"] is True


def test_removal_for_conciseness_still_matches():
    s = wp.score("council adopted AI policy", PAGE, "latin")
    assert s["rule_80"] is True


def test_light_reformulation_at_boundary():
    # 4 of 5 words present = 0.8, which meets the rule
    s = wp.score("staff use ChatGPT for writing", PAGE, "latin")
    assert s["presence_word"] == 0.8 and s["rule_80"] is True


def test_fabricated_quote_fails():
    s = wp.score("the mayor banned generative tools entirely", PAGE, "latin")
    assert s["rule_80"] is False


def test_case_and_width_are_normalized():
    assert wp.score("ＳＴＡＦＦ USE chatgpt", PAGE, "latin")["presence_word"] == 1.0


def test_cjk_defaults_to_word_unit():
    page = "本市は 生成AIの利用方針 を策定した。"
    s = wp.score("生成AIの利用方針", page, "cjk")
    assert s["primary_unit"] == "word" and s["rule_80"] is True


def test_cjk_char_unit_when_chosen():
    page = "本市は生成AIの利用方針を策定した。"
    assert wp.score("生成AIの利用方針", page, "cjk", nonspaced_unit="char")["rule_80"] is True
    assert wp.score("量子計算機を導入", page, "cjk", nonspaced_unit="char")["rule_80"] is False


def test_thai_word_unit_when_chosen():
    s = wp.score("ปัญญาประดิษฐ์", "หน่วยงานใช้ ปัญญาประดิษฐ์ ในการบริการ", "thai", nonspaced_unit="word")
    assert s["primary_unit"] == "word" and s["rule_80"] is True


def test_empty_quote_is_none():
    s = wp.score("  ...  ", PAGE, "latin")
    assert s["presence_word"] is None and s["rule_80"] is None


def test_run_on_synthetic_recovery(tmp_path):
    pid = "RS-X:run:INST-1:abc"
    (tmp_path / "SOURCE-PAGES.jsonl").write_text(
        json.dumps({"page_id": pid, "source_record": {"text": PAGE}}) + "\n", encoding="utf-8")
    cands = [
        {"candidate_id": "c1", "script": "latin", "text_surface": "main",
         "saved_quote_record": {"page_id": pid, "quote": "council adopted an AI policy"}},
        {"candidate_id": "c2", "script": "latin", "text_surface": "main",
         "saved_quote_record": {"page_id": pid, "quote": "budget cuts to libraries announced"}},
    ]
    (tmp_path / "CANDIDATES.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cands), encoding="utf-8")
    out = tmp_path / "o.csv"
    summary = wp.run(tmp_path, out, 0.8)
    assert summary == {"candidates_scored": 2, "missing_page": 0, "threshold": 0.8,
                       "nonspaced_unit": "word", "institutions": {"tuning": 1, "holdout": 0},
                       "by_script": {"latin": {"n": 2, "rule_80_true": 1, "rule_80_blank": 0,
                                               "rule_80_word_true": 1}}}
    rows = out.read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("candidate_id,") and len(rows) == 3


@pytest.mark.parametrize("t", [0.5, 0.9])
def test_threshold_is_configurable(t):
    s = wp.score("staff use ChatGPT for writing", PAGE, "latin", t)
    assert s["rule_80"] is (0.8 >= t)


def test_partitions_grouped_stratified_and_seeded():
    cands = {f"L{i}": ["latin"] * 2 for i in range(10)}
    cands |= {"BIG": ["latin"] * 150, "C1": ["cjk"], "C2": ["cjk"], "T1": ["thai"]}
    a, b = wp.assign_partitions(cands), wp.assign_partitions(cands)
    assert a == b
    assert a["BIG"] == "tuning" and a["T1"] == "tuning"
    assert sum(a[f"L{i}"] == "holdout" for i in range(11) if f"L{i}" in a) == 2
    assert sorted([a["C1"], a["C2"]]) == ["holdout", "tuning"]


def test_thai_combining_marks_stay_inside_the_word():
    # U+0E31, U+0E34, U+0E4C are Mn; SARA AM (U+0E33) becomes NIKHAHIT (Mn) + SARA AA under NFKC.
    # Thai has no spaces between words and no segmenter is used, so the whole run is one token.
    toks = wp.word_tokens("การนำปัญญาประดิษฐ์")
    assert toks == [wp.normalize("การนำปัญญาประดิษฐ์")]
    assert wp.word_tokens("การนำปัญญาประดิษฐ์ (AI) และเทคโนโลยี") == [
        wp.normalize("การนำปัญญาประดิษฐ์"), "ai", wp.normalize("และเทคโนโลยี")]


def test_marks_do_not_change_latin_tokens():
    assert wp.word_tokens("Staff don't use naïve café") == ["staff", "don't", "use", "naïve", "café"]
