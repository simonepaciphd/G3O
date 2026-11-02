# T-012 chunk 1 — enum, contract and version touchpoint inventory

Card: T-012 (PLAN.md `### T-012`), chunk 1 of 2. Inventory only; no code changed.
Prepared by: engineer lane eng-b (Claude Code, model claude-opus-5-5), 2026-10-31.
Base: G3O `origin/main` `a5b1d30` (includes T-013 `g3o/codebook/` and signed `codebook/codebook.yaml`, sha256 `f0b1348c…c72f`). Branch `reclass/t012-enums`, worktree `C:/Users/spaci/worktrees/G3O-eng-b-t012/`.
External repos read-only, local HEADs as found (no fetch): g3o-api `main` `acdb030`; g3o-website `main` `f6f627d`; procurement worktree `C:/Users/spaci/repos/g3o-wt-procurement` on `procurement/main` `fa04e59` (2026-10-27).

Owner column: a proposal only. The integrator assigns (PLAN T-012 "Chunking trigger"). "Unassigned" means no card's write claim names the file; the alternatives are listed. "Gen" = generated from the codebook (T-013 generators) or a generator target.

## 1. Reproducible grep patterns

Run from the repo root. G3O excludes `planning/` (governance, integrator-only).

| Key | What it finds | Pattern (`git grep -n -E '<pattern>' -- . ':!planning'`) |
|---|---|---|
| A | v2.5 page-verdict column / type | `genai_evidence\|GenAIEvidence\|genai-evidence` |
| B | the 4 v2.5 values | ``confirms_absence\|[`'"]ambiguous[`'"]\|confirms_activity\|background_only`` |
| C | NoNA enum mirrors | `NoNA\b` |
| D | column lists | `\b(PILOT_V1_)?DATA_COLUMNS\b\|\bACTIVITY_COLUMNS\b\|\bACTIVITY_SOURCE_COLUMNS\b\|\bINSTITUTION_REPORT_COLUMNS\b\|\bSUMMARY_COLUMNS\b\|\bCONTRACT_COLUMNS\b` |
| E | contract / version plumbing | `contract_version\|CONTRACT_VERSION\|contract_pin\|output_contract\|validate[-_]contract\|extract[-_]contract\|contract_surface\|parse_version\|Contract v[0-9]` |
| G | CX columns (incl. the existing `reported_*` columns CX-60/61 reshape) | `disclosure_form\|disclosure_scope\|evaluation_documented\|evaluation_type_\|content_contact\|content_data\b\|reported_outcomes\|reported_incidents\|outcome_kind\|incident_kind\|\bCX-[0-9]` |
| H | v2.7 fields (release label, setup pointer, channel, labels) | `evidence_channel\|codebook_release\|CODEBOOK_RELEASE\|release_label\|setup_pointer\|text_source\|verdict_rule\|page_verdict\|not_assessable` |
| I | pins | `contract_version_pin\|reproducibility\.json\|goldens/` |

External repos (g3o-api, g3o-website, procurement): one combined pattern, `git grep -c -E` from each repo root:

```
genai_evidence|GenAIEvidence|confirms_absence|confirms_activity|background_only|NoNA\b|contract_version|CONTRACT_VERSION|output_contract|DATA_COLUMNS|ACTIVITY_COLUMNS|ACTIVITY_SOURCE_COLUMNS|SUMMARY_COLUMNS|evidence_channel|codebook_release|setup_pointer|disclosure_form|disclosure_scope|evaluation_documented|reported_outcomes|reported_incidents|extract_version|validate_version|prompt_version|\bcontracts\b
```

(`\bcontracts\b` catches g3o-api's `runs.contracts` JSONB; procurement was grepped without it, under `-- procurement`.)

## 2. Counts

| Repo | Files matched | Of which false positives | Notes |
|---|---|---|---|
| G3O (this worktree) | 80 | 3 | 77 real: 46 code/prompt/test files (21 `g3o/` modules outside `g3o/codebook/`, 1 script, 4 prompt documents, 20 test modules); 13 codebook/T-013 files; 6 frozen data files; 12 docs, READMEs, fixtures and pin files. The review's "~34" (PF-014) does not match any cut of this list I could reproduce; the nearest is the 46 code/prompt/test files. |
| g3o-api | 16 | 1 | `worker/src/index.js:6` hits `contracts` in a doc path only (the file is still real through lines 1107/1132) |
| g3o-website | 31 | 0 | 6 live (`src/`, `docs/`); 21 under `planning/` (index-design notes, pilot scripts and JSON); 4 under `pilot-website-archive/` (archived) |
| procurement | 23 | 0 | 14 code/config/test/reference; 9 under `procurement/planning/` |

## 3. G3O — files, references, proposed owner

Line refs are at `a5b1d30`. Letters are the pattern keys above.

### 3.1 Core constants (T-012 write claim)

| Path | Lines | Reference held | Proposed owner | Gen? |
|---|---|---|---|---|
| `g3o/common/contract.py` | A/B 33,37,168-170 (`GenAIEvidence` 4-value `Literal`, the only Python copy), 294, 324 (`ContractRow.genai_evidence`), 333-344 (row rule: Group D `_NA_` unless `confirms_activity`), 395, 414-423 (batch rule vs `has_genai_activity`), 672 (`SourceRecord.genai_evidence`), 703-778 (Stage 6 validators: `confirms_activity`/`confirms_absence`); C 521-554 (7 NoNA aliases), 596-609 (use in `ConsolidatedActivity`); D 12, 27-28, 482-494, 853-899 (`to_csv_dict` against `DATA_COLUMNS`/`ACTIVITY_COLUMNS`/`ACTIVITY_SOURCE_COLUMNS`); E 8, 30 (docstring cites `output_contract.md`); G 231-232, 310-311, 610-611, 622 (`reported_outcomes`/`reported_incidents`) | T-012 (sole owner per card) | target of `generated/enums.py` and `generated/item_schemas.json` (manifest: "T-012 enum constants", "T-012 JSON schema") |
| `g3o/common/schema.py` | D 32-77 `DATA_COLUMNS` (`genai_evidence` at 70), 79-127 `ACTIVITY_COLUMNS`, 129-157 `ACTIVITY_SOURCE_COLUMNS` (`genai_evidence` at 152), 159-194 `INSTITUTION_REPORT_COLUMNS`, 196-227 `SUMMARY_COLUMNS`; B 17, 140 (docstrings); G 60-61, 120-121 | T-012 | no |
| `tests/test_schema_consistency.py` | see §7 | T-012 | no |

Note on "both enum copies": inside G3O the 4-value enum has one Python definition (`contract.py:168-170`), used by both the Stage 5 `ContractRow` and the Stage 6 `SourceRecord`. It has no NoNA variant. The NoNA mirrors (`contract.py:521-554`) copy the activity enums (`ActivityType`, `AdoptionStage`, `AccessType`, `InteractionType`, `DeploymentMode`, `TargetUsers`, `GovernanceFlag`), not the page verdict. The other copies of the 4 values are prose (§3.3) and procurement's tuple (§6).

### 3.2 Version / pin plumbing

| Path | Lines | Reference held | Proposed owner | Gen? |
|---|---|---|---|---|
| `g3o/common/contract_pin.py` | D 49-52 `GATED_COLUMN_LISTS`; E 39-44 contract paths, 56-63 `parse_version` (reads `vX.Y` from the contract H1), 65-80 `literal_enums` (discovers every `Literal` in `contract.py`), 94-138 `contract_surface` | **Unassigned.** Alternatives: T-012 (contract constants) or T-035 (pins) | no |
| `tests/goldens/contract_version_pin.json` | E 3, 8 (`v2.5`, `v1.3` + surface hashes) | T-035 (pin file) | no |
| `tests/goldens/reproducibility.json` | (no pattern hit; holds prompt job-line hashes) | T-035 (pin file) | no |
| `tests/test_contract_version_pin.py` | D 78-81, 246; E 12-46, 62-102, 167, 197-212; I 12, 44-46, 72, 167 | Ambiguous: T-035 (pins) or T-012 (it pins enums and column lists) | no |
| `tests/test_reproducibility_regression.py` | I 23, 51, 187-188 | T-035 | no |
| `g3o/run/telemetry.py` | E 52, 85-87 (prompt paths), 245 (`"contract": contract_surface()` in the run manifest) | T-030 | no |
| `tests/test_run_telemetry.py` | E 27, 140-153, 170-171; I 142 | T-030 | no |
| `g3o/run/presweep/records.py` | I 58 (docstring: reproducibility goldens move) | T-030 (orchestrator area); probably no change | no |
| `tests/fixtures/run_contract/FIELDS.md` | E 30, 37, 44, 244-245, 255, 362, 383; I 30, 44, 244 | **Unassigned.** Alternatives: T-030 (telemetry) or T-035 | no |
| `tests/fixtures/run_contract/manifest.json` | E 21, 26, 33-35 (`contract.{extract,validate}.version`) | **Unassigned.** Same alternatives | no |

### 3.3 Contract and prompt documents

| Path | Lines | Reference held | Proposed owner | Gen? |
|---|---|---|---|---|
| `g3o/extract/prompts/output_contract.md` | E 1 (`# G3O Output Contract v2.5`); A/B 54-55, 88-90, 126 (column 36, 4 values), 163, 219-226, 257-258, 289-391; D 37; G 111-112, 381 | T-010 (write claim "the three contract files (generated)") | target of `generated/extract_output_contract.md` |
| `g3o/validate/prompts/output_contract.md` | E 1 (`v1.3`), 5; A/B 18, 56-58, 130 (4 values), 135-259; G 92-93, 249 | T-010 | target of `generated/validate_output_contract.md` |
| `g3o/extract/prompts/system_prompt.md` | A/B 15-50, 77-78 | **Ambiguous:** T-010 Outputs list it; manifest says "T-022 / T-032 … system_prompt.md (and the Stage 6 prompts)" | target of `generated/system_prompt.md` |
| `g3o/validate/prompts/system_prompt.md` | A/B 12, 36, 50, 62-64, 84-85, 110; G 54 | **Ambiguous:** T-022/T-032 (manifest "Stage 6 prompts"), T-026 (Stage 6), or none if the OpenAI Stage 6 path is retired (T-026 excludes it) | partly |

### 3.4 Extract stage (T-022 "listed extract files")

| Path | Lines | Reference held | Proposed owner | Gen? |
|---|---|---|---|---|
| `g3o/extract/parser.py` | A 22; B 17, 62 | T-022 | no |
| `g3o/extract/salvage.py` | A 31, 72, 114, 331-414; B 12-41, 74, 114-115, 156, 192, 241, 389; G 174-175 (`none_reported` defaults) | T-022 | no |
| `g3o/extract/client.py` | E 31, 37-38 (loads `output_contract.md`) | T-022 | no |
| `g3o/run/presweep/stage_extract.py` | B 76, 236, 261 (`confirms_activity` comments/logic) | T-022 (sole owner) | no |
| `g3o/extract/__init__.py` | B 15 (docstring) | **Unassigned** (docstring only). Alternative: T-022 | no |
| `g3o/extract/README.md` | A/B 10; D 23; E 23 (39 columns + 5 provenance fields) | **Unassigned.** Alternatives: T-022 or T-090 | no |
| `tests/test_salvage.py` | A/B 8-1216 passim (624: the 4-value list); E 1080, 1142; G 124-942 | T-022 if "its tests" is implied (the write claim lists only "the listed extract files") | no |
| `tests/test_extract.py` | A/B 108, 355; E 163; G 98-99 | same as above | no |
| `tests/test_adversarial_llm_outputs.py` | A 140, 209, 476; B 140, 209; G 130-131, 185-186 | Ambiguous: T-022 or T-012 (it builds `ContractRow`s) | no |
| `tests/test_genai_definition_adherence.py` | A/B 118, 155; E 11; G 92-93 | Ambiguous: T-022 or T-012 | no |

### 3.5 Stage 6 (T-026 "the listed Stage 6 files and tests") and the retired OpenAI path

| Path | Lines | Reference held | Proposed owner | Gen? |
|---|---|---|---|---|
| `g3o/validate/jev_validate.py` | A/B 99-133, 223, 394-422; G 153-154, 381-382, 650-651, 677 | T-026 | no |
| `tests/test_jev_validate.py` | A/B 58-287, 555-559; G 206-586 | T-026 | no |
| `scripts/verify_jev_validate_live.py` | A/B 50, 82; G 76-77, 108-109 | **Unassigned.** Alternative: T-026 | no |
| `g3o/validate/client.py` | E 27, 33-34; **45, 124 hard-code "G3O Validation Contract v1.0"** while the document says v1.3 | **Unassigned:** OpenAI Stage 6 path, which T-026 excludes as retired but `stage_validate.py:53,330` still imports via `consolidate.py`. Alternatives: leave under the v2.5 version guard, or T-026 | no |
| `g3o/validate/qc.py` | A 161-340; B 36, 154-191; E 16 | **Unassigned** (same path; also imported by `g3o/classify/eligibility.py:63` for keywords only) | no |
| `g3o/validate/salvage.py` | A 55; B 8-55 | **Unassigned** (same path) | no |
| `g3o/validate/__init__.py` | E 10 (docstring) | **Unassigned** | no |
| `g3o/validate/README.md` | D 10; E 23 | **Unassigned.** Alternatives: T-026 or T-090 | no |
| `tests/test_validate.py` | A/B 122, 178, 486-516; E 215-217; G 98-99, 168-169; I 217 | **Unassigned** (retired-path tests) | no |
| `tests/test_validate_salvage.py` | A 74; B 75; G 54-55 | **Unassigned** (retired-path tests) | no |
| `tests/test_consolidated_contract.py` | A/B 100-550 passim; D 21, 529, 546; G 74-75 | Ambiguous: T-012 (tests `contract.py` Stage 6 models) or T-026 | no |

### 3.6 Persist / writer (T-028 `g3o/persist/writer.py` and its tests)

| Path | Lines | Reference held | Proposed owner | Gen? |
|---|---|---|---|---|
| `g3o/persist/writer.py` | D 15, 44-46, 353, 400-403, 561-563 | T-028 | no |
| `tests/test_persist.py` | A/B 107, 142, 150, 209, 220; D 17-19, 182-576; G 85-86 | T-028 | no |
| `tests/test_uid_stamping.py` | D 13, 42-45, 154-203 | Ambiguous: T-028 or T-012 | no |
| `g3o/persist/integrity.py` | B 152; D 29, 125-137 | **Unassigned.** Alternative: T-028 | no |
| `tests/test_integrity.py` | A/B 103, 138, 226, 521; G 79-80 | **Unassigned.** Alternative: T-028 | no |
| `g3o/persist/__init__.py` | D 7-12 | **Unassigned** (re-export; likely no change) | no |
| `g3o/persist/README.md` | D 13-15 | **Unassigned.** Alternatives: T-028 or T-090 | no |
| `g3o/common/institution_report.py` | D 30, 67, 70 (`INSTITUTION_REPORT_COLUMNS`) | **Unassigned** (consumer; changes only if that list changes) | no |

### 3.7 Reports and e2e

| Path | Lines | Reference held | Proposed owner | Gen? |
|---|---|---|---|---|
| `g3o/report/health.py` | A 306 (`sources_by_language` keyed by `genai_evidence`) | **Unassigned** | no |
| `tests/test_health_report.py` | A/B 232, 500, 564-587, 655-670 | **Unassigned** | no |
| `g3o/report/outcomes.py` | D 259 | **Unassigned** | no |
| `tests/test_outcomes.py` | A/B 158-159; G 135-136 | **Unassigned** | no |
| `tests/test_e2e_presweep_smoke.py` | A/B 132, 187; G 122 | T-030 (new-run e2e); T-035 adds back-fill/transfer cases | no |
| `tests/test_imports.py` | D 15-24 (imports column constants) | **Unassigned** (changes only on renames) | no |
| `tests/test_contract.py` | A/B 27-385 passim; D 19, 427; G 55-56, 98-99 | Ambiguous: T-012 (it tests `contract.py`; claim says "schema test") | no |

### 3.8 Codebook package (T-013, verified) and codebook (T-010, complete)

| Path | Reference held | Proposed owner | Gen? |
|---|---|---|---|
| `codebook/codebook.yaml` | source of every v2.7 list, incl. `core.page_verdict` (9 values) and `translation_v25` maps | T-010 (signed; no edit) | source |
| `tests/fixtures/codebook/codebook-r8-signoff.yaml` | copy of the signed codebook | T-013 | fixture |
| `g3o/codebook/generated/enums.py` | `CODEBOOK_RELEASE = '2.7'`, `ITEM_ENUMS` (line 14: 9-value `core.page_verdict`) | T-013 (generator); consumed by T-012 | yes |
| `g3o/codebook/generated/item_schemas.json` | per-item JSON schema | T-013; consumed by T-012 | yes |
| `g3o/codebook/generated/extract_output_contract.md`, `validate_output_contract.md` | generated contracts | T-013; installed by T-010 | yes |
| `g3o/codebook/generated/data_dictionary.md` | generated dictionary | T-013; installed by T-090 | yes |
| `g3o/codebook/generated/jev_questions.json` | question sets (A 913-961 cite `genai_evidence` in translation maps) | T-013; consumed by T-011 | yes |
| `g3o/codebook/generated/extractor_prompt_sections.md`, `system_prompt.md` | prompt sections | T-013; consumed by T-022/T-032 | yes |
| `g3o/codebook/generated/manifest.json` | intended targets (lines 735-770) | T-013 | yes |
| `g3o/codebook/generators.py`, `g3o/codebook/checks.py` | generators; `checks.py:760-770, 889-891` reads live `DATA_COLUMNS` as "the v2.5 column list" for the `translation_v25` completeness check | T-013 | no |
| `tests/test_codebook.py` | codebook tests | T-013 | no |

Hazard: `checks.py:889` imports the live `DATA_COLUMNS` and treats it as the v2.5 list. If T-012 adds v2.7 columns to `DATA_COLUMNS`, that check will start demanding `translation_v25` maps for v2.7-only columns, or misreport them. See §8.

### 3.9 Docs, frozen data, READMEs

| Path | Lines | Reference held | Proposed owner | Gen? |
|---|---|---|---|---|
| `docs/data_dictionary.md` | A/B 32-33, 101-107, 187-190, 247 (4 values); D 9-11, 20, 66, 92, 98, 163, 198, 201 (column counts pinned by the schema test); E 16, 256, 272; G 76, 237-238 | T-090 | target of `generated/data_dictionary.md` |
| `docs/replication.md` | D 220-232; E 170-172, 211; I 170-172 | **Unassigned.** Alternative: T-090 | no |
| `docs/architecture.md` | E 228 | **Unassigned.** Alternative: T-090 | no |
| `docs/storage-layout-v2.md` | I 218 | **Unassigned** (probably no change) | no |
| `CONTRIBUTING.md` | D/E 43, 48 | **Unassigned.** Alternative: T-090 | no |
| `data/README.md` | E 30 | **Unassigned.** Alternative: T-090 | no |
| `data/pilot_v1/README.md` | E 20 | none (frozen published dataset, C-006; no change) | no |
| `data/pilot_v1/g3o_full_database_v1.csv` | header has `genai_evidence`; 1,238 value lines | none (frozen) | no |
| `data/pilot_v1/merge_qc_summary.txt` | A 30 | none (frozen) | no |
| `baseline/g3o_activity_sources_v1.csv`, `baseline/g3o_activities_v1.csv`, `baseline/NOTES.md` | header/values; B 32 | none (frozen baseline) | no |

### 3.10 False positives (no change)

- `g3o/report/master_sites.py:205`: "Contract v1" is the master-sites contract.
- `tests/test_classify.py:220`: `"ambiguous"` is a triage rationale string.
- `docs/pipeline-status.md:861, 1083`: a historical status log (prose `ambiguous` sources; "Contract v2.3").

## 4. g3o-api (read-only, `C:/Users/spaci/repos/g3o-api` `acdb030`), for T-050

| Path | Lines | Reference held |
|---|---|---|
| `schema/schema_core.sql` | 103-104, 281-285 (`runs.contracts jsonb`, keyed `{extract, validate}`, instead of a scalar `contract_version`); 578-579 (`reported_*`); 613 (comment); 641 (`genai_evidence text`, no CHECK constraint); 659 (`search_tsv` weights `genai_evidence`) |
| `sql/013_agg_first_documented_month.sql` | 43, 84 (`genai_evidence = 'confirms_activity'`) |
| `worker/src/index.js` | 1107, 1132 (`genai_evidence` selected and returned); 6 (false positive: `contracts` in a path) |
| `worker/test/documented-or-unclear.test.mjs` | 52, 94 |
| `scripts/ingest.py` | 88-89 (column lists), 362-363, 382, 1127 (`confirms_absence`, `background_only`) |
| `scripts/export_bulk.py` | 104 (owned by T-052 per T-090) |
| `scripts/run_contract.py` | 299-310 (`contracts` jsonb) |
| `scripts/validate_run.py` | 123-161 (prints `contracts.<k>.version`) |
| `scripts/run_gates.py` | 485, 542, 554, 597, 617 |
| `scripts/rehearse_api52.py` | 54, 92-99, 154-156 |
| `scripts/verify_api.py` | 174 |
| `scripts/generate_synthetic_wave.py` | 86, 95, 103, 267, 307-308, 323-326, 343, 395 (4-value synthetic data) |
| `scripts/generate_synthetic_runs.py` | 213 |
| `docs/bulk-readme-template.md` | 256-263, 356 (4-value text; likely the #175 README surface, T-090/Colin) |
| `docs/evidence-status-contract.md` | 38-39 |
| `README.md` | 304 |

For T-050: the evidence column is free text, so the 9 values need no constraint change, but nothing holds a single codebook release label, setup pointer or `evidence_channel` (R-050); `runs.contracts` is the only version store and is per run, not per row.

## 5. g3o-website (read-only, `C:/Users/spaci/repos/g3o-website` `f6f627d`), for T-050

Live:

| Path | Lines | Reference held |
|---|---|---|
| `src/data/vocabulary.js` | 576-587: display labels for the 4 v2.5 values (`confirms_activity`, `confirms_absence`, `ambiguous`, `background_only`); another enum copy |
| `src/components/explore/Provenance.jsx` | 46-51 (doc comment, 4 values), 79 (`genai_evidence: establishes`) |
| `src/data/mockApi.js` | 568, 605 (`evidence.genai_evidence !== 'confirms_activity'`) |
| `src/data/mockFixture.js` | 409-459 (mock rows with 3 of the 4 values) |
| `src/copy.js` | 1933 (public copy explaining `genai_evidence`); 4384 is a false positive ("contracts for" in a quote) |
| `docs/research-visualizations-spec.md` | 132 (`e.genai_evidence = 'confirms_activity'`) |

Non-live: 21 files under `planning/` (`Goal-Spec*.md`, `index-design/**` including `pilot/*.py` and JSON read-check outputs). These are design notes and pilot artefacts; they are listed for completeness, not proposed for change. 4 files under `pilot-website-archive/` (archived generator, `pilotDashboardData.json`, `InstitutionProfile.jsx`, `policy.js`), which should not change.

The site shows no contract version today (no `contract_version`/`contracts` reference in `src/`). R-051's "version visible" is new UI.

## 6. Procurement (read-only, `C:/Users/spaci/repos/g3o-wt-procurement`, `procurement/main` `fa04e59`), for T-060

No `procurement/` path exists on G3O `main`. Procurement lives on branches `procurement/{main,brazil,italy,uruguay}` (the last three at `cee79b2`, 2026-10-11, with the same enum lines).

| Path | Lines | Reference held |
|---|---|---|
| `procurement/pipeline/core/contract.py` | 4-5 (snapshot pointer), **20 `CONTRACT_VERSION = "2.0"`**, **73 `GENAI_EVIDENCE` 4-value tuple** (the second code copy of the enum), 91-103 (Group D `_NA_` rule; `reported_*`) |
| `procurement/pipeline/core/classify.py` | 24-25, 123-136, 198-231 |
| `procurement/pipeline/core/coding.py` | 43-66 (`adoption_stage_for(…, genai_evidence_type)`) |
| `procurement/pipeline/core/models.py` | 71-84, 120-121 |
| `procurement/pipeline/core/standardize.py` | 395-402 |
| `procurement/pipeline/core/base.py` | 85 |
| `procurement/config/schema/procurement_record.schema.json` | 152, 177-201 (`genai_evidence_type` enum, 4 values), 218 |
| `procurement/docs/reference/output_contract_v2.0.SNAPSHOT.md` | 34 lines (frozen v2.0 snapshot) |
| `procurement/docs/reference/README.md` | 6-21 |
| `procurement/CLAUDE.md` | 20, 39 |
| `procurement/tests/test_core.py` | 37, 118, 249-387 |
| `procurement/tests/test_item_level.py` | 97-111 |
| `procurement/tests/test_template.py` | 129-132 |
| `procurement/tests/fixtures/_ocds_sample/README.md` | 2 hits |
| `procurement/planning/*` (9 files: PLAN, Plan-Draft, Plan-Review, RESOURCES, SPEC, SPEC-v001-draft.4, SPEC-v002, Spec-Review, handoffs/T-031) | governance; procurement integrator's |

The procurement worktree also carries a full `g3o/` tree on `procurement/main`. That is an older copy of the G3O pipeline, not procurement-owned, and is not listed here.

## 7. Schema-test items (`tests/test_schema_consistency.py`, `a5b1d30`)

The line numbers are unchanged from the `375f1ff` refs in the card.

- Pilot-v1 against live columns: `test_pilot_v1_full_header_matches_data_columns`, **lines 93-97**. Asserts `header == DATA_COLUMNS` (line 97). Fix per N3 a: freeze `PILOT_V1_DATA_COLUMNS` (the file already freezes `PILOT_V1_SUMMARY_COLUMNS` at 31-48 as a precedent).
- "Extras exactly five": `test_pipeline_extra_columns_are_exactly_five`, **lines 114-122**. `DATA_COLUMNS` minus `CONTRACT_COLUMNS` (50-90, which includes `genai_evidence` at 86) must equal the 5 provenance fields.
- Also coupled (not named in the card): `test_contract_columns_are_subset_of_data_columns` (109-111) breaks if `genai_evidence` leaves `DATA_COLUMNS`. `test_data_dictionary_column_counts_match_the_schema` (125-151) and `test_data_dictionary_names_every_shipped_source_column` (154-159) pin `docs/data_dictionary.md` (T-090, wave W10) to the schema lists, so a T-012 column change fails them until T-090 lands.

## 8. Uncovered surfaces (spec-change reports for the integrator)

These are enum or contract touchpoints that no card's write claim covers:

1. `g3o/report/health.py` + `tests/test_health_report.py`: `sources_by_language` counts by `genai_evidence` value.
2. `g3o/persist/integrity.py` + `tests/test_integrity.py`: the `_NA_` rule for absence/ambiguous/background sources. T-028 claims only `writer.py`.
3. `g3o/report/outcomes.py` + `tests/test_outcomes.py`, `g3o/common/institution_report.py`, `g3o/persist/__init__.py`: column-list consumers.
4. `g3o/common/contract_pin.py`: T-012 or T-035.
5. The OpenAI Stage 6 path (`g3o/validate/{client,qc,salvage}.py`, `tests/test_validate.py`, `tests/test_validate_salvage.py`) is excluded by T-026 as retired, but `stage_validate.py` still imports it. No card decides whether it is guarded, retired or updated.
6. `g3o/validate/prompts/system_prompt.md` and `g3o/extract/prompts/system_prompt.md`: the T-010 output table and the T-013 manifest disagree on the owner.
7. `tests/fixtures/run_contract/{FIELDS.md,manifest.json}`: contract-version fixtures.
8. `scripts/verify_jev_validate_live.py`.
9. Tests of `contract.py` other than the schema test (`test_contract.py`, `test_consolidated_contract.py`, `test_adversarial_llm_outputs.py`, `test_genai_definition_adherence.py`, `test_uid_stamping.py`): the T-012 claim says only "schema test", and T-022's claim lists no tests.
10. Docs outside T-090's three files: `docs/replication.md`, `docs/architecture.md`, `CONTRIBUTING.md`, `data/README.md`, `g3o/extract/README.md`, `g3o/validate/README.md`, `g3o/persist/README.md`, and the `g3o/extract/__init__.py` and `g3o/validate/__init__.py` docstrings.

## 9. Sequencing hazards found during the inventory (for the integrator)

- **The pin test will go red on T-012's branch.** `contract_pin.literal_enums()` discovers every `Literal` in `contract.py`, and `GATED_COLUMN_LISTS` covers `DATA_COLUMNS`, `ACTIVITY_COLUMNS`, `ACTIVITY_SOURCE_COLUMNS` and `SUMMARY_COLUMNS`. So any T-012 enum or column change moves the extract surface hash, and `tests/test_contract_version_pin.py` fails. Pin regeneration is excluded from T-012 (T-035, DEC-021), yet T-012's done condition says "tests pass". One of these has to give: an `xfail`/skip, a temporary regeneration, or a relaxed done condition.
- **The generated contracts have no version token in their H1.** `generated/extract_output_contract.md` line 4 is "# G3O output contract (extract), generated from the codebook". `contract_pin.parse_version()` raises `ValueError` without a `vX.Y` token, so installing the generated file as-is would break `contract_surface()` (pin test and run-manifest telemetry, `telemetry.py:245`). This is relevant to T-010's install, T-035 and R-050 (release label replaces the contract versions).
- **T-010 is marked complete, but the installed contracts on `main` are still v2.5 / v1.3.** `g3o/{extract,validate}/prompts/output_contract.md` H1s at `a5b1d30` and on `origin/reclass/t010-contract` still read v2.5 / v1.3. The manifest's intended targets remain uninstalled.
- **`codebook/checks.py:889` treats the live `DATA_COLUMNS` as "the v2.5 column list"** (see §3.8). It will drift once T-012 edits `DATA_COLUMNS`, unless it is repointed at the frozen pilot or v2.5 list.
- **Data-dictionary tests** (§7) couple T-012 (W2) to T-090 (W10).

## 10. Divergent copies noticed

- `g3o/validate/client.py:45, 124` hard-code "G3O Validation Contract v1.0"; the document H1 is v1.3.
- Procurement pins `CONTRACT_VERSION = "2.0"` against its v2.0 snapshot; G3O is at v2.5. In procurement, `genai_evidence` is the matched-terms snippet, and the enum lives in `genai_evidence_type`. Same name, different meaning from G3O's column.
- The website's `vocabulary.js` and g3o-api's synthetic generators carry their own 4-value copies, including the retired `ambiguous`.
- In G3O itself there is only one Python copy of the 4-value enum (§3.1). The card's "both enum copies (including the NoNA variants)" matches the Stage 5 activity enums plus their NoNA mirrors, not two page-verdict copies.
