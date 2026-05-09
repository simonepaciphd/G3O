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

| Variable          | When required                                                  |
|-------------------|----------------------------------------------------------------|
| `SERPER_API_KEY`  | Stages 1a / 1b (discovery). Without it, `discover` returns mock data. |
| `OPENAI_API_KEY`  | Stages 2, 3, 5, 6 (LLM via Batch API). Required end-to-end.    |

## One-off operations

```bash
# Discover candidate sources for one institution
python -m g3o discover \
  --institution "City of Helsinki" \
  --languages en,fi \
  --limit 5

# Scrape one URL
python -m g3o scrape --url https://example.com --text-only

# Confirm the OpenAI Batch model id is reachable
python -m g3o verify-model --model gpt-5-nano
```

`discover` and `scrape` cache to `cache/` (gitignored). Re-running the same
query or URL is idempotent.

## End-to-end run

The production entrypoint is `g3o presweep`, which orchestrates Stages 1a/2/1b/3/4/5
(and Stage 6 with `--stop-after validate`) over a stratified sample of the
institution master, persisting per-stage artifacts into `runs/<run_id>/<inst>/`.

```bash
python -m g3o presweep \
  --run-id 20260509-presweep \
  --master-csv path/to/master_institutions.csv \
  --sample-size 1000 \
  --seed 22294 \
  --stratification equal \
  --discovery-languages en \
  --discovery-results-per-query 5 \
  --execute --stop-after validate \
  --model gpt-5-nano
```

Without `--execute`, `presweep` runs in dry-run mode (no live submits). Resume
is auto-inferred from `_state/` files in `runs/<run_id>/`.

After Stage 6 completes, write the canonical CSVs:

```bash
python -m g3o persist \
  --run-dir runs/20260509-presweep \
  --run-id 20260509-presweep \
  --model gpt-5-nano \
  --version 2
```

This produces `runs/20260509-presweep/final/g3o_full_database_v2.csv` and
`g3o_institution_summary_v2.csv`.

## Stage-by-stage invocation

The Stage 6 consolidator can be re-run independently over an existing run
directory:

```bash
python -m g3o validate \
  --run-dir runs/20260509-presweep \
  --model gpt-5-nano \
  --notes "re-run with updated consolidation prompt"
```

The Stage 2 / Stage 3 classifiers can be invoked one institution at a time
for targeted debugging — see [`g3o/classify/README.md`](../g3o/classify/README.md).
Stage 5 extraction is library-only at the CLI level; it is invoked via
`presweep` (the per-institution DAG runner submits the Batch API jobs). See
[`g3o/extract/README.md`](../g3o/extract/README.md) for the library API.

## Reproducing pilot v1

The dataset under `data/pilot_v1/` was produced by an earlier, manual
ChatGPT-web pipeline plus retrofitted external databases — see
[`../data/pilot_v1/README.md`](../data/pilot_v1/README.md). It is **not**
reproducible from this repository as currently shipped. The production
pipeline above will produce v2 by re-running the institutional universe
through the API-driven flow; v2 supersedes v1.

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
