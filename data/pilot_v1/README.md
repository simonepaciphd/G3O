# Pilot v1

Pilot dataset that backs the public website
[`g3o-website`](https://github.com/simonepaciphd/g3o-website). It is a
**snapshot, not a panel**: collected once between January and March 2026,
prior to the API-driven production pipeline that lands in Push #2 of this
repository.

## Files

| File                                    | Rows  | Description                                                   |
|-----------------------------------------|-------|---------------------------------------------------------------|
| `g3o_full_database_v1.csv`              | 1,336 | One row per `(institution × activity × source)` triple.       |
| `g3o_institution_summary_v1.csv`        |   917 | One row per institution with rolled-up activity and tools.    |
| `merge_qc_summary.txt`                  |   —   | Per-source row counts and blank-required-field QC at merge.   |

The schema for `g3o_full_database_v1.csv` is documented in
[`../../docs/data_dictionary.md`](../../docs/data_dictionary.md). The
schema-of-record is the G3O Output Contract at
[`../../g3o/extract/prompts/output_contract.md`](../../g3o/extract/prompts/output_contract.md).
This snapshot was produced under contract **v2.0**; the live contract has since
moved to v2.2. Both changes since (`proposed` on the `adoption_stage` ladder,
`unknown` on `activity_type`) were additive, so no value in this file became
invalid — but the file was not coded under the current contract.

## How it was built

Pilot v1 was assembled from four upstream components, then merged with
conservative dedup rules:

1. **ChatGPT-web pilot (`pilot_web`, 485 rows).** Manual GenAI-search
   prompts run against ChatGPT with web-search enabled, applied to ~485
   institutions sampled from the institution master. Model:
   `GPT-5.4-thinking-web` (run label).

2. **Research-assistant validation samples (`ra_amber`, `ra_ella`,
   `ra_litong_aut`, `ra_litong_dem` — 276 rows total).** Independent
   human extractions on subsets of the same institutions, used as a
   sanity check on the automated pilot.

3. **Harmonized existing databases (`existing_pstw`, `existing_us_federal`,
   `existing_gpt_convenience`, `existing_policy_lab` — 575 rows total).**
   Public inventories from the European Commission's Public Sector Tech
   Watch (PSTW), the U.S. Federal AI Use Case Inventory, the Policy
   Innovation Lab catalogue, and an opportunistic GenAI-in-government
   convenience sample. These were re-coded into the G3O schema and
   joined to the institution master.

4. **Merge.** Rows from all four were vertically appended and
   deduplicated by `institution_id × activity × source_url`, with
   uncertainty flags propagated forward.

Per-source counts in `merge_qc_summary.txt`.

## Caveats

- **Not the production pipeline.** This dataset predates the API-driven
  pipeline described in the paper. Coverage is biased toward the
  ChatGPT-web pilot's batching strategy; multilingual recall is uneven;
  some sources are stale.
- **Coverage is small.** 917 institutions out of an institutional universe
  on the order of ~675,000. Treat this dataset as illustrative of what the
  pipeline can recover at small scale, not as a complete enumeration.
- **Pre-existing harmonization will be re-done.** The harmonized existing
  databases were produced by a one-off cleaner that is not part of this
  repo. Push #2 will run the same sources through the production
  pipeline; v2 will supersede v1.
- **Schema additions.** Pilot v1 has been retrofitted into the v2.0
  schema. Some fields that were not collected at pilot time appear as
  `unknown` or `_NA_`.

## Citing

```
Paci, Simone, Lowry Pressly, and Nathan Feldman. 2026.
"G3O — Global Government GenAI Observatory." Pilot dataset v1.
https://github.com/simonepaciphd/G3O.
```

License: [CC-BY 4.0](../LICENSE).
