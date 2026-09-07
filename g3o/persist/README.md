# `g3o.persist` — Stage 7: CSV assembly of validated rows

**Status:** implemented.

## Role in the pipeline

Stage 7 of the seven-stage pipeline (see [`docs/architecture.md`](../../docs/architecture.md)). Deterministic; no LLM calls.

- **Input.** All Stage 6 outputs across institutions in a run
  (`runs/<run_id>/institutions/<shard>/<inst>/6_validate.json` — storage layout
  v2, see [`docs/storage-layout-v2.md`](../../docs/storage-layout-v2.md)).
- **Output.** Three canonical CSVs at `runs/<run_id>/final/`:
  - `g3o_activities_v{N}.csv` — one row per `(institution × activity)`, columns in `g3o.common.schema.ACTIVITY_COLUMNS` order.
  - `g3o_activity_sources_v{N}.csv` — one row per source page, carrying an `activity_id` FK (or `_NA_`), columns in `g3o.common.schema.ACTIVITY_SOURCE_COLUMNS` order.
  - `g3o_institution_summary_v{N}.csv` — one row per institution per run, columns in `g3o.common.schema.SUMMARY_COLUMNS` order.

A Postgres-backed adapter is out of scope for the current release; CSV is the Stage 7 deliverable.

## Modules

- `writer.py` — walks the run's institution directories via `g3o.common.paths.iter_institution_dirs`, validates against `g3o.common.contract`, writes the three CSVs, emits a deterministic QC summary alongside.

## CLI

```bash
python -m g3o persist --run-dir runs/<run_id> --run-id <run_id> --version 2
```
