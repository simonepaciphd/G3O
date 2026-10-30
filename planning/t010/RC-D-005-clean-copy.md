# RC-D-005 clean copy: codebook release 2.7, re-signature candidate

**How to reply:** "approve", or name a line to change: "B3: option b", "C1: <new text>", "D6: drop". Anything not named is approved as shown. After approval the integrator folds section D into the item template and section E into the delta, and puts the sign-off build below to you for signature.

Prepared 2026-10-30 by the resolver subagent of the plan integrator (Claude Code, claude-opus-5-5), on your ruling: "drafts ok, give a subagent the task to resolve ambiguities in a way that's coherent with the rest, i will approve final clean copy". Revised in round 2 on your rulings "fix the remainder points -- make coherent with previous rulings (subagent)" and "even if just indirectly -- if the same logic applies, not necessarily a ruling on the specific item, but a different one of similar nature; if none is possible, then provide three options with a rec"; lines changed in round 2 are marked "(round 2)", and section G gives each of the five points. Nothing here is final until you approve it.

Candidate (sign-off build): `planning/t010/candidate-r8/codebook-r8-signoff.yaml`, sha256 `f0b1348cddbbe1ab0de8e16b80dae64a3e3400fe71788a6673f5cfc52348c72f`. Built by `planning/t010/build_skeleton.py --build r8-signoff` = the signed file + `drafts/fixes-r5.json` (130 entries, the earlier RC-D-005 rulings) + `drafts/fixes-r6.json` (129 entries, round 1) + `drafts/fixes-r7.json` (50 entries, round 2) + `drafts/fixes-r8.json` (the cut approved with this copy: PI 2026-10-30, "approved and cut"). Full log of every choice with reasons: `drafts/resolutions-r6.json`, `drafts/resolutions-r7.json` and `drafts/resolutions-r8.json`. (round 3)

## A. What changes against the signed release (`d24bbc7c…0764`)

109 of 120 items change; 56 of them in their text, 53 only in status or flags (table A6). (round 2)

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

Cut (round 3; PI 2026-10-30, "approved and cut"): the 15 characters " plus `unknown`" are removed from rule 1 of `year_announced`, `year_pilot_start` and `year_production_start`, which now reads "… jev Choice over those years: "…"". Nothing else in the rule changes; the text before is kept in `text_before_r8`.

### A4. Other item changes in final form

- **`observed_actor_relationship`:** two linked parts, as signed; now `parts: [relationship, searched_institution_role]` and the role part's question (W10) under `values.part_instructions`. Each part is its own jev question; the role keeps its signed gate (not asked when `unresolved`). (B4)
- **`pooled_activity_fields`:** derived Stage 6 item, no question of its own (linkage pipeline, coder derived, no threshold); each pooled field keeps its own item's rule (10 a). W43 is its framing sentence. (B3)
- **`source_type`:** gate `none`; the condition "only pages not typed automatically from domain or address" stays in its rule 1 and is kept as data (`ask_condition`). Value `other` now reads "None of the above" (cut). (B7, B8)
- **`support_status_second_reason`:** gate `none`; "empty unless two reasons hold" stays in its rule. (B9)
- **`deployment_scale_unit`:** gate "any stated number" (template A3); the extracted number is shown with its question (A8). (B13)
- **`reported_outcomes`, `reported_incidents`:** rule 2 dropped (it described the separate existence question that folded into the kind items). (B11)
- **Twelve items now offer "not documented"** and gain the signed rule "not_documented: the page is silent." (copied from `has_human_oversight`): `model_origin`, `build_arrangement`, `deployment_mode`, `target_users`, `governed_population`, `governance_form`, `observed_actor_role`; in round 2 also `source_type`, `deployment_scale_unit` and the three year items. (B1, B2; round 2)
- **Year items:** the candidate `unknown` (C16) stays a value but is no longer offered (`values.candidates_not_offered`, like `not_assessable` on the verdict); it is set mechanically. A page that states no year can answer "not documented". (B2; round 2)
- **`support_status`:** names its code list (`value_vocabulary: support_status`).

### A5. Texts dropped by the earlier RC-D-005 rulings (fixes-r5, 13 a)

32 drafter-direction slots (13 directions), each checked as carried out in the signed text: `fixes-r5.md`, first table. Not repeated here.

### A6. Status and flag changes (no wording)

| Change | Items | Ruling |
|---|---|---|
| `status: signed` on every core item; release `status: signed` | 109 | 2 a |
| Applicability gates in the template's form (item + values) | 30 | P1 |
| "not documented" offered as a choice (`jev_missing_choice`) | 21 offer it, 30 do not (incl. `page_verdict`, `procurement_status`), each with the signed text it rests on (`grounds`) | 12 a, B1 (round 2) |
| `not_assessable` never a choice | `page_verdict` | P3 |
| Negative verdict list; all parts "not covered" gives `not_assessable` | `page_verdict`, `support_status` vocabulary | 8 b, 9 a |
| Cross-page relation order with `has_component`, `governed_by` | `activity_relation_cross_page` | 7 a |
| Number and unit supported only as a pair | `deployment_scale_number`, `deployment_scale_unit` | 11 a |
| Procurement removed | `page_review_state` | 14 a |
| Family list, verdict order, owner key | vocabularies, `page_verdict`, `language_coverage` | P1 |

## B. Resolutions (one line each; source labels as put to you)

1. **12a′ — option iv.** "Not documented" is offered on 21 items; each of the 30 exclusions now cites the signed text it rests on, and `source_type` and `deployment_scale_unit`, whose round-1 exclusions rested on inference, now offer it; items without a rule get the signed has_* rule copied, so no new wording. (round 2)
2. **F8 — option b (keep the texts).** The 16 rules stay true as outcomes ("cannot be settled" ends below the 0.8 bar, so `unknown`). The year items no longer offer `unknown`: 12 a is later than C16 and makes it mechanical, and R2C04 has non-frozen fields use "not documented" for a silent page. (round 2)
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
16. **Procedural F1 a, F2 a, F6 a, F7 a, G1 — applied** (template D1-D4, D7); **plus D5**, now read from the signed combining rule (round 2, G3).
17. **T-020 readings:** confirmed T1 (32k = 32,000 tokens, a setting), T2 (per-character estimate; constants owned by the multilingual subproject), T3 (any-yes fallback yes, no, not documented, unknown), T4 (0.8 bar on every answer, incl. an offered "not documented"), T6 (most-sure part also under first-section), T7 (mapped values list their input parts), T8 (the codebook's explicit ban + permission pair; SPEC wording aligned), T10 (exact-string dedup), T11 ("not asked" / `_NA_` never reach parts). **Adjusted** T5: a quote counts if it passes the R-042 fuzzy match in its own part, not an exact match. **T9 (round 2):** a pooled source with no supported publication date is placed by the signed `stage_as_of` fallback (the page's latest stated date for the activity, else the access date), replacing round 1's "last".

## C. New text I wrote (verbatim)

1. **Stage 6 system prompt, sentence 2** (`shared/system_prompt_stage6`; the rest is W04 unchanged): "You read two activity records, or a set of quotes about one activity gathered from several sources, about a named institution and answer coding questions about them."

Not new wording, listed so you can see them: the cut "None of the above" (I7), and the signed sentence "not_documented: the page is silent." copied onto seven items (B1). The codebook also holds short data notes (the reason each item does or does not offer "not documented", the former gate texts); they are records, never shown to a classifier.

## D. Template amendments (`planning/t010/item-template-r5-amendments.md`)

1. `values: none` allowed on every mechanical or derived item and on list items; codes from `value_codes`, `value_vocabulary` or yes/no (F1 a).
2. Computed value list `values: {candidates: …}` for the year classifiers; their rules follow the question once (F2 a).
3. "Any value" gate: `values: any` (F6 a).
4. `missing_tokens: none` (F7 a).
5. Check 7: a gate item that is not a classifier (a quote step or mechanical item) has no round to compare; its order is the signed `combining_conventions.gate_items_first` rule, so the check notes it; a classifier gate without a round still fails. (round 2)
6. Parts form for linked-part items: one question per part (R2 b).
7. Top-level `shared` slots (part prompt, system prompts); `jev_choice: false`; `jev_missing_choice` with its meaning rule; generators write system prompts and part prompts (G1).
8. `question_context: {shows_value_of: […]}` (W33).

## E. SPEC additions for the delta (integrator puts them into `deltas/RC-D-005.md`)

1. **R-045 / R-015 (replaces item 6's first sentence):** "`not_documented` is offered to the classifier only on items where its meaning is not already covered by a signed value definition, a signed missing-label rule, the frozen CX answer set or a signed order; each such item names the rule that gives the meaning (12 a; 12a′ iv). `unknown` is never offered (12 a); the year items keep the C16 candidate `unknown` as a value, set by rule. The certainty bar sets it elsewhere, and the 0.8 bar applies to an offered `not_documented` like any answer (R-081)." (round 2)
2. **R-044, part-prompt marker:** part-prompt sentence = W01; temporary answer = W02 with the meaning W03.
3. **R-044 additions:** an any-yes rule falls back in the order yes, no, not documented, unknown; a quote counts only if it passes the R-042 match in the part that produced the answer; a value made by a mapping step lists its input parts and their quotes; governance wording aligned to the codebook ("a condition in any part ranks first; a ban in one part and a permission in another give `restricts_with_conditions`"); pooled evidence is ordered by source date, a source with no supported publication date taking its `stage_as_of` fallback date (latest stated date for the activity, else access date), then by page order (round 2); combined lists drop exact duplicates only; within one prompt the classifier gives one answer (no tie sentence), and value orders act when parts are combined.
4. **R-044 / X31:** `pooled_activity_fields` is a derived Stage 6 item with no question of its own; pooled prompts open with its framing sentence (W43).
5. **R-007 (with item 5):** the codebook's `shared` key holds the system prompts (passes 1-2 and extractor; Stage 6) and the part-prompt texts.
6. **C-004:** 32k = 32,000 tokens of request state, a pipeline setting.
7. **R-040:** the extracted scale number is shown to the classifier with the unit question.
8. **PLAN T-013:** generator support done on `reclass/t013-codebook` (`f5cc378`; round 2 `0a542ba`), and `codebook/schema.json` now accepts both the signed file and the candidate, with a test validating both. (round 2)
9. **PLAN T-016, re-pilot scope (draft for the integrator, the PLAN's sole writer; round 2):** "T-016 re-pilots every jev question generated from the re-signed codebook (52 questions, incl. the role part): the re-signed CX items and the non-CX items its card already lists, plus every item whose question is new in RC-D-005 (W05-W43, W10), the year questions without `unknown` (12 a), and the part-prompt sentence and temporary answer (W01-W03) on the long pages of the RS-008/RS-009 set, each run under the shared system prompt (W04, Stage 6 variant for the cross-page relation); per question: answer distribution, chosen-answer probability and comparison with the prior wording where it exists. The agent prepares the command and cost estimate; Simone runs it; the PI rules on the results before T-011." Reason: the card's objective is a re-pilot of "every reworded item", and under 3 a the 38 new questions were confirmed in chat ("drafts ok") but never run, so they are reworded items with no pilot evidence.

## F. Checks and hashes

- Signed file reproduces: `--build signed-2.7` gives `d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764`; `codebook/codebook.yaml` untouched. r5 builds (`c0f9b928…`, `3a8a3e5f…`) and r6 builds (`93026bbf…`, `6c4bfc6c…`) also reproduce. (round 2)
- Candidate draft build: `candidate-r8/codebook-r8-draft.yaml` sha256 `a66c7c4f1e13f3e76e89df6931addd67ff6d188ff293a6750e184a10c26ec27d`. Round 2 builds kept: r7 draft `e96f89756d99a82946171e3585907eb110dc0c6f6533fe4b624f7fde190b9678`, r7 sign-off `1b667db0810f69d948e2ab105d11e9a22a255494a3bfba21883d66d432303ad9` (both reproduce). (round 3)
- Candidate sign-off build: `candidate-r8/codebook-r8-signoff.yaml` sha256 `f0b1348cddbbe1ab0de8e16b80dae64a3e3400fe71788a6673f5cfc52348c72f` (committed `-text`, CRLF). (round 3)
- Builder checks: r5 and r6 checks on the intermediate states, then r7: 5 slot texts added, all the copied signed rule; none removed; 50 entries in place. (round 2)
- Builder checks, r8: r8 differs from r7 only in the three year-rule slots (" plus `unknown`" cut; provenance fields `origin`, `text_before_r8`, `cut_r8`, `cut_by` added) and `release.folds.r8`; signed-2.7, r5, r6 and r7 builds all reproduce. (round 3)
- T-013 checks 1-16 on the r8 sign-off build (`reclass/t013-codebook` `307517f`): all PASS except 4 (record holds the old hash; clears on re-signature) and 5 (committed generated files are for the signed file). Regenerated into a temporary root: check 5 PASS, all others unchanged. (round 3)
- T-013 full test suite (`-m "not network"`, eng-b venv): 2259 tests, 0 failures, 0 errors, 2 skipped (exit 0); the schema test validates the signed file and a byte copy of the r8 sign-off build. ruff on `g3o` and `tests`: all checks passed. (round 3)

## G. Round 2: the five points (round 2)

1. **B2 / F8, `unknown` on the year items — changed: not offered.** Rulings: "12 a" (PI 2026-10-30), on the option as asked: "a, offer `not_documented` (per-item missing-label rule), `unknown` stays mechanical"; R2C04 (r2#16, chosen "a"): "Reserved labels: 'not asked' …, 'not documented' (page silent) and 'unknown' (stated but undeterminable, or downgraded). New and non-frozen fields adopt them". C16 (alt-1, 2026-10-29) said "jev Choice over those years plus `unknown`"; 12 a is later and general, and the year items are non-frozen, so both later rulings override that clause. Least change: the candidate stays a value flagged not offered, as P3 did for `not_assessable` ("never a classifier answer"), and the signed rule texts are kept as approved (W44/W45, "drafts ok"); a silent page answers "not documented" with the copied signed rule. The 16 other `unknown` texts (F8 b) are unchanged. Paraphrase note: round 1 read C16 as allowing the offer; the verbatim 12 a option text and R2C04 do not.
2. **B1, the exclusions — two reversed, 30 kept with their grounds.** Each kept exclusion now records the signed text it rests on (`jev_missing_choice.grounds`): a signed `no` / `false` / `none_reported` definition or the signed CX map ("`no` of the `evaluation_type_*` and `content_*` items → "not documented""; "`none_reported` (CX-60, CX-61) → "not documented""), a signed missing-label rule, the frozen CX answer sets (R2C04: "the frozen institutional questionnaire items keep their signed spellings"), `procurement_status` rules/2, or the signed cross-page order. `activity_type`: its signed `unknown` rule, "the kind of undertaking is indeterminate from the available sources", already covers a silent page. `genai_mechanism_basis`: its signed rule 1, "jev Choice on every confirms_activity page/activity", and the signed `confirms_activity` definition, "The text must be explicitly generative AI", so a basis is always on the page. Reversed: `source_type` (`other` is "None of the above", not silence) and `deployment_scale_unit` (`none` is "A number is stated, but it counts none of these units"); neither exclusion had a signed ground, so 12 a's offer applies.
3. **D5 — replaced.** It now follows the signed combining rule `combining_conventions.gate_items_first` (all-04): "activity_type and action_type (and the scale number) are combined before the items they gate", together with the "any stated" gate on the number (F6 a). Check 7 compares rounds only between classifiers; for a quote-step or mechanical gate item it notes the order is that rule. The round-1 reading (borrowing the gate item's own gate position) is dropped: R-040 runs the quote step "for every activity", so that position was not grounded.
4. **T5 — kept; T9 — changed.** T5 rests on R-042 (USER SF-014 ii c): "Supporting text is checked against the stored page text by fuzzy match; a quote below the match threshold counts as no supporting text", with RC-D-002 row 17, "the check matches against the text the quote came from", and R-044, "the supporting quote comes from the chunk that produced the code". "Verbatim" in R-040 is what the quote step copies, not the check. T9: all-06 a orders pooled evidence "by source date, then page order" without saying what an undated source's date is. The signed `stage_as_of` rule answers the same question for an activity observation: "stage_as_of = source_publication_date if supported, else the page's latest stated date for the activity, else the access date". The same logic carries over, so an undated source takes that fallback date. Round 1's "last" had no ruling behind it.
5. **Open items — both settled.** (a) `codebook/schema.json` now accepts both files (values, gate, rules, long-page rule, missing tokens, status and version fields loosened to their shapes, `shared` added; checks 1-16 keep the value rules), with `tests/test_codebook.py::test_schema_validates_signed_file_and_rc_d_005_candidate` validating the signed file and a byte copy of the r7 sign-off build. (b) T-016 scope drafted as E9. Its ground is the card's own objective, a re-pilot of "every reworded item", with the 3 a ruling: "3 subagent drafts all & I read and edit/confirm".

No point needed the three-options fallback.

**Round 3 (PI 2026-10-30, "approved and cut").** The clean copy is approved, and the open point it carried is settled: rule 1 of the three year items still said "jev Choice over those years plus `unknown`" though point 1 stopped offering `unknown`; the words " plus `unknown`" are cut, cut-only (as in "2a"), in `drafts/fixes-r8.json`. Template amendments D1-D8 are folded into `item-template.md`, D5 in its round-2 wording.
