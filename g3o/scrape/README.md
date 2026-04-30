# `g3o.scrape` — retrieval + content extraction

HTTP fetch with retry/backoff, on-disk caching by URL hash, and content-type
routing between HTML and PDF.

## Modules

- `fetcher.py` — `scrape_url(url)` is the single entrypoint. Downloads once,
  routes to `html`/`pdf`, caches on disk under `config.CACHE_DIR`.
- `html.py` — text + link extraction with structural-noise stripping,
  plus `check_keyword_proximity()` used as a relevance filter.
- `pdf.py` — pdfplumber-backed text and link extraction (annotation URIs
  and regex-recovered URLs).

## CLI

```bash
python -m g3o scrape --url https://example.com
```
