# G3O — Global Government GenAI Observatory

> **Status: preliminary research infrastructure.** The accompanying paper is
> in preparation. This repository ships the production data-collection
> pipeline and the pilot v1 results that already feed
> [`g3o-website`](https://github.com/simonepaciphd/g3o-website). The full
> institutional universe (~675k institutions) and the v2 dataset will land
> in subsequent releases.

G3O builds an open, auditable, versioned panel of public-sector generative-AI
activity across ~675,000 government institutions worldwide. The pipeline runs
quarterly multilingual searches against an institutional universe, scrapes
candidate sources, extracts structured records via LLM with a fixed schema,
and cross-validates across sources. A complementary multilingual staff
survey covers internal use that is not publicly documented (separate repo,
to come).

This repository contains the **automated discovery + extraction pipeline**.
The institutional universe is built in a separate workflow and released
alongside future versions of the dataset.

## Pipeline architecture

```
┌─────────────┐    ┌────────────┐    ┌──────────────┐    ┌────────────────┐
│  discovery  │ -> │   scrape   │ -> │   extract    │ -> │    validate    │
│  (Serper)   │    │  (HTML/PDF)│    │ (OpenAI LLM) │    │ (cross-source) │
└─────────────┘    └────────────┘    └──────────────┘    └────────────────┘
   institution         retrieved        structured            deduplicated
   × language ×        sources          records               panel
   GenAI terms                          (G3O Output           (institution
                                         Contract v2.0)        × quarter)
```

Modules under `g3o/`:

| Module           | Status (Push #1)              | Push #2 |
|------------------|-------------------------------|---------|
| `g3o.discovery`  | implemented (Serper + queries)| —       |
| `g3o.scrape`     | implemented (HTML + PDF)      | —       |
| `g3o.extract`    | scaffold + prompts            | OpenAI client, validators, batch driver |
| `g3o.validate`   | scaffold                      | merge, dedup, QC                        |

See [`docs/architecture.md`](docs/architecture.md) for the mapping to the
paper, and [`docs/data_dictionary.md`](docs/data_dictionary.md) for the
output schema (G3O Output Contract v2.0).

## Repository layout

```
G3O/
├── g3o/                  # Python package — the production pipeline
├── data/pilot_v1/        # Pilot v1 results (~1k institutions; CC-BY 4.0)
├── docs/                 # architecture, data dictionary, replication
├── tests/                # pytest test suite
├── .github/workflows/    # CI
├── pyproject.toml        # editable install + package metadata
├── requirements.txt      # runtime deps
├── .env.template         # required environment variables
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
# edit .env: at minimum SERPER_API_KEY for live discovery; OPENAI_API_KEY
# is not required until extract/validate land in Push #2.

# Discover candidate sources for one institution:
python -m g3o discover --institution "City of Helsinki" --languages en,fi --limit 5

# Scrape one URL:
python -m g3o scrape --url https://example.com --text-only
```

Without `SERPER_API_KEY`, `discover` returns mock results so you can exercise
the pipeline shape without API credentials. The cache lives under `cache/`
(git-ignored); delete it to force re-fetches.

## Pilot v1 dataset

`data/pilot_v1/` ships the 1k-institution pilot dataset that backs the
[`g3o-website`](https://github.com/simonepaciphd/g3o-website). It was
collected with ChatGPT-web search prior to the API-driven pipeline and is
**a snapshot, not a panel** — the production pipeline (Push #2) will
produce v2 under different methodology. See
[`data/pilot_v1/README.md`](data/pilot_v1/README.md) for provenance, model,
date, and caveats.

## Citing G3O

The accompanying paper is in preparation and not yet circulated. For
current citation metadata see [`CITATION.cff`](CITATION.cff). Please do not
circulate the draft without the authors' consent.

## License

Code: [MIT](LICENSE).
Data (anything under `data/`): [CC-BY 4.0](data/LICENSE).

## Authors

Simone Paci (Stanford), Lowry Pressly (Stanford), Nathan Feldman (Rochester).
