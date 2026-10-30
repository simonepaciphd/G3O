"""Draft drafts/fixes-r7.json (RC-D-005 clean copy, round 2) from the r6 draft candidate.

Resolver subagent of the plan integrator (Claude Code, claude-opus-5-5), 2026-10-30. PI ruling, chat, 2026-10-30
(t010-rulings.md, last section): "fix the remainder points -- make coherent with previous rulings (subagent)".
Entries are applied after fixes-r5 and fixes-r6 by build_skeleton.py --build r7-draft | r7-signoff. No new slot text:
the only slot added is the signed sentence "not_documented: the page is silent." (items/core.has_human_oversight/rules/2),
re-used as the meaning of the offered `not_documented` on five more items.
Run: python planning/t010/drafts/fixes-r7-draft.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import yaml

T010 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(T010))
from build_skeleton import r5_apply_fix, r5_resolve  # noqa: E402

BASE = T010 / "candidate-r6/codebook-r6-draft.yaml"
raw = BASE.read_bytes()
BASE_SHA = hashlib.sha256(raw).hexdigest()
cb = yaml.safe_load(raw.decode("utf-8"))
I = cb["items"]
FIXES: list = []
RESOLVER = "agent-draft (resolver)"
n = 0


def get(path):
    parent, k = r5_resolve(cb, path)
    return parent[k]


def fix(ruling, op, what, path, after=None):
    global n
    n += 1
    f = {"id": f"R7-{n:02d}", "ruling": ruling, "op": op, "what": what, "path": path}
    if op in ("set", "delete"):
        f["before"] = copy.deepcopy(get(path))
    if op != "delete":
        f["after"] = after
    r5_apply_fix(cb, f, "r5-draft")
    FIXES.append(f)
    return f


REUSE = "not_documented: the page is silent."
REUSE_FROM = "items/core.has_human_oversight/rules/2"
assert get(REUSE_FROM)["text"] == REUSE
R2C04 = ("R2C04 (r2#16, PI 2026-10-29): \"Reserved labels: 'not asked' ..., 'not documented' (page silent) and 'unknown' "
         "(stated but undeterminable, or downgraded). New and non-frozen fields adopt them\"")
R12A = ("RC-D-005 12 a (PI 2026-10-30 \"12 a\"; option as asked: \"a, offer `not_documented` (per-item missing-label rule), "
        "`unknown` stays mechanical\")")


def offer_reused(iid: str, why: str, ruling: str):
    rules = get(f"items/{iid}/rules")
    idx = len(rules)
    slot = {"text": REUSE, "origin": f"{RESOLVER}; re-use of the signed text at {REUSE_FROM} (round 2)",
            "source": f"{REUSE_FROM} (PI 2026-10-30 \"approved!\"; fixes-r4 FX06)",
            "role": "missing label not_documented: meaning for this item"}
    fix(ruling, "set", f"{iid}: missing-label rule for `not_documented` added (re-used signed text)",
        f"items/{iid}/rules", rules + [slot])
    fix(ruling, "set", f"{iid}: `not_documented` offered with the re-used rule as its meaning",
        f"items/{iid}/jev_missing_choice",
        {"offered": ["not_documented"], "rule": [f"items/{iid}/rules/{idx}"],
         "resolution": f"RC-D-005 round 2: offered; {why}"})
    refs = get(f"items/{iid}/refs")
    fix("refs", "set", f"{iid}: refs, round-2 resolution added", f"items/{iid}/refs", refs + ["RC-D-005 round 2"])


# ---- point 1 (B2 / F8): `unknown` is not offered on the year items --------------------------------------------
for iid in ("core.year_announced", "core.year_pilot_start", "core.year_production_start"):
    fix("round 2 point 1", "add", f"{iid}: the computed candidate `unknown` is kept as a value but not offered (as P3 for "
        "`not_assessable`); it is set mechanically", f"items/{iid}/values/candidates_not_offered",
        {"codes": ["unknown"], "why": f"{R12A} is later than C16 alt-1 (round 1, 2026-10-29) and overrides its `plus unknown` "
         f"choice; {R2C04}"})
    offer_reused(iid, f"{R2C04}; {R12A}", "round 2 point 1")
fix("round 2 point 1", "set", "vocabularies.missing.jev_choice.resolution: no exception for the year items",
    "vocabularies/missing/jev_choice/resolution",
    {"offered_on": "items whose `not_documented` is not already covered by a signed value definition, a signed "
                   "missing-label rule, the frozen CX answer set or a signed order (RC-D-005 12a' iv, round 2); each names "
                   "its meaning rule in jev_missing_choice",
     "unknown": "never offered (12 a); the year items keep the C16 candidate `unknown` as a value, flagged "
                "values.candidates_not_offered, and it is set mechanically"})

# ---- point 2 (B1): exclusions that rested on inference are reversed ----------------------------------------------
offer_reused("core.source_type", "no signed text covers a page that does not show its kind: `other` is \"None of the "
             "above\", not silence (round-1 exclusion rested on inference)", "round 2 point 2")
offer_reused("core.deployment_scale_unit", "`none` is \"A number is stated, but it counts none of these units\", not a "
             "page silent about what the number counts (round-1 exclusion rested on inference)", "round 2 point 2")

GROUNDS = {
    "core.page_verdict": "signed: missing_tokens none (fixes-r5 R5-82); the item takes no reserved label",
    "core.procurement_status": "signed rules/2: \"`not_documented` is not used for this item\"",
    "core.disclosure_form": "frozen CX answer set (CX-10..18; pilot.py FORM) has no `not_documented`; R2C04 / R-045: \"frozen CX items keep their signed spellings with a mapping row\"; CX map: `unknown` (CX-17)",
    "core.disclosure_scope": "frozen CX answer set (CX-20..25; pilot.py SCOPE) has no `not_documented`; R2C04 / R-045 frozen spellings; CX map: `unknown` (CX-24)",
    "core.page_complete": "signed `no` definition: \"The page does not refer the reader elsewhere for more information about any GenAI activity it mentions.\"",
    "core.content_contact_named": "signed CX map: \"`no` of the `evaluation_type_*` and `content_*` items → \"not documented\"\"",
    "core.content_contact_details": "signed CX map: \"`no` of the `evaluation_type_*` and `content_*` items → \"not documented\"\"",
    "core.content_data": "signed CX map: \"`no` of the `evaluation_type_*` and `content_*` items → \"not documented\"\"; `no` = \"not stated on the page\"",
    "core.activity_type": "signed `unknown` rule (fixes-r4 FX06): \"the kind of undertaking is indeterminate from the available sources\"; signed applicability table (r2#8) keys `unknown`, no `not_documented`",
    "core.action_type": "signed `unknown` rule (FX06): \"The page mentions the activity but does not let it be settled\"; an activity row is a passage of its page (core.rule.activity_unit)",
    "core.adoption_stage": "signed `unknown` rule (FX06): \"Evidence confirms GenAI activity exists but stage is indeterminate.\"",
    "core.genai_mechanism_basis": "signed rules/0: \"jev Choice on every confirms_activity page/activity\" over the four bases; signed `confirms_activity` definition: \"The text must be explicitly generative AI\"",
    "core.outcome_kind": "signed CX map: \"`none_reported` (CX-60, CX-61) → \"not documented\"\"",
    "core.incident_kind": "signed CX map: \"`none_reported` (CX-60, CX-61) → \"not documented\"\"",
    "core.support_entailment": "signed `false` definition: \"The quoted text does not state that the field has the given value.\"",
    "core.activity_relation_cross_page": "signed priority order (unresolved ... unknown) has no `not_documented`, though R-044 ranks it in every order that has it; signed `unresolved`: \"The sources do not settle whether the two records describe the same activity.\"",
}
for k in ("drafting_writing", "summarization", "translation", "search_retrieval", "code", "image_audio_video",
          "extraction_classification", "analysis_recommendation"):
    GROUNDS[f"core.function_{k}"] = "signed `no` definition: \"The page does not state that the tool is used for ...\""
for k in ("pre_deployment_testing", "pilot_evaluation", "independent_audit", "ongoing_monitoring", "user_feedback",
          "bias_or_safety_testing"):
    GROUNDS[f"core.evaluation_type_{k}"] = "signed CX map: \"`no` of the `evaluation_type_*` and `content_*` items → \"not documented\"\""
excluded = [k for k, it in I.items() if k.startswith("core.") and isinstance(it.get("jev_missing_choice"), dict)
            and not it["jev_missing_choice"]["offered"]]
assert set(excluded) == set(GROUNDS), set(excluded) ^ set(GROUNDS)
for iid in excluded:
    jm = copy.deepcopy(get(f"items/{iid}/jev_missing_choice"))
    fix("round 2 point 2", "set", f"{iid}: exclusion re-checked; the signed text it rests on recorded",
        f"items/{iid}/jev_missing_choice", {**jm, "grounds": GROUNDS[iid],
                                             "resolution": "RC-D-005 12a' (iv), re-checked in round 2: not offered"})

fix("fold", "set", "release.folds.r6 names round 2", "release/folds/r6",
    get("release/folds/r6") + "; round 2: planning/t010/drafts/fixes-r7.json and drafts/resolutions-r7.json "
    "(PI 2026-10-30 \"fix the remainder points -- make coherent with previous rulings (subagent)\")")

out = {"format": "fixes-r7 v1: entries applied in order after fixes-r5 and fixes-r6 by build_skeleton.py apply_r7()",
       "status": "candidate for RC-D-005, round 2; put to the PI in planning/t010/RC-D-005-clean-copy.md",
       "drafted_by": "resolver subagent of the plan integrator, Claude Code, claude-opus-5-5, 2026-10-30",
       "ruling": 'PI, chat, 2026-10-30 (t010-rulings.md): "fix the remainder points -- make coherent with previous rulings (subagent)"',
       "base": "planning/t010/candidate-r6/codebook-r6-draft.yaml", "base_sha256": BASE_SHA,
       "reused_texts": {"not_documented rule": {"text": REUSE, "from": REUSE_FROM,
                                                "items": ["core.year_announced", "core.year_pilot_start",
                                                          "core.year_production_start", "core.source_type",
                                                          "core.deployment_scale_unit"]}},
       "fixes": FIXES}
(T010 / "drafts/fixes-r7.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"{len(FIXES)} entries; base {BASE_SHA[:12]}; excluded {len(excluded)}")
