# `_ocds_sample` — SYNTHETIC fixtures

These three OCDS releases are **hand-written test data, not real procurement records.**
Buyers, suppliers, ids, and URLs are invented (`example.org` / `example.test` domains,
which are reserved and resolve nowhere). Nothing here may be loaded into the master,
quoted as evidence, or copied into `sources.yaml`.

They exist to exercise the core offline, before any source is touched:

| File | Exercises |
|---|---|
| `award_relevant.json` | Award branch: awarded value, supplier, contract period, buyer identifiers, a clear generative-AI term → `yes` / `confirms_activity`. |
| `tender_ambiguous.json` | Tender branch: estimated value, framework flag, a context-required product name only → `unclear` / `ambiguous` + `genai_vs_traditional_ai`. |
| `award_irrelevant.json` | Negative control: ordinary IT procurement, no GenAI signal → `confirms_absence` on this row, per contract Edge Case A (a read source carrying no GenAI mention). What it does **not** settle is the institution-level `has_genai_activity` (column 8), which needs every source for that institution. |

The leading underscore keeps this directory out of the `tests/fixtures/<source_id>/`
namespace — real per-source fixtures go in folders named after their actual source.

When the first live OCDS source is picked, drop a handful of its **real** payloads in
`tests/fixtures/<source_id>/` and point the smoke test at those. These stay as the
core's own regression fixtures.
