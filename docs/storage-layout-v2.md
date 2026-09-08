> **Repo copy — authoritative.** Committed in Phase 1 per the 2026-07-28 brief, so the design is versioned with the code it governs. The handoff copy at `RAs/Data Validation Team/` and the drafting copy at `agent-workspace/storage-layout-v2-spec-2026-07-28.md` (both on Drive; neither tracked here) are reference-only from this commit on. Text below is unchanged from the signed-off spec.

# Spec — Pipeline Run-Storage Layout v2 (compression, retention, sharding)

**Status:** SIGNED OFF — PI (Simone), 2026-07-28: all four §9 decisions resolved to the recommended options (gzip `scrape/`+`extract/` only; md5-2hex 256 shards; v2-only readers; `--apply` + tar-verification gate). Implementation assigned to Thomas (Data Validation Team) per `RAs/Data Validation Team/instruction-briefs/2026-07-28 Storage Layout v2 Implementation — Thomas.md`. No implementation started as of sign-off.
**Date:** 2026-07-28
**Author:** agent (claude-fable-5 / claude-code, engineer persona), from PI direction
**Repo:** `G3O` (`C:\Users\spaci\repos\G3O`, github.com/simonepaciphd/G3O)
**Scope:** mitigations 1 (compression + retention) and 2 (sharding) from the 2026-07-28 storage-overhang diagnosis. Mitigation 3 (per-stage JSONL/SQLite restructure) is explicitly **out of scope**.

---

## 0. Summary

The pipeline writes one directory per institution under `runs/<run_id>/`, containing 8+ small JSON files plus one JSON per scraped/extracted page. Fine at pilot scale; at the full 719,588-institution frame one wave is ~720k directories, order 10–20M files, and an estimated 0.4–1.4 TB — with file *count*, not bytes, as the dominant operational cost (NTFS cluster slack, directory-scan walkers, backup/copy throughput).

This spec keeps the per-institution layout (it **is** the crash-recovery/resume mechanism — Session E decisions, `run_state.py`) and attacks the overhang three ways:

- **A. Compress** the bulk artifacts (`scrape/`, `extract/` page JSONs) with gzip — ~5–10× on page text.
- **B. Retention:** a gated `g3o archive` command that tars completed runs' per-institution trees and (only with `--apply`) removes the originals — live file count per finished run drops from ~20M to a few hundred.
- **C. Shard** the institution directories (256-way fanout) and the flat fetcher cache, so no directory ever holds more than a few thousand entries.

Stage-7 CSV outputs, the resume semantics, the attrition ledger, and the Neon ingest contract are all unchanged. Nothing here blocks or touches the backend work (Katon).

---

## 1. Current state (facts, with sources)

### 1.1 Run-tree layout (`docs/architecture.md`; `planning.write_run_layout`)

```
runs/<run_id>/
  manifest.json                     # run-level, small
  _state/                           # batch-chunk state + .done markers (run_state.py)
  attrition.jsonl                   # run-level ledger (common/attrition.py)
  final/                            # Stage-7 CSVs (persist/writer.py)
  <inst_id>/                        # ONE PER INSTITUTION  ← the overhang
    institution.json                # planning.py:80
    1a_discovery_general.json       # stage_discovery.py
    2_official_site.json            # stage_classify.py
    1b_discovery_site_restricted.json
    3_triage.json
    scrape/<url_hash>.json          # one per kept URL — full page text, indent=2 (stage_scrape.py:171)
    extract/<url_hash>.json         # one per page — LLM envelope, indent=2 (stage_extract.py:201)
    6_validate.json                 # consolidate.py:228, indent=2
    _timing.json                    # common/timing.py
```

`inst_id` = `synth_institution_id(row)` = `INST-{int(master_row_id):07d}` with a non-numeric fallback `INST-{raw}` (`run/presweep/records.py:13-19`). **Note:** the institution-key spec drafted 2026-07-28 (`agent-workspace/institution-key-spec-2026-07-28.md`; Drive, not tracked here) demotes `master_row_id` and introduces a stable master key; the shard scheme below is deliberately agnostic to the ID's internal structure.

### 1.2 Fetcher cache

Flat, unsharded: `cache/page_v2_<md5(url)>.json`, compact JSON, atomic temp+`os.replace` writes (`scrape/fetcher.py:74-120`). One file per unique URL ever fetched, shared cross-run. At full-frame scale this directory alone reaches millions of entries in a single folder.

### 1.3 Duplication

Page content is stored twice: once in the global cache, once in the per-run `scrape/<url_hash>.json` (per-run copy is the Q5=a resume guard, `stage_scrape.py:188-195` docstring). This spec keeps the duplication (both copies are load-bearing) but compresses the per-run copy; a cache-side gzip is included in Phase 4.

### 1.4 Every site that constructs or walks institution paths (migration inventory)

Constructors of `run_dir / inst_id`:

| Site | Ref |
|---|---|
| `planning.write_run_layout` | `planning.py:78` |
| `stage_scrape._read_existing_scraped`, `_scrape_one` | `stage_scrape.py:34,104` |
| `stage_extract._persist`, `_count_existing_extracts` | `stage_extract.py:199` |
| `validate/consolidate.py` | `:198,224,242` |
| `common/timing.py` | `:46` |
| `report/outcomes.py` | `:145` |

Directory-scan walkers (`run_dir.iterdir()`, currently filtering out `_`-prefixed / `.done` / `final` by name):

| Site | Ref |
|---|---|
| `persist/writer.load_consolidated_outputs` | `writer.py:101` |
| `report/health.py` | `:313,666` |
| `report/diff.py` | `:116` |
| `validate/qc.py` | `:281` |

Existence/glob checks that must learn the `.json`/`.json.gz` duality (Phase 2):

- `stage_scrape.py:130-137` (per-URL resume: `output_path.exists()` → load)
- `stage_scrape._read_existing_scraped` (`glob("*.json")`)
- `stage_extract._count_existing_extracts`
- all `scrape/`/`extract/` readers in `consolidate.py`, `report/outcomes.py`, `report/health.py`, `report/diff.py`

### 1.5 Scale math (planning envelope, estimates — no live full run exists to measure)

| Quantity | Value | Basis |
|---|---|---|
| Institutions (full frame) | 719,588 | master CSV, rebuilt 2026-07-13 |
| Files per institution | ~28 (8 fixed + 2×~10 pages) | layout above, ~10 kept URLs/inst |
| Files per full wave | ~20M | product |
| Bytes per institution | ~0.5–2 MB | tens-of-KB page texts × ~10, indent=2 |
| Bytes per full wave | ~0.4–1.4 TB | product |
| NTFS cluster slack | ≥4 KB × every small file | 4 KB default cluster |

---

## 2. Goals / non-goals

**Goals**

1. A full-frame wave's *live* footprint after completion: ≤ a few hundred filesystem objects and ~60–250 GB (post-gzip, post-archive).
2. No directory anywhere in the tree with more than ~5,000 entries at any point during a run.
3. Zero change to: resume semantics (file-existence = done), Stage-7 CSV schemas, attrition ledger, batch-chunk state machinery, the Neon ingest contract.
4. Every phase independently committable, testable, and revertible.

**Non-goals**

- No per-stage JSONL/SQLite consolidation (mitigation 3 — revisit only with evidence from a real large run).
- No Postgres writer in the pipeline (Stage-7 CSV remains the backend contract; `persist/README.md` decision stands).
- No migration tooling for legacy run layouts (see §5.2 — no live production runs exist to migrate).
- No change to what is *collected or extracted* — this is storage plumbing only, no research-substantive change.

---

## 3. Design — Part A: compression + retention

### A1. Gzip the bulk artifacts

**Scope:** `scrape/<url_hash>.json` and `extract/<url_hash>.json` only — these carry the page text and dominate bytes. The small per-institution stage files (`institution.json`, `1a/1b/2/3`, `6_validate.json`, `_timing.json`) stay plain, indented JSON: they are what a human opens during QC, and their bytes are noise once A3 archives them.

**Mechanism:** new module `g3o/common/artifact_io.py`:

```python
ARTIFACT_SUFFIX = ".json.gz"

def write_artifact(path: Path, text: str) -> None
    # path given WITHOUT suffix decision; writes <path>.gz via
    # gzip.GzipFile(fileobj=..., mode="wb", mtime=0, compresslevel=6)

def read_artifact(path: Path) -> str
    # accepts either <name>.json or <name>.json.gz; .gz wins if both exist

def artifact_exists(path: Path) -> bool
def glob_artifacts(dir: Path) -> list[Path]   # *.json + *.json.gz, deduped by stem
```

- `mtime=0` pins the gzip header timestamp → byte-identical output for identical input (protects `test_reproducibility_regression.py` and any future output hashing).
- `compresslevel=6`: default speed/ratio balance; page text compresses ~5–10× at any level ≥4.
- `indent=2` is **dropped** for the two gzipped artifact classes (compact JSON; the indent is pointless under gzip and costs decompress-side bytes). All other `indent=2` sites are untouched.
- Writes keep current atomicity semantics (single-writer per institution in the run tree — plain write is acceptable as today; the cache keeps its temp+`os.replace` pattern).

**Read-side duality:** every reader in §1.4 goes through `read_artifact`/`glob_artifacts`, so a run that crashed mid-upgrade (or a dev tree with mixed files) still reads. The resume guard in `stage_scrape.py:130` checks `artifact_exists` so a pre-upgrade partial run resumes rather than re-scrapes.

### A2. Retention: `g3o archive`

New CLI subcommand (`cli.py`):

```
python -m g3o archive --run-dir runs/<run_id> [--apply]
```

**Preconditions (refuse loudly if unmet):**
1. `runs/<run_id>/final/` contains the Stage-7 CSVs.
2. `_state/.done/` holds a marker for every stage in `g3o.run.presweep.STAGES`.
3. Run-level reports (`report/run_summary.py`, health) already written — archival is strictly the *last* operation on a run; reports read the live tree.

**Behavior:**
- Tars each shard directory (§B1) to `runs/<run_id>/archive/institutions/<shard>.tar` — plain tar, **no outer compression** (members are already gzipped where it matters; double compression wastes CPU for ~0 gain).
- **Verify before any delete:** re-open each tar, compare member count and total member bytes against a fresh walk of the source shard. Mismatch → abort, delete nothing, keep the bad tar with a `.FAILED` suffix.
- **Dry-run by default:** without `--apply`, print the plan (shard count, file count, byte totals, projected tar sizes) and exit. With `--apply`, delete each source shard directory only after its tar verifies. This mirrors the RLCR `apply_changeset.py` discipline and the project's archive-don't-delete rule (the data is archived in place, not deleted).
- **Idempotent/resumable:** a shard whose tar already exists and verifies is skipped; re-running after an interruption finishes the remainder.
- Run-level files (`manifest.json`, `_state/`, `attrition.jsonl`, `final/`, reports) are never archived — they stay live.

**Restore:** documented as plain `tar -xf archive/institutions/<shard>.tar -C <run_dir>/institutions/` in `docs/operations.md`. No restore code in v1.

**Effect:** a completed full-frame run's live tree = run-level files + ≤256 tars.

---

## 4. Design — Part B: sharding

### B1. Run-tree fanout

New layout (bumps to **layout v2**):

```
runs/<run_id>/institutions/<shard>/<inst_id>/...
```

- **`institutions/` level:** cleanly separates institution dirs from run-level entries, replacing the fragile name-based filtering in the four walkers (`startswith("_")`, `== ".done"`, `== "final"`).
- **Shard function:** `shard = md5(inst_id.encode())[:2]` (hex) → 256 shards, ~2,811 institution dirs per shard at full frame. Chosen over a numeric bucket (`master_row_id // 1000`) because it is **agnostic to the ID scheme** — the pending institution-key spec (2026-07-28) will change how institution IDs are derived, and md5-of-string survives that untouched. Deterministic from `inst_id` alone, so every constructor site in §1.4 computes it without needing the master row.

New module `g3o/common/paths.py` — the **single owner** of layout knowledge:

```python
LAYOUT_VERSION = 2

def institution_dir(run_dir: Path, inst_id: str) -> Path
def iter_institution_dirs(run_dir: Path) -> Iterator[Path]   # sorted, two-level walk
def require_layout(run_dir: Path) -> None                    # raises on missing/≠2 marker
```

All ten constructor/walker sites in §1.4 migrate to these three functions. No other module may build an institution path by hand (enforced by a grep-based unit test asserting no `run_dir / inst` patterns outside `paths.py`).

### B2. Layout version marker

`planning.write_run_layout` writes `"layout_version": 2` into `manifest.json`. `require_layout` is called at the entry of: the presweep orchestrator, `persist.write_run_csvs`, and every report generator. A run dir with no manifest or `layout_version != 2` fails loudly, naming this spec.

**No dual-layout read support.** Justified: the chunked-state machinery notes the pipeline "has never executed live" at scale (`run_state.py:110-118` rationale), and the only extant artifacts are small dev/test runs. Any needed legacy run is read by checking out a pre-v2 commit. This keeps every reader simple — the alternative (both layouts everywhere) doubles the test matrix permanently for zero production benefit.

### B3. Cache fanout (+ gzip)

- New path: `cache/<md5[:2]>/page_v2_<md5>.json.gz` — same 256-way fanout, same key.
- `_cache_path` is the single constructor (`fetcher.py:78`); `_load` gains a read fallback to the legacy flat path (`cache/page_v2_<md5>.json`) so existing cache entries stay warm; writes go sharded-gzipped only. No migration script — the flat remainder ages out naturally (current cache: 1 file).
- Cache writes keep the temp+`os.replace` atomic pattern and the `min_chars` floor exactly as today (`fetcher.py:82-120`); only the path and the byte encoding change.

---

## 5. Sequencing — four phases, each one commit/PR, each revertible

| Phase | Content | Touches | Risk |
|---|---|---|---|
| **1** | `paths.py`, shard fn, `institutions/` level, layout marker, migrate all §1.4 sites, update walkers | ~11 modules + tests | Mechanical; the walker name-filter removal is the one behavioral edge — covered by `test_persist`, `test_health_report`, `test_run_diff`, `test_e2e_presweep_smoke` |
| **2** | `artifact_io.py`, gzip `scrape/`+`extract/`, drop their `indent=2`, read-side duality, resume-guard update | `stage_scrape.py`, `stage_extract.py`, readers in §1.4 | Reproducibility tests may pin exact bytes/paths — update goldens under `tests/goldens/` deliberately, never blindly |
| **3** | `g3o archive` subcommand + `docs/operations.md` section | `cli.py`, new `g3o/run/archive.py` | Only phase with a delete path; gated by `--apply` + tar verification |
| **4** | Cache fanout + gzip + legacy-flat read fallback | `scrape/fetcher.py` | Independent of 1–3; smallest |

Docs updated in the same PRs: `docs/architecture.md` (layout table), `docs/replication.md` if it references paths, and — drive-by, flagged here for transparency — `g3o/persist/README.md`, which is stale (says "two CSVs"; the writer emits three).

Order matters only for 1→2→3 (2 writes into the layout 1 defines; 3 tars what 1+2 produce). 4 can land any time.

Per standing policy (engineer-log 2026-06-11): before the first live run on the new layout, a full-path smoke run on a tiny sample (~20 institutions, mock/live-cheap settings) through all stages **including `persist` and `archive --apply` on the smoke run itself**.

---

## 6. Testing plan

New tests:
- `test_paths.py` — shard determinism/spread, `iter_institution_dirs` ordering, `require_layout` refusal on missing/wrong marker, grep-guard against hand-built institution paths.
- `test_artifact_io.py` — round-trip, `.json`/`.json.gz` duality (gz wins), byte-identical output for identical input (mtime=0), `glob_artifacts` dedup.
- `test_archive.py` — dry-run deletes nothing; `--apply` only after verification; verification failure aborts with `.FAILED` tar and intact source; idempotent re-run; precondition refusals (missing `final/`, missing `.done` marker).
- `test_fetcher.py` additions — sharded write path, legacy flat-path read fallback, atomicity pattern preserved.

Existing suite: `test_e2e_presweep_smoke`, `test_presweep`, `test_persist`, `test_health_report`, `test_run_diff`, `test_scrape`, `test_reproducibility_regression` all exercise the layout and will catch regressions; expect fixture/golden updates in Phases 1–2 (reviewed, not rubber-stamped).

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Golden/fixture churn masks a real regression | Update goldens in a separate commit within the PR, diff reviewed line-by-line |
| Institution-key spec changes `inst_id` derivation mid-flight | md5-of-string shard is derivation-agnostic; `paths.py` is the only coupling point |
| `archive --apply` deletes on a bad tar | Verification precedes any delete; abort-on-mismatch; dry-run default |
| Mixed plain/gz trees during transition | Read-side duality (A1) everywhere; writers emit one format only |
| gzip header nondeterminism breaks reproducibility hashes | `mtime=0` pinned in one place (`artifact_io.py`) |
| Windows `os.replace` contention (known, `fetcher.py:107-112`) | Pattern unchanged; sharding *reduces* per-directory contention |

---

## 8. Projected effect (full-frame wave, estimates)

| Metric | Today (projected) | After A+B |
|---|---|---|
| Live files, run in progress | ~20M | ~7M (gzip doesn't cut count; sharding caps per-dir) |
| Live files, run completed+archived | ~20M | ~300 (run-level files + ≤256 tars) |
| Max entries in any one directory | 719,588 | ~2,811 |
| Bytes per wave | ~0.4–1.4 TB | ~60–250 GB |
| Fetcher cache | millions, flat | 256-way fanout, gzipped |

---

## 9. Open decisions for PI sign-off

1. **Gzip scope** — recommended: `scrape/` + `extract/` only (§A1). Alternative: gzip all per-institution JSONs (more bytes saved, worse QC ergonomics, same file count).
2. **Shard scheme** — recommended: md5-2hex, 256 shards (§B1), for key-spec agnosticism. Alternative: numeric `master_row_id` buckets (human-navigable, ordered — but breaks if the key spec lands non-numeric IDs).
3. **Legacy layout posture** — recommended: v2-only readers with loud refusal (§B2). Alternative: dual-layout read support (permanent complexity for no production artifact).
4. **Archive deletion gate** — recommended: `--apply` flag + tar verification (§A2). Confirm this satisfies the project's archive-don't-delete rule (the content is preserved in the tar, in place). Off-workstation archival of the tars (NAS/cold storage) is a separate, later decision.

On sign-off: spec moves to repo `docs/` (versioned with the code it governs), phases implemented in order, each behind its own PR.
