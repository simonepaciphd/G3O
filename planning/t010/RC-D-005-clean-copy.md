# RC-D-005 clean copy: codebook release 2.7, re-signature candidate

**How to reply:** "approve", or name a line to change: "B3: option b", "C1: <new text>", "D6: drop". Anything not named is approved as shown. After approval the integrator folds section D into the item template and section E into the delta, and puts the sign-off build below to you for signature.

Prepared 2026-10-30 by the resolver subagent of the plan integrator (Claude Code, claude-opus-5-5), on your ruling: "drafts ok, give a subagent the task to resolve ambiguities in a way that's coherent with the rest, i will approve final clean copy". Nothing here is final until you approve it.

Candidate (sign-off build): `planning/t010/candidate-r6/codebook-r6-signoff.yaml`, sha256 `6c4bfc6cbca3450fe2c8d028c77d4e921ae492688db89a26e41fbb1810a7ae3c`. Built by `planning/t010/build_skeleton.py --build r6-signoff` = the signed file + `drafts/fixes-r5.json` (130 entries, the earlier RC-D-005 rulings) + `drafts/fixes-r6.json` (129 entries, this round). Full log of every choice with reasons: `drafts/resolutions-r6.json`.

## A. What changes against the signed release (`d24bbc7c…0764`)

109 of 120 items change; 55 of them in their text, 54 only in status or flags (table A6).

### A1. New questions (W05-W43, as you approved them)

| W | Item | Question |
|---|---|---|
| W05 | `disclosure_scope` | How many institutions does the listing or document this page belongs to cover? |
| W06 | `content_contact_named` | Does the page name a person, office or unit as responsible for a GenAI activity it mentions, or for questions about it? |
| W07 | `content_contact_details` | Does the page give any contact details anywhere on it, such as an email address, phone number, postal address or contact form? |
| W08 | `source_type` | What kind of source is this page? |
| W09 | `observed_actor_relationship` (relationship part) | Whose activity is this, according to the page: the named institution's own, one of its units', a joint one it takes part in, or another body's? |
| W10 | `observed_actor_relationship` (role part) | What part does the named institution play in this activity? |
| W11 | `observed_actor_role` | What role does the body that the page shows acting in this activity play in it? |
| W12 | `action_type` | What kind of action is this activity? |
| W13 | `adoption_stage` | What stage has this activity reached, according to the page? |
| W14 | `procurement_status` | What purchase step, if any, does the page record for this activity's tool or service? |
| W15 | `service_domain` | Which areas of government work does this activity concern? Choose all that apply. |
| W16 | `model_origin` | Where does the model behind this activity's tool come from? |
| W17 | `build_arrangement` | How was this activity's tool built? |
| W18 | `interface` | How do users reach this activity's tool? |
| W19-W26 | the eight `function_*` items | Does the page state that this activity's tool is used for {drafting or writing text / summarising documents, reports or meetings / translating text or speech between languages / finding information / writing, reviewing or fixing software code / creating or editing images, audio or video / pulling information out of documents or forms, or sorting and classifying them / analysing information or giving recommendations or scores to support human decisions}? |
| W27 | `governed_population` | Whom does this rule on GenAI use apply to? |
| W28 | `governance_form` | What form does this rule on GenAI use take? Choose all that apply. |
| W29 | `governance_direction` | Does this rule ban, limit, allow, require or encourage the GenAI use it covers? |
| W30 | `genai_mechanism_basis` | What on the page shows that this activity's tool is generative AI? |
| W31 | `year_pilot_start` | In which year does the page say a pilot or trial of this activity began? |
| W32 | `year_production_start` | In which year does the page say this activity went into full, routine operation? |
| W33 | `deployment_scale_unit` | What does the stated number for this activity count? |
| W34 | `outcome_kind` | Does the page report a result of this activity, and if so, what kind? |
| W35 | `incident_kind` | Does the page report an incident with this activity, such as an error, failure or controversy, and if so, what kind? |
| W36-W41 | the six `evaluation_type_*` items | The page documents an evaluation of this GenAI activity, or a requirement or plan for one. Does it document an evaluation of this type: {testing before deployment / evaluation of a pilot or trial / an audit or evaluation by an independent body / ongoing monitoring of the tool in use / user feedback or satisfaction surveys / bias, fairness or safety testing}? *followed by EVAL_EMPHASIS (below)* |
| W42 | `activity_relation_cross_page` | How is the activity in the first record related to the activity in the second record? |
| W43 | `pooled_activity_fields` (framing, see B3) | The text below is a set of quotes about one activity, gathered from several sources, each with its source type and date. Answer each question about the activity from these quotes only. |

EVAL_EMPHASIS (E1), appended byte for byte to W36-W41, from the frozen CX-01.2 pilot (`pilot.py` L181-187):

> Rules: consider only evaluation of THIS activity and its own tool; an evaluation of a different tool or activity does not count (CX-02). A trial run or reported by a vendor counts only if the institution or an independent body is named as the evaluator (CX-38). Starting or announcing a pilot is not an evaluation (CX-39). A risk or impact assessment is not an evaluation unless it reports testing or measured performance (CX-37, CX-32b). A performance figure counts only if the page describes the evaluation behind it (CX-36).

### A2. Shared texts (new top-level `shared`)

- Part-prompt sentence (W01): "The text below is only one part of a longer page; the rest of the page is read separately. Answer from this part only."
- Temporary answer (W02 / W03): "not covered by this part" — "This part of the page does not deal with the question; another part of the page may."
- System prompt, passes 1-2 and the extractor (W04): as approved.
- System prompt, Stage 6: W04 with sentence 2 replaced (new text, C1).

### A3. Year items, rule 1 (W44, W45)

The quoted announced-year question inside rule 1 of `year_pilot_start` and `year_production_start` is replaced by W31 / W32; the rest of the rule is unchanged.

### A4. Other item changes in final form

- **`observed_actor_relationship`:** two linked parts, as signed; now `parts: [relationship, searched_institution_role]` and the role part's question (W10) under `values.part_instructions`. Each part is its own jev question; the role keeps its signed gate (not asked when `unresolved`). (B4)
- **`pooled_activity_fields`:** derived Stage 6 item, no question of its own (linkage pipeline, coder derived, no threshold); each pooled field keeps its own item's rule (10 a). W43 is its framing sentence. (B3)
- **`source_type`:** gate `none`; the condition "only pages not typed automatically from domain or address" stays in its rule 1 and is kept as data (`ask_condition`). Value `other` now reads "None of the above" (cut). (B7, B8)
- **`support_status_second_reason`:** gate `none`; "empty unless two reasons hold" stays in its rule. (B9)
- **`deployment_scale_unit`:** gate "any stated number" (template A3); the extracted number is shown with its question (A8). (B13)
- **`reported_outcomes`, `reported_incidents`:** rule 2 dropped (it described the separate existence question that folded into the kind items). (B11)
- **Seven items now offer "not documented"** and gain the signed rule "not_documented: the page is silent." (copied from `has_human_oversight`): `model_origin`, `build_arrangement`, `deployment_mode`, `target_users`, `governed_population`, `governance_form`, `observed_actor_role`. (B1)
- **`support_status`:** names its code list (`value_vocabulary: support_status`).

### A5. Texts dropped by the earlier RC-D-005 rulings (fixes-r5, 13 a)

32 drafter-direction slots (13 directions), each checked as carried out in the signed text: `fixes-r5.md`, first table. Not repeated here.

### A6. Status and flag changes (no wording)

| Change | Items | Ruling |
|---|---|---|
| `status: signed` on every core item; release `status: signed` | 109 | 2 a |
| Applicability gates in the template's form (item + values) | 30 | P1 |
| "not documented" offered as a choice (`jev_missing_choice`) | 16 offer it, 35 do not (incl. `page_verdict`, `procurement_status`), each with its reason | 12 a, B1 |
| `not_assessable` never a choice | `page_verdict` | P3 |
| Negative verdict list; all parts "not covered" gives `not_assessable` | `page_verdict`, `support_status` vocabulary | 8 b, 9 a |
| Cross-page relation order with `has_component`, `governed_by` | `activity_relation_cross_page` | 7 a |
| Number and unit supported only as a pair | `deployment_scale_number`, `deployment_scale_unit` | 11 a |
| Procurement removed | `page_review_state` | 14 a |
| Family list, verdict order, owner key | vocabularies, `page_verdict`, `language_coverage` | P1 |

## B. Resolutions (one line each; source labels as put to you)

1. **12a′ — option iv.** "Not documented" is offered on 16 items where no real value or existing "unknown" rule already covers a silent page; the 7 without a rule get the signed has_* rule copied, so no new wording.
2. **F8 — option b (keep).** The 16 rules stay true as outcomes ("cannot be settled" ends below the 0.8 bar, so `unknown`); the year items keep their signed candidate `unknown` (C16), the one place it is offered.
3. **R1 = F4 — option a.** By 10 a each pooled field uses its own item, so the item has no answers to ask for; W43 is its framing sentence.
4. **R2 = F3 — option b (parts form).** Keeps the signed "two linked parts in one item" intact and avoids a third attribution item beside `observed_actor_role`.
5. **N1 — option c (none).** The approved questions omit it, and for seven items the value order differs from the combining order.
6. **I5 — option b (keep).** The definitions are frozen CX-61 text; W35 says what an incident is, and the stop rule and `discontinuation_uncertain` cover different cases (confirmed stop vs unconfirmed).
7. **I7 — option a (drop the clause).** jev returns codes only (C-004); cut as in your "2a" method.
8. **F5 source_type — option b.** Rule 1 and R-002 already carry the condition; no new item.
9. **F5 second_reason — option a.** A gate on `downgraded_*` would store "not asked" where the signed rule says empty.
10. **F9 — option b (keep).** These are your chosen ruling texts, not drafter notes, and some are the only definition of their item (`unit_credit`, `date_upper_bound`).
11. **F10 — option a (drop).** The text describes a question the signed kind items absorbed; dropping an overridden text follows "2a".
12. **W32 note — leave to the page.** A permanent-pilot rule would be a new coding choice; `permanent_pilot` stays a derived flag.
13. **W33 note — number shown as data with the question.** Needs no wording, no filled-in text.
14. **W04 note — Stage 6 variant.** Stage 6 reads records or pooled quotes, not a page; only sentence 2 changes (C1).
15. **E1 — byte for byte,** appended to W36-W41 as the frozen template did.
16. **Procedural F1 a, F2 a, F6 a, F7 a, G1 — applied** (template D1-D4, D7); **plus D5** (gate order through the extracted number), which coherence with F6 a needed.
17. **T-020 readings:** confirmed T1 (32k = 32,000 tokens, a setting), T2 (per-character estimate; constants owned by the multilingual subproject), T3 (any-yes fallback yes, no, not documented, unknown), T4 (0.8 bar on every answer, incl. an offered "not documented"), T6 (most-sure part also under first-section), T7 (mapped values list their input parts), T8 (the codebook's explicit ban + permission pair; SPEC wording aligned), T10 (exact-string dedup), T11 ("not asked" / `_NA_` never reach parts). **Adjusted** T5: a quote counts if it passes the R-042 fuzzy match in its own part, not an exact match. **Decided** T9: undated pooled evidence goes last (after dated sources; undated sources already score low credibility).

## C. New text I wrote (verbatim)

1. **Stage 6 system prompt, sentence 2** (`shared/system_prompt_stage6`; the rest is W04 unchanged): "You read two activity records, or a set of quotes about one activity gathered from several sources, about a named institution and answer coding questions about them."

Not new wording, listed so you can see them: the cut "None of the above" (I7), and the signed sentence "not_documented: the page is silent." copied onto seven items (B1). The codebook also holds short data notes (the reason each item does or does not offer "not documented", the former gate texts); they are records, never shown to a classifier.

## D. Template amendments (`planning/t010/item-template-r5-amendments.md`)

1. `values: none` allowed on every mechanical or derived item and on list items; codes from `value_codes`, `value_vocabulary` or yes/no (F1 a).
2. Computed value list `values: {candidates: …}` for the year classifiers; their rules follow the question once (F2 a).
3. "Any value" gate: `values: any` (F6 a).
4. `missing_tokens: none` (F7 a).
5. Check 7: a gate item without a round (an extractor step) takes its own gate's position.
6. Parts form for linked-part items: one question per part (R2 b).
7. Top-level `shared` slots (part prompt, system prompts); `jev_choice: false`; `jev_missing_choice` with its meaning rule; generators write system prompts and part prompts (G1).
8. `question_context: {shows_value_of: […]}` (W33).

## E. SPEC additions for the delta (integrator puts them into `deltas/RC-D-005.md`)

1. **R-045 / R-015 (replaces item 6's first sentence):** "`not_documented` is offered to the classifier only on items where its meaning is not already covered by a real value or the item's `unknown` rule; each such item names the rule that gives the meaning (12 a; 12a′ iv). `unknown` is never offered, except as the computed candidate of the three year items (C16); otherwise the certainty bar sets it, and the 0.8 bar applies to an offered `not_documented` like any answer (R-081)."
2. **R-044, part-prompt marker:** part-prompt sentence = W01; temporary answer = W02 with the meaning W03.
3. **R-044 additions:** an any-yes rule falls back in the order yes, no, not documented, unknown; a quote counts only if it passes the R-042 match in the part that produced the answer; a value made by a mapping step lists its input parts and their quotes; governance wording aligned to the codebook ("a condition in any part ranks first; a ban in one part and a permission in another give `restricts_with_conditions`"); pooled evidence is ordered dated sources by date, then undated sources, each by page order; combined lists drop exact duplicates only; within one prompt the classifier gives one answer (no tie sentence), and value orders act when parts are combined.
4. **R-044 / X31:** `pooled_activity_fields` is a derived Stage 6 item with no question of its own; pooled prompts open with its framing sentence (W43).
5. **R-007 (with item 5):** the codebook's `shared` key holds the system prompts (passes 1-2 and extractor; Stage 6) and the part-prompt texts.
6. **C-004:** 32k = 32,000 tokens of request state, a pipeline setting.
7. **R-040:** the extracted scale number is shown to the classifier with the unit question.
8. **PLAN T-013:** generator support done on `reclass/t013-codebook` (`f5cc378`); `codebook/schema.json` still has the old shapes (follow-up, outside this round's edit scope).

## F. Checks and hashes

- Signed file reproduces: `--build signed-2.7` gives `d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764`; `codebook/codebook.yaml` untouched. r5 builds also reproduce (`c0f9b928…`, `3a8a3e5f…`).
- Candidate draft build: `candidate-r6/codebook-r6-draft.yaml` sha256 `93026bbf18f9c4d9a4bfa2af88018896eeeae1ba741d675ecc3bc28e9a4dae63`.
- Candidate sign-off build: `candidate-r6/codebook-r6-signoff.yaml` sha256 `6c4bfc6cbca3450fe2c8d028c77d4e921ae492688db89a26e41fbb1810a7ae3c` (committed `-text`, CRLF).
- Builder checks: W01-W45 byte-identical at their slots; 48 new slot texts, all W texts, W + EVAL_EMPHASIS, C1, the cut or the copied rule; 4 texts gone, all listed; every core classifier item has a question.
- T-013 checks 1-16 on the sign-off build (`reclass/t013-codebook` `f5cc378`): all PASS except 4 (record holds the old hash; clears on re-signature) and 5 (committed generated files are for the signed file). Regenerated into a temporary root: check 5 PASS, all others unchanged. 52 jev questions, none left ungenerated.
- T-013 full test suite (`-m "not network"`, eng-b venv): passes, exit 0; codebook tests include 5 new synthetic tests for D1-D8; the signed file's pinned check results unchanged.
