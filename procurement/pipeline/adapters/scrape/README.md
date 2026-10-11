# Scrape adapters

`access_mode = scrape` (94 sources — the largest group). Web pages only.

## Add a source
1. Copy `_template.py` → `<source_id>.py`; implement `search()`, `fetch()`, `extract()`.
2. These are non-OCDS → `extract()` (HTML parsing via `field_map`) is required.
3. Register in `config/sources.yaml` (`scrape.*`, `field_map`).
4. Smoke-test on a few pages before scaling.

## Legality & politeness (do this BEFORE scaling — record in tracker `notes_RA`)
- Read robots.txt and the site's terms of service.
- Set a polite delay (`scrape.polite_delay_s`) and a clear User-Agent.
- Respect rate limits; back off on errors; never hammer a portal.
- Note login walls, geoblocking, CAPTCHAs, language — if a site blocks
  automated access, flag it and move on (may become a `manual` case).

## Efficiency
Group the 94 sources by **portal family / platform** — many countries run the
same underlying software. One adapter for a platform can often be parameterized
across several sources.
