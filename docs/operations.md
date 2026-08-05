# Operations runbook — launch, pre-flight, resume, persist

The tracked, run-agnostic operations guide for a `g3o presweep` run. A
run-specific copy (with the exact command used) is kept alongside each run at
`runs/<run_id>/_LAUNCH.md`; that directory is gitignored, so this file is the
version-controlled reference.

Commands below use `<run-id>` as a placeholder and PowerShell line
continuations (`` ` ``). The pre-sweep launched on 2026-05-09 used run id
`20260509-presweep`, `--sample-size 1000`, `--seed 22294`.

> **Master CSV.** `--master-csv` points at the institution master, which lives
> **outside** this repo and is read-only. From the repo working directory the
> path used for the pre-sweep was
> `..\..\inputs\G3O_Institution_Master_v2\data_final\master_institutions.csv`.
> The master is not shipped in the public repository.

## One-time setup

```powershell
python -m playwright install chromium
g3o verify-model --model gpt-5-nano
```

`verify-model` is a one-job Batch API submit that confirms the model id is live
before a multi-day run starts.

## Pre-flight (no live submits)

Run readiness checks without spending anything:

```powershell
g3o presweep --preflight `
    --run-id <run-id> `
    --sample-size 1000 --seed 22294 `
    --master-csv ..\..\inputs\G3O_Institution_Master_v2\data_final\master_institutions.csv `
    --stop-after validate `
    --cost-ceiling 100
```

`--preflight` runs key checks, draws the planned sample, projects the Stage 5
chunk/size split and a cost preview, and exits **non-zero if a required key is
missing**. It writes no state and submits no production batches. Optional:

- `--verify-model` — also runs a live one-job `verify-model` round-trip
  (submits a batch; off by default).
- `--cost-ceiling <USD>` — reports whether the estimated OpenAI Batch cost
  exceeds the figure. Informational only; no abort is wired (Decision D7).

## Failure honesty in `--execute` (live mode)

- **Serper key gate:** in `--execute`, a missing `SERPER_API_KEY` is a hard
  error at startup — live mode never returns or caches mock results.
- **Request failures** are recorded as explicit error envelopes and in the
  attrition ledger, never as a silent "searched, found nothing" artifact.
- Purge any stale `cache/serp_*` entries before a fresh launch so a prior
  dev-mode mock can never seed a live run.

## Page-text cap and empty-page filter

Before Stage 5 job construction:

- Extracted page text is capped at `extract_text_cap_chars` (default `60000`)
  using the `head_tail` rule, bounding per-job size and cost (Decision D3).
- Empty / near-empty pages (under `empty_page_min_chars`, default `50`) are
  filtered out before extraction and recorded in the attrition ledger, so an
  empty page never pressures the model to fabricate a row.

## Attrition ledger

A live run always writes `runs/<run-id>/_attrition.jsonl`: one append-only
record per `(institution, stage, reason)` wherever coverage is lost (no
discovery hits, no kept URLs, scrape failure, empty page, parse failure). An
empty file means "this run lost no institutions", not "no ledger".

## Recommended launch (full pipeline through Stage 6)

```powershell
g3o presweep --execute `
    --run-id <run-id> `
    --sample-size 1000 --seed 22294 `
    --master-csv ..\..\inputs\G3O_Institution_Master_v2\data_final\master_institutions.csv `
    --stop-after validate
```

`--stop-after validate` runs Stages 1a → 6. To stop at Stage 5, drop the flag
(the default is `extract`).

Run from `tmux` / `screen`. Wall clock is dominated by Batch API turnaround
(per-stage `--max-wait-per-stage` ~25h SLA + jitter); per-stage timings and
costs land in the run summary printed on completion.

## Resume after interruption (auto-inferred)

If the orchestrator process crashes (reboot, network glitch, etc.), re-run the
**same** command. Resume is auto-detected from the presence of
`runs/<run-id>/_state/{stage}.json` files. On resume, the run aborts with a
clear diff if the freshly drawn sample or config diverges from the recorded
`manifest.json` (manifest guard) — so a changed master CSV or changed args
cannot silently diverge from the on-disk artifacts.

| State on disk | Action |
|---|---|
| `_state/.done/{stage}.json` present | Skip the stage; reconstruct return values from per-institution artifacts. |
| `_state/{stage}.json` present (active) | Trust the saved `batch_id`(s); skip submit; rejoin polling at terminal state; fetch + persist + mark done. |
| Neither present, partial outputs on disk | Fresh stage run; per-institution / per-URL skip-if-exists protects Serper / scrape spend. |
| `_state/{stage}.json` in failed/cancelled/expired terminal state | Runner raises with the state-file path; **does not auto-resubmit**. Investigate the OpenAI batch dashboard before retrying. |

## What's persisted to disk during `--execute`

```
runs/<run-id>/
├── manifest.json
├── _attrition.jsonl                       # per-(institution, stage, reason) coverage-loss ledger
├── _state/
│   ├── classify_official_site.json         # active state for in-flight Stage 2 batch (per-chunk)
│   ├── classify_triage.json                # … Stage 3 …
│   ├── extract.json                        # … Stage 5 …
│   ├── validate.json                       # … Stage 6 …
│   └── .done/
│       ├── discovery_general.json          # Stage 1a completion marker (no_batch)
│       ├── classify_official_site.json     # moved here once Stage 2 fetch succeeded
│       ├── …                               # …one per completed stage
│       └── validate.json
├── institutions/<shard>/INST-XXXXXXX/      # <shard> = md5(inst_id)[:2]
│   ├── institution.json
│   ├── 1a_discovery_general.json
│   ├── 2_official_site.json
│   ├── 1b_discovery_site_restricted.json   # absent if no usable official site
│   ├── 3_triage.json
│   ├── scrape/<url_hash>.json.gz           # one per fetched page (gzipped)
│   ├── extract/<url_hash>.json.gz          # one per Stage 5 result (gzipped)
│   └── 6_validate.json
└── final/                                  # written by `g3o persist` after Stage 6
    ├── g3o_activities_v{N}.csv
    ├── g3o_activity_sources_v{N}.csv
    └── g3o_institution_summary_v{N}.csv
```

## Persist (Stage 7) — separate, deterministic

After `validate` finishes, write the three canonical CSVs:

```powershell
g3o persist `
    --run-dir runs/<run-id> `
    --run-id <run-id> `
    --model gpt-5-nano `
    --version 1
```

`persist` is deterministic and refuses to clobber existing outputs without
`--overwrite`. It does not use the Batch API and is therefore not part of the
state-file machinery. See [`data_dictionary.md`](data_dictionary.md) for the
three CSVs' columns.

## Notes

- The seed (`22294`) makes the sample reproducible: delete `runs/<run-id>/` and
  re-run with the same seed to draw the same institutions.
- WS3 round-2 owns the `official_site_url` master column. Pre-rollout, the
  Stage 2 LLM path runs for every institution; bypass envelopes appear once the
  column is populated.
- The cost-model brief consumes per-stage telemetry from the run.
- **Serper spend is measured, not estimated.** `g3o.discovery.serper_client.get_balance()`
  reads `GET /account`; bracket a run with it and report the delta rather than
  multiplying queries by a rate — a silently retried or dropped request cannot
  hide inside a delta. Measured 2026-08-01: **1.84 credits/institution** under
  the default `chain` mode, **8.52** under `legacy`. The USD-per-credit rate is
  still an open PI input; `docs/budget/cost-model.md` carries both candidate
  rates ($0.00056 and $0.001, ~1.8× apart) rather than picking one.
