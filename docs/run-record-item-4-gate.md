# Run record — item 4, the n≈20 smoke gate

**Owner:** Thomas · **Verifiers:** Nolan (pipeline-side), Katon (DB-side) ·
**Authority:** the 2026-08-07 brief, item 4; amended by the PI's 2026-08-14 and
2026-08-18 letters.

The gate is **one uninterrupted pass** through every leg, at n≈20 with live keys,
before the PI cuts the production window. This file is the record of that pass.
Sections marked **PENDING** are filled during it; everything else is already
verified and dated, so the pass is transcription rather than reconstruction.

**Status: NOT YET RUN.** Blocked on the staging worker URL (§3.5).

---

## 1. What the gate must show

From the brief, in order: submit → stages → ingest to a Neon branch → windowed
publish visible on a staging view **with no manual refresh** → archive to Spaces
→ pull to Drive → checksums verify. Plus four named checks: a byte-identical
regression record on post-stamping `main`, an out-of-window run invisible, an
induced-failure test, and a secrecy grep.

---

## 2. Preconditions — verified before the pass

| # | Precondition | State | Evidence |
|---|---|---|---|
| 2.1 | Droplet reachable, shared `g3o` account | ✅ 08-17 | `g3o-run-01`, `64.23.186.164`, Ubuntu 24.04.4, 150 G free |
| 2.2 | `~/G3O` clean, carries uid stamping (#71) and orchestrator v0.6 (#73) | ✅ 08-17 | `d614404`, `git_dirty: false` — re-verify at gate time, see §6 |
| 2.3 | `~/g3o-api` pinned to the merged v0.6 loader **plus #7** | ✅ 08-18 | `60eb7c4`; `run_contract.py` confirmed to refuse rather than derive |
| 2.4 | Loader importable under the G3O venv | ✅ 08-18 | `ingest.py --help` clean; `build_argv` uses `sys.executable` |
| 2.5 | Dependencies present | ✅ 08-17 | g3o 0.1.0 · boto3 1.43.67 · psycopg 3.3.4 · playwright · openai 2.53.0 |
| 2.6 | DSN is the **branch**, and **unpooled** | ✅ 08-17 | `ep-restless-wildflower-ay6t9k64…/neondb`, `sslmode=require`, no `-pooler` |
| 2.7 | Secrets reach child processes | ✅ 08-18 | `~/.g3o/env` exports all nine; plain source proven to reach `python3` |
| 2.8 | Wave window covers the run | ✅ 08-17 | `wave_id 1`, `Wave 1 - 2026Q3`, `[2026-07-01, 2026-10-01)`, covers today |
| 2.9 | `g3o.frames` holds the run's frame | ✅ 08-17 | `mb-2026-07-30` |
| 2.10 | `--frame-id` is unambiguous | ✅ 08-17 | master carries **exactly one** `master_build_id`: `mb-2026-07-30` |
| 2.11 | Sweeps grain enforced | ✅ 08-17 | `sweeps_institution_run_uq UNIQUE (institution_uid, run_id)` (g3o-api #5) |
| 2.12 | Object store reachable, round trip verified | ✅ 08-18 | bucket `g3o-runs`, sfo3 endpoint, `us-east-1` region accepted; hash matched |
| 2.13 | Staging API serving the branch | ❌ **PENDING** | see §3.5 |

### Dry-run rehearsal, 2026-08-17 — `r20260817T224831Z-98a7`

Not a gate run; a rehearsal of the launch path. 20 institutions drawn across
2,907 strata, 8 stages planned, `outcome: stopped` with `reason: dry_run`.
Manifest spec-§4.1 complete: `run_started_at` round-trips against the minted id,
`operator: thomas`, `hostname: g3o-run-01`, `git_dirty: false`, contract pins
extract **v2.4** / validate **v1.2**, credentials recorded as fingerprints only.
**Secrecy grep over the full run tree returned 0.**

Preflight the same day: both keys present and well-formed, 240 Stage-5 jobs,
13.8 MB, 1 chunk (caps 100 MB / 25,000 requests), `verify_model` correctly
skipped rather than submitting.

---

## 3. The legs

### 3.1 Submit — PENDING

| Field | Value |
|---|---|
| run_id | |
| `--session-id` | *(must be set; an omitted flag records `unattended` silently)* |
| `--frame-id` | `mb-2026-07-30` |
| G3O sha at launch | |
| Started / ended (UTC) | |
| Outcome | |

### 3.2 Stages — PENDING

Stages completed, wall time, any `poll_timeout` (which is **not** a failure — the
batch has not ended), and the final `status` one-liner.

### 3.3 Ingest — PENDING

Loader pinned at `60eb7c4` via `--expect-loader-sha`. Record the loader's **own**
exit code and counts, never a paraphrase: exit 1 means *loaded and committed but
a strict check failed*. Record quarantine counts, and record `COUNTS UNKNOWN`
as such if the loader's output shape moved — that is not zero.

Expect `frame_id_source = 'operator'` on this run. Any other value means the
checkout is not at `60eb7c4`.

### 3.4 Archive — PENDING

Dry first (it deletes the institution tree), then `--apply --destination`.
Record the bucket prefix, `SHA256SUMS`, the ledger, and the post-upload re-hash
verdict.

> **Object-store path verified 2026-08-18, ahead of the pass.** A
> put → read-back → re-hash round trip through `S3ObjectStore` against bucket
> **`g3o-runs`** matched byte for byte, so the credentials work and the
> `us-east-1` default **is** accepted alongside the `sfo3` endpoint —
> `SPACES_REGION` stays unset. `exists` and `list_keys` both answered.
>
> That probe also caught a wrong bucket name in the runbook: every archive
> example named `s3://g3o-archive`, which does not exist. Since credentials are
> not touched until after `archive --apply` has tarred and **deleted** the live
> institution tree, that would have failed mid-pass with the tree already gone
> (recoverable from the local tars, but not a clean pass). Fixed before the gate.
>
> Still unexercised end to end: `archive_run` itself refuses anything without
> Stage-7 output, all eight `.done` markers and the run reports, so the full leg
> cannot run until a real run completes. Its first true execution is this pass.

### 3.5 Publish-verify — BLOCKED

`G3O_API_BASE` is unset **deliberately**. The worker on `api.g3observatory.org`
is the registry preview (`REGISTRY_ONLY=true`, `DEFAULT_WAVE=w000`), which serves
every institution as `not_reviewed` with zero findings by construction and reads
no Neon branch. Pointed at it, this leg would report a perfectly-loaded run
invisible — correct about the API, and silent about the load.

The PI is deploying a third worker from `worker/wrangler.jsonc` (no route, no
custom domain, so it structurally cannot touch the production hostname) with
`DEFAULT_WAVE=w001` and the branch DSN, and will send its `*.workers.dev` URL.
**Do not guess a value: a URL that resolves but serves the wrong wave would pass
this leg while proving nothing.**

### 3.6 Pull to Drive — the PI's act

First on the sprint's agreed drop list. If it trails the pass, say so explicitly
in §7 rather than counting checksums-verified-in-Spaces as the full leg.

---

## 4. The four named checks

### 4.1 Byte-identical regression record — ✅ DONE

Re-cut on `d614404` (post-stamping `main`), 2026-08-17. The delta was predicted
in writing before it was measured, and matched: `+institution_uid`/`+sweep_uid`
on activities and sources, `+institution_uid` on summary. **0 rows changed, 0
columns removed, 0 shared cells changed**, original column order preserved,
across **5 determinism replicates** — one run cannot distinguish "deterministic"
from "landed the same way once". Compared field-wise rather than by file hash:
`csv.writer` emits CRLF on every platform while git stores LF, so a byte
comparison fails on line endings alone on a fresh Linux checkout.

Recorded in `baseline/NOTES.md`. Note that the previous baseline was **already
stale before stamping**: `group_d_salvaged_fields` landed 2026-07-22 and nobody
re-cut in July, so it predated a merged change by twelve days. A regression
record whose baseline predates a merged change is worse than no record, because
it passes.

### 4.2 Out-of-window run invisible — PENDING, method ruled

Wave 1 spans the whole quarter, so no run producible this quarter falls outside
it. **Ruled method (PI, 2026-08-18): roll the window row back on the Neon branch
during the pass, assert hidden, restore.** Branch only — production has no window
cut, so there is nothing there to expose.

```sql
delete from g3o.wave_windows where wave_id = 1;   -- the rollback in the file's header
-- then: publish-verify --expect-hidden
-- then: re-apply sql/004_wave_window_w001.sql (idempotent, on conflict do nothing)
```

**Log the delete and the restore with timestamps.** A window that was briefly
absent is a fact about the pass, and belongs here rather than being reconstructed
from a diff later.

| Event | Timestamp (UTC) | By |
|---|---|---|
| window deleted | | |
| `--expect-hidden` asserted | | |
| window restored | | |
| restore confirmed present | | |

Substituting a `synthetic` run is **not** an acceptable alternative: the
published view is built `where not synthetic` (`schema_core.sql:756`), so such a
run is hidden for two reasons at once and the assertion cannot tell which one did
the work.

### 4.3 Induced failure — PENDING

Kill a stage mid-flight. Must end in a **named failed state**, with the cause in
`events.jsonl`, and **nothing published**. `FAILED` and `INTERRUPTED` both block
ingest.

| Field | Value |
|---|---|
| stage killed / how | |
| final state | |
| cause in `events.jsonl` | |
| confirmed nothing published | |

### 4.4 Secrecy grep — ✅ passed in rehearsal, re-run on the gate run

Grep the full `runs/<id>/` tree for the literal key strings; must return 0.
Returned 0 on `r20260817T224831Z-98a7` (2026-08-17). Credentials appear in the
manifest as `sha256[:8]` fingerprints only.

---

## 5. Notes the PI required in this record

**a. `r20260817T134319Z-3356` stands unamended, and predates `60eb7c4`.** That
run carries `frame_id_source = 'manifest'`. The pre-#7 loader derived it from the
manifest's `master_build_id`, because `resolve_frame_id` read
`frame.get("frame_id") or frame.get("master_build_id")` — and on that code **no
argument yields `'operator'`**: a matching `--frame-id` still records `manifest`,
and a differing one is a hard error. Ruled to stand rather than be corrected, for
three reasons: it is on the rehearsal branch and never becomes public;
`in_frame = false` would be *untrue*, since the run is in frame, and buying
tidiness with a false value is a bad trade in the column set that exists to be
trusted afterwards; and hand-editing `frame_id_source` is precisely the failure
that column exists to detect. If publish-verify samples it, that is a correct
sample of a rehearsal database.

**b. The staging view will show 3 institutions and 0 findings, and that is
correct.** An n=3 smoke from another lane is loaded `synthetic = false`,
`in_frame = true`, `publication_hold = null`, inside wave 1 — inert until a
staging worker points at wave 1, which §3.5 does. It resolves to 3 institutions,
`NO_EVIDENCE_FOUND` ×3, 0 findings, 2 evidence rows. **Not a publish failure**,
but the correct rendering of a thin run. Recorded so the gate screenshots are
unambiguous a month from now.

**c. Gates a–c passed on 2026-08-18 against the pre-#7 fixture.** Another lane
ran the two-run synthetic validation on the branch and all three passed, but the
fixture still minted the retired `G3O-S-w000-<tail>` form that #7 corrects, and
the evidence file records that as a standing caveat. The PI is deciding whether
it is re-run against the corrected fixture before this gate or carries forward as
a named caveat. **Not this lane's re-run** — recorded so a green gate this record
did not produce is not mistaken for one it did.

---

## 6. Code under test

| Component | Pin | Note |
|---|---|---|
| `G3O` | **TBD at gate time** | Must be a **merged** commit. This repo squash-merges, so a branch commit never survives — a manifest citing `code.git_sha` from an unmerged branch cites a commit the project does not contain. |
| `g3o-api` loader | `60eb7c4` | Passed as `--expect-loader-sha`. `main` has since moved to `8be1c40` (PR #2, `verify_api.py` only); the loader pin is unaffected. |
| `verify_api.py` | `8be1c40` | Gate condition 9. It was passing vacuously before that commit, so run it from `8be1c40` rather than an older checkout. |
| Contract | extract v2.4 / validate v1.2 | As pinned in the rehearsal manifest. |

**The run-id collision guard is not present.** Retired by SD-004 (2026-08-16),
removed in PR #74, parked at `origin/park/run-id-collision-gate`. The residual
exposure it named remains: a hand-passed `--run-id` naming an already-loaded run
survives submit, spends the compute, and fails at the `g3o.runs` primary key
during ingest. **Let the id mint** unless deliberately resuming.

---

## 7. Outcome

**PENDING.** Record here: the overall verdict, any leg that was dropped or
trailed (and why), and anything that failed and was retried.

Green means **one uninterrupted pass**. A leg that failed and was re-run is not a
green pass — record both attempts.

## 8. Sign-off

| Role | Who | Verdict | Date |
|---|---|---|---|
| Pipeline-side | Nolan | | |
| DB-side | Katon | | |
| Filed by | Thomas | | |
