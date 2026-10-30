# Plan-Draft: G3O pipeline reclassification

Status: DRAFT
Version: v001-draft1
Spec: `C:/Users/spaci/repos/G3O/planning/SPEC.md` v001.2 (APPROVED, not locked)
Resources: `C:/Users/spaci/repos/G3O/planning/RESOURCES.md` v001 (APPROVED)
Protocol: `planning-implementation-map-protocol.md` v0.3 (Stage 3 of `planning-protocol.md` v0.4)
Mode: PLAN_ONLY. No task below has started. Every code change, push, paid run, DB write and deploy is a researcher gate (C-003).
Prepared by: fork of session `20261027-claude-v2-3d85fb1367912304`, model claude-opus-5-5, 2026-10-27.
Path notes: new module and file paths marked † are proposed names, not yet existing; the executing engineer confirms them in the card return, and a rename is a mechanical delta, not a spec delta.

## 0. Context and interface inventory

### 0.1 Repositories, ownership, conventions

| Surface | Location | Owner | Convention / constraint | Evidence |
|---|---|---|---|---|
| Pipeline | `C:/Users/spaci/repos/G3O`, base `origin/main` `c6349d6` (local checkout is on `perf/validate-jev-parallel`; work branches from `origin/main`) | Simone (pipeline repo) | Branch per change, PR, approving review required (memory g3o-merge-requires-approving-review); a contract bump is an instrument change; regenerate `contract_version_pin.json` once at the end of a version | RS-010, RS-017; memory contract-v2-2 |
| v2.6 instrument | ref `archive/exval-v2.6` `052fcb2` (unpushed) | — | Already uses labels extract v2.6 and validate **v1.4**; consolidation targets the retired OpenAI Stage 6 path; patch conflicts on `validate/consolidate.py` | RS-011; `git show` of both validate contracts (v1.3 on main, v1.4 on archive) |
| Backend / API | `C:/Users/spaci/repos/g3o-api`, `origin/main` `fc33ea3` | Colin (RQ-007) | SQL migrations `sql/000-020` + down; live Neon `br-wave1-cutover`; DB write needs PI sign-off | RS-020, RS-021 |
| Website | `C:/Users/spaci/repos/g3o-website`, `origin/main` `282ca6a` (re-check facts; RS-022 LISTED only) | Colin | GitHub Pages deploy; reads API (`src/data/apiClient.js`) | RS-022 |
| Procurement | `C:/Users/spaci/repos/g3o-wt-procurement/procurement/planning/` (locked plan; integrator per its DEC-009; channel per its DEC-010: email via Simone) | procurement integrator | Do not edit from here; issue G3O #134 opened 2026-10-27 | RS-029 |
| Droplet | `/home/g3o/runs` | Simone | SSH only with PI authorisation; UTC clock (memory droplet-clock); `nohup` needs `< /dev/null` | RS-007 |
| Coordination | `C:/Users/spaci/repos/ai-os-private/coord/` | — | Claims per lane; native-writer close; claude-code budget 5 slots, codex-cli 4 | coord-scan 2026-10-27 |

### 0.2 Input classification

| Needed input | Class | RS / source | Note |
|---|---|---|---|
| v2.5 contract, prompts, enums, pins | EXISTS | RS-010 | |
| v2.6 rules, evidence_review, exval fixtures (30) | EXISTS | RS-011 | port, not merge |
| Re-pilot 2 verdict wording (7 values) | EXISTS | RS-004 (SRC-7) | `confirms_absence` added from v2.5 |
| CX-01.2 frozen wording, §11.1 chunk rule, C2-C4 text | EXISTS | RS-024 | C2-C4 never run |
| WS10 D1-D6, 114-transfer list, 45 owners | EXISTS | RS-026 | list authoritative (RQ-003) |
| jev client, Stage 2/3 answer-record pattern, Stage 6 jev | EXISTS | RS-012, RS-013, RS-014 | |
| nano Batch extractor | EXISTS | RS-015 | prompt and parser change |
| Link-extraction helpers (`g3o/scrape/html.py:36`, `pdf.py:53`) | EXISTS (uncalled) | RS-016 | |
| Link following, hop counter, URL dedup, provenance chain | TO-BUILD | RS-016 (G4) | |
| Two-pass jev page/activity coder | TO-BUILD | RS-012..RS-014 | |
| Page-level chunker + combination rule | TO-BUILD | RS-004 `byte_chunks`, RS-014 split (G13) | |
| Fuzzy quote matcher | TO-BUILD | RS-011 substring check (G10) | |
| Per-row contract version | TO-BUILD | RS-017, RS-020 (G6) | |
| jev answer storage in DB | TO-BUILD | RS-013 pattern, RS-020 (G5) | |
| Correction layer + projection | TO-BUILD | RS-026 fields, RS-020 precedent (G2) | |
| Back-fill entry point (fixed list, stored pages, no re-triage) | TO-BUILD | RS-017 (G3) | |
| Fixtures for multi-activity, links, chunks, 8 verdicts, C2-C4 | TO-BUILD | RS-011, RS-019, RS-008, RS-009 (G9) | |
| Stored page text, published runs | EXTERNAL | RS-007 | droplet; UNVERIFIED layout |
| Stored-text availability, documented institutions | UNKNOWN | RS-007 | spike T-001 |
| Unclear/documented strata | EXISTS | RS-025, RS-036 | |
| Published verdicts at freeze | EXTERNAL | RS-030 | after wave 5 + deploy |
| Wave-5 run `be8a` final output | EXTERNAL | RS-032 | still running 2026-10-27 |
| jev, OpenAI Batch | EXTERNAL | RS-031 | keys; paid |
| Claude Haiku / Sonnet subagents for agent read | EXTERNAL | — | model ids fixed at T-081 |
| Live `wave_windows` state | UNKNOWN | RS-021 | R-055 makes it irrelevant for back-fill rows only |
| PI wording line-edits, labels, audits | USER-SUPPLIED | — | gates |
| Colin acceptance of D-007 | USER-SUPPLIED | RS-023 | A-019 |
| Procurement integrator acceptance of D-008 | USER-SUPPLIED | RS-029 | A-018 |

### 0.3 Spec defects found while mapping (to the integrator; no edit made)

| ID | Location | Defect | Proposed fix class |
|---|---|---|---|
| SD-a | D-002 row | Cites R-060..R-062, which do not exist in the SPEC | mechanical |
| SD-b | D-004, R-075, A-001, C-001/D-002 labels | Say "v2.6" where the label of record is v2.7 (Q-018 P4) | mechanical |
| SD-c | A-002 vs R-042 | A-002 requires a "verbatim quote present"; R-042 rules fuzzy match | substantive (A-002 wording) |
| SD-d | C-007 / R-015 | "Two contract-version steps" = extract contract + validate contract pins (memory contract-v2-2). The validate label v1.4 is already used by unpushed `052fcb2`, the same collision P4 solved for v2.6 | substantive label choice (DEC-013) |
| SD-e | Sign-off block | "Open before lock: Q-017" is stale (resolved R-086) | mechanical |
| SD-f | Q-003 superseded row, Q-014 | Blocking column says "yes" for resolved/accepted items | mechanical |
| SD-g | R-086 | Two INFERRED items added after approval (disagreement definition; proportional Sonnet draw) were not in the accepted-inference list | PI confirm (DEC-011, DEC-018) |

## 1. Decisions

`PI DECISION PENDING` = substantive or cost/risk/ownership/user-facing; options listed in §8. `MECHANICAL` = governed by project convention.

| Decision ID | Question | Chosen option | Alternatives rejected | Reason | Spec IDs | Confidence | Reversible? |
|---|---|---|---|---|---|---|---|
| DEC-001 | G2 correction layer shape | PI DECISION PENDING | — | Changes DB design, Colin's work and how history is shown | R-051, R-055, R-073, R-077, C-005 | — | costly after load |
| DEC-002 | G3 back-fill entry point | PI DECISION PENDING | — | Changes cost (re-triage) and build size | R-070..R-076 | — | yes |
| DEC-003 | G4 where link following lives | PI DECISION PENDING | — | Changes run shape, cost and stage boundaries | R-030..R-036 | — | yes, before deploy |
| DEC-004 | G5 jev answer storage | PI DECISION PENDING | — | DB size, cost and public exposure of probabilities | R-026, A-013 | — | yes, before load |
| DEC-005 | G6 per-row contract version | PI DECISION PENDING | — | Public field; schema | R-050, R-051 | — | costly after load |
| DEC-006 | G9 fixture source | PI DECISION PENDING | — | PI labelling time vs realism | A-003, A-004, A-010..A-012, A-020, A-021 | — | yes |
| DEC-007 | G10 fuzzy matcher | PI DECISION PENDING | — | New dependency vs in-house code; Q-020 metric | R-042 | — | yes |
| DEC-008 | G13 page chunker | PI DECISION PENDING | — | Chunk size changes jev cost and R-044 behaviour | R-044, C-004 | — | yes |
| DEC-009 | R-006 free-text field routing (jev Choice / deterministic / nano) | PI DECISION PENDING | — | Which fields an LLM writes is researcher scope | R-006, C-001 | — | yes |
| DEC-010 | How nano's segmentation feeds the jev second pass | PI DECISION PENDING | — | Risk that nano text steers codes (C-001) | R-003, R-004, C-001 | — | yes |
| DEC-011 | How the Sonnet 100 are drawn from the 400 | PI DECISION PENDING | — | INFERRED in R-086 after approval | R-086 | — | yes, before draw |
| DEC-012 | Plan integrator and sole CHANGELOG / delta-log writer | PI DECISION PENDING | — | Ownership | all | — | yes |
| DEC-013 | Version labels for the two pinned surfaces | PI DECISION PENDING | — | Validate v1.4 label collision (SD-d) | D-001, C-007, R-050 | — | no, once shipped |
| DEC-014 | Timing of the D-008 procurement delta | PI DECISION PENDING | — | Coordination risk vs rework | D-008, R-085, A-018 | — | yes |
| DEC-015 | API exposure of older rows | PI DECISION PENDING | — | User-facing (R-051 INFERRED to Stage 3) | R-051, D-007 | — | yes |
| DEC-016 | Supporting-text length limit | PI DECISION PENDING | — | User-facing; R-043 OPEN | R-043 | — | yes |
| DEC-017 | Unit of agreement in the agent read | PI DECISION PENDING | — | Defines "disagreement" (R-086 INFERRED) | R-082, R-083, R-086 | — | yes, before read |
| DEC-018 | Reuse of v2.6 code from `052fcb2` | PI DECISION PENDING | — | Port vs rewrite changes review burden | R-005, R-014, R-042 | — | yes |
| DEC-019 | Freeze record | MECHANICAL: integrator records freeze from public API `meta.coverage.as_of` and `total` at the deploy date, as RS-036 harvest did; snapshot file kept | DB-side query (needs credentials) | Precedent RS-025/RS-036; free GETs already authorised (G8 c) | R-070, RQ-009 | high | yes |
| DEC-020 | Branch topology | MECHANICAL: one G3O feature branch per card from `origin/main`; PRs into an integration branch `reclass/v2.7`† owned by the integrator; g3o-api/website on Colin's branches | committing on `perf/validate-jev-parallel` | Repo convention; one integrator per shared surface | C-003 | high | yes |
| DEC-021 | Pin regeneration | MECHANICAL: only T-030 regenerates `contract_version_pin.json` and `reproducibility.json`, once, at the end of the version | per-card regen | memory contract-v2-2 gate mechanics | C-007 | high | yes |
| DEC-022 | Agent-read model ids | MECHANICAL: Haiku and Sonnet ids recorded at launch of T-081 from the harness (current family: claude-haiku-5-5, claude-sonnet-5-5) | fixing ids now | R-086 says "model ids at run time" | R-086 | high | yes |

## 2. Requirement traceability

| Spec ID | Required result/test | Producer task(s) | Verifier/reviewer task(s) | Status |
|---|---|---|---|---|
| G-001 | More fields, v2.7, published | T-010..T-030, T-051..T-053, T-095 | T-096 | mapped |
| G-002 | Every code backed by text | T-022, T-024 | T-041, T-082 (A-002) | mapped |
| G-003 | Documented + unclear reclassified | T-029, T-073, T-074 | T-074 (A-005), T-096 | mapped |
| G-004 | Downstream handoff possible (non-goal delivery) | T-095 (single versioned state) | T-096 | mapped (guard N-006) |
| G-005 | CX fields produced; indices withheld | T-011, T-021, T-023 | T-095 (A-009) | mapped |
| D-001 | Contract v2.7 | T-010, T-011, T-012 | T-031, PI gate T-010 (A-001) | mapped |
| D-002 | Production pipeline | T-020..T-030 | T-031, T-041 | mapped |
| D-003 | Back-fill release | T-029, T-070, T-072..T-074 | T-074, T-082, T-096 | mapped |
| D-004 | Published data | T-051..T-053, T-095 | T-054, T-095 (A-007) | mapped |
| D-005 | Quality packet | T-080..T-083 | PI T-083 (A-008) | mapped |
| D-006 | Documentation | T-090 | PI (A-017) | mapped |
| D-007 | Interface spec handoff | T-050 | Colin acceptance (A-019) | mapped |
| D-008 | Procurement delta | T-060 | procurement integrator (A-018) | mapped |
| R-001 | jev classifies only | T-021, T-023, T-026 | T-031 (code review: no nano output read as code) | mapped |
| R-002 | Pass-1 page codes | T-011, T-021 | T-041 (A-011) | mapped |
| R-003 | Segmentation; pass-2 scope incl. 5 verdicts | T-022, T-023 | T-041 (A-003) | mapped |
| R-004 | Pass-2 activity codes | T-011, T-023 | T-041 (A-003) | mapped |
| R-005 | Consolidation v2.7 | T-026 | T-041 (A-010) | mapped |
| R-006 | Free-text routing | T-022, T-023, T-024 (DEC-009) | T-041, T-082 | mapped |
| R-010..R-014 | v2.6/WS10 rules in contract and questions | T-010, T-011, T-026 | PI gate T-010 (A-001), T-041 | mapped |
| R-015 | 8-value verdict replaces `genai_evidence` | T-010, T-012, T-028, T-051 | T-041 (A-011), T-031 | mapped |
| R-016 | GenAI wording incl. named chatbot | T-010, T-011 | T-041 (A-012) | mapped |
| R-020..R-024 | CX-01.2 fields, CX-53 emails | T-011, T-021, T-023, T-024 | T-041 (A-020) | mapped |
| R-025 | Frozen wording | T-011 | T-031 (byte diff vs RS-024) | mapped |
| R-026 | jev answer storage | T-027, T-051 | T-041/T-082 (A-013) | mapped |
| R-030 | Completeness question | T-011, T-021 | T-041 (A-004) | mapped |
| R-031..R-034 | Links to scrape, 3 hops, any link, once per URL, provenance | T-022, T-025 | T-041 (A-004) | mapped |
| R-035 | Links in back-fill | T-025, T-029 | T-074 (A-014) | mapped |
| R-036 | Back-fill fetched pages outside denominator | T-025, T-051, T-074 | T-074 (A-006 diff + denominator check) | mapped |
| R-040 | nano quotes after jev | T-022 | T-041 (A-002) | mapped |
| R-041 | Downgrade without support | T-024 | T-041, T-082 | mapped |
| R-042 | Fuzzy quote check | T-003, T-024 | T-003 PI gate (Q-020 b), T-082 (A-002) | mapped |
| R-043 | Quote published with code | T-028, T-052, T-053 (DEC-016) | T-095 (A-007) | mapped |
| R-044 | Chunk combination | T-020 | T-041 (A-021) | mapped |
| R-050 | Per-row contract version | T-028, T-051 (DEC-005) | T-095 (A-007) | mapped |
| R-051 | Row per run; site shows most recent | T-051..T-053 (DEC-001, DEC-015) | T-054, T-095 (A-007) | mapped |
| R-052 | Published via API and site | T-050, T-052, T-053 | A-019, T-095 | mapped |
| R-053 | Superseded; residual Q-021 a hide fields | T-053 | T-095 | mapped |
| R-054 | Indices withheld | T-053 (guard) | T-095 (A-009) | mapped |
| R-055 | Back-fill rows visible regardless of waves | T-051, T-052 | T-054, T-095 | mapped |
| R-070 | Back-fill set at freeze, after wave 5 | T-070 (DEC-019) | T-074 (A-005) | mapped |
| R-071 | `none` not back-filled | T-070 (filter) | T-074 | mapped |
| R-072 | Unclear in same change | T-073 | T-074 | mapped |
| R-073 | Correction layer, no overwrite | T-051, T-074 | T-074 (A-006) | mapped |
| R-074 | No text → live re-scrape; failure state | T-001, T-029 | T-074 (A-015) | mapped |
| R-075 | Exactly one end state per institution | T-029, T-074 | T-074 (A-005) | mapped |
| R-076 | Page sets per group | T-029 | T-072, T-074 | mapped |
| R-077 | 114 WS10 transfers | T-070, T-074 | T-074 (A-022), T-081 | mapped |
| R-080 | Quality bar | T-082 | T-083 (A-008) | mapped |
| R-081 | 0.8 threshold incl. negatives | T-024 | T-082 (A-016) | mapped |
| R-082 | Agent read + PI audit | T-080, T-081, T-083 | T-083 | mapped |
| R-083 | Agreement ≠ accuracy | T-082 | T-083 | mapped |
| R-084 | S5 bar replaces gold set; C2-C4 fixture | T-040, T-041 | PI (A-020) | mapped |
| R-085 | Coordinated procurement update | T-060 | A-018 | mapped |
| R-086 | 400 / Haiku all / Sonnet 100 / audit rule / release with report | T-080, T-081, T-082 | T-083 | mapped |
| R-090 | Docs | T-090 | PI (A-017) | mapped |
| A-001 | Contract text sign-off with hash | T-010 | PI | mapped |
| A-002 | Quote trace on sample | T-082 | PI | mapped (SD-c) |
| A-003 | Multi-activity fixtures | T-040, T-041 | T-041 | mapped |
| A-004 | Link fixtures | T-040, T-041 | T-041 | mapped |
| A-005 | Reconciliation count | T-074 | PI | mapped |
| A-006 | No original value changed | T-054 (rehearsal), T-074 | PI | mapped |
| A-007 | API/site visible | T-095 | PI | mapped |
| A-008 | Signed audit | T-083 | PI | mapped |
| A-009 | No index published | T-095 | agent | mapped |
| A-010 | Consolidation fixtures | T-040, T-041 | agent | mapped |
| A-011 | Verdict fixtures | T-040, T-041 | agent + PI | mapped |
| A-012 | GenAI boundary fixtures | T-040, T-041 | PI | mapped |
| A-013 | jev answer fields | T-041, T-082 | agent | mapped |
| A-014 | Followed-link provenance in back-fill | T-074 | agent | mapped |
| A-015 | No-text institutions | T-074 | PI | mapped |
| A-016 | Below-threshold counts | T-082 | PI | mapped |
| A-017 | Docs review | T-090 | PI | mapped |
| A-018 | Procurement delta accepted | T-060 | PI | mapped |
| A-019 | Colin accepts interface spec | T-050 | PI | mapped |
| A-020 | C2-C4 fixtures | T-040, T-041 | agent + PI | mapped |
| A-021 | Chunk fixtures | T-040, T-041 | agent | mapped |
| A-022 | 114 transfers in correction layer | T-074 | PI | mapped |
| C-001 | nano not a classifier | T-022, T-023 (DEC-010) | T-031 | enforced by review |
| C-002 | Paid runs signed off | gates on T-002, T-041, T-072, T-073, T-081 | integrator | gate |
| C-003 | PLAN_ONLY until lock + sign-off | all cards | integrator | gate |
| C-004 | 32k state limit | T-020 | T-041 (A-021) | enforced by test |
| C-005 | No invented search records / denominator | T-051, T-074 | T-074 denominator check | enforced by check |
| C-006 | No pilot v1 | T-040, T-080, T-082 | T-031 (grep for `pilot_v1` inputs) | enforced by review |
| C-007 | Two pinned surfaces; procurement coordinated | T-012, T-030, T-060 (DEC-013) | T-031 (pin test) | enforced by test |
| C-008 | `inputs/` read-only | all | T-031 (no write path under `inputs/`) | boundary |
| N-001 | No `none` back-fill | T-070 filter | T-074 | guard |
| N-002 | Not human validation | T-081 scope note | integrator | guard |
| N-003 | No index publication | T-053 | T-095 (A-009) | guard |
| N-004 | Stages 1-3 unchanged except link intake | T-025, T-029 | T-031 (diff scope) | guard |
| N-005 | No identity service / auto transfers | T-074 (only the 114) | T-031 | guard |
| N-006 | Kaser delivery not ours | T-095 boundary | integrator | guard |
| N-007 | No prevalence restatement | T-082, T-090 boundary | integrator | guard |

## 3. Task cards

### Shared contract for every card (referenced as "Std")

- **Spec-change reporting (Std):** Spec version SPEC v001.2 → the Stage 6 locked version once locked. Report to the plan integrator (DEC-012) by coord mailbox; Simone approves every delta. Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md`.
- **Return report (Std):** changed files; each check with evidence; failures; blockers; unresolved decisions; proposed status `verified` or `blocked`. Sent to the integrator, who alone marks `complete`.
- **Gate rule (Std):** any push, paid call, DB write, deploy, SSH or external message inside a card needs its named researcher gate passed first (C-003).

### T-001 — Count stored-text availability for documented institutions (SPIKE)
Status: blocked (BLOCKED-INPUT: PI authorisation for read-only droplet SSH) · Type: spike · Priority: required · Spec: R-074, R-076, A-015 · DEC: —
**Objective:** counts of pages / pages with ≥200 chars text / raw `%PDF` per documented institution (latest run), and whether RS-006 scratch files still exist.
**Inputs:** | RS-004 `enumerate.py`, `count_pages.py` | Drive | as of 2026-10-27 | stop | · | RS-025 documented list | Drive | parsed | stop | · | RS-007 runs | droplet | read-only | report UNVERIFIED |
**Outputs:** | `count-documented.json`, `SPIKE-T001.md` | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/spikes/`† | T-029, T-072 | per-uid counts + totals; script hash |
**Resources:** researcher/engineer lane; Bash + SSH (`id_ed25519_g3o`); no skill beyond this plan; droplet home dir scratch.
**Dependencies:** Requires none · Enables T-029, T-072 · Can run with T-002, T-010, T-020 · Researcher gates: PI authorises SSH read.
**Ownership:** Read RS-007; Write the spikes folder + droplet `~/reclass-spike-*/`; Shared none.
**Boundary:** Included enumeration only. Excluded fetching, any run, DB. Fixed R-076 page sets.
**Spec-change reporting:** Std. Report when text missing for >5% of documented (changes R-074 load). Stop: nothing else. Continue: all.
**Verification:** self: totals reconcile with RS-025 count (9,705); independent: integrator re-runs on 20 uids; A: feeds A-015; rollback: delete scratch.
**Return report:** Std. **Done:** counts file + reconciliation note. **Chunking trigger:** runtime >2 h → split by run.

### T-002 — Measure jev two-pass cost and latency on a small set (SPIKE)
Status: blocked (gate: paid jev + nano calls) · Type: spike · Priority: critical-path · Spec: R-002..R-004, R-044, C-002, C-004 · DEC: informs DEC-002, DEC-003, DEC-008, DEC-010
**Objective:** per-page and per-activity jev call counts, tokens, latency and failure rate for pass 1 + segmentation + pass 2 on ≤50 real pages, using proxy questions (re-pilot 2 + CX pilot v2).
**Inputs:** | RS-004 `unclear2.py` | Drive | — | stop | · | RS-024 `pilot/pilot.py` | Drive | — | stop | · | RS-009 / RS-008 pages | local | — | stop | · | RS-031 keys | env | valid | stop |
**Outputs:** | `SPIKE-T002.md` + raw answers jsonl | spikes folder† | DEC-002/003/008/010, T-003, risk register | cost per 1k pages, p50/p95 latency, chunk counts |
**Resources:** engineer; Python, jev client RS-012, OpenAI Batch or sync; `claude-api` skill not applicable (OpenAI/jev).
**Dependencies:** Requires none · Enables T-003, T-021 · Can run with T-001, T-010, T-020 · Researcher gates: PI approves paid spike budget.
**Ownership:** Read RS-004, RS-008, RS-009, RS-024; Write spikes folder; Shared none.
**Boundary:** Included measurement. Excluded any coding rule choice. Fixed: proxy questions are not v2.7.
**Spec-change reporting:** Std. Report when cost or latency makes R-086/R-073 scale infeasible, or jev cannot take segmented context. Stop: T-021 design. Continue: T-010, T-020.
**Verification:** self: call counts match page count × passes; independent: integrator spot-checks 5 request ids; rollback: none needed.
**Return report:** Std. **Done:** report with numbers and raw logs. **Chunking trigger:** >50 pages requested → new gate.

### T-003 — Calibrate the fuzzy quote matcher (SPIKE, Q-020 b)
Status: pending · Type: spike · Priority: critical-path · Spec: R-042, A-002 · DEC: DEC-007
**Objective:** metric and threshold for quote-vs-page matching, with false-match / false-reject rates on labelled pairs incl. non-English pages; PI approves.
**Inputs:** | T-002 quotes | spikes folder | done | stop | · | RS-011 `check_quotes` | ref 052fcb2 | — | baseline | · | RS-009 pages (43+ languages via RS-025 mix) | local | — | stop |
**Outputs:** | `SPIKE-T003.md`, labelled pairs csv | spikes folder† | T-024 | metric, threshold, error table by language |
**Resources:** engineer; Python (library per DEC-007).
**Dependencies:** Requires T-002 · Enables T-024 · Can run with T-011, T-012 · Researcher gates: PI approves metric + threshold (Q-020 b).
**Ownership:** Read as inputs; Write spikes folder; Shared none.
**Boundary:** Included calibration. Excluded entailment checking (R-042 presence only).
**Spec-change reporting:** Std. Report when no threshold separates true/false matches for some script (e.g. CJK). Stop: T-024. Continue: others.
**Verification:** self: hold-out split; independent: PI labels 30 pairs; rollback: n/a.
**Return report:** Std. **Done:** PI-approved threshold recorded. **Chunking trigger:** >1 day labelling.

### T-010 — Draft Output Contract v2.7 and the validate-contract bump
Status: pending · Type: build · Priority: critical-path · Spec: D-001, R-010..R-016, R-020..R-025, R-030, R-040, R-041, R-044, R-050, C-007, A-001 · DEC: DEC-013, DEC-016
**Objective:** PI-signed v2.7 extract contract + system prompt + validate contract text, with hash.
**Inputs:** | RS-010 v2.5 docs | origin/main | c6349d6 | stop | · | RS-011 v2.6 rulings | 052fcb2 | — | stop | · | RS-004 re-pilot wording | Drive | — | stop | · | RS-024 CX-01.2 | Drive | frozen | stop | · | RS-026 WS10 D1-D6 | Drive | — | stop |
**Outputs:** | `g3o/extract/prompts/output_contract.md`, `g3o/extract/prompts/system_prompt.md`, `g3o/validate/prompts/output_contract.md` | branch `reclass/t010-contract`† | T-011, T-012, T-040, T-050, T-060, T-090 | every rule in A-001 present; 8-value verdict (R-015); labels per DEC-013 |
**Resources:** researcher (structure, cross-refs) + PI (all coding-rule wording; researcher persona does no prose drafting); `planning-output-specification-protocol.md` for ID tagging.
**Dependencies:** Requires none · Enables T-011, T-012, T-040, T-050, T-060, T-090 · Can run with T-001, T-002, T-020 · Researcher gates: PI writes/line-edits every coding rule; PI signs text hash (A-001); push gate.
**Ownership:** Read inputs; Write the three contract files only; Shared contract docs — owner T-010 until signed, then frozen (changes via delta).
**Boundary:** Included contract text. Excluded enums in code (T-012), jev questions (T-011). Fixed all SPEC rulings.
**Spec-change reporting:** Std. Report when a ruling cannot be written without contradicting another (e.g. R-014 vs R-041). Stop: T-011, T-012. Continue: T-020, spikes.
**Verification:** self: checklist R-010..R-044 → section anchors; independent: T-031 reviewer cross-check; A-001; rollback: branch only.
**Return report:** Std. **Done:** signed hash recorded by integrator. **Chunking trigger:** split extract vs validate contract if review rounds >2.

### T-011 — Build the v2.7 jev question sets (pass 1, pass 2, Stage 6)
Status: pending · Type: build · Priority: critical-path · Spec: R-002, R-004, R-005, R-015, R-016, R-020..R-025, R-030, G-005 · DEC: DEC-009, DEC-010
**Objective:** versioned jev question/choice sets implementing the signed contract; CX-01.2 wording byte-identical to RS-024.
**Inputs:** | T-010 signed contract | branch | signed | stop | · | RS-024 frozen wording | Drive | frozen | stop | · | RS-013 question-set pattern | origin/main | — | follow |
**Outputs:** | `g3o/classify/questions/v27/{page,activity,institution}.json`† + `JEV_QUESTION_SET_VERSION` | branch `reclass/t011-questions`† | T-021, T-023, T-026, T-040 | each question cites contract section; version stamped |
**Resources:** engineer + researcher review; Python.
**Dependencies:** Requires T-010 · Enables T-021, T-023, T-026 · Can run with T-012, T-003, T-040 · Researcher gates: PI approves question wording that is not verbatim contract/CX text.
**Ownership:** Read T-010, RS-024; Write `g3o/classify/questions/v27/`†; Shared none.
**Boundary:** Included question text + choice sets. Excluded stage code. Fixed R-025 frozen wording.
**Spec-change reporting:** Std. Report when a contract field has no closed choice set (affects DEC-009). Stop: affected question. Continue: others.
**Verification:** self: diff CX questions vs RS-024 (empty); schema validation; independent: T-031; A-011, A-012 via T-041; rollback: branch.
**Return report:** Std. **Done:** sets merged to `reclass/v2.7`† with version. **Chunking trigger:** split per pass.

### T-012 — Update enums, schema and contract constants in code
Status: pending · Type: build · Priority: critical-path · Spec: R-015, R-020..R-024, R-050, C-007 · DEC: DEC-005, DEC-013
**Objective:** `contract.py`/`schema.py` carry the 8-value page verdict replacing `genai_evidence`, new CX columns, contract-version field; both enum copies (incl. NoNA variants) updated.
**Inputs:** | T-010 signed contract | branch | signed | stop | · | RS-010 code | origin/main | c6349d6 | stop |
**Outputs:** | `g3o/common/contract.py`, `g3o/common/schema.py`, `tests/test_schema_consistency.py` updates | branch `reclass/t012-enums`† | T-021..T-028, T-050, T-051 | old v2.5 rows still validate (keep 4-value under version guard) |
**Resources:** engineer; pytest.
**Dependencies:** Requires T-010 · Enables T-021, T-022, T-024, T-026, T-027, T-028, T-050 · Can run with T-011, T-003 · Researcher gates: none beyond push.
**Ownership:** Read RS-010; Write the two modules + schema test; Shared `contract.py` — sole owner T-012.
**Boundary:** Included constants/types. Excluded pin regen (T-030, DEC-021). Fixed R-015 mapping: v2.5 rows unconverted.
**Spec-change reporting:** Std. Report when an enum appears in a surface not listed (memory: 7 touchpoints). Stop: none. Continue: all.
**Verification:** self: `git grep` all enum touchpoints; pytest schema tests; independent: T-031; rollback: branch.
**Return report:** Std. **Done:** tests pass; touchpoint list attached. **Chunking trigger:** none.

### T-020 — Build the page chunker and combination rule
Status: pending · Type: build · Priority: required · Spec: R-044, C-004, A-021 · DEC: DEC-008
**Objective:** chunk pages to the jev state limit and combine chunk answers per CX-01.2 §11.1, recording which chunk produced each code.
**Inputs:** | RS-004 `byte_chunks` | Drive | — | port | · | RS-014 split logic | origin/main | — | alt | · | RS-024 §11.1 (L184) | Drive | frozen | stop |
**Outputs:** | `g3o/common/page_chunks.py`†, `tests/test_page_chunks.py`† | branch `reclass/t020-chunks`† | T-021, T-023 | deterministic; chunk ids carried |
**Resources:** engineer; pytest.
**Dependencies:** Requires none (DEC-008 decided) · Enables T-021, T-023 · Can run with T-010, T-001, T-002 · Researcher gates: none beyond push.
**Ownership:** Write the two new files; Shared none.
**Boundary:** Included chunking + combination. Excluded jev calls.
**Spec-change reporting:** Std. Report when §11.1 is ambiguous for a field type. Stop: that field. Continue: rest.
**Verification:** self: unit tests on ordered vocab, yes/no, page fields; independent: T-031; A-021 via T-041; rollback: branch.
**Return report:** Std. **Done:** tests pass. **Chunking trigger:** none.

### T-021 — Build the jev pass-1 page coder stage
Status: pending · Type: build · Priority: critical-path · Spec: R-001, R-002, R-015, R-020, R-021, R-023, R-026, R-030, R-081 · DEC: DEC-004
**Objective:** stage that sends each page (chunked) to jev with the page question set and records answers with probabilities, confidence, model and request ids; applies 0.8 threshold flags.
**Inputs:** | T-011 page set | branch | merged | stop | · | T-012 enums | branch | merged | stop | · | T-020 chunker | branch | merged | stop | · | T-027 record module | branch | merged | stop | · | T-002 numbers | spikes | done | proceed w/ defaults |
**Outputs:** | `g3o/classify/jev_page_code.py`†, `g3o/run/presweep/stage_page_code.py`†, tests | branch `reclass/t021-pass1`† | T-022, T-023, T-025, T-030 | per-page artifact with completeness flag |
**Resources:** engineer; jev client RS-012; pytest with mocks (RS-019 pattern).
**Dependencies:** Requires T-011, T-012, T-020, T-027, T-002 · Enables T-022 (verdict gating), T-023, T-025 · Can run with T-024 · Researcher gates: none beyond push.
**Ownership:** Write the new modules + tests; Shared orchestrator wiring → T-030.
**Boundary:** Included stage module. Excluded orchestrator edits.
**Spec-change reporting:** Std. Report when jev rejects a question shape. Stop: T-023. Continue: T-024, T-025 mocks.
**Verification:** self: mocked tests for threshold + chunking; independent: T-031; A-011, A-013 via T-041; rollback: branch.
**Return report:** Std. **Done:** tests pass. **Chunking trigger:** >1 week → split CX fields from verdict.

### T-022 — Rework the nano extraction call (segmentation, quotes, links, residual free text)
Status: pending · Type: build · Priority: critical-path · Spec: R-001, R-003, R-006, R-031, R-040, C-001 · DEC: DEC-009, DEC-010, DEC-016
**Objective:** one nano Batch call per page after pass 1 returning: activity segments, verbatim quote per jev code, follow-up links (Q-018 P5), and free-text fields routed to nano under DEC-009. Runs only on the 5 verdicts in R-003.
**Inputs:** | RS-015 batch/client/parser/salvage | origin/main | — | stop | · | T-012 enums | merged | stop | · | T-021 artifact shape | merged | mock | · | T-010 contract | signed | stop |
**Outputs:** | `g3o/extract/{batch,client,parser,salvage}.py`, `g3o/extract/prompts/extract_v27.md`†, `g3o/run/presweep/stage_extract.py` | branch `reclass/t022-nano`† | T-023, T-024, T-025 | output never carries a code field (C-001) |
**Resources:** engineer; OpenAI Batch client RS-015.
**Dependencies:** Requires T-010, T-012 · Enables T-023, T-024, T-025 · Can run with T-021 (against mocked artifact) · Researcher gates: PI approves nano prompt text.
**Ownership:** Write the listed extract files; Shared `stage_extract.py` — sole owner T-022.
**Boundary:** Included extraction. Excluded quote verification (T-024). Fixed C-001.
**Spec-change reporting:** Std. Report when `cap_page_text` 60k truncation conflicts with full-page quotes. Stop: T-024. Continue: T-023 mocks.
**Verification:** self: parser tests; grep that no code value is parsed from nano; independent: T-031; rollback: branch.
**Return report:** Std. **Done:** tests pass; prompt approved. **Chunking trigger:** split links from quotes if parser >1 week.

### T-023 — Build the jev pass-2 activity coder
Status: pending · Type: build · Priority: critical-path · Spec: R-001, R-003, R-004, R-006, R-022, R-026 · DEC: DEC-009, DEC-010
**Objective:** per (page × activity) jev coding of Group D enums/flags under v2.6 rules and CX-01.2 finding fields, with the activity as context per DEC-010.
**Inputs:** | T-011 activity set | merged | stop | · | T-021 page artifact | merged | stop | · | T-022 segments | merged | stop | · | T-020, T-027 | merged | stop |
**Outputs:** | `g3o/classify/jev_activity_code.py`†, `g3o/run/presweep/stage_activity_code.py`†, tests | branch `reclass/t023-pass2`† | T-026, T-024 | one record per activity, linked to page + segment |
**Resources:** engineer; jev client.
**Dependencies:** Requires T-011, T-021, T-022, T-020, T-027 · Enables T-026 · Can run with T-025 · Researcher gates: none beyond push.
**Ownership:** Write new modules; Shared orchestrator → T-030.
**Boundary:** Included pass 2. Excluded consolidation.
**Spec-change reporting:** Std. Report when activity context exceeds state limit after chunking. Stop: affected pages. Continue: rest.
**Verification:** self: mocked multi-activity tests; independent: T-031; A-003 via T-041; rollback: branch.
**Return report:** Std. **Done:** tests pass. **Chunking trigger:** split CX finding fields from Group D.

### T-024 — Build support check, downgrade and deterministic extraction
Status: pending · Type: build · Priority: critical-path · Spec: R-006, R-023 (CX-53), R-040, R-041, R-042, R-081, G-002 · DEC: DEC-007, DEC-016
**Objective:** module that fuzzy-matches each quote (T-003 threshold), downgrades unsupported positive/substantive codes and codes <0.8 (incl. negatives → `unclear`/`unknown`), and runs deterministic extraction (emails when contact = yes; other DEC-009 deterministic fields).
**Inputs:** | T-003 approved threshold | spikes | approved | stop | · | T-022 quotes | merged | stop | · | T-012 enums | merged | stop |
**Outputs:** | `g3o/common/support_check.py`†, tests | branch `reclass/t024-support`† | T-026, T-028 | each downgrade records reason (`no_quote`, `low_confidence`) |
**Resources:** engineer; matcher per DEC-007.
**Dependencies:** Requires T-003, T-022, T-012 · Enables T-026, T-028 · Can run with T-021, T-023 · Researcher gates: none beyond push.
**Ownership:** Write new module; Shared none.
**Boundary:** Included check + downgrade + deterministic fields. Excluded threshold choice.
**Spec-change reporting:** Std. Report when a field has no defined no-evidence value. Stop: that field. Continue: rest.
**Verification:** self: tests per R-041 value list (Q-010 a), negative <0.8 case; independent: T-031; A-016 via T-082; rollback: branch.
**Return report:** Std. **Done:** tests pass. **Chunking trigger:** none.

### T-025 — Build link following (3 hops, once per URL, provenance)
Status: pending · Type: build · Priority: required · Spec: R-030..R-036, N-004, SC-03 · DEC: DEC-003
**Objective:** links from incomplete pages re-enter scraping and classification up to 3 hops; each URL fetched once per institution per run; provenance chain stored; back-fill fetches tagged per R-036.
**Inputs:** | RS-016 scrape + `extract_links` | origin/main | — | reuse | · | T-021 completeness flag | merged | stop | · | T-022 links | merged | stop |
**Outputs:** | `g3o/scrape/follow.py`†, `g3o/run/presweep/stage_follow.py`† (or scrape-stage hook per DEC-003), tests | branch `reclass/t025-links`† | T-029, T-030 | provenance fields: origin page, hop, fetch date, release id |
**Resources:** engineer; existing fetcher/politeness.
**Dependencies:** Requires T-021, T-022 · Enables T-029, T-030 · Can run with T-023, T-024 · Researcher gates: none beyond push.
**Ownership:** Write new modules; Shared `stage_scrape.py` only if DEC-003 a → then sole owner T-025.
**Boundary:** Included following. Excluded discovery/site-pick/triage (N-004).
**Spec-change reporting:** Std. Report when robots/politeness blocks a large share of cited links. Stop: none. Continue: all.
**Verification:** self: loop/dedup/hop tests (A-004); independent: T-031; rollback: feature flag off.
**Return report:** Std. **Done:** tests pass. **Chunking trigger:** split back-fill tagging.

### T-026 — Port v2.6 consolidation into jev Stage 6
Status: pending · Type: build · Priority: critical-path · Spec: R-005, R-012, R-014, R-015, R-081, A-010 · DEC: DEC-018
**Objective:** Stage 6 applies v2.6/v2.7 consolidation (explicit relations, no merge of unresolved, `no` rule per SF-009 b) on the new page/activity records.
**Inputs:** | RS-011 evidence_review + rules | 052fcb2 | — | port | · | RS-014 Stage 6 jev | origin/main | — | stop | · | T-011 institution set, T-023, T-024, T-027 | merged | stop |
**Outputs:** | `g3o/validate/jev_validate.py`, `g3o/run/presweep/stage_validate.py`, `g3o/common/evidence_review.py`† (ported), tests | branch `reclass/t026-stage6`† | T-028 | institution verdict + dispositions; question-set version stamped |
**Resources:** engineer.
**Dependencies:** Requires T-011, T-012, T-023, T-024, T-027 · Enables T-028 · Can run with T-025 · Researcher gates: none beyond push.
**Ownership:** Write listed files; Shared Stage 6 — sole owner T-026.
**Boundary:** Included consolidation. Excluded the retired OpenAI path.
**Spec-change reporting:** Std. Report when a v2.6 rule depends on removed fields. Stop: that rule. Continue: rest.
**Verification:** self: exval_cases (30) adapted + A-010 fixtures; independent: T-031; rollback: branch.
**Return report:** Std. **Done:** tests pass. **Chunking trigger:** split `no` rule from merge rules.

### T-027 — Build the shared jev answer record
Status: pending · Type: build · Priority: critical-path · Spec: R-026, A-013 · DEC: DEC-004
**Objective:** one record type for every jev answer (distribution, confidence, model id, request id, question-set version, chunk id) used by T-021, T-023, T-026 and written to artifacts (DB per DEC-004 via T-051/T-052).
**Inputs:** | RS-012, RS-013 pattern | origin/main | — | follow | · | T-012 | merged | stop |
**Outputs:** | `g3o/common/jev_record.py`†, tests | branch `reclass/t027-record`† | T-021, T-023, T-026, T-028, T-050 | fixes RS-014 gap (first-chunk ids only) |
**Resources:** engineer.
**Dependencies:** Requires T-012 · Enables T-021, T-023, T-026 · Can run with T-022, T-050 · Researcher gates: none.
**Ownership:** Write new module; Shared none.
**Boundary:** Included record + serialisation. Excluded DB columns (T-051).
**Spec-change reporting:** Std. Report when jev returns no distribution for a question type. Stop: none. Continue: all.
**Verification:** self: round-trip tests; independent: T-031; rollback: branch.
**Return report:** Std. **Done:** tests pass. **Chunking trigger:** none.

### T-028 — Update the Stage 7 writer for v2.7 rows
Status: pending · Type: build · Priority: critical-path · Spec: R-015, R-043, R-050, R-051 · DEC: DEC-005, DEC-016
**Objective:** CSV writer emits page-verdict, CX fields, supporting text, jev summary fields and per-row contract version (DEC-005).
**Inputs:** | RS-018 writer | origin/main | — | stop | · | T-012, T-024, T-026, T-027 | merged | stop |
**Outputs:** | `g3o/persist/writer.py`, tests | branch `reclass/t028-writer`† | T-029, T-030, T-051/T-052 (ingest) | column list matches T-050 spec |
**Resources:** engineer.
**Dependencies:** Requires T-012, T-024, T-026, T-027 · Enables T-030, T-052, T-090 · Can run with T-051 · Researcher gates: none.
**Ownership:** Write writer + tests; Shared CSV layout — agreed with T-050 (integrator T-030).
**Boundary:** Included writer. Excluded DB ingest.
**Spec-change reporting:** Std. Report when a field has no CSV home. Stop: none. Continue: all.
**Verification:** self: golden CSV for 3 fixture institutions; independent: T-031; rollback: branch.
**Return report:** Std. **Done:** tests pass. **Chunking trigger:** none.

### T-029 — Build the back-fill entry point
Status: pending · Type: build · Priority: critical-path · Spec: R-035, R-036, R-070..R-077, A-005, A-015 · DEC: DEC-002
**Objective:** run v2.7 stages for a fixed institution list from stored pages (per R-076 page sets), re-scraping no-text pages, following links, with no re-triage, and an end state per institution (R-075).
**Inputs:** | RS-017 runner/resume | origin/main | — | reuse | · | T-030 integrated pipeline | `reclass/v2.7` | green | stop | · | T-025 | merged | stop | · | T-001 counts | spikes | done | proceed, report |
**Outputs:** | `g3o/run/backfill/`†, `g3o/cli.py` subcommand | branch `reclass/t029-backfill`† | T-041, T-072, T-073 | named failure states enumerated |
**Resources:** engineer.
**Dependencies:** Requires T-030, T-025, T-001 · Enables T-031, T-041, T-072 · Can run with T-090 · Researcher gates: none beyond push.
**Ownership:** Write new package + cli hunk; Shared `cli.py` — integrator T-030 merges.
**Boundary:** Included entry point. Excluded Stages 1-3 (N-004), `none` institutions (N-001).
**Spec-change reporting:** Std. Report when stored text is missing far above T-001 counts. Stop: none. Continue: all.
**Verification:** self: mocked back-fill of 5 institutions incl. no-text + PDF; independent: T-031; rollback: branch.
**Return report:** Std. **Done:** tests pass. **Chunking trigger:** split re-scrape path.

### T-030 — Integrate the v2.7 pipeline (integrator task)
Status: pending · Type: integrate · Priority: critical-path · Spec: D-002, R-050, C-007 · DEC: DEC-020, DEC-021
**Objective:** wire new stages into the orchestrator/config/telemetry; merge card branches into `reclass/v2.7`†; regenerate pins once; mocked e2e green.
**Inputs:** | T-021..T-028 branches | merged-ready | stop |
**Outputs:** | `g3o/run/presweep/{orchestrator,config}.py`, `g3o/run/telemetry.py`, `tests/goldens/{contract_version_pin,reproducibility}.json`, `tests/test_e2e_presweep_smoke.py` | `reclass/v2.7`† | T-029, T-031, T-041 | e2e green; pins match DEC-013 labels |
**Resources:** engineer (integrator lane); pytest.
**Dependencies:** Requires T-021, T-022, T-023, T-024, T-025, T-026, T-027, T-028 · Enables T-029, T-031, T-041 · Can run with T-090 · Researcher gates: push of integration branch.
**Ownership:** Write listed files; Shared orchestrator, pins — sole owner.
**Boundary:** Included wiring. Excluded stage logic changes (send back to card).
**Spec-change reporting:** Std. Report when stage order conflicts with R-040 "after jev". Stop: e2e. Continue: T-090.
**Verification:** self: full test suite; independent: T-031; rollback: revert merge commits.
**Return report:** Std. **Done:** suite green on `reclass/v2.7`. **Chunking trigger:** none.

### T-031 — Independent code and contract review
Status: pending · Type: verify · Priority: critical-path · Spec: R-001, R-025, C-001, C-006, C-007, C-008, N-004, N-005 · DEC: —
**Objective:** reviewer not involved in T-010..T-030 checks the integrated branch against SPEC and contract.
**Inputs:** | `reclass/v2.7` + T-029 | branch | green | stop |
**Outputs:** | `Code-Review-T031.md` | `C:/Users/spaci/repos/G3O/planning/reviews/`† | integrator, PI | findings ranked; each with file:line |
**Resources:** fresh reviewer session; `planning-adversarial-review-protocol.md`; `/code-review` skill.
**Dependencies:** Requires T-029, T-030 · Enables T-071 · Can run with T-041 · Researcher gates: none.
**Ownership:** Read all; Write review file only; Shared none.
**Boundary:** Included review. Excluded fixes.
**Spec-change reporting:** Std. Report spec conflicts found. Stop: none. Continue: all.
**Verification:** checklist: no nano code fields; CX byte-diff; pin test; no `pilot_v1`/`inputs/` writes; Stage 1-3 diff empty except link intake.
**Return report:** Std. **Done:** review filed; criticals closed. **Chunking trigger:** split pipeline vs contract review.

### T-040 — Build the v2.7 fixture set
Status: pending · Type: build · Priority: critical-path · Spec: A-003, A-004, A-010, A-011, A-012, A-020, A-021, R-084, C-006 · DEC: DEC-006
**Objective:** labelled fixtures: multi-activity, incomplete/link chains, chunked pages, all 8 verdicts, GenAI boundary, C2-C4, consolidation cases.
**Inputs:** | RS-011 exval_cases (30) | 052fcb2 | — | adapt | · | RS-005 answers, RS-024 readcheck40 | Drive | — | mine | · | RS-008/RS-009 pages | local | — | mine | · | T-010 | signed | stop |
**Outputs:** | `tests/fixtures/v27/`† + label sheet | branch `reclass/t040-fixtures`† | T-041 | each fixture: expected value + PI label ref |
**Resources:** researcher + engineer; PI labelling.
**Dependencies:** Requires T-010 · Enables T-041 · Can run with T-011, T-012, T-020 · Researcher gates: PI labels/approves expected values.
**Ownership:** Write fixtures dir; Shared none.
**Boundary:** Included fixtures. Excluded pilot v1 (C-006).
**Spec-change reporting:** Std. Report when a case has no defined expected value under the contract. Stop: that case. Continue: rest.
**Verification:** self: every A-ID has ≥3 fixtures; independent: PI; rollback: branch.
**Return report:** Std. **Done:** PI-approved labels. **Chunking trigger:** split per A-ID.

### T-041 — Run the fixtures on the integrated pipeline (paid, small)
Status: blocked (gate: paid jev + nano) · Type: verify · Priority: critical-path · Spec: A-003, A-004, A-010..A-013, A-020, A-021, R-084 · DEC: —
**Objective:** real jev/nano run of T-040 fixtures through `reclass/v2.7` incl. back-fill path; pass/fail per A-ID.
**Inputs:** | T-029, T-030 | green | stop | · | T-040 | approved | stop | · | T-024 | merged | stop |
**Outputs:** | `fixture-run/` results + `T041-REPORT.md` | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/fixture-run/`† | T-071, PI | per-fixture expected vs got |
**Resources:** engineer; jev + OpenAI keys.
**Dependencies:** Requires T-029, T-030, T-040, T-024 · Enables T-071 · Can run with T-031 · Researcher gates: PI approves paid fixture run; PI rules on fixture failures.
**Ownership:** Write fixture-run folder; Shared none.
**Boundary:** Included run + report. Excluded fixing (back to cards).
**Spec-change reporting:** Std. Report systematic failures tracing to contract wording. Stop: T-071. Continue: T-090, T-050.
**Verification:** self: all A-IDs reported; independent: PI reads failures; rollback: n/a.
**Return report:** Std. **Done:** all fixtures pass or PI-ruled. **Chunking trigger:** >1 rerun cycle → new card.

### T-050 — Write the D-007 interface specification for Colin
Status: pending · Type: document · Priority: critical-path · Spec: D-007, R-043, R-050..R-055, A-019 · DEC: DEC-001, DEC-004, DEC-005, DEC-015, DEC-016
**Objective:** exact fields, types, version display, most-recent rule, hidden-fields rule (Q-021 a), back-fill visibility (R-055), correction-layer interface.
**Inputs:** | T-010, T-012 | signed/merged | stop | · | RS-020, RS-023 | repo/Drive | — | stop | · | T-027 record | merged | stop |
**Outputs:** | `C:/Users/spaci/repos/G3O/planning/handoffs/D-007-interface-spec.md`† | Colin, T-051..T-053, T-028 | acceptance block for A-019 |
**Resources:** researcher/engineer; email to Colin is an external message (gate).
**Dependencies:** Requires T-010, T-012, T-027 · Enables T-051, T-028 (column agreement) · Can run with T-022 · Researcher gates: PI approves spec before sending; sending is an external message.
**Ownership:** Write handoff file; Shared CSV/API field list — integrator T-030 + Colin.
**Boundary:** Included spec. Excluded API/site code.
**Spec-change reporting:** Std. Report when Colin rejects a field or shape. Stop: T-051. Continue: pipeline cards.
**Verification:** self: every published field in T-028 appears; independent: Colin; A-019; rollback: n/a.
**Return report:** Std. **Done:** Colin acceptance recorded. **Chunking trigger:** none.

### T-051 — g3o-api migration: correction layer, per-row version, jev fields, page verdict
Status: pending · Type: migrate · Priority: critical-path · Spec: R-015, R-026, R-036, R-050, R-051, R-055, R-073, C-005 · DEC: DEC-001, DEC-004, DEC-005
**Objective:** forward + down migrations implementing T-050.
**Inputs:** | T-050 accepted | handoffs | accepted | stop | · | RS-020 schema | g3o-api fc33ea3 | — | stop |
**Outputs:** | `g3o-api/sql/021_reclass_v27.sql`† + `down/` | Colin's branch | T-052, T-054, T-074 | no ALTER of original values; added columns nullable |
**Resources:** Colin (owner) or engineer with Colin review.
**Dependencies:** Requires T-050 · Enables T-052, T-054 · Can run with pipeline cards · Researcher gates: none until applied (apply = T-054/T-074 gates).
**Ownership:** Write `sql/021*`; Shared DB schema — sole owner Colin.
**Boundary:** Included DDL. Excluded data load.
**Spec-change reporting:** Std. Report when R-073 no-overwrite conflicts with existing triggers/views. Stop: T-052. Continue: others.
**Verification:** self: apply/down on disposable branch; independent: T-054; rollback: down migration.
**Return report:** Std. **Done:** migration reviewed. **Chunking trigger:** split correction layer from new columns.

### T-052 — g3o-api ingest and endpoints for v2.7
Status: pending · Type: build · Priority: critical-path · Spec: R-043, R-050..R-052, R-055, DEC-015 · DEC: DEC-015
**Objective:** ingest reads T-028 CSVs; API serves v2.7 fields, version label, most-recent selection, older rows per DEC-015, back-fill rows outside wave gating.
**Inputs:** | T-051 | reviewed | stop | · | T-028 golden CSVs | merged | stop |
**Outputs:** | `scripts/ingest.py`, `worker/src/index.js`, `schema/schema_core.sql` | Colin's branch | T-053, T-054, T-074 | API contract doc updated (RS-023) |
**Resources:** Colin.
**Dependencies:** Requires T-051, T-028 · Enables T-053, T-054, T-074 · Can run with T-030, T-090 · Researcher gates: deploy gate.
**Ownership:** Colin's files; Shared API contract — Colin.
**Boundary:** Included API. Excluded index endpoints (N-003).
**Spec-change reporting:** Std. Report when most-recent selection conflicts with wave logic. Stop: T-053. Continue: others.
**Verification:** self: `verify_api.py`; independent: T-054; rollback: worker revert.
**Return report:** Std. **Done:** staging API passes checks. **Chunking trigger:** split ingest vs worker.

### T-053 — Website changes for v2.7
Status: pending · Type: build · Priority: required · Spec: R-043, R-051, R-052, R-053 residual (Q-021 a), R-054, N-003 · DEC: DEC-015, DEC-016
**Objective:** show most-recent row with version label, new fields and quotes; hide new fields where latest row is v2.5; no index UI.
**Inputs:** | T-052 staging API | staged | stub | · | RS-022 site | `282ca6a` | re-check | stop |
**Outputs:** | `src/pages/Institution.jsx`, `src/data/vocabulary.js`, `src/copy.js`, tests | Colin's branch | T-095 | copy strings PI-approved |
**Resources:** Colin; site copy is public wording (PI gate).
**Dependencies:** Requires T-052 · Enables T-095 · Can run with T-029 · Researcher gates: PI approves public copy; deploy gate.
**Ownership:** Colin's files.
**Boundary:** Included UI. Excluded indices.
**Spec-change reporting:** Std. Report when hiding fields conflicts with existing layout. Continue: all.
**Verification:** self: site tests; independent: T-095 (A-007); rollback: Pages revert.
**Return report:** Std. **Done:** staging site reviewed. **Chunking trigger:** none.

### T-054 — Rehearse migration, load and rollback on a disposable DB branch
Status: blocked (gate: Neon branch creation + writes) · Type: verify · Priority: critical-path · Spec: A-006, R-055, R-073, C-005 · DEC: DEC-001
**Objective:** apply T-051, ingest T-041 output, check no original value changed, run down migration, record timings.
**Inputs:** | T-051, T-052 | reviewed | stop | · | T-041 outputs | done | stop |
**Outputs:** | `rehearsal/T054-REPORT.md` | `agent-workspace/2026-10-27-reclass-plan/rehearsal/`† | T-071, T-074 | diff empty on original columns; down restores |
**Resources:** engineer with Colin; Neon access (memory g3o-access-surfaces).
**Dependencies:** Requires T-051, T-052, T-041 · Enables T-071, T-074 · Can run with T-031 · Researcher gates: PI authorises disposable-branch writes.
**Ownership:** Disposable Neon branch only.
**Boundary:** Included rehearsal. Excluded live branch.
**Spec-change reporting:** Std. Report when rollback is not clean. Stop: T-071. Continue: docs.
**Verification:** self: row-count + hash diff; independent: integrator; rollback: drop branch.
**Return report:** Std. **Done:** clean apply + down. **Chunking trigger:** none.

### T-060 — Send the D-008 delta to the procurement integrator
Status: pending · Type: integrate · Priority: required · Spec: D-008, R-085, C-007, A-018 · DEC: DEC-014
**Objective:** delta (8-value verdict, labels per DEC-013, timing) delivered via procurement's channel (email via Simone, its DEC-010) and linked on G3O #134; acceptance recorded.
**Inputs:** | T-010 signed | stop | · | T-012 enums | merged | stop | · | RS-029 | — | stop |
**Outputs:** | `C:/Users/spaci/repos/G3O/planning/handoffs/D-008-procurement-delta.md`† + #134 comment | procurement integrator | acceptance for A-018 |
**Resources:** researcher; `gh` (external message gate).
**Dependencies:** Requires T-010, T-012 · Enables T-071 · Can run with T-021..T-028 · Researcher gates: PI approves text; posting is external.
**Ownership:** Write handoff file; Shared none (never edits procurement files).
**Boundary:** Included delta. Excluded procurement code.
**Spec-change reporting:** Std. Report when procurement asks to keep 4 values. Stop: T-071. Continue: all else.
**Verification:** self: delta lists every touched enum surface; independent: procurement integrator; rollback: n/a.
**Return report:** Std. **Done:** acceptance recorded. **Chunking trigger:** none.

### T-070 — Freeze and draw the back-fill set
Status: blocked (BLOCKED-INPUT: wave 5 published; v2.7 deployed) · Type: operate · Priority: critical-path · Spec: R-070, R-071, R-077, N-001 · DEC: DEC-019
**Objective:** snapshot documented + unclear at the freeze (API `as_of`), plus the 114 WS10 transfers, as the fixed back-fill list.
**Inputs:** | RS-030 API | live | after wave 5 + deploy | wait | · | RS-026 `activity-review-prepared.csv` | Drive | authoritative | stop |
**Outputs:** | `freeze/backfill-set.json` + `FREEZE.md` | `agent-workspace/2026-10-27-reclass-plan/freeze/`† | T-072, T-073, T-074, T-080 | count = documented + unclear at as_of; `none` excluded |
**Resources:** engineer; free GETs (authorised G8 c).
**Dependencies:** Requires T-071 + external wave-5 publication · Enables T-072 · Researcher gates: PI confirms freeze date.
**Ownership:** Write freeze folder.
**Boundary:** Included snapshot. Excluded runs.
**Spec-change reporting:** Std. Report when totals differ from 9,705 + 27,648 beyond wave-5 additions. Continue: none needed.
**Verification:** self: totals vs API meta; independent: integrator recount; rollback: re-snapshot.
**Return report:** Std. **Done:** PI-confirmed list. **Chunking trigger:** none.

### T-071 — Deploy v2.7 pipeline to the droplet
Status: blocked (gate: deploy) · Type: operate · Priority: critical-path · Spec: D-002, R-070 (freeze = deploy date) · DEC: —
**Objective:** merged `reclass/v2.7` → `main` (PR + approval) and droplet checkout updated, keys/optional features verified (memory g3o-prod-checkout-drifts-silently).
**Inputs:** | T-031 criticals closed | | T-041 pass | | T-054 clean | | T-060 accepted |
**Outputs:** | droplet checkout at merge sha; `DEPLOY.md` | `agent-workspace/2026-10-27-reclass-plan/deploy/`† | T-070 | sha + config check recorded |
**Resources:** engineer; SSH; gh.
**Dependencies:** Requires T-031, T-041, T-054, T-060 · Enables T-070 · Researcher gates: PI approves merge + deploy.
**Ownership:** droplet checkout; Shared `main` — integrator.
**Spec-change reporting:** Std. Report when deploy needs config not in SPEC. Stop: T-070.
**Verification:** self: `git rev-parse` on droplet; config key check; independent: integrator; rollback: checkout previous sha.
**Return report:** Std. **Done:** sha verified on droplet. **Chunking trigger:** none.

### T-072 — Back-fill smoke run (small sample)
Status: blocked (gate: paid run) · Type: verify · Priority: critical-path · Spec: R-035, R-036, R-074..R-077, C-002 · DEC: DEC-002
**Objective:** ~50 institutions covering documented, unclear, no-text, raw-PDF, link chains and ≥5 WS10 transfers; end-to-end to correction-layer files (no live DB).
**Inputs:** | T-070 list | frozen | stop | · | T-001 counts | done | stop |
**Outputs:** | droplet run dir + `SMOKE.md` | `/home/g3o/runs/<backfill-smoke-id>/`, report in agent-workspace† | T-073 | every institution has an end state |
**Resources:** engineer.
**Dependencies:** Requires T-070, T-001 · Enables T-073 · Researcher gates: PI approves smoke spend; PI reviews smoke report.
**Spec-change reporting:** Std. Report when failure-state share >10%. Stop: T-073.
**Verification:** self: end-state count = input; independent: integrator samples 10; rollback: discard run.
**Return report:** Std. **Done:** PI accepts smoke. **Chunking trigger:** none.

### T-073 — Full back-fill run
Status: blocked (gate: paid run) · Type: operate · Priority: critical-path · Spec: R-072, R-074, R-076, R-035, G-003 · DEC: DEC-002
**Objective:** run the frozen set through the back-fill entry point.
**Inputs:** | T-072 accepted | | T-070 list |
**Outputs:** | `/home/g3o/runs/<backfill-id>/` + run log | T-074 | progress + cost reported per batch |
**Resources:** engineer; `nohup ... < /dev/null` (memory).
**Dependencies:** Requires T-072 · Enables T-074 · Researcher gates: PI approves full spend.
**Spec-change reporting:** Std. Report when failures cluster by country (memory g3o-resume-pitfalls). Stop: run. Continue: monitoring.
**Verification:** self: per-batch counts; independent: integrator; rollback: run is additive; discard.
**Return report:** Std. **Done:** all institutions end-stated. **Chunking trigger:** split by group (documented / unclear) if > 1 week.

### T-074 — Load the correction layer and reconcile
Status: blocked (gate: live DB write) · Type: migrate · Priority: critical-path · Spec: R-036, R-073, R-075, R-077, A-005, A-006, A-014, A-015, A-022, C-005 · DEC: DEC-001
**Objective:** apply T-051 on live branch; ingest back-fill output as correction-layer rows; reconciliation table.
**Inputs:** | T-073 output | | T-054 clean | | T-052 deployed to staging |
**Outputs:** | live DB rows; `reconciliation/RECON.md` + csv | `agent-workspace/2026-10-27-reclass-plan/reconciliation/`† | T-080, T-095 | A-005 count identity; A-006 diff empty; denominator unchanged |
**Resources:** engineer + Colin.
**Dependencies:** Requires T-073, T-054, T-052 · Enables T-080, T-082, T-095 · Researcher gates: PI approves live writes.
**Spec-change reporting:** Std. Report when any original value would change. Stop: load.
**Verification:** self: hash diff, counts, 114 transfer check; independent: integrator; rollback: down migration / delete by release id.
**Return report:** Std. **Done:** RECON signed by PI. **Chunking trigger:** split transfers (114) from back-fill.

### T-080 — Draw the 400-institution quality sample
Status: pending · Type: verify · Priority: critical-path · Spec: R-082, R-086 · DEC: DEC-011
**Objective:** stratified sample (group × verdict changed) of 400 + Sonnet 100 per DEC-011; seed recorded.
**Inputs:** | T-074 reconciliation | done | stop |
**Outputs:** | `quality/sample-400.json`, `quality/sample-sonnet-100.json` | `agent-workspace/2026-10-27-reclass-plan/quality/`† | T-081 | seed, strata counts |
**Resources:** engineer; Python.
**Dependencies:** Requires T-074 · Enables T-081 · Researcher gates: none.
**Spec-change reporting:** Std. Report when a stratum has <25 institutions. Continue: all.
**Verification:** self: counts per stratum; independent: integrator; rollback: redraw with new seed (logged).
**Return report:** Std. **Done:** files written. **Chunking trigger:** none.

### T-081 — Agent-read swarm (Haiku 16×25, Sonnet 4×25)
Status: blocked (gate: run of 20 subagents) · Type: verify · Priority: critical-path · Spec: R-082, R-086, N-002, C-006 · DEC: DEC-017, DEC-022
**Objective:** each subagent reads its 25 institutions' pages, v2.7 codes and quotes and returns judgments per DEC-017.
**Inputs:** | T-080 samples | | T-073 artifacts | | DEC-017 rubric |
**Outputs:** | `quality/reads/{haiku,sonnet}-NN.jsonl` | quality folder† | T-082 | model id per file |
**Resources:** coordinator session; Agent tool with Haiku/Sonnet; `workflow-authoring` if run as a Workflow (user opt-in).
**Dependencies:** Requires T-080 · Enables T-082 · Researcher gates: PI approves the swarm run.
**Spec-change reporting:** Std. Report when rubric cannot be applied to a verdict type. Stop: affected reads.
**Verification:** self: 400 + 100 records; independent: T-083; rollback: rerun subagent.
**Return report:** Std. **Done:** all records present. **Chunking trigger:** slots < 5 → serialise batches.

### T-082 — Compile the quality packet
Status: pending · Type: verify · Priority: critical-path · Spec: R-080..R-083, R-086, A-002, A-013, A-016, N-007 · DEC: DEC-017
**Objective:** agreement tables (agent vs v2.7; Sonnet vs Haiku), threshold/downgrade counts per field, quote traces, jev-record field checks; agreement never framed as accuracy.
**Inputs:** | T-081 reads | | T-074 | | T-024 counts |
**Outputs:** | `quality/QUALITY-PACKET.md` | quality folder† | T-083 | disagreement list for PI |
**Resources:** researcher.
**Dependencies:** Requires T-081, T-074 · Enables T-083 · Researcher gates: none.
**Spec-change reporting:** Std. Report patterns pointing to contract defects. Continue: all.
**Verification:** self: numbers recomputed from raw; independent: PI; rollback: n/a.
**Return report:** Std. **Done:** packet complete. **Chunking trigger:** none.

### T-083 — PI audit
Status: pending · Type: verify · Priority: critical-path · Spec: R-082, R-086, A-008 · DEC: —
**Objective:** PI audits every disagreement + 25 random; signs A-008.
**Inputs:** | T-082 packet |
**Outputs:** | `quality/PI-AUDIT.md` (signed) | quality folder† | T-095 | rulings per case |
**Resources:** PI.
**Dependencies:** Requires T-082 · Enables T-095 · Researcher gates: this is the gate.
**Spec-change reporting:** Std (PI rulings that change rules become deltas). 
**Verification:** signature; rollback: n/a.
**Return report:** PI record. **Done:** signed. **Chunking trigger:** none.

### T-090 — Documentation: data dictionary, contract changelog, methods note
Status: pending · Type: document · Priority: required · Spec: D-006, R-090, A-017, N-007 · DEC: DEC-013
**Objective:** document every new field, value, version, downgrade and link rule.
**Inputs:** | T-010, T-012, T-028, T-050 | merged |
**Outputs:** | `docs/data_dictionary.md`, `docs/contract-changelog.md`†, `docs/methods-v27.md`† | branch `reclass/t090-docs`† | public, Kaser, RAs | every field in T-028 documented |
**Resources:** researcher (structure) + PI/writer for prose (researcher persona does no prose drafting).
**Dependencies:** Requires T-010, T-012, T-028, T-050 · Enables T-095 · Can run with T-029..T-041 · Researcher gates: PI approves prose.
**Spec-change reporting:** Std. Continue: all.
**Verification:** self: field-coverage script; independent: PI (A-017); rollback: branch.
**Return report:** Std. **Done:** PI-approved docs merged. **Chunking trigger:** split methods note.

### T-095 — Release decision and publication
Status: blocked (gate: publication) · Type: operate · Priority: critical-path · Spec: D-003, D-004, A-007, A-009, R-054, N-003, N-006 · DEC: —
**Objective:** PI decides release; API/site deployed; A-007 and A-009 checked.
**Inputs:** | T-083 signed | | T-090 | | T-053 staged | | T-074 |
**Outputs:** | `RELEASE.md` with screenshots/API responses | `agent-workspace/2026-10-27-reclass-plan/release/`† | public | A-007, A-009 evidence |
**Resources:** Colin (deploy) + integrator.
**Dependencies:** Requires T-083, T-090, T-053, T-074 · Enables T-096 · Researcher gates: PI release sign-off; deploy.
**Spec-change reporting:** Std. Stop: publication.
**Verification:** self: API responses for 20 sampled institutions; independent: PI; rollback: hide correction-layer projection (release id) + site revert.
**Return report:** Std. **Done:** released + evidence. **Chunking trigger:** none.

### T-096 — Final traceability review and reproduction rerun
Status: pending · Type: verify · Priority: required · Spec: all D-*, G-001..G-005 · DEC: —
**Objective:** rerun the documented pipeline on 20 sampled institutions from the release record and trace each published code to page, quote, jev request and version; feeds Stage 8.
**Inputs:** | T-095 release |
**Outputs:** | `TRACE.md` | `C:/Users/spaci/repos/G3O/planning/reviews/`† | integrator (Stage 8) | 20/20 traced or deltas raised |
**Resources:** fresh reviewer; `planning-spec-reconciliation-protocol.md`.
**Dependencies:** Requires T-095 · Enables Stage 8 · Researcher gates: paid rerun approval.
**Spec-change reporting:** Std.
**Verification:** self: trace table; independent: PI; rollback: n/a.
**Return report:** Std. **Done:** filed. **Chunking trigger:** none.

### T-097 — Standing integration: deltas, CHANGELOG, claims
Status: pending · Type: integrate · Priority: required · Spec: all · DEC: DEC-012
**Objective:** receive card reports, prepare deltas for PI, keep CHANGELOG, mark `complete`.
**Inputs:** card reports; coord mailbox. **Outputs:** `C:/Users/spaci/repos/G3O/planning/CHANGELOG.md`†, governance updates after PI approval.
**Resources:** integrator per DEC-012; `planning-spec-reconciliation-protocol.md`.
**Dependencies:** Requires none · Enables all · Can run with all · Researcher gates: PI approves every delta.
**Ownership:** sole writer of SPEC/RESOURCES/PLAN/CHANGELOG after lock.
**Spec-change reporting:** n/a (receiver). **Verification:** CHANGELOG entry per delta with PI approval ref. **Return report:** to PI. **Done:** Stage 8 closed. **Chunking trigger:** none.

## 4. DAG, critical path, waves

### 4.1 Edges (A → B means B requires A)
T-002→T-003; T-002→T-021; T-003→T-024; T-010→T-011; T-010→T-012; T-010→T-022; T-010→T-040; T-010→T-050; T-010→T-060; T-010→T-090; T-011→T-021; T-011→T-023; T-011→T-026; T-012→T-021; T-012→T-022; T-012→T-024; T-012→T-026; T-012→T-027; T-012→T-028; T-012→T-050; T-012→T-060; T-012→T-090; T-020→T-021; T-020→T-023; T-027→T-021; T-027→T-023; T-027→T-026; T-027→T-028; T-027→T-050; T-021→T-023; T-021→T-025; T-022→T-023; T-022→T-024; T-022→T-025; T-023→T-026; T-024→T-026; T-024→T-028; T-024→T-041; T-026→T-028; T-021..T-028→T-030; T-028→T-052; T-028→T-090; T-030→T-029; T-025→T-029; T-001→T-029; T-001→T-072; T-029→T-031; T-030→T-031; T-029→T-041; T-030→T-041; T-040→T-041; T-050→T-051; T-051→T-052; T-052→T-053; T-051→T-054; T-052→T-054; T-041→T-054; T-031→T-071; T-041→T-071; T-054→T-071; T-060→T-071; T-071→T-070; T-070→T-072; T-072→T-073; T-073→T-074; T-054→T-074; T-052→T-074; T-074→T-080; T-080→T-081; T-081→T-082; T-074→T-082; T-082→T-083; T-083→T-095; T-090→T-095; T-053→T-095; T-074→T-095; T-095→T-096. T-097 has no edges.
Topological sort exists (checked by hand: no edge points from a later wave to an earlier one below) → acyclic.

### 4.2 Critical path
T-010 → T-011 → T-021 → T-023 → T-026 → T-028 → T-030 → T-029 → T-041 → T-054 → T-071 → T-070 → T-072 → T-073 → T-074 → T-080 → T-081 → T-082 → T-083 → T-095 → T-096. External waits on the path: wave-5 publication (before T-070) and every PI gate. Slack: T-001, T-020, T-040, T-050..T-053, T-060, T-090, T-031 (until T-041 ends).

### 4.3 Waves (claude-code budget 5; one slot reserved for review/integration from W3)

| Wave | Task | Agent lane | Dependencies satisfied by | Write claim | Output handoff | Review gate |
|---|---|---|---|---|---|---|
| W1 | T-010 | researcher + PI | — | 3 contract files | T-011, T-012, T-040, T-050, T-060 | PI signs hash |
| W1 | T-020 | engineer A | DEC-008 | `page_chunks.py`† + test | T-021 | T-031 |
| W1 | T-001 | engineer B | PI SSH gate | spikes folder + droplet scratch | T-029, T-072 | integrator |
| W1 | T-002 | engineer C | PI spend gate | spikes folder (`SPIKE-T002*`) | T-003, T-021 | integrator |
| W1 | T-097 | integrator | — | CHANGELOG | all | PI |
| W2 | T-011 | engineer A | T-010 | `questions/v27/`† | T-021, T-023, T-026 | PI wording |
| W2 | T-012 | engineer B | T-010 | `contract.py`, `schema.py` | many | T-031 |
| W2 | T-003 | engineer C | T-002 | spikes folder (`SPIKE-T003*`) | T-024 | PI threshold |
| W2 | T-040 | researcher | T-010 | `tests/fixtures/v27/`† | T-041 | PI labels |
| W3 | T-027 | engineer B | T-012 | `jev_record.py`† | T-021, T-023, T-026, T-028, T-050 | T-031 |
| W3 | T-022 | engineer C | T-010, T-012 | `g3o/extract/*`, `stage_extract.py` | T-023, T-024, T-025 | PI prompt |
| W3 | T-060 | researcher | T-010, T-012 | `handoffs/D-008*`† | procurement | PI text |
| W3 | T-097 | integrator (reserved) | — | CHANGELOG | — | — |
| W4 | T-021 | engineer A | T-002, T-011, T-012, T-020, T-027 | `jev_page_code.py`†, `stage_page_code.py`† | T-023, T-025 | T-031 |
| W4 | T-024 | engineer C | T-003, T-012, T-022 | `support_check.py`† | T-026, T-028 | T-031 |
| W4 | T-050 | researcher | T-010, T-012, T-027 | `handoffs/D-007*`† | Colin | PI + Colin |
| W5 | T-023 | engineer A | T-021, T-022 | `jev_activity_code.py`†, `stage_activity_code.py`† | T-026 | T-031 |
| W5 | T-025 | engineer C | T-021, T-022 | `follow.py`†, `stage_follow.py`† | T-029 | T-031 |
| W5 | T-051 | Colin (outside slot budget) | T-050 | g3o-api `sql/021*`† | T-052, T-054 | T-054 |
| W6 | T-026 | engineer A | T-011, T-023, T-024, T-027 | Stage 6 files | T-028 | T-031 |
| W7 | T-028 | engineer A | T-026 | `persist/writer.py` | T-030, T-052, T-090 | T-031 |
| W8 | T-030 | integrator | T-021..T-028 | orchestrator, config, telemetry, pins, e2e test | T-029, T-031, T-041 | T-031 |
| W8 | T-090 | researcher + PI | T-010, T-012, T-028, T-050 | docs files | T-095 | PI |
| W8 | T-052 | Colin (outside slot budget) | T-051, T-028 | g3o-api ingest/worker | T-053, T-054, T-074 | T-054 |
| W9 | T-029 | engineer A | T-030, T-025, T-001 | `run/backfill/`†, cli hunk (merged by T-030 owner) | T-031, T-041 | T-031 |
| W9 | T-053 | Colin | T-052 | website files | T-095 | PI copy |
| W10 | T-031 | reviewer (reserved slot) | T-029, T-030 | `reviews/Code-Review-T031.md`† | T-071 | integrator |
| W10 | T-041 | engineer B | T-029, T-030, T-040, T-024 | `fixture-run/`† | T-054, T-071 | PI |
| W11 | T-054 | engineer B + Colin | T-041, T-051, T-052 | disposable Neon branch, `rehearsal/`† | T-071, T-074 | integrator |
| W12 | T-071 | engineer A | T-031, T-041, T-054, T-060 | droplet checkout, `deploy/`† | T-070 | PI |
| W13 | T-070 | engineer A | T-071 + wave 5 | `freeze/`† | T-072 | PI |
| W14 | T-072 | engineer A | T-070, T-001 | droplet smoke run dir | T-073 | PI |
| W15 | T-073 | engineer A | T-072 | droplet run dir | T-074 | PI |
| W16 | T-074 | engineer A + Colin | T-073, T-054, T-052 | live DB (release id), `reconciliation/`† | T-080, T-082, T-095 | PI |
| W17 | T-080 | engineer B | T-074 | `quality/sample-*`† | T-081 | integrator |
| W18 | T-081 | coordinator + 20 subagents (serialised in ≤4 concurrent) | T-080 | `quality/reads/`† | T-082 | PI |
| W19 | T-082 | researcher | T-081, T-074 | `quality/QUALITY-PACKET.md`† | T-083 | PI |
| W20 | T-083 | PI | T-082 | `quality/PI-AUDIT.md`† | T-095 | — |
| W21 | T-095 | Colin + integrator | T-083, T-090, T-053, T-074 | `release/`†, deploy | T-096 | PI |
| W22 | T-096 | reviewer | T-095 | `reviews/TRACE.md`† | Stage 8 | PI |

Collision check: within each wave write claims are disjoint; `orchestrator.py`, pins and `cli.py` merges belong to T-030's owner only; `contract.py` to T-012 only; `stage_extract.py` to T-022 only; Stage 6 files to T-026 only; DB schema to Colin only; `SPEC/PLAN/CHANGELOG` to the integrator only. Spikes T-001/T-002/T-003 write distinct file prefixes in one folder.

Shared-surface integrators: G3O `reclass/v2.7` → T-030 owner; g3o-api schema + API contract → Colin; D-007 field list → T-030 owner + Colin; plan governance → integrator (DEC-012).

## 5. Risks and gates

### 5.1 Risk register

| Risk | Trigger | Likelihood/impact | Prevention | Detection | Containment/rollback | Owner/task |
|---|---|---|---|---|---|---|
| jev two-pass cost/latency too high at ~37k institutions × ~5-9 pages × passes | T-002 numbers | M / H | spike before build; chunk size choice | T-002 report | revise DEC-003/008; PI scope delta | T-002, integrator |
| Many negatives fall below 0.8 → mass move to `unclear` (Q-019 a) | T-041, T-072 counts | M / H (headline shift) | report per-field counts early | T-072 smoke | PI may revisit threshold via delta before T-073 | T-024, T-072 |
| Fuzzy matcher fails on CJK/Thai etc. | T-003 error table | M / M | per-script calibration | T-003 | per-script threshold delta | T-003 |
| nano segmentation text steers jev (C-001 breach) | DEC-010 option with summaries | M / H | spans not prose (if chosen) | T-031 | change DEC-010 | T-022, T-031 |
| Original observations overwritten | migration/ingest bug | L / critical | additive schema; rehearsal | A-006 diff in T-054/T-074 | down migration; delete by release id | T-051, T-054, T-074 |
| Back-fill rows invisible (wave gating) | R-055 not implemented | M / H | explicit R-055 tests | T-054, T-095 | projection fix | T-052 |
| Droplet checkout drifts / missing keys switch features off | deploy | M / H | config check in T-071 | DEPLOY.md | redeploy | T-071 |
| Resume re-triages / skips scrape | DEC-002 b chosen | M / M | prefer explicit entry point (if chosen) | T-072 | rerun | T-029 |
| Failures cluster by country | T-073 | M / M | batch by country mix | per-batch log | targeted rerun | T-073 |
| Procurement breaks on new enum | deploy before acceptance | M / M | T-060 before T-071 | A-018 | hold deploy | T-060 |
| Validate-contract label collision v1.4 | DEC-013 unresolved | H / L | decide label now | T-031 pin check | relabel before merge | T-010 |
| Wave 5 delays freeze indefinitely | wave-5 run stalls | M / M | track run | T-070 wait | PI decides cut-off via delta | integrator |
| Haiku/Sonnet agent read mistaken for accuracy | packet wording | M / M | R-083 rule in packet template | T-083 | rewrite packet | T-082 |
| Stored text missing for documented set | T-001 | U / M | spike | T-001 | live re-scrape load (R-074) grows | T-001 |

### 5.2 Gate list (researcher gates; none passes by lock alone)

| Gate | Cards |
|---|---|
| PI coding-rule wording / contract hash | T-010, T-011 (non-verbatim questions), T-022 (nano prompt) |
| PI labels / thresholds | T-003, T-040, T-041 failures |
| Paid calls | T-002, T-041, T-072, T-073, T-081, T-096 |
| SSH / droplet | T-001, T-071, T-072, T-073 |
| DB writes | T-054 (disposable), T-074 (live) |
| Push / merge / deploy | every build card push; T-030 integration branch; T-071; T-052/T-053/T-095 deploy |
| External messages | T-050 (to Colin), T-060 (#134 / procurement) |
| Public wording | T-053 copy, T-090 prose |
| Release | T-083, T-095 |

### 5.3 Readiness after the Stage 6 lock

| State | Cards | Unblocked by |
|---|---|---|
| ready (no PI design decision needed) | T-010 (once DEC-013, DEC-016 ruled), T-097 | lock + DEC-012 |
| ready pending gate | T-001 (SSH), T-002 (spend) | PI authorisation |
| ready pending decision | T-020 (DEC-008) | DEC-008 |
| pending (upstream outputs) | T-003, T-011, T-012, T-021..T-031, T-040, T-041, T-050..T-054, T-060, T-080..T-083, T-090, T-095, T-096 | predecessors + DEC-001..DEC-007, DEC-009..DEC-011, DEC-014, DEC-015, DEC-017, DEC-018 |
| blocked (external) | T-070 | wave-5 publication + T-071 |

## 6. Feedback path

Each card reports spec conflicts to the integrator (DEC-012) via coord mailbox; the integrator prepares a delta for Simone; affected work pauses at the card's stop boundary; independent work continues. Only the integrator edits governance files after PI approval.

## 7. Structural completion gate (self-check)

| Check | Result |
|---|---|
| Coverage has no unexplained missing D/R/A/C IDs | PASS (R-053 superseded, mapped to residual; dangling R-060..R-062 reported as SD-a) |
| DAG acyclic | PASS (edge list §4.1; every edge goes to a later wave) |
| Each task has inputs, outputs, tools, skills, review, done | PASS (T-083/T-097 are PI/integrator roles; "skills" = protocol named or none) |
| Operational checks + researcher gates for judgments | PASS |
| Every input traces to RS-*, predecessor, USER-SUPPLIED or EXTERNAL | PASS |
| Each final D-* has a reproduction task | PASS (T-096 reruns the documented pipeline) |
| Collision-free waves | PASS (§4.3 note) |
| One integrator per shared surface | PASS |
| Spec-delta contract per card + one delta-log writer | PASS conditional: writer named by DEC-012 (pending) |
| Unknowns as blockers or spikes | PASS (T-001, T-002, T-003; T-070 external) |
| No implementation begun | PASS |

Overall: PASS, conditional on DEC-012 naming the delta-log writer; 18 decisions pending PI.

## 8. Decisions for the PI

- **DEC-001 Correction layer (G2):** (a) new g3o-api tables: correction rows linked to original observation ids + a projection view that selects each institution's most recent row; (b) back-fill rows written as ordinary rows of a new back-fill run (row per run, R-051) plus a thin link table to the originals and a release id; (c) extend the `backfill_verdicts.py` precedent (verdict-only corrections; new fields would need a separate path).
- **DEC-002 Back-fill entry point (G3):** (a) new first-class `backfill` command reusing Stages 4-7 code on a fixed list from stored pages, no re-triage; (b) copy-run + delete done markers + resume (no new command; accepts re-triage cost and its pitfalls); (c) `--master-csv` with the fixed list (re-runs discovery; conflicts with R-076 page sets).
- **DEC-003 Link following (G4):** (a) inside the scrape stage, re-entrant with a hop counter; (b) a separate follow-up leg after pass 1 that fetches, then sends pages back through pass 1, looping ≤3 hops; (c) follow-up leg after Stage 5 only (one extra loop per hop, simpler, slower).
- **DEC-004 jev answer storage (G5):** (a) per-institution JSON artifacts (Stage 2/3 pattern) + DB columns for confidence, model id, request id, full distribution in a jsonb column; (b) artifacts only on the droplet/object store, DB keeps confidence; (c) everything in DB columns.
- **DEC-005 Per-row contract version (G6):** (a) explicit `contract_version` column on every CSV/DB row; (b) derived from `run_id` → `runs.contracts`, with a rule that a run never mixes versions.
- **DEC-006 Fixtures (G9):** (a) synthetic pages; (b) real pages mined from local corpora, labelled by agent then PI; (c) both (synthetic for edge mechanics, real for verdicts/CX).
- **DEC-007 Fuzzy matcher (G10):** (a) add a library (e.g. rapidfuzz) as a dependency; (b) in-house normalised substring + edit distance.
- **DEC-008 Page chunker (G13):** (a) port `byte_chunks` (48,000 bytes, halve-and-retry ×3); (b) reuse Stage 6 split (100,000-byte budget, depth 3).
- **DEC-009 Free-text routing (R-006):** (a) proposed table: jev Choice for `year_announced`/`year_deployed` (year choices) and CX-60/61 normalisation; deterministic for contact emails and explicit years; nano for `activity_name`, `tool_name`, `vendor`, `reported_outcomes`, `reported_incidents`, `scope_notes`; (b) nano for every free-text field, jev only for closed sets; (c) PI supplies the table.
- **DEC-010 Segmentation → pass 2:** (a) nano returns character spans only; jev pass 2 sees the page with the span marked; (b) nano returns a short activity description used as jev context; (c) both, span for coding and description for display only.
- **DEC-011 Sonnet 100 draw:** (a) proportional to strata of the 400, fixed seed; (b) equal per stratum (25 × 4); (c) all "verdict changed" first, remainder random.
- **DEC-012 Integrator / delta-log writer:** (a) a researcher session acting for the PI, started by Simone (as in the procurement plan); (b) an engineer session; (c) Simone directly, with agents only drafting deltas.
- **DEC-013 Version labels:** (a) extract v2.7 + validate v1.5 (skip v1.4, used by unpushed `052fcb2`); (b) extract v2.7 + validate v1.4 (reuse; `052fcb2` stays archive-only); (c) extract v2.7 + validate v2.7 (align labels from now on).
- **DEC-014 D-008 timing:** (a) send as soon as T-010 is signed (early; may need a follow-up if T-012 finds more surfaces); (b) after T-041 passes, before deploy (later; firmer).
- **DEC-015 API exposure of older rows:** (a) API default = most recent; older rows via a history parameter/endpoint; (b) API serves most recent only; older rows backend-only (bulk export keeps them).
- **DEC-016 Supporting-text length:** (a) fixed cap with truncation marker (cap value set by PI); (b) full quoted sentence(s), no cap; (c) cap only on the website, full text in API.
- **DEC-017 Unit of agreement in the agent read:** (a) institution verdict only; (b) verdict + page verdicts; (c) verdict + page verdicts + activity fields and quotes.
- **DEC-018 v2.6 code reuse:** (a) port `evidence_review.py` and rules selectively from `052fcb2`; (b) rewrite against the jev Stage 6, using `052fcb2` and its 30 fixtures as reference only.
