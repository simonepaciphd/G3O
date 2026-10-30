<!-- GENERATED FILE - do not edit. Built from codebook/codebook.yaml by g3o.codebook.generators.extract_output_contract. -->
<!-- codebook release: 2.7 | codebook sha256: d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764 -->

# G3O output contract (extract), generated from the codebook

Codebook release `2.7`, sha256 `d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764`. 99 items.

## `core.page_verdict`
<!-- item: core.page_verdict sha256: fd63c805b56f323f6b330288afd8d12429e0b7e2e53b5397a2feae37a2e22f75 -->

| Field | Value |
|---|---|
| item hash | `fd63c805b56f323f6b330288afd8d12429e0b7e2e53b5397a2feae37a2e22f75` |
| family | `verdict` |
| name | `page_verdict` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `1` |
| round | `1` |
| answer_type | `single` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `tag_only` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_assessable (mechanical)` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `{"rule": "priority_order", "order": "S3 a"}` |
| translation_v25 | `{"column": "genai_evidence", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[0]"}` |

### Instruction

Code this PAGE for the named institution only, using only what the page says. Does it document a generative-AI activity at this institution? If several values fit, take the first in this order.

### Values

#### `confirms_activity`

The page documents a specific generative-AI activity AT THIS institution: its own GenAI tool, pilot, policy or guidance on GenAI, procurement, deployment, or institution-directed staff GenAI training. The text must be explicitly generative AI (LLMs, ChatGPT, Copilot, Gemini, AI chatbots, AI-generated content or equivalents) and tied to this institution, not only to a national programme or another body. The activity must be carried out or adopted by the named institution itself. Exclude activity by a parent, higher-level or neighbouring body (e.g. a district, county, regency, region, consortium or city department when the named institution is a village, ward or sub-unit), by a similarly named organisation or company, and pages by vendors that only use the place name. Generic 'AI', 'artificial intelligence', 'smart' systems, automation, analytics, prediction, transcription, translation, image or video recognition, or traditional machine-learning tools do not count unless the page says the tool generates text, images, audio, code or other content, or names a generative product or model (e.g. ChatGPT, Copilot, Gemini, Claude, an LLM, an AI chatbot or AI assistant).

#### `ambiguous_genai`

The page mentions AI at this institution, but it cannot be settled whether it is generative AI (e.g. a generic 'AI strategy', 'AI tools', analytics, traditional machine learning).

#### `ambiguous_attribution`

The page mentions generative AI, but it cannot be settled whether THIS institution is involved (e.g. a country-wide or regional GenAI initiative without confirmation that this institution takes part, or a page about a similarly named body).

#### `other_body`

The page documents a generative-AI activity, but it clearly belongs to a different body, not the named institution: a parent, higher-level or neighbouring body (e.g. a district, county, regency, region, consortium or city department when the named institution is a village, ward or sub-unit), a similarly named organisation or company, or a vendor or marketing page that only uses the place name.

#### `event_only`

The only GenAI content is a public-facing event, workshop, seminar, showcase or educational programme, with no documented adoption, procurement, deployment or governance by the institution itself (WS10 D1: not a qualifying activity).

#### `background_only`

The page gives only general context (national AI strategy, vendor overview, news about GenAI in general) and documents no activity at this institution.

#### `confirms_absence`

v2.5 `confirms_absence` (page states absence; distinct from `no_genai`, no relevant content)

#### `no_genai`

The page contains no generative-AI content relevant to this institution.

#### `not_assessable`

`not_assessable`, set mechanically when a page was not reviewed, never a classifier answer, not blocking institution `no`, and left out of the base for institution-level rates

### Rules

1. `items/core.page_verdict/rules/0`

The vocabulary has 9 values: the 8 below plus `not_assessable`, set mechanically when a page was not reviewed, never a classifier answer, not blocking institution `no`, and left out of the base for institution-level rates; in published summaries it is reported as `unknown` and stays a coding value; `page_review_state` keeps only pipeline failures; v2.5 rows stay unconverted and are mapped by the translation table.

2. `shared_rules/core.rule.genai_boundary/0` (shared rule `core.rule.genai_boundary`)

Generative-AI wording: the re-pilot 2 wording governs (SRC-7 L34-45), including that a named "AI chatbot or AI assistant" counts as a generative product; `system_prompt.md` L15 rule ("chatbot" alone is not evidence) is amended to match. A named "AI chatbot" or "AI assistant" counts as generative and overrides the rule-based-chatbot exclusion (contract L12) for that naming.

3. `shared_rules/core.rule.genai_boundary/1` (shared rule `core.rule.genai_boundary`)

S1 a: translation counts as generative AI only when the page ties it to a named generative product or says a language model produces it.

4. `shared_rules/core.rule.ws10_event/0` (shared rule `core.rule.ws10_event`)

WS10 D1 action boundary: a public-facing GenAI event or educational programme is not a qualifying activity; an event page can support a separate record only when it documents the institution's own adoption, procurement, deployment or governance.

5. `shared_rules/core.rule.attribution_grain/0` (shared rule `core.rule.attribution_grain`)

An activity carried out by an organisational unit of the named institution (department, office, service) counts for the named institution. An activity of its parent, a sibling, or a separate court, board or authority does not, unless the page says the named institution takes part.

6. `shared_rules/core.rule.attribution_grain/1` (shared rule `core.rule.attribution_grain`)

A joint activity counts when the page names this institution as a participant.

### long_page_rule text

`items/core.page_verdict/long_page_rule/tiers`

All supported verdicts in the signed order first, then failed verdicts in the same order.

## `core.disclosure_form`
<!-- item: core.disclosure_form sha256: 09cf9815915325c5bd2f8360c7df2821d73c779f829111a5683ebd2b56dcaac9 -->

| Field | Value |
|---|---|
| item hash | `09cf9815915325c5bd2f8360c7df2821d73c779f829111a5683ebd2b56dcaac9` |
| family | `disclosure` |
| name | `disclosure_form` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `1` |
| round | `2` |
| answer_type | `single` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-10..CX-18` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `first_section` |
| translation_v25 | `new` |

### Instruction

What kind of document is this page?

### Values

#### `register_cross_institution`

The page is, or is one entry in, a structured list of AI or algorithmic systems kept by a government body, with several entries in a common format (inventory, register, catalogue, algorithmic transparency record in a standard template), **and the list covers more than one institution** (a national or sectoral register, a standard-template record series across agencies).

#### `register_single_institution`

As CX-10, but the list covers **one institution only** (e.g. a city's own table of its AI tools).

#### `mandated_report`

The page is a document produced to meet a reporting obligation that concerns reporting on AI, algorithms or digital systems, such as a statutory annual-report section or a compliance or transparency report under a named rule.

#### `formal_record`

An official one-off document of record from a government body: adopted policy or guidance, legislation, council or board minutes or resolutions, budget documents, procurement notice or award, audit or inspection report, **response to a freedom-of-information request** (CX-01.1, W5 = b).

#### `informal_official`

A government body's own communication with no reporting obligation and no standard format: press release, news item, blog, social post, speech, event page, service or FAQ page.

#### `third_party`

Not published by a government body: news, vendor, academic, NGO or policy organization. A register entry quoted in a news article is `third_party` (code the page, not what it quotes).

### Rules

1. `items/core.disclosure_form/rules/0`

Any government-kept multi-entry list in a common format counts as a register, including one institution's own list; single-institution and cross-institution registers are separate values (CX-10, CX-10b). `disclosure_scope` (§3) still codes whole-of-government vs multi-institution for cross-institution registers; `register_single_institution` must carry `disclosure_scope` = `single_institution` (QC check).

2. `items/core.disclosure_form/rules/1`

The obligation must be named on the page, except that it may be inferred from the document's genre **when the document's title names AI or algorithmic reporting**. Otherwise a statutory annual report or a compliance report under a rule not about AI is `formal_record`. This is the one stated exception to CX-03.

3. `items/core.disclosure_form/rules/2`

(1) A city's entry in a national algorithm register describing its chatbot → `register_cross_institution`. (2) A ministry annual-report section headed with the regulation that requires AI-use reporting → `mandated_report`. (3) Council minutes approving a Copilot licence → `formal_record`. (4) A mayor's press release launching a chatbot → `informal_official`. (5) A trade-press article about that chatbot → `third_party`. (6) A city web page that lists its five AI tools in a table it made itself → `register_single_institution`.

4. `items/core.disclosure_form/rules/3`

Re-word CX-12/13: `mandated_report` only when the obligation concerns reporting on AI, algorithms or digital systems, named on the page; genre inference allowed only for documents whose title names AI/algorithmic reporting. Otherwise statutory annual reports code `formal_record`.

5. `items/core.disclosure_form/rules/4`

CX-12/13: a document produced to meet a reporting obligation that concerns reporting on AI, algorithms or digital systems (statutory annual-report section, compliance or transparency report under a rule). The obligation must be named on the page, except that it may be inferred from the document's genre when the document's title names AI or algorithmic reporting. Otherwise a statutory annual report or a compliance report under a rule not about AI is formal_record.

6. `items/core.disclosure_form/rules/5`

Add those reports to the same sentence.

7. `items/core.disclosure_form/rules/6`

The page's kind cannot be determined from its text (e.g. an archived fragment with no header).

## `core.disclosure_scope`
<!-- item: core.disclosure_scope sha256: 628eef37275d69d7e443f582adda3242f857898a17311c7d0240482730f58868 -->

| Field | Value |
|---|---|
| item hash | `628eef37275d69d7e443f582adda3242f857898a17311c7d0240482730f58868` |
| family | `disclosure` |
| name | `disclosure_scope` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `1` |
| round | `3` |
| answer_type | `single` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-20..CX-25` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.disclosure_form", "values": ["register_cross_institution", "register_single_institution", "mandated_report"], "source": "X02"}` |
| long_page_rule | `first_section` |
| translation_v25 | `new` |

### Values

#### `whole_of_government`

The listing or document the page belongs to covers institutions across the government (all central agencies, or all units of a level).

#### `multi_institution`

It covers several institutions, but not government-wide (a sector, a region, a group of agencies).

#### `single_institution`

It covers one institution only.

### Rules

1. `items/core.disclosure_scope/rules/0`

Yes, as below.

2. `items/core.disclosure_scope/rules/1`

Pages whose `disclosure_form` is `register_cross_institution`, `register_single_institution` or `mandated_report`. On other pages the field is not asked and stores the reserved "not asked" label (CX-06).

3. `items/core.disclosure_scope/rules/2`

Ask `disclosure_scope` only when `disclosure_form` in {register_cross_institution, register_single_institution, mandated_report}; otherwise store `_NA_`.

4. `items/core.disclosure_scope/rules/3`

Coverage cannot be determined from the page.

## `core.page_complete`
<!-- item: core.page_complete sha256: aa535149e9d7875984e77693fae7af0fd1f205ad48852a9fe3bd856f1f184d14 -->

| Field | Value |
|---|---|
| item hash | `aa535149e9d7875984e77693fae7af0fd1f205ad48852a9fe3bd856f1f184d14` |
| family | `completeness` |
| name | `page_complete` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `1` |
| round | `2` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.page_verdict", "values": ["confirms_activity", "ambiguous_genai", "ambiguous_attribution", "other_body", "event_only"]}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Instruction

'Does the page refer the reader to another page or document for more information about a GenAI activity it mentions?'

### Values

#### `yes`

The page refers the reader to another page or document for more information about a GenAI activity it mentions, so the page is incomplete (see the note on the name).

#### `no`

The page does not refer the reader elsewhere for more information about any GenAI activity it mentions.

### Rules

1. `items/core.page_complete/rules/0`

The first pass also records whether the page holds all available information about every activity it mentions, or links to further pages with information about any of them.

2. `items/core.page_complete/rules/1`

Add a note in the codebook that yes means incomplete.

3. `items/core.page_complete/rules/2`

Note: `yes` means incomplete (the page refers the reader onward); the name `page_complete` reads the other way.

## `core.source_type`
<!-- item: core.source_type sha256: 0008679290c739d3727328af7302d232ef1024cbf908136157fefe819194a76e -->

| Field | Value |
|---|---|
| item hash | `0008679290c739d3727328af7302d232ef1024cbf908136157fefe819194a76e` |
| family | `source` |
| name | `source_type` |
| level | `source` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `1` |
| round | `2` |
| answer_type | `single` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"rule": "only pages not typed automatically from domain or address (r2#25)"}` |
| long_page_rule | `{"rule": "first_section", "source": "combining-rules.json items[core.source_type]; ruling source-01, all-06"}` |
| translation_v25 | `{"column": "source_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[1]"}` |

### Values

#### `news_major`

Major national/international news outlet (Reuters, BBC, NYT, Le Monde, NHK, etc.)

#### `news_trade`

Technology or government trade press (GovTech, FedScoop, PublicTechnology, etc.)

#### `vendor`

Vendor website, case study, blog post, or press release

#### `academic`

Peer-reviewed paper, working paper, university report

#### `policy_org`

Think tank, IGO, or policy organization (OECD, World Bank, ITU, Brookings, etc.)

#### `social_media`

Official social media accounts (Twitter/X, LinkedIn from institutional accounts)

#### `procurement_tender`

Tender notice, RFP, contract award, vendor selection document

#### `other`

None of the above; explain in `source_snippet`

### Rules

1. `items/core.source_type/rules/0`

'Official' comes from the domain field and 'archive' from the address; the classifier only sorts the rest (news, vendor, academic, policy organisation, social media, procurement, other). The question wording is amended.

2. `items/core.source_type/rules/1`

Source type is answered by the same classifier question in every pipeline where it applies. The AI-text pipeline drops its genre table and procurement's fixed value is replaced.

## `core.content_contact_named`
<!-- item: core.content_contact_named sha256: 715fb22182701f236290cb74b351e21b7f78deadf88ad177f90b65b05b413995 -->

| Field | Value |
|---|---|
| item hash | `715fb22182701f236290cb74b351e21b7f78deadf88ad177f90b65b05b413995` |
| family | `disclosure` |
| name | `content_contact_named` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `1` |
| round | `2` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main_plus_chrome` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-51` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.page_verdict", "values": ["confirms_activity", "ambiguous_genai", "ambiguous_attribution", "other_body", "event_only"], "gated_out_value": "no", "source": "final-open F07 (PI 2026-10-30 \"all accepted\")"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Values

#### `yes`

The page gives a named person, office or unit as responsible for the activity or for questions about it; a named official with no contact details counts.

#### `no`

The page names no person, office or unit as responsible for the activity or for questions about it. Pages whose verdict shows no GenAI also take this value.

### Rules

1. `items/core.content_contact_named/rules/0`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.

2. `items/core.content_contact_named/rules/1`

Pipeline change: store a separate `chrome_text` (header/footer/nav) next to main text, and give jev both for the contact item only.

## `core.content_contact_details`
<!-- item: core.content_contact_details sha256: c6e78dae75bb317ad353f8d38c074a99309570906f0fbccb1e4e29913d1e88ac -->

| Field | Value |
|---|---|
| item hash | `c6e78dae75bb317ad353f8d38c074a99309570906f0fbccb1e4e29913d1e88ac` |
| family | `disclosure` |
| name | `content_contact_details` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `1` |
| round | `2` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main_plus_chrome` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-51` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.page_verdict", "values": ["confirms_activity", "ambiguous_genai", "ambiguous_attribution", "other_body", "event_only"], "gated_out_value": "no", "source": "final-open F07 (PI 2026-10-30 \"all accepted\")"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Values

#### `yes`

The page gives contact details anywhere on it: an email address, phone number, postal address or contact form, including press or vendor contacts and site footers.

#### `no`

No contact details appear anywhere on the page, including its header and footer. Pages whose verdict shows no GenAI also take this value.

### Rules

1. `items/core.content_contact_details/rules/0`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.

2. `items/core.content_contact_details/rules/1`

Pipeline change: store a separate `chrome_text` (header/footer/nav) next to main text, and give jev both for the contact item only.

## `core.content_contact`
<!-- item: core.content_contact sha256: ac74198148c2a229f62fe7751cdf74417302701ff91429f6ad20dcc6ec6760a6 -->

| Field | Value |
|---|---|
| item hash | `ac74198148c2a229f62fe7751cdf74417302701ff91429f6ad20dcc6ec6760a6` |
| family | `disclosure` |
| name | `content_contact` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-51` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_contact/rules/0`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.

## `core.content_contact_emails`
<!-- item: core.content_contact_emails sha256: c9df1d05e48c6664217b5e7321ffd7779c265c30e6d20aafeb48e0e6f84cdb53 -->

| Field | Value |
|---|---|
| item hash | `c9df1d05e48c6664217b5e7321ffd7779c265c30e6d20aafeb48e0e6f84cdb53` |
| family | `disclosure` |
| name | `content_contact_emails` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `mechanical` |
| pass | `none` |
| round | `none` |
| answer_type | `list` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main_plus_chrome` |
| visibility | `public_derived` |
| frozen_signature | `CX-01.3:CX-53` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.content_contact", "values": ["yes"]}` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_contact_emails/rules/0`

When `content_contact` = yes, extract the contact with a deterministic `@` search over the stored main page text, the stored header and footer text and the page's e-mail links (e-mail regex in `pilot/contact.py`, `EMAIL_RE`) and store the list beside the code (`content_contact_emails`), in full and internally only; only the domain part of each address and a count are published. No API call. Not yet in the installed instrument; owed to the back-code engineering card

2. `items/core.content_contact_emails/rules/1`

Published supporting quotes stay verbatim, with no masking. Contact e-mails are stored in full internally, and only the domain and a count are published.

3. `items/core.content_contact_emails/rules/2`

Store the full list internally; publish only the domain part (and a count), or only role addresses (no personal-name pattern).

## `core.content_purpose`
<!-- item: core.content_purpose sha256: e2da06a8dc9358f1880a3bf55e71b2f1a850d627aa8abc44fe7836019f45d48e -->

| Field | Value |
|---|---|
| item hash | `e2da06a8dc9358f1880a3bf55e71b2f1a850d627aa8abc44fe7836019f45d48e` |
| family | `disclosure` |
| name | `content_purpose` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-51` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_purpose/rules/0`

Included: the items in CX-51 and CX-52, each `yes` / `no` (yes = stated on the page). For the items CX-51 and CX-52 mark as derived, `yes` and `no` are derived from the activity codes as they state, with no question. Whether they replace or sit beside T2 is an index-construction choice (exclusivity is reported only, index decision 1 = (b)).

2. `items/core.content_purpose/rules/1`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.

3. `items/core.content_purpose/rules/2`

A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question.

4. `items/core.content_purpose/rules/3`

Ask `content_*` only on pages with a GenAI-bearing verdict (the five R-003 values); store `_NA_` otherwise; reword to 'about any GenAI activity on the page'.

5. `items/core.content_purpose/rules/5`

Description items and the data item are also "no" where the verdict shows no GenAI.

Rule entry without a `text` slot, rendered by slot path: `items/core.content_purpose/rules/4`

`items/core.content_purpose/rules/4/draft`

purpose: the activity's function items

## `core.content_tool_or_model`
<!-- item: core.content_tool_or_model sha256: 51b49ac3978e182459b7d7295db44171c97be9b97927cfecb556b21662943a23 -->

| Field | Value |
|---|---|
| item hash | `51b49ac3978e182459b7d7295db44171c97be9b97927cfecb556b21662943a23` |
| family | `disclosure` |
| name | `content_tool_or_model` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-51` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_tool_or_model/rules/0`

Included: the items in CX-51 and CX-52, each `yes` / `no` (yes = stated on the page). For the items CX-51 and CX-52 mark as derived, `yes` and `no` are derived from the activity codes as they state, with no question. Whether they replace or sit beside T2 is an index-construction choice (exclusivity is reported only, index decision 1 = (b)).

2. `items/core.content_tool_or_model/rules/1`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.

3. `items/core.content_tool_or_model/rules/2`

A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question.

4. `items/core.content_tool_or_model/rules/3`

Ask `content_*` only on pages with a GenAI-bearing verdict (the five R-003 values); store `_NA_` otherwise; reword to 'about any GenAI activity on the page'.

5. `items/core.content_tool_or_model/rules/5`

Description items and the data item are also "no" where the verdict shows no GenAI.

Rule entry without a `text` slot, rendered by slot path: `items/core.content_tool_or_model/rules/4`

`items/core.content_tool_or_model/rules/4/draft`

tool or model: tool or model name

## `core.content_vendor`
<!-- item: core.content_vendor sha256: e694522f50d73169edcb4731d0e483c9fa9d4ac600cc78dc90d52b0e591637ac -->

| Field | Value |
|---|---|
| item hash | `e694522f50d73169edcb4731d0e483c9fa9d4ac600cc78dc90d52b0e591637ac` |
| family | `disclosure` |
| name | `content_vendor` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-51` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_vendor/rules/0`

Included: the items in CX-51 and CX-52, each `yes` / `no` (yes = stated on the page). For the items CX-51 and CX-52 mark as derived, `yes` and `no` are derived from the activity codes as they state, with no question. Whether they replace or sit beside T2 is an index-construction choice (exclusivity is reported only, index decision 1 = (b)).

2. `items/core.content_vendor/rules/1`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.

3. `items/core.content_vendor/rules/2`

A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question.

4. `items/core.content_vendor/rules/3`

Ask `content_*` only on pages with a GenAI-bearing verdict (the five R-003 values); store `_NA_` otherwise; reword to 'about any GenAI activity on the page'.

5. `items/core.content_vendor/rules/5`

Description items and the data item are also "no" where the verdict shows no GenAI.

Rule entry without a `text` slot, rendered by slot path: `items/core.content_vendor/rules/4`

`items/core.content_vendor/rules/4/draft`

vendor: model developer, stated or looked up, or contracting party

`items/core.content_vendor/rules/4/amended_by`

Vendor is "yes" if a developer is recorded, whether stated on the page or looked up.

## `core.content_data`
<!-- item: core.content_data sha256: d4c082c3cd02bb721a676870aa414ecb99862a25ba4a616d913a1dff2c9a6014 -->

| Field | Value |
|---|---|
| item hash | `d4c082c3cd02bb721a676870aa414ecb99862a25ba4a616d913a1dff2c9a6014` |
| family | `disclosure` |
| name | `content_data` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `1` |
| round | `2` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-51` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.page_verdict", "values": ["confirms_activity", "ambiguous_genai", "ambiguous_attribution", "other_body", "event_only"], "gated_out_value": "no", "source": "page-09 c"}` |
| long_page_rule | `{"rule": "any_yes", "order": ["yes", "no", "not_documented", "unknown"]}` |
| translation_v25 | `new` |

### Instruction

Code the source PAGE. Does the page state this about any GenAI activity on the page: the data inputs or data handled are described? yes = stated on the page.

### Values

#### `yes`

stated on the page

#### `no`

not stated on the page

### Rules

1. `items/core.content_data/rules/0`

Included: the items in CX-51 and CX-52, each `yes` / `no` (yes = stated on the page). For the items CX-51 and CX-52 mark as derived, `yes` and `no` are derived from the activity codes as they state, with no question. Whether they replace or sit beside T2 is an index-construction choice (exclusivity is reported only, index decision 1 = (b)).

2. `items/core.content_data/rules/1`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.

3. `items/core.content_data/rules/2`

Ask `content_*` only on pages with a GenAI-bearing verdict (the five R-003 values); store `_NA_` otherwise; reword to 'about any GenAI activity on the page'.

4. `items/core.content_data/rules/3`

One page question, asked on GenAI pages.

5. `items/core.content_data/rules/4`

Description items and the data item are also "no" where the verdict shows no GenAI.

## `core.content_users`
<!-- item: core.content_users sha256: e6b026ff14d744e53ccdc05477f044ae2fc859763efdac15f182159b02134f29 -->

| Field | Value |
|---|---|
| item hash | `e6b026ff14d744e53ccdc05477f044ae2fc859763efdac15f182159b02134f29` |
| family | `disclosure` |
| name | `content_users` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-51` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_users/rules/0`

Included: the items in CX-51 and CX-52, each `yes` / `no` (yes = stated on the page). For the items CX-51 and CX-52 mark as derived, `yes` and `no` are derived from the activity codes as they state, with no question. Whether they replace or sit beside T2 is an index-construction choice (exclusivity is reported only, index decision 1 = (b)).

2. `items/core.content_users/rules/1`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.

3. `items/core.content_users/rules/2`

A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question.

4. `items/core.content_users/rules/3`

Ask `content_*` only on pages with a GenAI-bearing verdict (the five R-003 values); store `_NA_` otherwise; reword to 'about any GenAI activity on the page'.

5. `items/core.content_users/rules/5`

Description items and the data item are also "no" where the verdict shows no GenAI.

Rule entry without a `text` slot, rendered by slot path: `items/core.content_users/rules/4`

`items/core.content_users/rules/4/draft`

users: `target_users` or `governed_population`

`items/core.content_users/rules/4/amended_by`

Users is "yes" if any activity states who the tool serves or who a governance rule applies to (`governed_population`).

## `core.content_status_date`
<!-- item: core.content_status_date sha256: f3207a42027ad36d9bbc48d35d5fc1646baa66804a35809a47c0c9476019ffe9 -->

| Field | Value |
|---|---|
| item hash | `f3207a42027ad36d9bbc48d35d5fc1646baa66804a35809a47c0c9476019ffe9` |
| family | `disclosure` |
| name | `content_status_date` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-51` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_status_date/rules/0`

Included: the items in CX-51 and CX-52, each `yes` / `no` (yes = stated on the page). For the items CX-51 and CX-52 mark as derived, `yes` and `no` are derived from the activity codes as they state, with no question. Whether they replace or sit beside T2 is an index-construction choice (exclusivity is reported only, index decision 1 = (b)).

2. `items/core.content_status_date/rules/1`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.

3. `items/core.content_status_date/rules/2`

A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question.

4. `items/core.content_status_date/rules/3`

Ask `content_*` only on pages with a GenAI-bearing verdict (the five R-003 values); store `_NA_` otherwise; reword to 'about any GenAI activity on the page'.

5. `items/core.content_status_date/rules/5`

Description items and the data item are also "no" where the verdict shows no GenAI.

Rule entry without a `text` slot, rendered by slot path: `items/core.content_status_date/rules/4`

`items/core.content_status_date/rules/4/draft`

status or date: `adoption_stage` or a year field

## `core.content_human_oversight`
<!-- item: core.content_human_oversight sha256: 0cdfa78ca8fd04c11fd42536140fd698be65ade63c7b7a22f192b6f583450dbc -->

| Field | Value |
|---|---|
| item hash | `0cdfa78ca8fd04c11fd42536140fd698be65ade63c7b7a22f192b6f583450dbc` |
| family | `safeguard` |
| name | `content_human_oversight` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-52` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_human_oversight/rules/0`

Safeguard items included, as Kaser does: `content_human_oversight`, `content_risk_assessment`, `content_user_notification`. They are not asked on the page. Each is the page-level member of one safeguard family tagged by level, derived from that safeguard's shared four-answer question asked once per activity (`has_human_oversight`, `has_risk_assessment`, `has_transparency_notice`): `yes` if any activity on the page is `yes`, otherwise `no`. **`content_user_notification` = yes only if the page describes a notice or label telling users they are interacting with GenAI or that content is AI-generated**; a page announcing that the institution uses GenAI is not by itself a notice (CX-01.1, W1 = a). The shared activity question uses this definition. The overlap with governance G1, G3, G4 is reported under R-070.

2. `items/core.content_human_oversight/rules/1`

One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer.

3. `items/core.content_human_oversight/rules/2`

Ask each safeguard once per (page x activity) in pass 2 and derive both the page-level `content_*` (any activity yes) and the activity-level `has_*` (yes / not_documented) from it.

Rule entry without a `text` slot, rendered by slot path: `items/core.content_human_oversight/rules/3`

`items/core.content_human_oversight/rules/3/draft`

`yes` if any activity on the page is `yes`, otherwise `no`.

## `core.content_risk_assessment`
<!-- item: core.content_risk_assessment sha256: a3b70b60178ef7dcd5bd48adaa28e72935c25cb8cbe3bbf896d19a66e1080a7e -->

| Field | Value |
|---|---|
| item hash | `a3b70b60178ef7dcd5bd48adaa28e72935c25cb8cbe3bbf896d19a66e1080a7e` |
| family | `safeguard` |
| name | `content_risk_assessment` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-52` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_risk_assessment/rules/0`

Safeguard items included, as Kaser does: `content_human_oversight`, `content_risk_assessment`, `content_user_notification`. They are not asked on the page. Each is the page-level member of one safeguard family tagged by level, derived from that safeguard's shared four-answer question asked once per activity (`has_human_oversight`, `has_risk_assessment`, `has_transparency_notice`): `yes` if any activity on the page is `yes`, otherwise `no`. **`content_user_notification` = yes only if the page describes a notice or label telling users they are interacting with GenAI or that content is AI-generated**; a page announcing that the institution uses GenAI is not by itself a notice (CX-01.1, W1 = a). The shared activity question uses this definition. The overlap with governance G1, G3, G4 is reported under R-070.

2. `items/core.content_risk_assessment/rules/1`

One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer.

3. `items/core.content_risk_assessment/rules/2`

Ask each safeguard once per (page x activity) in pass 2 and derive both the page-level `content_*` (any activity yes) and the activity-level `has_*` (yes / not_documented) from it.

Rule entry without a `text` slot, rendered by slot path: `items/core.content_risk_assessment/rules/3`

`items/core.content_risk_assessment/rules/3/draft`

`yes` if any activity on the page is `yes`, otherwise `no`.

## `core.content_user_notification`
<!-- item: core.content_user_notification sha256: 0e4007b0a890b53b2f7e1e2ad543c793600e7d8292c714bad1214188610ccc19 -->

| Field | Value |
|---|---|
| item hash | `0e4007b0a890b53b2f7e1e2ad543c793600e7d8292c714bad1214188610ccc19` |
| family | `safeguard` |
| name | `content_user_notification` |
| level | `page` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-52` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_user_notification/rules/0`

Safeguard items included, as Kaser does: `content_human_oversight`, `content_risk_assessment`, `content_user_notification`. They are not asked on the page. Each is the page-level member of one safeguard family tagged by level, derived from that safeguard's shared four-answer question asked once per activity (`has_human_oversight`, `has_risk_assessment`, `has_transparency_notice`): `yes` if any activity on the page is `yes`, otherwise `no`. **`content_user_notification` = yes only if the page describes a notice or label telling users they are interacting with GenAI or that content is AI-generated**; a page announcing that the institution uses GenAI is not by itself a notice (CX-01.1, W1 = a). The shared activity question uses this definition. The overlap with governance G1, G3, G4 is reported under R-070.

2. `items/core.content_user_notification/rules/1`

One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer.

3. `items/core.content_user_notification/rules/2`

Ask each safeguard once per (page x activity) in pass 2 and derive both the page-level `content_*` (any activity yes) and the activity-level `has_*` (yes / not_documented) from it.

Rule entry without a `text` slot, rendered by slot path: `items/core.content_user_notification/rules/3`

`items/core.content_user_notification/rules/3/draft`

`yes` if any activity on the page is `yes`, otherwise `no`.

## `core.source_url`
<!-- item: core.source_url sha256: 7cb7f3e19ded83dc31917c48b1e7d1a1e05c40bb7288bd65c4a91d005abed815 -->

| Field | Value |
|---|---|
| item hash | `7cb7f3e19ded83dc31917c48b1e7d1a1e05c40bb7288bd65c4a91d005abed815` |
| family | `source` |
| name | `source_url` |
| level | `source` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
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
| input_text | `metadata` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "source_url", "map": "identity"}` |

### Rules

1. `items/core.source_url/rules/0`

The URL of the supplied page, verbatim from the input. **Never fabricate or alter.**

2. `items/core.source_url/rules/1`

Take `source_title` from RenderedPage.title (fallback: first heading); never from a model.

## `core.source_title`
<!-- item: core.source_title sha256: e1d1c299600b950a43908abb37fd003f8d2befe4a8a309b819ec2200cd594bad -->

| Field | Value |
|---|---|
| item hash | `e1d1c299600b950a43908abb37fd003f8d2befe4a8a309b819ec2200cd594bad` |
| family | `source` |
| name | `source_title` |
| level | `source` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
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
| input_text | `metadata` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "source_title", "map": "identity", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[2]"}` |

### Rules

1. `items/core.source_title/rules/0`

Take `source_title` from RenderedPage.title (fallback: first heading); never from a model.

## `core.source_access_date`
<!-- item: core.source_access_date sha256: c0f6e5370bc39a3b99b587ddfed7c5903c3736cbe59af7c4dfa069256c682383 -->

| Field | Value |
|---|---|
| item hash | `c0f6e5370bc39a3b99b587ddfed7c5903c3736cbe59af7c4dfa069256c682383` |
| family | `source` |
| name | `source_access_date` |
| level | `source` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
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
| input_text | `metadata` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "source_access_date", "map": "identity"}` |

### Rules

1. `items/core.source_access_date/rules/0`

Date the supplied page was retrieved (provided in the input metadata as the scrape date).

2. `items/core.source_access_date/rules/1`

Take `source_title` from RenderedPage.title (fallback: first heading); never from a model.

## `core.source_language`
<!-- item: core.source_language sha256: 6cc54c04dceb30c62e55b7cd3d367333c7ad7562d60980cd3dfb379c008533aa -->

| Field | Value |
|---|---|
| item hash | `6cc54c04dceb30c62e55b7cd3d367333c7ad7562d60980cd3dfb379c008533aa` |
| family | `source` |
| name | `source_language` |
| level | `source` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
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
| input_text | `metadata` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "source_language", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[3]"}` |

### Rules

1. `items/core.source_language/rules/0`

Pinned local language-ID library on stored text; same tag grammar as `institution_search_languages`; `mul` when no language exceeds a set share.

## `core.source_on_official_domain`
<!-- item: core.source_on_official_domain sha256: 6945030e27b6e87bbd1b81bea18df0717b95df2423a65ecb5378e833f85aa2c5 -->

| Field | Value |
|---|---|
| item hash | `6945030e27b6e87bbd1b81bea18df0717b95df2423a65ecb5378e833f85aa2c5` |
| family | `source` |
| name | `source_on_official_domain` |
| level | `source` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
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
| input_text | `metadata` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.source_on_official_domain/rules/0`

`own_official` / `other_official` / `not_official` from URL host vs the master official-site overlay.

## `core.syndication_group`
<!-- item: core.syndication_group sha256: fb11c681bcea5419cf7c559de3175aa348bb265e6fa0271621c7e6e791780a2e -->

| Field | Value |
|---|---|
| item hash | `fb11c681bcea5419cf7c559de3175aa348bb265e6fa0271621c7e6e791780a2e` |
| family | `source` |
| name | `syndication_group` |
| level | `source` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
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
| input_text | `metadata` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.syndication_group/rules/0`

Deterministic near-duplicate hash (e.g. shingled MinHash on normalised text) per page; `syndication_group` id; QC flag when codes differ within a group.

## `core.page_review_state`
<!-- item: core.page_review_state sha256: 6e45e6450437a113b42a588c2275f1f76d85bce3bc97f714e508639dc90b5d04 -->

| Field | Value |
|---|---|
| item hash | `6e45e6450437a113b42a588c2275f1f76d85bce3bc97f714e508639dc90b5d04` |
| family | `source` |
| name | `page_review_state` |
| level | `source` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
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
| input_text | `metadata` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.page_review_state/rules/0`

`reviewed` / `fetch_failed` / `no_usable_text` / `link_not_followed_cap` / `link_not_followed_hops`; non-`reviewed` states count as unresolved signals in Stage 6.

2. `items/core.page_review_state/rules/1`

The approved plan's verdict list grows to nine; the review status keeps only failed downloads and links not followed.

## `core.discovery_path`
<!-- item: core.discovery_path sha256: 9463aa96ddbc9e77d36c9a9b1bb2d31abe252a6661a8319355a068bd5c2b01dc -->

| Field | Value |
|---|---|
| item hash | `9463aa96ddbc9e77d36c9a9b1bb2d31abe252a6661a8319355a068bd5c2b01dc` |
| family | `source` |
| name | `discovery_path` |
| level | `source` |
| pipelines | `web_extract` |
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
| input_text | `metadata` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.discovery_path/rules/0`

Add a deterministic `discovery_path` (searched / followed hop n / back-fill followed) on every source row in all runs, and report prevalence with and without followed pages.

## `core.text_source`
<!-- item: core.text_source sha256: ae8c5d2ea7c875db19004206965364543a9c2c3434647602f2e3e89d5f06ed0d -->

| Field | Value |
|---|---|
| item hash | `ae8c5d2ea7c875db19004206965364543a9c2c3434647602f2e3e89d5f06ed0d` |
| family | `source` |
| name | `text_source` |
| level | `source` |
| pipelines | `web_extract` |
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
| input_text | `metadata` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.text_source/rules/0`

A per-row `text_source` (stored / live re-fetch / new run) records which rows lack chrome text and links.

## `core.source_publication_date`
<!-- item: core.source_publication_date sha256: 9b0656c0c6510e1f0f97749c8bbdc50a5450b360a3fb9ebc5858dc67e56d65e3 -->

| Field | Value |
|---|---|
| item hash | `9b0656c0c6510e1f0f97749c8bbdc50a5450b360a3fb9ebc5858dc67e56d65e3` |
| family | `source` |
| name | `source_publication_date` |
| level | `source` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
| linkage | `extractor` |
| coder | `quote_step` |
| pass | `none` |
| round | `none` |
| answer_type | `date` |
| order_tie_rule | `none` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `metadata` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `{"rule": "first_section", "source": "combining-rules.json items[core.source_publication_date]; ruling source-01, all-06"}` |
| translation_v25 | `{"column": "source_publication_date", "map": "identity"}` |

### Rules

1. `items/core.source_publication_date/rules/0`

Take dates from HTML metadata / PDF properties / URL patterns deterministically; if absent, the extractor returns a date with its verbatim quote, validated by R-042.

2. `items/core.source_publication_date/rules/1`

One shared date of 1 November 2022, with "before" needing proof. Date origin is recorded as metadata, web address, quote from page text, archive upper bound, or unknown; the AI-text code changes.

## `core.source_snippet`
<!-- item: core.source_snippet sha256: d0ab6f896f41ba81d558777d6eb9cbba9746d19176c200862a8ff508ac20b284 -->

| Field | Value |
|---|---|
| item hash | `d0ab6f896f41ba81d558777d6eb9cbba9746d19176c200862a8ff508ac20b284` |
| family | `source` |
| name | `source_snippet` |
| level | `source` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
| linkage | `extractor` |
| coder | `quote_step` |
| pass | `none` |
| round | `none` |
| answer_type | `text` |
| order_tie_rule | `none` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "source_snippet", "map": "identity", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[4]"}` |

### Rules

1. `items/core.source_snippet/rules/0`

Define `source_snippet` on v2.7 rows as the verbatim supporting text of the page verdict (truncated), with no paraphrase.

2. `items/core.source_snippet/rules/1`

Snippets are verbatim in every pipeline, no translations are stored, and procurement's rule is amended.

## `core.source_credibility`
<!-- item: core.source_credibility sha256: c0b0cb123df70dc40b5f011df6be100ea1c1b0f331f267454c5a0006d9e39616 -->

| Field | Value |
|---|---|
| item hash | `c0b0cb123df70dc40b5f011df6be100ea1c1b0f331f267454c5a0006d9e39616` |
| family | `source` |
| name | `source_credibility` |
| level | `source` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "source_credibility", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[5]"}` |

### Rules

1. `items/core.source_credibility/rules/0`

`source_credibility` = fixed map from `source_type` plus `low` when `source_publication_date` = unknown; drop the translation clause.

## `core.activity_segment`
<!-- item: core.activity_segment sha256: 682fa27ba8f84d627704cf7f1cfdae2dec8dcf1361701f04355bd3c12d3e24a6 -->

| Field | Value |
|---|---|
| item hash | `682fa27ba8f84d627704cf7f1cfdae2dec8dcf1361701f04355bd3c12d3e24a6` |
| family | `activity_identity` |
| name | `activity_relation_within_page` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `extractor` |
| coder | `classifier` |
| pass | `2` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `{"rule": "combined_list", "source": "combining-rules.json items[core.activity_segment]; ruling activity-19"}` |
| translation_v25 | `new` |

### Instruction

The extractor proposes spans; jev answers per span: new distinct activity / same as span k / component of span k / not an activity.

### Values

#### `same_activity`

The two passages describe the same activity: the same action by the same actor on the same tool or instrument.

#### `component_of_program`

The first passage's activity is a named component of the program described in the second. Both stay separate activities, linked.

#### `has_component`

The first passage describes a program, and the second passage's activity is one of its named components. Both stay separate activities, linked.

#### `shared_participation`

The two passages describe one joint action in which several bodies take part. They are one activity: the two passages are merged. The link needs at least two bodies, each named on the page as taking part, with a quote.

#### `governs`

The first passage's activity is a policy or other governance instrument that sets rules for the activity in the second (for example a policy and a tool it approves). When a pair fits both this link and a component link, this link is used.

#### `governed_by`

The second passage's activity is a policy or other governance instrument that sets rules for the activity in the first. When a pair fits both this link and a component link, this link is used.

#### `distinct_action`

The two passages describe different activities, and none of the other links applies.

#### `unresolved`

The page does not settle whether the two passages describe the same activity or different ones. They are kept separate.

#### `not_an_activity`

The passage does not describe an activity as the activity rule defines one. In a pair of passages, it is used when either passage is not an activity; no other link is coded for that pair.

### Rules

1. `shared_rules/core.rule.activity_unit/0` (shared rule `core.rule.activity_unit`)

One activity = one action (deployment, governance instrument, staff training) by one actor concerning one tool or instrument. A named program is one activity; each named component is its own activity, linked to the program as a component of it. Repeated transactions for the same product by the same unit are one activity. A policy and the tools it approves are separate activities, linked by a "governs" relation.

2. `items/core.activity_segment/rules/1`

One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page.

3. `items/core.activity_segment/rules/2`

Add "has component" and "governed by".

4. `items/core.activity_segment/rules/3`

Components stay separate activities; a governing policy is recorded as governing.

5. `items/core.activity_segment/rules/4`

Each pair of passages gets a link.

## `core.activity_name`
<!-- item: core.activity_name sha256: 728ade2be54620595dfe7ad68dba12705d4bead42e9315aef9886d816caef531 -->

| Field | Value |
|---|---|
| item hash | `728ade2be54620595dfe7ad68dba12705d4bead42e9315aef9886d816caef531` |
| family | `activity_identity` |
| name | `activity_name` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `extractor` |
| coder | `quote_step` |
| pass | `none` |
| round | `none` |
| answer_type | `text` |
| order_tie_rule | `none` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "activity_name", "map": "identity"}` |

### Instruction

Short name. Use official name if one exists (e.g., "MyCity Chatbot", "Pair Platform"). Otherwise descriptive (e.g., "Internal Copilot pilot for document drafting").

## `core.observed_actor_name`
<!-- item: core.observed_actor_name sha256: b32deb08bbf848ebd7916fd76b2317cdfffe2ee0dc14123aaafadce8984eff37 -->

| Field | Value |
|---|---|
| item hash | `b32deb08bbf848ebd7916fd76b2317cdfffe2ee0dc14123aaafadce8984eff37` |
| family | `attribution` |
| name | `observed_actor_name` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `extractor` |
| coder | `quote_step` |
| pass | `none` |
| round | `none` |
| answer_type | `text` |
| order_tie_rule | `none` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `internal` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.observed_actor_name/rules/0`

The extractor returns the verbatim actor name and organisational unit. jev Choice gives the relationship (this institution / unit of it / joint participant / other / unresolved) and the role (as v2.6).

## `core.observed_actor_relationship`
<!-- item: core.observed_actor_relationship sha256: b37c48292069ae16d694b68dbfbd4d7439533287508bb7b79271e591f30998df -->

| Field | Value |
|---|---|
| item hash | `b37c48292069ae16d694b68dbfbd4d7439533287508bb7b79271e591f30998df` |
| family | `attribution` |
| name | `observed_actor_relationship` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `2` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.observed_actor_relationship]; ruling activity-19, activity-14, all-04", "order": ["this_institution", "unit_of_institution", "joint_participant", "unresolved", "other", "not_documented", "unknown"]}` |
| translation_v25 | `new` |

### Values (structured; rendered by slot path)

`items/core.observed_actor_relationship/values/relationship/0/definition`

The searched institution itself carries out or adopts the activity.

`items/core.observed_actor_relationship/values/relationship/1/definition`

An organisational unit of the searched institution (a department, office or service) carries out the activity; it counts for the institution.

`items/core.observed_actor_relationship/values/relationship/2/definition`

The activity is a joint one, and the page names the searched institution as a participant.

`items/core.observed_actor_relationship/values/relationship/3/definition`

The activity belongs to another body: a parent, sibling or neighbouring body, a separate court, board or authority, a similarly named organisation, or a vendor. The searched institution's role is still asked.

`items/core.observed_actor_relationship/values/relationship/4/definition`

The page does not settle whose activity this is. The role of the searched institution is not asked.

`items/core.observed_actor_relationship/values/searched_institution_role/0/definition`

The searched institution buys or contracts for the tool or service in its own name.

`items/core.observed_actor_relationship/values/searched_institution_role/1/definition`

Another body runs or buys the activity for the searched institution, and the page names the searched institution as benefiting.

`items/core.observed_actor_relationship/values/searched_institution_role/2/definition`

The searched institution buys or sets up a contract or framework on behalf of other bodies.

`items/core.observed_actor_relationship/values/searched_institution_role/3/definition`

The searched institution takes part as a unit of the body that carries out the activity.

`items/core.observed_actor_relationship/values/searched_institution_role/4/definition`

The searched institution takes part as one of several joint participants.

### Rules

1. `items/core.observed_actor_relationship/rules/0`

The observed-actor relationship is coded per activity, not per page, with a QC flag on `confirms_activity` pages that have no own / unit / joint activity; the attribution role becomes the second of two linked parts of that relationship (relationship; role of the searched institution, "not asked" when the relationship is unresolved), describes only the searched institution, and counts "beneficiary" only when the page names it; the two parts are published as one column: the relationship code, then `:` and the role code when the role is a real answer, otherwise the relationship code alone; there is no separate published P06 column. The observed actor's own role is kept as a separate internal item, `observed_actor_role`, and not published; the C04 grain rule is kept.

2. `items/core.observed_actor_relationship/rules/1`

The role field describes only the searched institution's part in the activity (contracting authority, beneficiary, central purchasing body, unit, joint) and never creates rows for another institution.

3. `items/core.observed_actor_relationship/rules/2`

The relationship moves to the per-activity pass; a quality check flags 'confirms activity' pages with no activity by this institution, a unit of it or a joint participant; the attribution role becomes part of the relationship, with 'beneficiary' counting only when the page names it.

4. `shared_rules/core.rule.attribution_grain/0` (shared rule `core.rule.attribution_grain`)

An activity carried out by an organisational unit of the named institution (department, office, service) counts for the named institution. An activity of its parent, a sibling, or a separate court, board or authority does not, unless the page says the named institution takes part.

5. `shared_rules/core.rule.attribution_grain/1` (shared rule `core.rule.attribution_grain`)

A joint activity counts when the page names this institution as a participant.

6. `items/core.observed_actor_relationship/rules/4`

Relationship: this institution, unit, joint participant, other, unresolved, unknown.

7. `items/core.observed_actor_relationship/rules/5`

Role of the searched institution: contracting authority, beneficiary, central purchasing body, unit, joint

8. `items/core.observed_actor_relationship/rules/6`

A silent page gets "not documented"; a page that mentions the matter but cannot be settled gets "unknown".

### long_page_rule text

`items/core.observed_actor_relationship/long_page_rule/role_part`

the role part is taken from the same part that produced the relationship

## `core.activity_type`
<!-- item: core.activity_type sha256: 747a666fe663dd4371968d1bb061c0bd5a9d5879b131474fb53b002900c121f9 -->

| Field | Value |
|---|---|
| item hash | `747a666fe663dd4371968d1bb061c0bd5a9d5879b131474fb53b002900c121f9` |
| family | `activity_typing` |
| name | `activity_type` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `2` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `{"rule": "highest_probability", "source": "combining-rules.json items[core.activity_type]; ruling activity-20"}` |
| translation_v25 | `{"column": "activity_type", "map": "identity"}` |

### Instruction

G3O activity typology. See definitions below.

### Values

#### `policy_guidance`

Executive orders, agency memos, acceptable-use rules, procurement standards, internal guidance on permissible GenAI tools and data handling.

#### `pilot_experiment`

Limited trials, sandboxes, proof-of-concept deployments, or time-bounded experiments.

#### `program_initiative`

Cross-agency programs, governance bodies, training programs, or platform rollouts spanning multiple units.

#### `internal_operational`

Routine internal use for drafting, summarization, knowledge search, translation, internal helpdesks, or developer tooling.

#### `public_facing_service`

Citizen- or business-facing chatbots, service navigation, translation, complaint handling, case triage.

### Rules

1. `items/core.activity_type/rules/0`

**Rule: policy vs. pilot.** If an institution has issued a GenAI policy AND is running a pilot, these are **two distinct activities**. Produce separate rows for each (with their respective sources).

2. `items/core.activity_type/rules/1`

**Rule: country-wide program.** If a national program exists but this specific institution's participation is confirmed by a source, record it as an activity. If participation is NOT confirmed, do NOT record an activity row -- instead produce a row with `has_genai_activity` = `unclear`, `genai_evidence` = `ambiguous`, and flag `institution_attribution`.

3. `shared_rules/core.rule.allowed_type_action_pairs/0` (shared rule `core.rule.allowed_type_action_pairs`)

List the allowed (type, action) pairs; activities with other pairs are flagged for review

4. `shared_rules/core.rule.allowed_type_action_pairs/1` (shared rule `core.rule.allowed_type_action_pairs`)

a disallowed pair is flagged for review and no label is changed

5. `items/core.activity_type/rules/3`

Evidence confirms a GenAI activity at this institution, but the kind of undertaking is indeterminate from the available sources. Use only after the five kinds above have been considered and none is supportable -- never as a default.

## `core.action_type`
<!-- item: core.action_type sha256: 85ed03a3421b4a8e7d3dcfaf411bf365a543d05cff8b00bfcabf5cca27ff0131 -->

| Field | Value |
|---|---|
| item hash | `85ed03a3421b4a8e7d3dcfaf411bf365a543d05cff8b00bfcabf5cca27ff0131` |
| family | `activity_typing` |
| name | `action_type` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `2` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `{"rule": "highest_probability", "source": "combining-rules.json items[core.action_type]; ruling activity-20"}` |
| translation_v25 | `new` |

### Values

#### `deployment`

The institution puts a GenAI tool to use, or tries one out, for its own work or for the public. The stage and the purchase status are coded separately.

#### `governance`

The institution issues or applies a rule on GenAI use: a policy, guidance, approved-tool list, order or standard. A body that sets or oversees such rules also counts.

#### `staff_training`

The institution trains its own staff to use GenAI.

#### `program`

A container activity whose named components are each their own activity, linked to it. Used only when the page names the components.

### Rules

1. `items/core.action_type/rules/0`

jev Choice per activity: deployment / procurement / governance / staff_training / proposal / program / unknown. (Whether `proposal` is a type or only a stage is a PI choice.)

2. `items/core.action_type/rules/1`

Drop 'proposal' and 'procurement' from action type, since stage and procurement status carry those, and define 'program' as a container used only with named components.

3. `shared_rules/core.rule.allowed_type_action_pairs/0` (shared rule `core.rule.allowed_type_action_pairs`)

List the allowed (type, action) pairs; activities with other pairs are flagged for review

4. `shared_rules/core.rule.allowed_type_action_pairs/1` (shared rule `core.rule.allowed_type_action_pairs`)

a disallowed pair is flagged for review and no label is changed

5. `shared_rules/core.rule.governance_gate/0` (shared rule `core.rule.governance_gate`)

A body that sets or oversees rules gets the governance questions.

6. `items/core.action_type/rules/4`

The page mentions the activity but does not let it be settled.

## `core.adoption_stage`
<!-- item: core.adoption_stage sha256: c2792d68cd20786326873e3bd3c3d30ae47e431fb8f7e79cd85a3998fae815bc -->

| Field | Value |
|---|---|
| item hash | `c2792d68cd20786326873e3bd3c3d30ae47e431fb8f7e79cd85a3998fae815bc` |
| family | `activity_typing` |
| name | `adoption_stage` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.adoption_stage]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.adoption_stage]; ruling activity-21, all-04", "order": ["discontinued", "production", "pilot", "announced", "proposed", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "adoption_stage", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[6]"}` |

### Values

#### `proposed`

Exploratory or hedged intent with no concrete commitment: "considering," "exploring," "studying feasibility," early discussions, unfunded or undated ideas. The text must still be explicitly generative-AI and tied to this institution. No named tool tied to a timeline, no signed MoU or contract, no budget line, no adopted policy.

#### `announced`

Publicly stated intent to deploy with a concrete, documented commitment but no evidence of actual use. Includes: MoUs, budget allocations without deployment, strategy timelines.

#### `pilot`

Limited deployment: subset of users/departments/use cases; described as trial/pilot/PoC/experiment; time-bounded.

#### `production`

Fully operational: available to intended user base, no longer experimental, in routine operations.

#### `discontinued`

Previously deployed but explicitly ended, cancelled, or suspended.

### Rules

1. `items/core.adoption_stage/rules/0`

Keep adoption_stage for use; add `procurement_status`: none_documented / tender_or_rfp / award_or_contract / payment_or_subscription / unknown. Payment-only activities get adoption_stage `unknown` plus procurement_status `payment_or_subscription`.

2. `items/core.adoption_stage/rules/1`

Purchase records fill the purchase-status field and get an "unknown" adoption stage unless use is shown. The owed contract amendment shrinks to removing purchase language, the procurement rules are amended, and the evidence-tier wording is fixed.

3. `items/core.adoption_stage/rules/2`

The §4.3 amendment shrinks to removing purchase language, and no longer waits on procurement's owed text.

4. `shared_rules/core.rule.ws10_proposals/0` (shared rule `core.rule.ws10_proposals`)

WS10 D4: institution-specific, explicitly GenAI proposals remain a qualifying activity.

5. `items/core.adoption_stage/rules/4`

**"Permanent pilot" rule:** If described as "pilot" but running >12 months AND serving the full intended user base, code `production`. Note in `scope_notes`: "Described as pilot but operational >12 months with full user base."

6. `items/core.adoption_stage/rules/5`

Evidence confirms GenAI activity exists but stage is indeterminate.

## `core.procurement_status`
<!-- item: core.procurement_status sha256: 58c5ee8463a406a72a6126a76b2328fe9b7f760b2d06d510ea5399070137c067 -->

| Field | Value |
|---|---|
| item hash | `58c5ee8463a406a72a6126a76b2328fe9b7f760b2d06d510ea5399070137c067` |
| family | `activity_typing` |
| name | `procurement_status` |
| level | `activity` |
| pipelines | `web_extract`, `procurement` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.procurement_status]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.procurement_status]; ruling activity-19, all-04", "order": ["payment_or_subscription", "award_or_contract", "tender_or_rfp", "none_documented", "not_documented", "unknown"]}` |
| translation_v25 | `new` |

### Values

#### `none_documented`

The page documents the activity but no purchase step for it.

#### `tender_or_rfp`

The institution has issued a call for tenders, a request for proposals or a similar invitation to bid for the tool or service.

#### `award_or_contract`

A contract, award or licence agreement for the tool or service is reported as made.

#### `payment_or_subscription`

The page records a payment, invoice or subscription for the tool or service. On its own this does not show use; the stage is then unknown unless use is shown.

### Rules

1. `items/core.procurement_status/rules/0`

Keep adoption_stage for use; add `procurement_status`: none_documented / tender_or_rfp / award_or_contract / payment_or_subscription / unknown. Payment-only activities get adoption_stage `unknown` plus procurement_status `payment_or_subscription`.

2. `items/core.procurement_status/rules/1`

Purchase records fill the purchase-status field and get an "unknown" adoption stage unless use is shown. The owed contract amendment shrinks to removing purchase language, the procurement rules are amended, and the evidence-tier wording is fixed.

3. `items/core.procurement_status/rules/2`

A page that describes the activity but shows no purchase step takes `none_documented`, which is a real answer; `not_documented` is not used for this item.

4. `items/core.procurement_status/rules/3`

The page mentions a purchase of the tool or service but does not let it be settled.

## `core.model_origin`
<!-- item: core.model_origin sha256: e707525beafe92682470f295f6a3698a11b4ea62a4a037b51a811d7d0229717c -->

| Field | Value |
|---|---|
| item hash | `e707525beafe92682470f295f6a3698a11b4ea62a4a037b51a811d7d0229717c` |
| family | `tool` |
| name | `model_origin` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.model_origin]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "highest_probability", "source": "combining-rules.json items[core.model_origin]; ruling activity-20"}` |
| translation_v25 | `{"column": "access_type", "condition": "When build arrangement is model_trained_or_fine_tuned_by_institution, the old column is not filled (old rules would give mixed or in_house).", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[7]"}` |

### Values

#### `commercial`

The model comes from a commercial provider (for example OpenAI, Microsoft, Google or Anthropic) and is used through its product, licence or programming interface.

#### `open_weight`

The model's weights are openly released (for example Llama, Mistral or Falcon), whether the institution or a provider runs it.

#### `government_developed`

The model was developed by or for a government (for example France's Albert or Germany's OpenGPT-X), including by the institution's own team.

### Rules

1. `items/core.model_origin/rules/0`

`model_origin`: commercial / open_weight / government_developed / unknown. `build_arrangement`: off_the_shelf_product / custom_application_on_external_model / model_trained_or_fine_tuned_by_institution / unknown.

2. `items/core.model_origin/rules/1`

The page mentions the model behind the tool but does not let it be settled.

## `core.build_arrangement`
<!-- item: core.build_arrangement sha256: cb8c1de57bfc0cbbc2a04462a910f62ecf0e7244539f449eb02e52767e847367 -->

| Field | Value |
|---|---|
| item hash | `cb8c1de57bfc0cbbc2a04462a910f62ecf0e7244539f449eb02e52767e847367` |
| family | `tool` |
| name | `build_arrangement` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.build_arrangement]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.build_arrangement]; ruling activity-19, all-04", "order": ["model_trained_or_fine_tuned_by_institution", "custom_application_on_external_model", "off_the_shelf_product", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "access_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[8]"}` |

### Values

#### `off_the_shelf_product`

The institution uses a ready-made product as supplied (for example a commercial chat assistant or an office-suite assistant), set up but not built on.

#### `custom_application_on_external_model`

The institution, or a contractor for it, built its own application (a chatbot, assistant or workflow) on a model it did not train.

#### `model_trained_or_fine_tuned_by_institution`

The institution, or a contractor for it, trained or fine-tuned the model itself. Internal use alone does not show this.

### Rules

1. `items/core.build_arrangement/rules/0`

`model_origin`: commercial / open_weight / government_developed / unknown. `build_arrangement`: off_the_shelf_product / custom_application_on_external_model / model_trained_or_fine_tuned_by_institution / unknown.

2. `items/core.build_arrangement/rules/1`

The page mentions how the tool was built but does not let it be settled.

## `core.interface`
<!-- item: core.interface sha256: c3ee2916f682225c020da3c984b0b43de29fba82c89192e0121d0777cc12a609 -->

| Field | Value |
|---|---|
| item hash | `c3ee2916f682225c020da3c984b0b43de29fba82c89192e0121d0777cc12a609` |
| family | `tool` |
| name | `interface` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.interface]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.interface]; ruling activity-19, all-04", "order": ["conversational", "backend_or_api", "other_interface", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[9]"}` |

### Values

#### `conversational`

Users type or speak to the tool in a chat or question-and-answer exchange, as with a chatbot or assistant window.

#### `backend_or_api`

The tool runs behind the scenes, or other software calls it through a programming interface; users do not talk to it directly.

#### `other_interface`

Users reach the tool in another way than a chat exchange or a back-end connection.

### Rules

1. `items/core.interface/rules/0`

`interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

2. `items/core.interface/rules/1`

Interface becomes conversational / back-end or API / other interface / not applicable / unknown, and deployment mode carries integrated versus standalone.

3. `items/core.interface/rules/2`

The classifier chooses among the real interfaces and the missing-answer labels.

4. `items/core.interface/rules/3`

A silent page gets "not documented"; a page that mentions the matter but cannot be settled gets "unknown".

## `core.function_drafting_writing`
<!-- item: core.function_drafting_writing sha256: c21dd32f1b659edf30de9eb1f67d4f9f28b284186936fadb8cbad6beedfaa36a -->

| Field | Value |
|---|---|
| item hash | `c21dd32f1b659edf30de9eb1f67d4f9f28b284186936fadb8cbad6beedfaa36a` |
| family | `tool` |
| name | `function_drafting_writing` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_drafting_writing]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[10]"}` |

### Values

#### `yes`

The page states that the tool is used for drafting or writing text, such as memos, letters, press releases or social media posts.

#### `no`

The page does not state that the tool is used for drafting or writing text, such as memos, letters, press releases or social media posts.

### Rules

1. `items/core.function_drafting_writing/rules/0`

`interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

## `core.function_summarization`
<!-- item: core.function_summarization sha256: a9556d12c63b142b658400e09842645429bcd7ae1212b3ad57e1e9b5efe4722a -->

| Field | Value |
|---|---|
| item hash | `a9556d12c63b142b658400e09842645429bcd7ae1212b3ad57e1e9b5efe4722a` |
| family | `tool` |
| name | `function_summarization` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_summarization]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[11]"}` |

### Values

#### `yes`

The page states that the tool is used for summarising documents, reports or meetings.

#### `no`

The page does not state that the tool is used for summarising documents, reports or meetings.

### Rules

1. `items/core.function_summarization/rules/0`

`interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

## `core.function_translation`
<!-- item: core.function_translation sha256: 149059df8c5d72b42c0ca1dcee4e85eed3336600b5a7eba9e44e95055d2a4e33 -->

| Field | Value |
|---|---|
| item hash | `149059df8c5d72b42c0ca1dcee4e85eed3336600b5a7eba9e44e95055d2a4e33` |
| family | `tool` |
| name | `function_translation` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_translation]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[12]"}` |

### Values

#### `yes`

The page states that the tool is used for translating text or speech between languages.

#### `no`

The page does not state that the tool is used for translating text or speech between languages.

### Rules

1. `items/core.function_translation/rules/0`

`interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

## `core.function_search_retrieval`
<!-- item: core.function_search_retrieval sha256: e5099ebac371dbafd5bc1ced2a18a0c2f1fd1c394c85dc9646bbb35c832b9101 -->

| Field | Value |
|---|---|
| item hash | `e5099ebac371dbafd5bc1ced2a18a0c2f1fd1c394c85dc9646bbb35c832b9101` |
| family | `tool` |
| name | `function_search_retrieval` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_search_retrieval]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[13]"}` |

### Values

#### `yes`

The page states that the tool is used for finding information, such as answering questions from documents or searching the institution's own records.

#### `no`

The page does not state that the tool is used for finding information, such as answering questions from documents or searching the institution's own records.

### Rules

1. `items/core.function_search_retrieval/rules/0`

`interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

## `core.function_code`
<!-- item: core.function_code sha256: 9a8ffa6538b549724c8cfb2c5688c4ee7e72dd3840a2e0c682d6ee28467f61ab -->

| Field | Value |
|---|---|
| item hash | `9a8ffa6538b549724c8cfb2c5688c4ee7e72dd3840a2e0c682d6ee28467f61ab` |
| family | `tool` |
| name | `function_code` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_code]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[14]"}` |

### Values

#### `yes`

The page states that the tool is used for writing, reviewing or fixing software code.

#### `no`

The page does not state that the tool is used for writing, reviewing or fixing software code.

### Rules

1. `items/core.function_code/rules/0`

`interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

## `core.function_image_audio_video`
<!-- item: core.function_image_audio_video sha256: bf683421e2544ede91205041d9dfec1419c5cd55180bebeed64e0ed7bd5bb3a7 -->

| Field | Value |
|---|---|
| item hash | `bf683421e2544ede91205041d9dfec1419c5cd55180bebeed64e0ed7bd5bb3a7` |
| family | `tool` |
| name | `function_image_audio_video` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_image_audio_video]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[15]"}` |

### Values

#### `yes`

The page states that the tool is used for creating or editing images, audio or video.

#### `no`

The page does not state that the tool is used for creating or editing images, audio or video.

### Rules

1. `items/core.function_image_audio_video/rules/0`

`interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

## `core.function_extraction_classification`
<!-- item: core.function_extraction_classification sha256: f2127d70ceed5bb5bed14a924d08591cee5d29841cdf072a02583dd8e45e550b -->

| Field | Value |
|---|---|
| item hash | `f2127d70ceed5bb5bed14a924d08591cee5d29841cdf072a02583dd8e45e550b` |
| family | `tool` |
| name | `function_extraction_classification` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_extraction_classification]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[16]"}` |

### Values

#### `yes`

The page states that the tool is used for pulling information out of documents or forms, or sorting and classifying them.

#### `no`

The page does not state that the tool is used for pulling information out of documents or forms, or sorting and classifying them.

### Rules

1. `items/core.function_extraction_classification/rules/0`

`interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

## `core.function_analysis_recommendation`
<!-- item: core.function_analysis_recommendation sha256: 6f6c4ee0ad101664c8ffb39f0a182a76baf21b1e7a9af80044f9d48a5d831560 -->

| Field | Value |
|---|---|
| item hash | `6f6c4ee0ad101664c8ffb39f0a182a76baf21b1e7a9af80044f9d48a5d831560` |
| family | `tool` |
| name | `function_analysis_recommendation` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_analysis_recommendation]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[17]"}` |

### Values

#### `yes`

The page states that the tool is used for analysing information or giving recommendations or scores to support human decisions, such as case triage or eligibility checks.

#### `no`

The page does not state that the tool is used for analysing information or giving recommendations or scores to support human decisions, such as case triage or eligibility checks.

### Rules

1. `items/core.function_analysis_recommendation/rules/0`

`interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

## `core.tool_name`
<!-- item: core.tool_name sha256: 4c960a1917007ed502ea252e91c5370eeddfa71ee468390b7f7ffe488a9e6beb -->

| Field | Value |
|---|---|
| item hash | `4c960a1917007ed502ea252e91c5370eeddfa71ee468390b7f7ffe488a9e6beb` |
| family | `tool` |
| name | `tool_name` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `extractor` |
| coder | `quote_step` |
| pass | `none` |
| round | `none` |
| answer_type | `list` |
| order_tie_rule | `none` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.tool_name]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `combined_list` |
| translation_v25 | `{"column": "tool_name", "map": "identity"}` |

### Instruction

Specific tool, model, or platform name (e.g., "Microsoft 365 Copilot", "ChatGPT", "Albert").

### Rules

1. `items/core.tool_name/rules/0`

`tool_name` = product or platform as written on the page; new `model_name` = model as written (e.g. "GPT-4o") or `unknown`. Several tools are `; `-separated in page order. `not_applicable` for activities without a tool.

2. `items/core.tool_name/rules/1`

The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.model_name`
<!-- item: core.model_name sha256: 34a1685ff0f6304c3ae75cd690ac994f6a3f7e0cf0bc08ddcfec3e2a6ae8de8b -->

| Field | Value |
|---|---|
| item hash | `34a1685ff0f6304c3ae75cd690ac994f6a3f7e0cf0bc08ddcfec3e2a6ae8de8b` |
| family | `tool` |
| name | `model_name` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `extractor` |
| coder | `quote_step` |
| pass | `none` |
| round | `none` |
| answer_type | `list` |
| order_tie_rule | `none` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.model_name]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `combined_list` |
| translation_v25 | `new` |

### Rules

1. `items/core.model_name/rules/0`

`tool_name` = product or platform as written on the page; new `model_name` = model as written (e.g. "GPT-4o") or `unknown`. Several tools are `; `-separated in page order. `not_applicable` for activities without a tool.

2. `items/core.model_name/rules/1`

The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.contracting_party`
<!-- item: core.contracting_party sha256: f27653658f96d43998f2df1cc678c307b15c520c5decb3777d2d20f12f851c96 -->

| Field | Value |
|---|---|
| item hash | `f27653658f96d43998f2df1cc678c307b15c520c5decb3777d2d20f12f851c96` |
| family | `tool` |
| name | `contracting_party` |
| level | `activity` |
| pipelines | `web_extract`, `procurement` |
| linkage | `extractor` |
| coder | `quote_step` |
| pass | `none` |
| round | `none` |
| answer_type | `text` |
| order_tie_rule | `none` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.contracting_party]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "combined_list", "source": "combining-rules.json items[core.contracting_party]; ruling activity-19"}` |
| translation_v25 | `{"column": "vendor", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[18]"}` |

### Rules

1. `items/core.contracting_party/rules/0`

Developer (from lookup or page, with its basis recorded) and contracting party (page-stated only).

2. `items/core.contracting_party/rules/1`

Vendor holds what the source names, which in purchase records is the contracting party. The developer from the lookup goes into a new model-developer column, and the lookup stops filling vendor.

3. `items/core.contracting_party/rules/2`

The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.developer`
<!-- item: core.developer sha256: 6d8f20d47f88ffa283e605b5b8c241c8f0450f3ab2e38bf0cc6d5a81cb56b8f0 -->

| Field | Value |
|---|---|
| item hash | `6d8f20d47f88ffa283e605b5b8c241c8f0450f3ab2e38bf0cc6d5a81cb56b8f0` |
| family | `tool` |
| name | `developer` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `pipeline` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `text` |
| order_tie_rule | `none` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.developer]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "combined_list", "source": "combining-rules.json items[core.developer]; ruling activity-19"}` |
| translation_v25 | `{"column": "vendor", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[19]"}` |

### Rules

1. `items/core.developer/rules/0`

Developer (from lookup or page, with its basis recorded) and contracting party (page-stated only).

2. `items/core.developer/rules/1`

vendor = the organisation the page names as supplying the GenAI product or service, verbatim. If none is named but tool_name matches a published lookup table (product -> developer, versioned), fill it deterministically and set `vendor_basis` = lookup, otherwise `stated`.

3. `items/core.developer/rules/2`

The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.developer_basis`
<!-- item: core.developer_basis sha256: 69d48cfec18b21e93b776f59f7debbbe66734ecebfb0e70855672b311fcd3a8e -->

| Field | Value |
|---|---|
| item hash | `69d48cfec18b21e93b776f59f7debbbe66734ecebfb0e70855672b311fcd3a8e` |
| family | `provenance` |
| name | `developer_basis` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `mechanical` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.developer_basis/rules/0`

Developer (from lookup or page, with its basis recorded) and contracting party (page-stated only).

2. `items/core.developer_basis/rules/1`

Every 'how we know' field uses the same five values: stated, from metadata, looked up, derived, quoted by the quote step. The per-run version record also holds the codebook version, the channel tag stays on each row, and per-code coder details are stored internally and linked to that record.

## `core.deployment_mode`
<!-- item: core.deployment_mode sha256: e9160a52e14cdec94954a5ebc06659530de0027b705d6a7cf86b351cb7e0c90b -->

| Field | Value |
|---|---|
| item hash | `e9160a52e14cdec94954a5ebc06659530de0027b705d6a7cf86b351cb7e0c90b` |
| family | `tool` |
| name | `deployment_mode` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.deployment_mode]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "highest_probability", "source": "combining-rules.json items[core.deployment_mode]; ruling activity-20"}` |
| translation_v25 | `{"column": "deployment_mode", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[20]"}` |

### Instruction

`standalone`: separate tool/interface. `integrated`: embedded in existing system (e.g., Copilot inside Outlook).

### Values

#### `integrated`

integrated: the GenAI feature works inside software or a service channel the institution already used (office suite, case system, existing website service).

#### `standalone`

standalone: a separate application or site created for the GenAI tool.

### Rules

1. `items/core.deployment_mode/rules/0`

The page mentions whether the tool is separate or built into existing software but does not let it be settled.

## `core.target_users`
<!-- item: core.target_users sha256: 81b0492719d9b307f44ef4ee5b2bec3edfae804d90980ab9b076aba2178a928d -->

| Field | Value |
|---|---|
| item hash | `81b0492719d9b307f44ef4ee5b2bec3edfae804d90980ab9b076aba2178a928d` |
| family | `tool` |
| name | `target_users` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.target_users]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "combined_list", "then": "mapping step to one value", "source": "combining-rules.json items[core.target_users].alternative; ruling activity-22 b"}` |
| translation_v25 | `{"column": "target_users", "map": "identity"}` |

### Instruction

Who interacts with the GenAI system.

### Values

#### `internal_staff`

Only the institution's own staff use the tool.

#### `public`

People outside the institution use the tool: members of the public, residents or businesses.

#### `both`

Both the institution's staff and people outside it use the tool. On long pages, one part naming staff and another the public also gives this value.

### Rules

1. `items/core.target_users/rules/0`

target_users only for tool activities (`not_applicable` otherwise). A04 for governance.

2. `items/core.target_users/rules/1`

The page mentions who uses the tool but does not let it be settled.

### long_page_rule text

`items/core.target_users/long_page_rule/mapping/other_lists`

Drop 'not covered by this part' and missing labels from the list. 'both' present, or staff and public both present, gives 'both'. One real value gives that value. No real value: not_documented if any part says the page is silent, else unknown. Every part 'not covered' gives not_documented.

## `core.governed_population`
<!-- item: core.governed_population sha256: 8548e8dbd51ea4a8c03dc0aa0b53b7a2e70cf495c3ed7eeeb2da82faee7c582b -->

| Field | Value |
|---|---|
| item hash | `8548e8dbd51ea4a8c03dc0aa0b53b7a2e70cf495c3ed7eeeb2da82faee7c582b` |
| family | `governance` |
| name | `governed_population` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"item": "core.action_type", "values": ["governance"], "rule": "core.rule.governance_gate"}` |
| long_page_rule | `{"rule": "combined_list", "then": "mapping step to one value", "source": "combining-rules.json items[core.governed_population].alternative; ruling activity-22 b"}` |
| translation_v25 | `new` |

### Values

#### `internal_personnel`

The rule applies to the institution's own staff and officials.

#### `external_users`

The rule applies to people or bodies outside the institution, such as the public or the parties it regulates.

#### `both`

The rule applies both to the institution's own staff and to people or bodies outside it. On long pages, one part naming each also gives this value.

### Rules

1. `items/core.governed_population/rules/0`

jev Choice: internal_personnel / external_users / both / unknown; `not_applicable` for non-governance.

2. `items/core.governed_population/rules/1`

The page mentions whom the rule applies to but does not let it be settled.

### long_page_rule text

`items/core.governed_population/long_page_rule/mapping/other_lists`

Drop 'not covered by this part' and missing labels from the list. 'both' present, or staff and public both present, gives 'both'. One real value gives that value. No real value: not_documented if any part says the page is silent, else unknown. Every part 'not covered' gives not_documented.

## `core.governance_form`
<!-- item: core.governance_form sha256: 1022dfd04964d1ddc24f2604645f6c15f13b769e42a00f3686e5ba8cfea26fea -->

| Field | Value |
|---|---|
| item hash | `1022dfd04964d1ddc24f2604645f6c15f13b769e42a00f3686e5ba8cfea26fea` |
| family | `governance` |
| name | `governance_form` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `multi` |
| order_tie_rule | `all_that_apply` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.action_type", "values": ["governance"], "rule": "core.rule.governance_gate"}` |
| long_page_rule | `combined_list` |
| translation_v25 | `new` |

### Values

#### `dedicated_genai_or_ai_policy_or_guideline`

A policy, guideline, code of practice or acceptable-use rule whose main subject is generative AI or AI.

#### `approved_tool_list_or_endorsement`

A list of approved or permitted GenAI tools, or an official endorsement of a named tool.

#### `clause_in_instrument_on_other_subject`

A clause on GenAI inside a rule, policy or guidance whose main subject is something else (for example IT security or records management).

#### `court_or_regulatory_order`

An order, decision or practice direction on GenAI use issued by a court or a regulator.

#### `procurement_standard`

A standard or requirement for buying GenAI tools or services, such as purchasing criteria or contract terms.

### Rules

1. `items/core.governance_form/rules/0`

jev Choice: dedicated_genai_or_ai_policy_or_guideline / approved_tool_list_or_endorsement / clause_in_instrument_on_other_subject / court_or_regulatory_order / procurement_standard / unknown. Applies only when the action is governance (`not_applicable` otherwise).

2. `items/core.governance_form/rules/1`

S6 c: `governance_form` becomes multi-select, so a document can be both guideline and endorsement.

3. `items/core.governance_form/rules/2`

The page mentions the form of the rule but does not let it be settled.

## `core.governance_direction`
<!-- item: core.governance_direction sha256: 3c1d1277c4675ae3f17ef40058f9a08e9daffb352d75934037723bc1e5cbf5c3 -->

| Field | Value |
|---|---|
| item hash | `3c1d1277c4675ae3f17ef40058f9a08e9daffb352d75934037723bc1e5cbf5c3` |
| family | `governance` |
| name | `governance_direction` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"item": "core.action_type", "values": ["governance"], "rule": "core.rule.governance_gate"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.governance_direction]; ruling activity-19, activity-10, activity-11, all-04", "order": ["restricts_with_conditions", "prohibits", "permits", "requires", "promotes", "not_documented", "unknown"]}` |
| translation_v25 | `new` |

### Values

#### `prohibits`

The rule bans the GenAI use it covers, with no use allowed.

#### `restricts_with_conditions`

The rule allows use only under conditions (for example approval, training, limits on data, or human review), or bans some uses and allows others. On long pages, a ban in one part and a permission in another also give this value.

#### `permits`

The rule allows the use without conditions.

#### `requires`

The rule makes GenAI use mandatory for some task or for some staff.

#### `promotes`

The rule encourages or supports GenAI use without making it mandatory.

### Rules

1. `items/core.governance_direction/rules/0`

One classifier question on governance activities only: prohibits, restricts with conditions, permits, requires or promotes, unknown; not applicable otherwise; with a supporting quote.

2. `items/core.governance_direction/rules/1`

Two values, "requires" and "promotes"

3. `items/core.governance_direction/rules/2`

"Permits" only when use is allowed without conditions; across parts, a ban in one part and a permission in another also becomes "restricts with conditions" (a mapping step).

4. `items/core.governance_direction/rules/3`

A silent page gets "not documented"; a page that mentions the matter but cannot be settled gets "unknown".

### long_page_rule text

`items/core.governance_direction/long_page_rule/rank_of_requires_vs_promotes`

Order: restricts_with_conditions, prohibits, permits, requires, promotes, not_documented, unknown.

## `core.service_domain`
<!-- item: core.service_domain sha256: cd57c8b15002f6d8218e8d4f6e3012a147415c0799f8a664f3488bd38bbcadf5 -->

| Field | Value |
|---|---|
| item hash | `cd57c8b15002f6d8218e8d4f6e3012a147415c0799f8a664f3488bd38bbcadf5` |
| family | `activity_typing` |
| name | `service_domain` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `multi` |
| order_tie_rule | `all_that_apply` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `{"rule": "combined_list", "source": "combining-rules.json items[core.service_domain]; ruling activity-20", "per_value_producing_part": "highest_probability", "replaces_rule": "highest_probability (activity-20 a, before activity-13 b made the item multi-select)"}` |
| translation_v25 | `new` |

### Values

#### `general_public_services`

Running government itself: executive and legislative bodies, financial, fiscal and tax affairs, foreign affairs, and general administration and internal services. The earlier value 'general administration' is coded here.

#### `defence`

Military and civil defence.

#### `public_order_safety`

Police, fire protection, the courts and prisons.

#### `economic_affairs`

Economic, commercial and labour affairs; agriculture, forestry and fishing; fuel and energy; industry and construction; transport; communication.

#### `environmental_protection`

Waste and waste-water management, pollution control, and the protection of biodiversity and landscape.

#### `housing_community_amenities`

Housing and community development, water supply and street lighting.

#### `health`

Medical products, outpatient and hospital services, and public health services.

#### `recreation_culture_religion`

Recreation and sport, culture, broadcasting and publishing, and religious and other community services.

#### `education`

Education at every level, from pre-primary to university, and services that support it.

#### `social_protection`

Support in sickness and disability, old age, for survivors, families and children, in unemployment, for housing, and against social exclusion.

#### `other`

An area that fits none of the ten areas above.

### Rules

1. `items/core.service_domain/rules/0`

One classifier question per activity over a short list of areas plus 'general administration' and 'unknown'.

2. `items/core.service_domain/rules/1`

The UN and Eurostat classification of the functions of government, top level (as used by Public Sector Tech Watch)

3. `items/core.service_domain/rules/2`

Activities that fit no area get "other".

4. `items/core.service_domain/rules/3`

The question becomes a tick-all-that-apply list.

5. `items/core.service_domain/rules/4`

A silent page gets "not documented"; a page that mentions the matter but cannot be settled gets "unknown".

6. `items/core.service_domain/rules/5`

No separate value. A rule says the earlier 'general administration' is coded 'general public services'.

### long_page_rule text

`items/core.service_domain/long_page_rule/multi_select_vs_single_winner`

Take every area any part ticks with a supported answer. Each area's quote and certainty come from the part most sure of it. Missing labels only if no part ticks a real area.

## `core.genai_mechanism_basis`
<!-- item: core.genai_mechanism_basis sha256: 8386c42537ca24971610796d9c7fca06aacd3e0988b13ce4109e79131b3ebb1e -->

| Field | Value |
|---|---|
| item hash | `8386c42537ca24971610796d9c7fca06aacd3e0988b13ce4109e79131b3ebb1e` |
| family | `verdict` |
| name | `genai_mechanism_basis` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `2` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.genai_mechanism_basis]; ruling activity-19, all-04", "order": ["named_genai_product_or_model", "explicit_genai_label", "generative_capability_described", "ai_chatbot_or_assistant_label_only", "not_documented", "unknown"]}` |
| translation_v25 | `new` |

### Values

#### `named_genai_product_or_model`

The page names a generative product or model, such as ChatGPT, Copilot, Gemini, Claude or a named language model.

#### `explicit_genai_label`

The page calls the tool generative AI, a large language model or the like, without naming a product.

#### `generative_capability_described`

The page says the tool generates text, images, audio, code or other content, without naming a product or using a generative-AI label.

#### `ai_chatbot_or_assistant_label_only`

The only signal is that the page calls the tool an 'AI chatbot' or 'AI assistant'; under the GenAI boundary rule this counts as generative.

### Rules

1. `items/core.genai_mechanism_basis/rules/0`

jev Choice on every confirms_activity page/activity: named_genai_product_or_model / explicit_genai_label / generative_capability_described / ai_chatbot_or_assistant_label_only. The extractor returns the supporting quote.

2. `shared_rules/core.rule.genai_boundary/0` (shared rule `core.rule.genai_boundary`)

Generative-AI wording: the re-pilot 2 wording governs (SRC-7 L34-45), including that a named "AI chatbot or AI assistant" counts as a generative product; `system_prompt.md` L15 rule ("chatbot" alone is not evidence) is amended to match. A named "AI chatbot" or "AI assistant" counts as generative and overrides the rule-based-chatbot exclusion (contract L12) for that naming.

3. `shared_rules/core.rule.genai_boundary/1` (shared rule `core.rule.genai_boundary`)

S1 a: translation counts as generative AI only when the page ties it to a named generative product or says a language model produces it.

## `core.year_announced`
<!-- item: core.year_announced sha256: 490389fef42e79b3d4599328ae2115a1592f32ee2b46df77d03d0cb952467213 -->

| Field | Value |
|---|---|
| item hash | `490389fef42e79b3d4599328ae2115a1592f32ee2b46df77d03d0cb952467213` |
| family | `dates` |
| name | `year_announced` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.year_announced]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `earliest_year` |
| translation_v25 | `{"column": "year_announced", "map": "identity"}` |

### Instruction

"In which year does the page say this activity was first announced?"

### Values (structured; rendered by slot path)

### Rules

1. `items/core.year_announced/rules/0`

Deterministic: extract all four-digit years 2015-2030 from the activity span and its context. jev Choice over those years plus `unknown`: "In which year does the page say this activity was first announced?" No fallback to publication year. Across chunks: earliest chosen year.

2. `items/core.year_announced/rules/1`

Pilot and production years use the same candidate-then-classifier method, with candidates converted from other calendars and fiscal years under a multilingual-subproject rule. Governance uses the announcement year as its adoption year and marks pilot and production years not applicable.

## `core.year_pilot_start`
<!-- item: core.year_pilot_start sha256: 7e8eec1bffcb92388ee8e4c2f61bffbeafb1d8f8fd9f703f62c5154a04b0cc3a -->

| Field | Value |
|---|---|
| item hash | `7e8eec1bffcb92388ee8e4c2f61bffbeafb1d8f8fd9f703f62c5154a04b0cc3a` |
| family | `dates` |
| name | `year_pilot_start` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.year_pilot_start]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `earliest_year` |
| translation_v25 | `{"column": "year_deployed", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[21]"}` |

### Values (structured; rendered by slot path)

### Rules

1. `items/core.year_pilot_start/rules/0`

Deterministic: extract all four-digit years 2015-2030 from the activity span and its context. jev Choice over those years plus `unknown`: "In which year does the page say this activity was first announced?" No fallback to publication year. Across chunks: earliest chosen year.

2. `items/core.year_pilot_start/rules/1`

Pilot and production years use the same candidate-then-classifier method, with candidates converted from other calendars and fiscal years under a multilingual-subproject rule. Governance uses the announcement year as its adoption year and marks pilot and production years not applicable.

3. `items/core.year_pilot_start/rules/2`

Two columns, each stated-only.

## `core.year_production_start`
<!-- item: core.year_production_start sha256: 530fec649c78cff7ace582cc47588176ef4708e456738475d267c001fb9f0ac2 -->

| Field | Value |
|---|---|
| item hash | `530fec649c78cff7ace582cc47588176ef4708e456738475d267c001fb9f0ac2` |
| family | `dates` |
| name | `year_production_start` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.year_production_start]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `earliest_year` |
| translation_v25 | `{"column": "year_deployed", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[22]"}` |

### Values (structured; rendered by slot path)

### Rules

1. `items/core.year_production_start/rules/0`

Deterministic: extract all four-digit years 2015-2030 from the activity span and its context. jev Choice over those years plus `unknown`: "In which year does the page say this activity was first announced?" No fallback to publication year. Across chunks: earliest chosen year.

2. `items/core.year_production_start/rules/1`

Pilot and production years use the same candidate-then-classifier method, with candidates converted from other calendars and fiscal years under a multilingual-subproject rule. Governance uses the announcement year as its adoption year and marks pilot and production years not applicable.

3. `items/core.year_production_start/rules/2`

Two columns, each stated-only.

## `core.deployment_scale_number`
<!-- item: core.deployment_scale_number sha256: f475424d5b5a9a547768e9d58e2d9ac0cb9927308630ccc156fe4d361be0ac19 -->

| Field | Value |
|---|---|
| item hash | `f475424d5b5a9a547768e9d58e2d9ac0cb9927308630ccc156fe4d361be0ac19` |
| family | `scale` |
| name | `deployment_scale_number` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `extractor` |
| coder | `quote_step` |
| pass | `none` |
| round | `none` |
| answer_type | `number` |
| order_tie_rule | `none` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.deployment_scale_number]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "combined_list", "pairs": "(number, unit), the unit from the same part as its number", "source": "combining-rules.json items[core.deployment_scale_number].alternative; ruling activity-24 b"}` |
| translation_v25 | `new` |

### Rules

1. `items/core.deployment_scale_number/rules/0`

The extractor returns the verbatim number span. jev Choice gives the unit: licences_or_seats / users / interactions / units_or_departments / none.

2. `items/core.deployment_scale_number/rules/1`

the quote step copies the scale number verbatim and the classifier picks the unit

3. `items/core.deployment_scale_number/rules/2`

The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.deployment_scale_unit`
<!-- item: core.deployment_scale_unit sha256: da0f1f763a76751f02792b920c7cbbb52a0bf11950f4f96c6780d736b4eed8d6 -->

| Field | Value |
|---|---|
| item hash | `da0f1f763a76751f02792b920c7cbbb52a0bf11950f4f96c6780d736b4eed8d6` |
| family | `scale` |
| name | `deployment_scale_unit` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `4` |
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
| status | `slot` |
| gate | `{"item": "core.deployment_scale_number", "values": ["any stated"]}` |
| long_page_rule | `{"rule": "combined_list", "pairs": "(number, unit), the unit from the same part as its number", "source": "combining-rules.json items[core.deployment_scale_unit].alternative; ruling activity-24 b"}` |
| translation_v25 | `new` |

### Values

#### `licences_or_seats`

The number counts licences, seats or accounts bought or issued.

#### `users`

The number counts people who use the tool.

#### `interactions`

The number counts uses of the tool, such as questions answered, conversations held or documents handled.

#### `units_or_departments`

The number counts offices, departments, schools or other units that use the tool.

#### `none`

A number is stated, but it counts none of these units.

### Rules

1. `items/core.deployment_scale_unit/rules/0`

The extractor returns the verbatim number span. jev Choice gives the unit: licences_or_seats / users / interactions / units_or_departments / none.

## `core.has_human_oversight`
<!-- item: core.has_human_oversight sha256: 3c2001c829bacae4f2f7e3961d8e95c0b7345000c1903cd508cc411d63ce4769 -->

| Field | Value |
|---|---|
| item hash | `3c2001c829bacae4f2f7e3961d8e95c0b7345000c1903cd508cc411d63ce4769` |
| family | `safeguard` |
| name | `has_human_oversight` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.has_human_oversight]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.has_human_oversight]; ruling activity-23, all-04 (order: the draft's alternative (b))", "order": ["yes", "no", "unclear", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "has_human_oversight", "map": "identity"}` |

### Instruction

Is human review required before acting on GenAI outputs?

### Values

#### `yes`

yes: the page states the safeguard applies to this activity (for a governance activity: the rule requires it).

#### `no`

no: the page states it does not apply.

#### `unclear`

unclear: the page mentions the safeguard but it cannot be settled whether it applies to this activity.

### Rules

1. `shared_rules/core.rule.safeguard_attachment/0` (shared rule `core.rule.safeguard_attachment`)

A safeguard in a governance activity is not copied to deployment activities in pass 2. Stage 6 may link them only through a recorded relation.

2. `shared_rules/core.rule.safeguard_attachment/1` (shared rule `core.rule.safeguard_attachment`)

A contract with safeguard clauses is split off as a governance activity linked to the tool.

3. `items/core.has_human_oversight/rules/1`

One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer.

4. `items/core.has_human_oversight/rules/2`

not_documented: the page is silent.

## `core.has_transparency_notice`
<!-- item: core.has_transparency_notice sha256: 992b6e22dcd511270d2adf2d2fe96ff95bd8cb5b2d1e2bd6e89fc47fac8447c7 -->

| Field | Value |
|---|---|
| item hash | `992b6e22dcd511270d2adf2d2fe96ff95bd8cb5b2d1e2bd6e89fc47fac8447c7` |
| family | `safeguard` |
| name | `has_transparency_notice` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.has_transparency_notice]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.has_transparency_notice]; ruling activity-23, all-04 (order: the draft's alternative (b))", "order": ["yes", "no", "unclear", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "has_transparency_notice", "map": "identity"}` |

### Instruction

Are users/citizens notified that GenAI is involved?

### Values

#### `yes`

yes: the page states the safeguard applies to this activity (for a governance activity: the rule requires it).

#### `no`

no: the page states it does not apply.

#### `unclear`

unclear: the page mentions the safeguard but it cannot be settled whether it applies to this activity.

### Rules

1. `shared_rules/core.rule.safeguard_attachment/0` (shared rule `core.rule.safeguard_attachment`)

A safeguard in a governance activity is not copied to deployment activities in pass 2. Stage 6 may link them only through a recorded relation.

2. `shared_rules/core.rule.safeguard_attachment/1` (shared rule `core.rule.safeguard_attachment`)

A contract with safeguard clauses is split off as a governance activity linked to the tool.

3. `items/core.has_transparency_notice/rules/1`

One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer.

4. `items/core.has_transparency_notice/rules/2`

not_documented: the page is silent.

## `core.has_data_classification`
<!-- item: core.has_data_classification sha256: 68084992dbde87ad50504404f47dc4e6ec31d81952f10f34b3dd443ebcc8495c -->

| Field | Value |
|---|---|
| item hash | `68084992dbde87ad50504404f47dc4e6ec31d81952f10f34b3dd443ebcc8495c` |
| family | `safeguard` |
| name | `has_data_classification` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.has_data_classification]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.has_data_classification]; ruling activity-23, all-04 (order: the draft's alternative (b))", "order": ["yes", "no", "unclear", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "has_data_classification", "map": "identity"}` |

### Instruction

Are there documented data-handling restrictions for GenAI use?

### Values

#### `yes`

yes: the page states the safeguard applies to this activity (for a governance activity: the rule requires it).

#### `no`

no: the page states it does not apply.

#### `unclear`

unclear: the page mentions the safeguard but it cannot be settled whether it applies to this activity.

### Rules

1. `shared_rules/core.rule.safeguard_attachment/0` (shared rule `core.rule.safeguard_attachment`)

A safeguard in a governance activity is not copied to deployment activities in pass 2. Stage 6 may link them only through a recorded relation.

2. `shared_rules/core.rule.safeguard_attachment/1` (shared rule `core.rule.safeguard_attachment`)

A contract with safeguard clauses is split off as a governance activity linked to the tool.

3. `items/core.has_data_classification/rules/1`

One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer.

4. `items/core.has_data_classification/rules/2`

not_documented: the page is silent.

## `core.has_risk_assessment`
<!-- item: core.has_risk_assessment sha256: 2698cd63443ceb8088c716d3b611c26273c2a560366fc7cef8dfba1f05dbdfbf -->

| Field | Value |
|---|---|
| item hash | `2698cd63443ceb8088c716d3b611c26273c2a560366fc7cef8dfba1f05dbdfbf` |
| family | `safeguard` |
| name | `has_risk_assessment` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
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
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.has_risk_assessment]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.has_risk_assessment]; ruling activity-23, all-04 (order: the draft's alternative (b))", "order": ["yes", "no", "unclear", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "has_risk_assessment", "map": "identity"}` |

### Instruction

Has a formal risk/impact assessment been documented?

### Values

#### `yes`

yes: the page states the safeguard applies to this activity (for a governance activity: the rule requires it).

#### `no`

no: the page states it does not apply.

#### `unclear`

unclear: the page mentions the safeguard but it cannot be settled whether it applies to this activity.

### Rules

1. `shared_rules/core.rule.safeguard_attachment/0` (shared rule `core.rule.safeguard_attachment`)

A safeguard in a governance activity is not copied to deployment activities in pass 2. Stage 6 may link them only through a recorded relation.

2. `shared_rules/core.rule.safeguard_attachment/1` (shared rule `core.rule.safeguard_attachment`)

A contract with safeguard clauses is split off as a governance activity linked to the tool.

3. `items/core.has_risk_assessment/rules/1`

One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer.

4. `items/core.has_risk_assessment/rules/2`

not_documented: the page is silent.

## `core.outcome_kind`
<!-- item: core.outcome_kind sha256: 75a57dacf1821fb733a64d2bbd44f2aa043845b38c9054065820009069dc1577 -->

| Field | Value |
|---|---|
| item hash | `75a57dacf1821fb733a64d2bbd44f2aa043845b38c9054065820009069dc1577` |
| family | `outcomes` |
| name | `outcome_kind` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `single` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-61` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.outcome_kind]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.outcome_kind]; ruling activity-19, all-04", "order": ["quantified", "qualitative", "none_reported", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "reported_outcomes", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[23]"}` |

### Values

#### `quantified`

states a measured or numeric result

#### `qualitative`

states a result in words only, with no measure

#### `none_reported`

states no result

### Rules

1. `items/core.outcome_kind/rules/0`

A jev `Choice` per (finding × page), over the page text with this activity's span marked, asked for outcomes and for incidents separately: `quantified` / `qualitative` / `none_reported`. It answers both whether the page reports an outcome (an incident) of this activity and of what kind; no separate existence question is asked. The outcome or incident text is extracted only when the answer is not `none_reported`. The incident item also takes the value in CX-61b.

2. `items/core.outcome_kind/rules/1`

Ask CX-61 in pass 2 over the page text with the activity span marked; the extractor then quotes support for the chosen value.

3. `items/core.outcome_kind/rules/2`

Pass-2 jev Choice on page text: does the page report an outcome (incident) of this activity: quantified / qualitative / none? The extractor extracts verbatim text only when not none; CX-60 then applies to legacy rows only.

4. `items/core.outcome_kind/rules/3`

Your outcome and incident gates are re-ruled down to quotes only; the signed item answers both whether and what kind, and the separate existence question folds into it.

## `core.incident_kind`
<!-- item: core.incident_kind sha256: 1783196e41d3163a3b7348d956bcc4ef0af9b79c400a0484d44bd11d71ced9cc -->

| Field | Value |
|---|---|
| item hash | `1783196e41d3163a3b7348d956bcc4ef0af9b79c400a0484d44bd11d71ced9cc` |
| family | `outcomes` |
| name | `incident_kind` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `single` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-61` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.incident_kind]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.incident_kind]; ruling activity-27, all-04", "order": ["quantified", "qualitative", "discontinuation_uncertain", "none_reported", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "reported_incidents", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[24]"}` |

### Values

#### `quantified`

states a measured or numeric result

#### `qualitative`

states a result in words only, with no measure

#### `none_reported`

states no result

#### `discontinuation_uncertain`

The page suggests that this activity may have been ended, cancelled or suspended, but does not confirm it.

### Rules

1. `items/core.incident_kind/rules/0`

A jev `Choice` per (finding × page), over the page text with this activity's span marked, asked for outcomes and for incidents separately: `quantified` / `qualitative` / `none_reported`. It answers both whether the page reports an outcome (an incident) of this activity and of what kind; no separate existence question is asked. The outcome or incident text is extracted only when the answer is not `none_reported`. The incident item also takes the value in CX-61b.

2. `items/core.incident_kind/rules/1`

Ask CX-61 in pass 2 over the page text with the activity span marked; the extractor then quotes support for the chosen value.

3. `items/core.incident_kind/rules/2`

Pass-2 jev Choice on page text: does the page report an outcome (incident) of this activity: quantified / qualitative / none? The extractor extracts verbatim text only when not none; CX-60 then applies to legacy rows only.

4. `items/core.incident_kind/rules/3`

Your outcome and incident gates are re-ruled down to quotes only; the signed item answers both whether and what kind, and the separate existence question folds into it.

5. `items/core.incident_kind/rules/4`

Retire flags that just mirror a column; keep 'identity unresolved' and 'stage ambiguous', and fold 'discontinuation uncertain' into the incident question as a value instead of a separate question.

6. `items/core.incident_kind/rules/5`

`discontinuation_uncertain` (incident item only)

7. `items/core.incident_kind/rules/6`

The incident question ignores stops unless a problem is reported.

## `core.reported_outcomes`
<!-- item: core.reported_outcomes sha256: 461640be1d75ba79ac2297ad85a4a36bc119cfd9d8a1bb73bb9a14248192181d -->

| Field | Value |
|---|---|
| item hash | `461640be1d75ba79ac2297ad85a4a36bc119cfd9d8a1bb73bb9a14248192181d` |
| family | `outcomes` |
| name | `reported_outcomes` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `extractor` |
| coder | `quote_step` |
| pass | `none` |
| round | `none` |
| answer_type | `list` |
| order_tie_rule | `none` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-60` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.outcome_kind", "values": ["not none_reported"]}` |
| long_page_rule | `combined_list` |
| translation_v25 | `{"column": "reported_outcomes", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[25]"}` |

### Instruction

Documented performance claims. Only record if explicitly stated. Never infer.

### Rules

1. `items/core.reported_outcomes/rules/0`

Deterministic step (no API), for rows coded before CX-01.3 only: map all "nothing found" spellings to `none_reported`. The mapping table is published with the code.

2. `items/core.reported_outcomes/rules/1`

jev Choice per activity: page reports realised outcomes / only expected or projected outcomes / usage figures only / none. Unless none, the extractor returns verbatim spans (no length limit in storage, display cap per R-043). CX-61 then runs on the spans.

## `core.reported_incidents`
<!-- item: core.reported_incidents sha256: 66b35b76fde638868351219a3e179a72358ccc6a176b581650fed4b473b10ca5 -->

| Field | Value |
|---|---|
| item hash | `66b35b76fde638868351219a3e179a72358ccc6a176b581650fed4b473b10ca5` |
| family | `outcomes` |
| name | `reported_incidents` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `extractor` |
| coder | `quote_step` |
| pass | `none` |
| round | `none` |
| answer_type | `list` |
| order_tie_rule | `none` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-60` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.incident_kind", "values": ["not none_reported"]}` |
| long_page_rule | `combined_list` |
| translation_v25 | `{"column": "reported_incidents", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[26]"}` |

### Instruction

Documented errors, failures, or controversies. Only record if explicitly stated.

### Rules

1. `items/core.reported_incidents/rules/0`

Deterministic step (no API), for rows coded before CX-01.3 only: map all "nothing found" spellings to `none_reported`. The mapping table is published with the code.

2. `items/core.reported_incidents/rules/1`

jev Choice: page reports a malfunction or error / data or privacy breach / public criticism or complaint / suspension or withdrawal / none. Unless none, the extractor returns verbatim spans.

## `core.evaluation_documented`
<!-- item: core.evaluation_documented sha256: eb98377467f2a74928e96fe901cb43eae39c10be2d8bf1297696cb1f020f222a -->

| Field | Value |
|---|---|
| item hash | `eb98377467f2a74928e96fe901cb43eae39c10be2d8bf1297696cb1f020f222a` |
| family | `evaluation` |
| name | `evaluation_documented` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `3` |
| answer_type | `single` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-30..CX-40` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"table": "applicability keyed on activity_type (r2#8)", "key": "core.activity_type", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.evaluation_documented]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "order": ["results_reported", "conducted_no_results", "required_or_planned", "unclear", "not_documented", "unknown"], "source": "table order (CX §11.1); `unknown` placed after `not_documented` per all-04 b"}` |
| translation_v25 | `new` |

### Instruction

Does this page document an evaluation of this GenAI activity?

### Values

#### `results_reported`

The page states that this activity was tested, evaluated, audited or monitored **and** reports a result (a metric, a finding or a conclusion).

#### `conducted_no_results`

The page states that an evaluation, test, audit, pilot review or monitoring took place or is in place, but reports no result.

#### `required_or_planned`

The page states that an evaluation is required (by a rule) or planned, with no evidence that it has happened. A policy finding that requires evaluation of GenAI tools takes this value.

#### `unclear`

The page makes an evaluative statement, but its subject, or whether it concerns this GenAI activity, cannot be settled. An evaluation clearly of a different tool or activity is `not_documented`, not `unclear` (CX-01.2, C4 = a).

### Rules

1. `items/core.evaluation_documented/rules/0`

A requirement to carry out a risk or impact assessment is **not** `required_or_planned`; it belongs to `has_risk_assessment` alone (consistent with CX-37).

2. `items/core.evaluation_documented/rules/1`

A clause requiring periodic review of the GenAI policy itself is `not_documented`, unless it requires testing, monitoring or evaluation of GenAI tools or their outputs; then it counts as `required_or_planned`. This includes any policy with a GenAI section (e.g. a general IT policy).

3. `items/core.evaluation_documented/rules/2`

A required pre-use review that mixes fitness-for-purpose with security or compliance checks counts as `required_or_planned`. A pure risk or impact assessment requirement stays under CX-32b.

4. `items/core.evaluation_documented/rules/3`

No negative value. A page saying no evaluation was done or planned is `not_documented`.

5. `items/core.evaluation_documented/rules/4`

A performance figure counts as `results_reported` only if the page also describes the activity behind it (a test, a pilot review, a survey, an audit, monitoring); otherwise `not_documented`.

6. `items/core.evaluation_documented/rules/5`

A risk or impact assessment counts here only if it reports testing or measured performance; otherwise it belongs to `has_risk_assessment` alone.

7. `items/core.evaluation_documented/rules/6`

A vendor's performance claim counts only if the page names the institution or an independent body as the evaluator.

8. `items/core.evaluation_documented/rules/7`

A pilot stage alone is `not_documented`. "The pilot will be evaluated" is `required_or_planned`; "the pilot evaluation found …" is `results_reported`.

9. `items/core.evaluation_documented/rules/8`

(1) An agency blog: "after a three-month trial, 78% of staff said the assistant saved time" → `results_reported`. (2) Minutes: "the pilot is being reviewed by IT" → `conducted_no_results`. (3) A guidance memo: "all GenAI tools must be tested before deployment" → `required_or_planned` on the policy finding. (4) A press release: "the chatbot has answered 40,000 questions" → `not_documented` (a usage count with no evaluation described; CX-36). (5) A vendor case study: "accuracy improved 30%" with no named evaluator → `not_documented` (CX-38).

10. `items/core.evaluation_documented/rules/9`

Delete CX-32c's policy-review clause: a periodic review of the policy document is `not_documented` unless it requires testing, monitoring or evaluation of GenAI tools or their outputs.

11. `items/core.evaluation_documented/rules/10`

CX-32: the page states that an evaluation is required (by a rule) or planned, with no evidence that it has happened. A policy that requires evaluation of GenAI tools takes this value. A clause requiring periodic review of the GenAI policy itself is NOT this value unless it requires testing, monitoring or evaluation of GenAI tools or their outputs (CX-32c). A requirement to carry out a risk or impact assessment is NOT this value (CX-32b).

12. `items/core.evaluation_documented/rules/11`

The page has no evaluation statement about this activity.

## `core.evaluation_type_pre_deployment_testing`
<!-- item: core.evaluation_type_pre_deployment_testing sha256: ea5987af915a041e5c2629de6903c29c2470f6b023517c483bda41d5ebaa612c -->

| Field | Value |
|---|---|
| item hash | `ea5987af915a041e5c2629de6903c29c2470f6b023517c483bda41d5ebaa612c` |
| family | `evaluation` |
| name | `evaluation_type_pre_deployment_testing` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `4` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-41` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Values

#### `yes`

The page documents an evaluation of this type for the activity: testing before deployment.

#### `no`

The page does not document an evaluation of this type (testing before deployment) for the activity.

### Rules

1. `items/core.evaluation_type_pre_deployment_testing/rules/0`

Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.

2. `items/core.evaluation_type_pre_deployment_testing/rules/1`

Procedural: ask (or keep) type items only if `evaluation_documented` is still positive after R-041 and R-081; otherwise store `_NA_`.

## `core.evaluation_type_pilot_evaluation`
<!-- item: core.evaluation_type_pilot_evaluation sha256: 27e0db2eb31011d4c8d4361ddd4861dc01926b00059885c572a6ff6ea8170753 -->

| Field | Value |
|---|---|
| item hash | `27e0db2eb31011d4c8d4361ddd4861dc01926b00059885c572a6ff6ea8170753` |
| family | `evaluation` |
| name | `evaluation_type_pilot_evaluation` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `4` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-41` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Values

#### `yes`

The page documents an evaluation of this type for the activity: evaluation of a pilot or trial.

#### `no`

The page does not document an evaluation of this type (evaluation of a pilot or trial) for the activity.

### Rules

1. `items/core.evaluation_type_pilot_evaluation/rules/0`

Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.

2. `items/core.evaluation_type_pilot_evaluation/rules/1`

Procedural: ask (or keep) type items only if `evaluation_documented` is still positive after R-041 and R-081; otherwise store `_NA_`.

## `core.evaluation_type_independent_audit`
<!-- item: core.evaluation_type_independent_audit sha256: 4ebf5ba2d6a3e533b6730c91c06a04879929634af735a8971a73f40f5d2cd45a -->

| Field | Value |
|---|---|
| item hash | `4ebf5ba2d6a3e533b6730c91c06a04879929634af735a8971a73f40f5d2cd45a` |
| family | `evaluation` |
| name | `evaluation_type_independent_audit` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `4` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-41` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Values

#### `yes`

The page documents an evaluation of this type for the activity: an audit or evaluation by an independent body.

#### `no`

The page does not document an evaluation of this type (an audit or evaluation by an independent body) for the activity.

### Rules

1. `items/core.evaluation_type_independent_audit/rules/0`

Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.

2. `items/core.evaluation_type_independent_audit/rules/1`

Procedural: ask (or keep) type items only if `evaluation_documented` is still positive after R-041 and R-081; otherwise store `_NA_`.

## `core.evaluation_type_ongoing_monitoring`
<!-- item: core.evaluation_type_ongoing_monitoring sha256: 3a1627cf8f0e2e710baed963c501b85f52f0224699f755eec778eac398376c7e -->

| Field | Value |
|---|---|
| item hash | `3a1627cf8f0e2e710baed963c501b85f52f0224699f755eec778eac398376c7e` |
| family | `evaluation` |
| name | `evaluation_type_ongoing_monitoring` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `4` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-41` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Values

#### `yes`

The page documents an evaluation of this type for the activity: ongoing monitoring of the tool in use.

#### `no`

The page does not document an evaluation of this type (ongoing monitoring of the tool in use) for the activity.

### Rules

1. `items/core.evaluation_type_ongoing_monitoring/rules/0`

Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.

2. `items/core.evaluation_type_ongoing_monitoring/rules/1`

Procedural: ask (or keep) type items only if `evaluation_documented` is still positive after R-041 and R-081; otherwise store `_NA_`.

## `core.evaluation_type_user_feedback`
<!-- item: core.evaluation_type_user_feedback sha256: 1e0155dd412152c3f036b7d27569ebc10b6375a64eda51b1b6942c77dec246b9 -->

| Field | Value |
|---|---|
| item hash | `1e0155dd412152c3f036b7d27569ebc10b6375a64eda51b1b6942c77dec246b9` |
| family | `evaluation` |
| name | `evaluation_type_user_feedback` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `4` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-41` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Values

#### `yes`

The page documents an evaluation of this type for the activity: user feedback or satisfaction surveys.

#### `no`

The page does not document an evaluation of this type (user feedback or satisfaction surveys) for the activity.

### Rules

1. `items/core.evaluation_type_user_feedback/rules/0`

Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.

2. `items/core.evaluation_type_user_feedback/rules/1`

Procedural: ask (or keep) type items only if `evaluation_documented` is still positive after R-041 and R-081; otherwise store `_NA_`.

## `core.evaluation_type_bias_or_safety_testing`
<!-- item: core.evaluation_type_bias_or_safety_testing sha256: 8486f5e9bc9211779b9ae13597c14dbe9b2d5680ec830fafee2a7c485e538843 -->

| Field | Value |
|---|---|
| item hash | `8486f5e9bc9211779b9ae13597c14dbe9b2d5680ec830fafee2a7c485e538843` |
| family | `evaluation` |
| name | `evaluation_type_bias_or_safety_testing` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `4` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `CX-01.3:CX-41` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `{"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Values

#### `yes`

The page documents an evaluation of this type for the activity: bias, fairness or safety testing.

#### `no`

The page does not document an evaluation of this type (bias, fairness or safety testing) for the activity.

### Rules

1. `items/core.evaluation_type_bias_or_safety_testing/rules/0`

Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.

2. `items/core.evaluation_type_bias_or_safety_testing/rules/1`

Procedural: ask (or keep) type items only if `evaluation_documented` is still positive after R-041 and R-081; otherwise store `_NA_`.

## `core.stage_as_of`
<!-- item: core.stage_as_of sha256: a31c92bf8e3ea867c88c781195963cfca2d0b31534f1edc8bbb96160a783265c -->

| Field | Value |
|---|---|
| item hash | `a31c92bf8e3ea867c88c781195963cfca2d0b31534f1edc8bbb96160a783265c` |
| family | `dates` |
| name | `stage_as_of` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `date` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.stage_as_of/rules/0`

stage_as_of = source_publication_date if supported, else the page's latest stated date for the activity, else the access date; plus `stage_as_of_basis`.

## `core.stage_as_of_basis`
<!-- item: core.stage_as_of_basis sha256: 7532ef33a9684efc68cee471ee06979e1309c64060d85e8c457c109b4302c541 -->

| Field | Value |
|---|---|
| item hash | `7532ef33a9684efc68cee471ee06979e1309c64060d85e8c457c109b4302c541` |
| family | `provenance` |
| name | `stage_as_of_basis` |
| level | `activity` |
| pipelines | `web_extract` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.stage_as_of_basis/rules/0`

stage_as_of = source_publication_date if supported, else the page's latest stated date for the activity, else the access date; plus `stage_as_of_basis`.

2. `items/core.stage_as_of_basis/rules/1`

Every 'how we know' field uses the same five values: stated, from metadata, looked up, derived, quoted by the quote step. The per-run version record also holds the codebook version, the channel tag stays on each row, and per-code coder details are stored internally and linked to that record.

## `core.permanent_pilot`
<!-- item: core.permanent_pilot sha256: c8cab1feaf94e127f78dc8fd0d4eae3b6d354dc06d01a262205662ceae3e81ce -->

| Field | Value |
|---|---|
| item hash | `c8cab1feaf94e127f78dc8fd0d4eae3b6d354dc06d01a262205662ceae3e81ce` |
| family | `activity_typing` |
| name | `permanent_pilot` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.permanent_pilot/rules/0`

Each item states its coder (classifier, mechanical, quote step or derived), and the approved plan's field list becomes a pointer to the codebook. 'Permanent pilot' becomes a derived flag, and 'vendor claim only' is read from the source being a vendor; one build task's scope changes.

## `core.vendor_claim_only`
<!-- item: core.vendor_claim_only sha256: c428206aa8650a6567087b70a01cf493a6cca65aff96ee2622269365dce66cb4 -->

| Field | Value |
|---|---|
| item hash | `c428206aa8650a6567087b70a01cf493a6cca65aff96ee2622269365dce66cb4` |
| family | `quality` |
| name | `vendor_claim_only` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.vendor_claim_only/rules/0`

Each item states its coder (classifier, mechanical, quote step or derived), and the approved plan's field list becomes a pointer to the codebook. 'Permanent pilot' becomes a derived flag, and 'vendor claim only' is read from the source being a vendor; one build task's scope changes.

## `core.unit_credit`
<!-- item: core.unit_credit sha256: 451c38d1d198e285e1100756e2ed241e89204d0549dd05763f137468182bd76a -->

| Field | Value |
|---|---|
| item hash | `451c38d1d198e285e1100756e2ed241e89204d0549dd05763f137468182bd76a` |
| family | `attribution` |
| name | `unit_credit` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `deterministic` |
| coder | `derived` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.unit_credit/rules/0`

Keep your rule and add a yes/no column marking credit received through a unit, so analyses can remove duplicates; the data dictionary explains it.

## `core.uncertainty_flags`
<!-- item: core.uncertainty_flags sha256: cf94b432c589e804010029d741897ed6df4249b20d8c56f214ce7ec4604f4fda -->

| Field | Value |
|---|---|
| item hash | `cf94b432c589e804010029d741897ed6df4249b20d8c56f214ce7ec4604f4fda` |
| family | `quality` |
| name | `uncertainty_flags` |
| level | `activity`, `row` |
| pipelines | `web_extract` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "uncertainty_flags", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[27]"}` |

### Rules

1. `items/core.uncertainty_flags/rules/0`

Compute each flag from codes (table above); add `identity_unresolved` for Stage 6 relations; drop `source_language_barrier`; `discontinued_uncertain` becomes a pass-2 jev yes/no.

2. `items/core.uncertainty_flags/rules/1`

Retire flags that just mirror a column; keep 'identity unresolved' and 'stage ambiguous', and fold 'discontinuation uncertain' into the incident question as a value instead of a separate question.

3. `items/core.uncertainty_flags/rules/2`

AI-text flags fold into the main list, the language-barrier flag is dropped everywhere, and language coverage is carried by the multilingual subproject's item.

## `core.support_entailment`
<!-- item: core.support_entailment sha256: 57ebd9eca0dfe0732fb9deb3aa4bc740a21deaf1282aca3ce92a17c2d066b839 -->

| Field | Value |
|---|---|
| item hash | `57ebd9eca0dfe0732fb9deb3aa4bc740a21deaf1282aca3ce92a17c2d066b839` |
| family | `support` |
| name | `support_entailment` |
| level | `row` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `first_in_order` |
| support_required | `False` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `internal` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Instruction

'Does this text state that <field> is <value>?'

### Values

#### `true`

The quoted text states that the field has the given value.

#### `false`

The quoted text does not state that the field has the given value. The answer's support status becomes 'downgraded: quote does not state the value'.

### Rules

1. `items/core.support_entailment/rules/0`

State = quote (plus a short window); question: 'Does this text state that <field> is <value>?' true/false; false or confidence < threshold -> downgrade `no_support`.

## `core.support_status`
<!-- item: core.support_status sha256: e14c257ac1af8625118a2011ad275638b73d412381d6d4ea5808631876d50e71 -->

| Field | Value |
|---|---|
| item hash | `e14c257ac1af8625118a2011ad275638b73d412381d6d4ea5808631876d50e71` |
| family | `support` |
| name | `support_status` |
| level | `row` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.support_status/rules/0`

Support-status values: `supported` / `downgraded_no_quote` / `downgraded_low_confidence` / `downgraded_quote_not_stating_value` / `set_by_rule`, for every value a rule fixed, including "not asked" and `_NA_` (exempt from the no-quote downgrade; record-02 a; O12) / `not_required`, for `not_documented`, `unknown`, `no` and negative page verdicts.

2. `items/core.support_status/rules/1`

`not_required`: the answer needs no supporting quote by its nature. It is given to `not_documented`, `unknown`, `no` and negative page verdicts.

3. `items/core.support_status/rules/2`

A second reason item

## `core.supporting_text`
<!-- item: core.supporting_text sha256: ab1a6071437a92a0293225daff189f3b12f0e7849e1a69a4b5f1ef6891f4569e -->

| Field | Value |
|---|---|
| item hash | `ab1a6071437a92a0293225daff189f3b12f0e7849e1a69a4b5f1ef6891f4569e` |
| family | `support` |
| name | `supporting_text` |
| level | `row` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
| linkage | `extractor` |
| coder | `quote_step` |
| pass | `none` |
| round | `none` |
| answer_type | `text` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `unknown` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `quote_source` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.supporting_text/rules/0`

For every jev code on a page or activity, the extractor (C-001; the quote step) extracts the verbatim supporting text from the page. RC-D-002 row 15 replaces "after jev has coded": the quote step never sees the answer for the field it quotes, but may see that a gate is not `none`. The quote step runs for every activity, including items the applicability table skips; those copies are kept internally, and the item is published as "not asked". A01 and CX-61 get quotes relevant to the field. The scale number is copied verbatim by the quote step and the classifier picks the unit; the publication date is coded by the quote step under the R-042 check. X35 adds an entailment check per (code, quote) with a chosen-answer probability bar.

2. `items/core.supporting_text/rules/1`

Supporting text is checked against the stored page text by fuzzy match; a quote below the match threshold counts as no supporting text.

3. `items/core.supporting_text/rules/2`

Supporting text is published with the code it supports. The API carries the full text; the website shows it up to a display cap, with a marker and access to the full text.

4. `items/core.supporting_text/rules/3`

Published supporting quotes stay verbatim, with no masking.

## `core.confidence`
<!-- item: core.confidence sha256: 537c6f63b1d27f9707737584b2f124f63ae479557815040a65e67c52d8393c16 -->

| Field | Value |
|---|---|
| item hash | `537c6f63b1d27f9707737584b2f124f63ae479557815040a65e67c52d8393c16` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "confidence", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[29]"}` |

### Rules

1. `items/core.confidence/rules/0`

Each source's confidence uses only that source's credibility and quote support. At consolidation, an activity is 'high' if one source is high or two medium sources that are not copies of each other agree; otherwise it takes the highest source value.

## `core.codebook_release`
<!-- item: core.codebook_release sha256: 70c06b42eb6445d646e96fb7738b9ae2b8caf74883db08d70e044d5c561ebe5f -->

| Field | Value |
|---|---|
| item hash | `70c06b42eb6445d646e96fb7738b9ae2b8caf74883db08d70e044d5c561ebe5f` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "contract_version", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[31]"}` |

### Rules

1. `items/core.codebook_release/rules/0`

Every published row carries the contract version that produced it. That is one version label, the codebook release, replacing `contract_version`, plus the setup pointer and `evidence_channel`; the extract and validate contract labels are recorded only in the setup record. C-007 applies to the release. v2.5 rows keep their contract version.

## `core.setup_pointer`
<!-- item: core.setup_pointer sha256: a67b942925a1dcc27697fd82b8cdd4b1db61c67122694d15f8f8aa26e8fdeca8 -->

| Field | Value |
|---|---|
| item hash | `a67b942925a1dcc27697fd82b8cdd4b1db61c67122694d15f8f8aa26e8fdeca8` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.setup_pointer/rules/0`

A manifest (contract versions, `JEV_QUESTION_SET_VERSION`, jev model, extractor model id + prompt SHA-256, chunker + estimator version, matcher + threshold, confidence threshold, codebook item hashes) keyed by `instrument_id` on every row.

2. `items/core.setup_pointer/rules/1`

Every jev answer is stored with its probability distribution, confidence, response model id and request id. Every automated coder (classifier, quote step, detector, mechanical rules) stores coder type, model, version and request id; the per-run version record holds the codebook version, and per-code coder details are internal and linked to it; the row carries the codebook version + setup pointer; the classifier record keeps the chosen-answer probability.

## `core.evidence_channel`
<!-- item: core.evidence_channel sha256: 1874109a354313ca536f067b515d7a8e258dbac12447765149f3a65d2048555a -->

| Field | Value |
|---|---|
| item hash | `1874109a354313ca536f067b515d7a8e258dbac12447765149f3a65d2048555a` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.evidence_channel/rules/0`

Channel enum (web_extract, procurement, text_detection)

## `core.coder_record`
<!-- item: core.coder_record sha256: 3ce7044e0f14e915db89ee5a6e5a1395fb47f6c884a634b32532e6e3004471ab -->

| Field | Value |
|---|---|
| item hash | `3ce7044e0f14e915db89ee5a6e5a1395fb47f6c884a634b32532e6e3004471ab` |
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
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.coder_record/rules/0`

Every jev answer is stored with its probability distribution, confidence, response model id and request id. Every automated coder (classifier, quote step, detector, mechanical rules) stores coder type, model, version and request id; the per-run version record holds the codebook version, and per-code coder details are internal and linked to it; the row carries the codebook version + setup pointer; the classifier record keeps the chosen-answer probability.

2. `items/core.coder_record/rules/1`

`coder_type`, `coder_model`, `coder_version`, `request_id` common across channels

## `core.observed_actor_role`
<!-- item: core.observed_actor_role sha256: e045ce6235185b64555efa5530f3de196f55ba70e6149f5d529720029abf5367 -->

| Field | Value |
|---|---|
| item hash | `e045ce6235185b64555efa5530f3de196f55ba70e6149f5d529720029abf5367` |
| family | `attribution` |
| name | `observed_actor_role` |
| level | `activity` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `2` |
| answer_type | `single` |
| order_tie_rule | `first_in_order` |
| support_required | `True` |
| downgrade_target | `unknown` |
| threshold | `{"metric": "chosen_answer_probability", "bar": 0.8}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown`, `_NA_` |
| input_text | `main` |
| visibility | `internal` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `{"rule": "same_part_as", "item": "core.observed_actor_relationship", "fallback": "highest_probability"}` |
| translation_v25 | `new` |

### Values

#### `institutional_actor`

The actor seen on the page carries out or adopts the activity as an institution.

#### `issuer`

The actor issued the policy, rule, guidance or document.

#### `participant`

The actor takes part in an activity that someone else runs.

#### `external_speaker`

The actor speaks or presents about GenAI, for example at an event, without carrying out the activity.

#### `service_provider`

The actor supplies the tool or service, as a vendor, contractor or developer.

#### `event_host`

The actor hosts or organises an event about GenAI.

### Rules

1. `items/core.observed_actor_role/rules/0`

Code it as before; not published.

2. `items/core.observed_actor_role/rules/1`

Only `institutional_actor`, `issuer` and `participant` count as the actor taking part in the activity; `external_speaker`, `service_provider` and `event_host` do not.

## `core.date_upper_bound`
<!-- item: core.date_upper_bound sha256: b813dbae96dda535658b0db6b8cd26729e56117716d41bf571961e7dfef019b4 -->

| Field | Value |
|---|---|
| item hash | `b813dbae96dda535658b0db6b8cd26729e56117716d41bf571961e7dfef019b4` |
| family | `provenance` |
| name | `date_upper_bound` |
| level | `source`, `activity` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
| linkage | `deterministic` |
| coder | `mechanical` |
| pass | `none` |
| round | `none` |
| answer_type | `yes_no` |
| order_tie_rule | `none` |
| support_required | `False` |
| downgrade_target | `none` |
| threshold | `none` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `slot` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.date_upper_bound/rules/0`

add a yes/no note "this date is an upper bound".

## `core.support_rule_name`
<!-- item: core.support_rule_name sha256: 65a9ae6a920590ee4e488ab6a40bb49111187bea0d8e8401bcdef0d3de70d899 -->

| Field | Value |
|---|---|
| item hash | `65a9ae6a920590ee4e488ab6a40bb49111187bea0d8e8401bcdef0d3de70d899` |
| family | `support` |
| name | `support_rule_name` |
| level | `row` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
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
| status | `slot` |
| gate | `{"item": "core.support_status", "values": ["set_by_rule"], "gated_out_value": "empty (record-01 a wording)"}` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.support_rule_name/rules/0`

Add a rule-name item, empty unless the status is "set by rule".

## `core.support_status_second_reason`
<!-- item: core.support_status_second_reason sha256: e782c3663184e51a96ff21bcf305c9fa647a453faa15ca95529c1f66072fa65a -->

| Field | Value |
|---|---|
| item hash | `e782c3663184e51a96ff21bcf305c9fa647a453faa15ca95529c1f66072fa65a` |
| family | `support` |
| name | `support_status_second_reason` |
| level | `row` |
| pipelines | `web_extract`, `procurement`, `ai_text` |
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
| status | `slot` |
| gate | `{"rule": "empty unless two reasons hold (final-open F10)"}` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Values

#### `downgraded_no_quote`

The answer also failed because it has no supporting quote.

#### `downgraded_low_confidence`

The answer also failed because the classifier's certainty was below the 0.8 bar.

#### `downgraded_quote_not_stating_value`

The answer also failed because its quote does not state the value.

### Rules

1. `items/core.support_status_second_reason/rules/0`

A second reason item

2. `items/core.support_status_second_reason/rules/1`

Values: downgraded_no_quote, downgraded_low_confidence, downgraded_quote_not_stating_value. The main status takes the first failed check in check order (quote, then the 0.8 bar); the second item takes the other; empty when only one reason holds.

3. `items/core.support_status_second_reason/rules/2`

With this check order, only `downgraded_low_confidence` can be a second reason, because a failed quote check is always the main reason. The other two codes stay on the list so that it matches the support-status list.
