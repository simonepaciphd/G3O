# G3O Validation Contract v1.2 -- Per-Institution Consolidation

You are producing the consolidated, deduplicated, conflict-resolved record for one institution as the Stage 6 (Validation) output of the G3O production pipeline. Every field is ingested programmatically. Follow this contract with **zero deviation**.

This contract sits downstream of the G3O Output Contract (`g3o/extract/prompts/output_contract.md`). Vocabulary references (source-credibility tiers, uncertainty-flag vocabulary, `genai_evidence` semantics, controlled enum values) inherit from it; this document only specifies what changes for the consolidated shape.

---

## 1. General formatting rules

| Rule | Detail |
|------|--------|
| Document type | Return exactly ONE JSON object conforming to the schema in §6. No commentary, no preamble, no Markdown, no code fences -- only the raw JSON object. |
| Top-level keys | The object MUST have exactly four keys: `consolidation_metadata` (object), `institution` (object), `activities` (array), `sources` (array of >=1 element). No other keys are permitted. |
| Field names | Use the exact field names listed in §§2-5 -- those names are the JSON keys. |
| Strings | Plain JSON strings. Do not use Markdown link syntax (`[text](url)`); emit the bare URL. |
| Empty / missing values | Use the prescribed default for each field (`unknown`, `none_reported`, `not_documented`, `none`). **Never emit `null` or an empty string** unless the schema explicitly allows it. |
| `_NA_` rule | `_NA_` is permitted in EXACTLY ONE place: `SourceRecord.activity_id` when the source's `genai_evidence` is `confirms_absence`, `ambiguous`, or `background_only`. Group D fields in `ConsolidatedActivity` are NEVER `_NA_`. |
| Character limits | Respect per-field max-length limits. Truncate gracefully if needed. |
| Encoding | UTF-8. Preserve diacritics in institution names, activity names, source titles, and snippets. |

---

## 2. `consolidation_metadata`

The `consolidation_metadata` object. Every key MUST appear:

| Key | Value |
|-----|-------|
| institution_id | (from user message; must equal `institution.institution_id`) |
| n_input_pages | Integer >=1: count of distinct source pages consolidated |
| n_input_rows | Integer >=1: total Stage 5 rows you consolidated |
| response_timestamp | ISO-8601 UTC when you begin your response, e.g. `2026-05-09T14:30:00Z` |
| model_label | Your model identifier, e.g. `gpt-5-nano` |
| notes | Consolidation-level notes (e.g., conflict-resolution choices, ambiguity decisions). Use `none` if nothing to report. |

---

## 3. `institution`

The institution-level metadata block -- exactly one record per response.

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| institution_id | string | input | Verbatim from input |
| institution_name | string | input | Verbatim from input. Preserve diacritics. |
| country | string | input | Verbatim from input |
| branch_of_government | string | input | Verbatim from input |
| level_of_government | string | input | Verbatim from input |
| has_genai_activity | enum: `yes` / `no` / `unclear` | your judgment | Institution-level verdict per §3.1 |
| institution_summary | string, max 300 chars | your synthesis | One-sentence summary. See §3.2. |
| institution_search_languages | string, comma-sep ISO 639-1 | input | Verbatim from input metadata |

### 3.1 `has_genai_activity` verdict rules

- `yes` <=> `len(activities) >= 1` AND >=1 source has `genai_evidence = confirms_activity`.
- `no` <=> `len(activities) == 0` AND every source has `genai_evidence = confirms_absence`.
- `unclear` <=> `len(activities) == 0` AND no source has `genai_evidence = confirms_activity` (sources are some mix of `ambiguous` / `background_only`; at least one such source exists).

### 3.2 `institution_summary` rules

ONE sentence, max 300 chars. Take the most informative `institution_summary` from the input rows; tie-break by Tier-1 source. If `has_genai_activity = no`, briefly state what was reviewed.

---

## 4. `activities`

An array of `(institution × activity)` records. Cardinality follows §3.1: empty when `has_genai_activity != yes`.

### 4.1 Structure

Each activity object has the following keys (all required):

| # | Field | Type | Allowed values | Description |
|---|-------|------|----------------|-------------|
| 1 | activity_id | string | `^A[1-9]\d*$` | `A1`, `A2`, `A3`, ... -- per-institution, gapless, in input-row-appearance order |
| 2 | activity_name | string | Max 120 chars; NOT `_NA_` | Canonical name; use most authoritative input wording |
| 3 | activity_type | enum | `policy_guidance` / `pilot_experiment` / `program_initiative` / `internal_operational` / `public_facing_service` / `unknown` | NO `_NA_` |
| 4 | adoption_stage | enum | `proposed` / `announced` / `pilot` / `production` / `discontinued` / `unknown` | NO `_NA_` |
| 5 | access_type | enum | `proprietary_vendor` / `open_source` / `sovereign_model` / `in_house` / `mixed` / `unknown` | NO `_NA_` |
| 6 | interaction_type | enum | `chatbot` / `document_processing` / `code_generation` / `decision_support` / `translation` / `content_creation` / `search_retrieval` / `multiple` / `not_applicable` / `unknown` | NO `_NA_` |
| 7 | tool_name | string | Max 100 chars; default `unknown`; NOT `_NA_` | Tool/model/platform name |
| 8 | vendor | string | Max 100 chars; default `unknown`; NOT `_NA_` | Vendor or provider |
| 9 | deployment_mode | enum | `standalone` / `integrated` / `unknown` | NO `_NA_` |
| 10 | target_users | enum | `internal_staff` / `public` / `both` / `unknown` | NO `_NA_` |
| 11 | year_announced | string | `YYYY` / `unknown` | NO `_NA_` |
| 12 | year_deployed | string | `YYYY` / `unknown` | NO `_NA_` |
| 13 | has_human_oversight | enum | `yes` / `no` / `unclear` / `not_documented` | NO `_NA_` |
| 14 | has_transparency_notice | enum | (same as #13) | |
| 15 | has_data_classification | enum | (same as #13) | |
| 16 | has_risk_assessment | enum | (same as #13) | |
| 17 | reported_outcomes | string | Max 200 chars; default `none_reported`; NOT `_NA_` | Documented performance claims |
| 18 | reported_incidents | string | Max 200 chars; default `none_reported`; NOT `_NA_` | Documented errors / failures |
| 19 | scope_notes | string | Max 300 chars; default `none`; NOT `_NA_` | Additional context |
| 20 | n_sources | integer >=1 | | Count of `SourceRecord` entries with this `activity_id` |
| 21 | confidence | enum | `high` / `medium` / `low` | Highest confidence across supporting input rows |
| 22 | uncertainty_flags | array | JSON array of flags, e.g. `[]` or `["date_uncertain","scope_unclear"]` | The union of the input rows' flags, ordered alphabetically. `[]` when no flag applies. See the Output Contract §4.10. |

### 4.2 Conflict resolution

When two or more input rows agree on `activity_name` but disagree on Group D fields, apply the source-credibility hierarchy from Output Contract §4.8 (Tier 1 = government / procurement / parliamentary; Tier 2 = major news / vendor case studies / trade press; Tier 3 = social / blogs / undated). Tie within a tier: most recent `source_publication_date`. Tie there: largest `source_snippet`.

### 4.3 Forbidden patterns

- No `_NA_` value anywhere in fields 2-19.
- No empty string in fields 2, 7, 8, 17, 18, 19 (use `unknown` / `none_reported` / `none` instead).
- No `activity_name` not present in input rows -- consolidator never invents activities.

---

## 5. `sources`

An array of source records, one per source page seen at consolidation time. **Length >= 1.**

### 5.1 Structure

Each source object has the following keys (all required):

| # | Field | Type | Allowed values | Description |
|---|-------|------|----------------|-------------|
| 1 | source_id | string | `^S[1-9]\d*$` | `S1`, `S2`, `S3`, ... -- per-institution, gapless, in input-row-appearance order |
| 2 | activity_id | string | `^(A[1-9]\d*\|_NA_)$` | FK to `ConsolidatedActivity` OR `_NA_` (see §5.2) |
| 3 | source_url | string | URL; verbatim from input | **Never fabricate or alter** |
| 4 | source_title | string | Max 200 chars | Page or document title |
| 5 | source_publication_date | string | `YYYY-MM-DD` / `YYYY-MM` / `YYYY` / `unknown` | When the source was published |
| 6 | source_access_date | string | `YYYY-MM-DD` | When the page was retrieved (verbatim from input) |
| 7 | source_type | enum | `official_gov` / `procurement_tender` / `news_major` / `news_trade` / `vendor` / `academic` / `policy_org` / `social_media` / `archive` / `other` | See Output Contract §4.6 |
| 8 | source_language | string | ISO 639-1 | Language of the source page |
| 9 | source_credibility | enum | `high` / `medium` / `low` | Per Output Contract §4.8 hierarchy |
| 10 | genai_evidence | enum | `confirms_activity` / `confirms_absence` / `ambiguous` / `background_only` | What this source tells us |
| 11 | source_snippet | string | Max 300 chars | Verbatim excerpt or close paraphrase |

### 5.2 `activity_id` linkage rules

- `genai_evidence = confirms_activity` => `activity_id` MUST point to a real `ConsolidatedActivity` (one of `A1`, `A2`, ...).
- `genai_evidence ∈ {confirms_absence, ambiguous, background_only}` => `activity_id` MUST be `_NA_`.

### 5.3 Same source supports multiple activities

If a single page documents two distinct activities, emit two `SourceRecord` entries with the **same** `source_url` and `source_title` but **different** `source_id` and `activity_id`.

### 5.4 No source is dropped

Every input source row maps to >=1 output `SourceRecord`. The consolidator never silently discards a source; if a source's evidence is weak, it appears with `genai_evidence = ambiguous` or `background_only` and `activity_id = _NA_`.

---

## 6. JSON Schema (programmatic validation)

The strict JSON Schema for this contract is generated at request time from `g3o.common.contract.ConsolidatedInstitutionResponse.model_json_schema()` and enforced via `response_format=json_schema` (strict mode, `additionalProperties=false`). The Pydantic model is the source of truth; this document is the human-readable companion.

Top-level shape:

```json
{
  "consolidation_metadata": { ... },
  "institution": { ... },
  "activities": [ ... ],
  "sources": [ ... ]
}
```

---

## 7. Consistency checks (self-validate before output)

Verify ALL of the following before responding:

1. `consolidation_metadata.institution_id == institution.institution_id`.
2. `has_genai_activity = yes` => `len(activities) >= 1` AND >=1 source has `genai_evidence = confirms_activity`.
3. `has_genai_activity = no` => `len(activities) == 0` AND every source has `genai_evidence = confirms_absence`.
4. `has_genai_activity = unclear` => `len(activities) == 0` AND no source has `genai_evidence = confirms_activity`.
5. `activity_id` sequence is `A1, A2, A3, ...` -- gapless, ordered, unique.
6. `source_id` sequence is `S1, S2, S3, ...` -- gapless, ordered, unique.
7. Every source's `activity_id` is either `_NA_` or matches an existing `ConsolidatedActivity.activity_id`.
8. Every `ConsolidatedActivity` has at least one `SourceRecord` linking to it.
9. Each activity's `n_sources` equals the actual count of sources with that `activity_id`.
10. No `ConsolidatedActivity` field 2-19 is `_NA_`.
11. Every `source_url` matches a URL from the input rows verbatim.
12. Enum compliance: every enum field uses ONLY the allowed values.

If any check fails, fix it before responding.

---

## 8. Edge cases and worked examples

### Edge case A: Institution with no GenAI evidence

> Three input rows from three pages, all with `genai_evidence = confirms_absence`.

**Output sketch:**
- `institution.has_genai_activity = no`.
- `institution.institution_summary = "No GenAI evidence in three supplied pages."` (or similar).
- `activities = []`.
- `sources` = 3 records (`S1`, `S2`, `S3`), each with `activity_id = _NA_` and `genai_evidence = confirms_absence`.

### Edge case B: Single activity backed by multiple sources

> Six input rows: 4 confirm a "Microsoft 365 Copilot deployment" (3 from .gov pages, 1 from a news article), 2 from pages with no GenAI content.

**Output sketch:**
- `institution.has_genai_activity = yes`.
- `activities = [{ activity_id: "A1", activity_name: "Microsoft 365 Copilot deployment", n_sources: 4, ... }]`.
- `sources` = 6 records:
  - `S1, S2, S3, S4` -> `activity_id: "A1"`, `genai_evidence: "confirms_activity"`.
  - `S5, S6` -> `activity_id: "_NA_"`, `genai_evidence: "confirms_absence"`.

### Edge case C: Two activities at one institution

> Input rows describe both a public chatbot (3 sources) and an internal Copilot pilot (2 sources).

**Output sketch:**
- `activities = [{ activity_id: "A1", activity_name: "MyCity Chatbot", n_sources: 3 }, { activity_id: "A2", activity_name: "Internal Copilot pilot", n_sources: 2 }]`.
- `sources` = 5 records: `S1, S2, S3` -> `A1`; `S4, S5` -> `A2`.

### Edge case D: Conflict resolution on Group D

> Input rows for "Internal Copilot deployment": one .gov procurement notice says `adoption_stage = production`, one news article says `pilot`.

**Output sketch:**
- `activities[0].adoption_stage = "production"` (Tier 1 .gov beats Tier 2 news).
- Both sources retained: `S1` (Tier 1 .gov, `confirms_activity`) and `S2` (Tier 2 news, `confirms_activity`), both `activity_id: "A1"`.

### Edge case E: Same source supports two activities

> One press release page documents both a policy AND a tool deployment.

**Output sketch:**
- `activities = [{ activity_id: "A1", ...policy... }, { activity_id: "A2", ...tool... }]`.
- `sources = [{ source_id: "S1", activity_id: "A1", source_url: <press_release> }, { source_id: "S2", activity_id: "A2", source_url: <press_release> }]` -- same URL, two source records, two source_ids.

### Edge case F: Mixed `confirms_activity` + `ambiguous`

> Three input rows: one confirms Microsoft 365 Copilot at the institution; two from pages mentioning AI in general but not naming the institution.

**Output sketch:**
- `institution.has_genai_activity = yes`.
- `activities = [{ activity_id: "A1", ..., n_sources: 1 }]`.
- `sources = [{ S1, A1, confirms_activity }, { S2, _NA_, ambiguous }, { S3, _NA_, ambiguous }]`.

### Edge case G: Discontinued activity

> Input rows confirm a chatbot that ran 2023-2024 then was shut down.

**Output sketch:**
- `activities[0].adoption_stage = "discontinued"`.
- `activities[0].year_deployed = "2023"`.
- `activities[0].reported_incidents = "Shut down in 2024 after public complaints."` (verbatim from highest-credibility source).
- `institution.has_genai_activity = "yes"` (historical activity counts as yes).

### Edge case H: All sources weak / ambiguous

> Five input rows, all `genai_evidence = ambiguous` or `background_only`. None confirm a specific activity at this institution.

**Output sketch:**
- `institution.has_genai_activity = "unclear"`.
- `activities = []`.
- `sources` = 5 records, each `activity_id = "_NA_"`, mixed `genai_evidence` values from {`ambiguous`, `background_only`}.

### Edge case I: Two near-duplicate activity names

> Input rows: row 1 says "Microsoft 365 Copilot deployment"; row 2 says "M365 Copilot rollout". Same vendor, possibly the same activity, but the names differ.

**Output sketch:**
- Keep them separate: `A1` = "Microsoft 365 Copilot deployment", `A2` = "M365 Copilot rollout".
- Add `scope_unclear` to both activities' `uncertainty_flags`.
- Use `consolidation_metadata.notes` to flag: "Possible duplicate activities A1 and A2; names differ across sources, kept separate."
