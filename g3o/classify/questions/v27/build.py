"""Build and check the v2.7 jev question sets (T-011).

Three sets, one JSON file each, beside this module:

- ``page.json``: pass 1, asked per page (or per part of a long page);
- ``activity.json``: pass 2, asked per (page x activity);
- ``institution.json``: Stage 6, the cross-page relation question (X30) and
  the pooled-evidence set (X31), which re-asks the pass-2 questions over the
  pooled quotes of a merged activity.

Every question string is taken from the T-013 generator output for the signed
codebook (``g3o.codebook.generators.gen_jev_questions``), regenerated here from
``codebook/codebook.yaml`` rather than copied by hand, so the text is the
signed text by construction. The checks below re-verify that, and that the CX
questions are byte-identical to the re-signed CX version (RC-D-002 row 39).

What the codebook does not hold is declared, never filled in silently: the
fields and order of each set's jev state, the activity-span marker, the text of
the dynamic year choices, and the Stage 6 record and quote fields. Each such
string is listed under ``non_verbatim`` with its wording-packet item id and
``approval: "pending"`` (RC-D-014 S3 b: approved by the PI in one packet before
the T-030 merge). Stage code (T-021, T-023, T-026) builds the states; this
module only declares them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.codebook.generators import GENERATED_DIR, gen_jev_questions
from g3o.codebook.loader import REPO_ROOT, Codebook, load_codebook

#: Version stamp for the three sets (pinned in goldens and stored with answers).
JEV_QUESTION_SET_VERSION = "g3o.classify.questions.v27.jev.1"

#: Codebook r12 candidate (RC-D-015 / RC-D-017; signed only when planning/t010/signoff-record.md
#: holds this sha256). A different codebook is refused.
SIGNED_CODEBOOK_SHA256 = "9b581163d6861640d4d011c2bc2ad2b9b6dabf5a1e915e044cf8983c93f59a53"

SET_DIR = Path(__file__).resolve().parent
SET_FILES = {"page": "page.json", "activity": "activity.json", "institution": "institution.json"}
BUILDER_ID = "g3o.classify.questions.v27.build"

EXTRACT_CONTRACT = f"{GENERATED_DIR}/extract_output_contract.md"
VALIDATE_CONTRACT = f"{GENERATED_DIR}/validate_output_contract.md"

#: Questions not in any T-011 set, with the reason (reported to the integrator).
EXCLUDED = {
    "core.support_entailment": (
        "pass none: the X35 quote check run between rounds by T-024 (RC-D-002 row 45); "
        "not a pass-1, pass-2 or Stage 6 question, and T-024 is not a T-011 consumer"
    ),
}

POOLED_ITEM = "core.pooled_activity_fields"
POOLED_INSTRUCTION_SLOT = f"items/{POOLED_ITEM}/instruction"
STAGE6_RELATION = "core.activity_relation_cross_page"

PENDING = "pending"  # PI wording approval, RC-D-014 S3 b

# --------------------------------------------------------------------------- state declarations
# Field names, order and markers the codebook does not pin (packet items W-01..W-08).
# Where the T-016 re-pilot (PI-ruled run, 2026-10-30) used a form, that form is declared;
# elsewhere the value is None until the PI rules.

PAGE_STATE = {
    "packet_items": ["W-01", "W-02"],
    "approval": PENDING,
    "form_source": "T-016 re-pilot state (scripts/spikes/t016/repilot_v27.py page_units)",
    "fields": [
        {"name": "coder_instructions", "value": "signed slot shared/system_prompt, verbatim"},
        {"name": "institution", "value": "institution name from the master"},
        {"name": "country", "value": "country from the master"},
        {"name": "level_of_government", "value": "level of government from the master"},
        {"name": "page_url", "value": "stored page URL"},
        {"name": "page_title", "value": "stored page title"},
        {"name": "page_part", "value": "chunk marker '{i} of {n}' (always present)"},
        {"name": "part_note", "value": "signed slot shared/part_prompt/sentence, only when n > 1"},
        {"name": "page_text", "value": "the part's main text"},
    ],
}

ACTIVITY_STATE = {
    "packet_items": ["W-01", "W-02", "W-03", "W-04", "W-06"],
    "approval": PENDING,
    "extends": "page state",
    "activity_fields": None,          # W-03: which extracted / earlier-round fields, by round
    "prior_answers_form": None,       # W-03: codes or plain-word labels
    "span_marker": None,              # W-04: open / close strings around each linked passage
    "span_note": None,                # W-04: whether a sentence explains the marker
    "scale_number_field": None,       # W-06: how core.deployment_scale_unit is shown the number
    "signed_constraints": [
        "DEC-010 a: jev pass 2 sees the page with the activity's span marked",
        # W-05-style declaration (wording packet, pending approval): summary of codebook r12
        # core.rule.cx_grain slot 2, sentence 3.
        "codebook core.rule.cx_grain slot 2: finding-field state = page text plus the finding's "
        "activity_name, activity_type, adoption_stage and tool_name; the state is pinned in the "
        "versioned question-set files and approved with the wording packet, and any change "
        "counts as a wording change",
        "combining convention activity_level: every part holding a linked passage votes",
    ],
}

DYNAMIC_YEAR_CHOICES = {
    "packet_items": ["W-05"],
    "approval": PENDING,
    # W-05 (wording packet, pending approval): pointer to the candidate rule, forms not enumerated.
    "candidates": "candidate years under codebook r12 rule 1, from the activity span and its context",
    "calendar_conversion": "fiscal-year candidates under codebook r12 rule 1, built by T-064",
    "order": "candidates ascending, then the item's offered missing label(s)",
    "candidate_code": "the year as written",
    "candidate_text": None,           # W-05: year only (T-016 form) / year + rules / PI sentence
    "rules_text_placement": None,     # W-05: where the item's rules_text goes
}

PAIR_STATE = {
    "packet_items": ["W-02", "W-07"],
    "approval": PENDING,
    "fields": [
        {"name": "coder_instructions", "value": "signed slot shared/system_prompt_stage6, verbatim"},
        {"name": "institution", "value": "institution name"},
        {"name": "country", "value": "country"},
        {"name": "first_record", "value": None},   # W-07: record fields
        {"name": "second_record", "value": None},  # W-07: record fields
    ],
}

POOLED_STATE = {
    "packet_items": ["W-02", "W-08"],
    "approval": PENDING,
    "instruction_slot": POOLED_INSTRUCTION_SLOT,
    "instruction_placement": None,    # W-08: state field or prefix to each question
    "quote_fields": None,             # W-08: per-quote fields (signed: source type and date)
    "pool_order": "source date, then position on the page (combining convention first_part)",
    "split_marker": None,             # W-08: marker when the pool is split into parts
}


# --------------------------------------------------------------------------- build
def _require_signed(cb: Codebook) -> None:
    if cb.sha256 != SIGNED_CODEBOOK_SHA256:
        raise ValueError(f"codebook sha256 {cb.sha256} is not the pinned r12 {SIGNED_CODEBOOK_SHA256}")


def _contract_section(q: dict[str, Any]) -> str:
    path = VALIDATE_CONTRACT if q["pass"] == "stage6" else EXTRACT_CONTRACT
    return f"{path} ## `{q['item_id']}`"


def _entry(q: dict[str, Any]) -> dict[str, Any]:
    e = {"question_id": q["question_id"], "contract_section": _contract_section(q)}
    e.update({k: v for k, v in q.items() if k != "question_id"})
    e["jev_type"] = "Choice"  # every item, incl. yes_no and multi (T-016 ruling 9 a: one Choice)
    if "computed_values" in q:
        e["dynamic_choices"] = "year"
    return e


def _by_round(qs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(qs, key=lambda q: q["round"] if isinstance(q["round"], int) else 99)  # stable


def _header(cb: Codebook, name: str) -> dict[str, Any]:
    return {
        "question_set": name,
        "question_set_version": JEV_QUESTION_SET_VERSION,
        "built_by": BUILDER_ID,
        "do_not_edit": True,
        "build_command": "python -m g3o.classify.questions.v27 build",
        "codebook_release": cb.label,
        "codebook_sha256": cb.sha256,
        "source": "g3o.codebook.generators.gen_jev_questions (regenerated from the codebook)",
    }


def _non_verbatim(*specs: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for s in specs:
        for item in s["packet_items"]:
            out.append({"packet_item": item, "approval": s["approval"]})
    seen, uniq = set(), []
    for x in out:
        if x["packet_item"] not in seen:
            seen.add(x["packet_item"])
            uniq.append(x)
    return sorted(uniq, key=lambda x: x["packet_item"])


def build_sets(cb: Codebook | None = None) -> dict[str, dict[str, Any]]:
    """The three set documents, built from the signed codebook."""
    cb = cb or load_codebook()
    _require_signed(cb)
    gen = json.loads(gen_jev_questions(cb).content)
    qs = [q for q in gen["questions"] if q["question_id"] not in EXCLUDED]
    page = _by_round([q for q in qs if q["pass"] == 1])
    activity = _by_round([q for q in qs if q["pass"] == 2])
    stage6 = _by_round([q for q in qs if q["pass"] == "stage6"])
    left = [q["question_id"] for q in qs if q not in page + activity + stage6]
    if left:
        raise ValueError(f"questions with no set: {left}")
    part_prompt = gen["part_prompt"]
    pooled_text = cb.resolve_text(POOLED_INSTRUCTION_SLOT)
    if pooled_text is None:
        raise ValueError(f"codebook lacks {POOLED_INSTRUCTION_SLOT}")

    docs = {
        "page": {
            **_header(cb, "page"),
            "pass": 1,
            "unit": "page (or one part of a long page)",
            "system_prompt_slot": "shared/system_prompt",
            "system_prompt": cb.resolve_text("shared/system_prompt"),
            "part_prompt": part_prompt,
            "state": PAGE_STATE,
            "non_verbatim": _non_verbatim(PAGE_STATE),
            "questions": [_entry(q) for q in page],
        },
        "activity": {
            **_header(cb, "activity"),
            "pass": 2,
            "unit": "page x activity, with the activity's span marked (DEC-010 a)",
            "system_prompt_slot": "shared/system_prompt",
            "system_prompt": cb.resolve_text("shared/system_prompt"),
            "part_prompt": part_prompt,
            "state": ACTIVITY_STATE,
            "dynamic_year_choices": DYNAMIC_YEAR_CHOICES,
            "non_verbatim": _non_verbatim(ACTIVITY_STATE, DYNAMIC_YEAR_CHOICES),
            "questions": [_entry(q) for q in activity],
        },
        "institution": {
            **_header(cb, "institution"),
            "pass": "stage6",
            "unit": "institution: activity pairs (X30) and pooled evidence per merged activity (X31)",
            "system_prompt_slot": "shared/system_prompt_stage6",
            "system_prompt": cb.resolve_text("shared/system_prompt_stage6"),
            "part_prompt": part_prompt,
            "relation": {"state": PAIR_STATE, "questions": [_entry(q) for q in stage6]},
            "pooled": {
                "item_id": POOLED_ITEM,
                "item_hash": cb.item_hash(POOLED_ITEM),
                "contract_section": f"{VALIDATE_CONTRACT} ## `{POOLED_ITEM}`",
                "instruction_slot": POOLED_INSTRUCTION_SLOT,
                "instruction": pooled_text,
                "membership": (
                    "every activity.json question (SPEC R-004: pass 2 = the Group D codes); "
                    "reported to the integrator for confirmation"
                ),
                "question_set": "activity",
                "question_ids": [q["question_id"] for q in activity],
                "state": POOLED_STATE,
            },
            "non_verbatim": _non_verbatim(PAIR_STATE, POOLED_STATE),
        },
    }
    docs["page"]["excluded"] = [{"question_id": k, "reason": v} for k, v in EXCLUDED.items()]
    return docs


def dump(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def write_sets(cb: Codebook | None = None, out_dir: Path = SET_DIR) -> list[Path]:
    paths = []
    for name, doc in build_sets(cb).items():
        p = out_dir / SET_FILES[name]
        p.write_bytes(dump(doc).encode("utf-8"))
        paths.append(p)
    return paths


# --------------------------------------------------------------------------- checks
def _all_questions(doc: dict[str, Any]) -> list[dict[str, Any]]:
    if "questions" in doc:
        return doc["questions"]
    return doc["relation"]["questions"]


def check_sets(cb: Codebook | None = None, set_dir: Path = SET_DIR) -> list[str]:
    """Self-checks of the T-011 card. Returns failures (empty = pass)."""
    cb = cb or load_codebook()
    errors: list[str] = []
    if cb.sha256 != SIGNED_CODEBOOK_SHA256:
        return [f"codebook sha256 {cb.sha256} is not the pinned r12"]
    gen = json.loads(gen_jev_questions(cb).content)
    signed = {q["question_id"]: q for q in gen["questions"]}

    # 0. the committed T-013 output is the same as the regenerated one
    committed = REPO_ROOT / GENERATED_DIR / "jev_questions.json"
    if committed.read_text(encoding="utf-8") != gen_jev_questions(cb).content:
        errors.append("committed g3o/codebook/generated/jev_questions.json differs from regeneration")

    # 1. the files on disk are exactly the build output
    built = build_sets(cb)
    docs = {}
    for name, fname in SET_FILES.items():
        p = set_dir / fname
        if not p.exists():
            errors.append(f"{fname} missing")
            continue
        text = p.read_text(encoding="utf-8")  # universal newlines: autocrlf checkouts
        if text != dump(built[name]):
            errors.append(f"{fname} differs from the build output (rebuild)")
        docs[name] = json.loads(text)
    if len(docs) != len(SET_FILES):
        return errors

    seen: list[str] = []
    for name, doc in docs.items():
        # 2. version stamp and codebook hash
        if doc.get("question_set_version") != JEV_QUESTION_SET_VERSION:
            errors.append(f"{name}: version stamp missing or wrong")
        if doc.get("codebook_sha256") != SIGNED_CODEBOOK_SHA256:
            errors.append(f"{name}: codebook hash wrong")
        rounds: dict[str, int] = {}
        last_round = 0
        for q in _all_questions(doc):
            qid = q["question_id"]
            seen.append(qid)
            s = signed.get(qid)
            if s is None:
                errors.append(f"{name}/{qid}: not a codebook question")
                continue
            # 3. citation: contract section, item id and hash
            if q.get("item_hash") != cb.item_hash(q["item_id"]):
                errors.append(f"{name}/{qid}: item hash does not match the codebook")
            path, _, heading = q.get("contract_section", "").partition(" ## ")
            contract = (REPO_ROOT / path).read_text(encoding="utf-8") if path else ""
            if f"\n## {heading}\n" not in contract:
                errors.append(f"{name}/{qid}: contract section {q.get('contract_section')!r} not found")
            # 4. verbatim: every text field equals the signed generator text
            for key in ("instructions", "criteria", "part_prompt_answer", "rules_text"):
                if q.get(key) != s.get(key):
                    errors.append(f"{name}/{qid}: {key} is not the signed text")
            # 5. CX questions byte-identical to the re-signed CX version (empty diff)
            if str(q.get("frozen_signature", "none")).startswith("CX-01.3"):
                ins = cb.instruction(q["item_id"])
                if "part" not in q and (ins is None or ins.text != q["instructions"]):
                    errors.append(f"{name}/{qid}: CX instruction differs from the signed item")
                for c in q["criteria"]:
                    d = cb.resolve_text(c["definition_slot"])
                    if d is None or not c["text"].startswith(d):
                        errors.append(f"{name}/{qid}: CX value {c['code']} differs from the signed item")
            # 6. order by round; a gating question comes in an earlier round
            r = q["round"] if isinstance(q["round"], int) else 0
            if r < last_round:
                errors.append(f"{name}/{qid}: out of round order")
            last_round = max(last_round, r)
            rounds[q["item_id"]] = min(rounds.get(q["item_id"], r), r)
            g = q.get("gate")
            if isinstance(g, dict) and g.get("item") in rounds and rounds[g["item"]] >= r:
                errors.append(f"{name}/{qid}: gate item {g['item']} is not in an earlier round")
        # 7. every non-verbatim declaration is pending or recorded as approved
        for nv in doc.get("non_verbatim", []):
            if nv.get("approval") not in (PENDING, "approved"):
                errors.append(f"{name}: non_verbatim {nv} has no approval state")
    # 8. every generated question is in exactly one set or excluded with a reason
    expected = set(signed) - set(EXCLUDED)
    if sorted(seen) != sorted(expected):
        errors.append(f"set membership mismatch: missing {sorted(expected - set(seen))}, "
                      f"extra {sorted(set(seen) - expected)}")
    if len(seen) != len(set(seen)):
        errors.append("a question appears in more than one set")
    pooled = docs["institution"]["pooled"]
    if pooled["instruction"] != cb.resolve_text(POOLED_INSTRUCTION_SLOT):
        errors.append("institution: pooled instruction is not the signed text")
    if pooled["question_ids"] != [q["question_id"] for q in docs["activity"]["questions"]]:
        errors.append("institution: pooled membership differs from the activity set")
    for name in ("page", "activity", "institution"):
        slot = docs[name]["system_prompt_slot"]
        if docs[name]["system_prompt"] != cb.resolve_text(slot):
            errors.append(f"{name}: system prompt is not the signed {slot}")
        if docs[name]["part_prompt"] != gen["part_prompt"]:
            errors.append(f"{name}: part prompt is not the signed text")
    return errors
