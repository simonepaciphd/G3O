# Baseline capture — the byte-identical regression reference

The three CSVs in this directory are the comparison target for the
byte-identical gate: re-run the harness below at the same seed and config, and
diff its `final/*.csv` against these files to confirm a change altered only
observability, never pipeline behaviour.

**Current cut: 2026-08-17**, on `d614404` (post-uid-stamping `main`). The
2026-07-10 cut it replaces is described under [History](#history).

## How it is produced

A standalone script mirroring `tests/test_e2e_presweep_smoke.py`'s stubbing
strategy (Serper, scrape, and the OpenAI Batch client stubbed at their module
boundaries — no live `SERPER_API_KEY`/`OPENAI_API_KEY`, no network calls) drives
the full pipeline deterministically:

1. `PresweepConfig(run_id="baseline-smoke-1", sample_size=3, seed=22294,
   dry_run=False, stop_after="validate", scrape_respect_robots=False,
   scrape_host_delay_seconds=0)` against a synthetic 3-row master CSV
   (institutions `Ministry 0/1/2`, matching the smoke test's fixture). The master
   carries an `institution_uid` column — `G3O-I-00000001`…`00000003` — which
   plan time now requires.
2. `g3o.discovery.serper_client.search_google_detailed` stubbed to return two
   fixed URLs (`https://example.gov/ai-policy`, `https://example.gov/news`) for
   every query.
3. `g3o.scrape.fetcher.scrape_url` (via `stage_scrape.scrape_url`) stubbed to
   return a fixed `RenderedPage` per URL.
4. `g3o.common.batch_client.{submit_batch,poll_batch,fetch_results,
   find_batches_by_metadata}` stubbed to answer every Stage 2/3/5/6 batch
   deterministically (official site = the first canned URL; triage keeps every
   candidate; extract returns one `confirms_absence` row per page; validate
   returns `has_genai_activity="no"`, zero activities).
5. Entered through `launch(config, session_id=…, invocation="api")` — the
   documented entry point since the Run API — then
   `g3o.persist.write_run_csvs(run_dir, run_id="baseline-smoke-1",
   run_model="gpt-5-nano", version=1, run_date="2026-07-10")` for Stage 7.

`run_id`, `run_model` and `run_date` are pinned to the original capture's values
on purpose: it is what makes the diff against the previous cut readable as a
*column* delta rather than a provenance delta.

This harness is verification scaffolding, not a pipeline feature, so it is not
checked in; its logic is a straight extension of the already-committed
`tests/test_e2e_presweep_smoke.py` (same stubs, same fixture) plus the Stage 7
`write_run_csvs` call that test does not exercise.

## ⚠️ Compare field-wise, not by file hash

Two independent reasons, and the second one bites on the droplet:

1. **A file hash cannot tell an intended new column from a moved value.** When
   the expected answer is "changed, in exactly this way", a whole-file digest
   answers a different question than the one being asked.
2. **Line endings are not portable here.** `csv.writer`'s default terminator is
   `\r\n` on *every* platform, so the pipeline emits **CRLF**. These files are
   stored in git as **LF** and materialise as CRLF only where
   `core.autocrlf=true` (a Windows working tree). On a fresh Linux checkout — the
   droplet — the working-tree baseline is LF while `final/*.csv` is CRLF, so a
   byte comparison fails on line endings alone while every value is identical.

Compare parsed cells on the shared column set, assert the column delta against a
prediction written down in advance, and assert the new columns are **non-empty**
rather than merely present: a column added to a list but never threaded writes an
empty cell and no error (`institution_report.py`'s `r.get(col)`), so a presence
test passes on a half-landed change. This is the same platform-dependence class
as the prompt-hash defect fixed in `34cb017`.

## The 2026-08-17 re-cut

Predicted delta, and the observed delta, matched exactly — with one correction
found by the gate itself:

| File | Columns | Added |
|---|---|---|
| `g3o_activities_v1.csv` | 35 → 37 | `institution_uid`, `sweep_uid` |
| `g3o_activity_sources_v1.csv` | 17 → 20 | `institution_uid`, `sweep_uid`, `group_d_salvaged_fields` |
| `g3o_institution_summary_v1.csv` | 21 → 22 | `institution_uid` |

Provenance of every added column, because two separate changes are folded into
this one cut:

- `institution_uid` / `sweep_uid` — uid stamping, **#71** (`a7bca03`,
  2026-08-16). Both are inserted at the **front** of the activities and sources
  column lists, and `institution_uid` at the front of the summary; they are not
  appended.
- `group_d_salvaged_fields` — the per-field Group-D salvage flag, **`efa90e0`**
  (2026-07-22), which post-dates the previous capture by twelve days. **The
  baseline was already stale before uid stamping**, and nobody re-cut it in July.
  It is legitimately `""` on every row here because this run salvages nothing
  (`schema.py:21`), which is why the non-empty assertion is scoped to the uid
  columns.

Everything else held: **0 rows changed, 0 columns removed, 0 shared cells
changed** across all three files, and the surviving columns kept their original
relative order.

**Determinism control: 5 independent runs, one SHA256 per file.** A single run
cannot distinguish "this change is deterministic" from "this change happened to
land the same way once", and the baseline is worthless as a comparison target if
the pipeline is not deterministic at this config.

## Result

`run_id = baseline-smoke-1`, `n_institutions = 3`, all three resolved to
`has_genai_activity = "no"` with zero activities (the canned Stage 6 response).

| File | Data rows (excl. header) |
|---|---|
| `g3o_activities_v1.csv` | 0 |
| `g3o_activity_sources_v1.csv` | 3 |
| `g3o_institution_summary_v1.csv` | 3 |

Row counts are unchanged from the 2026-07-10 cut, which is the first thing to
check: uid stamping is additive, and a row-count change would have meant
something else moved.

## History

- **2026-08-17** — re-cut on `d614404` for uid stamping (#71), per the PI's
  2026-08-14 ruling that stamping is the last artifact-changing PR before the
  item-4 gate baseline is frozen. Also absorbed the July `group_d_salvaged_fields`
  column the previous cut had never picked up.
- **2026-07-10** — original capture, institution-outcome-reporting Phase 2
  Step 0, on the unmodified codebase before any Phase 2 changes. No prior mock
  run existed under `runs/` at the same sample size/seed, so a fresh one was
  generated. Superseded twice over (see above); the pre-stamping bytes are
  recoverable from git history at `66116a5`.
