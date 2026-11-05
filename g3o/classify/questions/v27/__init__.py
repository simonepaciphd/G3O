"""v2.7 jev question sets (T-011): pass 1 (page), pass 2 (activity), Stage 6 (institution).

The sets are JSON files beside this module, built from the signed codebook by
``python -m g3o.classify.questions.v27 build`` and checked by ``... check``.
Strings the codebook does not hold (state fields, span marker, dynamic year
choice text, Stage 6 record fields) are declared with the PI's wording-packet
ruling (RC-D-014 S3 b), or ``approval: "pending"`` with the slot's open points;
do not merge while any is pending.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from functools import cache
from typing import Any

from g3o.classify.questions.v27.build import (
    JEV_QUESTION_SET_VERSION,
    SET_DIR,
    SET_FILES,
    SIGNED_CODEBOOK_SHA256,
)


@cache
def load_set(name: str) -> dict[str, Any]:
    """One set document (``page``, ``activity`` or ``institution``)."""
    doc = json.loads((SET_DIR / SET_FILES[name]).read_text(encoding="utf-8"))
    if doc["question_set_version"] != JEV_QUESTION_SET_VERSION:
        raise ValueError(f"{name}: question-set version {doc['question_set_version']!r}")
    if doc["codebook_sha256"] != SIGNED_CODEBOOK_SHA256:
        raise ValueError(f"{name}: codebook hash {doc['codebook_sha256']!r}")
    return doc


def choice_request(question: dict[str, Any], *, part: bool = False,
                   years: Iterable[int | str] | None = None) -> dict[str, Any]:
    """``{instructions, criteria}`` for one jev Choice, in the T-016 re-pilot form.

    ``criteria`` maps each code to its signed text, in codebook order. With
    ``part`` (a long page's part) the temporary answer "not covered by this
    part" is added last. For a dynamic-year question, ``years`` are offered
    first, ascending, before the offered missing label(s). A year may be given as
    an int (``g3o.extract.years.YearCandidate.year``) or a digit string; its code
    is the year in four ASCII digits (declared ``candidate_code``). Its text is
    the year alone (declared ``candidate_text``; PI W-05 a).
    """
    criteria: dict[str, str] = {}
    if question.get("dynamic_choices") == "year":
        if years is None:
            raise ValueError(f"{question['question_id']}: year candidates required")
        codes = sorted({int(y) for y in years})  # int() also reads non-ASCII decimal digits
        if any(not 1000 <= y <= 9999 for y in codes):
            raise ValueError(f"{question['question_id']}: year candidates must be four-digit years")
        criteria.update({str(y): str(y) for y in codes})
    elif years is not None:
        raise ValueError(f"{question['question_id']}: not a dynamic-year question")
    criteria.update({c["code"]: c["text"] for c in question["criteria"]})
    if part:
        pa = question["part_prompt_answer"]
        criteria[pa["label"]] = pa["meaning"]
    return {"instructions": question["instructions"], "criteria": criteria}


__all__ = ["JEV_QUESTION_SET_VERSION", "SIGNED_CODEBOOK_SHA256", "choice_request", "load_set"]
