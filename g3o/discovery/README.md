# `g3o.discovery` — Stage 1: candidate source discovery

Stage 1 of the seven-stage pipeline (see [`docs/architecture.md`](../../docs/architecture.md)). Maps institutions to candidate URLs via the Google Search API (Serper).

## Modules

- `serper_client.py` — Serper.dev client with retry + on-disk cache. Falls back to mock data when `SERPER_API_KEY` is unset, so the rest of the pipeline can be exercised without API credentials.
- `query_builder.py` — turns an institution + a language roster into a list of `(query, language)` tuples. Push #1 ships a small term roster covering the pilot languages; the multilingual roster will expand alongside the master institutions universe.

## Inputs and outputs

- **Input.** One institution row from `master_institutions.csv` plus a language list.
- **Output.** ~40 candidate URLs per institution (site-restricted plus cross-language generalized variants). Persisted at `runs/<run_id>/<inst>/1_discovery.json`. Fed into Stage 2 (official-site classification) and Stage 3 (URL triage).

## CLI

```bash
python -m g3o discover --institution "City of Helsinki" --languages en,fi --limit 3
```

Returns a JSON list of search results (one record per hit) on stdout.
