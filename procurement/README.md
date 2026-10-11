# procurement/ — G3O procurement pipeline

Code for the G3O procurement evidence channel: one shared core (`pipeline/core/`) and one thin adapter per source (`pipeline/adapters/{api,bulk,scrape}/`). Migrated from the Drive subproject `G3O/subprojects/procurement-pipeline/` on 2026-10-11, byte-identical (code sha256 `398167e275c48445391a0b64ae4ff3f916837b2524487b4cc198c88f293bbeaa`).

Code only. Specs, codebook, protocols, the handoff index, outputs, run caches and logs stay on Drive. Start from `agent-workspace/2026-10-07-handoff-index.md` there.

## Branches

- `procurement/main` — the shared core. Core fixes land here first, then merge down into every country branch.
- `procurement/<country>` (`uruguay`, `brazil`, `italy`) — long-lived, one per country. Adapter, config and fixture work for that country.
- `procurement/main` → `main` by PR, at least once per sprint.

## Setup and run

Run everything from this folder (`procurement/`); imports are `pipeline.*`.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q tests
python -m pipeline.cli sources --mode api --ocds
python -m pipeline.cli run <source_id> --limit 5 --since YYYY-MM --until YYYY-MM \
    --cache-dir data_cache/runs/<run_id> --out-dir outputs/runs/<run_id> \
    [--match --master <path>/master_institutions.csv --ledger <path>/institution_key_ledger.csv]
```

The default `--master`/`--ledger` paths assume the Drive layout and do not resolve from this repo; pass them explicitly. `data_cache/` and `outputs/` are git-ignored; archive run outputs on Drive.

## Not covered by root CI

The root `ruff` config excludes this folder, and the root `pytest` collects only `tests/`. Run `pytest -q tests` here before every PR.
