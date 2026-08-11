# Run-contract fixtures — field notes

Example `manifest.json` + `events.jsonl` for the Run API telemetry surface, from
**SPEC — G3O Run API v1 (2026-08-02, v0.1) §4**. Published ahead of the
implementation so the `g3o-api` loader can be written against a fixed shape
rather than against a moving PR.

**Status:** fixture set **v1**, notes revised **v1.1**. The Run API is not
implemented yet; nothing in the repo writes these files today. If reality
corrects a fixture, the set is versioned (see [Changelog](#changelog)) and Katon
is told the same day. **v1.1 changed notes only — no fixture bytes moved**, so a
loader written against v1 needs no revision.

**These are synthetic example runs, not records of real runs.** No run with
these ids exists. Mixed provenance, deliberately:

| Real, and verifiable against this commit | Illustrative only |
|---|---|
| `code.git_sha` (= `e2eba1c`, tip of `main` when written) | `run_id`, all `ts`, `run_started_at` |
| `contract.*.version` / `.sha256` (= `tests/goldens/contract_version_pin.json`) | all `counts_*`, `wall_seconds`, `n_*` |
| `prompts.*` sha256 (= the four files in the working tree) | `batch_id`, `key_fingerprint` |
| `config` field set + defaults (= `PresweepConfig`, `g3o/run/presweep/config.py:48-143`) | `hostname`, `install_path`, `operator`, `session_id` |
| `config_hash` (actually computed over this `config`) | `frame.*` (null — pending, see below) |

Verify the real ones:

```bash
git rev-parse HEAD                                    # matches code.git_sha
cat tests/goldens/contract_version_pin.json           # matches contract.*
python -c "import hashlib,pathlib,sys;print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())" g3o/extract/prompts/system_prompt.md
```

## Files

| File | Run | Shape |
|---|---|---|
| `manifest.json` | `r20260810T142233Z-9f3b` | written by `launch()` before any spend |
| `events.jsonl` | `r20260810T142233Z-9f3b` | completed, all 8 stages, `stop_after=validate` |
| `events_failed.jsonl` | `r20260810T151004Z-2b71` | raises mid-`extract`; `run_failed` precedes the raise (§1.5) |
| `events_resumed.jsonl` | `r20260810T153512Z-4d8a` | F16 poll timeout → `run_stopped` → re-invoked → rejoined → completed |

One manifest is supplied. The other two runs' manifests are identical in
**shape**, differing only in `run_id` / `run_started_at`; on resume the manifest
is **never** rewritten (§4.1), so a resumed run's manifest still carries the
original launch's `run_started_at` and `session_id`. All three share one
`config_hash` — the configuration is the same, only identity and paths differ.
That is the intended property; see the exclusion list below.

## `manifest.json`

| Field | Type | Notes |
|---|---|---|
| `manifest_schema_version` | int | `1`. Bumped only on a breaking change to this surface. |
| `run_id` | str | `r<YYYYMMDD>T<HHMMSS>Z-<4hex>`, UTC (§2). |
| `run_started_at` | str | ISO-8601 UTC. **Authoritative for wave classification** (§2, §5.5) — never parse the id string for this. |
| `session_id` | str | Launching session only. Per-event `session_id` may differ (see events). |
| `operator`, `hostname` | str | Free text. |
| `invocation` | str | `api` \| `cli`. |
| `code.git_sha` | str | 40-hex. |
| `code.git_dirty` | bool | `true` is permitted and recorded, not blocked (§4.1). |
| `code.package_version` | str | `importlib.metadata`. |
| `code.install_path` | str | Guards the stale-editable-install failure mode. Machine-specific. |
| `frame.frame_id` | str \| null | FK target for `g3o.frames` (§5.1). **Currently null — see decision 5.** |
| `frame.master_build_id` | str \| null | Which master build the run sampled from. **Currently null.** |
| `contract.<name>` | obj | `{path, version, sha256}` per contract. **Two entries — see decision 1.** `sha256` is the §29 pin over the *machine-readable surface*, **not** the file's own sha256. |
| `prompts.<repo-relative path>` | str | sha256 of the **file bytes**. **Keyed by path — see decision 2.** |
| `config` | obj | Full `PresweepConfig` snapshot, all 27 fields, JSON-serializable. `Path`→POSIX string, tuple→array. Declared fields only; derived properties (`evidence_terms`, `institution_search_languages`, `chain_query_languages`) are **not** included — they are reproducible from the fields, and duplicating them would create a second source of truth. |
| `config_hash` | str | sha256, canonicalization below. |
| `config_hash_excludes` | list[str] | The exclusion list, recorded in-band so the hash is reproducible without out-of-band knowledge. |
| `credentials.<provider>` | obj | `{source, fingerprint, label}`. `source` ∈ `explicit` \| `env` \| `unset`. `fingerprint` = `sha256(key)[:8]`, or null when unset. **Never any key material** (§3.3). |
| `model_ids.requested` | obj | The model *asked for*. **See decision 6.** |

### `config_hash` canonicalization

```python
hashed = {k: v for k, v in config.items() if k not in config_hash_excludes}
canonical = json.dumps(hashed, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode("utf-8")
config_hash = hashlib.sha256(canonical).hexdigest()   # full 64-hex
```

Pinned exactly because the hash is stored in `g3o.runs.config_hash` (§5.2) and
may be re-verified server-side. An unstated canonicalization is a hash only the
writer agrees with.

Accepted by the PI 2026-08-11 (see resolved question 1). Whether it is
*re-verifiable* server-side is still Katon's to confirm — his question 4.

## `events.jsonl`

Append-only, one JSON object per line. Envelope on **every** line (§4.3) —
these six keys are the only guaranteed ones:

```
{ts, run_id, session_id, git_sha, seq, event}   + "stage" on stage-scoped events
```

Everything event-specific nests under **`payload`** (decision 3). `git_sha` is
repeated per event, redundantly with the manifest, so a truncated log still
self-identifies its code version.

| `event` | `stage`? | `payload` |
|---|---|---|
| `run_launched` | no | `invocation`, `config_hash` |
| `resume` | no | `stages_done[]`, `chunks_rejoined[]`, `key_fingerprint` |
| `stage_started` | yes | `counts_in` |
| `stage_completed` | yes | `counts_in`, `counts_out`, `wall_seconds` (+ stage extras: `filter_mode`/`would_drop`, `n_failed`) |
| `chunk_submitted` | yes | `chunk`, `batch_id`, `n_jobs`, `key_fingerprint` |
| `chunk_terminal` | yes | `chunk`, `batch_id`, `terminal_state`, `n_output`, `n_error`, `resolved_model` |
| `poll_timeout` | yes | `batch_id`, `waited_seconds`, `max_wait_per_stage`, `note` |
| `spend_snapshot` **(optional)** | no | `provider`, `metric`, `value`, `best_effort` |
| `run_completed` / `run_stopped` / `run_failed` | sometimes | `outcome`, `stop_after`; `run_failed` adds `error_class`, `error_message`; `run_stopped` adds `reason` |

### Loader invariants

1. **One file, one `run_id`.**
2. **`seq` starts at 1, contiguous, no gaps.** PK is `(run_id, seq)` (§5.2).
3. **`ts` is non-decreasing.** Gaps up to `max_wait_per_stage` (default 90000 s = 25 h) are normal, not stalls — `events_resumed.jsonl` has one.
4. **The last line is terminal.** `run_completed` and `run_failed` are final. `run_stopped` may appear mid-file **iff** immediately followed by `resume`.
5. **No terminal event, or a truncated final line, means abnormal termination** — a crashed run's log simply ends early (§4.3). It must **not** be read as "still running". `_state/` is the recovery source of truth, never this log. See open question 3.
6. **`session_id` varies within a run** across invocations (`events_resumed.jsonl` seq 22-29). Join on `run_id`; treat `session_id` as per-event provenance.
7. **`chunk` is 1-based** (`run_state.py:161`).
8. **`terminal_state` ∈ `{completed, failed, expired, cancelled}`** (`batch_client.py:88`).
9. **`stage` ∈ the 8-name roster** (`config.py:26`), in roster order: `discovery_general`, `classify_official_site`, `discovery_site_restricted`, `filter_eligibility`, `classify_triage`, `scrape`, `extract`, `validate`. Only the four LLM stages (`classify_official_site`, `classify_triage`, `extract`, `validate`) emit `chunk_*`.
10. **Telemetry is passive.** No control flow reads it; failures after launch WARN and never abort (§4.4). Treat these files as a record, never as a lock.
11. **`git_sha` may vary within a run**, like `session_id`, when a resume happens under different code (decision 7). The fixtures keep it constant; do not assume constancy. The manifest's copy is the *launching* code version.
12. **`spend_snapshot` is optional and may be absent entirely** from a run's log (resolved question 4). Never treat its absence, or a gap between snapshots, as a defect.

## Decisions taken where the spec's §4 example and reality diverge

The manifest surface is mine to own; these are recorded, not silent. 1, 2 and 6
are corrections to the §4.1 example rather than departures from its intent.
7 is not a §4 divergence at all — it is a PI ruling, recorded here because it is
the decision a loader author needs to read alongside the rest.

1. **`contract` is keyed by contract name, not a single block.** §4.1 shows one
   `{version, sha256}`. There are **two** independently-versioned contracts —
   extract `v2.2` and validate `v1.1`, pinned separately in
   `tests/goldens/contract_version_pin.json`. A single block cannot record both.
   *Consequence for §5.2:* `g3o.runs.contract_version` / `.contract_sha256` are
   scalar columns and cannot hold two contracts — Katon needs either two column
   pairs or a jsonb. **Flagged; his call.**
2. **`prompts` is keyed by repo-relative path.** §4.1's bare filenames
   (`system_prompt.md`, `output_contract.md`) collide: there are two of each,
   under `g3o/extract/prompts/` and `g3o/validate/prompts/`.
3. **Event payloads nest under `payload`.** §4.3 specifies an envelope and then
   "payload highlights" without saying where they live; §5.2's `run_events` has
   a `payload jsonb` column, so this maps 1:1 and needs no ingest-side surgery.
4. **`config_hash` excludes `run_id`, `runs_dir`, `master_csv`.** `run_id` is a
   `PresweepConfig` field, so hashing it would make every run's hash unique by
   construction — defeating cross-run comparison via `g3o.runs.config_hash`
   while adding nothing to the resume drift check (which compares a run against
   its own stored snapshot). The two absolute paths differ between droplet, PI
   machine and CI, so including them would make the same logical configuration
   hash differently per machine. The list is recorded in-band.
5. **A `frame` block is added.** §4.1's example omits it; §5.1 requires it
   ("it goes in the manifest → ingest") and it is assigned to this surface.
   Shape is fixed now, values are `null` pending Nolan's uid-stamping PR, so no
   `manifest_schema_version` bump is needed when they arrive.
6. **`model_ids.requested` + `resolved_model` per chunk.** The manifest is
   written *before* any spend, so it cannot know the versioned model id
   (`gpt-5-nano-2025-08-07`) — and that versioned id, not the requested alias,
   is the T1 provenance anchor (`batch_client.py:160`). The requested alias goes
   in the manifest; the resolved id is recorded per chunk in `chunk_terminal`.
   A run whose chunks resolved to different model versions is therefore
   detectable. `system_fingerprint` is deliberately absent: newer models omit
   it, and absence must be recorded honestly rather than fabricated
   (`batch_client.py:167`).
7. **Resume under a changed `git_sha` is permitted and recorded, not fatal**
   (PI, 2026-08-11; resolved question 2). Same treatment §4.1 gives
   `git_dirty`: recorded, never blocked. The per-event `git_sha` is what makes
   the change legible after the fact — the manifest alone could not show it.
   Deliberately asymmetric with a changed *credential* fingerprint, which still
   fails loudly (§3.5): a mismatched key makes the original batches
   unreachable, which is unrecoverable, whereas mixed code within a run is
   merely a fact worth knowing.

## Questions escalated to the PI — three resolved, one open

Numbering is preserved from the 2026-08-10 escalation so the email thread and
this file stay cross-referenceable.

1. **RESOLVED** (PI, 2026-08-11) — decision 4's exclusion list *is* the
   intended `config_hash` semantics: `run_id`, `runs_dir` and `master_csv` are
   excluded, the list is recorded in-band, and "same configuration" therefore
   means same declared fields modulo run identity and machine-local paths.
   Katon's question 4 (server-side re-verification) is still open on his side.
2. **RESOLVED** (PI, 2026-08-11) — resuming under a different `git_sha` is
   permitted and recorded, not fatal. Written up as decision 7; loader
   invariant 11 follows from it.
3. **OPEN — a hard kill emits no `run_failed`.** §1.5 guarantees `run_failed` precedes
   every post-manifest *raise*, but `SIGKILL` produces no raise, so Item 3's
   induced-failure test will yield a log with **no** terminal event (invariant
   5) rather than a named failed state. Which named state should that resolve
   to, and is it derived by the orchestrator from `_state/` + absent terminal
   event? Not representable as a fixture until Item 3 measures the real shape;
   a `events_truncated.jsonl` will be added in fixture set v2 once it is.
4. **RESOLVED** (PI, 2026-08-11) — `spend_snapshot` stays, as best-effort and
   optional: emitted only where a Serper account call is already cheap, never
   blocking, and declared optional to the loader (invariant 12). It remains
   droppable per the sprint memo's relief-valve list **without** a loader
   change, which is the point of declaring it optional now. §9 open item 4
   (whether the extra account calls earn their keep at scale) is answered on
   cost figures once PR C measures them.

## Sufficiency check for Katon

Please answer in writing so this seam can be closed:

1. Does `manifest.json` carry everything `ensure_run()` needs for `g3o.runs`, or is a field missing?
2. Does `frame.frame_id` match what `g3o.frames` expects as a key (§5.1)?
3. Is `payload`-nesting right for `run_events.payload jsonb`?
4. Will you re-verify `config_hash` server-side? If so, does the canonicalization above work, and is the exclusion list right?
5. Do the three terminal shapes (completed / failed / stopped-then-resumed) plus invariant 5 cover what your loader must handle?
6. Decision 1 — two contracts vs. scalar `contract_version`/`contract_sha256` columns: two column pairs, or jsonb?

## Changelog

- **v1.1** — 2026-08-11 — **notes only, no fixture bytes changed.** PI resolved
  escalated questions 1, 2 and 4 (`config_hash` exclusions stand; resume under a
  changed `git_sha` is permitted and recorded, now decision 7 + invariant 11;
  `spend_snapshot` is optional, now invariant 12). Question 3 (named state after
  a hard kill) stays open pending Item 3. Katon's six sufficiency questions are
  unaffected and still open.
- **v1** — 2026-08-10 — initial, from spec v0.1 §4, authored at `e2eba1c`.
