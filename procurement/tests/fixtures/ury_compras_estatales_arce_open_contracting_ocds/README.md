# `ury_compras_estatales_arce_open_contracting_ocds` — REAL fixtures (n=100 probe)

101 **real OCDS release packages**, fetched live 2026-09-15 from Uruguay's ARCE
endpoint via the real, unmodified `pipeline.cli` (`--limit 100 --allow-unverified`),
in a Desktop-only test session (`~/Desktop/G3O-Procurement-Pipeline-Status/uruguay-funnel-analysis-TEST/n100-run/`,
see that folder's `funnel_report_n100.md` for the full write-up). Nothing in that
session wrote to Drive; these payloads were copied into Drive on 2026-09-19.

**Supersedes** the original 2026-08-29 hand-picked 5-record set, which is
archived (not deleted, G3O rule 6) at
`archive/ury_fixtures_n5-superseded-2026-09-19/`.

## What this set actually is

Not a random or representative sample of Uruguay's procurement activity —
it's whatever a bounded, `--limit 100` pull of the live RSS index returned,
in index order, unfiltered. Unlike the old 5-record set, nothing here was
hand-picked for shape diversity; the diversity (tenders, awards, clarification
notices, adjustment notices, sparse and populated records alike) is whatever
naturally showed up in that window.

**Discrepancy, resolved 2026-10-07:** the CLI's run report says 100 records
fetched; this directory holds 101 files. The extra file, `adjudicacion-1370285.json`,
was fetched and cached by the adapter, then discarded, because `Pipeline.run()`
checked `--limit` only after pulling the next payload. Fixed in
`pipeline/core/base.py`. Full row-to-payload mapping:
`outputs/diagnostics/uruguay-n100-2026-09-15/reconciliation/`.

## Why this replacement happened

The n=100 run's own analysis (`funnel_report_n100.md`, Desktop-only) found that
the shared `extract_ocds()` (`pipeline/core/standardize.py`) never reads
`awards[].items[]` — only top-level `tender`/`award` `title`/`description`/`value`.
For this source those top-level fields are empty on the large majority of
records, while real item-level text and values (e.g. `"TIMBRE PROFESIONAL"`,
`170.0 UYU`) sit one level deeper, invisible to both the classifier and the
extension table's money field. That finding was verified independently against
this same cached data before this fixture swap. **This fixture replacement does
not fix that gap** — `extract_ocds()` is untouched. It only gives the test
suite a larger, more realistic sample of the sparsity the fix will need to
handle. The fix itself (whether/how to fold `items[]` into the extractor) is
still open — see `funnel_report_n100.md`'s "What I'd recommend" section.

## Do not

Load these into the master, quote them as evidence, or treat them as a
recall/precision/prevalence sample. They are a bounded plumbing/QC probe's
raw output, not a designed sample.
