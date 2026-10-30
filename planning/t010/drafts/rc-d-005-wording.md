# RC-D-005 wording drafts: classifier questions, part-prompt texts, system prompt

Status: AGENT DRAFT, for Simone to read, edit and confirm line by line (RC-D-005 rulings 3 a, 4, 5 a, 6 a; PI 2026-10-30). Nothing here is final.
Drafted 2026-10-30 by a drafting subagent of the plan integrator (Claude Code, claude-opus-5-5). Codebook read: `codebook/codebook.yaml`, release 2.7, sha256 `d24bbc7c…0764` (confirmed). Machine-readable twin: `rc-d-005-wording.json` (same W numbers).

How to reply: "W07: <new text>", "W07 ok", or "W07: drop". Value definitions and rules are not touched; every question only sits in front of the signed definitions.

Count: 38 classifier items with `instruction: none` (confirmed), one extra entry for the role part of the observed-actor relationship, 2 year rule texts, part-prompt sentence, temporary answer (label + meaning), system prompt = 45 entries.

## General notes (N1-N3; reply "N1: …")

- **N1 — tie sentence.** I did not add "If several values fit, take the first in this order" to any question. Every item carries `order_tie_rule: first_in_order`, but for seven items the value order is not the long-page priority order, so the sentence would pick differently within a page than across parts: adoption stage (value order starts at `proposed`, combining starts at `discontinued`), purchase status, build arrangement, governance direction, incident kind, observed-actor relationship (`other` before `unresolved` in values, the reverse in combining) and the cross-page relation. Choose: add it to every single-answer question, add it only where the orders agree (e.g. the GenAI basis item), or leave it to the generator.
- **N2 — "this activity".** Activity questions say "this activity" / "this activity's tool", as the signed announced-year and evaluation questions do; they assume the activity's name and span are in the question's input. Page questions say "this page" / "the page".
- **N3 — "not documented" in the question.** No question mentions "not documented" or "unknown"; the offered "not documented" choice carries its own meaning (12 a). See I1-I4 for items where that choice overlaps a real value.

## A. Shared texts (part prompts, system prompt)

### W01 — Part-prompt sentence (R-044 marker, RC-D-003 §2)

- Path: `shared/part_prompt/sentence`
- Draft:

  > The text below is only one part of a longer page; the rest of the page is read separately. Answer from this part only.

- Source: new; part label idea from agent-workspace/2026-10-27-unclear-screen/unclear2.py L98, L128 (`page_part` = "1 of 3")
- Note: Optional variant with the part number, if the generator may fill it: "The text below is part {i} of {n} of a longer page; ...". A filled-in number is generator scaffolding, which check 3 allows only if it is declared. "Answer from this part only" is my addition: it tells the model not to guess about the other parts, which is what makes the temporary answer work. Delete it if you read it as a new rule.

### W02 — Temporary answer: label

- Path: `shared/part_prompt/temporary_answer/label`
- Draft:

  > not covered by this part

- Source: SPEC R-044 (label as written there)
- Note: Kept exactly as SPEC R-044 and item-template check 16 spell it.

### W03 — Temporary answer: meaning shown to the model

- Path: `shared/part_prompt/temporary_answer/meaning`
- Draft:

  > This part of the page does not deal with the question; another part of the page may.

- Source: new
- Note: Written to stay apart from "not documented" (the whole page is silent). If every part gives this answer, R-044 turns it into "not documented" for the page.

### W04 — Shared system prompt (extractor and classifier)

- Path: `shared/system_prompt`
- Draft:

  > You are a research coder for the Global Government GenAI Observatory (G3O), a public, auditable dataset that measures how government institutions worldwide adopt generative AI. You read one web page, or one part of one, about a named institution and answer coding questions about it. Use only what the text says: record what it states explicitly and never infer, guess or use outside knowledge. Give each answer in the form the question asks for and nothing else: for a question with listed answers, choose from those answers only; for an extraction, copy the exact words from the text.

- Source: g3o/extract/prompts/system_prompt.md L3 (mission sentence, shortened), L39 ("Only record what is explicitly documented. Never infer"), L69 ("Return ONLY ..."); agent-workspace/2026-10-27-unclear-screen/unclear2.py L84 ("using only what the page says")
- Note: Three parts as ruled (6 a): role (sentence 1), task framing (sentences 2-3), output format (sentence 4). I left out the v2.5 GenAI-boundary and attribution prose: those are signed rules that the item prompts already carry (check 16). For Stage 6 the second sentence does not fit (the input is two activity records or pooled quotes, not a page); you may want a second variant, or "one web page ... or a set of records".

## B. Questions for the 38 classifier items, by family

### Family: Disclosure (page)

#### W05 — core.disclosure_scope

- Level: page; answer: single; pass 1, round 3; gate: core.disclosure_form in ['register_cross_institution', 'register_single_institution', 'mandated_report']
- Values: whole_of_government / multi_institution / single_institution (+ not documented offered, 12 a)
- Path: `items/core.disclosure_scope/instruction`
- Draft:

  > How many institutions does the listing or document this page belongs to cover?

- Source: planning/t010/drafts/cx-01.3-draft.json row "pilot.py L196 page_questions disclosure_scope instructions" (frozen CX-01.2 question), with the "Code the source PAGE." lead-in dropped
- Note: Same trimming as the signed sibling question on document kind, which also dropped the lead-in. "How many" is the frozen wording; the answers are ranges (government-wide / several / one), not counts.

#### W06 — core.content_contact_named

- Level: page; answer: yes_no; pass 1, round 2; gate: core.page_verdict in ['confirms_activity', 'ambiguous_genai', 'ambiguous_attribution', 'other_body', 'event_only']
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.content_contact_named/instruction`
- Draft:

  > Does the page name a person, office or unit as responsible for a GenAI activity it mentions, or for questions about it?

- Source: planning/t010/drafts/cx-01.3-draft.json row "contact.py L42 contact question instructions" ("Does the page give this: {v}?") with {v} = contact.py L30 w4a wording
- Note: Page-level item, so "the activity" of the definition became "a GenAI activity it mentions" (the signed page-completeness question uses the same phrase). The definition's "a named official with no contact details counts" stays in the definition, not the question.

#### W07 — core.content_contact_details

- Level: page; answer: yes_no; pass 1, round 2; gate: core.page_verdict in ['confirms_activity', 'ambiguous_genai', 'ambiguous_attribution', 'other_body', 'event_only']
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.content_contact_details/instruction`
- Draft:

  > Does the page give any contact details anywhere on it, such as an email address, phone number, postal address or contact form?

- Source: planning/t010/drafts/cx-01.3-draft.json row "contact.py L42 contact question instructions" with {v} = contact.py L31 w4b wording
- Note: "Anywhere on it" covers the header and footer text this item reads; the definition names press, vendor and footer contacts, so the question does not repeat them.

### Family: Source

#### W08 — core.source_type

- Level: source; answer: single; pass 1, round 2; gate: only pages not typed automatically from domain or address (r2#25)
- Values: news_major / news_trade / vendor / academic / policy_org / social_media / procurement_tender / other (+ not documented offered, 12 a)
- Path: `items/core.source_type/instruction`
- Draft:

  > What kind of source is this page?

- Source: g3o/extract/prompts/output_contract.md L123 column description ("Category of the source.") turned into a question
- Note: Close to the signed document-kind question ("What kind of document is this page?"); both are asked in pass 1. If you want them told apart, an option is "Who published this page, or what kind of record is it?" — the values mix publisher types (news, vendor, academic) and record types (tender). Government and archived pages are typed before this question, so the question does not mention them.

### Family: Attribution

#### W09 — core.observed_actor_relationship

- Level: activity; answer: single; pass 2, round 2; gate: none
- Values: relationship: this_institution / unit_of_institution / joint_participant / other / unresolved; role: contracting_authority / beneficiary / central_purchasing_body / unit / joint (+ not documented offered, 12 a)
- Path: `items/core.observed_actor_relationship/instruction`
- Draft:

  > Whose activity is this, according to the page: the named institution's own, one of its units', a joint one it takes part in, or another body's?

- Source: new
- Note: Relationship part only. The definitions say "searched institution"; the question says "named institution", as the signed page-verdict question does. The list in the question is a plain paraphrase of the four real values; "unresolved" is left to the definitions. Delete the list if you want the bare question "Whose activity is this, according to the page?".

#### W10 — core.observed_actor_relationship — role part

- Level: activity; answer: single; pass 2, round 2; gate: none
- Values: relationship: this_institution / unit_of_institution / joint_participant / other / unresolved; role: contracting_authority / beneficiary / central_purchasing_body / unit / joint (+ not documented offered, 12 a)
- Path: `items/core.observed_actor_relationship/values/searched_institution_role/instruction`
- Draft:

  > What part does the named institution play in this activity?

- Source: new
- Note: Second part of the same item (the role of the named institution; asked unless the relationship is unresolved). The item has one instruction slot but two linked parts, so the path is a proposal: see "Needs a ruling" R2.

#### W11 — core.observed_actor_role

- Level: activity; answer: single; pass 2, round 2; gate: none
- Values: institutional_actor / issuer / participant / external_speaker / service_provider / event_host (+ not documented offered, 12 a)
- Path: `items/core.observed_actor_role/instruction`
- Draft:

  > What role does the body that the page shows acting in this activity play in it?

- Source: new
- Note: "The body that the page shows acting" is my plain rendering of "observed actor" (the actor seen on the page, as opposed to the named institution). Internal item, not published.

### Family: Activity typing

#### W12 — core.action_type

- Level: activity; answer: single; pass 2, round 2; gate: none
- Values: deployment / governance / staff_training / program (+ not documented offered, 12 a)
- Path: `items/core.action_type/instruction`
- Draft:

  > What kind of action is this activity?

- Source: new
- Note: Bare question; the four definitions (putting a tool to use, a rule on GenAI use, staff training, a program with named components) do the work.

#### W13 — core.adoption_stage

- Level: activity; answer: single; pass 2, round 3; gate: applicability table (asked for all types)
- Values: proposed / announced / pilot / production / discontinued (+ not documented offered, 12 a)
- Path: `items/core.adoption_stage/instruction`
- Draft:

  > What stage has this activity reached, according to the page?

- Source: new; "Record the most current status" idea from g3o/extract/prompts/system_prompt.md L54
- Note: "Has reached" points at the latest stage, matching the long-page order (discontinued first). The permanent-pilot rule stays in the rules.

#### W14 — core.procurement_status

- Level: activity; answer: single; pass 2, round 3; gate: applicability table (asked for all types)
- Values: none_documented / tender_or_rfp / award_or_contract / payment_or_subscription (+ not documented offered, 12 a)
- Path: `items/core.procurement_status/instruction`
- Draft:

  > What purchase step, if any, does the page record for this activity's tool or service?

- Source: new
- Note: "If any" makes room for the real answer "none documented" (page describes the activity, no purchase step). See inconsistency I3: this item's rules say "not documented" is not used for it.

#### W15 — core.service_domain

- Level: activity; answer: multi; pass 2, round 3; gate: none
- Values: general_public_services / defence / public_order_safety / economic_affairs / environmental_protection / housing_community_amenities / health / recreation_culture_religion / education / social_protection / other (+ not documented offered, 12 a)
- Path: `items/core.service_domain/instruction`
- Draft:

  > Which areas of government work does this activity concern? Choose all that apply.

- Source: new
- Note: "Concern" rather than "serve" so that internal tools and policies fit (general public services covers internal administration). "Choose all that apply" because the item is multi-select.

### Family: Tool

#### W16 — core.model_origin

- Level: activity; answer: single; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: commercial / open_weight / government_developed (+ not documented offered, 12 a)
- Path: `items/core.model_origin/instruction`
- Draft:

  > Where does the model behind this activity's tool come from?

- Source: new; value wording follows g3o/extract/prompts/output_contract.md §4.4 (access_type)

#### W17 — core.build_arrangement

- Level: activity; answer: single; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: off_the_shelf_product / custom_application_on_external_model / model_trained_or_fine_tuned_by_institution (+ not documented offered, 12 a)
- Path: `items/core.build_arrangement/instruction`
- Draft:

  > How was this activity's tool built?

- Source: new
- Note: Bare question; an off-the-shelf product counts as "built" only in the loose sense — if that jars, an option is "How did the institution get or build this activity's tool?".

#### W18 — core.interface

- Level: activity; answer: single; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: conversational / backend_or_api / other_interface (+ not documented offered, 12 a)
- Path: `items/core.interface/instruction`
- Draft:

  > How do users reach this activity's tool?

- Source: new
- Note: Matches the wording of the third value ("Users reach the tool in another way ...").

#### W19 — core.function_drafting_writing

- Level: activity; answer: yes_no; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.function_drafting_writing/instruction`
- Draft:

  > Does the page state that this activity's tool is used for drafting or writing text?

- Source: new; the task phrase is copied from the item's own `yes` definition (examples left in the definition)
- Note: One stem for all eight function items, so they read alike. See inconsistency I1 (`no` and "not documented" mean the same here).

#### W20 — core.function_summarization

- Level: activity; answer: yes_no; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.function_summarization/instruction`
- Draft:

  > Does the page state that this activity's tool is used for summarising documents, reports or meetings?

- Source: new; the task phrase is copied from the item's own `yes` definition (examples left in the definition)
- Note: One stem for all eight function items, so they read alike. See inconsistency I1 (`no` and "not documented" mean the same here).

#### W21 — core.function_translation

- Level: activity; answer: yes_no; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.function_translation/instruction`
- Draft:

  > Does the page state that this activity's tool is used for translating text or speech between languages?

- Source: new; the task phrase is copied from the item's own `yes` definition (examples left in the definition)
- Note: One stem for all eight function items, so they read alike. See inconsistency I1 (`no` and "not documented" mean the same here).

#### W22 — core.function_search_retrieval

- Level: activity; answer: yes_no; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.function_search_retrieval/instruction`
- Draft:

  > Does the page state that this activity's tool is used for finding information?

- Source: new; the task phrase is copied from the item's own `yes` definition (examples left in the definition)
- Note: One stem for all eight function items, so they read alike. See inconsistency I1 (`no` and "not documented" mean the same here).

#### W23 — core.function_code

- Level: activity; answer: yes_no; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.function_code/instruction`
- Draft:

  > Does the page state that this activity's tool is used for writing, reviewing or fixing software code?

- Source: new; the task phrase is copied from the item's own `yes` definition (examples left in the definition)
- Note: One stem for all eight function items, so they read alike. See inconsistency I1 (`no` and "not documented" mean the same here).

#### W24 — core.function_image_audio_video

- Level: activity; answer: yes_no; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.function_image_audio_video/instruction`
- Draft:

  > Does the page state that this activity's tool is used for creating or editing images, audio or video?

- Source: new; the task phrase is copied from the item's own `yes` definition (examples left in the definition)
- Note: One stem for all eight function items, so they read alike. See inconsistency I1 (`no` and "not documented" mean the same here).

#### W25 — core.function_extraction_classification

- Level: activity; answer: yes_no; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.function_extraction_classification/instruction`
- Draft:

  > Does the page state that this activity's tool is used for pulling information out of documents or forms, or sorting and classifying them?

- Source: new; the task phrase is copied from the item's own `yes` definition (examples left in the definition)
- Note: One stem for all eight function items, so they read alike. See inconsistency I1 (`no` and "not documented" mean the same here).

#### W26 — core.function_analysis_recommendation

- Level: activity; answer: yes_no; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.function_analysis_recommendation/instruction`
- Draft:

  > Does the page state that this activity's tool is used for analysing information or giving recommendations or scores to support human decisions?

- Source: new; the task phrase is copied from the item's own `yes` definition (examples left in the definition)
- Note: One stem for all eight function items, so they read alike. See inconsistency I1 (`no` and "not documented" mean the same here).

### Family: Governance

#### W27 — core.governed_population

- Level: activity; answer: single; pass 2, round 3; gate: core.action_type in ['governance']
- Values: internal_personnel / external_users / both (+ not documented offered, 12 a)
- Path: `items/core.governed_population/instruction`
- Draft:

  > Whom does this rule on GenAI use apply to?

- Source: new
- Note: "Rule" follows the value definitions ("The rule applies to ..."); the item is asked only for governance actions.

#### W28 — core.governance_form

- Level: activity; answer: multi; pass 2, round 3; gate: core.action_type in ['governance']
- Values: dedicated_genai_or_ai_policy_or_guideline / approved_tool_list_or_endorsement / clause_in_instrument_on_other_subject / court_or_regulatory_order / procurement_standard (+ not documented offered, 12 a)
- Path: `items/core.governance_form/instruction`
- Draft:

  > What form does this rule on GenAI use take? Choose all that apply.

- Source: new
- Note: Multi-select, hence "Choose all that apply".

#### W29 — core.governance_direction

- Level: activity; answer: single; pass 2, round 3; gate: core.action_type in ['governance']
- Values: prohibits / restricts_with_conditions / permits / requires / promotes (+ not documented offered, 12 a)
- Path: `items/core.governance_direction/instruction`
- Draft:

  > Does this rule ban, limit, allow, require or encourage the GenAI use it covers?

- Source: new
- Note: The five verbs paraphrase the five values in their order. "Limit" stands for "restricts with conditions", which also covers a ban on some uses with others allowed; that stays in the definition.

### Family: GenAI basis

#### W30 — core.genai_mechanism_basis

- Level: activity; answer: single; pass 2, round 2; gate: none
- Values: named_genai_product_or_model / explicit_genai_label / generative_capability_described / ai_chatbot_or_assistant_label_only (+ not documented offered, 12 a)
- Path: `items/core.genai_mechanism_basis/instruction`
- Draft:

  > What on the page shows that this activity's tool is generative AI?

- Source: new
- Note: The values are a strength order (named product first). See note N1 on whether to add "If several fit, take the first in this order" — here the value order and the long-page order agree, so adding it is safe.

### Family: Dates

#### W31 — core.year_pilot_start

- Level: activity; answer: single; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: candidate years (deterministic year extraction, plus unknown (C16)) (+ not documented offered, 12 a)
- Path: `items/core.year_pilot_start/instruction`
- Draft:

  > In which year does the page say a pilot or trial of this activity began?

- Source: new; replaces the copied announced-year question (ruling 4)
- Note: "Pilot or trial" follows the pilot stage definition ("trial/pilot/PoC/experiment"). Asked only for activity types the applicability table marks; governance is not asked.

#### W32 — core.year_production_start

- Level: activity; answer: single; pass 2, round 3; gate: applicability table (not asked: policy_guidance)
- Values: candidate years (deterministic year extraction, plus unknown (C16)) (+ not documented offered, 12 a)
- Path: `items/core.year_production_start/instruction`
- Draft:

  > In which year does the page say this activity went into full, routine operation?

- Source: new; replaces the copied announced-year question (ruling 4)
- Note: "Full, routine operation" paraphrases the production stage definition. Open point, not decided here: whether a "permanent pilot" (coded production under the stage rule) gives its pilot start year as its production year. The question as drafted would leave that to the page.

### Family: Scale

#### W33 — core.deployment_scale_unit

- Level: activity; answer: single; pass 2, round 4; gate: core.deployment_scale_number in ['any stated']
- Values: licences_or_seats / users / interactions / units_or_departments / none (+ not documented offered, 12 a)
- Path: `items/core.deployment_scale_unit/instruction`
- Draft:

  > What does the stated number for this activity count?

- Source: new; follows the item rule ("jev Choice gives the unit" for the extracted number)
- Note: Assumes the number the extractor found is shown to the model with the question (rule 1). If it is not, the question needs the number filled in by the generator: "What does the number '{number}' count?".

### Family: Outcomes and incidents

#### W34 — core.outcome_kind

- Level: activity; answer: single; pass 2, round 3; gate: applicability table (asked for all types)
- Values: quantified / qualitative / none_reported (+ not documented offered, 12 a)
- Path: `items/core.outcome_kind/instruction`
- Draft:

  > Does the page report a result of this activity, and if so, what kind?

- Source: new; "does the page report an outcome ... of this activity" from item rule 3 (direction), shortened
- Note: "Result" matches the value definitions ("states a measured or numeric result"). The one question answers both whether and what kind, as the rule says.

#### W35 — core.incident_kind

- Level: activity; answer: single; pass 2, round 3; gate: applicability table (asked for all types)
- Values: quantified / qualitative / none_reported / discontinuation_uncertain (+ not documented offered, 12 a)
- Path: `items/core.incident_kind/instruction`
- Draft:

  > Does the page report an incident with this activity, such as an error, failure or controversy, and if so, what kind?

- Source: new; "errors, failures, or controversies" from g3o/extract/prompts/output_contract.md L112 (reported_incidents column description)
- Note: The signed definitions never say what an incident is, so I took the v2.5 column description; delete the "such as" clause if you do not want it in the question. See inconsistency I5.

### Family: Evaluation types

#### W36 — core.evaluation_type_pre_deployment_testing

- Level: activity, page; answer: yes_no; pass 2, round 4; gate: core.evaluation_documented in ['results_reported', 'conducted_no_results', 'required_or_planned']
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.evaluation_type_pre_deployment_testing/instruction`
- Draft:

  > The page documents an evaluation of this GenAI activity, or a requirement or plan for one. Does it document an evaluation of this type: testing before deployment?

- Source: planning/t010/drafts/cx-01.3-draft.json row "pilot.py L210 type_questions instructions" (frozen CX-01.2 template), with {v} = the type phrase from the item's `yes` definition; "the named GenAI activity" changed to "this GenAI activity" to match the signed evaluation question
- Note: Frozen-instrument wording (CX-41), so kept nearly word for word. The frozen template also appends `EVAL_EMPHASIS` (pilot.py L181-187), whose text I could not see in the drafts; the integrator should say whether it is carried. See inconsistency I1.

#### W37 — core.evaluation_type_pilot_evaluation

- Level: activity, page; answer: yes_no; pass 2, round 4; gate: core.evaluation_documented in ['results_reported', 'conducted_no_results', 'required_or_planned']
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.evaluation_type_pilot_evaluation/instruction`
- Draft:

  > The page documents an evaluation of this GenAI activity, or a requirement or plan for one. Does it document an evaluation of this type: evaluation of a pilot or trial?

- Source: planning/t010/drafts/cx-01.3-draft.json row "pilot.py L210 type_questions instructions" (frozen CX-01.2 template), with {v} = the type phrase from the item's `yes` definition; "the named GenAI activity" changed to "this GenAI activity" to match the signed evaluation question
- Note: Frozen-instrument wording (CX-41), so kept nearly word for word. The frozen template also appends `EVAL_EMPHASIS` (pilot.py L181-187), whose text I could not see in the drafts; the integrator should say whether it is carried. See inconsistency I1.

#### W38 — core.evaluation_type_independent_audit

- Level: activity, page; answer: yes_no; pass 2, round 4; gate: core.evaluation_documented in ['results_reported', 'conducted_no_results', 'required_or_planned']
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.evaluation_type_independent_audit/instruction`
- Draft:

  > The page documents an evaluation of this GenAI activity, or a requirement or plan for one. Does it document an evaluation of this type: an audit or evaluation by an independent body?

- Source: planning/t010/drafts/cx-01.3-draft.json row "pilot.py L210 type_questions instructions" (frozen CX-01.2 template), with {v} = the type phrase from the item's `yes` definition; "the named GenAI activity" changed to "this GenAI activity" to match the signed evaluation question
- Note: Frozen-instrument wording (CX-41), so kept nearly word for word. The frozen template also appends `EVAL_EMPHASIS` (pilot.py L181-187), whose text I could not see in the drafts; the integrator should say whether it is carried. See inconsistency I1.

#### W39 — core.evaluation_type_ongoing_monitoring

- Level: activity, page; answer: yes_no; pass 2, round 4; gate: core.evaluation_documented in ['results_reported', 'conducted_no_results', 'required_or_planned']
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.evaluation_type_ongoing_monitoring/instruction`
- Draft:

  > The page documents an evaluation of this GenAI activity, or a requirement or plan for one. Does it document an evaluation of this type: ongoing monitoring of the tool in use?

- Source: planning/t010/drafts/cx-01.3-draft.json row "pilot.py L210 type_questions instructions" (frozen CX-01.2 template), with {v} = the type phrase from the item's `yes` definition; "the named GenAI activity" changed to "this GenAI activity" to match the signed evaluation question
- Note: Frozen-instrument wording (CX-41), so kept nearly word for word. The frozen template also appends `EVAL_EMPHASIS` (pilot.py L181-187), whose text I could not see in the drafts; the integrator should say whether it is carried. See inconsistency I1.

#### W40 — core.evaluation_type_user_feedback

- Level: activity, page; answer: yes_no; pass 2, round 4; gate: core.evaluation_documented in ['results_reported', 'conducted_no_results', 'required_or_planned']
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.evaluation_type_user_feedback/instruction`
- Draft:

  > The page documents an evaluation of this GenAI activity, or a requirement or plan for one. Does it document an evaluation of this type: user feedback or satisfaction surveys?

- Source: planning/t010/drafts/cx-01.3-draft.json row "pilot.py L210 type_questions instructions" (frozen CX-01.2 template), with {v} = the type phrase from the item's `yes` definition; "the named GenAI activity" changed to "this GenAI activity" to match the signed evaluation question
- Note: Frozen-instrument wording (CX-41), so kept nearly word for word. The frozen template also appends `EVAL_EMPHASIS` (pilot.py L181-187), whose text I could not see in the drafts; the integrator should say whether it is carried. See inconsistency I1.

#### W41 — core.evaluation_type_bias_or_safety_testing

- Level: activity, page; answer: yes_no; pass 2, round 4; gate: core.evaluation_documented in ['results_reported', 'conducted_no_results', 'required_or_planned']
- Values: yes / no (+ not documented offered, 12 a)
- Path: `items/core.evaluation_type_bias_or_safety_testing/instruction`
- Draft:

  > The page documents an evaluation of this GenAI activity, or a requirement or plan for one. Does it document an evaluation of this type: bias, fairness or safety testing?

- Source: planning/t010/drafts/cx-01.3-draft.json row "pilot.py L210 type_questions instructions" (frozen CX-01.2 template), with {v} = the type phrase from the item's `yes` definition; "the named GenAI activity" changed to "this GenAI activity" to match the signed evaluation question
- Note: Frozen-instrument wording (CX-41), so kept nearly word for word. The frozen template also appends `EVAL_EMPHASIS` (pilot.py L181-187), whose text I could not see in the drafts; the integrator should say whether it is carried. See inconsistency I1.

### Family: Activity identity (Stage 6)

#### W42 — core.activity_relation_cross_page

- Level: activity; answer: single; pass stage6, round 1; gate: none
- Values: same_activity / component_of_program / has_component / shared_participation / governs / governed_by / distinct_action / unresolved (+ not documented offered, 12 a)
- Path: `items/core.activity_relation_cross_page/instruction`
- Draft:

  > How is the activity in the first record related to the activity in the second record?

- Source: new
- Note: The definitions speak of "the first record" and "the second record", so the question does too. See inconsistency I4 on "not documented".

#### W43 — core.pooled_activity_fields

- Level: activity; answer: single; pass stage6, round 2; gate: none
- Values: none (+ not documented offered, 12 a)
- Path: `items/core.pooled_activity_fields/instruction`
- Draft:

  > The text below is a set of quotes about one activity, gathered from several sources, each with its source type and date. Answer each question about the activity from these quotes only.

- Source: new; framing from item rule 1 ("the union of the activity's supported quotes from all its sources (state = quotes with source type and date)")
- Note: Not a question: this item has no values. Drafted only as a framing sentence in case you rule it should have one. See "Needs a ruling" R1.

## C. Year items: rule 1 with the replacement question (ruling 4)

Rule 1 of both year items is a copy of the announced-year rule and embeds the announced-year question. Only the quoted question changes; the rest of the rule is kept byte for byte. Open point for the integrator (P1-type, not wording): the rule still says "jev Choice over those years plus `unknown`", while 12 a makes `unknown` mechanical and offers "not documented" instead; the same words sit in the signed announced-year rule.

### W44 — core.year_pilot_start, rule 1

- Path: `items/core.year_pilot_start/rules/0/text`
- Draft:

  > Deterministic: extract all four-digit years 2015-2030 from the activity span and its context. jev Choice over those years plus `unknown`: "In which year does the page say a pilot or trial of this activity began?" No fallback to publication year. Across chunks: earliest chosen year.

- Source: items/core.year_pilot_start/rules/0/text (signed text), question swapped for the draft in the item's own entry

### W45 — core.year_production_start, rule 1

- Path: `items/core.year_production_start/rules/0/text`
- Draft:

  > Deterministic: extract all four-digit years 2015-2030 from the activity span and its context. jev Choice over those years plus `unknown`: "In which year does the page say this activity went into full, routine operation?" No fallback to publication year. Across chunks: earliest chosen year.

- Source: items/core.year_production_start/rules/0/text (signed text), question swapped for the draft in the item's own entry

## Needs a ruling

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
