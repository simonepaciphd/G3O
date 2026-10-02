# Deployment — getting reviewed code onto the production host

**Decision of record:** PI ruling 2026-10-02, option A: manual, recorded deploys
with visible staleness checks. Automatic deploy on merge was considered and
rejected (see [Why not deploy automatically](#why-not-deploy-automatically)).

## Why this document exists

On 2026-10-02 an operator's runs on `g3o-run-01` were silently skipping the
Bright Data Web Unlocker. Two separate gaps produced the same silence:

1. The production checkout was at `5af0071` (2026-09-15), nine merges behind
   `main`. The unlocker merged two days later (PR #121), so the host did not
   have the code at all.
2. The unlocker's token was not in the host's env file. Without it the
   unlocker switches itself off without a word, so blocked pages fell back to
   the baseline scraper.

Nothing in the pipeline compared the checkout with `main` or reported an
optional service as off. Both now show up in the preflight and in `g3o doctor`.

## The model: one repository, two kinds of checkout

There is **one** repository, `simonepaciphd/G3O`, not separate R&D and
production repos.

| | Development checkouts | The production checkout |
|---|---|---|
| Where | laptops, worktrees, CI | `g3o-run-01:/home/g3o/G3O`, owned by `g3o` |
| What it holds | any branch | local `main`, at whatever commit was **last deployed** |
| How it changes | `git` as usual | **only** through `scripts/deploy.sh` |
| Interpreter | your own venv | `~/venv`, an *editable* install of the checkout |
| Keys | your `.env` | `~/.g3o/env` (mode 600), sourced by the run wrappers |

GitHub `main` is reviewed code: a PR, an approving review, CI green. Production
is a pinned copy of some commit on `main`, and it only moves when somebody
deploys. **A merge does not deploy.** After merging anything a production run
should use, deploy it.

The installed package is editable, so the code a run executes *is* the
checkout. Changing the checkout under a live run changes that run's code at its
next import, resume or worker start. This is why the deploy script refuses to
run while a pipeline process is alive.

## How to tell what is deployed

```bash
ssh g3o@g3o-run-01                      # as the pipeline account
cat ~/DEPLOYED.json                      # last deploy: commit, previous, who, when, doctor result
tail ~/deploy-log.jsonl                  # every deploy, one line each
cd ~/G3O && set -a && . ~/.g3o/env && set +a && ~/venv/bin/g3o doctor
```

`g3o doctor` prints three things: the deployed commit against `origin/main` (a
read-only `git ls-remote`, nothing fetched); each paid service, whether this
commit will call it, and whether its key is present (values are never printed);
and `warnings`. It exits 1 if a key a live run needs is missing.

**The preflight carries the same block.** `g3o presweep --preflight`, which
the Berivox launcher runs before every submit, adds `services`, `deployment`
and `warnings` to its JSON and repeats each warning on stderr. A stale checkout
or an inactive unlocker is therefore printed on the first command an operator
runs.

## Deploying

Run on the host, as `g3o`:

```bash
cd ~/G3O
scripts/deploy.sh --dry-run          # what would change; touches nothing
scripts/deploy.sh                    # deploy origin/main
scripts/deploy.sh <sha-or-tag>       # deploy a specific commit
```

The script stops at the first failure. In order, it:

1. **refuses while any pipeline process of `g3o` is running.** Wait for the run
   to finish, or stop it deliberately;
2. **refuses if tracked files are modified.** Production runs what is in git;
3. fetches `origin` and resolves the target to a commit;
4. points local `main` at it with `git checkout -B main <sha>`, forward or back;
5. runs `pip install -e` into `~/venv` so dependency changes land (for example,
   the jev merge added `typesafe-sdk`), then `pip check`;
6. runs `g3o doctor` with `~/.g3o/env` sourced;
7. writes `~/DEPLOYED.json` and appends to `~/deploy-log.jsonl`.

If the doctor reports a missing key, the code **is** deployed and the script
exits 1. It prints the rollback command. Add the key, or roll back.

**First use, on a host whose checkout predates this script:** take the script
from `origin/main`, not from the old tree:

```bash
cd ~/G3O && git fetch origin && git show origin/main:scripts/deploy.sh > /tmp/deploy.sh
bash /tmp/deploy.sh --dry-run && bash /tmp/deploy.sh
```

### Rolling back

```bash
scripts/deploy.sh "$(python3 -c 'import json;print(json.load(open("/home/g3o/DEPLOYED.json"))["previous"])')"
```

or name any earlier commit from `~/deploy-log.jsonl`. A rollback is just a deploy
of an older commit, and it is recorded the same way.

### What a deploy does not touch

- **`~/g3o-api`**, the ingest loader, is a separate repository pinned
  separately (`runbook-orchestrator.md`).
- **Root-owned files**: the Berivox launcher `/usr/local/sbin/g3o-berivox`, its
  run template, and sudoers. Changing those is a root action by the PI, recorded
  in the access register.
- **`~/.g3o/env`.** Keys are added by hand (next section).

## Keys on the production host

`~/.g3o/env` is the only place production keys live. It is mode 600, owned by
`g3o`, inside a root-owned directory, so edit it in place by rewriting its
contents rather than replacing the file:

```bash
cp -p ~/.g3o/env ~/g3o-env.bak-$(date +%Y%m%d)        # back up first
# build ~/env.new = current contents + the new line, never echoing the value, then:
cat ~/env.new > ~/.g3o/env && shred -u ~/env.new
```

| Variable | Needed when | If missing |
|---|---|---|
| `SERPER_API_KEY` | always (Stage 1) | live run refuses to start |
| `OPENAI_API_KEY` | any stage on an OpenAI model (`extract` by default) | live run refuses to start |
| `TYPESAFE_API_KEY` | any stage on jev (Stages 2/3/6 by default) | live run refuses to start |
| `G3O_UNLOCKER_API_TOKEN` | to use the Web Unlocker (on by default in config) | **unlocker silently off**: doctor and preflight warn |
| `G3O_UNLOCKER_ZONE` | non-default zone | defaults to `web_unlocker1` |
| `G3O_SERPER_USD_PER_CREDIT` | the pack in use is not $0.001/credit | ceiling prices Serper at $0.001 |
| `DATABASE_URL` | the `e2e` ingest leg | ingest fails |

The Unlocker needs the Bright Data **account API key** (console → Account
settings → API keys), not a zone's proxy password. A zone password returns
HTTP 401 "Invalid token". After adding a key, run `g3o doctor` and check the
service shows `credential_present: true`. Then record the change in the PI's access
register the same day.

## Spend: one ceiling over every paid API

`G3O_BUDGET_LIMIT_USD` / `--cost-ceiling` (the Berivox launcher sets $500)
covers OpenAI, TypeSafe, Serper and the Web Unlocker, both in the preflight
projection and in the runtime monitor. `_cost_report.json` breaks actual spend
down in `by_api`. Rates, what is measured and what is assumed:
[`budget-enforcement.md`](budget-enforcement.md).

## Why not deploy automatically

Considered on 2026-10-02 and rejected:

- **GitHub Action that deploys on every merge.** It would hold a key that runs
  code as `g3o`, the account that can read every pooled API key, so anyone able
  to change a workflow would have a path to those keys. This repository has
  several collaborators with write access, and a personal-account repository
  cannot grant less. It would also swap code under live runs and put each merge
  into production before anyone ran it there.
- **Scheduled pull (cron).** No key in GitHub, but it still swaps code under
  live runs and still deploys untested merges.

The manual deploy keeps a human between a merge and the production host. The
staleness warning in every preflight is what stops "a human forgot" from
staying silent.
