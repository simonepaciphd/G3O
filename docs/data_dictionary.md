# Data dictionary

This dictionary describes the **three normalized CSVs** the Stage 7 writer
emits for a run (`g3o.persist.writer`), with column orders pinned in
`g3o.common.schema`:

| CSV                              | Column constant            | Cols | Grain                              |
|----------------------------------|----------------------------|------|------------------------------------|
| `g3o_activities_v{N}.csv`        | `ACTIVITY_COLUMNS`         | 35   | one row per (institution × activity) |
| `g3o_activity_sources_v{N}.csv`  | `ACTIVITY_SOURCE_COLUMNS`  | 18   | one row per source page             |
| `g3o_institution_summary_v{N}.csv`| `SUMMARY_COLUMNS`         | 21   | one row per institution per run     |

The schema-of-record for the model-produced fields (controlled vocabularies,
character limits, coding rules, edge cases, self-validation checks) is the
**G3O Output Contract v2.0** at
[`../g3o/extract/prompts/output_contract.md`](../g3o/extract/prompts/output_contract.md).
This file is a quick-reference index keyed to the shipped column constants; for
any disagreement on field semantics, the contract wins.

The legacy 44-column flat surface (`DATA_COLUMNS`) is retained at the end of
this document as a **historical** reference — it is the Stage 5 row-level
debug surface and the frozen schema of the published pilot v1 CSV, not the
current Stage 7 product.

## Grain

Each CSV has its own grain, stated in the table above:

- **Activities** — one row per `(institution × activity)` pair the Stage 6
  consolidator emitted for the institution.
- **Activity-sources** — one row per source page, keyed back to the activity
  it supports via `activity_id` (or `_NA_` for sources whose `genai_evidence`
  is `confirms_absence` / `ambiguous` / `background_only`).
- **Institution-summary** — one row per institution per run, rolling up its
  activities and sources.

How institutions that the pipeline never reached (no discovery hits, no kept
URLs, no scrapeable pages), or that produced no activity, are represented in
the final product is a pending methodology decision and is **not** asserted
here. The machine-readable `runs/<run_id>/_attrition.jsonl` ledger records,
per institution and stage, where coverage was lost.

## `g3o_activities_v{N}.csv` — `ACTIVITY_COLUMNS` (35)

One row per `(institution × activity)`.

| Group              | Columns                                                                                                                                                                                                                                                       |
|--------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Provenance (5)     | `global_row_id`, `run_id`, `run_model`, `run_tool`, `run_date`                                                                                                                                                                                                |
| Institution + verdict (8) | `institution_id`, `institution_name`, `country`, `branch_of_government`, `level_of_government`, `has_genai_activity`, `institution_summary`, `institution_search_languages`                                                                              |
| Activity key (1)   | `activity_id`                                                                                                                                                                                                                                                  |
| Activity fields (18) | `activity_name`, `activity_type`, `adoption_stage`, `access_type`, `interaction_type`, `tool_name`, `vendor`, `deployment_mode`, `target_users`, `year_announced`, `year_deployed`, `has_human_oversight`, `has_transparency_notice`, `has_data_classification`, `has_risk_assessment`, `reported_outcomes`, `reported_incidents`, `scope_notes` |
| Aggregates (3)     | `n_sources` (sources supporting this activity), `confidence`, `uncertainty_flags`                                                                                                                                                                              |

Provenance: `global_row_id` is `{run_id}::{institution_id}::{activity_id}`;
`run_model` is the model id (e.g. `gpt-5-nano`); `run_tool` is the emitting
module; `run_date` is `YYYY-MM-DD`. The activity-field semantics
(controlled vocabularies, `_NA_` rules, char limits) are governed by the
Output Contract.

## `g3o_activity_sources_v{N}.csv` — `ACTIVITY_SOURCE_COLUMNS` (18)

One row per source page.

| Group           | Columns                                                                                                                                            |
|-----------------|----------------------------------------------------------------------------------------------------------------------------------------------------|
| Provenance (5)  | `global_row_id`, `run_id`, `run_model`, `run_tool`, `run_date`                                                                                     |
| Foreign keys (3)| `institution_id`, `activity_id`, `source_id`                                                                                                       |
| Source fields (9)| `source_url`, `source_title`, `source_publication_date`, `source_access_date`, `source_type`, `source_language`, `source_credibility`, `genai_evidence`, `source_snippet` |
| Salvage provenance (1) | `group_d_salvaged_fields`                                                                                                                   |

`source_id` is unique per `(run_id, institution_id)`. `activity_id` is the FK
to the activities table, or `_NA_` when the source confirms absence, is
ambiguous, or is background-only. `genai_evidence` is one of
`confirms_activity` / `confirms_absence` / `ambiguous` / `background_only`;
`source_credibility` is `high` / `medium` / `low`. Full field semantics are in
the Output Contract.

### `group_d_salvaged_fields` — the imputation trace

Added 2026-07-21. **This is the only mark of imputation anywhere on the
analysis surface**, which is why it is documented here in full rather than
deferred to the contract.

- **What it holds.** The `;`-joined, alphabetically sorted names of the Group-D
  activity fields whose illegal `_NA_` was rewritten to a contract default at
  Stage 5 for at least one record extracted from this source page — or `""`
  when none were. Page-level and deterministic, per the PI decision of
  2026-07-28: it says "at least one record extracted from this page had these
  fields salvaged", not which record.
- **Who writes it.** `g3o.persist.writer.salvaged_fields_by_source` at Stage 7,
  read from the `_attrition.jsonl` ledger's `group_d_incomplete_salvaged`
  records. It is a deterministic persist-time annotation, **not** model output.
- **Why it matters.** Salvage rewrites `_NA_` in place to fixed in-band
  defaults (`unknown` / `not_documented` / `none_reported` / `none` —
  `g3o/extract/salvage.py`). On the activities CSV a model-coded `unknown` and
  a code-imputed `unknown` are therefore indistinguishable; this column on the
  sources CSV is the only way to tell them apart, and only by joining back.
- **Known under-mark.** The join key is `(institution_id, source_url)`. If
  Stage 6 altered a `source_url`, the annotation does not attach and the row
  reads as un-salvaged (`writer.py`, `salvaged_fields_by_source` docstring).
  The error is one-directional — an under-mark, never an over-mark — and the
  salvage remains fully accounted for in the attrition ledger itself.
- **Not on the activities CSV.** Promoting the flag to the activity grain is an
  open schema decision, not an omission.

## `g3o_institution_summary_v{N}.csv` — `SUMMARY_COLUMNS` (21)

One row per institution per run (current-run-only roll-up, per the Session C
decision of 2026-05-09).

| Group                         | Columns                                                                                                          |
|-------------------------------|------------------------------------------------------------------------------------------------------------------|
| Identity (5)                  | `institution_id`, `institution_name`, `country`, `branch_of_government`, `level_of_government`                   |
| Run scope (2)                 | `run_id`, `run_date`                                                                                             |
| Institution-level verdict (3) | `has_genai_activity`, `institution_summary`, `institution_search_languages`                                     |
| Counts (6)                    | `n_pages_extracted`, `n_activities`, `n_sources`, `n_high_credibility_sources`, `n_medium_credibility_sources`, `n_low_credibility_sources` |
| Distinct lists (3)            | `activities_found`, `tools_found`, `vendors_found` (each pipe-delimited, ` \| `-joined)                          |
| Aggregated confidence + flags (2) | `best_confidence`, `consolidated_uncertainty_flags`                                                          |

`tools_found` and `vendors_found` exclude the literal `unknown`.
`best_confidence` is the highest activity-level confidence (`high` > `medium` >
`low`, or `_NA_` when there are no activities). `consolidated_uncertainty_flags`
is the de-duplicated, sorted union of activity-level flags (or `none`).

---

## Historical: the legacy 44-column flat surface (`DATA_COLUMNS`)

**Legacy as of Session C.** The 44 columns below are
`g3o.common.schema.DATA_COLUMNS`: the Stage 5 row-level debug surface (one row
per `institution × activity × source` triple) and the frozen header of the
published `data/pilot_v1/g3o_full_database_v1.csv`. The current Stage 7 product
is the three normalized CSVs above; this section is retained only for auditing
pilot v1 and reading raw Stage 5 output. The model-produced columns (1–39) are
governed by the same Output Contract v2.0.

| #  | Column                          | Source                | Description                                               |
|----|---------------------------------|-----------------------|-----------------------------------------------------------|
| 1  | `global_row_id`                 | pipeline              | Sequential ID across the merged database.                 |
| 2  | `run_id`                        | pipeline              | Run that produced this row (e.g., `chatgpt_web_v1`).      |
| 3  | `row_id`                        | extract (contract #1) | Sequential within the run.                                |
| 4  | `batch_id`                      | extract (#2)          | Batch within the run.                                     |
| 5  | `institution_id`                | extract (#3)          | Institution identifier (joins to the institution master). |
| 6  | `institution_name`              | extract (#4)          | Verbatim institution name (preserves diacritics).         |
| 7  | `country`                       | extract (#5)          |                                                           |
| 8  | `branch_of_government`          | extract (#6)          | `executive` / `legislative` / `judicial`.                 |
| 9  | `level_of_government`           | extract (#7)          | `national` / `subnational` and finer levels.              |
| 10 | `has_genai_activity`            | extract (#8)          | `yes` / `no` / `unclear` — institution-level verdict.     |
| 11 | `institution_summary`           | extract (#9)          | One-sentence institution-level summary.                   |
| 12 | `institution_search_languages`  | extract (#10)         | ISO 639-1 codes actually searched.                        |
| 13 | `activity_name`                 | extract (#11)         | Activity name; official if available.                     |
| 14 | `activity_type`                 | extract (#12)         | G3O typology (5-way enum); `_NA_` when no activity.       |
| 15 | `adoption_stage`                | extract (#13)         | `proposed` / `announced` / `pilot` / `production` / `discontinued` / `unknown` / `_NA_`. |
| 16 | `access_type`                   | extract (#14)         | `proprietary_vendor` / `open_source` / `sovereign_model` / `in_house` / `mixed` / `unknown` / `_NA_`. |
| 17 | `interaction_type`              | extract (#15)         | `chatbot` / `document_processing` / `code_generation` / `decision_support` / `translation` / `content_creation` / `search_retrieval` / `multiple` / `not_applicable` / `unknown` / `_NA_`. |
| 18 | `tool_name`                     | extract (#16)         | Specific tool, model, or platform.                        |
| 19 | `vendor`                        | extract (#17)         | Vendor or provider; institution itself for in-house.      |
| 20 | `deployment_mode`               | extract (#18)         | `standalone` / `integrated`.                              |
| 21 | `target_users`                  | extract (#19)         | `internal_staff` / `public` / `both`.                     |
| 22 | `year_announced`                | extract (#20)         | `YYYY` / `unknown`.                                       |
| 23 | `year_deployed`                 | extract (#21)         | `YYYY` / `unknown`.                                       |
| 24 | `has_human_oversight`           | extract (#22)         | Guardrail field.                                          |
| 25 | `has_transparency_notice`       | extract (#23)         | Guardrail field.                                          |
| 26 | `has_data_classification`       | extract (#24)         | Guardrail field.                                          |
| 27 | `has_risk_assessment`           | extract (#25)         | Guardrail field.                                          |
| 28 | `reported_outcomes`             | extract (#26)         | Free text up to 200 chars or `none_reported`.             |
| 29 | `reported_incidents`            | extract (#27)         | Free text up to 200 chars or `none_reported`.             |
| 30 | `scope_notes`                   | extract (#28)         | Free text up to 300 chars or `none`.                      |
| 31 | `source_url`                    | extract (#29)         | Landing-page URL the row evidences.                       |
| 32 | `source_title`                  | extract (#30)         | Page or document title.                                   |
| 33 | `source_publication_date`       | extract (#31)         | `YYYY-MM-DD` / `YYYY-MM` / `YYYY` / `unknown`.            |
| 34 | `source_access_date`            | extract (#32)         | `YYYY-MM-DD` (date research was performed).               |
| 35 | `source_type`                   | extract (#33)         | Source category (controlled vocabulary).                  |
| 36 | `source_language`               | extract (#34)         | ISO 639-1.                                                |
| 37 | `source_credibility`            | extract (#35)         | `high` / `medium` / `low`.                                |
| 38 | `genai_evidence`                | extract (#36)         | `confirms_activity` / `confirms_absence` / `ambiguous` / `background_only`. |
| 39 | `source_snippet`                | extract (#37)         | Verbatim excerpt up to 300 chars.                         |
| 40 | `confidence`                    | extract (#38)         | Row-level confidence: `high` / `medium` / `low`.          |
| 41 | `uncertainty_flags`             | extract (#39)         | Semicolon-separated flags or `none`.                      |
| 42 | `run_model`                     | pipeline              | Model that produced the row (e.g., `gpt-5-nano`).         |
| 43 | `run_tool`                      | pipeline              | Tool name (e.g., `OpenAI API`).                           |
| 44 | `run_date`                      | pipeline              | When the run executed (`YYYY-MM-DD`).                     |

Enum values above are the **current** contract's, synced verbatim from
`output_contract.md` §3.2. The columns are the pilot's; the vocabularies are
the contract's, and the two are not the same vintage — `adoption_stage =
proposed` entered the enum in commit `25e544e` (2026-07-04), after pilot v1 was
frozen.

Five of the values listed above have **zero** observations across pilot v1's
1,336 rows (counted from `data/pilot_v1/g3o_full_database_v1.csv`, 2026-08-02):
`adoption_stage = proposed`, and `no` on each of the four guardrail fields
(`has_human_oversight`, `has_transparency_notice`, `has_data_classification`,
`has_risk_assessment`). Every other listed value is observed. The first is
explained by the freeze date; what the other four mean for how the guardrail
fields should be read is an open question for the project authors, recorded
here as a count and deliberately not interpreted.

For controlled vocabularies, edge cases, and the "policy vs pilot" /
"country-wide program" coding rules, see
[`../g3o/extract/prompts/output_contract.md`](../g3o/extract/prompts/output_contract.md).
