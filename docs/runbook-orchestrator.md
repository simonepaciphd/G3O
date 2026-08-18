# Runbook — running a sweep on the droplet

One page. Everything is `python -m g3o.run.orchestrate <verb>`; the pipeline CLI
(`g3o …`) is unchanged and is not used here except for Stage 7 and the reports.

**Exit codes, every verb:** `0` green · `1` it ran and is not green · `2` it
refused or could not run. Scripts should branch on 2 vs 1: *did not happen* vs
*look at the result*.

---

## The one-liners

```bash
# PREFLIGHT — ALWAYS FIRST. No submits, no state writes. Non-zero = do not submit.
g3o presweep --preflight --master-csv ~/data/master_institutions.csv --sample-size 20 --seed 22294 \
    --runs-dir "$G3O_RUNS_DIR" \
    || { echo "PREFLIGHT FAILED — not submitting"; exit 2; }

# SUBMIT — starts the run and returns; closing this shell changes nothing.
python -m g3o.run.orchestrate submit --config run-config.json --execute --detach \
    --session-id "$G3O_SESSION_ID"

# STATUS — one line, any time, from any shell on the box.
python -m g3o.run.orchestrate status --latest

# RESUME — not a separate verb. Same command, same run id: it rejoins.
python -m g3o.run.orchestrate submit --config run-config.json --execute --detach \
    --session-id "$G3O_SESSION_ID" \
    --run-id r20260813T101500Z-9c2f

# WATCH — status every minute until it stops changing.
watch -n 60 python -m g3o.run.orchestrate status --latest
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
cd ~/G3O && git checkout <sha> && pip install -e . && playwright install chromium
cd ~/g3o-api && git checkout <sha>         # the ingest loader is pinned separately

# 2. Two optional dependencies, deliberately not declared in pyproject.toml:
#    boto3 for the archive leg, psycopg for the loader. Both are needed on the
#    droplet and nowhere else. psycopg is not optional in practice: the ingest
#    leg runs g3o-api/scripts/ingest.py under THIS interpreter (build_argv uses
#    sys.executable) and that script imports psycopg at module scope, so without
#    it the ingest leg cannot start.
pip install boto3 "psycopg[binary]"

# 3. Secrets, in the environment. Never on a command line: an argument lands in
#    shell history and in every `ps` listing on the box.
#
#    On the provisioned droplet these already exist in ~/.g3o/env (mode 600),
#    and they are exported. KEEP the `export` -- see the note below. Values are
#    quoted; bash strips the quotes, so read the file with the shell rather than
#    with a naive line parser.
mkdir -p ~/.g3o
cat >> ~/.g3o/env <<'EOF'
export OPENAI_API_KEY=...
export SERPER_API_KEY=...
export DATABASE_URL=...            # the NEON BRANCH dsn, not production, and
                                   # the UNPOOLED string: the loader runs one
                                   # long transaction, which a pooler in
                                   # transaction mode breaks.
export SPACES_KEY=...
export SPACES_SECRET=...
export SPACES_ENDPOINT=https://sfo3.digitaloceanspaces.com
export SPACES_BUCKET=...
# SPACES_REGION is optional; g3o.run.orchestrate.objectstore defaults it to
# us-east-1. Verified 2026-08-18 against the sfo3 endpoint: a put/read/re-hash
# round trip on bucket g3o-runs matched byte for byte, so leave it unset.
export G3O_API_REPO=$HOME/g3o-api
export G3O_API_BASE=...            # the staging worker that reads the NEON
                                   # BRANCH, with REGISTRY_ONLY dropped and
                                   # DEFAULT_WAVE=w001. The production worker
                                   # is REGISTRY_ONLY and serves zero findings,
                                   # so publish-verify against it reports a run
                                   # invisible however well the load went.
export G3O_RUNS_DIR=$HOME/runs
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
> . ~/.g3o/env                                                # plain source is enough
> python3 -c "import os; assert os.environ['DATABASE_URL']"   # cheap proof
> ```
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
python -m g3o.run.orchestrate submit --config run-config.json        # no --execute
```

A dry run plans and spends nothing, and reports as `stopped`, never `completed`
— "it finished" must not read as "it gathered data".

---

## While it runs

```
$ python -m g3o.run.orchestrate status --latest
r20260813T101500Z-9c2f  RUNNING      stages=5/8  in-flight=extract  chunks=2  pid=8123/alive  last=chunk_submitted@2026-08-13T14:22:07Z(seq 41)
```

| Field | Read it as |
|---|---|
| `stages=5/8` | `.done` markers in `_state/` — what a resume would skip |
| `in-flight=extract` | a stage that started and has not reported completion |
| `chunks=2` | batches submitted and not yet fetched |
| `pid=8123/alive` | the supervised process. `dead` ⇒ the state is `INTERRUPTED` |
| `last=…` | the last event in `events.jsonl` |

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
python -m g3o persist --run-dir $G3O_RUNS_DIR/$RUN --run-id $RUN
python -m g3o presweep-report --run-dir $G3O_RUNS_DIR/$RUN

# 2. INGEST — refuses anything but a completed run. Loader exit code passed through.
#    --frame-id is the master build this run sampled from; there is no --wave-id
#    any more (v0.6 derives wave membership from the database, not from here).
python -m g3o.run.orchestrate ingest --run-id $RUN --frame-id mb-2026-07-30 \
    --expect-loader-sha <the pinned g3o-api sha>

# 3. ARCHIVE — dry first (it deletes the institution tree), then apply + upload.
python -m g3o.run.orchestrate archive --run-id $RUN
python -m g3o.run.orchestrate archive --run-id $RUN --apply \
    --destination s3://g3o-runs/runs

# 4. PUBLISH-VERIFY — read-only. Asks the API; flips nothing.
python -m g3o.run.orchestrate publish-verify --run-id $RUN
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
EnvironmentFile=/home/g3o/.g3o/env
WorkingDirectory=/home/g3o/G3O
Environment=G3O_OPERATOR=thomas
Environment=G3O_SESSION_ID=set-this-per-run
ExecStart=/home/g3o/G3O/.venv/bin/python -m g3o.run.orchestrate submit \
    --config /home/g3o/run-config.json --execute --run-id %i \
    --session-id ${G3O_SESSION_ID}
Restart=no
[Install]
WantedBy=multi-user.target
```

`Restart=no` is deliberate: a run that failed must be looked at, not restarted
into the same wall. Resume is a decision, and it is one command.

Two things about `EnvironmentFile` before trusting this unit. It is **not** a
shell: it parses `KEY=value` directly, which means it reads the un-exported
secret lines correctly where `source` does not — but it also does not honour an
`export ` prefix and does not expand `$HOME`. Any line added to `~/.g3o/env` in
shell form is therefore invisible or literal here, so state absolute paths with
`Environment=` in the unit rather than relying on the file. `G3O_OPERATOR` and
`G3O_SESSION_ID` are set in the unit for the same reason they are not in the
shared file: they identify a person and a session, and the unit is per run.

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

- **Publish-verify needs a worker that reads the run's database.** The leg is
  only as meaningful as the endpoint in `G3O_API_BASE`. The worker on
  `api.g3observatory.org` is the registry preview — `REGISTRY_ONLY=true`,
  `DEFAULT_WAVE=w000` — which serves every institution as `not_reviewed` with
  zero findings by design, and does not read a Neon branch. Pointed at it, this
  leg reports a perfectly-loaded run invisible, and the report is correct about
  the API while saying nothing about the load. Confirm the endpoint reads the
  same database the run was ingested into before believing either verdict.
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
