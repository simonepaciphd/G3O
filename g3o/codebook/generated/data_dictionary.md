<!-- GENERATED FILE - do not edit. Built from codebook/codebook.yaml by g3o.codebook.generators.data_dictionary. -->
<!-- codebook release: 2.7 | codebook sha256: 64a8a2d808a3eb6c4583d7c65d1a9068e557785fdb17ed11e7ffd99e4ebe7dc5 -->

# G3O codebook data dictionary

Codebook release `2.7`, sha256 `64a8a2d808a3eb6c4583d7c65d1a9068e557785fdb17ed11e7ffd99e4ebe7dc5`. 109 items.

## `core.page_verdict`
<!-- item: core.page_verdict sha256: f3224d00890eba351b1b5b696c2d6eacdf7f3863c010e0a99de35216d1fa0bfe -->

| Field | Value |
|---|---|
| item hash | `f3224d00890eba351b1b5b696c2d6eacdf7f3863c010e0a99de35216d1fa0bfe` |
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
| missing_tokens | `none` |
| input_text | `main` |
| visibility | `public` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `{"rule": "priority_order", "order": ["confirms_activity", "ambiguous_attribution", "ambiguous_genai", "other_body", "event_only", "background_only", "confirms_absence", "no_genai", "not_assessable"]}` |
| translation_v25 | `{"column": "genai_evidence", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[0]"}` |

### Instruction

Code this PAGE for the named institution only, using only what the page says. Does it document an AI activity at this institution? If several values fit, take the first in this order.

### Entailment label

AI content

### Values

#### `confirms_activity`

The page documents a specific AI activity AT THIS institution: its own AI tool, pilot, policy or guidance on AI (whether it governs the institution's own staff or others it regulates), procurement, deployment, or AI training that the institution directs at public-sector staff (its own staff or the staff of bodies it serves). The page itself must call the tool or activity AI, artificial intelligence or machine learning, or name an AI product or model, and tie it to this institution, not only to a national programme or another body. Generative AI counts (LLMs, ChatGPT, Copilot, Gemini, AI chatbots, AI-generated content), and so does any other tool the page calls AI or machine learning (for example AI analytics or prediction, AI translation or transcription, AI image or video recognition). Content that the institution publishes on its own page and credits as made with AI (for example an image credit naming an AI tool, or a text marked as written with AI) is the institution's own use of an AI tool and counts, unless the page attributes that content to another body. The activity must be carried out or adopted by the named institution itself. Exclude activity by a parent, higher-level or neighbouring body (e.g. a district, county, regency, region, consortium or city department when the named institution is a village, ward or sub-unit), by a similarly named organisation or company, and pages by vendors that only use the place name. A vendor or other third-party page counts when it names this institution as the client or user of the tool. 'Smart' systems, automation, analytics, prediction, transcription, translation or recognition that the page does not call AI or machine learning do not count.

Entailment label: an AI activity at this institution

#### `ambiguous_genai`

The page mentions AI at this institution, but no specific activity can be made out (e.g. an agenda item or a passing reference to 'AI' that describes no tool, policy, purchase, deployment or training).

Entailment label: a mention of AI at this institution with no specific activity

#### `ambiguous_attribution`

The page mentions AI, but it cannot be settled whether THIS institution is involved (e.g. a country-wide or regional AI initiative without confirmation that this institution takes part, or a page about a similarly named body).

Entailment label: AI that may not involve this institution

#### `other_body`

The page documents an AI activity, but it clearly belongs to a different body, not the named institution: a parent, higher-level or neighbouring body (e.g. a district, county, regency, region, consortium or city department when the named institution is a village, ward or sub-unit), a similarly named organisation or company, or a vendor or marketing page that only uses the place name.

Entailment label: an AI activity of another body

#### `event_only`

The only AI content is a public-facing event, workshop, seminar, showcase or educational programme, with no documented adoption, procurement, deployment, governance or staff training by the institution itself (not a qualifying activity). Training that the institution directs at public-sector staff is not public-facing, whatever its format.

Entailment label: only a public AI event or educational programme

#### `background_only`

The page gives only general context (national AI strategy, vendor overview, news about AI in general) and documents no activity at this institution.

Entailment label: only general background on AI

#### `confirms_absence`

The page states that this institution has no AI activity, for example that it does not use AI tools. Different from no_genai, where the page simply has no relevant content.

Entailment label: a statement that this institution has no AI activity

#### `no_genai`

The page contains no AI content relevant to this institution.

Entailment label: nothing on AI at this institution

#### `not_assessable`

`not_assessable`, set mechanically when a page was not reviewed, never a classifier answer, not blocking institution `no`, and left out of the base for institution-level rates

Entailment label: not reviewed

### Rules

1. `items/core.page_verdict/rules/0`

`not_assessable` is not one of the answers: it is set when a page was not reviewed.

2. `shared_rules/core.rule.genai_boundary/0` (shared rule `core.rule.genai_boundary`)

A tool the page calls an "AI chatbot" or "AI assistant" counts as generative AI, even where a rule-based chatbot would otherwise be excluded.

3. `shared_rules/core.rule.genai_boundary/1` (shared rule `core.rule.genai_boundary`)

Translation counts as an AI activity when the page calls it AI or machine learning. It counts as generative AI only when the page ties it to a named generative product or says a language model produces it.

4. `shared_rules/core.rule.ws10_event/0` (shared rule `core.rule.ws10_event`)

A public-facing AI event or educational programme is not a qualifying activity; an event page can support a separate record only when it documents the institution's own adoption, procurement, deployment, governance or staff training.

5. `shared_rules/core.rule.attribution_grain/0` (shared rule `core.rule.attribution_grain`)

An activity carried out by an organisational unit of the named institution (department, office, service) counts for the named institution. When the named institution is a government (national, state, regional or local), its ministries and departments are such units. An activity of its parent, a sibling, or a separate court, board or authority does not, unless the page says the named institution takes part.

6. `shared_rules/core.rule.attribution_grain/1` (shared rule `core.rule.attribution_grain`)

A joint activity counts when the page names this institution as a participant.

### long_page_rule text

`items/core.page_verdict/long_page_rule/tiers`

All supported verdicts in the signed order first, then failed verdicts in the same order.

## `core.disclosure_form`
<!-- item: core.disclosure_form sha256: 4c7908f12b580b3e4e8a7be9d770ead29af77e02f08681fc291c854d70394907 -->

| Field | Value |
|---|---|
| item hash | `4c7908f12b580b3e4e8a7be9d770ead29af77e02f08681fc291c854d70394907` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `first_section` |
| translation_v25 | `new` |

### Instruction

What kind of document is this page?

### Entailment label

kind of document

### Values

#### `register_cross_institution`

The page is, or is one entry in, a structured list of AI or algorithmic systems kept by a government body, with several entries in a common format (inventory, register, catalogue, algorithmic transparency record in a standard template), **and the list covers more than one institution** (a national or sectoral register, a standard-template record series across agencies).

Entailment label: an entry in a register that covers several institutions

#### `register_single_institution`

As `register_cross_institution`, but the list covers **one institution only** (e.g. a city's own table of its AI tools).

Entailment label: an entry in one institution's own register

#### `mandated_report`

The page is a document produced to meet a reporting obligation that concerns reporting on AI, algorithms or digital systems, such as a statutory annual-report section or a compliance or transparency report under a named rule.

Entailment label: a report required by a rule on AI reporting

#### `formal_record`

An official one-off document of record from a government body: adopted policy or guidance, legislation, council or board minutes or resolutions, budget documents, procurement notice or award, audit or inspection report, **response to a freedom-of-information request**.

Entailment label: an official document of record

#### `informal_official`

A government body's own communication with no reporting obligation and no standard format: press release, news item, blog, social post, speech, event page, service or FAQ page.

Entailment label: an informal communication from a government body

#### `third_party`

Not published by a government body: news, vendor, academic, NGO or policy organization. A register entry quoted in a news article is `third_party` (code the page, not what it quotes).

Entailment label: a page not published by a government body

### Rules

1. `items/core.disclosure_form/rules/0`

Any government-kept multi-entry list in a common format counts as a register, including one institution's own list; single-institution and cross-institution registers are separate values. `disclosure_scope` still codes whole-of-government vs multi-institution for cross-institution registers; `register_single_institution` must carry `disclosure_scope` = `single_institution` (QC check).

2. `items/core.disclosure_form/rules/1`

The obligation must be named on the page, except that it may be inferred from the document's genre **when the document's title names AI or algorithmic reporting**. Otherwise a statutory annual report or a compliance report under a rule not about AI is `formal_record`.

3. `items/core.disclosure_form/rules/2`

(1) A city's entry in a national algorithm register describing its chatbot → `register_cross_institution`. (2) A ministry annual-report section headed with the regulation that requires AI-use reporting → `mandated_report`. (3) Council minutes approving a Copilot licence → `formal_record`. (4) A mayor's press release launching a chatbot → `informal_official`. (5) A trade-press article about that chatbot → `third_party`. (6) A city web page that lists its five AI tools in a table it made itself → `register_single_institution`.

4. `items/core.disclosure_form/rules/3`

A document produced to meet a reporting obligation that concerns reporting on AI, algorithms or digital systems (statutory annual-report section, compliance or transparency report under a rule). The obligation must be named on the page, except that it may be inferred from the document's genre when the document's title names AI or algorithmic reporting. Otherwise a statutory annual report or a compliance report under a rule not about AI is formal_record.

5. `items/core.disclosure_form/rules/4`

The page's kind cannot be determined from its text (e.g. an archived fragment with no header).

## `core.disclosure_scope`
<!-- item: core.disclosure_scope sha256: bbf20d49f25291065f7e23d8da177e661d18017fb41dcfb7ec2ebcc07a75fe9c -->

| Field | Value |
|---|---|
| item hash | `bbf20d49f25291065f7e23d8da177e661d18017fb41dcfb7ec2ebcc07a75fe9c` |
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
| status | `signed` |
| gate | `{"item": "core.disclosure_form", "values": ["register_cross_institution", "register_single_institution", "mandated_report"], "source": "X02"}` |
| long_page_rule | `first_section` |
| translation_v25 | `new` |

### Instruction

How many institutions does the listing or document this page belongs to cover?

### Entailment label

coverage of the listing or document

### Values

#### `whole_of_government`

The listing or document the page belongs to covers institutions across the government (all central agencies, or all units of a level).

Entailment label: the whole of government

#### `multi_institution`

It covers several institutions, but not government-wide (a sector, a region, a group of agencies).

Entailment label: several institutions

#### `single_institution`

It covers one institution only.

Entailment label: one institution

### Rules

1. `items/core.disclosure_scope/rules/0`

Yes, as below.

2. `items/core.disclosure_scope/rules/1`

Pages whose `disclosure_form` is `register_cross_institution`, `register_single_institution` or `mandated_report`. On other pages the field is not asked and stores the reserved "not asked" label.

3. `items/core.disclosure_scope/rules/2`

Coverage cannot be determined from the page.

## `core.page_complete`
<!-- item: core.page_complete sha256: 113384334a8758749a57c8b6e25c7f77680c397198b7c4a26d4e40b997c91f5e -->

| Field | Value |
|---|---|
| item hash | `113384334a8758749a57c8b6e25c7f77680c397198b7c4a26d4e40b997c91f5e` |
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
| status | `signed` |
| gate | `{"item": "core.page_verdict", "values": ["confirms_activity", "ambiguous_genai", "ambiguous_attribution", "other_body", "event_only"]}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Instruction

'Does the page refer the reader to another page or document for more information about an AI activity it mentions?'

### Entailment label

referral elsewhere for more on an AI activity

### Values

#### `yes`

The page refers the reader to another page or document for more information about an AI activity it mentions, so the page is incomplete (see the note on the name).

Entailment label: given

#### `no`

The page does not refer the reader elsewhere for more information about any AI activity it mentions.

Entailment label: not given

### Rules

1. `items/core.page_complete/rules/0`

The first pass also records whether the page holds all available information about every activity it mentions, or links to further pages with information about any of them.

2. `items/core.page_complete/rules/1`

Note: `yes` means incomplete (the page refers the reader onward); the name `page_complete` reads the other way.

## `core.source_type`
<!-- item: core.source_type sha256: 5d2e196e4b10755e018d1d822130b9ce51cd0f21f01b856aae21f6d90610ae3a -->

| Field | Value |
|---|---|
| item hash | `5d2e196e4b10755e018d1d822130b9ce51cd0f21f01b856aae21f6d90610ae3a` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `{"rule": "first_section", "source": "combining-rules.json items[core.source_type]; ruling source-01, all-06"}` |
| translation_v25 | `{"column": "source_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[1]"}` |

### Instruction

What kind of source is this page?

### Entailment label

kind of source

### Values

#### `news_major`

Major national/international news outlet (Reuters, BBC, NYT, Le Monde, NHK, etc.)

Entailment label: a major news outlet

#### `news_trade`

Technology or government trade press (GovTech, FedScoop, PublicTechnology, etc.)

Entailment label: technology or government trade press

#### `vendor`

Vendor website, case study, blog post, or press release

Entailment label: a vendor's page

#### `academic`

Peer-reviewed paper, working paper, university report

Entailment label: academic work

#### `policy_org`

Think tank, intergovernmental organisation or other policy organisation (OECD, World Bank, ITU, Brookings, etc.); not a government body's own page.

Entailment label: a think tank or policy organisation

#### `social_media`

Official social media accounts (Twitter/X, LinkedIn from institutional accounts)

Entailment label: an official social media account

#### `procurement_tender`

Tender notice, RFP, contract award, vendor selection document

Entailment label: a tender, contract award or vendor selection document

#### `other`

None of the above, including a government body's own page.

Entailment label: another kind of source, including a government body's own page

### Rules

1. `items/core.source_type/rules/0`

Whether the page is official is taken from its web domain, and whether it is an archive copy from its address; pages typed that way are not asked. This question sorts the other pages by kind of source.

2. `items/core.source_type/rules/1`

The same question is used in every pipeline where it applies.

3. `items/core.source_type/rules/2`

not_documented: the page is silent.

## `core.content_contact_named`
<!-- item: core.content_contact_named sha256: c14e3b5271cb6b4e8df73f4dcb77100ec06c3adc4c04a5ebe592f12bbdf28c8f -->

| Field | Value |
|---|---|
| item hash | `c14e3b5271cb6b4e8df73f4dcb77100ec06c3adc4c04a5ebe592f12bbdf28c8f` |
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
| status | `signed` |
| gate | `{"item": "core.page_verdict", "values": ["confirms_activity", "ambiguous_genai", "ambiguous_attribution", "other_body", "event_only"], "gated_out_value": "no", "source": "final-open F07 (PI 2026-10-30 \"all accepted\")"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Instruction

Does the page name a person, office or unit as responsible for an AI activity it mentions, or for questions about it?

### Entailment label

named person, office or unit responsible for an AI activity

### Values

#### `yes`

The page gives a named person, office or unit as responsible for the activity or for questions about it; a named official with no contact details counts.

Entailment label: given

#### `no`

The page names no person, office or unit as responsible for the activity or for questions about it. Pages whose verdict shows no AI also take this value.

Entailment label: not given

### Rules

1. `items/core.content_contact_named/rules/0`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes: `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any AI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five AI-bearing values; on other pages they are `no`.

## `core.content_contact_details`
<!-- item: core.content_contact_details sha256: d28c7a2aee5b9a1370e7049188e8f2f95512a04bb7d0abc40e442c2d0e5b7f53 -->

| Field | Value |
|---|---|
| item hash | `d28c7a2aee5b9a1370e7049188e8f2f95512a04bb7d0abc40e442c2d0e5b7f53` |
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
| status | `signed` |
| gate | `{"item": "core.page_verdict", "values": ["confirms_activity", "ambiguous_genai", "ambiguous_attribution", "other_body", "event_only"], "gated_out_value": "no", "source": "final-open F07 (PI 2026-10-30 \"all accepted\")"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Instruction

Does the page give any contact details anywhere on it, such as an email address, phone number, postal address or contact form?

### Entailment label

contact details

### Values

#### `yes`

The page gives contact details anywhere on it: an email address, phone number, postal address or contact form, including press or vendor contacts and site footers.

Entailment label: given

#### `no`

No contact details appear anywhere on the page, including its header and footer. Pages whose verdict shows no AI also take this value.

Entailment label: not given

### Rules

1. `items/core.content_contact_details/rules/0`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes: `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any AI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five AI-bearing values; on other pages they are `no`.

## `core.content_contact`
<!-- item: core.content_contact sha256: baa275cc015ab1e206c1f64085e88e2ba12272a88b973f8766d52215e8c0784a -->

| Field | Value |
|---|---|
| item hash | `baa275cc015ab1e206c1f64085e88e2ba12272a88b973f8766d52215e8c0784a` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_contact/rules/0`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes: `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any AI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five AI-bearing values; on other pages they are `no`.

## `core.content_contact_emails`
<!-- item: core.content_contact_emails sha256: ed70a76875d9dfc801610a334e226550b3304a9d3f11b88dd7a0811aab76e265 -->

| Field | Value |
|---|---|
| item hash | `ed70a76875d9dfc801610a334e226550b3304a9d3f11b88dd7a0811aab76e265` |
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
| status | `signed` |
| gate | `{"item": "core.content_contact", "values": ["yes"]}` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_contact_emails/rules/0`

When `content_contact` = yes, extract the contact with a deterministic `@` search over the stored main page text, the stored header and footer text and the page's e-mail links (e-mail regex in `pilot/contact.py`, `EMAIL_RE`) and store the list beside the code (`content_contact_emails`), in full and internally only; only the domain part of each address and a count are published. No API call. Not yet in the installed instrument; owed to the back-code engineering card

2. `items/core.content_contact_emails/rules/1`

Published supporting quotes stay verbatim, with no masking. Contact e-mails are stored in full internally, and only the domain and a count are published.

3. `items/core.content_contact_emails/rules/2`

When `content_contact` = yes and the search finds no address, the value is `not_documented`.

## `core.content_purpose`
<!-- item: core.content_purpose sha256: 081399c1e5329f2425e24ccbaec6ec3df5503f449e3c51699f28e23a9de257dc -->

| Field | Value |
|---|---|
| item hash | `081399c1e5329f2425e24ccbaec6ec3df5503f449e3c51699f28e23a9de257dc` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_purpose/rules/0`

Included: the page description items, each `yes` / `no` (yes = stated on the page). For the items marked as derived, `yes` and `no` are derived from the activity codes as stated, with no question.

2. `items/core.content_purpose/rules/1`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes: `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any AI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five AI-bearing values; on other pages they are `no`.

3. `items/core.content_purpose/rules/2`

A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question.

4. `items/core.content_purpose/rules/3`

purpose: the activity's function items

## `core.content_tool_or_model`
<!-- item: core.content_tool_or_model sha256: 5bc83e76db256532a9abed9ed6e20cd4bbe8ff4a203a37963840b45748bb829d -->

| Field | Value |
|---|---|
| item hash | `5bc83e76db256532a9abed9ed6e20cd4bbe8ff4a203a37963840b45748bb829d` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_tool_or_model/rules/0`

Included: the page description items, each `yes` / `no` (yes = stated on the page). For the items marked as derived, `yes` and `no` are derived from the activity codes as stated, with no question.

2. `items/core.content_tool_or_model/rules/1`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes: `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any AI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five AI-bearing values; on other pages they are `no`.

3. `items/core.content_tool_or_model/rules/2`

A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question.

4. `items/core.content_tool_or_model/rules/3`

tool or model: tool or model name

## `core.content_vendor`
<!-- item: core.content_vendor sha256: 24632fd60cb1d9587dd65fe8e2e922893981d4eafa46035a8f4babd41b2d1d36 -->

| Field | Value |
|---|---|
| item hash | `24632fd60cb1d9587dd65fe8e2e922893981d4eafa46035a8f4babd41b2d1d36` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_vendor/rules/0`

Included: the page description items, each `yes` / `no` (yes = stated on the page). For the items marked as derived, `yes` and `no` are derived from the activity codes as stated, with no question.

2. `items/core.content_vendor/rules/1`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes: `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any AI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five AI-bearing values; on other pages they are `no`.

3. `items/core.content_vendor/rules/2`

A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question.

4. `items/core.content_vendor/rules/3`

vendor: model developer, stated or looked up, or contracting party

## `core.content_data`
<!-- item: core.content_data sha256: 7c5141d851e5c3912b9b926a4ab4e5d89d8f8df3e931531ef095f47cd28b3434 -->

| Field | Value |
|---|---|
| item hash | `7c5141d851e5c3912b9b926a4ab4e5d89d8f8df3e931531ef095f47cd28b3434` |
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
| status | `signed` |
| gate | `{"item": "core.page_verdict", "values": ["confirms_activity", "ambiguous_genai", "ambiguous_attribution", "other_body", "event_only"], "gated_out_value": "no", "source": "page-09 c"}` |
| long_page_rule | `{"rule": "any_yes", "order": ["yes", "no", "not_documented", "unknown"]}` |
| translation_v25 | `new` |

### Instruction

Code the source PAGE. Does the page state this about any AI activity on the page: the data inputs or data handled are described? yes = stated on the page.

### Entailment label

description of the data an AI activity uses

### Values

#### `yes`

stated on the page

Entailment label: given

#### `no`

not stated on the page

Entailment label: not given

### Rules

1. `items/core.content_data/rules/0`

Included: the page description items, each `yes` / `no` (yes = stated on the page). For the items marked as derived, `yes` and `no` are derived from the activity codes as stated, with no question.

2. `items/core.content_data/rules/1`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes: `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any AI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five AI-bearing values; on other pages they are `no`.

3. `items/core.content_data/rules/2`

One page question, asked on AI pages.

4. `items/core.content_data/rules/3`

Description items and the data item are also "no" where the verdict shows no AI.

## `core.content_users`
<!-- item: core.content_users sha256: 6e9f2d6c36a680942780706dccd8a1225f64ffe197a81eb335d629d7047ffc5e -->

| Field | Value |
|---|---|
| item hash | `6e9f2d6c36a680942780706dccd8a1225f64ffe197a81eb335d629d7047ffc5e` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_users/rules/0`

Included: the page description items, each `yes` / `no` (yes = stated on the page). For the items marked as derived, `yes` and `no` are derived from the activity codes as stated, with no question.

2. `items/core.content_users/rules/1`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes: `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any AI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five AI-bearing values; on other pages they are `no`.

3. `items/core.content_users/rules/2`

A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question.

4. `items/core.content_users/rules/3`

users: `target_users` or `governed_population`

## `core.content_status_date`
<!-- item: core.content_status_date sha256: ddade1c7e26bf62a5c9ed042a695654489de405834c403320f215cb72f713ed7 -->

| Field | Value |
|---|---|
| item hash | `ddade1c7e26bf62a5c9ed042a695654489de405834c403320f215cb72f713ed7` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_status_date/rules/0`

Included: the page description items, each `yes` / `no` (yes = stated on the page). For the items marked as derived, `yes` and `no` are derived from the activity codes as stated, with no question.

2. `items/core.content_status_date/rules/1`

Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes: `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any AI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five AI-bearing values; on other pages they are `no`.

3. `items/core.content_status_date/rules/2`

A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question.

4. `items/core.content_status_date/rules/3`

status or date: `adoption_stage` or a year field

## `core.content_human_oversight`
<!-- item: core.content_human_oversight sha256: ecabd6ecbb5ebd89a404faa7aa1053d51895cd09b1feaa6b9333dbd2671f0d73 -->

| Field | Value |
|---|---|
| item hash | `ecabd6ecbb5ebd89a404faa7aa1053d51895cd09b1feaa6b9333dbd2671f0d73` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_human_oversight/rules/0`

Safeguard items included, as Kaser does: `content_human_oversight`, `content_risk_assessment`, `content_user_notification`. They are not asked on the page. Each is the page-level member of one safeguard family tagged by level, derived from that safeguard's shared four-answer question asked once per activity (`has_human_oversight`, `has_risk_assessment`, `has_transparency_notice`): `yes` if any activity on the page is `yes`, otherwise `no`. **`content_user_notification` = yes only if the page describes a notice or label telling users they are interacting with AI or that content is AI-generated**; a page announcing that the institution uses AI is not by itself a notice (CX-01.1, W1 = a). The shared activity question uses this definition. The overlap with governance G1, G3, G4 is reported under R-070.

2. `items/core.content_human_oversight/rules/1`

One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer.

3. `items/core.content_human_oversight/rules/2`

`yes` if any activity on the page is `yes`, otherwise `no`.

## `core.content_risk_assessment`
<!-- item: core.content_risk_assessment sha256: 3dd5d635c172e6b6fe2825c83638d3cd1b89608a839148cb04e27d04e5ce79d4 -->

| Field | Value |
|---|---|
| item hash | `3dd5d635c172e6b6fe2825c83638d3cd1b89608a839148cb04e27d04e5ce79d4` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_risk_assessment/rules/0`

Safeguard items included, as Kaser does: `content_human_oversight`, `content_risk_assessment`, `content_user_notification`. They are not asked on the page. Each is the page-level member of one safeguard family tagged by level, derived from that safeguard's shared four-answer question asked once per activity (`has_human_oversight`, `has_risk_assessment`, `has_transparency_notice`): `yes` if any activity on the page is `yes`, otherwise `no`. **`content_user_notification` = yes only if the page describes a notice or label telling users they are interacting with AI or that content is AI-generated**; a page announcing that the institution uses AI is not by itself a notice (CX-01.1, W1 = a). The shared activity question uses this definition. The overlap with governance G1, G3, G4 is reported under R-070.

2. `items/core.content_risk_assessment/rules/1`

One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer.

3. `items/core.content_risk_assessment/rules/2`

`yes` if any activity on the page is `yes`, otherwise `no`.

## `core.content_user_notification`
<!-- item: core.content_user_notification sha256: 6514048ff7a43362bc01c8ebe6cb247cb61b44a77faa1c603aaa5fb89bf506db -->

| Field | Value |
|---|---|
| item hash | `6514048ff7a43362bc01c8ebe6cb247cb61b44a77faa1c603aaa5fb89bf506db` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.content_user_notification/rules/0`

Safeguard items included, as Kaser does: `content_human_oversight`, `content_risk_assessment`, `content_user_notification`. They are not asked on the page. Each is the page-level member of one safeguard family tagged by level, derived from that safeguard's shared four-answer question asked once per activity (`has_human_oversight`, `has_risk_assessment`, `has_transparency_notice`): `yes` if any activity on the page is `yes`, otherwise `no`. **`content_user_notification` = yes only if the page describes a notice or label telling users they are interacting with AI or that content is AI-generated**; a page announcing that the institution uses AI is not by itself a notice (CX-01.1, W1 = a). The shared activity question uses this definition. The overlap with governance G1, G3, G4 is reported under R-070.

2. `items/core.content_user_notification/rules/1`

One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer.

3. `items/core.content_user_notification/rules/2`

`yes` if any activity on the page is `yes`, otherwise `no`.

## `core.source_url`
<!-- item: core.source_url sha256: 6e9f3ffb20c3e1e4ebc08f74fb499162e3830cd1306adae0e373a53c90133e0e -->

| Field | Value |
|---|---|
| item hash | `6e9f3ffb20c3e1e4ebc08f74fb499162e3830cd1306adae0e373a53c90133e0e` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "source_url", "map": "identity"}` |

### Rules

1. `items/core.source_url/rules/0`

The URL of the supplied page, verbatim from the input. **Never fabricate or alter.**

2. `items/core.source_url/rules/1`

Take `source_title` from RenderedPage.title (fallback: first heading); never from a model. The first heading is looked for in the main content of the page first (its first h1, else its first h2 to h6) and only then in the whole page (again the first h1, else the first h2 to h6). Headings inside navigation, sidebars, footers, forms, embedded frames, graphics and script or style blocks are left out, and so is any heading over 300 characters. For a PDF it is the first non-empty line of the extracted text of 300 characters or fewer; when the first three non-empty lines are all longer, the PDF has no heading. This applies to newly scraped PDFs only. Where no heading was looked for (a file type without one, a failed render, or a record stored before this rule), the fallback is not measured; that is different from a page that was measured and has no heading.

## `core.source_title`
<!-- item: core.source_title sha256: bffa6f00a89d353ca5b5d4c1044230cb13237862601756f1453566b7b8a45f92 -->

| Field | Value |
|---|---|
| item hash | `bffa6f00a89d353ca5b5d4c1044230cb13237862601756f1453566b7b8a45f92` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "source_title", "map": "identity", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[2]"}` |

### Rules

1. `items/core.source_title/rules/0`

Take `source_title` from RenderedPage.title (fallback: first heading); never from a model. The first heading is looked for in the main content of the page first (its first h1, else its first h2 to h6) and only then in the whole page (again the first h1, else the first h2 to h6). Headings inside navigation, sidebars, footers, forms, embedded frames, graphics and script or style blocks are left out, and so is any heading over 300 characters. For a PDF it is the first non-empty line of the extracted text of 300 characters or fewer; when the first three non-empty lines are all longer, the PDF has no heading. This applies to newly scraped PDFs only. Where no heading was looked for (a file type without one, a failed render, or a record stored before this rule), the fallback is not measured; that is different from a page that was measured and has no heading.

## `core.source_access_date`
<!-- item: core.source_access_date sha256: 6dedbfa5c479055d2507e57e5cc291a4b29108ac441b3a5aab26d54fc72feae3 -->

| Field | Value |
|---|---|
| item hash | `6dedbfa5c479055d2507e57e5cc291a4b29108ac441b3a5aab26d54fc72feae3` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "source_access_date", "map": "identity"}` |

### Rules

1. `items/core.source_access_date/rules/0`

Date the supplied page was retrieved (provided in the input metadata as the scrape date).

2. `items/core.source_access_date/rules/1`

Take `source_title` from RenderedPage.title (fallback: first heading); never from a model. The first heading is looked for in the main content of the page first (its first h1, else its first h2 to h6) and only then in the whole page (again the first h1, else the first h2 to h6). Headings inside navigation, sidebars, footers, forms, embedded frames, graphics and script or style blocks are left out, and so is any heading over 300 characters. For a PDF it is the first non-empty line of the extracted text of 300 characters or fewer; when the first three non-empty lines are all longer, the PDF has no heading. This applies to newly scraped PDFs only. Where no heading was looked for (a file type without one, a failed render, or a record stored before this rule), the fallback is not measured; that is different from a page that was measured and has no heading.

## `core.source_language`
<!-- item: core.source_language sha256: 11736d1618fb6297a36945c4cd82b305ccfe9de6d5da43ba421d1bb28c98628a -->

| Field | Value |
|---|---|
| item hash | `11736d1618fb6297a36945c4cd82b305ccfe9de6d5da43ba421d1bb28c98628a` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "source_language", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[3]"}` |

### Rules

1. `items/core.source_language/rules/0`

Pinned local language-ID library on stored text; same tag grammar as `institution_search_languages`; `mul` when no language exceeds a set share.

## `core.source_on_official_domain`
<!-- item: core.source_on_official_domain sha256: 232b102bdb49835791ea8db3e793255ae7b7f0b51374326ad5d41f3c0095e7e7 -->

| Field | Value |
|---|---|
| item hash | `232b102bdb49835791ea8db3e793255ae7b7f0b51374326ad5d41f3c0095e7e7` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.source_on_official_domain/rules/0`

`own_official` / `other_official` / `not_official` from URL host vs the master official-site overlay.

## `core.syndication_group`
<!-- item: core.syndication_group sha256: 1e8ac31aa635119028239a474d8716741d56b9d148ff432c8bfbe248c471d1e6 -->

| Field | Value |
|---|---|
| item hash | `1e8ac31aa635119028239a474d8716741d56b9d148ff432c8bfbe248c471d1e6` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.syndication_group/rules/0`

Deterministic near-duplicate hash (e.g. shingled MinHash on normalised text) per page; `syndication_group` id; QC flag when codes differ within a group.

## `core.page_review_state`
<!-- item: core.page_review_state sha256: 9b238e3bb7ee2e748e4b62bedb882fcb43cb0f7340f1634b8241e2fce26e77b6 -->

| Field | Value |
|---|---|
| item hash | `9b238e3bb7ee2e748e4b62bedb882fcb43cb0f7340f1634b8241e2fce26e77b6` |
| family | `source` |
| name | `page_review_state` |
| level | `source` |
| pipelines | `web_extract`, `ai_text` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.page_review_state/rules/0`

`reviewed` / `fetch_failed` / `no_usable_text` / `link_not_followed_cap` / `link_not_followed_hops`; non-`reviewed` states count as unresolved signals in Stage 6.

2. `items/core.page_review_state/rules/1`

The approved plan's verdict list grows to nine; the review status keeps only failed downloads and links not followed.

## `core.discovery_path`
<!-- item: core.discovery_path sha256: 357c1255fd4564a9c6e0f145c723ac10b26223629a465bdeb5ac12462c7858b8 -->

| Field | Value |
|---|---|
| item hash | `357c1255fd4564a9c6e0f145c723ac10b26223629a465bdeb5ac12462c7858b8` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.discovery_path/rules/0`

Add a deterministic `discovery_path` (searched / followed hop n / back-fill followed) on every source row in all runs, and report prevalence with and without followed pages.

## `core.text_source`
<!-- item: core.text_source sha256: 978a2076564d9a86756e24deff140bc472bf88bdd2aad3d3e524c49a455c0793 -->

| Field | Value |
|---|---|
| item hash | `978a2076564d9a86756e24deff140bc472bf88bdd2aad3d3e524c49a455c0793` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.text_source/rules/0`

A per-row `text_source` (stored / live re-fetch / new run) records which rows lack chrome text and links.

## `core.source_publication_date`
<!-- item: core.source_publication_date sha256: 44eac9838bdb4ff1e4552e1ce3e2fe7f65e4d874149b5b3d1b0cbaaa49589f06 -->

| Field | Value |
|---|---|
| item hash | `44eac9838bdb4ff1e4552e1ce3e2fe7f65e4d874149b5b3d1b0cbaaa49589f06` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `{"rule": "first_section", "source": "combining-rules.json items[core.source_publication_date]; ruling source-01, all-06"}` |
| translation_v25 | `{"column": "source_publication_date", "map": "identity"}` |

### Rules

1. `items/core.source_publication_date/rules/0`

Take dates from HTML metadata, PDF properties or URL patterns deterministically; if none is found, the extractor returns a date with its verbatim quote, which is checked against the stored page text like any other quote.

2. `items/core.source_publication_date/rules/1`

One shared date of 1 November 2022, with "before" needing proof. Date origin is recorded as metadata, web address, quote from page text, archive upper bound, or unknown.

## `core.source_snippet`
<!-- item: core.source_snippet sha256: cd81837b81c62d13bd865eb4173c1561fd8eadb2cdbd1f81acca9a9dc297a7a6 -->

| Field | Value |
|---|---|
| item hash | `cd81837b81c62d13bd865eb4173c1561fd8eadb2cdbd1f81acca9a9dc297a7a6` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "source_snippet", "map": "identity", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[4]"}` |

### Rules

1. `items/core.source_snippet/rules/0`

Define `source_snippet` on v2.7 rows as the verbatim supporting text of the page verdict (truncated), with no paraphrase.

2. `items/core.source_snippet/rules/1`

Snippets are verbatim in every pipeline, no translations are stored, and procurement's rule is amended.

## `core.source_credibility`
<!-- item: core.source_credibility sha256: 19f28f187dc610987d2b2166922be7e44dec86054280dd820a52977024d6e945 -->

| Field | Value |
|---|---|
| item hash | `19f28f187dc610987d2b2166922be7e44dec86054280dd820a52977024d6e945` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "source_credibility", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[5]"}` |

### Rules

1. `items/core.source_credibility/rules/0`

`source_credibility` = fixed map from `source_type` plus `low` when `source_publication_date` = unknown or not_documented; drop the translation clause.

2. `items/core.source_credibility/rules/1`

Credibility by `source_type`: official domain (typed from the web domain) `high`; `procurement_tender` `high`; `news_major` `medium`; `news_trade` `medium`; `policy_org` `medium`; `vendor` `medium`; `academic` `high`; `social_media` `low`; `other` `medium`; archive address (typed from the address) `medium`; `source_type` missing (`not_documented`, `unknown`, or `not_asked` on an unreadable page) `low`.

## `core.activity_segment`
<!-- item: core.activity_segment sha256: 1b7750af042738acd295133cb4b1a14e0cfb189619952074db0f3607cfef5f17 -->

| Field | Value |
|---|---|
| item hash | `1b7750af042738acd295133cb4b1a14e0cfb189619952074db0f3607cfef5f17` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `{"rule": "combined_list", "source": "combining-rules.json items[core.activity_segment]; ruling activity-19"}` |
| translation_v25 | `new` |

### Instruction

The extractor proposes spans; jev answers per span: new distinct activity / same as span k / component of span k / not an activity.

### Entailment label

relation to the other activity

### Values

#### `same_activity`

The two passages describe the same activity: the same action by the same actor on the same tool or instrument.

Entailment label: the same activity

#### `component_of_program`

The first passage's activity is a named component of the program described in the second. Both stay separate activities, linked.

Entailment label: a named component of the other activity's programme

#### `has_component`

The first passage describes a program, and the second passage's activity is one of its named components. Both stay separate activities, linked.

Entailment label: a programme that has the other activity as a named component

#### `shared_participation`

The two passages describe one joint action in which several bodies take part. They are one activity: the two passages are merged. The link needs at least two bodies, each named on the page as taking part, with a quote.

Entailment label: one joint action shared with the other activity

#### `governs`

The first passage's activity is a policy or other governance instrument that sets rules for the activity in the second (for example a policy and a tool it approves). When a pair fits both this link and a component link, this link is used.

Entailment label: a rule that governs the other activity

#### `governed_by`

The second passage's activity is a policy or other governance instrument that sets rules for the activity in the first. When a pair fits both this link and a component link, this link is used.

Entailment label: governed by the other activity's rule

#### `distinct_action`

The two passages describe different activities, and none of the other links applies.

Entailment label: a different activity

#### `unresolved`

The page does not settle whether the two passages describe the same activity or different ones. They are kept separate.

Entailment label: not settled

#### `not_an_activity`

The passage does not describe an activity as the activity rule defines one. In a pair of passages, it is used when either passage is not an activity; no other link is coded for that pair.

Entailment label: not an activity

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
<!-- item: core.activity_name sha256: 69808679d441b3cc10cb66a680689e5e2cd4e9280cdd8c6d867494c3ac71e32f -->

| Field | Value |
|---|---|
| item hash | `69808679d441b3cc10cb66a680689e5e2cd4e9280cdd8c6d867494c3ac71e32f` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "activity_name", "map": "identity"}` |

### Instruction

Short name. Use official name if one exists (e.g., "MyCity Chatbot", "Pair Platform"). Otherwise descriptive (e.g., "Internal Copilot pilot for document drafting").

## `core.observed_actor_name`
<!-- item: core.observed_actor_name sha256: e75b120e8bce7ce52b35f2469175efedcbcb30fd659a8d187ef206c852aebb05 -->

| Field | Value |
|---|---|
| item hash | `e75b120e8bce7ce52b35f2469175efedcbcb30fd659a8d187ef206c852aebb05` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.observed_actor_name/rules/0`

The extractor returns the verbatim actor name and organisational unit.

## `core.observed_actor_relationship`
<!-- item: core.observed_actor_relationship sha256: 4c440a4b3d97d7010e60412db483419f4fc47629fc874a131d8a219524a4bb16 -->

| Field | Value |
|---|---|
| item hash | `4c440a4b3d97d7010e60412db483419f4fc47629fc874a131d8a219524a4bb16` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.observed_actor_relationship]; ruling activity-19, activity-14, all-04", "order": ["this_institution", "unit_of_institution", "joint_participant", "unresolved", "other", "not_documented", "unknown"]}` |
| translation_v25 | `new` |

### Instruction

Whose activity is this, according to the page: the named institution's own, one of its units', a joint one it takes part in, or another body's?

### Entailment label

body that carries out the activity

### Values (structured; rendered by slot path)

`items/core.observed_actor_relationship/values/relationship/0/definition`

The page names the searched institution itself, not one of its units, as carrying out or adopting the activity.

`items/core.observed_actor_relationship/values/relationship/0/entailment_label`

the named institution itself

`items/core.observed_actor_relationship/values/relationship/1/definition`

The page names an organisational unit of the searched institution (a department, office or service) as carrying out the activity; it counts for the institution. Choose this, not the institution itself, whenever the page names the unit.

`items/core.observed_actor_relationship/values/relationship/1/entailment_label`

a unit of the named institution

`items/core.observed_actor_relationship/values/relationship/2/definition`

The activity is a joint one, and the page names the searched institution as a participant.

`items/core.observed_actor_relationship/values/relationship/2/entailment_label`

a joint group that includes the named institution

`items/core.observed_actor_relationship/values/relationship/3/definition`

The activity belongs to another body: a parent, sibling or neighbouring body, a separate court, board or authority, a similarly named organisation, or a vendor. The searched institution's role is still asked.

`items/core.observed_actor_relationship/values/relationship/3/entailment_label`

another body

`items/core.observed_actor_relationship/values/relationship/4/definition`

The page does not settle whose activity this is. The role of the searched institution is not asked.

`items/core.observed_actor_relationship/values/relationship/4/entailment_label`

not settled by the page

`items/core.observed_actor_relationship/values/searched_institution_role/0/definition`

The searched institution buys or contracts for the tool or service in its own name.

`items/core.observed_actor_relationship/values/searched_institution_role/0/entailment_label`

buying or contracting in its own name

`items/core.observed_actor_relationship/values/searched_institution_role/1/definition`

Another body runs or buys the activity for the searched institution, and the page names the searched institution as benefiting.

`items/core.observed_actor_relationship/values/searched_institution_role/1/entailment_label`

benefiting from an activity another body runs or buys

`items/core.observed_actor_relationship/values/searched_institution_role/2/definition`

The searched institution buys or sets up a contract or framework on behalf of other bodies.

`items/core.observed_actor_relationship/values/searched_institution_role/2/entailment_label`

buying on behalf of other bodies

`items/core.observed_actor_relationship/values/searched_institution_role/3/definition`

The searched institution is itself a unit (a department, office or school) of a larger body that carries out the activity. Not for an activity that a unit of the searched institution carries out.

`items/core.observed_actor_relationship/values/searched_institution_role/3/entailment_label`

a unit of the larger body that carries out the activity

`items/core.observed_actor_relationship/values/searched_institution_role/4/definition`

The searched institution takes part as one of several joint participants.

`items/core.observed_actor_relationship/values/searched_institution_role/4/entailment_label`

one of several joint participants

`items/core.observed_actor_relationship/values/part_instructions/searched_institution_role`

What part does the named institution play in this activity?

`items/core.observed_actor_relationship/values/part_entailment_labels`

named institution's part

### Rules

1. `items/core.observed_actor_relationship/rules/0`

The relationship is coded per activity. The role of the searched institution is the second part of this question: it describes only the searched institution, is not asked when the relationship is unresolved, and counts `beneficiary` only when the page names it. The two parts are published as one column: the relationship code, then `:` and the role code when the role is a real answer, otherwise the relationship code alone. The observed actor's own role is a separate internal question and is not published.

2. `items/core.observed_actor_relationship/rules/1`

The role field describes only the searched institution's part in the activity (contracting authority, beneficiary, central purchasing body, unit, joint) and never creates rows for another institution.

3. `shared_rules/core.rule.attribution_grain/0` (shared rule `core.rule.attribution_grain`)

An activity carried out by an organisational unit of the named institution (department, office, service) counts for the named institution. When the named institution is a government (national, state, regional or local), its ministries and departments are such units. An activity of its parent, a sibling, or a separate court, board or authority does not, unless the page says the named institution takes part.

4. `shared_rules/core.rule.attribution_grain/1` (shared rule `core.rule.attribution_grain`)

A joint activity counts when the page names this institution as a participant.

5. `items/core.observed_actor_relationship/rules/3`

Relationship answers: this institution, unit of the institution, joint participant, other, unresolved, or not documented.

6. `items/core.observed_actor_relationship/rules/4`

Role of the searched institution: contracting authority, beneficiary, central purchasing body, unit, joint

7. `items/core.observed_actor_relationship/rules/5`

Not documented: the page says nothing on this question. For whose activity this is, a page that says something but does not settle it gets unresolved.

### long_page_rule text

`items/core.observed_actor_relationship/long_page_rule/role_part`

the role part is taken from the same part that produced the relationship

## `core.activity_type`
<!-- item: core.activity_type sha256: 9b0dbf4bdc73d1ea6d60e92fb0ca9c307b114264dfb0ad48aba03e1f48361ee2 -->

| Field | Value |
|---|---|
| item hash | `9b0dbf4bdc73d1ea6d60e92fb0ca9c307b114264dfb0ad48aba03e1f48361ee2` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `{"rule": "highest_probability", "source": "combining-rules.json items[core.activity_type]; ruling activity-20"}` |
| translation_v25 | `{"column": "activity_type", "map": "identity"}` |

### Instruction

What kind of activity is this, according to the page?

### Entailment label

kind of activity

### Values

#### `policy_guidance`

Executive orders, agency memos, acceptable-use rules, procurement standards, internal guidance on permissible AI tools and data handling.

Entailment label: a policy or guidance

#### `pilot_experiment`

Limited trials, sandboxes, proof-of-concept deployments, or time-bounded experiments.

Entailment label: a pilot or trial

#### `program_initiative`

Cross-agency programs, governance bodies, training programs, or platform rollouts spanning multiple units.

Entailment label: a programme that spans several units

#### `internal_operational`

Routine internal use for drafting, summarization, knowledge search, translation, internal helpdesks, or developer tooling.

Entailment label: routine internal use

#### `public_facing_service`

Citizen- or business-facing chatbots, service navigation, translation, complaint handling, case triage.

Entailment label: a service for the public or businesses

### Rules

1. `items/core.activity_type/rules/0`

An AI policy and a pilot at the same institution are two separate activities; code only the activity in question.

2. `items/core.activity_type/rules/1`

A national programme counts as this institution's activity only when the page confirms that this institution takes part.

3. `items/core.activity_type/rules/2`

`unknown` is not one of the answers: it is set when the chosen answer's certainty is below the bar. It means the page confirms an AI activity at this institution but does not let its kind be told; it is never a default.

## `core.action_type`
<!-- item: core.action_type sha256: ba678413a7169cb0a7963c2617c0e629f77325545a3d13d991ca5c589d961657 -->

| Field | Value |
|---|---|
| item hash | `ba678413a7169cb0a7963c2617c0e629f77325545a3d13d991ca5c589d961657` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `{"rule": "highest_probability", "source": "combining-rules.json items[core.action_type]; ruling activity-20"}` |
| translation_v25 | `new` |

### Instruction

What kind of action is this activity?

### Entailment label

kind of action

### Values

#### `deployment`

The institution puts an AI tool to use, or tries one out, for its own work or for the public. Publishing its own content credited as made with AI is putting a tool to use. The stage and the purchase status are coded separately.

Entailment label: putting an AI tool to use

#### `governance`

The institution issues or applies a rule on AI use: a policy, guidance, approved-tool list, order or standard. A body that sets or oversees such rules also counts.

Entailment label: a rule on AI use

#### `staff_training`

The institution trains public-sector staff, its own or those of bodies it serves, to use AI.

Entailment label: training of public-sector staff by the institution

#### `program`

A container activity whose named components are each their own activity, linked to it. Used only when the page names the components.

Entailment label: a programme with named components

### Rules

1. `items/core.action_type/rules/0`

One answer per activity: deployment, governance, staff training or program. Purchases and proposals are not action types; the purchase status and the stage carry them.

2. `shared_rules/core.rule.governance_gate/0` (shared rule `core.rule.governance_gate`)

A body that sets or oversees rules gets the governance questions.

3. `items/core.action_type/rules/2`

`unknown` is not one of the answers: it is set when the chosen answer's certainty is below the bar. It means the page mentions the activity but does not let its kind of action be settled.

## `core.adoption_stage`
<!-- item: core.adoption_stage sha256: 7bb0b0e80894be92f16d6bc51778b7de0dc0a09dd13355860518cb03632a0dd6 -->

| Field | Value |
|---|---|
| item hash | `7bb0b0e80894be92f16d6bc51778b7de0dc0a09dd13355860518cb03632a0dd6` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.adoption_stage]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.adoption_stage]; ruling activity-21, all-04", "order": ["discontinued", "production", "pilot", "announced", "proposed", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "adoption_stage", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[6]"}` |

### Instruction

What stage has this activity reached, according to the page?

### Entailment label

stage

### Values

#### `proposed`

Exploratory or hedged intent with no concrete commitment: "considering," "exploring," "studying feasibility," early discussions, unfunded or undated ideas. The text must still call the tool or activity AI and tie it to this institution. No named tool tied to a timeline, no signed MoU or contract, no budget line, no adopted policy.

Entailment label: proposed or being explored

#### `announced`

Publicly stated intent to deploy with a concrete, documented commitment but no evidence of actual use. Includes: MoUs, budget allocations without deployment, strategy timelines.

Entailment label: announced with a concrete commitment

#### `pilot`

Limited deployment: subset of users/departments/use cases; described as trial/pilot/PoC/experiment; time-bounded.

Entailment label: a pilot or trial

#### `production`

Fully operational: available to intended user base, no longer experimental, in routine operations.

Entailment label: in full, routine operation

#### `discontinued`

Previously deployed but explicitly ended, cancelled, or suspended.

Entailment label: ended, cancelled or suspended

### Rules

1. `items/core.adoption_stage/rules/0`

Purchase steps are coded in the purchase-status question, not here. A payment or subscription alone does not show use: such an activity's stage is unknown unless the page shows use (set by rule, not chosen).

2. `shared_rules/core.rule.ws10_proposals/0` (shared rule `core.rule.ws10_proposals`)

Proposals specific to this institution and explicitly about AI remain a qualifying activity.

3. `items/core.adoption_stage/rules/2`

`unknown` is not one of the answers: it is set when the chosen answer's certainty is below the bar. It means the page confirms the AI activity but does not let its stage be settled.

## `core.procurement_status`
<!-- item: core.procurement_status sha256: f861980556dfa3d13157436b45d9fa9acd27c2281a42c350f62498460fad47f6 -->

| Field | Value |
|---|---|
| item hash | `f861980556dfa3d13157436b45d9fa9acd27c2281a42c350f62498460fad47f6` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.procurement_status]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.procurement_status]; ruling activity-19, all-04", "order": ["payment_or_subscription", "award_or_contract", "tender_or_rfp", "none_documented", "not_documented", "unknown"]}` |
| translation_v25 | `new` |

### Instruction

What purchase step, if any, does the page record for this activity's tool or service?

### Entailment label

purchase step

### Values

#### `none_documented`

The page documents the activity but no purchase step for it.

Entailment label: none recorded

#### `tender_or_rfp`

The institution has issued a call for tenders, a request for proposals or a similar invitation to bid for the tool or service.

Entailment label: a call for tenders or proposals

#### `award_or_contract`

A contract, award or licence agreement for the tool or service is reported as made.

Entailment label: a contract, award or licence

#### `payment_or_subscription`

The page records a payment, invoice or subscription for the tool or service. On its own this does not show use; the stage is then unknown unless use is shown.

Entailment label: a payment or subscription

### Rules

1. `items/core.procurement_status/rules/0`

Answers: `none_documented`, `tender_or_rfp`, `award_or_contract`, `payment_or_subscription`. Use is coded in the adoption stage. A payment-only activity takes `payment_or_subscription` here and stage `unknown`.

2. `items/core.procurement_status/rules/1`

A page that describes the activity but shows no purchase step takes `none_documented`, which is a real answer; `not_documented` is not used for this item.

3. `items/core.procurement_status/rules/2`

The page mentions a purchase of the tool or service but does not let it be settled.

## `core.model_origin`
<!-- item: core.model_origin sha256: a8eccc5010f668b465e986fc3fd060716ff41a7ee9dcd25eff4e70100d1262f6 -->

| Field | Value |
|---|---|
| item hash | `a8eccc5010f668b465e986fc3fd060716ff41a7ee9dcd25eff4e70100d1262f6` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.model_origin]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "highest_probability", "source": "combining-rules.json items[core.model_origin]; ruling activity-20"}` |
| translation_v25 | `{"column": "access_type", "condition": "When build arrangement is model_trained_or_fine_tuned_by_institution, the old column is not filled (old rules would give mixed or in_house).", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[7]"}` |

### Instruction

Where does the model behind this activity's tool come from?

### Entailment label

source of the model

### Values

#### `commercial`

The model comes from a commercial provider (for example OpenAI, Microsoft, Google or Anthropic) and is used through its product, licence or programming interface.

Entailment label: a commercial provider

#### `open_weight`

The model's weights are openly released (for example Llama, Mistral or Falcon), whether the institution or a provider runs it.

Entailment label: an openly released model

#### `government_developed`

The model was developed by or for a government (for example France's Albert or Germany's OpenGPT-X), including by the institution's own team.

Entailment label: a model developed by or for a government

### Rules

1. `items/core.model_origin/rules/0`

`model_origin`: commercial / open_weight / government_developed / unknown. `build_arrangement`: off_the_shelf_product / custom_application_on_external_model / model_trained_or_fine_tuned_by_institution / unknown.

2. `items/core.model_origin/rules/1`

The page mentions the model behind the tool but does not let it be settled.

3. `items/core.model_origin/rules/2`

not_documented: the page is silent.

## `core.build_arrangement`
<!-- item: core.build_arrangement sha256: 5ad6eb5e066f8167db901e699752996fe8ace4c3bba4c615e77e766e3ebab582 -->

| Field | Value |
|---|---|
| item hash | `5ad6eb5e066f8167db901e699752996fe8ace4c3bba4c615e77e766e3ebab582` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.build_arrangement]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.build_arrangement]; ruling activity-19, all-04", "order": ["model_trained_or_fine_tuned_by_institution", "custom_application_on_external_model", "off_the_shelf_product", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "access_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[8]"}` |

### Instruction

How was this activity's tool built?

### Entailment label

way the tool was built

### Values

#### `off_the_shelf_product`

The institution uses a ready-made product as supplied (for example a commercial chat assistant or an office-suite assistant), set up but not built on.

Entailment label: a ready-made product

#### `custom_application_on_external_model`

The institution, or a contractor for it, built its own application (a chatbot, assistant or workflow) on a model it did not train.

Entailment label: its own application on a model it did not train

#### `model_trained_or_fine_tuned_by_institution`

The institution, or a contractor for it, trained or fine-tuned the model itself. Internal use alone does not show this.

Entailment label: a model the institution trained or fine-tuned

### Rules

1. `items/core.build_arrangement/rules/0`

`model_origin`: commercial / open_weight / government_developed / unknown. `build_arrangement`: off_the_shelf_product / custom_application_on_external_model / model_trained_or_fine_tuned_by_institution / unknown.

2. `items/core.build_arrangement/rules/1`

The page mentions how the tool was built but does not let it be settled.

3. `items/core.build_arrangement/rules/2`

not_documented: the page is silent.

## `core.interface`
<!-- item: core.interface sha256: 7ff9950b948b59cf784f3303003661c59aa9d0fa285ac9829255eb909c84d8b2 -->

| Field | Value |
|---|---|
| item hash | `7ff9950b948b59cf784f3303003661c59aa9d0fa285ac9829255eb909c84d8b2` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.interface]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.interface]; ruling activity-19, all-04", "order": ["conversational", "backend_or_api", "other_interface", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[9]"}` |

### Instruction

How do users reach this activity's tool?

### Entailment label

way users reach the tool

### Values

#### `conversational`

Users type or speak to the tool in a chat or question-and-answer exchange, as with a chatbot or assistant window. A tool the page calls a chatbot or assistant counts.

Entailment label: a chat or question-and-answer exchange

#### `backend_or_api`

The tool runs behind the scenes, or other software calls it through a programming interface; users do not talk to it directly.

Entailment label: a back-end or programming interface

#### `other_interface`

Users reach the tool in another way than a chat exchange or a back-end connection.

Entailment label: another way

### Rules

1. `items/core.interface/rules/0`

One answer per activity: conversational, back-end or API, or another interface. Whether the tool sits inside software the institution already used is the deployment-mode question.

2. `items/core.interface/rules/1`

The classifier chooses among the real interfaces and the missing-answer labels.

3. `items/core.interface/rules/2`

Not documented: the page does not say how users reach the tool.

## `core.function_drafting_writing`
<!-- item: core.function_drafting_writing sha256: 9d4a44529aa69940a10a092f981ef8aabed9aeb7c82c2de0d32d22757676c481 -->

| Field | Value |
|---|---|
| item hash | `9d4a44529aa69940a10a092f981ef8aabed9aeb7c82c2de0d32d22757676c481` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_drafting_writing]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[10]"}` |

### Instruction

Does the page state that this activity's tool is used for drafting or writing text?

### Entailment label

tool

### Values

#### `yes`

The page states that the tool is used for drafting or writing text, such as memos, letters, press releases or social media posts.

Entailment label: used for drafting or writing text

#### `no`

The page does not state that the tool is used for drafting or writing text, such as memos, letters, press releases or social media posts.

Entailment label: not used for drafting or writing text

### Rules

1. `items/core.function_drafting_writing/rules/0`

Each function is its own yes/no question about this activity's tool. On a long page the answer is yes if any part says yes.

## `core.function_summarization`
<!-- item: core.function_summarization sha256: 134e27de8e50c257d2916e7e5f82c3e9333c1a5469ae6fd582a091fd48581373 -->

| Field | Value |
|---|---|
| item hash | `134e27de8e50c257d2916e7e5f82c3e9333c1a5469ae6fd582a091fd48581373` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_summarization]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[11]"}` |

### Instruction

Does the page state that this activity's tool is used for summarising documents, reports or meetings?

### Entailment label

tool

### Values

#### `yes`

The page states that the tool is used for summarising documents, reports or meetings.

Entailment label: used for summarising documents, reports or meetings

#### `no`

The page does not state that the tool is used for summarising documents, reports or meetings.

Entailment label: not used for summarising documents, reports or meetings

### Rules

1. `items/core.function_summarization/rules/0`

Each function is its own yes/no question about this activity's tool. On a long page the answer is yes if any part says yes.

## `core.function_translation`
<!-- item: core.function_translation sha256: 08bcc42a47982423b900361d535646758863d637d4c8f5b96280dfc232cc7603 -->

| Field | Value |
|---|---|
| item hash | `08bcc42a47982423b900361d535646758863d637d4c8f5b96280dfc232cc7603` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_translation]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[12]"}` |

### Instruction

Does the page state that this activity's tool is used for translating text or speech between languages?

### Entailment label

tool

### Values

#### `yes`

The page states that the tool is used for translating text or speech between languages.

Entailment label: used for translating between languages

#### `no`

The page does not state that the tool is used for translating text or speech between languages.

Entailment label: not used for translating between languages

### Rules

1. `items/core.function_translation/rules/0`

Each function is its own yes/no question about this activity's tool. On a long page the answer is yes if any part says yes.

## `core.function_search_retrieval`
<!-- item: core.function_search_retrieval sha256: a9d975c026c25b4ab93cad2a6e6917a394bd2ea42a94bc4e8676c103255c4877 -->

| Field | Value |
|---|---|
| item hash | `a9d975c026c25b4ab93cad2a6e6917a394bd2ea42a94bc4e8676c103255c4877` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_search_retrieval]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[13]"}` |

### Instruction

Does the page state that this activity's tool is used for finding information?

### Entailment label

tool

### Values

#### `yes`

The page states that the tool is used for finding information, such as answering questions from documents or searching the institution's own records.

Entailment label: used for finding information

#### `no`

The page does not state that the tool is used for finding information, such as answering questions from documents or searching the institution's own records.

Entailment label: not used for finding information

### Rules

1. `items/core.function_search_retrieval/rules/0`

Each function is its own yes/no question about this activity's tool. On a long page the answer is yes if any part says yes.

## `core.function_code`
<!-- item: core.function_code sha256: 04ec6ce8f32cb2105118b4f45e56c88be084fb2918dddb5472b0fd20e4b1edfa -->

| Field | Value |
|---|---|
| item hash | `04ec6ce8f32cb2105118b4f45e56c88be084fb2918dddb5472b0fd20e4b1edfa` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_code]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[14]"}` |

### Instruction

Does the page state that this activity's tool is used for writing, reviewing or fixing software code?

### Entailment label

tool

### Values

#### `yes`

The page states that the tool is used for writing, reviewing or fixing software code.

Entailment label: used for writing, reviewing or fixing code

#### `no`

The page does not state that the tool is used for writing, reviewing or fixing software code.

Entailment label: not used for writing, reviewing or fixing code

### Rules

1. `items/core.function_code/rules/0`

Each function is its own yes/no question about this activity's tool. On a long page the answer is yes if any part says yes.

## `core.function_image_audio_video`
<!-- item: core.function_image_audio_video sha256: 31fcf07acca54ccbeca7637feb59496c407059a2e8eafc17e97b8a4f822dda81 -->

| Field | Value |
|---|---|
| item hash | `31fcf07acca54ccbeca7637feb59496c407059a2e8eafc17e97b8a4f822dda81` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_image_audio_video]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[15]"}` |

### Instruction

Does the page state that this activity's tool is used for creating or editing images, audio or video?

### Entailment label

tool

### Values

#### `yes`

The page states that the tool is used for creating or editing images, audio or video.

Entailment label: used for creating or editing images, audio or video

#### `no`

The page does not state that the tool is used for creating or editing images, audio or video.

Entailment label: not used for creating or editing images, audio or video

### Rules

1. `items/core.function_image_audio_video/rules/0`

Each function is its own yes/no question about this activity's tool. On a long page the answer is yes if any part says yes.

## `core.function_extraction_classification`
<!-- item: core.function_extraction_classification sha256: 5b6fd7b8062937a905121023bbfe841b4a22936d1f3190e712a36cef331ddbfc -->

| Field | Value |
|---|---|
| item hash | `5b6fd7b8062937a905121023bbfe841b4a22936d1f3190e712a36cef331ddbfc` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_extraction_classification]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[16]"}` |

### Instruction

Does the page state that this activity's tool is used for pulling information out of documents or forms, or sorting and classifying them?

### Entailment label

tool

### Values

#### `yes`

The page states that the tool is used for pulling information out of documents or forms, or sorting and classifying them.

Entailment label: used for pulling information out of documents or sorting them

#### `no`

The page does not state that the tool is used for pulling information out of documents or forms, or sorting and classifying them.

Entailment label: not used for pulling information out of documents or sorting them

### Rules

1. `items/core.function_extraction_classification/rules/0`

Each function is its own yes/no question about this activity's tool. On a long page the answer is yes if any part says yes.

## `core.function_analysis_recommendation`
<!-- item: core.function_analysis_recommendation sha256: 4a973c2f1e681855c13ae910fc161c7c408dc362ab85015b8b3873c46ac44cb9 -->

| Field | Value |
|---|---|
| item hash | `4a973c2f1e681855c13ae910fc161c7c408dc362ab85015b8b3873c46ac44cb9` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.function_analysis_recommendation]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `{"column": "interaction_type", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[17]"}` |

### Instruction

Does the page state that this activity's tool is used for analysing information or giving recommendations or scores to support human decisions?

### Entailment label

tool

### Values

#### `yes`

The page states that the tool is used for analysing information or giving recommendations or scores to support human decisions, such as case triage or eligibility checks.

Entailment label: used for analysis or recommendations that support decisions

#### `no`

The page does not state that the tool is used for analysing information or giving recommendations or scores to support human decisions, such as case triage or eligibility checks.

Entailment label: not used for analysis or recommendations that support decisions

### Rules

1. `items/core.function_analysis_recommendation/rules/0`

Each function is its own yes/no question about this activity's tool. On a long page the answer is yes if any part says yes.

## `core.tool_name`
<!-- item: core.tool_name sha256: 1e879decc441d08c1b631a1f9440e6ef97606a9d056326e738407db500984350 -->

| Field | Value |
|---|---|
| item hash | `1e879decc441d08c1b631a1f9440e6ef97606a9d056326e738407db500984350` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.tool_name]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
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
<!-- item: core.model_name sha256: 920c2ca82290833327903b8555b400f782cfb9d1af1b42c99b0700ba966b947f -->

| Field | Value |
|---|---|
| item hash | `920c2ca82290833327903b8555b400f782cfb9d1af1b42c99b0700ba966b947f` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.model_name]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `combined_list` |
| translation_v25 | `new` |

### Rules

1. `items/core.model_name/rules/0`

`tool_name` = product or platform as written on the page; new `model_name` = model as written (e.g. "GPT-4o") or `unknown`. Several tools are `; `-separated in page order. `not_applicable` for activities without a tool.

2. `items/core.model_name/rules/1`

The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.contracting_party`
<!-- item: core.contracting_party sha256: 08c049166dc9dff75f2da9a369b32e7cb664c615d17f0f09a58e5c75adf1c3cd -->

| Field | Value |
|---|---|
| item hash | `08c049166dc9dff75f2da9a369b32e7cb664c615d17f0f09a58e5c75adf1c3cd` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.contracting_party]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "combined_list", "source": "combining-rules.json items[core.contracting_party]; ruling activity-19"}` |
| translation_v25 | `{"column": "vendor", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[18]"}` |

### Rules

1. `items/core.contracting_party/rules/0`

Developer (stated on the page, with its basis recorded) and contracting party (page-stated only).

2. `items/core.contracting_party/rules/1`

Vendor holds what the source names, which in purchase records is the contracting party. The developer from the lookup goes into a new model-developer column, and the lookup stops filling vendor.

3. `items/core.contracting_party/rules/2`

The quote step runs for every activity; skipped items are kept internally and published as "not asked".

## `core.developer`
<!-- item: core.developer sha256: eaa4b9278a86d5d25d3b8a6de4a4cfdfd66f8b06b5d39a07ebb35e0284bdc6bf -->

| Field | Value |
|---|---|
| item hash | `eaa4b9278a86d5d25d3b8a6de4a4cfdfd66f8b06b5d39a07ebb35e0284bdc6bf` |
| family | `tool` |
| name | `developer` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.developer]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "combined_list", "source": "combining-rules.json items[core.developer]; ruling activity-19"}` |
| translation_v25 | `{"column": "vendor", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[19]"}` |

### Rules

1. `items/core.developer/rules/0`

Developer (stated on the page, with its basis recorded) and contracting party (page-stated only).

2. `items/core.developer/rules/1`

vendor = the organisation the page names as supplying the AI product or service, verbatim.

3. `items/core.developer/rules/2`

The quote step runs for every activity; skipped items are kept internally and published as "not asked".

4. `items/core.developer/rules/3`

A developer stated on the page comes from the quote step, with its supporting quote; `developer_basis` = stated.

## `core.developer_basis`
<!-- item: core.developer_basis sha256: 49985b943e91ec215c6a7919ab4d9db9f68916d7df01be30bf940983017bcc57 -->

| Field | Value |
|---|---|
| item hash | `49985b943e91ec215c6a7919ab4d9db9f68916d7df01be30bf940983017bcc57` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.developer_basis/rules/0`

Developer (stated on the page, with its basis recorded) and contracting party (page-stated only).

2. `items/core.developer_basis/rules/1`

The per-run version record also holds the codebook version, the channel tag stays on each row, and per-code coder details are stored internally and linked to that record.

3. `items/core.developer_basis/rules/2`

When `developer` is a missing token (`not_asked`, `not_documented`, `unknown` or `_NA_`), `developer_basis` takes the same token.

4. `items/core.developer_basis/rules/3`

At Stage 6, a merged activity takes its `developer` as it takes `contracting_party`: from the observation with the highest source credibility, ties by pool order, a real value over a missing token. Its `developer_basis` is `stated` when that developer is a real value, else the developer's missing token.

## `core.deployment_mode`
<!-- item: core.deployment_mode sha256: ed5672b2fed226dd6a980bec93b1b15edb9d943ae4d08eeea596d69b8377008c -->

| Field | Value |
|---|---|
| item hash | `ed5672b2fed226dd6a980bec93b1b15edb9d943ae4d08eeea596d69b8377008c` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.deployment_mode]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "highest_probability", "source": "combining-rules.json items[core.deployment_mode]; ruling activity-20"}` |
| translation_v25 | `{"column": "deployment_mode", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[20]"}` |

### Instruction

`standalone`: separate tool/interface. `integrated`: embedded in existing system (e.g., Copilot inside Outlook).

### Entailment label

fit with existing software

### Values

#### `integrated`

integrated: the AI feature works inside software or a service channel the institution already used (office suite, case system, existing website service).

Entailment label: built into software or a service already in use

#### `standalone`

standalone: a separate application or site created for the AI tool.

Entailment label: a separate application or site

### Rules

1. `items/core.deployment_mode/rules/0`

The page mentions whether the tool is separate or built into existing software but does not let it be settled.

2. `items/core.deployment_mode/rules/1`

not_documented: the page is silent.

## `core.target_users`
<!-- item: core.target_users sha256: fd900391b467a5aade9e8ddba9eb1c3da8247f681ccf54cbe1867015410b4a64 -->

| Field | Value |
|---|---|
| item hash | `fd900391b467a5aade9e8ddba9eb1c3da8247f681ccf54cbe1867015410b4a64` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.target_users]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "combined_list", "then": "mapping step to one value", "source": "combining-rules.json items[core.target_users].alternative; ruling activity-22 b"}` |
| translation_v25 | `{"column": "target_users", "map": "identity"}` |

### Instruction

Who interacts with the AI system.

### Entailment label

users of the tool

### Values

#### `internal_staff`

Only the institution's own staff use the tool.

Entailment label: the institution's own staff only

#### `public`

People outside the institution use the tool: members of the public, residents or businesses.

Entailment label: people outside the institution

#### `both`

Both the institution's staff and people outside it use the tool. On long pages, one part naming staff and another the public also gives this value.

Entailment label: both staff and people outside the institution

### Rules

1. `items/core.target_users/rules/0`

Asked only for tool activities.

2. `items/core.target_users/rules/1`

The page mentions who uses the tool but does not let it be settled.

3. `items/core.target_users/rules/2`

not_documented: the page is silent.

### long_page_rule text

`items/core.target_users/long_page_rule/mapping/other_lists`

Drop 'not covered by this part' and missing labels from the list. 'both' present, or staff and public both present, gives 'both'. One real value gives that value. No real value: not_documented if any part says the page is silent, else unknown. Every part 'not covered' gives not_documented.

## `core.governed_population`
<!-- item: core.governed_population sha256: e57d050167a5cbc640be0588e4e4b1a51d9ce6a1ef81c22ebfbf0bf8714ee7f5 -->

| Field | Value |
|---|---|
| item hash | `e57d050167a5cbc640be0588e4e4b1a51d9ce6a1ef81c22ebfbf0bf8714ee7f5` |
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
| status | `signed` |
| gate | `{"item": "core.action_type", "values": ["governance"], "rule": "core.rule.governance_gate"}` |
| long_page_rule | `{"rule": "combined_list", "then": "mapping step to one value", "source": "combining-rules.json items[core.governed_population].alternative; ruling activity-22 b"}` |
| translation_v25 | `new` |

### Instruction

Whom does this rule on AI use apply to?

### Entailment label

people the rule applies to

### Values

#### `internal_personnel`

The rule applies to the institution's own staff and officials.

Entailment label: the institution's own staff and officials

#### `external_users`

The rule applies to people or bodies outside the institution, such as the public or the parties it regulates.

Entailment label: people or bodies outside the institution

#### `both`

The rule applies both to the institution's own staff and to people or bodies outside it. On long pages, one part naming each also gives this value.

Entailment label: both staff and people or bodies outside the institution

### Rules

1. `items/core.governed_population/rules/0`

The page mentions whom the rule applies to but does not let it be settled.

2. `items/core.governed_population/rules/1`

not_documented: the page is silent.

### long_page_rule text

`items/core.governed_population/long_page_rule/mapping/other_lists`

Drop 'not covered by this part' and missing labels from the list. 'both' present, or staff and public both present, gives 'both'. One real value gives that value. No real value: not_documented if any part says the page is silent, else unknown. Every part 'not covered' gives not_documented.

## `core.governance_form`
<!-- item: core.governance_form sha256: 9b84ef67dcb070a32922917d06ab5a956193261e27e713de958b3f34a14bf93a -->

| Field | Value |
|---|---|
| item hash | `9b84ef67dcb070a32922917d06ab5a956193261e27e713de958b3f34a14bf93a` |
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
| status | `signed` |
| gate | `{"item": "core.action_type", "values": ["governance"], "rule": "core.rule.governance_gate"}` |
| long_page_rule | `combined_list` |
| translation_v25 | `new` |

### Instruction

What form does this rule on AI use take? Choose all that apply.

### Entailment label

form of the rule

### Values

#### `dedicated_genai_or_ai_policy_or_guideline`

A policy, guideline, code of practice or acceptable-use rule whose main subject is AI.

Entailment label: a policy or guideline mainly about AI

#### `approved_tool_list_or_endorsement`

A list of approved or permitted AI tools, or an official endorsement of a named tool.

Entailment label: a list of approved tools or an endorsement of a tool

#### `clause_in_instrument_on_other_subject`

A clause on AI inside a rule, policy or guidance whose main subject is something else (for example IT security or records management).

Entailment label: a clause in a rule on another subject

#### `court_or_regulatory_order`

An order, decision or practice direction on AI use issued by a court or a regulator.

Entailment label: an order of a court or regulator

#### `procurement_standard`

A standard or requirement for buying AI tools or services, such as purchasing criteria or contract terms.

Entailment label: a standard for buying AI tools or services

### Rules

1. `items/core.governance_form/rules/0`

jev Choice: dedicated_genai_or_ai_policy_or_guideline / approved_tool_list_or_endorsement / clause_in_instrument_on_other_subject / court_or_regulatory_order / procurement_standard / unknown. Applies only when the action is governance (`not_applicable` otherwise).

2. `items/core.governance_form/rules/1`

More than one form can apply: a document can be both a guideline and an endorsement.

3. `items/core.governance_form/rules/2`

The page mentions the form of the rule but does not let it be settled.

4. `items/core.governance_form/rules/3`

not_documented: the page is silent.

## `core.governance_direction`
<!-- item: core.governance_direction sha256: f84d7bfb555ec9856b9d13f4b269dfedd31b070fd148dc5a93b30b8c4fd38149 -->

| Field | Value |
|---|---|
| item hash | `f84d7bfb555ec9856b9d13f4b269dfedd31b070fd148dc5a93b30b8c4fd38149` |
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
| status | `signed` |
| gate | `{"item": "core.action_type", "values": ["governance"], "rule": "core.rule.governance_gate"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.governance_direction]; ruling activity-19, activity-10, activity-11, all-04", "order": ["restricts_with_conditions", "prohibits", "permits", "requires", "promotes", "not_documented", "unknown"]}` |
| translation_v25 | `new` |

### Instruction

Does this rule ban, limit, allow, require or encourage the AI use it covers?

### Entailment label

stance of the rule on AI use

### Values

#### `prohibits`

The rule bans the AI use it covers, with no use allowed.

Entailment label: a ban

#### `restricts_with_conditions`

The rule allows use only under conditions (for example approval, training, limits on data, or human review), or bans some uses and allows others. On long pages, a ban in one part and a permission in another also give this value.

Entailment label: use allowed only under conditions

#### `permits`

The rule allows the use without conditions.

Entailment label: use allowed without conditions

#### `requires`

The rule makes AI use mandatory for some task or for some staff.

Entailment label: use required

#### `promotes`

The rule encourages or supports AI use without making it mandatory.

Entailment label: use encouraged

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
<!-- item: core.service_domain sha256: 123bf211ef3127c9998ee9064714c651171f1a284832af21f9c117c6ecdb8150 -->

| Field | Value |
|---|---|
| item hash | `123bf211ef3127c9998ee9064714c651171f1a284832af21f9c117c6ecdb8150` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `{"rule": "combined_list", "source": "combining-rules.json items[core.service_domain]; ruling activity-20", "per_value_producing_part": "highest_probability", "replaces_rule": "highest_probability (activity-20 a, before activity-13 b made the item multi-select)"}` |
| translation_v25 | `new` |

### Instruction

Which areas of government work does this activity concern? Choose all that apply.

### Entailment label

area of government work

### Values

#### `general_public_services`

Running government itself: executive and legislative bodies, financial, fiscal and tax affairs, foreign affairs and foreign economic aid, general administration and internal services, and basic research.

Entailment label: general public services

#### `defence`

Military and civil defence, and foreign military aid.

Entailment label: defence

#### `public_order_safety`

Police, fire protection, the courts and prisons.

Entailment label: public order and safety

#### `economic_affairs`

Economic, commercial and labour affairs; agriculture, forestry, fishing and hunting; fuel and energy; mining, manufacturing and construction; transport; communication (post and telecommunications); other industries, such as trade, tourism, hotels and restaurants.

Entailment label: economic affairs

#### `environmental_protection`

Waste and waste-water management, pollution control, and the protection of biodiversity and landscape.

Entailment label: environmental protection

#### `housing_community_amenities`

Housing and community development, water supply and street lighting.

Entailment label: housing and community amenities

#### `health`

Medical products, outpatient and hospital services, and public health services.

Entailment label: health

#### `recreation_culture_religion`

Recreation and sport, culture, broadcasting and publishing, and religious and other community services.

Entailment label: recreation, culture and religion

#### `education`

Education at every level, from pre-primary to tertiary, education not tied to a level, and services that support it. Training of public-sector staff by an institution counts under that institution's area, not education.

Entailment label: education

#### `social_protection`

Support in sickness and disability, old age, for survivors, families and children, in unemployment, for housing, and against social exclusion.

Entailment label: social protection

#### `other`

An area that fits none of the ten areas above.

Entailment label: another area

### Rules

1. `items/core.service_domain/rules/0`

One question per activity: tick every area of government work the activity concerns.

2. `items/core.service_domain/rules/1`

The UN and Eurostat classification of the functions of government, top level (as used by Public Sector Tech Watch)

3. `items/core.service_domain/rules/2`

Activities that fit no area get "other".

4. `items/core.service_domain/rules/3`

Not documented: the page does not say which area of government work the activity concerns.

5. `items/core.service_domain/rules/4`

No separate value. A rule says the earlier 'general administration' is coded 'general public services'.

### long_page_rule text

`items/core.service_domain/long_page_rule/multi_select_vs_single_winner`

Take every area any part ticks with a supported answer. Each area's quote and certainty come from the part most sure of it. Missing labels only if no part ticks a real area.

## `core.genai_mechanism_basis`
<!-- item: core.genai_mechanism_basis sha256: c23be1bdd952944f28000538057031619e40ec02d05d4445e2a57644a7480cdd -->

| Field | Value |
|---|---|
| item hash | `c23be1bdd952944f28000538057031619e40ec02d05d4445e2a57644a7480cdd` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.genai_mechanism_basis]; ruling activity-19, all-04", "order": ["named_genai_product_or_model", "explicit_genai_label", "generative_capability_described", "ai_chatbot_or_assistant_label_only", "no_generative_signal", "not_documented", "unknown"]}` |
| translation_v25 | `new` |

### Instruction

What on the page, if anything, shows that this activity's tool is generative AI?

### Entailment label

sign that the tool is generative AI

### Values

#### `named_genai_product_or_model`

The page names a generative product or model, such as ChatGPT, Copilot, Gemini, Claude or a named language model.

Entailment label: a named generative product or model

#### `explicit_genai_label`

The page calls the tool generative AI, a large language model or the like, without naming a product.

Entailment label: a generative-AI label

#### `generative_capability_described`

The page says the tool generates text, images, audio, code or other content, without naming a product or using a generative-AI label.

Entailment label: a description of the content it generates

#### `ai_chatbot_or_assistant_label_only`

The only signal is that the page calls the tool an 'AI chatbot' or 'AI assistant'; under the GenAI boundary rule this counts as generative.

Entailment label: only the words 'AI chatbot' or 'AI assistant'

#### `no_generative_signal`

The page calls the tool AI or machine learning but gives none of the other signs: no generative product or model is named, the tool is not called generative AI or a language model, no generated content is described, and it is not called an AI chatbot or AI assistant.

Entailment label: no sign that the tool is generative AI

### Rules

1. `items/core.genai_mechanism_basis/rules/0`

Asked for every activity on a page that confirms an AI activity. The supporting quote is extracted separately.

2. `shared_rules/core.rule.genai_boundary/0` (shared rule `core.rule.genai_boundary`)

A tool the page calls an "AI chatbot" or "AI assistant" counts as generative AI, even where a rule-based chatbot would otherwise be excluded.

3. `shared_rules/core.rule.genai_boundary/1` (shared rule `core.rule.genai_boundary`)

Translation counts as an AI activity when the page calls it AI or machine learning. It counts as generative AI only when the page ties it to a named generative product or says a language model produces it.

## `core.year_announced`
<!-- item: core.year_announced sha256: 5012f56b9cc6e875253650faab5901f2dc885bb9b047e2efcd69b53751d88251 -->

| Field | Value |
|---|---|
| item hash | `5012f56b9cc6e875253650faab5901f2dc885bb9b047e2efcd69b53751d88251` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.year_announced]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `earliest_year` |
| translation_v25 | `{"column": "year_announced", "map": "identity"}` |

### Instruction

In which year does the page say this activity was first announced?

### Entailment label

year it was first announced

### Values (structured; rendered by slot path)

### Rules

1. `items/core.year_announced/rules/0`

Deterministic: extract all four-digit years 2015-2030 from the activity span and its context, plus the calendar years named by any fiscal-year label there and the years written in the Japanese era (with the era name), the Buddhist Era (with its marker) or the ROC calendar (民國), converted to CE; a label spanning two calendar years gives both. A year range gives both its end years, even outside 2015-2030, unless a numbering word such as "p.", "No." or "§" comes just before it; a two-digit end year counts only in a fiscal-year label. A two-digit year is read as 20xx, except that those from (current year mod 100) + 25 through 99 are read as 19xx. No fallback to publication year. Across chunks: earliest chosen year.

2. `items/core.year_announced/rules/1`

Pilot and production years use the same candidate-then-classifier method. Fiscal-year labels in any language, years in the Japanese era (written with the era name), the Buddhist Era (with its marker) and the ROC calendar (民國), and years written in other digits become candidate years by their written form alone, under the approved conversion table (T-064); the country is never used. Governance uses the announcement year as its adoption year; pilot and production years are not asked for it.

3. `items/core.year_announced/rules/2`

not_documented: the page is silent.

## `core.year_pilot_start`
<!-- item: core.year_pilot_start sha256: f1f89ccdbc5ca6c6e7827a9d2db5f32576f58510aa3ebebf96c7bfd14c63cbc7 -->

| Field | Value |
|---|---|
| item hash | `f1f89ccdbc5ca6c6e7827a9d2db5f32576f58510aa3ebebf96c7bfd14c63cbc7` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.year_pilot_start]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `earliest_year` |
| translation_v25 | `{"column": "year_deployed", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[21]"}` |

### Instruction

In which year does the page say a pilot or trial of this activity began?

### Entailment label

year its pilot or trial began

### Values (structured; rendered by slot path)

### Rules

1. `items/core.year_pilot_start/rules/0`

Deterministic: extract all four-digit years 2015-2030 from the activity span and its context, plus the calendar years named by any fiscal-year label there and the years written in the Japanese era (with the era name), the Buddhist Era (with its marker) or the ROC calendar (民國), converted to CE; a label spanning two calendar years gives both. A year range gives both its end years, even outside 2015-2030, unless a numbering word such as "p.", "No." or "§" comes just before it; a two-digit end year counts only in a fiscal-year label. A two-digit year is read as 20xx, except that those from (current year mod 100) + 25 through 99 are read as 19xx. No fallback to publication year. Across chunks: earliest chosen year.

2. `items/core.year_pilot_start/rules/1`

Pilot and production years use the same candidate-then-classifier method. Fiscal-year labels in any language, years in the Japanese era (written with the era name), the Buddhist Era (with its marker) and the ROC calendar (民國), and years written in other digits become candidate years by their written form alone, under the approved conversion table (T-064); the country is never used. Governance uses the announcement year as its adoption year; pilot and production years are not asked for it.

3. `items/core.year_pilot_start/rules/2`

Two columns, each stated-only.

4. `items/core.year_pilot_start/rules/3`

not_documented: the page is silent.

## `core.year_production_start`
<!-- item: core.year_production_start sha256: efe66c3eeb335786bafe62cca5a3d4da7c5b9da1da1ecebffa2c08fb7479a94a -->

| Field | Value |
|---|---|
| item hash | `efe66c3eeb335786bafe62cca5a3d4da7c5b9da1da1ecebffa2c08fb7479a94a` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.year_production_start]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `earliest_year` |
| translation_v25 | `{"column": "year_deployed", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[22]"}` |

### Instruction

In which year does the page say this activity went into full, routine operation?

### Entailment label

year it went into full operation

### Values (structured; rendered by slot path)

### Rules

1. `items/core.year_production_start/rules/0`

Deterministic: extract all four-digit years 2015-2030 from the activity span and its context, plus the calendar years named by any fiscal-year label there and the years written in the Japanese era (with the era name), the Buddhist Era (with its marker) or the ROC calendar (民國), converted to CE; a label spanning two calendar years gives both. A year range gives both its end years, even outside 2015-2030, unless a numbering word such as "p.", "No." or "§" comes just before it; a two-digit end year counts only in a fiscal-year label. A two-digit year is read as 20xx, except that those from (current year mod 100) + 25 through 99 are read as 19xx. No fallback to publication year. Across chunks: earliest chosen year.

2. `items/core.year_production_start/rules/1`

Pilot and production years use the same candidate-then-classifier method. Fiscal-year labels in any language, years in the Japanese era (written with the era name), the Buddhist Era (with its marker) and the ROC calendar (民國), and years written in other digits become candidate years by their written form alone, under the approved conversion table (T-064); the country is never used. Governance uses the announcement year as its adoption year; pilot and production years are not asked for it.

3. `items/core.year_production_start/rules/2`

Two columns, each stated-only.

4. `items/core.year_production_start/rules/3`

not_documented: the page is silent.

## `core.deployment_scale_number`
<!-- item: core.deployment_scale_number sha256: c3740fb709eb05a98b259f988dc7611e778dfd87abd332d7de982d11ad8b23ae -->

| Field | Value |
|---|---|
| item hash | `c3740fb709eb05a98b259f988dc7611e778dfd87abd332d7de982d11ad8b23ae` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.deployment_scale_number]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
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
<!-- item: core.deployment_scale_unit sha256: 87368e214a3f451255e7ecf7d61518e8642043fce8097e9299abcbfc9994d55b -->

| Field | Value |
|---|---|
| item hash | `87368e214a3f451255e7ecf7d61518e8642043fce8097e9299abcbfc9994d55b` |
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
| status | `signed` |
| gate | `{"item": "core.deployment_scale_number", "values": "any", "as_ruled": "any stated"}` |
| long_page_rule | `{"rule": "combined_list", "pairs": "(number, unit), the unit from the same part as its number", "source": "combining-rules.json items[core.deployment_scale_unit].alternative; ruling activity-24 b"}` |
| translation_v25 | `new` |

### Instruction

What does the stated number for this activity count?

### Entailment label

unit counted by the stated number

### Values

#### `licences_or_seats`

The number counts licences, seats or accounts bought or issued.

Entailment label: licences, seats or accounts

#### `users`

The number counts people who use the tool.

Entailment label: people who use the tool

#### `interactions`

The number counts uses of the tool, such as questions answered, conversations held or documents handled.

Entailment label: uses of the tool

#### `units_or_departments`

The number counts offices, departments, schools or other units that use the tool.

Entailment label: offices, departments or other units

#### `none`

A number is stated, but it counts none of these units.

Entailment label: none of these units

### Rules

1. `items/core.deployment_scale_unit/rules/0`

The extractor returns the verbatim number span. jev Choice gives the unit: licences_or_seats / users / interactions / units_or_departments / none.

2. `items/core.deployment_scale_unit/rules/1`

not_documented: the page is silent.

## `core.has_human_oversight`
<!-- item: core.has_human_oversight sha256: f457c8145acede1568adb8b4935f40c6ec54f1527e86afb4de1fcfb0bbc7e614 -->

| Field | Value |
|---|---|
| item hash | `f457c8145acede1568adb8b4935f40c6ec54f1527e86afb4de1fcfb0bbc7e614` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.has_human_oversight]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.has_human_oversight]; ruling activity-23, all-04 (order: the draft's alternative (b))", "order": ["yes", "no", "unclear", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "has_human_oversight", "map": "identity"}` |

### Instruction

Is human review required before acting on AI outputs?

### Entailment label

human review of AI outputs

### Values

#### `yes`

yes: the page states the safeguard applies to this activity (for a governance activity: the rule requires it).

Entailment label: in place or required

#### `no`

no: the page states it does not apply.

Entailment label: not in place

#### `unclear`

unclear: the page mentions the safeguard but it cannot be settled whether it applies to this activity.

Entailment label: mentioned, but not settled for this activity

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
<!-- item: core.has_transparency_notice sha256: 1feb9b1b0a856b2230f82f423887235fa54e5e5639cc0fea2e740ea24e31accb -->

| Field | Value |
|---|---|
| item hash | `1feb9b1b0a856b2230f82f423887235fa54e5e5639cc0fea2e740ea24e31accb` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.has_transparency_notice]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.has_transparency_notice]; ruling activity-23, all-04 (order: the draft's alternative (b))", "order": ["yes", "no", "unclear", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "has_transparency_notice", "map": "identity"}` |

### Instruction

Are users/citizens notified that AI is involved?

### Entailment label

notice to users that AI is involved

### Values

#### `yes`

yes: the page states the safeguard applies to this activity (for a governance activity: the rule requires it).

Entailment label: in place or required

#### `no`

no: the page states it does not apply.

Entailment label: not in place

#### `unclear`

unclear: the page mentions the safeguard but it cannot be settled whether it applies to this activity.

Entailment label: mentioned, but not settled for this activity

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
<!-- item: core.has_data_classification sha256: 7f4298c0a9d34091bdff171a97ab9d0a143b74439e2a7354c756d7d955111bd2 -->

| Field | Value |
|---|---|
| item hash | `7f4298c0a9d34091bdff171a97ab9d0a143b74439e2a7354c756d7d955111bd2` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.has_data_classification]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.has_data_classification]; ruling activity-23, all-04 (order: the draft's alternative (b))", "order": ["yes", "no", "unclear", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "has_data_classification", "map": "identity"}` |

### Instruction

Are there documented data-handling restrictions for AI use?

### Entailment label

restriction on the data AI may handle

### Values

#### `yes`

yes: the page states the safeguard applies to this activity (for a governance activity: the rule requires it).

Entailment label: in place or required

#### `no`

no: the page states it does not apply.

Entailment label: not in place

#### `unclear`

unclear: the page mentions the safeguard but it cannot be settled whether it applies to this activity.

Entailment label: mentioned, but not settled for this activity

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
<!-- item: core.has_risk_assessment sha256: 6b438e33e59995ecb695bcbde885caee7d2bea00896ac8832eb4342638b0dace -->

| Field | Value |
|---|---|
| item hash | `6b438e33e59995ecb695bcbde885caee7d2bea00896ac8832eb4342638b0dace` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.has_risk_assessment]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.has_risk_assessment]; ruling activity-23, all-04 (order: the draft's alternative (b))", "order": ["yes", "no", "unclear", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "has_risk_assessment", "map": "identity"}` |

### Instruction

Has a formal risk/impact assessment been documented?

### Entailment label

formal risk or impact assessment

### Values

#### `yes`

yes: the page states the safeguard applies to this activity (for a governance activity: the rule requires it).

Entailment label: in place or required

#### `no`

no: the page states it does not apply.

Entailment label: not in place

#### `unclear`

unclear: the page mentions the safeguard but it cannot be settled whether it applies to this activity.

Entailment label: mentioned, but not settled for this activity

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
<!-- item: core.outcome_kind sha256: 59564af9fc5b525d9472d8ed39d46328708e5f8768eade74b8f57edb7b3aaacc -->

| Field | Value |
|---|---|
| item hash | `59564af9fc5b525d9472d8ed39d46328708e5f8768eade74b8f57edb7b3aaacc` |
| family | `outcomes` |
| name | `outcome_kind` |
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
| frozen_signature | `CX-01.3:CX-61` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.outcome_kind]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.outcome_kind]; ruling activity-19, all-04", "order": ["quantified", "qualitative", "none_reported", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "reported_outcomes", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[23]"}` |

### Instruction

Does the page report a result of this activity, and if so, what kind?

### Entailment label

reported result

### Values

#### `quantified`

The page reports a result of this activity that is measured or given as a number.

Entailment label: a measured or numeric result

#### `qualitative`

The page reports a result of this activity in words only, with no measure. Goals, plans or expected benefits are not results.

Entailment label: a result in words only

#### `none_reported`

The page reports no result of this activity.

Entailment label: none reported

### Rules

1. `items/core.outcome_kind/rules/0`

Asked about this activity only, once for results and once for incidents. The answer says both whether the page reports one and what kind; the text of the result or incident is extracted only when the answer is not `none_reported`. The incident question also offers `discontinuation_uncertain`.

## `core.incident_kind`
<!-- item: core.incident_kind sha256: 0f4afe6e02b0cd70050442ee5f46ecef32fb1aa645bdf3832b2a076deebfed66 -->

| Field | Value |
|---|---|
| item hash | `0f4afe6e02b0cd70050442ee5f46ecef32fb1aa645bdf3832b2a076deebfed66` |
| family | `outcomes` |
| name | `incident_kind` |
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
| frozen_signature | `CX-01.3:CX-61` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.incident_kind]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "source": "combining-rules.json items[core.incident_kind]; ruling activity-27, all-04", "order": ["quantified", "qualitative", "discontinuation_uncertain", "none_reported", "not_documented", "unknown"]}` |
| translation_v25 | `{"column": "reported_incidents", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[24]"}` |

### Instruction

Does the page report an incident with this activity, such as an error, failure or controversy, and if so, what kind?

### Entailment label

reported incident

### Values

#### `quantified`

The page reports an incident with this activity and gives a measure or number for it.

Entailment label: an incident given with a measure or number

#### `qualitative`

The page reports an incident with this activity in words only, with no measure.

Entailment label: an incident described in words only

#### `none_reported`

The page reports no incident with this activity.

Entailment label: none reported

#### `discontinuation_uncertain`

The page suggests that this activity may have been ended, cancelled or suspended, but does not confirm it.

Entailment label: a possible but unconfirmed end of the activity

### Rules

1. `items/core.incident_kind/rules/0`

Asked about this activity only, once for results and once for incidents. The answer says both whether the page reports one and what kind; the text of the result or incident is extracted only when the answer is not `none_reported`. The incident question also offers `discontinuation_uncertain`.

2. `items/core.incident_kind/rules/1`

Retire flags that just mirror a column; keep 'identity unresolved' and 'stage ambiguous', and fold 'discontinuation uncertain' into the incident question as a value instead of a separate question.

3. `items/core.incident_kind/rules/2`

`discontinuation_uncertain` (incident item only)

4. `items/core.incident_kind/rules/3`

The incident question ignores stops unless a problem is reported.

## `core.reported_outcomes`
<!-- item: core.reported_outcomes sha256: b8966f48a7aaa47f305aa79f349549b07b42f1f878241510f6e3cdc80550e6b4 -->

| Field | Value |
|---|---|
| item hash | `b8966f48a7aaa47f305aa79f349549b07b42f1f878241510f6e3cdc80550e6b4` |
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
| status | `signed` |
| gate | `{"item": "core.outcome_kind", "values": ["quantified", "qualitative"], "as_ruled": "not none_reported"}` |
| long_page_rule | `combined_list` |
| translation_v25 | `{"column": "reported_outcomes", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[25]"}` |

### Instruction

Documented performance claims. Only record if explicitly stated. Never infer.

## `core.reported_incidents`
<!-- item: core.reported_incidents sha256: beed4c12c06a509a8abebfdbfae91d3457c4a9524e3308533f371dc4c0d073d2 -->

| Field | Value |
|---|---|
| item hash | `beed4c12c06a509a8abebfdbfae91d3457c4a9524e3308533f371dc4c0d073d2` |
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
| status | `signed` |
| gate | `{"item": "core.incident_kind", "values": ["quantified", "qualitative", "discontinuation_uncertain"], "as_ruled": "not none_reported"}` |
| long_page_rule | `combined_list` |
| translation_v25 | `{"column": "reported_incidents", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[26]"}` |

### Instruction

Documented errors, failures, or controversies. Only record if explicitly stated.

## `core.evaluation_documented`
<!-- item: core.evaluation_documented sha256: 04b649f49a72fd77cbec33e3669e421e7153302044dab5fe06ec6878eff0a0ee -->

| Field | Value |
|---|---|
| item hash | `04b649f49a72fd77cbec33e3669e421e7153302044dab5fe06ec6878eff0a0ee` |
| family | `evaluation` |
| name | `evaluation_documented` |
| level | `activity`, `page` |
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
| frozen_signature | `CX-01.3:CX-30..CX-40` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "applicability.json cells[item=core.evaluation_documented]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "priority_order", "order": ["results_reported", "conducted_no_results", "required_or_planned", "unclear", "not_documented", "unknown"], "source": "table order (CX §11.1); `unknown` placed after `not_documented` per all-04 b"}` |
| translation_v25 | `new` |

### Instruction

Does this page document an evaluation of this AI activity?

### Entailment label

evaluation

### Values

#### `results_reported`

The page states that this activity was tested, evaluated, audited or monitored **and** reports a result (a metric, a finding or a conclusion).

Entailment label: carried out, with results reported

#### `conducted_no_results`

The page states that an evaluation, test, audit, pilot review or monitoring took place or is in place, but reports no result.

Entailment label: carried out, with no results reported

#### `required_or_planned`

The page states that an evaluation is required (by a rule) or planned, with no evidence that it has happened. A policy finding that requires evaluation of AI tools takes this value.

Entailment label: required or planned

#### `unclear`

The page makes an evaluative statement, but its subject, or whether it concerns this AI activity, cannot be settled. An evaluation clearly of a different tool or activity is `not_documented`, not `unclear`.

Entailment label: mentioned, but not clearly about this activity

### Rules

1. `items/core.evaluation_documented/rules/0`

A requirement to carry out a risk or impact assessment is **not** `required_or_planned`; it belongs to `has_risk_assessment` alone.

2. `items/core.evaluation_documented/rules/1`

A clause requiring periodic review of the AI policy itself is `not_documented`, unless it requires testing, monitoring or evaluation of AI tools or their outputs; then it counts as `required_or_planned`. This includes any policy with an AI section (e.g. a general IT policy).

3. `items/core.evaluation_documented/rules/2`

A required pre-use review that mixes fitness-for-purpose with security or compliance checks counts as `required_or_planned`. A pure risk or impact assessment requirement stays under `has_risk_assessment`.

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

(1) An agency blog: "after a three-month trial, 78% of staff said the assistant saved time" → `results_reported`. (2) Minutes: "the pilot is being reviewed by IT" → `conducted_no_results`. (3) A guidance memo: "all AI tools must be tested before deployment" → `required_or_planned` on the policy finding. (4) A press release: "the chatbot has answered 40,000 questions" → `not_documented` (a usage count with no evaluation described). (5) A vendor case study: "accuracy improved 30%" with no named evaluator → `not_documented`.

10. `items/core.evaluation_documented/rules/9`

The page states that an evaluation is required (by a rule) or planned, with no evidence that it has happened. A policy that requires evaluation of AI tools takes this value. A clause requiring periodic review of the AI policy itself is NOT this value unless it requires testing, monitoring or evaluation of AI tools or their outputs. A requirement to carry out a risk or impact assessment is NOT this value.

11. `items/core.evaluation_documented/rules/10`

The page has no evaluation statement about this activity.

## `core.evaluation_type_pre_deployment_testing`
<!-- item: core.evaluation_type_pre_deployment_testing sha256: c3706c6d9bebdf6e901dc45dce655bbb948818fd9883ad5bf64ea58eaa7076a5 -->

| Field | Value |
|---|---|
| item hash | `c3706c6d9bebdf6e901dc45dce655bbb948818fd9883ad5bf64ea58eaa7076a5` |
| family | `evaluation` |
| name | `evaluation_type_pre_deployment_testing` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `5` |
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
| status | `signed` |
| gate | `{"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Instruction

The page documents an evaluation of this AI activity, or a requirement or plan for one. Does it document an evaluation of this type: testing before deployment? Rules: consider only evaluation of THIS activity and its own tool; an evaluation of a different tool or activity does not count. A trial run or reported by a vendor counts only if the institution or an independent body is named as the evaluator. Starting or announcing a pilot is not an evaluation. A risk or impact assessment is not an evaluation unless it reports testing or measured performance. A performance figure counts only if the page describes the evaluation behind it.

### Entailment label

evaluation

### Values

#### `yes`

The page documents an evaluation of this type for the activity: testing before deployment.

Entailment label: includes testing before deployment

#### `no`

The page does not document an evaluation of this type (testing before deployment) for the activity.

Entailment label: does not include testing before deployment

### Rules

1. `items/core.evaluation_type_pre_deployment_testing/rules/0`

Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.

## `core.evaluation_type_pilot_evaluation`
<!-- item: core.evaluation_type_pilot_evaluation sha256: 1099159d5be8b73c936cf133d62882c92b016ba20959f5eb29a124fbf02f5796 -->

| Field | Value |
|---|---|
| item hash | `1099159d5be8b73c936cf133d62882c92b016ba20959f5eb29a124fbf02f5796` |
| family | `evaluation` |
| name | `evaluation_type_pilot_evaluation` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `5` |
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
| status | `signed` |
| gate | `{"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Instruction

The page documents an evaluation of this AI activity, or a requirement or plan for one. Does it document an evaluation of this type: evaluation of a pilot or trial? Rules: consider only evaluation of THIS activity and its own tool; an evaluation of a different tool or activity does not count. A trial run or reported by a vendor counts only if the institution or an independent body is named as the evaluator. Starting or announcing a pilot is not an evaluation. A risk or impact assessment is not an evaluation unless it reports testing or measured performance. A performance figure counts only if the page describes the evaluation behind it.

### Entailment label

evaluation

### Values

#### `yes`

The page documents an evaluation of this type for the activity: evaluation of a pilot or trial.

Entailment label: includes evaluation of a pilot or trial

#### `no`

The page does not document an evaluation of this type (evaluation of a pilot or trial) for the activity.

Entailment label: does not include evaluation of a pilot or trial

### Rules

1. `items/core.evaluation_type_pilot_evaluation/rules/0`

Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.

## `core.evaluation_type_independent_audit`
<!-- item: core.evaluation_type_independent_audit sha256: e0766d1413eca8d14e85c1e33b0b6605f3bef4b81795fded86c169ee7a0ceedb -->

| Field | Value |
|---|---|
| item hash | `e0766d1413eca8d14e85c1e33b0b6605f3bef4b81795fded86c169ee7a0ceedb` |
| family | `evaluation` |
| name | `evaluation_type_independent_audit` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `5` |
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
| status | `signed` |
| gate | `{"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Instruction

The page documents an evaluation of this AI activity, or a requirement or plan for one. Does it document an evaluation of this type: an audit or evaluation by an independent body? Rules: consider only evaluation of THIS activity and its own tool; an evaluation of a different tool or activity does not count. A trial run or reported by a vendor counts only if the institution or an independent body is named as the evaluator. Starting or announcing a pilot is not an evaluation. A risk or impact assessment is not an evaluation unless it reports testing or measured performance. A performance figure counts only if the page describes the evaluation behind it.

### Entailment label

evaluation

### Values

#### `yes`

The page documents an evaluation of this type for the activity: an audit or evaluation by an independent body.

Entailment label: includes an audit or evaluation by an independent body

#### `no`

The page does not document an evaluation of this type (an audit or evaluation by an independent body) for the activity.

Entailment label: does not include an audit or evaluation by an independent body

### Rules

1. `items/core.evaluation_type_independent_audit/rules/0`

Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.

## `core.evaluation_type_ongoing_monitoring`
<!-- item: core.evaluation_type_ongoing_monitoring sha256: 71286dc8612e46e34aaf558f5927e29a38add37c5720508ac8f122e7d95bf290 -->

| Field | Value |
|---|---|
| item hash | `71286dc8612e46e34aaf558f5927e29a38add37c5720508ac8f122e7d95bf290` |
| family | `evaluation` |
| name | `evaluation_type_ongoing_monitoring` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `5` |
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
| status | `signed` |
| gate | `{"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Instruction

The page documents an evaluation of this AI activity, or a requirement or plan for one. Does it document an evaluation of this type: ongoing monitoring of the tool in use? Rules: consider only evaluation of THIS activity and its own tool; an evaluation of a different tool or activity does not count. A trial run or reported by a vendor counts only if the institution or an independent body is named as the evaluator. Starting or announcing a pilot is not an evaluation. A risk or impact assessment is not an evaluation unless it reports testing or measured performance. A performance figure counts only if the page describes the evaluation behind it.

### Entailment label

evaluation

### Values

#### `yes`

The page documents an evaluation of this type for the activity: ongoing monitoring of the tool in use.

Entailment label: includes ongoing monitoring of the tool in use

#### `no`

The page does not document an evaluation of this type (ongoing monitoring of the tool in use) for the activity.

Entailment label: does not include ongoing monitoring of the tool in use

### Rules

1. `items/core.evaluation_type_ongoing_monitoring/rules/0`

Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.

## `core.evaluation_type_user_feedback`
<!-- item: core.evaluation_type_user_feedback sha256: dea28705e59122ac47606e82ec2a32a190ef8ed19a8272c91ed2f8e280f675dc -->

| Field | Value |
|---|---|
| item hash | `dea28705e59122ac47606e82ec2a32a190ef8ed19a8272c91ed2f8e280f675dc` |
| family | `evaluation` |
| name | `evaluation_type_user_feedback` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `5` |
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
| status | `signed` |
| gate | `{"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Instruction

The page documents an evaluation of this AI activity, or a requirement or plan for one. Does it document an evaluation of this type: user feedback or satisfaction surveys? Rules: consider only evaluation of THIS activity and its own tool; an evaluation of a different tool or activity does not count. A trial run or reported by a vendor counts only if the institution or an independent body is named as the evaluator. Starting or announcing a pilot is not an evaluation. A risk or impact assessment is not an evaluation unless it reports testing or measured performance. A performance figure counts only if the page describes the evaluation behind it.

### Entailment label

evaluation

### Values

#### `yes`

The page documents an evaluation of this type for the activity: user feedback or satisfaction surveys.

Entailment label: includes user feedback or satisfaction surveys

#### `no`

The page does not document an evaluation of this type (user feedback or satisfaction surveys) for the activity.

Entailment label: does not include user feedback or satisfaction surveys

### Rules

1. `items/core.evaluation_type_user_feedback/rules/0`

Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.

## `core.evaluation_type_bias_or_safety_testing`
<!-- item: core.evaluation_type_bias_or_safety_testing sha256: b1d0421cf3637b33abd41b5a668afff5cb9352b61c14e809e26aca6c6d877fc2 -->

| Field | Value |
|---|---|
| item hash | `b1d0421cf3637b33abd41b5a668afff5cb9352b61c14e809e26aca6c6d877fc2` |
| family | `evaluation` |
| name | `evaluation_type_bias_or_safety_testing` |
| level | `activity`, `page` |
| pipelines | `web_extract` |
| linkage | `jev_choice` |
| coder | `classifier` |
| pass | `2` |
| round | `5` |
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
| status | `signed` |
| gate | `{"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"}` |
| long_page_rule | `any_yes` |
| translation_v25 | `new` |

### Instruction

The page documents an evaluation of this AI activity, or a requirement or plan for one. Does it document an evaluation of this type: bias, fairness or safety testing? Rules: consider only evaluation of THIS activity and its own tool; an evaluation of a different tool or activity does not count. A trial run or reported by a vendor counts only if the institution or an independent body is named as the evaluator. Starting or announcing a pilot is not an evaluation. A risk or impact assessment is not an evaluation unless it reports testing or measured performance. A performance figure counts only if the page describes the evaluation behind it.

### Entailment label

evaluation

### Values

#### `yes`

The page documents an evaluation of this type for the activity: bias, fairness or safety testing.

Entailment label: includes bias, fairness or safety testing

#### `no`

The page does not document an evaluation of this type (bias, fairness or safety testing) for the activity.

Entailment label: does not include bias, fairness or safety testing

### Rules

1. `items/core.evaluation_type_bias_or_safety_testing/rules/0`

Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.

## `core.stage_as_of`
<!-- item: core.stage_as_of sha256: 9bda6a142f0941947e27263b11e1f023f120627db2fc9b3ead3e6b15bb99fa76 -->

| Field | Value |
|---|---|
| item hash | `9bda6a142f0941947e27263b11e1f023f120627db2fc9b3ead3e6b15bb99fa76` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.stage_as_of/rules/0`

stage_as_of = source_publication_date if supported, else the page's latest stated date for the activity, else the access date; plus `stage_as_of_basis`.

## `core.stage_as_of_basis`
<!-- item: core.stage_as_of_basis sha256: c4b647d7928f513a6a95f9d65e11fd351d23b597e78d12fed5a731cd9783d3d7 -->

| Field | Value |
|---|---|
| item hash | `c4b647d7928f513a6a95f9d65e11fd351d23b597e78d12fed5a731cd9783d3d7` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Values

#### `publication`

stage_as_of is the supported source_publication_date.

#### `stated`

stage_as_of is the page's latest stated date for the activity.

#### `access`

stage_as_of is the access date.

### Rules

1. `items/core.stage_as_of_basis/rules/0`

stage_as_of = source_publication_date if supported, else the page's latest stated date for the activity, else the access date; plus `stage_as_of_basis`.

2. `items/core.stage_as_of_basis/rules/1`

When the observations carrying a merged activity's `stage_as_of` reach that date by different steps, `stage_as_of_basis` takes the first of them in the order `publication`, `stated`, `access`.

## `core.permanent_pilot`
<!-- item: core.permanent_pilot sha256: 2c15465e82f9f7f3ea29dfce9ac4cb3f9f0629345bf9880d12dfebfe45a46748 -->

| Field | Value |
|---|---|
| item hash | `2c15465e82f9f7f3ea29dfce9ac4cb3f9f0629345bf9880d12dfebfe45a46748` |
| family | `activity_typing` |
| name | `permanent_pilot` |
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
| status | `signed` |
| gate | `{"item": "core.activity_type", "values": ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"], "table": "applicability keyed on activity_type (r2#8)", "rule": "core.rule.applicability_table", "source": "same gate as core.adoption_stage (RC-D-025 A2): applicability.json cells[item=core.adoption_stage]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}` |
| long_page_rule | `{"rule": "any_yes"}` |
| translation_v25 | `new` |

### Instruction

Does the page describe this activity as a pilot that has run for more than 12 months and serves its full intended user base?

### Entailment label

status as a long-running pilot

### Values

#### `yes`

The same passage describes it as a pilot, running for more than 12 months, and serving the full intended user base.

Entailment label: a pilot running over 12 months for its full intended user base

#### `no`

The page gives evidence that the activity is not such a pilot (for example a pilot under 12 months old, or limited to part of its intended users).

Entailment label: not such a long-running, full-scale pilot

### Rules

1. `items/core.permanent_pilot/rules/0`

A supported `yes` sets the final `adoption_stage` to `production` only when the stage answer is `pilot` or `production`; for any other stage the classifier's stage answer is kept and this flag is kept as coded.

2. `items/core.permanent_pilot/rules/1`

The page does not let this be settled.

## `core.vendor_claim_only`
<!-- item: core.vendor_claim_only sha256: 55b92f0eee7ff1506210ef663c3839c5a4a1d7cd690bd36e3ae5a247ae19b536 -->

| Field | Value |
|---|---|
| item hash | `55b92f0eee7ff1506210ef663c3839c5a4a1d7cd690bd36e3ae5a247ae19b536` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.vendor_claim_only/rules/0`

`yes` when every source supporting the activity has source type `vendor`; `unknown` when any of them has no source type; otherwise `no`. A page typed automatically (official domain or archive address) has a type and is not `vendor`.

## `core.unit_credit`
<!-- item: core.unit_credit sha256: 300296a33913ac5bd7c8163ea1da222da1a176e78591a22447b9d84049b94786 -->

| Field | Value |
|---|---|
| item hash | `300296a33913ac5bd7c8163ea1da222da1a176e78591a22447b9d84049b94786` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.unit_credit/rules/0`

Keep your rule and add a yes/no column marking credit received through a unit, so analyses can remove duplicates; the data dictionary explains it.

## `core.uncertainty_flags`
<!-- item: core.uncertainty_flags sha256: 634a01d4f82fbe62c12870d25ab0de60b094c8cb0c2a26f3a688451d2c2dbd76 -->

| Field | Value |
|---|---|
| item hash | `634a01d4f82fbe62c12870d25ab0de60b094c8cb0c2a26f3a688451d2c2dbd76` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `{"column": "uncertainty_flags", "origin": "PI 2026-10-30 \"all review approved\"; agent draft r4 translation", "source": "drafts/translation-r4.json entries[27]"}` |

### Rules

1. `items/core.uncertainty_flags/rules/0`

Two flags. `stage_ambiguous`: the stated adoption-stage answers differ across parts or pooled observations before combining; missing answers are ignored. `identity_unresolved`: a Stage 6 cross-page relation is `unresolved`; it is a row flag of the left-hand activity of that relation. A support node carries only its own code's flags; an activity row carries the union. `discontinuation_uncertain` is a value of the incident question, not a flag. No flag is defined for AI-text evidence.

## `core.support_entailment`
<!-- item: core.support_entailment sha256: 788c0223c3a3d3baa7fca234c08dca065d53d4f6642a71901d8a5f480a539075 -->

| Field | Value |
|---|---|
| item hash | `788c0223c3a3d3baa7fca234c08dca065d53d4f6642a71901d8a5f480a539075` |
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
| threshold_by_checked_item | `{"core.page_verdict": 0.6, "core.activity_type": 0.8, "core.action_type": 0.6}` |
| missing_tokens | `not_asked`, `not_documented`, `unknown` |
| input_text | `main` |
| visibility | `internal` |
| frozen_signature | `none` |
| version_introduced | `2.7` |
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Instruction

Does this text state or clearly show that the <field label> of the activity "<activity name>" is "<value label>"?

### Instruction (page form)

Does this text state or clearly show that the <field label> of the page is "<value label>"?

### Label rules

The field label is the checked item's `entailment_label` and the value label its value's `entailment_label` (for the role part of `observed_actor_relationship`, `values.part_entailment_labels` and the role values' labels). For the three year items the value label is the calendar (CE) year in four ASCII digits after conversion, for example "2024" for "FY24". Items coded per page or per source (`content_contact_details`, `content_contact_named`, `content_data`, `disclosure_form`, `disclosure_scope`, `page_complete`, `page_verdict`, `source_type`) use the page form `instruction_page`; every other item uses the activity form, naming the activity (for a two-record relation, the first record's activity).

### Values

#### `true`

The quoted text states or clearly shows that the field has the given value.

#### `false`

The quoted text does not state or clearly show that the field has the given value. The answer's support status becomes 'downgraded: quote does not state the value'.

### Rules

1. `items/core.support_entailment/rules/0`

The check sees the quote plus 200 characters on each side, clipped to the producing part, and asks: 'Does this text state or clearly show that the <field label> of the activity "<activity name>" is "<value label>"?' (page-level items use the page form). The answer fails when it is `false`, when there is no answer or no probability, or when its probability is below the checked item's bar (`threshold_by_checked_item`; otherwise the item's `threshold`). A failed answer gives the support status `downgraded_quote_not_stating_value`, and the value takes the checked item's downgrade target.

## `core.support_status`
<!-- item: core.support_status sha256: 9922a0d04275fadb3ec1f0e76d1c4af19e86bca6b9f7733bf590dbb74fb86154 -->

| Field | Value |
|---|---|
| item hash | `9922a0d04275fadb3ec1f0e76d1c4af19e86bca6b9f7733bf590dbb74fb86154` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.support_status/rules/0`

Support-status values: `supported` / `downgraded_no_quote` / `downgraded_low_confidence` / `downgraded_quote_not_stating_value` / `set_by_rule`, for every value a rule fixed, including "not asked" and `_NA_` (exempt from the no-quote downgrade; record-02 a; O12) / `not_required`, for `not_documented`, `unknown`, `no`, `none_reported`, `none_documented`, `none`, `unclear`, `unresolved`, `not_an_activity`, `no_generative_signal` and negative page verdicts.

2. `items/core.support_status/rules/1`

`not_required`: the answer needs no supporting quote by its nature. It is given to `not_documented`, `unknown`, `no`, `none_reported`, `none_documented`, `none`, `unclear`, `unresolved`, `not_an_activity`, `no_generative_signal` and negative page verdicts.

3. `items/core.support_status/rules/2`

A second reason item

## `core.supporting_text`
<!-- item: core.supporting_text sha256: ed7c6f3e92f25fcdd9f5220099088627f3b129dc5cefbe68e94ab2020fdcd517 -->

| Field | Value |
|---|---|
| item hash | `ed7c6f3e92f25fcdd9f5220099088627f3b129dc5cefbe68e94ab2020fdcd517` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.supporting_text/rules/0`

For every classifier code on a page or activity, the quote step copies the verbatim supporting text from the page. It sees the chosen answer for the field it quotes and copies the text that supports it; it may also see that a gate is not `none`. Each supporting text (a quote, a link passage or a field's supporting text) is at most 200 characters; a longer one is kept whole and flagged. The quote step runs for every activity, including items the applicability table skips; those copies are kept internally, and the item is published as "not asked". The GenAI mechanism basis and the outcome and incident kinds get quotes relevant to the field. The quote step copies the scale number verbatim and the classifier picks the unit; the quote step codes the publication date, checked against the stored text. A second check asks whether each quote states the coded value (`core.support_entailment`).

2. `items/core.supporting_text/rules/1`

Supporting text is checked against the stored page text by fuzzy match; a quote below the match threshold counts as no supporting text.

3. `items/core.supporting_text/rules/2`

Supporting text is published with the code it supports. The API carries the full text; the website shows it up to 200 characters, with a marker and access to the full text.

4. `items/core.supporting_text/rules/3`

Published supporting quotes stay verbatim, with no masking.

## `core.has_genai_activity`
<!-- item: core.has_genai_activity sha256: a030dc0edb4f7abfaa51b66a8c95dd8c750f89448ee1338f41ab9f1902b30043 -->

| Field | Value |
|---|---|
| item hash | `a030dc0edb4f7abfaa51b66a8c95dd8c750f89448ee1338f41ab9f1902b30043` |
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

Institution-level consolidation (Stage 6): explicit relations are decided before observations merge; distinct or unresolved relations never merge; the institution gets `no` only with complete supplied context and no unresolved signal. An institution whose reviewed pages are all negative at confidence ≥ 0.8 gets `no` directly; the complete-context rule blocks `no` only when an unresolved signal remains (a negative page below the bar counts as one). The truth table: `background_only` pages may sit in the institution `no` set; any downgraded page counts as unresolved, except a `confirms_activity` page counted under the page-verdict roll-up; the bar is the chosen answer's probability ≥ 0.8; `yes` can come from any pipeline, `no` from web pages only, and AI-text results never count; any supported AI purchase record can give `yes`, while the evidence tier still shows it as commitment; `not_assessable` is set mechanically only and does not block `no`. Stage 6 also asks the cross-page relation with the shared relation list, including `governs`; codes merged activities on their pooled evidence, split into parts when too long; and sets the evidence tier, the review depth (nine verdict counts per pipeline), activity confidence and the unit-credit flag. `unresolved` stays a coding value and is reported as `unknown` in published summaries. `not_assessable` stays out of the institution-rate base.

2. `items/core.has_genai_activity/rules/1`

Page-verdict roll-up: a reviewed, unfailed web page whose final verdict is `confirms_activity`, whose verdict support status is `downgraded_quote_not_stating_value` or `downgraded_no_quote`, whose chosen probability passes the classifier verdict bar, and which has at least one supported activity observation on the same page, counts as a supported `confirms_activity` page. `downgraded_low_confidence` is never rescued and a page with no supported activity is never rescued. The verdict is never rewritten and keeps its support status; the source row's `confidence` stays `low`.

3. `items/core.has_genai_activity/rules/2`

Supported activity observation: an activity observation is supported when its final `activity_type` or its final `action_type` has support status `supported`. A value that is gated out, set by rule, downgraded or missing is not supported. The other of the two may be `unknown`.

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
<!-- item: core.evidence_tier sha256: 5638c7694144b5900a5bbce6ece02b2ffcedc7a5cc04af9ef25ed7c385717b3c -->

| Field | Value |
|---|---|
| item hash | `5638c7694144b5900a5bbce6ece02b2ffcedc7a5cc04af9ef25ed7c385717b3c` |
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

Published beside `has_genai_activity`: the highest tier any published activity reaches. `documented_use`: action type `deployment` or `program` at stage `pilot`, `production` or `discontinued`. `documented_commitment`: stage `announced`, or purchase status `tender_or_rfp`, `award_or_contract` or `payment_or_subscription`. `governance_or_training_only`: action type `governance` or `staff_training`. `proposal_only`: stage `proposed`. An activity that meets none of these is `unclear`. With no published activity, the tier is `none_found` when `has_genai_activity` is `no`, otherwise `unclear`.

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

## `core.language_coverage`
<!-- item: core.language_coverage sha256: f05f522f2bc12009427b791952760892e5ccdc368a5799e3df58c29dff197b51 -->

| Field | Value |
|---|---|
| item hash | `f05f522f2bc12009427b791952760892e5ccdc368a5799e3df58c29dff197b51` |
| family | `provenance` |
| name | `language_coverage` |
| level | `row` |
| pipelines | `procurement`, `ai_text` |
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

1. `items/core.language_coverage/rules/0`

Defined with the language-readiness bar

2. `items/core.language_coverage/rules/1`

AI-text flags fold into the main list, the language-barrier flag is dropped everywhere, and language coverage is carried by the multilingual subproject's item.

## `core.observed_actor_role`
<!-- item: core.observed_actor_role sha256: 810963929241da559892fb090d147f5ce543f0a47569f9503b7bcd4c0a79d208 -->

| Field | Value |
|---|---|
| item hash | `810963929241da559892fb090d147f5ce543f0a47569f9503b7bcd4c0a79d208` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `{"rule": "highest_probability"}` |
| translation_v25 | `new` |

### Instruction

What role does the body that the page shows acting in this activity play in it?

### Entailment label

role of the body acting in it

### Values

#### `institutional_actor`

The actor carries out or adopts the activity (a tool, pilot, training or programme) as an institution. For a policy, rule or guidance the actor issued, choose issuer.

Entailment label: carrying it out as an institution

#### `issuer`

The actor issued the policy, rule, guidance or document that the activity is.

Entailment label: the issuer of the rule or document

#### `participant`

The actor takes part in an activity that someone else runs.

Entailment label: a participant in an activity someone else runs

#### `external_speaker`

The actor speaks or presents about AI, for example at an event, without carrying out the activity.

Entailment label: a speaker who does not carry it out

#### `service_provider`

The actor supplies the tool or service, as a vendor, contractor or developer.

Entailment label: the supplier of the tool or service

#### `event_host`

The actor hosts or organises an event about AI.

Entailment label: the host of an event about AI

### Rules

1. `items/core.observed_actor_role/rules/0`

This answer is kept for internal checks and not published.

2. `items/core.observed_actor_role/rules/1`

Only `institutional_actor`, `issuer` and `participant` count as the actor taking part in the activity; `external_speaker`, `service_provider` and `event_host` do not.

3. `items/core.observed_actor_role/rules/2`

not_documented: the page is silent.

## `core.date_upper_bound`
<!-- item: core.date_upper_bound sha256: 227b575cb825948691e2a44a969205daa7339368f4c50df23b10ef61d1339693 -->

| Field | Value |
|---|---|
| item hash | `227b575cb825948691e2a44a969205daa7339368f4c50df23b10ef61d1339693` |
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
| status | `signed` |
| gate | `none` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.date_upper_bound/rules/0`

add a yes/no note "this date is an upper bound".

## `core.support_rule_name`
<!-- item: core.support_rule_name sha256: 93a31f186f55ddcc978d2175e796da477de173bfd8df4a980a83e134f7442ac5 -->

| Field | Value |
|---|---|
| item hash | `93a31f186f55ddcc978d2175e796da477de173bfd8df4a980a83e134f7442ac5` |
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
| status | `signed` |
| gate | `{"item": "core.support_status", "values": ["set_by_rule"], "gated_out_value": "empty (record-01 a wording)"}` |
| long_page_rule | `none` |
| translation_v25 | `new` |

### Rules

1. `items/core.support_rule_name/rules/0`

Add a rule-name item, empty unless the status is "set by rule".

## `core.support_status_second_reason`
<!-- item: core.support_status_second_reason sha256: 789e41d0caa0aa77d9911763f463a01683c667b3f7c1cf1e233910eb832938ac -->

| Field | Value |
|---|---|
| item hash | `789e41d0caa0aa77d9911763f463a01683c667b3f7c1cf1e233910eb832938ac` |
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
| status | `signed` |
| gate | `none` |
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
