"""Build rc-d-005-wording.md / .json from one entry list (agent draft, RC-D-005 3 a / 4 / 5 a / 6 a)."""
import json
import sys
import yaml

ROOT = "C:/Users/spaci/worktrees/G3O-integrator/"
CB = yaml.safe_load(open(ROOT + "codebook/codebook.yaml", encoding="utf-8"))
ITEMS = CB["items"]

UNCLEAR2 = "agent-workspace/2026-10-27-unclear-screen/unclear2.py"
SYS = "g3o/extract/prompts/system_prompt.md"
OC = "g3o/extract/prompts/output_contract.md"
CXJ = "planning/t010/drafts/cx-01.3-draft.json"

# ---- shared entries -------------------------------------------------------
SHARED = [
    dict(path="shared/part_prompt/sentence",
         title="Part-prompt sentence (R-044 marker, RC-D-003 §2)",
         text="The text below is only one part of a longer page; the rest of the page is read separately. Answer from this part only.",
         source=f"new; part label idea from {UNCLEAR2} L98, L128 (`page_part` = \"1 of 3\")",
         note="Optional variant with the part number, if the generator may fill it: \"The text below is part {i} of {n} of a longer page; ...\". A filled-in number is generator scaffolding, which check 3 allows only if it is declared. \"Answer from this part only\" is my addition: it tells the model not to guess about the other parts, which is what makes the temporary answer work. Delete it if you read it as a new rule."),
    dict(path="shared/part_prompt/temporary_answer/label",
         title="Temporary answer: label",
         text="not covered by this part",
         source="SPEC R-044 (label as written there)",
         note="Kept exactly as SPEC R-044 and item-template check 16 spell it."),
    dict(path="shared/part_prompt/temporary_answer/meaning",
         title="Temporary answer: meaning shown to the model",
         text="This part of the page does not deal with the question; another part of the page may.",
         source="new",
         note="Written to stay apart from \"not documented\" (the whole page is silent). If every part gives this answer, R-044 turns it into \"not documented\" for the page."),
    dict(path="shared/system_prompt",
         title="Shared system prompt (extractor and classifier)",
         text=("You are a research coder for the Global Government GenAI Observatory (G3O), a public, auditable dataset that measures "
               "how government institutions worldwide adopt generative AI. You read one web page, or one part of one, about a named "
               "institution and answer coding questions about it. Use only what the text says: record what it states explicitly "
               "and never infer, guess or use outside knowledge. Give each answer in the form the question asks for and nothing else: "
               "for a question with listed answers, choose from those answers only; for an extraction, copy the exact words from the text."),
         source=f"{SYS} L3 (mission sentence, shortened), L39 (\"Only record what is explicitly documented. Never infer\"), L69 (\"Return ONLY ...\"); {UNCLEAR2} L84 (\"using only what the page says\")",
         note="Three parts as ruled (6 a): role (sentence 1), task framing (sentences 2-3), output format (sentence 4). I left out the v2.5 GenAI-boundary and attribution prose: those are signed rules that the item prompts already carry (check 16). For Stage 6 the second sentence does not fit (the input is two activity records or pooled quotes, not a page); you may want a second variant, or \"one web page ... or a set of records\"."),
]

# ---- item entries: id -> (question, source, note) --------------------------
Q = {}
def q(item, text, source, note, path=None, title=None):
    Q.setdefault(item, []).append(dict(text=text, source=source, note=note, path=path, title=title))

# disclosure
q("core.disclosure_scope",
  "How many institutions does the listing or document this page belongs to cover?",
  f"{CXJ} row \"pilot.py L196 page_questions disclosure_scope instructions\" (frozen CX-01.2 question), with the \"Code the source PAGE.\" lead-in dropped",
  "Same trimming as the signed sibling question on document kind, which also dropped the lead-in. \"How many\" is the frozen wording; the answers are ranges (government-wide / several / one), not counts.")
q("core.content_contact_named",
  "Does the page name a person, office or unit as responsible for a GenAI activity it mentions, or for questions about it?",
  f"{CXJ} row \"contact.py L42 contact question instructions\" (\"Does the page give this: {{v}}?\") with {{v}} = contact.py L30 w4a wording",
  "Page-level item, so \"the activity\" of the definition became \"a GenAI activity it mentions\" (the signed page-completeness question uses the same phrase). The definition's \"a named official with no contact details counts\" stays in the definition, not the question.")
q("core.content_contact_details",
  "Does the page give any contact details anywhere on it, such as an email address, phone number, postal address or contact form?",
  f"{CXJ} row \"contact.py L42 contact question instructions\" with {{v}} = contact.py L31 w4b wording",
  "\"Anywhere on it\" covers the header and footer text this item reads; the definition names press, vendor and footer contacts, so the question does not repeat them.")

# source
q("core.source_type",
  "What kind of source is this page?",
  f"{OC} L123 column description (\"Category of the source.\") turned into a question",
  "Close to the signed document-kind question (\"What kind of document is this page?\"); both are asked in pass 1. If you want them told apart, an option is \"Who published this page, or what kind of record is it?\" — the values mix publisher types (news, vendor, academic) and record types (tender). Government and archived pages are typed before this question, so the question does not mention them.")

# attribution
q("core.observed_actor_relationship",
  "Whose activity is this, according to the page: the named institution's own, one of its units', a joint one it takes part in, or another body's?",
  "new",
  "Relationship part only. The definitions say \"searched institution\"; the question says \"named institution\", as the signed page-verdict question does. The list in the question is a plain paraphrase of the four real values; \"unresolved\" is left to the definitions. Delete the list if you want the bare question \"Whose activity is this, according to the page?\".")
q("core.observed_actor_relationship",
  "What part does the named institution play in this activity?",
  "new",
  "Second part of the same item (the role of the named institution; asked unless the relationship is unresolved). The item has one instruction slot but two linked parts, so the path is a proposal: see \"Needs a ruling\" R2.",
  path="items/core.observed_actor_relationship/values/searched_institution_role/instruction",
  title="core.observed_actor_relationship — role part")
q("core.observed_actor_role",
  "What role does the body that the page shows acting in this activity play in it?",
  "new",
  "\"The body that the page shows acting\" is my plain rendering of \"observed actor\" (the actor seen on the page, as opposed to the named institution). Internal item, not published.")

# activity typing
q("core.action_type",
  "What kind of action is this activity?",
  "new",
  "Bare question; the four definitions (putting a tool to use, a rule on GenAI use, staff training, a program with named components) do the work.")
q("core.adoption_stage",
  "What stage has this activity reached, according to the page?",
  "new; \"Record the most current status\" idea from " + SYS + " L54",
  "\"Has reached\" points at the latest stage, matching the long-page order (discontinued first). The permanent-pilot rule stays in the rules.")
q("core.procurement_status",
  "What purchase step, if any, does the page record for this activity's tool or service?",
  "new",
  "\"If any\" makes room for the real answer \"none documented\" (page describes the activity, no purchase step). See inconsistency I3: this item's rules say \"not documented\" is not used for it.")
q("core.service_domain",
  "Which areas of government work does this activity concern? Choose all that apply.",
  "new",
  "\"Concern\" rather than \"serve\" so that internal tools and policies fit (general public services covers internal administration). \"Choose all that apply\" because the item is multi-select.")

# tool
q("core.model_origin",
  "Where does the model behind this activity's tool come from?",
  f"new; value wording follows {OC} §4.4 (access_type)",
  "")
q("core.build_arrangement",
  "How was this activity's tool built?",
  "new",
  "Bare question; an off-the-shelf product counts as \"built\" only in the loose sense — if that jars, an option is \"How did the institution get or build this activity's tool?\".")
q("core.interface",
  "How do users reach this activity's tool?",
  "new",
  "Matches the wording of the third value (\"Users reach the tool in another way ...\").")
FUNCS = {
    "core.function_drafting_writing": "drafting or writing text",
    "core.function_summarization": "summarising documents, reports or meetings",
    "core.function_translation": "translating text or speech between languages",
    "core.function_search_retrieval": "finding information",
    "core.function_code": "writing, reviewing or fixing software code",
    "core.function_image_audio_video": "creating or editing images, audio or video",
    "core.function_extraction_classification": "pulling information out of documents or forms, or sorting and classifying them",
    "core.function_analysis_recommendation": "analysing information or giving recommendations or scores to support human decisions",
}
for k, v in FUNCS.items():
    q(k, f"Does the page state that this activity's tool is used for {v}?",
      "new; the task phrase is copied from the item's own `yes` definition (examples left in the definition)",
      "One stem for all eight function items, so they read alike. See inconsistency I1 (`no` and \"not documented\" mean the same here).")

# governance
q("core.governed_population",
  "Whom does this rule on GenAI use apply to?",
  "new",
  "\"Rule\" follows the value definitions (\"The rule applies to ...\"); the item is asked only for governance actions.")
q("core.governance_form",
  "What form does this rule on GenAI use take? Choose all that apply.",
  "new",
  "Multi-select, hence \"Choose all that apply\".")
q("core.governance_direction",
  "Does this rule ban, limit, allow, require or encourage the GenAI use it covers?",
  "new",
  "The five verbs paraphrase the five values in their order. \"Limit\" stands for \"restricts with conditions\", which also covers a ban on some uses with others allowed; that stays in the definition.")

# verdict family (activity)
q("core.genai_mechanism_basis",
  "What on the page shows that this activity's tool is generative AI?",
  "new",
  "The values are a strength order (named product first). See note N1 on whether to add \"If several fit, take the first in this order\" — here the value order and the long-page order agree, so adding it is safe.")

# dates
q("core.year_pilot_start",
  "In which year does the page say a pilot or trial of this activity began?",
  "new; replaces the copied announced-year question (ruling 4)",
  "\"Pilot or trial\" follows the pilot stage definition (\"trial/pilot/PoC/experiment\"). Asked only for activity types the applicability table marks; governance is not asked.")
q("core.year_production_start",
  "In which year does the page say this activity went into full, routine operation?",
  "new; replaces the copied announced-year question (ruling 4)",
  "\"Full, routine operation\" paraphrases the production stage definition. Open point, not decided here: whether a \"permanent pilot\" (coded production under the stage rule) gives its pilot start year as its production year. The question as drafted would leave that to the page.")

# scale
q("core.deployment_scale_unit",
  "What does the stated number for this activity count?",
  "new; follows the item rule (\"jev Choice gives the unit\" for the extracted number)",
  "Assumes the number the extractor found is shown to the model with the question (rule 1). If it is not, the question needs the number filled in by the generator: \"What does the number '{number}' count?\".")

# outcomes
q("core.outcome_kind",
  "Does the page report a result of this activity, and if so, what kind?",
  "new; \"does the page report an outcome ... of this activity\" from item rule 3 (direction), shortened",
  "\"Result\" matches the value definitions (\"states a measured or numeric result\"). The one question answers both whether and what kind, as the rule says.")
q("core.incident_kind",
  "Does the page report an incident with this activity, such as an error, failure or controversy, and if so, what kind?",
  f"new; \"errors, failures, or controversies\" from {OC} L112 (reported_incidents column description)",
  "The signed definitions never say what an incident is, so I took the v2.5 column description; delete the \"such as\" clause if you do not want it in the question. See inconsistency I5.")

# evaluation types
EVT = {
    "core.evaluation_type_pre_deployment_testing": "testing before deployment",
    "core.evaluation_type_pilot_evaluation": "evaluation of a pilot or trial",
    "core.evaluation_type_independent_audit": "an audit or evaluation by an independent body",
    "core.evaluation_type_ongoing_monitoring": "ongoing monitoring of the tool in use",
    "core.evaluation_type_user_feedback": "user feedback or satisfaction surveys",
    "core.evaluation_type_bias_or_safety_testing": "bias, fairness or safety testing",
}
for k, v in EVT.items():
    q(k, f"The page documents an evaluation of this GenAI activity, or a requirement or plan for one. Does it document an evaluation of this type: {v}?",
      f"{CXJ} row \"pilot.py L210 type_questions instructions\" (frozen CX-01.2 template), with {{v}} = the type phrase from the item's `yes` definition; \"the named GenAI activity\" changed to \"this GenAI activity\" to match the signed evaluation question",
      "Frozen-instrument wording (CX-41), so kept nearly word for word. The frozen template also appends `EVAL_EMPHASIS` (pilot.py L181-187), whose text I could not see in the drafts; the integrator should say whether it is carried. See inconsistency I1.")

# activity identity (stage 6)
q("core.activity_relation_cross_page",
  "How is the activity in the first record related to the activity in the second record?",
  "new",
  "The definitions speak of \"the first record\" and \"the second record\", so the question does too. See inconsistency I4 on \"not documented\".")
q("core.pooled_activity_fields",
  "The text below is a set of quotes about one activity, gathered from several sources, each with its source type and date. Answer each question about the activity from these quotes only.",
  "new; framing from item rule 1 (\"the union of the activity's supported quotes from all its sources (state = quotes with source type and date)\")",
  "Not a question: this item has no values. Drafted only as a framing sentence in case you rule it should have one. See \"Needs a ruling\" R1.")

# year rule texts
RULE1 = ITEMS["core.year_pilot_start"]["rules"][0]["text"]
assert RULE1 == ITEMS["core.year_production_start"]["rules"][0]["text"]
OLDQ = "\"In which year does the page say this activity was first announced?\""
assert OLDQ in RULE1
RULES = [
    ("core.year_pilot_start", "\"In which year does the page say a pilot or trial of this activity began?\""),
    ("core.year_production_start", "\"In which year does the page say this activity went into full, routine operation?\""),
]

FAMILY_ORDER = ["disclosure", "source", "attribution", "activity_typing", "tool", "governance", "verdict", "dates", "scale", "outcomes", "evaluation", "activity_identity"]
FAMILY_TITLE = {"disclosure": "Disclosure (page)", "source": "Source", "attribution": "Attribution", "activity_typing": "Activity typing",
                "tool": "Tool", "governance": "Governance", "verdict": "GenAI basis", "dates": "Dates", "scale": "Scale",
                "outcomes": "Outcomes and incidents", "evaluation": "Evaluation types", "activity_identity": "Activity identity (Stage 6)"}


def codes(it):
    v = it["values"]
    if isinstance(v, list):
        return " / ".join(x["code"] for x in v)
    if isinstance(v, dict) and "relationship" in v:
        return ("relationship: " + " / ".join(x["code"] for x in v["relationship"]) +
                "; role: " + " / ".join(x["code"] for x in v["searched_institution_role"]))
    if isinstance(v, dict) and "candidates" in v:
        return "candidate years (" + v["candidates"] + ")"
    return str(v)


def gate(it):
    g = it.get("gate")
    if g in (None, "none"):
        return "none"
    if "table" in g:
        na = [k for k, c in g["cells"].items() if c != "ask"]
        return "applicability table" + (f" (not asked: {', '.join(na)})" if na else " (asked for all types)")
    if "item" in g:
        return f"{g['item']} in {g.get('values')}"
    return g.get("rule", str(g))


def main():
    targets = [v for v in ITEMS.values() if v.get("coder") == "classifier" and v.get("instruction") == "none"]
    assert len(targets) == 38, len(targets)
    assert set(Q) == {v["id"] for v in targets}, set(Q) ^ {v["id"] for v in targets}
    out_json, md = {}, []
    n = 0

    def nid():
        nonlocal n
        n += 1
        return f"W{n:02d}"

    md.append(SHARED_MD_HEAD)
    md.append("## A. Shared texts (part prompts, system prompt)\n")
    for e in SHARED:
        w = nid()
        out_json[w] = {"path": e["path"], "text": e["text"], "origin": "agent-draft", "source": e["source"]}
        md.append(f"### {w} — {e['title']}\n\n- Path: `{e['path']}`\n- Draft:\n\n  > {e['text']}\n\n- Source: {e['source']}\n- Note: {e['note']}\n")

    md.append("## B. Questions for the 38 classifier items, by family\n")
    fams = {}
    for it in targets:
        fams.setdefault(it["family"], []).append(it)
    assert set(fams) <= set(FAMILY_ORDER), set(fams) - set(FAMILY_ORDER)
    for f in FAMILY_ORDER:
        if f not in fams:
            continue
        md.append(f"### Family: {FAMILY_TITLE[f]}\n")
        for it in fams[f]:
            for e in Q[it["id"]]:
                w = nid()
                path = e["path"] or f"items/{it['id']}/instruction"
                out_json[w] = {"path": path, "text": e["text"], "origin": "agent-draft", "source": e["source"]}
                title = e["title"] or it["id"]
                md.append(f"#### {w} — {title}\n\n- Level: {', '.join(it['level'])}; answer: {it['answer_type']}; pass {it['pass']}, round {it['round']}; gate: {gate(it)}\n"
                          f"- Values: {codes(it)} (+ not documented offered, 12 a)\n- Path: `{path}`\n- Draft:\n\n  > {e['text']}\n\n- Source: {e['source']}\n"
                          + (f"- Note: {e['note']}\n" if e["note"] else ""))

    md.append("## C. Year items: rule 1 with the replacement question (ruling 4)\n\n"
              "Rule 1 of both year items is a copy of the announced-year rule and embeds the announced-year question. Only the quoted question changes; the rest of the rule is kept byte for byte. "
              "Open point for the integrator (P1-type, not wording): the rule still says \"jev Choice over those years plus `unknown`\", while 12 a makes `unknown` mechanical and offers \"not documented\" instead; the same words sit in the signed announced-year rule.\n")
    for item, newq in RULES:
        w = nid()
        text = RULE1.replace(OLDQ, newq)
        src = f"items/{item}/rules/0/text (signed text), question swapped for the draft in the item's own entry"
        out_json[w] = {"path": f"items/{item}/rules/0/text", "text": text, "origin": "agent-draft", "source": src}
        md.append(f"### {w} — {item}, rule 1\n\n- Path: `items/{item}/rules/0/text`\n- Draft:\n\n  > {text}\n\n- Source: {src}\n")

    md.append(TAIL_MD)
    open(ROOT + "planning/t010/drafts/rc-d-005-wording.md", "w", encoding="utf-8", newline="\n").write("\n".join(md))
    open(ROOT + "planning/t010/drafts/rc-d-005-wording.json", "w", encoding="utf-8", newline="\n").write(
        json.dumps({"_meta": META, "entries": out_json}, ensure_ascii=False, indent=1) + "\n")
    print("entries", n)


META = {
    "delta": "RC-D-005 (rulings 3 a, 4, 5 a, 6 a, 12 a; PI 2026-10-30)",
    "status": "agent draft for PI edit; nothing here is final",
    "codebook": "codebook/codebook.yaml release 2.7 sha256 d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764",
    "drafted_by": "drafting subagent of the plan integrator, Claude Code, claude-opus-5-5, 2026-10-30",
    "fold_rule": "fold an entry only after the PI edits or confirms it; set origin to 'pi' (or the agreed tag) at fold",
}

SHARED_MD_HEAD = """# RC-D-005 wording drafts: classifier questions, part-prompt texts, system prompt

Status: AGENT DRAFT, for Simone to read, edit and confirm line by line (RC-D-005 rulings 3 a, 4, 5 a, 6 a; PI 2026-10-30). Nothing here is final.
Drafted 2026-10-30 by a drafting subagent of the plan integrator (Claude Code, claude-opus-5-5). Codebook read: `codebook/codebook.yaml`, release 2.7, sha256 `d24bbc7c…0764` (confirmed). Machine-readable twin: `rc-d-005-wording.json` (same W numbers).

How to reply: "W07: <new text>", "W07 ok", or "W07: drop". Value definitions and rules are not touched; every question only sits in front of the signed definitions.

Count: 38 classifier items with `instruction: none` (confirmed), one extra entry for the role part of the observed-actor relationship, 2 year rule texts, part-prompt sentence, temporary answer (label + meaning), system prompt = 45 entries.

## General notes (N1-N3; reply "N1: …")

- **N1 — tie sentence.** I did not add "If several values fit, take the first in this order" to any question. Every item carries `order_tie_rule: first_in_order`, but for seven items the value order is not the long-page priority order, so the sentence would pick differently within a page than across parts: adoption stage (value order starts at `proposed`, combining starts at `discontinued`), purchase status, build arrangement, governance direction, incident kind, observed-actor relationship (`other` before `unresolved` in values, the reverse in combining) and the cross-page relation. Choose: add it to every single-answer question, add it only where the orders agree (e.g. the GenAI basis item), or leave it to the generator.
- **N2 — "this activity".** Activity questions say "this activity" / "this activity's tool", as the signed announced-year and evaluation questions do; they assume the activity's name and span are in the question's input. Page questions say "this page" / "the page".
- **N3 — "not documented" in the question.** No question mentions "not documented" or "unknown"; the offered "not documented" choice carries its own meaning (12 a). See I1-I4 for items where that choice overlaps a real value.
"""

TAIL_MD = """## Needs a ruling

- **R1 — `pooled_activity_fields` (W43 framing only).** The item has `values: none` and no question of its own: by its rule 1 and your ruling 10 a, jev asks each activity question again over pooled quotes, with each field's own rule. It cannot get a question without a coding choice. As a `classifier` item with no values it also fails generator check 9. Options I see: (a) make it a non-classifier item (rule only), with W43 as the framing sentence of pooled prompts if you want one; (b) retire it into the Stage 6 rules. I drafted nothing beyond the framing sentence.
- **R2 — observed-actor relationship, role part (W10).** The item has two linked parts but one instruction slot, and a jev question returns one code (functions rule). Asking the role needs a second question; the codebook has no slot for it. I drafted it under a proposed path (`values/searched_institution_role/instruction`); where it lives is a structure choice.

## Signed definitions that sit badly with a question (or with the offered "not documented")

- **I1 — yes/no items whose `no` means "the page does not state".** The 8 function items, the 6 evaluation-type items and the 2 contact items define `no` as the page not stating the thing, which is what "not documented" means. Offering "not documented" too (12 a) gives the model two choices with one meaning. The CX-06 map already sends `no` of the evaluation-type and `content_*` items to "not documented".
- **I2 — no "not documented" meaning for most items.** 12 a says the offered choice is defined by each item's missing-label rule, but only 4 of the 38 items have one ("A silent page gets 'not documented' …": the relationship, interface, governance direction, service domain); most others have a missing-label rule for `unknown` only. The other items need a meaning for "not documented", or a shared one.
- **I3 — purchase status.** Its rules say "`not_documented` is not used for this item" (a page with no purchase step is `none_documented`), but 12 a offers "not documented" on every item, and its long-page order still lists it.
- **I4 — items where "not documented" has no clear sense.** Cross-page relation (the answer is about a pair of records; `unresolved` already covers "cannot tell"; its long-page order has no `not_documented`); the scale unit (asked only when a number is stated; `none` already covers a number in none of the units); source type (every page has a source); the year items (the rule offers years plus `unknown`).
- **I5 — incident kind.** Its values are copied from the outcome item ("states a measured or numeric result", "states no result"), so they speak of results, not incidents. And its rule "The incident question ignores stops unless a problem is reported" seems to pull against the value `discontinuation_uncertain` (a possible stop with no problem reported). The question (W35) works either way, but the definitions may need a look.
- **I6 — outcome and incident `none_reported`.** "States no result" and "not documented" overlap the way I1 does (CX-06 maps `none_reported` to "not documented").
- **I7 — source type `other`.** Its definition says "explain in `source_snippet`"; jev returns codes only (C-004), so the classifier cannot do that part.
"""

if __name__ == "__main__":
    main()
