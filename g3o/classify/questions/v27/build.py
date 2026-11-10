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
string is listed under ``non_verbatim`` with its wording-packet item id and its
``approval`` (RC-D-014 S3 b: approved by the PI in one packet before the T-030
merge): ``"approved"`` with the ruling record, or ``"pending"`` while a slot
lists an ``open`` point the rulings do not settle. Stage code (T-021, T-023, T-026) builds the states; this
module only declares them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.codebook.generators import (
    GENERATED_DIR,
    _criterion,
    _part_prompt,
    _question,
    gen_jev_questions,
)
from g3o.codebook.loader import REPO_ROOT, Codebook, load_codebook

#: Version stamp for the three sets (pinned in goldens and stored with answers).
JEV_QUESTION_SET_VERSION = "g3o.classify.questions.v27.jev.1"

#: Codebook r14 candidate (RC-D-025; signed only when planning/t010/signoff-record.md holds this sha256).
#: A different codebook is refused.
SIGNED_CODEBOOK_SHA256 = "3d6ce44a189d6ae5b533d97da503b56b3a3ec112c42a6e725dc346c0cd5d8ec1"

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
    "core.source_type": (
        "residual source_type is asked by T-015 (RC-D-002 O2), not by the v27 page set; "
        'PI 2026-11-08 chat "accept all" (2026-11-08 RULINGS.md item 2.2, lane B Q3 a; SPEC R-002 amended by the integrator)'
    ),
}

POOLED_ITEM = "core.pooled_activity_fields"
POOLED_INSTRUCTION_SLOT = f"items/{POOLED_ITEM}/instruction"
STAGE6_RELATION = "core.activity_relation_cross_page"

PENDING = "pending"  # PI wording approval, RC-D-014 S3 b
APPROVED = "approved"

#: PI rulings on the wording packet (agent-workspace 2026-11-07-v27-orch WORDING-PACKET.md;
#: verbatim replies in its RULINGS.md items 2-4). A slot is ``approved`` only when every
#: value it declares is entered; a slot with an open point stays ``pending`` and lists it.
PACKET_RULINGS = {
    "W-01": 'PI 2026-11-05 chat "w1a" (W-01 a: keep the re-pilot page layout)',
    "W-02": 'PI 2026-11-05 chat "w2a" (W-02 a: coder briefing and part sentence with the page material)',
    "W-03": 'PI 2026-11-05 chat "w3a" (W-03 a: name, tool, earlier answers as plain-word labels); '
            'PI chat "all recs accepted" (RULINGS.md item 4, to be recorded as RC-D-022): W3-1 a (field = codebook item name), W3-2 a (a missing earlier answer is left out); '
            'PI 2026-11-08 chat "accept all" (2026-11-08 RULINGS.md item 2.15): lane A 1 a role part searched_institution_role, 2 a multi-answer list of labels, 3 a activity.json question order',
    "W-04": 'PI 2026-11-05 chat "w4a" (W-04 a: markers only); strings [[Ak]]/[[/Ak]] (ruling 3 a)',
    "W-05": 'PI 2026-11-05 chat "w5a" (W-05 a: the year alone); W-05-P2 refresh accepted as procedural',
    "W-06": 'PI 2026-11-05 chat "w6a" (W-06 a: labelled field); label stated_number (ruling 3 a)',
    "W-07": 'PI 2026-11-05 chat "w7a" (W-07 a: full record); '
            'PI chat "all recs accepted" (RULINGS.md item 4, to be recorded as RC-D-022): W7 (i) a item names plus page_url, (ii) b plain-word labels, (iii) a supporting_quotes; '
            'PI 2026-11-08 chat "accept all" (2026-11-08 RULINGS.md item 2.10): lane A 4 a a missing record value is left out',
    "W-08": 'PI 2026-11-05 chat "w8a" (W-08 a: sentence as a field; quote, source type, date, address); '
            'PI chat "all recs accepted" (RULINGS.md item 4, to be recorded as RC-D-022): W8 (i)-(iv) a pool_note, quote_text, source_publication_date, page_part; '
            'PI 2026-11-08 chat "accept all" (2026-11-08 RULINGS.md item 2.11-12): lane A 5 a source_type as its signed label, 6 a no date = field left out',
    "B-Q4": 'PI 2026-11-07 recovery reply "1a": chrome_text verbatim then emails in the same chrome_text field; full chrome, not footer-only',
}

# --------------------------------------------------------------------------- state declarations
# Field names, order and markers the codebook does not pin (packet items W-01..W-08).
# Where the T-016 re-pilot (PI-ruled run, 2026-10-30) used a form, that form is declared and
# kept (W-01 a). A value still None is a point the PI rulings do not settle (see "open").

PAGE_STATE = {
    "packet_items": ["W-01", "W-02", "B-Q4"],
    "approval": APPROVED,
    "open": [],
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
        {"name": "chrome_text",                                               # PI recovery item 1a
         "value": "the page's chrome text, in the requests of core.content_contact_named and "
                  "core.content_contact_details only (codebook input_text main_plus_chrome; r2#48)",
         "shown_text": "stored chrome_text verbatim, followed by extracted emails; "
                       "the same full page chrome accompanies every part; omitted if not measured"},
    ],
}

ACTIVITY_STATE = {
    "packet_items": ["W-01", "W-02", "W-03", "W-04", "W-06"],
    "approval": APPROVED,
    "extends": "page state (its chrome field is not part of pass 2)",
    "activity_fields": [               # W-03 a
        {"name": "activity_name", "value": "the extracted activity name", "rounds": "every round"},
        {"name": "tool_name", "value": "the extracted tool name", "rounds": "every round"},
        {"name": "the codebook item name of the answer's item (the question's column, e.g. activity_type)",
         "value": "each answer to this activity from an earlier pass-2 round",
         "rounds": "every round after the answer's round"},                     # W3-1 a
    ],
    "prior_answers_form": "plain-word labels: each earlier-round answer as its value's entailment_label "
                          "(the labels signed for the quote check, codebook X35 label_rules; slots "
                          "items/<item>/values/<n>/entailment_label, generated in jev_questions.json "
                          "core.support_entailment labels), not its code; a year item's answer as the "
                          "calendar (CE) year in four ASCII digits (X35 label_rules)",
    "prior_missing_answer_form": "left out: an earlier-round answer not_documented, unknown, not_asked or _NA_ "
                                 "gives no field, so the coder is not shown it",  # W3-2 a
    "prior_answer_order": "the activity.json question order",                   # lane A 3 a
    "prior_answer_role_part_name": "searched_institution_role: the field of the second part of "
                                   "core.observed_actor_relationship (its codebook part name); the first "
                                   "part keeps observed_actor_relationship",          # lane A 1 a
    "prior_multi_answer_form": "a list of the chosen values' entailment_labels, in codebook value order "
                               "(core.governance_form, core.service_domain)",         # lane A 2 a
    "span_marker": {"open": "[[Ak]]", "close": "[[/Ak]]",
                    "k": "the activity id, e.g. [[A1]] ... [[/A1]] (as the P-2 extractor marks)",
                    "placement": "around each linked passage of the activity"},  # W-04 a, ruling 3 a
    "span_note": "none: no sentence explains the markers",                     # W-04 a
    "scale_number_field": {"name": "stated_number",
                           "value": "the extractor's exact number words"},     # W-06 a, ruling 3 a
    "signed_constraints": [
        "DEC-010 a: jev pass 2 sees the page with the activity's span marked",
        # W-05 declaration (RC-D-018 "3a"): summary of codebook r13 core.rule.cx_grain slot 2,
        # sentences 2 and 3 (unchanged since r12).
        "codebook core.rule.cx_grain slot 2: finding-field state = page text plus the finding's "
        "activity_name, activity_type, adoption_stage and tool_name; the state is pinned in the "
        "versioned question-set files and approved with the wording packet, and any change "
        "counts as a wording change",
        "combining convention activity_level: every part holding a linked passage votes",
    ],
}

DYNAMIC_YEAR_CHOICES = {
    "packet_items": ["W-05"],
    "approval": APPROVED,
    # W-05 a (RC-D-018 "2 a"); strings refreshed per W-05-P2 (lane E fact check on codebook r13),
    # with R-3 b. Pointers to the signed rules and to the T-064 module that implements them; the
    # forms themselves are not enumerated here.
    "candidates": "candidate years under codebook r13 rule 1, from the activity span and its context",
    "calendar_conversion": "candidate years by written form under codebook r13 rules 1 and 2, conversion table T-064",
    "candidate_source": "g3o.extract.years.extract_year_candidates (T-064), one candidate per distinct year",
    "range_end_bound": "years read from a label (both ends of a year range, the years of a fiscal-year label, "
                       "Japanese era, Buddhist Era and ROC years) count outside 2015-2030 only within 1900-2099; "
                       "the ends of a range after a numbering word keep 2015-2030 (RC-D-018 D1, RC-D-019 C2 b; "
                       "not in the signed rule 1 text); the bound applies to each range end on its own (R-3 b)",
    "reference_year": "the calendar year of the run, recorded on every source (r13 rule 1 two-digit sentence; B1 c)",
    "order": "candidates ascending, then the item's offered missing label(s)",
    "candidate_code": "the candidate's calendar (CE) year in four ASCII digits, e.g. \"2024\" for \"FY24\" "
                      "or \"2567 B.E.\" (YearCandidate.year)",
    "candidate_text": "the calendar year alone, e.g. \"2024\", with no further text (T-016 form)",  # W-05 a
    "rules_text_placement": "after the not_documented answer, as built: the item's rules follow "
                            "the not_documented criterion text",                  # W-05 a
}

PAIR_STATE = {
    "packet_items": ["W-02", "W-07"],
    "approval": APPROVED,
    "fields": [
        {"name": "coder_instructions", "value": "signed slot shared/system_prompt_stage6, verbatim"},
        {"name": "institution", "value": "institution name"},
        {"name": "country", "value": "country"},
        {"name": "first_record", "value": "the first activity's full record (record_fields)"},    # W-07 a
        {"name": "second_record", "value": "the second activity's full record (record_fields)"},  # W-07 a
    ],
    "record_fields": [                 # W-07 a, in the ruled order; names W7 (i) a, (iii) a
        {"name": "activity_name", "value": "name"},
        {"name": "activity_type", "value": "type"},
        {"name": "action_type", "value": "action"},
        {"name": "tool_name", "value": "tool"},
        {"name": "contracting_party", "value": "contracting party"},
        {"name": "developer", "value": "developer"},
        {"name": "year_announced", "value": "year announced"},
        {"name": "page_url", "value": "page address"},
        {"name": "source_type", "value": "source type"},
        {"name": "supporting_quotes", "value": "supporting quotes"},
    ],
    "record_value_form": "plain-word labels (W7 (ii) b, as W-03 a): activity_type, action_type and source_type "
                         "as their value's entailment_label (codebook X35 label_rules), not the code; "
                         "year_announced as the calendar (CE) year in four ASCII digits (X35 label_rules); "
                         "activity_name, tool_name, contracting_party, developer, page_url and the quotes "
                         "as stored (not coded values)",
    "record_missing_value_form": "left out: a record field whose value is not_documented, unknown, not_asked "
                                 "or _NA_ gives no field (as W3-2 a)",                # lane A 4 a
}

POOLED_STATE = {
    "packet_items": ["W-02", "W-08"],
    "approval": APPROVED,
    "instruction_slot": POOLED_INSTRUCTION_SLOT,
    "instruction_placement": "a state field with the pooled material; questions stay exactly as signed",  # W-08 a
    "instruction_field": "pool_note",  # W8 (i) a
    "quote_fields": [                  # W-08 a; names W8 (ii) a, (iii) a, source_type and page_url kept
        {"name": "quote_text", "value": "quote text"},
        {"name": "source_type", "value": "source type"},
        {"name": "source_publication_date", "value": "date: the date the source was published"},
        {"name": "page_url", "value": "page address"},
    ],
    "quote_source_type_form": "its value's entailment_label (signed label), not the code",  # lane A 5 a
    "quote_missing_date_form": "left out: a quote with no publication date has no "
                               "source_publication_date field (as W3-2 a)",           # lane A 6 a
    "pool_order": "source date, then position on the page (combining convention first_part)",
    "split_marker": {"name": "page_part", "value": "marker '{i} of {n}', as for page parts"},  # W-08 a, W8 (iv) a
}


# --------------------------------------------------------------------------- build
def _require_signed(cb: Codebook) -> None:
    if cb.sha256 != SIGNED_CODEBOOK_SHA256:
        raise ValueError(f"codebook sha256 {cb.sha256} is not the pinned r14 {SIGNED_CODEBOOK_SHA256}")


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
    """One entry per packet item: approved when ruled and no slot here lists an open point for it."""
    items = sorted({item for s in specs for item in s["packet_items"]})
    open_points = [p for s in specs for p in s.get("open", [])]
    out = []
    for item in items:
        ruled = item in PACKET_RULINGS
        is_open = any(p.startswith(f"{item}:") for p in open_points)
        e: dict[str, Any] = {"packet_item": item, "approval": APPROVED if ruled and not is_open else PENDING}
        if ruled:
            e["approval_record"] = PACKET_RULINGS[item]
        out.append(e)
    return out


def _nones(x: Any) -> bool:
    if x is None:
        return True
    if isinstance(x, dict):
        return any(_nones(v) for v in x.values())
    if isinstance(x, list):
        return any(_nones(v) for v in x)
    return False


ACTIVITY_PAIR_TEXT = (
    "How does this activity relate to the linked activity named in this task: is it the "
    "same activity described again, part of the linked programme, a programme the linked "
    "activity is part of, a joint activity with it, a rule that governs it or one governed "
    "by it, or a separate activity?"
)


def activity_pair_question(cb: Codebook) -> dict[str, Any]:
    """Approved P-2c adaptation; definitions and rules remain the signed codebook's."""
    iid = "core.activity_segment"
    used: list[tuple[str, str]] = []
    rules = cb.rule_texts(iid)
    criteria = [_criterion(v["code"], cb.definition(iid, i), rules, used)
                for i, v in enumerate(cb.value_list(iid)) if v.get("jev_choice", True)]
    q = _question(cb, iid, cb.items[iid], iid, cb.instruction(iid), criteria,
                  "none", None, _part_prompt(cb, used))
    q.update(instructions=ACTIVITY_PAIR_TEXT, instruction_slot="builder/activity_pair/P-2c",
             approval="approved", approval_record='PI 2026-11-07 "Approve exact wording"',
             unit="unordered pair of resolved page activity spans; lhs starts earlier",
             state_fields={"activity": "lhs activity label", "linked_activity": "rhs activity label"},
             same_start="stop affected pair: pair_direction_tie")
    return _entry(q)


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
            "pair_questions": [activity_pair_question(cb)],
            "pair_wording": {"approval": "approved",
                             "approval_record": 'PI 2026-11-07 "Approve exact wording"',
                             "source": "P-2c quote question reused verbatim; decision 7b"},
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
        return [f"codebook sha256 {cb.sha256} is not the pinned r14"]
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
            if nv.get("approval") not in (PENDING, APPROVED):
                errors.append(f"{name}: non_verbatim {nv} has no approval state")
            if nv.get("approval") == APPROVED and not nv.get("approval_record"):
                errors.append(f"{name}: non_verbatim {nv['packet_item']} approved without a ruling record")
        # 7b. an approved slot declares every value and no open point; a pending one says why
        slots = [doc.get("state"), doc.get("dynamic_year_choices"),
                 doc.get("relation", {}).get("state"), doc.get("pooled", {}).get("state")]
        for slot in (s for s in slots if s):
            if slot.get("approval") == APPROVED and (_nones(slot) or slot.get("open")):
                errors.append(f"{name}: slot {slot['packet_items']} approved with an undeclared value")
            if slot.get("approval") == PENDING and _nones(slot) and not slot.get("open"):
                errors.append(f"{name}: slot {slot['packet_items']} has an undeclared value and no open point")
    # Pair adapter is a separately approved instrument, not a generated jev_choice item.
    if docs["activity"].get("pair_questions") != [activity_pair_question(cb)]:
        errors.append("activity: pair question differs from approved wording or signed criteria")
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
