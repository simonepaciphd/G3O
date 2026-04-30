# Contributing to G3O

Thank you for your interest in G3O. This document covers the development setup, the layout of the production pipeline, and the ground rules for contributions.

## Setup

```bash
git clone https://github.com/simonepaciphd/G3O.git
cd G3O
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.template .env
# fill in SERPER_API_KEY (required for live discovery)
# OPENAI_API_KEY is needed once the extract layer lands in Push #2
```

Run the test suite and linter before submitting changes:

```bash
ruff check
pytest -q
```

## Architecture

The pipeline lives under `g3o/` and is organized as four modules that mirror the paper:

```
discovery → scrape → extract → validate
```

- `g3o.discovery` — institution-driven Serper queries (multilingual).
- `g3o.scrape` — HTTP fetch + HTML/PDF content extraction.
- `g3o.extract` — schema-first LLM extraction (Push #2 — see module README).
- `g3o.validate` — cross-source merge and consolidation (Push #2).

The schema-of-record is `g3o/extract/prompts/output_contract.md`. The CSV header for the production database lives in `g3o.common.schema.DATA_COLUMNS`. These two must stay in sync.

## Ground rules

- **No secrets in commits.** `.env` is gitignored; the template lives at `.env.template`. If you find a key in a diff, remove it before opening a PR.
- **Schema stability.** Changes to `output_contract.md` or `DATA_COLUMNS` are versioned and require maintainer sign-off.
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
