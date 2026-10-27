# SPEC: G3O procurement pipeline (whole pipeline, retrofit)

Status: LOCKED v003 (2026-10-27T09:20-07:00, Simone Paci in chat: "LOCK"; spec delta SD-002). The agent's three readings (term search stays retrieval; overrides R-005/R-006/R-012/R-024; English snippet from the gpt-5-nano pass) were shown before the lock and not corrected. Prior locks: v002 2026-10-27T08:54-07:00 (snapshot `SPEC-v002.md`); v001-draft.4 2026-10-27T08:02-07:00 (snapshot `SPEC-v001-draft.4.md`)
Version: v003 (2026-10-27: SD-002, jev classification aligned with the main G3O pipeline; SD-001 RA-agnostic ownership)
Supersedes: none (first planning-protocol spec for this subproject; prior governing documents are cited, not replaced)
Owner: Simone Paci (PI)
Mode: revision (retrofit: extracted from existing documents; ruling 2a, 2026-10-26)
Drafted: 2026-10-27 by researcher session `20261027-claude-v2-0307d4d58c63fd23` (claude-opus-5-5)

**Extraction rule (ruling 2a).** Every line is tagged with its source. `USER:<ruling, date>` = a PI ruling. `SOURCE:<key> §` = a document listed in *Authoritative inputs*. A document marked *draft/proposal* below records what an RA or agent proposed; a line that rests only on such a document is tagged `SOURCE:<key> (proposal)` and is not settled until the PI approves it. `INFERRED` = a reading of the sources by the drafting agent, provisional. `OPEN` = not settled anywhere; listed in the open-questions table. No ruling has been reinterpreted; where two sources disagree, both are cited and the item is `OPEN`.

## Authoritative inputs

Drive root `H:\My Drive\Research\G3O\subprojects\procurement-pipeline\` = `PP\`. Repo `simonepaciphd/G3O` = `G3O:`.

| Key | Input | Authority | What it constrains |
|---|---|---|---|
| LC | Launch card `coord/launch/2026-10-27/3-g3o-procurement-plan.txt`, rulings 1a, 2a, 3a, 4 (2026-10-26) | PI rulings | Scope of this plan, method, location, mode |
| ES | `PP\docs\procurement-extension-spec.md` | PI scope ruling 2026-07-28, amended by PI rulings 2026-08-04 (D2/D3, D4, Q5a-c); §9 notes still open | Unit, outputs, crosswalk, extension, matching, coding |
| PM | `PP\agent-workspace\2026-08-04-reply-to-ainhoa.md` | **PI's own reply memo, 2026-08-04** (primary record of D1-D6; Q1a, Q5a-c, Q6 "confirmed, no ruling needed"; §4 contract re-pin instruction; §5 sample go-ahead) | Rulings of 2026-08-04 |
| PC | `PP\CLAUDE.md` | Subproject operating manual (2026-08-27); restates rulings D1-D6, Q1a, Q5a-c | Hard constraints, PI-reserved decisions |
| RC | `G3O:procurement/CLAUDE.md` @ `cee79b2` | Repo operating manual for RA sessions (2026-10-11, PI-requested) | RA-facing rules, branch rules |
| RM | `PP\implementation-roadmap.md` (status 2026-10-09) | Living plan | Phases 0-5, done/open items |
| AR | `PP\docs\architecture.md` | Design doc (audited 2026-08-03) | Target artifacts, review, reproducibility |
| CB | `PP\docs\genai-procurement-codebook.md` v0.4 | Working instrument applying the contract; no independent authority (CB §1) | Relevance, evidence, review triggers |
| CT | `G3O:g3o/extract/prompts/output_contract.md`, v2.5 on `main` @ `c6349d6` and on `procurement/main` | Root instrument (read-only) | The 39 fields, enums, defaults |
| SN | `G3O:procurement/docs/reference/output_contract_v2.0.SNAPSHOT.md` | Pinned copy of v2.0 (2026-08-03) | What the code currently mirrors |
| AI | `PP\docs\adapter-output-interface.md` | **Draft v0.1 (2026-10-09), not signed off** | Adapter contract, staged tables, Italy milestone |
| UP | `PP\docs\uruguay-full-run-protocol.md` | **Draft (2026-10-09)**; window and scope reserved to PI | Uruguay traversal, retries, logging, QC |
| VP | `PP\docs\classification-validation-protocol.md` | **Draft (2026-10-09)** | Validation sets |
| IR | `PP\agent-workspace\2026-10-07-item-level-rules-PROPOSAL.md` | **Proposal**; R1-R5, R8 implemented pending PI review | Item text and money rules |
| HI | `PP\agent-workspace\2026-10-07-handoff-index.md` (updated 2026-10-09) | RA index | Outstanding issues #1-#13, versions |
| SP | `PP\agent-workspace\2026-10-09-sprint-plan.md` | **Proposed** sprint plan | Sprint items P1-P5, I1-I3, V1-V2, U1 |
| SR | `PP\docs\source-registry.md` + tracker snapshot `PP\docs\G3O - Procurement Repository Tracker.xlsx` (2026-07-14) | Source list (canonical tracker is the Drive Google Sheet) | The 191 repositories |
| PU | `PP\agent-workspace\PI-Update-2026-08-29.md` §"Approvals to continue" | RA requests to PI, unanswered on record | Four pending approvals |
| MEM | Memory `contract-v2-2-owed-to-procurement` (2026-08-06) | Agent memory, verified against CT below | Contract v2.2 history |
| LOG | `PP\interaction-log.csv` row 2026-10-26 (Asenat session `e74cc28d`) | Session record | Italy source findings, open asks |
| S1 | PI answers in chat to the Stage-1 decision list, 2026-10-27, this session: "accept all procedural; SF-001 b, SF-002 b, SF-003 b, 4b, 5a, 6a, 7a, 8a, 9a, 10 RA or PI, verified when we've run the pipeline on it end to end and verified that the output conforms the expected" | PI rulings | Q-029-Q-038, P1-P3 |
| S3 | PI answers in chat to the Stage-5 plan-review decisions U-1-U-8, 2026-10-27, this session: "1 c, 2 c 3 a 4 c 5 a 6 a 7 a 8 granted, let's add this to the email to asenat …, no assigned RA for the fan-out yet, keep deferred for now, we'll decide after Italy is settled; defaults accepted" (U-items in `Plan-Review.md`) | PI rulings | R-016, R-025, A-008, N-005, Q-039; plan decisions |
| S4 | PI instruction in chat, 2026-10-27, after the baseline lock: "I would like to untie Aihnoa from the critical path -- she stays in charge of uruguay and that's it for now. Let's have the full plan RA-agnostic (maybe we'll give it to asenata if she does well on italy)" | PI ruling (spec delta SD-001) | Actors, Q-037 |
| S5 | PI answers in chat, 2026-10-27, after the v002 lock: "yes let's add it to the plan: it should be the main classification engine (we need this pipeline to produce a database that is as close as possible to the main g3o end to end pipeline, which has a contract_output for extraction/classification of text sources about genai use by instittuions)"; "i'm currently updating the main pipeline to use jev for most classification work, with gpt 5 nano doing a second pass to extract the source text for each jev decision"; "1a, 2 a for part of the codebook (some may not apply to procurement) + additional extensions (for categories that only apply to procuremeent) 3 dependency" | PI rulings (spec delta SD-002) | R-009, R-010, R-022, R-025, R-035, R-042-R-044, N-005, D-008, C-009, Q-021 |

Facts checked by the drafting agent on 2026-10-27: CT is v2.5 on both `main` and `procurement/main`; CT §4.2 contains `unknown` in `activity_type`; CT §4.3 `proposed` still reads "no signed MoU or contract, no budget line"; CT §3.2 lists 39 columns; CT §3.1 states the Stage-7 shipped product is three normalized CSVs, with the triple grain governing Stage-5 extraction output.

## Goal and success

- G-001 [USER: LC 1a, 2026-10-26; SOURCE: PC "Project context", ES §1]: Turn all 191 tracked public-procurement repositories into GenAI-procurement evidence for G3O, through the API, bulk and scrape access modes.
- G-002 [SOURCE: ES §1 rule 1-4, USER: ruling 2026-07-28]: The pipeline is an evidence channel into the existing G3O instrument, not a second observatory. Every observation is a row conforming to the G3O output contract at its grain (institution × activity × source).
- G-003 [SOURCE: ES §6.4, CB §5.4]: The evidence supports a census claim: searched sources with no GenAI evidence are recorded, not silent.
- G-004 [SOURCE: ES §4, ES §1 rule 4]: Procurement-specific detail the contract cannot hold (money, procedure, supplier role, contractual governance terms) is captured in an extension table and nowhere else.
- G-005 [SOURCE: AR §7, UP §6 (proposal), AI §7 (proposal)]: Every published result is reproducible from archived inputs, a recorded code version and documented commands by a person other than the one who produced it.
- G-006 OPEN (Q-019): The downstream use of the delivered rows inside G3O (which G3O product or table consumes them, and when) is not stated in any source.

## Actors, audience, and operating context

| Actor | Needs / permissions | Context of use | Successful experience |
|---|---|---|---|
| PI (Simone) | Rules on meaning: relevance, coding, taxonomy, thresholds, contract versions, sources, windows [SOURCE: PC "Still the PI's"; RC "Simone's"] | Checkpoints on staged samples before fan-out [SOURCE: ES §8.4, RM Phase 2-4] | Can rule from a checkpoint package without reading code [INFERRED] |
| RA, shared core (unassigned) | Engineering of the shared core on `procurement/main`: setup, core plumbing, matcher, tests, QC [SOURCE: PC "Yours"]. No named person; the PI assigns one [USER 2026-10-27 (S4, SD-001)]. A possible assignee after Italy is Asenat Mantovani (PI remark, not a ruling) | Repo `procurement/main` [SOURCE: RC "Branches"] | — |
| RA, Uruguay (Ainhoa Zamora) | Engineering for Uruguay only: Uruguay adapter, config row, fixtures/tests, runs, source documentation [USER 2026-10-27 (S4, SD-001); previously shared core + Uruguay, USER LC 4] | Branch `procurement/uruguay` [SOURCE: RC "Branches"] | — |
| RA, Italy (Asenat Mantovani) | Same engineering scope, Italy only; never edits `pipeline/core/` [SOURCE: RC "Branches", AI §1 (proposal)] | Branch `procurement/italy` [USER: LC 4] | — |
| Reproducer (a role, not a named person) | Reruns another person's run from written instructions and archived inputs [SOURCE: AI §7.4 (proposal); role USER 2026-10-27 (S1) (Q-037 a)] | Assigned per run in the plan [INFERRED] | Identical staged rows and code hash [SOURCE: AI §7.4 (proposal)] |
| Human reviewers / coders | Label validation sets blind; adjudicate review-queue items [SOURCE: VP §A-B (proposal); CB §8] | — | — |
| Multilingual subproject owner | Supplies non-English query terms and activity-typing rosters [SOURCE: PC; RM Phase 1; HI #3a] | `subprojects/multilingual-pipeline/` | — |
| Master Database Team | Owns `master_institutions.csv` and the key ledger [SOURCE: ES §5; HI #4a] | Read-only to this pipeline | — |
| Downstream G3O consumer | OPEN (Q-019) | — | — |

## Deliverables

| ID | Deliverable | Format/surface | Required contents | Consumer | Priority | Resources (Stage 2) |
|---|---|---|---|---|---|---|
| D-001 | Contract-conformant primary rows | Rows conforming to the G3O output contract, version per Q-001 [SOURCE: ES §2.1; CT] | All contract columns at (institution × activity × source); `source_type: procurement_tender` [SOURCE: CB §7]; contract defaults, never `null` [SOURCE: ES §3; CT §1] | Q-019 | must [SOURCE: ES §2] | RS-009, RS-010, RS-002, RS-008, RS-023, RS-029, RS-030, RS-031, RS-033, RS-050, RS-051 (gap: mapper, aggregation) |
| D-002 | Procurement extension table | One row per primary row, joined on `record_id`, schema `procurement_extension.schema.json` [SOURCE: ES §2.2, §7] | ES §4.1-4.3 fields, evidenced only; no relevance verdict, activity type or institution link [SOURCE: ES §2.2] | Q-019 | must [SOURCE: ES §2] | RS-024, RS-029, RS-033, RS-014, RS-002 |
| D-003 | Institution link table | Own table, schema `institution_link.schema.json`; resolved `institution_uid` only [SOURCE: ES §5 + Q5c amendment] | `record_id`, `institution_uid`, `role`, `match_method`, `match_score`, `matched_on`, `confidence`, `reviewer`, `reviewed_at` [SOURCE: ES §5]; `master_build_id` on every link [SOURCE: RM Phase 1 matcher] | D-001 builder | must [SOURCE: ES §5 "blocking requirement"] | RS-025, RS-032, RS-033, RS-028, RS-050, RS-051 |
| D-004 | Institution review queue | Schema `institution_review.schema.json` [SOURCE: ES §5 Q5c; USER: Q5c 2026-08-04] | Each unresolved buyer with candidates; leaves as a confirmed link or a closed rejection [SOURCE: ES §5 Q5c] | Reviewers → D-003 | must | RS-026, RS-032, RS-033, RS-047 (gap: closing workflow) |
| D-005 | Relevance review decision record | Persisted table [SOURCE: RM Phase 1 "Persist a full human-review decision queue"] | Reviewer, final relevance/activity, evidence, rationale, identity, timestamp [SOURCE: CB §8; RM] | D-001 builder | must [SOURCE: ES §1 table 1.4 "Accepted"] | RS-023, RS-030, RS-008 (gap: table) |
| D-006 | Per-run archive | Manifest JSON + staged tables + cached raw payloads on Drive [SOURCE: UP §5, §7 (proposal); AI §5 (proposal)] | Command, window, months read, limit, versions (pipeline, code hash, classifier, query set, matcher, master build), counts, QC booleans, every failure [SOURCE: UP §5; AI §5] | Reproducing RA, PI | must [SOURCE: AR §7] | RS-028, RS-034, RS-012, RS-011, RS-038 (gap: real run) |
| D-007 | Per-source documentation | `docs/sources/<source_id>.md` + `verification_status`/`verification_note` in `config/sources.yaml` [SOURCE: AI §3, §7.3 (proposal)]; PC "Respect each source" and RM Phase 4 name the tracker's `notes_RA` column instead (surface differs; Q-032) | Access, terms/robots/rate-limit findings, endpoint, window, exact commands [SOURCE: AI §7.3 (proposal)] | Reproducing RA, PI | must [INFERRED from PC "Respect each source" + G-005] | RS-020, RS-011, RS-012, RS-055, RS-057 (gap: surface) |
| D-008 | Classification validation report (of the jev decisions, SD-002) | Report against human-labelled set [SOURCE: VP §A (proposal); CB §9] | Agreement (κ), precision for `yes` and `yes ∪ unclear`, and recall among term-retrieved records only, with CIs; states that recall of records the query terms miss is not measured; error analysis by language and text source; never reported as prevalence [SOURCE: VP §A.2-4 (proposal); claim scope USER 2026-10-27 (S1) (Q-035 a)] | PI | must before results are reported [SOURCE: UP §6 "Classifier sanity" (proposal)] | RS-013, RS-048, RS-030, RS-047 (gap: labels) |
| D-009 | Matcher validation report | Buyer-level labelled sample stratified as ES §5 requires (national/subnational × several countries × script); ES §5 governs and VP §B is amended to match [SOURCE: ES §5 "Validate before trusting"; USER 2026-10-27 (S1) (Q-036 a); VP §B (proposal)] | Precision and recall per tier [SOURCE: ES §5]; precision-vs-score curve for tier-4 [SOURCE: VP §B (proposal)] | PI sets threshold from it [USER: PC "Still the PI's"] | must [SOURCE: ES §5] | RS-032, RS-047, RS-050, RS-013, RS-002 (gap: strata, labels) |
| D-010 | PI checkpoint package per access-mode template | Staged sample, labelled plumbing/QC [USER: 2026-08-04 clearance, RM status] | Staged output of the first source of each mode before fan-out [SOURCE: ES §8.4; RM Phases 2-4] | PI | must [SOURCE: ES §8.4] | RS-043, RS-044, RS-042, RS-019, RS-056, RS-036 (gap: bulk/scrape) |
| D-011 | Run / coverage report per source | Report with each run [SOURCE: UP §6 (proposal); RM Phase 1 D1] | Counts yes / unclear / no / not-assessable, cannot-type, review queue, linked, failures; not-assessable separate from absence [SOURCE: UP §5-6 (proposal); RC "Hard rules"]; each source's language-coverage status by the query set [USER 2026-10-27 (S1) (Q-029 b)] | PI | must | RS-028, RS-046, RS-047, RS-012 |
| D-012 | Consolidated, deduplicated, QC'd primary output across sources | [SOURCE: RM Phase 5] | Cross-source build of D-001-D-003; `outputs/staging/` is not the master [SOURCE: RM Phase 5] | Q-019 | must [SOURCE: RM Phase 5] | RS-033, RS-042 (gap: consolidation) |
| D-013 | Clean-checkout reproducibility run | [SOURCE: RM Phase 5] | Small sample rerun from a clean checkout [SOURCE: RM Phase 5] | PI | must [SOURCE: RM Phase 5] | RS-040, RS-047, RS-038, RS-039, RS-041 |
| D-014 | Shared adapter/output interface, signed | `docs/adapter-output-interface.md` v1.0 [SOURCE: AI header; SP I1 (proposal)] | What a country adds vs. never touches; adapter contract; staged outputs [SOURCE: AI §1-6] | RAs | should [OPEN Q-016: AI is a draft] | RS-011, RS-028, RS-036, RS-016 |

## Requirements

| ID | Requirement | Applies to | Source | Priority | Notes |
|---|---|---|---|---|---|
| R-001 | The root instrument does not change; output conforms to the contract's fields and enums | D-001 | USER 2026-07-28 via ES §1.1 | must | Version of record: Q-001 |
| R-002 | Only the 191 tracked repositories are read; no policy PDFs, roadmaps, strategies, gazette guidance | all | USER 2026-07-28 via ES §1.2 | must | |
| R-003 | No new unit of analysis, taxonomy, relevance scheme or theoretical framework | all | USER 2026-07-28 via ES §1.3, PC | must | A proposal that would add one is surfaced, not built [PC] |
| R-004 | Extension fields only where the contract cannot hold the information, each evidenced in the document, never inferred | D-002 | ES §1.4, §4 | must | New extension fields beyond ES §4: Q-005 |
| R-005 | Procurement evidence codes `adoption_stage: announced`, `year_announced` = contract/award year, `year_deployed: unknown` unless another source evidences deployment; never `production` from procurement alone; where another source evidences pilot/production, that is a separate row and the higher-evidence stage governs the activity; within one contracting process with both a tender and an award, the higher-evidence stage governs | D-001 | USER 2026-07-28 via ES §6.1; process case USER 2026-10-27 (S1) (Q-031 b) | must | |
| R-006 | A tender-only record creates an activity row coded `adoption_stage: proposed`, dated by publication; accepted consequence: the institution flips to `has_genai_activity: yes` | D-001 | USER D2/D3 2026-08-04, PM §3; restated ES §6.2 note, CB §6 | must | Conflicts with CT §4.3 text: Q-002 |
| R-007 | A relevant record that cannot be typed is reported (`cannot_type`), not coded, until the contract admits `unknown`; once it does, it is coded `activity_type: unknown` | D-001, D-011 | USER D1 2026-08-04, PM §3 and §5.2; restated PC, CB §5.3; coding as `unknown`: USER 2026-10-27 (S1) (Q-032 b) | must | When the trigger is met depends on Q-001/Q-003 |
| R-008 | `activity_type` applied directly from the notice using the contract's §4.2 signals | D-001 | PI-confirmed Q1a 2026-08-04, PM §2 ("confirmed, no ruling needed"); restated PC | must | English-only signals today: Q-013 |
| R-009 | Classification decisions on candidate notices are made by TypeSafe **jev** (pinned model version), as in the main G3O pipeline, using the main pipeline's question sets where they apply to procurement plus procurement-only extension questions for categories that exist only in procurement. A **gpt-5-nano second pass** extracts the source text supporting each jev decision. The procurement coding rules (R-005, R-006, R-012, R-024) stay deterministic and are applied on top of the jev decisions | classifier output, D-001 | USER 2026-10-27 (S5, SD-002) (overturns D5 for this channel; 1a, 2a) | must | Design follows the main-pipeline rewrite (C-009). Superseded rule: deterministic term/regex matching, no LLM adjudication (USER D5 2026-08-04, PM §3) |
| R-010 | Query set = `config/genai_queries.yaml` v1.0 as approved; no terms or languages added in this subproject; the GPT-5/GPT5 recall gap ships deliberately | retrieval | USER D4 2026-08-04, PM §3; restated PC, RM Phase 1 | must | Non-English coverage: Q-012; under SD-002 the query set selects the candidate notices that jev classifies (retrieval, not the decision) [USER 2026-10-27 (S5, SD-002)] |
| R-011 | Temporal window: no fixed start year; each source's full history; earliest record date recorded per source | D-006, D-011 | USER D4 2026-08-04, PM §3; restated ES §9, RM Phase 1 | must | Uruguay cost tension: Q-007 |
| R-012 | One staged record per award/lot; one activity per contracting process (OCID), not per release; interim `vendor: multiple` for multi-supplier releases, held for checkpoint | D-001, D-002 | USER D6 2026-08-04, PM §3 ("lots and awards carried in the extension table"); staging half PI-confirmed Q6, PM §2; activity half amended by USER 2026-10-27 (S1) (Q-031 b) | must | Interim rule: Q-004; non-OCDS process identifier and D-002 join: Q-031 residual |
| R-013 | Institutions keyed by `institution_uid`, never `master_row_id`; links resolved through the key ledger (`absent` live, `retired` terminal, merges chained) | D-003 | PI-confirmed Q5a 2026-08-04, PM §2 (resolve through ledger; merges only from a PI-filled `pi_decision`); ES §5 amendment | must | |
| R-014 | Matching tiers 0-5 as ES §5; tier 2 unreachable (no registry id; acquiring one is a new source) | D-003, D-004 | ES §5; PI-confirmed Q5b 2026-08-04, PM §2 | must | |
| R-015 | Subnational fuzzy matches require a second corroborating signal; native-script matching; respect `duplicate` and `disambiguation` | D-003 | ES §5 | must | |
| R-016 | Auto-accept threshold set by the PI from the validation measurement, never from a default; the measurement follows the ES §5 stratified design. Exception: tier-1 (domain) and tier-3 (exact-name) deterministic auto-accepts are allowed before validation [USER 2026-10-27 (S3) (U-6 a)] | D-003, D-009 | PC "Still the PI's"; ES §5; design USER 2026-10-27 (S1) (Q-036 a) | must | Interim "every fuzzy candidate goes to review": SOURCE PU #2 (RA practice). Value: Q-009b |
| R-017 | `institution_link` holds resolved uids only; unresolved candidates in the review queue | D-003, D-004 | PI-confirmed Q5c 2026-08-04, PM §2 | must | |
| R-018 | A row without a resolved institution cannot enter the primary table | D-001 | ES §3 (buyer_name row) | must | Uruguay master coverage: Q-010 |
| R-019 | Never emit `null` in contract output; use contract defaults (`_NA_`, `unknown`, `none_reported`, `not_documented`) | D-001 | ES §3; CT §1; PC | must | `null` allowed in extension where schema declares it [CB §7] |
| R-020 | Never fabricate or alter a `source_url`; record only stated vendors, dates, values, penalties, statuses | D-001, D-002 | ES §3; CB §7; PC | must | |
| R-021 | Negative evidence: a searched source with no GenAI evidence yields `confirms_absence` rows, one per institution × repository × window; this applies whether or not the source's language is covered by the query set, and the run report states each source's language-coverage status | D-001, D-011 | ES §6.4; CB §5, §5.4; language USER 2026-10-27 (S1) (Q-029 b); grain USER 2026-10-27 (S1) (Q-030 b) | must | Extension rows for absence rows: Q-030 residual |
| R-022 | `has_genai_activity` is institution-level, same value on every row of an institution, aggregated across its sources after review; consolidation reuses the main pipeline's Stage 6 jev consolidation [USER 2026-10-27 (S5, SD-002)] | D-001 | CB §5.2; CT §1 "Institution-level fields" | must | Aggregation scope: Q-018 |
| R-023 | Records with no descriptive text are `not_assessable`, never absence, and reported separately | D-001, D-011 | RC "Hard rules", ratified USER 2026-10-27 (S1) (Q-034 a); IR R8 (proposal, implemented) | must | Contract representation: Q-032 residual |
| R-024 | Framework establishment → central purchasing body; call-off → calling institution; framework without caller → `unclear`/`ambiguous` + `institution_attribution` | D-001, D-003 | ES §6.3 | must | |
| R-025 | `source_snippet` ≤300 chars, English translation with original in parentheses; original-language evidence preserved; the translation may be produced by an LLM, which is not adjudication under D5; under SD-002 it is produced in the gpt-5-nano evidence pass (R-009) | D-001 | ES §3; CB §7; method USER 2026-10-27 (S3) (U-4 c) | must | |
| R-026 | `uncertainty_flags` from the contract's closed vocabulary only; `internal_*` flags dropped before contract output | D-001 | CB §7 | must | |
| R-027 | Human-review triggers per CB §8 route candidates to review; unresolved cases do not enter the master | D-005, D-001 | CB §8; ES §1 table 1.4 | must | Uncertainty band "pilot-defined": Q-022 |
| R-028 | Small-sample smoke run before any full pull; fix every error first | every source | PC "Hard constraints" (standing lab rule) | must | |
| R-029 | Respect each source: robots.txt, rate limits, terms checked before scraping and recorded | every source, D-007 | PC "Hard constraints"; RC | must | When terms forbid access: Q-023 |
| R-030 | A source marked `unverified_snapshot` runs only as a bounded probe (`--allow-unverified` + `--limit`). A source becomes verified when the pipeline has been run on it end to end and its output has been checked to conform to what is expected; the RA or the PI approves the change | every source | RM Phase 1; RC; criterion and approver USER 2026-10-27 (S1) (Q-038) | must | Stated as a capability constraint, recorded as-is. Residuals: Q-038 (run size, "expected", frame pin) |
| R-031 | No money summed across currencies; no imputed quantities; partial totals flagged; no FX conversion in the pipeline | D-002 | RC "Hard rules" (never sum across currencies), ratified USER 2026-10-27 (S1) (Q-034 a); IR R3-R5 (proposal) | must (currency rule); rest Q-005 | |
| R-032 | Every staged row validated against its schema before write; failures raise | staged tables | AR §6 | must | |
| R-033 | Nothing dropped silently: fetch/search failures recorded and counted; fetched + failed = items read | D-006, D-011 | UP §4, §6 (proposal); AI §2 (proposal) | should [proposal] | |
| R-034 | Provenance on every record: pipeline version, classifier version, fetch time, raw payload reference; query/codebook version on coded records | D-001, D-006 | AR §7; CB §1 | must | |
| R-035 | Instruments versioned: a substantive change to inclusion rules or terms needs a new codebook version and a new query-set version; existing records keep their version | CB, query set | CB §1 | must | |
| R-036 | `manual` sources (41) are not automated; they are flagged for human collection | 41 manual rows | RM "Out of scope"; README; AR §3 | must as written | Ruling 1a says "all 191": Q-024 |
| R-037 | Country work adds only adapter, config row, fixtures/tests; the shared core changes only on `procurement/main` | code | RC "Branches", ratified USER 2026-10-27 (S1) (Q-034 a); AI §1 (proposal) | must | |
| R-038 | Code lives in git (`G3O:procurement/`), never in Drive; data, outputs, logs on Drive | all | PI rulings 2026-10-11 via LOG 2026-10-11 rows; RC "Where things live" | must | Drive `pipeline/` copy status: Q-025 |
| R-039 | Secrets never in code | code | PC; RC | must | |
| R-040 | Validation labels come from people, blind to the classifier, two coders, disagreements resolved by a third coder or the PI; oversampled positives never reported as prevalence | D-008, D-009 | VP §A-B (proposal) | should [proposal] | Q-016 |
| R-041 | Every reported result passes the run QC checks before it is reported (dispositions sum, every row matched or in review, nothing lost, row→payload→award map, money sanity, classifier sanity, not-assessable separate, reproducibility) | D-011 | UP §6 (proposal) | should [proposal] | Q-016 |
| R-042 | A written **question-set mapping**: which items of the main pipeline's codebook/question sets apply to procurement, which do not, and the procurement-only extension questions; versioned as a new procurement codebook version (R-035) | classifier | USER 2026-10-27 (S5, SD-002) (2a) | must | PI approves the mapping |
| R-043 | Procurement calls the main G3O pipeline's jev client, question sets and Stage 6 consolidation as a shared dependency, not a copy; the shared code version and jev model version are recorded in every run manifest | code, D-006 | USER 2026-10-27 (S5, SD-002) (2a) | must | |
| R-044 | TypeSafe spending: the API key is read from the environment (never committed, R-039) and every run that calls jev or gpt-5-nano has a PI-approved spending ceiling before it starts | every run | USER 2026-10-27 (S5, SD-002) (plan entry) | must | |

## Scenarios

| ID | Actor/start | Trigger/input | Expected final state | Failure behavior | Requirement IDs |
|---|---|---|---|---|---|
| SC-01 Canonical award | RA, verified source | GenAI award naming product and buyer | `confirms_activity` row, `announced`, award year; extension row; resolved link | Unresolved buyer → D-004, no primary row | R-005, R-013, R-018 |
| SC-02 Tender only | RA | GenAI tender, no award | `proposed` row dated by publication | — | R-006, Q-002 |
| SC-03 Searched, nothing | RA | Releases with text, no GenAI signal, for an institution in a repository and window | One `confirms_absence` row per institution × repository × window [USER 2026-10-27 (S1) (Q-030 b)]; institution not set `no` from one record [CB §4, §5] | — | R-021, R-022 |
| SC-04 No text | RA | Release with no title/description/items | `not_assessable`, counted separately | Never absence | R-023 |
| SC-05 AI, not clearly generative | Classifier | "AI tools" notice | `unclear`/`ambiguous` + `genai_vs_traditional_ai`; review | — | R-027, CT §4.1 |
| SC-06 Untypeable relevant | Classifier | GenAI confirmed, use unstated | Reported `cannot_type`; coded `activity_type: unknown` once the contract version of record admits it [USER 2026-10-27 (S1) (Q-032 b)] | Never a guessed member | R-007, Q-003 |
| SC-07 Multi-award release | RA | Release with several awards/suppliers | One staged record per award; one activity; interim `vendor: multiple` | — | R-012, Q-004 |
| SC-08 Framework | RA | Framework establishment / call-off / no caller | Attribution per ES §6.3 | `institution_attribution` flag | R-024 |
| SC-09 Mixed currency | RA | Award lines in two currencies | No cross-currency sum; flagged | — | R-031 |
| SC-10 Source fault | RA | Network error, 429/5xx, 404 | Retried where allowed; failures recorded and reported | Nothing dropped silently | R-033 |
| SC-11 Source terms forbid or block automation | RA | robots/ToS/WAF block | OPEN (Q-023) | Not circumvented [LOG 2026-10-26] | R-029 |
| SC-12 Reproduction | Second RA | Instructions + archived inputs | Identical staged rows and code hash | Discrepancy reported | G-005, D-013 |
| SC-13 Master rebuild | Matcher | New master build | Links remain valid via uid + ledger; build id recorded | — | R-013 |

## Inputs and provenance

| Input | Owner/source | Required? | Validity/freshness | Missing/conflict behavior |
|---|---|---|---|---|
| 191 repositories | Drive tracker (canonical); `config/sources.yaml` (150) + `config/manual_sources.yaml` (41) [SOURCE: SR; ES §1]. OCDS count: SR/README say 67 of 191; `sources.yaml` carries 65 `is_ocds: true` among its 150 (reviewer count, 2026-10-27; not reconciled) | yes | Snapshot 2026-07-14; all rows `unverified_snapshot` until checked [SOURCE: RM] | Unverified → bounded probe only [R-030] |
| Output contract | G3O root [CT] | yes | Version of record OPEN [Q-001] | — |
| Query set v1.0 | PI-approved [USER D4] | yes | es/fr/pt (+en) coverage [SOURCE: HI §3] | Missing language → Q-012 |
| Institution master + key ledger | Master Database Team, `inputs/G3O_Institution_Master/data_final/` [SOURCE: PC "Read-only paths"] | yes | Build `mb-2026-07-30` recorded at 2026-10-09 [SOURCE: HI §3]; root CLAUDE.md says the master was rebuilt 2026-07-13 at 719,588 rows | Coverage gaps (Uruguay 185 rows) → Q-010 |
| Human labels | Coders, PI [SOURCE: VP] | yes for D-008/D-009 | — | Positives sourcing → Q-015 |
| Non-English rosters/terms | Multilingual subproject [SOURCE: PC] | yes for non-English typing and Italian retrieval | Not delivered [SOURCE: HI #3a; board #87] | Report `cannot_type`; Q-012, Q-013 |

## Output/interface contracts

| Producer/result | Consumer | Format/granularity | Required fields/properties | Rejection condition |
|---|---|---|---|---|
| D-001 | Q-019 | Contract rows, triple grain | CT §3.2 columns | Any `null`; unresolved institution; non-vocabulary flag; Group-D rule violated (CT §6 check 2) [SOURCE: CB §5.1] |
| D-002 | Q-019 | 1:1 on `record_id` | ES §4 | Carries relevance/type/link [ES §2.2]; unevidenced value |
| D-003 | D-001 builder | N per record | ES §5 columns + `master_build_id` | Numeric-looking uid [SOURCE: AR §6]; unresolved candidate |
| Adapter → core | Shared core | Intermediate field dict | AI §4 (proposal) | Guessed fields [AI §4] |

## Quality attributes

| Attribute | Required outcome | Observable threshold/evidence | Priority |
|---|---|---|---|
| Classification accuracy | Measured against human labels | Threshold OPEN (Q-020) | must measure [VP, UP §6] |
| Matching accuracy | Measured per tier | PI sets auto-accept from curve (R-016) | must |
| Reproducibility | Second RA reproduces | Identical rows + code hash [AI §7.4 (proposal)] | must [AR §7] |
| Completeness accounting | No silent loss | Reconciliation counts (R-033) | should [proposal] |
| Source respect | No ToS/robots violation | Recorded check per source (D-007) | must [PC] |

## Acceptance tests

| ID | Given | When | Then | Evidence | Approver | Requirement IDs |
|---|---|---|---|---|---|---|
| A-001 | D-001 output | Validated against CT schema/enums | Zero schema violations, zero `null` | Validation log | PI | R-001, R-019 |
| A-002 | Any primary row | Inspected | Has a resolved `institution_uid` present in the ledger | Join check | PI | R-013, R-018 |
| A-003 | Procurement rows | Inspected | No `production`; awards `announced` with award year; tender-only `proposed` dated by publication | Distribution table | PI | R-005, R-006 |
| A-004 | Each run | Manifest QC | All QC booleans true; failures listed | D-006 | PI | R-033, R-041 |
| A-005 | Each source in scope | Before full run | Smoke run (5) archived; source terms recorded | D-006, D-007 | PI | R-028, R-029 |
| A-006 | First source per access mode | Before fan-out | PI checkpoint signed on staged sample | D-010 + PI note | PI | ES §8.4 |
| A-007 | Classifier | Before results reported | Validation report exists with κ, P/R + CIs; pass threshold OPEN | D-008 | PI | R-040, Q-020 |
| A-008 | Matcher | Before fuzzy (tier-4) auto-accept is enabled; tiers 1/3 exempt [USER 2026-10-27 (S3) (U-6 a)] | Validation report exists; PI threshold recorded | D-009 + PI note | PI | R-016 |
| A-009 | A run by person X | Reproduced by a different person in the reproducer role from D-007 + archive | Identical `record_id`s, field values, code hash | Diff report | PI | G-005 |
| A-010 | Clean checkout | Small-sample rerun | Same outputs as archived | D-013 | PI | RM Phase 5 |
| A-011 | Run report | Inspected | `not_assessable` and `cannot_type` counts present and separate from absence | D-011 | PI | R-007, R-023 |
| A-012 | Coverage of the 191 | At pipeline close | Every repository has a recorded status (run / blocked with reason / manual-flagged / out of scope); status vocabulary OPEN | Coverage table | PI | G-001, Q-024 |

## Constraints

- C-001 [USER 2026-07-28 via ES §1]: Root contract unchanged by this subproject; the contract file is read-only here [PC "Read-only paths"; LC Boundaries].
- C-002 [PC; LC Boundaries]: `inputs/` and the institution master are read-only.
- C-003 [USER LC 3a]: Planning governance lives in `procurement/planning/` of `G3O`, branch `procurement/main` (departure from the protocol's root-level `planning/`, recorded in `Plan-Manifest.md`).
- C-004 [USER LC 4]: RAs implement; agents launch no execution lanes from this plan.
- C-005 [PC; RC]: Decisions about meaning are the PI's; an RA or agent asks rather than decides.
- C-006 [SOURCE: AI §8, HI #6; LOG 2026-10-26]: RA repository write access is a precondition for RA work in git; status as of 2026-10-27: Asenat invited (pending), Ainhoa not a collaborator [LC Known facts].
- C-007 [SOURCE: UP §1]: Per-release fetch cost on Uruguay ARCE ≈0.7 s/release, ~1M releases, ~200 h for full history (measured 2026-10-07).
- C-008 [SOURCE: HI #4a]: Institution master coverage of Uruguay is 185 rows (no hospitals, state enterprises, armed forces); 0/132 probe rows linked.
- C-009 [USER 2026-10-27 (S5, SD-002) (3)]: Procurement classification depends on the main G3O pipeline's rewrite to jev classification plus a gpt-5-nano evidence pass, in progress by the PI (location not recorded). Procurement classification cannot be built before it lands.

## Non-goals

- N-001 [USER 2026-07-28 via ES §1 table]: Roadmap actions as a second unit of analysis (archived).
- N-002 [USER 2026-07-28]: The four analytical dimensions framework.
- N-003 [USER 2026-07-28]: Any data source outside the 191 repositories (policy PDFs, strategies, gazette guidance, national registries for tier 2).
- N-004 [USER D4 2026-08-04]: Deciding language coverage here; owned by `subprojects/multilingual-pipeline/`.
- N-005 SUPERSEDED-BY:SD-002 [USER 2026-10-27 (S5, SD-002)]. Was: "[USER D5 2026-08-04, PM §3]: LLM adjudication in the pilot." Classification now uses jev and gpt-5-nano (R-009).
- N-006 [SOURCE: PC "Hard constraints"; RM Phase 2 note]: Presenting staged output (`outputs/staging/`) as the G3O master.
- N-007 [SOURCE: CB §5.1]: Repurposing `background_only` for a meaning other than the contract's. (Whether the channel emits it at all is Q-017.)
- N-008 [SOURCE: UP §6 "Not-assessable share"; VP §A.3]: Prevalence claims from validation samples or from not-assessable rows.

## Open questions and provisional assumptions

Per procedural P1 (USER 2026-10-27 (S1)): "Blocking" below names the tasks or deliverables a question blocks; open questions do not block approval of this spec. Each becomes a researcher gate in the plan, owner the PI.

| ID | Question/assumption | Why it matters | Owner | Blocking? | Resolution |
|---|---|---|---|---|---|
| Q-001 | **Contract version of record.** ES/PC/CB/RC pin v2.0 (snapshot SN); HI §1/§3 call v2.5 the contract of record and SP P3 proposes re-pinning; CT is v2.5 on `main`. **PM §4 (PI, 2026-08-04): "Re-pin once v2.2 lands … rather than re-pinning twice"**; v2.2 has since landed and the contract moved on to v2.5 (MEM: `unknown` shipped as v2.2 via PR #51). Which version does D-001 conform to, and is PM §4 now triggered? (Surfaced per LC; not resolved.) | Every D-001 test | PI | yes (D-001, A-001) | Surfaced per P2 (USER 2026-10-27 (S1)); not resolved |
| Q-002 | **`proposed` for tenders vs. CT §4.3.** D2/D3 rules tenders `proposed`; CT v2.5 §4.3 still defines `proposed` as having no contract and no budget line; PM §3 D2/D3 says §4.3 "is being amended in the same v2.2 bump"; MEM (2026-08-06) says it is still owed and "procurement's tender coding is still blocked"; PM §5 says tender-only records "are codeable". Proceed under D2/D3 anyway, or hold tender rows until §4.3 is amended? | SC-02, R-006 | PI | yes for tender rows | — |
| Q-003 | **D1 `unknown`.** CT v2.5 includes `activity_type: unknown` (MEM: shipped as v2.2, PR #51, its §4.2 row flagged as needing a PI line-edit). R-007's own trigger ("until the contract admits `unknown`") appears met. Does that lift the D1 hold (report → code), from which version, and was the §4.2 definition row line-edited? | R-007, SC-06 | PI | yes for untypeable rows | — |
| Q-004 | **Interim `vendor: multiple`** (D6) held for checkpoint [ES §9; PU #4; board #85]. Confirm, amend or replace. | R-012 | PI | yes for release collapse | — |
| Q-005 | **Item-level rules R1-R8** and four proposed extension fields (`value_source`, `value_completeness`, `description_source`, `value_includes_tax`) [IR; SP P2; HI #1]. R1-R5, R8 are implemented pending review. | R-004, R-023, R-031 | PI | yes for money fields | — |
| Q-006 | **Clarification notices** (`aclar_llamado`, `tenderUpdate`, 59% of Uruguay probe releases): do they create staged rows? [IR Q3; HI #8e; UP §2] | Counts, absence | PI | yes for Uruguay run | — |
| Q-007 | **Uruguay window and source scope** [UP §1-2; HI #9]. D4 rules full history (R-011); UP offers (a) full history ~200 h, (b) bounded window, (c) bulk files (not located). Is D4 binding for Uruguay, or does the PI set a window? Other Uruguayan sources? | Uruguay run | PI | yes for Uruguay run | — |
| Q-008 | **Live `outputs/`** holds the old-extractor 132-row Uruguay probe: keep, revert or regenerate [HI #10]. | Staging integrity | PI | no (Uruguay only) | — |
| Q-009a | **OCDS fan-out sign-off** [PU #1; board #141]. Checkpoint package D-010 prepared 2026-08-29; no recorded PI sign-off. | Phase 2 fan-out | PI | yes for fan-out | — |
| Q-009b | **Matcher auto-accept threshold** value and validation-sample plan [PU #2; board #86]. | R-016 | PI | yes for auto-accept | — |
| Q-010 | **Uruguay master coverage** (C-008): with R-018, almost no Uruguay row can enter D-001. Master expansion (Master Database Team) or accepted gap? | Uruguay D-001 | PI → Master team | yes for Uruguay D-001 | — |
| Q-011 | **"Intendencia de X" normalization** (HI #4b): proposed fix needs a cross-country check. Is this a matching rule for the PI, or engineering? | Matching recall | PI | no | — |
| Q-012 | **Italian (and other non-es/fr/pt) query terms** routed to multilingual subproject [HI #3a; SP I2; AI §8]. Not delivered. | Italy retrieval | PI (routing) | yes for Italy retrieval | — |
| Q-013 | **Non-English activity typing** (board #87; RM Phase 1): typing is English-only; non-English relevant records report `cannot_type`. | R-008 on all non-English sources | Multilingual subproject | yes for typed rows | — |
| Q-014 | **Italy source questions** [LOG 2026-10-26]: API key requirement and rate limits (need a live request); whether OCP-hosted bulk files count as the same source (bears on R-002/N-003); Italy window; portal blocking automated requests (RM Phase 2: ANAC 403s past its WAF), i.e. Italy already meets the Q-023 condition, so the proposed 2026-11-04 Italy milestone (Q-027) may not be feasible. | Italy | PI | yes for Italy run | — |
| Q-015 | **Positives for the validation set**: Uruguay has none; sourcing from other sources or PI-known cases [VP §A; SP V1]. | D-008 | PI | yes for D-008 | — |
| Q-016 | **Approval status of the draft protocols** (AI, UP, VP, IR, SP): which become binding requirements (currently `should [proposal]`)? | R-033, R-040, R-041, D-014 | PI | yes for those items | — |
| Q-017 | **`background_only`**: RM Phase 1 lists "Emit `background_only` where it applies" as a to-do; CB §5.1 says the channel does not emit it and must not repurpose it. | D-001 coverage of CT §4.7 | PI | no | — |
| Q-018 | **Institution-level aggregation scope**: aggregate `has_genai_activity` over procurement sources only, or jointly with other G3O channels? Who performs it (this pipeline or G3O consolidation)? | R-022, D-001 | PI | yes for D-001 | — |
| Q-019 | **Downstream consumer and landing**: where D-001/D-002/D-003 go in G3O (CT §3.1: shipped product is three normalized Stage-7 CSVs), in what form, and when. | G-006, D-012 | PI | yes for D-012 | — |
| Q-020 | **Pass thresholds** for classifier and matcher validation; acceptance of a run's QC. No source sets numbers. | A-007, A-008 | PI | yes for A-007 | — |
| Q-021 | **Classification beyond the pilot** (NLP-only vs. NLP+LLM) [PC "Still the PI's"]. When does "pilot" end? | R-009 scope | PI | no | RESOLVED USER 2026-10-27 (S5, SD-002): jev is the classification engine, with a gpt-5-nano evidence pass (R-009) |
| Q-022 | **"Pilot-defined uncertainty band"** for review routing (CB §8) is undefined for a deterministic classifier. | R-027 | PI | no | — |
| Q-023 | **Sources whose terms forbid or technically block automation**: skip, request permission, or reclassify as manual? [SC-11] | Phases 2-4 | PI | yes per affected source | — |
| Q-024 | **Scope of "all 191"** (ruling 1a) vs. the 41 `manual` rows out of automation (R-036). Do manual sources stay flagged-only, or enter the plan as human-collection work? | G-001, A-012 | PI | yes for A-012 | — |
| Q-025 | **Drive `pipeline/` folder**: archive as superseded once RAs work in git (board #143 to-do), and how to treat any drift since 2026-10-11 (Stage 2 compares). | R-038 | PI | no | — |
| Q-026 | **The 745 pending rename decisions** in the key ledger (CB §10) that retire uids on the next master build. | R-013 | PI | no | — |
| Q-027 | **Timeline**: no deadline for the whole pipeline in any source; SP proposes sprint dates (Italy small run 2026-11-04; Uruguay full run from 2026-11-02). | Plan waves | PI | no | — |
| Q-028 | **Brazil** (PNCP, non-OCDS, ≤5-record sample built): is it in the RA assignments? LC 4 names only shared core + Uruguay and Italy. | Phase 2 non-OCDS | PI | no | — |
| Q-029 | **Absence and language readiness** (Spec-Review SF-001): when does "searched, nothing found" count as `confirms_absence` for a source whose language the query set does not cover? | G-003, R-021, R-022 | PI | no | RESOLVED USER 2026-10-27 (S1), SF-001 b: emit `confirms_absence`; the run report flags each source's language-coverage status (R-021, D-011) |
| Q-030 | **Grain of negative-evidence rows and extension scope** (SF-002): per release, per (institution × repository × window), or counted only; do absence rows get extension rows (ES §2 "per relevant record" vs. D-002 "one per primary row")? | D-001, D-002, A-001 | PI | yes for D-002 on absence rows | PARTLY RESOLVED USER 2026-10-27 (S1), SF-002 b: one row per institution × repository × window (R-021, SC-03). **Still OPEN:** whether absence rows get extension rows (ES §2 vs. D-002) |
| Q-031 | **Activity identity** (SF-003): one activity per release (D6, PM §3) vs. per contracting process (CB §2, IR R6b); how D-002 joins to an activity whose `record_id`s are award-level; stage when one process has a tender and an award. | D-001, D-002, A-003 | PI | yes for non-OCDS activity rows and the D-002 join | PARTLY RESOLVED USER 2026-10-27 (S1), SF-003 b: one activity per contracting process (OCID); higher-evidence stage governs (R-005, R-012). **Still OPEN (gap noted by drafting agent):** process identifier for non-OCDS sources; how D-002 (1:1 on `record_id`) joins when one activity has several award-level records |
| Q-032 | **Contract representation of `not_assessable` and `cannot_type` records** (SF-004), and their weight in institution aggregation (R-022). Also: D-007 recording surface (`verification_note` + `docs/sources/` vs. tracker `notes_RA`). | D-001, R-022, D-007 | PI | yes for `not_assessable` rows | PARTLY RESOLVED USER 2026-10-27 (S1), 4b: `cannot_type` records coded `activity_type: unknown`, conditional on Q-001/Q-003 (R-007, SC-06). **Still OPEN:** contract representation of `not_assessable` and its weight in R-022 aggregation; D-007 recording surface |
| Q-033 | **PI 2026-10-07 directive** exists only second-hand (quoted in HI, AI, UP, VP, SP, LOG); may it be cited, or is a primary copy available? (SF-005b) | Q-007, D-008, D-014, actors | PI | no | RESOLVED USER 2026-10-27 (S1), 5a: cite as `USER (second-hand)` |
| Q-034 | **Did committing `RC` (2026-10-11) ratify its hard rules?** If not, R-023, R-031, R-037 drop to proposal; G-005/D-006 "reproduction by another person" rests on AI §7.4/SP I3 (proposals), not AR §7 (SF-006). | R-023, R-031, R-037, G-005, D-006 | PI | no | RESOLVED USER 2026-10-27 (S1), 6a: yes; R-023, R-031 (currency rule), R-037 stay `must` |
| Q-035 | **Recall claim of D-008** (SF-007): term-retrieved positives cannot measure retrieval misses; scope D-008 to precision + conditional recall, add a retrieval-independent positive stratum, and/or make codebook 1.0 (CB §9) a deliverable. | D-008, G-003 | PI | no | RESOLVED USER 2026-10-27 (S1), 7a: D-008 claims precision + recall among retrieved records and states that limit |
| Q-036 | **Matcher validation design** (SF-008): ES §5 stratified sample (ruled 2026-07-28) vs. VP §B Uruguay review-queue sample; global vs. per-country/script threshold. | D-009, R-016 | PI | no | RESOLVED USER 2026-10-27 (S1), 8a: ES §5 governs; VP §B to be amended (plan task; VP sits in the Drive subproject) |
| Q-037 | **Reproducer and RA availability** (SF-009): who executes A-009; is Ainhoa available for Uruguay (scope reduced by SD-001) (LOG 2026-10-11: "starting a new job")? | A-009, G-005, actors | PI | no | RESOLVED USER 2026-10-27 (S1), 9a: reproducer named as a role. Ainhoa's availability was not part of the ruling; carried to the Stage 7 handoffs; scope of the availability question reduced to Uruguay by SD-001 |
| Q-038 | **Source verification criterion and approver; frame pin** (SF-010): what evidence flips `verification_status`, who approves it, and which tracker version fixes the 191. | R-030, A-012 | PI | yes for any full run | PARTLY RESOLVED USER 2026-10-27 (S1): approver RA or PI; verified = pipeline run end to end on the source and output checked to conform to what is expected (R-030). **Still OPEN:** (i) whether that end-to-end run is the bounded probe R-030 allows or a larger run; (ii) what "expected" is checked against (e.g. A-001 contract validation, a hand-checked sample); (iii) frame pin: which tracker version fixes the 191 |
| Q-039 | **Per-source languages** (plan review PF-006): RAs record each source's language(s) [USER 2026-10-27 (S3) (U-3 a)]. **Still OPEN:** how a source with several languages is counted for the language-coverage status (R-021, D-011). | R-021, D-011 | PI | yes for multi-language sources' coverage status | — |

## Change history

| Version | Delta ID | Changed spec IDs | Change | Approved by/at | Reason | Downstream artifacts superseded |
|---|---|---|---|---|---|---|
| v001-draft | — | all | Initial extraction (ruling 2a) | not approved | — | none |
| v001-draft.2 | — | inputs, R-005-R-016, SC-03, D-007, D-014, N-005, N-007, Q-001-Q-003, Q-009, Q-014, Q-029-Q-038 | Mechanical fixes from Spec-Review SF-005a, SF-011-SF-013; reviewer's decision items added as OPEN | not approved | Spec review | none |
| v001-draft.3 | — | inputs (S1), actors, D-008, D-009, D-011, R-005, R-007, R-012, R-016, R-021, R-023, R-030, R-031, R-037, SC-03, SC-06, A-009, open-questions preamble, Q-001, Q-029-Q-038 | PI rulings S1 applied: SF-001 b, SF-002 b, SF-003 b (amends the activity half of D6), SF-004 b, SF-005 a, SF-006 a, SF-007 a, SF-008 a, SF-009 a, SF-010 (approver RA or PI; criterion as stated); P1-P3 accepted. Unruled residuals kept OPEN in Q-030, Q-031, Q-032, Q-038 | Simone Paci 2026-10-27 (chat) | PI rulings 2026-10-27 | none |
| v001-draft.3 | R-1 | D-001-D-014 Resources column | Resource links from `RESOURCES.md` v001 (Stage 2); no content change | link-only | Stage 2 | none |
| v001-draft.4 | — | inputs (S3), R-016, R-025, A-008, N-005, Q-039 | PI rulings S3 from plan review: U-4 c (LLM translation for R-025, not adjudication), U-6 a (tiers 1/3 auto-accept before validation), U-3 a (RAs record source languages; multi-language counting OPEN as Q-039) | Simone Paci 2026-10-27 (chat) | Plan review PF-006, PF-007, PF-013 | none |
| v002 | SD-001 | Actors (core RA row added; Ainhoa row narrowed to Uruguay), inputs (S4), Q-037 | Ownership made RA-agnostic after the baseline lock; Ainhoa Zamora keeps Uruguay only | Simone Paci 2026-10-27 (chat) | PI instruction S4 | PLAN task owners, waves, critical path; handoffs T-011, T-022, T-031, T-037, T-047, T-048 superseded |
| v003 | SD-002 | inputs (S5), R-009 (rewritten), R-010, R-022, R-025, R-042-R-044 (new), N-005 (superseded), C-009 (new), D-008, Q-021 | jev becomes the classification engine as in the main G3O pipeline; gpt-5-nano evidence pass; procurement coding rules kept as deterministic overrides (1a); shared main-pipeline code for the applicable part of the codebook plus procurement-only extensions (2a); main-pipeline rewrite is a dependency (3) | Simone Paci 2026-10-27 (chat) | PI rulings S5 | PLAN: T-062-T-065 new; T-018 revised; T-057 superseded by T-064; T-014, T-020, T-025-T-027, T-035 changed |

## Sign-off

- Spec review: `Spec-Review.md` (2026-10-27; 13 findings; mechanical fixes applied; PI decisions applied in v001-draft.3)
- Approved by/at: Simone Paci, 2026-10-27, in chat ("APPROVED let's move to resource"), v001-draft.3; D6 reading in R-012 not corrected
- Locked by/at (Stage 6 baseline): Simone Paci, 2026-10-27T08:02-07:00 (v001-draft.4). v002 (SD-001): re-locked 2026-10-27T08:54-07:00 by Simone Paci. v003 (SD-002): re-locked 2026-10-27T09:20-07:00 by Simone Paci
- Delegated inferences accepted: none
