# CLAUDE.md — G3O procurement pipeline (repo copy)

Instruction file for Claude Code. Start Claude Code with **this folder** (`procurement/`) as the working directory. Run every command from here; imports are `pipeline.*`.

## Where things live

- **Code:** this repo (`simonepaciphd/G3O`), folder `procurement/`. Never copy code into Google Drive, and never `git init` inside a Drive folder: Drive sync corrupts Git.
- **Documents, data, outputs, logs:** the shared Drive folder `procurement-pipeline` (G3O → subprojects). Its path differs per machine; ask the user where their Drive copy is. Read these first: `docs/procurement-extension-spec.md` (the scope ruling), `docs/architecture.md`, `docs/adapter-output-interface.md`, `docs/genai-procurement-codebook.md`, and `agent-workspace/2026-10-07-handoff-index.md`.
- Run outputs go to Drive. `data_cache/` and `outputs/` are git-ignored here.

## Branches

- `procurement/main` holds the shared core. `procurement/<country>` (`uruguay`, `brazil`, `italy`) are long-lived country branches.
- On a country branch, add only that country's adapter (`pipeline/adapters/<access_mode>/<source_id>.py`), its row in `config/sources.yaml`, and its fixtures and tests. **Never edit `pipeline/core/` on a country branch.** If the core can't handle a source, stop and tell the user to raise it with Simone.
- Commit small, with clear messages. Push to the user's own country branch only. Never push to `main` or to another country's branch.
- Run `pytest -q tests` before every commit. CI (`.github/workflows/procurement.yml`) runs it again on push.

## Scope (PI ruling 2026-07-28; full text in the Drive spec)

- Every observation is a row in the G3O output contract (pinned here as `docs/reference/output_contract_v2.0.SNAPSHOT.md`; the live contract is `../g3o/extract/prompts/output_contract.md`). The pipeline is an evidence channel, not a second observatory.
- **No new data sources.** Only the repositories in `config/sources.yaml`.
- **No new taxonomies, relevance schemes or units of analysis.** Fields that only procurement surfaces (contract value, procedure type, supplier role, contractual governance terms) go in the procurement extension table.
- The query set `config/genai_queries.yaml` is PI-approved (v1.0). Do not add terms or languages; Italian terms come from the multilingual subproject.

## What is the user's, and what is Simone's

**The user's (engineering):** setup, adapters cloned from templates, tests, fixtures, small runs, QC, notes on each source.

**Simone's. Never decide these; stop and ask:** anything about what the data *means*. That covers what counts as a GenAI purchase, how a record is coded or categorised, the relevance definition, the matcher threshold, contract version changes, and which sources or time windows are in scope. Rulings already made are implemented in `pipeline/core/coding.py`, each citing its ruling. Read that file before coding anything by hand, and don't re-open those rulings.

## Hard rules

- **Small first.** Smoke-run 5 records (`--limit 5`) before anything larger, and fix every error there.
- **Ask before any command that contacts a website.** Check robots.txt, rate limits and terms of use first, and record what you found in the source's `verification_note`.
- A source marked `verification_status: unverified_snapshot` runs only with `--allow-unverified --limit N`.
- Procurement evidence codes `adoption_stage: announced` (award) or `proposed` (tender-only). Never `production`.
- Never emit `null` in contract-conformant output; use the contract defaults (`_NA_`, `unknown`, `none_reported`, `not_documented`).
- Never alter or invent a `source_url` or any value the notice does not state. Never sum money across currencies.
- Negative evidence counts: `confirms_absence` rows stay. Records with no descriptive text are `not_assessable`, never absence.
- Key institutions by `institution_uid`, never `master_row_id`. The institution master (`--match`) is read-only. The user may not have it; ask before running `--match`.
- No secrets in code. Keys go in `.env` or `config/secrets.yaml` (both git-ignored).

## Logging

At the end of each working session, add one row to `interaction-log.csv` in the Drive folder (date, tool, model, what the user asked, what was done, files affected), and register new finished files in `asset-registry.csv`. Append rows; never rewrite those files.
