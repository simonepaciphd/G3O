# Architecture

The G3O production pipeline is a seven-stage flow that mirrors the data
collection design described in the paper. Each stage is a separate Python
package; the boundary between them is a serializable artifact persisted on
disk under `runs/<run_id>/<inst>/`.

```
1a  discovery_general            (Serper queries; cached on disk)
        │
        ▼
2   classify_official_site       (LLM, Batch API, gpt-5-nano)
        │
        ▼
1b  discovery_site_restricted    (Serper site:<official_site>)
        │
        ▼
3   classify_url_triage          (LLM, Batch API)
        │
        ▼
4   scrape                       (HTTP + HTML / PDF / headless-render)
        │
        ▼
5   extract                      (LLM, Batch API; one call per page)
        │
        ▼
6   validate                     (LLM, Batch API; one call per institution)
        │
        ▼
7   persist                      (deterministic CSV writer)
```

Stages 2, 3, 5, and 6 call the OpenAI Batch API on `gpt-5-nano` with
`response_format=json_schema` and prompt caching. Stages 1a, 1b, 4, and 7 are
deterministic. End-to-end orchestration lives in `g3o.run.presweep`.

## Mapping to the paper

The paper section "Data Collection Pipeline" describes a three-layer pipeline
(discovery → extraction → cross-validation). This codebase decomposes those
layers further to keep failure modes, rate limits, and caching strategies
independent.

| Paper layer       | Code module       | What it does                                                                                          |
|-------------------|-------------------|-------------------------------------------------------------------------------------------------------|
| Discovery         | `g3o.discovery`   | Stages 1a/1b. Builds institution × language × GenAI-term queries; runs them via Serper, with a site-restricted second pass keyed off the Stage 2 official site. |
| Discovery         | `g3o.classify`    | Stages 2 + 3. Picks the canonical institutional homepage and applies keep/drop URL triage before any page is fetched.                                            |
| Discovery         | `g3o.scrape`      | Stage 4. Fetches each kept URL; routes between HTML, PDF, and a headless-browser fallback for JS-shell pages.                                                    |
| Extraction        | `g3o.extract`     | Stage 5. Schema-first per-page LLM extraction into the G3O Output Contract v2.0.                                                                                  |
| Cross-validation  | `g3o.validate`    | Stage 6. Per-institution LLM consolidation of Stage 5 rows: dedup within institution, source-credibility resolution, uncertainty-flag propagation.                |
| Cross-validation  | `g3o.persist`     | Stage 7. Deterministic CSV writer that assembles the three normalized per-run tables (activities, activity-sources, institution-summary).                          |

## Implementation status

| Module          | Status                                                                                                  |
|-----------------|----------------------------------------------------------------------------------------------------------|
| `g3o.discovery` | Implemented: Serper client (general + site-restricted modes), multilingual query builder, on-disk cache. |
| `g3o.classify`  | Implemented: official-site picker (Stage 2), URL triage (Stage 3), both via Batch API.                   |
| `g3o.scrape`    | Implemented: HTML, PDF, and Playwright-backed headless render adapter; on-disk cache.                    |
| `g3o.extract`   | Implemented: Batch API client, batch driver, contract-validating parser; orchestrated via `presweep`.    |
| `g3o.validate`  | Implemented: per-institution consolidation driver, deterministic QC, prompts.                            |
| `g3o.persist`   | Implemented: walks per-institution Stage 6 outputs, emits the three canonical normalized CSVs with provenance. |
| `g3o.run`       | Implemented: `presweep` orchestrator (resume-aware), `verify_model` Batch-API smoke test.                |
| `g3o.common`    | Implemented: schema, contract validators, Batch API client, run-state tracking.                          |

## Boundary artifacts

All run-local artifacts live under `runs/<run_id>/` (gitignored):

| Boundary               | Path                                                  |
|------------------------|-------------------------------------------------------|
| Stage 1a → Stage 2     | `runs/<run_id>/<inst>/1a_discovery_general.json`      |
| Stage 2 → Stage 1b     | `runs/<run_id>/<inst>/2_official_site.json`           |
| Stage 1b → Stage 3     | `runs/<run_id>/<inst>/1b_discovery_site_restricted.json` |
| Stage 3 → Stage 4      | `runs/<run_id>/<inst>/3_triage.json`                  |
| Stage 4 → Stage 5      | `runs/<run_id>/<inst>/scrape/<url_hash>.json`         |
| Stage 5 → Stage 6      | `runs/<run_id>/<inst>/extract/*.json`                 |
| Stage 6 → Stage 7      | `runs/<run_id>/<inst>/6_validate.json`                |
| Stage 7 → release      | `runs/<run_id>/final/g3o_activities_v{N}.csv`, `g3o_activity_sources_v{N}.csv`, `g3o_institution_summary_v{N}.csv` |

Validated releases checked into the repo live under `data/v<N>/` (currently
only the pilot at `data/pilot_v1/`).

## Caching and idempotency

- `discovery` and `scrape` cache by hash on disk under `cache/` (gitignored).
  Re-running with the same query or URL is idempotent and free of API cost.
- `classify`, `extract`, and `validate` rely on OpenAI prompt caching at the
  model level and on Batch API for the 50% bulk discount. The pipeline does
  not re-cache LLM outputs separately; per-stage results in
  `runs/<run_id>/<inst>/` are the cache.
- `presweep` infers resume points from the presence of `_state/` files in
  `runs/<run_id>/` and skips stages that have already completed.
- `persist` is fully deterministic given its inputs.

## Why this split

- **Discovery is split into two passes** (general, then site-restricted)
  bracketing the official-site classifier. The site-restricted pass uses the
  classifier's output as a seed, dramatically improving recall on the
  institution's own domain without paying for it on every Serper call.
- **`classify` filters before any page is fetched.** The triage stage cuts
  ~40 candidate URLs per institution down to ~12, which is what the per-page
  costs of `scrape` and `extract` add up against.
- **Discovery and scrape have different rate limits.** Serper is paid per
  query; HTTP fetches are bounded by per-host politeness. Splitting lets each
  back off independently.
- **Extraction is the expensive layer.** Keeping it isolated lets us swap
  models, re-run on cached pages, or replay against a different prompt
  without re-doing search/scrape.
- **Validation must be deterministic relative to its inputs.** The LLM
  consolidation call is reproducible given the same Stage 5 rows; QC is
  fully deterministic. Holding it separate lets us re-run merges over an
  extended record set without re-issuing per-page API calls.
- **Persist is non-LLM.** The CSV assembler doesn't touch the model — it
  walks `runs/<run_id>/<inst>/6_validate.json` files, validates against the
  contract, and writes the canonical tables.

## See also

- [`../README.md`](../README.md) — project overview and quickstart.
- [`data_dictionary.md`](data_dictionary.md) — output schema.
- [`replication.md`](replication.md) — how to reproduce / extend pilot results.
- [`../g3o/extract/prompts/output_contract.md`](../g3o/extract/prompts/output_contract.md) — schema-of-record.
