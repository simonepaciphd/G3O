# Draft value lists (for PI review)

Drafted 2026-10-29 by a subagent for the integrator. Nothing here is final. Codes only, each tied to the words of the ruling it comes from; no definitions. Full sources per code: `value-lists.json` in this folder.

## 1. Interface

| Code | Ruling words |
|---|---|
| `conversational` | conversational |
| `backend_or_api` | back-end or API |
| `other_interface` | other interface |
| `not_asked` | not applicable (renamed "not asked" everywhere) |
| `unknown` | unknown |

Flags:
- "Other interface" was drafted behind the scenes as `other_ui`. Pick one spelling.
- "Not applicable" was meant for policy activities with no tool. If only the applicability table sets it, "not asked" fits. If the classifier can still choose it, a classifier answer ends up named "not asked", which contradicts what "not asked" means.
- "Not documented" (page silent) is not in the ruled list. Either a silent page is `unknown`, or `not_documented` is added, since new fields are meant to take the full missing-value set.
- One answer only: a tool offered as a chat window and through an API must pick one.

## 2. Governance direction

| Code | Ruling words |
|---|---|
| `prohibits` | prohibits |
| `restricts_with_conditions` | restricts with conditions |
| `permits` | permits |
| `requires_or_promotes` | requires or promotes |
| `unknown` | unknown |
| `not_asked` | not applicable otherwise (asked only for governance activities) |

Flags:
- **"Requires or promotes": one value or two?** As one value, a binding duty to use GenAI is pooled with encouragement. As two (`requires`, `promotes`), the two are kept apart, at the cost of one more value and a finer line to code.
- "Permits subject to conditions" fits both "restricts with conditions" and "permits". The list does not say which applies.
- One policy can ban some tools and permit others. The question takes one answer, and no ordering rule is ruled.
- "Not documented" is missing here too (same choice as for interface).

## 3. Service area

Ruled: `general_administration` ("general administration") and `unknown`. **The list of areas is not given anywhere.** G3O's own texts name only examples: "health, tax or justice" (the question) and "health, tax, justice, education, general administration" (the review that proposed the field). G3O has no service-area taxonomy of its own. Three candidates follow, with no recommendation:

**A. US Federal AI Use Case Inventory, 2024 topic areas** (checked in the raw file G3O ingested): Government Services (includes Benefits and Service Delivery); Diplomacy & Trade; Education & Workforce; Energy & the Environment; Emergency Management; Health & Medical; Law & Justice; Science & Space; Transportation; Mission-Enabling (internal agency support) → general administration; Other.
- For: built for government AI uses; has an internal-support area matching "general administration"; matches a source G3O already cites.
- Against: US-federal only. Tax, finance and defence are not areas (finance shows up only in free-text "Other"). Local services have no clear place. It adds "Other", which the ruling does not list.

**B. COFOG level I (UN/Eurostat functions of government)**, as used by Public Sector Tech Watch (in G3O's inputs): General public services; Defence; Public order and safety; Economic affairs; Environmental protection; Housing and community amenities; Health; Recreation, culture and religion; Education; Social protection. Nine of these appear in the Tech Watch file. Defence comes from the COFOG standard and should be checked against it.
- For: an international standard that fits any country and level; compares directly with Tech Watch; has a finer second level if needed.
- Against: "General public services" also holds tax, legislatures and foreign affairs, so tax disappears into general administration. Courts sit under public order. It classifies by the ministry's function, not by what the tool does.

**C. Only the words in G3O's rulings**: health, tax, justice, education, general administration, unknown.
- For: imports nothing; shortest.
- Against: these are examples, not a list. Most uses (transport, welfare, policing, elections) would fall to `unknown`, so it needs extending before use.

Flags for any list:
- No "other" value is ruled.
- One answer per activity: should a cross-ministry tool be able to take several areas, as governance form now can?
- Where an internal tool in a health ministry goes (health or general administration) depends on which list is chosen.

## 4. Links between activities (one shared list)

| Code | Ruling words | Within a page | Across pages |
|---|---|---|---|
| `same_activity` | same activity | yes | yes |
| `component_of_program` | component of program | yes | yes |
| `shared_participation` | shared participation | yes | yes |
| `governs` | governs | yes | yes |
| `distinct_action` | distinct action ("distinct" in the plan) | yes | yes |
| `unresolved` | unresolved | yes | yes |
| `not_an_activity` | not an activity within a page | yes | no |

Flags:
- **Direction.** "Component of program" and "governs" run one way: a component belongs to a program, and a policy governs a tool. The previous version stored links as unordered pairs. Either keep one code with a fixed order (first item is the component, or the governing policy), or add reverse codes (`has_component`, `governed_by`).
- "Distinct" or "distinct action": pick one spelling. The previous version used `distinct_action`.
- In the previous version, a component link merged the two items into one activity. The new activity definition keeps components as separate activities, linked to the program. The code can stay the same, but its effect changes.
- One pair cannot carry two links (e.g. a program policy that is also a component), and no precedence is ruled.
- Within a page, the round-1 design answered once per passage against one earlier passage ("new / same as k / component of k / not an activity"). The shared list is a list of links between pairs, so it is unclear whether within-page coding is per passage or per pair, and what the first passage gets.
- A link the classifier cannot settle could end up as `unresolved` or as `unknown` (the field's current downgrade target). That gives two codes for "could not tell".
- Across pages, pairs skipped as obviously different get no classifier answer. They could be coded `distinct_action` (set by rule) or "not asked".

## 5. Whose activity it is (observed actor relationship)

The rulings say the institution's role "becomes part of the relationship" and that there is no separate role column. They do not say whether that means one list or two linked parts. Both drafts follow; neither is preferred.

**Draft 1, one list:** `this_institution`, `contracting_authority`, `central_purchasing_body`, `beneficiary`, `unit_of_institution`, `joint_participant`, `other`, `unresolved`, `unknown`.

**Draft 2, two linked parts of one item:**
- Relationship: `this_institution`, `unit_of_institution`, `joint_participant`, `other`, `unresolved`, `unknown`.
- Role of the searched institution: `contracting_authority`, `beneficiary`, `central_purchasing_body`, `unit`, `joint`, `not_asked` (when the relationship is other or unresolved), `not_documented`, `unknown`.

Flags:
- "Unit" and "joint" appear in both source lists. Draft 1 holds each once; Draft 2 repeats them.
- In Draft 1, "this institution", "contracting authority" and "central purchasing body" overlap: all three are the institution acting itself.
- An activity another body runs for this institution is "other" in one ruling and "beneficiary" in the other. The ruling says when "beneficiary" counts (only when the page names it), not whether it replaces "other".
- Draft 1 cannot record a unit that acted as the contracting authority.
- In Draft 2, the role part has no value for an institution simply running its own tool. It also must not turn into a separate public column.
- The earlier actor-role list (issuer, participant, external speaker, service provider, event host, ...) describes the observed actor, not the searched institution. Round 1 kept it; round 2 is silent. Does it stay?

## 6. Shared vocabularies

**How we know (provenance):** `stated`, `from_metadata`, `looked_up`, `derived`, `quoted_by_quote_step`. An earlier draft spelled these `deterministic_metadata`, `lookup` and `extractor_quoted`.
- **Date origin does not fit cleanly.** The ruled date-origin values are meant to use this vocabulary. "Metadata" maps cleanly. "Web address" could be metadata or derived. "Quote from page text" could be quoted or stated. "Archive upper bound" has no clean home, and the fact that it is a bound, not a date, would be lost. "Unknown" is not among the five values, so either the missing-value tokens apply here or `unknown` is added.
- "Stated" and "quoted by the quote step" overlap for web pages.
- The stage date's fallback to the access date has no obvious home. Neither does the planned date-confidence field.

**Support status:** `supported`, `downgraded_no_quote`, `downgraded_low_confidence`, `downgraded_quote_not_stating_value` ("downgraded, quote does not state the value"), `set_by_rule` (with a rule id), `not_required`.
- The two new values have no fixed spelling yet. Earlier drafts used `downgraded_not_entailed`, `deterministic` and `deterministic_rule`.
- The rule id could go in a separate field or inside the value.
- The plan says a page verdict's status reads "downgraded". The round-2 ruling suggests this means one of the existing downgraded values, not a new seventh value.
- "Set by rule" and "not required" overlap for values a rule fixes without a quote, such as "not asked".
- When a code has both no quote and low confidence, no rule says which reason wins.

**Missing values:** `not_asked`, `not_documented`, `unknown`.
- An earlier draft spelled "not asked" as `_NA_`. `_NA_` also still appears in the plan's support rule and in the current data for rows with no activity. Is it the old spelling of "not asked", or a fourth token?
- "Unresolved" and the mechanical "not assessable" verdict work like missing values but sit outside this set.

## Needs the PI

1. Interface: is "not asked" set only by the applicability table, and is `not_documented` added? Spelling: `other_interface` or `other_ui`.
2. Governance direction: is "requires or promotes" one value or two? How is "permits with conditions" coded? Is `not_documented` added?
3. Service area: which list (A, B, C or another)? Add "other"? One answer or several?
4. Activity links: how is direction handled (fixed order or reverse codes)? Spelling of "distinct". Does a component link still merge? Is within-page coding per passage or per pair?
5. Observed actor: one list or two linked parts, and does the earlier actor-role list stay?
6. Provenance: where do web address, archive upper bound and unknown go? Spellings.
7. Support status: spellings of the two new values, and where the rule id goes.
8. Missing values: spelling of "not asked", and whether `_NA_` survives.
