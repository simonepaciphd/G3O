# Architecture

The G3O production pipeline is a four-stage flow that mirrors the data
collection design described in the paper. Each stage is a separate Python
package; the boundary between them is a serializable artifact (search
results, scraped pages, structured records).

```
┌─────────────┐    ┌────────────┐    ┌──────────────┐    ┌────────────────┐
│  discovery  │ -> │   scrape   │ -> │   extract    │ -> │    validate    │
│  (Serper)   │    │ (HTML/PDF) │    │ (OpenAI LLM) │    │ (cross-source) │
└─────────────┘    └────────────┘    └──────────────┘    └────────────────┘
   institution         retrieved        structured            deduplicated
   × language ×        sources          records               panel
   GenAI terms                          (G3O Output           (institution
                                         Contract v2.0)        × quarter)
```

## Mapping to the paper

Section 5 of the paper ("Data Collection Pipeline") describes a three-layer
pipeline (discovery → extraction → cross-validation). This codebase splits
"discovery" into two stages — discovery (which URLs to fetch) and scrape
(actually fetching them) — because they have different failure modes,
caching strategies, and rate-limit constraints.

| Paper layer        | Code module        | What it does                                                         |
|--------------------|--------------------|----------------------------------------------------------------------|
| Discovery          | `g3o.discovery`    | Builds institution × language × GenAI-term queries; runs them via Serper. |
| Discovery          | `g3o.scrape`       | Fetches each candidate URL; extracts plaintext from HTML and PDF.    |
| Extraction         | `g3o.extract`      | Schema-first LLM extraction into the G3O Output Contract v2.0.       |
| Cross-validation   | `g3o.validate`     | Merges across sources; deduplication anchored on institution + activity; uncertainty flags propagated. |

## Implementation status

| Module           | Push #1                                                  | Push #2                                                                              |
|------------------|----------------------------------------------------------|--------------------------------------------------------------------------------------|
| `g3o.discovery`  | Implemented: Serper client, multilingual query builder.  | Expand multilingual term roster; add procurement-portal connectors when relevant.    |
| `g3o.scrape`     | Implemented: HTML and PDF extraction; on-disk cache.     | Add Playwright fallback for JavaScript-rendered pages; readability heuristics.       |
| `g3o.extract`    | Scaffold + prompt assets (system prompt, output contract).| Implement OpenAI client + Pydantic validators + batch driver. End-to-end on a small sample. |
| `g3o.validate`   | Scaffold.                                                | Port the merge/dedup/QC logic; produce `g3o_full_database_v2.csv` + summary + QC.    |

## Boundary artifacts

| Boundary             | Format            | Where it lives at runtime    |
|----------------------|-------------------|------------------------------|
| discovery → scrape   | JSONL search hits | `runs/<run_id>/hits.jsonl`   |
| scrape → extract     | JSONL pages       | `runs/<run_id>/pages.jsonl`  |
| extract → validate   | CSV records       | `runs/<run_id>/records.csv`  |
| validate → release   | CSV + summary     | `data/v<N>/`                 |

`runs/` is gitignored; only the validated release tree under `data/v<N>/`
is checked in.

## Caching and idempotency

Both `discovery` and `scrape` cache by hash on disk under `cache/`
(gitignored). Re-running with the same query or URL is idempotent and
free.

`extract` will not cache at the prompt level (cost) but will rely on
OpenAI's prompt-cache where available. `validate` is fully deterministic
given its inputs.

## Why this split

- **Discovery and scrape have different rate limits.** Serper is paid
  per query; HTTP fetches are bounded by per-host politeness. Splitting
  lets us back off independently.
- **Extraction is the expensive layer.** Keeping it isolated lets us
  swap models, re-run on cached pages, or replay against a different
  prompt without re-doing search/scrape.
- **Validation must be deterministic.** Holding it separate lets us
  re-run merges over an extended record set without re-issuing API calls.

## See also

- [`../README.md`](../README.md) — project overview and quickstart.
- [`data_dictionary.md`](data_dictionary.md) — output schema.
- [`replication.md`](replication.md) — how to reproduce / extend pilot results.
- [`../g3o/extract/prompts/output_contract.md`](../g3o/extract/prompts/output_contract.md) — schema-of-record.
