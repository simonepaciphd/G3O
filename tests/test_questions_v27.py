"""v2.7 jev question sets (T-011): built from the signed codebook, offline.

Covers the card's self-checks (CX diff empty, sets reproduce from the codebook,
version stamp, citations, round order) plus seeded faults so a check that
silently stops catching its fault fails here. No network, no API keys.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from g3o.classify.questions.v27 import (
    JEV_QUESTION_SET_VERSION,
    SIGNED_CODEBOOK_SHA256,
    choice_request,
    load_set,
)
from g3o.classify.questions.v27.build import (
    EXCLUDED,
    SET_DIR,
    SET_FILES,
    build_sets,
    check_sets,
)
from g3o.codebook.generators import gen_jev_questions
from g3o.codebook.loader import Codebook, load_codebook


@pytest.fixture(scope="module")
def cb() -> Codebook:
    return load_codebook()


@pytest.fixture(scope="module")
def signed(cb: Codebook) -> dict:
    return json.loads(gen_jev_questions(cb).content)


def _copy_sets(tmp_path: Path) -> Path:
    for f in SET_FILES.values():
        shutil.copy(SET_DIR / f, tmp_path / f)
    return tmp_path


def test_codebook_is_pinned_r12(cb: Codebook) -> None:
    assert cb.sha256 == SIGNED_CODEBOOK_SHA256


def test_committed_sets_pass_all_checks(cb: Codebook) -> None:
    assert check_sets(cb) == []


def test_sets_cover_every_question_once(signed: dict) -> None:
    ids = [q["question_id"] for n in ("page", "activity") for q in load_set(n)["questions"]]
    ids += [q["question_id"] for q in load_set("institution")["relation"]["questions"]]
    assert len(ids) == len(set(ids))
    assert set(ids) | set(EXCLUDED) == {q["question_id"] for q in signed["questions"]}
    assert (len(load_set("page")["questions"]), len(load_set("activity")["questions"])) == (8, 42)


def test_version_stamp_and_pending_wording() -> None:
    for name in SET_FILES:
        doc = load_set(name)
        assert doc["question_set_version"] == JEV_QUESTION_SET_VERSION
        assert doc["non_verbatim"], name
        assert all(nv["approval"] == "pending" for nv in doc["non_verbatim"])


def test_cx_questions_byte_identical(cb: Codebook) -> None:
    cx = [q for n in ("page", "activity") for q in load_set(n)["questions"]
          if q["frozen_signature"].startswith("CX-01.3")]
    assert len(cx) == 14
    for q in cx:
        assert q["instructions"] == cb.instruction(q["item_id"]).text
        for c in q["criteria"]:
            assert c["text"].startswith(cb.resolve_text(c["definition_slot"]))


def test_choice_request_forms() -> None:
    page = {q["question_id"]: q for q in load_set("page")["questions"]}
    r = choice_request(page["core.page_verdict"], part=True)
    assert list(r["criteria"])[-1] == "not covered by this part"
    assert "not_assessable" not in r["criteria"]
    act = {q["question_id"]: q for q in load_set("activity")["questions"]}
    y = choice_request(act["core.year_announced"], years=["2024", "2019", "2024"])
    assert list(y["criteria"]) == ["2019", "2024", "not_documented"]
    with pytest.raises(ValueError):
        choice_request(act["core.year_announced"])
    with pytest.raises(ValueError):
        choice_request(act["core.activity_type"], years=["2020"])


def test_year_choices_take_t064_candidates() -> None:
    """Codes are CE years in four ASCII digits, whatever form T-064 read them from."""
    from g3o.extract.years import extract_year_candidates

    act = {q["question_id"]: q for q in load_set("activity")["questions"]}
    arabic_2025 = "".join(chr(0x0660 + int(d)) for d in "2025")
    text = f"Piloted in FY24, extended 2019 - 2021, live {arabic_2025}."
    years = [c.year for c in extract_year_candidates(text)]
    assert years == [2019, 2021, 2024, 2025]
    y = choice_request(act["core.year_pilot_start"], years=years)
    assert list(y["criteria"]) == ["2019", "2021", "2024", "2025", "not_documented"]
    assert y["criteria"]["2024"] == "2024"
    fullwidth_2024 = "".join(chr(0xFF10 + int(d)) for d in "2024")
    mixed = choice_request(act["core.year_pilot_start"], years=["2024", 2024, fullwidth_2024])
    assert list(mixed["criteria"]) == ["2024", "not_documented"]
    with pytest.raises(ValueError):
        choice_request(act["core.year_pilot_start"], years=[24])
    decl = load_set("activity")["dynamic_year_choices"]
    assert decl["approval"] == "pending" and decl["candidate_text"] is None
    assert "g3o.extract.years.extract_year_candidates" in decl["candidate_source"]


@pytest.mark.parametrize("fault", ["text", "cx", "order", "version", "hash", "drop"])
def test_seeded_faults_are_caught(tmp_path: Path, cb: Codebook, fault: str) -> None:
    d = _copy_sets(tmp_path)
    name = "page"
    doc = json.loads((d / "page.json").read_text(encoding="utf-8"))
    qs = doc["questions"]
    if fault == "text":
        qs[0]["instructions"] += " "
    elif fault == "cx":
        cx = next(q for q in qs if q["frozen_signature"].startswith("CX-01.3"))
        cx["criteria"][0]["text"] = "x" + cx["criteria"][0]["text"]
    elif fault == "order":
        qs.reverse()
    elif fault == "version":
        doc["question_set_version"] = "v0"
    elif fault == "hash":
        qs[0]["item_hash"] = "0" * 64
    elif fault == "drop":
        qs.pop()
    (d / f"{name}.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                                    encoding="utf-8")
    assert check_sets(cb, d), fault


def test_build_is_deterministic(cb: Codebook) -> None:
    assert build_sets(cb) == build_sets(cb)
