# Resources: G3O procurement pipeline (whole pipeline, retrofit)

Status: LOCKED (Stage 6 baseline, 2026-10-27T08:02-07:00, Simone Paci in chat: "LOCK"); approved 2026-10-27
Version: v001
Decisions: S2 = PI answers in chat 2026-10-27: "1: a, 2 a (draft quick email for her about this: look at spec/plan, commit code, share resources on drive), 6a, 13 a 3a, 5 b 6 stale ; prcedural accept all". Coordinator reading: 1 = RQ-001 a; 2 = RQ-002 a; 6a = D-006 a; 13 a = D-013 a; 3a = RQ-003 a; 5 b = RQ-005 b; 6 stale = RQ-006; procedural G1-G6 accepted.
Spec: `procurement/planning/SPEC.md` v001-draft.3 (approved 2026-10-27)
Prepared by: Claude Code resource-map subagent (claude-opus-5-5), 2026-10-27, read-only. Coordinator spot-checked: 781cf0c absent; 8b4e211 diff; Drive `cli.py` = 55fe353 blob; replay `links.csv` header-only; `rosters/` empty; no contract-row mapper or `has_genai_activity` aggregation in `pipeline/`; `CONTRACT_VERSION = "2.0"`; tracker column `notes_RA_Lee`.

Search scope:
- Searched:
  - PP (`H:\My Drive\Research\G3O\subprojects\procurement-pipeline\`): `asset-registry.csv` (116 rows); file listing with mtimes of root, `docs/`, `config/`, `pipeline/`, `tests/`, `outputs/`, `agent-workspace/` and `data_cache/`; `archive/` by folder name only.
  - Repo worktree `procurement/` on `procurement/main`. The italy, uruguay and brazil branches were compared by commit (all at `cee79b2`). Also the log of 55fe353, 8b4e211 and cee79b2; CI workflow; `cat-file 781cf0c`.
  - Contract title line on main, origin/main and procurement/main.
  - Master `data_final/`: headers; ledger status counts; URY/ITA/BRA row counts.
  - Multilingual `rosters/`; root `query_builder.py`.
  - Board #81-87, #141, #143 (titles and states); procurement CI runs.
- NOT searched:
  - the canonical tracker Google Sheet (only the 2026-07-14 xlsx snapshot);
  - issue bodies;
  - `archive/` contents;
  - `data_cache` payload contents;
  - Asenat's machine and remote;
  - other G3O branches and worktrees;
  - the root Drive tree outside the named paths;
  - the root registry beyond a grep.
- Tests were not run.

## Asset inventory

| Asset ID | Location | Type | Description | Purpose / producer | Access constraints | Verification status | Registry |
|---|---|---|---|---|---|---|---|
| RS-001 | PP\asset-registry.csv | registry | 116 rows; last row 2026-10-09 | Inventory | Append via native writer only | VERIFIED | reg |
| RS-002 | PP\docs\procurement-extension-spec.md (ES) | doc | Scope ruling 2026-07-28 + 2026-08-04 notes; §2 outputs, §3 crosswalk, §4 extension, §5 matching | PI ruling | Read-only | VERIFIED (headings) | reg |
| RS-003 | PP\agent-workspace\2026-08-04-reply-to-ainhoa.md (PM) | doc | PI reply: D1-D6, confirmations, §4 re-pin, §5 sample go-ahead | PI | — | VERIFIED (headings) | unreg |
| RS-004 | PP\CLAUDE.md (PC) + PP\AGENTS.md | doc | Subproject operating manual (2026-08-27) | Agent | — | VERIFIED | reg |
| RS-005 | repo procurement/CLAUDE.md @ cee79b2 (RC) | doc | Repo manual for RA sessions; distinct from PC (blob 9f80bd6 vs Drive 0300f98) | PI-requested 2026-10-11 | Git | VERIFIED (blob) | unreg |
| RS-006 | PP\implementation-roadmap.md (RM) | doc | Phases 0-5, status 2026-10-09; Phase 1 matcher sub-items still `[ ]` though README/HI/registry row 91 say built | Agent/RA | — | VERIFIED | reg |
| RS-007 | PP\docs\architecture.md (AR) | doc | Core + adapters; §7 reproducibility | Agent | — | VERIFIED (headings) | reg |
| RS-008 | PP\docs\genai-procurement-codebook.md (CB) | doc | `0.4-rulings-2026-08-04`; §5 relevance, §8 review triggers | RA/agent | — | VERIFIED (header) | reg |
| RS-009 | G3O:g3o/extract/prompts/output_contract.md (CT) | instrument | v2.5 on main, origin/main (c6349d6), procurement/main | Root instrument | Read-only | VERIFIED (title) | root reg |
| RS-010 | procurement/docs/reference/output_contract_v2.0.SNAPSHOT.md + README (SN) | instrument copy | v2.0 snapshot; Drive and repo byte-identical | Pinned 2026-08-03 | Read-only | VERIFIED | reg |
| RS-011 | PP\docs\adapter-output-interface.md (AI) | doc | DRAFT v0.1 2026-10-09: adapter contract, 4 staged tables, manifest, Italy milestone §7 | Agent | Unsigned | VERIFIED | reg |
| RS-012 | PP\docs\uruguay-full-run-protocol.md (UP) | doc | Draft: window, traversal, retries, manifest §5, QC §6 | Agent | Window/scope PI | VERIFIED | reg |
| RS-013 | PP\docs\classification-validation-protocol.md (VP) | doc | Draft: §A labels/κ/P-R; §B matcher sample (to amend per Q-036) | Agent | — | VERIFIED | reg |
| RS-014 | PP\agent-workspace\2026-10-07-item-level-rules-PROPOSAL.md (IR) | doc | R1-R8; R1-R5, R8 implemented pending review | Agent/RA | Proposal | VERIFIED (header) | reg |
| RS-015 | PP\agent-workspace\2026-10-07-handoff-index.md (HI) | doc | Locations, commands, versions (code sha256 398167e2…, mb-2026-07-30), issues #1-13 | RA | — | VERIFIED | reg |
| RS-016 | PP\agent-workspace\2026-10-09-sprint-plan.md (SP) | doc | Proposed sprint items with done-criteria | Agent | Proposal | VERIFIED | reg |
| RS-017 | PP\docs\source-registry.md (SR) | doc | Tracker columns → config | Agent | — | VERIFIED (headings) | reg |
| RS-018 | PP\docs\G3O - Procurement Repository Tracker.xlsx (2026-07-14) + …-071426.xlsx | dataset | 191 rows; RA column is `notes_RA_Lee` (63 filled), not `notes_RA`; both files same fill counts | Snapshot of the Drive Sheet | Read-only | VERIFIED | reg |
| RS-019 | PP\agent-workspace\PI-Update-2026-08-29.md (+ .html) (PU) | doc | "Approvals to continue" 1-4 | RA | — | VERIFIED | .html reg; .md unreg |
| RS-020 | config/sources.yaml (Drive = repo) | config | 150 rows: api 33, bulk 23, scrape 94; all `unverified_snapshot`; 65 `is_ocds`; `verification_note` on BRA PNCP, URY ARCE only | Generated 2026-07-21 | — | VERIFIED | reg |
| RS-021 | config/manual_sources.yaml | config | 41 manual rows | Generated | Not CLI-wired | VERIFIED | reg |
| RS-022 | config/genai_queries.yaml | config | v1.0; en, es, fr, pt; no `it` | PI D4 | PI ruling to change | VERIFIED | reg |
| RS-023 | config/schema/procurement_record.schema.json | schema | Intermediate, 33 properties | Agent | — | VERIFIED | reg |
| RS-024 | config/schema/procurement_extension.schema.json | schema | 26 properties; none of IR's 4 proposed fields | Agent | — | VERIFIED | reg |
| RS-025 | config/schema/institution_link.schema.json | schema | 16 properties incl. ES §5 columns + master_build_id | Agent | — | VERIFIED | reg |
| RS-026 | config/schema/institution_review.schema.json | schema | 16 properties | Agent | — | VERIFIED | reg |
| RS-027 | config/sources.example.yaml | config | Config-row template | Agent | — | LISTED | reg |
| RS-028 | pipeline/cli.py + pipeline/core/base.py | code | run/export/sources; unverified guard; window; cache; `--match`; `write_manifest()` (versions, counts, 3 QC booleans; no language-coverage field) | Agent/RA | — | VERIFIED | reg |
| RS-029 | pipeline/core/standardize.py | code | `extract_ocds()` one record per award/lot; item-level R1-R5; `build_extension()` | Agent/RA | — | VERIFIED | reg |
| RS-030 | pipeline/core/classify.py + search.py | code | `NLPClassifier` nlp/terms@1.0; `not_assessable` (R8); cannot_type; LLM stub raises | Agent/RA | — | VERIFIED | reg |
| RS-031 | pipeline/core/coding.py + contract.py | code | Coding rules; `CONTRACT_VERSION = "2.0"`; defaults | Agent/RA | — | VERIFIED | reg |
| RS-032 | pipeline/core/matcher.py | code | Tiers 0/1/3/4/5, ledger, duplicate flag, subnational corroboration; no auto-accept; nothing closes review rows | Agent/RA | Master read-only | VERIFIED | reg |
| RS-033 | pipeline/core/store.py + models.py | code | `StagingStore`: 4 tables, schema validation before write, CSV export | Agent/RA | — | VERIFIED | reg |
| RS-034 | pipeline/adapters/api/ury_…arce…ocds.py | code | ARCE adapter: month RSS, retries, failure records, cache | RA | Browser UA; ToS review open | VERIFIED | reg |
| RS-035 | pipeline/adapters/api/bra_…pncp.py | code | PNCP non-OCDS adapter | RA | unverified | LISTED | reg |
| RS-036 | pipeline/adapters/{api,bulk,scrape}/_template.py + READMEs | code | Templates only; no bulk or scrape adapter | Agent | — | LISTED | reg |
| RS-037 | tests/ (test_core 60, test_matcher 21, test_item_level 10, test_arce_adapter 7/8 repo, test_template 1) | tests | HI 104 pass (Drive 10-09); LOG 105 pass (repo 10-26); CI green | RA | — | VERIFIED (defs counted, not run) | reg |
| RS-038 | tests/fixtures/_ocds_sample/ (5 synthetic) + tests/fixtures/ury_…/ (101 payloads) | fixtures | Synthetic never in output; URY real 2026-09-15 payloads | RA | — | VERIFIED | reg |
| RS-039 | requirements.txt | env | Pinned deps | Agent | — | LISTED | reg |
| RS-040 | .github/workflows/procurement.yml + CI runs | CI | pytest Ubuntu/Windows, py3.11/3.12; green on 8b4e211, cee79b2, 4 branches | PI 8b4e211 | — | VERIFIED | unreg |
| RS-041 | repo procurement/README.md | doc | Repo README: migrated 2026-10-11, code-only, master paths passed explicitly | PI | — | VERIFIED | unreg |
| RS-042 | PP\outputs\staging\ + outputs\per_source\ (BRA 5, URY 132) | dataset | Live staging: BRA 5-row checkpoint + URY 132-row old-extractor probe | RA | Not the master | VERIFIED (listing) | reg |
| RS-043 | PP\archive\5record-checkpoint-2026-08-29\ | dataset | Original 5+5 checkpoint staging | RA | Archive | VERIFIED (listing) | reg |
| RS-044 | PP\agent-workspace\2026-08-29-pi-checkpoint-draft.md | doc | DRAFT checkpoint note BRA+URY, "not sent yet" | Agent | Draft | VERIFIED | reg |
| RS-045 | PP\outputs\diagnostics\uruguay-n100-2026-09-15\original\ + REVISED-2026-10-07.md | dataset/doc | n=100 diagnostic as sent + PI-requested rewording | RA | — | VERIFIED (listing) | reg |
| RS-046 | …\reconciliation\ | code/data | 100 fetched / 101 cached / 91 OCIDs / 132-row map | RA | — | LISTED | reg |
| RS-047 | …\rerun-2026-10-09\ | code/data | Offline replay, code 398167e2…: 132 rows, 71 confirms_absence, 61 not_assessable, 0 yes/unclear, 0 linked, 132 in review (48 buyers); `links.csv` header only | RA | — | VERIFIED | reg |
| RS-048 | PP\outputs\validation\classification_candidates_ury_n100.csv | dataset | Unlabelled frame, 71 neg + 61 n/a; no positives | RA | — | LISTED | reg |
| RS-049 | PP\data_cache\ury_…arce…\ | raw cache | 20 payloads, no manifest anywhere | RA (provenance unconfirmed) | git-ignored | LISTED | unreg |
| RS-050 | inputs\…\data_final\master_institutions.csv | dataset | Build mb-2026-07-30; ITA 7,957, BRA 5,648, URY 185 | Master team | Read-only | VERIFIED (header + counts) | root (not checked) |
| RS-051 | inputs\…\data_final\institution_key_ledger.csv | dataset | 719,588 active, 745 absent, 0 retired, 0 merged | Master team | Read-only | VERIFIED | root (not checked) |
| RS-052 | inputs\…\data_final\ jurisdiction ledger, pre-districts master, skeleton, README | dataset | Not channel inputs | Master team | Read-only | VERIFIED (headers) | root (not checked) |
| RS-053 | G3O origin/main g3o/discovery/query_builder.py `GENAI_TERMS_BY_LANG["it"]` | code | 4 root-discovery Italian terms | Root pipeline | Not procurement-approved (D4) | VERIFIED | n/a |
| RS-054 | subprojects\multilingual-pipeline\rosters\ | folder | Only `archive/`; no Italian or typing roster | Multilingual | — | VERIFIED | n/a |
| RS-055 | PP\interaction-log.csv (LOG) | log | Last row 2026-10-26 (Asenat): ANAC findings, 781cf0c unpushed | Agents | Concurrent writers | VERIFIED | reg |
| RS-056 | Board #81-87, #141, #143 | external | All OPEN (checkpoint, sample-replaced notice, items[] gate, v2.2 re-pin, vendor:multiple, threshold, non-English typing, four approvals, code into repo) | Board | Private | VERIFIED (titles) | n/a |
| RS-057 | Commit 781cf0c (procurement/italy, Asenat) | git | Not in this clone | Asenat | Unpushed | UNVERIFIED | unreg |
| RS-058 | repo procurement/planning/ | governance | Untracked | This session | — | VERIFIED | unreg |
| RS-059 | PP\agent-workspace\2026-10-11-asenat-onboarding-DRAFT.md + .html | doc | Italy RA onboarding | Agent | Draft | VERIFIED (headings) | unreg |
| RS-060 | PP\docs\RA-onboarding.md | doc | RA brief | Agent | — | VERIFIED (headings) | reg |
| RS-061 | PP\docs\PI-email-2026-08-04.md; registry path docs/PI-questions-2026-08-04.md | doc | PI-email present; registered PI-questions path missing | RA | — | VERIFIED / path missing | PI-email unreg; row 71 reg |
| RS-062 | PP\archive\ (pre-item-level code, pre-3-Aug tree, superseded instruments, n5 material, old log) | archive | Superseded | Agents | Archive | LISTED | reg |
| RS-063 | PP\agent-workspace\2026-08-29-summary.md/.html, email-to-PI-2026-08-03.md | doc | Status summary, email draft | Agent/RA | Scratch | VERIFIED (headings) | .html reg; .md unreg |
| RS-064 | PP\pipeline\ + config\ + tests\ (Drive code copy) | code copy | Equals migration commit 55fe353 | RA | R-038 | VERIFIED (hashes) | reg |

## Drive pipeline/ vs repo drift

Method: git blob SHA-1 of each Drive file against `git ls-tree -r procurement/main procurement/`. A CRLF-normalised check was also run. Excluded: outputs/, archive/, agent-workspace/, data_cache/, __pycache__ and desktop.ini. All four branches are at `cee79b2`. Result: 148 files identical, 4 differ, plus the one-sided files below.

| Path | Status | Drive mtime | Evidence |
|---|---|---|---|
| pipeline/cli.py | differs; repo ahead | 2026-10-09 | Drive c47c583 = 55fe353 blob; repo e7fbd76 from 8b4e211 (Simone, 2026-10-11): `code_hash()` uses `as_posix()` |
| tests/test_arce_adapter.py | differs; repo ahead | 2026-10-09 | Repo adds `test_code_hash_is_independent_of_os_path_separator` |
| README.md | differs; different documents | 2026-10-09 | Drive = subproject manual; repo = repo README |
| CLAUDE.md | differs; different documents | 2026-08-27 | Drive = PC; repo = RC |
| .gitattributes, .github/workflows/procurement.yml | repo only | — | eol=lf; CI |
| procurement/planning/* | repo working tree, untracked | — | this plan |
| AGENTS.md, asset-registry.csv, implementation-roadmap.md, interaction-log, docs/*.md, tracker xlsx | Drive only | to 2026-10-26 | By design (repo README: docs and logs stay on Drive) |
| config/, rest of pipeline/, tests/ incl. fixtures, docs/reference/, requirements.txt, .gitignore | identical | ≤ 2026-10-09 | 148 matching blobs |

No file in the compared trees was modified after 2026-10-11. Consequence: HI's code fingerprint `398167e2…` describes the Drive copy and 55fe353. The repo's fingerprint differs by construction (8b4e211 changed `cli.py`); it was not computed. Commit 781cf0c is not in this clone. Authority is not decided here (RQ-001).

## Resource-to-deliverable map

| Spec ID | Needed input | Resource(s) | Relationship | Confidence | Evidence |
|---|---|---|---|---|---|
| D-001 | Contract vocab, crosswalk, coding rules, staged records, links, review decisions, mapper | RS-009, RS-010, RS-002, RS-008, RS-023, RS-029, RS-030, RS-031, RS-033, RS-050, RS-051 | documentation / existing-code / input-data | high for inputs; mapper missing | No contract-row mapper; no `has_genai_activity` aggregation (classify.py/models.py say it is institution-level and not produced) |
| D-002 | Extension schema, builder, item rules | RS-024, RS-029, RS-033, RS-014, RS-002 | existing-code | high | `build_extension()`; replay extensions 132 rows; IR fields absent |
| D-003 | Link schema, matcher, master, ledger | RS-025, RS-032, RS-033, RS-028, RS-050, RS-051 | existing-code / input-data | high (code); low URY yield | 21 matcher tests; replay 0/132 linked; URY 185 master rows |
| D-004 | Review schema, queue writer, closing workflow | RS-026, RS-032, RS-033, RS-047 | existing-code | medium | Queue written; nothing closes rows |
| D-005 | Relevance decision table | RS-023, RS-030, RS-008 | near-match | low | No table or schema; RM item `[ ]` |
| D-006 | Manifest writer, cache, archive | RS-028, RS-034, RS-012, RS-011, RS-038, RS-049 | existing-code | high (code) | `write_manifest()` tested; no real manifest on Drive |
| D-007 | Per-source docs, terms/robots findings | RS-020, RS-018, RS-011, RS-012, RS-055, RS-057 | documentation | medium | No `docs/sources/`; Italy note only in unpushed 781cf0c |
| D-008 | Protocol, frame, labels incl. positives | RS-013, RS-048, RS-030, RS-047 | documentation / input-data | low | 0 positives; no labels |
| D-009 | Stratified buyer sample, labels, scores | RS-032, RS-047, RS-050, RS-013, RS-002 | existing-code / input-data | low | URY queue only; ES §5 strata unmet |
| D-010 | First-source sample per mode + package | RS-043, RS-044, RS-042, RS-019, RS-056, RS-036 | upstream-artifact | high OCDS-API; none bulk/scrape | Checkpoint draft not sent; no bulk/scrape adapter |
| D-011 | Run-report counts, QC | RS-028, RS-046, RS-047, RS-012 | existing-code | medium | No language-coverage field |
| D-012 | Consolidation/dedup/QC | RS-033, RS-042 | near-match | low | No consolidation code |
| D-013 | Clean checkout, rerun | RS-040, RS-047, RS-038, RS-039, RS-041 | software / existing-code | medium | CI from fresh clone; replay offline; no recorded clean-checkout rerun |
| D-014 | Interface draft, adapter base, templates | RS-011, RS-028, RS-036, RS-016 | documentation / existing-code | high (draft) | Unsigned |

R-level links: R-001/R-019 → RS-009, RS-031 (v2.0 only; Q-001). R-009 → RS-030. R-010 → RS-022. R-012 → RS-029, RS-031. R-013 → RS-051, RS-032. R-016 → RS-032 (no threshold). R-023 → RS-030. R-030 → RS-020, RS-028. R-031 → RS-029. R-032 → RS-033. R-033 → RS-028, RS-034. R-034 → RS-023, RS-024. R-036 → RS-021. R-037 → RS-011, RS-005. R-038 → drift section, RS-064. Q-012 → RS-053, RS-054.

## Unresourced deliverables

| Spec ID | Missing | Options | User decision | Status |
|---|---|---|---|---|
| D-001 | Contract-row mapper; institution aggregation; contract pin | (a) create in shared core; (b) revise D-001 to stop at staging until Q-001/Q-018/Q-019; (c) UNRESOLVED | G1: (a) create; blocked on Q-001, Q-018, Q-019 [USER 2026-10-27 (S2)] | DECIDED; blocked on Q-gate |
| D-002 | IR's 4 fields (Q-005); activity-level join (Q-031) | (a) add after ruling; (b) keep 26-field schema; (c) UNRESOLVED | G1: (a) add after Q-005/Q-031 rulings [USER 2026-10-27 (S2)] | DECIDED; blocked on Q-gate |
| D-003 | URY master coverage (C-008); threshold | (a) master expansion; (b) accept gap / revise URY scope; (c) UNRESOLVED | G2: URY coverage stays PI gate Q-010; no Master-team task [USER 2026-10-27 (S2)] | DECIDED; blocked on Q-gate |
| D-004 | Review-closing tool/procedure | (a) create; (b) revise to "queue written"; (c) UNRESOLVED | G1: (a) create [USER 2026-10-27 (S2)] | RESOLVED |
| D-005 | Decision table, schema, writer | (a) create; (b) fold into a D-004-style table; (c) UNRESOLVED | G1: (a) create [USER 2026-10-27 (S2)] | RESOLVED |
| D-006 | A real archived run | (a) create via first documented run; (b) replay RS-047 as interim evidence; (c) UNRESOLVED | (a) created by the first documented run [USER 2026-10-27 (S2)] | RESOLVED |
| D-007 | `docs/sources/`; Italy note; ARCE terms review | (a) create `docs/sources/<id>.md`; (b) use `notes_RA_Lee`/`verification_note` (Q-032); (c) UNRESOLVED | G1: (a) create; surface blocked on Q-032; Italy evidence per RQ-002 a [USER 2026-10-27 (S2)] | DECIDED; blocked on Q-gate |
| D-008 | Labels, positives (Q-015), coders | (a) acquire; (b) revise scope; (c) UNRESOLVED | G1: (a) acquire; blocked on Q-015 [USER 2026-10-27 (S2)] | DECIDED; blocked on Q-gate |
| D-009 | Stratified sample + labels; VP §B amendment | (a) create from other sources' queues; (b) revise strata to available countries; (c) UNRESOLVED | G1: (a) create (ES §5 strata, Q-036 a) [USER 2026-10-27 (S2)] | RESOLVED |
| D-010 | Bulk/scrape adapters + samples; OCDS-API package unpresented | (a) create; (b) present existing package; (c) UNRESOLVED | G3: present the existing OCDS-API package + build bulk/scrape first sources [USER 2026-10-27 (S2)] | RESOLVED |
| D-011 | Per-source language-coverage status | (a) add to manifest/report; (b) report outside the manifest; (c) UNRESOLVED | G1: (a) add language-coverage status [USER 2026-10-27 (S2)] | RESOLVED |
| D-012 | Consolidation code; landing (Q-019) | (a) create; (b) defer pending Q-019; (c) UNRESOLVED | G1: (a) create; landing blocked on Q-019 [USER 2026-10-27 (S2)] | DECIDED; blocked on Q-gate |
| D-013 | Recorded clean-checkout rerun | (a) create; (b) accept CI + replay; (c) UNRESOLVED | (a) recorded clean-checkout rerun required [USER 2026-10-27 (S2)] | RESOLVED |
| D-014 | RA sign-off for v1.0 | (a) obtain; (b) keep as draft (Q-016); (c) UNRESOLVED | G1: (a) obtain sign-off (Q-016) [USER 2026-10-27 (S2)] | DECIDED; blocked on Q-gate |

## Unmapped resources

| Asset ID | Classification | Reason | User decision |
|---|---|---|---|
| RS-001 | useful | Inventory; registration target | — |
| RS-003-RS-007, RS-015-RS-017, RS-019 | useful | Spec authoritative inputs; govern tasks | — |
| RS-021 | useful | R-036 / Q-024 | — |
| RS-027 | useful | Config-row template | — |
| RS-035 | useful | Non-OCDS API (Q-028); D-010 input | — |
| RS-039 | useful | D-013 environment | — |
| RS-045 | redundant | Superseded by revision + replay; kept for record | — |
| RS-049 | investigate | 20 payloads, no manifest | G5 [USER 2026-10-27 (S2)] |
| RS-052 | out-of-scope | Not channel inputs | — |
| RS-053 | out-of-scope | Italian root terms, not D4-approved | RQ-005 b [USER 2026-10-27 (S2)] |
| RS-054 | investigate | Confirms Q-012/Q-013 inputs undelivered | — |
| RS-055, RS-056 | useful | Log; board gates | — |
| RS-057 | investigate | Italy note not local | — |
| RS-058 | useful | Planning governance | — |
| RS-059, RS-060 | useful | Stage-7 handoff material | — |
| RS-061 | investigate | Registered path missing | — |
| RS-062, RS-063 | redundant | Superseded drafts | — |
| RS-064 | redundant | Drive code copy = 55fe353; repo is baseline; archive decision stays Q-025 | RQ-001 a [USER 2026-10-27 (S2)] |

## Open questions

| ID | Question | Why it matters | Blocking? | Resolution |
|---|---|---|---|---|
| RQ-001 | Authoritative code tree for the baseline (repo `cee79b2` incl. 8b4e211, or Drive = 55fe353), and which fingerprint completed-task evidence cites | Completed tasks; D-006, D-013 | yes for completed tasks | RESOLVED (a): repo `procurement/main` @ cee79b2 is the baseline; completed-task evidence cites repo commits; HI `398167e2…` kept as the Drive/55fe353 record [USER 2026-10-27 (S2)] |
| RQ-002 | Obtain 781cf0c (after Asenat's write access) and accept its ANAC findings as D-007 evidence? | D-007 Italy, Q-014 | yes for Italy D-007 | RESOLVED (a): obtain 781cf0c once Asenat's write access lands; accept as Italy D-007 evidence. PI asked for an email draft to Asenat (spec/plan, commit code, share resources on Drive) [USER 2026-10-27 (S2)] |
| RQ-003 | Roadmap Phase 1 matcher checklist unchecked vs. README/HI/registry "built": which record governs "done"? | Completed D-003 tasks | no | RESOLVED (a): code + tests decide "done"; matcher enters as complete [USER 2026-10-27 (S2)] |
| RQ-004 | Registry row 71 path missing; is `docs/PI-email-2026-08-04.md` the same document? | Registry integrity | no | G4: recorded as a registry discrepancy; registry not hand-edited [USER 2026-10-27 (S2)] |
| RQ-005 | May root discovery Italian terms (RS-053) inform procurement terms, or only via multilingual (D4)? | Q-012 | no | RESOLVED (b): Italian terms only through the multilingual subproject [USER 2026-10-27 (S2)] |
| RQ-006 | Is tracker `notes_RA_Lee` the column RM Phase 4 means by `notes_RA`, and who is "Lee"? Canonical Sheet not read | D-007 (Q-032), Q-038 | no | PI: "stale". Read as: `notes_RA_Lee` is stale prior-RA notes, not the RM Phase 4 / D-007 surface [USER 2026-10-27 (S2)] |
| RQ-007 | 20 manifest-less cached URY payloads: evidence or unrecorded probe? | D-006 provenance | no | G5: classed investigate, not evidence [USER 2026-10-27 (S2)] |

## Change history
| Version | Change | Approved by/at |
|---|---|---|
| v001 | Initial resource map (Stage 2); gap decisions S2 applied; registration (G6) after approval | Simone Paci 2026-10-27 (chat) |
