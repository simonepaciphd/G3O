# Operations runbook — launch, pre-flight, resume, persist

The tracked, run-agnostic operations guide for a `g3o presweep` run. A
run-specific copy (with the exact command used) is kept alongside each run at
`runs/<run_id>/_LAUNCH.md`; that directory is gitignored, so this file is the
version-controlled reference.

Commands below use `<run-id>` as a placeholder and PowerShell line
continuations (`` ` ``). The pre-sweep launched on 2026-05-09 used run id
`20260509-presweep`, `--sample-size 1000`, `--seed 22294`.

> **Run ids (Run API spec §2, 2026-08-11).** `--run-id` is now optional. Omit it
> and one is minted as `r<YYYYMMDD>T<HHMMSS>Z-<4hex>` (UTC) and echoed to
> **stderr** as `run_id=<id>` the moment it exists — before the run blocks — so a
> long run can be resumed or monitored while still in flight. It is also the first
> key of the JSON document on stdout.
>
> Pass an explicit `--run-id` for exactly two purposes: replicating a run, and
> **resuming** one. A minted id can never name an existing run directory, so a
> resume is always a deliberate act rather than an accident of timing. Resume
> itself is unchanged — re-invoke the same command with the same id and each stage
> rejoins from `_state/`.
>
> `--session-id` (spec §4.2) records which session drove the run; precedence is
> the flag, then `G3O_SESSION_ID`, then `unattended`.
>
> **What a run records about itself (Run API spec §4).** Every run launched
> through the CLI or `launch()` writes two things into `runs/<run_id>/`:
>
> - `manifest.json` — the planning manifest as before, now carrying the run's
>   identity as well: `run_started_at` (authoritative for wave classification),
>   `session_id`, git sha/dirty, install path, package version, the contract pin
>   and prompt hashes, the config snapshot with its `config_hash`, credential
>   fingerprints, and the master build id when the master declares one. Written
>   atomically before any spend. On resume the identity half is **preserved** and
>   only the planning half refreshes.
> - `events.jsonl` — append-only, one JSON object per line: `run_launched`,
>   per-stage `stage_started`/`stage_completed`, per-chunk `chunk_submitted`/
>   `chunk_terminal`, `poll_timeout`, and one terminal `run_completed` /
>   `run_stopped` / `run_failed`. `seq` is contiguous from 1 across resumes.
>
> Both are records, never controls: `_state/` remains the only thing resume reads,
> and a telemetry write that fails warns rather than stopping the run. A log that
> ends with **no** terminal event means the process died — read it as abnormal
> termination, not as "still running", and check `_state/` for the truth.
>
> One caveat carried over from §3.5: **resume with the key you launched with.**
> Batches are listed per API key, so a resume under a rotated key would find none
> of the in-flight chunks and resubmit them — both sets would bill. The run
> refuses to continue rather than allow that, naming both fingerprints.
>
> A second caveat, from §1.7: **concurrent same-process launches must agree on
> `dry_run`.** Serper live mode is held in a module global, so two launches in one
> process that disagree race it — a dry run setting it `False` after a live run set
> it `True` sends the live run down the mock path, producing a run that believes it
> searched and did not. Concurrent launches are otherwise safe: no key state is
> process-global (§3.2) and both shared caches write atomically (§3.4). Until the
> flag is threaded the way the credentials were, this is **not supported** — run
> disagreeing launches in separate processes.

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
- `--cost-ceiling <USD>` — aborts (exit 3) if the estimated OpenAI Batch cost
  exceeds the figure. Can also be set via `G3O_BUDGET_LIMIT_USD` env var;
  the CLI flag takes precedence. Enforced on both `--preflight` and
  `--execute` paths (supersedes Decision D7; PR #52).

## Failure honesty in `--execute` (live mode)

- **Serper key gate:** in `--execute`, a missing Serper key is a hard error at
  startup — live mode never returns or caches mock results. The gate reads the
  run's *resolved* credentials (Run API spec §3.1: explicit → env → unset), so it
  covers a key passed programmatically exactly as it covers `SERPER_API_KEY`.
- **Key attribution:** every batch submit carries `g3o_key_fingerprint`
  (`sha256(key)[:8]`) alongside its `{g3o_run_id, g3o_stage, g3o_chunk}` identity
  (§3.5), so batches listed server-side under two different keys stay
  attributable. Reconciliation still matches on identity alone — matching on the
  fingerprint too would make a batch submitted under an earlier key unfindable,
  and a missed reconcile is a double submit.
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
├── final/                                  # written by `g3o persist` after Stage 6
│   ├── g3o_activities_v{N}.csv
│   ├── g3o_activity_sources_v{N}.csv
│   └── g3o_institution_summary_v{N}.csv
└── archive/institutions/<shard>.tar        # written by `g3o archive --apply` (see below)
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

## Archive (retention) — the last operation on a run

A finished run's institution tree is the storage overhang: at the full frame
roughly 20M files. Once the run is complete, `g3o archive` tars it one shard at
a time to `runs/<run-id>/archive/institutions/<shard>.tar` (plain tar — the page
artifacts inside are already gzipped, so outer compression buys ~nothing).

```powershell
g3o archive --run-dir runs/<run-id>            # dry run: prints the plan, writes nothing
g3o archive --run-dir runs/<run-id> --apply    # tars, verifies, then deletes the sources
```

**Dry run is the default.** Without `--apply` the command prints shard count,
file count, byte totals, and projected tar sizes, then exits without writing or
deleting anything. Note the projected tar size is an *estimate* (tar block
overhead modelled, extended headers not).

**Preconditions.** `archive` refuses unless all three hold, and reports every
gap at once:

1. `final/` contains the three Stage-7 CSVs (run `g3o persist` first).
2. `_state/.done/` holds a marker for every stage in `g3o.run.presweep.STAGES`.
3. Run-level reports (`run_summary.json`, `_health_report.json`) are written.

Condition 3 is the one that bites: the reports read the *live* institution
tree, so archiving before they run produces an empty report against an archived
run. Archival is strictly the last operation on a run.

**Verification precedes every delete.** Each tar is re-opened after writing and
its member count and total member bytes compared against a fresh walk of the
source. A mismatch aborts the whole command, deletes nothing, and renames the
bad tar to `<shard>.tar.FAILED` so it is never mistaken for a good archive.
Shards archived before the failure stay archived — each verified against its
own source.

**Idempotent.** Re-running after an interruption finishes the remainder: a
shard whose tar exists and verifies is not rewritten, and a shard whose source
is already gone is skipped.

Run-level files (`manifest.json`, `_state/`, `_attrition.jsonl`, `final/`, the
reports) are never archived — they stay live. A completed full-frame run's live
tree is those files plus at most 256 tars.

### Restore

There is no restore subcommand (spec §A2, v1 scope). Restoring a shard is one
plain `tar`:

```powershell
tar -xf archive/institutions/<shard>.tar -C <run_dir>/institutions/
```

The tar is rooted at the shard name, so this recreates
`institutions/<shard>/INST-XXXXXXX/...` exactly where it was. To restore an
entire run, repeat for each tar in `archive/institutions/`.

Tars are written in **GNU format**, not Python's `PAX` default: PAX spends an
extra 1 KB per member on an extended header for sub-second mtimes, which is
~20 GB of padding at full-frame scale and nothing reads it. GNU tar, bsdtar
(Windows' bundled `tar.exe`), Python's `tarfile`, and 7-zip all read GNU
format, so the command above is unaffected.

## Notes

- The seed (`22294`) makes the sample reproducible: delete `runs/<run-id>/` and
  re-run with the same seed to draw the same institutions.
- WS3 round-2 owns the `official_site_url` master column. Pre-rollout, the
  Stage 2 LLM path runs for every institution; bypass envelopes appear once the
  column is populated.

  **Since 2026-08-30 the pipeline populates it from its own output** (PI ruling),
  without writing the registry. Two halves, deliberately separate:

  - `orchestrate e2e` runs a **harvest** leg after the gate and before the load,
    rebuilding `<runs-dir>/_site_overlay/official_sites.csv` from every completed
    run — one row per institution Stage 2 found a site for, carrying `run_id`,
    `git_sha`, the model and the model's confidence. The rebuild is deterministic,
    so a repeat over an unchanged corpus is a byte-identical no-op. Disable with
    `--no-harvest`; make it a gate with `--require-harvest`.
  - `presweep --official-sites <overlay.csv>` **spends** it: the drawn sample is
    decorated in memory with `official_site_url`, so Stage 2 is bypassed for those
    institutions and Stage 1b gets the site directly. The read-only master and the
    frame CSV are never touched.

  Two filters are on by default and both are recorded in the manifest under
  `run_official_sites`. `--official-sites-min-confidence` defaults to `high` — the
  model's rating of its own pick, not a validated accuracy figure. Picks whose
  `site:` host is shared with another institution are skipped, because one
  `site:nsw.gov.au` issued for 95 different councils is worse than leaving them
  website-free; `--official-sites-allow-shared` turns that off.

  The instrument's identity is `config.official_sites_hash`, a digest of the
  (uid, site) pairs the run actually spends — not of the file, which is rebuilt
  under the same name after every run. It is guarded on resume: a run that
  classified with Stage 2 cannot resume into one that bypasses it.
- The cost-model brief consumes per-stage telemetry from the run.
- **Serper spend is measured, not estimated.** `g3o.discovery.serper_client.get_balance()`
  reads `GET /account`; bracket a run with it and report the delta rather than
  multiplying queries by a rate — a silently retried or dropped request cannot
  hide inside a delta. Measured 2026-08-01: **1.84 credits/institution** under
  the default `chain` mode, **8.52** under `legacy`. The USD-per-credit rate is
  still an open PI input; `docs/budget/cost-model.md` carries both candidate
  rates ($0.00056 and $0.001, ~1.8× apart) rather than picking one.
