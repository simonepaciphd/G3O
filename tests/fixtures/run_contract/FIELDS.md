# Run-contract fixtures — field notes

Example `manifest.json` + `events.jsonl` for the Run API telemetry surface, from
**SPEC — G3O Run API v1 (2026-08-02, v0.1) §4**. Published ahead of the
implementation so the `g3o-api` loader can be written against a fixed shape
rather than against a moving PR.

**Status:** fixture set **v1**, notes revised **v1.2**. **Sufficiency confirmed
by Katon in writing, 2026-08-11** — he verified rather than read (recomputed
`config_hash` to a match, checked every offline-checkable invariant across all
three logs) and needs nothing changed in the set. That closes the Item 1 seam.

The Run API **is** implemented now: `g3o/run/telemetry.py` on branch
`item-2-PR-C` (PR C) writes both files. It is not merged to `main` yet, so a
loader test pinned to this branch stays pinned for now. Three places where the
implementation and these notes diverged are corrected below — see
[what the implementation actually writes](#what-the-implementation-actually-writes).

If reality corrects a fixture, the set is versioned (see
[Changelog](#changelog)) and Katon is told the same day. **v1.2 changed notes
only — no fixture bytes moved**, so a loader written against v1 needs no
revision and no re-download.

**These are synthetic example runs, not records of real runs.** No run with
these ids exists. Mixed provenance, deliberately:

| Real, and verifiable **at `e2eba1c`** | Illustrative only |
|---|---|
| `code.git_sha` (= `e2eba1c`, tip of `main` when written) | `run_id`, all `ts`, `run_started_at` |
| `contract.*.version` / `.sha256` (= `tests/goldens/contract_version_pin.json`) | all `counts_*`, `wall_seconds`, `n_*` |
| ~~`prompts.*` sha256~~ — **superseded, see below** | `batch_id`, `key_fingerprint` |
| `config` field set + defaults (= `PresweepConfig`, `g3o/run/presweep/config.py:48-143`) | `hostname`, `install_path`, `operator`, `session_id` |
| `config_hash` (actually computed over this `config`) | `frame.*` (null — pending, see below) |

**These values are pinned to `e2eba1c`, not to today's `main`** (v1.2 correction).
Contract v2.3 landed in `e9b2b07`, so `main` now pins extract **v2.3** / validate
**v1.2** and rewrote **all four** prompt assets. The fixture is a valid
snapshot of the commit it names; it is *not* a snapshot of `main`. Verify against
that commit, which is what the original recipe should have said:

```bash
git show e2eba1c:tests/goldens/contract_version_pin.json   # matches contract.*
git show e2eba1c:g3o/extract/prompts/system_prompt.md | \
  python -c "import hashlib,sys;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())"
```

A run's own manifest is always self-consistent — `code.git_sha` names the commit
its `contract` and `prompts` hashes were taken at — so a loader never needs to
resolve them against any particular branch. That property is why this staleness
is a documentation fix and not a fixture re-cut.

### `prompts.*`: this fixture's values are CRLF-derived and superseded

Found while re-checking the recipe above, and it is a **defect in the
implementation**, not only a stale note. This fixture's prompt hashes were
computed from a **Windows working tree**, where the four `.md` files carry CRLF;
the repository has no `.gitattributes`, so the same commit checks out with LF on
Linux. For `g3o/extract/prompts/system_prompt.md` at `e2eba1c`:

```
6a39912a…   sha256 of the CRLF working-tree bytes   <- what this fixture records
1b74cab1…   sha256 of the git blob (LF)             <- what a Linux checkout sees
```

So a file-bytes hash makes `prompts.*` **platform-dependent**: the droplet and a
Windows machine would record different hashes for identical prompt content, while
`contract.*.sha256` — which hashes Python objects, not bytes — would be identical.
A manifest that says "contract unchanged, prompts changed" for the same commit is
exactly the false signal this block exists to prevent, and it would surface on the
first comparison between a droplet run and a local one.

**Fix, on `item-2-PR-C`:** normalise line endings to LF before hashing, so the
value is a property of the content rather than of the checkout, and matches the
git blob on every platform. Once that lands, the LF column above is what a real
manifest contains, and **this fixture's `prompts.*` values are illustrative
only** — reproducible from a CRLF checkout, not from the implementation. Recorded
rather than re-cut, because prompt hashes are opaque strings to the loader: it
stores them and never recomputes them, so nothing downstream moves.

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
| `frame.master_build_id` | str \| null | Which master build the run sampled from; `mb-YYYY-MM-DD`. Null until a master build carries the column — **see decision 5.** |
| `contract.<name>` | obj | `{path, version, sha256}` per contract. **Two entries — see decision 1.** `sha256` is the §29 pin over the *machine-readable surface*, **not** the file's own sha256. |
| `prompts.<repo-relative path>` | str | sha256 of the file, **line endings normalised to LF**. **Keyed by path — see decision 2.** This fixture's values predate the normalisation and are CRLF-derived — see above. |
| `config` | obj | Full `PresweepConfig` snapshot, JSON-serializable. `Path`→string, tuple→array. **27 keys in this fixture; 29 in a real manifest** — v1.2 correction, see below. |
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

Accepted by the PI 2026-08-11 (see resolved question 1). **Re-verified
server-side by Katon, 2026-08-11** — recomputed from `manifest.json` to an exact
match (`952dfc5f…`), and pinned as a loader test against this fixture so drift on
either side fails loudly instead of the two quietly disagreeing (his question 4).

**Cross-language caveat** (Katon, v1.2): it reproduces because both sides are
Python. Any re-implementation elsewhere must match Python's float `repr` and
unicode handling to land on the same bytes. Nothing in the current config
snapshot is a float except `scrape_host_delay_seconds` (`1.0`), so the exposure
is small today and real the moment a float parameter is added.

### `config` is 27 keys here and 29 in a real manifest

v1.2 correction, and the one place a pre-implementation guess in this file was
simply wrong. The original note claimed "declared fields only; derived properties
are **not** included". PR C records two more:

| Extra key | Why it is in the snapshot |
|---|---|
| `institution_search_languages` | Derived, but **the resume guard compares it** — it is the Stage-5 provenance string, and a run resumed under a different language roster must abort rather than silently mix instruments. |
| `genai_terms_roster_hash` | Not a config field at all: a fingerprint of a module constant in `discovery/query_builder.py`. Recorded because the guard needs something to compare, or a run could be resumed against an edited query roster with nothing noticing. |

Both live in `config` rather than beside it because
`planning._assert_manifest_matches_on_resume` reads them there. Moving them out to
satisfy this document would have meant rewriting a load-bearing guard to match a
note — the wrong direction, so the note changed instead.

**No loader consequence.** `config_snapshot` is `jsonb` and the hash is recomputed
from each manifest's own `config`, so a 29-key snapshot verifies exactly as a
27-key one does. The only stale figure is the count: Katon's verification record
reads "24 of 27 after exclusions"; against a real manifest it is **26 of 29**.

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

## What the implementation actually writes

v1.2, added now that PR C exists. Every difference below is **additive** — extra
keys inside `payload`, which is `jsonb`, so a loader written against v1 reads a
real log unchanged. Recorded because "the fixture said four keys and the file has
five" should be a documented fact, not a surprise during ingest.

| Where | Fixture says | Implementation also emits | Why |
|---|---|---|---|
| `chunk_submitted` | `chunk`, `batch_id`, `n_jobs`, `key_fingerprint` | `adopted: true`, on the reconciliation path only | A chunk adopted from a server-side batch entered flight without a fresh create. It still emits `chunk_submitted` — otherwise a chunk would report `chunk_terminal` with no submission anywhere in the log — and `adopted` is what distinguishes the two. |
| `poll_timeout` | `batch_id`, `waited_seconds`, `max_wait_per_stage`, `note` | `chunk` | One event per still-flying chunk, so the chunk has to be named. |
| `chunk_terminal` (failed / expired / cancelled) | `n_output`, `n_error`, `resolved_model` | `n_error: null`, `resolved_model: null`, `n_output: 0` | Nothing was fetched, so there is no error count and no resolved model to report. Null is the honest value; zero would claim a measurement. |
| `run_completed` / `run_stopped` / `run_failed` | `outcome`, `stop_after` (+ extras) | `wall_seconds` | Already present in the fixture's own data (`events.jsonl` seq 27); the payload table just omitted it. |
| `spend_snapshot` | one example line | **never emitted** | Dropped per the sprint's relief-valve list. Invariant 12 already covers this: absence means nothing. Adding it later needs no loader change, which was the point of declaring it optional. |

One more, on the manifest rather than the events: a real `manifest.json` carries
the **planning** keys too (`run_kind`, `layout_version`, `run_date`,
`run_timestamp`, `run_model`, `stages_planned`, `institutions`). §4.1 names
`runs/<run_id>/manifest.json` — the path the pre-existing planning manifest
already occupied — so the two compose into one document rather than one replacing
the other. `ensure_run()` reads the §4.1 keys and can ignore the rest.

On resume the §4.1 identity keys are **preserved** and only the planning keys
refresh, which is what makes `run_started_at` trustworthy as the wave-classification
input (§5.5). Before PR C the planning timestamp was rewritten on every
invocation, so a resumed run would have reported the *resume* moment as its start.

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
   pairs or a jsonb. **ANSWERED (Katon, 2026-08-11): `runs.contracts jsonb not
   null`,** keyed by contract name, mirroring this block verbatim rather than
   flattening it — because the count already went 1 → 2, so two column pairs would
   hard-code today's number into the schema. A change against spec §5.2; it lands
   in the v0.6 header and Simone's sign-off gates the apply. Vindicated since:
   extract went `v2.2` → `v2.3` and validate `v1.1` → `v1.2` inside the same week
   this fixture was written, and the two moved **independently**.
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
   Shape is fixed now, so no `manifest_schema_version` bump is needed when values
   arrive. **Resolved in both directions, 2026-08-11:**

   - *What the pipeline populates* (PR C): **`master_build_id` only**, read from
     the master CSV's own `master_build_id` column when it has one, with one
     distinct value required across the sampled rows — disagreement records null
     rather than choosing. **`frame_id` stays null**, because it is the FK target
     of `g3o.frames`, whose design (§5.1) is still an open item awaiting Katon's
     and the PI's explicit OK. Recording the build id we can attest while leaving
     the key we cannot is the split, not an oversight.
   - *The format*, which did not need to wait for Nolan: `mb-YYYY-MM-DD`, already
     enforced on `main` by `scripts/build_codebook_html.py:284`, which also
     requires exactly one distinct value per master build. The 2026-07-17 master
     carries no such column at all, so today both fields are null on a real run;
     Nolan's PR (or a newer master build) is what supplies the column.
   - *What the loader does* (Katon): `runs.frame_id` stays **NOT NULL** and the
     loader derives the frame key from `master_build_id`, taking an explicit
     `--frame-id` when the manifest's is null and recording it as
     operator-supplied. Deliberately **no** default to the current master build —
     that would attribute a run to a frame it may not have sampled, which is the
     invariant the FK exists to protect.
   - *Consequence for the Item 4 smoke gate:* until a build-id-carrying master
     lands, whoever runs the smoke passes `--frame-id` explicitly. That belongs in
     the Item 3 runbook rather than being discovered during the gate.
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

## Sufficiency check for Katon — CLOSED, 2026-08-11

Answered in writing; the set is **sufficient and unchanged**. He verified rather
than read: `config_hash` recomputed to an exact match, and invariants 1, 2, 3, 4,
6 and 9 checked across all three logs (27 / 29 / 21 lines). Invariants 7, 8, 10,
11 and 12 are not offline-checkable from the files alone — they are single-valued
in this set or properties of the live pipeline.

| # | Question | Answer |
|---|---|---|
| 1 | Everything `ensure_run()` needs? | **Yes.** Three `g3o.runs` fields are correctly *absent*: `run_completed_at` comes from the `run_completed` event (a manifest written before spend cannot know it), and `synthetic` / `in_frame` are ingest-side operator decisions. `ensure_run` loads events first, then completes the row. |
| 2 | Does `frame.frame_id` match `g3o.frames`? | **Yes, keep the shape.** Follow-ups now resolved in decision 5 above. |
| 3 | Is `payload`-nesting right? | **Yes, 1:1, no surgery.** `stage` living in the envelope rather than the payload is also right — it maps straight to §5.2's `stage` column. |
| 4 | Re-verify `config_hash` server-side? | **Yes, and it verifies.** Pinned as a loader test against this fixture. Cross-language caveat recorded above. |
| 5 | Do the terminal shapes + invariant 5 cover it? | **Yes.** All three load. Invariant 5 changes loader behaviour: no terminal event ⇒ load the run and its facts, leave `run_completed_at` null, and **refuse to mark it publishable without an explicit operator override**. An abnormally-terminated run must not publish silently just because a wave window happens to cover it. |
| 6 | Two column pairs or jsonb? | **jsonb**, one column. See decision 1. |

### Schema v0.6 commitments made in that reply

His to decide per the 2026-08-07 brief; **Simone signs off before any production
apply.** Recorded here because a loader author reading this file needs them, and
because two are changes against signed spec §5.2:

1. `runs.contracts jsonb not null` replaces §5.2's scalar `contract_version` /
   `contract_sha256`. *(change against §5.2)*
2. `run_events` gains `session_id text` and `git_sha text` — **not in §5.2**, and
   the gap he caught: invariants 6 and 11 make both per-event provenance, and
   `events_resumed.jsonl` proves it (`e28ca730` → `a1b2c3d4` at seq 22). As
   specced, the resuming session was representable nowhere, which would have
   defeated §4.2's whole purpose as the join key back to `interaction-log.csv`.
   *(change against §5.2)*
3. `runs.frame_id` stays NOT NULL; the loader requires `--frame-id` when the
   manifest's is null, recorded as operator-supplied. No silent default.
4. A run whose log has no terminal event loads with `run_completed_at` null and is
   not publishable without an explicit operator override.

Commitment 4 is also half of the Item 3 joint gate: the induced-failure test
requires "nothing published", and this is the database side of it already agreed.

## Changelog

- **v1.2** — 2026-08-11 — **notes only, no fixture bytes changed**; no loader
  revision and no re-download needed. Katon confirmed sufficiency in writing
  (Item 1 seam closed) — his six answers and four v0.6 DDL commitments are
  recorded above. Corrections, all mine: the `contract` / `prompts` / `config`
  values are pinned to `e2eba1c` and the verify recipe now says so (`main` has
  since moved to extract v2.3 / validate v1.2); `config` carries **29** keys in a
  real manifest, not 27, because the resume guard compares two of them; and a new
  [what the implementation actually writes](#what-the-implementation-actually-writes)
  section records five additive payload differences plus the fact that
  `spend_snapshot` is never emitted. Found while re-checking the recipe: a
  file-bytes prompt hash is **platform-dependent** (CRLF vs LF), so this fixture's
  `prompts.*` are CRLF-derived and superseded, and the implementation is being
  fixed to normalise to LF — no loader impact, the values are opaque to it. Decision 5 now answers the frame question in
  both directions (`master_build_id` only, `mb-YYYY-MM-DD`, `frame_id` null).
  Added Katon's cross-language canonicalization caveat. Open question 3 (named
  state after a hard kill) still open; he confirmed it does not block him and it
  lands as `events_truncated.jsonl` in **fixture set v2**, alongside a values
  re-cut against a real PR C manifest.
- **v1.1** — 2026-08-11 — **notes only, no fixture bytes changed.** PI resolved
  escalated questions 1, 2 and 4 (`config_hash` exclusions stand; resume under a
  changed `git_sha` is permitted and recorded, now decision 7 + invariant 11;
  `spend_snapshot` is optional, now invariant 12). Question 3 (named state after
  a hard kill) stays open pending Item 3. Katon's six sufficiency questions are
  unaffected and still open.
- **v1** — 2026-08-10 — initial, from spec v0.1 §4, authored at `e2eba1c`.
