# Baseline capture — institution-outcome-reporting Phase 2, Step 0

Captured 2026-07-10, on the unmodified codebase (before any Phase 2 changes),
to confirm no behavior regression once Features 1-4 land.

No prior mock run existed under `runs/` at the same sample size/seed, so a
fresh one was generated.

## How it was produced

A standalone script mirroring `tests/test_e2e_presweep_smoke.py`'s stubbing
strategy (Serper, scrape, and the OpenAI Batch client stubbed at their module
boundaries — no live `SERPER_API_KEY`/`OPENAI_API_KEY`, no network calls) was
used to drive the full pipeline deterministically:

1. `PresweepConfig(run_id="baseline-smoke-1", sample_size=3, seed=22294,
   dry_run=False, stop_after="validate", scrape_respect_robots=False,
   scrape_host_delay_seconds=0)` against a synthetic 3-row master CSV
   (institutions `Ministry 0/1/2`, matching the existing smoke test's fixture).
2. `g3o.discovery.serper_client.search_google` stubbed to return two fixed
   URLs (`https://example.gov/ai-policy`, `https://example.gov/news`) for
   every query.
3. `g3o.scrape.fetcher.scrape_url` (via `stage_scrape.scrape_url`) stubbed to
   return a fixed `RenderedPage` per URL.
4. `g3o.common.batch_client.{submit_batch,poll_batch,fetch_results,
   find_batches_by_metadata}` stubbed to answer every Stage 2/3/5/6 batch
   deterministically (official site = the first canned URL; triage keeps
   every candidate; extract returns one `confirms_absence` row per page;
   validate returns `has_genai_activity="no"`, zero activities).
5. `run_presweep(config)` run to completion (through Stage 6), then
   `g3o.persist.write_run_csvs(run_dir, run_id="baseline-smoke-1",
   run_model="gpt-5-nano", version=1, run_date="2026-07-10")` for Stage 7.

This harness is verification scaffolding, not a pipeline feature, so it is
not checked in; its logic is a straight extension of the already-committed
`tests/test_e2e_presweep_smoke.py` (same stubs, same fixture) plus the Stage 7
`write_run_csvs` call that test doesn't exercise.

> **Superseded by uid stamping (2026-08-16).** The three CSVs below predate
> `institution_uid` / `sweep_uid` (PI ruling 2026-08-14) and no longer match
> what the pipeline emits: `g3o_activities_v1.csv` and
> `g3o_activity_sources_v1.csv` each gain two columns, and
> `g3o_institution_summary_v1.csv` gains one. They are kept as the pre-stamping
> record, not as a comparison target — **re-cut the baseline on top of the
> stamping merge before running the byte-identical gate against it.** The
> synthetic 3-row master named in step 1 now needs an `institution_uid` column
> (`G3O-I-00000001`…`00000003`); `tests/test_e2e_presweep_smoke.py`, which this
> harness mirrors, has already been updated.

## Result

`run_id = baseline-smoke-1`, `n_institutions = 3`, all three resolved to
`has_genai_activity = "no"` with zero activities (the canned Stage 6 response).

| File | Data rows (excl. header) |
|---|---|
| `g3o_activities_v1.csv` | 0 |
| `g3o_activity_sources_v1.csv` | 3 |
| `g3o_institution_summary_v1.csv` | 3 |

These three CSVs are snapshotted in this directory. Post-Phase-2, the same
harness (same seed/config/stubs) is re-run and its `final/*.csv` output is
diffed byte-for-byte against these files to confirm Features 1-4 changed only
observability/reporting, not pipeline behavior.
