# `g3o.validate` — Stage 6: per-institution LLM consolidation

**Status:** implemented.

## Role in the pipeline

Stage 6 of the seven-stage pipeline (see [`docs/architecture.md`](../../docs/architecture.md)). Takes all extract-stage rows for one institution and consolidates them into a final per-institution record.

- **Input.** All Stage 5 rows for one institution (one row per `(institution × activity × source)` triple, possibly conflicting across pages).
- **Output.** Canonical (institution × activity × source) rows for that institution + a per-institution summary row in the `SUMMARY_COLUMNS` shape.
- **Operations performed by the LLM.** Activity dedup within institution (same activity reported by multiple pages → one canonical activity, multiple sources). Conflict resolution via the source-credibility hierarchy in Output Contract §4.8 (high-credibility government domain wins over a vendor blog). Uncertainty flag propagation per §4.10 (flags accumulate across sources rather than overwriting).
- **Mode.** OpenAI Batch API, `response_format=json_schema`, prompt caching enabled. One LLM call per institution.
- **Default model.** `gpt-5-nano`.
- **Per-call shape.** ~14k input tokens (system prompt + contract + ~12 pages worth of extract rows), ~4k output tokens.

Deterministic QC (`qc.py`) runs after the LLM pass and reports counts only — row totals, blank-required-field counts, source-family breakdowns. No silent overwrites; QC surfaces anomalies, the LLM does the consolidation.

## Modules

- `client.py` — OpenAI Batch API wrapper for the consolidation call, built on `g3o.common.batch_client`.
- `consolidate.py` — per-institution batch driver: assembles inputs from `runs/<run_id>/<inst>/5_extract/*.json`, calls the model, persists `runs/<run_id>/<inst>/6_validate.json`, surfaces conflicts.
- `qc.py` — deterministic QC summary.
- `prompts/system_prompt.md`, `prompts/output_contract.md` — consolidation prompts.

## CLI

```bash
python -m g3o validate --run-dir runs/<run_id> --model gpt-5-nano
```
