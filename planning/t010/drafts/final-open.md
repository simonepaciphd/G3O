# Last open choices and owed sentences (DRAFT for sign-off)

2026-10-29. Drafted by a subagent (claude-opus-5-5). Nothing applied. Machine-readable copy: `final-open.json`. The release label and signature record are left for sign-off.

## Picks

| Choice | Pick | Confidence |
|---|---|---|
| Long pages: the permanent-pilot rule when its facts sit in different parts | Within-part only, stated as a known limit | low |
| Long pages: rank of 'requires' against 'promotes' in the rule-direction order | Requires before promotes | high |
| Long pages: audience lists other than staff plus public | Real answers decide; missing labels only when no part gives one | high |
| Long pages: service area is now tick-all-that-apply | Combined list of every supported area | medium |
| Long pages: the page question on whether data handling is described | Any yes | high |
| Long pages: role of the actor seen on the page | Same part as the relationship | medium |
| Which pages get the two contact questions | GenAI pages only; 'no' elsewhere | low |
| Publishing the two-part 'whose activity' item as one column | One column, compound value | medium |
| Service area: what happens to 'general administration' | Map it to 'general public services' | medium |
| Codes for the second failure reason | The three downgrade codes; empty unless two reasons hold | medium |
| Allowed (type, action) pairs | 18 allowed, 12 flagged of 30 | medium |

## Why each pick

**Long pages: the permanent-pilot rule when its facts sit in different parts** — Within-part only, stated as a known limit (low). Smallest change, and the case gets stated. You turned down new kinds of combining rule for stage and for scale. The facts stay in the record as their own items. Against it: your keep-information habit points to re-asking the stage, and your call to derive the permanent-pilot flag points to a new item.

- Within-part only, stated as a known limit (pick): The stage question applies the permanent-pilot rule inside each part. If the facts (over 12 months; full user base) sit in different parts, no part reaches production and the combined stage stays pilot. The codebook states this case. Benefit: No new step or question; the signed rule text is unchanged; the case is stated, not left silent. Risk: Long pages whose facts are split under-count production.
- Re-ask the stage over the pooled stage quotes: When the combined stage is pilot and the activity spans more than one part, ask the stage question once more over the stage quotes pooled from all parts, so the rule sees both facts. Benefit: Closes the gap with the existing question and quote machinery; nothing lost. Risk: A new kind of combining step and one more paid call per affected activity; needs wording and test pages.
- New yes/no item on the full user base; derive after combining: Add an activity question 'serves its full intended user base' (any yes across parts). After combining, stage pilot + earliest pilot year at least 12 months before the source date + that item yes gives production, set by rule, and the permanent-pilot flag yes. Benefit: Deterministic; fits the ruling that permanent pilot is a derived flag. Risk: A new question to word, sign and pay for; the 12-month test on whole years is coarse.

**Long pages: rank of 'requires' against 'promotes' in the rule-direction order** — Requires before promotes (high). You split the value to keep binding duties apart from encouragement, and you have ranked the more specific statement first elsewhere. It is also the placeholder already in the build. Nothing points the other way.

- Requires before promotes (pick): Order: restricts_with_conditions, prohibits, permits, requires, promotes, not_documented, unknown. Benefit: A binding duty in any part is not hidden by encouragement elsewhere; this is why the value was split. Matches the placeholder already in the build. Risk: A single mandatory clause in a mostly encouraging strategy labels the whole instrument 'requires'.
- Promotes before requires: Order: ..., permits, promotes, requires, not_documented, unknown. Benefit: The broader stance of the document wins. Risk: Hides binding duties, the distinction the split was made to keep.
- Mixed requires and promotes map to requires (mapping step): Priority order as in a, plus an explicit mapping line: requires + promotes across parts gives requires. Benefit: States the mixed case explicitly, like the ban-plus-permission mapping. Risk: Adds a mapping line that the priority order already implies.

**Long pages: audience lists other than staff plus public** — Real answers decide; missing labels only when no part gives one (high). This writes out three rules you already made: real answers beat 'not documented', which beats 'unknown'; parts that do not cover the item do not vote; and the page as a whole decides.

- Real answers decide; missing labels only when no part gives one (pick): Drop 'not covered by this part' and missing labels from the list. 'both' present, or staff and public both present, gives 'both'. One real value gives that value. No real value: not_documented if any part says the page is silent, else unknown. Every part 'not covered' gives not_documented. Benefit: Uses every real answer; matches the ranking of real answers above missing labels. Risk: An 'unknown' part that might name the other audience is outvoted by a part naming one audience.
- Any unknown alongside a single audience gives unknown: As a, except that a list holding one real audience plus 'unknown' gives 'unknown'. Benefit: Conservative: no single audience is claimed while a part is unsure. Risk: Unclear parts beat clear ones, against the ranking ruled for missing labels.

**Long pages: service area is now tick-all-that-apply** — Combined list of every supported area (medium). You made the item multi-select so that cross-ministry tools are recorded fully, like the form of a rule, which combines as a list. Against it: before the item became multi-select, you picked 'most sure wins' for it.

- Combined list of every supported area (pick): Take every area any part ticks with a supported answer. Each area's quote and certainty come from the part most sure of it. Missing labels only if no part ticks a real area. Benefit: Cross-ministry tools are recorded fully, the purpose of making the item multi-select; same rule as the multi-select form of a rule. Risk: Departs from the 'most sure wins' rule set for this item; one stray tick in a long page adds an area.
- The most-sure part's whole set: Take the set of areas from the single part with the highest certainty. Benefit: Keeps the 'most sure wins' rule as ruled. Risk: Areas named only in other parts are lost, the opposite of the multi-select aim.
- Combined list, but 'other' dropped when a listed area is present: As a, then remove 'other' if any listed area was ticked. Benefit: Keeps 'other' for activities that truly fit no area. Risk: Loses an unlisted area that an activity covers besides a listed one.

**Long pages: the page question on whether data handling is described** — Any yes (high). The other page yes/no questions use 'any yes', and the computed page items are yes if any activity is yes. Nothing points the other way.

- Any yes (pick): Yes if any part says yes; otherwise no if any part says no; then not_documented, then unknown. Benefit: Same rule as the other page yes/no questions (page refers onward, named contact); a description in any part counts. Risk: One loose 'yes' in any part decides.
- First part: Take the first part with a supported answer. Benefit: Matches the rule for document type. Risk: A description later in the page is missed.

**Long pages: role of the actor seen on the page** — Same part as the relationship (medium). One question asks for the role and the relationship together, and you accepted 'take the role from the same part' for the two-part item. Against it: your 'most sure wins' rule for unranked items.

- Same part as the relationship (pick): Take the role from the part that produced the combined relationship; if that part gives no real role, take the most-sure real role from the other parts. Benefit: Role and relationship describe the same actor mention, as they were asked together. Risk: A detailed role stated in another part can be passed over.
- Most sure wins: Take the role with the highest certainty across parts. Benefit: The rule chosen for other items with no natural ranking. Risk: The role may describe a different mention of the actor from the relationship.

**Which pages get the two contact questions** — GenAI pages only; 'no' elsewhere (low). You gate all page content items on the GenAI verdicts, and you chose 'no' over 'not asked' so that every page has a value. Against it: you named only the description items and the data item, and 'no contact details' is often false (footers).

- GenAI pages only; 'no' elsewhere (pick): Gate on the five GenAI verdicts, as the data question; pages with no GenAI get 'no'. Benefit: Same base and same value as the other page description items; every page gets a value. Risk: 'No contact details' is false on many non-GenAI pages (footers give addresses).
- GenAI pages only; 'not asked' elsewhere: Gate on the five GenAI verdicts; pages with no GenAI get 'not asked'. Benefit: Follows the round-1 page-item gate; no false 'no'. Risk: Contact items alone use a different base from the other description items.
- Every page: No gate; both questions are asked on every page. Benefit: True values on every page. Risk: Paid questions on pages with no GenAI; 'responsible for the activity' has no activity to refer to; more e-mails extracted and stored.

**Publishing the two-part 'whose activity' item as one column** — One column, compound value (medium). You picked the two-part design because it records combinations, and you publish everything you choose. A single column respects 'no separate role column'. Found on re-check: the option you approved says the role is not asked when the relationship is 'other', but its own example is 'other' plus 'beneficiary'. Please rule which one holds.

- One column, compound value (pick): Publish relationship, then ':' and the role when the role is a real answer (e.g. `unit_of_institution:contracting_authority`); otherwise the relationship alone. Missing role labels stay internal. Benefit: One column; combinations are published, not lost. Risk: Readers must split the value; many distinct published codes.
- Relationship only; role internal: Publish the relationship part; keep the role internally. Benefit: Simplest; no compound codes. Risk: The role, including 'beneficiary', is not published, against publishing every chosen item.
- Map each pair to one public value: A fixed table maps each (relationship, role) pair to one value from a single list. Benefit: One plain value per row. Risk: Brings back the overlaps the two-part design removed; combinations are lost.

**Service area: what happens to 'general administration'** — Map it to 'general public services' (medium). Your international list places general administration under general public services, which is how the question itself framed tax. Against it: keeping information favours keeping the value, and you ruled it earlier.

- Map it to 'general public services' (pick): No separate value. A rule says the earlier 'general administration' is coded 'general public services'. Benefit: Keeps the international list intact and comparable with Public Sector Tech Watch; whether a tool is internal is already carried by activity type. Risk: Internal support tools share an area with tax, legislatures and foreign affairs.
- Keep it as an extra value: Add 'general administration' beside the ten functions, for internal support of the institution itself. Benefit: Keeps the earlier ruled value and a home for staff tools. Risk: Overlaps 'general public services'; breaks the one-to-one match with the standard.
- Drop it: Leave it out with no mapping. Benefit: Pure standard list. Risk: The earlier ruled value disappears without a stated home.

**Codes for the second failure reason** — The three downgrade codes; empty unless two reasons hold (medium). You asked for both reasons to be recorded, and a separate item is already built. The order of the two follows the existing check order. Against it: you declined to give either reason precedence.

- The three downgrade codes; empty unless two reasons hold (pick): Values: downgraded_no_quote, downgraded_low_confidence, downgraded_quote_not_stating_value. The main status takes the first failed check in check order (quote, then the 0.8 bar); the second item takes the other; empty when only one reason holds. Benefit: Uses existing codes; nothing hidden; works if the checks change. Risk: In practice only 'low confidence' ever appears second, so two of the three codes are unused.
- Low confidence only: One value, downgraded_low_confidence; empty otherwise. Benefit: Exactly the cases that occur (a missing quote and a quote that misstates cannot co-occur). Risk: Rigid if the check order changes.
- Combined values in the main status, no second item: e.g. downgraded_no_quote_and_low_confidence; drop the second item. Benefit: One field. Risk: Undoes the item the fold built; longer status list.

## Allowed (type, action) pairs

No source gives this list. It is inferred from the activity-type definitions, the definition of a program as a container with named components, your definition of one activity, the mismatches the draft named, your ruling that governance bodies count as governance, and your ruling that unknown-type activities are asked everything. A flag sends the activity to review or to a label correction; it does not forbid the pair.

| Type \ action | deployment | governance | staff_training | program | unknown |
|---|---|---|---|---|---|
| policy_guidance | flag | allowed | flag | flag | flag |
| pilot_experiment | allowed | flag | allowed | flag | allowed |
| program_initiative | allowed | allowed | allowed | allowed | allowed |
| internal_operational | allowed | flag | flag | flag | allowed |
| public_facing_service | allowed | flag | flag | flag | allowed |
| unknown | allowed | allowed | allowed | allowed | allowed |

Flag reasons: a policy acting as a deployment, or with an unknown action, gets neither question set. A tool type with a governance action gets both. Staff training is its own activity, typed as a program. A program container belongs to the program type. Least certain allowed cell: pilot x staff training.

## The five sentences

Diff notation: [-removed-] {+added+}.

### Mandated reports: compliance reports under rules not about AI

Before: The obligation must be named on the page, except that it may be inferred from the document's genre **when the document's title names AI or algorithmic reporting**. Otherwise a statutory annual report is `formal_record`. This is the one stated exception to CX-03.

After: The obligation must be named on the page, except that it may be inferred from the document's genre **when the document's title names AI or algorithmic reporting**. Otherwise a statutory annual report or a compliance report under a rule not about AI is `formal_record`. This is the one stated exception to CX-03.

Diff: Otherwise a statutory annual report {+or a compliance report under a rule not about AI+} is `formal_record`.

### Which activity answers feed the computed page items

Before: `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer or contracting party; users: `target_users`; status or date: `adoption_stage` or a year field), otherwise no.

After: `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no.

Diff: vendor: model developer{+, stated or looked up,+} or contracting party; users: `target_users`{+ or `governed_population`+};

### Pages with no GenAI: 'no' instead of 'not asked'

Before: The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are not asked.

After: The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.

Diff: on other pages they are [-not asked-]{+`no`+}.

### Note that 'yes' on the page-complete item means incomplete

Before: Add a note in the codebook that yes means incomplete.

After: Note: `yes` means incomplete (the page refers the reader onward); the name `page_complete` reads the other way.

Diff: [-Add a note in the codebook that-]{+Note:+} [-yes-]{+`yes`+} means incomplete{+ (the page refers the reader onward); the name `page_complete` reads the other way+}.

### Publishing the two-part 'whose activity' item as one column

Before: no text yet (the slot is empty).

After: Published as one column: the relationship code, then `:` and the role code when the role is a real answer (e.g. `unit_of_institution:contracting_authority`); otherwise the relationship code alone. The role is never published as a separate column.

Diff: {+Published as one column: the relationship code, then `:` and the role code when the role is a real answer (e.g. `unit_of_institution:contracting_authority`); otherwise the relationship code alone. The role is never published as a separate column.+}
