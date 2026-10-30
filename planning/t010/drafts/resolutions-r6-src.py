"""Write drafts/resolutions-r6.json: the resolver's machine-readable log (RC-D-005 follow-ups).

Resolver subagent of the plan integrator, Claude Code, claude-opus-5-5, 2026-10-30. One entry per open point: source
label (as put to the PI), options, the option chosen, reasons, the rules it rests on, and the fixes-r6 entries that
encode it. Run: python planning/t010/drafts/resolutions-r6-src.py
"""
import json
from pathlib import Path

D = Path(__file__).resolve().parent
FX = json.loads((D / "fixes-r6.json").read_text(encoding="utf-8"))


def ids(pred):
    return [f["id"] for f in FX["fixes"] if pred(f)]


R = []


def res(label, question, options, chosen, reasons, rests_on, encoded=(), new_text=None, notes=None):
    R.append({"id": label, "question": question, "options": options, "chosen": chosen, "reasons": reasons,
              "rests_on": rests_on, "encoded_by": list(encoded), "new_text": new_text, "notes": notes})


res("12a'", "Which items offer `not_documented` as a jev choice",
    {"i": "only where an item rule gives it a meaning", "ii": "all, using the general vocabularies.missing definition",
     "iii": "all, with per-item rules drafted", "iv": "as iii, excluding items where a real value already covers it"},
    "iv",
    ["12 a offers `not_documented` with a per-item missing-label rule; (i) would leave silent single-part pages on items "
     "like model_origin at `unknown` while R-044 gives long silent pages `not documented`, so the same silence would get two labels.",
     "(ii) and (iii) contradict signed rules: procurement_status rules/2 says `not_documented` is not used, and on yes/no "
     "items `no` already means \"not stated\" (CX-06 map).",
     "Under (iv) 16 items offer it: 9 with their own signed rule, 7 with the signed has_* rule re-used verbatim "
     "(\"not_documented: the page is silent.\"), so no new wording; 35 items do not, each with a recorded reason "
     "(a real value, an `unknown` rule that already covers silence, a frozen CX answer set, or the applicability table)."],
    ["RC-D-005 12 a", "procurement_status rules/2", "CX-06 map (vocabularies.missing.cx_mapping_row)",
     "R-044 (all parts not covered -> not documented)", "fixes-r4 FX06 per-item `unknown` rules", "r2#8 applicability table"],
    ids(lambda f: f["ruling"].startswith("12a'")),
    notes="Re-used text, not new wording: items/core.has_human_oversight/rules/2, added to model_origin, build_arrangement, "
          "deployment_mode, target_users, governed_population, governance_form, observed_actor_role.")
res("F8", "16 signed rules say when the answer is `unknown`, but under 12 a `unknown` is mechanical",
    {"a": "drop / retag", "b": "keep"}, "b",
    ["The rules stay true as statements of the outcome: a page that mentions a matter without settling it leaves the "
     "classifier below the 0.8 bar, so the row gets `unknown` mechanically.",
     "Retagging them out of the prompt would break the ruling 2 a condition (every value carries the item's full rules); "
     "dropping them would remove signed text.",
     "The year items keep the computed candidate `unknown` among their choices, as their signed values and rule 1 say (C16); "
     "this is the one place `unknown` is offered, recorded in vocabularies.missing.jev_choice.resolution and as a SPEC addition."],
    ["ruling 2 a (check 16)", "R-081", "C16", "items/core.year_*/values, rules/0"],
    ids(lambda f: "F8" in f["ruling"]))
res("R1 = F4", "`pooled_activity_fields`", {"a": "derived/pipeline item, rules only", "b": "values + question"}, "a",
    ["Ruling 10 a: each pooled field combines by its own item's rule, so the item has no answers of its own; giving it "
     "values would need a new coding choice.",
     "W43 (approved) is kept as the item's instruction slot, read as the framing sentence of the pooled prompts."],
    ["RC-D-005 10 a", "r2#6", "X31", "W43 note"], ids(lambda f: f["ruling"].startswith("R1")))
res("R2 = F3", "Observed-actor relationship with two linked parts",
    {"a": "role as its own internal item gated on relationship != unresolved; W10 its question",
     "b": "template parts form"}, "b",
    ["The signed item is \"two linked parts in one item\" (activity-14 b; values.structure, role_gate, role_missing_tokens, "
     "long_page_rule.role_part); the parts form keeps all of it and adds only the order of the parts and the role question (W10).",
     "(a) would create a third attribution item beside `observed_actor_role` (the observed actor's own role, activity-15 a) "
     "and move signed values out of the item.",
     "W10's proposed path (values/searched_institution_role/instruction) cannot hold a key because that key is the value "
     "list; it sits at values/part_instructions/searched_institution_role."],
    ["activity-14 b", "activity-15 a", "fixes-r4 FX08", "O8"], ids(lambda f: f["ruling"].startswith("R2")))
res("N1", "Tie sentence \"If several values fit, take the first in this order\"",
    {"a": "every single-answer question", "b": "only where value order = combine order", "c": "none"}, "c",
    ["The approved drafts W05-W43 leave it out; adding it is new wording.",
     "For seven items the value order is not the combining order, so (a) would make the within-part and across-part "
     "choices disagree; (b) would add a sentence to very few items for no gain in consistency.",
     "`order_tie_rule` stays as data; the value and priority orders act when parts are combined (R-044)."],
    ["W05-W43 as approved", "R-044", "item-template field 15"])
res("I5", "`incident_kind` definitions reuse outcome wording and pull against `discontinuation_uncertain`",
    {"a": "redraft definitions", "b": "keep"}, "b",
    ["The definitions are the frozen CX-61 texts; redrafting them changes signed questionnaire wording.",
     "The approved question W35 names what an incident is (\"an error, failure or controversy\"), so the frozen result "
     "wording reads as the incident's result.",
     "The two texts can both hold: a confirmed stop with no problem reported is `none_reported` (\"ignores stops unless a "
     "problem is reported\"); a possible stop the page does not confirm is `discontinuation_uncertain` (C2 a)."],
    ["CX-61 (frozen)", "C2 a", "W35"])
res("I7", "source_type `other`: \"explain in `source_snippet`\" while jev returns codes only",
    {"a": "drop the clause", "b": "move the explanation to the extractor"}, "a",
    ["C-004: jev returns codes only, so the classifier cannot do the second half.",
     "The cut follows the PI's \"2a\" method (cut before the part that cannot stand) and needs no new wording; (b) would "
     "need a new extractor instruction."],
    ["C-004", "PI 2026-10-30 \"2a\" (cut before the overridden part)"], ids(lambda f: f["ruling"].startswith("I7")))
res("F5 source_type", "Rule-only gate on `source_type`", {"a": "new item recording automatic typing as the gate",
                                                          "b": "gate none, rules/0 carries the condition"}, "b",
    ["rules/0 already says the classifier only sorts pages not typed from the domain or address; R-002 assigns the "
     "condition to the pipeline. No new item or wording is needed.",
     "The former gate text is kept as data (`ask_condition`) pointing at rules/0."],
    ["R-002", "r2#25", "r2#30"], ids(lambda f: f["ruling"].startswith("F5 source_type")))
res("F5 second_reason", "Rule-only gate on `support_status_second_reason`",
    {"a": "gate none, F10 rule carries it", "b": "gate on `downgraded_*`"}, "a",
    ["A gate on the main status being downgraded is necessary but not sufficient (two reasons must hold), and gated-out rows "
     "would store \"not asked\", while the signed rule says the item is empty when only one reason holds.",
     "The former gate text is kept as data (`fill_condition`) pointing at rules/1."],
    ["R-041", "record-03 c", "final-open F10", "RC-D-003 O13"], ids(lambda f: f["ruling"].startswith("F5 second")))
res("F9", "Ruling-style text in rule slots without a `direction` role", {"a": "drop as 13 a", "b": "keep"}, "b",
    ["13 a dropped drafter directions (tagged `direction`); these texts are the PI's chosen ruling options, signed as rules.",
     "Several are the only statement of their item's rule (unit_credit rules/0, date_upper_bound rules/0, observed_actor_role "
     "rules/0); dropping them would leave items undefined or fail check 9.",
     "None is contradicted by a later ruling, unlike F10."],
    ["RC-D-005 13 a (scope: drafter notes)", "PI 2026-10-30 \"2a\""])
res("F10", "`reported_outcomes` / `reported_incidents` rules/1 describe a folded-away question",
    {"a": "drop", "b": "keep"}, "a",
    ["The signed kind items say the separate existence question folds into them (outcome_kind / incident_kind rules/0 and "
     "/1, CX-61); rules/1 still describes that question with other values and would reach the extractor prompt.",
     "Dropping the whole text is the limit case of the PI's \"2a\" method (cut the overridden part); its one live point "
     "(extract only when the kind is not `none_reported`) is carried by the gate and by the kind items' rules/0."],
    ["CX-61", "outcome_kind rules/0-1", "PI 2026-10-30 \"2a\""], ids(lambda f: f["ruling"].startswith("F10")))
res("W32 note", "Permanent pilot: pilot year as production year?", {"a": "add a rule", "b": "leave to the page"}, "b",
    ["The approved question asks for the year the page says the activity went into full, routine operation; adding a "
     "rule would be new wording and a coding choice.",
     "`permanent_pilot` is a derived flag (R-006), so analyses can still find these rows."],
    ["W32 as approved", "R-006"])
res("W33 note", "Scale number shown with the unit question?", {"a": "yes, as row data", "b": "generator fills the number into the text"},
    "a", ["rules/0: the extractor returns the number span and jev gives the unit; the question (approved) refers to \"the stated number\".",
          "Showing it as data needs no wording; filling it into the text would be undeclared scaffolding (check 3)."],
    ["R-040 (C4 a)", "deployment_scale_unit rules/0"], ids(lambda f: f["ruling"].startswith("W33")))
res("W04 note", "System prompt's page framing vs Stage 6 inputs",
    {"a": "Stage 6 variant with sentence 2 replaced", "b": "one prompt for all", "c": "leave Stage 6 open"}, "a",
    ["Stage 6 reads two activity records or pooled quotes, not a page, so W04's sentence 2 would misstate the input.",
     "The variant keeps W04's sentences 1, 3 and 4 byte for byte and replaces only sentence 2 (new text N-01, shown in the clean copy)."],
    ["RC-D-005 6 a", "W04 note", "W42, W43"], ids(lambda f: "W04 note" in f["ruling"]),
    new_text=FX["resolver_texts"]["N-01"])
res("E1", "EVAL_EMPHASIS with the six evaluation-type questions", {"default": "byte for byte"}, "default",
    ["Appended to each of W36-W41 in the instruction slot, as the frozen CX-01.2 template appends it (pilot.py L210); "
     "the W text stays byte-identical as the prefix."],
    ["CX-01.2 (frozen)", "pilot.py L181-187, L210"], ids(lambda f: "E1" in f["ruling"]))
for lab, txt, enc in (("F1 a", "values none on mechanical / derived items (template A1); support_status names its vocabulary", ids(lambda f: f["ruling"].startswith("F1"))),
                      ("F2 a", "computed value list for the year classifiers (template A2); no data change", []),
                      ("F6 a", "\"any value\" gate form (template A3); scale unit gate", ids(lambda f: f["ruling"].startswith("F6"))),
                      ("F7 a", "check 1 accepts missing_tokens none (template A4); no data change", []),
                      ("G1", "generator honours jev_choice false and jev_missing_choice, writes part prompts and system prompts (template A7)", [])):
    res(lab, txt, {"a": "procedural default"}, "a", ["Applied as the procedural default; coherent with the resolutions above."],
        ["RC-D-005 follow-ups (procedural)"], enc)
res("A5", "Check 7 when a gate item has no classifier round (scale unit gated on the extracted number)",
    {"a": "gate item takes its own gate's position"}, "a",
    ["Needed for coherence with F6 a: the extracted number exists once its own gate (activity_type, pass 2 round 2) is "
     "answered, so the unit (round 4) is correctly later. Not among the listed defaults; logged as required by coherence."],
    ["item-template §4 check 7", "combining_conventions.gate_items_first (\"and the scale number\")"])

T020 = [
    ("T1", "32k = 32,000 tokens (configurable)", "confirm", "C-004 states the 32k state limit; a pipeline setting, recorded in SPEC C-004 (E5)."),
    ("T2", "mixed-script pages use per-character constants and margins", "confirm", "An implementation estimate of the token limit; script handling belongs to the multilingual subproject. No codebook text."),
    ("T3", "yes/no any-yes fallback rank: yes, no, not documented, unknown", "confirm", "R-044 / all-04 b: real answers first, then not documented, then unknown. SPEC addition (E3)."),
    ("T4", "0.8 bar applies to every classifier answer incl. `no` / `not_documented`", "confirm", "R-081 (\"includes negative and absence codes\"); an offered `not_documented` below 0.8 becomes `unknown`. SPEC addition (E1)."),
    ("T5", "a quote not found exactly in its own part counts as no quote", "adjust", "R-042 is a fuzzy presence match, not an exact one: a quote counts if it passes the R-042 match against the part that produced the answer (R-044); otherwise no quote. SPEC addition (E3)."),
    ("T6", "most-sure-part rule also under first-section", "confirm", "R-044 / all-05 a apply to every rule type: among parts giving the winning answer, quote and certainty come from the most sure part. No new text."),
    ("T7", "mapped values carry no single quote but list input parts", "confirm", "Each input was checked before combining (all-03 a); the mapped value lists the input parts and their quotes. SPEC addition (E3)."),
    ("T8", "governance mapping implements only the explicit pair (vs SPEC's \"any condition or mix\")", "confirm", "The signed codebook (the source of record for orders) has the priority order with restricts_with_conditions first (any condition wins) and the mapping prohibits + permits -> restricts_with_conditions (the mix). SPEC R-044 wording aligned to the codebook (E3)."),
    ("T9", "undated pooled evidence position (first / last)", "decide: last", "A first-section rule should not let an undated source pre-empt dated ones; undated sources already score low credibility (source_credibility rule). Order: dated sources by date, then undated, each by page order. SPEC addition (E3)."),
    ("T10", "text-list dedup exact-string only", "confirm", "Quotes are verbatim; any normalisation would rewrite them. SPEC addition (E3)."),
    ("T11", "\"not asked\" / `_NA_` never reach part answers", "confirm", "combining_conventions.missing_rank: applicability is applied after the gating item is combined; `_NA_` rows have no activity to ask about. No new text."),
]
for tid, reading, verdict, why in T020:
    res(f"T-020 {tid}", reading, {"confirm": "confirm", "adjust": "adjust"}, verdict, [why], ["SPEC v001.8 R-042, R-044, R-081, C-004"])

out = {"format": "resolutions-r6 v1", "drafted_by": "resolver subagent of the plan integrator, Claude Code, claude-opus-5-5, 2026-10-30",
       "ruling": FX["ruling"], "status": "proposed; nothing final until the PI approves planning/t010/RC-D-005-clean-copy.md",
       "coherence_rules": ["prefer the option that changes the least signed meaning and follows prior PI rulings",
                           "where equally coherent, prefer no new wording",
                           "new wording minimal, origin agent-draft (resolver), listed in the clean copy"],
       "fixes_file": "planning/t010/drafts/fixes-r6.json", "resolutions": R}
(D / "resolutions-r6.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(len(R), "resolutions")
