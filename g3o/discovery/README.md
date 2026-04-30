# `g3o.discovery` — discovery layer

Maps institutions to candidate sources via the Google Search API (Serper).

## Modules

- `serper_client.py` — Serper.dev client with retry + on-disk cache. Falls
  back to mock data when `SERPER_API_KEY` is unset, so the rest of the
  pipeline can be exercised without API credentials.
- `query_builder.py` — turns an institution + a language roster into a list
  of `(query, language)` tuples. Push #1 ships a small term roster covering
  the languages used in the pilot; the multilingual roster will expand
  alongside the master institutions universe.

## CLI

```bash
python -m g3o discover --institution "City of Helsinki" --languages en,fi --limit 3
```

Returns a JSON list of search results (one record per hit) on stdout.
