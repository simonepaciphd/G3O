# Applicability table: draft for review

Agent draft, 2026-10-29. Not ruled. Which activity-level questions are asked, by activity type (round-2 item 8, b). A = ask, – = not asked, * = rests on inference (see the JSON `basis` for each cell).

Counts: 160 ask, 20 not asked, 38 inferred (13 of them not asked). Sources: `applicability.json`.

| Item | policy | pilot | program | internal | public | unknown |
|---|---|---|---|---|---|---|
| adoption_stage | A | A | A | A | A | A |
| procurement_status | A* | A | A | A | A | A |
| model_origin | – | A | A* | A | A | A |
| build_arrangement | – | A | A* | A | A | A |
| interface | – | A | A* | A | A | A |
| function_drafting_writing | –* | A | A* | A | A | A |
| function_summarization | –* | A | A* | A | A | A |
| function_translation | –* | A | A* | A | A | A |
| function_search_retrieval | –* | A | A* | A | A | A |
| function_code | –* | A | A* | A | A | A |
| function_image_audio_video | –* | A | A* | A | A | A |
| function_extraction_classification | –* | A | A* | A | A | A |
| function_analysis_recommendation | –* | A | A* | A | A | A |
| tool_name | –* | A | A* | A | A | A |
| model_name | –* | A | A* | A | A | A |
| contracting_party | –* | A | A* | A | A | A |
| developer | –* | A | A* | A | A | A |
| deployment_mode | – | A | A* | A | A | A |
| target_users | – | A | A* | A | A | A |
| year_announced | A | A | A | A | A | A |
| year_pilot_start | – | A | A* | A | A | A* |
| year_production_start | – | A | A* | A | A | A* |
| deployment_scale_number | –* | A | A* | A | A | A |
| has_human_oversight | A | A | A | A | A | A |
| has_transparency_notice | A | A | A | A | A | A |
| has_data_classification | A | A | A | A | A | A |
| has_risk_assessment | A | A | A | A | A | A |
| outcome_kind | A* | A | A | A | A | A |
| incident_kind | A* | A | A | A | A | A |
| evaluation_documented | A | A | A | A | A | A |

Not in this table: governed_population, governance_form and governance_direction, which are asked only when action type is governance.

## Tensions

1. Policy that names a tool. The round-1 rulings and the current contract gate tool fields on 'activities without a tool', not on policy_guidance. The activity-unit rule moves approved tools into their own activity, but a policy that bans or restricts a named tool, or an approved-tool list the classifier does not split, would lose tool_name/model_name/developer. Options: keep not_asked on policy_guidance and rely on the activity-unit rule to split the tool off; or ask tool_name/model_name on policy_guidance too.
2. Policy pages often list permitted and prohibited uses (drafting yes, decisions no). The eight function items would be not_asked on policy_guidance, so this content is not captured anywhere in the 30 items (governance_direction records direction, not function).
3. Policy coverage numbers ('applies to all 40,000 staff', '12 departments') resemble deployment_scale_number units (users, units_or_departments). Gating scale out of policy_guidance drops them; asking risks coding coverage as deployment scale.
4. model_origin/build_arrangement on policy_guidance: a policy can require sovereign, open-weight or government-built models. That is a rule about other tools, not the policy's own origin, so the cell stays not_asked, but the requirement has no home among these items.
5. program_initiative is mixed: platform rollouts have a tool; governance bodies and training programs do not. The round-1 ruling said deployment_mode and access_type do not apply to staff_training, but a table keyed on activity_type cannot separate training from rollouts, so every tool item stays ask on program_initiative and that part of the round-1 example is lost (answers fall to unknown instead of not asked).
6. The round-1 example 'proposal-without-tool' cannot be expressed: proposal is now a stage, not an activity type. Proposals of every type are asked the tool items and will mostly return unknown.
7. The unknown row is all ask. v2.5's typical unknown evidence is a purchase record naming a GenAI product, so tool facts are expected. Gating unknown out would lose them; asking everything costs the full question set. Also, activity_type's downgrade target is unknown: an activity whose type is downgraded (no quote / low confidence) moves to the all-ask row, so the table must read the post-downgrade type, and gate order puts activity_type in round 2 ahead of these round-3 items.
8. Two keys on one activity. Tool items gate on activity_type; governed_population, governance_form and governance_direction gate on action_type = governance. Mismatched pairs give odd results: activity_type policy_guidance + action_type deployment gets neither tool items nor governance items; activity_type internal_operational/public_facing_service + action_type governance gets both. Target_users (tool) and governed_population (governance) were meant to be complements, but under two keys both or neither can be asked. A consistency check on the (activity_type, action_type) pair, or a ruling on allowed pairs, would close this.
9. program_initiative includes 'governance bodies'. Whether such an activity is action_type governance (and so gets governance_form, whose values are instruments, not bodies) is not ruled.
10. Safeguards on governance activities: the round-1 ruling defines 'yes' for a governance activity as 'the rule requires it', and the attachment rule forbids copying a policy's safeguard to the tools it governs. So the same safeguard can be yes on the policy and not_documented on the tool. A round-2 ruling also tags contract clauses as a governance answer; a purchase record is usually typed internal_operational or unknown, not policy_guidance, so which activity carries a contract-clause safeguard is unclear.
11. Missing-value tokens: interface keeps a not_applicable value, and the round-1 rulings name not_applicable, while a tidy-up ruling renames not_applicable to 'not asked'. Once the table gates interface out of policy_guidance, the in-enum value only covers tool-less activities inside asked types (e.g. a training program). Whether the classifier may still answer it, or it is dropped as redundant, is open.
12. Extractor and derived items. tool_name, model_name, contracting_party and deployment_scale_number are coded by the quote step, and developer is derived; none is a classifier question. For them 'not asked' must mean 'not extracted' (or extracted then discarded). The quote step may see that a gate passed, which fits the first reading. deployment_scale_unit is gated on the number, so it inherits this table indirectly.
13. Series continuity. v2.5 policy rows hold tool_name 'unknown', vendor 'unknown' (edge case E) and year_deployed values; under this table they become not asked. The round-1 ruling already notes v2.5 unknown values on policy rows cannot be recoded without a rerun, and a round-2 ruling fills year_deployed from pilot/production years, which are both not asked on policy rows.
14. Index denominators: a round-2 ruling drops new not-asked values from item counts, so every policy_guidance not_asked cell changes how policy-heavy institutions score relative to v2.5.
15. procurement_status on policy_guidance: a procurement standard is typed policy_guidance; asking procurement_status on it risks the classifier reading the standard's tender language as a tender. Kept ask (no source gates it out).
16. The seven 'sourced' not-asked cells on policy_guidance rest on reading the rulings' word 'governance' as activity_type policy_guidance. A tidy-up ruling routes the governance-only items to action_type = governance instead, so the same rulings could equally be read as gating these items on action_type. The applicability ruling says action type no longer drives applicability, which supports the activity_type reading, but the mapping is an interpretation.
17. evaluation_documented is coded at activity and page level; this table can only gate the activity-level question.
