# `g3o.persist` — Stage 7: CSV assembly of validated rows

**Status:** implemented.

## Role in the pipeline

Stage 7 of the seven-stage pipeline (see [`docs/architecture.md`](../../docs/architecture.md)). Deterministic; no LLM calls.

- **Input.** All Stage 6 outputs across institutions in a run (`runs/<run_id>/<inst>/6_validate.json`).
- **Output.** Two canonical CSVs at `runs/<run_id>/final/`:
  - `g3o_full_database_v{N}.csv` — one row per `(institution × activity × source)` triple, columns in `g3o.common.schema.DATA_COLUMNS` order.
  - `g3o_institution_summary_v{N}.csv` — one row per institution, columns in `g3o.common.schema.SUMMARY_COLUMNS` order.

A Postgres-backed adapter is out of scope for the current release; CSV is the Stage 7 deliverable.

## Modules

- `writer.py` — walks the run directory, validates against `g3o.common.contract`, writes the two CSVs, emits a deterministic QC summary alongside.

## CLI

```bash
python -m g3o persist --run-dir runs/<run_id> --run-id <run_id> --version 2
```
