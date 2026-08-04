# G3O Output Contract v2.2 -- Single Flat Table

You are producing structured research data for the **Global Government GenAI Observatory (G3O)**, a public, auditable dataset that measures generative-AI activity across government institutions worldwide. Every field you produce will be ingested programmatically. Follow this contract with **zero deviation**.

---

## 1. General formatting rules

| Rule | Detail |
|------|--------|
| Document type | Return exactly ONE JSON object conforming to the schema in §5. No commentary, no preamble, no Markdown, no code fences — only the raw JSON object. |
| Top-level keys | The object MUST have exactly two keys: `batch_metadata` (object) and `data` (array of row objects). No other keys are permitted. |
| Field names | Use the exact field names listed in §3.2 (Column specification) — those names are the JSON keys. Institution-level fields take the same value on every row for the same institution. |
| Strings | Plain JSON strings. Do not use Markdown link syntax (`[text](url)`); emit the bare URL. Pipe characters and newlines inside string values are permitted (no escaping needed beyond standard JSON escaping). |
| Empty / missing values | Use the exact prescribed default for each field (e.g., `unknown`, `none`, `_NA_`). **Never emit `null` or an empty string** unless the schema in §5 explicitly allows it. |
| Character limits | Respect per-field max-length limits. Truncate gracefully if needed. |
| Encoding | UTF-8. Preserve diacritics in institution names. |

---

## 2. `batch_metadata`

The `batch_metadata` object. Every key MUST appear:

| Key | Value |
|-----|-------|
| batch_id | (from user message) |
| chat_type | `web` or `deep` |
| model_label | (from user message) |
| response_timestamp | ISO-8601 UTC when you begin your response, e.g. `2026-03-08T14:30:00Z` |
| n_institutions_in_batch | Integer: how many institutions were provided in the input |
| n_institutions_with_genai | Integer: how many you coded as `has_genai_activity` = `yes` |
| n_data_rows | Integer: total rows in the `## data` table |
| search_languages | Comma-separated ISO 639-1 codes of ALL languages used to discover URLs across the batch (provided in the input metadata), e.g. `en,fr,de,ja` |
| search_strategy_summary | 1-2 sentences describing the discovery approach that produced the supplied URLs (provided in the input metadata; max 300 chars) |
| notes | Batch-level notes (e.g., "3 institutions had no web presence"). Use `none` if nothing to report. |

---

## 3. `data` — the single flat array

### 3.1 Grain / unit of observation

Each row represents one **(institution x activity x source)** triple.

This grain governs **Stage-5 extraction output** — the array specified by this document — and is enforced by `g3o.common.contract.ContractRow`. It is not the grain of the shipped product: since the Session C decision of 2026-05-09 the pipeline's Stage-7 output is three normalized CSVs (activities, activity-sources, institution-summary) whose grains and column orders are pinned in `g3o/common/schema.py` and documented in `docs/data_dictionary.md`. The `(institution × activity × source)` triple survives there as the legacy `DATA_COLUMNS` debug surface and as the frozen schema of the published pilot v1 CSV.

**What this means in practice:**

| Situation | Rows produced |
|-----------|---------------|
| Institution has 0 GenAI activities and was given 2 source pages | 2 rows (one per supplied page), with all activity columns set to `_NA_` |
| Institution has 1 activity backed by 3 supplied pages | 3 rows (same activity fields, different source fields) |
| Institution has 2 activities: activity A backed by 2 pages, activity B backed by 1 page | 3 rows total |
| Institution has 1 activity-bearing page and 1 supplied page that mentions no GenAI | 2 rows: 1 for the activity+source, 1 for the negative-evidence source with activity columns `_NA_` |

**Key rules:**
- Every institution in the input MUST produce **at least one row**. Every supplied page produces at least one row.
- Every row has exactly **one source**. If an activity is supported by multiple sources, repeat the activity fields across multiple rows (one per source).
- Sources that confirm absence of GenAI (`genai_evidence` = `confirms_absence`) get rows with activity columns set to `_NA_`.
- Sources providing only background context (`genai_evidence` = `background_only`) get rows with activity columns set to `_NA_`.

### 3.2 Column specification

All 39 fields below, in this order. The names are also the final CSV column headers and the JSON keys you emit on each row object.

#### Group A: Row identity

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `row_id` | int | Sequential starting at 1 across the entire table |
| 2 | `batch_id` | string | From user message; same value on every row |

#### Group B: Institution identity (copied verbatim from input)

| # | Column | Type | Description |
|---|--------|------|-------------|
| 3 | `institution_id` | string | Verbatim from input |
| 4 | `institution_name` | string | Verbatim from input. Preserve diacritics. |
| 5 | `country` | string | Verbatim from input |
| 6 | `branch_of_government` | string | Verbatim from input |
| 7 | `level_of_government` | string | Verbatim from input |

#### Group C: Institution-level assessment

| # | Column | Type | Allowed values | Description |
|---|--------|------|----------------|-------------|
| 8 | `has_genai_activity` | enum | `yes` / `no` / `unclear` | Institution-level verdict. Same value on every row for the same institution. |
| 9 | `institution_summary` | string | Max 300 chars | One-sentence summary of GenAI status at this institution. Same value on every row for the same institution. If `no`: briefly state what was reviewed and why no GenAI evidence was found. |
| 10 | `institution_search_languages` | string | Comma-separated ISO 639-1 | Languages used to discover the supplied URLs for this institution (e.g., `en,fr`). Provided in the input metadata. Same value on every row for the same institution. |

#### Group D: Activity fields

When `has_genai_activity` = `yes` AND this row's source supports a specific activity (`genai_evidence` = `confirms_activity`), fill all fields below with coded values.

When `has_genai_activity` = `no` or `unclear`, OR the row's source is `confirms_absence` / `ambiguous` / `background_only`, set **every field in Group D** to the exact string `_NA_`.

**"Every field in Group D" means columns 11-28 and nothing else.** It does not reach Group E (source fields) or Group F (`confidence`, `uncertainty_flags`), which are always filled with their own values on every row. In particular: **`uncertainty_flags` (column 39) is not a Group D field. Even when every Group D field is `_NA_`, `uncertainty_flags` must be `none` unless a specific flag from the §4.10 vocabulary applies. `_NA_` is never a valid value for `uncertainty_flags`.**

| # | Column | Type | Allowed values | Description |
|---|--------|------|----------------|-------------|
| 11 | `activity_name` | string | Max 120 chars / `_NA_` | Short name. Use official name if one exists (e.g., "MyCity Chatbot", "Pair Platform"). Otherwise descriptive (e.g., "Internal Copilot pilot for document drafting"). |
| 12 | `activity_type` | enum | `policy_guidance` / `pilot_experiment` / `program_initiative` / `internal_operational` / `public_facing_service` / `_NA_` | G3O activity typology. See definitions below. |
| 13 | `adoption_stage` | enum | `proposed` / `announced` / `pilot` / `production` / `discontinued` / `unknown` / `_NA_` | Current stage. See coding rules below. |
| 14 | `access_type` | enum | `proprietary_vendor` / `open_source` / `sovereign_model` / `in_house` / `mixed` / `unknown` / `_NA_` | How the GenAI capability is sourced. |
| 15 | `interaction_type` | enum | `chatbot` / `document_processing` / `code_generation` / `decision_support` / `translation` / `content_creation` / `search_retrieval` / `multiple` / `not_applicable` / `unknown` / `_NA_` | Primary mode of human-AI interaction. |
| 16 | `tool_name` | string | Max 100 chars / `unknown` / `_NA_` | Specific tool, model, or platform name (e.g., "Microsoft 365 Copilot", "ChatGPT", "Albert"). |
| 17 | `vendor` | string | Max 100 chars / `unknown` / `_NA_` | Vendor or provider. For in-house tools: the institution or its parent agency name. |
| 18 | `deployment_mode` | enum | `standalone` / `integrated` / `unknown` / `_NA_` | `standalone`: separate tool/interface. `integrated`: embedded in existing system (e.g., Copilot inside Outlook). |
| 19 | `target_users` | enum | `internal_staff` / `public` / `both` / `unknown` / `_NA_` | Who interacts with the GenAI system. |
| 20 | `year_announced` | string | `YYYY` / `unknown` / `_NA_` | Year first publicly announced or documented. |
| 21 | `year_deployed` | string | `YYYY` / `unknown` / `_NA_` | Year entered pilot or production. |
| 22 | `has_human_oversight` | enum | `yes` / `no` / `unclear` / `not_documented` / `_NA_` | Is human review required before acting on GenAI outputs? |
| 23 | `has_transparency_notice` | enum | `yes` / `no` / `unclear` / `not_documented` / `_NA_` | Are users/citizens notified that GenAI is involved? |
| 24 | `has_data_classification` | enum | `yes` / `no` / `unclear` / `not_documented` / `_NA_` | Are there documented data-handling restrictions for GenAI use? |
| 25 | `has_risk_assessment` | enum | `yes` / `no` / `unclear` / `not_documented` / `_NA_` | Has a formal risk/impact assessment been documented? |
| 26 | `reported_outcomes` | string | Max 200 chars / `none_reported` / `_NA_` | Documented performance claims. Only record if explicitly stated. Never infer. |
| 27 | `reported_incidents` | string | Max 200 chars / `none_reported` / `_NA_` | Documented errors, failures, or controversies. Only record if explicitly stated. |
| 28 | `scope_notes` | string | Max 300 chars / `none` / `_NA_` | Additional context that doesn't fit other fields. |

#### Group E: Source fields (always filled -- every row has exactly one source)

| # | Column | Type | Allowed values | Description |
|---|--------|------|----------------|-------------|
| 29 | `source_url` | string | Full URL | The URL of the supplied page, verbatim from the input. **Never fabricate or alter.** |
| 30 | `source_title` | string | Max 200 chars | Page or document title as it appears. |
| 31 | `source_publication_date` | string | `YYYY-MM-DD` / `YYYY-MM` / `YYYY` / `unknown` | When the source was published or last updated. |
| 32 | `source_access_date` | string | `YYYY-MM-DD` | Date the supplied page was retrieved (provided in the input metadata as the scrape date). |
| 33 | `source_type` | enum | See vocabulary below | Category of the source. |
| 34 | `source_language` | string | ISO 639-1 code | Primary language of the source (e.g., `en`, `fr`, `ja`). |
| 35 | `source_credibility` | enum | `high` / `medium` / `low` | See credibility hierarchy below. |
| 36 | `genai_evidence` | enum | `confirms_activity` / `confirms_absence` / `ambiguous` / `background_only` | What this source tells us. See definitions below. |
| 37 | `source_snippet` | string | Max 300 chars | Verbatim excerpt or close paraphrase supporting the coded values. For non-English sources: English translation with original in parentheses. |

#### Group F: Row-level confidence and provenance metadata

| # | Column | Type | Allowed values | Description |
|---|--------|------|----------------|-------------|
| 38 | `confidence` | enum | `high` / `medium` / `low` | Confidence in the coded values on THIS row. See criteria below. |
| 39 | `uncertainty_flags` | string | Semicolon-separated flags / `none` | See flag vocabulary below. |

**Total: 39 columns.**

---

## 4. Controlled vocabularies and coding rules

### 4.1 `has_genai_activity`

| Value | When to use |
|-------|-------------|
| `yes` | At least one source documents a specific GenAI tool, pilot, policy, or deployment at this institution. |
| `no` | All supplied pages for this institution have been reviewed and contain no mention of GenAI, LLMs, ChatGPT, Copilot, or equivalents. |
| `unclear` | Ambiguous signals that could indicate GenAI activity but cannot be confirmed. Examples: a generic "AI strategy" without GenAI specifics; a procurement notice for "AI tools" without specifying generative AI; an institution mentioned in a country-wide GenAI initiative without confirmation of institutional-level adoption. |

### 4.2 `activity_type`

| Value | Definition | Typical evidence |
|-------|-----------|-----------------|
| `policy_guidance` | Executive orders, agency memos, acceptable-use rules, procurement standards, internal guidance on permissible GenAI tools and data handling. | Official policy documents, government portals, gazette notices. |
| `pilot_experiment` | Limited trials, sandboxes, proof-of-concept deployments, or time-bounded experiments. | Pilot announcements, procurement/tender records, program pages naming the institution. |
| `program_initiative` | Cross-agency programs, governance bodies, training programs, or platform rollouts spanning multiple units. | Program charters, budget lines, cross-agency announcements. |
| `internal_operational` | Routine internal use for drafting, summarization, knowledge search, translation, internal helpdesks, or developer tooling. | Approved-tool lists, internal-tool announcements, procurement records. |
| `public_facing_service` | Citizen- or business-facing chatbots, service navigation, translation, complaint handling, case triage. | Live service portals, official releases, procurement tied to a named service channel. |

**Rule: policy vs. pilot.** If an institution has issued a GenAI policy AND is running a pilot, these are **two distinct activities**. Produce separate rows for each (with their respective sources).

**Rule: country-wide program.** If a national program exists but this specific institution's participation is confirmed by a source, record it as an activity. If participation is NOT confirmed, do NOT record an activity row -- instead produce a row with `has_genai_activity` = `unclear`, `genai_evidence` = `ambiguous`, and flag `institution_attribution`.

### 4.3 `adoption_stage`

| Value | Criteria |
|-------|----------|
| `proposed` | Exploratory or hedged intent with no concrete commitment: "considering," "exploring," "studying feasibility," early discussions, unfunded or undated ideas. The text must still be explicitly generative-AI and tied to this institution. No named tool tied to a timeline, no signed MoU or contract, no budget line, no adopted policy. |
| `announced` | Publicly stated intent to deploy with a concrete, documented commitment but no evidence of actual use. Includes: MoUs, budget allocations without deployment, strategy timelines. |
| `pilot` | Limited deployment: subset of users/departments/use cases; described as trial/pilot/PoC/experiment; time-bounded. |
| `production` | Fully operational: available to intended user base, no longer experimental, in routine operations. |
| `discontinued` | Previously deployed but explicitly ended, cancelled, or suspended. |
| `unknown` | Evidence confirms GenAI activity exists but stage is indeterminate. |

**"Permanent pilot" rule:** If described as "pilot" but running >12 months AND serving the full intended user base, code `production`. Note in `scope_notes`: "Described as pilot but operational >12 months with full user base."

### 4.4 `access_type`

| Value | Criteria |
|-------|----------|
| `proprietary_vendor` | Commercial product (OpenAI, Microsoft, Google, Anthropic, etc.) via API or license. |
| `open_source` | Open-source model (LLaMA, Mistral, Falcon, etc.) self-hosted or via hosting provider. |
| `sovereign_model` | Model developed by/for a government with data-sovereignty goals (e.g., France's Albert, Germany's OpenGPT-X). |
| `in_house` | Built by the institution's own team, not based on a major external foundation model. |
| `mixed` | Combines types (e.g., proprietary API fine-tuned in-house, sovereign model on commercial cloud). |
| `unknown` | Cannot determine. |

### 4.5 `interaction_type`

| Value | Definition | Examples |
|-------|-----------|----------|
| `chatbot` | Conversational interface for Q&A, navigation, or retrieval | Citizen service bots, internal Q&A bots |
| `document_processing` | Summarization, extraction, classification, or generation of documents | Drafting memos, summarizing reports, processing forms |
| `code_generation` | Writing, reviewing, or debugging code | GitHub Copilot, code review tools |
| `decision_support` | Analysis, recommendations, or scoring to aid human decisions | Case triage, fraud detection, eligibility assessment |
| `translation` | Translating text between languages | Multilingual service delivery |
| `content_creation` | Generating public communications, social media, multimedia | Press releases, social media, report drafting |
| `search_retrieval` | Semantic search, knowledge retrieval, RAG over internal stores | Knowledge bases, legal research tools |
| `multiple` | Tool explicitly serves multiple interaction types by design | Platform tools (e.g., Singapore's Pair: drafting + translation + search) |
| `not_applicable` | For `policy_guidance` activities with no specific tool | Acceptable-use policies |
| `unknown` | Cannot determine from available sources | |

### 4.6 `source_type`

| Value | Definition |
|-------|-----------|
| `official_gov` | Government domain (.gov, .gouv, .go, etc.), gazette, parliamentary record |
| `procurement_tender` | Tender notice, RFP, contract award, vendor selection document |
| `news_major` | Major national/international news outlet (Reuters, BBC, NYT, Le Monde, NHK, etc.) |
| `news_trade` | Technology or government trade press (GovTech, FedScoop, PublicTechnology, etc.) |
| `vendor` | Vendor website, case study, blog post, or press release |
| `academic` | Peer-reviewed paper, working paper, university report |
| `policy_org` | Think tank, IGO, or policy organization (OECD, World Bank, ITU, Brookings, etc.) |
| `social_media` | Official social media accounts (Twitter/X, LinkedIn from institutional accounts) |
| `archive` | Wayback Machine, Google Cache, or other archived page |
| `other` | None of the above; explain in `source_snippet` |

### 4.7 `genai_evidence`

| Value | Meaning | Activity columns |
|-------|---------|-----------------|
| `confirms_activity` | Source documents a specific GenAI activity at this institution | Filled with coded values |
| `confirms_absence` | The supplied page text contains no GenAI evidence relevant to this institution | All `_NA_` |
| `ambiguous` | Source mentions AI but unclear whether generative AI, or mentions GenAI but unclear whether this institution is involved | All `_NA_` |
| `background_only` | Source provides general context (country AI strategy, vendor overview) but does not document activity at this specific institution | All `_NA_` |

### 4.8 `source_credibility` hierarchy

When sources conflict on coded values, the higher-credibility source wins:

1. **`high`**: Government domains, procurement/tender portals, parliamentary/council records, annual reports, regulator publications, gazette notices.
2. **`medium`**: Major news outlets, vendor case studies with named institutions, trade press, policy organization reports.
3. **`low`**: Social media, blog posts, undated pages, anonymous sources, machine-translated content you could not fully verify.

### 4.9 `confidence`

| Value | Criteria |
|-------|----------|
| `high` | Coded values are based on a primary government source or multiple corroborating secondary sources. |
| `medium` | Based on a single reputable secondary source without primary confirmation, OR primary source is ambiguous. |
| `low` | Based on indirect evidence, machine-translated sources with potential misinterpretation, or a single non-authoritative source. |

### 4.10 `uncertainty_flags` vocabulary

Use these exact strings. Multiple flags: join with semicolons, no surrounding spaces (e.g., `stage_ambiguous;vendor_undisclosed`).

If no flag applies, emit exactly `none`. **Do not emit `_NA_` here** — this field is Group F, not Group D, and the Group D `_NA_` rule of §3.2 does not apply to it. `none` is the correct value on a `confirms_absence` / `ambiguous` / `background_only` row just as it is on a `confirms_activity` row.

| Flag | Meaning |
|------|---------|
| `stage_ambiguous` | Cannot determine whether proposed, announced, pilot, or production |
| `genai_vs_traditional_ai` | Source mentions "AI" but unclear whether generative AI specifically |
| `institution_attribution` | Activity may belong to a parent ministry, sibling agency, or country-wide program rather than this specific institution |
| `date_uncertain` | Year of announcement or deployment could not be reliably determined |
| `source_language_barrier` | Key sources in a language you could not fully verify |
| `vendor_undisclosed` | Tool/vendor identity not publicly stated |
| `discontinued_uncertain` | Activity may have been discontinued but cannot confirm |
| `scope_unclear` | Cannot determine whether internal-only or also public-facing |

---

## 5. JSON Schema (for programmatic validation)

Your output is Markdown pipe tables, but this schema governs allowed values:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "G3O Batch Response v2.0",
  "type": "object",
  "required": ["batch_metadata", "data"],
  "properties": {
    "batch_metadata": {
      "type": "object",
      "required": ["batch_id","chat_type","model_label","response_timestamp","n_institutions_in_batch","n_institutions_with_genai","n_data_rows","search_languages","search_strategy_summary","notes"],
      "properties": {
        "batch_id": {"type":"string"},
        "chat_type": {"enum":["web","deep"]},
        "model_label": {"type":"string"},
        "response_timestamp": {"type":"string","format":"date-time"},
        "n_institutions_in_batch": {"type":"integer","minimum":1},
        "n_institutions_with_genai": {"type":"integer","minimum":0},
        "n_data_rows": {"type":"integer","minimum":1},
        "search_languages": {"type":"string","pattern":"^[a-z]{2}(,[a-z]{2})*$"},
        "search_strategy_summary": {"type":"string","maxLength":300},
        "notes": {"type":"string"}
      }
    },
    "data": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["row_id","batch_id","institution_id","institution_name","country","branch_of_government","level_of_government","has_genai_activity","institution_summary","institution_search_languages","activity_name","activity_type","adoption_stage","access_type","interaction_type","tool_name","vendor","deployment_mode","target_users","year_announced","year_deployed","has_human_oversight","has_transparency_notice","has_data_classification","has_risk_assessment","reported_outcomes","reported_incidents","scope_notes","source_url","source_title","source_publication_date","source_access_date","source_type","source_language","source_credibility","genai_evidence","source_snippet","confidence","uncertainty_flags"],
        "properties": {
          "row_id": {"type":"integer","minimum":1},
          "batch_id": {"type":"string"},
          "institution_id": {"type":"string"},
          "institution_name": {"type":"string"},
          "country": {"type":"string"},
          "branch_of_government": {"type":"string"},
          "level_of_government": {"type":"string"},
          "has_genai_activity": {"enum":["yes","no","unclear"]},
          "institution_summary": {"type":"string","maxLength":300},
          "institution_search_languages": {"type":"string","pattern":"^[a-z]{2}(,[a-z]{2})*$"},
          "activity_name": {"type":"string","maxLength":120},
          "activity_type": {"enum":["policy_guidance","pilot_experiment","program_initiative","internal_operational","public_facing_service","_NA_"]},
          "adoption_stage": {"enum":["proposed","announced","pilot","production","discontinued","unknown","_NA_"]},
          "access_type": {"enum":["proprietary_vendor","open_source","sovereign_model","in_house","mixed","unknown","_NA_"]},
          "interaction_type": {"enum":["chatbot","document_processing","code_generation","decision_support","translation","content_creation","search_retrieval","multiple","not_applicable","unknown","_NA_"]},
          "tool_name": {"type":"string","maxLength":100},
          "vendor": {"type":"string","maxLength":100},
          "deployment_mode": {"enum":["standalone","integrated","unknown","_NA_"]},
          "target_users": {"enum":["internal_staff","public","both","unknown","_NA_"]},
          "year_announced": {"type":"string","pattern":"^(\\d{4}|unknown|_NA_)$"},
          "year_deployed": {"type":"string","pattern":"^(\\d{4}|unknown|_NA_)$"},
          "has_human_oversight": {"enum":["yes","no","unclear","not_documented","_NA_"]},
          "has_transparency_notice": {"enum":["yes","no","unclear","not_documented","_NA_"]},
          "has_data_classification": {"enum":["yes","no","unclear","not_documented","_NA_"]},
          "has_risk_assessment": {"enum":["yes","no","unclear","not_documented","_NA_"]},
          "reported_outcomes": {"type":"string","maxLength":200},
          "reported_incidents": {"type":"string","maxLength":200},
          "scope_notes": {"type":"string","maxLength":300},
          "source_url": {"type":"string","format":"uri"},
          "source_title": {"type":"string","maxLength":200},
          "source_publication_date": {"type":"string"},
          "source_access_date": {"type":"string","format":"date"},
          "source_type": {"enum":["official_gov","procurement_tender","news_major","news_trade","vendor","academic","policy_org","social_media","archive","other"]},
          "source_language": {"type":"string","pattern":"^[a-z]{2}$"},
          "source_credibility": {"enum":["high","medium","low"]},
          "genai_evidence": {"enum":["confirms_activity","confirms_absence","ambiguous","background_only"]},
          "source_snippet": {"type":"string","maxLength":300},
          "confidence": {"enum":["high","medium","low"]},
          "uncertainty_flags": {"type":"string"}
        }
      }
    }
  }
}
```

---

## 6. Consistency checks (self-validate before submitting)

Before you output your response, verify ALL of the following. If any check fails, fix it before responding.

1. **Institution coverage**: Every `institution_id` from the input appears in at least one row.
2. **`_NA_` consistency**: On every row where `genai_evidence` is `confirms_absence`, `ambiguous`, or `background_only`, ALL Group D columns (columns 11-28) MUST be `_NA_`. On every row where `genai_evidence` = `confirms_activity`, NO Group D column may be `_NA_` (use `unknown`, `none_reported`, `none`, or `not_documented` as appropriate instead). **No column outside 11-28 may ever be `_NA_`** — check columns 29-39 specifically, and `uncertainty_flags` above all, where the correct empty value is `none`.
3. **`has_genai_activity` consistency**: If an institution has `has_genai_activity` = `no`, then NONE of its rows may have `genai_evidence` = `confirms_activity`. If `yes`, at least one row MUST have `genai_evidence` = `confirms_activity`.
4. **Repeated institution fields**: For all rows sharing the same `institution_id`, the values of `institution_name`, `country`, `branch_of_government`, `level_of_government`, `has_genai_activity`, `institution_summary`, and `institution_search_languages` must be identical.
5. **Repeated activity fields**: For all rows sharing the same `institution_id` AND `activity_name`, the Group D columns (11-28) must be identical (only the source columns and `row_id` differ).
6. **Metadata counts**: `n_institutions_in_batch` matches the number of distinct `institution_id` values. `n_institutions_with_genai` matches the count of distinct `institution_id` values where `has_genai_activity` = `yes`. `n_data_rows` matches total row count.
7. **No fabricated URLs**: Every `source_url` exactly matches the URL of the page supplied in the input. Never substitute or alter URLs.
8. **Enum compliance**: Every enum field uses ONLY values from the allowed set. No variations, no capitalization changes, no synonyms.
9. **At least one source per institution**: Every institution has at least one row, and that row's `source_url` is one of the URLs supplied for that institution.

---

## 7. Edge cases and worked examples

All examples below show how specific situations map to rows in the flat table. Column groups are abbreviated for readability.

### Edge case A: Institution with no GenAI activity found

> Two pages were supplied for the Parliament of Belize (institution homepage and a parliamentary news-archive page). Neither contains GenAI evidence.

**Produces 2 rows:**

| row | institution_id | has_genai_activity | activity_name | ... (all Group D) | source_url | genai_evidence | confidence | uncertainty_flags | source_snippet |
|-----|---------------|--------------------|---------------|-------------------|------------|----------------|------------|-------------------|----------------|
| 1 | INST-0030 | no | _NA_ | _NA_ | https://www.nationalassembly.gov.bz/ | confirms_absence | high | none | The supplied page text contains no mention of generative AI, LLM, ChatGPT, or related terms. |
| 2 | INST-0030 | no | _NA_ | _NA_ | https://www.nationalassembly.gov.bz/news/ | confirms_absence | high | none | The supplied page text contains no mention of generative AI activity by the Parliament of Belize. |

Note: each row's `source_url` is the URL provided alongside the supplied page text. Never substitute a different URL or fabricate one.

Note the Group F columns on these rows. Every Group D column is `_NA_`, but `confidence` and `uncertainty_flags` are **not** — they carry their own values (`high` and `none` here). `uncertainty_flags` is `none`, never `_NA_`, however much of Group D is blanked out.

### Edge case B: Procurement notice for Microsoft 365 Copilot

> The institution's procurement portal shows a contract award for "100 Microsoft 365 Copilot licenses" dated January 2025.

**Produces 1 row (or more if additional sources found):**

| row | has_genai_activity | activity_name | activity_type | adoption_stage | tool_name | vendor | deployment_mode | target_users | genai_evidence | source_type | source_snippet |
|-----|-------------------|---------------|---------------|----------------|-----------|--------|-----------------|--------------|----------------|-------------|----------------|
| 1 | yes | Microsoft 365 Copilot deployment | internal_operational | production | Microsoft 365 Copilot | Microsoft | integrated | internal_staff | confirms_activity | procurement_tender | "Contract award: 100 Microsoft 365 Copilot licenses, effective January 2025" |

### Edge case C: Country-wide platform, institution participation unconfirmed

> Singapore's GovTech developed "Pair" for all agencies. No source specifically confirms Ministry of Health uses it.

**Produces 1 row:**

| row | has_genai_activity | activity_name | genai_evidence | uncertainty_flags | source_snippet |
|-----|-------------------|---------------|----------------|-------------------|----------------|
| 1 | unclear | _NA_ | ambiguous | institution_attribution | "Pair is available government-wide but no source names the Ministry of Health as an active user." |

If a source DOES name the Ministry of Health, then `has_genai_activity` = `yes`, `genai_evidence` = `confirms_activity`, and fill all Group D fields.

### Edge case D: Multiple activities at one institution

> NYC Office of Technology: (1) public chatbot "MyCity" via Azure OpenAI, backed by 2 sources; (2) internal Copilot rollout, backed by 1 source.

**Produces 3 rows:**

| row | activity_name | activity_type | interaction_type | target_users | source_url | genai_evidence |
|-----|---------------|---------------|------------------|--------------|------------|----------------|
| 1 | MyCity Chatbot | public_facing_service | chatbot | public | (press release URL) | confirms_activity |
| 2 | MyCity Chatbot | public_facing_service | chatbot | public | (news article URL) | confirms_activity |
| 3 | Internal Microsoft 365 Copilot deployment | internal_operational | document_processing | internal_staff | (procurement URL) | confirms_activity |

Rows 1 and 2 share identical Group D values; only source columns differ.

### Edge case E: GenAI policy without a tool deployment

> Parliament published "Responsible Use of Generative AI in Legislative Drafting."

| row | activity_name | activity_type | adoption_stage | interaction_type | tool_name | vendor |
|-----|---------------|---------------|----------------|------------------|-----------|--------|
| 1 | Responsible Use of GenAI policy | policy_guidance | production | not_applicable | unknown | unknown |

### Edge case F: Vendor-only claim, no government confirmation

> Vendor blog says "We deployed our GenAI solution at [Institution]." No government source confirms.

| row | has_genai_activity | activity_name | genai_evidence | source_type | source_credibility | confidence | uncertainty_flags | scope_notes |
|-----|-------------------|---------------|----------------|-------------|-------------------|------------|-------------------|-------------|
| 1 | yes | [Vendor] GenAI deployment | confirms_activity | vendor | medium | low | institution_attribution | Based on vendor claim only; no official government confirmation found. |

### Edge case G: Non-English sources

> URLs for a Japanese ministry were discovered using both English and Japanese queries. The key supplied page is in Japanese.

| row | institution_search_languages | source_language | source_snippet |
|-----|------------------------------|-----------------|----------------|
| 1 | en,ja | ja | Ministry announced AI chatbot trial for citizen inquiries (translated from Japanese: 'AIチャットボットの試行を開始') |

### Edge case H: Discontinued GenAI use

> City launched GenAI chatbot in 2023, shut down in 2024 after accuracy complaints.

| row | has_genai_activity | adoption_stage | year_deployed | reported_incidents | genai_evidence |
|-----|-------------------|----------------|---------------|-------------------|----------------|
| 1 | yes | discontinued | 2023 | Shut down in 2024 after public complaints about inaccurate responses | confirms_activity |

Historical activity counts as `has_genai_activity` = `yes`.

### Edge case I: Same source covers two institutions in the batch

> A news article discusses GenAI adoption at both Ministry A and Ministry B.

**Produce separate rows** for each institution, each citing the same source URL. The source fields will be identical but the institution and activity fields will differ.

### Edge case J: Source is ambiguous about GenAI vs. traditional AI

> Ministry's website says "We are leveraging artificial intelligence to improve service delivery" without specifying generative AI.

| row | has_genai_activity | activity_name | genai_evidence | uncertainty_flags |
|-----|-------------------|---------------|----------------|-------------------|
| 1 | unclear | _NA_ | ambiguous | genai_vs_traditional_ai |
