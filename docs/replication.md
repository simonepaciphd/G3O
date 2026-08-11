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

Both variables are read **per call**, not at import (Run API spec §3, 2026-08-11),
so the CLI behaves exactly as documented above. A programmatic caller uses
`launch()` — the single entry point (§1) — and may pass keys per run, skipping the
environment entirely:

```python
from g3o.run.api import Credentials, launch

receipt = launch(
    config,                     # PresweepConfig; run_id may be left empty
    credentials=Credentials(
        openai_api_key="sk-…", serper_api_key="…", label="key-B-grant",
    ),
    session_id="…",             # joins the run back to the session that drove it
)
print(receipt.run_id, receipt.outcome, receipt.runs_dir)
```

Precedence per provider is explicit field → environment → unset; unset behaves as
it always has (mock discovery, a raise on the first LLM stage). A run records only
`sha256(key)[:8]` and the label, never key material.

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
institution master, persisting per-stage artifacts into
`runs/<run_id>/institutions/<shard>/<inst>/`, where `<shard>` is
`md5(inst_id)[:2]` (storage layout v2 — see
[`storage-layout-v2.md`](storage-layout-v2.md)).

```bash
python -m g3o presweep \
  --run-id 20260509-presweep \
  --master-csv path/to/master_institutions.csv \
  --sample-size 1000 \
  --seed 22294 \
  --stratification equal \
  --discovery-languages en \
  --discovery-results-per-query 10 \
  --discovery-mode chain \
  --execute --stop-after validate \
  --model gpt-5-nano
```

Without `--execute`, `presweep` runs in dry-run mode (no live submits). Resume
is auto-inferred from `_state/` files in `runs/<run_id>/`.

### Discovery defaults changed 2026-08-01

PI sign-off on the confirmation run
(`agent-workspace/2026-08-01-discovery-chain-validation.md`). `--discovery-mode`
now defaults to `chain`, `--discovery-results-per-query` to `10`, and
`--serper-autocorrect` to `off`. Measured over 200 institutions per arm, same
sample, as `GET /account` balance deltas:

| | `legacy` | `chain` |
|---|---:|---:|
| Serper credits / institution | 8.52 | **1.84** |
| Institutions with an own-domain *relevant* hit | 20.0% | **64.5%** |
| Stage 2 found an official site | 6.5% | **88.0%** |

Paired McNemar: 94 gains, 5 losses, exact two-sided *p* = 2.4 × 10⁻²².

**To replicate a run made before 2026-08-01**, pin all three explicitly. The
request payload is then byte-identical to what that run sent:

```bash
  --discovery-mode legacy \
  --discovery-results-per-query 5 \
  --serper-autocorrect omit
```

After Stage 6 completes, write the canonical CSVs:

```bash
python -m g3o persist \
  --run-dir runs/20260509-presweep \
  --run-id 20260509-presweep \
  --model gpt-5-nano \
  --version 2
```

This produces three normalized CSVs in `runs/20260509-presweep/final/`:
`g3o_activities_v2.csv` (one row per institution × activity),
`g3o_activity_sources_v2.csv` (one row per source page), and
`g3o_institution_summary_v2.csv` (one row per institution). Column orders are
pinned in `g3o.common.schema` and documented in
[`data_dictionary.md`](data_dictionary.md).

## Reproducibility floor

What an identical re-run does and does not hold fixed (T1, 2026-06-11):

- **Sampling is deterministic.** The stratified draw depends only on the
  master CSV contents, `--seed`, `--sample-size`, and the stratification
  keys (`g3o.run.presweep.stratified_sample`). The same inputs reproduce the
  same institution list, byte for byte.
- **Every LLM request pins its generation parameters.** All four LLM stages
  serialize through one path (`g3o.common.batch_client._serialize_job_line`),
  which pins `reasoning_effort` (`DEFAULT_REASONING_EFFORT`, currently
  `"medium"`) on every job. The GPT-5 model family does not accept a
  non-default `temperature`, so client-side output determinism is **not**
  achievable; the pin instead freezes the one generation parameter the
  provider exposes, so a server-side default change cannot silently alter
  outputs. LLM responses themselves remain non-deterministic.
- **The manifest records both sides of each call.**
  `run_generation_parameters` is written at plan time;
  after batches fetch, an `llm_provenance` block records, per stage, the
  versioned model id(s) the server answered with (e.g.
  `gpt-5-nano-2025-08-07`), `system_fingerprint`(s) when returned (newer
  models often return none), and the batch ids. A resume whose pinned
  generation parameters differ from the original launch aborts with a diff,
  alongside the existing sample/config guards.
- **Frozen-input regression tests run in CI.**
  `tests/test_reproducibility_regression.py` pins the stratified draw and the
  serialized Batch API request line for each LLM stage against goldens
  computed from frozen inputs; any change to a prompt, response schema,
  generation parameter, sampler, or the serializer fails CI until the goldens
  are regenerated deliberately (`G3O_REGEN_GOLDENS=1`).
- **A contract change cannot ship under an unchanged version header.**
  `tests/test_contract_version_pin.py` pins `(version, sha256 of the
  machine-readable surface)` for both contract documents in
  `tests/goldens/contract_version_pin.json`. The goldens above detect that the
  contract text moved, but their remedy is *regenerate* — so a regen commit can
  carry a controlled-vocabulary change through with the header untouched, which
  is what commit `25e544e` did on 2026-07-04. This test fails CI in that case
  **and refuses to regenerate**, pointing at the `CONTRIBUTING.md` sign-off
  gate. Same protocol (`G3O_REGEN_GOLDENS=1`, separate commit, reviewed diff);
  bumping the version in the contract's H1 is what unblocks it.

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
2. The columns enumerated in the G3O Output Contract (Groups A–F,
   columns 1–39) are a strict subset of `DATA_COLUMNS`. The five
   pipeline-derived columns (`global_row_id`, `run_id`, `run_model`,
   `run_tool`, `run_date`) wrap the contract columns in published
   files.

These two invariants govern the legacy 44-column full-database format
(`DATA_COLUMNS`), retained as the frozen schema of the published pilot v1 CSV.
The live Stage 7 output is the three normalized CSVs above; their column orders
are pinned separately in `g3o.common.schema` (`ACTIVITY_COLUMNS`,
`ACTIVITY_SOURCE_COLUMNS`, `SUMMARY_COLUMNS`) — see
[`data_dictionary.md`](data_dictionary.md).

## Versioning policy

- Files under `data/v<N>/` are immutable once a version is tagged.
- Bug fixes that change values produce a new version (`v<N+1>`).
- Methodology changes that change values produce a new pilot or release
  marker (`v3`, `pilot_v2`).
- The `mvp-v0` git tag points at the pre-restructure MVP (search/scrape
  only) for historical reference.
