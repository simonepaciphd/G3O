<!-- GENERATED FILE - do not edit. Built from codebook/codebook.yaml by g3o.codebook.generators.extractor_prompt_sections. -->
<!-- codebook release: 2.7 | codebook sha256: 64a8a2d808a3eb6c4583d7c65d1a9068e557785fdb17ed11e7ffd99e4ebe7dc5 -->

# Extractor prompt sections

Codebook release `2.7`, sha256 `64a8a2d808a3eb6c4583d7c65d1a9068e557785fdb17ed11e7ffd99e4ebe7dc5`. Intended target: T-022 / T-032 extractor prompt sections (path chosen there).

## `core.source_publication_date`
<!-- item: core.source_publication_date sha256: 44eac9838bdb4ff1e4552e1ce3e2fe7f65e4d874149b5b3d1b0cbaaa49589f06 -->

Column `source_publication_date`; item hash `44eac9838bdb4ff1e4552e1ce3e2fe7f65e4d874149b5b3d1b0cbaaa49589f06`.

### Rules

1. Take dates from HTML metadata, PDF properties or URL patterns deterministically; if none is found, the extractor returns a date with its verbatim quote, which is checked against the stored page text like any other quote.
2. One shared date of 1 November 2022, with "before" needing proof. Date origin is recorded as metadata, web address, quote from page text, archive upper bound, or unknown.

## `core.source_snippet`
<!-- item: core.source_snippet sha256: cd81837b81c62d13bd865eb4173c1561fd8eadb2cdbd1f81acca9a9dc297a7a6 -->

Column `source_snippet`; item hash `cd81837b81c62d13bd865eb4173c1561fd8eadb2cdbd1f81acca9a9dc297a7a6`.

### Rules

1. Define `source_snippet` on v2.7 rows as the verbatim supporting text of the page verdict (truncated), with no paraphrase.
2. Snippets are verbatim in every pipeline, no translations are stored, and procurement's rule is amended.

## `core.activity_segment`
<!-- item: core.activity_segment sha256: 1b7750af042738acd295133cb4b1a14e0cfb189619952074db0f3607cfef5f17 -->

Column `activity_relation_within_page`; item hash `1b7750af042738acd295133cb4b1a14e0cfb189619952074db0f3607cfef5f17`.

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
<!-- item: core.activity_name sha256: 69808679d441b3cc10cb66a680689e5e2cd4e9280cdd8c6d867494c3ac71e32f -->

Column `activity_name`; item hash `69808679d441b3cc10cb66a680689e5e2cd4e9280cdd8c6d867494c3ac71e32f`.

### Instruction

Short name. Use official name if one exists (e.g., "MyCity Chatbot", "Pair Platform"). Otherwise descriptive (e.g., "Internal Copilot pilot for document drafting").

## `core.observed_actor_name`
<!-- item: core.observed_actor_name sha256: e75b120e8bce7ce52b35f2469175efedcbcb30fd659a8d187ef206c852aebb05 -->

Column `observed_actor_name`; item hash `e75b120e8bce7ce52b35f2469175efedcbcb30fd659a8d187ef206c852aebb05`.

### Rules

1. The extractor returns the verbatim actor name and organisational unit.

## `core.tool_name`
<!-- item: core.tool_name sha256: 1e879decc441d08c1b631a1f9440e6ef97606a9d056326e738407db500984350 -->

Column `tool_name`; item hash `1e879decc441d08c1b631a1f9440e6ef97606a9d056326e738407db500984350`.

### Instruction

Specific tool, model, or platform name (e.g., "Microsoft 365 Copilot", "ChatGPT", "Albert").

### Rules

1. `tool_name` = product or platform as written on the page; new `model_name` = model as written (e.g. "GPT-4o") or `unknown`. Several tools are `; `-separated in page order. `not_applicable` for activities without a tool.
2. The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.model_name`
<!-- item: core.model_name sha256: 920c2ca82290833327903b8555b400f782cfb9d1af1b42c99b0700ba966b947f -->

Column `model_name`; item hash `920c2ca82290833327903b8555b400f782cfb9d1af1b42c99b0700ba966b947f`.

### Rules

1. `tool_name` = product or platform as written on the page; new `model_name` = model as written (e.g. "GPT-4o") or `unknown`. Several tools are `; `-separated in page order. `not_applicable` for activities without a tool.
2. The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.contracting_party`
<!-- item: core.contracting_party sha256: 08c049166dc9dff75f2da9a369b32e7cb664c615d17f0f09a58e5c75adf1c3cd -->

Column `contracting_party`; item hash `08c049166dc9dff75f2da9a369b32e7cb664c615d17f0f09a58e5c75adf1c3cd`.

### Rules

1. Developer (stated on the page, with its basis recorded) and contracting party (page-stated only).
2. Vendor holds what the source names, which in purchase records is the contracting party. The developer from the lookup goes into a new model-developer column, and the lookup stops filling vendor.
3. The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.developer`
<!-- item: core.developer sha256: eaa4b9278a86d5d25d3b8a6de4a4cfdfd66f8b06b5d39a07ebb35e0284bdc6bf -->

Column `developer`; item hash `eaa4b9278a86d5d25d3b8a6de4a4cfdfd66f8b06b5d39a07ebb35e0284bdc6bf`.

### Rules

1. Developer (stated on the page, with its basis recorded) and contracting party (page-stated only).
2. vendor = the organisation the page names as supplying the AI product or service, verbatim.
3. The quote step runs for every activity; skipped items are kept internally and published as "not asked".
4. A developer stated on the page comes from the quote step, with its supporting quote; `developer_basis` = stated.

## `core.deployment_scale_number`
<!-- item: core.deployment_scale_number sha256: c3740fb709eb05a98b259f988dc7611e778dfd87abd332d7de982d11ad8b23ae -->

Column `deployment_scale_number`; item hash `c3740fb709eb05a98b259f988dc7611e778dfd87abd332d7de982d11ad8b23ae`.

### Rules

1. The extractor returns the verbatim number span. jev Choice gives the unit: licences_or_seats / users / interactions / units_or_departments / none.
2. the quote step copies the scale number verbatim and the classifier picks the unit
3. The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.reported_outcomes`
<!-- item: core.reported_outcomes sha256: b8966f48a7aaa47f305aa79f349549b07b42f1f878241510f6e3cdc80550e6b4 -->

Column `reported_outcomes`; item hash `b8966f48a7aaa47f305aa79f349549b07b42f1f878241510f6e3cdc80550e6b4`.

### Instruction

Documented performance claims. Only record if explicitly stated. Never infer.

## `core.reported_incidents`
<!-- item: core.reported_incidents sha256: beed4c12c06a509a8abebfdbfae91d3457c4a9524e3308533f371dc4c0d073d2 -->

Column `reported_incidents`; item hash `beed4c12c06a509a8abebfdbfae91d3457c4a9524e3308533f371dc4c0d073d2`.

### Instruction

Documented errors, failures, or controversies. Only record if explicitly stated.

## `core.supporting_text`
<!-- item: core.supporting_text sha256: ed7c6f3e92f25fcdd9f5220099088627f3b129dc5cefbe68e94ab2020fdcd517 -->

Column `supporting_text`; item hash `ed7c6f3e92f25fcdd9f5220099088627f3b129dc5cefbe68e94ab2020fdcd517`.

### Rules

1. For every classifier code on a page or activity, the quote step copies the verbatim supporting text from the page. It sees the chosen answer for the field it quotes and copies the text that supports it; it may also see that a gate is not `none`. Each supporting text (a quote, a link passage or a field's supporting text) is at most 200 characters; a longer one is kept whole and flagged. The quote step runs for every activity, including items the applicability table skips; those copies are kept internally, and the item is published as "not asked". The GenAI mechanism basis and the outcome and incident kinds get quotes relevant to the field. The quote step copies the scale number verbatim and the classifier picks the unit; the quote step codes the publication date, checked against the stored text. A second check asks whether each quote states the coded value (`core.support_entailment`).
2. Supporting text is checked against the stored page text by fuzzy match; a quote below the match threshold counts as no supporting text.
3. Supporting text is published with the code it supports. The API carries the full text; the website shows it up to 200 characters, with a marker and access to the full text.
4. Published supporting quotes stay verbatim, with no masking.
