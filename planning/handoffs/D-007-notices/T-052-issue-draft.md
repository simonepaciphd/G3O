# Draft T-052 issue — guarded ingestion, API/history and bulk export

Target: simonepaciphd/g3o-api; proposed owner: Colin.

Status: INTERNAL DRAFT — NOT SENT. PI contract approval is recorded; posting still requires explicit PI instruction after T-050B conformance. Colin acceptance A-019 remains pending. No implementation, migration, database-write, deploy or release authorization is conveyed by this draft.

Approved source: planning/handoffs/D-007-interface-spec.md v1.1 and D-007-field-map.json on local branch planning/r11-rcd009, with RC-D-011 (2026-11-02) superseding S2a's case rule. Lowercase the entire extracted email address (local part and domain) before deduplication; count case-only variants once per actual page. Keep full normalized addresses internal and publish only domain/count pairs. Do not collapse aliases or plus-addresses; supporting quotes remain verbatim. Replace the local source pointer with a verified accessible publication link before sending; no send authorized.

The instrument and storage implementation is local-fixture work until T-030/T-035 bind actual runtime configuration. T-050B compares implemented T-012/T-027 contracts before seeking consumer acceptance. Generated data dictionary owns definitions; the storage map owns physical locations and encodings.

Requested interface:
- The current loader ignores added CSV columns; it must reject unsupported release/interface capabilities BEFORE any DML. Passing local Q2a CSV tests is not evidence of successful old-loader ingestion.
- Validate required mappings, accepted version labels, instrument pointer/provenance, source-claim uniqueness, original observation/relation closure, list/missing-token JSON unions and explicit legacy unavailability. Preserve full supporting text without truncation or delimiter reinterpretation.
- Serve eligible latest institution rows by default and older labelled rows through the existing planned history parameter. Hide new fields where the latest row is v2.5; display its old none result as no with the v2.5 verdict-rule label.
- Release filtering applies to every endpoint, aggregate and bulk export. Only activities on confirms_activity pages are public/count toward tier. Summary unresolved/not_assessable display as unknown without overwriting raw coding.
- Exclude full extracted emails, local artifact paths, internal coder records/distributions and internal-only nested rollup/support items. Keep public domain/count pairs and approved verbatim quotes.
- Preserve correction/wave rules; reject correction reuse of an original run_id; explicitly refresh affected aggregates and verify watermarks.
- Update export_bulk and its tests; link the generated dictionary from the API README. Indices remain withheld.

Required evidence: guarded pre-DML refusal tests, supported-format round trips, hidden-row tests across all public surfaces, history/version display and export tests. Consume T-028 integrated outputs and T-051 reviewed migration. Staging/live DB/deployment steps remain separately gated.
