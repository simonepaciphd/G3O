"""Draft drafts/fixes-r6.json (RC-D-005 wording fold and resolutions) from the r5 candidate.

Integrator tool (T-010, RC-D-005), written 2026-10-30 by the resolver subagent of the plan integrator (Claude Code,
claude-opus-5-5). PI ruling, chat, 2026-10-30 (t010-rulings.md, last section): "drafts ok, give a subagent the task to
resolve ambiguities in a way that's coherent with the rest, i will approve final clean copy".

It reads the r5 draft candidate (planning/t010/candidate-r5/codebook-r5-draft.yaml), writes one entry per change with
its ruling or resolution id, path, before and after, and applies the entries in order with the builder's own
r5_apply_fix(), so every path and `before` is the state the builder meets after the r5 fixes. Every new slot text is
either a W entry of drafts/rc-d-005-wording.json (approved as drafted), EVAL_EMPHASIS read from the frozen pilot.py,
a cut of a signed text, a re-use of a signed text, or one of the resolver's own texts listed in RESOLVER_TEXTS (each
shown to the PI in RC-D-005-clean-copy.md section C).
Run: python planning/t010/drafts/fixes-r6-draft.py
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
from pathlib import Path

import yaml

T010 = Path(__file__).resolve().parents[1]
ROOT = T010.parents[1]
sys.path.insert(0, str(T010))
from build_skeleton import r5_apply_fix, r5_resolve  # noqa: E402

BASE = T010 / "candidate-r5/codebook-r5-draft.yaml"
raw = BASE.read_bytes()
BASE_SHA = hashlib.sha256(raw).hexdigest()
cb = yaml.safe_load(raw.decode("utf-8"))
I = cb["items"]
W = json.loads((T010 / "drafts/rc-d-005-wording.json").read_text(encoding="utf-8"))["entries"]
assert sorted(W) == [f"W{n:02d}" for n in range(1, 46)]
PILOT = Path("H:/My Drive/Research/G3O/archive/planning-drive-copy-superseded-2026-10-26/launch-analysis-pr/"
             "index-design/pilot/pilot.py")
FIXES: list = []
APPROVAL = 'PI 2026-10-30 "drafts ok"'
RESOLVER = "agent-draft (resolver)"


def eval_emphasis() -> str:
    """EVAL_EMPHASIS exactly as the frozen CX-01.2 pilot defines it (pilot.py L181-187)."""
    src = PILOT.read_text(encoding="utf-8")
    lines = src.splitlines()
    assert lines[180].startswith("EVAL_EMPHASIS = ("), lines[180]
    assert lines[186] == ")", lines[186]
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "EVAL_EMPHASIS":
            assert node.lineno == 181 and node.end_lineno == 187
            return ast.literal_eval(node.value)
    raise AssertionError("EVAL_EMPHASIS not found")


EE = eval_emphasis()
EE_SOURCE = ("H:/My Drive/Research/G3O/archive/planning-drive-copy-superseded-2026-10-26/launch-analysis-pr/index-design/"
             "pilot/pilot.py L181-187 EVAL_EMPHASIS (frozen CX-01.2 wording, byte for byte; E1)")


def get(path):
    parent, k = r5_resolve(cb, path)
    return parent[k]


def fix(fid, ruling, op, what, path=None, paths=None, before=None, after=None, **extra):
    f = {"id": fid, "ruling": ruling, "op": op, "what": what}
    if paths is not None:
        f["paths"] = paths
    else:
        f["path"] = path
    if op in ("set", "delete"):
        f["before"] = before if before is not None else (
            [copy.deepcopy(get(p)) for p in paths] if paths is not None and op == "delete" else copy.deepcopy(get(path if paths is None else paths[0])))
    if op != "delete":
        f["after"] = after
    f.update(extra)
    r5_apply_fix(cb, f, "r5-draft")
    FIXES.append(f)
    return f


def wslot(wid: str, text: str | None = None, extra_source: str = "") -> dict:
    e = W[wid]
    s = {"text": e["text"] if text is None else text,
         "origin": f"{APPROVAL}; agent draft {wid}" + ("; EVAL_EMPHASIS (E1)" if extra_source else ""),
         "source": f"drafts/rc-d-005-wording.json {wid} ({e['source']})" + (f" + {extra_source}" if extra_source else "")}
    return s


def addref(iid: str, *refs: str):
    old = copy.deepcopy(I[iid]["refs"])
    new = old + [r for r in refs if r not in old]
    if new != old:
        fix(f"R6-REF-{iid.split('.', 1)[1]}", "refs", "set", "refs: the RC-D-005 resolution(s) added", path=f"items/{iid}/refs", after=new)


n = 0


def nid():
    global n
    n += 1
    return f"R6-{n:02d}"


# ============================================================== W01-W04 + Stage 6 system prompt (shared slots)
RESOLVER_TEXTS = {}
S2 = "You read one web page, or one part of one, about a named institution and answer coding questions about it."
assert S2 in W["W04"]["text"]
S2_STAGE6 = ("You read two activity records, or a set of quotes about one activity gathered from several sources, "
             "about a named institution and answer coding questions about them.")
RESOLVER_TEXTS["N-01"] = {"path": "shared/system_prompt_stage6", "new_sentence": S2_STAGE6,
                          "replaces": S2, "why": "W04 note: the page framing does not fit Stage 6 inputs (two records or pooled quotes)"}
STAGE6 = W["W04"]["text"].replace(S2, S2_STAGE6)
shared = {
    "part_prompt": {
        "sentence": wslot("W01"),
        "temporary_answer": {"label": wslot("W02"), "meaning": wslot("W03")},
        "applies_to": "every part prompt of a long page (R-044, all-03 a) and of split pooled Stage 6 evidence (r2#6)",
    },
    "system_prompt": {**wslot("W04"), "applies_to": ["pass 1", "pass 2", "extractor"]},
    "system_prompt_stage6": {"text": STAGE6, "origin": f"{RESOLVER}; W04 with its second sentence replaced (W04 note)",
                             "source": "drafts/rc-d-005-wording.json W04; drafts/resolutions-r6.json W04-note (new sentence 2)",
                             "applies_to": ["stage6"]},
}
fix(nid(), "5 a, 6 a; W01-W04; W04 note", "add", "top-level `shared`: part-prompt sentence, temporary answer (label, meaning), "
    "system prompt (W04) and its Stage 6 variant", path="shared", after=shared)

# ============================================================== W05-W43 instructions (W10 under R2 b, below)
EVAL_W = {"W36", "W37", "W38", "W39", "W40", "W41"}
for wid in sorted(W):
    p = W[wid]["path"]
    if not (p.startswith("items/") and p.endswith("/instruction")) or wid == "W10":
        continue
    assert get(p) == "none", (wid, p)
    if wid in EVAL_W:
        slot = wslot(wid, W[wid]["text"] + EE, EE_SOURCE)
    else:
        slot = wslot(wid)
    fix(nid(), f"3 a; {wid}" + ("; E1" if wid in EVAL_W else ""), "set", f"instruction from {wid}"
        + (" followed by EVAL_EMPHASIS byte for byte (E1)" if wid in EVAL_W else ""), path=p, after=slot)

# ============================================================== W44 / W45: the year question inside rule 1 (ruling 4)
OLDQ = '"In which year does the page say this activity was first announced?"'
for wid, iid in (("W44", "core.year_pilot_start"), ("W45", "core.year_production_start")):
    r0 = copy.deepcopy(get(f"items/{iid}/rules/0"))
    assert OLDQ in r0["text"]
    assert W[wid]["text"] == r0["text"].replace(OLDQ, '"' + W[f"W{31 if wid == 'W44' else 32}"]["text"] + '"')
    new = {**r0, **wslot(wid), "text_before_r6": r0["text"]}
    fix(nid(), f"4; {wid}", "set", f"{iid} rule 1: the quoted announced-year question replaced by the item's own question ({wid})",
        path=f"items/{iid}/rules/0", after=new)

# ============================================================== R2 b: observed-actor relationship, role part (W10)
OAR = "items/core.observed_actor_relationship"
fix(nid(), "R2 b", "add", "relationship item: machine-readable order of its two linked parts (template parts form)",
    path=OAR + "/values/parts", after=["relationship", "searched_institution_role"])
fix(nid(), "R2 b; W10", "add", "relationship item: the role part's question (W10); path chosen under R2 b "
    "(W10 proposed values/searched_institution_role/instruction, but that key holds the value list)",
    path=OAR + "/values/part_instructions", after={"searched_institution_role": wslot("W10")})
addref("core.observed_actor_relationship", "RC-D-005 W09-W10", "RC-D-005 R2 b")

# ============================================================== R1 a: pooled_activity_fields is a derived Stage 6 item
P = "items/core.pooled_activity_fields"
fix(nid(), "R1 a", "set", "pooled_activity_fields: linkage pipeline (no jev question of its own)", path=P + "/linkage", after="pipeline")
fix(nid(), "R1 a", "set", "pooled_activity_fields: coder derived", path=P + "/coder", after="derived")
fix(nid(), "R1 a", "set", "pooled_activity_fields: no threshold of its own (each pooled field keeps its item's bar)",
    path=P + "/threshold", after="none")
fix(nid(), "R1 a", "delete", "pooled_activity_fields: no jev missing choice (not a jev item)", path=P + "/jev_missing_choice")
addref("core.pooled_activity_fields", "RC-D-005 W43", "RC-D-005 R1 a")

# ============================================================== 12a' (iv): which items offer `not_documented`
REUSE = "not_documented: the page is silent."
REUSE_FROM = "items/core.has_human_oversight/rules/2"
assert get(REUSE_FROM)["text"] == REUSE
OFFER_REUSE = {   # unknown rule says "mentions ... but does not let it be settled", so silence is the other case
    "core.model_origin": "its `unknown` rule covers a page that mentions the model but does not settle it; a silent page is the other case",
    "core.build_arrangement": "its `unknown` rule covers a page that mentions how the tool was built but does not settle it; a silent page is the other case",
    "core.deployment_mode": "its `unknown` rule covers a page that mentions integration but does not settle it; a silent page is the other case",
    "core.target_users": "its `unknown` rule covers a page that mentions users but does not settle it; a silent page is the other case",
    "core.governed_population": "its `unknown` rule covers a page that mentions whom the rule applies to but does not settle it; a silent page is the other case",
    "core.governance_form": "its `unknown` rule covers a page that mentions the rule's form but does not settle it; a silent page is the other case",
    "core.observed_actor_role": "no missing-label rule; the linked relationship item already offers `not_documented` for a silent page (its rules/6)",
}
OFFER_OWN = ["core.observed_actor_relationship", "core.interface", "core.governance_direction", "core.service_domain",
             "core.has_human_oversight", "core.has_transparency_notice", "core.has_data_classification",
             "core.has_risk_assessment", "core.evaluation_documented"]
EXCLUDE = {
    "core.disclosure_form": "frozen CX item whose signed answer set has no `not_documented` (CX map: `unknown`, CX-17); its `unknown` rule covers a page whose kind cannot be told, and every page has a kind",
    "core.disclosure_scope": "frozen CX item whose signed answer set has no `not_documented` (CX map: `unknown`, CX-24); its `unknown` rule (\"Coverage cannot be determined from the page\") covers the silent case",
    "core.page_complete": "yes/no item: `no` (the page does not refer elsewhere) already covers a silent page",
    "core.source_type": "every page has a source; `other` covers a source none of the values fits",
    "core.content_contact_named": "yes/no item: `no` is \"not stated\" (CX-06 map sends `no` of the content items to \"not documented\")",
    "core.content_contact_details": "yes/no item: `no` is \"not stated\" (CX-06 map sends `no` of the content items to \"not documented\")",
    "core.content_data": "yes/no item: `no` is \"not stated on the page\" (CX-06 map sends `no` of the content items to \"not documented\")",
    "core.activity_type": "its `unknown` rule covers an activity whose kind cannot be told; the applicability table (r2#8) has an `unknown` column and no `not_documented` column, so a `not_documented` type would close every applicability gate",
    "core.action_type": "its `unknown` rule (\"The page mentions the activity but does not let it be settled\") covers every case: an activity row is always mentioned on its page",
    "core.adoption_stage": "its `unknown` rule (\"Evidence confirms GenAI activity exists but stage is indeterminate\") covers the silent case",
    "core.genai_mechanism_basis": "asked only for activities the page shows as GenAI (core.rule.genai_boundary), so the page always shows some basis",
    "core.year_announced": "the computed candidate `unknown` (C16, F8 b) already covers a page that states no year",
    "core.year_pilot_start": "the computed candidate `unknown` (C16, F8 b) already covers a page that states no year",
    "core.year_production_start": "the computed candidate `unknown` (C16, F8 b) already covers a page that states no year",
    "core.deployment_scale_unit": "asked only when a number is stated; `none` covers a number that counts none of the units",
    "core.outcome_kind": "`none_reported` (\"states no result\") covers a silent page (CX-06 map: `none_reported` to \"not documented\")",
    "core.incident_kind": "`none_reported` (\"states no result\") covers a silent page (CX-06 map: `none_reported` to \"not documented\")",
    "core.support_entailment": "the answer is about one quote: `false` covers a quote that does not state the value",
    "core.activity_relation_cross_page": "compares two records, not a page; `unresolved` covers a pair that cannot be settled",
}
for k in ("drafting_writing", "summarization", "translation", "search_retrieval", "code", "image_audio_video",
          "extraction_classification", "analysis_recommendation"):
    EXCLUDE[f"core.function_{k}"] = "yes/no item: `no` is \"the page does not state\" this function"
for k in ("pre_deployment_testing", "pilot_evaluation", "independent_audit", "ongoing_monitoring", "user_feedback",
          "bias_or_safety_testing"):
    EXCLUDE[f"core.evaluation_type_{k}"] = "yes/no item: `no` is \"not documented\" (CX-06 map sends `no` of the evaluation-type items to \"not documented\")"

jev_items = [k for k, it in I.items() if k.startswith("core.") and it["linkage"] == "jev_choice" and it["coder"] == "classifier"]
covered = set(OFFER_REUSE) | set(OFFER_OWN) | set(EXCLUDE) | {"core.page_verdict", "core.procurement_status"}
assert set(jev_items) == covered, (set(jev_items) ^ covered)

for iid in OFFER_OWN:
    jm = get(f"items/{iid}/jev_missing_choice")
    assert jm["offered"] == ["not_documented"] and isinstance(jm["rule"], list), iid
    fix(nid(), "12a' (iv)", "set", f"{iid}: `not_documented` offered, meaning from its own signed rule (unchanged; resolution recorded)",
        path=f"items/{iid}/jev_missing_choice", after={**jm, "resolution": "RC-D-005 12a' (iv): offered; the item's own rule gives the meaning"})
for iid, why in OFFER_REUSE.items():
    rules = get(f"items/{iid}/rules")
    idx = len(rules)
    slot = {"text": REUSE, "origin": f"{RESOLVER}; re-use of the signed text at {REUSE_FROM} (12a' iv)",
            "source": f"{REUSE_FROM} (PI 2026-10-30 \"approved!\"; fixes-r4 FX06)",
            "role": "missing label not_documented: meaning for this item"}
    fix(nid(), "12a' (iv)", "set", f"{iid}: missing-label rule for `not_documented` added (re-used signed text)",
        path=f"items/{iid}/rules", after=rules + [slot])
    fix(nid(), "12a' (iv)", "set", f"{iid}: `not_documented` offered with the re-used rule as its meaning",
        path=f"items/{iid}/jev_missing_choice",
        after={"offered": ["not_documented"], "rule": [f"items/{iid}/rules/{idx}"],
               "resolution": f"RC-D-005 12a' (iv): offered; {why}"})
    addref(iid, "RC-D-005 12a' iv")
for iid, why in EXCLUDE.items():
    fix(nid(), "12a' (iv)", "set", f"{iid}: `not_documented` not offered as a jev choice",
        path=f"items/{iid}/jev_missing_choice",
        after={"offered": [], "rule": "none", "why": why, "resolution": "RC-D-005 12a' (iv): not offered"})
fix(nid(), "12a' (iv); F8 b", "add", "vocabularies.missing.jev_choice: the resolution and the year exception recorded",
    path="vocabularies/missing/jev_choice/resolution",
    after={"offered_on": "items whose `not_documented` has a meaning that no real value or `unknown` rule already covers "
                         "(RC-D-005 12a' iv); each names its rule in jev_missing_choice",
           "computed_unknown_candidate": "the three year items keep the computed candidate `unknown` among their choices "
                                         "(C16; signed values and rule 1; RC-D-005 F8 b); everywhere else `unknown` is mechanical"})

# ============================================================== I7 a: source_type `other` loses the snippet clause
OT = "items/core.source_type/values/7/definition"
old = copy.deepcopy(get(OT))
assert old["text"] == "None of the above; explain in `source_snippet`"
fix(nid(), "I7 a", "set", "source_type `other`: cut before the clause jev cannot carry out (C-004: jev returns codes only)",
    path=OT, after={**old, "text": "None of the above", "omitted_tail": "; explain in `source_snippet`",
                    "omitted_by": "RC-D-005 I7 a (resolver): jev returns codes only (C-004); cut before the part it cannot do, as PI 2026-10-30 \"2a\""})

# ============================================================== F5: rule-only gates
ST = "items/core.source_type"
g = copy.deepcopy(get(ST + "/gate"))
fix(nid(), "F5 source_type b", "set", "source_type gate none; the condition stays in rules/0 and is applied by the pipeline (R-002)",
    path=ST + "/gate", after="none")
fix(nid(), "F5 source_type b", "add", "source_type: the former gate text kept as data, pointing at the rule that carries it",
    path=ST + "/ask_condition", after={**g, "carried_by": "items/core.source_type/rules/0", "resolution": "RC-D-005 F5 source_type b"})
addref("core.source_type", "RC-D-005 W08", "RC-D-005 F5 b", "RC-D-005 I7 a")
SR = "items/core.support_status_second_reason"
g = copy.deepcopy(get(SR + "/gate"))
fix(nid(), "F5 second_reason a", "set", "support_status_second_reason gate none; F10 rule (rules/1) carries \"empty unless two reasons hold\"",
    path=SR + "/gate", after="none")
fix(nid(), "F5 second_reason a", "add", "support_status_second_reason: the former gate text kept as data, pointing at its rule",
    path=SR + "/fill_condition", after={**g, "carried_by": "items/core.support_status_second_reason/rules/1",
                                        "resolution": "RC-D-005 F5 second_reason a"})
addref("core.support_status_second_reason", "RC-D-005 F5 a")

# ============================================================== F10 a: drop rules describing a folded-away question
for iid in ("core.reported_outcomes", "core.reported_incidents"):
    r1 = get(f"items/{iid}/rules/1")
    assert r1["text"].startswith("jev Choice"), r1
    fix(nid(), "F10 a", "delete", f"{iid} rules/1: describes the separate existence question that folded into the kind item "
        "(outcome_kind / incident_kind rules/0 and /1); dropped as overridden", path=f"items/{iid}/rules/1")
    addref(iid, "RC-D-005 F10 a")

# ============================================================== F6 a: "any value" gate form
SU = "items/core.deployment_scale_unit"
assert get(SU + "/gate") == {"item": "core.deployment_scale_number", "values": ["any stated"]}
fix(nid(), "F6 a", "set", "scale unit gate in the \"any value\" form: any stated number opens it",
    path=SU + "/gate", after={"item": "core.deployment_scale_number", "values": "any", "as_ruled": "any stated"})
# W33 note: the stated number is shown with the unit question
fix(nid(), "W33 note", "add", "scale unit: the extracted number is shown with its question (rules/0: the extractor returns "
    "the number span, jev gives the unit)", path=SU + "/question_context",
    after={"shows_value_of": ["core.deployment_scale_number"], "resolution": "RC-D-005 W33 note"})
addref("core.deployment_scale_unit", "RC-D-005 W33", "RC-D-005 F6 a")

# ============================================================== F1 a: support_status names its vocabulary
fix(nid(), "F1 a", "add", "support_status: its codes are the named vocabulary (values none; template F1 a)",
    path="items/core.support_status/value_vocabulary", after="support_status")

# ============================================================== release fold record
fix(nid(), "fold", "add", "release.folds.r6", path="release/folds/r6",
    after="planning/t010/drafts/fixes-r6.json (RC-D-005: wording W01-W45 approved as drafted, PI 2026-10-30 \"drafts ok\"; "
          "E1; resolutions in drafts/resolutions-r6.json, put to the PI in planning/t010/RC-D-005-clean-copy.md)")

# ----------------------------------------------------------------------------- write
out = {
    "format": "fixes-r6 v1: entries applied in order after fixes-r5 by build_skeleton.py apply_r6(); op set | add | delete; `before` is the exact value met",
    "status": "candidate for RC-D-005: W01-W45 approved as drafted; resolutions pending PI approval of the clean copy",
    "drafted_by": "resolver subagent of the plan integrator, Claude Code, claude-opus-5-5, 2026-10-30",
    "ruling": 'PI, chat, 2026-10-30 (t010-rulings.md): "drafts ok, give a subagent the task to resolve ambiguities in a way that\'s coherent with the rest, i will approve final clean copy"',
    "base": "planning/t010/candidate-r5/codebook-r5-draft.yaml",
    "base_sha256": BASE_SHA,
    "eval_emphasis": EE,
    "resolver_texts": RESOLVER_TEXTS,
    "reused_texts": {"not_documented rule": {"text": REUSE, "from": REUSE_FROM, "items": list(OFFER_REUSE)}},
    "fixes": FIXES,
}
dst = T010 / "drafts/fixes-r6.json"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"{len(FIXES)} entries -> {dst}; base {BASE_SHA[:12]}")
