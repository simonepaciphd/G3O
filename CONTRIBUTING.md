# Contributing to G3O

Thank you for your interest in G3O. This document covers the development setup, the layout of the production pipeline, and the ground rules for contributions.

## Setup

```bash
git clone https://github.com/simonepaciphd/G3O.git
cd G3O
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.template .env
# fill in SERPER_API_KEY (required for live discovery, Stages 1a/1b)
# OPENAI_API_KEY is required for the LLM stages (2 official-site, 3 triage,
#   5 extract, 6 validate)
```

Run the test suite and linter before submitting changes:

```bash
ruff check
pytest -q
```

## Architecture

The pipeline lives under `g3o/` as a seven-stage flow across these packages:

```
discovery → classify → scrape → extract → validate → persist
```

- `g3o.discovery` — Stages 1a/1b: institution-driven Serper queries (multilingual) + on-disk cache.
- `g3o.classify` — Stages 2/3: LLM official-site picker and URL triage (Batch API).
- `g3o.scrape` — Stage 4: HTTP fetch + HTML/PDF/headless-render routing.
- `g3o.extract` — Stage 5: schema-first per-page LLM extraction.
- `g3o.validate` — Stage 6: per-institution LLM consolidation + deterministic QC.
- `g3o.persist` — Stage 7: deterministic CSV writer (three normalized tables).
- `g3o.run` / `g3o.common` — orchestration (`presweep`, `verify-model`) and shared schema / contract validators / batch client / run-state.

The schema-of-record is `g3o/extract/prompts/output_contract.md`. The live Stage 7 CSV column orders are pinned in `g3o.common.schema` (`ACTIVITY_COLUMNS`, `ACTIVITY_SOURCE_COLUMNS`, `SUMMARY_COLUMNS`); the legacy 44-column `DATA_COLUMNS` governs the historical full-database format (pilot v1). These must stay in sync with the contract.

## Ground rules

- **No secrets in commits.** `.env` is gitignored; the template lives at `.env.template`. If you find a key in a diff, remove it before opening a PR.
- **Schema stability.** Changes to `output_contract.md` or the `g3o.common.schema` column lists (`ACTIVITY_COLUMNS`, `ACTIVITY_SOURCE_COLUMNS`, `SUMMARY_COLUMNS`, legacy `DATA_COLUMNS`) are versioned and require maintainer sign-off.
- **Pilot data is read-only.** `data/pilot_v1/` is a fixed snapshot. Future versions land as `data/pilot_v2/`, `data/v2/`, etc., never overwrites.
- **Researcher control.** Substantive design choices (typology, validation, sampling) are reserved for the project authors. Pull requests that touch typology or coding rules need explicit sign-off in the issue first.

## How to contribute

1. Open an issue describing the change. For non-trivial work, get sign-off on the approach before writing code.
2. Branch from `main`: `git checkout -b feature/your-change`.
3. Make the change. Add tests under `tests/`.
4. Run `ruff check && pytest -q` locally.
5. Open a PR. CI runs the same checks plus an optional Serper smoke test.

## Reporting issues

Open a GitHub issue. For data-quality concerns about specific records in `data/pilot_v1/`, please include the institution name and the source URL — not a raw row dump — so issues stay readable.
