# `g3o.scrape` — Stage 4: retrieval + content extraction

Stage 4 of the seven-stage pipeline (see [`docs/architecture.md`](../../docs/architecture.md)). HTTP fetch with retry/backoff, on-disk caching by URL hash, and content-type routing between HTML, PDF, and a headless-browser fallback for JS-heavy pages.

## Modules

- `fetcher.py` — `scrape_url(url)` is the single entrypoint. Downloads once, sniffs the body (`%PDF-`, OOXML DOCX) before trusting headers, routes to `html`/`pdf`/`docx`/`render`, caches on disk under `config.CACHE_DIR`.
- `html.py` — text + link extraction with structural-noise stripping, plus `check_keyword_proximity()` used as a relevance filter.
- `pdf.py` — pdfplumber-backed text and link extraction (annotation URIs and regex-recovered URLs).
- `docx.py` — standard-library (`zipfile` + XML) DOCX text extraction from `word/document.xml` (T-065).
- `readability.py` — the R-015 readability check (binary markers, letters < 10%) on extracted or stored text; returns a failure reason, sets nothing.
- `render.py` — Playwright-backed headless adapter for JS-shell pages where `requests` returns near-empty text. Triggered by the fetcher when the static HTML pass yields below a configurable text threshold.

## Inputs and outputs

- **Input.** A list of URLs from Stage 3 (URL triage), each with the institution it belongs to.
- **Output.** Per URL, a normalized `{url, text, title, content_type, fetch_metadata, success}` record persisted at `runs/<run_id>/<inst>/4_scrape/<url_hash>.json`. Fed into Stage 5 (extract).

## CLI

```bash
python -m g3o scrape --url https://example.com
```
