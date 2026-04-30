# Replication

How to run the production pipeline locally and how the published pilot v1
dataset relates to it.

## Setup

```bash
git clone https://github.com/simonepaciphd/G3O.git
cd G3O
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.template .env
```

Fill in `.env`:

| Variable          | When required                       |
|-------------------|--------------------------------------|
| `SERPER_API_KEY`  | Live Serper queries; without it, `discover` returns mock data. |
| `OPENAI_API_KEY`  | Push #2: `extract` and `validate`. Not needed for Push #1.     |

## Push #1 — discover and scrape

```bash
# 1. Discover candidate sources for one institution
python -m g3o discover \
  --institution "City of Helsinki" \
  --languages en,fi \
  --limit 5 \
  > runs/helsinki_hits.json

# 2. Scrape one URL
python -m g3o scrape \
  --url https://example.com \
  --text-only \
  > runs/example_text.txt
```

Both commands cache to `cache/` (gitignored). Re-running the same query
or URL is idempotent.

## Push #2 — extract and validate

Coming with the next plan. The interface will be:

```bash
# 3. Extract structured records from scraped pages
python -m g3o extract \
  --batch institutions.csv \
  --pages runs/<run_id>/pages.jsonl \
  --out runs/<run_id>/records.csv

# 4. Cross-validate and merge into a versioned release
python -m g3o validate \
  --inputs runs/<run_id>/records.csv \
  --out data/v2/
```

Both will respect prompt caching where available and will be deterministic
given their inputs.

## Reproducing pilot v1

The dataset under `data/pilot_v1/` was produced by an earlier, manual
ChatGPT-web pipeline plus retrofitted external databases — see
[`../data/pilot_v1/README.md`](../data/pilot_v1/README.md). It is **not**
reproducible from this repository as currently shipped. The production
pipeline (Push #2) will produce v2 by re-running the institutional
universe through the API-driven flow; v2 supersedes v1.

If you need to reproduce v1 specifically (e.g., to audit a row), the
upstream prompt assets live at
[`../g3o/extract/prompts/system_prompt.md`](../g3o/extract/prompts/system_prompt.md)
and
[`../g3o/extract/prompts/output_contract.md`](../g3o/extract/prompts/output_contract.md);
running them through ChatGPT (web search) on the same institution list
would approximate v1's `pilot_web` component but not re-create it
exactly.

## Schema invariants

Two assertions must always hold; CI checks them:

1. The list `g3o.common.schema.DATA_COLUMNS` is the exact header order
   of every published `g3o_full_database_v<N>.csv`.
2. The columns enumerated in the G3O Output Contract v2.0 (Groups A–F,
   columns 1–39) are a strict subset of `DATA_COLUMNS`. The five
   pipeline-derived columns (`global_row_id`, `run_id`, `run_model`,
   `run_tool`, `run_date`) wrap the contract columns in published
   files.

## Versioning policy

- Files under `data/v<N>/` are immutable once a version is tagged.
- Bug fixes that change values produce a new version (`v<N+1>`).
- Methodology changes that change values produce a new pilot or release
  marker (`v3`, `pilot_v2`).
- The `mvp-v0` git tag points at the pre-restructure MVP (search/scrape
  only) for historical reference.
