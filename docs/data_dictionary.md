# Data dictionary

This dictionary enumerates the 44 columns of the production database
(`g3o.common.schema.DATA_COLUMNS` and the published
`data/v<N>/g3o_full_database_v<N>.csv`).

The schema-of-record for the model-produced columns (1–39) is the **G3O
Output Contract v2.0** at
[`../g3o/extract/prompts/output_contract.md`](../g3o/extract/prompts/output_contract.md).
That document specifies controlled vocabularies, character limits,
coding rules, edge cases, and self-validation checks. This file is a
quick-reference index; for any disagreement, the contract wins.

## Grain

Each row represents one **(institution × activity × source)** triple.
An institution with no GenAI activity is still represented (one or more
rows with all activity fields set to `_NA_`).

## Columns

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
| 15 | `adoption_stage`                | extract (#13)         | `announced` / `pilot` / `production` / `discontinued` / `unknown`. |
| 16 | `access_type`                   | extract (#14)         | `proprietary_vendor` / `open_source` / `sovereign_model` / `in_house` / `mixed`. |
| 17 | `interaction_type`              | extract (#15)         | `chatbot` / `document_processing` / `decision_support` / etc. |
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
| 42 | `run_model`                     | pipeline              | Model that produced the row (e.g., `gpt-4.1`).            |
| 43 | `run_tool`                      | pipeline              | Tool name (e.g., `OpenAI API`).                           |
| 44 | `run_date`                      | pipeline              | When the run executed (`YYYY-MM-DD`).                     |

For controlled vocabularies, edge cases, and the "policy vs pilot" /
"country-wide program" coding rules, see
[`../g3o/extract/prompts/output_contract.md`](../g3o/extract/prompts/output_contract.md).

## Institution-summary table

`g3o_institution_summary_v<N>.csv` is a roll-up to the institution level.
Columns: `institution_id`, `institution_name`, `country`,
`branch_of_government`, `level_of_government`, `has_genai_activity`,
`n_total_rows`, `n_runs_covered`, `runs`, `n_activity_source_rows`,
`activities_found`, `tools_found`, `best_summary`. Order in
`g3o.common.schema.SUMMARY_COLUMNS`.
