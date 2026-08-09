# `data/` — published G3O datasets

Datasets published from this repository. Released versioned and immutable.
A new version is a new directory (`pilot_v1/`, `v1/`, `v2/`, …); existing
files are never overwritten.

## Versioning

| Path             | What it is                                                       |
|------------------|------------------------------------------------------------------|
| `pilot_v1/`      | Pilot snapshot, ~1k institutions. ChatGPT-web + RA samples + harmonized existing DBs. |
| `v1/` *(future)* | First release from the API-driven production pipeline (Push #2). |

The full institutional universe (~675,000 institutions) is built in a
separate workflow and will be released alongside the first production
dataset. It is intentionally **not** included in `data/pilot_v1/`.

## License

All files under `data/` are released under [CC-BY 4.0](LICENSE) unless
explicitly noted. Attribution required; downstream uses welcome.

## Schema

The data dictionary is at [`../docs/data_dictionary.md`](../docs/data_dictionary.md).
The schema-of-record is the G3O Output Contract (currently v2.2) at
[`../g3o/extract/prompts/output_contract.md`](../g3o/extract/prompts/output_contract.md).
