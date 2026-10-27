# Plan draft: G3O procurement pipeline (whole pipeline, retrofit)

Status: DRAFT (Stage 3; not reviewed, not adjudicated)
Version: v001-draft.1
Spec: `procurement/planning/SPEC.md` v001-draft.3 (APPROVED 2026-10-27)
Resources: `procurement/planning/RESOURCES.md` v001 (APPROVED 2026-10-27)
Mode: `PLAN_ONLY` (ruling 4): tasks are executed by RAs from Stage 7 handoffs; agents launch nothing.
Drafted: 2026-10-27, researcher session `20261027-claude-v2-0307d4d58c63fd23` (claude-opus-5-5), per `planning-implementation-map-protocol.md` v0.3.
Topology status: provisional until Stage 4 review and Stage 5 adjudication.

## Phase 0: Context and interface inventory

Starting state comes from `RESOURCES.md`. Discovery was not re-run. Only the repo tree listing (`git ls-tree procurement/main -- procurement`) and the `base.py`/`cli.py` entry points were inspected again.

**Code baseline (RQ-001 a).** The baseline is `simonepaciphd/G3O` `procurement/main` @ `cee79b2`. All four procurement branches sit there. The Drive copy `PP\pipeline\` equals `55fe353` and is not a baseline.

**Shared core** (`procurement/pipeline/core/`; changes only on `procurement/main`, R-037):

| Module | Role |
|---|---|
| `base.py` | `SourceAdapter` (search/fetch/extract), `RunReport`, `Pipeline.run` |
| `standardize.py` | Award/lot records, extension builder |
| `classify.py` + `search.py` | Terms classifier, `not_assessable` |
| `coding.py` + `contract.py` | Coding rules; v2.0 vocab mirror |
| `matcher.py` | Tiers 0/1/3/4/5 + ledger |
| `store.py` + `models.py` | 4 schema-validated staging tables |

Other surfaces in the repo tree:
- `procurement/pipeline/cli.py`: `run`/`export`/`sources`, `code_hash()`, `write_manifest()`.
- Adapters: `pipeline/adapters/{api,bulk,scrape}/`. These hold templates plus `ury_…arce…ocds.py` and `bra_…pncp.py`.
- Config: `config/sources.yaml` (150 rows), `manual_sources.yaml` (41), `genai_queries.yaml` v1.0, and `config/schema/*.json` (4).
- Tests: `tests/` (5 files), with CI in `.github/workflows/procurement.yml`.

**Data and outputs.** These live on Drive, in `PP\outputs\`, `PP\data_cache\` and run archives (R-038). Read-only inputs are the master and the key ledger under `inputs\G3O_Institution_Master\data_final\` (RS-050, RS-051).

**Interfaces:**
- Adapter → core: intermediate dict (RS-011 §4, draft).
- Core → staging: 4 tables (RS-033).
- Staging → contract rows: **does not exist** (D-001 gap).
- Run → manifest: `write_manifest()` (RS-028).

**Test, deploy and rollback.**
- Tests: pytest. CI runs on all `procurement/*` branches, Ubuntu and Windows, py3.11/3.12.
- There is no deploy step.
- Rollback is git revert on a branch. Drive outputs are archived, never overwritten (PC "Archive, don't delete").

**People and capacity.** Execution is by people (C-004):
- Ainhoa Zamora: shared core + Uruguay. Availability not ruled (Q-037 residual). Not yet a repo collaborator (C-006).
- Asenat Mantovani: Italy, `procurement/italy`. Invite pending (C-006).
- PI: all researcher gates.
- Human coders: unnamed.
- Multilingual subproject owner: external.
- Master Database Team: external.
- Plan integrator / `CHANGELOG.md` writer: OPEN (DEC-009).

**Coordination.** Live claims were checked 2026-10-27. This session claims `procurement/planning/`, and no other session claims procurement paths.

**Debt that affects the goal:**
- The code mirrors contract v2.0 (Q-001).
- There is no contract-row mapper.
- The handoff-index fingerprint `398167e2…` describes `55fe353`, not the baseline.
- The roadmap's Phase 1 checkboxes lag the code (RQ-003).

### Input classification

| Input | Class | Resource |
|---|---|---|
| Shared core, matcher, CLI, ARCE adapter, PNCP adapter, schemas, fixtures, tests, CI | EXISTS | RS-020-RS-041 |
| Master + key ledger | EXISTS (EXTERNAL owner) | RS-050, RS-051 |
| Contract text | EXISTS (EXTERNAL, read-only) | RS-009, RS-010 |
| n=100 replay, reconciliation | EXISTS | RS-046, RS-047 |
| OCDS-API checkpoint package | EXISTS (unpresented) | RS-043, RS-044 |
| Asenat's Italy findings (781cf0c) | USER-SUPPLIED (not local) | RS-057 |
| Contract-row mapper, aggregation, decision table, review closing, absence rows, language-coverage field, consolidation, bulk/scrape adapters, `docs/sources/` surface | TO-BUILD | gaps in RESOURCES |
| Human labels (classifier, matcher), positives | USER-SUPPLIED | Q-015 |
| Italian query terms, non-English typing rosters | EXTERNAL (multilingual) | RS-054; RQ-005 b |
| PI rulings on Q-001-Q-038 residuals | USER-SUPPLIED | SPEC open questions |
| Uruguay master coverage | EXTERNAL (Master team), PI gate Q-010 | RS-050 |

## Phase 1: Decisions

These are mechanical choices made under existing conventions. Choices reserved to the PI are not made here; they appear as researcher gates.

| Decision ID | Question | Chosen option | Alternatives rejected | Reason | Spec IDs | Confidence | Reversible? |
|---|---|---|---|---|---|---|---|
| DEC-001 | How do already-delivered pieces enter? | As `complete` cards T-001-T-009, citing commit/file/test evidence; no rework | Re-plan from zero | Ruling 2a; RQ-003 a | all | high | yes |
| DEC-002 | Where do contract-row production and aggregation live? | New shared-core modules on `procurement/main`, after the staging tables, never in adapters | In adapters; in root G3O | R-037; ES §2 (adapters stay thin) | D-001, R-022 | high | yes |
| DEC-003 | Activity identity in code | Add an `activity_id` derived from the OCID to the staged record; staging stays per award/lot; the mapper collapses per activity | Collapse at staging | R-012 (staging per award, PI Q6); Q-031 b | R-005, R-012 | medium | yes |
| DEC-004 | Unit of work for the 150 automatable sources | One per-source card template (T-034.x) instantiated per source, after the access-mode checkpoint | One card per source now | 150 near-identical cards are unreviewable; sources are released by PI gates | G-001, A-005 | medium | yes |
| DEC-005 | Validation labelling | Separate labelling tasks owned by human coders, distinct from report tasks | RA labels own outputs | R-040 (blind, two coders) | D-008, D-009 | high | yes |
| DEC-006 | Integration of country branches | Country branches merge into `procurement/main` only through the integrator, after CI passes; merge order is core first, then countries | Direct pushes to main | RC "Branches"; one integrator per shared surface | R-037 | high | yes |
| DEC-007 | Where documentation-only edits to Drive docs (RM checkboxes, VP §B amendment draft) happen | By the owning RA in the Drive subproject, logged in `interaction-log.csv` | Agent edits | Card boundary: this session makes no Drive edits; RA work follows PP rules | D-009, RQ-003 | high | yes |
| DEC-008 | First documented run | The Uruguay run (T-035) is the first archived run creating D-006 | A synthetic run | D-006 a | D-006, D-013 | medium | yes |
| DEC-009 | Plan integrator and sole `CHANGELOG.md` writer | **OPEN: USER-DECISION at Stage 5**. Candidates: PI; Ainhoa (core owner); an agent session acting for the PI | — | Protocol requires one; ruling 4 names no integrator | all | — | — |

## Phase 2: Requirement traceability

"Producer" is the task that delivers the item. "Verifier" is the independent check. **B** marks a producer blocked on a gate. Status values: `covered` (producer is complete or ready), `planned` (producer pending), `blocked`.

| Spec ID | Required result/test | Producer task(s) | Verifier/reviewer task(s) | Status |
|---|---|---|---|---|
| G-001 | All 191 repositories processed | T-034.x, T-032, T-033, T-036, T-038, T-039 (B) | T-042 | blocked (Q-024, Q-038) |
| G-002 | Contract-conformant rows | T-014 (B) | T-049 | blocked (Q-001) |
| G-003 | Census: absence recorded | T-019 | T-049 | planned |
| G-004 | Extension only for non-contract detail | T-001 (complete), T-021 (B) | T-049 | covered / blocked (Q-005) |
| G-005 | Reproducible by another person | T-003 (complete), T-041 | T-041 (reproducer) | planned |
| G-006 | Downstream use | — | — | blocked (Q-019); no producer until ruled |
| D-001 | Primary rows | T-014 (B) | T-049 | blocked (Q-001, Q-018, Q-019) |
| D-002 | Extension table | T-001, T-021 (B) | T-049 | covered / blocked |
| D-003 | Link table | T-002 | T-024 | covered |
| D-004 | Review queue + closing | T-002, T-017 | T-024 | planned |
| D-005 | Relevance decision record | T-016 | T-049 | planned |
| D-006 | Per-run archive | T-003, T-035 | T-041 | planned |
| D-007 | Per-source docs | T-012, T-028 (B) | T-041 | blocked (Q-032) |
| D-008 | Classification validation report | T-025 (B), T-026, T-027 | PI gate on T-027 | blocked (Q-015) |
| D-009 | Matcher validation report | T-022, T-023, T-024 | PI gate on T-024 | planned |
| D-010 | Checkpoint package per mode | T-006 (complete), T-031, T-032, T-033 | PI gate | planned |
| D-011 | Run/coverage report | T-003, T-020 | T-049 | planned |
| D-012 | Consolidated output | T-040 (B) | T-049 | blocked (Q-019) |
| D-013 | Clean-checkout rerun | T-041 | PI gate | planned |
| D-014 | Signed interface | T-008 (complete), T-037 | PI gate | planned |
| R-001, R-019 | Conform; no `null` | T-013 (B), T-014 (B) | T-049 (A-001) | blocked (Q-001) |
| R-002, R-003, N-001-N-003 | Scope guard | All cards: "Excluded" boundary | T-050 plan-level scope audit | covered |
| R-004 | Extension fields evidenced | T-001, T-021 (B) | T-049 | covered / blocked |
| R-005, R-006 | Stage coding | T-001 (`coding.py`), T-015; T-013 (B) for `proposed` vs §4.3 | T-049 (A-003) | planned / blocked (Q-002) |
| R-007 | `cannot_type` → `unknown` | T-013 (B) | T-049 (A-011) | blocked (Q-001, Q-003) |
| R-008, R-009, R-010 | Typing, deterministic, query set | T-001 (complete) | T-027 | covered |
| R-011 | Full history; earliest date | T-003 (window), T-035 (B) | T-041 | blocked (Q-007) |
| R-012 | Award staging; activity per OCID; `vendor: multiple` | T-001, T-015; Q-004 gate on T-014 | T-049 | planned |
| R-013-R-015, R-017 | Matching rules | T-002 (complete) | T-024 | covered |
| R-016 | Threshold from validation | T-024 → PI gate | PI | planned |
| R-018 | No unresolved institution in primary | T-014 (B) | T-049 (A-002) | blocked |
| R-020, R-025, R-026 | Provenance-safe text fields | T-001, T-014 (B) | T-049 | covered / blocked |
| R-021 | Absence rows + language status | T-019, T-020 | T-049 | planned |
| R-022 | Institution aggregation | T-018 (B) | T-049 | blocked (Q-018, Q-032) |
| R-023 | `not_assessable` separate | T-001 (complete), T-020 | T-049 (A-011) | covered |
| R-024 | Framework attribution | T-001 (`coding.py`), T-014 (B) | T-049 | covered / blocked |
| R-027 | Review triggers | T-016 | T-049 | planned |
| R-028, R-029 | Smoke run; respect source | T-034.x step 1-2, T-012, T-028 | T-034.x review | planned |
| R-030 | Verification criterion | T-029 (B) | PI/RA approver | blocked (Q-038) |
| R-031 | Money rules | T-001 (complete), T-021 (B) | T-049 | covered |
| R-032, R-033, R-034 | Validation, accounting, provenance | T-001, T-003 (complete) | T-041 | covered |
| R-035 | Instrument versioning | Guard on every card ("Fixed decisions") | T-050 | covered |
| R-036 | Manual sources flagged | T-039 (B) | T-042 | blocked (Q-024) |
| R-037 | Country work boundaries | DEC-006; T-046 | T-046 | planned |
| R-038 | Code in git, data on Drive | T-007 (complete), T-045 (B) | T-046 | covered |
| R-039 | No secrets in code | Guard on every card; CI | T-046 | covered |
| R-040 | Blind two-coder labels | T-023, T-026 | T-024, T-027 | planned |
| R-041 | QC before reporting | T-020 | T-049 | planned |
| A-001-A-003 | Contract, institution, stage checks | T-049 | PI | blocked (via T-014) |
| A-004 | Manifest QC | T-020, T-035 | T-041 | planned |
| A-005 | Smoke + terms per source | T-034.x | PI | planned |
| A-006 | Checkpoint signed per mode | T-031, T-032, T-033 | PI | planned |
| A-007 | Classifier validation | T-027 | PI | blocked (Q-015, Q-020) |
| A-008 | Matcher validation + threshold | T-024 | PI | planned (Q-009b, Q-020 gates) |
| A-009, A-010 | Reproduction; clean checkout | T-041 | PI | planned |
| A-011 | `not_assessable`/`cannot_type` counts | T-020 | T-049 | planned |
| A-012 | Coverage of 191 | T-042 (B) | PI | blocked (Q-024, Q-038) |
| C-001, C-002 | Read-only contract, inputs, master | Guard on every card | T-046 | covered |
| C-003 | Planning location | This plan | — | covered |
| C-004 | Agents launch nothing | Stage 7 handoffs only | — | covered |
| C-005 | Meaning decisions are the PI's | Researcher gates | — | covered |
| C-006 | Write access | T-011 | PI | planned |
| C-007 | Uruguay fetch cost | T-035 sizing | PI gate Q-007 | planned |
| C-008 | Uruguay master coverage | PI gate Q-010 on T-035/T-014 | — | blocked |
| N-004 | No language decisions here | T-043, T-044 EXTERNAL | — | covered |
| N-005 | No LLM adjudication in the pilot | Guard (T-001 stub raises) | T-050 | covered |
| N-006 | Staging is not the master | Guard; T-040 | T-049 | covered |
| N-007 | `background_only` not repurposed | Guard on T-014 | T-049 | covered |
| N-008 | No prevalence from validation | Guard on T-027 | PI | covered |

## Phase 3: Task cards

### Defaults inherited by every card

Each card below states only what differs from these defaults. A field not stated on a card means the default applies.

- **Spec version:** `SPEC.md` v001-draft.3. It is locked at Stage 6; the cards carry the locked version from then on.
- **Persona/role:**
  - Human RA tasks: the named RA working through the RA harness (`paci-research-lab/ra-ai-os`). The RA's agent works under `procurement/CLAUDE.md` (RC).
  - PI tasks: Simone.
- **Tools:** git and GitHub (repo `simonepaciphd/G3O`), Python 3.11/3.12 with `procurement/requirements.txt`, and pytest. The Drive subproject is used for data, outputs and logs.
- **Skills/protocols:** RC (`procurement/CLAUDE.md`) and PC (`PP\CLAUDE.md`). Read-only references: ES (`PP\docs\procurement-extension-spec.md`) and CB (`PP\docs\genai-procurement-codebook.md`).
- **Working directory:** the RA's clone of `simonepaciphd/G3O`, on the branch named on the card. Data stays on Drive `PP\`.
- **Collision control:**
  - Read scope is the whole repo.
  - The write claim is only the paths on the card.
  - The shared surface `procurement/pipeline/core/` has one owner, Ainhoa. Its integrator is DEC-009.
- **Fixed decisions, never reopened by a task:**
  - all approved spec items and PI rulings;
  - query set v1.0;
  - codebook v0.4;
  - the contract file is read-only;
  - `inputs/` and the master are read-only;
  - no LLM adjudication;
  - no secrets in code;
  - no new unit, taxonomy or source.
- **Spec-change reporting:**
  - Report to the plan integrator (DEC-009).
  - Report when the source data contradicts a spec rule, a rule is ambiguous for a real record, a new constraint appears (terms, blocking, cost), or the output would deviate from an acceptance test.
  - Stop boundary: no output that depends on the contested rule is written or staged.
  - Safe continuation: tests, fixtures and independent sources.
  - Forbidden: editing `SPEC.md`, `CHANGELOG.md` or PLAN files.
- **Return report:** to the integrator. It lists changed files, each check with its evidence, failures, blockers, unresolved decisions, and the proposed status (`verified` or `blocked`). Only the integrator marks a task `complete`.
- **Failure and rollback:** revert the branch commit. Archived Drive outputs are never overwritten; a rerun writes a new run folder.
- **Chunking trigger:** split the task into sequential handoffs when it spans more than one session or mixes core and country writes.

### Completed work (DEC-001; ruling 2a; RQ-003 a)

| Card | Delivered | Spec refs | Evidence | Status |
|---|---|---|---|---|
| T-001 | Shared staging core:<br>- term search + deterministic classifier (`nlp/terms@1.0`, LLM stub raises)<br>- one staged record per award/lot<br>- item-level rules R1-R5, R8 (`not_assessable`)<br>- coding rules (stage, type, vendor, framework)<br>- extension builder<br>- 4 schema-validated staging tables | D-002, R-004, R-005, R-008-R-010, R-012 (staging half), R-019, R-020, R-023, R-024, R-031, R-032, R-034 | RS-029-RS-033; tests RS-037 (HI: 104 pass on Drive 10-09; LOG: 105 pass on the repo 10-26); CI green on `cee79b2` (RS-040) | complete. Money-field rules still sit behind gate Q-005 (T-021) |
| T-002 | Matcher tiers 0/1/3/4/5 with ledger resolution, duplicate flag and subnational corroboration; link and review tables; `--match` | D-003, D-004 (queue half), R-013-R-015, R-017 | RS-032, RS-025, RS-026; 21 matcher tests; replay review queue 132 rows / 48 buyers (RS-047) | complete (RQ-003 a). No auto-accept (R-016) |
| T-003 | Run controls:<br>- unverified-source guard<br>- window<br>- cache<br>- retries and failure accounting<br>- manifest writer (versions, counts, QC booleans) | D-006 (writer), D-011 (counts), R-030 (guard), R-033, R-034 | RS-028, RS-034; `test_cli_run_writes_a_manifest…` | complete |
| T-004 | Uruguay ARCE OCDS adapter + 101 real fixture payloads | Uruguay source, R-028 | RS-034, RS-038; `test_arce_adapter.py` | complete |
| T-005 | n=100 Uruguay diagnostic, reconciliation, offline replay with current code | D-011 pattern, C-007, C-008 | RS-045-RS-047: 132 rows, 71 `confirms_absence`, 61 `not_assessable`, 0 linked | complete |
| T-006 | OCDS-API 5-record checkpoint package (BRA + URY) prepared | D-010 (preparation) | RS-043, RS-044 ("not sent yet"); board #81 OPEN | complete as preparation; presentation is T-031 |
| T-007 | Code migrated to git; OS-independent fingerprint; CI on all procurement branches; RA repo manual | R-038, R-039 | `55fe353`, `8b4e211`, `cee79b2`; RS-040, RS-041, RS-005 | complete. Remaining #143 items are T-011 and T-045 |
| T-008 | Draft protocols: adapter interface v0.1, Uruguay full-run protocol, validation protocol | D-014, D-006, D-008, D-009 (drafts) | RS-011-RS-013 | complete as drafts; sign-off is T-037, Q-016 |
| T-009 | Brazil PNCP non-OCDS adapter + 5-record sample | Phase 2 non-OCDS | RS-035 (LISTED only), RS-042 | complete, **evidence LISTED, not opened**; Brazil assignment is Q-028 |

### New cards

#### T-011: Give both RAs working repo access and land Asenat's commit

- Status: ready. Type: operate. Priority: critical-path.
- Spec refs: C-006, R-038, D-007. Decision refs: RQ-002 a.
- **Objective:** both RAs can push their branches, and 781cf0c is on `origin/procurement/italy`.
- **Inputs:**
  - invite 339864628 (pending);
  - Ainhoa's GitHub login (unknown);
  - 781cf0c on Asenat's machine (USER-SUPPLIED).
- **Outputs:**
  - `origin/procurement/italy` contains 781cf0c;
  - both RAs listed as collaborators;
  - Asenat's non-code Italy material in `PP\` (PI email, 2026-10-27 draft).
- **Owner:** PI (invites), Asenat (push, Drive upload), Ainhoa (accept).
- **Dependencies:** requires none; enables T-012, T-015-T-020, T-022, T-037.
- **Researcher gates:**
  - Ainhoa's availability (Q-037 residual);
  - Ainhoa's login.
- **Write claim:** `procurement/italy` (Asenat).
- **Self-checks:**
  - `git ls-remote origin procurement/italy` shows a commit whose ancestry contains 781cf0c;
  - CI green on that push;
  - collaborator list via `gh api repos/simonepaciphd/G3O/collaborators`.
- **Done:** both checks pass and are recorded in `PP\interaction-log.csv`.

#### T-012: Record the Italy ANAC source findings as source documentation

- Status: pending (needs T-011). Type: document. Priority: required.
- Spec refs: D-007, R-029, Q-014.
- **Objective:** the ANAC terms, robots and blocking findings are recorded in the Italy config row's `verification_note`, with evidence. The final documentation surface waits on Q-032.
- **Inputs:** 781cf0c; LOG 2026-10-26 (RS-055).
- **Outputs:** `procurement/config/sources.yaml` (`ita_anac_bdncp_open_data_ocds` row) on `procurement/italy`.
- **Owner:** Asenat.
- **Researcher gates:** none to start. The Q-014 answers come later.
- **Write claim:** that one row.
- **Self-checks:**
  - YAML loads;
  - `pipeline.cli sources` lists the row;
  - CI green.
- **Review:** integrator reads the note against LOG.
- **Excluded:**
  - live API or portal requests (Q-014);
  - any change to `verification_status` (R-030; T-029).
- **Done:** note merged to `procurement/italy`; status unchanged.

#### T-013: Re-pin the contract mirror to the version of record

- Status: blocked, BLOCKED-SPEC (Q-001; also Q-002, Q-003). Type: migrate. Priority: critical-path.
- Spec refs: R-001, R-006, R-007, R-019, C-001.
- **Objective:** `contract.py` and the reference snapshot match the PI-ruled contract version. If that version admits `unknown`, `cannot_type` codes `activity_type: unknown` (Q-032 b). `proposed` for tenders follows the Q-002 ruling.
- **Inputs:** RS-009 (CT v2.5), RS-010 (SN v2.0), the PI ruling.
- **Outputs:**
  - `procurement/pipeline/core/contract.py`;
  - `procurement/docs/reference/output_contract_v<X>.SNAPSHOT.md` (new file; v2.0 kept);
  - `coding.py` changes for `unknown` and `proposed`;
  - tests.
- **Owner:** Ainhoa, on `procurement/main`.
- **Researcher gates:**
  - Q-001 (version);
  - Q-002 (tenders);
  - Q-003 (lift D1; §4.2 line-edit).
- **Write claim:** `contract.py`, `coding.py`, `docs/reference/`, `tests/test_core.py`.
- **Self-checks:**
  - a test asserts every vocab member equals the snapshot's enum tables;
  - snapshot sha256 recorded in its README;
  - all tests and CI pass.
- **Review:** integrator diffs the vocab against CT.
- **Acceptance tests:** A-001 (partial).
- **Done:** merged on main; snapshot and version recorded in the manifest field `contract_version`.

#### T-015: Carry activity identity (OCID) through staging

- Status: pending (needs T-011). Type: build. Priority: critical-path.
- Spec refs: R-005, R-012, Q-031 (resolved part). Decision refs: DEC-003.
- **Objective:** every staged OCDS record carries `activity_id` = OCID, while staging stays per award/lot. Non-OCDS sources raise "activity id undefined" until the Q-031 residual is ruled.
- **Inputs:** RS-029, RS-023, RS-038.
- **Outputs:**
  - `standardize.py`;
  - `config/schema/procurement_record.schema.json` (new property);
  - `models.py`;
  - tests.
- **Owner:** Ainhoa (main).
- **Researcher gates:** none for OCDS. Non-OCDS waits on the Q-031 residual.
- **Write claim:** `standardize.py`, `models.py`, `procurement_record.schema.json`, `tests/test_core.py`.
- **Self-checks:**
  - on the 5 synthetic fixtures plus 101 Uruguay fixtures, `activity_id` is non-empty;
  - records of one OCID share it;
  - the multi-lot fixture gives n records and 1 `activity_id`;
  - the replay reproduces 132 rows.
- **Excluded:** collapsing to contract rows (T-014); the D-002 join (Q-031 residual).
- **Done:** checks pass; CI green; merged.

#### T-016: Build the relevance review decision record

- Status: pending (needs T-011). Type: build. Priority: required.
- Spec refs: D-005, R-027.
- **Objective:** a persisted, schema-validated table of human relevance decisions. Fields: reviewer, final relevance and activity type, evidence, rationale, identity, timestamp (CB §8). Each decision is keyed to `record_id`.
- **Inputs:** RS-008 §8, RS-023, RS-033.
- **Outputs:**
  - `config/schema/relevance_review.schema.json`;
  - a fifth table in `store.py`;
  - a CSV export;
  - a CLI subcommand to load decisions from a reviewer CSV.
- **Owner:** Ainhoa (main).
- **Researcher gates:** confirm that the field list matches CB §8. This is a PI check, not a design choice.
- **Write claim:** the new schema, `store.py`, `models.py`, `cli.py` (subcommand only), tests.
- **Self-checks:**
  - schema validation rejects missing reviewer or timestamp;
  - a round trip of reviewer CSV → table → export is lossless;
  - a record with a decision is no longer listed as pending.
- **Can run with:** T-015 (disjoint except `models.py`; sequence T-015 → T-016 within Ainhoa's lane).
- **Done:** checks pass; merged.

#### T-017: Close institution review rows (confirm or reject)

- Status: pending (needs T-016, because both write `store.py`). Type: build. Priority: required.
- Spec refs: D-004, R-017.
- **Objective:** a reviewer can confirm a candidate, which writes a resolved `institution_link` with reviewer and time, or close it as rejected. No unresolved uid enters the link table.
- **Inputs:** RS-026, RS-032, RS-033, the replay queue (RS-047).
- **Outputs:** `store.py`/`matcher.py` closing functions; a CLI subcommand; tests.
- **Owner:** Ainhoa (main).
- **Write claim:** `store.py`, `matcher.py`, `cli.py` (subcommand), tests.
- **Self-checks:**
  - confirm moves the row to links with `match_method` = reviewed;
  - reject leaves no link;
  - a uid absent from the ledger is refused (A-002).
- **Done:** checks pass; merged.

#### T-018: Aggregate `has_genai_activity` per institution

- Status: blocked, BLOCKED-SPEC (Q-018 scope and owner; Q-032 residual `not_assessable` weight). Type: build. Priority: critical-path.
- Spec refs: R-022, D-001.
- **Objective:** one institution-level value, computed after review over the scope the PI rules, written identically on every row of the institution.
- **Inputs:** staging tables, T-016 decisions, T-017 links.
- **Outputs:** new core module `pipeline/core/aggregate.py`; tests.
- **Owner:** Ainhoa (main).
- **Researcher gates:** Q-018; Q-032 residual.
- **Write claim:** `aggregate.py`, tests.
- **Self-checks:**
  - a property test confirms each institution has exactly one value;
  - one rejected record never yields `no` (R-021, CB §5);
  - `not_assessable` handling follows the ruling.
- **Done:** checks pass; merged.

#### T-019: Emit negative-evidence rows per institution × repository × window

- Status: pending (needs T-015). Type: build. Priority: critical-path.
- Spec refs: R-021, SC-03, G-003, Q-029 b, Q-030 b.
- **Objective:**
  - for each institution with searched, text-bearing records and no GenAI evidence in a source and window, exactly one `confirms_absence` staged row;
  - emitted whether or not the source's language is covered;
  - no extension row for it until the Q-030 residual is ruled.
- **Inputs:** classifier output, link table, run window (T-003).
- **Outputs:** `classify.py` or a new `absence.py`; staging schema property; tests.
- **Owner:** Ainhoa (main).
- **Researcher gates:** Q-030 residual for extension rows only.
- **Write claim:** `absence.py` (new), `models.py`, `procurement_record.schema.json`, tests.
- **Self-checks:**
  - on the replay, the count of absence rows equals the distinct (institution, source, window) cells among the 71 negatives, and 0 come from the 61 `not_assessable`;
  - `not_assessable` never yields absence (R-023).
- **Excluded:** the institution `no` value (T-018).
- **Done:** checks pass; merged.

#### T-020: Report language coverage and QC per run

- Status: pending (needs T-019). Type: build. Priority: required.
- Spec refs: D-011, R-021, R-041, A-004, A-011, Q-029 b.
- **Objective:** the manifest and run report state:
  - each source's language-coverage status against query set v1.0;
  - counts of yes / unclear / no / not-assessable / cannot-type / review / linked / failures;
  - the UP §6 QC booleans (should, Q-016).
- **Inputs:** RS-028, RS-012 §5-6, RS-022, the source language from `sources.yaml`/tracker.
- **Outputs:** `cli.py` `write_manifest()`, `base.py` `RunReport`, tests.
- **Owner:** Ainhoa (main).
- **Researcher gates:** none. Whether the UP §6 checks are binding is Q-016; until then they are reported, not enforced.
- **Write claim:** `cli.py` (manifest), `base.py` (RunReport), tests.
- **Self-checks:**
  - the manifest JSON has `language_coverage` per source;
  - the counts add up to items read (R-033);
  - an Italian-language source shows "not covered".
- **Done:** checks pass; merged.

#### T-014: Map staged records to contract rows

- Status: blocked, BLOCKED-SPEC (Q-001, Q-004, Q-018, Q-019; C-008 via Q-010 for Uruguay yield). Type: build. Priority: critical-path.
- Spec refs: D-001, G-002, R-001, R-005-R-007, R-012, R-018-R-020, R-024-R-026, N-007.
- **Objective:**
  - produce the CT §3.2 columns at the triple grain from staged records, accepted review decisions (T-016), resolved links (T-017) and aggregation (T-018);
  - one activity per OCID with the higher-evidence stage;
  - no row without a resolved institution;
  - no `null`.
- **Inputs:** outputs of T-013, T-015-T-019.
- **Outputs:** `pipeline/core/contract_rows.py`; an `export --contract` CLI path; tests.
- **Owner:** Ainhoa (main).
- **Researcher gates:**
  - Q-001;
  - Q-004 (`vendor: multiple`);
  - Q-019 (landing form);
  - checkpoint review of the first mapped sample (PI).
- **Write claim:** `contract_rows.py`, `cli.py` (export path), tests.
- **Self-checks:**
  - schema and enum validation against the T-013 snapshot gives 0 violations and 0 `null`;
  - every uid resolves in the ledger;
  - no `production`;
  - tender-only rows are `proposed`;
  - the institution value is constant per institution.
- **Acceptance tests:** A-001, A-002, A-003.
- **Done:** checks pass; PI checkpoint signed.

#### T-021: Add the item-level money fields

- Status: blocked, BLOCKED-SPEC (Q-005). Type: build. Priority: optional until ruled.
- Spec refs: D-002, R-004, R-031.
- **Objective:** add the four proposed extension fields (or the PI-amended set) to the schema and builder.
- **Outputs:** `procurement_extension.schema.json`, `standardize.py`, tests.
- **Owner:** Ainhoa (main).
- **Researcher gates:** Q-005.
- **Self-checks:**
  - schema validation;
  - no cross-currency sum (a test with a mixed-currency fixture);
  - each value carries its source.
- **Done:** checks pass; merged.

#### T-022: Design the stratified matcher validation sample

- Status: pending (needs T-011). Type: spike, bounded to one sample design. Priority: required.
- Spec refs: D-009, R-016, Q-036 a.
- **Objective:**
  - a buyer-level sample frame stratified as ES §5 requires (national/subnational × several countries × script), drawn from available review queues and master rows;
  - a proposed VP §B amendment for the PI;
  - where strata cannot be filled yet, the shortfall stated per stratum.
- **Inputs:** RS-002 §5, RS-013 §B, RS-047, RS-050, and any new source queues.
- **Outputs:**
  - `PP\outputs\validation\matcher_sample_frame_<date>.csv`;
  - `PP\agent-workspace\<date>-VP-B-amendment-PROPOSAL.md`.
- **Owner:** Ainhoa.
- **Researcher gates:**
  - PI approves the amendment and the sample;
  - strata that need sources not yet run stay blocked.
- **Write claim:** those two Drive files.
- **Self-checks:**
  - a strata table with counts;
  - the sampling seed recorded;
  - no buyer drawn twice.
- **Done:** files on Drive; PI gate recorded.

#### T-023: Label the matcher sample blind (two coders)

- Status: pending (needs T-022 + PI approval). Type: verify. Priority: required.
- Spec refs: D-009, R-040.
- **Objective:** two independent labels per buyer, with disagreements adjudicated by a third coder or the PI.
- **Outputs:** `PP\outputs\validation\matcher_labels_<date>.csv`.
- **Owner:** human coders (unnamed; PI assigns).
- **Researcher gates:** coder assignment.
- **Self-checks:**
  - every sampled buyer has two labels;
  - coders could not see the matcher score (column absent from their sheet);
  - a disagreement log exists.
- **Done:** labels complete.

#### T-024: Report matcher validation

- Status: pending (needs T-023). Type: verify. Priority: required.
- Spec refs: D-009, A-008, R-016, Q-009b, Q-020.
- **Objective:** precision and recall per tier, plus a precision-vs-score curve for tier 4, per stratum.
- **Outputs:** `PP\outputs\validation\matcher_validation_<date>.md` + a script under `procurement/tools/` (main).
- **Owner:** Ainhoa (report).
- **Researcher gates:** the PI sets the auto-accept threshold, or none (Q-009b, Q-020).
- **Self-checks:**
  - the script reruns from the labels to identical numbers;
  - confidence intervals stated.
- **Done:** report filed; PI decision recorded in SPEC Q-009b.

#### T-025: Assemble the classification validation frame with positives

- Status: blocked, BLOCKED-INPUT (Q-015 positives). Type: build. Priority: required.
- Spec refs: D-008, Q-015, Q-035 a.
- **Objective:** a frame of term-retrieved records, stratified as VP §A requires, including positives from sources other than Uruguay or PI-known cases.
- **Inputs:** RS-048 (0 positives), later source runs.
- **Outputs:** `PP\outputs\validation\classification_frame_<date>.csv`.
- **Owner:** Ainhoa.
- **Researcher gates:** Q-015.
- **Self-checks:** strata counts; seed; provenance per record.

#### T-026: Label the classification frame blind (two coders)

- Status: pending (needs T-025). Type: verify.
- Spec refs: D-008, R-040.
- **Owner:** coders.
- **Self-checks:** as T-023, with the classifier output hidden from coders.

#### T-027: Report classification validation

- Status: pending (needs T-026). Type: verify.
- Spec refs: D-008, A-007, N-008, Q-035 a, Q-020.
- **Objective:**
  - κ, precision for `yes` and `yes ∪ unclear`, and recall among retrieved records, with CIs;
  - an explicit statement that misses by the query terms are unmeasured;
  - errors by language and text source;
  - no prevalence.
- **Owner:** Ainhoa.
- **Researcher gates:** pass threshold (Q-020).
- **Self-checks:** the script reruns to identical numbers; the report states its scope limit verbatim.

#### T-028: Create the per-source documentation surface

- Status: blocked, BLOCKED-SPEC (Q-032 residual: `docs/sources/` vs `verification_note`; `notes_RA_Lee` ruled stale, RQ-006). Type: document.
- Spec refs: D-007, R-029, G-005.
- **Objective:** one documentation record per source covering access, terms/robots/rate-limit findings, endpoint, window and exact commands.
- **Owner:** Ainhoa defines the template; each source's RA fills it in.
- **Self-checks:** every source that has run has a record; the record's commands reproduce the run (checked in T-041).

#### T-029: Write the source verification procedure

- Status: blocked, BLOCKED-SPEC (Q-038 residuals i-iii). Type: document.
- Spec refs: R-030, Q-038, A-012.
- **Objective:** a written procedure for flipping `verification_status`, following the PI's criterion. The criterion is an end-to-end run on the source with output checked to conform; the approver is the RA or the PI.
- **Output:** a section of the T-028 surface plus the `sources.yaml` field rule.
- **Owner:** Ainhoa.
- **Self-checks:** the procedure names the run size, the conformity check and the tracker version.

#### T-031: Present the OCDS-API checkpoint package to the PI

- Status: ready. Type: verify. Priority: critical-path (gates Phase 2 fan-out).
- Spec refs: D-010, A-006, Q-009a.
- **Objective:** the PI receives the 2026-08-29 package (BRA + URY). It also states that the Uruguay sample was replaced (board #82) and how the n=100 replay changes the picture.
- **Inputs:** RS-043, RS-044, RS-047, board #81/#82.
- **Outputs:** the presented package (board #81 comment or email); the PI decision recorded at Q-009a.
- **Owner:** Ainhoa, or an agent acting for the PI if Ainhoa is unavailable (DEC-009 / Q-037).
- **Researcher gates:** Q-009a sign-off.
- **Self-checks:** the package lists its code version, which must be the repo baseline or explicitly `55fe353`.
- **Done:** PI decision recorded.

#### T-032: Build and checkpoint the first bulk source

- Status: blocked (gate: the PI picks the first bulk source, since sources are reserved to the PI by PC; Q-023 for that source). Type: build. Priority: required.
- Spec refs: D-010, A-005, A-006, R-028, R-029.
- **Objective:** a bulk adapter from `adapters/bulk/_template.py`, with a smoke run of 5, a staged sample, and a checkpoint package.
- **Owner:** Ainhoa, or the assigned RA.
- **Write claim:** `adapters/bulk/<source>.py`, its config row, fixtures, tests, on that country's branch.
- **Self-checks:**
  - a terms/robots record;
  - smoke-run manifest archived;
  - schema-valid staging;
  - CI green.

#### T-033: Build and checkpoint the first scrape source

- Status: blocked (same gate as T-032; scraping is most exposed to Q-023). Type: build.
- Spec refs and checks: as T-032, using `adapters/scrape/_template.py`.

#### T-034.x: Per-source fan-out (template, instantiated per source)

- Status: blocked until the checkpoint for the source's access mode is signed (A-006: OCDS-API by T-031; bulk by T-032; scrape by T-033). Type: build/operate.
- Spec refs: G-001, A-005, R-028-R-030, D-006, D-007, D-011.
- **Steps:**
  1. Record terms and robots (T-028 surface).
  2. Run a smoke run of 5, archived.
  3. Write the adapter, reusing the OCDS core for the 65 `is_ocds` sources.
  4. Run a bounded probe.
  5. Request verification (T-029).
  6. Run the full run.
- **Owner:** the RA assigned to the country:
  - Uruguay: Ainhoa;
  - Italy: Asenat, in T-036;
  - Brazil: Q-028;
  - other countries: unassigned (PI).
- **Researcher gates:**
  - per source, Q-023 if the terms or technical blocking forbid access;
  - the per-source window.
- **Write claim:** that source's adapter, config row and tests on its country branch.
- **Done:** run archived; source documentation complete; run report filed.

#### T-035: Uruguay full run, the first documented archived run

- Status: blocked, BLOCKED-SPEC (Q-006 clarification notices; Q-007 window and scope; Q-008 live outputs; Q-010 master coverage; Q-038 verification). Type: operate. Priority: critical-path.
- Spec refs: D-006, D-011, R-011, C-007, DEC-008.
- **Objective:** a run following UP (as amended by PI rulings), archived with manifest, staged tables and cached payloads.
- **Inputs:** T-019, T-020, T-004, the ARCE terms review.
- **Outputs:** `PP\outputs\runs\<run_id>\` (manifest, staging, report); cache under `PP\data_cache\`.
- **Owner:** Ainhoa.
- **Researcher gates:**
  - Q-006, Q-007, Q-008, Q-010;
  - smoke run of 5 first (R-028);
  - PI go for any run of more than 24 h.
- **Self-checks:**
  - all A-004 QC booleans true;
  - fetched + failed = items read;
  - manifest code hash = the repo commit;
  - `not_assessable` reported separately.
- **Done:** archive complete; PI review.

#### T-036: Italy ANAC adapter and run

- Status: blocked, BLOCKED-SPEC (Q-012 Italian terms via multilingual, RQ-005 b; Q-014; Q-023 portal blocking). Type: build/operate.
- Spec refs: D-007, R-028, R-029, Q-014, Q-027.
- **Objective:** an adapter for `ita_anac_bdncp_open_data_ocds`, a smoke run of 5, and a bounded run once access is lawful and the terms exist.
- **Inputs:** T-012, T-044, the PI Q-014 rulings.
- **Owner:** Asenat (`procurement/italy`).
- **Write claim:**
  - `pipeline/adapters/api/ita_anac_bdncp_open_data_ocds.py` (or bulk, per Q-014);
  - its config row;
  - fixtures and tests.
- **Self-checks:**
  - CI green;
  - smoke manifest archived;
  - no request made beyond what the terms allow.
- **Done:** PI review of the smoke run.

#### T-037: Review the adapter interface draft and record sign-off

- Status: pending (needs T-011). Type: verify. Priority: required.
- Spec refs: D-014, Q-016.
- **Objective:** both RAs read adapter-interface v0.1 against the code and return comments; the PI decides v1.0.
- **Outputs:**
  - comments on the board issue;
  - `PP\docs\adapter-output-interface.md` v1.0 (Ainhoa edits after the PI ruling).
- **Owner:** Asenat and Ainhoa (review); PI (sign).
- **Researcher gates:** Q-016 for AI.
- **Self-checks:** every §4 field exists in `procurement_record.schema.json`, or is listed as a discrepancy.

#### T-038: Brazil PNCP

- Status: blocked (Q-028 assignment; Q-031 residual non-OCDS activity id).
- Spec refs: G-001, D-010.
- Owner: unassigned.

#### T-039: Manual sources (41)

- Status: blocked (Q-024).
- Spec refs: R-036, G-001, A-012.
- Owner: PI decides.
- Output: either a flag-only list or human-collection tasks.

#### T-040: Consolidate, deduplicate and QC across sources

- Status: blocked, BLOCKED-SPEC (Q-019; needs T-014). Type: integrate.
- Spec refs: D-012, N-006.
- **Objective:** a cross-source build of D-001-D-003, deduplicated, with QC, in the landing form the PI rules.
- **Owner:** Ainhoa.
- **Self-checks:**
  - unique keys;
  - row counts reconciled to per-source runs;
  - no staged-only rows presented as master.

#### T-041: Reproducibility rerun from a clean checkout

- Status: pending (needs T-035). Type: verify. Priority: required.
- Spec refs: D-013, G-005, A-009, A-010, Q-037 a.
- **Objective:** a person other than the run's author, acting in the reproducer role, reruns a small sample from a clean clone using only the source documentation and the archive. They get identical `record_id`s, field values and code hash.
- **Outputs:** `PP\outputs\runs\<run_id>\reproduction\` (diff report).
- **Owner:** reproducer role (assigned per run; not the run's author).
- **Researcher gates:** the PI assigns the reproducer.
- **Self-checks:** a zero-diff report, or a listed discrepancy.

#### T-042: Coverage table of the 191 repositories

- Status: blocked (Q-024; Q-038 iii frame pin; status vocabulary OPEN in A-012). Type: verify.
- Spec refs: A-012, G-001.
- **Objective:** every repository has a recorded status.
- **Owner:** integrator.

#### T-043 and T-044: EXTERNAL inputs from the multilingual subproject

- T-043: non-English activity typing (Q-013; board #87, owner litong).
- T-044: Italian query terms (Q-012; RQ-005 b).
- Status: blocked. These are tracked here only as dependencies. This plan does no work on them (N-004).

#### T-045: Archive the Drive code copy

- Status: blocked (Q-025 PI ruling). Type: operate.
- Spec refs: R-038; RS-064.
- **Objective:** move `PP\pipeline\`, `config\` and `tests\` to `PP\archive\` with a pointer to the repo.
- **Owner:** PI or an RA.
- **Self-checks:** the hash comparison again shows the Drive copy equal to `55fe353` before the move.

#### T-046: Integrate country branches into main

- Status: pending (runs on each country merge). Type: integrate.
- Spec refs: R-037, R-038, R-039, C-001, C-002. Decision refs: DEC-006.
- **Owner:** integrator (DEC-009).
- **Self-checks:**
  - CI green on the merge;
  - a diff of the country branch shows no change under `pipeline/core/`;
  - no secrets (grep for key patterns).

#### T-047: Record the baseline code fingerprint

- Status: pending (needs T-011). Type: document. Priority: required (RQ-001 a).
- Spec refs: G-005, D-006.
- **Objective:** compute `code_hash()` at `cee79b2` and record it with the commit. The handoff-index value `398167e2…` is labelled as `55fe353`.
- **Output:** a note in `PP\agent-workspace\` plus an `interaction-log.csv` row.
- **Owner:** Ainhoa.
- **Self-checks:** the same hash on Windows and Linux (the CI test exists).

#### T-048: Bring the roadmap and registry records in line

- Status: pending. Type: document. Priority: optional.
- Spec refs: RQ-003 a, RQ-004.
- **Objective:**
  - tick the roadmap Phase 1 matcher items, citing T-002 evidence;
  - record the registry-row-71 discrepancy in the interaction log, without hand-editing the registry.
- **Owner:** Ainhoa (Drive).

#### T-049: Independent verification of contract output

- Status: pending (needs T-014). Type: verify. Priority: critical-path.
- Spec refs: A-001-A-003, A-011, R-018-R-026.
- **Objective:** a reviewer other than the author runs the acceptance checks on a mapped sample and on full output.
- **Owner:** reproducer role or the PI.
- **Self-checks:** the acceptance-test table, each with its evidence file.

#### T-050: Plan-level scope audit

- Status: pending (runs at each wave close). Type: verify.
- Spec refs: R-002, R-003, R-035, N-001-N-008.
- **Objective:** confirm that no task added a source, unit, taxonomy or term, and that instrument versions are unchanged unless ruled.
- **Owner:** integrator.

## Phase 4: DAG and waves

Edges are input/output only. Gates are not edges.

```
T-011 → T-012, T-015, T-016, T-022, T-037, T-047
T-015 → T-016 (models.py) → T-017 (store.py)
T-015 → T-019 → T-020
T-013 (gate) ─┐
T-016, T-017 ─┼→ T-018 (gate) → T-014 (gate) → T-049, T-040 (gate)
T-019 ────────┘
T-022 → T-023 → T-024
T-025 (gate) → T-026 → T-027
T-019, T-020, T-004 → T-035 (gate) → T-041
T-031 (gate) → T-034.x (OCDS-API)
T-032 / T-033 (gates) → T-034.x (bulk / scrape)
T-012, T-044 (ext) → T-036 (gate)
T-028, T-029 (gates) → T-034.x
```

The graph is acyclic: each edge points from a lower wave to a higher one.

**Critical path:** T-011 → T-015 → T-019 → T-020 → T-035 → T-041. Contract output runs on a parallel critical path: T-013 → T-014 → T-049. That path waits on the PI gates Q-001, Q-018 and Q-019.

**Tasks with slack:** T-047, T-048, T-037, T-022-T-024.

| Wave | Task | Agent lane | Dependencies satisfied by | Write claim | Output handoff | Review gate |
|---|---|---|---|---|---|---|
| 0 | T-001-T-009 | — | done | — | evidence above | integrator marks complete at lock |
| 1 | T-011 | PI + both RAs | — | `procurement/italy` push | access | PI |
| 1 | T-031 | Ainhoa (or PI agent) | T-006 | none (presentation) | Q-009a ruling | PI |
| 2 | T-012 | Asenat | T-011 | Italy config row | note | integrator |
| 2 | T-015 | Ainhoa | T-011 | standardize/models/schema | activity_id | integrator |
| 2 | T-022 | Ainhoa | T-011 | Drive validation files | frame + amendment | PI |
| 2 | T-037 | both RAs | T-011 | board comments | review | PI |
| 2 | T-047, T-048 | Ainhoa | T-011 | Drive notes | records | integrator |
| 3 | T-016 → T-017 | Ainhoa (sequential) | T-015 | store/models/cli | decision + review closing | integrator |
| 3 | T-019 → T-020 | Ainhoa (sequential, after T-017 if `models.py` is shared) | T-015 | absence/manifest | absence rows, report | integrator |
| 3 | T-023 | coders | T-022 + PI | labels | labels | third coder / PI |
| 4 | T-024 | Ainhoa | T-023 | report + tools | threshold ruling | PI |
| 4 | T-035 | Ainhoa | T-019, T-020 + gates | Drive run folder | archive | PI |
| 4 | T-013 | Ainhoa | Q-001 ruling | contract/coding | pinned mirror | integrator |
| 5 | T-018 → T-014 | Ainhoa | T-013, T-016-T-019 + gates | aggregate/contract_rows | contract rows | T-049 |
| 5 | T-041 | reproducer | T-035 | reproduction folder | diff | PI |
| 5+ | T-034.x, T-032, T-033, T-036, T-038 | per country RA | mode checkpoint + gates | per-source paths | per-source runs | PI per mode |
| 6 | T-049, T-040, T-042 | reviewer / integrator | T-014 | verification files | final | PI |

**Collision check.** Within Wave 3 everything is in Ainhoa's lane. T-016, T-017, T-019 and T-020 share `models.py`, `store.py` and `cli.py`, so they run sequentially in one lane rather than in parallel. Wave 2 write claims are disjoint: T-012 is the Italy config row on `procurement/italy`, T-015 is core on main, T-022 is Drive files, and T-037 is the board.

**Integrator.** There is one integrator for `procurement/main` and for the `config/sources.yaml` merges (DEC-009, OPEN). That role is also the delta-log (`CHANGELOG.md`) writer.

**Capacity note.** Ainhoa is a single lane for most of the critical path. Asenat's ready work is small (T-011, T-012, T-037) until the Italy gates clear.

## Phase 5: Risks, gates and packaging

| Risk | Trigger | Likelihood/impact | Prevention | Detection | Containment/rollback | Owner/task |
|---|---|---|---|---|---|---|
| Ainhoa unavailable | Q-037 residual; LOG 10-11 "starting a new job" | medium / high (critical path) | Confirm before Stage 7 | No T-011 acceptance | Reassign core lane (PI) | PI |
| Contract version unresolved | Q-001 open | high / high | Gate T-013 | — | Staging-only output continues | PI |
| Uruguay yields ~0 contract rows | C-008, 0/132 linked | high / high | Q-010 gate | T-005 replay | Report-only Uruguay | PI / Master team |
| Italy access unlawful or blocked | Q-014, Q-023 | high / medium | Gate T-036 | T-012 note | Skip or request permission | PI |
| Italy retrieval impossible without Italian terms | Q-012, RS-054 empty | high / medium | EXTERNAL T-044 | — | Language status reported (T-020) | multilingual |
| Fingerprint confusion between Drive and repo | RQ-001 | medium / medium | T-047 | Manifest hash ≠ commit | Relabel | Ainhoa |
| Uruguay full history cost ~200 h | C-007 | high / medium | Q-007 gate; cache | Run time | Bounded window | PI |
| Shared-core collision when the Italy branch touches core | R-037 | low / high | DEC-006, T-046 diff check | CI + diff | Revert | integrator |
| Validation without positives | Q-015 | high / high | Gate T-025 | Frame counts | Report precision only | PI |

**Explicit gates:**
- **Destructive:** T-045 (move to archive).
- **External communication:** T-031 (to the PI), and Asenat's email (PI sends).
- **Long-running or costly:** T-035, T-034.x full runs (smoke run of 5 first; PI go above 24 h).
- **Credentials:** API keys (Q-014). Never in code.
- **Shared infrastructure:** merges to `procurement/main` (T-046).
- **Substantive choices:** every researcher gate above.

**Ready for task engineering at Stage 7, subject to the Stage 5 adjudication:**
- T-011 and T-031.
- Once T-011 lands: T-012, T-015, T-022, T-037, T-047, T-048.

**Blocked, with what unblocks them:**

| Tasks | Unblocked by |
|---|---|
| T-013 | Q-001, Q-002, Q-003 |
| T-014 | Q-001, Q-004, Q-018, Q-019, Q-010 |
| T-018 | Q-018, Q-032 |
| T-021 | Q-005 |
| T-025 | Q-015 |
| T-028 | Q-032 |
| T-029 | Q-038 |
| T-032, T-033 | PI's first-source choice; Q-023 |
| T-035 | Q-006, Q-007, Q-008, Q-010, Q-038 |
| T-036 | Q-012, Q-014, Q-023 |
| T-038 | Q-028 |
| T-039 | Q-024 |
| T-040 | Q-019 |
| T-042 | Q-024, Q-038 |
| T-045 | Q-025 |

## Structural completion gate (self-check)

- **Coverage:** every D, R, A and C ID appears in Phase 2. G-006 has no producer because it is blocked on Q-019. This is stated, not hidden.
- **DAG:** acyclic. Every edge points to a later wave.
- **Cards:** every card has its inputs, outputs, tools, skills, review and done condition, either on the card or through the defaults block. Checks are operational: counts, schema, hashes, diffs.
- **Inputs:** every task input traces to an RS ID, a predecessor output, or a USER-SUPPLIED or EXTERNAL source.
- **Reproduction:** every final D item has a reproduction or verification task (T-041, T-049). The documented pipeline the final traceability review reruns is `pipeline.cli` plus the source documentation and the run archive.
- **Collisions:** write claims within each wave are collision-free, given that Ainhoa's lane is sequential.
- **Integrator and delta-log writer:** one role, but **not yet named** (DEC-009). This is the only gate item the draft cannot close; it goes to Stage 5.
- **Unknowns:** all shown as `blocked` with a reason, or as SPIKE (T-022).
- **No implementation:** this session made reads only.
