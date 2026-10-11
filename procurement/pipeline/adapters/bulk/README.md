# Bulk adapters

`access_mode = bulk` (23 sources). Downloadable files instead of a live API.

## Add a source
1. Copy `_template.py` → `<source_id>.py`; implement `search()` (+ usually pass-through `fetch()`).
2. OCDS release packages → core OCDS extractor handles `extract()`; else override.
3. Register in `config/sources.yaml` (`bulk.format`, release index URL).
4. Smoke-test on a small slice before processing full files.

## Per-source checklist (record in tracker `notes_RA`)
- File format(s): CSV / JSON / XML / ZIP / OCDS release package.
- Where the files are listed (release index page/endpoint); update cadence.
- File sizes — stream-parse large files; don't load fully into memory.
- Is it OCDS? If yes, reuse the core OCDS extractor.
- Encoding / delimiter / schema quirks.

Prefer OCDS bulk releases first — same standardizer as OCDS API sources.
