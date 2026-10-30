# G3O codebook 2.7 — final draft for approval

Built from `codebook/codebook.yaml`, sha256 `9ddf5a093ab836ee79d95ab04f70602ce1361b2db07512e14d9014f4b9d2cd8e`. Not signed; release label and version fields are set at sign-off.

This is the whole codebook for release 2.7 as it would be signed: 109 items in five sections, then the shared lists and rules. Every text is the approved wording; the 13 proposed changes listed first are the only text you have not yet seen. Changed text is highlighted where it appears.

## What's new since your last approval (proposed changes, pending your approval)

1. **Shared participation: does the link merge the two activities?.** The drafted meaning of "shared participation" (within a page and across pages) had no source, and nothing said whether the two passages or records become one activity. *Proposed:* They are one activity and merge; the link needs at least two bodies named as taking part, with a quote. (confidence medium)
2. **"Not an activity" when links are coded per pair.** The value describes one passage, but within-page links are now coded per pair of passages. *Proposed:* In a pair, use it when either passage is not an activity; no other link is coded for that pair. (confidence medium)
3. **Role values "unit" and "joint" next to the relationship values.** The role list of the searched institution has "unit" and "joint", which look like the relationship values "unit of institution" and "joint participant"; no text defined them. *Proposed:* No change: keep both roles with the approved definitions. (confidence low)
4. **Which observed-actor roles count as taking part.** The six roles of the observed actor came only as code names. The approved definitions read the names; the ruling says "code it as before", and version 2.6 also said which roles count as taking part. *Proposed:* Keep the approved definitions and add the version 2.6 rule on which roles count as taking part. (confidence medium)
5. **The second reason can only be low certainty.** Under the approved check order (quote first, then the 0.8 bar), a failed quote check is always the main reason, so only "low certainty" can be a second reason; two of the three approved codes never occur. *Proposed:* Keep the three approved codes and say that only low certainty can occur as a second reason. (confidence medium)
6. **Reserved missing labels used as answer codes on 17 items.** Seventeen items list `unknown` (12) or `not_documented` (5) among their answer codes, but these are reserved missing labels; the approved item template forbids an answer code that equals one (check 8). *Proposed:* Take the label out of the answer list and keep its item-specific meaning as a rule line on the item. (confidence medium)
7. **Purchase status "none documented" next to the reserved "not documented".** The purchase-status answer `none_documented` (the page shows the activity but no purchase step) is very close to the reserved label `not_documented`. *Proposed:* Keep the ruled code and say that, for this item, a page with no purchase step takes `none_documented`; `not_documented` is not used. (confidence medium)
8. **Rules written twice: keep the plan text in each pair.** The five 'same rule written twice' cards had no approve option, so 'approve all' does not settle them; you asked (P4) to keep one text of each pair. This also removes the role-gate text that appeared twice on the observed-actor relationship. *Proposed:* In each pair keep the plan text (the longer text, which contains the other) and drop the restatement. Dropped: “the role is asked when the relationship is `other`; skipped only when `unresolved`”; “Published as one column: the relationship code, then `:` and the role code when the role i…”; “Inside the institution-level rule both keep their current roles, and `not_assessable` stay…”; “`not_required`, for `not_documented`, `unknown`, `no` and negative page verdicts; `_NA_` t…”; “`not_required`, for `not_documented`, `unknown`, `no` and negative page verdicts; `_NA_` t…”. (confidence medium)
9. **Your sentence for the support status "Not required".** After the 2a cut the option text reads only "Not required". The approved status list says which answers take it. *Proposed:* "`not_required`: the answer needs no supporting quote by its nature. It is given to `not_documented`, `unknown`, `no` and negative page verdicts.". (confidence high)
10. **Remove the 'wording owed' notes inside six texts.** Four plan texts still carry six bracketed notes saying wording is owed (for example "[wording: PI — RC-D-002 row 8: value definitions for the 9 values]"). Your approval of every slot supplies that wording, and the notes would otherwise go into every prompt. *Proposed:* Remove the six notes from the codebook texts. (confidence high)
11. **Remove the superseded version-1.5 text from the verdict rule.** The plan text on the page verdict ends with its superseded history ("v001.5 text: Page-verdict vocabulary has 8 values ..."), which contradicts the 9-value rule before it and would go into every prompt. *Proposed:* Cut the history tail from the codebook text. (confidence high)
12. **Remove planning remarks (costs, version steps, test pages) from rule texts.** Several approved ruling texts end with remarks about what the change costs the project (version steps, re-pilots, test pages, procurement copies). They are not coding rules, and they would go into every prompt. *Proposed:* Cut only the listed remarks; keep every coding rule. (confidence medium)
13. **Remove reference codes from rule texts.** Plan and ruling texts carry reference codes in brackets, for example "(r2#22; activity-16 b; all-11)", and lead-ins such as "RC-D-002 row 8:". They would go into every prompt. *Proposed:* Remove brackets that hold only reference codes, and the 'RC-D-00x row N:' lead-ins at a sentence start; keep every bracket with words in it. (confidence medium)

## What the page says

### page verdict

<sub>core.page_verdict</sub>

**Question.** Code this PAGE for the named institution only, using only what the page says. Does it document a generative-AI activity at this institution? If several values fit, take the first in this order.

**Answer.** one answer

**Answers and their meaning.** - `confirms_activity` — The page documents a specific generative-AI activity AT THIS institution: its own GenAI tool, pilot, policy or guidance on GenAI, procurement, deployment, or institution-directed staff GenAI training. The text must be explicitly generative AI (LLMs, ChatGPT, Copilot, Gemini, AI chatbots, AI-generated content or equivalents) and tied to this institution, not only to a national programme or another body. The activity must be carried out or adopted by the named institution itself. Exclude activity by a parent, higher-level or neighbouring body (e.g. a district, county, regency, region, consortium or city department when the named institution is a village, ward or sub-unit), by a similarly named organisation or company, and pages by vendors that only use the place name. Generic 'AI', 'artificial intelligence', 'smart' systems, automation, analytics, prediction, transcription, translation, image or video recognition, or traditional machine-learning tools do not count unless the page says the tool generates text, images, audio, code or other content, or names a generative product or model (e.g. ChatGPT, Copilot, Gemini, Claude, an LLM, an AI chatbot or AI assistant).
- `ambiguous_genai` — The page mentions AI at this institution, but it cannot be settled whether it is generative AI (e.g. a generic 'AI strategy', 'AI tools', analytics, traditional machine learning).
- `ambiguous_attribution` — The page mentions generative AI, but it cannot be settled whether THIS institution is involved (e.g. a country-wide or regional GenAI initiative without confirmation that this institution takes part, or a page about a similarly named body).
- `other_body` — The page documents a generative-AI activity, but it clearly belongs to a different body, not the named institution: a parent, higher-level or neighbouring body (e.g. a district, county, regency, region, consortium or city department when the named institution is a village, ward or sub-unit), a similarly named organisation or company, or a vendor or marketing page that only uses the place name.
- `event_only` — The only GenAI content is a public-facing event, workshop, seminar, showcase or educational programme, with no documented adoption, procurement, deployment or governance by the institution itself (WS10 D1: not a qualifying activity).
- `background_only` — The page gives only general context (national AI strategy, vendor overview, news about GenAI in general) and documents no activity at this institution.
- `confirms_absence` — v2.5 `confirms_absence` (page states absence; distinct from `no_genai`, no relevant content)
- `no_genai` — The page contains no generative-AI content relevant to this institution.
- `not_assessable` — `not_assessable`, set mechanically when a page was not reviewed, never a classifier answer, not blocking institution `no`, and left out of the base for institution-level rates _[cleaned: change 13]_

**Rules.** - The vocabulary has 9 values: the 8 below plus `not_assessable`, set mechanically when a page was not reviewed, never a classifier answer, not blocking institution `no`, and left out of the base for institution-level rates; in published summaries it is reported as `unknown` and stays a coding value; `page_review_state` keeps only pipeline failures; v2.5 rows stay unconverted and are mapped by the translation table. _[cleaned: change 10, 11, 12, 13]_
- See shared rule: *genai boundary*
- See shared rule: *ws10 event*
- See shared rule: *attribution grain*

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: S3 a
The verdict order for combining long-page parts has two tiers: supported verdicts in the S3 a order, then failed verdicts in the same order. The S3 a order is: confirms_activity, ambiguous_attribution, ambiguous_genai, other_body, event_only, background_only, confirms_absence, no_genai, not_assessable (`not_assessable` last, for completeness only, C1 a). _[cleaned: change 13]_
- tiers: All supported verdicts in the signed order first, then failed verdicts in the same order.

**When several answers fit.** first in order

**Missing labels it can take.** not_assessable (mechanical)

**Coded by; level; published.** classifier; page; public

### disclosure form

<sub>core.disclosure_form</sub>

**Question.** What kind of document is this page?

**Answer.** one answer

**Answers and their meaning.** - `register_cross_institution` — The page is, or is one entry in, a structured list of AI or algorithmic systems kept by a government body, with several entries in a common format (inventory, register, catalogue, algorithmic transparency record in a standard template), **and the list covers more than one institution** (a national or sectoral register, a standard-template record series across agencies).
- `register_single_institution` — As CX-10, but the list covers **one institution only** (e.g. a city's own table of its AI tools).
- `mandated_report` — The page is a document produced to meet a reporting obligation that concerns reporting on AI, algorithms or digital systems, such as a statutory annual-report section or a compliance or transparency report under a named rule.
- `formal_record` — An official one-off document of record from a government body: adopted policy or guidance, legislation, council or board minutes or resolutions, budget documents, procurement notice or award, audit or inspection report, **response to a freedom-of-information request** (CX-01.1, W5 = b).
- `informal_official` — A government body's own communication with no reporting obligation and no standard format: press release, news item, blog, social post, speech, event page, service or FAQ page.
- `third_party` — Not published by a government body: news, vendor, academic, NGO or policy organization. A register entry quoted in a news article is `third_party` (code the page, not what it quotes).

**Rules.** - Any government-kept multi-entry list in a common format counts as a register, including one institution's own list; single-institution and cross-institution registers are separate values (CX-10, CX-10b). `disclosure_scope` (§3) still codes whole-of-government vs multi-institution for cross-institution registers; `register_single_institution` must carry `disclosure_scope` = `single_institution` (QC check).
- The obligation must be named on the page, except that it may be inferred from the document's genre **when the document's title names AI or algorithmic reporting**. Otherwise a statutory annual report or a compliance report under a rule not about AI is `formal_record`. This is the one stated exception to CX-03.
- (1) A city's entry in a national algorithm register describing its chatbot → `register_cross_institution`. (2) A ministry annual-report section headed with the regulation that requires AI-use reporting → `mandated_report`. (3) Council minutes approving a Copilot licence → `formal_record`. (4) A mayor's press release launching a chatbot → `informal_official`. (5) A trade-press article about that chatbot → `third_party`. (6) A city web page that lists its five AI tools in a table it made itself → `register_single_institution`.
- *direction*: Re-word CX-12/13: `mandated_report` only when the obligation concerns reporting on AI, algorithms or digital systems, named on the page; genre inference allowed only for documents whose title names AI/algorithmic reporting. Otherwise statutory annual reports code `formal_record`.
- *classifier_line (mandated_report)*: CX-12/13: a document produced to meet a reporting obligation that concerns reporting on AI, algorithms or digital systems (statutory annual-report section, compliance or transparency report under a rule). The obligation must be named on the page, except that it may be inferred from the document's genre when the document's title names AI or algorithmic reporting. Otherwise a statutory annual report or a compliance report under a rule not about AI is formal_record.
- *direction for CX-13 (wording: final-open W01, in the CX-13 cell)*: Add those reports to the same sentence.
- *missing label unknown: meaning for this item*: The page's kind cannot be determined from its text (e.g. an archived fragment with no header). **[proposed change 6]**

**Long pages: combining the parts.** `first_section`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** classifier; page; public

### disclosure scope

<sub>core.disclosure_scope</sub>

**Answer.** one answer

**Answers and their meaning.** - `whole_of_government` — The listing or document the page belongs to covers institutions across the government (all central agencies, or all units of a level).
- `multi_institution` — It covers several institutions, but not government-wide (a sector, a region, a group of agencies).
- `single_institution` — It covers one institution only.

**Rules.** - Yes, as below.
- Pages whose `disclosure_form` is `register_cross_institution`, `register_single_institution` or `mandated_report`. On other pages the field is not asked and stores the reserved "not asked" label (CX-06).
- *direction*: Ask `disclosure_scope` only when `disclosure_form` in {register_cross_institution, register_single_institution, mandated_report}; otherwise store `_NA_`.
- *missing label unknown: meaning for this item*: Coverage cannot be determined from the page. **[proposed change 6]**

**When it is asked.** 
- item: `core.disclosure_form`
- values: `register_cross_institution`, `register_single_institution`, `mandated_report`

**Long pages: combining the parts.** `first_section`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** classifier; page; public

### page complete

<sub>core.page_complete</sub>

**Question.** 'Does the page refer the reader to another page or document for more information about a GenAI activity it mentions?'

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page refers the reader to another page or document for more information about a GenAI activity it mentions, so the page is incomplete (see the note on the name).
- `no` — The page does not refer the reader elsewhere for more information about any GenAI activity it mentions.

**Rules.** - The first pass also records whether the page holds all available information about every activity it mentions, or links to further pages with information about any of them.
- *direction: note (wording: final-open W04)*: Add a note in the codebook that yes means incomplete.
- *note*: Note: `yes` means incomplete (the page refers the reader onward); the name `page_complete` reads the other way.

**When it is asked.** 
- item: `core.page_verdict`
- values: `confirms_activity`, `ambiguous_genai`, `ambiguous_attribution`, `other_body`, `event_only`

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** classifier; page; public

### content contact named

<sub>core.content_contact_named</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page gives a named person, office or unit as responsible for the activity or for questions about it; a named official with no contact details counts.
- `no` — The page names no person, office or unit as responsible for the activity or for questions about it. Pages whose verdict shows no GenAI also take this value.

**Rules.** - Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.
- *direction*: Pipeline change: store a separate `chrome_text` (header/footer/nav) next to main text, and give jev both for the contact item only.

**When it is asked.** 
- item: `core.page_verdict`
- values: `confirms_activity`, `ambiguous_genai`, `ambiguous_attribution`, `other_body`, `event_only`
- gated out value: `no`
Gate on the five GenAI verdicts, as the data question; pages with no GenAI get 'no'.

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** classifier; page; public

### content contact details

<sub>core.content_contact_details</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page gives contact details anywhere on it: an email address, phone number, postal address or contact form, including press or vendor contacts and site footers.
- `no` — No contact details appear anywhere on the page, including its header and footer. Pages whose verdict shows no GenAI also take this value.

**Rules.** - Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.
- *direction*: Pipeline change: store a separate `chrome_text` (header/footer/nav) next to main text, and give jev both for the contact item only.

**When it is asked.** 
- item: `core.page_verdict`
- values: `confirms_activity`, `ambiguous_genai`, `ambiguous_attribution`, `other_body`, `event_only`
- gated out value: `no`
Gate on the five GenAI verdicts, as the data question; pages with no GenAI get 'no'.

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** classifier; page; public

### content contact

<sub>core.content_contact</sub>

**Answer.** yes or no

**Rules.** - Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; page; public

### content contact emails

<sub>core.content_contact_emails</sub>

**Answer.** list

**Rules.** - When `content_contact` = yes, extract the contact with a deterministic `@` search over the stored main page text, the stored header and footer text and the page's e-mail links (e-mail regex in `pilot/contact.py`, `EMAIL_RE`) and store the list beside the code (`content_contact_emails`), in full and internally only; only the domain part of each address and a count are published. No API call. Not yet in the installed instrument; owed to the back-code engineering card
- Published supporting quotes stay verbatim, with no masking. Contact e-mails are stored in full internally, and only the domain and a count are published.
- *direction*: Store the full list internally; publish only the domain part (and a count), or only role addresses (no personal-name pattern).

**When it is asked.** 
- item: `core.content_contact`
- values: `yes`

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; page; public_derived

### content purpose

<sub>core.content_purpose</sub>

**Answer.** yes or no

**Rules.** - Included: the items in CX-51 and CX-52, each `yes` / `no` (yes = stated on the page). For the items CX-51 and CX-52 mark as derived, `yes` and `no` are derived from the activity codes as they state, with no question. Whether they replace or sit beside T2 is an index-construction choice (exclusivity is reported only, index decision 1 = (b)).
- Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.
- A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question. _[cleaned: change 12]_
- *direction*: Ask `content_*` only on pages with a GenAI-bearing verdict (the five R-003 values); store `_NA_` otherwise; reword to 'about any GenAI activity on the page'.
- *direction (wording: final-open W03, in the CX-51 cell)*: Description items and the data item are also "no" where the verdict shows no GenAI.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; page; public

### content tool or model

<sub>core.content_tool_or_model</sub>

**Answer.** yes or no

**Rules.** - Included: the items in CX-51 and CX-52, each `yes` / `no` (yes = stated on the page). For the items CX-51 and CX-52 mark as derived, `yes` and `no` are derived from the activity codes as they state, with no question. Whether they replace or sit beside T2 is an index-construction choice (exclusivity is reported only, index decision 1 = (b)).
- Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.
- A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question. _[cleaned: change 12]_
- *direction*: Ask `content_*` only on pages with a GenAI-bearing verdict (the five R-003 values); store `_NA_` otherwise; reword to 'about any GenAI activity on the page'.
- *direction (wording: final-open W03, in the CX-51 cell)*: Description items and the data item are also "no" where the verdict shows no GenAI.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; page; public

### content vendor

<sub>core.content_vendor</sub>

**Answer.** yes or no

**Rules.** - Included: the items in CX-51 and CX-52, each `yes` / `no` (yes = stated on the page). For the items CX-51 and CX-52 mark as derived, `yes` and `no` are derived from the activity codes as they state, with no question. Whether they replace or sit beside T2 is an index-construction choice (exclusivity is reported only, index decision 1 = (b)).
- Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.
- A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question. _[cleaned: change 12]_
- *direction*: Ask `content_*` only on pages with a GenAI-bearing verdict (the five R-003 values); store `_NA_` otherwise; reword to 'about any GenAI activity on the page'.
- *direction (wording: final-open W03, in the CX-51 cell)*: Description items and the data item are also "no" where the verdict shows no GenAI.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; page; public

### content data

<sub>core.content_data</sub>

**Question.** Code the source PAGE. Does the page state this about any GenAI activity on the page: the data inputs or data handled are described? yes = stated on the page.

**Answer.** yes or no

**Answers and their meaning.** - `yes` — stated on the page
- `no` — not stated on the page

**Rules.** - Included: the items in CX-51 and CX-52, each `yes` / `no` (yes = stated on the page). For the items CX-51 and CX-52 mark as derived, `yes` and `no` are derived from the activity codes as they state, with no question. Whether they replace or sit beside T2 is an index-construction choice (exclusivity is reported only, index decision 1 = (b)).
- Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.
- *direction*: Ask `content_*` only on pages with a GenAI-bearing verdict (the five R-003 values); store `_NA_` otherwise; reword to 'about any GenAI activity on the page'.
- One page question, asked on GenAI pages.
- Description items and the data item are also "no" where the verdict shows no GenAI.

**When it is asked.** 
- item: `core.page_verdict`
- values: `confirms_activity`, `ambiguous_genai`, `ambiguous_attribution`, `other_body`, `event_only`
- gated out value: `no`

**Long pages: combining the parts.** 
- rule: `any_yes`
- order: `yes`, `no`, `not_documented`, `unknown`
Yes if any part says yes; otherwise no if any part says no; then not_documented, then unknown.

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** classifier; page; public

### content users

<sub>core.content_users</sub>

**Answer.** yes or no

**Rules.** - Included: the items in CX-51 and CX-52, each `yes` / `no` (yes = stated on the page). For the items CX-51 and CX-52 mark as derived, `yes` and `no` are derived from the activity codes as they state, with no question. Whether they replace or sit beside T2 is an index-construction choice (exclusivity is reported only, index decision 1 = (b)).
- Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.
- A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question. _[cleaned: change 12]_
- *direction*: Ask `content_*` only on pages with a GenAI-bearing verdict (the five R-003 values); store `_NA_` otherwise; reword to 'about any GenAI activity on the page'.
- *direction (wording: final-open W03, in the CX-51 cell)*: Description items and the data item are also "no" where the verdict shows no GenAI.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; page; public

### content status date

<sub>core.content_status_date</sub>

**Answer.** yes or no

**Rules.** - Included: the items in CX-51 and CX-52, each `yes` / `no` (yes = stated on the page). For the items CX-51 and CX-52 mark as derived, `yes` and `no` are derived from the activity codes as they state, with no question. Whether they replace or sit beside T2 is an index-construction choice (exclusivity is reported only, index decision 1 = (b)).
- Items: `content_purpose` (what the tool is used for), `content_tool_or_model` (product or model named), `content_vendor` (supplier named), `content_data` (data inputs or data handled described), `content_users` (who uses it or who is affected), `content_status_date` (deployment status or date stated), `content_contact` = yes if either sub-item is yes (CX-01.2, contact wording w4): `content_contact_named` (a named person, office or unit given as responsible for the activity or for questions about it; a named official with no contact details counts, C1 = a) and `content_contact_details` (contact details anywhere on the page: email address, phone number, postal address or contact form, including press or vendor contacts and site footers). `content_purpose`, `content_tool_or_model`, `content_vendor`, `content_users` and `content_status_date` are derived, not asked: each is yes when any activity on the page has a value stated on the page in its matching activity field (purpose: the activity's function items; tool or model: tool or model name; vendor: model developer, stated or looked up, or contracting party; users: `target_users` or `governed_population`; status or date: `adoption_stage` or a year field), otherwise no. `content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.
- A page item is yes when any activity on the page has a stated value in the matching field, with no classifier question. _[cleaned: change 12]_
- *direction*: Ask `content_*` only on pages with a GenAI-bearing verdict (the five R-003 values); store `_NA_` otherwise; reword to 'about any GenAI activity on the page'.
- *direction (wording: final-open W03, in the CX-51 cell)*: Description items and the data item are also "no" where the verdict shows no GenAI.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; page; public

### content human oversight

<sub>core.content_human_oversight</sub>

**Answer.** yes or no

**Rules.** - Safeguard items included, as Kaser does: `content_human_oversight`, `content_risk_assessment`, `content_user_notification`. They are not asked on the page. Each is the page-level member of one safeguard family tagged by level, derived from that safeguard's shared four-answer question asked once per activity (`has_human_oversight`, `has_risk_assessment`, `has_transparency_notice`): `yes` if any activity on the page is `yes`, otherwise `no`. **`content_user_notification` = yes only if the page describes a notice or label telling users they are interacting with GenAI or that content is AI-generated**; a page announcing that the institution uses GenAI is not by itself a notice (CX-01.1, W1 = a). The shared activity question uses this definition. The overlap with governance G1, G3, G4 is reported under R-070.
- One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer. _[cleaned: change 12]_
- *direction*: Ask each safeguard once per (page x activity) in pass 2 and derive both the page-level `content_*` (any activity yes) and the activity-level `has_*` (yes / not_documented) from it.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; page; public

### content risk assessment

<sub>core.content_risk_assessment</sub>

**Answer.** yes or no

**Rules.** - Safeguard items included, as Kaser does: `content_human_oversight`, `content_risk_assessment`, `content_user_notification`. They are not asked on the page. Each is the page-level member of one safeguard family tagged by level, derived from that safeguard's shared four-answer question asked once per activity (`has_human_oversight`, `has_risk_assessment`, `has_transparency_notice`): `yes` if any activity on the page is `yes`, otherwise `no`. **`content_user_notification` = yes only if the page describes a notice or label telling users they are interacting with GenAI or that content is AI-generated**; a page announcing that the institution uses GenAI is not by itself a notice (CX-01.1, W1 = a). The shared activity question uses this definition. The overlap with governance G1, G3, G4 is reported under R-070.
- One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer. _[cleaned: change 12]_
- *direction*: Ask each safeguard once per (page x activity) in pass 2 and derive both the page-level `content_*` (any activity yes) and the activity-level `has_*` (yes / not_documented) from it.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; page; public

### content user notification

<sub>core.content_user_notification</sub>

**Answer.** yes or no

**Rules.** - Safeguard items included, as Kaser does: `content_human_oversight`, `content_risk_assessment`, `content_user_notification`. They are not asked on the page. Each is the page-level member of one safeguard family tagged by level, derived from that safeguard's shared four-answer question asked once per activity (`has_human_oversight`, `has_risk_assessment`, `has_transparency_notice`): `yes` if any activity on the page is `yes`, otherwise `no`. **`content_user_notification` = yes only if the page describes a notice or label telling users they are interacting with GenAI or that content is AI-generated**; a page announcing that the institution uses GenAI is not by itself a notice (CX-01.1, W1 = a). The shared activity question uses this definition. The overlap with governance G1, G3, G4 is reported under R-070.
- One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer. _[cleaned: change 12]_
- *direction*: Ask each safeguard once per (page x activity) in pass 2 and derive both the page-level `content_*` (any activity yes) and the activity-level `has_*` (yes / not_documented) from it.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; page; public

## Each activity on a page

### activity relation within page

<sub>core.activity_segment</sub>

**Question.** The extractor proposes spans; jev answers per span: new distinct activity / same as span k / component of span k / not an activity.

**Answer.** one answer

**Answers and their meaning.** - `same_activity` — The two passages describe the same activity: the same action by the same actor on the same tool or instrument.
- `component_of_program` — The first passage's activity is a named component of the program described in the second. Both stay separate activities, linked.
- `has_component` — The first passage describes a program, and the second passage's activity is one of its named components. Both stay separate activities, linked.
- `shared_participation` — The two passages describe one joint action in which several bodies take part. They are one activity: the two passages are merged. The link needs at least two bodies, each named on the page as taking part, with a quote. **[proposed change 1]**
- `governs` — The first passage's activity is a policy or other governance instrument that sets rules for the activity in the second (for example a policy and a tool it approves). When a pair fits both this link and a component link, this link is used.
- `governed_by` — The second passage's activity is a policy or other governance instrument that sets rules for the activity in the first. When a pair fits both this link and a component link, this link is used.
- `distinct_action` — The two passages describe different activities, and none of the other links applies.
- `unresolved` — The page does not settle whether the two passages describe the same activity or different ones. They are kept separate.
- `not_an_activity` — The passage does not describe an activity as the activity rule defines one. In a pair of passages, it is used when either passage is not an activity; no other link is coded for that pair. **[proposed change 2]**

**Rules.** - See shared rule: *activity unit*
- One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page. _[cleaned: change 13]_
- Add "has component" and "governed by".
- Components stay separate activities; a governing policy is recorded as governing.
- Each pair of passages gets a link.

**Long pages: combining the parts.** 
- rule: `combined_list`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### activity name

<sub>core.activity_name</sub>

**Question.** Short name. Use official name if one exists (e.g., "MyCity Chatbot", "Pair Platform"). Otherwise descriptive (e.g., "Internal Copilot pilot for document drafting").

**Answer.** text

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** quote step; activity; public

### observed actor name

<sub>core.observed_actor_name</sub>

**Answer.** text

**Rules.** - The extractor returns the verbatim actor name and organisational unit. jev Choice gives the relationship (this institution / unit of it / joint participant / other / unresolved) and the role (as v2.6).

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** quote step; activity; internal

### observed actor relationship

<sub>core.observed_actor_relationship</sub>

**Answer.** one answer

**Answers and their meaning.** **structure**: Two linked parts in one item
**relationship**
- `this_institution` — The searched institution itself carries out or adopts the activity.
- `unit_of_institution` — An organisational unit of the searched institution (a department, office or service) carries out the activity; it counts for the institution.
- `joint_participant` — The activity is a joint one, and the page names the searched institution as a participant.
- `other` — The activity belongs to another body: a parent, sibling or neighbouring body, a separate court, board or authority, a similarly named organisation, or a vendor. The searched institution's role is still asked.
- `unresolved` — The page does not settle whose activity this is. The role of the searched institution is not asked.
**searched institution role**
- `contracting_authority` — The searched institution buys or contracts for the tool or service in its own name.
- `beneficiary` — Another body runs or buys the activity for the searched institution, and the page names the searched institution as benefiting.
- `central_purchasing_body` — The searched institution buys or sets up a contract or framework on behalf of other bodies.
- `unit` — The searched institution takes part as a unit of the body that carries out the activity.
- `joint` — The searched institution takes part as one of several joint participants.
**role missing tokens**: `not_asked`, `not_documented`, `unknown`
**role gate**: 
- part: `searched_institution_role`
- keyed on: `relationship`
- not asked when relationship: `unresolved`
- asked when relationship includes: `other`
- gated out value: `not_asked`
the role is asked when the relationship is `other`; skipped only when `unresolved`

**Rules.** - The observed-actor relationship is coded per activity, not per page, with a QC flag on `confirms_activity` pages that have no own / unit / joint activity; the attribution role becomes the second of two linked parts of that relationship (relationship; role of the searched institution, "not asked" when the relationship is unresolved), describes only the searched institution, and counts "beneficiary" only when the page names it; the two parts are published as one column: the relationship code, then `:` and the role code when the role is a real answer, otherwise the relationship code alone; there is no separate published P06 column. The observed actor's own role is kept as a separate internal item, `observed_actor_role`, and not published; the C04 grain rule is kept. _[cleaned: change 13]_
- The role field describes only the searched institution's part in the activity (contracting authority, beneficiary, central purchasing body, unit, joint) and never creates rows for another institution. _[cleaned: change 12]_
- The relationship moves to the per-activity pass; a quality check flags 'confirms activity' pages with no activity by this institution, a unit of it or a joint participant; the attribution role becomes part of the relationship, with 'beneficiary' counting only when the page names it. _[cleaned: change 12]_
- See shared rule: *attribution grain*
- Relationship: this institution, unit, joint participant, other, unresolved, unknown.
- Role of the searched institution: contracting authority, beneficiary, central purchasing body, unit, joint
- A silent page gets "not documented"; a page that mentions the matter but cannot be settled gets "unknown".

**Long pages: combining the parts.** 
- rule: `priority_order`
- role part: the role part is taken from the same part that produced the relationship
- order: `this_institution`, `unit_of_institution`, `joint_participant`, `unresolved`, `other`, `not_documented`, `unknown`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### activity type

<sub>core.activity_type</sub>

**Question.** G3O activity typology. See definitions below.

**Answer.** one answer

**Answers and their meaning.** - `policy_guidance` — Executive orders, agency memos, acceptable-use rules, procurement standards, internal guidance on permissible GenAI tools and data handling.
- `pilot_experiment` — Limited trials, sandboxes, proof-of-concept deployments, or time-bounded experiments.
- `program_initiative` — Cross-agency programs, governance bodies, training programs, or platform rollouts spanning multiple units.
- `internal_operational` — Routine internal use for drafting, summarization, knowledge search, translation, internal helpdesks, or developer tooling.
- `public_facing_service` — Citizen- or business-facing chatbots, service navigation, translation, complaint handling, case triage.

**Rules.** - **Rule: policy vs. pilot.** If an institution has issued a GenAI policy AND is running a pilot, these are **two distinct activities**. Produce separate rows for each (with their respective sources).
- **Rule: country-wide program.** If a national program exists but this specific institution's participation is confirmed by a source, record it as an activity. If participation is NOT confirmed, do NOT record an activity row -- instead produce a row with `has_genai_activity` = `unclear`, `genai_evidence` = `ambiguous`, and flag `institution_attribution`.
- See shared rule: *allowed type action pairs*
- *missing label unknown: meaning for this item*: Evidence confirms a GenAI activity at this institution, but the kind of undertaking is indeterminate from the available sources. Use only after the five kinds above have been considered and none is supportable -- never as a default. **[proposed change 6]**

**Long pages: combining the parts.** 
- rule: `highest_probability`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### action type

<sub>core.action_type</sub>

**Answer.** one answer

**Answers and their meaning.** - `deployment` — The institution puts a GenAI tool to use, or tries one out, for its own work or for the public. The stage and the purchase status are coded separately.
- `governance` — The institution issues or applies a rule on GenAI use: a policy, guidance, approved-tool list, order or standard. A body that sets or oversees such rules also counts.
- `staff_training` — The institution trains its own staff to use GenAI.
- `program` — A container activity whose named components are each their own activity, linked to it. Used only when the page names the components.

**Rules.** - jev Choice per activity: deployment / procurement / governance / staff_training / proposal / program / unknown. (Whether `proposal` is a type or only a stage is a PI choice.)
- Drop 'proposal' and 'procurement' from action type, since stage and procurement status carry those, and define 'program' as a container used only with named components. _[cleaned: change 12]_
- See shared rule: *allowed type action pairs*
- See shared rule: *governance gate*
- *missing label unknown: meaning for this item*: The page mentions the activity but does not let it be settled. **[proposed change 6]**

**Long pages: combining the parts.** 
- rule: `highest_probability`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### adoption stage

<sub>core.adoption_stage</sub>

**Answer.** one answer

**Answers and their meaning.** - `proposed` — Exploratory or hedged intent with no concrete commitment: "considering," "exploring," "studying feasibility," early discussions, unfunded or undated ideas. The text must still be explicitly generative-AI and tied to this institution. No named tool tied to a timeline, no signed MoU or contract, no budget line, no adopted policy.
- `announced` — Publicly stated intent to deploy with a concrete, documented commitment but no evidence of actual use. Includes: MoUs, budget allocations without deployment, strategy timelines.
- `pilot` — Limited deployment: subset of users/departments/use cases; described as trial/pilot/PoC/experiment; time-bounded.
- `production` — Fully operational: available to intended user base, no longer experimental, in routine operations.
- `discontinued` — Previously deployed but explicitly ended, cancelled, or suspended.

**Rules.** - Keep adoption_stage for use; add `procurement_status`: none_documented / tender_or_rfp / award_or_contract / payment_or_subscription / unknown. Payment-only activities get adoption_stage `unknown` plus procurement_status `payment_or_subscription`. _[cleaned: change 12]_
- Purchase records fill the purchase-status field and get an "unknown" adoption stage unless use is shown. The owed contract amendment shrinks to removing purchase language, the procurement rules are amended, and the evidence-tier wording is fixed.
- The §4.3 amendment shrinks to removing purchase language, and no longer waits on procurement's owed text. _[cleaned: change 10, 12, 13]_
- See shared rule: *ws10 proposals*
- **"Permanent pilot" rule:** If described as "pilot" but running >12 months AND serving the full intended user base, code `production`. Note in `scope_notes`: "Described as pilot but operational >12 months with full user base."
- *missing label unknown: meaning for this item*: Evidence confirms GenAI activity exists but stage is indeterminate. **[proposed change 6]**

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `discontinued`, `production`, `pilot`, `announced`, `proposed`, `not_documented`, `unknown`
- permanent pilot across parts: 
  - rule: `within_part_only`
  - known limit: yes
The stage question applies the permanent-pilot rule inside each part. If the facts (over 12 months; full user base) sit in different parts, no part reaches production and the combined stage stays pilot. The codebook states this case.

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### procurement status

<sub>core.procurement_status</sub>

**Answer.** one answer

**Answers and their meaning.** - `none_documented` — The page documents the activity but no purchase step for it.
- `tender_or_rfp` — The institution has issued a call for tenders, a request for proposals or a similar invitation to bid for the tool or service.
- `award_or_contract` — A contract, award or licence agreement for the tool or service is reported as made.
- `payment_or_subscription` — The page records a payment, invoice or subscription for the tool or service. On its own this does not show use; the stage is then unknown unless use is shown.

**Rules.** - Keep adoption_stage for use; add `procurement_status`: none_documented / tender_or_rfp / award_or_contract / payment_or_subscription / unknown. Payment-only activities get adoption_stage `unknown` plus procurement_status `payment_or_subscription`. _[cleaned: change 12]_
- Purchase records fill the purchase-status field and get an "unknown" adoption stage unless use is shown. The owed contract amendment shrinks to removing purchase language, the procurement rules are amended, and the evidence-tier wording is fixed.
- *none_documented against not_documented*: A page that describes the activity but shows no purchase step takes `none_documented`, which is a real answer; `not_documented` is not used for this item. **[proposed change 7]**
- *missing label unknown: meaning for this item*: The page mentions a purchase of the tool or service but does not let it be settled. **[proposed change 6]**

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `payment_or_subscription`, `award_or_contract`, `tender_or_rfp`, `none_documented`, `not_documented`, `unknown`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### model origin

<sub>core.model_origin</sub>

**Answer.** one answer

**Answers and their meaning.** - `commercial` — The model comes from a commercial provider (for example OpenAI, Microsoft, Google or Anthropic) and is used through its product, licence or programming interface.
- `open_weight` — The model's weights are openly released (for example Llama, Mistral or Falcon), whether the institution or a provider runs it.
- `government_developed` — The model was developed by or for a government (for example France's Albert or Germany's OpenGPT-X), including by the institution's own team.

**Rules.** - `model_origin`: commercial / open_weight / government_developed / unknown. `build_arrangement`: off_the_shelf_product / custom_application_on_external_model / model_trained_or_fine_tuned_by_institution / unknown.
- *missing label unknown: meaning for this item*: The page mentions the model behind the tool but does not let it be settled. **[proposed change 6]**

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `highest_probability`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### build arrangement

<sub>core.build_arrangement</sub>

**Answer.** one answer

**Answers and their meaning.** - `off_the_shelf_product` — The institution uses a ready-made product as supplied (for example a commercial chat assistant or an office-suite assistant), set up but not built on.
- `custom_application_on_external_model` — The institution, or a contractor for it, built its own application (a chatbot, assistant or workflow) on a model it did not train.
- `model_trained_or_fine_tuned_by_institution` — The institution, or a contractor for it, trained or fine-tuned the model itself. Internal use alone does not show this.

**Rules.** - `model_origin`: commercial / open_weight / government_developed / unknown. `build_arrangement`: off_the_shelf_product / custom_application_on_external_model / model_trained_or_fine_tuned_by_institution / unknown.
- *missing label unknown: meaning for this item*: The page mentions how the tool was built but does not let it be settled. **[proposed change 6]**

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `model_trained_or_fine_tuned_by_institution`, `custom_application_on_external_model`, `off_the_shelf_product`, `not_documented`, `unknown`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### interface

<sub>core.interface</sub>

**Answer.** one answer

**Answers and their meaning.** - `conversational` — Users type or speak to the tool in a chat or question-and-answer exchange, as with a chatbot or assistant window.
- `backend_or_api` — The tool runs behind the scenes, or other software calls it through a programming interface; users do not talk to it directly.
- `other_interface` — Users reach the tool in another way than a chat exchange or a back-end connection.

**Rules.** - `interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.
- Interface becomes conversational / back-end or API / other interface / not applicable / unknown, and deployment mode carries integrated versus standalone. _[cleaned: change 12]_
- The classifier chooses among the real interfaces and the missing-answer labels.
- A silent page gets "not documented"; a page that mentions the matter but cannot be settled gets "unknown".

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `conversational`, `backend_or_api`, `other_interface`, `not_documented`, `unknown`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### function drafting writing

<sub>core.function_drafting_writing</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page states that the tool is used for drafting or writing text, such as memos, letters, press releases or social media posts.
- `no` — The page does not state that the tool is used for drafting or writing text, such as memos, letters, press releases or social media posts.

**Rules.** - `interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### function summarization

<sub>core.function_summarization</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page states that the tool is used for summarising documents, reports or meetings.
- `no` — The page does not state that the tool is used for summarising documents, reports or meetings.

**Rules.** - `interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### function translation

<sub>core.function_translation</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page states that the tool is used for translating text or speech between languages.
- `no` — The page does not state that the tool is used for translating text or speech between languages.

**Rules.** - `interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### function search retrieval

<sub>core.function_search_retrieval</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page states that the tool is used for finding information, such as answering questions from documents or searching the institution's own records.
- `no` — The page does not state that the tool is used for finding information, such as answering questions from documents or searching the institution's own records.

**Rules.** - `interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### function code

<sub>core.function_code</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page states that the tool is used for writing, reviewing or fixing software code.
- `no` — The page does not state that the tool is used for writing, reviewing or fixing software code.

**Rules.** - `interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### function image audio video

<sub>core.function_image_audio_video</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page states that the tool is used for creating or editing images, audio or video.
- `no` — The page does not state that the tool is used for creating or editing images, audio or video.

**Rules.** - `interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### function extraction classification

<sub>core.function_extraction_classification</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page states that the tool is used for pulling information out of documents or forms, or sorting and classifying them.
- `no` — The page does not state that the tool is used for pulling information out of documents or forms, or sorting and classifying them.

**Rules.** - `interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### function analysis recommendation

<sub>core.function_analysis_recommendation</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page states that the tool is used for analysing information or giving recommendations or scores to support human decisions, such as case triage or eligibility checks.
- `no` — The page does not state that the tool is used for analysing information or giving recommendations or scores to support human decisions, such as case triage or eligibility checks.

**Rules.** - `interface` (one Choice): conversational / embedded_in_existing_software / standalone_application / backend_or_api / not_applicable / unknown. Functions as separate jev yes/no items (jev returns one code per question): drafting_writing, summarization, translation, search_retrieval, code, image_audio_video, extraction_classification, analysis_recommendation. Each item is chunk-safe with any-yes.

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### tool name

<sub>core.tool_name</sub>

**Question.** Specific tool, model, or platform name (e.g., "Microsoft 365 Copilot", "ChatGPT", "Albert").

**Answer.** list

**Rules.** - `tool_name` = product or platform as written on the page; new `model_name` = model as written (e.g. "GPT-4o") or `unknown`. Several tools are `; `-separated in page order. `not_applicable` for activities without a tool. _[cleaned: change 13]_
- The quote step runs for every activity; skipped items are kept internally and published as "not asked".

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`
- amended:   - 
    - activity type: `policy_guidance`
    - draft: `not_asked`
    - now: `ask`
    - ruling: activity-03 a

**Long pages: combining the parts.** `combined_list`

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** quote step; activity; public

### model name

<sub>core.model_name</sub>

**Answer.** list

**Rules.** - `tool_name` = product or platform as written on the page; new `model_name` = model as written (e.g. "GPT-4o") or `unknown`. Several tools are `; `-separated in page order. `not_applicable` for activities without a tool. _[cleaned: change 13]_
- The quote step runs for every activity; skipped items are kept internally and published as "not asked".

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`
- amended:   - 
    - activity type: `policy_guidance`
    - draft: `not_asked`
    - now: `ask`
    - ruling: activity-03 a

**Long pages: combining the parts.** `combined_list`

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** quote step; activity; public

### contracting party

<sub>core.contracting_party</sub>

**Answer.** text

**Rules.** - Developer (from lookup or page, with its basis recorded) and contracting party (page-stated only). _[cleaned: change 12]_
- Vendor holds what the source names, which in purchase records is the contracting party. The developer from the lookup goes into a new model-developer column, and the lookup stops filling vendor.
- The quote step runs for every activity; skipped items are kept internally and published as "not asked".

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `combined_list`

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** quote step; activity; public

### developer

<sub>core.developer</sub>

**Answer.** text

**Rules.** - Developer (from lookup or page, with its basis recorded) and contracting party (page-stated only). _[cleaned: change 12]_
- vendor = the organisation the page names as supplying the GenAI product or service, verbatim. If none is named but tool_name matches a published lookup table (product -> developer, versioned), fill it deterministically and set `vendor_basis` = lookup, otherwise `stated`.
- The quote step runs for every activity; skipped items are kept internally and published as "not asked".

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`
- amended:   - 
    - activity type: `policy_guidance`
    - draft: `not_asked`
    - now: `ask`
    - ruling: activity-03 a (the developer derived from them)

**Long pages: combining the parts.** 
- rule: `combined_list`

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** derived; activity; public

### developer basis

<sub>core.developer_basis</sub>

**Answer.** one answer

**Rules.** - Developer (from lookup or page, with its basis recorded) and contracting party (page-stated only). _[cleaned: change 12]_
- Every 'how we know' field uses the same five values: stated, from metadata, looked up, derived, quoted by the quote step. The per-run version record also holds the codebook version, the channel tag stays on each row, and per-code coder details are stored internally and linked to that record.

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** mechanical; activity; public

### deployment mode

<sub>core.deployment_mode</sub>

**Question.** `standalone`: separate tool/interface. `integrated`: embedded in existing system (e.g., Copilot inside Outlook).

**Answer.** one answer

**Answers and their meaning.** - `integrated` — integrated: the GenAI feature works inside software or a service channel the institution already used (office suite, case system, existing website service).
- `standalone` — standalone: a separate application or site created for the GenAI tool.

**Rules.** - *missing label unknown: meaning for this item*: The page mentions whether the tool is separate or built into existing software but does not let it be settled. **[proposed change 6]**

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `highest_probability`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### target users

<sub>core.target_users</sub>

**Question.** Who interacts with the GenAI system.

**Answer.** one answer

**Answers and their meaning.** - `internal_staff` — Only the institution's own staff use the tool.
- `public` — People outside the institution use the tool: members of the public, residents or businesses.
- `both` — Both the institution's staff and people outside it use the tool. On long pages, one part naming staff and another the public also gives this value.

**Rules.** - target_users only for tool activities (`not_applicable` otherwise). A04 for governance.
- *missing label unknown: meaning for this item*: The page mentions who uses the tool but does not let it be settled. **[proposed change 6]**

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `combined_list`
- then: mapping step to one value
- mapping: 
  - map: 
    - internal staff + public: `both`
  - other lists: Drop 'not covered by this part' and missing labels from the list. 'both' present, or staff and public both present, gives 'both'. One real value gives that value. No real value: not_documented if any part says the page is silent, else unknown. Every part 'not covered' gives not_documented.
- text:   - List all answers, then map the list to one value.
  - combined_list over the parts' answers, with {internal_staff, public} read as `both`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### governed population

<sub>core.governed_population</sub>

**Answer.** one answer

**Answers and their meaning.** - `internal_personnel` — The rule applies to the institution's own staff and officials.
- `external_users` — The rule applies to people or bodies outside the institution, such as the public or the parties it regulates.
- `both` — The rule applies both to the institution's own staff and to people or bodies outside it. On long pages, one part naming each also gives this value.

**Rules.** - jev Choice: internal_personnel / external_users / both / unknown; `not_applicable` for non-governance.
- *missing label unknown: meaning for this item*: The page mentions whom the rule applies to but does not let it be settled. **[proposed change 6]**

**When it is asked.** 
- item: `core.action_type`
- values: `governance`
- rule: shared rule *governance gate*

**Long pages: combining the parts.** 
- rule: `combined_list`
- then: mapping step to one value
- mapping: 
  - map: 
    - internal personnel + external users: `both`
  - other lists: Drop 'not covered by this part' and missing labels from the list. 'both' present, or staff and public both present, gives 'both'. One real value gives that value. No real value: not_documented if any part says the page is silent, else unknown. Every part 'not covered' gives not_documented.
- text:   - List all answers, then map the list to one value.
  - combined_list with {internal_personnel, external_users} read as `both`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### governance form

<sub>core.governance_form</sub>

**Answer.** one or more answers

**Answers and their meaning.** - `dedicated_genai_or_ai_policy_or_guideline` — A policy, guideline, code of practice or acceptable-use rule whose main subject is generative AI or AI.
- `approved_tool_list_or_endorsement` — A list of approved or permitted GenAI tools, or an official endorsement of a named tool.
- `clause_in_instrument_on_other_subject` — A clause on GenAI inside a rule, policy or guidance whose main subject is something else (for example IT security or records management).
- `court_or_regulatory_order` — An order, decision or practice direction on GenAI use issued by a court or a regulator.
- `procurement_standard` — A standard or requirement for buying GenAI tools or services, such as purchasing criteria or contract terms.

**Rules.** - jev Choice: dedicated_genai_or_ai_policy_or_guideline / approved_tool_list_or_endorsement / clause_in_instrument_on_other_subject / court_or_regulatory_order / procurement_standard / unknown. Applies only when the action is governance (`not_applicable` otherwise).
- S6 c: `governance_form` becomes multi-select, so a document can be both guideline and endorsement. _[cleaned: change 12]_
- *missing label unknown: meaning for this item*: The page mentions the form of the rule but does not let it be settled. **[proposed change 6]**

**When it is asked.** 
- item: `core.action_type`
- values: `governance`
- rule: shared rule *governance gate*

**Long pages: combining the parts.** `combined_list`

**When several answers fit.** all that apply

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### governance direction

<sub>core.governance_direction</sub>

**Answer.** one answer

**Answers and their meaning.** - `prohibits` — The rule bans the GenAI use it covers, with no use allowed.
- `restricts_with_conditions` — The rule allows use only under conditions (for example approval, training, limits on data, or human review), or bans some uses and allows others. On long pages, a ban in one part and a permission in another also give this value.
- `permits` — The rule allows the use without conditions.
- `requires` — The rule makes GenAI use mandatory for some task or for some staff.
- `promotes` — The rule encourages or supports GenAI use without making it mandatory.

**Rules.** - One classifier question on governance activities only: prohibits, restricts with conditions, permits, requires or promotes, unknown; not applicable otherwise; with a supporting quote. _[cleaned: change 12]_
- Two values, "requires" and "promotes"
- "Permits" only when use is allowed without conditions; across parts, a ban in one part and a permission in another also becomes "restricts with conditions" (a mapping step).
- A silent page gets "not documented"; a page that mentions the matter but cannot be settled gets "unknown".

**When it is asked.** 
- item: `core.action_type`
- values: `governance`
- rule: shared rule *governance gate*

**Long pages: combining the parts.** 
- rule: `priority_order`
- rank of requires vs promotes: Order: restricts_with_conditions, prohibits, permits, requires, promotes, not_documented, unknown.
- order: `restricts_with_conditions`, `prohibits`, `permits`, `requires`, `promotes`, `not_documented`, `unknown`
- mapping: 
  - map: 
    - prohibits + permits (across parts): `restricts_with_conditions`
"Permits" only when use is allowed without conditions; across parts, a ban in one part and a permission in another also becomes "restricts with conditions" (a mapping step).

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### service domain

<sub>core.service_domain</sub>

**Answer.** one or more answers

**Answers and their meaning.** - `general_public_services` — Running government itself: executive and legislative bodies, financial, fiscal and tax affairs, foreign affairs, and general administration and internal services. The earlier value 'general administration' is coded here.
- `defence` — Military and civil defence.
- `public_order_safety` — Police, fire protection, the courts and prisons.
- `economic_affairs` — Economic, commercial and labour affairs; agriculture, forestry and fishing; fuel and energy; industry and construction; transport; communication.
- `environmental_protection` — Waste and waste-water management, pollution control, and the protection of biodiversity and landscape.
- `housing_community_amenities` — Housing and community development, water supply and street lighting.
- `health` — Medical products, outpatient and hospital services, and public health services.
- `recreation_culture_religion` — Recreation and sport, culture, broadcasting and publishing, and religious and other community services.
- `education` — Education at every level, from pre-primary to university, and services that support it.
- `social_protection` — Support in sickness and disability, old age, for survivors, families and children, in unemployment, for housing, and against social exclusion.
- `other` — An area that fits none of the ten areas above.

**Rules.** - One classifier question per activity over a short list of areas plus 'general administration' and 'unknown'. _[cleaned: change 12]_
- The UN and Eurostat classification of the functions of government, top level (as used by Public Sector Tech Watch)
- Activities that fit no area get "other".
- The question becomes a tick-all-that-apply list.
- A silent page gets "not documented"; a page that mentions the matter but cannot be settled gets "unknown".
- *mapping of the round-2 value*: No separate value. A rule says the earlier 'general administration' is coded 'general public services'.

**Long pages: combining the parts.** 
- rule: `combined_list`
- multi select vs single winner: Take every area any part ticks with a supported answer. Each area's quote and certainty come from the part most sure of it. Missing labels only if no part ticks a real area.
- per value producing part: `highest_probability`
- replaces rule: highest_probability (activity-20 a, before activity-13 b made the item multi-select)

**When several answers fit.** all that apply

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### genai mechanism basis

<sub>core.genai_mechanism_basis</sub>

**Answer.** one answer

**Answers and their meaning.** - `named_genai_product_or_model` — The page names a generative product or model, such as ChatGPT, Copilot, Gemini, Claude or a named language model.
- `explicit_genai_label` — The page calls the tool generative AI, a large language model or the like, without naming a product.
- `generative_capability_described` — The page says the tool generates text, images, audio, code or other content, without naming a product or using a generative-AI label.
- `ai_chatbot_or_assistant_label_only` — The only signal is that the page calls the tool an 'AI chatbot' or 'AI assistant'; under the GenAI boundary rule this counts as generative.

**Rules.** - jev Choice on every confirms_activity page/activity: named_genai_product_or_model / explicit_genai_label / generative_capability_described / ai_chatbot_or_assistant_label_only. The extractor returns the supporting quote.
- See shared rule: *genai boundary*

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `named_genai_product_or_model`, `explicit_genai_label`, `generative_capability_described`, `ai_chatbot_or_assistant_label_only`, `not_documented`, `unknown`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### year announced

<sub>core.year_announced</sub>

**Question.** "In which year does the page say this activity was first announced?"

**Answer.** one answer

**Answers and their meaning.** **candidates**: deterministic year extraction, plus unknown (C16)

**Rules.** - Deterministic: extract all four-digit years 2015-2030 from the activity span and its context. jev Choice over those years plus `unknown`: "In which year does the page say this activity was first announced?" No fallback to publication year. Across chunks: earliest chosen year.
- Pilot and production years use the same candidate-then-classifier method, with candidates converted from other calendars and fiscal years under a multilingual-subproject rule. Governance uses the announcement year as its adoption year and marks pilot and production years not applicable. _[cleaned: change 12]_

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** `earliest_year`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### year pilot start

<sub>core.year_pilot_start</sub>

**Answer.** one answer

**Answers and their meaning.** **candidates**: deterministic year extraction, plus unknown (C16)

**Rules.** - Deterministic: extract all four-digit years 2015-2030 from the activity span and its context. jev Choice over those years plus `unknown`: "In which year does the page say this activity was first announced?" No fallback to publication year. Across chunks: earliest chosen year.
- Pilot and production years use the same candidate-then-classifier method, with candidates converted from other calendars and fiscal years under a multilingual-subproject rule. Governance uses the announcement year as its adoption year and marks pilot and production years not applicable. _[cleaned: change 12]_
- Two columns, each stated-only.

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** `earliest_year`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### year production start

<sub>core.year_production_start</sub>

**Answer.** one answer

**Answers and their meaning.** **candidates**: deterministic year extraction, plus unknown (C16)

**Rules.** - Deterministic: extract all four-digit years 2015-2030 from the activity span and its context. jev Choice over those years plus `unknown`: "In which year does the page say this activity was first announced?" No fallback to publication year. Across chunks: earliest chosen year.
- Pilot and production years use the same candidate-then-classifier method, with candidates converted from other calendars and fiscal years under a multilingual-subproject rule. Governance uses the announcement year as its adoption year and marks pilot and production years not applicable. _[cleaned: change 12]_
- Two columns, each stated-only.

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** `earliest_year`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### deployment scale number

<sub>core.deployment_scale_number</sub>

**Answer.** number

**Rules.** - The extractor returns the verbatim number span. jev Choice gives the unit: licences_or_seats / users / interactions / units_or_departments / none.
- the quote step copies the scale number verbatim and the classifier picks the unit _[cleaned: change 13]_
- The quote step runs for every activity; skipped items are kept internally and published as "not asked".

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `not_asked`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `combined_list`
- pairs: (number, unit), the unit from the same part as its number
- text:   - Store all figures with their units.
  - combined_list of (number, unit) pairs, if the column may hold several scales.

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** quote step; activity; public

### deployment scale unit

<sub>core.deployment_scale_unit</sub>

**Answer.** one answer

**Answers and their meaning.** - `licences_or_seats` — The number counts licences, seats or accounts bought or issued.
- `users` — The number counts people who use the tool.
- `interactions` — The number counts uses of the tool, such as questions answered, conversations held or documents handled.
- `units_or_departments` — The number counts offices, departments, schools or other units that use the tool.
- `none` — A number is stated, but it counts none of these units.

**Rules.** - The extractor returns the verbatim number span. jev Choice gives the unit: licences_or_seats / users / interactions / units_or_departments / none.

**When it is asked.** 
- item: `core.deployment_scale_number`
- values: `any stated`

**Long pages: combining the parts.** 
- rule: `combined_list`
- pairs: (number, unit), the unit from the same part as its number
- text:   - Store all figures with their units.
  - combined_list, paired with the number (as for the number).

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### has human oversight

<sub>core.has_human_oversight</sub>

**Question.** Is human review required before acting on GenAI outputs?

**Answer.** one answer

**Answers and their meaning.** - `yes` — yes: the page states the safeguard applies to this activity (for a governance activity: the rule requires it).
- `no` — no: the page states it does not apply.
- `unclear` — unclear: the page mentions the safeguard but it cannot be settled whether it applies to this activity.

**Rules.** - See shared rule: *safeguard attachment*
- One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer. _[cleaned: change 12]_
- *missing label not_documented: meaning for this item*: not_documented: the page is silent. **[proposed change 6]**

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `yes`, `no`, `unclear`, `not_documented`, `unknown`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### has transparency notice

<sub>core.has_transparency_notice</sub>

**Question.** Are users/citizens notified that GenAI is involved?

**Answer.** one answer

**Answers and their meaning.** - `yes` — yes: the page states the safeguard applies to this activity (for a governance activity: the rule requires it).
- `no` — no: the page states it does not apply.
- `unclear` — unclear: the page mentions the safeguard but it cannot be settled whether it applies to this activity.

**Rules.** - See shared rule: *safeguard attachment*
- One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer. _[cleaned: change 12]_
- *missing label not_documented: meaning for this item*: not_documented: the page is silent. **[proposed change 6]**

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `yes`, `no`, `unclear`, `not_documented`, `unknown`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### has data classification

<sub>core.has_data_classification</sub>

**Question.** Are there documented data-handling restrictions for GenAI use?

**Answer.** one answer

**Answers and their meaning.** - `yes` — yes: the page states the safeguard applies to this activity (for a governance activity: the rule requires it).
- `no` — no: the page states it does not apply.
- `unclear` — unclear: the page mentions the safeguard but it cannot be settled whether it applies to this activity.

**Rules.** - See shared rule: *safeguard attachment*
- One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer. _[cleaned: change 12]_
- *missing label not_documented: meaning for this item*: not_documented: the page is silent. **[proposed change 6]**

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `yes`, `no`, `unclear`, `not_documented`, `unknown`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### has risk assessment

<sub>core.has_risk_assessment</sub>

**Question.** Has a formal risk/impact assessment been documented?

**Answer.** one answer

**Answers and their meaning.** - `yes` — yes: the page states the safeguard applies to this activity (for a governance activity: the rule requires it).
- `no` — no: the page states it does not apply.
- `unclear` — unclear: the page mentions the safeguard but it cannot be settled whether it applies to this activity.

**Rules.** - See shared rule: *safeguard attachment*
- One per-activity question per safeguard with the four answers; the page-level answer is yes if any activity is yes, otherwise no. The activity-level transparency question is re-worded to the signed notification definition, data classification stays activity-only, and contract clauses are tagged as a governance answer. _[cleaned: change 12]_
- *missing label not_documented: meaning for this item*: not_documented: the page is silent. **[proposed change 6]**

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `yes`, `no`, `unclear`, `not_documented`, `unknown`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### outcome kind

<sub>core.outcome_kind</sub>

**Answer.** one answer

**Answers and their meaning.** - `quantified` — states a measured or numeric result
- `qualitative` — states a result in words only, with no measure
- `none_reported` — states no result

**Rules.** - A jev `Choice` per (finding × page), over the page text with this activity's span marked, asked for outcomes and for incidents separately: `quantified` / `qualitative` / `none_reported`. It answers both whether the page reports an outcome (an incident) of this activity and of what kind; no separate existence question is asked. The outcome or incident text is extracted only when the answer is not `none_reported`. The incident item also takes the value in CX-61b.
- *direction*: Ask CX-61 in pass 2 over the page text with the activity span marked; the extractor then quotes support for the chosen value.
- *direction*: Pass-2 jev Choice on page text: does the page report an outcome (incident) of this activity: quantified / qualitative / none? The extractor extracts verbatim text only when not none; CX-60 then applies to legacy rows only.
- Your outcome and incident gates are re-ruled down to quotes only; the signed item answers both whether and what kind, and the separate existence question folds into it. _[cleaned: change 12]_

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `quantified`, `qualitative`, `none_reported`, `not_documented`, `unknown`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### incident kind

<sub>core.incident_kind</sub>

**Answer.** one answer

**Answers and their meaning.** - `quantified` — states a measured or numeric result
- `qualitative` — states a result in words only, with no measure
- `none_reported` — states no result
- `discontinuation_uncertain` — The page suggests that this activity may have been ended, cancelled or suspended, but does not confirm it.

**Rules.** - A jev `Choice` per (finding × page), over the page text with this activity's span marked, asked for outcomes and for incidents separately: `quantified` / `qualitative` / `none_reported`. It answers both whether the page reports an outcome (an incident) of this activity and of what kind; no separate existence question is asked. The outcome or incident text is extracted only when the answer is not `none_reported`. The incident item also takes the value in CX-61b.
- *direction*: Ask CX-61 in pass 2 over the page text with the activity span marked; the extractor then quotes support for the chosen value.
- *direction*: Pass-2 jev Choice on page text: does the page report an outcome (incident) of this activity: quantified / qualitative / none? The extractor extracts verbatim text only when not none; CX-60 then applies to legacy rows only.
- Your outcome and incident gates are re-ruled down to quotes only; the signed item answers both whether and what kind, and the separate existence question folds into it. _[cleaned: change 12]_
- Retire flags that just mirror a column; keep 'identity unresolved' and 'stage ambiguous', and fold 'discontinuation uncertain' into the incident question as a value instead of a separate question. _[cleaned: change 12]_
- *value cell of CX-61b*: `discontinuation_uncertain` (incident item only)
- The incident question ignores stops unless a problem is reported.

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `quantified`, `qualitative`, `discontinuation_uncertain`, `none_reported`, `not_documented`, `unknown`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### reported outcomes

<sub>core.reported_outcomes</sub>

**Question.** Documented performance claims. Only record if explicitly stated. Never infer.

**Answer.** list

**Rules.** - Deterministic step (no API), for rows coded before CX-01.3 only: map all "nothing found" spellings to `none_reported`. The mapping table is published with the code.
- jev Choice per activity: page reports realised outcomes / only expected or projected outcomes / usage figures only / none. Unless none, the extractor returns verbatim spans (no length limit in storage, display cap per R-043). CX-61 then runs on the spans.

**When it is asked.** 
- item: `core.outcome_kind`
- values: `not none_reported`

**Long pages: combining the parts.** `combined_list`

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** quote step; activity; public

### reported incidents

<sub>core.reported_incidents</sub>

**Question.** Documented errors, failures, or controversies. Only record if explicitly stated.

**Answer.** list

**Rules.** - Deterministic step (no API), for rows coded before CX-01.3 only: map all "nothing found" spellings to `none_reported`. The mapping table is published with the code.
- jev Choice: page reports a malfunction or error / data or privacy breach / public criticism or complaint / suspension or withdrawal / none. Unless none, the extractor returns verbatim spans.

**When it is asked.** 
- item: `core.incident_kind`
- values: `not none_reported`

**Long pages: combining the parts.** `combined_list`

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** quote step; activity; public

### evaluation documented

<sub>core.evaluation_documented</sub>

**Question.** Does this page document an evaluation of this GenAI activity?

**Answer.** one answer

**Answers and their meaning.** - `results_reported` — The page states that this activity was tested, evaluated, audited or monitored **and** reports a result (a metric, a finding or a conclusion).
- `conducted_no_results` — The page states that an evaluation, test, audit, pilot review or monitoring took place or is in place, but reports no result.
- `required_or_planned` — The page states that an evaluation is required (by a rule) or planned, with no evidence that it has happened. A policy finding that requires evaluation of GenAI tools takes this value.
- `unclear` — The page makes an evaluative statement, but its subject, or whether it concerns this GenAI activity, cannot be settled. An evaluation clearly of a different tool or activity is `not_documented`, not `unclear` (CX-01.2, C4 = a).

**Rules.** - A requirement to carry out a risk or impact assessment is **not** `required_or_planned`; it belongs to `has_risk_assessment` alone (consistent with CX-37).
- A clause requiring periodic review of the GenAI policy itself is `not_documented`, unless it requires testing, monitoring or evaluation of GenAI tools or their outputs; then it counts as `required_or_planned`. This includes any policy with a GenAI section (e.g. a general IT policy).
- A required pre-use review that mixes fitness-for-purpose with security or compliance checks counts as `required_or_planned`. A pure risk or impact assessment requirement stays under CX-32b.
- No negative value. A page saying no evaluation was done or planned is `not_documented`.
- A performance figure counts as `results_reported` only if the page also describes the activity behind it (a test, a pilot review, a survey, an audit, monitoring); otherwise `not_documented`.
- A risk or impact assessment counts here only if it reports testing or measured performance; otherwise it belongs to `has_risk_assessment` alone.
- A vendor's performance claim counts only if the page names the institution or an independent body as the evaluator.
- A pilot stage alone is `not_documented`. "The pilot will be evaluated" is `required_or_planned`; "the pilot evaluation found …" is `results_reported`.
- (1) An agency blog: "after a three-month trial, 78% of staff said the assistant saved time" → `results_reported`. (2) Minutes: "the pilot is being reviewed by IT" → `conducted_no_results`. (3) A guidance memo: "all GenAI tools must be tested before deployment" → `required_or_planned` on the policy finding. (4) A press release: "the chatbot has answered 40,000 questions" → `not_documented` (a usage count with no evaluation described; CX-36). (5) A vendor case study: "accuracy improved 30%" with no named evaluator → `not_documented` (CX-38).
- *direction*: Delete CX-32c's policy-review clause: a periodic review of the policy document is `not_documented` unless it requires testing, monitoring or evaluation of GenAI tools or their outputs.
- *classifier_line (required_or_planned)*: CX-32: the page states that an evaluation is required (by a rule) or planned, with no evidence that it has happened. A policy that requires evaluation of GenAI tools takes this value. A clause requiring periodic review of the GenAI policy itself is NOT this value unless it requires testing, monitoring or evaluation of GenAI tools or their outputs (CX-32c). A requirement to carry out a risk or impact assessment is NOT this value (CX-32b).
- *missing label not_documented: meaning for this item*: The page has no evaluation statement about this activity. **[proposed change 6]**

**When it is asked.** 
- table: applicability keyed on activity_type
- key: `core.activity_type`
- rule: shared rule *applicability table*
- cells: 
  - policy guidance: `ask`
  - pilot experiment: `ask`
  - program initiative: `ask`
  - internal operational: `ask`
  - public facing service: `ask`
  - unknown: `ask`

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `results_reported`, `conducted_no_results`, `required_or_planned`, `unclear`, `not_documented`, `unknown`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity, page; public

### evaluation type pre deployment testing

<sub>core.evaluation_type_pre_deployment_testing</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page documents an evaluation of this type for the activity: testing before deployment.
- `no` — The page does not document an evaluation of this type (testing before deployment) for the activity.

**Rules.** - Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.
- *direction*: Procedural: ask (or keep) type items only if `evaluation_documented` is still positive after R-041 and R-081; otherwise store `_NA_`.

**When it is asked.** 
- item: `core.evaluation_documented`
- values: `results_reported`, `conducted_no_results`, `required_or_planned`
- after: downgrades

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity, page; public

### evaluation type pilot evaluation

<sub>core.evaluation_type_pilot_evaluation</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page documents an evaluation of this type for the activity: evaluation of a pilot or trial.
- `no` — The page does not document an evaluation of this type (evaluation of a pilot or trial) for the activity.

**Rules.** - Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.
- *direction*: Procedural: ask (or keep) type items only if `evaluation_documented` is still positive after R-041 and R-081; otherwise store `_NA_`.

**When it is asked.** 
- item: `core.evaluation_documented`
- values: `results_reported`, `conducted_no_results`, `required_or_planned`
- after: downgrades

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity, page; public

### evaluation type independent audit

<sub>core.evaluation_type_independent_audit</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page documents an evaluation of this type for the activity: an audit or evaluation by an independent body.
- `no` — The page does not document an evaluation of this type (an audit or evaluation by an independent body) for the activity.

**Rules.** - Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.
- *direction*: Procedural: ask (or keep) type items only if `evaluation_documented` is still positive after R-041 and R-081; otherwise store `_NA_`.

**When it is asked.** 
- item: `core.evaluation_documented`
- values: `results_reported`, `conducted_no_results`, `required_or_planned`
- after: downgrades

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity, page; public

### evaluation type ongoing monitoring

<sub>core.evaluation_type_ongoing_monitoring</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page documents an evaluation of this type for the activity: ongoing monitoring of the tool in use.
- `no` — The page does not document an evaluation of this type (ongoing monitoring of the tool in use) for the activity.

**Rules.** - Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.
- *direction*: Procedural: ask (or keep) type items only if `evaluation_documented` is still positive after R-041 and R-081; otherwise store `_NA_`.

**When it is asked.** 
- item: `core.evaluation_documented`
- values: `results_reported`, `conducted_no_results`, `required_or_planned`
- after: downgrades

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity, page; public

### evaluation type user feedback

<sub>core.evaluation_type_user_feedback</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page documents an evaluation of this type for the activity: user feedback or satisfaction surveys.
- `no` — The page does not document an evaluation of this type (user feedback or satisfaction surveys) for the activity.

**Rules.** - Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.
- *direction*: Procedural: ask (or keep) type items only if `evaluation_documented` is still positive after R-041 and R-081; otherwise store `_NA_`.

**When it is asked.** 
- item: `core.evaluation_documented`
- values: `results_reported`, `conducted_no_results`, `required_or_planned`
- after: downgrades

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity, page; public

### evaluation type bias or safety testing

<sub>core.evaluation_type_bias_or_safety_testing</sub>

**Answer.** yes or no

**Answers and their meaning.** - `yes` — The page documents an evaluation of this type for the activity: bias, fairness or safety testing.
- `no` — The page does not document an evaluation of this type (bias, fairness or safety testing) for the activity.

**Rules.** - Included. Asked only when `evaluation_documented` ∈ {`results_reported`, `conducted_no_results`, `required_or_planned`}; six yes/no items: `pre_deployment_testing`, `pilot_evaluation`, `independent_audit`, `ongoing_monitoring`, `user_feedback`, `bias_or_safety_testing`.
- *direction*: Procedural: ask (or keep) type items only if `evaluation_documented` is still positive after R-041 and R-081; otherwise store `_NA_`.

**When it is asked.** 
- item: `core.evaluation_documented`
- values: `results_reported`, `conducted_no_results`, `required_or_planned`
- after: downgrades

**Long pages: combining the parts.** `any_yes`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity, page; public

### stage as of

<sub>core.stage_as_of</sub>

**Answer.** date

**Rules.** - stage_as_of = source_publication_date if supported, else the page's latest stated date for the activity, else the access date; plus `stage_as_of_basis`.

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** derived; activity; public

### stage as of basis

<sub>core.stage_as_of_basis</sub>

**Answer.** one answer

**Rules.** - stage_as_of = source_publication_date if supported, else the page's latest stated date for the activity, else the access date; plus `stage_as_of_basis`.
- Every 'how we know' field uses the same five values: stated, from metadata, looked up, derived, quoted by the quote step. The per-run version record also holds the codebook version, the channel tag stays on each row, and per-code coder details are stored internally and linked to that record.

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** derived; activity; public

### permanent pilot

<sub>core.permanent_pilot</sub>

**Answer.** yes or no

**Rules.** - Each item states its coder (classifier, mechanical, quote step or derived), and the approved plan's field list becomes a pointer to the codebook. 'Permanent pilot' becomes a derived flag, and 'vendor claim only' is read from the source being a vendor; one build task's scope changes.

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** derived; activity; public

### vendor claim only

<sub>core.vendor_claim_only</sub>

**Answer.** yes or no

**Rules.** - Each item states its coder (classifier, mechanical, quote step or derived), and the approved plan's field list becomes a pointer to the codebook. 'Permanent pilot' becomes a derived flag, and 'vendor claim only' is read from the source being a vendor; one build task's scope changes.

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** derived; activity; public

### unit credit

<sub>core.unit_credit</sub>

**Answer.** yes or no

**Rules.** - Keep your rule and add a yes/no column marking credit received through a unit, so analyses can remove duplicates; the data dictionary explains it.

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** derived; activity; public

### uncertainty flags

<sub>core.uncertainty_flags</sub>

**Answer.** list

**Rules.** - Compute each flag from codes (table above); add `identity_unresolved` for Stage 6 relations; drop `source_language_barrier`; `discontinued_uncertain` becomes a pass-2 jev yes/no.
- Retire flags that just mirror a column; keep 'identity unresolved' and 'stage ambiguous', and fold 'discontinuation uncertain' into the incident question as a value instead of a separate question. _[cleaned: change 12]_
- AI-text flags fold into the main list, the language-barrier flag is dropped everywhere, and language coverage is carried by the multilingual subproject's item.

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** derived; activity, row; public

### observed actor role

<sub>core.observed_actor_role</sub>

**Answer.** one answer

**Answers and their meaning.** - `institutional_actor` — The actor seen on the page carries out or adopts the activity as an institution.
- `issuer` — The actor issued the policy, rule, guidance or document.
- `participant` — The actor takes part in an activity that someone else runs.
- `external_speaker` — The actor speaks or presents about GenAI, for example at an event, without carrying out the activity.
- `service_provider` — The actor supplies the tool or service, as a vendor, contractor or developer.
- `event_host` — The actor hosts or organises an event about GenAI.

**Rules.** - Code it as before; not published.
- *which roles count as taking part*: Only `institutional_actor`, `issuer` and `participant` count as the actor taking part in the activity; `external_speaker`, `service_provider` and `event_host` do not. **[proposed change 4]**

**Long pages: combining the parts.** 
- rule: `same_part_as`
- item: `core.observed_actor_relationship`
- fallback: `highest_probability`
Take the role from the part that produced the combined relationship; if that part gives no real role, take the most-sure real role from the other parts.

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; internal

## Facts about each source page

### source type

<sub>core.source_type</sub>

**Answer.** one answer

**Answers and their meaning.** - `news_major` — Major national/international news outlet (Reuters, BBC, NYT, Le Monde, NHK, etc.)
- `news_trade` — Technology or government trade press (GovTech, FedScoop, PublicTechnology, etc.)
- `vendor` — Vendor website, case study, blog post, or press release
- `academic` — Peer-reviewed paper, working paper, university report
- `policy_org` — Think tank, IGO, or policy organization (OECD, World Bank, ITU, Brookings, etc.)
- `social_media` — Official social media accounts (Twitter/X, LinkedIn from institutional accounts)
- `procurement_tender` — Tender notice, RFP, contract award, vendor selection document
- `other` — None of the above; explain in `source_snippet`

**Rules.** - 'Official' comes from the domain field and 'archive' from the address; the classifier only sorts the rest (news, vendor, academic, policy organisation, social media, procurement, other). The question wording is amended.
- Source type is answered by the same classifier question in every pipeline where it applies. The AI-text pipeline drops its genre table and procurement's fixed value is replaced.

**When it is asked.** 
- rule: only pages not typed automatically from domain or address

**Long pages: combining the parts.** 
- rule: `first_section`

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** classifier; source; public

### source url

<sub>core.source_url</sub>

**Answer.** text

**Rules.** - The URL of the supplied page, verbatim from the input. **Never fabricate or alter.**
- Take `source_title` from RenderedPage.title (fallback: first heading); never from a model.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; source; public

### source title

<sub>core.source_title</sub>

**Answer.** text

**Rules.** - Take `source_title` from RenderedPage.title (fallback: first heading); never from a model.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; source; public

### source access date

<sub>core.source_access_date</sub>

**Answer.** text

**Rules.** - Date the supplied page was retrieved (provided in the input metadata as the scrape date).
- Take `source_title` from RenderedPage.title (fallback: first heading); never from a model.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; source; public

### source language

<sub>core.source_language</sub>

**Answer.** text

**Rules.** - Pinned local language-ID library on stored text; same tag grammar as `institution_search_languages`; `mul` when no language exceeds a set share.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; source; public

### source on official domain

<sub>core.source_on_official_domain</sub>

**Answer.** text

**Rules.** - `own_official` / `other_official` / `not_official` from URL host vs the master official-site overlay.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; source; public

### syndication group

<sub>core.syndication_group</sub>

**Answer.** text

**Rules.** - Deterministic near-duplicate hash (e.g. shingled MinHash on normalised text) per page; `syndication_group` id; QC flag when codes differ within a group.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; source; public

### page review state

<sub>core.page_review_state</sub>

**Answer.** text

**Rules.** - `reviewed` / `fetch_failed` / `no_usable_text` / `link_not_followed_cap` / `link_not_followed_hops`; non-`reviewed` states count as unresolved signals in Stage 6.
- The approved plan's verdict list grows to nine; the review status keeps only failed downloads and links not followed. _[cleaned: change 12]_

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; source; public

### discovery path

<sub>core.discovery_path</sub>

**Answer.** text

**Rules.** - Add a deterministic `discovery_path` (searched / followed hop n / back-fill followed) on every source row in all runs, and report prevalence with and without followed pages.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; source; public

### text source

<sub>core.text_source</sub>

**Answer.** text

**Rules.** - A per-row `text_source` (stored / live re-fetch / new run) records which rows lack chrome text and links. _[cleaned: change 13]_

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; source; public

### source publication date

<sub>core.source_publication_date</sub>

**Answer.** date

**Rules.** - Take dates from HTML metadata / PDF properties / URL patterns deterministically; if absent, the extractor returns a date with its verbatim quote, validated by R-042.
- One shared date of 1 November 2022, with "before" needing proof. Date origin is recorded as metadata, web address, quote from page text, archive upper bound, or unknown; the AI-text code changes.

**Long pages: combining the parts.** 
- rule: `first_section`

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** quote step; source; public

### source snippet

<sub>core.source_snippet</sub>

**Answer.** text

**Rules.** - Define `source_snippet` on v2.7 rows as the verbatim supporting text of the page verdict (truncated), with no paraphrase.
- Snippets are verbatim in every pipeline, no translations are stored, and procurement's rule is amended.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** quote step; source; public

### source credibility

<sub>core.source_credibility</sub>

**Answer.** one answer

**Rules.** - `source_credibility` = fixed map from `source_type` plus `low` when `source_publication_date` = unknown; drop the translation clause. _[cleaned: change 13]_

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; source; public

### confidence

<sub>core.confidence</sub>

**Answer.** one answer

**Rules.** - Each source's confidence uses only that source's credibility and quote support. At consolidation, an activity is 'high' if one source is high or two medium sources that are not copies of each other agree; otherwise it takes the highest source value.

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** derived; source, activity; public

### date upper bound

<sub>core.date_upper_bound</sub>

**Answer.** yes or no

**Rules.** - add a yes/no note "this date is an upper bound".

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; source, activity; public

## Results for the institution as a whole

### has genai activity

<sub>core.has_genai_activity</sub>

**Answer.** one answer

**Rules.** - Institution-level consolidation (Stage 6) applies the v2.6 consolidation rules as jev questions or deterministic rules: explicit relations before merging observations; distinct/unresolved relations never merge; institution-level `no` only with complete supplied context and no unresolved signal. An institution whose reviewed pages are all negative at confidence ≥ 0.8 gets `no` directly; the complete-context rule blocks `no` only when an unresolved signal remains (a low-confidence negative downgraded under R-081 counts as one). Stage 6 becomes the X29 truth table, with these ruled components: `background_only` pages may sit in the institution `no` set; any downgraded page counts as unresolved; the bar is the chosen answer's probability ≥ 0.8; `yes` can come from any pipeline, `no` from web pages only, and AI-text results never count; any supported GenAI purchase record can give `yes`, while the evidence tier still shows it as commitment; `not_assessable` is set mechanically only and does not block `no`. Also: X30 with the shared relation list incl. `governs`; X31 pooled evidence, split when too long; A06 per r2#21; A07 with 9 counts per pipeline; X23 replaced by r2#27; unit-credit flag. `unresolved` stays a coding value and is reported as `unknown` in published summaries; unresolved relations still never merge. Inside the institution-level rule both `unresolved` and `not_assessable` keep their current roles, and `not_assessable` stays out of the institution-rate base. _[cleaned: change 10, 13]_
- Codebook table: `yes` if >= 1 supported `confirms_activity` page with a supported activity; `no` if every attempted page (incl. failed fetches and unfollowed links) ends in {no_genai, confirms_absence, event_only, other_body} at confidence >= 0.8 and no page is ambiguous, background_only or failed; otherwise `unclear`. Variant for PI: allow background_only in `no`.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; institution; public

### verdict rule

<sub>core.verdict_rule</sub>

**Answer.** one answer

**Rules.** - v2.5 `none` institutions show `no` labelled as produced by the v2.5 rule (`verdict_rule`, r2#45).

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; institution; public

### evidence tier

<sub>core.evidence_tier</sub>

**Answer.** one answer

**Rules.** - Highest of: documented_use (any pilot, production or discontinued deployment) > documented_commitment (announced, or procured if C09 alt-1) > governance_or_training_only > proposal_only > none_found / unclear. Published beside has_genai_activity.
- Use = a deployment or program at pilot, production or discontinued; commitment = announced, or a tender, contract or payment; governance or training only = those action types only; proposal only = stage 'proposed' or action type 'proposal'. You word the rule, and tests are added.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; institution; public

### review depth

<sub>core.review_depth</sub>

**Answer.** list

**Rules.** - n_pages_reviewed, n_pages_by_verdict (8 counts), n_pages_failed, n_followed_links, all computed at Stage 6.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; institution; public

### activity relation

<sub>core.activity_relation_cross_page</sub>

**Answer.** one answer

**Answers and their meaning.** - `same_activity` — The two activity records describe the same activity: the same action by the same actor on the same tool or instrument. Only records joined by this link are merged.
- `component_of_program` — The first record's activity is a named component of the program in the second. Both stay separate activities, linked.
- `has_component` — The first record describes a program, and the second record's activity is one of its named components. Both stay separate activities, linked.
- `shared_participation` — The two records describe one joint action in which several bodies take part. They are one activity: the two records are merged. The link needs at least two bodies, each named as taking part, with a quote. **[proposed change 1]**
- `governs` — The first record's activity is a policy or other governance instrument that sets rules for the activity in the second. When a pair fits both this link and a component link, this link is used.
- `governed_by` — The second record's activity is a policy or other governance instrument that sets rules for the activity in the first. When a pair fits both this link and a component link, this link is used.
- `distinct_action` — The two records describe different activities, and none of the other links applies. The value is stored with a rule note.
- `unresolved` — The sources do not settle whether the two records describe the same activity. They are never merged.

**Rules.** - Every pair of activity observations is asked, including identical names; candidate pairs pre-filtered deterministically only to skip obviously distinct pairs (different activity_type and tool), never to merge.
- See shared rule: *activity unit*
- One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page. _[cleaned: change 13]_
- Add "has component" and "governed by".
- Components stay separate activities; a governing policy is recorded as governing.
- Store the distinct value with a rule note.

**Long pages: combining the parts.** 
- rule: `priority_order`
- order: `unresolved`, `distinct_action`, `governs`, `component_of_program`, `shared_participation`, `same_activity`, `unknown`
- split rule: Split the pool so every part sees both activities.

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### pooled activity fields

<sub>core.pooled_activity_fields</sub>

**Answer.** one answer

**Rules.** - For a merged activity, jev answers each Group D question once over the union of the activity's supported quotes from all its sources (state = quotes with source type and date).
- Pooled quotes are split into parts, and the existing combining rules apply (yes if any part says yes; ordered lists take the first value found). The page-splitting rule is extended.

**Long pages: combining the parts.** 
- rule: per item

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** classifier; activity; public

### n sources

<sub>core.n_sources</sub>

**Answer.** number

**Rules.** - As v1.3.

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** derived; activity; public

### institution summary

<sub>core.institution_summary</sub>

**Answer.** text

**Rules.** - Generate the summary from codes: verdict, number of activities, their types/stages, page counts reviewed and failed.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** derived; institution; public

### cx display rollup

<sub>core.cx_display_rollup</sub>

**Answer.** list

**Rules.** - Stage 6 computes a display value per activity (any supported positive; first in table order for ordered fields), labelled 'display roll-up, not an index input'.

**Missing labels it can take.** not asked, not documented, unknown, no activity (_NA_)

**Coded by; level; published.** derived; activity; public

## Record-keeping on every row

### support entailment

<sub>core.support_entailment</sub>

**Question.** 'Does this text state that <field> is <value>?'

**Answer.** yes or no

**Answers and their meaning.** - `true` — The quoted text states that the field has the given value.
- `false` — The quoted text does not state that the field has the given value. The answer's support status becomes 'downgraded: quote does not state the value'.

**Rules.** - State = quote (plus a short window); question: 'Does this text state that <field> is <value>?' true/false; false or confidence < threshold -> downgrade `no_support`.

**When several answers fit.** first in order

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** classifier; row; internal

### support status

<sub>core.support_status</sub>

**Answer.** one answer

**Rules.** - Support-status values: `supported` / `downgraded_no_quote` / `downgraded_low_confidence` / `downgraded_quote_not_stating_value` / `set_by_rule`, for every value a rule fixed, including "not asked" and `_NA_` (exempt from the no-quote downgrade; record-02 a; O12) / `not_required`, for `not_documented`, `unknown`, `no` and negative page verdicts. _[cleaned: change 13]_
- `not_required`: the answer needs no supporting quote by its nature. It is given to `not_documented`, `unknown`, `no` and negative page verdicts. **[proposed change 9]**
- A second reason item

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; row; public

### supporting text

<sub>core.supporting_text</sub>

**Answer.** text

**Rules.** - For every jev code on a page or activity, the extractor (C-001; the quote step) extracts the verbatim supporting text from the page. RC-D-002 row 15 replaces "after jev has coded": the quote step never sees the answer for the field it quotes, but may see that a gate is not `none`. The quote step runs for every activity, including items the applicability table skips; those copies are kept internally, and the item is published as "not asked". A01 and CX-61 get quotes relevant to the field. The scale number is copied verbatim by the quote step and the classifier picks the unit; the publication date is coded by the quote step under the R-042 check. X35 adds an entailment check per (code, quote) with a chosen-answer probability bar. _[cleaned: change 13]_
- Supporting text is checked against the stored page text by fuzzy match; a quote below the match threshold counts as no supporting text.
- Supporting text is published with the code it supports. The API carries the full text; the website shows it up to a display cap, with a marker and access to the full text.
- Published supporting quotes stay verbatim, with no masking.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** quote step; row; public

### codebook release

<sub>core.codebook_release</sub>

**Answer.** text

**Rules.** - Every published row carries the contract version that produced it. That is one version label, the codebook release, replacing `contract_version`, plus the setup pointer and `evidence_channel`; the extract and validate contract labels are recorded only in the setup record. C-007 applies to the release. v2.5 rows keep their contract version. _[cleaned: change 13]_

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; row; public

### setup pointer

<sub>core.setup_pointer</sub>

**Answer.** text

**Rules.** - A manifest (contract versions, `JEV_QUESTION_SET_VERSION`, jev model, extractor model id + prompt SHA-256, chunker + estimator version, matcher + threshold, confidence threshold, codebook item hashes) keyed by `instrument_id` on every row.
- Every jev answer is stored with its probability distribution, confidence, response model id and request id. Every automated coder (classifier, quote step, detector, mechanical rules) stores coder type, model, version and request id; the per-run version record holds the codebook version, and per-code coder details are internal and linked to it; the row carries the codebook version + setup pointer; the classifier record keeps the chosen-answer probability. _[cleaned: change 13]_

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; row; public

### evidence channel

<sub>core.evidence_channel</sub>

**Answer.** one answer

**Rules.** - Channel enum (web_extract, procurement, text_detection)

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; row; public

### coder record

<sub>core.coder_record</sub>

**Answer.** text

**Rules.** - Every jev answer is stored with its probability distribution, confidence, response model id and request id. Every automated coder (classifier, quote step, detector, mechanical rules) stores coder type, model, version and request id; the per-run version record holds the codebook version, and per-code coder details are internal and linked to it; the row carries the codebook version + setup pointer; the classifier record keeps the chosen-answer probability. _[cleaned: change 13]_
- `coder_type`, `coder_model`, `coder_version`, `request_id` common across channels

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; row; internal

### language coverage

<sub>core.language_coverage</sub>

**Answer.** text

**Rules.** - Defined with the language-readiness bar
- AI-text flags fold into the main list, the language-barrier flag is dropped everywhere, and language coverage is carried by the multilingual subproject's item.

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; row; public

### support rule name

<sub>core.support_rule_name</sub>

**Answer.** text

**Rules.** - Add a rule-name item, empty unless the status is "set by rule".

**When it is asked.** 
- item: `core.support_status`
- values: `set_by_rule`
- gated out value: empty (record-01 a wording)

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; row; public

### support status second reason

<sub>core.support_status_second_reason</sub>

**Answer.** one answer

**Answers and their meaning.** - `downgraded_no_quote` — The answer also failed because it has no supporting quote.
- `downgraded_low_confidence` — The answer also failed because the classifier's certainty was below the 0.8 bar.
- `downgraded_quote_not_stating_value` — The answer also failed because its quote does not state the value.

**Rules.** - A second reason item
- Values: downgraded_no_quote, downgraded_low_confidence, downgraded_quote_not_stating_value. The main status takes the first failed check in check order (quote, then the 0.8 bar); the second item takes the other; empty when only one reason holds.
- *which codes can occur*: With this check order, only `downgraded_low_confidence` can be a second reason, because a failed quote check is always the main reason. The other two codes stay on the list so that it matches the support-status list. **[proposed change 5]**

**When it is asked.** 
- rule: empty unless two reasons hold (final-open F10)

**Missing labels it can take.** not asked, not documented, unknown

**Coded by; level; published.** mechanical; row; public

## Shared lists, rules and conventions

### Missing labels

<sub>vocabularies.missing</sub>

**Values.** `not_asked`, `not_documented`, `unknown`, `_NA_`

**Rules.** 
Missing-value tokens: one reserved set of four: "not asked" (`not_applicable` renamed "not asked" everywhere, T2) when a rule skipped the question; "not documented"; "unknown"; and `_NA_` for items on a row that has no activity. The temporary part answer of R-044 is not a reserved token. Exception: on pages whose verdict shows no GenAI, the description items and `content_data` take `no`, not "not asked". New and non-frozen fields adopt it; frozen CX items keep their signed spellings with a mapping row. _[cleaned: change 10, 12, 13]_
- na label: Store `not_asked` when a rule skips a question; store `_NA_` on items of a row that has no activity.
- published summary map: 
  - map: 
    - unresolved: `unknown`
    - not assessable: `unknown`
Keep them as values when coding; map them onto "unknown" in published summaries.
  - label text: Treat "unresolved" and "not assessable" as missing answers, reported as "unknown"
  - institution rule: Inside the institution-level rule both keep their current roles, and `not_assessable` stays out of the institution-rate base. _[cleaned: change 13]_
  - not assessable in institution rate base: no
- cx mapping row: Missing-answer labels. The signed spellings of these items are kept, and each maps to one of the codebook's reserved labels: "not asked" (ruled out by a rule), "not documented" (page silent), "unknown" (stated but undeterminable, or downgraded). Map: `unknown` of `disclosure_form` (CX-17) and of `disclosure_scope` (CX-24) → "unknown"; `unclear` of `evaluation_documented` (CX-33) → "unknown"; `not_documented` (CX-34) → "not documented"; `no` of the `evaluation_type_*` and `content_*` items → "not documented"; `none_reported` (CX-60, CX-61) → "not documented". Where these rows say an item is not asked (CX-25, CX-41, CX-51), it stores the reserved "not asked" label.
- cx mapping row location: Keep the new map row in the questionnaire; keep the "narrowed in" marks.

### How we know a value

<sub>vocabularies.provenance</sub>

**Values.** - `stated` — "Stated" = the page says it, whoever copied it
- `from_metadata` — The value comes from the page's metadata or its web address, or is the date the page was fetched; it is not read from the page text.
- `looked_up` — The value was found in a source other than the page itself, such as a web archive's record of when the page first appeared.
- `derived` — The value is computed by a rule from other coded values; it is not stated on the page or looked up.
- `quoted_by_quote_step` — "quoted by the quote step" = only the quote step's copy.

**Rules.** 
Every 'how we know' field uses the same five values: stated, from metadata, looked up, derived, quoted by the quote step. The per-run version record also holds the codebook version, the channel tag stays on each row, and per-code coder details are stored internally and linked to that record.
- date origin map: 
  - map: 
    - metadata: `from_metadata`
    - web address: `from_metadata`
    - page text quote: `quoted_by_quote_step`
    - archive upper bound: `looked_up`
    - unknown: missing-answer labels (vocabularies.missing)
    - access date: `from_metadata`
Web address to from metadata; page quote to quoted by the quote step; archive bound to looked up; unknown through the missing-answer labels; access date to from metadata; add a yes/no note "this date is an upper bound".
  - codes source: value-lists.json vocabularies.provenance alternatives['Date-origin list as ruled in r2#31'] (+ access date, A08)
  - upper bound item: `core.date_upper_bound`

### Quote support status

<sub>vocabularies.support_status</sub>

**Values.** `supported`, `downgraded_no_quote`, `downgraded_low_confidence`, `downgraded_quote_not_stating_value`, `set_by_rule`, `not_required`

**Rules.** 
Support-status values: `supported` / `downgraded_no_quote` / `downgraded_low_confidence` / `downgraded_quote_not_stating_value` / `set_by_rule`, for every value a rule fixed, including "not asked" and `_NA_` (exempt from the no-quote downgrade; record-02 a; O12) / `not_required`, for `not_documented`, `unknown`, `no` and negative page verdicts. _[cleaned: change 13]_
- rule name item: `core.support_rule_name`
- second reason item: `core.support_status_second_reason`
- rules:   - Add a rule-name item, empty unless the status is "set by rule".
  - "Set by rule" for anything a rule fixed, including "not asked"
  - `not_required`: the answer needs no supporting quote by its nature. It is given to `not_documented`, `unknown`, `no` and negative page verdicts. **[proposed change 9]**
  - Both reasons recorded
- status by answer: 
  - not documented: `not_required`
  - unknown: `not_required`
  - no: `not_required`
  - negative page verdicts (R-041): `not_required`
  - not asked: `set_by_rule`
  -  NA : `set_by_rule`

### Links between activities

<sub>vocabularies.relation</sub>

**Values.** `same_activity`, `component_of_program`, `has_component`, `shared_participation`, `governs`, `governed_by`, `distinct_action`, `unresolved`, `not_an_activity`

**Rules.** 
One shared relation list serves within-page and cross-page links: same activity, component of program, has component, shared participation, governs, governed by, distinct (`distinct_action`), unresolved, plus not-an-activity within a page. _[cleaned: change 13]_
- within page only: `not_an_activity`

### Generative-AI era cutoff

<sub>vocabularies.genai_era_cutoff</sub>

**Rules.** 
One shared date of 1 November 2022, with "before" needing proof. Date origin is recorded as metadata, web address, quote from page text, archive upper bound, or unknown; the AI-text code changes.

### Genai boundary

<sub>core.rule.genai_boundary</sub>

**Rule.** - Generative-AI wording: the re-pilot 2 wording governs (SRC-7 L34-45), including that a named "AI chatbot or AI assistant" counts as a generative product; `system_prompt.md` L15 rule ("chatbot" alone is not evidence) is amended to match. A named "AI chatbot" or "AI assistant" counts as generative and overrides the rule-based-chatbot exclusion (contract L12) for that naming.
- S1 a: translation counts as generative AI only when the page ties it to a named generative product or says a language model produces it.

### Activity unit

<sub>core.rule.activity_unit</sub>

**Rule.** - One activity = one action (deployment, governance instrument, staff training) by one actor concerning one tool or instrument. A named program is one activity; each named component is its own activity, linked to the program as a component of it. Repeated transactions for the same product by the same unit are one activity. A policy and the tools it approves are separate activities, linked by a "governs" relation.

### Ws10 event

<sub>core.rule.ws10_event</sub>

**Rule.** - WS10 D1 action boundary: a public-facing GenAI event or educational programme is not a qualifying activity; an event page can support a separate record only when it documents the institution's own adoption, procurement, deployment or governance.

### Ws10 governance

<sub>core.rule.ws10_governance</sub>

**Rule.** - WS10 D2: formal institution-issued GenAI governance qualifies whether it governs staff or external users; governance is recorded separately from deployment.

### Ws10 excluded only

<sub>core.rule.ws10_excluded_only</sub>

**Rule.** - WS10 D3: a completed review containing only clearly excluded events yields no qualifying evidence with exclusion reasons preserved; genuinely uncertain signals stay unclear.

### Ws10 proposals

<sub>core.rule.ws10_proposals</sub>

**Rule.** - WS10 D4: institution-specific, explicitly GenAI proposals remain a qualifying activity.

### Attribution grain

<sub>core.rule.attribution_grain</sub>

**Rule.** - An activity carried out by an organisational unit of the named institution (department, office, service) counts for the named institution. An activity of its parent, a sibling, or a separate court, board or authority does not, unless the page says the named institution takes part.
- A joint activity counts when the page names this institution as a participant.

### V26 detail fields

<sub>core.rule.v26_detail_fields</sub>

**Rule.** - v2.6 rules: observed actor distinguished from query target; each detail field independently supported or cleared; every source keeps its disposition, reason and original mention; page-level extraction cannot issue institution-wide `no`.

### Safeguard attachment

<sub>core.rule.safeguard_attachment</sub>

**Rule.** - A safeguard in a governance activity is not copied to deployment activities in pass 2. Stage 6 may link them only through a recorded relation.
- A contract with safeguard clauses is split off as a governance activity linked to the tool.

### Stated only

<sub>core.rule.stated_only</sub>

**Rule.** - Documented performance claims. Only record if explicitly stated. Never infer.

### Cx grain

<sub>core.rule.cx_grain</sub>

**Rule.** - **Page fields** (`disclosure_form`, `disclosure_scope`, the optional `content_*` items) are properties of the source page. They are coded once per (institution × page), on the stored page text the item declares as its input (the main text unless the item states otherwise), and copied to every evidence row from that page. The `content_*` items that CX-51 and CX-52 mark as derived are not asked; they are computed once per page from the codes of the activities on that page.
- **Finding fields** (`evaluation_documented`, optional `evaluation_type_*`, and the outcome and incident items of CX-61) are coded per (finding × page). The state given to jev is the page text plus that finding's `activity_name`, `activity_type`, `adoption_stage` and `tool_name`. The state of each question set (its fields, their order and the chunk marker) is pinned in the codebook and is part of the frozen instrument; any change to it counts as a wording change.
- Code what the page says. Never use outside knowledge of the institution, the country's laws or the register system.
- The codebook stores page-level and finding × page codes only. How page codes roll up to a finding, institution or country is an index decision (index decisions 6–8), not a codebook rule.
- The raw jev answer is stored with its probability distribution, confidence, response model id and request id.

### Applicability table

<sub>core.rule.applicability_table</sub>

**Rule.** - Tool and model name (and the developer derived from them)
- Purchase stage (asked in the draft)
- All tool questions asked of programs and proposals; governance bodies not treated as governance actions.
- Unknown-type activities get the full question set.
- The quote step runs for every activity; skipped items are kept internally and published as "not asked".

### Governance gate

<sub>core.rule.governance_gate</sub>

**Rule.** - A body that sets or oversees rules gets the governance questions.

### Allowed type action pairs

<sub>core.rule.allowed_type_action_pairs</sub>

**Rule.** - List the allowed (type, action) pairs; activities with other pairs are flagged for review
- a disallowed pair is flagged for review and no label is changed _[cleaned: change 13]_

### Combining long pages: check then combine

<sub>combining_conventions.check_then_combine</sub>

**Rule.** 
- rulings: `all-03`
- text:   - Each part's answer is checked (quote, 0.8 bar) before combining; downgraded parts enter as their downgrade target (`unknown`), except page verdicts, which keep their value and the downgraded tag. _[cleaned: change 13]_
  - Each part is checked as drafted; the prompt states the text is only part of the document; every question gets a temporary value "not covered by this part"; such parts do not vote when parts are combined; if every part gives it, the page is "not documented"; the temporary value is never published.
  - check each part but add a new to the prompt that this is only part of the doc & add a temporary value to each question "not covered by this part", to be taken into account when combining parts

### Combining long pages: not covered by this part

<sub>combining_conventions.not_covered_by_this_part</sub>

**Rule.** 
- rulings: `all-03`
- temporary value: not covered by this part
- published: no
- applies to: every question in every part prompt of a long page
- text:   - the prompt states the text is only part of the document; every question gets a temporary value "not covered by this part"; such parts do not vote when parts are combined; if every part gives it, the page is "not documented"; the temporary value is never published.
- generator check 16: the generator must add this value to every part prompt (fold-log-round3.md)

### Combining long pages: missing rank

<sub>combining_conventions.missing_rank</sub>

**Rule.** 
- rulings: `all-04`
- order: `real answers`, `not_documented`, `unknown`
- text:   - Real answers, then not documented, then unknown
  - A clean reading that the page is silent beats an unclear or failed answer.
  - `not_asked` never competes, because applicability is applied after the gating item is combined.

### Combining long pages: producing part

<sub>combining_conventions.producing_part</sub>

**Rule.** 
- rulings: `all-05`
- text:   - When several parts give the winning value, the producing part is the one with the highest chosen-answer probability (ties: earliest). Its probability and quote become the combined answer's.
  - Among parts giving the winning answer, take the highest certainty; ties go to the earliest part.

### Combining long pages: first part

<sub>combining_conventions.first_part</sub>

**Rule.** 
- rulings: `all-06`
- text:   - Skip silent or failed parts; take the first part with a supported real answer. For pooled evidence, sort by source date, then by position on the page.
  - The same rules apply to pooled Stage 6 evidence split into parts; first_section there needs a fixed pool order. _[cleaned: change 13]_

### Combining long pages: gate items first

<sub>combining_conventions.gate_items_first</sub>

**Rule.** 
- rulings: `all-04`
- text:   - activity_type and action_type (and the scale number) are combined before the items they gate.

### Combining long pages: activity level

<sub>combining_conventions.activity_level</sub>

**Rule.** 
- text:   - Activity items combine the answers about the same activity from every part holding one of its linked passages; parts without a passage do not vote.


## Procurement and AI-text modules

11 placeholder items for the procurement and AI-text pipelines stay outside the 2.7 build; they move over in a later release.
