# `g3o.classify` — Stages 2 + 3: LLM filtering of candidate URLs

**Status:** scaffold. Implementation lands in **Session A** of Push #2.

## Role in the pipeline

Two LLM stages of the seven-stage pipeline (see [`docs/budget/pipeline-spec-2026-05-08.md`](../../../../docs/budget/pipeline-spec-2026-05-08.md)) that filter the Serper output before any page text is fetched. Both call OpenAI Batch API on `gpt-5-nano` and use `response_format=json_schema` for Pydantic-validated output.

## Stage 2 — Official-site classification (`official_site.py`)

- **Input.** One institution row + Stage 1 candidate URLs.
- **Output.** `{official_url: str | None, confidence: "high" | "medium" | "low" | "none", rationale: str}` persisted at `runs/<run_id>/<inst>/2_official_site.json`.
- **Why.** Identifies the canonical institutional homepage so Stage 3 can prioritize crawl, and so source-credibility downstream can mark official-site evidence appropriately.
- **Per-call shape.** ~2k input tokens.

## Stage 3 — URL triage (`url_triage.py`)

- **Input.** One institution row + Stage 1 candidate URLs + Stage 2 official site.
- **Output.** `{decisions: [{url: str, decision: "keep" | "drop", rationale: str}, ...]}` persisted at `runs/<run_id>/<inst>/3_triage.json`. Typically ~12 URLs marked `keep` per institution.
- **Why.** Cuts the ~40 candidate URLs per institution to a tractable set for Stage 4 scrape and Stage 5 extract, where per-page costs add up.
- **Per-call shape.** ~6k input tokens.

## What lands in Session A

- `official_site.py`, `url_triage.py` — both stages, calling `g3o.common.batch_client`.
- Pydantic-validated output schemas (defined in `g3o.common.contract`).
- CLI: `python -m g3o classify official-site --institution-id ...` and `python -m g3o classify triage --institution-id ...`.
