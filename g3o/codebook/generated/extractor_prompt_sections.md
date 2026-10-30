<!-- GENERATED FILE - do not edit. Built from codebook/codebook.yaml by g3o.codebook.generators.extractor_prompt_sections. -->
<!-- codebook release: 2.7 | codebook sha256: d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764 -->

# Extractor prompt sections

Codebook release `2.7`, sha256 `d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764`. Intended target: T-022 / T-032 extractor prompt sections (path chosen there).

## `core.source_publication_date`
<!-- item: core.source_publication_date sha256: 9b0656c0c6510e1f0f97749c8bbdc50a5450b360a3fb9ebc5858dc67e56d65e3 -->

Column `source_publication_date`; item hash `9b0656c0c6510e1f0f97749c8bbdc50a5450b360a3fb9ebc5858dc67e56d65e3`.

### Rules

1. Take dates from HTML metadata / PDF properties / URL patterns deterministically; if absent, the extractor returns a date with its verbatim quote, validated by R-042.
2. One shared date of 1 November 2022, with "before" needing proof. Date origin is recorded as metadata, web address, quote from page text, archive upper bound, or unknown; the AI-text code changes.

## `core.source_snippet`
<!-- item: core.source_snippet sha256: d0ab6f896f41ba81d558777d6eb9cbba9746d19176c200862a8ff508ac20b284 -->

Column `source_snippet`; item hash `d0ab6f896f41ba81d558777d6eb9cbba9746d19176c200862a8ff508ac20b284`.

### Rules

1. Define `source_snippet` on v2.7 rows as the verbatim supporting text of the page verdict (truncated), with no paraphrase.
2. Snippets are verbatim in every pipeline, no translations are stored, and procurement's rule is amended.

## `core.activity_segment`
<!-- item: core.activity_segment sha256: 682fa27ba8f84d627704cf7f1cfdae2dec8dcf1361701f04355bd3c12d3e24a6 -->

Column `activity_relation_within_page`; item hash `682fa27ba8f84d627704cf7f1cfdae2dec8dcf1361701f04355bd3c12d3e24a6`.

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
<!-- item: core.activity_name sha256: 728ade2be54620595dfe7ad68dba12705d4bead42e9315aef9886d816caef531 -->

Column `activity_name`; item hash `728ade2be54620595dfe7ad68dba12705d4bead42e9315aef9886d816caef531`.

### Instruction

Short name. Use official name if one exists (e.g., "MyCity Chatbot", "Pair Platform"). Otherwise descriptive (e.g., "Internal Copilot pilot for document drafting").

## `core.observed_actor_name`
<!-- item: core.observed_actor_name sha256: b32deb08bbf848ebd7916fd76b2317cdfffe2ee0dc14123aaafadce8984eff37 -->

Column `observed_actor_name`; item hash `b32deb08bbf848ebd7916fd76b2317cdfffe2ee0dc14123aaafadce8984eff37`.

### Rules

1. The extractor returns the verbatim actor name and organisational unit. jev Choice gives the relationship (this institution / unit of it / joint participant / other / unresolved) and the role (as v2.6).

## `core.tool_name`
<!-- item: core.tool_name sha256: 4c960a1917007ed502ea252e91c5370eeddfa71ee468390b7f7ffe488a9e6beb -->

Column `tool_name`; item hash `4c960a1917007ed502ea252e91c5370eeddfa71ee468390b7f7ffe488a9e6beb`.

### Instruction

Specific tool, model, or platform name (e.g., "Microsoft 365 Copilot", "ChatGPT", "Albert").

### Rules

1. `tool_name` = product or platform as written on the page; new `model_name` = model as written (e.g. "GPT-4o") or `unknown`. Several tools are `; `-separated in page order. `not_applicable` for activities without a tool.
2. The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.model_name`
<!-- item: core.model_name sha256: 34a1685ff0f6304c3ae75cd690ac994f6a3f7e0cf0bc08ddcfec3e2a6ae8de8b -->

Column `model_name`; item hash `34a1685ff0f6304c3ae75cd690ac994f6a3f7e0cf0bc08ddcfec3e2a6ae8de8b`.

### Rules

1. `tool_name` = product or platform as written on the page; new `model_name` = model as written (e.g. "GPT-4o") or `unknown`. Several tools are `; `-separated in page order. `not_applicable` for activities without a tool.
2. The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.contracting_party`
<!-- item: core.contracting_party sha256: f27653658f96d43998f2df1cc678c307b15c520c5decb3777d2d20f12f851c96 -->

Column `contracting_party`; item hash `f27653658f96d43998f2df1cc678c307b15c520c5decb3777d2d20f12f851c96`.

### Rules

1. Developer (from lookup or page, with its basis recorded) and contracting party (page-stated only).
2. Vendor holds what the source names, which in purchase records is the contracting party. The developer from the lookup goes into a new model-developer column, and the lookup stops filling vendor.
3. The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.deployment_scale_number`
<!-- item: core.deployment_scale_number sha256: f475424d5b5a9a547768e9d58e2d9ac0cb9927308630ccc156fe4d361be0ac19 -->

Column `deployment_scale_number`; item hash `f475424d5b5a9a547768e9d58e2d9ac0cb9927308630ccc156fe4d361be0ac19`.

### Rules

1. The extractor returns the verbatim number span. jev Choice gives the unit: licences_or_seats / users / interactions / units_or_departments / none.
2. the quote step copies the scale number verbatim and the classifier picks the unit
3. The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.reported_outcomes`
<!-- item: core.reported_outcomes sha256: 461640be1d75ba79ac2297ad85a4a36bc119cfd9d8a1bb73bb9a14248192181d -->

Column `reported_outcomes`; item hash `461640be1d75ba79ac2297ad85a4a36bc119cfd9d8a1bb73bb9a14248192181d`.

### Instruction

Documented performance claims. Only record if explicitly stated. Never infer.

### Rules

1. Deterministic step (no API), for rows coded before CX-01.3 only: map all "nothing found" spellings to `none_reported`. The mapping table is published with the code.
2. jev Choice per activity: page reports realised outcomes / only expected or projected outcomes / usage figures only / none. Unless none, the extractor returns verbatim spans (no length limit in storage, display cap per R-043). CX-61 then runs on the spans.

## `core.reported_incidents`
<!-- item: core.reported_incidents sha256: 66b35b76fde638868351219a3e179a72358ccc6a176b581650fed4b473b10ca5 -->

Column `reported_incidents`; item hash `66b35b76fde638868351219a3e179a72358ccc6a176b581650fed4b473b10ca5`.

### Instruction

Documented errors, failures, or controversies. Only record if explicitly stated.

### Rules

1. Deterministic step (no API), for rows coded before CX-01.3 only: map all "nothing found" spellings to `none_reported`. The mapping table is published with the code.
2. jev Choice: page reports a malfunction or error / data or privacy breach / public criticism or complaint / suspension or withdrawal / none. Unless none, the extractor returns verbatim spans.

## `core.supporting_text`
<!-- item: core.supporting_text sha256: ab1a6071437a92a0293225daff189f3b12f0e7849e1a69a4b5f1ef6891f4569e -->

Column `supporting_text`; item hash `ab1a6071437a92a0293225daff189f3b12f0e7849e1a69a4b5f1ef6891f4569e`.

### Rules

1. For every jev code on a page or activity, the extractor (C-001; the quote step) extracts the verbatim supporting text from the page. RC-D-002 row 15 replaces "after jev has coded": the quote step never sees the answer for the field it quotes, but may see that a gate is not `none`. The quote step runs for every activity, including items the applicability table skips; those copies are kept internally, and the item is published as "not asked". A01 and CX-61 get quotes relevant to the field. The scale number is copied verbatim by the quote step and the classifier picks the unit; the publication date is coded by the quote step under the R-042 check. X35 adds an entailment check per (code, quote) with a chosen-answer probability bar.
2. Supporting text is checked against the stored page text by fuzzy match; a quote below the match threshold counts as no supporting text.
3. Supporting text is published with the code it supports. The API carries the full text; the website shows it up to a display cap, with a marker and access to the full text.
4. Published supporting quotes stay verbatim, with no masking.
