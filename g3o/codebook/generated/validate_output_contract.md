<!-- GENERATED FILE - do not edit. Built from codebook/codebook.yaml by g3o.codebook.generators.validate_output_contract. -->
<!-- codebook release: 2.7 | codebook sha256: dd3cc7e9c7e7dd9c9031f242001350ae730d418f9a8915affc2a08a85675c08b -->

# G3O output contract (validate, Stage 6), generated from the codebook

Codebook release `2.7`, sha256 `dd3cc7e9c7e7dd9c9031f242001350ae730d418f9a8915affc2a08a85675c08b`. 14 items.

## `core.has_genai_activity`
<!-- item: core.has_genai_activity sha256: 5d8e6ba766281d035d01c6b90cfd05d0c33af81c4023c9ffd3e565649b8b58b7 -->

| Field | Value |
|---|---|
| item hash | `5d8e6ba766281d035d01c6b90cfd05d0c33af81c4023c9ffd3e565649b8b58b7` |
| family | `verdict` |
| name | `has_genai_activity` |
| level | `institution` |
| pipelines | `stage6` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `single` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "has_genai_activity", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[28]"}` |

### Rules

1. `items/core.has_genai_activity/rules/0`

Institution-level consolidation (Stage 6) applies the v2.6 consolidation rules as jev questions or deterministic rules: explicit relations before merging observations; distinct/unresolved relations never merge; institution-level `no` only with complete supplied context and no unresolved signal. An institution whose reviewed pages are all negative at confidence ≥ 0.8 gets `no` directly; the complete-context rule blocks `no` only when an unresolved signal remains (a low-confidence negative downgraded under R-081 counts as one). Stage 6 becomes the X29 truth table, with these ruled components: `background_only` pages may sit in the institution `no` set; any downgraded page counts as unresolved, except a `confirms_activity` page counted under the page-verdict roll-up; the bar is the chosen answer's probability ≥ 0.8; `yes` can come from any pipeline, `no` from web pages only, and AI-text results never count; any supported AI purchase record can give `yes`, while the evidence tier still shows it as commitment; `not_assessable` is set mechanically only and does not block `no`. Also: X30 with the shared relation list incl. `governs`; X31 pooled evidence, split when too long; A06 per r2#21; A07 with 9 counts per pipeline; X23 replaced by r2#27; unit-credit flag. `unresolved` stays a coding value and is reported as `unknown` in published summaries; unresolved relations still never merge. Inside the institution-level rule both `unresolved` and `not_assessable` keep their current roles, and `not_assessable` stays out of the institution-rate base.

2. `items/core.has_genai_activity/rules/1`

Codebook table: `yes` if >= 1 supported `confirms_activity` page with a supported activity; `no` if every attempted page (incl. failed fetches and unfollowed links) ends in {no_genai, confirms_absence, event_only, other_body} at confidence >= 0.8 and no page is ambiguous, background_only or failed; otherwise `unclear`. Variant for PI: allow background_only in `no`.

3. `items/core.has_genai_activity/rules/2`

Page-verdict roll-up: a reviewed, unfailed web page whose final verdict is `confirms_activity`, whose verdict support status is `downgraded_quote_not_stating_value` or `downgraded_no_quote`, whose chosen probability passes the classifier verdict bar, and which has at least one supported activity observation on the same page, counts as a supported `confirms_activity` page. `downgraded_low_confidence` is never rescued and a page with no supported activity is never rescued. The verdict is never rewritten and keeps its support status; the source row's `confidence` stays `low`.

## `core.verdict_rule`
<!-- item: core.verdict_rule sha256: aec5d5efdd3c58217aa68520910d52f04083fce2c5c9045aed07feca1a551006 -->

| Field | Value |
|---|---|
| item hash | `aec5d5efdd3c58217aa68520910d52f04083fce2c5c9045aed07feca1a551006` |
| family | `provenance` |
| name | `verdict_rule` |
| level | `institution` |
| pipelines | `stage6` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `single` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.verdict_rule/rules/0`

v2.5 `none` institutions show `no` labelled as produced by the v2.5 rule (`verdict_rule`, r2#45).

## `core.evidence_tier`
<!-- item: core.evidence_tier sha256: c7358fa49e107f3adbeefd0a6e5944d75e8f6ec14ae5dcd8c121818d3631d71d -->

| Field | Value |
|---|---|
| item hash | `c7358fa49e107f3adbeefd0a6e5944d75e8f6ec14ae5dcd8c121818d3631d71d` |
| family | `verdict` |
| name | `evidence_tier` |
| level | `institution` |
| pipelines | `stage6` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `single` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.evidence_tier/rules/0`

Highest of: documented_use (any pilot, production or discontinued deployment) > documented_commitment (announced, or procured if C09 alt-1) > governance_or_training_only > proposal_only > none_found / unclear. Published beside has_genai_activity.

2. `items/core.evidence_tier/rules/1`

Use = a deployment or program at pilot, production or discontinued; commitment = announced, or a tender, contract or payment; governance or training only = those action types only; proposal only = stage 'proposed' or action type 'proposal'. You word the rule, and tests are added.

## `core.review_depth`
<!-- item: core.review_depth sha256: b1e3d31d4664ec90346676843db71e07b4c4bcec4e2749a3167c2519aa42424b -->

| Field | Value |
|---|---|
| item hash | `b1e3d31d4664ec90346676843db71e07b4c4bcec4e2749a3167c2519aa42424b` |
| family | `quality` |
| name | `review_depth` |
| level | `institution` |
| pipelines | `stage6` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `list` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.review_depth/rules/0`

n_pages_reviewed, n_pages_by_verdict (8 counts), n_pages_failed, n_followed_links, all computed at Stage 6.

## `core.activity_relation_cross_page`
<!-- item: core.activity_relation_cross_page sha256: f065c023f39a30eb1e9e1e89d0eb8f96ab60ebfa902a5de7c69abc0f1c6d7691 -->

| Field | Value |
|---|---|
| item hash | `f065c023f39a30eb1e9e1e89d0eb8f96ab60ebfa902a5de7c69abc0f1c6d7691` |
| family | `activity_identity` |
| name | `activity_relation` |
| level | `activity` |
| pipelines | `stage6` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `stage6` |
| round | `1` |
| answer_type | `single` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.activity_relation_cross_page]; ruling institution-01, all-04", "order": ["unresolved", "distinct_action", "governs", "governed_by", "component_of_program", "has_component", "shared_participation", "same_activity", "unknown"]}` |
| translation_v25 | `new` |

### Instruction

How is the activity in the first record related to the activity in the second record?

### Entailment label

relation to the other activity

### Values

#### `same_activity`

The two activity records describe the same activity: the same action by the same actor on the same tool or instrument. Only records joined by this link are merged.

Entailment label: the same activity

#### `component_of_program`

The first record's activity is a named component of the program in the second. Both stay separate activities, linked.

Entailment label: a named component of the other activity's programme

#### `has_component`

The first record describes a program, and the second record's activity is one of its named components. Both stay separate activities, linked.

Entailment label: a programme that has the other activity as a named component

#### `shared_participation`

The two records describe one joint action in which several bodies take part. They are one activity: the two records are merged. The link needs at least two bodies, each named as taking part, with a quote.

Entailment label: one joint action shared with the other activity

#### `governs`

The first record's activity is a policy or other governance instrument that sets rules for the activity in the second. When a pair fits both this link and a component link, this link is used.

Entailment label: a rule that governs the other activity

#### `governed_by`

The second record's activity is a policy or other governance instrument that sets rules for the activity in the first. When a pair fits both this link and a component link, this link is used.

Entailment label: governed by the other activity's rule

#### `distinct_action`

The two records describe different activities, and none of the other links applies. The value is stored with a rule note.

Entailment label: a different activity

#### `unresolved`

The sources do not settle whether the two records describe the same activity. They are never merged.

Entailment label: not settled

### Rules

1. `items/core.activity_relation_cross_page/rules/0`

Every pair of activity observations is asked, including identical names; candidate pairs pre-filtered deterministically only to skip obviously distinct pairs (different activity_type and tool), never to merge.

2. `shared_rules/core.rule.activity_unit/0` (shared rule `core.rule.activity_unit`)

One activity = one action (deployment, governance instrument, staff training) by one actor concerning one tool or instrument. A named program is one activity; each named component is its own activity, linked to the program as a component of it. Repeated transactions for the same product by the same unit are one activity. A policy and the tools it approves are separate activities, linked by a "governs" relation.

3. `items/core.activity_relation_cross_page/rules/2`

One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page.

4. `items/core.activity_relation_cross_page/rules/3`

Add "has component" and "governed by".

5. `items/core.activity_relation_cross_page/rules/4`

Components stay separate activities; a governing policy is recorded as governing.

6. `items/core.activity_relation_cross_page/rules/5`

Store the distinct value with a rule note.

### long_page_rule text

`items/core.activity_relation_cross_page/long_page_rule/split_rule`

Split the pool so every part sees both activities.

## `core.pooled_activity_fields`
<!-- item: core.pooled_activity_fields sha256: e7bb3504420de2437c4fb2433390b098488993337945d5c1d57e478ee060655b -->

| Field | Value |
|---|---|
| item hash | `e7bb3504420de2437c4fb2433390b098488993337945d5c1d57e478ee060655b` |
| family | `activity_identity` |
| name | `pooled_activity_fields` |
| level | `activity` |
| pipelines | `stage6` |
| linkage | `pipeline` |
| coder | `derived` |
| pass | `stage6` |
| round | `2` |
| answer_type | `single` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `{"rule": "none", "pooled_fields": "each field uses its own item's long_page_rule", "source": "r2#6", "ruling": "RC-D-005 10 a"}` |
| translation_v25 | `new` |

### Instruction

The text below is a set of quotes about one activity, gathered from several sources, each with its source type and date. Answer each question about the activity from these quotes only.

### Rules

1. `items/core.pooled_activity_fields/rules/0`

For a merged activity, jev answers each Group D question once over the union of the activity's supported quotes from all its sources (state = quotes with source type and date).

2. `items/core.pooled_activity_fields/rules/1`

Pooled quotes are split into parts, and the existing combining rules apply (yes if any part says yes; ordered lists take the first value found). The page-splitting rule is extended.

## `core.confidence`
<!-- item: core.confidence sha256: 02d8f7878e803f3b94926601c37b2b7f8772413b59d2994bfc562699a40c8329 -->

| Field | Value |
|---|---|
| item hash | `02d8f7878e803f3b94926601c37b2b7f8772413b59d2994bfc562699a40c8329` |
| family | `quality` |
| name | `confidence` |
| level | `source`, `activity` |
| pipelines | `web_extract`, `stage6` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `single` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "confidence", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[29]"}` |

### Rules

1. `items/core.confidence/rules/0`

Each source's confidence uses only that source's credibility and quote support. At consolidation, an activity is 'high' if one source is high or two medium sources that are not copies of each other agree; otherwise it takes the highest source value.

2. `items/core.confidence/rules/1`

When all applicable evidence checks completed and none failed, source confidence = `source_credibility` (high/medium/low). Any `downgraded_no_quote`, `downgraded_quote_not_stating_value` or `downgraded_low_confidence` on any associated original code, including a `no` or negative value downgraded below the 0.8 bar, makes it `low`. `not_required` / `set_by_rule` neutral. Pending/unperformed checks leave it unfinished (not scored); unavailable credibility stays unknown unless a failed check sets low. Original failures survive the final-value downgrade.

3. `items/core.confidence/rules/2`

At consolidation, when an activity's confidence is aggregated from its sources, a source whose confidence is `unknown` counts as `low`.

## `core.n_sources`
<!-- item: core.n_sources sha256: 18270c4c8fcc6f67a1f5e3adb9005f1f429a9bb27bd29bb8d3fe7b39dc9905f4 -->

| Field | Value |
|---|---|
| item hash | `18270c4c8fcc6f67a1f5e3adb9005f1f429a9bb27bd29bb8d3fe7b39dc9905f4` |
| family | `quality` |
| name | `n_sources` |
| level | `activity` |
| pipelines | `stage6` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `number` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.n_sources/rules/0`

As v1.3.

## `core.institution_summary`
<!-- item: core.institution_summary sha256: 47f16063b2706efab4cfeb7a11a07159a793d884031525de33b4f69f93191105 -->

| Field | Value |
|---|---|
| item hash | `47f16063b2706efab4cfeb7a11a07159a793d884031525de33b4f69f93191105` |
| family | `verdict` |
| name | `institution_summary` |
| level | `institution` |
| pipelines | `stage6` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `text` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "institution_summary", "map": "identity", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[30]"}` |

### Rules

1. `items/core.institution_summary/rules/0`

Generate the summary from codes: verdict, number of activities, their types/stages, page counts reviewed and failed.

## `core.cx_display_rollup`
<!-- item: core.cx_display_rollup sha256: 03fd62398d893f650e46c90537028a7b66d4e14c224c3b3500374515b61e69c8 -->

| Field | Value |
|---|---|
| item hash | `03fd62398d893f650e46c90537028a7b66d4e14c224c3b3500374515b61e69c8` |
| family | `disclosure` |
| name | `cx_display_rollup` |
| level | `activity` |
| pipelines | `stage6` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `list` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.cx_display_rollup/rules/0`

Stage 6 computes a display value per activity (any supported positive; first in table order for ordered fields), labelled 'display roll-up, not an index input'.

## `core.codebook_release`
<!-- item: core.codebook_release sha256: 486c259a39f209960cf2f7e620525a4fa6afd2c55bbb49321a2aece61f866fd9 -->

| Field | Value |
|---|---|
| item hash | `486c259a39f209960cf2f7e620525a4fa6afd2c55bbb49321a2aece61f866fd9` |
| family | `provenance` |
| name | `codebook_release` |
| level | `row` |
| pipelines | `web_extract`, `stage6`, `procurement`, `ai_text` |
| linkage | `deterministic` |
| coder | `mechanical` |
| pass | `none` |
| round | `none` |
| answer_type | `text` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "contract_version", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[31]"}` |

### Rules

1. `items/core.codebook_release/rules/0`

Every published row carries the contract version that produced it. That is one version label, the codebook release, replacing `contract_version`, plus the setup pointer and `evidence_channel`; the extract and validate contract labels are recorded only in the setup record. C-007 applies to the release. v2.5 rows keep their contract version.

## `core.setup_pointer`
<!-- item: core.setup_pointer sha256: 58d0baf502066294c9ce6151b5d7d499789520452ae4b970081da64aa551d979 -->

| Field | Value |
|---|---|
| item hash | `58d0baf502066294c9ce6151b5d7d499789520452ae4b970081da64aa551d979` |
| family | `provenance` |
| name | `setup_pointer` |
| level | `row` |
| pipelines | `web_extract`, `stage6`, `procurement`, `ai_text` |
| linkage | `deterministic` |
| coder | `mechanical` |
| pass | `none` |
| round | `none` |
| answer_type | `text` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.setup_pointer/rules/0`

A manifest (contract versions, `JEV_QUESTION_SET_VERSION`, jev model, extractor model id + prompt SHA-256, chunker + estimator version, matcher + threshold, confidence threshold, codebook item hashes) keyed by `instrument_id` on every row.

2. `items/core.setup_pointer/rules/1`

Every jev answer is stored with its probability distribution, confidence, response model id and request id. Every automated coder (classifier, quote step, detector, mechanical rules) stores coder type, model, version and request id; the per-run version record holds the codebook version, and per-code coder details are internal and linked to it; the row carries the codebook version + setup pointer; the classifier record keeps the chosen-answer probability.

## `core.evidence_channel`
<!-- item: core.evidence_channel sha256: d6a78890e3f781cc67a15785c8b81773ad12ebcc5e82c5bf0a94029463de82ff -->

| Field | Value |
|---|---|
| item hash | `d6a78890e3f781cc67a15785c8b81773ad12ebcc5e82c5bf0a94029463de82ff` |
| family | `provenance` |
| name | `evidence_channel` |
| level | `row` |
| pipelines | `web_extract`, `stage6`, `procurement`, `ai_text` |
| linkage | `deterministic` |
| coder | `mechanical` |
| pass | `none` |
| round | `none` |
| answer_type | `single` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.evidence_channel/rules/0`

Channel enum (web_extract, procurement, ai_text)

## `core.coder_record`
<!-- item: core.coder_record sha256: 12443b1c740af48ea758a3ce0f785c07cd1ac8d35444e29cc63cac4122269a73 -->

| Field | Value |
|---|---|
| item hash | `12443b1c740af48ea758a3ce0f785c07cd1ac8d35444e29cc63cac4122269a73` |
| family | `provenance` |
| name | `coder_record` |
| level | `row` |
| pipelines | `web_extract`, `stage6`, `procurement`, `ai_text` |
| linkage | `deterministic` |
| coder | `mechanical` |
| pass | `none` |
| round | `none` |
| answer_type | `text` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `internal` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.coder_record/rules/0`

Every jev answer is stored with its probability distribution, confidence, response model id and request id. Every automated coder (classifier, quote step, detector, mechanical rules) stores coder type, model, version and request id; the per-run version record holds the codebook version, and per-code coder details are internal and linked to it; the row carries the codebook version + setup pointer; the classifier record keeps the chosen-answer probability.

2. `items/core.coder_record/rules/1`

`coder_type`, `coder_model`, `coder_version`, `request_id` common across channels
