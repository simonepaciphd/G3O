"""Write drafts/resolutions-r7.json: the resolver's round-2 log (RC-D-005 clean copy, five remaining points).

Resolver subagent of the plan integrator, Claude Code, claude-opus-5-5, 2026-10-30. PI rulings, chat, 2026-10-30
(t010-rulings.md, last section): "fix the remainder points -- make coherent with previous rulings (subagent)" and
"even if just indirectly -- if the same logic applies, not necessarily a ruling on the specific item, but a different
one of similar nature; if none is possible, then provide three options with a rec".
Run: python planning/t010/drafts/resolutions-r7-src.py
"""
import json
from pathlib import Path

D = Path(__file__).resolve().parent
FX = json.loads((D / "fixes-r7.json").read_text(encoding="utf-8"))


def ids(prefix):
    return [f["id"] for f in FX["fixes"] if f["ruling"].startswith(prefix)]


R = [
    {"id": "point 1 (B2 / F8)", "round1": "year items keep the computed candidate `unknown` as an offered choice",
     "chosen": "not offered: candidate kept as a value, flagged values.candidates_not_offered, set mechanically; "
               "`not_documented` offered with the copied signed rule; rule texts unchanged",
     "settled_by": "direct rulings",
     "ruling_text": ['PI 2026-10-30 "12 a"; option as asked (t010-rulings.md): "a, offer `not_documented` (per-item missing-label rule), `unknown` stays mechanical"',
                     "R2C04 (r2#16, chosen a): \"Reserved labels: 'not asked' (ruled out by a rule, with 'not applicable' merged into it), 'not documented' (page silent) and 'unknown' (stated but undeterminable, or downgraded). New and non-frozen fields adopt them\"",
                     "P3 (RC-D-005, default accepted): `not_assessable` never a jev choice (the analogous encoding of a kept value never offered)"],
     "overridden": 'C16 alt-1 (round 1, 2026-10-29): "jev Choice over those years plus `unknown`" -- earlier and specific to the old v2.5 spelling',
     "why": ["12 a is later and covers every jev choice; the year items are non-frozen, so R2C04's split applies",
             "keeping the value with a not-offered flag changes the least signed text; W44/W45 were approved as drafted",
             "round 1 read C16 as allowing the offer; the verbatim option text and R2C04 do not (paraphrase corrected)"],
     "encoded_by": ids("round 2 point 1")},
    {"id": "point 2 (B1 / 12a' iv)", "round1": "35 items excluded from the not_documented offer",
     "chosen": "30 exclusions kept, each recording its signed ground (jev_missing_choice.grounds); source_type and "
               "deployment_scale_unit reversed (offered, copied signed rule)",
     "settled_by": "signed texts per item; baseline = 12 a offers `not_documented`",
     "ruling_text": ['activity_type signed `unknown` rule (FX06): "the kind of undertaking is indeterminate from the available sources"',
                     'genai_mechanism_basis signed rules/0: "jev Choice on every confirms_activity page/activity"; signed confirms_activity definition: "The text must be explicitly generative AI"',
                     'signed CX map: "`no` of the `evaluation_type_*` and `content_*` items -> "not documented""; "`none_reported` (CX-60, CX-61) -> "not documented""',
                     'R2C04: "the frozen institutional questionnaire items keep their signed spellings with a mapping row"'],
     "why": ["an exclusion needs a signed ground; source_type (`other` = \"None of the above\") and the scale unit "
             "(`none` = \"counts none of these units\") had only an inference"],
     "encoded_by": ids("round 2 point 2")},
    {"id": "point 3 (D5)", "round1": "check 7: a gate item without a round takes its own gate's position",
     "chosen": "check 7 compares rounds only between classifiers; a quote-step or mechanical gate item is noted, its "
               "order being the signed gate_items_first rule; a classifier gate without a round still fails",
     "settled_by": "signed combining rule + F6 a",
     "ruling_text": ['combining_conventions.gate_items_first (all-04): "activity_type and action_type (and the scale number) are combined before the items they gate."',
                     'F6 a (procedural default, accepted with "drafts ok"): the "any value" gate form on the scale unit'],
     "why": ["R-040 runs the quote step \"for every activity, including items the applicability table skips\", so the "
             "round-1 borrowed position had no ground"],
     "encoded_by": ["reclass/t013-codebook: g3o/codebook/checks.py check_07_gates"]},
    {"id": "point 4 (T5)", "round1": "adjust: R-042 fuzzy match in the producing part", "chosen": "kept",
     "settled_by": "direct rulings",
     "ruling_text": ['SPEC R-042 (USER SF-014 ii c): "Supporting text is checked against the stored page text by fuzzy match; a quote below the match threshold counts as no supporting text."',
                     'RC-D-002 row 17 (R-042 note): "the check matches against the text the quote came from"',
                     'R-044: "the supporting quote comes from the chunk that produced the code"'],
     "why": ["\"verbatim\" (R-040) is what the quote step copies; the check is the fuzzy presence match"]},
    {"id": "point 4 (T9)", "round1": "undated pooled evidence last",
     "chosen": "an undated source takes the signed stage_as_of fallback date (latest stated date for the activity, else access date)",
     "settled_by": "analogy (PI follow-up ruling: a ruling of similar nature)",
     "ruling_text": ['all-06 a: "pooled evidence is ordered by source date, then page order"',
                     'signed core.stage_as_of rule: "stage_as_of = source_publication_date if supported, else the page\'s latest stated date for the activity, else the access date"'],
     "why": ["both rules must date an activity observation when its publication date is missing; the signed fallback "
             "answers that question, so the same logic carries over; \"last\" had no ruling behind it"]},
    {"id": "point 5a (schema.json)", "chosen": "schema loosened to shapes (checks keep the value rules); test validates the signed file and a byte copy of the r7 sign-off build",
     "settled_by": "coordinator scope (5a); schema description: allowed values are the checks' job",
     "encoded_by": ["reclass/t013-codebook: codebook/schema.json, tests/test_codebook.py, tests/fixtures/codebook/"]},
    {"id": "point 5b (T-016 scope)", "chosen": "E9 draft: every generated jev question of the re-signed codebook, plus part-prompt texts on long pages, under the shared system prompt",
     "settled_by": "PLAN T-016 objective + 3 a",
     "ruling_text": ['PLAN T-016 (RC-D-002 N28): "A paid re-pilot, run by Simone before the build (r2#3), of every reworded item"',
                     'PI 2026-10-30: "3 subagent drafts all & I read and edit/confirm"'],
     "why": ["the 38 new questions are reworded items confirmed in chat but never run"]},
]
out = {"format": "resolutions-r7 v1", "drafted_by": "resolver subagent of the plan integrator, Claude Code, claude-opus-5-5, 2026-10-30",
       "rulings": ['PI 2026-10-30: "fix the remainder points -- make coherent with previous rulings (subagent)"',
                   'PI 2026-10-30: "even if just indirectly -- if the same logic applies, not necessarily a ruling on the specific item, but a different one of similar nature; if none is possible, then provide three options with a rec"'],
       "status": "proposed; nothing final until the PI approves planning/t010/RC-D-005-clean-copy.md",
       "three_option_fallback_used": False, "fixes_file": "planning/t010/drafts/fixes-r7.json", "resolutions": R}
(D / "resolutions-r7.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(len(R), "points")
