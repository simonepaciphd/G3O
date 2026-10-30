<!-- GENERATED FILE - do not edit. Built from codebook/codebook.yaml by g3o.codebook.generators.extractor_prompt_sections. -->
<!-- codebook release: 2.7 | codebook sha256: f0b1348cddbbe1ab0de8e16b80dae64a3e3400fe71788a6673f5cfc52348c72f -->

# Extractor prompt sections

Codebook release `2.7`, sha256 `f0b1348cddbbe1ab0de8e16b80dae64a3e3400fe71788a6673f5cfc52348c72f`. Intended target: T-022 / T-032 extractor prompt sections (path chosen there).

## `core.source_publication_date`
<!-- item: core.source_publication_date sha256: 8183c96a145464289b2baa6ecf2653b7b944cae281dd7624397a13387aaa7320 -->

Column `source_publication_date`; item hash `8183c96a145464289b2baa6ecf2653b7b944cae281dd7624397a13387aaa7320`.

### Rules

1. Take dates from HTML metadata / PDF properties / URL patterns deterministically; if absent, the extractor returns a date with its verbatim quote, validated by R-042.
2. One shared date of 1 November 2022, with "before" needing proof. Date origin is recorded as metadata, web address, quote from page text, archive upper bound, or unknown; the AI-text code changes.

## `core.source_snippet`
<!-- item: core.source_snippet sha256: a26fef1a984c518461bea85a9771caad96db7347f057ec8e66cf035ba014314e -->

Column `source_snippet`; item hash `a26fef1a984c518461bea85a9771caad96db7347f057ec8e66cf035ba014314e`.

### Rules

1. Define `source_snippet` on v2.7 rows as the verbatim supporting text of the page verdict (truncated), with no paraphrase.
2. Snippets are verbatim in every pipeline, no translations are stored, and procurement's rule is amended.

## `core.activity_segment`
<!-- item: core.activity_segment sha256: 44cc63f10ebef97a1402d517332330fb5ff41ffcf9de22de80b87a4f8e57b97e -->

Column `activity_relation_within_page`; item hash `44cc63f10ebef97a1402d517332330fb5ff41ffcf9de22de80b87a4f8e57b97e`.

### Instruction

The extractor proposes spans; jev answers per span: new distinct activity / same as span k / component of span k / not an activity.

### Values

#### `same_activity`
<!-- value: same_activity -->

The two passages describe the same activity: the same action by the same actor on the same tool or instrument.

Rules:
1. One activity = one action (deployment, governance instrument, staff training) by one actor concerning one tool or instrument. A named program is one activity; each named component is its own activity, linked to the program as a component of it. Repeated transactions for the same product by the same unit are one activity. A policy and the tools it approves are separate activities, linked by a "governs" relation.
2. One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page.
3. Add "has component" and "governed by".
4. Components stay separate activities; a governing policy is recorded as governing.
5. Each pair of passages gets a link.

#### `component_of_program`
<!-- value: component_of_program -->

The first passage's activity is a named component of the program described in the second. Both stay separate activities, linked.

Rules:
1. One activity = one action (deployment, governance instrument, staff training) by one actor concerning one tool or instrument. A named program is one activity; each named component is its own activity, linked to the program as a component of it. Repeated transactions for the same product by the same unit are one activity. A policy and the tools it approves are separate activities, linked by a "governs" relation.
2. One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page.
3. Add "has component" and "governed by".
4. Components stay separate activities; a governing policy is recorded as governing.
5. Each pair of passages gets a link.

#### `has_component`
<!-- value: has_component -->

The first passage describes a program, and the second passage's activity is one of its named components. Both stay separate activities, linked.

Rules:
1. One activity = one action (deployment, governance instrument, staff training) by one actor concerning one tool or instrument. A named program is one activity; each named component is its own activity, linked to the program as a component of it. Repeated transactions for the same product by the same unit are one activity. A policy and the tools it approves are separate activities, linked by a "governs" relation.
2. One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page.
3. Add "has component" and "governed by".
4. Components stay separate activities; a governing policy is recorded as governing.
5. Each pair of passages gets a link.

#### `shared_participation`
<!-- value: shared_participation -->

The two passages describe one joint action in which several bodies take part. They are one activity: the two passages are merged. The link needs at least two bodies, each named on the page as taking part, with a quote.

Rules:
1. One activity = one action (deployment, governance instrument, staff training) by one actor concerning one tool or instrument. A named program is one activity; each named component is its own activity, linked to the program as a component of it. Repeated transactions for the same product by the same unit are one activity. A policy and the tools it approves are separate activities, linked by a "governs" relation.
2. One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page.
3. Add "has component" and "governed by".
4. Components stay separate activities; a governing policy is recorded as governing.
5. Each pair of passages gets a link.

#### `governs`
<!-- value: governs -->

The first passage's activity is a policy or other governance instrument that sets rules for the activity in the second (for example a policy and a tool it approves). When a pair fits both this link and a component link, this link is used.

Rules:
1. One activity = one action (deployment, governance instrument, staff training) by one actor concerning one tool or instrument. A named program is one activity; each named component is its own activity, linked to the program as a component of it. Repeated transactions for the same product by the same unit are one activity. A policy and the tools it approves are separate activities, linked by a "governs" relation.
2. One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page.
3. Add "has component" and "governed by".
4. Components stay separate activities; a governing policy is recorded as governing.
5. Each pair of passages gets a link.

#### `governed_by`
<!-- value: governed_by -->

The second passage's activity is a policy or other governance instrument that sets rules for the activity in the first. When a pair fits both this link and a component link, this link is used.

Rules:
1. One activity = one action (deployment, governance instrument, staff training) by one actor concerning one tool or instrument. A named program is one activity; each named component is its own activity, linked to the program as a component of it. Repeated transactions for the same product by the same unit are one activity. A policy and the tools it approves are separate activities, linked by a "governs" relation.
2. One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page.
3. Add "has component" and "governed by".
4. Components stay separate activities; a governing policy is recorded as governing.
5. Each pair of passages gets a link.

#### `distinct_action`
<!-- value: distinct_action -->

The two passages describe different activities, and none of the other links applies.

Rules:
1. One activity = one action (deployment, governance instrument, staff training) by one actor concerning one tool or instrument. A named program is one activity; each named component is its own activity, linked to the program as a component of it. Repeated transactions for the same product by the same unit are one activity. A policy and the tools it approves are separate activities, linked by a "governs" relation.
2. One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page.
3. Add "has component" and "governed by".
4. Components stay separate activities; a governing policy is recorded as governing.
5. Each pair of passages gets a link.

#### `unresolved`
<!-- value: unresolved -->

The page does not settle whether the two passages describe the same activity or different ones. They are kept separate.

Rules:
1. One activity = one action (deployment, governance instrument, staff training) by one actor concerning one tool or instrument. A named program is one activity; each named component is its own activity, linked to the program as a component of it. Repeated transactions for the same product by the same unit are one activity. A policy and the tools it approves are separate activities, linked by a "governs" relation.
2. One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page.
3. Add "has component" and "governed by".
4. Components stay separate activities; a governing policy is recorded as governing.
5. Each pair of passages gets a link.

#### `not_an_activity`
<!-- value: not_an_activity -->

The passage does not describe an activity as the activity rule defines one. In a pair of passages, it is used when either passage is not an activity; no other link is coded for that pair.

Rules:
1. One activity = one action (deployment, governance instrument, staff training) by one actor concerning one tool or instrument. A named program is one activity; each named component is its own activity, linked to the program as a component of it. Repeated transactions for the same product by the same unit are one activity. A policy and the tools it approves are separate activities, linked by a "governs" relation.
2. One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page.
3. Add "has component" and "governed by".
4. Components stay separate activities; a governing policy is recorded as governing.
5. Each pair of passages gets a link.

## `core.activity_name`
<!-- item: core.activity_name sha256: 9a9a55c3d066738f911fdc5269670d927e3bee2da8236094fb9e2c68e1069401 -->

Column `activity_name`; item hash `9a9a55c3d066738f911fdc5269670d927e3bee2da8236094fb9e2c68e1069401`.

### Instruction

Short name. Use official name if one exists (e.g., "MyCity Chatbot", "Pair Platform"). Otherwise descriptive (e.g., "Internal Copilot pilot for document drafting").

## `core.observed_actor_name`
<!-- item: core.observed_actor_name sha256: d76dc7f2c930b753dd8511068222d56eb0e16384dcefe9064fc860a06e4ef25f -->

Column `observed_actor_name`; item hash `d76dc7f2c930b753dd8511068222d56eb0e16384dcefe9064fc860a06e4ef25f`.

### Rules

1. The extractor returns the verbatim actor name and organisational unit. jev Choice gives the relationship (this institution / unit of it / joint participant / other / unresolved) and the role (as v2.6).

## `core.tool_name`
<!-- item: core.tool_name sha256: e606956923481de92a2b4c59bbffa78de57b1fcc574c7b2f5e666a7c000969b1 -->

Column `tool_name`; item hash `e606956923481de92a2b4c59bbffa78de57b1fcc574c7b2f5e666a7c000969b1`.

### Instruction

Specific tool, model, or platform name (e.g., "Microsoft 365 Copilot", "ChatGPT", "Albert").

### Rules

1. `tool_name` = product or platform as written on the page; new `model_name` = model as written (e.g. "GPT-4o") or `unknown`. Several tools are `; `-separated in page order. `not_applicable` for activities without a tool.
2. The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.model_name`
<!-- item: core.model_name sha256: 7dd785b572b3e2c6fb2bec9e18322fd3947632922cf627ddc43a1b3cd53ed834 -->

Column `model_name`; item hash `7dd785b572b3e2c6fb2bec9e18322fd3947632922cf627ddc43a1b3cd53ed834`.

### Rules

1. `tool_name` = product or platform as written on the page; new `model_name` = model as written (e.g. "GPT-4o") or `unknown`. Several tools are `; `-separated in page order. `not_applicable` for activities without a tool.
2. The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.contracting_party`
<!-- item: core.contracting_party sha256: 73a561ad26b6e2535ca6b6f25409adb5d21dacc0ecd48722b16e6442ad34ff24 -->

Column `contracting_party`; item hash `73a561ad26b6e2535ca6b6f25409adb5d21dacc0ecd48722b16e6442ad34ff24`.

### Rules

1. Developer (from lookup or page, with its basis recorded) and contracting party (page-stated only).
2. Vendor holds what the source names, which in purchase records is the contracting party. The developer from the lookup goes into a new model-developer column, and the lookup stops filling vendor.
3. The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.deployment_scale_number`
<!-- item: core.deployment_scale_number sha256: 732f308184bb60eedf1e67468eb657857b20ce4dcfc76fb97cf16c19454b3686 -->

Column `deployment_scale_number`; item hash `732f308184bb60eedf1e67468eb657857b20ce4dcfc76fb97cf16c19454b3686`.

### Rules

1. The extractor returns the verbatim number span. jev Choice gives the unit: licences_or_seats / users / interactions / units_or_departments / none.
2. the quote step copies the scale number verbatim and the classifier picks the unit
3. The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.reported_outcomes`
<!-- item: core.reported_outcomes sha256: 841fe4e05bdbe08ab94621fc8d47e330ac1a68b3fb8af5875eddf8de74af9554 -->

Column `reported_outcomes`; item hash `841fe4e05bdbe08ab94621fc8d47e330ac1a68b3fb8af5875eddf8de74af9554`.

### Instruction

Documented performance claims. Only record if explicitly stated. Never infer.

### Rules

1. Deterministic step (no API), for rows coded before CX-01.3 only: map all "nothing found" spellings to `none_reported`. The mapping table is published with the code.

## `core.reported_incidents`
<!-- item: core.reported_incidents sha256: 5965e825e8086c714fe752e1004c91a1c7f839644191a4e2077a3693f744e429 -->

Column `reported_incidents`; item hash `5965e825e8086c714fe752e1004c91a1c7f839644191a4e2077a3693f744e429`.

### Instruction

Documented errors, failures, or controversies. Only record if explicitly stated.

### Rules

1. Deterministic step (no API), for rows coded before CX-01.3 only: map all "nothing found" spellings to `none_reported`. The mapping table is published with the code.

## `core.supporting_text`
<!-- item: core.supporting_text sha256: 07b6262cefe97510c6c521d3c7a46503b8fa75d67c9fb7e490fecbb39d24017c -->

Column `supporting_text`; item hash `07b6262cefe97510c6c521d3c7a46503b8fa75d67c9fb7e490fecbb39d24017c`.

### Rules

1. For every jev code on a page or activity, the extractor (C-001; the quote step) extracts the verbatim supporting text from the page. RC-D-002 row 15 replaces "after jev has coded": the quote step never sees the answer for the field it quotes, but may see that a gate is not `none`. The quote step runs for every activity, including items the applicability table skips; those copies are kept internally, and the item is published as "not asked". A01 and CX-61 get quotes relevant to the field. The scale number is copied verbatim by the quote step and the classifier picks the unit; the publication date is coded by the quote step under the R-042 check. X35 adds an entailment check per (code, quote) with a chosen-answer probability bar.
2. Supporting text is checked against the stored page text by fuzzy match; a quote below the match threshold counts as no supporting text.
3. Supporting text is published with the code it supports. The API carries the full text; the website shows it up to a display cap, with a marker and access to the full text.
4. Published supporting quotes stay verbatim, with no masking.
