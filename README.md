# G3O — Global Government GenAI Observatory

> **Status: preliminary research infrastructure.** The accompanying paper is
> in preparation. This repository ships the production data-collection
> pipeline and the pilot v1 results that back the live observatory at
> [`simonepaciphd.github.io/g3o-website`](https://simonepaciphd.github.io/g3o-website/)
> (source: [`g3o-website`](https://github.com/simonepaciphd/g3o-website)).
> The full institutional universe (~675k institutions) and the v2 dataset
> will land in subsequent releases.

G3O builds an open, auditable, versioned panel of public-sector generative-AI
activity across ~675,000 government institutions worldwide. The pipeline runs
quarterly multilingual searches against an institutional universe, scrapes
candidate sources, extracts structured records via LLM with a fixed schema,
and cross-validates across sources. A complementary multilingual staff
survey covers internal use that is not publicly documented (separate repo,
to come).

## Pipeline architecture

```
1a  discovery_general            (Serper queries; cached on disk)
        │
        ▼
2   classify_official_site       (LLM, Batch API, gpt-5-nano)
        │
        ▼
1b  discovery_site_restricted    (Serper site:<official_site>)
        │
        ▼
3   classify_url_triage          (LLM, Batch API)
        │
        ▼
4   scrape                       (HTTP + HTML / PDF / headless-render)
        │
        ▼
5   extract                      (LLM, Batch API; one call per page)
        │
        ▼
6   validate                     (LLM, Batch API; one call per institution)
        │
        ▼
7   persist                      (deterministic CSV writer)
```

Stages 2, 3, 5, and 6 call the OpenAI Batch API on `gpt-5-nano`. Stages 1a,
1b, 4, and 7 are deterministic. End-to-end orchestration lives in
`g3o.run.presweep`.

Per-institution artifacts land under `runs/<run_id>/<inst>/` (gitignored):
`1a_discovery_general.json`, `2_official_site.json`,
`1b_discovery_site_restricted.json`, `3_triage.json`, `scrape/<url_hash>.json`,
`extract/<url_hash>.json`, and `6_validate.json`. Stage 7 assembles three
normalized CSVs under `runs/<run_id>/final/`: `g3o_activities_v{N}.csv`,
`g3o_activity_sources_v{N}.csv`, and `g3o_institution_summary_v{N}.csv`.

| Module          | Stage   | Description                                                  |
|-----------------|---------|--------------------------------------------------------------|
| `g3o.discovery` | 1a / 1b | Serper queries + multilingual builder + on-disk cache        |
| `g3o.classify`  | 2 + 3   | LLM official-site picker + URL triage (Batch API)            |
| `g3o.scrape`    | 4       | HTTP fetch with HTML / PDF / headless-render routing + cache |
| `g3o.extract`   | 5       | Per-page LLM extraction to G3O Output Contract v2.0 rows     |
| `g3o.validate`  | 6       | Per-institution LLM consolidation + deterministic QC         |
| `g3o.persist`   | 7       | Deterministic CSV writer (three normalized tables)           |
| `g3o.run`       | —       | Orchestration: `presweep`, `verify-model`                    |
| `g3o.common`    | —       | Schema, contract validators, batch client, run state         |

See [`docs/architecture.md`](docs/architecture.md) for the mapping to the
paper, and [`docs/data_dictionary.md`](docs/data_dictionary.md) for the
output schema (G3O Output Contract v2.0).

For **what the pipeline has actually been measured to do** — per-stage
benchmarks, what is still unmeasured, and the ranked improvement list — see
[`docs/pipeline-status.md`](docs/pipeline-status.md). Figures there are labelled
by evidence class (measured / threshold / assumption); the distinction matters,
because an unlabelled assumption in the cost model was wrong by ~4×.

## Repository layout

```
G3O/
├── g3o/                  # Python package — the production pipeline
│   ├── discovery/        # Stage 1a / 1b
│   ├── classify/         # Stages 2 + 3
│   ├── scrape/           # Stage 4
│   ├── extract/          # Stage 5
│   ├── validate/         # Stage 6
│   ├── persist/          # Stage 7
│   ├── run/              # Orchestration: presweep, verify-model
│   └── common/           # Schema, contract, batch client, run state
├── data/pilot_v1/        # Pilot v1 results (~1k institutions; CC-BY 4.0)
├── docs/                 # Architecture, data dictionary, replication, working draft
├── tests/                # pytest test suite
├── runs/                 # Per-run artifacts (gitignored)
├── cache/                # On-disk fetch cache (gitignored)
├── .github/workflows/    # CI
├── pyproject.toml        # Editable install + package metadata
├── requirements.txt      # Runtime deps
├── .env.template         # Required environment variables
├── LICENSE               # MIT (code)
└── data/LICENSE          # CC-BY 4.0 (data)
```

## Quickstart

```bash
git clone https://github.com/simonepaciphd/G3O.git
cd G3O
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e .

cp .env.template .env
# edit .env:
#   SERPER_API_KEY  — Stage 1 discovery (mock results without it)
#   OPENAI_API_KEY  — Stages 2, 3, 5, 6 (LLM via Batch API)

# One-off: discover candidate sources for a single institution
python -m g3o discover --institution "City of Helsinki" --languages en,fi --limit 5

# One-off: scrape a single URL
python -m g3o scrape --url https://example.com --text-only

# Confirm the OpenAI Batch model id is reachable
python -m g3o verify-model --model gpt-5-nano

# End-to-end: stratified pre-sweep over a sample of the institution master
python -m g3o presweep \
  --run-id 20260509-presweep \
  --master-csv path/to/master_institutions.csv \
  --sample-size 1000 \
  --execute --stop-after validate

# Stage 7 only: write the final CSVs from an existing run-dir
python -m g3o persist --run-dir runs/20260509-presweep --run-id 20260509-presweep
```

Without `SERPER_API_KEY`, `discover` returns mock results so you can exercise
the pipeline shape without API credentials. The on-disk fetch cache lives
under `cache/` (gitignored); per-run artifacts live under `runs/<run_id>/`
(gitignored). Delete either to force re-fetches.

## Pilot v1 dataset

`data/pilot_v1/` ships the 1k-institution pilot dataset that backs the
[live observatory](https://simonepaciphd.github.io/g3o-website/). It was
collected with ChatGPT-web search prior to the API-driven pipeline and is
**a snapshot, not a panel** — the production pipeline will produce v2 under
different methodology. See [`data/pilot_v1/README.md`](data/pilot_v1/README.md)
for provenance, model, date, and caveats.

## Citing G3O

Working paper: **The G3O Initiative: Building a Global Panel of Government
GenAI Use** (Paci, Pressly, Feldman & Vannutelli, May 2026). Current draft:
[`docs/introducing-g3o-current-draft.pdf`](docs/introducing-g3o-current-draft.pdf).
For citation metadata, see [`CITATION.cff`](CITATION.cff). The draft is
preliminary; please contact the authors before circulating beyond the repo.

## License

Code: [MIT](LICENSE).
Data (anything under `data/`): [CC-BY 4.0](data/LICENSE).

## Authors

Simone Paci (Stanford), Lowry Pressly (Stanford), Nathan Feldman (Rochester),
Silvia Vannutelli (Northwestern, NBER).
