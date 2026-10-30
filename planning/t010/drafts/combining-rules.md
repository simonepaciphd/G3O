# Long-page combining rules (draft for PI review)

Drafted 2026-10-29 by a subagent. Nothing here is final. Each item gets one of the six ruled rule types. Full reasoning, probability and downgrade handling per item: `combining-rules.json` in this folder.

## How every rule works (shared conventions, proposed)

- **Check, then combine.** Each part's answer is checked for a quote and the 0.8 bar before combining. A downgraded answer enters as `unknown`. Page verdicts are the exception: they keep their value and the downgraded tag.
- **Missing values rank last.** In every order: real values first, then `unknown`, then `not_documented`. "Not asked" never competes. It is set after the item that gates it has been combined, so type items are combined first.
- **Which part speaks for the answer.** The combined answer takes the probability and quote of the part that produced it. If several parts gave the winning value, that is the one with the highest probability (ties: earliest part). The older wording ("first value found") would pick the earliest such part instead.
- **"First section"** means the first part with a supported answer. A silent or downgraded first part is skipped.
- **Activity items** combine the answers about the same activity from every part that holds one of its passages, as linked by segmentation. Parts that do not mention the activity do not vote.
- **Pooled evidence** at the institution stage uses the same rules when it is split. "First section" there needs a fixed order for the pool.

## Rules

| Item | Rule | Order (first wins) | Basis | Alternative |
|---|---|---|---|---|
| source_type | first section | | first part has masthead and byline; same as disclosure form | highest probability |
| source_publication_date | first section | | byline date at top; later parts quote other dates | none clearly defensible |
| activity_segment | combined list | | union of passages; segmentation links across parts | none |
| observed_actor_relationship * | priority | this_institution, contracting_authority, central_purchasing_body, unit_of_institution, joint_participant, beneficiary, unresolved, other, unknown, not_documented | mirrors the verdict order (own, then unsettled, then other body) | highest probability |
| activity_type | highest probability | | values have no ranking; a conflict means one part is wrong | priority, tool uses before containers |
| action_type | highest probability | | as activity type | priority with program first |
| adoption_stage | priority (sourced) | discontinued, production, pilot, announced, proposed, unknown, not_documented | "most advanced stage first" is the ruled example; discontinued first is proposed | discontinued last; or latest-dated stage (not one of the six types) |
| procurement_status | priority | payment_or_subscription, award_or_contract, tender_or_rfp, unknown, none_documented, not_documented | most advanced purchase stage first | highest probability |
| model_origin | highest probability | | origins do not nest | priority, a part that names the model first |
| build_arrangement | priority | model_trained_or_fine_tuned_by_institution, custom_application_on_external_model, off_the_shelf_product, unknown, not_documented | values nest; deeper = more specific | highest probability |
| interface * | priority | conversational, backend_or_api, other_interface, unknown, not_documented | named interface before "other" | highest probability |
| contracting_party | combined list | | can be several; same as tool names | first section |
| developer | combined list | | same as tool names; lookup runs on the combined tool list | first section |
| deployment_mode | highest probability | | two values with no ranking | priority, integrated first |
| target_users | priority | both, public, internal_staff, unknown, not_documented | widest audience first | combined list with staff + public read as "both" |
| governed_population | priority | both, external_users, internal_personnel, unknown, not_documented | as target users | as target users |
| governance_direction * | priority | restricts_with_conditions, prohibits, permits, requires_or_promotes, unknown, not_documented | mixed provisions usually mean conditions | most restrictive first; or highest probability |
| service_domain * | highest probability | | no list ruled, so no order can be written | once a list exists: any specific area before general administration |
| genai_mechanism_basis | priority | named_genai_product_or_model, explicit_genai_label, generative_capability_described, ai_chatbot_or_assistant_label_only, unknown, not_documented | strength ladder of the evidence | none needed |
| deployment_scale_number | first section | | quoted number, no probability; must stay paired with its unit | combined list of number-unit pairs |
| deployment_scale_unit | first section | | same part as the number | as number |
| has_human_oversight, has_transparency_notice, has_data_classification, has_risk_assessment | priority | yes, unclear, no, unknown, not_documented | "any yes" does not say what happens when no part says yes; unsettled above stated absence, as in the verdict order | any yes with the same fallback; or yes, no, unclear, not_documented |
| outcome_kind | priority | quantified, qualitative, none_reported, unknown, not_documented | richest report first | highest probability |
| incident_kind | priority | quantified, qualitative, discontinuation_uncertain, none_reported, unknown, not_documented | incident before the weaker discontinuation signal | discontinuation uncertain first |
| activity_relation_cross_page * | priority (type sourced) | unresolved, distinct_action, governs, component_of_program, shared_participation, same_activity, unknown | never merge on conflict; specific link before plain "same" | highest probability |

\* The order depends on a value list that is only drafted, not ruled. For the observed actor, the order is written for the one-list draft. Under the two-part draft, the relationship part uses this_institution, unit_of_institution, joint_participant, unresolved, other, unknown, not_documented, and the role comes from the same part.

Counts: priority order 16, highest probability 5, first section 4, combined list 3. Two items have a sourced rule type; the other 26 are proposed.

## Failure cases worth a look

1. **Audience fields cannot produce "both".** If staff use a tool in one part and residents use it in another, the result is "public", not "both". This applies to target users and governed population. The fix is a combined list read as "both", which needs a mapping step you would have to approve.
2. **Stage: a brief suspension reads as discontinued.** A part covering a suspension that was later lifted puts the stage at "discontinued". Separately, the "permanent pilot" rule needs facts that can sit in different parts, so no single part may reach "production".
3. **Safeguards: an unsettled mention beats an explicit no.** A general privacy section ("all AI is reviewed by humans") outranks "this tool's outputs are not reviewed". The alternative order (no before unclear) fixes this but hides the open signal.
4. **Cross-page links: splitting the pool can block merges.** A part may hold quotes from only one of the two activities, so it answers "distinct" by default and wins. A same-versus-distinct conflict gives "distinct", not "unresolved". Each part should probably hold quotes from both activities.
5. **Scale number keeps the first figure.** "A pilot with 50 users", then later "now 12,000 licences", gives 50. No ruled type picks the latest or largest figure.
6. **Governance direction: a ban plus an approval reads as a ban.** If no part codes "with conditions", a policy that bans public chatbots and approves the in-house one comes out as "prohibits".
7. **Highest probability favours confident short mentions.** A one-line summary at 0.97 beats a detailed later description at 0.91. This applies to activity type, action type, model origin, deployment mode and service area. For action type, it can lose a program whose components appear only in a later part.
8. **Segmentation errors pass through every activity rule.** A passage cut at a part boundary can become two activities. A wrongly linked passage can lift the evidence basis or the purchase stage, or add a developer through the lookup.

## Already set in the skeleton: points to check

- **Page completeness looks reversed.** Yes means "complete", so "any yes" makes a page complete if any one part says so. The earlier ruling meant "incomplete if any part says incomplete". Every part but the last also ends at a cut, so the per-part question has to ignore that.
- **"First section" needs a fallback** for a first part that is silent or downgraded (proposed above). It also needs a fixed pool order for pooled evidence.
- **Evaluation documented:** the table order has no place for `unknown`, the downgrade target. Proposed: just above `not_documented`.
- **Page verdict:** agreed. Since downgraded verdicts keep their value, a downgraded "confirms activity" in one part beats supported negatives in every other part, and the page counts as unresolved. This looks intended; please confirm. The alternative is to rank supported verdicts above downgraded ones.
