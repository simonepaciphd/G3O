# Resources: G3O pipeline reclassification (jev classifies, the extractor (Claude Haiku 5.5) extracts support; contract v2.7; back-fill)

Status: LOCKED (approved Simone Paci, 2026-10-27, chat "APPROVED"; locked 2026-10-28T09:50-07:00 by Simone Paci (RC-BL-001, chat "lock")); v001.1 by delta RC-D-001, approved 2026-10-29 (Simone Paci, chat "approve delta")
Version: v001.1
Spec: `C:/Users/spaci/repos/G3O/planning/SPEC.md` v001.4 at lock (written against v001.1; the v001.2-v001.4 changes add no resource link not already listed: release flag and correction layer use RS-020, §4.3 text RS-029, validation notice RS-033)
Search scope: `H:/My Drive/Research/G3O/asset-registry.csv` (path greps, not a full parse); SRC-1..SRC-8 and files they cite; G3O repo via `git show/grep` on `origin/main` (`c6349d6`) and `archive/exval-v2.6` (`052fcb2`), plus the untracked `runs/` listing; g3o-api `origin/main` (`fc33ea3`; schema, sql, scripts, worker files by grep); g3o-website origin file list and `planning/ra-roles` file list; the four agent-workspace folders in SRC-1/4/5/8; procurement-pipeline CLAUDE.md/AGENTS.md and `pipeline/core/contract.py`; CX-01.2 index-design folder (pilot/, evidence/); RAs/Website Team listing; g3o_validation `planning/RESOURCES.md` listing; local auto-memory.
Not searched: the droplet (`/home/g3o/runs`, scratch dirs), the live Neon DB, TypeSafe/OpenAI, `inputs/` (not listed), `background/`, GitHub remotes beyond fetch. Not opened: g3o-api bundles, other worktrees, WS10 `calibration20/`, `docs/Paper/`.
Freshness: `git fetch` run 2026-10-27 after the scan (PI RQ-006 yes): G3O `origin/main` still `c6349d6`, g3o-api `acdb030` (docs-only drift from `fc33ea3`, per Plan-Review PF-025); g3o-website `origin/main` now `282ca6a` (website facts RS-022 to re-check at Stage 3).
Prepared by: Claude Code subagent (claude-opus-5-5), 2026-10-27; spot-checked and transcribed by the parent session `20261027-claude-v2-3d85fb1367912304`. Parent spot-checks: WS10 `full-review/PROGRESS.json` (51/1,464 activities, `review_complete: false`) and `activity-review-prepared.csv` (114 rows) confirmed; RS-016 corrected: `extract_links` helpers exist (`g3o/scrape/html.py:36`, `g3o/scrape/pdf.py:53`) but no stage calls them and no link following exists.

## Asset inventory

| Asset ID | Location | Type | Description | Purpose / producer | Access constraints | Verification status | Registry |
|---|---|---|---|---|---|---|---|
| RS-001 | `H:/My Drive/Research/G3O/asset-registry.csv` | inventory | 2,816 lines; pipeline-code rows scattered (old `agent-workspace/G3O-public/...` and branch rows) | Native writer | read-only; never hand-edit | VERIFIED (grep) | n/a |
| RS-002 | `C:/Users/spaci/repos/G3O/planning/` (SPEC, Stage1-Interview, Spec-Review, Plan-Manifest) | spec | Approved SPEC v001.1 and rulings | this plan | uncommitted; no push | VERIFIED | unregistered |
| RS-003 | `agent-workspace/2026-10-27-unclear-screen/HANDOFF.md` (SRC-1) | planning-handoff | Rulings 1-11, S1-S9; verified counts; new-field footprint | researcher 2026-10-27 | — | VERIFIED | registered |
| RS-004 | same folder: `enumerate.py`, `count_pages.py`, `unclear2.py` (SRC-7 L32-55; `byte_chunks` 48,000-byte chunks, halve-and-retry ×3) | code | Read-only enumerators over `/home/g3o/runs`; jev re-pilot | researcher | droplet paths hard-coded | VERIFIED | registered |
| RS-005 | same folder: `count-pages.json`, `enumerate.out`, `enumerate-per-run.json`, `report-repilot{,2}.json`, `answers-repilot{,2}.jsonl` | output | Unclear-set counts; re-pilot answers (372 pages, 250 institutions) | researcher | — | VERIFIED | report-repilot*.json registered; others unregistered |
| RS-006 | droplet `~/unclear-screen-20261027/enumerate-union.json`; `~/index-pilot-20261025/` | data | Per-uid latest run, ambiguous/text flags, `lang` for the 27,648 | researcher | SSH | UNVERIFIED | unregistered |
| RS-007 | droplet `/home/g3o/runs/<run>/institutions/<shard>/<iid>/scrape/<md5(url)>.json[.gz]`; `<run>/final/*.csv` | input-data | Stored page text and final CSVs (33 runs with final CSVs at 2026-10-27) | pipeline | SSH; PI-authorised read | UNVERIFIED (layout from RS-004 code) | unregistered |
| RS-008 | `C:/Users/spaci/repos/G3O/runs/` (6 dirs; `r20260830T114940Z-32ea-scrape.tar`, 29,504 scrape files) | data | Local copy of one run's stored text | 2026-09-03 PI-authorised pull | local, gitignored | VERIFIED | tar registered; dirs unregistered |
| RS-009 | `agent-workspace/2026-09-27-jev-compare/` (REPORT.md = SRC-8; `pulled/` tars 17,595 + 14,173 scrape files; results/) | data/report | jev-vs-nano agreement (not accuracy); offline page corpus | researcher 2026-09-29 | — | VERIFIED | unregistered |
| RS-010 | G3O `origin/main`: `g3o/extract/prompts/{output_contract.md v2.5, system_prompt.md}`; `g3o/validate/prompts/output_contract.md` v1.3; `g3o/common/{contract.py, schema.py, contract_pin.py}`; `tests/goldens/{contract_version_pin.json, reproducibility.json}` | existing-code | Contract of record; `genai_evidence` 4-value enum (§4.7, col 36); `source_snippet` exists; pins v2.5 / v1.3 | pipeline | change needs PI sign-off (C-003) | VERIFIED | partially registered |
| RS-011 | ref `archive/exval-v2.6` (`052fcb2`): `g3o/common/evidence_review.py`, v2.6/v1.4 prompts, `docs/extraction-validation-rulings.md`, `tests/fixtures/exval_cases.json` (30), `tests/test_evidence_review.py`; `agent-workspace/2026-09-06-extraction-validation/` (SRC-4) | existing-code | v2.6 rules; `check_quotes` is whitespace-normalised substring (L145-146); consolidation targets retired OpenAI Stage 6; patch conflicts on `validate/consolidate.py` | Codex 2026-09-06 | local ref, unpushed | VERIFIED | patch/REVIEW registered; worktree rows stale |
| RS-012 | `g3o/common/jev_client.py`; `g3o/run/presweep/jev_stage_runner.py` | existing-code | `JEV_MAX_TOKENS_PER_REQUEST=64_000`; `JevAnswer` confidence + probabilities; `JevResult` response_model, request_id | pipeline | jev key | VERIFIED | partially registered |
| RS-013 | `g3o/run/presweep/stage_classify.py`; `g3o/classify/{jev_url_triage.py, jev_official_site.py}` | existing-code | Stages 2/3 write probabilities, confidence, model, request id, question-set version to per-institution JSON (files only, not DB) | pipeline | — | VERIFIED | partially registered |
| RS-014 | `g3o/validate/jev_validate.py`; `g3o/run/presweep/stage_validate.py` | existing-code | Stage 6 jev; byte-chunk fallback (`CHUNK_BUDGET_BYTES=100_000`, `MAX_SPLIT_DEPTH=3`); keeps first chunk's ids only; no probabilities in `6_validate.json`; question-set version not stamped | pipeline | — | VERIFIED (partial) | partially registered |
| RS-015 | `g3o/extract/{client,batch,parser,salvage}.py`; `g3o/run/presweep/stage_extract.py`; `g3o/common/batch_client.py` | existing-code | Stage 5 nano Batch per (institution × page); `cap_page_text` 60k chars head+tail; salvage defaults. OpenAI-only client today; v2.7 needs an Anthropic Messages + Message Batches client (new code, T-022; RC-D-001) | pipeline | OpenAI key (v2.5 path) | VERIFIED (grep/heads) | partially registered |
| RS-016 | `g3o/run/presweep/stage_scrape.py`; `g3o/scrape/{fetcher,render,pdf,politeness,breaker,unlocker,html}.py` | existing-code | Fetches triage-kept URLs; robots, throttle, redirects. `extract_links` helpers exist but are uncalled; no link following, hop limit or provenance chain | pipeline | — | VERIFIED (grep; parent corrected) | partially registered |
| RS-017 | `g3o/run/presweep/{config,orchestrator,sampling,eval_frame}.py`; `g3o/common/run_state.py`; `g3o/run/{api,telemetry}.py`; `g3o/run/orchestrate/*`; `g3o/cli.py` | existing-code | `stop_after`; `--resume` via `_state/.done`; sample from `--master-csv`; no fixed-list / start-from-stored-pages entry; contract stamps per run, kept on resume | pipeline | — | VERIFIED (partial) | partially registered |
| RS-018 | `g3o/persist/writer.py`; `g3o/common/schema.py`; `docs/data_dictionary.md`; `docs/{storage-layout-v2,operations,deployment,pipeline-status}.md` | existing-code/documentation | Stage 7 CSV writer; data dictionary; no contract changelog file | pipeline | — | LISTED (dictionary head VERIFIED) | partially registered |
| RS-019 | G3O tests: `test_jev_validate.py`, `test_jev_stages.py`, `test_e2e_presweep_smoke.py`, `test_genai_definition_adherence.py`, `test_contract_version_pin.py`, `test_reproducibility_regression.py`, `test_schema_consistency.py`, `tests/fixtures/{frozen_master.csv, run_contract/}` | existing-code | Mock-based unit/e2e harness; no fixtures for multi-activity, links, chunking, 8 verdicts, C2-C4 | pipeline | — | VERIFIED (headers) | partially registered |
| RS-020 | g3o-api `origin/main`: `schema/schema_core.sql`; `sql/000-020`; `scripts/{ingest,backfill_verdicts,run_contract,export_bulk,verify_api,validate_run}.py`; `worker/src/index.js` | existing-code | `runs.contracts` jsonb per run; v2.5 columns; `evidence.genai_evidence` text, no CHECK; no correction table, per-row version or jev fields; `backfill_verdicts.py` precedent; `export_bulk.py` = #175 | Colin (owner, RQ-007) | DB write needs PI sign-off | VERIFIED (grep) | partly registered |
| RS-021 | g3o-api `sql/004_wave_window_w001.sql`; memory g3o-wave-window-gates-visibility | existing-code/doc | Visibility = `run_started_at` in `wave_windows`; file span ends 2026-10-01; memory: extended to 2027-01-01 | PI | live DB | VERIFIED (file); live UNVERIFIED | not checked |
| RS-022 | g3o-website: `src/pages/{Institution,Compare}.jsx`, `src/{copy.js, data/vocabulary.js, data/registry.js, data/apiClient.js}`, `test/` | existing-code | Publication surfaces | Colin | origin now `282ca6a` | LISTED | unregistered |
| RS-023 | `RAs/Website Team/Backend/contracts/2026-07-27 API Contract — Data Platform.md`; Frontend tracker (Colin) | documentation | Existing public API contract; base for D-007 | Colin | — | LISTED | registered |
| RS-024 | CX-01.2 proposal (SRC-6) + `pilot/` + `INDEX-DECISIONS.md` under `archive/planning-drive-copy-superseded-2026-10-26/launch-analysis-pr/index-design/` | upstream-artifact | Frozen wording; CX-05; §11.1 chunk rule (L184); C2-C4 never run (L204) | PI-signed 2026-10-25 | frozen | VERIFIED | unregistered at current path |
| RS-025 | same `index-design/evidence/`: `w001-documented-list.json.gz`, `w001-detail-sample-800.json.gz`, `analyse-output.txt`, `harvest.py` | input-data | All 9,705 documented (uid, country, level, branch, type, finding_count); 800 detail sample (as_of 2026-10-24T14:04:52Z) | researcher 2026-10-25 | — | VERIFIED | unregistered |
| RS-026 | `agent-workspace/2026-09-05-combined-ws10-review/`: DECISIONS*, OWNER-REPRESENTATION (SRC-5), CODEBOOK-signoff, `scope-counts.json`, `activity-review-prepared.csv` (114, authoritative per RQ-003), `owner-context.csv` (45), `evidence-review-prepared.csv`, `source/` | upstream-artifact/input-data | WS10 D1-D6; transfer list; suggested correction-layer fields | researcher/Codex 2026-09-05 | — | VERIFIED | registered |
| RS-027 | same package: `full-review/{PROGRESS.json, NEXT.md, REVIEW-CURRENT.md, ...}`; `merge-readiness-20260906/CLOSEOUT.md`; `engineer-handoff-20260906/HANDOFF.md` | upstream-artifact | Combined review incomplete (51/1,464 activities; groups 0-13 of 45); no row diff | researcher | — | VERIFIED (parent spot-check) | registered |
| RS-028 | registered `C:/Users/spaci/worktrees/g3o-api-fixrow/scripts/{prepare,build,check}_attribution_*.py` | existing-code | Stage14 unsigned attribution-correction package | Codex 2026-09-05 | — | UNVERIFIED (worktree absent) | registered (stale path) |
| RS-029 | `subprojects/procurement-pipeline/{CLAUDE.md, AGENTS.md, pipeline/core/contract.py, docs/reference/output_contract_v2.0.SNAPSHOT.md}`; procurement plan `C:/Users/spaci/repos/g3o-wt-procurement/procurement/planning/` (locked; integrator DEC-009) | documentation/existing-code | Pinned v2.0; v2.2 §4.3 owed; `contract.py` L73 copies 4-value `GENAI_EVIDENCE` | procurement lane | do not edit from here | VERIFIED (grep; plan manifest read by parent) | UNVERIFIED |
| RS-030 | Live DB (Neon br-wave1-cutover) / API `api.g3observatory.org` | external-service | Published verdicts; 27,648 unclear and 535,546 of 719,588 reviewed confirmed by API meta (as_of 2026-10-24T14:04:52Z) | Backend | read-only; free GETs authorised (G8 c) | VERIFIED (API GET 2026-10-27) | unregistered |
| RS-031 | TypeSafe jev (jev-1.13.0 per SRC-8); extractor Anthropic `claude-haiku-5-5`, medium effort: Messages API (sync, testing) and Message Batches (full runs) (RC-D-001; was OpenAI Batch gpt-5-nano-2025-08-07, shut down 2026-12-11) | external-service | Classifier; extractor | vendors | keys (`TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY`); paid runs need sign-off | UNVERIFIED (effort setting and Batch: T-002) | n/a |
| RS-032 | Wave-5 run `r20261023T134656Z-be8a` | input-data | `final: false` on 2026-10-27; still running per PI | pipeline | droplet | VERIFIED (via RS-005) | unregistered |
| RS-033 | `C:/Users/spaci/repos/g3o_validation/planning/RESOURCES.md` (BL-001) | documentation | Sibling plan; its RS-016 pins this contract surface | validation plan | locked | LISTED | n/a |
| RS-034 | G3O `g3o/report/{diff,institution_report,outcomes}.py`; g3o-api `scripts/{teardown_run,rehearse_api52}.py` | existing-code | Run-diff and rehearsal tooling | pipeline/backend | — | LISTED | partially registered |
| RS-035 | `agent-workspace/runs/{20260802-e2e-100, 20260816-n3-smoke}`; `data/pilot_v1` | data | Contaminated e2e; pilot v1 (barred C-006) | — | — | LISTED | registered |
| RS-036 | `agent-workspace/2026-10-27-reclass-plan/harvest_unclear.py` + outputs `unclear-list.json`, `unclear-detail-sample-800.json` | input-data | Public-API harvest (G8 c), 2026-10-27, meta coverage as_of 2026-10-24T14:04:52Z: 27,648 unclear (total_is_exact). Level: local 22,253; second_subnational 2,635; national 2,279; first_subnational 481. Branch: executive 24,700; bureaucratic 2,789; legislative 108; judicial 51. 205 countries (USA 4,217; FRA 2,068; IDN 2,030; IND 1,848; ITA 1,309; ...). 800 sample (seed 20261027): evidence rows/institution p50 4, p90 12, max 41; distinct URLs mean 5.6; 58 source languages (en 36.2%, fr 8.7%, es 7.6%, id 5.6%, de 4.8%, ...); `genai_evidence` confirms_absence 2,560 / ambiguous 2,100 / background_only 8 | this session | free GETs | VERIFIED (parsed) | unregistered |
| RS-037 | Anthropic API organization + G3O key (`ANTHROPIC_API_KEY` in the untracked `C:/Users/spaci/repos/G3O/.env`; droplet copy at T-071) | external-service | Extractor access (RC-D-001, ruling F1 c) | Simone Paci, created 2026-10-29 | key | VERIFIED 2026-10-29: free model-list call returned HTTP 200 and lists `claude-haiku-5-5`; rate-limit tier recorded by T-002 | n/a |

## Resource-to-deliverable map

| Spec ID | Needed input | Resource(s) | Relationship | Confidence | Evidence |
|---|---|---|---|---|---|
| D-001 | v2.5 base contract and prompts | RS-010 | existing-code | high | origin/main read |
| D-001 / R-010..R-014 | v2.6 rules, WS10 D1-D4 | RS-011, RS-026 | upstream-artifact | high | rulings doc; DECISIONS |
| D-001 / R-015, R-016 | verdict and GenAI wording | RS-004, RS-005 | upstream-artifact | high | unclear2.py L32-55 |
| D-001 / R-020..R-025 | CX-01.2 wording | RS-024 | upstream-artifact | high | L184, L204 |
| D-001 / C-007 | version-pin mechanics | RS-010 | existing-code | high | pin json |
| D-002 / R-001..R-004 | jev page and activity passes | RS-012, RS-013, RS-014 | existing-code | medium | no two-pass page coder |
| D-002 / R-005 | v2.6 consolidation as jev rules | RS-011, RS-014 | existing-code | medium | REVIEW.md |
| D-002 / R-006, R-040 | nano extraction | RS-015 | existing-code | medium | batch.py |
| D-002 / R-026 | jev answer storage | RS-012, RS-013, RS-020 | existing-code | medium | stage_classify L220-230 |
| D-002 / R-030..R-034 | link following | RS-016 | existing-code | low | helpers only |
| D-002 / R-042 | quote check | RS-011 | existing-code | medium | substring only |
| D-002 / R-044 | chunking + combination | RS-012, RS-014, RS-004, RS-024 | existing-code/upstream-artifact | medium | read |
| D-002 / R-050 | per-row contract version | RS-017, RS-020 | existing-code | low | per run only |
| D-003 / R-070, R-071 | back-fill set at freeze | RS-030, RS-025, RS-036, RS-005, RS-006, RS-032 | input-data | medium | counts |
| D-003 / R-074, R-076 | stored page text | RS-007, RS-008, RS-009 | input-data | medium | droplet unverified |
| D-003 / entry point | fixed list, stored pages, no re-triage | RS-017 | existing-code | low | absent |
| D-003 / R-073 | correction layer | RS-026, RS-020 | upstream-artifact | low | fields suggested only |
| D-003 / R-077 | 114 WS10 transfers | RS-026, RS-027, RS-028 | input-data | medium | list authoritative (RQ-003) |
| D-004 / R-050..R-055 | DB, API, site, visibility | RS-020, RS-021, RS-022 | existing-code | medium | grep |
| D-005 / R-080..R-084 | sampling frame, prior reads, fixtures | RS-025, RS-036, RS-005, RS-024, RS-009 | input-data | medium | Q-017 facts |
| D-005 / fixtures | A-003, A-004, A-010..A-012, A-020..A-022 | RS-011, RS-019, RS-005, RS-008, RS-009 | existing-code/input-data | low-medium | gap G9 |
| D-006 | dictionary, changelog, methods | RS-018, RS-011, RS-010 | documentation | medium | no changelog file |
| D-007 | interface spec base | RS-023, RS-020, RS-022 | documentation | medium | listed |
| D-008 / R-085 | procurement dependency and channel | RS-029 | documentation/existing-code | high | contract.py L73; procurement DEC-009/010 |

## Unresourced deliverables

| Spec ID | Missing | Options | User decision | Status |
|---|---|---|---|---|
| D-003 / R-077 | G1 Completed WS10 combined review | a finish first / b reclassify the 114 via v2.7 + R-082 read / c narrow R-077 / d UNRESOLVED | b (2026-10-27) | RESOLVED (R-077) |
| D-003 / R-073 | G2 Correction-layer table and views | a new g3o-api migration / b extend `backfill_verdicts.py` precedent / c UNRESOLVED | to Stage 3 (procedural default) | OPEN (design) |
| D-003 | G3 Back-fill entry point | a first-class command / b copy-run + resume / c `--master-csv` / d UNRESOLVED | to Stage 3 | OPEN (design) |
| D-002 / R-030..R-035 | G4 Link following, hops, dedup, provenance | a in scrape stage / b follow-up leg after Stage 5 / c revise / d UNRESOLVED | to Stage 3 | OPEN (design) |
| D-002 / R-026 | G5 jev answer storage and DB columns | a artifact pattern + DB columns / b file-only / c UNRESOLVED | to Stage 3 | OPEN (design) |
| D-002/D-004 / R-050 | G6 Per-row contract version | a row column / b via `run_id` + no mixed runs / c UNRESOLVED | to Stage 3 | OPEN (design) |
| D-004 / R-051 | G7 Visibility of back-fill/correction rows | a cut/extend wave window / b correction-layer projection independent of waves / c UNRESOLVED | b (2026-10-27) | RESOLVED (R-055) |
| D-005 / Q-017 | G8 Strata for unclear; documented page/text counts | a droplet / b DB / c public API / d existing strata only / e defer | c (2026-10-27) | RESOLVED for strata (RS-036); documented stored-text counts still UNVERIFIED |
| D-005 / fixtures | G9 Fixtures for new cases | a synthetic / b mined real pages / c both / d UNRESOLVED | to Stage 3 | OPEN (design) |
| D-002 / R-042 | G10 Fuzzy matcher | a library / b in-house | to Stage 3 (with Q-020 b) | OPEN (design) |
| D-008 / C-007 | G11 Procurement verbatim enum copy | a notify only / b coordinated update / c UNRESOLVED | b + message (2026-10-27) | RESOLVED (D-008, R-085) |
| R-070 | G12 Wave 5 membership | a re-check at freeze / b exclude | PI: "still running, we'll do the full update once it's in" | RESOLVED (R-070) |
| D-002 / R-044 | G13 Page-level chunker | a port `byte_chunks` / b reuse Stage 6 split | to Stage 3 | OPEN (design) |
| D-004 / D-007 | G14 Fresh origin state | a fetch / b Colin supplies | a (fetched 2026-10-27) | RESOLVED (website re-check at Stage 3) |

## Unmapped resources

| Asset ID | Classification | Reason | User decision |
|---|---|---|---|
| RS-033 | investigate | Validation plan pins this contract surface; may need a delta | |
| RS-034 | useful | Run-diff tooling for A-005/A-006 | |
| RS-035 | out-of-scope | Contaminated e2e; pilot v1 barred (C-006) | |
| RS-028 | investigate | Possible prior code for transfer diffs; location unknown | |
| RS-001 old `G3O-public` rows | redundant | Superseded paths | |

## Open questions

| ID | Question | Why it matters | Blocking? |
|---|---|---|---|
| RQ-001 | Route for Q-017 counts | Q-017 before lock | resolved: public API (G8 c) |
| RQ-002 | Droplet scratch files still present / reusable? | Unclear strata, language | no |
| RQ-003 | Is `activity-review-prepared.csv` the authoritative 114 list? | R-077 | resolved: yes |
| RQ-004 | Where are the Stage14 attribution scripts; still wanted? | Possible reuse | no |
| RQ-005 | Live `wave_windows` state | superseded by R-055 for back-fill rows; still relevant to new runs | no |
| RQ-006 | Fetch repos? | Freshness | resolved: yes, fetched |
| RQ-007 | Does Colin own g3o-api too? | D-007 scope | resolved: yes |
| RQ-008 | Is notification enough for procurement? | C-007 | resolved: no, coordinated update (G11 b) |
| RQ-009 | Who records the freeze date, from which surface? | R-070 | no |

## Change history

| Version | Change | Approved by/at |
|---|---|---|
| v001.1 | RC-D-001: extractor gpt-5-nano → Claude Haiku 5.5 (title, RS-015 note, RS-031, new RS-037) | Simone Paci, 2026-10-29, chat "approve delta" |
| v001 | Stage 2 subagent draft; parent spot-checks; PI gap rulings G1 b, G7 b, G8 c, G11 b, G12, RQ-003/006/007 applied; design gaps routed to Stage 3 | Simone Paci, 2026-10-27 |
