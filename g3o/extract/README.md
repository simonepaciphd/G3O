# `g3o.extract` — schema-first LLM extraction

**Status:** scaffold (Push #1). Implementation lands in Push #2.

The extract layer turns scraped pages into structured records that conform to
the **G3O Output Contract v2.0** (`prompts/output_contract.md`). Each row in
the output represents one `(institution × activity × source)` triple.

## What's here today

- `prompts/system_prompt.md` — system instructions for the extractor model.
- `prompts/output_contract.md` — schema-of-record. The 39 columns specified
  there are extended at pipeline time with five run/provenance fields
  (`global_row_id`, `run_id`, `run_model`, `run_tool`, `run_date`), giving
  the 44 columns enumerated in `g3o.common.schema.DATA_COLUMNS`.

## What lands in Push #2

- `client.py` — OpenAI client with retry/backoff, JSON-mode parsing, and
  prompt-cache support.
- `validator.py` — Pydantic models that mirror the output contract; reject
  payloads with missing fields, illegal enum values, or shape errors.
- `batch.py` — institution-batch driver (10 institutions × N sources per
  call), prompt assembly from the assets above, and merge into the
  `DATA_COLUMNS` schema.
- CLI: `python -m g3o extract --batch <institutions.csv> --sources <pages.jsonl>`.
