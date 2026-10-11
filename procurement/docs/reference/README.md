# `docs/reference/` — pinned copies of instruments owned elsewhere

Read-only. Nothing in this folder is authored by this subproject, and nothing here may be
edited from this subproject.

## `output_contract_v2.0.SNAPSHOT.md`

A verbatim snapshot of the **G3O output contract v2.0**, the root instrument
(`C:\Users\spaci\repos\G3O\g3o\extract\prompts\output_contract.md`). Obtained 2026-08-03.

- SHA-256 (first 32): `9cadb0ce83311c70fb9dd82d8b8fe07b`
- 459 lines, 39 columns, grain (institution × activity × source).

**Verified as the correct instrument** before use — every cross-reference in
`docs/procurement-extension-spec.md` resolves against it:

| Spec reference | Contract location |
|---|---|
| 39 fields, grain (institution × activity × source) | §3.1 + "Total: 39 columns" |
| `source_type` contains `procurement_tender` ("Tender notice, RFP, contract award, vendor selection document") | §4.6, verbatim |
| §7 Edge Case B: procurement award → `internal_operational` / `production` / `Microsoft` / `integrated` / `internal_staff` / `confirms_activity` / `procurement_tender` | Edge case B, all seven values identical |
| B3, B5, C8, D12, D13, D17, D20, D21, E29–E32, E36, E37 | Columns 3, 5, 8, 12, 13, 17, 20, 21, 29–32, 36, 37 |

**If the upstream contract changes, this snapshot is stale.** It is a convenience copy so the
pipeline does not have to re-derive enum members from memory — the repo copy governs. Re-pin it
and re-run `pytest` (the enum tests read this file) whenever the root instrument is revised.

The machine-readable extract of the enums lives in `pipeline/core/contract.py`, copied verbatim
from this snapshot.
