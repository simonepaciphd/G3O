# PLAN: G3O procurement pipeline (whole pipeline, retrofit)

Status: READY-WITH-BLOCKS (readiness; lock state is "Baseline lock" below)
Spec: `procurement/planning/SPEC.md` v001-draft.4 (approved). Resources: `procurement/planning/RESOURCES.md` v001 (approved)
Baseline lock: 2026-10-27T08:02-07:00, Simone Paci (chat "LOCK"); SPEC v001-draft.4 + RESOURCES v001 + this PLAN
Source draft plan / review: `procurement/planning/Plan-Draft.md` v001-draft.1; `procurement/planning/Plan-Review.md` (both kept unchanged)
Mode: `PLAN_ONLY` (ruling 4). RAs execute from Stage 7 handoffs. Agents launch no execution lanes.
Adjudicated: 2026-10-27, researcher session `20261027-claude-v2-0307d4d58c63fd23` (claude-opus-5-5), per `planning-adjudication-protocol.md` v0.2.

## Fixed decisions and preserved strengths

**PI rulings fixed for execution.** These are all in `SPEC.md`:
- the scope, extraction and spec rulings S1;
- the resource rulings S2 (`RESOURCES.md`);
- the plan-review rulings S3.

The S3 plan rulings:

- **U-1 c:** the plan integrator and sole `CHANGELOG.md` writer is **an agent session acting for the PI**. Simone starts it, and it prepares each change for her approval.
  - It merges, records rulings and versions the governance files only after her approval.
  - It implements no task card. This keeps C-004 intact: Simone launches the session, and this plan launches no lane.
- **U-2 c:** handoffs are files in the repo, at `procurement/planning/handoffs/T-###.md`. RA return reports and spec-delta reports go to Simone by email.
- **U-3 a:** the RAs record each source's language(s). How a multi-language source is counted is open (Q-039).
- **U-4 c:** the R-025 English translation is produced by an LLM. This is ruled not to be adjudication.
- **U-5 a:** the 2026-08-29 checkpoint package is presented labelled as historical, together with the n=100 replay.
- **U-6 a:** tier-1 and tier-3 deterministic auto-accepts are allowed before validation.
- **U-7 a:** `procurement/main` gets branch protection, requiring a PR plus green CI.
- **U-8:**
  - Drive access for the RAs is granted.
  - Fan-out beyond Uruguay and Italy has no assigned RA. It is deferred until Italy is settled.
  - Moving the Drive-only tasks to Asenat was not ruled, so they stay with Ainhoa.
- **A1-A3:** accepted (procedural).

**Code and instruments:**
- Code baseline: `procurement/main` @ `cee79b2` (RQ-001 a).
- Query set v1.0 (D4) and codebook v0.4 stand.
- The contract file is read-only. `inputs/` and the master are read-only.
- No LLM adjudication; LLM translation is allowed (U-4 c).
- No secrets in code. No new unit, taxonomy or source.

**Preserved strengths (reviewer):**
1. PI-reserved items stay BLOCKED-SPEC gates with a Q-ID.
2. Completed claims T-001 to T-004 hold: 105 tests pass at `cee79b2`.
3. Ainhoa's core work runs as one sequential lane.

## Finding disposition ledger

Full ledger, with evidence and parent checks: `Plan-Review.md` § Disposition ledger. Summary of plan changes:

| Finding | Disposition | Plan change | User decision |
|---|---|---|---|
| PF-001 | ACCEPT + USER-DECISION | Integrator named (DEC-009); channel (DEC-010); T-054 ruling propagation; T-055 reconciliation; T-024/T-031 done conditions reworded | U-1 c, U-2 c |
| PF-002 | ACCEPT | T-051 cache-replay mode; comparison field set is a PI gate (A2) | — |
| PF-003 | ACCEPT | T-052 replay ported to repo; edge T-052 → T-045 | — |
| PF-004 | ACCEPT | Edge T-017 → T-019; synthetic linked fixture; Q-010 gate | — |
| PF-005 | ACCEPT-MODIFIED | Separate absence table (DEC-012) | — |
| PF-006 | USER-DECISION | T-056 per-source languages; Q-039 gate | U-3 a |
| PF-007 | USER-DECISION | T-057 LLM snippet translation (DEC-013) | U-4 c |
| PF-008 | ACCEPT | T-053 ARCE terms record; edge T-028 → T-041 | — |
| PF-009 | ACCEPT | T-023 needs fan-out strata; D-009 blocked; slack removed | — |
| PF-010 | ACCEPT | Q-030/Q-031 residual gates on T-014, T-040; D-002 at contract grain in T-014 | — |
| PF-011 | ACCEPT | DEC-003 revised to `ocds_ocid`; T-015 reduced, off critical path | — |
| PF-012 | USER-DECISION | T-031 presents labelled historical + replay | U-5 a |
| PF-013 | ACCEPT + USER-DECISION | T-002 text corrected; tiers 1/3 allowed | U-6 a |
| PF-014 | ACCEPT | T-009 `verified`-pending with check | — |
| PF-015 | USER-DECISION | T-058 branch protection | U-7 a |
| PF-016 | ACCEPT + USER-DECISION | Absolute Drive paths in defaults; Drive access in T-011 | U-8 granted |
| PF-017 | ACCEPT | Q-011, Q-017, Q-021, Q-022, Q-026 attached as gates | — |
| PF-018 | USER-DECISION | T-060 fan-out assignment, deferred until Italy settles | U-8 |
| PF-019 | ACCEPT-MODIFIED | T-036 gate: PI adopts query set v1.x with `it` terms (A3) | — |
| PF-020 | ACCEPT | False edges removed (repo is public); T-047, T-037 ready now | — |
| PF-021 | ACCEPT | `contract_version` field in T-013 claim; edge T-047 → T-035 | — |
| PF-022 | ACCEPT | Coverage corrected (R-033, R-034, R-026, R-019) | — |
| PF-023 | ACCEPT | Self-check fixes | — |
| PF-024 | ACCEPT-MODIFIED | Planning commit at Stage 6 (protocol rule 13); Asenat email is PI-held; T-059 applies VP §B | — |
| PF-025 | ACCEPT | T-006/T-008 `verified (preparation/draft)`; Wave-4 Ainhoa tasks sequenced | — |

## Decisions

The Plan-Draft decisions carry over unless revised here.

| Decision ID | Question | Chosen option | Reason | Spec IDs | Reversible? |
|---|---|---|---|---|---|
| DEC-001 | Delivered pieces | `complete` or `verified` cards with evidence | Ruling 2a; RQ-003 a | all | yes |
| DEC-002 | Home of contract rows and aggregation | New shared-core modules on `procurement/main` | R-037 | D-001, R-022 | yes |
| DEC-003 (rev.) | Activity identity | Collapse on the existing `ocds_ocid`. Non-OCDS records get an empty key plus `internal_activity_key_missing`, never a raise | PF-011; R-012; Q-031 b | R-005, R-012 | yes |
| DEC-004 | 150 automatable sources | Per-source template T-034.x, released per access-mode checkpoint | Reviewability | G-001 | yes |
| DEC-005 | Labelling | Separate coder tasks | R-040 | D-008, D-009 | yes |
| DEC-006 | Branch integration | Country → main only by PR through the integrator after CI; core first, then countries; enforced by protection (T-058) | RC; U-7 a | R-037 | yes |
| DEC-007 | Drive document edits | By the owning RA, logged in `PP\interaction-log.csv` | Card boundary | D-009 | yes |
| DEC-008 | First documented run | Uruguay (T-035) | D-006 a | D-006 | yes |
| DEC-009 | Integrator / delta-log writer | Agent session acting for the PI, started by Simone; prepares, Simone approves; implements no card | U-1 c | all | yes |
| DEC-010 | Handoff and report channel | Handoffs at `procurement/planning/handoffs/T-###.md`; RA return and delta reports by email to Simone, who forwards them to the integrator session | U-2 c | all | yes |
| DEC-011 | Absolute data paths | Every run passes `--master`, `--ledger`, `--out-dir`, `--cache-dir` as absolute Drive paths | PF-016; `cli.py:32-35` | R-038 | yes |
| DEC-012 | Absence-row storage | Separate `absence` table: own schema, key (`institution_uid`, `source_id`, window). Per-record `confirms_absence` stays staging evidence. T-014 emits contract absence rows only from the table | PF-005 | R-021, D-001 | yes |
| DEC-013 | Snippet translation | LLM translation step, versioned (model + prompt recorded per row); original kept in parentheses; never used for relevance | U-4 c; R-025; N-005 | R-025 | yes |
| DEC-014 | Fan-out owner | None yet; decided after Italy is settled (T-060) | U-8 | G-001 | yes |

## Requirement traceability

Status values: `covered` (producer complete), `planned`, `blocked` (gate named).

| Spec ID | Producer task/output | Verifier/review evidence | Status |
|---|---|---|---|
| G-001 | T-034.x, T-032, T-033, T-036, T-038, T-039 | T-042 | blocked (T-060, Q-024, Q-038) |
| G-002 | T-014 | T-049 | blocked (Q-001) |
| G-003 | T-019 | T-049 | planned |
| G-004 | T-001; T-021 | T-049 | covered / blocked (Q-005) |
| G-005 | T-051, T-041 | T-041 | planned |
| G-006 | — | — | blocked (Q-019): no producer until ruled |
| D-001 | T-014 | T-049 | blocked (Q-001, Q-004, Q-018, Q-019, Q-030/Q-031 residuals) |
| D-002 | T-001; T-014 (contract grain); T-021 | T-049 | covered / blocked |
| D-003 | T-002 | T-024 | covered |
| D-004 | T-002 (queue), T-017 (closing) | T-024 | planned |
| D-005 | T-016 | T-049 | planned |
| D-006 | T-003 (writer), T-035 (first archive) | T-041 | planned |
| D-007 | T-012, T-053, T-028 | T-041 | blocked (T-028: Q-032) |
| D-008 | T-025, T-026, T-027 | PI gate on T-027 | blocked (Q-015) |
| D-009 | T-022, T-023, T-024, T-059 | PI gate on T-024 | blocked (strata need fan-out, T-060) |
| D-010 | T-006 (prepared), T-031, T-032, T-033 | PI gate | planned |
| D-011 | T-003, T-020, T-056 | T-049 | planned |
| D-012 | T-040 | T-049 | blocked (Q-019) |
| D-013 | T-051, T-041 | PI gate | planned |
| D-014 | T-008 (draft), T-037 | PI gate (Q-016) | planned |
| R-001, R-019 | T-013, T-014 | T-049 (A-001) | blocked (Q-001) |
| R-002, R-003, N-001-N-003 | Card boundaries | T-050 | covered |
| R-004 | T-001; T-021 | T-049 | covered / blocked |
| R-005, R-006 | T-001 (`coding.py`); T-013 (`proposed` vs §4.3) | T-049 (A-003) | blocked (Q-002) for tenders |
| R-007 | T-013 | T-049 (A-011) | blocked (Q-001, Q-003) |
| R-008-R-010 | T-001 | T-027 | covered |
| R-011 | T-003; T-035 | T-041 | blocked (Q-007) |
| R-012 | T-001, T-015, T-014 (Q-004 gate) | T-049 | planned |
| R-013-R-015, R-017 | T-002 | T-024 | covered |
| R-016 | T-002 (tiers 1/3 allowed, U-6 a); T-024 → PI threshold for tier 4 | PI | planned |
| R-018 | T-014 | T-049 (A-002) | blocked |
| R-020, R-024 | T-001; T-014 | T-049 | covered / blocked |
| R-025 | T-057 | T-049 | planned |
| R-026 | T-014 | T-049 | blocked |
| R-021 | T-019, T-020, T-056 | T-049 | planned |
| R-022 | T-018 | T-049 | blocked (Q-018, Q-032) |
| R-023 | T-001; T-020 | T-049 (A-011) | covered |
| R-027 | T-016 | T-049 | planned (Q-022 gate) |
| R-028, R-029 | T-034.x steps 1-2; T-012, T-053, T-028 | T-034.x review | planned |
| R-030 | T-029 | RA/PI approver | blocked (Q-038) |
| R-031 | T-001; T-021 | T-049 | covered |
| R-032 | T-001 | T-041 | covered |
| R-033 | T-020 (fetched + failed = read) | T-041 | planned |
| R-034 | T-001 (partial); T-020 (codebook/query version on records) | T-041 | planned |
| R-035 | Card defaults; T-036 v1.x gate | T-050 | covered |
| R-036 | T-039 | T-042 | blocked (Q-024) |
| R-037 | DEC-006, T-058, T-046 | T-046 | planned |
| R-038 | T-007; T-045; T-052 | T-046 | covered / blocked (Q-025) |
| R-039 | Defaults; CI | T-046 | covered |
| R-040 | T-023, T-026 | T-024, T-027 | blocked (via T-022/T-025) |
| R-041 | T-020 | T-049 | planned |
| A-001-A-003 | T-049 | PI | blocked (via T-014) |
| A-004 | T-020, T-035 | T-041 | planned |
| A-005 | T-034.x, T-053 | PI | planned |
| A-006 | T-031, T-032, T-033 | PI | planned |
| A-007 | T-027 | PI | blocked (Q-015, Q-020) |
| A-008 | T-024 | PI | blocked (via T-023) |
| A-009, A-010 | T-051, T-041 | PI | planned |
| A-011 | T-020 | T-049 | planned |
| A-012 | T-042 | PI | blocked (Q-024, Q-038) |
| C-001, C-002 | Defaults | T-046 | covered |
| C-003, C-004, C-005 | This plan; DEC-009 | — | covered |
| C-006 | T-011 | PI | planned |
| C-007 | T-035 | PI gate Q-007 | planned |
| C-008 | Q-010 gate on T-019 (Uruguay), T-035, T-014 | — | blocked |
| N-004 | T-043, T-044 EXTERNAL | — | covered |
| N-005 | Defaults; DEC-013 | T-050 | covered |
| N-006 | Defaults; T-040 | T-049 | covered |
| N-007 | T-014 (Q-017 gate) | T-049 | covered |
| N-008 | T-027 | PI | covered |

## Card defaults (every card inherits)

- **Spec version:** `SPEC.md`, the version locked at Stage 6 (v001-draft.4 until then). Each handoff carries the locked version.
- **Persona/role:**
  - RA tasks: the named RA, through the RA harness (`paci-research-lab/ra-ai-os`), with its agent under `procurement/CLAUDE.md` (RC).
  - PI tasks: Simone.
  - Integrator tasks: the integrator session (DEC-009).
- **Tools:** git and GitHub (`simonepaciphd/G3O`, public), Python 3.11/3.12 with `procurement/requirements.txt`, and pytest. Drive is used for data, outputs and logs (access granted, U-8).
- **Skills/protocols:** RC, PC. Read-only references: ES (`PP\docs\procurement-extension-spec.md`) and CB (`PP\docs\genai-procurement-codebook.md`).
- **Working directory and paths:**
  - Work in the RA's clone of `simonepaciphd/G3O`, on the card's branch.
  - Every run passes absolute Drive paths for `--master`, `--ledger`, `--out-dir` and `--cache-dir` (DEC-011).
- **Collision control:**
  - Read scope is the whole repo.
  - The write claim is only the card's paths.
  - `procurement/pipeline/core/` has one owner, Ainhoa.
  - All merges to `procurement/main` go through the integrator, by PR (DEC-006).
- **Fixed decisions:** as listed above. Q-021 (classification beyond the pilot) is a standing gate: no card changes R-009's scope.
- **Spec-change reporting (DEC-010):**
  - Report by email to Simone; she forwards to the integrator.
  - Report when: source data contradicts a spec rule; a rule is ambiguous on a real record; a new constraint appears (terms, blocking, cost, credentials); or output would deviate from an acceptance test.
  - Stop boundary: no output that depends on the contested rule is written or staged.
  - Safe continuation: tests, fixtures, independent sources.
  - Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md`.
- **Return report:** by email to Simone (DEC-010). It lists changed files, each check with its evidence, failures, blockers, unresolved decisions, and the proposed status (`verified` or `blocked`). Only the integrator marks a task `complete`, after Simone approves.
- **Failure and rollback:** revert the branch commit. Archived Drive outputs are never overwritten; a rerun writes a new run folder.
- **Chunking trigger:** split the task when it spans more than one session, mixes core and country writes, or puts a long-running action after a build.

## Task graph

### Completed or verified work (ruling 2a)

| Task | Status | Delivered | Evidence | Acceptance IDs |
|---|---|---|---|---|
| T-001 | complete | Staging core: term search and deterministic classifier (LLM stub raises); one record per award/lot; item rules R1-R5, R8; coding rules; extension builder; 4 schema-validated tables | RS-029-RS-033; 105 tests pass at `cee79b2` (reviewer re-run 2026-10-27); CI green | — |
| T-002 | complete | Matcher tiers 0/1/3/4/5, ledger, duplicate flag, subnational corroboration. **Tier-1 and tier-3 deterministic auto-accept** (`matcher.py:316,335`), allowed by U-6 a; tier 4 goes to review | RS-032; 21 matcher tests; replay queue 132 rows / 48 buyers | — |
| T-003 | complete | Unverified guard, window, cache write, retries, failure records, manifest writer | RS-028, RS-034; manifest test | — |
| T-004 | complete | Uruguay ARCE adapter + 101 real fixtures | RS-034, RS-038; `test_arce_adapter.py` | — |
| T-005 | complete | n=100 diagnostic, reconciliation, offline replay | RS-045-RS-047 | — |
| T-006 | verified (preparation) | OCDS-API 5+5 checkpoint package, built before R1-R8 and the migration; no code version | RS-043, RS-044 | presented in T-031 |
| T-007 | complete | Migration to git; OS-independent fingerprint; CI; repo manual | `55fe353`, `8b4e211`, `cee79b2` | — |
| T-008 | verified (draft) | Draft interface v0.1, Uruguay run protocol, validation protocol | RS-011-RS-013 | signed in T-037 / Q-016 |
| T-009 | verified-pending | Brazil PNCP adapter + 5-record sample. **Check owed:** open RS-035 and RS-042, add one fixture test. Brazil assignment Q-028 | RS-035 (LISTED), RS-042; no PNCP test (`grep pncp tests/`) | — |

### Summary of new tasks

| Task | Status | Requires (edges) | Enables | Write claim | Researcher gates | Acceptance IDs |
|---|---|---|---|---|---|---|
| T-011 | ready | — | T-012, T-015-T-017, T-019, T-020, T-051-T-053, T-056 (push) | `procurement/italy` push | Ainhoa availability + login (Q-037 residual) | — |
| T-012 | pending | T-011 | T-036 | Italy config row | — | — |
| T-013 | blocked | — | T-014 | `contract.py`, `coding.py`, `docs/reference/`, `cli.py` (`contract_version` field), tests | Q-001, Q-002, Q-003 | A-001 (part) |
| T-014 | blocked | T-013, T-015, T-016, T-017, T-018, T-019, T-057 | T-049, T-040 | `contract_rows.py`, `cli.py` export, tests | Q-001, Q-004, Q-017, Q-019, Q-026, Q-030/Q-031 residuals, Q-010 (Uruguay), first-sample PI checkpoint | A-001-A-003 |
| T-015 | pending | T-011 | T-014 | `standardize.py` (flag), tests | — | — |
| T-016 | pending | T-011 | T-017, T-014 | relevance schema, `store.py`, `models.py`, `cli.py` subcommand, tests | CB §8 field check; Q-022 | — |
| T-017 | pending | T-016 | T-019, T-014 | `store.py`, `matcher.py`, `cli.py` subcommand, tests | Q-011 (completion gate) | A-002 (part) |
| T-018 | blocked | T-016, T-017 | T-014 | `aggregate.py`, tests | Q-018, Q-032 residual | — |
| T-019 | pending | T-017, T-052 | T-020, T-014, T-035 | absence schema + `absence.py`, `store.py` (table), tests, linked fixture | Q-030 residual (extension rows); Q-010 (Uruguay output) | — |
| T-020 | pending | T-019, T-056 | T-035 | `cli.py` manifest, `base.py` RunReport, record schema (version fields), tests | Q-039 (multi-language) | A-004, A-011 |
| T-021 | blocked | — | — | extension schema, `standardize.py`, tests | Q-005 | — |
| T-022 | pending | — | T-023, T-059 | Drive validation files | PI approves design | — |
| T-023 | blocked | T-022, T-034.x (≥1 non-Latin + ≥2 more countries) | T-024 | labels | coder assignment | — |
| T-024 | pending | T-023 | — | report + `procurement/tools/matcher_validation.py` | Q-009b, Q-020 | A-008 |
| T-025 | blocked | — | T-026 | classification frame | Q-015 | — |
| T-026 | pending | T-025 | T-027 | labels | coder assignment | — |
| T-027 | pending | T-026 | — | report + `procurement/tools/classification_validation.py` | Q-020 | A-007 |
| T-028 | blocked | — | T-034.x, T-041 | documentation template | Q-032 residual | — |
| T-029 | blocked | T-028 | T-034.x, T-035 | procedure | Q-038 residuals | — |
| T-031 | ready | — | T-034.x (OCDS-API) | presentation only | Q-009a | A-006 |
| T-032 | blocked | — | T-034.x (bulk) | bulk adapter (country branch) | PI picks first bulk source; Q-023 | A-005, A-006 |
| T-033 | blocked | — | T-034.x (scrape) | scrape adapter | PI picks first scrape source; Q-023 | A-005, A-006 |
| T-034.x | blocked | mode checkpoint; T-028, T-029 | T-023, T-042 | per-source paths | owner (T-060); Q-023; window | A-005 |
| T-035 | blocked | T-019, T-020, T-047, T-053, T-029 | T-041 | Drive run folder | Q-006, Q-007, Q-008, Q-010, Q-038; PI go above 24 h | A-004 |
| T-036 | blocked | T-012, T-044 | — | Italy adapter, row, tests | Q-012, Q-014, Q-023; adopt query set v1.x (A3) | A-005 |
| T-037 | ready | — | — | board/email comments; `PP\docs\adapter-output-interface.md` after ruling | Q-016 | — |
| T-038 | blocked | — | — | — | Q-028; Q-031 residual | — |
| T-039 | blocked | — | T-042 | — | Q-024 | — |
| T-040 | blocked | T-014 | T-049 | consolidation module | Q-019, Q-030/Q-031 residuals | — |
| T-041 | pending | T-035, T-051, T-028 | — | reproduction folder | reproducer assignment; comparison field set (A2) | A-009, A-010 |
| T-042 | blocked | T-034.x, T-039 | — | coverage table | Q-024, Q-038 (iii); status vocabulary | A-012 |
| T-043, T-044 | blocked (EXTERNAL) | — | T-036 (T-044) | none here | multilingual subproject | — |
| T-045 | blocked | T-052 | — | Drive archive move | Q-025 | — |
| T-046 | pending (per merge) | T-058 | — | merges | — | — |
| T-047 | ready | — | T-035 | Drive note | — | — |
| T-048 | pending | — | — | Drive roadmap, log | — | — |
| T-049 | pending | T-014 | — | verification files | — | A-001-A-003, A-011 |
| T-050 | pending (per wave) | — | — | audit note | — | — |
| T-051 | pending | T-011 | T-041 | `base.py`, `cli.py` (`--from-cache`), ARCE adapter read path, tests | comparison field set (A2) | A-009, A-010 |
| T-052 | pending | T-011 | T-019, T-045 | `procurement/tools/replay.py` or `tests/test_replay_ury.py` | — | — |
| T-053 | pending | T-011 | T-035 | URY config row note | — | A-005 |
| T-054 | pending (on each ruling) | — | the unblocked cards | `SPEC.md`, `PLAN.md`, `CHANGELOG.md` (integrator only) | Simone approves each | — |
| T-055 | pending (end) | all executed tasks | — | `Spec-Reconciliation.md` | Simone | — |
| T-056 | pending | T-011 | T-020 | `config/sources.yaml` `languages` field (+ `sources.example.yaml`) | Q-039 | — |
| T-057 | pending | T-011 | T-014 | `pipeline/core/translate.py`, tests | prompt + model approval (PI) | — |
| T-058 | ready | — | T-046 | repo branch-protection setting | — | — |
| T-059 | pending | T-022 | T-023 | `PP\docs\classification-validation-protocol.md` §B | PI approves amendment | — |
| T-060 | blocked (deferred) | Italy settled (T-036) | T-034.x owners | — | PI assigns (U-8) | — |

## Task cards

Only what differs from the defaults is stated. The cards of Plan-Draft v001-draft.1 are superseded by these.

### T-011 — Give both RAs working access and land Asenat's commit
- **Status:** ready. Type: operate. Priority: critical-path.
- **Spec refs:** C-006, R-038, D-007. **Decision refs:** RQ-002 a, U-8.
- **Objective:**
  - Both RAs can push their branches.
  - Both have Drive access: read on `inputs\G3O_Institution_Master\data_final\`, write on the procurement subproject.
  - 781cf0c is on `origin/procurement/italy`.
  - Asenat's non-code Italy material is on Drive.
- **Inputs:**
  - invite 339864628 (pending);
  - Ainhoa's GitHub login (unknown);
  - 781cf0c (on Asenat's machine);
  - the PI's email to Asenat (draft held by Simone).
- **Owner:** PI (invites, Drive sharing), Asenat (push, upload), Ainhoa (accept).
- **Researcher gates:** Ainhoa's availability and login (Q-037 residual).
- **Write claim:** the `procurement/italy` push (Asenat).
- **Self-checks:**
  - `git fetch origin procurement/italy && git merge-base --is-ancestor 781cf0c origin/procurement/italy` succeeds;
  - CI green on that push;
  - `gh api repos/simonepaciphd/G3O/collaborators` lists both;
  - both RAs can open the master folder.
- **Done:** all four checks pass, recorded in `PP\interaction-log.csv`.

### T-012 — Record the Italy ANAC findings in the Italy config row
- **Status:** pending. Type: document. Priority: required.
- **Spec refs:** D-007, R-029, Q-014.
- **Requires:** T-011.
- **Objective:** the terms, robots and blocking findings are in `verification_note` of `ita_anac_bdncp_open_data_ocds`, with evidence. `verification_status` is unchanged (R-030, T-029).
- **Owner:** Asenat (`procurement/italy`).
- **Write claim:** that row only.
- **Self-checks:**
  - YAML loads;
  - `python -m pipeline.cli sources` lists the row;
  - CI green.
- **Review:** integrator compares the note with the LOG row of 2026-10-26.
- **Excluded:** live API or portal requests (Q-014).

### T-013 — Re-pin the contract mirror to the version of record
- **Status:** blocked, BLOCKED-SPEC (Q-001, Q-002, Q-003). Type: migrate. Priority: critical-path.
- **Spec refs:** R-001, R-006, R-007, R-019, C-001.
- **Objective:**
  - `contract.py` matches the PI-ruled version, and a new reference snapshot is added (the v2.0 snapshot is kept).
  - `cannot_type` codes `activity_type: unknown` when that version admits it (Q-032 b).
  - Tenders follow the Q-002 ruling.
  - The manifest gains a `contract_version` field.
- **Owner:** Ainhoa (main).
- **Write claim:**
  - `pipeline/core/contract.py`;
  - `pipeline/core/coding.py`;
  - `docs/reference/output_contract_v<X>.SNAPSHOT.md` + README;
  - `pipeline/cli.py` (the `contract_version` field only);
  - `tests/test_core.py`.
- **Self-checks:**
  - a test asserts every vocab member equals the snapshot's enum tables;
  - snapshot sha256 recorded in its README;
  - manifest test asserts `contract_version`;
  - CI green.
- **Acceptance:** A-001 (part).
- **Done:** merged to main by PR.

### T-014 — Map staged records to contract rows
- **Status:** blocked, BLOCKED-SPEC. Type: build. Priority: critical-path.
- **Gates:**
  - Q-001;
  - Q-004 (`vendor: multiple`);
  - Q-017 (`background_only` is never emitted unless ruled);
  - Q-019 (landing form);
  - Q-026 (link validity at the next master build);
  - Q-030 residual (extension rows for absence);
  - Q-031 residual (D-002 join, non-OCDS key);
  - Q-010 (Uruguay yield);
  - PI checkpoint on the first mapped sample.
- **Spec refs:** D-001, D-002, G-002, R-001, R-005-R-007, R-012, R-018-R-020, R-024-R-026, N-007.
- **Requires:** T-013, T-015, T-016, T-017, T-018, T-019, T-057.
- **Objective:**
  - Produce CT §3.2 columns at the triple grain.
  - Use one activity per `ocds_ocid` with the higher-evidence stage.
  - Use accepted decisions (T-016), resolved links (T-017) and aggregation (T-018).
  - Absence rows come only from the absence table (DEC-012).
  - Snippets are translated by T-057.
  - Drop `internal_*` flags (R-026).
  - No row without a resolved institution, no `null`.
  - Also produce D-002 at contract grain.
- **Owner:** Ainhoa (main).
- **Write claim:** `pipeline/core/contract_rows.py`, `pipeline/cli.py` (`export --contract`), tests.
- **Self-checks:**
  - validation against the T-013 snapshot gives 0 violations and 0 `null`;
  - every uid resolves in the ledger;
  - no `production`;
  - tender-only rows are `proposed` (per Q-002);
  - the institution value is constant per institution;
  - no `internal_*` flag in the output;
  - every D-001 row has its D-002 join.
- **Acceptance:** A-001, A-002, A-003.

### T-015 — Make activity identity safe for every source
- **Status:** pending. Type: build. Priority: required (off the critical path).
- **Spec refs:** R-012. **Decision refs:** DEC-003 (rev.).
- **Requires:** T-011.
- **Objective:**
  - Tests assert that records of one OCID share `ocds_ocid`.
  - Non-OCDS records get an empty key plus `internal_activity_key_missing`.
  - Nothing raises.
- **Owner:** Ainhoa (main).
- **Write claim:** `pipeline/core/standardize.py` (flag only), `tests/test_core.py`.
- **Self-checks:**
  - the multi-lot fixture (4 synthetic JSON fixtures in `tests/fixtures/_ocds_sample/`) gives n records sharing one `ocds_ocid`;
  - the 101 Uruguay fixtures all carry `ocds_ocid`;
  - a PNCP-shaped record stages with the flag.

### T-016 — Build the relevance review decision record
- **Status:** pending. Type: build.
- **Spec refs:** D-005, R-027.
- **Requires:** T-011.
- **Objective:** a persisted, schema-validated table of human relevance decisions (CB §8 fields), keyed to `record_id`, loaded from a reviewer CSV.
- **Owner:** Ainhoa (main).
- **Gates:**
  - PI confirms the field list against CB §8;
  - Q-022 (the "uncertainty band" for routing; until ruled, CB §8 triggers only).
- **Write claim:** `config/schema/relevance_review.schema.json`, `store.py`, `models.py`, `cli.py` (subcommand), tests.
- **Self-checks:**
  - missing reviewer or timestamp is rejected;
  - reviewer CSV → table → export round trip is lossless;
  - a decided record leaves the pending list.

### T-017 — Close institution review rows
- **Status:** pending. Type: build.
- **Spec refs:** D-004, R-017.
- **Requires:** T-016 (`store.py`).
- **Objective:**
  - Confirming a candidate writes a resolved link with reviewer and time.
  - Rejecting closes the row with no link.
  - A uid absent from the ledger is refused.
- **Owner:** Ainhoa (main).
- **Completion gate:** Q-011 ("Intendencia de X" normalization stays a PI question; no normalization is added here).
- **Write claim:** `store.py`, `matcher.py`, `cli.py` (subcommand), tests.
- **Self-checks:** confirm → link with `match_method` reviewed; reject → no link; a non-ledger uid is refused (A-002).

### T-018 — Aggregate `has_genai_activity` per institution
- **Status:** blocked (Q-018, Q-032 residual). Type: build. Priority: critical-path.
- **Spec refs:** R-022, D-001.
- **Requires:** T-016, T-017.
- **Owner:** Ainhoa (main).
- **Write claim:** `pipeline/core/aggregate.py`, tests.
- **Self-checks:**
  - one value per institution;
  - one rejected record never yields `no`;
  - `not_assessable` handled per the ruling.

### T-019 — Emit negative-evidence rows per institution × repository × window
- **Status:** pending. Type: build. Priority: critical-path.
- **Spec refs:** R-021, SC-03, G-003, Q-029 b, Q-030 b. **Decision refs:** DEC-012.
- **Requires:** T-017 (resolved links), T-052 (repo replay).
- **Objective:**
  - A separate `absence` table, keyed (`institution_uid`, `source_id`, window start/end).
  - One row per institution with searched, text-bearing records and no GenAI evidence, whatever the source's language.
  - Per-record `confirms_absence` is unchanged.
  - No extension rows (Q-030 residual).
- **Owner:** Ainhoa (main).
- **Gates:**
  - Q-030 residual (extension only);
  - Q-010 before any Uruguay absence output is reported.
- **Write claim:** `config/schema/absence.schema.json`, `pipeline/core/absence.py`, `store.py` (table registration), tests, `tests/fixtures/_absence_linked/` (synthetic, resolved links).
- **Self-checks:**
  - on the synthetic linked fixture, rows equal the distinct (institution, source, window) cells with no positive record;
  - `not_assessable` never yields a row;
  - on the repo replay (T-052), 0 rows, because 0 links: expected and stated.

### T-020 — Report language coverage, accounting and QC per run
- **Status:** pending. Type: build.
- **Spec refs:** D-011, R-021, R-033, R-034, R-041, A-004, A-011.
- **Requires:** T-019, T-056.
- **Objective:** the manifest and run report state:
  - each source's language-coverage status against query set v1.0, from T-056;
  - the counts yes / unclear / no / not-assessable / cannot-type / review / linked / absence rows / failures;
  - the reconciliation fetched + failed = items read;
  - the codebook and query-set version on each record;
  - the UP §6 QC booleans (reported, not enforced, until Q-016).
- **Owner:** Ainhoa (main).
- **Gate:** Q-039 (multi-language counting). Until ruled, list the languages per source and mark the status "mixed".
- **Write claim:** `cli.py` (`write_manifest`), `base.py` (RunReport), `config/schema/procurement_record.schema.json` (version fields), tests.
- **Self-checks:**
  - `language_coverage` is present per source;
  - the counts reconcile;
  - an Italian-only source shows "not covered".

### T-021 — Add the item-level money fields
- **Status:** blocked (Q-005). Unchanged from the draft.

### T-022 — Design the stratified matcher validation sample
- **Status:** pending. Type: spike (one design). Priority: required.
- **Spec refs:** D-009, R-016, Q-036 a.
- **Objective:**
  - A sample frame stratified as ES §5 requires.
  - A per-stratum shortfall table (today only Uruguay, Latin script, 48 buyers).
  - A VP §B amendment proposal.
- **Owner:** Ainhoa (Drive).
- **Gate:** PI approves the design and the amendment.
- **Write claim:** `PP\outputs\validation\matcher_sample_frame_<date>.csv`, `PP\agent-workspace\<date>-VP-B-amendment-PROPOSAL.md`.
- **Self-checks:** strata table; seed recorded; no duplicate buyers.

### T-023 — Label the matcher sample blind (two coders)
- **Status:** blocked. Type: verify.
- **Requires:** T-022, T-059, and fan-out data covering ≥1 non-Latin-script source and ≥2 more countries (T-034.x).
- **Owner:** coders, assigned by the PI.
- **Self-checks:** two labels per buyer; the score is hidden from coders; a disagreement log.

### T-024 — Report matcher validation
- **Status:** pending. Type: verify.
- **Requires:** T-023.
- **Objective:** precision and recall per tier, including tiers 1 and 3; a tier-4 precision-vs-score curve per stratum.
- **Owner:** Ainhoa.
- **Write claim:** `PP\outputs\validation\matcher_validation_<date>.md`, `procurement/tools/matcher_validation.py` (main).
- **Gates:** Q-009b and Q-020. The PI sets the tier-4 threshold or none.
- **Self-checks:** the script reruns to identical numbers; CIs stated.
- **Done:** report filed; ruling sent to the integrator (T-054).

### T-025, T-026, T-027 — Classification validation
- As in the draft, with these changes:
  - T-026 has a coder-assignment gate.
  - T-027's script is `procurement/tools/classification_validation.py`.
  - T-027 is done when the report is filed and the ruling is sent to the integrator.
- T-025 is blocked on Q-015.

### T-028 — Create the per-source documentation surface
- **Status:** blocked (Q-032 residual: `docs/sources/` vs `verification_note`; `notes_RA_Lee` is stale, RQ-006).
- **Enables:** T-034.x, T-041.

### T-029 — Write the source verification procedure
- **Status:** blocked (Q-038 residuals).
- **Requires:** T-028.
- **Objective:** a procedure implementing the PI criterion: an end-to-end run on the source with output checked to conform; approver RA or PI.

### T-031 — Present the OCDS-API checkpoint package to the PI
- **Status:** ready. Type: verify. Priority: critical-path (gates OCDS-API fan-out).
- **Spec refs:** D-010, A-006, Q-009a. **Decision refs:** U-5 a.
- **Objective:**
  - Present the 2026-08-29 package, labelled as **historical: pre-R1-R8 code, no recorded version**.
  - Present it alongside the n=100 replay (RS-047), which used code `398167e2…` = `55fe353`.
  - State that the Uruguay sample was replaced (board #82).
- **Owner:** Ainhoa. If she is unavailable, the integrator session prepares it.
- **Write claim:** none (an email or board comment to Simone).
- **Gate:** Q-009a.
- **Self-checks:** every number in the presentation cites its file (RS-043, RS-044, RS-047).
- **Done:** ruling sent to the integrator (T-054).

### T-032, T-033 — First bulk and first scrape source
- **Status:** blocked. The PI picks the first source per mode (PC: sources are the PI's); Q-023 applies.
- Otherwise as in the draft. Owners: deferred with T-060, unless the PI assigns earlier.

### T-034.x — Per-source fan-out (template)
- **Status:** blocked until the source's access-mode checkpoint is signed (T-031, T-032, T-033).
- **Requires:** T-028, T-029.
- **Steps:**
  1. Record terms and robots.
  2. Smoke run of 5, archived.
  3. Adapter, reusing the OCDS core for the 65 `is_ocds` sources.
  4. Bounded probe.
  5. Request verification (T-029).
  6. Full run.
- **Owners:**
  - Uruguay: Ainhoa;
  - Italy: Asenat (T-036);
  - Brazil: Q-028;
  - all others: **deferred until Italy is settled (T-060, U-8)**.

### T-035 — Uruguay full run (first documented archive)
- **Status:** blocked (Q-006, Q-007, Q-008, Q-010, Q-038). Type: operate. Priority: critical-path.
- **Spec refs:** D-006, D-011, R-011, C-007.
- **Requires:** T-019, T-020, T-047, T-053, T-029.
- **Outputs:** `PP\outputs\runs\<run_id>\` (manifest, staging, report); cache under `PP\data_cache\` (absolute paths, DEC-011).
- **Owner:** Ainhoa.
- **Gates:** Q-006, Q-007, Q-008, Q-010; smoke run of 5 first; PI go for any run longer than 24 h.
- **Self-checks:**
  - all A-004 QC booleans true;
  - fetched + failed = items read;
  - manifest `code_sha256` equals the T-047 value recorded for the commit the run used;
  - `not_assessable` reported separately.

### T-036 — Italy ANAC adapter and run
- **Status:** blocked (Q-012 via T-044; Q-014; Q-023).
- **Added gate (A3):** the PI adopts query set v1.x with `it` terms from the multilingual subproject, as a versioned query set (R-010, R-035).
- **Owner:** Asenat (`procurement/italy`). Otherwise as in the draft.

### T-037 — Review the adapter interface draft
- **Status:** ready (the repo is public). Type: verify.
- **Objective:** both RAs read interface v0.1 against the code and return comments by email (DEC-010). The PI decides v1.0 (Q-016).
- **Self-checks:** every §4 field exists in `procurement_record.schema.json`, or is listed as a discrepancy.

### T-038 to T-040, T-042 to T-044
- As in the draft, with the gate additions in the task graph.

### T-041 — Reproducibility rerun from a clean checkout
- **Status:** pending. Type: verify.
- **Requires:** T-035, T-051, T-028.
- **Objective:** a person other than the run's author, in the reproducer role, reruns a small sample from a clean clone in `--from-cache` mode (T-051), using only the source documentation and the archive.
- **Gates:** the PI assigns the reproducer; the PI signs the comparison field set (A2).
- **Self-checks:** a zero-diff report on the signed field set, or listed discrepancies.

### T-045 — Archive the Drive code copy
- **Status:** blocked (Q-025).
- **Requires:** T-052.
- **Self-checks:**
  - the hash comparison shows Drive = `55fe353` before the move;
  - `grep -r "parents\[3\]\|PP.pipeline" PP\outputs` finds no live script that imports the Drive `pipeline`.

### T-046 — Integrate branches into main
- **Status:** pending (per merge).
- **Requires:** T-058.
- **Owner:** integrator session; Simone approves each merge.
- **Self-checks:**
  - CI green;
  - no change under `pipeline/core/` from a country branch;
  - no secrets.

### T-047 — Record the baseline code fingerprint
- **Status:** ready (public repo). Type: document.
- **Objective:**
  - Compute `code_hash()` at `cee79b2` and record it with the commit.
  - Label `398167e2…` as `55fe353`.
  - Keep a hash ↔ commit table for later runs.
- **Owner:** Ainhoa (Drive note `PP\agent-workspace\<date>-code-fingerprints.md`; log row).
- **Self-checks:** same hash on Windows and Linux.

### T-048 — Bring the roadmap and registry records in line
- **Status:** pending. Unchanged from the draft. Owner Ainhoa; the move to Asenat was not ruled.

### T-049, T-050 — As in the draft.

### T-051 — Add a cache-replay mode (new; PF-002)
- **Status:** pending. Type: build. Priority: required.
- **Spec refs:** G-005, D-013, A-009, A-010.
- **Requires:** T-011.
- **Objective:**
  - `python -m pipeline.cli run --from-cache <dir>` reads archived raw payloads instead of fetching.
  - Output is identical on a defined comparison field set, which excludes run-time fields such as `fetched_at` and manifest timestamps.
- **Owner:** Ainhoa (main).
- **Gate:** the PI signs the excluded-field list (A2).
- **Write claim:** `pipeline/core/base.py`, `pipeline/cli.py` (flag), the ARCE adapter read path, tests.
- **Self-checks:** two replays of the 101 Uruguay fixtures give identical values on the field set; no network call (test with networking disabled).

### T-052 — Port the n=100 replay into the repo (new; PF-003)
- **Status:** pending. Type: migrate.
- **Requires:** T-011.
- **Objective:** a repo test or tool reproduces the RS-047 numbers from the 101 fixtures with the branch's own code: 132 rows, 71 `confirms_absence`, 61 `not_assessable`.
- **Owner:** Ainhoa (main).
- **Write claim:** `procurement/tests/test_replay_ury.py` (or `procurement/tools/replay.py`).
- **Self-checks:** the test imports `procurement/pipeline` (not Drive); its numbers match RS-047 or the differences are explained.

### T-053 — Record the Uruguay ARCE terms, robots and rate limits (new; PF-008)
- **Status:** pending. Type: document.
- **Spec refs:** D-007, R-029, A-005.
- **Requires:** T-011.
- **Objective:** findings in the `ury_…arce…` row's `verification_note` (browser User-Agent requirement, terms, robots, rate limits), with evidence.
- **Owner:** Ainhoa (main).
- **Write claim:** that row.
- **Excluded:** circumventing any block.
- **Self-checks:** YAML loads; CI green.

### T-054 — Propagate PI rulings (new; PF-001)
- **Status:** pending (fires on each ruling). Type: integrate.
- **Objective:** for each PI ruling:
  - record it in `SPEC.md` (pre-lock: change history; post-lock: a spec delta through `planning-spec-reconciliation-protocol.md`);
  - write `CHANGELOG.md`;
  - update card states in `PLAN.md`;
  - emit the released handoffs to `procurement/planning/handoffs/`.
- **Owner:** integrator session (DEC-009); Simone approves each change.
- **Write claim:** `SPEC.md`, `PLAN.md`, `CHANGELOG.md`, `handoffs/` (sole writer).
- **Self-checks:** every newly unblocked card lists the ruling that released it; the commit names the delta ID.

### T-055 — Reconcile the spec after execution (new; Stage 8)
- **Status:** pending (end of execution or abort). Type: verify.
- **Objective:** produce `Spec-Reconciliation.md` per `planning-spec-reconciliation-protocol.md`.
- **Owner:** integrator session; Simone approves.

### T-056 — Record each source's language(s) (new; PF-006, U-3 a)
- **Status:** pending. Type: document.
- **Requires:** T-011.
- **Objective:** a `languages` field (ISO 639-1 list) on each `config/sources.yaml` row, filled by the RAs from the portal, with source evidence in `verification_note`.
- **Owner:** Ainhoa (core schema + Uruguay); Asenat (Italy row). The other rows wait for T-060.
- **Write claim:** `config/sources.yaml` (per-row), `config/sources.example.yaml`. The field is added by Ainhoa on main; country rows are filled on country branches.
- **Gate:** Q-039 for multi-language rows.
- **Self-checks:** the loader accepts the field; rows without it report "unknown", never "covered".

### T-057 — Translate snippets into English (new; PF-007, U-4 c)
- **Status:** pending. Type: build.
- **Spec refs:** R-025, N-005. **Decision refs:** DEC-013.
- **Requires:** T-011.
- **Objective:**
  - An LLM translation step producing `source_snippet` = English translation (original in parentheses), at most 300 characters.
  - Model and prompt version recorded per row.
  - Never used for relevance or typing.
- **Owner:** Ainhoa (main).
- **Gate:** the PI approves the model and prompt.
- **Write claim:** `pipeline/core/translate.py`, tests. API keys are read from the environment, never committed (R-039).
- **Self-checks:**
  - English inputs pass through unchanged;
  - the original is preserved;
  - the length limit holds;
  - a test with the LLM stubbed confirms translation output never reaches `classify.py`.

### T-058 — Protect `procurement/main` (new; U-7 a)
- **Status:** ready. Type: operate.
- **Objective:** branch protection on `procurement/main` requires a PR plus green CI (`procurement.yml`).
- **Owner:** Simone, or the integrator session with her approval. This is a repo setting.
- **Self-checks:** `gh api repos/simonepaciphd/G3O/branches/procurement%2Fmain --jq .protected` returns `true`.

### T-059 — Apply the approved VP §B amendment (new; PF-024)
- **Status:** pending.
- **Requires:** T-022 + PI approval.
- **Owner:** Ainhoa (Drive).
- **Write claim:** `PP\docs\classification-validation-protocol.md` §B.

### T-060 — Assign fan-out owners (new; PF-018, U-8)
- **Status:** blocked, deferred by the PI until Italy is settled.
- **Objective:** the PI assigns RAs and capacity for T-034.x beyond Uruguay and Italy, and for T-032, T-033 and T-038.

## Parallel waves

| Wave | Ready condition | Lanes/tasks | Collision result | Integration/review gate |
|---|---|---|---|---|
| 0 | done | T-001-T-005, T-007 complete; T-006, T-008 verified; T-009 verified-pending | — | integrator records at lock |
| 1 | Stage 6 lock | PI: T-011, T-058. Ainhoa: T-031, T-047, T-022, T-048. Both RAs: T-037 | Disjoint (Drive notes, a repo setting, presentation, comments) | PI on T-031, T-022 |
| 2 | T-011 done | Ainhoa, sequential: T-053 → T-052 → T-015 → T-056 (core field) → T-051 → T-057. Asenat: T-012, then T-056 Italy row | Ainhoa's lane is sequential (shared `cli.py`/`base.py`/`standardize.py`/`sources.yaml`); Asenat writes only the Italy row on her branch; the `sources.yaml` merge goes through the integrator | integrator merges by PR |
| 3 | Wave 2 merged | Ainhoa, sequential: T-016 → T-017 → T-019 → T-020 | Sequential lane | integrator |
| 4 | Wave 3 + gates | Ainhoa, sequential: T-035 (if gates clear), then T-013 (if Q-001 ruled), T-018 (if Q-018 ruled) | Sequential | PI on T-035 |
| 5 | T-035, T-013, T-018 | Ainhoa: T-014. Reproducer: T-041 | Disjoint (code vs Drive reproduction folder) | T-049 |
| 6+ | mode checkpoints, T-060 | T-034.x, T-032, T-033, T-036, T-038; T-023 → T-024 after strata exist | Per-country branches; integrator merges | PI per mode |
| 7 | T-014 | T-049, T-040, T-042; T-055 at close | — | PI |

On each ruling, the integrator runs T-054. At each wave close, it runs T-050 and T-046.

**Critical path:** T-011 → T-016 → T-017 → T-019 → T-020 → T-035 → T-041. T-052 joins at T-019; T-053, T-047 and T-029 join at T-035. Contract output runs on a second path, T-013 → T-018 → T-014 → T-049, behind gates Q-001, Q-018 and Q-019. T-015 is off the critical path (PF-011).

**DAG check:** every edge points to a later wave or an earlier position in a sequential lane. No cycles.

## Launch manifest

`PLAN_ONLY`: no agent lanes are launched. These are the human lanes Stage 7 packages for. Tab labels apply only if an RA's harness registers in AI OS. The RA harness is separate (`ra-ai-os`).

| Lane | Task/chunk | Persona | CWD | Inputs | Claim | Output | Researcher gates | Review | Release |
|---|---|---|---|---|---|---|---|---|---|
| PI | T-011, T-058 | Simone | GitHub settings, Drive sharing | invite, logins | repo settings | access, protection | Ainhoa availability | self-check commands | at lock |
| Ainhoa (core + URY) | T-031, T-047, T-022, T-048 | RA via ra-ai-os | her G3O clone (`procurement/main`, read) + Drive | RS-043/044/047; `cli.py`; RS-047 queue | Drive notes only | presentation, fingerprint note, sample frame, roadmap ticks | Q-009a; design approval; availability | PI / integrator | at lock, once availability is confirmed |
| Asenat (Italy) | T-037, then T-012, T-056 (Italy row) | RA via ra-ai-os | her G3O clone, `procurement/italy` | 781cf0c; RS-011 | Italy config row | comments; note; languages | Q-014 later | integrator | T-037 at lock; T-012 after T-011 |
| Integrator | T-054, T-046, T-050, T-055 | agent session for the PI (DEC-009) | the worktree | rulings, PRs | governance files, merges | versions, merges | Simone approves each | Simone | started by Simone |

## Task-engineering queue (Stage 7)

These packets are written to `procurement/planning/handoffs/` after the lock (DEC-010). Each carries:
- the card;
- the locked spec version;
- the fixed decisions above;
- inputs with their state;
- the write claim;
- gates;
- self-checks and acceptance IDs;
- rollback;
- the email return-report format;
- the spec-delta trigger and stop/continue rule;
- the chunking trigger.

Ready at lock:

| Packet | For | Notes |
|---|---|---|
| T-011 | Simone | Checklist; most of it is hers |
| T-058 | Simone | One setting |
| T-031 | Ainhoa | Fallback: integrator session prepares it |
| T-047 | Ainhoa | — |
| T-022 | Ainhoa | — |
| T-048 | Ainhoa | — |
| T-037 | Asenat and Ainhoa | — |

Released by T-011: T-012 (Asenat); T-053, T-052, T-015, T-056, T-051, T-057 (Ainhoa, one sequential chunked handoff series).

## Spec-change control

- **Current spec:** `SPEC.md` v001-draft.4, LOCKED 2026-10-27T08:02-07:00.
- **Delta log:** `procurement/planning/CHANGELOG.md`, created before Wave 1. The integrator session is the sole writer.
- **Delta recipient:** Simone by email (DEC-010), forwarded to the integrator.
- **Lane reporting contract:** card defaults. Triggers: contradiction, ambiguity, new constraint, acceptance deviation. Stop: dependent output. Continue: independent work.
- **Post-execution:** T-055, `Spec-Reconciliation.md` (required closure artifact).

## Risks, approvals, rollback

| Risk | Trigger | Likelihood/impact | Prevention | Detection | Containment | Owner |
|---|---|---|---|---|---|---|
| Ainhoa unavailable | Q-037 residual; LOG 10-11 | medium / high | Confirm before Stage 7 | T-011 not accepted | PI reassigns the core lane | PI |
| Contract version unresolved | Q-001 | high / high | Gate T-013 | — | Staging-only output continues | PI |
| Uruguay yields ~0 contract rows | C-008; 0/132 linked | high / high | Q-010 gate | T-052 replay | Report-only Uruguay | PI / Master team |
| Italy access blocked or unlawful | Q-014, Q-023 | high / medium | Gate T-036 | T-012 | Skip or request permission | PI |
| No Italian terms | RS-054 empty | high / medium | T-044 EXTERNAL; A3 gate | — | Language status "not covered" (T-020) | multilingual |
| LLM translation errors in evidence text | T-057 | medium / medium | Original kept; model and prompt recorded; never used for coding | T-049 sample check | Re-translate (versioned) | Ainhoa / PI |
| Fingerprint confusion | RQ-001 | medium / medium | T-047 table | Manifest hash ≠ recorded commit | Relabel | Ainhoa |
| Uruguay full history ~200 h | C-007 | high / medium | Q-007; cache; T-051 | Run time | Bounded window | PI |
| Direct push to the shared core | R-037 | low / high | T-058 protection | CI + T-046 diff | Revert | integrator |
| Matcher validation stalled | Strata need fan-out (PF-009), fan-out deferred | high / medium | — | — | Tier-4 stays in review (R-016) | PI |
| Validation without positives | Q-015 | high / high | Gate T-025 | Frame counts | Precision-only report | PI |

**Gates:**
- **Destructive:** T-045.
- **External communication:** T-031; the PI's email to Asenat.
- **Long-running:** T-035, T-034.x (smoke run of 5 first; PI go above 24 h).
- **Credentials:** API keys for T-057 and Q-014 (environment only).
- **Shared infrastructure:** T-058, T-046.
- **Substantive:** every researcher gate.

## Blocked and deferred items

| Tasks | Unblocked by |
|---|---|
| T-013 | Q-001, Q-002, Q-003 |
| T-014 | Q-001, Q-004, Q-017, Q-019, Q-026, Q-030/Q-031 residuals, Q-010 |
| T-018 | Q-018, Q-032 |
| T-021 | Q-005 |
| T-023 | fan-out strata (T-060) |
| T-025 | Q-015 |
| T-028 | Q-032 |
| T-029 | Q-038 |
| T-032, T-033 | PI's first-source choice, Q-023, T-060 |
| T-034.x | mode checkpoints, T-028, T-029, T-060 |
| T-035 | Q-006, Q-007, Q-008, Q-010, Q-038 |
| T-036 | Q-012 (T-044), Q-014, Q-023, A3 |
| T-038 | Q-028 |
| T-039 | Q-024 |
| T-040 | Q-019 |
| T-042 | Q-024, Q-038 |
| T-045 | Q-025 |
| T-060 | deferred until Italy is settled |

Open questions with no task gated on them: Q-021 (standing default), Q-027 (timeline; no dates are committed).

## Readiness-audit results

- **Critical and high findings:** all 7 high findings resolved (PF-001-PF-004, PF-006-PF-008).
- **Substantive decisions:** answered (U-1-U-8). The two parts left open are blocked tasks: the Q-039 multi-language counting and T-060 fan-out.
- **Must-have spec IDs:** each has a producer and a verifier. G-006 has no producer, blocked on Q-019.
- **DAG:** acyclic. Inputs resolve to RS IDs, predecessor outputs, or USER-SUPPLIED/EXTERNAL.
- **Write claims:** disjoint within each wave. Ainhoa's lane is sequential, and the `sources.yaml` rows merge through the integrator.
- **Integrator:** one integrator session holds every shared surface.
- **Review capacity:** the integrator is reserved; T-049 and T-041 are run by people other than the author.
- **Tools and protocols:** exist. The integrator session is started by Simone.
- **Approval, cost, credential and rollback gates:** assigned.
- **Researcher gates:** carried in the cards, the task graph and the manifest.
- **Delta reporting:** every lane reports by email. The sole delta-log writer is named. `Spec-Reconciliation.md` is required (T-055).
- **Execution authorization:** `PLAN_ONLY` matches ruling 4.
- **Plan-Visual.html:** rendered from `_assets/planning-dashboard/`; the sync badge reads "✓ plan checks pass" (57 tasks, 48 edges; headless Chrome DOM check, 2026-10-27). Columns are waves, not dates (Q-027).

## User authorization to execute

`PLAN_ONLY` (ruling 4, 2026-10-26): no agent execution. RAs implement from the Stage 7 handoffs after the Stage 6 lock.
