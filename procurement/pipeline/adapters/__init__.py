"""Per-source adapters, grouped by access type (api / bulk / scrape).

To add a source: copy the type's `_template.py` to `<source_id>.py` and fill in
`search` + `fetch` (and `extract` if the source is not OCDS). Everything else is
inherited from the shared core.
"""
