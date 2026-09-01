# `data/` — published G3O datasets

Datasets published from this repository. Released versioned and immutable.
A new version is a new directory; existing files are never overwritten.

## Versioning

**File releases are named for the pipeline wave they correspond to**, so that a
directory here and the version reported by the API name the same thing. The
archived pilot predates that scheme and keeps its original name.

| Path              | What it is                                                       |
|-------------------|------------------------------------------------------------------|
| `pilot_v1/`       | Archived pilot snapshot, ~1k institutions. ChatGPT-web + RA samples + harmonized existing DBs. Superseded; retained for provenance. |
| `w001/` *(future)* | First published release from the API-driven production pipeline; corresponds to wave `w001`, the wave the live API currently serves. |

The full institutional universe (719,588 institutions) is built in a
separate workflow and will be released alongside the first production
dataset. It is intentionally **not** included in `data/pilot_v1/`.

## License

All files under `data/` are released under [CC-BY 4.0](LICENSE) unless
explicitly noted. Attribution required; downstream uses welcome.

## Schema

The data dictionary is at [`../docs/data_dictionary.md`](../docs/data_dictionary.md).
The schema-of-record is the G3O Output Contract at
[`../g3o/extract/prompts/output_contract.md`](../g3o/extract/prompts/output_contract.md).
