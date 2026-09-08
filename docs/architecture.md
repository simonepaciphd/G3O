# Architecture

The G3O production pipeline is a seven-stage flow that mirrors the data
collection design described in the paper. Each stage is a separate Python
package; the boundary between them is a serializable artifact persisted on
disk under `runs/<run_id>/institutions/<shard>/<inst>/`.

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
| Discovery         | `g3o.discovery`   | Stages 1a/1b. Two query strategies, selected by `--discovery-mode` — see [Discovery query strategy](#discovery-query-strategy) below. |
| Discovery         | `g3o.classify`    | Stages 2 + 3. Picks the canonical institutional homepage and applies keep/drop URL triage before any page is fetched.                                            |
| Discovery         | `g3o.scrape`      | Stage 4. Fetches each kept URL; routes between HTML, PDF, and a headless-browser fallback for JS-shell pages.                                                    |
| Extraction        | `g3o.extract`     | Stage 5. Schema-first per-page LLM extraction into the G3O Output Contract.                                                                                       |
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

## Discovery query strategy

Stages 1a and 1b share a `--discovery-mode` switch. **`chain` is the default**
since 2026-08-01 (PI sign-off on the confirmation run); `legacy` stays reachable
and byte-identical for replication.

| | `legacy` | **`chain`** (default) |
|---|---|---|
| Stage 1a | 8 four-slot queries: `"name" country disambiguation "GenAI term"`, one per term in `GENAI_TERMS_BY_LANG` | 1 query: `<name> <country> <disambiguation> official website` — unquoted |
| Stage 1b | each of those 8, wrapped in `site:<domain>` | 1 query: `site:<domain> AI` — one bare token |
| Credits / institution — **measured**, n=200/arm | **8.52** | **1.84** |
| Institutions with an own-domain *relevant* hit | 20.0% | **64.5%** |
| Stage 2 found an official site | 6.5% | **88.0%** |

Paired McNemar over 200 institutions: 94 gains, 5 losses, exact two-sided
*p* = 2.4 × 10⁻²². Report:
`agent-workspace/2026-08-01-discovery-chain-validation.md` (Drive; not tracked here).

The chain exists because **Stage 1a was asking one query to do two incompatible
jobs** — identify the institution *and* find GenAI evidence — and the four-slot
format did neither well. Splitting them lets each leg be judged on its own job:
leg 1 surfaces the institution's true domain 82% of the time, and Stage 2
converts 153 of those 164 (93%) into an official-site pick that leg 2 can then
search.

**`legacy` is cheaper than its 16-credit design cost only because most of it
never runs.** Its GenAI-term queries rarely surface a homepage, so Stage 2 found
an official site for just 13/200 institutions and Stage 1b — which runs only for
those — was skipped for the other 187. Read the 8.52 as a symptom, not a saving.

Three measured results are load-bearing and should not be re-litigated by
tuning the query builders:

- **Quoting the institution name is the primary failure.** Master local names
  are abbreviated (`Polson H S`, `KELLER ISD`); an exact-phrase match on them
  returns almost nothing, and three institutions returned zero URLs under the
  production control. Leg 1 is therefore unquoted — but still sanitized, since
  outside quotes a token-initial `-` is Google's exclusion operator.
- **Dropping quotes is not by itself the fix.** Own-domain hits leap 5→20 but
  *relevant* hits stay at 5: fifteen of those twenty are bare homepages with no
  AI content. Score on relevance, never on domain match alone.
- **Once site-bound, extra English terms add exactly 0 pp**, and OR-chaining
  them is actively harmful (4/24 against 16/24 for the bare token). Legacy
  Stage 1b's eight site-wrapped queries repeat the institution name inside a
  query already bound to that institution's domain; **93.2% of them (179/192)
  return zero results.**

Native-language legs (a real, measured +2/24 that is unreachable any other way)
belong to `subprojects/multilingual-pipeline/` (Drive; not tracked here), which owns country-conditional
discovery-language routing and the term rosters. Do not add them here.

Volume is a **reserve, not a ceiling** (PI direction, 2026-08-01): the chain
collects fewer URLs per institution than legacy (~16 against ~23), accepted on
the understanding that more can be collected later. Both stages union and
dedupe over a *list* of queries precisely so adding a leg stays a config change
rather than a refactor. Draw on the reserve against evidence from Stages 1c/3,
not pre-emptively — and note that extra English tokens measure at 0 pp and
should never be drawn on.

Spec and measurements:
`agent-workspace/2026-08-01-serper-discovery-yield-findings.md` (Drive; not tracked here).

## Boundary artifacts

All run-local artifacts live under `runs/<run_id>/` (gitignored). Institution
directories are sharded 256 ways beneath an `institutions/` level — **storage
layout v2**, specified in [`storage-layout-v2.md`](storage-layout-v2.md):

```
runs/<run_id>/
  manifest.json            # run-level; carries "layout_version": 2
  _state/                  # batch-chunk state + .done/ markers
  _attrition.jsonl         # run-level ledger (g3o.common.attrition.LEDGER_NAME)
  final/                   # Stage-7 CSVs
  institutions/
    <shard>/               # md5(inst_id)[:2] -> 256 shards
      <inst_id>/           # the per-institution artifacts in the table below
```

In the table, `<inst>` abbreviates `institutions/<shard>/<inst_id>` with
`<shard> = md5(inst_id)[:2]`. The shard is derived from `inst_id` alone (no
master-row lookup, nothing keyed on `master_row_id`). `g3o.common.paths` is the
single owner of this layout: every institution path is built by
`institution_dir()`, every walk goes through `iter_institution_dirs()`, and
`require_layout()` refuses at entry any run tree that does not declare
`layout_version: 2` — there is no dual-layout read support, so a pre-v2 run is
read by checking out a pre-v2 commit.

The two page-level artifact classes (`scrape/`, `extract/`) are gzipped and
written compact; every other per-institution file stays plain, indented JSON.
`g3o.common.artifact_io` is the single owner of that encoding — writers emit
`.json.gz` only, readers accept `.json` or `.json.gz` with `.gz` winning, and
the gzip header is pinned (`mtime=0`, no `FNAME`) so identical input yields
byte-identical output.

| Boundary               | Path                                                  |
|------------------------|-------------------------------------------------------|
| Stage 1a → Stage 2     | `runs/<run_id>/<inst>/1a_discovery_general.json`      |
| Stage 2 → Stage 1b     | `runs/<run_id>/<inst>/2_official_site.json`           |
| Stage 1b → Stage 3     | `runs/<run_id>/<inst>/1b_discovery_site_restricted.json` |
| Stage 3 → Stage 4      | `runs/<run_id>/<inst>/3_triage.json`                  |
| Stage 4 → Stage 5      | `runs/<run_id>/<inst>/scrape/<url_hash>.json.gz`      |
| Stage 5 → Stage 6      | `runs/<run_id>/<inst>/extract/*.json.gz`              |
| Stage 6 → Stage 7      | `runs/<run_id>/<inst>/6_validate.json`                |
| Stage 7 → release      | `runs/<run_id>/final/g3o_activities_v{N}.csv`, `g3o_activity_sources_v{N}.csv`, `g3o_institution_summary_v{N}.csv` |

Validated releases checked into the repo live under `data/v<N>/` (currently
only the pilot at `data/pilot_v1/`).

## Caching and idempotency

- `discovery` and `scrape` cache by hash on disk under `cache/` (gitignored).
  Re-running with the same query or URL is idempotent and free of API cost.
- `classify`, `extract`, and `validate` use the Batch API for the documented
  50% bulk discount, and their shared system messages are prompt-cache-eligible
  (identical ≥1,024-token prefix per batch). **Caveat (review F20, verified
  2026-06-11):** whether prompt-caching discounts *stack* with the Batch
  discount is **not stated in OpenAI's current docs** — do not assume the
  cached-input rate applies inside Batch when budgeting. The cost model takes
  the conservative no-stack figure and validates against the first live run's
  cached-token telemetry (see `docs/budget/`). The pipeline does not re-cache
  LLM outputs separately; per-stage results in
  `runs/<run_id>/institutions/<shard>/<inst>/` are the cache.
- `presweep` infers resume points from the presence of `_state/` files in
  `runs/<run_id>/` and skips stages that have already completed.
- `persist` is fully deterministic given its inputs.

## Why this split

- **Discovery is split into two passes** (general, then site-restricted)
  bracketing the official-site classifier. The site-restricted pass uses the
  classifier's output as a seed, dramatically improving recall on the
  institution's own domain without paying for it on every Serper call. The
  two-query chain sharpens this split rather than replacing it: it gives each
  pass a single job (identify the institution, then find evidence on it) and
  leaves Stage 2 as the arbiter between them.
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
  walks `runs/<run_id>/institutions/<shard>/<inst_id>/6_validate.json` files,
  validates against the contract, and writes the canonical tables.

## See also

- [`../README.md`](../README.md) — project overview and quickstart.
- [`pipeline-status.md`](pipeline-status.md) — **what the pipeline has actually
  been measured to do**, stage by stage, what is still unmeasured, and the
  ranked improvement list. This file describes design; that one describes
  evidence.
- [`data_dictionary.md`](data_dictionary.md) — output schema.
- [`replication.md`](replication.md) — how to reproduce / extend pilot results.
- [`../g3o/extract/prompts/output_contract.md`](../g3o/extract/prompts/output_contract.md) — schema-of-record.
