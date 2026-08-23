# Runbook — running a sweep on the droplet

One page. Everything is `~/venv/bin/python -m g3o.run.orchestrate <verb>`; the
pipeline CLI (`~/venv/bin/g3o …`) is unchanged and is not used here except for
the preflight, Stage 7 and the reports.

> **Every command names `~/venv/bin/` explicitly, and that is not stylistic.**
> Measured on the droplet 2026-08-19: `PATH` is the stock Ubuntu one, nothing in
> `~/.bashrc` activates a venv, and so **neither `g3o` nor `python` resolves** —
> only `python3`, which is the system interpreter. A bare `g3o presweep` or
> `python -m g3o.run.orchestrate` dies with *command not found*; a bare
> `python3 -m g3o.run.orchestrate` finds an interpreter with no `g3o` in it. Both
> failures are loud, which is the good case. The bad case is a **second working
> venv**, and the box had one: `~/G3O/.venv`, created 2026-08-08, complete, and
> carrying different dependency versions from `~/venv` (openai 2.53.0 against
> 2.54.0, boto3 1.43.67 against 1.43.72). Both ran the same source, so
> *"it ran under some interpreter"* was not evidence that it ran under the pinned
> one. **It was removed on PI ruling 2026-08-19**, and its package set is
> recorded at `~/G3O-dotvenv-freeze-20260819.txt` on the box because two
> completed runs name it in their `_orchestrator/submit.json`. There is now
> exactly one venv under `$HOME`. **Keep it that way** — and if you ever build a
> second for any reason, nothing in this file will notice, which is why every
> command below names its interpreter rather than trusting the environment.

**Exit codes, every verb:** `0` green · `1` it ran and is not green · `2` it
refused or could not run. Scripts should branch on 2 vs 1: *did not happen* vs
*look at the result*.

---

## The one-liners

```bash
# PREFLIGHT — ALWAYS FIRST. No submits, no state writes. Non-zero = do not submit.
~/venv/bin/g3o presweep --preflight --master-csv "$G3O_MASTER_CSV" --sample-size 20 --seed 22294 \
    --runs-dir "$G3O_RUNS_DIR" \
    || { echo "PREFLIGHT FAILED — not submitting"; exit 2; }

# SUBMIT — starts the run and returns; closing this shell changes nothing.
~/venv/bin/python -m g3o.run.orchestrate submit --config run-config.json --execute --detach \
    --session-id "$G3O_SESSION_ID"

# STATUS — one line, any time, from any shell on the box.
~/venv/bin/python -m g3o.run.orchestrate status --latest

# RESUME — not a separate verb. Same command, same run id: it rejoins.
~/venv/bin/python -m g3o.run.orchestrate submit --config run-config.json --execute --detach \
    --session-id "$G3O_SESSION_ID" \
    --run-id r20260813T101500Z-9c2f

# WATCH — status every minute until it stops changing.
watch -n 60 ~/venv/bin/python -m g3o.run.orchestrate status --latest
```

`submit` prints the minted run id **first**, before the run does anything, so a
detached run can be monitored and resumed while it is still in flight. Copy it.

**Run the preflight and read its exit code.** It is the only check that verifies
the keys before spend: it computes `keys_ok` (`g3o/run/preflight.py`), and the
sole consumer is the CLI's own exit status — **`submit` does not gate on it.**
`submit` refuses on the cost ceiling and on nothing else, so a keyless run passes
submit and dies at discovery, costing you minutes and leaving a partial run
record. It is not a silent-mock hazard — `serper_client` refuses to return mock
results while `--execute` is active, and the presweep refuses too — but the
guard is late, and the preflight is the one that is early. It also prints the
planned sample and the projected Batch spend, which is where the `--cost-ceiling`
figure comes from. Gating `submit` on `keys_ok` is a follow-up, after the
window.

Measured on the droplet 2026-08-19 at `da89d94`, n=20 / seed 22294: exit **0**,
`keys_ok: true`, both keys `well_formed`, and `est_openai_batch_total_usd`
**$0.14** (of which `extract` is $0.115). **Serper is not priced by the
preflight** and there is no credit count in its output — `cost_preview.note`
gives the measured rate instead (1.84 credits/institution under
`discovery_mode='chain'`, the default; 8.52 under `legacy`), because the
USD-per-credit rate is an unresolved input. At n=20 that is ≈37 credits. Read
`stage5_projection.n_chunks` too: it chunks on bytes and request count, **not on
tokens**, so a projection of 4.33 M input tokens still reports one chunk.

**Pass `--session-id` on every run you care about.** It is the join key from a
published database row back to the session that produced it (spec §4.2), and it
is not recoverable afterwards — omit it and the manifest records the literal
string `unattended`, which is a valid value and therefore fails silently. The
precedence is the flag, then `$G3O_SESSION_ID`, then `unattended`; the flag is
written out above so the omission is visible rather than implied.

---

## Before the first run: the box

```bash
# 1. Code, pinned.
git clone https://github.com/simonepaciphd/G3O.git ~/G3O
git clone https://github.com/simonepaciphd/g3o-api.git ~/g3o-api
cd ~/G3O && git checkout <sha>
cd ~/g3o-api && git checkout <sha>         # the ingest loader is pinned separately

# 2. The venv. It is `~/venv`, OUTSIDE the checkout, and there is one reason:
#    the interpreter that runs the sweep must survive the git operations done to
#    the tree it runs. `git checkout <sha>` to re-pin, or `git clean -xdf` to
#    recover a confused checkout, both leave ~/venv untouched; a venv inside
#    ~/G3O does not survive the second one.
#
#    A bare `pip install -e .` is what PEP 668 refuses here: the box's system
#    python3 carries /usr/lib/python3.12/EXTERNALLY-MANAGED, so that install
#    exits with `externally-managed-environment` and nothing is installed.
python3 -m venv ~/venv
~/venv/bin/pip install --upgrade pip
cd ~/G3O && ~/venv/bin/pip install -e .

# 3. Two optional dependencies, deliberately not declared in pyproject.toml:
#    boto3 for the archive leg, psycopg for the loader.
#
#    psycopg is here for a structural reason, not a G3O one. NOTHING in this
#    repo imports it -- the run-id collision guard that once did was retired by
#    SD-004. It is needed because build_argv launches
#    g3o-api/scripts/ingest.py with `python or sys.executable` and no CLI flag
#    exposes that parameter, so the loader always runs under THIS interpreter
#    and its dependency lands in THIS venv. See the seam note below.
~/venv/bin/pip install boto3 "psycopg[binary]"
~/venv/bin/python -c "import psycopg, boto3"    # cheap proof; exit 0 or fix it
#    Do NOT verify psycopg by running `ingest.py --help`. Every psycopg import
#    in that script is deliberately lazy ("so that --help and the argument
#    guards work on a machine without the driver installed"), so --help exits 0
#    on an environment that will fail at connect time. Use the import check
#    above, or g3o-api's own scripts/dbcheck.py.

# 4. The browser Playwright drives. NOT --with-deps: that shells out to sudo,
#    and the `g3o` account is not meant to need root to install a browser.
~/venv/bin/playwright install chromium

# 5. The frame. 171 MB, in NO repo, and nothing downloads it for you: the master
#    is the read-only canonical build in the PI's Drive tree, so it is pushed to
#    the box. NOTE THE TWO MACHINES -- the mkdir is on the box and must happen
#    first, because scp will not create the destination directory.
mkdir -p ~/data ~/runs                              # ON THE BOX
                                                    # ON THE PI'S MACHINE:
# scp "H:/My Drive/Research/G3O/inputs/G3O_Institution_Master/data_final/master_institutions.csv" \
#     g3o-run-01:~/data/
sha256sum ~/data/master_institutions.csv            # ON THE BOX; must match Drive

# 6. Secrets, in the environment. Never on a command line: an argument lands in
#    shell history and in every `ps` listing on the box.
#
#    On the provisioned droplet these already exist in ~/.g3o/env (mode 600),
#    and every line carries `export`. KEEP it -- see the note below.
#
#    EVERY VALUE BELOW IS QUOTED, and the template is the only place that is
#    true: single quotes on the literals, double quotes where $HOME must still
#    expand. The DSN is why. It ends
#    `?sslmode=require&channel_binding=require`, and unquoted, bash splits at
#    the `&`: the first half runs in the background, the assignment "succeeds",
#    and DATABASE_URL is never set -- with no error and no output. Do not
#    unquote a value here on the grounds that it looks harmless.
mkdir -p ~/.g3o
cat >> ~/.g3o/env <<'EOF'
export OPENAI_API_KEY='...'
export SERPER_API_KEY='...'
export DATABASE_URL='...'          # the NEON BRANCH dsn, not production, and
                                   # the UNPOOLED string: the loader runs one
                                   # long transaction, which a pooler in
                                   # transaction mode breaks. THE QUOTES ARE
                                   # LOAD-BEARING -- see the `&` note above.
export SPACES_KEY='...'
export SPACES_SECRET='...'
export SPACES_ENDPOINT='https://sfo3.digitaloceanspaces.com'
export SPACES_BUCKET='...'
# SPACES_REGION is optional; g3o.run.orchestrate.objectstore defaults it to
# us-east-1. Verified 2026-08-18 against the sfo3 endpoint: a put/read/re-hash
# round trip on bucket g3o-runs matched byte for byte, so leave it unset.
#
# The REGION is confirmed independently, 2026-08-19, and needs no credentials:
# an anonymous GET of the bucket host answers 403 AccessDenied at sfo3 (the
# bucket is there; we simply may not list it) and 404 NoSuchBucket at fra1,
# nyc3 and ams3. A bucket lives in exactly one region, so that split settles it:
#   for r in sfo3 fra1 nyc3 ams3; do
#       curl -s -o /dev/null -w "$r %{http_code}\n" https://g3o-runs.$r.digitaloceanspaces.com/
#   done
export G3O_API_REPO="$HOME/g3o-api"
export G3O_API_BASE='...'          # the staging worker that reads the NEON
                                   # BRANCH, with REGISTRY_ONLY dropped and
                                   # DEFAULT_WAVE=w001. The production worker
                                   # is REGISTRY_ONLY and serves zero findings,
                                   # so publish-verify against it reports a run
                                   # invisible however well the load went.
export G3O_RUNS_DIR="$HOME/runs"
export G3O_MASTER_CSV="$HOME/data/master_institutions.csv"
EOF
chmod 600 ~/.g3o/env

# G3O_OPERATOR is deliberately NOT in that file. It is the manifest's
# accountability field, `telemetry.operator()` falls back to the OS user, and
# the droplet's `g3o` account is shared -- so a name in a file we both source
# would stamp the other person's runs. Same for G3O_SESSION_ID: it identifies
# a session, and a shared file cannot. Both go per session:
export G3O_OPERATOR=thomas
export G3O_SESSION_ID=20260817-claude-g3o-endgame   # yours, not this example
```

> **`G3O_MASTER_CSV` is read by no code, and it is in the file on purpose.**
> Grep the repo and you will find zero hits — the master reaches the pipeline
> only as `--master-csv` (required on `g3o presweep`, `g3o/cli.py:1180`) or as
> the run config's `master_csv` field. The variable exists so **this runbook's
> own one-liners** have one place to name the path, and so a re-pointed master is
> a one-line edit rather than a search through commands. It is a shell
> convenience, not configuration the code consumes. Stated here so that the next
> reader who greps for it does not conclude the runbook is broken — and so that
> nobody sets it and expects a run to pick it up.

> **Every line must keep its `export`.** Until 2026-08-18 the file assigned
> without exporting, so a plain `source` populated the *shell* and no child
> process — and `launch()`, the orchestrator and the loader (a subprocess under
> the same interpreter) all read `os.environ`. A run sourced the documented way
> started with no keys, no DSN and no Spaces credentials. Fixed at the source on
> the PI's instruction, rather than by requiring every invocation to remember
> `set -a`: a convention that has to be remembered fails the first time someone
> is tired, at 2 a.m., on the one run that costs money.
>
> ```bash
> . ~/.g3o/env                                                          # plain source is enough
> ~/venv/bin/python -c "import os; assert os.environ['DATABASE_URL']"   # cheap proof
> ```
>
> Confirmed on the box 2026-08-19: all nine lines carry `export`, the seven
> secret values are single-quoted, and the proof above passes.
>
> Run that proof after any edit to the file, and after a rebuild. Two mechanics
> if you ever have to edit it: `~/.g3o/` is **root-owned** while `env` inside it
> belongs to `g3o`, so the file is writable but **nothing can create a sibling
> next to it** — `sed -i` fails, because it stages a temp file in the target's
> directory and renames. Stage in `$HOME` and then `cat staged > ~/.g3o/env`,
> which truncates the existing inode and needs no directory permission. Backups
> go to `$HOME` for the same reason.

### The run config

A JSON object of `PresweepConfig` fields. It is the record of what was
submitted, and it is copied into `runs/<run-id>/_orchestrator/submit_config.json`
next to the manifest it produced. An unknown key is refused, not ignored.
`scripts/orchestrator/run-config.example.json` is a starting point:

```json
{
  "run_id": "",
  "runs_dir": "/home/g3o/runs",
  "master_csv": "/home/g3o/data/master_institutions.csv",
  "sample_size": 20,
  "seed": 22294,
  "dry_run": true,
  "stop_after": "validate",
  "filter_mode": "shadow",
  "max_workers": 4
}
```

`--sample-size`, `--seed`, `--stop-after`, `--model`, `--max-workers`,
`--filter-mode`, `--master-csv`, `--runs-dir` and `--execute` override the file
from the command line. Everything else lives in the file.

### Dry run first

```bash
~/venv/bin/python -m g3o.run.orchestrate submit --config run-config.json        # no --execute
```

A dry run plans and spends nothing, and reports as `stopped`, never `completed`
— "it finished" must not read as "it gathered data".

---

## While it runs

```
$ ~/venv/bin/python -m g3o.run.orchestrate status --latest
r20260813T101500Z-9c2f  RUNNING      stages=5/8  in-flight=extract  chunks=2  pid=8123/alive  last=chunk_submitted@2026-08-13T14:22:07Z(seq 41)
```

| Field | Read it as |
|---|---|
| `stages=5/8` | `.done` markers in `_state/` — what a resume would skip |
| `in-flight=extract` | a stage that started and has not reported completion |
| `chunks=2` | batches submitted and not yet fetched |
| `pid=8123/alive` | the supervised process. `dead` ⇒ the state is `INTERRUPTED` |
| `last=…` | the last event in `events.jsonl` |

> **Killing a run orphans its in-flight OpenAI batch, and nothing reaps it.**
> Measured 2026-08-18: `discovery_general` finished in 1.9 s at n=2, so a kill
> aimed at stage 1 landed in `classify_official_site` *after* a batch had been
> submitted. That batch kept running server-side and billed until cancelled by
> hand. Stage 1 is fast at any small n, so treat every kill as leaving a live
> batch. Read the `batch_id` from the last `chunk_submitted` event and cancel it:
>
> ```bash
> tail -3 $G3O_RUNS_DIR/$RUN/events.jsonl        # find the batch_id
> ~/venv/bin/python -c "import os; from openai import OpenAI; print(OpenAI(api_key=os.environ['OPENAI_API_KEY']).batches.cancel('batch_...').status)"
> ```
>
> Never cancel a batch belonging to a run you intend to **resume** — re-invoking
> rejoins polling, and a `poll_timeout` is not a failure.

**States:** `LAUNCHING` · `RUNNING` · `COMPLETED` · `STOPPED` (dry run, or
`--stop-after` short of the end) · `FAILED` (the run said so) · `INTERRUPTED`
(the process is gone and the run never got to say so — killed, or the box died).
`FAILED` and `INTERRUPTED` both block ingest.

A `poll_timeout` is **not** a failure: the batch has not ended. Re-invoke to
rejoin polling; never cancel a batch that is still in progress.

Full detail: `status --json`, `runs/<id>/events.jsonl`,
`runs/<id>/_orchestrator/submit.log`.

---

## After it completes

```bash
RUN=r20260813T101500Z-9c2f

# 1. Stage 7 + the run-level reports. Archival refuses without them.
~/venv/bin/python -m g3o persist --run-dir $G3O_RUNS_DIR/$RUN --run-id $RUN
~/venv/bin/python -m g3o presweep-report --run-dir $G3O_RUNS_DIR/$RUN

# 2. INGEST — refuses anything but a completed run. Loader exit code passed through.
#    --frame-id is the master build this run sampled from; there is no --wave-id
#    any more (v0.6 derives wave membership from the database, not from here).
~/venv/bin/python -m g3o.run.orchestrate ingest --run-id $RUN --frame-id mb-2026-07-30 \
    --expect-loader-sha <the pinned g3o-api sha>

# 3. ARCHIVE — dry first (it deletes the institution tree), then apply + upload.
~/venv/bin/python -m g3o.run.orchestrate archive --run-id $RUN
~/venv/bin/python -m g3o.run.orchestrate archive --run-id $RUN --apply \
    --destination s3://g3o-runs/runs

# 4. PUBLISH-VERIFY — read-only. Asks the API; flips nothing.
~/venv/bin/python -m g3o.run.orchestrate publish-verify --run-id $RUN
```

**Ingest** reports the loader's own verdict, never a paraphrase of it. Exit 1
means *loaded and committed but a strict check failed* — the rows and the
quarantine CSVs are in the database; read
`runs/<id>/_orchestrator/ingest_reports/`. If the report says **COUNTS
UNKNOWN**, the loader's output shape changed and the numbers are unavailable —
that is not zero. Extra loader flags pass through: `--loader-arg --synthetic`.

Two flags to know about and not use on a real run. `--loader-arg --no-refresh`
skips the materialized-view refresh: the facts land and the site keeps serving
stale aggregates, which is exactly the "publishes with no manual refresh"
property the smoke gate asserts. `--loader-arg --synthetic` loads a run as
queryable-but-never-published. Neither belongs on a gate run.

**Archive** streams every uploaded object back out of the bucket and re-hashes
it. `SHA256SUMS` and `archive_ledger.jsonl` land at the root of the run's prefix;
the ledger is plain text and lists the files inside each tar, so the archive can
be browsed without extracting it.

**Publish-verify** checks against an expectation: a completed run should be
visible, a failed one should not. `--expect-hidden` asserts invisibility (an
out-of-window run). Making a run visible is the wave window the PI cuts — this
verb never does it. Since uid stamping (#71) it joins on `institution_uid` and
returns a real verdict; a run planned before stamping carries no uid column and
still reports `not_verifiable`, because the API is keyed by the uid and this leg
will not guess a join.

### Restore one shard

```bash
tar -xf $G3O_RUNS_DIR/$RUN/archive/institutions/<shard>.tar -C $G3O_RUNS_DIR/$RUN/institutions/
```

---

## On the PI's machine: pull to Drive

The pull is the PI's act, by design. Standalone — needs only Python and boto3,
no G3O checkout:

```powershell
pip install boto3
$env:SPACES_KEY="..."; $env:SPACES_SECRET="..."
$env:SPACES_ENDPOINT="https://sfo3.digitaloceanspaces.com"

python scripts\orchestrator\pull_run_archive.py `
    --run-id r20260813T101500Z-9c2f `
    --destination s3://g3o-runs/runs `
    --dest "G:\My Drive\G3O\run-archive"

# Re-verify a copy already in Drive, downloading nothing:
python scripts\orchestrator\pull_run_archive.py --run-id r2026... `
    --dest "G:\My Drive\G3O\run-archive" --verify-only
```

It re-hashes every file **at the Drive path** against the `SHA256SUMS` that
travelled with the bundle. The droplet already proved bucket == disk; this proves
Drive == bucket, which is where a sync client can quietly truncate a file. Any
machine with coreutils can do the same check by hand:

```bash
cd "<dest>/<run-id>" && sha256sum -c SHA256SUMS
```

---

## systemd, if you want restart-on-boot

`--detach` already survives disconnection (a new session, no controlling
terminal — what `nohup` does). Use a unit only if the run should survive a
reboot:

```ini
# /etc/systemd/system/g3o-run@.service   →  systemctl start g3o-run@r20260813T101500Z-9c2f
[Unit]
Description=G3O sweep %i
[Service]
Type=simple
User=g3o
WorkingDirectory=/home/g3o/G3O
Environment=G3O_OPERATOR=thomas
Environment=G3O_SESSION_ID=set-this-per-run
ExecStart=/bin/bash -c '. /home/g3o/.g3o/env && exec /home/g3o/venv/bin/python \
    -m g3o.run.orchestrate submit --config /home/g3o/run-config.json \
    --execute --run-id %i --session-id "$G3O_SESSION_ID"'
Restart=no
[Install]
WantedBy=multi-user.target
```

`Restart=no` is deliberate: a run that failed must be looked at, not restarted
into the same wall. Resume is a decision, and it is one command.

> **There is no `EnvironmentFile=` in that unit, and removing it is the fix, not
> an omission.** `EnvironmentFile=` is **not** a shell, and it does not honour an
> `export ` prefix — so now that every line of `~/.g3o/env` carries `export` (the
> 2026-08-18 fix, which is right for the shell path), the directive loads
> **nothing**. Measured on the box 2026-08-19 with a transient
> `systemd-run --user` unit over a probe file of the same shape:
>
> | Line in the file | What the unit saw |
> |---|---|
> | `export PROBE_EXPORTED='v'` | **unset** |
> | `PROBE_PLAIN='v'` | `v` — quotes stripped |
> | `export PROBE_HOME="$HOME/runs"` | **unset** |
>
> So a run started with `systemctl start g3o-run@<id>` and an `EnvironmentFile=`
> would begin with no keys, no DSN and no Spaces credentials — the exact failure
> the `export` fix closed on the shell path, reappearing on this one, and silent
> in the same way. Sourcing the file in the `ExecStart` shell is what makes the
> two paths read the same file the same way: `.` honours `export`, strips the
> quotes, and expands `$HOME`. `G3O_OPERATOR` and `G3O_SESSION_ID` stay on
> `Environment=` lines for the reason they are not in the shared file at all —
> they identify a person and a session, and the unit is per run.
>
> **The replacement was run, not reasoned.** The same `. ~/.g3o/env && exec
> ~/venv/bin/python …` shape, under a transient `systemd-run --user` unit against
> the real `~/.g3o/env` on 2026-08-19: **all eleven** variables present
> (the seven secrets, `G3O_API_REPO`, `G3O_RUNS_DIR`, and the two `Environment=`
> ones), `G3O_RUNS_DIR` expanded to `/home/g3o/runs`, and `g3o`, `psycopg` and
> `boto3` all importable in the unit's interpreter.
>
> Note the quoting in that unit is doubly load-bearing: single quotes around the
> whole `bash -c` script keep systemd from splitting it, and `"$G3O_SESSION_ID"`
> stays quoted inside so an unset value fails visibly rather than silently
> dropping the argument.

The same mechanics apply to `EnvironmentFile=` anywhere else you meet it: it
parses `KEY=value` directly, strips quotes, and neither honours `export ` nor
expands `$HOME`. A line written in shell form is invisible or literal to it. If
you ever do point it at a file, state absolute paths with `Environment=` rather
than relying on expansion — and read the table above before assuming a secret
arrived.

---

## Decommission

One command each. Do this only after the archive has been pulled to Drive **and
verified there** — the bucket is not the last copy until it is.

```bash
# 1. Confirm the archive is on the PI's machine and verifies (from that machine):
python scripts/orchestrator/pull_run_archive.py --run-id $RUN --dest "<drive>" --verify-only

# 2. Empty and delete the Spaces bucket.
s3cmd del --recursive --force s3://g3o-runs && s3cmd rb s3://g3o-runs

# 3. Destroy the droplet.
doctl compute droplet delete <droplet-id> --force

# 4. Revoke what the box held: the Spaces key pair, and the API keys it spent.
doctl compute cdn ... # n/a — do the key revocations in the DO and OpenAI consoles.
```

Step 4 is not optional. The droplet held live API keys and a database DSN; that
exposure is accepted and on the record for the duration of the run, and it ends
when the run does.

---

## Where things are

```
runs/<run-id>/
  manifest.json                  run identity, config, hashes, key fingerprints
  events.jsonl                   the run's own record of what it did
  _state/                        recovery: chunk plans + .done markers
  _attrition.jsonl               drops and degradations
  final/                         Stage-7 CSVs
  archive/institutions/*.tar     after `archive --apply`
  _orchestrator/
    submit.json  submit.log      the supervised process, and its output
    submit_config.json           what was submitted
    ingest.json  ingest.log      the loader's verdict, exit code, counts
    ingest_reports/              quarantine CSVs
    archive.json  publish.json   leg records
    bundle/SHA256SUMS            checksums for the uploaded bundle
    bundle/archive_ledger.jsonl  plain-text inventory, tar members included
```

## Known seams

- **Publish-verify pointed at the wrong database returns `pass`. It is a FALSE
  GREEN, not a false negative.** This entry said the opposite until 2026-08-20;
  so did two other documents. Corrected against the code and a live measurement.
  `visible` is `(code == 200)` and nothing else is consulted
  (`publish.py:275`); the verdict is `pass` iff
  `expected and n_visible == len(checks)` (`:295`); and `waves_seen` and
  `aggregate` are recorded on the result but never enter the verdict (`:328`,
  `:330`). A 200 proves only **frame membership** — the rollup is a `left join`
  and `evidence_status` coalesces to `not_reviewed`
  (`g3o-api worker/src/index.js:637-663`) — so the leg never looks at `findings`
  at all. And because `api.g3observatory.org`'s wave-0 frame **is**
  `mb-2026-07-30`, every uid a run sampled is already in it, every check answers
  200, and the leg prints *"all N sampled institution(s) are visible, as
  expected"* about a database that has never seen the run. Ruling R1 sharpens
  this: with the full registry as the denominator, frame membership stops
  discriminating a loaded run from an empty one. **A false negative gets
  investigated; a false green closes the leg and the run is declared verified.**
  Until the leg asserts the pinned wave *and* the findings, the only trustworthy
  confirmation that a run loaded is DB-side — the shape the Item-4 record uses:
  `v_wave_institution_facts` and the `mv_institution_rollup` join, counted for
  the run.
- **Publish-verify calls `/aggregate`, which does not exist.** `publish.py:280`
  requests the singular form; the contract §3 and the Worker both serve
  `/aggregates`, and the singular measures HTTP 404 `no_such_endpoint`. The
  getter treats a non-200 as data, so nothing raises and the 404 is stored in a
  field the verdict never reads. Fixing the path alone changes no verdict.
- **The ingest leg runs g3o-api's loader under G3O's interpreter.**
  `build_argv` accepts a `python` parameter but no CLI flag reaches it, so the
  loader is always launched with `sys.executable` -- which is why
  `psycopg[binary]` has to be installed into this repo's venv even though no G3O
  module imports it. That crossing is what let an unrelated deletion of this
  venv break the ingest leg mid-gate on 2026-08-19. `g3o-api` now declares and
  owns `psycopg` itself (`g3o-api/requirements.txt`, PI ruling 2026-08-20), so
  the fix is to plumb a `--loader-python` flag through to `build_argv` and point
  it at `~/g3o-api/.venv/bin/python`, after which this repo can drop psycopg
  entirely. Until that lands, both venvs need it and this one is the one that is
  load-bearing.
- **`--frame-id` is operator-supplied, and unvalidated here.** The manifest's
  `frame` block is null on every run the pipeline emits today, so the master
  build is named on the command line and the loader records it as
  `frame_id_source = 'operator'`. A typo is not caught by this orchestrator.
  When stamping populates the block, that flips to `'manifest'` and the flag
  becomes redundant.
- **Nothing checks that a `--run-id` is unused.** The guard that would have
  was retired rather than deferred (SD-004, 2026-08-16): minted ids are
  `r<YYYYMMDD>T<HHMMSS>Z-<4hex>` and the orchestrator is the only sanctioned
  launch path, so a collision is unreachable through any supported route. The
  residual exposure is a **hand-passed `--run-id`** naming a run already loaded:
  it survives submit, spends the compute, and then fails at the `g3o.runs`
  primary key during ingest. Omit `--run-id` and let it mint unless you are
  deliberately resuming.
- **`spend_snapshot` events are not emitted** (the sprint's agreed droppable);
  their absence means nothing, by fixture loader invariant 12. Reopened after
  the window: a run that cannot say what it spent is a poor record.
- **Concurrent same-process launches must agree on `dry_run`.** Serper live mode
  is a module global, so a dry run can flip a live run onto the mock path. See
  `docs/operations.md`.
