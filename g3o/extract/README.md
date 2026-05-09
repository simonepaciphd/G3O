# `g3o.extract` — Stage 5: per-page LLM extraction

**Status:** scaffold. Implementation lands in **Session B** of Push #2.

## Role in the pipeline

Stage 5 of the seven-stage pipeline (see [`docs/budget/pipeline-spec-2026-05-08.md`](../../../../docs/budget/pipeline-spec-2026-05-08.md)). Takes scraped page text from Stage 4 + institution metadata, and produces 0+ canonical rows per page conforming to the G3O Output Contract v2.0.

- **Input.** One scraped page (`{url, text, title, content_type}` from `g3o.scrape`) + the institution row.
- **Output.** A list of contract rows (39 fields) in JSON, one per `(institution × activity × source)` triple supported by this page. Pages with no GenAI evidence return one row with `genai_evidence = confirms_absence` and Group D set to `_NA_`.
- **Mode.** OpenAI Batch API, `response_format=json_schema`, prompt caching enabled. One LLM call per page; calls are batched across institutions for the 50% Batch API price.
- **Default model.** `gpt-5-nano` (per the cost model in `docs/budget/budget-draft-05-08-26.md`).
- **Per-call shape.** ~6k input tokens (page + system prompt + contract), ~700 output tokens.

## What's here today

- `prompts/system_prompt.md` — system instructions for the extractor model. Revised to match scrape-then-extract mode (decision A1, 2026-05-08).
- `prompts/output_contract.md` — schema-of-record. The 39 columns specified there are extended at pipeline time with five run/provenance fields (`global_row_id`, `run_id`, `run_model`, `run_tool`, `run_date`), giving the 44 columns enumerated in `g3o.common.schema.DATA_COLUMNS`.

## What lands in Session B

- `client.py` — OpenAI Batch API wrapper for per-page extraction, built on `g3o.common.batch_client`.
- `batch.py` — batch assembly across institutions; result fetching; retry on schema validation failure (per pipeline-spec §6 retry policy).
- `parser.py` — JSON → contract rows; attaches the five provenance fields; routes through `g3o.common.contract` for Pydantic validation.
- CLI: `python -m g3o extract --run <run_id> --institutions <ids.csv>`.
