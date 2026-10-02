#!/usr/bin/env bash
# deploy.sh — move the production checkout to a named commit, recorded.
#
# Run ON THE PRODUCTION HOST, as the account that owns the checkout (g3o on
# g3o-run-01). Full procedure, rollback and rationale: docs/deployment.md.
#
#   scripts/deploy.sh                 # deploy origin/main
#   scripts/deploy.sh <sha|tag|ref>   # deploy that commit (also: rollback)
#   scripts/deploy.sh --dry-run [ref] # say what would happen, change nothing
#
# What it does, in order, stopping at the first failure:
#   1. refuses while any pipeline process of this user is running (the venv is
#      an editable install, so moving the tree changes code under a live run);
#   2. refuses if tracked files are modified (deploy what is in git, only);
#   3. fetches origin and resolves the target to a commit;
#   4. points local `main` at it (`git checkout -B main <sha>`; forward or back);
#   5. reinstalls the package into the venv so dependency changes land
#      (`pip install -e`), then `pip check`;
#   6. runs `g3o doctor` with the production env file sourced: which paid
#      services this commit will call and whether their keys are present;
#   7. writes ~/DEPLOYED.json and appends one line to ~/deploy-log.jsonl.
#
# Environment overrides (defaults are the g3o-run-01 layout):
#   G3O_REPO (~/G3O)  G3O_VENV (~/venv)  G3O_ENV_FILE (~/.g3o/env)
set -euo pipefail

REPO=${G3O_REPO:-$HOME/G3O}
VENV=${G3O_VENV:-$HOME/venv}
ENV_FILE=${G3O_ENV_FILE:-$HOME/.g3o/env}
RECORD=$HOME/DEPLOYED.json
LOG=$HOME/deploy-log.jsonl

DRY=0
if [ "${1:-}" = "--dry-run" ]; then DRY=1; shift; fi
REF=${1:-origin/main}

die() { echo "deploy: $*" >&2; exit 2; }
say() { echo "deploy: $*"; }

[ -d "$REPO/.git" ] || die "$REPO is not a git checkout"
[ -x "$VENV/bin/pip" ] || die "$VENV has no pip"

# 1. No live pipeline run of this user.
live=$(pgrep -u "$(id -u)" -af 'g3o\.run\.orchestrate|bin/g3o presweep|g3o\.cli presweep|-m g3o ' \
       | awk -v me="$$" '$1 != me' || true)
if [ -n "$live" ]; then
    echo "$live" >&2
    die "a pipeline process is running (above); deploy after it finishes"
fi

cd "$REPO"
# 2. Clean tracked tree.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    git status --short --untracked-files=no >&2
    die "tracked files are modified (above); commit them upstream or discard them first"
fi

# 3. Resolve the target.
git fetch -q origin
target=$(git rev-parse --verify -q "${REF}^{commit}") || die "cannot resolve '$REF' to a commit"
previous=$(git rev-parse HEAD)
behind=$(git rev-list --count "$target..origin/main")
say "current  $(git log -1 --format='%h %cs %s' "$previous")"
say "target   $(git log -1 --format='%h %cs %s' "$target")  ($REF)"
[ "$behind" -eq 0 ] || say "note: target is $behind commit(s) behind origin/main"

if [ "$DRY" -eq 1 ]; then
    say "dry run: commits that would change:"
    git log --oneline "$previous..$target" | sed 's/^/  + /'
    git log --oneline "$target..$previous" | sed 's/^/  - /'
    exit 0
fi

# 4. Move the tree.
git checkout -q -B main "$target"

# 5. Dependencies.
"$VENV/bin/pip" install -q -e "$REPO"
"$VENV/bin/pip" check

# 6. Doctor, against the production env.
doctor_ok=true
doctor_out=$(mktemp)
if ! (set -a; [ -f "$ENV_FILE" ] && . "$ENV_FILE"; set +a; "$VENV/bin/g3o" doctor) >"$doctor_out"; then
    doctor_ok=false
fi
cat "$doctor_out"
n_warnings=$("$VENV/bin/python" -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("warnings", [])))' \
    "$doctor_out" 2>/dev/null || echo null)
rm -f "$doctor_out"

# 7. Record.
now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
who=${SUDO_USER:-${USER:-$(id -un)}}
entry=$(printf '{"commit":"%s","previous":"%s","ref":"%s","deployed_at":"%s","deployed_by":"%s","host":"%s","doctor_ok":%s,"n_warnings":%s}' \
    "$target" "$previous" "$REF" "$now" "$who" "$(hostname)" "$doctor_ok" "$n_warnings")
printf '%s\n' "$entry" > "$RECORD"
printf '%s\n' "$entry" >> "$LOG"
say "recorded in $RECORD and $LOG"

if [ "$doctor_ok" != true ]; then
    say "DOCTOR FAILED: a key this commit needs is missing (see warnings above)."
    say "The code IS deployed. Add the key to $ENV_FILE, or roll back with: scripts/deploy.sh $previous"
    exit 1
fi
say "done: $(git log -1 --format='%h %s')"
