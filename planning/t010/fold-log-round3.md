# T-010 fold log, round 3: drafts as amended by the round-3 rulings (DRAFT, uncommitted)

Status: 2026-10-29. Integrator subagent (Claude Code, claude-opus-5-5), run for the plan integrator, session `20261029-claude-v2-b92f4144070ec139`. Nothing here is signed. Not committed (P4).

- **Inputs.**
  - Rulings: `codebook-review/round3/codebook-rulings-round3.json`, 61 items, all PI-approved. Option texts come from `questions-r3.json`; draft-entry pointers from `questions-r3-sourcemap.json`.
  - Drafts: `drafts/applicability.json`, `value-lists.json`, `combining-rules.json` and `cx-01.3-draft.json`.
  - Earlier sources, as before: SPEC, rulings for rounds 1 and 2, CX-01.2, re-pilot 2 and v2.5.
- **Tool.** The builder `planning/t010/build_skeleton.py` writes `C:/Users/spaci/worktrees/G3O-integrator/codebook/codebook.yaml`. Nothing in the YAML is hand-edited.
- **Slot discipline.**
  - Slot origins:
    - `agent-draft`: draft text, loaded from the draft JSON, with the marker "Agent draft — PI to write or line-edit".
    - `ruling-r3`: option or record text, loaded from `questions-r3.json` or the rulings file, with the marker "round-3 ruling option text — PI to write or line-edit".
  - `verify_round3()` re-reads the source files and asserts every such slot verbatim. One declared transform exists, the all-11 respelling (section 4, item 6).
- **Questionnaire slots.**
  - Every CX slot now carries the CX-01.3 draft cell as `text`. The CX-01.2 cell sits beside it as `frozen_text`, with `frozen_source` and `draft_action` (`edit` / `new` / `no_change`).
  - The ruling ids per row are computed from the question bodies and the sourcemap. A `no_change` row that no round-3 item names says so in its `source`.

## 1. Per round-3 ruling: what changed and where

The "Where" column gives item ids and fields. `shared_rules.*`, `vocabularies.*` and `combining_conventions.*` are top-level blocks.

| Id | Choice | What changed | Where |
|---|---|---|---|
| all-01 | b | `_NA_` is the fourth missing label; its slot is the option text. `_NA_` is also added to `missing_tokens` of every activity-level item (see section 4, item 1). | `vocabularies.missing.values`, `.na_label`; `missing_tokens` of all `level: activity` items |
| all-02 | a | "not documented" kept in the missing tokens of the four items; the option text is added as a rule. | `core.interface`, `core.governance_direction`, `core.service_domain`, `core.observed_actor_relationship`: `rules`, `missing_tokens` |
| all-03 | a + PI comment | Adds the draft convention "check, then combine", the `reading` text and the PI comment verbatim. Also adds the temporary value "not covered by this part" as a convention, never published (see section 4, item 2). | `combining_conventions.check_then_combine`, `combining_conventions.not_covered_by_this_part` |
| all-04 | b | Every priority order is re-ranked: real answers, then `not_documented`, then `unknown`. This includes the signed evaluation order, where `unknown` is appended after `not_documented`. | `combining_conventions.missing_rank`, `.gate_items_first`; `long_page_rule.order` of every priority-order item; `core.evaluation_documented.long_page_rule` |
| all-05 | a | The most-sure part supplies the quote and certainty (ties: earliest part). | `combining_conventions.producing_part` |
| all-06 | a | The first part with a supported answer counts; pooled evidence is ordered by source date, then page order. | `combining_conventions.first_part`; refs on `core.disclosure_form`, `core.disclosure_scope`, `core.source_type`, `core.source_publication_date` |
| all-07 | c | `unresolved` and `not_assessable` are kept as coding values and mapped to `unknown` in published summaries. | `vocabularies.missing.published_summary_map`; refs on `core.page_verdict`, `core.observed_actor_relationship`, `core.activity_segment`, `core.activity_relation_cross_page` |
| all-08 | approve | New row CX-06 (the missing-label map), draft text. | `vocabularies.missing.cx_mapping_row` |
| all-09 | a | The map is taken as drafted (same slot; its source names all-09). | `vocabularies.missing.cx_mapping_row` |
| all-10 | a | The map stays a questionnaire row; the "narrowed in" marks are kept in the CX-13, CX-25 and CX-32c draft cells. | `vocabularies.missing.cx_mapping_row_location`; CX-61 slots in `core.outcome_kind.rules`, `core.incident_kind.rules` |
| all-11 | approve | First spellings adopted: `other_interface`, `distinct_action`, `from_metadata` / `looked_up` / `quoted_by_quote_step`, `downgraded_quote_not_stating_value`, `set_by_rule` and `discontinuation_uncertain`. The CX-61b and OUTCOME_KIND draft cells are respelled by a declared transform. | `core.interface.values`, `core.activity_segment.values`, `core.activity_relation_cross_page.values`, `vocabularies.provenance`, `vocabularies.support_status`, `vocabularies.relation`, `core.incident_kind.values` / `.rules` |
| page-01 | c | Adds a note slot (option text) that "yes" means the page refers onward, i.e. incomplete. The note's own wording is still owed. | `core.page_complete.rules` |
| page-02 | b | Two-tier verdict order: supported verdicts in S3 a order, then failed ones. | `core.page_verdict.long_page_rule.tiers` |
| page-03 | approve | Draft cells for CX-12, CX-13 and CX-25; pilot L134 (FORM[mandated_report]) as a classifier line. | `core.disclosure_form.values[mandated_report].definition`, `core.disclosure_form.rules`, `core.disclosure_scope.rules` |
| page-04 | b | Ruling text added as a direction. The CX-13 draft does not yet name compliance reports under non-AI rules, so that wording is owed (section 4). | `core.disclosure_form.rules` |
| page-05 | approve | Draft cells for CX-01 (shared grain rule), CX-50 and CX-51, plus the L203 instruction. | `shared_rules.core.rule.cx_grain`; `rules` of all `core.content_*`; `core.content_data.instruction`, `.values` |
| page-06 | a | The five description lines (pilot L147-149, L151, L152) go to `retired`, with their archived signed text. | `retired`; refs on `core.content_purpose`, `_tool_or_model`, `_vendor`, `_users`, `_status_date` |
| page-07 | a | `core.content_data` is no longer derived. It becomes a page classifier question: pass 1, round 2, yes/no, gated on the five GenAI verdicts. | `core.content_data` (whole item) |
| page-08 | b, c | Derivation sources: users = `target_users` + `governed_population`; vendor = `developer` (stated or looked up) + `contracting_party`. The CX-51 draft still states the old pairing, so its wording is owed. | `core.content_users.rules`, `core.content_vendor.rules` (`derived_from`, `amended_by`) |
| page-09 | c | Description items and `content_data` are "no" where the verdict shows no GenAI. The CX-51 draft still says "not asked", so its wording is owed. | `core.content_data.gate.gated_out_value`; `rules` of the five derived description items |
| page-10 | approve | Draft cells for CX-52 and CX-53; each page safeguard item gets a derivation entry from its `has_*` item. | `rules` of `core.content_human_oversight`, `_risk_assessment`, `_user_notification`, `core.content_contact_emails` |
| page-11 | a | Three safeguard lines (pilot L154-156) go to `retired`, with their archived text. | `retired`; refs on the three items |
| page-12 | a | The CX-53 draft sentence on storage and publication is kept. | `core.content_contact_emails.rules` |
| activity-01 | approve | The 180 draft cells replace `{table, rows: open}` on the 30 gated items, with inferred cells listed. | `gate` of the 30 applicability items |
| activity-02 | c | New shared rule for the allowed-pairs check (option text); the pairs list stays open. | `shared_rules.core.rule.allowed_type_action_pairs`; `core.activity_type.rules`, `core.action_type.rules` |
| activity-03 | a, e | Cells for `tool_name`, `model_name` and `developer` change from `not_asked` to `ask` on `policy_guidance` (recorded under `gate.amended`). `procurement_status` stays `ask`. | `gate` of those four items; `shared_rules.core.rule.applicability_table` |
| activity-04 | a, d | Cells as drafted. Governance bodies count as governance actions: a new shared rule, referenced from the governance gate. | `shared_rules.core.rule.governance_gate`; `gate.rule` of `core.governed_population`, `core.governance_form`, `core.governance_direction`; `core.action_type.rules` |
| activity-05 | a | Unknown-type activities are asked everything; the table reads the type after the check. | `shared_rules.core.rule.applicability_table` |
| activity-06 | b | Contract clauses become their own governance activity. | `shared_rules.core.rule.safeguard_attachment`; refs on `core.has_*` |
| activity-07 | b | The quote step runs for every activity; skipped items are kept internally and published as "not asked". | `rules` of `core.tool_name`, `core.model_name`, `core.contracting_party`, `core.deployment_scale_number`, `core.developer`; `shared_rules.core.rule.applicability_table` |
| activity-08 | b | Series break documented. | `translation_v25.series_break` of `core.tool_name`, `core.contracting_party`, `core.developer`, `core.year_pilot_start`, `core.year_production_start` |
| activity-09 | a | `not_asked` is removed from the interface answers (only the table sets it). | `core.interface.values`, `.rules` |
| activity-10 | b | `requires_or_promotes` is split into `requires` and `promotes`. | `core.governance_direction.values`, `.rules`, `.long_page_rule.order` |
| activity-11 | a | Any condition or mix gives `restricts_with_conditions`, with a mapping step across parts. | `core.governance_direction.rules`, `.long_page_rule.mapping` |
| activity-12 | b | COFOG top level: codes from value-lists Candidate B, labels from the option text (asserted equal). | `core.service_domain.values` |
| activity-13 | a, b | `other` added; answers are multi-select, all that apply. | `core.service_domain.values`, `.answer_type`, `.order_tie_rule`, `.rules` |
| activity-14 | b | Two linked parts in one item: relationship and searched-institution role. The two-part combining order comes from the draft. | `core.observed_actor_relationship.values`, `.rules`, `.long_page_rule` |
| activity-15 | a | New internal item `core.observed_actor_role`. Codes are read by the builder from `git 052fcb2:g3o/common/evidence_review.py`, the source value-lists.json cites, and asserted equal to the draft's list. | `core.observed_actor_role` (whole item) |
| activity-16 | b | `has_component` and `governed_by` added. | `core.activity_segment.values`, `core.activity_relation_cross_page.values`, `vocabularies.relation` |
| activity-17 | a | Components are linked, not merged; when two links fit, `governs` wins. | `rules` of `core.activity_segment`, `core.activity_relation_cross_page` |
| activity-18 | b | Links are coded per pair of passages. | `core.activity_segment.rules` |
| activity-19 | approve | Combining rules taken as drafted. | `long_page_rule` of `core.activity_segment`, `core.observed_actor_relationship`, `core.procurement_status`, `core.build_arrangement`, `core.interface`, `core.contracting_party`, `core.developer`, `core.genai_mechanism_basis`, `core.outcome_kind`, `core.governance_direction` (base order) |
| activity-20 | a | `highest_probability` (most sure wins). | `long_page_rule` of `core.activity_type`, `core.action_type`, `core.model_origin`, `core.deployment_mode`, `core.service_domain` |
| activity-21 | a | Discontinued first, as drafted. | `core.adoption_stage.long_page_rule` |
| activity-22 | b | `combined_list`, then a mapping step (staff + public reads as "both"). | `long_page_rule` of `core.target_users`, `core.governed_population` |
| activity-23 | b | Order yes, no, unclear (the draft's alternative (b)). | `long_page_rule` of the four `core.has_*` items |
| activity-24 | b | `combined_list` of (number, unit) pairs. | `long_page_rule` of `core.deployment_scale_number`, `core.deployment_scale_unit` |
| activity-25 | approve | Draft cells: CX-02 (shared grain rule), CX-60, CX-61 and CX-61b (incident value); OUTCOME_KIND supplies the three value definitions. | `shared_rules.core.rule.cx_grain`; `core.outcome_kind.values` / `.rules`; `core.incident_kind.values` / `.rules`; `rules` of `core.reported_outcomes`, `core.reported_incidents` |
| activity-26 | a | CX-60 applies to old rows only (draft text). | `rules` of `core.reported_outcomes`, `core.reported_incidents`; refs |
| activity-27 | a | Incident order as drafted: a reported incident beats the stop signal. | `core.incident_kind.long_page_rule` |
| activity-28 | a | A confirmed stop is recorded only by the stage. | `core.incident_kind.rules` |
| activity-29 | approve | Draft cell for CX-32c; pilot L161 as a classifier line. | `core.evaluation_documented.rules` |
| activity-30 | a | CX-32c as drafted, same row. | `core.evaluation_documented.rules` |
| source-01 | a | First part for both items (see all-06). | `long_page_rule` of `core.source_type`, `core.source_publication_date` |
| institution-01 | b | Order as drafted, plus a rule that each part holds quotes from both activities. | `core.activity_relation_cross_page.long_page_rule.split_rule` |
| institution-02 | a | Pre-filtered pairs store `distinct_action`, marked as set by rule. | `core.activity_relation_cross_page.rules` |
| record-01 | a | New item `core.support_rule_name`, gated on `set_by_rule`. | `core.support_rule_name`; `vocabularies.support_status.rule_name_item` |
| record-02 | a | "Set by rule" for anything a rule fixed, including "not asked". | `core.support_status.rules`; `vocabularies.support_status.rules` |
| record-03 | c | New item `core.support_status_second_reason`; its codes are open. | `core.support_status_second_reason`; `vocabularies.support_status.second_reason_item` |
| shared-01 | a | Date-origin mapping, plus the new yes/no item `core.date_upper_bound`. | `vocabularies.provenance.date_origin_map`; `core.date_upper_bound`; refs on `core.stage_as_of_basis` |
| shared-02 | a | Two definitions, `stated` and `quoted_by_quote_step`, cut from the option text. | `vocabularies.provenance.values` |

No round-3 id is left without a codebook change. `verify_round3()` checks this, and would also accept a line here that marks an id "no codebook change" with a reason.

## 2. Remaining `open` fields

Build counts:

| Count | Before (round-2 skeleton) | After |
|---|---|---|
| Open leaves | 220 | 168 |
| Open item fields | 214 (116 items) | 164 (120 items) |

Most of what stays open is procedural: 120 `version_introduced` and 32 `translation_v25`, under P2 and P3. Leaving those aside, open item fields fell from 66 to 12. `verify_round3()` fails if any `open` leaf is missing from the table below.

| Field | Items | Reason |
|---|---|---|
| `version_introduced` | all items | The release label is set at sign-off (procedural P3, t010-rulings 2026-10-29). |
| `translation_v25` | `core.page_verdict`, `core.source_type`, `core.source_title`, `core.source_language`, `core.source_snippet`, `core.source_credibility`, `core.adoption_stage`, `core.model_origin`, `core.build_arrangement`, `core.interface`, `core.function_drafting_writing`, `core.function_summarization`, `core.function_translation`, `core.function_search_retrieval`, `core.function_code`, `core.function_image_audio_video`, `core.function_extraction_classification`, `core.function_analysis_recommendation`, `core.contracting_party`, `core.developer`, `core.deployment_mode`, `core.year_pilot_start`, `core.year_production_start`, `core.outcome_kind`, `core.incident_kind`, `core.reported_outcomes`, `core.reported_incidents`, `core.uncertainty_flags`, `core.has_genai_activity`, `core.confidence`, `core.institution_summary`, `core.codebook_release` | Translation cells stay open until the translation table exists (procedural P2). No round-3 ruling touches them. |
| `long_page_rule` | `core.adoption_stage` | `permanent_pilot_across_parts`: activity-21 says the gap (permanent-pilot facts split across parts) "is open under every option". |
| `long_page_rule` | `core.governance_direction` | `rank_of_requires_vs_promotes`: activity-10 b split the value, and the drafted order had one slot for it. The two are listed in option-label order as a placeholder; their rank is not ruled. |
| `long_page_rule` | `core.target_users`, `core.governed_population` | `mapping.other_lists`: activity-22 b gives only staff + public → "both". The mapping for any other collected list is not ruled. |
| `long_page_rule` | `core.service_domain` | `multi_select_vs_single_winner`: activity-20 a says the most-sure answer wins, but activity-13 b makes the item multi-select. How a single-winner rule applies to a multi-answer item is not ruled. |
| `long_page_rule` | `core.content_data` | No combining rule is drafted, because the combining draft treated the item as derived. page-07 a makes it a page yes/no question again. |
| `long_page_rule` | `core.observed_actor_role` | New item (activity-15 a); no combining rule drafted. |
| `gate` | `core.content_contact_named`, `core.content_contact_details` | No source sets their gate. The CX-51 draft limits only the five derived items and `content_data` to GenAI pages. |
| `rules` | `core.observed_actor_relationship` | activity-14 b commits to "rules for publishing it as one column", but none are drafted. |
| `rules` | `core.service_domain` | r2#62 ruled `general_administration`, which the COFOG list chosen in activity-12 b does not contain. Whether it is dropped, kept or mapped to `general_public_services` is not ruled, so it is left out of the values for now. |
| `values` | `core.support_status_second_reason` | record-03 c creates the item, but which codes the second reason takes (presumably the `downgraded_*` values) is not ruled. |

Open paths outside items:

- `release.label`: set at sign-off (P3).
- `release.signature_record`: set at sign-off (P4).
- `shared_rules.core.rule.allowed_type_action_pairs.0.pairs`: activity-02 c requires a list of allowed (type, action) pairs, and no source gives one.

## 3. SPEC CONFLICTS (folded codebook vs SPEC v001.6 text)

These are for the integrator's next delta. Each entry quotes the SPEC row and clause, then says where the folded codebook departs from it.

1. **R-045** (four missing labels). SPEC: "Missing-value tokens: one reserved set: "not asked" (`not_applicable` renamed "not asked" everywhere, T2), "not documented", "unknown"." The codebook now has a fourth reserved label, `_NA_`, for items on a row with no activity (all-01 b). R-041 still lists `_NA_` among the values that "need none", which is consistent with a fourth label, but not with R-045's single set of three.
2. **R-044 and R-045** (temporary per-part value). R-044 sets "a per-item combining rule stated in the codebook (rule types: first section, any yes, priority order, earliest year, combined list, highest probability)". all-03 adds a temporary answer, "not covered by this part", to every question in every part prompt. It is neither a value nor a reserved token, it never votes in combining, and if every part gives it the page becomes "not documented". Neither row provides for it.
3. **R-044** (six rule types). SPEC: "(rule types: first section, any yes, priority order, earliest year, combined list, highest probability)". Departures:
   - A mapping step after combining for `governance_direction` (activity-11 a).
   - `combined_list` followed by a mapping to one value for `target_users` and `governed_population` (activity-22 b).
   - A two-tier verdict order (page-02 b), against "The verdict order for combining long-page parts is S3 a: confirms_activity, ambiguous_attribution, ambiguous_genai, other_body, event_only, background_only, confirms_absence, no_genai, not_assessable".
4. **R-044** (first part and missing ranking). The row still carries the text "Page fields take the first chunk's value; ... ordered vocabularies take the first value in table order found in any chunk." Departures:
   - all-06 a takes the first part with a supported answer and skips silent or failed parts.
   - source-01 a applies that first-part rule to `source_type` and `source_publication_date`, which are source-level items, not page fields.
   - all-04 b inserts `not_documented` and then `unknown` after the signed table order of `evaluation_documented`.
   - all-05 a takes the quote from the most-sure part. This fits "The supporting quote comes from the chunk that produced the code", but replaces CX §11.1's "first value found" (CX-01.2 text, not SPEC).
5. **R-041** (support status). SPEC: "Support-status values: supported / downgraded_no_quote / downgraded_low_confidence / downgraded, quote does not state the value / one "set by rule" value with a rule id (exempt from the no-quote downgrade) / not_required". Departures:
   - The status now has two companion items: `core.support_rule_name` holds the rule id as its own item (record-01 a), and `core.support_status_second_reason` records a second failure reason (record-03 c).
   - record-02 a gives "set by rule" to rule-fixed values, including `not_asked`, and keeps `not_required` for `not_documented` and `unknown` only. R-041 groups these together: "`no`, `unknown`, `not_documented`, `_NA_` and negative page verdicts need none".
   - R-041 says a failed verdict's "support status says `downgraded`". page-02 b now also ranks failed verdicts below supported ones.
6. **R-017** (relation list). SPEC: "One shared relation list serves within-page and cross-page links: same activity, component of program, shared participation, governs, distinct, unresolved, plus not-an-activity within a page (r2#22)." Departures:
   - The list gains the reverse values `has_component` and `governed_by` (activity-16 b).
   - "distinct" is spelled `distinct_action` (all-11).
   - When two links fit one pair, `governs` wins (activity-17 a), and within-page links are coded per pair (activity-18 b). SPEC states neither.
7. **R-014** (one relationship, no separate role column). SPEC: "the attribution role becomes part of that relationship, describes only the searched institution ...; there is no separate P06 column". Departures:
   - The item now has two linked parts, relationship and searched-institution role (activity-14 b), and its one-column publication rule is still owed.
   - A separate internal item for the observed actor's role, `core.observed_actor_role`, is kept (activity-15 a).
8. **R-002 / R-023** (page items derived, not asked). R-002 says: "The page `content_*` descriptive and safeguard items are derived from activity codes, not asked (r2#19, r2#10)". The R-023 note says: "the page `content_*` descriptive items are derived from activity codes, replacing X05's question (r2#19)". Under page-07 a, `content_data` stays a page question.
9. **R-003 / R-045** (meaning of "not asked"). R-003 says: "The page `content_*` gate (X05) acts through derivation from activity codes". R-045 defines "not asked" as ruled out by a rule. page-09 c makes the description items and `content_data` "no", not "not asked", on pages whose verdict shows no GenAI, so the gate's gated-out value is `no`.
10. **R-015 / R-005** (published summaries). R-015: `not_assessable` is "left out of the base for institution-level rates". R-005: "distinct/unresolved relations never merge". all-07 c maps `unresolved` and `not_assessable` onto `unknown` in published summaries, and its `commits_to` names "a restated institution rule" that SPEC does not yet contain.
11. **R-004** (additions to applicability). SPEC: "applicability keyed on `activity_type`, not action type (C06, r2#8; governance-only items gate on action type `governance`, T4)". The codebook adds two things SPEC does not state:
    - An allowed (type, action) pairs check (activity-02 c).
    - Governance bodies treated as governance actions (activity-04 d).
12. **R-040** (quote step on skipped items). SPEC: "the quote step never sees the answer for the field it quotes, but may see that a gate is not `none` (r2#18)". activity-07 b runs the quote step for every activity, including items the table skips, keeps those copies internally and publishes them as "not asked". This is not contradicted, but it widens what the quote step runs on.
13. **D-009 / R-090** (date origin). D-009 says: "date-origin values use the shared provenance vocabulary, T3". shared-01 a fits the date origins into the five provenance values and adds a separate yes/no item, `core.date_upper_bound`, which neither row names.

A ruling conflict that is not a SPEC conflict (SPEC names no service-area values): activity-12 b's COFOG list has no `general_administration`, which round 2 (r2#62) ruled as a value. This is listed as open in section 2.

## 4. Could not apply as written; integrator mechanics to check

Wording owed. The ruling is recorded as a direction slot, and the PI or drafter writes the text:

- **page-04 b**: the CX-13 sentence naming compliance reports under non-AI rules as formal records.
- **page-08 b, c**: the CX-51 pairing sentence (users with `governed_population`; vendor including looked-up developers).
- **page-09 c**: the CX-51 "on other pages they are not asked" clause.
- **page-01 c**: the note text itself.
- **activity-14 b**: the publication rule.

Mechanical choices made in applying the rulings, surfaced for sign-off:

1. **`_NA_` placement.** `_NA_` is added to `missing_tokens` of every item whose level includes `activity` (all-01 b: "items of a row that has no activity"). Page-level items are left alone.
2. **Generator check 16** (item-template §4). The temporary value "not covered by this part" lives only in `combining_conventions.not_covered_by_this_part`; it is not a value on any item. The generator must add it to every question in every part prompt of a long page. Check 16's "full rules beside every value" expansion must also carry the convention sentence that the text is only part of the document (all-03 reading). It must not publish the value or let it vote.
3. **Missing tokens out of value lists.** Missing-token codes in the draft lists (`not_asked`, `not_documented`, `unknown`) are kept out of `values`, per template check 8, and stay in `missing_tokens`. Interface `not_asked` is set only by the table (activity-09 a). `unresolved` and `not_an_activity` stay values.
4. **Safeguard order.** For the `has_*` order (activity-23 b), the real answers come from the draft's alternative (b). The missing labels come from the drafted order, then are ranked by all-04 b, which yields yes, no, unclear, not_documented, unknown.
5. **Frozen-signature fields.** They read `CX-01.3 (draft, unsigned):<rows>`, keeping each item's row range after the prefix.
6. **Respelling.** `discontinued_uncertain` is respelled to `discontinuation_uncertain` in the CX-61b and OUTCOME_KIND draft cells (all-11). Each slot records the transform; `verify_round3()` checks the un-transformed text against the draft.
7. **Per-item combining prose not carried.** The draft's basis, probability, downgraded_parts, alternative and failure-case prose is not copied into items. Only the rule type and order are taken, plus the draft sentences a ruling relies on (alternatives for activity-22 and 24; the role-part sentence for activity-14). Several downgraded_parts texts say `unknown` ranks above `not_documented`; all-04 b supersedes them.
8. **pilot.py lines.** The edited lines (L134, L161, L203, L173-177) are attached to their items as `classifier_line` rules, value definitions or instructions. Unchanged pilot.py lines stay out of the codebook, as before. The retired lines are in `retired`.
9. **Service area `other`.** The code comes from the value-lists flag "add `other`". It has no label, because the option text gives none.
10. **Stale CX-53 sentence.** The sentence "Not yet in the installed instrument" is kept, as page-10 says.

## Final fold (2026-10-30)

PI, chat, 2026-10-30: "all accepted" (t010-rulings.md, 2026-10-30; RC-D-003 §16). Folded by an integrator subagent (Claude Code, claude-opus-5-5) for session `20261029-claude-v2-b92f4144070ec139`. Uncommitted.

- **Sources.** Picks and sentences: `drafts/final-open.json`. O12, O14, O15 and the activity-14 b gate: the approved text of `deltas/RC-D-003.md`.
- **Slot convention.** New slots have origin `PI 2026-10-30 "all accepted"; final-open <id>` or `...; RC-D-003 <id>`, and the marker "PI-approved text (2026-10-30, "all accepted") — PI to write or line-edit".
- **Checks.** `verify_final()` checks every such slot verbatim against its file. An edited CX cell must equal its draft cell with the accepted edits applied.

| Ruling | What changed | Where (item id, field) |
|---|---|---|
| F01 a | Permanent pilot applies within each part only; stated as a known limit | `core.adoption_stage` `long_page_rule.permanent_pilot_across_parts` |
| F02 a | `requires` ranks before `promotes`; the builder asserts the order equals the pick's text | `core.governance_direction` `long_page_rule.rank_of_requires_vs_promotes` |
| F03 a | Real answers decide; missing labels only when no part gives one | `core.target_users`, `core.governed_population` `long_page_rule.mapping.other_lists` |
| F04 a | Rule becomes `combined_list`; each area's quote and certainty come from the most-sure part; `replaces_rule` records activity-20 a | `core.service_domain` `long_page_rule` |
| F05 a | `any_yes`, order yes, no, not_documented, unknown | `core.content_data` `long_page_rule` |
| F06 a | Taken from the same part as the relationship; fallback most sure | `core.observed_actor_role` `long_page_rule` |
| F07 a | Asked on the five GenAI verdicts; `no` elsewhere | `core.content_contact_named`, `core.content_contact_details` `gate` |
| F08 a + W05 | One-column publication sentence (W05); the F08 pick is attached as `pick` | `core.observed_actor_relationship` `rules` |
| F09 a | `general_administration` maps to `general_public_services` | `core.service_domain` `rules` (map) |
| F10 a, O13 | Values are the three `downgraded_*` codes; empty unless two reasons hold. The record-03 c text is marked `amended_by` O13 | `core.support_status_second_reason` `values`, `gate`, `rules`, `refs`; `core.support_status` `rules` |
| O11 | 30 pairs (18 allowed, 12 flag) with their basis, from final-open | `shared_rules.core.rule.allowed_type_action_pairs[0].pairs` |
| O14 | Handling: flag for review, no label changed (RC-D-003 §11 text). The activity-02 c text is marked `amended_by` O14 | `shared_rules.core.rule.allowed_type_action_pairs` |
| O12 | `status_by_answer` map: `no`, negative page verdicts, `not_documented` and `unknown` take `not_required`; `not_asked` and `_NA_` take `set_by_rule`. Uses the RC-D-003 §5 text. The record-02 a text is marked `amended_by` O12 | `vocabularies.support_status`; `core.support_status` `rules`, `refs` |
| O15 | The institution rule keeps both roles, and `not_assessable` stays out of the rate base (RC-D-003 §10 text) | `vocabularies.missing.published_summary_map.institution_rule`; `core.has_genai_activity` `rules`, `refs` |
| O16 | The ten mechanical choices of §4: accepted as folded | no codebook change |
| activity-14 b | The role is asked when the relationship is `other`, and not asked only when it is `unresolved`. The option text is cut before ", not asked (when the relationship is other or unresolved), not documented, unknown." and the omitted tail is recorded on the slot. Gate text from RC-D-003 §16 | `core.observed_actor_relationship` `values.role_gate`, `rules` |
| W01 | CX-13 cell: "or a compliance report under a rule not about AI" | `core.disclosure_form` `rules` (CX-13 slot); page-04 b direction role updated |
| W02 | CX-51 cell: vendor "stated or looked up"; users "or `governed_population`". The five derivation texts are now cut from W02 | `rules` of every CX-51 slot (contact items, `core.content_contact`, `core.content_data`, five derived items); `core.content_*` derivation `draft` |
| W03 | CX-51 cell: on other pages they are `no` | the same CX-51 slots; page-09 c direction role updated |
| W04 | Note sentence added; the page-01 c slot becomes a direction | `core.page_complete` `rules` |
| C P1 | **Not made.** See below | none |
| C P2 | ", or not asked where CX-51 says so" removed from the CX-50 cell | `rules` of `core.content_data` and of the five derived items (CX-50 slot) |

- **P1 not applied.** No line in the worktree, or in either copy of `pilot.py`, carries the sentence.
  - The worktree has no `pilot.py`.
  - `archive/.../index-design/pilot/pilot.py:134` and `g3o-website/planning/index-design/pilot/pilot.py:134` both hold the frozen CX-01.2 text.
  - The CX-01.3 draft of that line (the codebook's `classifier_line (mandated_report)` slot on `core.disclosure_form`) reads "Otherwise a statutory annual report is formal_record." That has no backticks, so it is not identical to W01. It is left unedited, pending the integrator.
- **SPEC pin.** SPEC.md moved to v001.7 during this fold, which breaks six SPEC slot anchors (R-041 ×2, R-017 ×3, R-044). Five whole-row slots would also change text (R-045, R-005, R-015, R-014, R-040).
  - This build therefore reads SPEC v001.6 via a new flag: `python build_skeleton.py --spec-rev 1b319f5`.
  - Without the flag, the build fails until the anchors are re-cut against v001.7.
- **Build.** `items=120 shared_rules=14 retired=15 open_fields=155 sha256=4a36fffb0dcd78f6dc9f2d283dfc68410c2579984d52a346ddb746cc57a1920d`. Identical on two runs.
  - The hash also depends on RC-D-003 line numbers in slot sources.
- **Open fields left.** 155 leaves:
  - `version_introduced`: 120 items (P3).
  - `translation_v25`: 33 leaves on 32 items (P2).
  - `release.label` (P3) and `release.signature_record` (P4).
  - No substantive open field remains. `verify_final()` fails if one appears.
- **Wording slots without text.** These are not `open` leaves. They are value definitions with marker "no approved wording — PI to write", now including the three second-reason codes.

- **Re-cut against SPEC v001.7 (2026-10-30, later).** SPEC.md v001.7 and RC-D-003.md are now final. The builder's default build therefore reads the working SPEC.md again; `--spec-rev` is kept as an option.
  - Re-cut anchors:
    - R-044: "…parts is S3 a:" → "…parts has two tiers:".
    - R-041 ×2: end "(r2#37 merged with r2#53)." → "(r2#37 merged with r2#53; spellings all-11)."
    - R-017 ×3: end "within a page (r2#22)." → "within a page (r2#22; activity-16 b; all-11)."
  - Whole-row slots now take the v001.7 text: R-045, R-005, R-015, R-014, R-040.
  - RC-D-003 refs are read from the final file: lines 96 (O12), 150 (O15), 161 (O14) and 262 (activity-14 b).
  - Build: `items=120 shared_rules=14 retired=15 open_fields=155 sha256=55bdd7533fe73062f4f34ec3adbd88d0da0a80389573c340ff627653e54600f2`. Identical on two runs; all checks pass.
  - Overlaps were kept, not deduped:
    - The R-041 slot and the O12 slot.
    - The R-005 slot and the O15 slot.
    - The R-014 slot and both the activity-14 b gate slot and the W05/F08 slot.
- **PI "1a, 2a" (chat, 2026-10-30), folded into the same rebuild.**
  - **1a.** The CX-01.3 classifier line (`core.disclosure_form`, `classifier_line (mandated_report)`) changed. Before: "Otherwise a statutory annual report is formal_record." After: "Otherwise a statutory annual report or a compliance report under a rule not about AI is formal_record." No backticks; origin `PI 2026-10-30 "1a"; final-open W01`.
  - **2a.** Three option texts are cut before the part that was overridden, as activity-14 b was. The `amended_by` tags are dropped, and each slot records `omitted_tail` and `omitted_by`:
    - record-02 a: kept `"Not required"`; omitted " only for answers that need no quote by their nature (not documented, unknown)."
    - activity-02 c: kept "List the allowed (type, action) pairs; activities with other pairs are flagged for review"; omitted " or have one label corrected."
    - record-03 c: kept "A second reason item"; omitted ", or a combined value."
  - Build: `items=120 shared_rules=14 retired=15 open_fields=155 sha256=23cb4857a6f9fb525c52f969d4b1922f252f0bf36c6f9cf060be8ea1fb28bf8b`. Identical on two runs; all checks pass.
