# API adapters

`access_mode = api` (33 sources; prioritize the OCDS ones).

## Add a source
1. Copy `_template.py` → `<source_id>.py` (e.g. `chl_mercadopublico.py`).
2. Keep the class named `Adapter`; implement `search()` and `fetch()` (the CLI imports that exact name).
3. OCDS source → don't touch `extract()` (core OCDS extractor handles it).
   Non-OCDS → override `extract()` with a field map.
4. Register the source in `config/sources.yaml`.
5. Smoke-test on a small sample (`tests/`) before a full pull.

## Per-source checklist (record in the tracker `notes_RA` column)
- Endpoint + docs (Swagger/OpenAPI) URL; is it OCDS?
- Auth: none / API key / OAuth (key goes in `config/secrets.yaml`, never in code).
- Pagination style (page / cursor / offset) and page size caps.
- Rate limits; set `rate_limit_per_min` in the source config.
- Does the API support keyword search (pushdown) or must we filter locally?

## OCDS shortcut
If OCDS, most work is base URL + pagination + auth. Once the first OCDS-API
source works, cloning to the other OCDS sources is largely a URL swap.
