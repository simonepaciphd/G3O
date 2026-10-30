# PLAN: G3O pipeline reclassification

Status: READY-WITH-BLOCKS
Spec: `C:/Users/spaci/repos/G3O/planning/SPEC.md` v001.7 (v001.4 APPROVED 2026-10-28; v001.5 by RC-D-001, v001.6 by RC-D-002, 2026-10-29; v001.7 by RC-D-003, 2026-10-30); resources: `C:/Users/spaci/repos/G3O/planning/RESOURCES.md` v001.2 (v001 APPROVED 2026-10-27; v001.1 by RC-D-001; v001.2 by RC-D-002)
Baseline lock: 2026-10-28T09:50-07:00 by Simone Paci (RC-BL-001, chat "lock")
Deadline: none
Source draft plan/review: `C:/Users/spaci/repos/G3O/planning/Plan-Draft.md` (v001-draft1), `C:/Users/spaci/repos/G3O/planning/Plan-Review.md` (27 findings); rulings `C:/Users/spaci/repos/G3O/planning/Stage5-Rulings.md`
Mode: PLAN_ONLY
Delta RC-D-001 (approved 2026-10-29, Simone, chat "approve delta"; text `planning/deltas/RC-D-001.md`): the extractor is now Claude Haiku 5.5 (`claude-haiku-5-5`, medium effort, direct Anthropic API, RS-037). **Throughout this plan, "nano", "gpt-5-nano" and "OpenAI" in extraction context mean the extractor** (C-001, SPEC v001.5). Calls are sync for testing (T-002, T-041, T-072, T-096) and Message Batches for full runs (T-073, ordinary runs after deploy). Berivox reviews (T-031; card PRs, non-blocking). W1 runs sequentially: T-010 → T-002 → T-020 → T-001. Waves 6 and 7 run after deploy as ordinary v2.7 runs; wave 5 is finished.
Delta RC-D-002 (approved 2026-10-29, Simone, chat "approve delta"; text `planning/deltas/RC-D-002.md`; change schedule `planning/t010/governance-impacts.md`, whose Resolutions table overrides any conflicting row): the codebook (`codebook/codebook.yaml`†, SPEC R-007) is the machine-readable single source of truth; jev questions, extractor prompts, enums, schema, the data dictionary and the contract docs are generated from it (new T-013). **Throughout this plan, "contract v2.7" or "the signed contract" as a T-010 output means the signed codebook release and the contract docs generated from it, and "`contract_version`" on a row means the codebook release label plus the setup pointer and `evidence_channel`** (SPEC R-050 v001.6; extract v2.7 / validate v1.5 are recorded only in the setup record, C3 a). New cards (plain IDs, per this plan's convention; RC-D-002 names the first two T-013† and T-014†): T-013 (codebook schema, generators, CI), T-014 (scraper chrome text and links), T-015 (source-level field coder), T-016 (re-pilot of the re-signed items, paid, Simone-run), T-062 (D-009 handoff, after v2.7 deploys), T-063 (D-010 calendar-conversion heads-up). T-002 now requires T-010 and T-013 (RC-D-002 D); W1-W4 re-laid. Coding-rule wording is the PI's: SPEC v001.6 carries `[wording: PI ...]` markers where a rule's text must change, and the six choices the schedule left unruled were resolved as RC-D-002 O1-O6 (PI, 2026-10-29, chat "all accepted"): O1 R-043 unchanged; O2 T-015 owns every source-level field; O3 T-010 and T-013 are soft both ways; O4 T-024 ships its checks as a library the passes call; O5 lanes T-014 and T-015 to eng-a, T-016 to the integrator (Simone runs the paid re-pilot); O6 the inferred priorities and missing-input behaviour stand.
Delta RC-D-003 (approved 2026-10-30, Simone, chat "all accepted"; text `planning/deltas/RC-D-003.md`; record `planning/t010/t010-rulings.md`): the SPEC departures of codebook review round 3 and the sign-off of its open items O1-O16 (SPEC v001.7: R-002, R-003, R-004, R-005, R-007, R-014, R-015, R-017, R-023, R-040, R-041, R-044, R-045, R-090, D-001, D-009, A-001, A-003, A-007, A-021). The item template `planning/t010/item-template.md` (27 fields, generator checks 1-16) is approved with it, which meets the T-013 input gate. Card impacts: T-020 implements the check-then-combine step, the temporary part answer "not covered by this part", first-part skipping, the missing-answer rank, the most-sure quote, the mapping steps and the two-tier verdict order (R-044, R-045; A-021); T-011 / T-021 / T-023 carry the part-prompt sentence, `content_data` as a page question and the allowed-pairs flag; T-022 / T-032 run the quote step on skipped items too (R-040), which T-002 counts in the quote-step cost; T-024 / T-027 / T-012 carry the support-status spellings and the items `support_rule_name` and `support_status_second_reason` (R-041); T-026 takes the reverse relation values, per-pair links and pooled-evidence order (R-017, R-044); T-028 / T-052 / T-053 publish the relationship and role as one column and report `unresolved` and `not_assessable` as `unknown` in summaries (R-014, R-005, R-015; A-007); T-015 and T-062 / T-090 take the date-origin map and `date_upper_bound` (D-009, R-090). No new card, no RESOURCES change, no version steps beyond the v2.7 release's two (C-007, r2#5).

Prepared by: session `20261028-claude-v2-20be995c13d4020f` (Claude Code, claude-opus-5-5, researcher persona) under `planning-adjudication-protocol.md` v0.3; task cards converted by three forks of that session from the Plan-Draft cards and the integrator's delta brief, then assembled and checked by the parent.
Base refs (fetched 2026-10-28): G3O `origin/main` `375f1ff` (Plan-Draft used `c6349d6`; #135 since changed `g3o/run/presweep/orchestrator.py` and `tests/test_presweep.py`); g3o-api `origin/main` `acdb030`; g3o-website `origin/main` `282ca6a`. Local G3O checkout is on `perf/validate-jev-parallel`; work branches from `origin/main`.
Path notes: paths marked † are proposed names, confirmed by the executing engineer; a rename is a mechanical delta.

## Fixed decisions and preserved strengths

PI rulings (Stage 5, 2026-10-28; verbatim answers in `Stage5-Rulings.md`):

- DEC-001 a: correction layer = new g3o-api correction tables linked to original observation ids + most-recent projection view; loader reuses the `scripts/backfill_verdicts.py` safety pattern (dry-run default, `--apply`, shared parse function, explicit refresh with watermark check). Rejected: c (in-place UPDATE breaks R-073, cannot carry 1:N activities), b / b′ (run rows conflict with C-005 and wave windows; silent-miscount risk).
- DEC-002 a: first-class `backfill` command, Stages 4-7 on a fixed list from stored pages, no re-triage.
- DEC-003 b: link following is a separate follow-up leg after pass 1, ≤3 hops; option d closed by RC-D-001 (B): Message Batches for full runs, sync for testing.
- DEC-004 a: jev answers in per-institution JSON artifacts + DB columns (confidence, model id, request id) + full distribution in jsonb; the API does not serve the distribution.
- DEC-005 a: explicit `contract_version` column on every CSV / DB row. RC-D-002 N24 (r2#32): becomes the codebook release label, plus the setup pointer and `evidence_channel` (SPEC R-050 v001.6).
- DEC-006 c: synthetic fixtures for mechanics, real pages for verdicts / CX (agent then PI labels).
- DEC-007 a: pinned fuzzy-match library (rapidfuzz); threshold from T-003, PI approves (Q-020 b).
- DEC-008 c: page chunker splits by estimated tokens, halve-and-retry fallback.
- DEC-009 a: free-text routing table (SPEC R-006 note). Superseded by RC-D-002 N24 (r2#28): the per-item `coder` column in the codebook (SPEC R-006, R-007 v001.6).
- DEC-010 a: nano returns character spans only; jev pass 2 sees the page with the span marked.
- DEC-011 a + item 27: 400 = 100 per stratum; Sonnet 100 = 25 per stratum, fixed seed; overall figures weighted.
- DEC-012 a: integrator = a researcher session acting for the PI, started by Simone; sole writer of SPEC / RESOURCES / PLAN / CHANGELOG / delta log.
- DEC-013 a: labels extract v2.7 + validate v1.5. Amended by RC-D-002 C3 a (N24): the two labels are recorded only in the setup record; each row carries one codebook release label.
- DEC-014 b: procurement delta after T-041 passes, before deployment.
- DEC-015 a: API default most recent row; older rows via history parameter / endpoint.
- DEC-016 c: full supporting text in API; website display cap (value set by PI after T-003). Unchanged (RC-D-002 N24, r2#17).
- DEC-017 b: agent read compares institution verdict + page verdicts; agents read blind.
- DEC-018 b: rewrite consolidation against jev Stage 6; `052fcb2` reference only, its 30 fixtures as tests.
- SD-g: both R-086 inferences confirmed.
- Items 20 a (all pages of unclear institutions), 21 b (ordinary runs load hidden until release), 22 b (per-institution URL cap), 23 i/ii (transfer owners on top of the 400; `none` owners included), 24 b (keep waves; PI opens windows), 25 i/ii (GitHub issues to Colin; engineer fallback), 26 a (§4.3 in v2.7), 27 (100 per stratum) — carried into SPEC v001.4.

Mechanical (unchanged from Plan-Draft §1): DEC-019 freeze record from public API `meta.coverage`; DEC-020 one feature branch per card into `reclass/v2.7`†; DEC-021 pins are regenerated once, at the final integration step (T-035, moved from T-030 after the second review); DEC-022 agent-read model ids recorded at T-081 launch.

Global red line added 2026-10-28 (Simone, `~/.claude/CLAUDE.md` red line 4): agents never run anything that costs money. Every paid step (jev, extractor Batch/sync, VM compute) is prepared by the card's agent with the exact command and a cost estimate and run by Simone as a one-line `! <command>`. Applies to T-002, T-016 (RC-D-002 N28), T-041, T-072, T-073, T-096; T-081 carries a decision point on whether the Claude subagent swarm counts.

Preserved strengths (Plan-Review): per-card stop/continue and spec-delta rules; sole integrator per shared surface; T-096 / Stage 8 reconciliation; complete gate list for paid / SSH / DB / push / deploy / external; T-072 smoke never touches the live DB; the plan proposes spec fixes without editing; R-083 / C-006 guarded.

## Finding disposition ledger

| Finding | Disposition | Evidence/reason | Plan change | User decision |
|---|---|---|---|---|
| PF-001 | ACCEPT-MODIFIED | T-022 runs before pass 2, so nothing produced quotes for activity-level codes (R-040) | New T-032 (pass-2 supporting-text call) after T-023; T-024 requires T-032 | procedural default accepted 2026-10-27 |
| PF-002 | ACCEPT | Confirmed: `g3o/extract/batch.py:49` `DEFAULT_TEXT_CAP_CHARS = 60_000` (head+tail) loses mid-page quotes; R-044 needs the quote from the producing chunk | T-022 and T-032 extract per chunk; the cap does not apply on the v2.7 path; edge T-020→T-022 added | procedural default |
| PF-003 | USER-DECISION → resolved | Unreclassified pages would keep 4-value answers inside a reclassified institution | SPEC R-076 v001.4: all pages of unclear institutions; T-001, T-029, T-072 scope widened | item 20 a |
| PF-004 | ACCEPT | Confirmed: g3o-api `scripts/ingest.py` upserts `ON CONFLICT (run_id, institution_uid, source_id) DO UPDATE` (L105, L162) | Fresh release id, never an original run_id (T-029, T-052 guard); T-054 rehearsal on a branch cut from live; T-074 pre-load snapshot | procedural default |
| PF-005 | USER-DECISION → resolved | DEC-001 c breaks R-073 / G-001; b conflicts with C-005 and wave windows | DEC-001 a in T-050, T-051, T-052, T-074 | DEC-001 a |
| PF-006 | ACCEPT | Back-fill rows would be public before the PI audit | Release flag (SPEC R-056): T-050/T-051/T-052 implement; new T-055 takes the schema and ingest live before deploy so ordinary v2.7 runs load hidden; T-074 loads back-fill hidden; T-095 releases | procedural default; item 21 b |
| PF-007 | ACCEPT | No owner for `v_wave_*` views, materialized aggregates, `sql/013..020`, refresh; `sql/007` trigger does not fire on UPDATE (per `backfill_verdicts.py` header) | T-050 specifies, T-051/T-052 (Colin) own; T-054 and T-074 run explicit refresh + watermark check | procedural default |
| PF-008 | ACCEPT | Wave-5 wait sat on T-070 only; deploy could precede wave-5 publication | T-071 carries an external gate: wave 5 `r20261023T134656Z-be8a` published | procedural default |
| PF-009 | USER-DECISION → resolved | Ordinary runs between deploy and release were unplanned | Ordinary v2.7 runs load hidden until release (R-056); T-052, T-095 | item 21 b |
| PF-010 | USER-DECISION → resolved | Link fan-out unbounded within 3 hops | SPEC R-032 v001.4 per-institution URL cap; T-002 measures fan-out; T-025 implements + records cap reached; PI sets the value | item 22 b |
| PF-011 | USER-DECISION → resolved | No mechanism for the 114 transfers; owners may be `none`; sample placement unclear | New T-034 (WS10 transfer path); T-070 draws the 45 owners incl. `none`; T-080 adds a transfer stratum on top of the 400; SPEC R-077, R-086, N-001 v001.4 | item 23 i, ii |
| PF-012 | USER-DECISION → resolved | Agent read not blinded; audit load unstated | T-081 blind read (verdict + page verdicts); T-082 reports the disagreement count = PI audit load | DEC-017 b + blind |
| PF-013 | ACCEPT | Agent-read traceability missing | T-081: input manifests, prompt hash, identical inputs across models, transcripts kept, per-record model id; page pull under SSH gate | procedural default |
| PF-014 | ACCEPT-MODIFIED | Unclaimed enum / contract touchpoints across 3 repos (34 G3O files) | T-012 chunk 1 inventories every touchpoint and the integrator assigns each file to one card before chunk 2; g3o-api / website files to T-050..T-053; procurement to T-060 | procedural default |
| PF-015 | USER-DECISION → resolved | "Most recent row" replaced per-wave latest-run-wins; w001 expires 2027-01-01 | Keep waves for ordinary runs, correction rows wave-free (T-050/T-052); T-097 standing check that a window is open beyond 2027-01-01 | item 24 b |
| PF-016 | ACCEPT | ~8 sequential Batch rounds per run; no runtime estimate | T-002 measures rounds and latency; DP in T-025 for sync vs Batch (DEC-003 d) | DEC-003 option d deferred to T-002 |
| PF-017 | ACCEPT | Droplet disk unchecked | T-001 records free disk and run-dir footprint; T-071 re-checks | procedural default |
| PF-018 | ACCEPT | No e2e on the integrated back-fill path | New T-035 merges T-029 and T-034, owns the `cli.py` hunks, runs the e2e through new-run, back-fill and transfer entry points and regenerates pins once; T-041 runs fixtures through all three paths | procedural default |
| PF-019 | USER-DECISION → resolved | Colin lanes labelled slack; channel and fallback unstated | Colin lane on the critical path (T-050→T-051→T-052→T-054→T-071); GitHub issues on g3o-api / g3o-website; fallback engineer session under PI sign-off | item 25 i, ii |
| PF-020 | ACCEPT | No notice to the locked validation plan (BL-001) | New T-061 (notice to the validation plan's integrator), required before T-071 | procedural default |
| PF-021 | ACCEPT | Spec-changing options were unlabelled | Labels applied in the 2026-10-27 relay; every chosen option that changes the SPEC is carried in SPEC v001.4 | none further |
| PF-022 | ACCEPT | DEC-014 a impossible under the T-012 edge; delta lacked mapping, pins, §4.3 status | DEC-014 b: edge T-041→T-060; T-060 delta lists old→new mapping, pins (extract v2.7, validate v1.5), §4.3 status (R-087) | DEC-014 b, item 26 a |
| PF-023 | ACCEPT | g3o-api `scripts/export_bulk.py` and the #175 README not updated | T-050 specifies, T-052 updates `export_bulk.py` + `test_export_bulk.py`; T-090 updates the #175 README | procedural default |
| PF-024 | USER-DECISION → resolved | Both chunker options were byte-based; jev's limit is tokens | DEC-008 c in T-020; T-002 calibrates the estimator (soft edge) | DEC-008 c |
| PF-025 | ACCEPT | Stale SPEC version and g3o-api ref in Plan-Draft header | Header: SPEC v001.4; g3o-api `acdb030`; G3O `375f1ff` | none |
| PF-026 | ACCEPT | Edge errors: T-050→T-028, T-020→T-022; soft vs hard edges | Both edges added as hard; only T-002→T-020 is soft (estimator calibration) | none |
| PF-027 | ACCEPT | Missing rerun agreement criterion, cap-reached record, full-set projection | T-096 agreement criterion; T-025 / T-072 cap-reached record; T-072 full-set cost / runtime projection | none |
| RV2-C1 | ACCEPT | Second review (fresh-context subagent, 2026-10-28): migration 021 reached live only at T-074 (W19 then), after the T-071 deploy, so ordinary v2.7 runs could not load hidden (item 21 b, R-056); T-052 gate named production while its done condition was staging | New T-055 (pre-apply snapshot, 021 live, production ingest deploy, hidden-row and v2.5-ingest checks) between T-054 and T-071; T-052 gate staging only | entailed by item 21 b |
| RV2-H1 | ACCEPT | T-030 e2e needed the back-fill entry point built later by T-029; no card merged T-029/T-034 or owned their `cli.py` hunks; pins regenerated before those merges | New T-035 (see PF-018); T-030 new-run only; T-031, T-041 require T-035 | none |
| RV2-H2 | ACCEPT | T-051 self-check wrote to a disposable Neon branch with no gate | PI gate on every Neon branch creation, snapshot and DB write (T-051, T-054, T-055, T-074) | none |
| RV2-M1 | ACCEPT-MODIFIED | Neon branch / compute billing was unverified | Simone confirmed 2026-10-28 that Neon branches and snapshots are free ("1 free"); agents run those commands under the existing PI DB-write gates | Neon billing: free |
| RV2-M2 | ACCEPT | T-096 used SSH without a gate | SSH gate added; rerun output loads to no DB | none |
| RV2-M3 | ACCEPT | T-083 and T-095 shared W23 though T-095 requires T-083 | Waves re-laid: T-083 W25, T-095 W26, T-096 W27 | none |
| RV2-M4 | ACCEPT | T-003 consumed quotes T-002 never produced | T-002 adds a nano quote leg inside its paid gate | none |
| RV2-M5 | ACCEPT | T-054 rehearsed on fixture output with no original observation ids | T-041 adds a ≤5-institution real-id back-fill subset (paid, Simone-run) feeding T-054 | none |
| RV2-M6 | ACCEPT | T-022 limited pass-1 quotes and follow-up links to the 5 R-003 verdicts, below R-040 / R-030 / R-031 / R-006 | T-022: quotes for every positive/substantive page code on every page (Q-010 a), links for every incomplete page, segmentation only on the 5 verdicts, free-text values carry support | entailed by SPEC |
| RV2-M7 | ACCEPT | R-043, R-051, R-055, R-087 had no real check | Checks added to T-054, T-095, T-031 | none |
| RV2-M8 | ACCEPT | Cards named the shared checkout (on `perf/validate-jev-parallel`) as cwd | Every engineer card uses its lane worktree `C:/Users/spaci/worktrees/G3O-<lane>/`† | none |
| RV2-L1..L7 | ACCEPT | Chunker path mismatch; T-061 RS-016→RS-033; T-021 input vs hard edge; DP-005 vs signed-contract inputs; #175 README repo; transfer stratum weighting; stale line in Stage5-Rulings.md | Fixed in the named cards and files; transfer stratum reported separately, excluded from weighted figures | none |

## Requirement traceability

| Spec ID | Producer task/output | Verifier/review evidence | Status |
|---|---|---|---|
| G-001 | T-010..T-034, T-051..T-053, T-095 | T-096 | mapped |
| G-002 | T-022, T-032, T-024 | T-041, T-082 (A-002) | mapped |
| G-003 | T-029, T-073, T-074 | T-074 (A-005), T-096 | mapped |
| G-004 | T-095 (single versioned state), T-052 export_bulk, T-090 #175 README | T-096 | mapped (guard N-006) |
| G-005 | T-011, T-021, T-023 | T-095 (A-009) | mapped |
| D-001 | T-010, T-013, T-011, T-012 | T-031, PI gate T-010 (A-001), CI drift check (T-013) | mapped |
| D-002 | T-020..T-030, T-032, T-034 | T-031, T-041 | mapped |
| D-003 | T-029, T-034, T-070, T-072..T-074 | T-074, T-082, T-096 | mapped |
| D-004 | T-051..T-053, T-095 | T-054, T-095 (A-007) | mapped |
| D-005 | T-080..T-083 | T-083 (A-008) | mapped |
| D-006 | T-090 | PI (A-017) | mapped |
| D-007 | T-050 | Colin acceptance (A-019) | mapped |
| D-008 | T-060 | procurement integrator (A-018) | mapped |
| D-009 | T-062 | AI-text-detection owner acceptance | mapped (RC-D-002 N35) |
| D-010 | T-063 | multilingual subproject reply | mapped (RC-D-002 L) |
| R-001 | T-021, T-023, T-026 | T-031 (no nano output read as a code) | mapped |
| R-002 | T-011, T-021, T-010 (`content_data` stays a page question, RC-D-003) | T-041 (A-011) | mapped |
| R-003 | T-022 (spans), T-023, T-024 (`no` on non-GenAI pages, RC-D-003) | T-041 (A-003) | mapped |
| R-004 | T-011, T-023, T-010 (allowed-pairs table, RC-D-003) | T-041 (A-003) | mapped |
| R-005 | T-026, T-028, T-052, T-053 (published `unknown`, RC-D-003) | T-041 (A-010) | mapped |
| R-006 | T-011 (Choice), T-022 (nano), T-024 (deterministic) per DEC-009 a (superseded by the codebook coder column, RC-D-002 row 5) | T-041, T-082 | mapped |
| R-007 | T-010 (items), T-013 (schema, generators, CI) | T-031, CI drift check, A-001 linkage | mapped (RC-D-002 N35) |
| R-008 | T-011 (round / gate order), T-021, T-023 | T-041 | mapped (RC-D-002 N35) |
| R-010..R-014 | T-010, T-011, T-023, T-026, T-052, T-053 (one published relationship column, RC-D-003) | PI gate T-010 (A-001), T-041 | mapped |
| R-015 | T-010, T-012, T-028, T-051, T-052, T-053 (published `unknown`, RC-D-003) | T-041 (A-011), T-031 | mapped |
| R-016 | T-010, T-011 | T-041 (A-012) | mapped |
| R-017 | T-010, T-011, T-022 (segmentation), T-023, T-026 | T-016, T-041 (A-003) | mapped (RC-D-002 N35) |
| R-020..R-024 | T-011, T-021, T-023, T-024 | T-041 (A-020) | mapped |
| R-025 | T-010 (re-signed CX version), T-011 | T-016 (re-pilot), T-031 (byte diff vs the re-signed CX version, RC-D-002 row 39) | mapped |
| R-026 | T-027, T-051 | T-041, T-082 (A-013) | mapped |
| R-030 | T-011, T-021 | T-041 (A-004) | mapped |
| R-031..R-034 | T-022, T-025 (hop limit + URL cap) | T-041 (A-004) | mapped |
| R-035 | T-025, T-029 | T-074 (A-014) | mapped |
| R-036 | T-025, T-051, T-074 | T-074 (A-006 diff + denominator check) | mapped |
| R-040 | T-022 (pass 1), T-032 (pass 2), T-028 (skipped-item copies internal, RC-D-003) | T-041 (A-002) | mapped |
| R-041 | T-024, T-027, T-012 (companion items, RC-D-003) | T-041, T-082 | mapped |
| R-042 | T-003, T-024 | T-003 PI gate (Q-020 b), T-082 (A-002) | mapped |
| R-043 | T-028, T-052 (full text), T-053 (display cap) | T-095 (A-007) | mapped |
| R-044 | T-020, T-022, T-032, T-011, T-021, T-023, T-026, T-015 (RC-D-003) | T-041 (A-021) | mapped |
| R-045 | T-010, T-013, T-012, T-020 (`_NA_`, temporary part answer, RC-D-003) | T-031 | mapped (RC-D-002 N35) |
| R-050 | T-012, T-028, T-051 (`contract_version`) | T-095 (A-007) | mapped |
| R-051 | T-051..T-053 (projection, history parameter) | T-054, T-095 (A-007) | mapped |
| R-052 | T-050, T-052, T-053 | A-019, T-095 | mapped |
| R-053 | T-053 (Q-021 a residual) | T-095 | mapped |
| R-054 | T-053 (guard) | T-095 (A-009) | mapped |
| R-055 | T-051, T-052; T-097 wave-window check | T-054, T-095 | mapped |
| R-056 | T-050, T-051, T-052 (release flag), T-074 (load hidden), T-095 (release) | T-054, T-095 | mapped |
| R-057 | T-050, T-028, T-052, T-053 | T-095 (A-007) | mapped (RC-D-002 N35) |
| R-058 | T-024 (e-mails), T-028, T-052, T-053 | T-095 (A-007) | mapped (RC-D-002 N35) |
| R-059 | T-014, T-029 (`text_source`), T-028, T-090 (translation table, methods note) | T-095, A-017 | mapped (RC-D-002 N35) |
| R-070 | T-070 (DEC-019) | T-074 (A-005) | mapped |
| R-071 | T-070 (filter, transfer-owner exception) | T-074 | mapped |
| R-072 | T-073 | T-074 | mapped |
| R-073 | T-051, T-074 | T-054, T-074 (A-006) | mapped |
| R-074 | T-001, T-029 | T-074 (A-015) | mapped |
| R-075 | T-029, T-074 | T-074 (A-005) | mapped |
| R-076 | T-001 (counts), T-029 (all pages) | T-072, T-074 | mapped |
| R-077 | T-034, T-070, T-074 | T-074 (A-022), T-081 | mapped |
| R-080 | T-082 | T-083 (A-008) | mapped |
| R-081 | T-024 | T-082 (A-016) | mapped |
| R-082 | T-080, T-081, T-083 | T-083 | mapped |
| R-083 | T-082 | T-083 | mapped |
| R-084 | T-040, T-041 | PI (A-020) | mapped |
| R-085 | T-060 | A-018 | mapped |
| R-086 | T-080, T-081, T-082 | T-083 | mapped |
| R-087 | T-010 (§4.3 text), T-060 | T-031, A-018 | mapped |
| R-090 | T-090, T-015, T-062 (date-origin map, RC-D-003) | PI (A-017) | mapped |
| A-001 | T-010 | PI | mapped |
| A-002 | T-082 | PI | mapped |
| A-003 | T-040, T-041 | T-041 | mapped |
| A-004 | T-040, T-041 | T-041 | mapped |
| A-005 | T-074 | PI | mapped |
| A-006 | T-054 (rehearsal), T-074 | PI | mapped |
| A-007 | T-095 | PI | mapped |
| A-008 | T-083 | PI | mapped |
| A-009 | T-095 | agent | mapped |
| A-010 | T-040, T-041 | agent | mapped |
| A-011 | T-040, T-041 | agent + PI | mapped |
| A-012 | T-040, T-041 | PI | mapped |
| A-013 | T-041, T-082 | agent | mapped |
| A-014 | T-074 | agent | mapped |
| A-015 | T-074 | PI | mapped |
| A-016 | T-082 | PI | mapped |
| A-017 | T-090 | PI | mapped |
| A-018 | T-060 | PI | mapped |
| A-019 | T-050 | PI | mapped |
| A-020 | T-040, T-041 | agent + PI | mapped |
| A-021 | T-040, T-041 | agent | mapped |
| A-022 | T-034, T-074 | PI | mapped |
| C-001 | T-022, T-023 (spans only, DEC-010 a); T-022, T-032 (named selections, RC-D-002 row 33) | T-031 (incl. the named selections, RC-D-002 N30) | enforced by review |
| C-002 | Simone-run paid steps: T-002, T-016, T-041, T-072, T-073, T-096; T-081 per DP | integrator | gate |
| C-003 | all cards | integrator | gate |
| C-004 | T-020; T-026 (pooled Stage 6 split, RC-D-002 row 34) | T-041 (A-021, A-010) | enforced by test |
| C-005 | T-034, T-051, T-074 | T-074 denominator check | enforced by check |
| C-006 | T-040, T-080, T-082 | T-031 (grep for pilot v1 inputs) | enforced by review |
| C-007 | T-012, T-013 (release versioning), T-030, T-060, T-062 (DEC-013 a as amended by C3 a) | T-031 (pin test) | enforced by test |
| C-008 | all | T-031 (no write path under `inputs/`) | boundary |
| N-001 | T-070 filter (transfer-owner exception) | T-074 | guard |
| N-002 | T-081 scope note | integrator | guard |
| N-003 | T-053 | T-095 (A-009) | guard |
| N-004 | T-025, T-029 | T-031 (diff scope) | guard |
| N-005 | T-034 (only the 114) | T-031 | guard |
| N-006 | T-095 boundary | integrator | guard |
| N-007 | T-082, T-090 boundary | integrator | guard |

## Lanes

| Lane | Display name | Persona |
|---|---|---|
| researcher | You | researcher (human) |
| integrator | Plan integrator | researcher (agent session acting for the PI, DEC-012 a) |
| eng-a | Engineer A | engineer |
| eng-b | Engineer B (code integrator) | engineer |
| eng-c | Engineer C | engineer |
| colin | Colin (API / website) | Colin; fallback engineer under PI sign-off |
| reviewer | Independent reviewer | engineer or researcher, fresh context, read-only (T-096) |
| berivox | Berivox review (Harsh, Geet) | human reviewers (RC-D-001 D): T-031, plus non-blocking review of card PRs into `reclass/v2.7`† after merge; findings as GitHub issues labelled `reclass-v2.7` |
| quality | Agent-read coordinator | researcher |

## Task graph

| Task | Lane | Waves | Status | Requires | Soft | Enables | Resources | Delivers | Write claim | Researcher gates | Acceptance IDs |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T-001 | eng-b | W1 | blocked | none | none | T-029, T-072 | RS-004, RS-006, RS-007, RS-025, RS-036 | none | spikes folder (`count-backfill.json`, `SPIKE-T001*`); droplet `~/reclass-spike-*/` | PI authorises read-only droplet SSH | A-015 |
| T-002 | eng-c | W2 | blocked | T-010, T-013 | none | T-003, T-021, T-025 | RS-004, RS-008, RS-009, RS-012, RS-015, RS-024, RS-031 | none | spikes folder, files prefixed `SPIKE-T002*` | PI approves the paid spike budget; Simone runs the paid command (red line 4, ruling 2026-10-28) | A-004, A-021 |
| T-003 | eng-c | W3 | pending | T-002 | none | T-024 | RS-009, RS-011, RS-025 | none | spikes folder, files prefixed `SPIKE-T003*` | PI approves metric and threshold (Q-020 b) and sets the website display cap (DEC-016 c) | A-002 |
| T-010 | integrator | W1 | pending | none | T-013 | T-002, T-011, T-012, T-016, T-022, T-040, T-050, T-060, T-061, T-063, T-090 | RS-004, RS-010, RS-011, RS-024, RS-026, RS-039 | D-001 | `codebook/codebook.yaml`† and the three (generated) contract files | PI writes or line-edits every coding rule; PI approves the item template (r2#59) and signs the CX items one by one (CX-01.3†); PI signs the codebook hash (A-001); push gate | A-001 |
| T-011 | eng-a | W3 | pending | T-010, T-013, T-016 | none | T-015, T-021, T-023, T-026 | RS-013, RS-024 | none | `g3o/classify/questions/v27/`† | PI approves question wording that is not verbatim contract or CX text; push gate | A-011, A-012 |
| T-012 | eng-b | W2 | pending | T-010, T-013 | none | T-015, T-021, T-022, T-024, T-026, T-027, T-028, T-050, T-060, T-090 | RS-010 | none | `contract.py`, `schema.py`, enum modules, schema test; the inventory file | none beyond push | A-011, A-013 |
| T-013 | eng-b | W1 | pending | none | T-010 | T-002, T-011, T-012, T-016, T-022, T-032 | RS-010, RS-013, RS-039 | none | `g3o/codebook/`†, `codebook/schema.json`†, `tests/test_codebook*.py`†, the codebook step in `.github/workflows/ci.yml` | PI approves the item template and generator checks (r2#59); push of the branch | A-001 |
| T-014 | eng-a | W2 | pending | none | none | T-022, T-025 | RS-016 | none | `g3o/scrape/html.py`, the stored-record hunk of `g3o/run/presweep/stage_scrape.py`, their tests | push of the branch | none |
| T-015 | eng-a | W4 | pending | T-011, T-012, T-022, T-027 | none | T-026, T-028 | RS-012 | none | `g3o/common/source_fields.py`† and its tests | push of the branch | none |
| T-016 | integrator | W2 | pending | T-010, T-013 | none | T-011 | RS-004, RS-005, RS-008, RS-009, RS-024, RS-031 | none | re-pilot folder `agent-workspace/2026-10-27-reclass-plan/repilot-v27/`† | PI approves the cost estimate; Simone runs the paid command via `! <command>` (red line 4); PI rules on the results | none |
| T-020 | eng-a | W1 | pending | none | T-002 | T-021, T-022, T-023 | RS-004, RS-014, RS-024 | none | the two new files | none beyond push | A-021 |
| T-021 | eng-a | W4 | pending | T-002, T-011, T-012, T-020, T-027 | none | T-023, T-025, T-030 | RS-012, RS-019 | none | the new modules and tests | none beyond push | A-011, A-013 |
| T-022 | eng-c | W3 | pending | T-010, T-012, T-013, T-014, T-020 | none | T-015, T-023, T-024, T-025, T-032 | RS-015 | none | the listed extract files | PI approves the nano prompt text; push gate | A-003, A-021 |
| T-023 | eng-a | W5 | pending | T-011, T-020, T-021, T-022, T-027 | none | T-026, T-032 | RS-012 | none | the new modules and tests | none beyond push | A-003 |
| T-032 | eng-c | W6 | pending | T-013, T-022, T-023 | none | T-024, T-030 | RS-015 | none | `g3o/extract/pass2_support.py`† and its tests | PI approves the pass-2 nano prompt text; push gate | A-003, A-021 |
| T-024 | eng-c | W7 | pending | T-003, T-012, T-022, T-032 | none | T-026, T-028, T-041 | none | none | `g3o/common/support_check.py`† and its tests | push of the branch | A-002, A-016 |
| T-025 | eng-b | W5 | pending | T-002, T-014, T-021, T-022 | none | T-029, T-030 | RS-016 | none | new modules `g3o/scrape/follow.py`†, `g3o/run/presweep/stage_follow.py`† and their tests | PI sets the per-institution URL cap value after T-002; push of the branch | A-004, A-014 |
| T-026 | eng-a | W8 | pending | T-011, T-012, T-015, T-023, T-024, T-027 | none | T-028 | RS-011, RS-014 | none | the listed Stage 6 files and tests | push of the branch | A-010 |
| T-027 | eng-b | W3 | pending | T-012 | none | T-015, T-021, T-023, T-026, T-028, T-050 | RS-012, RS-013, RS-014 | none | new module `g3o/common/jev_record.py`† and its tests | push of the branch | A-013 |
| T-028 | eng-a | W9 | pending | T-012, T-015, T-024, T-026, T-027, T-050 | none | T-030, T-052, T-090 | RS-018 | none | `g3o/persist/writer.py` and its tests | push of the branch | A-007, A-017 |
| T-030 | eng-b | W10 | pending | T-021, T-025, T-028, T-032 | none | T-029 | none | none | the listed orchestrator, config, telemetry and e2e files; merges of the new-run card branches into `reclass/v2.7`† | push of the integration branch | none |
| T-029 | eng-a | W11 | pending | T-001, T-025, T-030 | none | T-034, T-035 | RS-017 | none | new package `g3o/run/backfill/`† and its tests | push of the branch | A-005, A-015 |
| T-034 | eng-a | W12 | pending | T-029 | none | T-035 | RS-026 | none | `g3o/run/backfill/transfers.py`† and its tests | push of the branch | A-022 |
| T-035 | eng-b | W13 | pending | T-029, T-034 | none | T-031, T-041 | none | D-002 | `g3o/cli.py` hunks, the two pin files, e2e test additions; merges of T-029 and T-034 into `reclass/v2.7`† | push of the integration branch | none |
| T-031 | berivox | W14 | pending | T-035 | none | T-071 | none | none | the review file only | none | none |
| T-040 | integrator | W2 | pending | T-010 | none | T-041 | RS-005, RS-008, RS-009, RS-011, RS-024 | none | `tests/fixtures/v27/`† and the label sheet | PI labels and approves expected values for real-page fixtures | A-003, A-004, A-010, A-011, A-012, A-020, A-021 |
| T-041 | eng-b | W14 | blocked | T-024, T-035, T-040 | none | T-054, T-060, T-071 | RS-031 | none | the fixture-run folder | PI approves the cost estimate and runs the paid fixture run and the real-id subset via `! <command>`; SSH to read the subset's stored pages needs PI authorisation; PI rules on fixture failures | A-003, A-004, A-010, A-011, A-012, A-013, A-020, A-021, A-022 |
| T-050 | integrator | W4 | pending | T-010, T-012, T-027 | none | T-028, T-051 | RS-020, RS-023 | D-007 | `C:/Users/spaci/repos/G3O/planning/handoffs/D-007-interface-spec.md`† | PI approves the spec before it is sent; posting the GitHub issues is an external message | none |
| T-051 | colin | W5 | pending | T-050 | none | T-052, T-054 | RS-020 | none | `sql/021*`†, `sql/down/021*`†, `scripts/load_corrections.py`† | PI authorises creation of and writes to the disposable branch used by this card's self-check; Neon branch creation, snapshots and writes each need a named PI gate; Neon branches and snapshots are free (Simone, 2026-10-28), so the agent runs these commands itself once the PI gate has passed; live apply is the T-055 gate; push on Colin's branch | none |
| T-052 | colin | W10 | pending | T-028, T-051 | none | T-053, T-054, T-055, T-074 | RS-023 | none | Colin's files listed in Outputs | deploy to staging only (production deploy is T-055); push on Colin's branch | none |
| T-053 | colin | W11 | pending | T-052 | none | T-095 | RS-022 | none | Colin's files listed in Outputs | PI approves public copy and the display cap value; deploy gate | none |
| T-054 | eng-b | W15 | blocked | T-041, T-051, T-052 | none | T-055, T-074 | none | none | the disposable Neon branch; rehearsal folder† | PI authorises creation of and writes to the disposable branch; Neon branch creation, snapshots and writes each need a named PI gate; Neon branches and snapshots are free (Simone, 2026-10-28), so the agent runs these commands itself once the PI gate has passed | none |
| T-055 | colin | W16 | blocked | T-052, T-054 | none | T-071, T-074 | none | none | live DB schema (migration 021); production worker; golive folder† | PI authorises the live DB write (snapshot + apply) and the production deploy; Neon branch creation, snapshots and writes each need a named PI gate; Neon branches and snapshots are free (Simone, 2026-10-28), so the agent runs these commands itself once the PI gate has passed | none |
| T-060 | integrator | W15 | pending | T-010, T-012, T-041 | none | T-071 | RS-029 | D-008 | `planning/handoffs/D-008-procurement-delta.md`† | PI approves delta text; posting and email are external | none |
| T-061 | integrator | W2 | pending | T-010 | none | T-071 | RS-033 | none | `planning/handoffs/validation-notice.md`†; one mailbox file | PI approves the notice text | none |
| T-062 | integrator | W18 | pending | T-071 | none | none | RS-038 | D-009 | `planning/handoffs/D-009-ai-text-delta.md`† | PI approves delta text; sending is external | none |
| T-063 | integrator | W2 | pending | T-010 | none | none | RS-040 | D-010 | `planning/handoffs/D-010-multilingual-heads-up.md`† | PI approves the text; sending is external | none |
| T-071 | eng-a | W17 | blocked | T-031, T-041, T-055, T-060, T-061 | none | T-062, T-070 | none | none | droplet checkout; deploy folder† | PI approves merge and deploy; SSH authorisation; external gate — wave 5 published | none |
| T-070 | eng-a | W18 | blocked | T-071 | none | T-072 | RS-026, RS-030 | none | freeze folder† | PI confirms the freeze date | none |
| T-072 | eng-a | W19 | blocked | T-001, T-070 | none | T-073 | none | none | smoke run dir; smoke folder† | paid run — the agent prepares the exact command and cost estimate and Simone runs it via `! <command>` (red line 4, 2026-10-28); SSH authorisation; PI reviews the smoke report | none |
| T-073 | eng-a | W20 | blocked | T-072 | none | T-074 | none | none | back-fill run dir | paid run — the agent prepares the exact command and a cost estimate from the T-072 projection, and Simone runs it via `! <command>` (red line 4); SSH authorisation | none |
| T-074 | eng-a | W21 | blocked | T-052, T-054, T-055, T-073 | none | T-080, T-082, T-095 | none | D-003 | live DB under the release id; reconciliation folder† | PI approves live writes (snapshot + load); Neon branch creation, snapshots and writes each need a named PI gate; Neon branches and snapshots are free (Simone, 2026-10-28), so the agent runs these commands itself once the PI gate has passed | none |
| T-080 | eng-b | W22 | pending | T-074 | none | T-081 | none | none | quality sample files† | none | none |
| T-081 | quality | W23 | blocked | T-080 | none | T-082 | none | none | `quality/reads/`† | PI approves the read prompt and authorises the swarm launch (see DP-065); SSH authorisation for the page pull | none |
| T-082 | integrator | W24 | pending | T-074, T-081 | none | T-083 | none | D-005 | `quality/QUALITY-PACKET.md`† | none | none |
| T-083 | researcher | W25 | pending | T-082 | none | T-095 | none | none | `quality/PI-AUDIT.md`† | this card is the gate | none |
| T-090 | integrator | W10 | pending | T-010, T-012, T-028 | none | T-095 | none | D-006 | the docs files in the G3O repo listed in Outputs (and the #175 README text only, not its file in another repo) | PI approves public prose; push | none |
| T-095 | colin | W26 | blocked | T-053, T-074, T-083, T-090 | none | T-096 | none | D-004 | release flag; deploys; release folder† | PI release sign-off; deploy; live DB write (release flag) | none |
| T-096 | reviewer | W27 | pending | T-095 | none | none | none | none | `planning/reviews/TRACE.md`† | paid rerun — the agent prepares the command and cost estimate and Simone runs it via `! <command>` (red line 4); SSH authorisation; PI approves the agreement criterion | none |
| T-097 | integrator | W1-W27 | pending | none | none | none | none | none | SPEC.md, RESOURCES.md, PLAN.md, CHANGELOG.md (sole writer after lock) | PI approves every delta | none |

## Parallel waves

| Wave | Target | Ready condition | Lanes/tasks | Collision result | Integration/review gate |
|---|---|---|---|---|---|
| W1 | after lock | lock + per-card gates | eng-b: T-001, integrator: T-010, eng-b: T-013, eng-a: T-020, T-097 (standing W1-W27) | disjoint claims (one writer per path) | T-001: PI authorises read-only droplet SSH; T-010: PI writes or line-edits every coding rule; PI approves the item template and signs the CX items one by one; PI signs the codebook hash (A-001); push gate; T-013: PI approves the item template and generator checks (r2#59); push of the branch; T-020: none beyond push (RC-D-002 N34: T-002 moved to W2, T-013 added) |
| W2 | after W1 | verified: T-010, T-013 | eng-c: T-002, eng-b: T-012, tbd: T-014, tbd: T-016, integrator: T-040, integrator: T-061, integrator: T-063 | disjoint claims (one writer per path) | T-002: PI approves the paid spike budget; Simone runs the paid command (red line 4, ruling 2026-10-28); T-012: none beyond push; T-014: push of the branch; T-016: PI approves the cost estimate; Simone runs the paid command; PI rules on the results; T-040: PI labels and approves expected values for real-page fixtures; T-061: PI approves the notice text; T-063: PI approves the text; sending is external |
| W3 | after W2 | verified: T-002, T-010, T-012, T-013, T-014, T-016, T-020 | eng-c: T-003, eng-a: T-011, eng-c: T-022, eng-b: T-027 | disjoint claims (one writer per path) | T-003: PI approves metric and threshold (Q-020 b) and sets the website display cap (DEC-016 c); T-011: PI approves question wording that is not verbatim contract or CX text; push gate; T-022: PI approves the nano prompt text; push gate; T-027: push of the branch |
| W4 | after W3 | verified: T-002, T-010, T-011, T-012, T-020, T-022, T-027 | eng-a: T-021, integrator: T-050, tbd: T-015 | disjoint claims (one writer per path) | T-021: none beyond push; T-050: PI approves the spec before it is sent; posting the GitHub issues is an external message; T-015: push of the branch |
| W5 | after W4 | verified: T-002, T-011, T-020, T-021, T-022, T-027, T-050 | eng-a: T-023, eng-b: T-025, colin: T-051 | disjoint claims (one writer per path) | T-023: none beyond push; T-025: PI sets the per-institution URL cap value after T-002; push of the branch; T-051: PI authorises creation of and writes to the disposable branch used by this card's self-check; Neon branch creation, snapshots and writes each need a named PI gate; Neon branches and snapshots are free (Simone, 2026-10-28), so the agent runs these commands itself once the PI gate has passed; live apply is the T-055 gate; push on Colin's branch |
| W6 | after W5 | verified: T-022, T-023 | eng-c: T-032 | disjoint claims (one writer per path) | T-032: PI approves the pass-2 nano prompt text; push gate |
| W7 | after W6 | verified: T-003, T-012, T-022, T-032 | eng-c: T-024 | disjoint claims (one writer per path) | T-024: push of the branch |
| W8 | after W7 | verified: T-011, T-012, T-023, T-024, T-027 | eng-a: T-026 | disjoint claims (one writer per path) | T-026: push of the branch |
| W9 | after W8 | verified: T-012, T-024, T-026, T-027, T-050 | eng-a: T-028 | disjoint claims (one writer per path) | T-028: push of the branch |
| W10 | after W9 | verified: T-010, T-012, T-021, T-025, T-028, T-032, T-051 | eng-b: T-030, colin: T-052, integrator: T-090 | disjoint claims (one writer per path) | T-030: push of the integration branch; T-052: deploy to staging only (production deploy is T-055); push on Colin's branch; T-090: PI approves public prose; push |
| W11 | after W10 | verified: T-001, T-025, T-030, T-052 | eng-a: T-029, colin: T-053 | disjoint claims (one writer per path) | T-029: push of the branch; T-053: PI approves public copy and the display cap value; deploy gate |
| W12 | after W11 | verified: T-029 | eng-a: T-034 | disjoint claims (one writer per path) | T-034: push of the branch |
| W13 | after W12 | verified: T-029, T-034 | eng-b: T-035 | disjoint claims (one writer per path) | T-035: push of the integration branch |
| W14 | after W13 | verified: T-024, T-035, T-040 | berivox: T-031, eng-b: T-041 | disjoint claims (one writer per path) | T-031: none; T-041: PI approves the cost estimate and runs the paid fixture run and the real-id subset via `! <command>`; SSH to read the subset's stored pages needs PI authorisation; PI rules on fixture failures |
| W15 | after W14 | verified: T-010, T-012, T-041, T-051, T-052 | eng-b: T-054, integrator: T-060 | disjoint claims (one writer per path) | T-054: PI authorises creation of and writes to the disposable branch; Neon branch creation, snapshots and writes each need a named PI gate; Neon branches and snapshots are free (Simone, 2026-10-28), so the agent runs these commands itself once the PI gate has passed; T-060: PI approves delta text; posting and email are external |
| W16 | after W15 | verified: T-052, T-054 | colin: T-055 | disjoint claims (one writer per path) | T-055: PI authorises the live DB write (snapshot + apply) and the production deploy; Neon branch creation, snapshots and writes each need a named PI gate; Neon branches and snapshots are free (Simone, 2026-10-28), so the agent runs these commands itself once the PI gate has passed |
| W17 | after W16 | verified: T-031, T-041, T-055, T-060, T-061 | eng-a: T-071 | disjoint claims (one writer per path) | T-071: PI approves merge and deploy; SSH authorisation; external gate — wave 5 published |
| W18 | after W17 | verified: T-071 | eng-a: T-070, integrator: T-062 | disjoint claims (one writer per path) | T-070: PI confirms the freeze date; T-062: PI approves delta text; sending is external |
| W19 | after W18 | verified: T-001, T-070 | eng-a: T-072 | disjoint claims (one writer per path) | T-072: paid run — the agent prepares the exact command and cost estimate and Simone runs it via `! <command>` (red line 4, 2026-10-28); SSH authorisation; PI reviews the smoke report |
| W20 | after W19 | verified: T-072 | eng-a: T-073 | disjoint claims (one writer per path) | T-073: paid run — the agent prepares the exact command and a cost estimate from the T-072 projection, and Simone runs it via `! <command>` (red line 4); SSH authorisation |
| W21 | after W20 | verified: T-052, T-054, T-055, T-073 | eng-a: T-074 | disjoint claims (one writer per path) | T-074: PI approves live writes (snapshot + load); Neon branch creation, snapshots and writes each need a named PI gate; Neon branches and snapshots are free (Simone, 2026-10-28), so the agent runs these commands itself once the PI gate has passed |
| W22 | after W21 | verified: T-074 | eng-b: T-080 | disjoint claims (one writer per path) | T-080: none |
| W23 | after W22 | verified: T-080 | quality: T-081 | disjoint claims (one writer per path) | T-081: PI approves the read prompt and authorises the swarm launch (see DP-065); SSH authorisation for the page pull |
| W24 | after W23 | verified: T-074, T-081 | integrator: T-082 | disjoint claims (one writer per path) | T-082: none |
| W25 | after W24 | verified: T-082 | researcher: T-083 | disjoint claims (one writer per path) | T-083: this card is the gate |
| W26 | after W25 | verified: T-053, T-074, T-083, T-090 | colin: T-095 | disjoint claims (one writer per path) | T-095: PI release sign-off; deploy; live DB write (release flag) |
| W27 | after W26 | verified: T-095 | reviewer: T-096 | disjoint claims (one writer per path) | T-096: paid rerun — the agent prepares the command and cost estimate and Simone runs it via `! <command>` (red line 4); SSH authorisation; PI approves the agreement criterion |

## Task cards

### T-001 — Count stored-text availability for documented and unclear institutions

Status: blocked
Type: spike
Priority: required
Spec refs: R-074, R-076, A-015
Decision refs: none

#### Objective
Per-institution counts for the latest run of every documented and every unclear institution: pages, pages with at least 200 characters of usable stored text, and raw `%PDF` pages. Also whether the RS-006 scratch files still exist, the droplet's free disk, and the run-directory footprint (PF-017). Blocked until the PI authorises read-only droplet SSH.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| RS-004 `enumerate.py`, `count_pages.py` | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-unclear-screen/` | as of 2026-10-27 | stop, report |
| RS-025 documented and unclear lists | Drive (RS-025 / RS-036 strata) | parsed | stop, report |
| RS-007 stored runs | droplet `/home/g3o/runs` | read-only | report UNVERIFIED |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Counts file | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/spikes/count-backfill.json`† | T-029, T-072, integrator | per-uid counts for both groups (pages, pages ≥200 chars, raw `%PDF`), group totals, script hash |
| Spike report | `.../spikes/SPIKE-T001.md`† | T-029, T-072, PI | totals reconciled to RS-025 (9,705 documented; 27,648 unclear); free disk and run-dir footprint; RS-006 scratch status |

#### Execution resources
- Persona/role: engineer
- Tools/connectors: Bash, SSH with `id_ed25519_g3o` only (memory: ssh-keys-blocked-by-codex-sandbox-ace), Python
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-b/`† (scripts, branched from `origin/main` `375f1ff`; never the shared checkout `C:/Users/spaci/repos/G3O`); outputs to the spikes folder above; droplet scratch `~/reclass-spike-*/`

#### Dependencies
- Requires: none
- Enables: T-029, T-072
- Can run with: T-010, T-013, T-020, T-097
- Researcher gates: PI authorises read-only droplet SSH

#### Ownership and collision control
- Read scope: RS-004, RS-025, RS-007 (read-only)
- Write claim: spikes folder (`count-backfill.json`, `SPIKE-T001*`); droplet `~/reclass-spike-*/`
- Shared surfaces: spikes folder shared with T-002/T-003 by distinct file prefixes

#### Procedure boundary
- Included: enumeration and counting only; disk and footprint read-out
- Excluded: fetching, any pipeline run, any DB access
- Fixed decisions: R-076 v001.4 page sets (all pages of the latest run, both groups)

#### Spec-change reporting
- Spec version: SPEC v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: usable stored text is missing for more than 5% of either group (changes the R-074 re-scrape load), or free disk cannot hold the projected back-fill run directories
- Stop boundary: none (report only)
- Safe continuation: all
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: group totals reconcile with RS-025 counts (9,705 documented; 27,648 unclear)
- Independent review: integrator re-runs the count on 20 uids
- Acceptance tests: feeds A-015
- Failure/rollback: delete droplet scratch; spike outputs are read-only evidence

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Counts file and spike report written, reconciliation note against RS-025 included, integrator's 20-uid re-run matches.

#### Chunking trigger
Runtime over 2 hours → split by run.

### T-002 — Measure jev two-pass cost, latency and fan-out on a small set

Status: blocked
Type: spike
Priority: critical-path
Spec refs: R-002, R-003, R-004, R-008, R-032, R-044, C-002, C-004
Decision refs: DEC-003, DEC-008, DEC-010

#### Objective
Measured on at most 50 real pages, using proxy questions (re-pilot 2 + CX pilot v2), for pass 1 + segmentation + pass 2:
- per-page and per-activity jev call counts, tokens, latency and failure rate;
- link fan-out per page and per institution within 3 hops (PF-010; Simone sets the R-032 URL cap from it, item 22 b);
- Batch round-trip latency and the number of sequential rounds per run (PF-016; feeds DEC-003 d);
- a calibrated token estimator per script, Latin / CJK / Thai, against jev's token counts (DEC-008 c);
- a nano supporting-quote extraction leg on the same pages: verbatim quotes for the positive / substantive pass-1 proxy codes, written to `SPIKE-T002-answers.jsonl`† so T-003 has quote-vs-page pairs to calibrate on (review M4);
- RC-D-002 row 37 (ruling N2 a): the extractor leg measures the extractor prompts generated by T-013 from the signed codebook (T-010). Sizing drivers: the r2#41 round structure (R-008), C11 functions, four safeguard questions per activity (r2#10), CX-61 over the page, `governance_direction`, `service_domain`, X35 per (code, quote), X30 every pair, X31 pooled with split. X21 is mostly deterministic now (r2#25), and A05's relationship moves to pass 2. The free question-load count comes first: it exists as `planning/t010/question-load.md` (r2#52), and the PI kept the full question set (RC-D-002 L, item 52).

Paid (jev and nano legs, one paid gate): the agent prepares the command and a cost estimate, and Simone runs it.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| RS-004 `unclear2.py` | Drive, `agent-workspace/2026-10-27-unclear-screen/` | as of 2026-10-27 | stop |
| RS-024 `pilot/pilot.py` | Drive | frozen CX pilot v2 | stop |
| RS-009 / RS-008 pages | local corpora | — | stop |
| RS-031 jev and OpenAI keys | environment | valid | stop |
| Signed codebook | T-010 | signed | stop |
| Generated extractor prompts | T-013 generators run on the signed codebook | generated | stop |
| Question-load count (r2#52) | `C:/Users/spaci/repos/G3O/planning/t010/question-load.md` | 2026-10-29 | report |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Spike report | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/spikes/SPIKE-T002.md`† | T-003, T-020, T-021, T-025, DEC-003 d, risk register, PI (URL cap) | cost per 1k pages; p50/p95 latency; chunk counts; fan-out distribution; Batch round count and latency; estimator constant and error per script |
| Raw answers | `.../spikes/SPIKE-T002-answers.jsonl`† | T-003 (quotes), integrator | every request id and response kept; nano quotes with page id and chunk id, one row per (code, quote) |
| Paid-run command | `.../spikes/SPIKE-T002-command.md`† | Simone | exact `! <command>` line plus cost estimate |

#### Execution resources
- Persona/role: engineer
- Tools/connectors: Python, jev client (RS-012), Anthropic Messages client for `claude-haiku-5-5` at medium effort (sync), plus a small Message Batches subset (RC-D-001 A, B); load the `claude-api` skill; records the account's rate-limit tier (RS-037) and confirms how the effort setting is applied
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-c/`† (scripts, branched from `origin/main` `375f1ff`; never the shared checkout `C:/Users/spaci/repos/G3O`); outputs to the spikes folder; Simone's shell for the paid run

#### Dependencies
- Requires: T-010, T-013 (RC-D-002 D, row 37; was: none)
- Enables: T-003, T-021, T-025
- Can run with: T-012, T-014, T-016, T-040, T-061, T-063 (W2)
- Researcher gates: PI approves the paid spike budget; Simone runs the paid command (red line 4, ruling 2026-10-28)

#### Ownership and collision control
- Read scope: RS-004, RS-008, RS-009, RS-024
- Write claim: spikes folder, files prefixed `SPIKE-T002*`
- Shared surfaces: spikes folder shared with T-001/T-003 by distinct prefixes

#### Procedure boundary
- Included: measurement, estimator calibration and the nano quote leg; preparing the paid command
- Excluded: any coding-rule choice; executing any paid call (Simone runs it)
- Fixed decisions: the proxy questions are not v2.7 (jev legs); the extractor leg uses the generated v2.7 prompts (RC-D-002 D); DEC-003 b placement; DEC-008 c token-based chunking

#### Spec-change reporting
- Spec version: SPEC v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: cost or latency makes the back-fill (R-070, R-076 all pages) or R-086 infeasible at scale; jev cannot take segmented context; the fan-out leaves no workable URL cap
- Stop boundary: T-021 design
- Safe continuation: T-010, T-020
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: call counts equal page count × passes; estimator error reported per script; every positive proxy code has a quote row (or a recorded empty result) in `SPIKE-T002-answers.jsonl`
- Independent review: integrator spot-checks 5 request ids against raw answers
- Acceptance tests: none directly (informs A-004, A-021)
- Failure/rollback: none needed (measurement only)

#### Decision points
- DP-001: Composition of the up-to-50-page sample
  - Default: documented and unclear pages in proportion, drawn from RS-008/RS-009
  - Recommendation: include at least 10 CJK/Thai pages and some long PDFs — the estimator and chunking need non-Latin and long-page evidence
- DP-002: Batch timing subset (RC-D-001 B; was: whether to time synchronous nano calls as well as Batch)
  - Default: sync on all pages, plus a small Message Batches subset
  - Recommendation: keep the subset — it is the only source of the Batch round-trip figure for projecting T-073's runtime

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Report with all measured numbers, raw logs and the paid-run record (command, estimate, actual cost) written. Integrator spot-check passed. Fan-out figures handed to Simone for the URL-cap ruling.

#### Chunking trigger
More than 50 pages requested → new paid gate.

### T-003 — Calibrate the fuzzy quote matcher (Q-020 b)

Status: pending
Type: spike
Priority: critical-path
Spec refs: R-042, R-043, A-002
Decision refs: DEC-007, DEC-016

#### Objective
Using pinned `rapidfuzz` (DEC-007 a), choose a metric and threshold for matching quotes against pages, with false-match and false-reject rates on labelled pairs that include non-English pages. Also produce a quote-length distribution for proposing the website display cap (DEC-016 c). The PI approves the metric, the threshold and the cap. RC-D-002 N33: the calibration pairs include quotes matched against chrome text, since the check uses the text the quote came from (r2#48; chrome text from T-014); the DEC-016 c cap proposal stays (r2#17).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| T-002 quotes | spikes folder, `SPIKE-T002-answers.jsonl`† | done | stop |
| RS-011 `check_quotes` | ref `archive/exval-v2.6` `052fcb2` | — | use as baseline only |
| RS-009 pages (43+ languages via RS-025 mix) | local | — | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Spike report | `.../spikes/SPIKE-T003.md`† | T-024, PI | metric, threshold, error table by language/script; `rapidfuzz` version pin, licence and wheel availability for droplet Python |
| Labelled pairs | `.../spikes/SPIKE-T003-pairs.csv`† | T-024, PI | true/false labels, hold-out split marked |
| Display-cap proposal | in `SPIKE-T003.md` | PI, T-050, T-053 | quote-length distribution and a proposed website cap value |

#### Execution resources
- Persona/role: engineer
- Tools/connectors: Python, `rapidfuzz` (pinned)
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-c/`† (scripts, branched from `origin/main` `375f1ff`; never the shared checkout `C:/Users/spaci/repos/G3O`); outputs to the spikes folder

#### Dependencies
- Requires: T-002
- Enables: T-024
- Can run with: T-011, T-022, T-027 (W3)
- Researcher gates: PI approves metric and threshold (Q-020 b) and sets the website display cap (DEC-016 c)

#### Ownership and collision control
- Read scope: T-002 outputs, RS-011, RS-009
- Write claim: spikes folder, files prefixed `SPIKE-T003*`
- Shared surfaces: spikes folder shared by distinct prefixes

#### Procedure boundary
- Included: calibration; length distribution; cap proposal
- Excluded: entailment checking (R-042 checks presence only); choosing the cap (the PI sets it)
- Fixed decisions: DEC-007 a (library), DEC-016 c (cap on the website only, full text in the API)

#### Spec-change reporting
- Spec version: SPEC v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: no threshold separates true from false matches for some script (e.g. CJK); `rapidfuzz` cannot be installed on the droplet
- Stop boundary: T-024
- Safe continuation: others
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: hold-out split; error rates reported on the hold-out
- Independent review: PI labels 30 pairs
- Acceptance tests: A-002 (via T-024, T-041)
- Failure/rollback: n/a

#### Decision points
- DP-003: A single threshold or one per script
  - Default: a single threshold
  - Recommendation: per-script thresholds only where the hold-out error table shows a single one fails — keeps the rule simple unless the evidence forces otherwise
- DP-004: Rule for the proposed website display cap
  - Default: propose the length that covers 90% of quotes
  - Recommendation: propose from the observed distribution and show what share of quotes each candidate cap would truncate — the PI sets the value

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
PI-approved metric and threshold, plus the PI-set display cap, recorded by the integrator. Hold-out error table attached.

#### Chunking trigger
More than 1 day of labelling → split labelling from calibration.

### T-010 — Draft Output Contract v2.7 and the validate-contract v1.5 bump

Status: pending
Type: build
Priority: critical-path
Spec refs: D-001, R-006, R-007, R-010, R-011, R-012, R-013, R-014, R-015, R-016, R-017, R-020, R-021, R-022, R-023, R-024, R-025, R-030, R-040, R-041, R-043, R-044, R-045, R-050, R-087, C-007, A-001
Decision refs: DEC-009, DEC-013, DEC-016

#### Objective
RC-D-002 row 38: the output is the signed codebook `codebook/codebook.yaml`† plus the contract docs generated from it (generators: T-013); the hash is the codebook file's at sign-off (A-001). The first step (RC-D-002 B) is done: the adversarial codebook review, rounds 1 and 2, with the PI's per-item rulings (RS-039; SPEC SRC-10, SRC-11) and the open sub-choices (RC-D-002 J). The PI's choices seed the item slots (ruling 1 a for items that keep their SPEC wording); the final CX text is drafted in the codebook and the PI signs it item by item as CX-01.3† (r2#3). The integrator writes the item template and the generator checks (r2#59) for PI approval. The PI writes or line-edits every coding rule.

PI-signed texts, with a hash:
- the v2.7 extract contract and system prompt;
- the validate contract, labelled **v1.5** (DEC-013 a; v1.4 is taken by `052fcb2`).

Contents:
- procurement's owed §4.3 amendment (R-087, item 26 a), now the removal of purchase language, no longer waiting on procurement's owed text (r2#14; RC-D-002 row 38);
- the free-text routing of DEC-009 a, replaced by the per-item coder column (r2#28; RC-D-002 row 38);
- per-chunk supporting quotes (R-044);
- the supporting-text rule: full text in the API, website display cap (R-043 v001.4; DEC-016 c stays, r2#17).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| RS-010 v2.5 contract docs | G3O `origin/main` | `375f1ff` | stop |
| RS-011 v2.6 rulings | ref `archive/exval-v2.6` `052fcb2` | — | stop |
| RS-004 re-pilot 2 wording | Drive, `unclear2.py` L32-55 | — | stop |
| RS-024 CX-01.2 | Drive | frozen | stop |
| RS-026 WS10 D1-D6 | Drive | — | stop |
| Procurement §4.3 amendment text | no longer an input: §4.3 is the removal of purchase language (r2#14; RC-D-002 row 38). Was: procurement integrator, by email via Simone (procurement DEC-010) | — | — |
| Codebook-review rulings, rounds 1-2, and sub-choices | RS-039; RC-D-002 J, K, L | PI-ruled 2026-10-29 | stop |
| Generators | T-013 | merged | sign the codebook first; generate the contract docs once T-013 merges |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Codebook | `codebook/codebook.yaml`† on branch `reclass/t010-contract`† | T-011, T-012, T-013, T-016, T-022, T-032, T-040, T-050, T-060, T-062, T-063, T-090 | every item in the r2#59 template; signed wording verbatim; `core.*` for v2.7 (RC-D-002 A) |
| Extract contract | `g3o/extract/prompts/output_contract.md` (generated from the codebook) on branch `reclass/t010-contract`† | T-011, T-012, T-022, T-040, T-050, T-060, T-061, T-090 | every A-001 rule present; 9-value verdict (R-015 v001.6); label v2.7 in the setup record (C3 a); §4.3 (R-087) |
| System prompt | `g3o/extract/prompts/system_prompt.md` | same | R-016 amendment to the "chatbot" rule |
| Validate contract | `g3o/validate/prompts/output_contract.md` | same | label v1.5 |
| Signed hash | integrator record | T-031, T-097 | hash of the codebook file at PI sign-off (A-001, RC-D-002 row 1); was: hash of the three files |

#### Execution resources
- Persona/role: integrator (researcher session) for structure and cross-references; the PI writes or line-edits every coding rule (researcher persona drafts no prose)
- Tools/connectors: Read/Edit on the branch; git (push gated)
- Skills/protocols: `planning-output-specification-protocol.md` for ID tagging
- Working directory/environment: session cwd `H:/My Drive/Research/G3O` with absolute paths; contract edits in the integrator worktree `C:/Users/spaci/worktrees/G3O-integrator/`† on branch `reclass/t010-contract`†, branched from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`, which is on `perf/validate-jev-parallel`)

#### Dependencies
- Requires: none
- Soft: T-013 (generators emit the contract docs; see the open note in T-013)
- Enables: T-002, T-011, T-012, T-016, T-022, T-040, T-050, T-060, T-061, T-063, T-090
- Can run with: T-001, T-013, T-020, T-097
- Researcher gates: PI writes or line-edits every coding rule; PI approves the item template (r2#59; approved 2026-10-30 with RC-D-003) and signs the CX items one by one (CX-01.3†, r2#3); PI signs the codebook hash (A-001); push gate

#### Ownership and collision control
- Read scope: inputs above
- Write claim: `codebook/codebook.yaml`† and the three contract files (generated; RC-D-002 row 38)
- Shared surfaces: codebook and contract docs — owned by T-010 until signed, then frozen (changes only by delta); generator code is T-013's

#### Procedure boundary
- Included: contract text, cross-references, §4.3 integration
- Excluded: enums in code (T-012); jev questions (T-011); schema, loader and generators (T-013); procurement's own files
- Fixed decisions: all SPEC v001.4 rulings; DEC-009 a (superseded by the coder column), DEC-013 a (as amended by C3 a), DEC-016 c, R-087; the RC-D-002 rulings (SPEC SRC-10..SRC-12)

#### Spec-change reporting
- Spec version: SPEC v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a ruling cannot be written without contradicting another (e.g. R-014 vs R-041); the §4.3 text conflicts with a v2.7 rule
- Stop boundary: T-011, T-012
- Safe continuation: T-020, spikes
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: checklist mapping R-010..R-044 and R-087 to contract section anchors; every codebook item fills the r2#59 template (RC-D-002 row 38)
- Independent review: T-031 reviewer cross-check
- Acceptance tests: A-001
- Failure/rollback: branch only

#### Decision points
- DP-005: (closed by RC-D-002 row 38, r2#14: §4.3 is the removal of purchase language and no longer waits on procurement's text) How to proceed if procurement's §4.3 text has not arrived when the rest is ready
  - Default: T-011 and T-012 wait for the signed contract hash; drafting of T-010 itself may proceed with a §4.3 placeholder
  - Recommendation: T-011 and T-012 wait for the signed contract hash; drafting of T-010 itself may proceed with a §4.3 placeholder — consistent with T-011 / T-012 requiring the signed contract (stop)

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Codebook and the three generated files on the branch, §4.3 included, checklist complete, PI-signed codebook hash recorded by the integrator (RC-D-002 row 38).

#### Chunking trigger
More than 2 review rounds → split extract contract from validate contract.

### T-011 — Build the v2.7 jev question sets (pass 1, pass 2, Stage 6)

Status: pending
Type: build
Priority: critical-path
Spec refs: R-002, R-004, R-005, R-006, R-015, R-016, R-020, R-021, R-022, R-023, R-024, R-025, R-030, G-005
Decision refs: DEC-009, DEC-010

#### Objective
Versioned jev question and choice sets implementing the signed contract:
- pass 1, per page;
- pass 2, per activity, with the activity's span marked in the page text (DEC-010 a);
- Stage 6.

Year Choice questions for `year_announced` and `year_deployed`, and the CX-60/61 normalisation as Choice questions (DEC-009 a). CX-01.2 wording byte-identical to RS-024.

RC-D-002 row 39: CX wording is byte-identical to the re-signed version (CX-01.3†), not RS-024 (r2#3). Questions are generated from the codebook by T-013 and ordered by round and gate (R-008, r2#41). Year candidates come from C16 / r2#50, with calendar conversion (D-010, T-063); dynamic choice sets only for year candidates (the r2#2 (a) path was not chosen). The Stage 6 set adds X29-X31.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| T-010 signed contract | branch `reclass/t010-contract`† | signed | stop |
| RS-024 frozen CX-01.2 wording | Drive | frozen | stop (history only after RC-D-002 row 39) |
| Re-signed CX wording (CX-01.3†) | codebook, T-010 | signed | stop |
| T-013 generators | branch `reclass/t013-codebook`† | merged | stop |
| T-016 re-pilot results | re-pilot folder | PI-ruled | stop |
| Calendar and fiscal-year conversion rule | multilingual subproject via T-063 (D-010) | received | stop the year-candidate questions; report |
| RS-013 question-set pattern | G3O `origin/main` | `375f1ff` | follow the pattern |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Question sets | `g3o/classify/questions/v27/{page,activity,institution}.json`† + `JEV_QUESTION_SET_VERSION` on branch `reclass/t011-questions`† | T-021, T-023, T-026, T-040 | each question cites its contract section and codebook item id and hash; version stamped; CX text identical to the re-signed version (RC-D-002 row 39) |

#### Execution resources
- Persona/role: engineer, with researcher review
- Tools/connectors: Python, JSON schema validation
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-a/`† on `reclass/t011-questions`†, branched from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-010, T-013, T-016 (RC-D-002 rows 39, N34)
- Enables: T-015, T-021, T-023, T-026
- Can run with: T-003, T-022, T-027 (W3)
- Researcher gates: PI approves question wording that is not verbatim contract or CX text; push gate

#### Ownership and collision control
- Read scope: T-010 outputs, RS-024, RS-013
- Write claim: `g3o/classify/questions/v27/`†
- Shared surfaces: none

#### Procedure boundary
- Included: question text and choice sets
- Excluded: stage code
- Fixed decisions: R-025 wording (the re-signed version); the codebook coder column (replaces DEC-009 a routing); DEC-010 a span marking

#### Spec-change reporting
- Spec version: SPEC v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a contract field has no closed choice set (affects DEC-009 a routing)
- Stop boundary: the affected question
- Safe continuation: other questions
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: diff of CX questions against the re-signed CX version is empty (RC-D-002 row 39); schema validation passes
- Independent review: T-031
- Acceptance tests: A-011, A-012 (via T-041)
- Failure/rollback: branch

#### Decision points
- DP-006: (obsolete per RC-D-002 row 39: year candidates come from C16 / r2#50 with calendar conversion) Bounds of the year choice set for `year_announced` / `year_deployed`
  - Default: the engineer proposes a closed range covering every year present in published v2.5 data, plus a "not stated" choice
  - Recommendation: same, with the PI approving the range and the "not stated" wording — a data-derived range avoids inventing bounds

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Sets merged to `reclass/v2.7`† with version stamp; CX diff empty; PI-approved non-verbatim wording recorded.

#### Chunking trigger
Split per pass.

### T-012 — Update enums, schema and contract constants in code

Status: pending
Type: build
Priority: critical-path
Spec refs: R-015, R-020, R-021, R-022, R-023, R-024, R-050, C-007
Decision refs: DEC-005, DEC-013

#### Objective
`contract.py` and `schema.py` carry:
- the 8-value page verdict replacing `genai_evidence`, in both enum copies (including the NoNA variants);
- the new CX columns;
- an explicit `contract_version` field on every row schema (DEC-005 a).

RC-D-002 row 40: enums and schema are generated from the codebook (T-013); `contract_version` becomes the codebook release label + setup pointer + `evidence_channel` (r2#32, R-050 v001.6); the page verdict has 9 values (R-015 v001.6). Schema-test fix (ruling N3 a; schedule N26, placed here by RC-D-002 L): freeze `PILOT_V1_DATA_COLUMNS` and assert pilot v1 against it instead of the live `DATA_COLUMNS` (`tests/test_schema_consistency.py:93-97` at `375f1ff`); the sibling "extras exactly five" test (`:114-122`) gets the same treatment, since the version and channel columns break it. Pilot v1 stays retired as evidence (C-006).

The first chunk is an inventory of every enum, contract and version touchpoint (PF-014: 34 G3O files per the review, plus lists for g3o-api, website and procurement for T-050/T-060). The integrator assigns each listed file to one owner card before chunk 2.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| T-010 signed contract | branch `reclass/t010-contract`† | signed | stop |
| RS-010 code | G3O `origin/main` | `375f1ff` | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Touchpoint inventory (chunk 1) | `C:/Users/spaci/repos/G3O/planning/handoffs/T-012-touchpoints.md`† | integrator, T-050, T-060 | every file with an enum/contract/version reference, by repo; proposed owner card |
| Enum and schema code (chunk 2) | `g3o/common/contract.py`, `g3o/common/schema.py`, enum modules, `tests/test_schema_consistency.py` on branch `reclass/t012-enums`† | T-021..T-028, T-032, T-050, T-051 | v2.5 rows still validate (4-value kept under a version guard); codebook release label, setup pointer and `evidence_channel` fields present (RC-D-002 row 40); pilot v1 asserted against the frozen `PILOT_V1_DATA_COLUMNS` |

#### Execution resources
- Persona/role: engineer
- Tools/connectors: git grep, pytest
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-b/`† on `reclass/t012-enums`†, branched from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-010, T-013 (RC-D-002 row 40)
- Enables: T-015, T-021, T-022, T-024, T-026, T-027, T-028, T-050, T-060, T-090
- Can run with: T-002, T-014, T-016, T-040, T-061, T-063 (W2)
- Researcher gates: none beyond push

#### Ownership and collision control
- Read scope: whole G3O repo, g3o-api and g3o-website (read-only, for the inventory)
- Write claim: `contract.py`, `schema.py`, enum modules, schema test; the inventory file
- Shared surfaces: `contract.py` — sole owner T-012; files in the inventory owned by other cards stay with them as the integrator assigns

#### Procedure boundary
- Included: constants, types, inventory
- Excluded: pin regeneration (T-035, DEC-021); files outside the write claim
- Fixed decisions: R-015 mapping (v2.5 rows unconverted); DEC-005 a and DEC-013 a labels, as amended (RC-D-002 N24, C3 a); N3 a

#### Spec-change reporting
- Spec version: SPEC v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: an enum appears in a surface not covered by any card
- Stop boundary: none (report only)
- Safe continuation: all
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: `git grep` over all enum touchpoints matches the inventory; pytest schema tests pass
- Independent review: T-031
- Acceptance tests: supports A-011, A-013 (via T-041)
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Inventory accepted and owners assigned by the integrator; tests pass; touchpoint list attached.

#### Chunking trigger
Sequential chunks: chunk 1 inventory → integrator assignment → chunk 2 code.

### T-013 — Build the codebook schema, loader, generators and CI check (RC-D-002 A)

Status: pending
Type: build
Priority: critical-path
Spec refs: D-001, R-007, R-008, R-045, R-050, C-007, A-001
Decision refs: DEC-013 (as amended by RC-D-002 C3 a)

#### Objective
The machine-readable codebook (`codebook/codebook.yaml`†, D-001) gets a schema, a loader and generators, plus a CI check (RC-D-002 A, row 53). The generators build, from the codebook:
- the jev question and choice sets (consumed by T-011);
- the extractor prompt sections (T-022, T-032);
- the Python enums and the JSON schema (T-012);
- the data dictionary (T-090) and the human-readable `output_contract.md` (T-010).

Generators only assemble the signed wording and never rewrite it, so CX text stays byte-identical (R-025). CI fails when a generated file differs from the codebook. The schema supports the r2#59 item template fields, the pipeline coverage and level tags (r2#29, r2#54) and release versioning (r2#5, C-007), and it implements the A-001 linkage check: each generated question or prompt traces to an item id and hash. v2.7 ships `core.*` and the G3O generators; procurement (D-008) and AI-text detection (D-009) move over later, and neither move blocks v2.7 deployment.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Item template and generator checks (r2#59) | integrator, under T-010 | PI-approved | build the schema against the draft template; stop before merge until approved |
| Codebook items | `codebook/codebook.yaml`† on `reclass/t010-contract`† (T-010) | draft, then signed | generate from the draft; regenerate from the signed file |
| RS-010 contract, enum and pin code | G3O `origin/main` `375f1ff` | — | stop |
| RS-013 question-set pattern | G3O `origin/main` `375f1ff` | — | follow the pattern |
| RS-039 codebook-review rulings | `planning/t010/codebook-review/` | PI-ruled 2026-10-29 | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Codebook package | `g3o/codebook/`† (schema, loader, generators), `codebook/schema.json`†, `tests/test_codebook*.py`†, a codebook drift step in `.github/workflows/ci.yml`; branch `reclass/t013-codebook`† | T-002, T-010, T-011, T-012, T-016, T-022, T-032, T-090, T-031 | verbatim assembly only; CI fails on drift; every generated question / prompt / enum carries its item id and hash; release label per C-007 / R-050 |

#### Execution resources
- Persona/role: engineer (lane eng-b)
- Tools/connectors: Python, pytest, YAML and JSON-schema validation
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-b/`† on `reclass/t013-codebook`†, branched from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: none
- Soft: T-010 (item template, written by the integrator, r2#59). RC-D-002 O3: soft edges both ways; neither blocks the other (RC-D-002 open item resolved by PI, 2026-10-29, chat "all accepted").
- Enables: T-002, T-011, T-012, T-016, T-022, T-032
- Can run with: T-001, T-010, T-020, T-097 (W1)
- Researcher gates: PI approves the item template and the generator checks (r2#59; approved 2026-10-30 with RC-D-003); push of the branch

#### Ownership and collision control
- Read scope: RS-010, RS-013, RS-039, T-010 drafts
- Write claim: `g3o/codebook/`†, `codebook/schema.json`†, `tests/test_codebook*.py`†, the codebook step in `.github/workflows/ci.yml`
- Shared surfaces: `codebook/codebook.yaml`† content is T-010's; generated files are written only by the generators

#### Procedure boundary
- Included: schema, loader, generators, CI drift check, linkage check
- Excluded: item wording (PI, under T-010); procurement and AI-text adoption (D-008, D-009); stage code
- Fixed decisions: RC-D-002 A (architecture, PI "ok as rec"); C3 a (one release label per row); r2#5; r2#59

#### Spec-change reporting
- Spec version: SPEC v001.6 (RC-D-002)
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: an item cannot be expressed in the template; a generator would have to rewrite signed text
- Stop boundary: the affected generator
- Safe continuation: the other generators
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: regenerating from the codebook reproduces the committed generated files byte for byte; CI fails on a seeded drift
- Self-check: a generated CX question is byte-identical to its signed item text; each generated question and prompt carries its item id and hash (A-001 linkage)
- Independent review: T-031 (reviews the generators and CI, RC-D-002 A)
- Acceptance tests: A-001 (linkage check)
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests and CI drift check pass on `reclass/t013-codebook`†; template approved by the PI; return report filed with the integrator.

#### Chunking trigger
Split per generator target (questions, prompts, enums / schema, docs).

### T-014 — Store chrome text and page links in the scraper (RC-D-002 F)

Status: pending
Type: build
Priority: required
Spec refs: R-023 (CX-53), R-031, R-035, R-059, N-004
Decision refs: none (PI ruling N1 a, RC-D-002 F)

#### Objective
`g3o/scrape/html.py` strips header / footer / nav / aside (L11, L21 at `375f1ff`) and stores no links. Ruled (PI, 2026-10-29, "n1 a"): the scraper stores the stripped chrome text as a separate field, and the page's links. This serves `content_contact_details`, CX-53 e-mail extraction and follow-up links (R-031). There is no back-fill of stored pages: pages stored before the change lack both, a back-filled institution gains them only for pages fetched live again (R-035), and the row's `text_source` says which (R-059). Procurement is exempt (r2#54).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| RS-016 scrape modules (`g3o/scrape/html.py`, `extract_links` at `html.py:36` and `pdf.py:53`), `g3o/run/presweep/stage_scrape.py` | G3O `origin/main` `375f1ff` | — | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Scraper change, plus tests | `g3o/scrape/html.py`, the stored-record hunk of `g3o/run/presweep/stage_scrape.py`, tests; branch `reclass/t014-scrape`† | T-003, T-022, T-024, T-025, T-029 | chrome text in its own field; links stored; main-text field unchanged; records stored before the change load with both fields absent |

#### Execution resources
- Persona/role: engineer, lane eng-a (RC-D-002 O5)
- Tools/connectors: Python, pytest, BeautifulSoup (existing)
- Skills/protocols: none beyond this plan
- Working directory/environment: the lane's worktree `C:/Users/spaci/worktrees/G3O-<lane>/`† on `reclass/t014-scrape`†, branched from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: none
- Enables: T-022, T-025
- Can run with: T-002, T-012, T-016, T-040, T-061, T-063 (W2)
- Researcher gates: push of the branch

#### Ownership and collision control
- Read scope: RS-016
- Write claim: `g3o/scrape/html.py`, the stored-record hunk of `g3o/run/presweep/stage_scrape.py`, their tests
- Shared surfaces: `stage_scrape.py` (T-025 does not own it, DEC-003 b); orchestrator wiring → T-030

#### Procedure boundary
- Included: chrome-text field, link storage, loading of old records
- Excluded: link following (T-025); re-fetching stored pages; discovery, site pick, triage (N-004)
- Fixed decisions: ruling N1 a (RC-D-002 F); no back-fill of stored pages; procurement exempt (r2#54)

#### Spec-change reporting
- Spec version: SPEC v001.6 (RC-D-002)
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: keeping chrome text changes the main-text output on existing fixtures
- Stop boundary: none (report only)
- Safe continuation: all
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: fixture pages give the same main text as at `375f1ff`, plus a separate chrome-text field and the stored links
- Self-check: a record stored before the change loads with both fields absent
- Independent review: T-031
- Acceptance tests: supports A-004 (links) via T-041
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass on branch `reclass/t014-scrape`†, return report filed with the integrator.

#### Chunking trigger
none

### T-015 — Build the source-level field coder (RC-D-002 H Q3, N25)

Status: pending
Type: build
Priority: required
Spec refs: R-002, R-026, R-040, R-045, R-090
Decision refs: none

#### Objective
One coder for the source-level fields X21-X28 plus X37 / X38 (RC-D-002 H Q3, schedule N25):
- `source_type`: domain and address first, then the shared classifier question (r2#25, r2#30);
- the X22 credibility map, without the translation clause;
- per-source confidence (r2#27);
- flags kept only where they add information, as one shared list (r2#38, r2#39);
- verbatim `source_snippet` (r2#35);
- date: metadata first, then the quote step, with the date origin (X26, r2#31; date-origin values use the shared provenance vocabulary, T3);
- language ID; title, url, access date.

It takes the deterministic parts from T-024. RC-D-002 O2: this card owns every source-level field, including the residual `source_type` question and X22 / X27 / X28 / X37 / X38 (RC-D-002 open item resolved by PI, 2026-10-29, chat "all accepted").

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Source-level question set | T-011 | merged | stop |
| Enums | T-012 | merged | stop |
| Quote-step dates | T-022 | merged | stop |
| jev answer record | T-027 | merged | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Source-level coder module, plus tests | `g3o/common/source_fields.py`†, tests; branch `reclass/t015-source`† | T-026, T-028 | every source carries X21-X28, X37, X38 with coder and basis; date origin recorded |

#### Execution resources
- Persona/role: engineer, lane eng-a (RC-D-002 O5)
- Tools/connectors: Python, pytest; jev client (RS-012) for the residual `source_type` question
- Skills/protocols: none beyond this plan
- Working directory/environment: the lane's worktree `C:/Users/spaci/worktrees/G3O-<lane>/`†, feature branch from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-011, T-012, T-022, T-027
- Enables: T-026, T-028
- Can run with: T-021, T-050 (W4)
- Researcher gates: push of the branch

#### Ownership and collision control
- Read scope: T-011, T-012, T-022, T-024, T-027 outputs
- Write claim: `g3o/common/source_fields.py`† and its tests
- Shared surfaces: orchestrator wiring → T-030 (eng-b)

#### Procedure boundary
- Included: the source-level fields listed above
- Excluded: page and activity codes (T-021, T-023); quote checking (T-024)
- Fixed decisions: r2#25, r2#27, r2#30, r2#31, r2#35, r2#38, r2#39; T3

#### Spec-change reporting
- Spec version: SPEC v001.6 (RC-D-002)
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a source field has no defined coder in the codebook
- Stop boundary: that field
- Safe continuation: the other fields
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: fixture sources cover an official domain, an archive address, a classifier-typed source and a metadata-less date
- Independent review: T-031
- Acceptance tests: supports A-013 via T-041
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass on branch `reclass/t015-source`†, return report filed with the integrator.

#### Chunking trigger
Split `source_type` from the date and flag fields.

### T-016 — Re-pilot the re-signed questionnaire items (paid, small; RC-D-002 N28)

Status: pending
Type: spike
Priority: critical-path
Spec refs: R-015, R-016, R-020..R-025, R-084, A-020, C-002
Decision refs: none (r2#3)

#### Objective
A paid re-pilot, run by Simone before the build (r2#3), of every reworded item: the re-signed CX items (CX-01.3†; X01-X11 plus r2#9, #10, #19) and the non-CX items whose rulings commit to a re-pilot: the amended `confirms_activity` / C04, A01, the 9-value verdict question (r2#7), interface (r2#20), `governance_direction` (r2#58), `service_domain` (r2#62) and `governance_form` multi-select (S6 c). The agent prepares the exact command and a cost estimate; Simone runs it via `! <command>` (red line 4). The PI rules on the results before T-011 relies on the wording.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Signed items | codebook, T-010 | signed | stop |
| Generated questions for those items | T-013 | generated | stop |
| RS-004 re-pilot pattern (`unclear2.py`), RS-005 prior answers, RS-024 `pilot/` | Drive | as listed | stop |
| RS-008 / RS-009 pages | local | — | stop |
| RS-031 jev key | environment | valid | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Re-pilot report and answers | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/repilot-v27/`† (`REPILOT-REPORT.md`†, answers jsonl, command file with the `! <command>` line and cost estimate) | PI, T-011, T-040 | per item: answer distribution, probability, comparison with the prior wording where it exists; every request id kept |

#### Execution resources
- Persona/role: integrator prepares; Simone runs the paid re-pilot via `!` (RC-D-002 O5)
- Tools/connectors: Python, jev client (RS-012); command prepared for Simone to run as `! <command>`
- Skills/protocols: none beyond this plan
- Working directory/environment: a lane worktree `C:/Users/spaci/worktrees/G3O-<lane>/`† (scripts, branched from `origin/main` `375f1ff`); outputs to the re-pilot folder; Simone's shell for the paid run

#### Dependencies
- Requires: T-010, T-013
- Enables: T-011
- Can run with: T-002, T-012, T-014, T-040, T-061, T-063 (W2)
- Researcher gates: PI approves the cost estimate; Simone runs the paid command (red line 4); PI rules on the results

#### Ownership and collision control
- Read scope: codebook, RS-004, RS-005, RS-008, RS-009, RS-024
- Write claim: the re-pilot folder
- Shared surfaces: none

#### Procedure boundary
- Included: preparing the command and estimate; reporting on the run Simone launches
- Excluded: running any paid call itself; rewording any item (PI)
- Fixed decisions: r2#3 (re-pilot before the build); red line 4

#### Spec-change reporting
- Spec version: SPEC v001.6 (RC-D-002)
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: an item's answers suggest the wording does not work as signed
- Stop boundary: T-011 for that item
- Safe continuation: the other items
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: every listed item has answers; call count matches pages × items
- Independent review: integrator spot-checks 5 request ids
- Acceptance tests: informs A-020, A-011, A-012
- Failure/rollback: none needed (measurement only)

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Report, answers and the paid-run record (command, estimate, actual cost) written; PI ruling on the results recorded by the integrator.

#### Chunking trigger
More pages or items than in the approved estimate → new paid gate.

### T-020 — Build the token-based page chunker and combination rule

Status: pending
Type: build
Priority: critical-path
Spec refs: R-044, R-045 (RC-D-003), C-004, A-021
Decision refs: DEC-008

#### Objective
Chunk pages by estimated tokens to fit jev's 32k-token state limit, keeping halve-and-retry as a fallback (DEC-008 c). Combine chunk answers per CX-01.2 §11.1 and record which chunk produced each code (chunk ids carried for R-044). The estimator constant comes from T-002 (soft edge): the build starts in W1 and the constant is filled in after T-002. RC-D-002 row 41: the combination implements the per-item combine rules read from the codebook (r2#42, R-044 v001.6), replacing the X16 three-rule list; the S3 a verdict order; and a split routine that T-026 reuses for pooled Stage 6 evidence (r2#6, C-004).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| RS-004 `byte_chunks` | Drive | — | fallback logic reference |
| RS-014 Stage 6 split logic | G3O `origin/main` `375f1ff` | — | alternative reference |
| RS-024 §11.1 (L184) | Drive | frozen | stop |
| T-002 estimator constant | `SPIKE-T002.md`† | done | build with a placeholder constant; fill once T-002 reports |
| Per-item combining rules (RC-D-002 row 41) | codebook (T-010) via the T-013 loader | merged | build with the rule types as configuration; read them from the codebook once T-013 merges |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Chunker module | `g3o/common/page_chunks.py`†, `tests/test_page_chunks.py`† on branch `reclass/t020-chunks`† | T-021, T-022, T-023 | deterministic; chunk ids carried; estimator constant per script configurable |

#### Execution resources
- Persona/role: engineer
- Tools/connectors: Python, pytest
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-a/`† on `reclass/t020-chunks`†, branched from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: none
- Enables: T-021, T-022, T-023
- Can run with: T-001, T-010, T-013, T-097
- Researcher gates: none beyond push

#### Ownership and collision control
- Read scope: RS-004, RS-014, RS-024
- Write claim: the two new files
- Shared surfaces: none

#### Procedure boundary
- Included: chunking, combination, estimator plumbing
- Excluded: jev calls
- Fixed decisions: DEC-008 c; R-044 combination rule

#### Spec-change reporting
- Spec version: SPEC v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: §11.1 is ambiguous for a field type; T-002 shows the estimator cannot keep chunks under 32k for some script even with the fallback
- Stop boundary: the affected field
- Safe continuation: rest
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: unit tests on ordered vocabularies, yes/no items and page fields; tests that over-limit chunks trigger halve-and-retry; one test per combining-rule type and for the S3 a order (RC-D-002 row 41)
- Independent review: T-031
- Acceptance tests: A-021 (via T-041)
- Failure/rollback: branch

#### Decision points
- DP-007: Safety margin below the 32k-token limit for the estimator
  - Default: a margin equal to the largest estimator error T-002 observes for the page's script
  - Recommendation: same — ties the margin to measured error rather than a guessed constant

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass with the T-002 constant in place.

#### Chunking trigger
none

### T-021 — Build the jev pass-1 page coder stage

Status: pending
Type: build
Priority: critical-path
Spec refs: R-001, R-002, R-008, R-015, R-020, R-021, R-023, R-026, R-030, R-081
Decision refs: DEC-004

#### Objective
A stage that:
- sends each page, chunked, to jev with the page question set;
- records the answers through the shared jev answer record (T-027): probabilities, confidence, model id, request id;
- applies the 0.8 threshold flags;
- RC-D-002 row 42: asks X17 and the residual `source_type` (the residual `source_type` question moves to T-015, RC-D-002 O2); sets `not_assessable` mechanically (never asked, C1 a); asks no page `content_*` descriptive or safeguard items (they are derived); the A05 relationship moves to T-023; asks in round and gate order (R-008).

The completeness flag comes from jev; the follow-up links come from the T-022 nano call (P5 / Q-018). RC-D-002 F: follow-up link candidates come from the stored page links (T-014), and the quote step selects among them (T-022).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| T-011 page question set | branch | merged | stop |
| T-012 enums | branch | merged | stop |
| T-020 chunker | branch | merged | stop |
| T-027 record module | branch | merged | stop |
| T-002 numbers | spikes folder | done | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Pass-1 stage | `g3o/classify/jev_page_code.py`†, `g3o/run/presweep/stage_page_code.py`†, tests on branch `reclass/t021-pass1`† | T-023, T-025, T-030 | per-page artifact with verdict, CX page fields, completeness flag, chunk ids |

#### Execution resources
- Persona/role: engineer
- Tools/connectors: jev client (RS-012), pytest with mocks (RS-019 pattern)
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-a/`† on `reclass/t021-pass1`†, branched from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-002, T-011, T-012, T-020, T-027
- Enables: T-023, T-025, T-030
- Can run with: T-015, T-050
- Researcher gates: none beyond push

#### Ownership and collision control
- Read scope: T-011, T-012, T-020, T-027 outputs
- Write claim: the new modules and tests
- Shared surfaces: orchestrator wiring → T-030 (eng-b)

#### Procedure boundary
- Included: stage module
- Excluded: orchestrator edits; nano call (T-022)
- Fixed decisions: R-081 threshold 0.8; DEC-004 a storage via T-027

#### Spec-change reporting
- Spec version: SPEC v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: jev rejects a question shape
- Stop boundary: T-023
- Safe continuation: T-025 against mocks
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: mocked tests for threshold flags and chunked pages
- Independent review: T-031
- Acceptance tests: A-011, A-013 (via T-041)
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass.

#### Chunking trigger
More than 1 week → split CX fields from the verdict.

### T-022 — Rework the nano extraction call (spans, pass-1 quotes, links, residual free text)

Status: pending
Type: build
Priority: critical-path
Spec refs: R-001, R-003, R-006, R-020, R-021, R-023, R-030, R-031, R-040, R-041, R-044, C-001
Decision refs: DEC-009, DEC-010, DEC-016

#### Objective
One nano Batch call per page after pass 1, scoped per item to match the SPEC (review M6):
1. verbatim supporting quotes for every positive / substantive **pass-1 page code** on **every** page, whatever its verdict (R-040, R-041; Q-010 a: negative, `unknown`, `_NA_` codes need none), per chunk, each from the chunk that produced the code (PF-002, R-044) — so a positive CX page field (R-020, R-021, R-023) on e.g. a `background_only` page is supported rather than downgraded by construction;
2. follow-up links for every page pass 1 marks incomplete (R-030, R-031; P5), whatever its verdict;
3. activity segmentation as **character spans only** (DEC-010 a), so no paraphrase reaches jev — only on pages with one of the 5 R-003 verdicts (`confirms_activity`, `ambiguous_genai`, `ambiguous_attribution`, `other_body`, `event_only`);
4. the residual free-text fields routed to nano under DEC-009 a (`activity_name`, `tool_name`, `vendor`, `reported_outcomes`, `reported_incidents`, `scope_notes`), each value carrying its verbatim supporting text (R-006, R-040).

Pages with no positive page code, complete, and outside the 5 verdicts need no nano request.

RC-D-002 row 43: the quote step is blind to the answer for the field it quotes but may see that a gate is not `none` (r2#18), and makes the named selections of C-001 (SPEC v001.6). Item 2 becomes selecting follow-up links among the page's stored links (r2#48; needs T-014). C22 / C23 spans only when the CX-61 gate is not `none` (r2#9). The A09 scale number is copied verbatim, with the unit picked by the classifier (C4 a), and the X26 date is coded by the quote step. It also extracts C12 `model_name` and the A05 actor name. The residual free-text list in item 4 follows the codebook coder column (r2#28: `scope_notes` gone, `vendor` split into developer and contracting party). X19 is dropped: no extraction-time quote cap (r2#17). The prompts are generated from the codebook by T-013.

The 60,000-character head+tail cap (`g3o/extract/batch.py:49` `DEFAULT_TEXT_CAP_CHARS`) does not apply on the v2.7 path. Quotes for pass-2 codes are T-032's job.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| RS-015 batch/client/parser/salvage | G3O `origin/main` `375f1ff` | — | stop |
| T-010 contract | branch | signed | stop |
| T-012 enums | branch | merged | stop |
| T-020 chunker | branch | merged | stop |
| T-021 artifact shape | branch | merged or mocked | use mock |
| Generated prompt sections | T-013 | merged | stop |
| Stored chrome text and links | T-014 | merged | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Nano extraction | `g3o/extract/{batch,client,parser,salvage}.py`, `g3o/extract/prompts/extract_v27.md`†, `g3o/run/presweep/stage_extract.py`, plus the new Anthropic client module† (RC-D-001), on branch `reclass/t022-nano`† | T-023, T-024, T-025, T-032 | output never carries a code field (C-001); spans as offsets, only for the 5 R-003 verdicts; a quote (or recorded empty result) for every positive / substantive pass-1 page code on every page; links for every incomplete page; every nano free-text value has supporting text; quotes tagged with chunk id; no head+tail truncation on the v2.7 path |

#### Execution resources
- Persona/role: engineer
- Tools/connectors: new Anthropic Messages + Message Batches client for `claude-haiku-5-5` at medium effort (RC-D-001 A; the OpenAI client in RS-015 stays for the v2.5 path), pytest; load the `claude-api` skill
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-c/`† on `reclass/t022-nano`†, branched from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-010, T-012, T-013, T-014, T-020 (RC-D-002 row 43, N34)
- Enables: T-015, T-023, T-024, T-025, T-032
- Can run with: T-003, T-011, T-027 (W3)
- Researcher gates: PI approves the nano prompt text; push gate

#### Ownership and collision control
- Read scope: RS-015, T-010, T-012, T-020, T-021 outputs
- Write claim: the listed extract files
- Shared surfaces: `stage_extract.py` — sole owner T-022; the nano Batch client is reused read-only by T-032

#### Procedure boundary
- Included: extraction for pass-1 quotes (all pages), links (all incomplete pages), spans (5 R-003 verdicts), residual free text with supporting text
- Excluded: quote verification (T-024); pass-2 quotes (T-032)
- Fixed decisions: C-001; DEC-009 a; DEC-010 a; R-044 chunk provenance

#### Spec-change reporting
- Spec version: SPEC v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: removing the 60k cap breaks the Batch request size; spans cannot be produced reliably on chunked pages
- Stop boundary: T-024
- Safe continuation: T-023 against mocks
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: parser tests; grep confirms no code value is parsed from nano output; tests that quotes carry chunk ids
- Self-check: request-selection tests — a `background_only` page with a positive CX page code gets a quote request; an incomplete `no_genai` page gets a links request; spans are requested only for the 5 R-003 verdicts; every nano free-text value in the fixtures has supporting text
- Independent review: T-031
- Acceptance tests: A-003, A-021 (via T-041)
- Failure/rollback: branch

#### Decision points
- DP-008: Coordinate base for the character spans on chunked pages
  - Default: offsets into the full page text
  - Recommendation: full-page offsets — they stay stable whatever the chunker does, and T-023 marks spans on the full page

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass; nano prompt approved by the PI.

#### Chunking trigger
Split links from quotes if the parser work exceeds 1 week.

### T-023 — Build the jev pass-2 activity coder

Status: pending
Type: build
Priority: critical-path
Spec refs: R-001, R-003, R-004, R-006, R-008, R-017, R-022, R-026
Decision refs: DEC-009, DEC-010

#### Objective
jev coding per (page × activity span), with the span marked in the page text (DEC-010 a): Group D enums and flags under v2.6 rules, the CX-01.2 finding fields, and the jev Choice free-text fields (DEC-009 a).

RC-D-002 row 44: pass 2 adds applicability keyed on `activity_type` (r2#8; governance-only items gate on action type `governance`, T4); C10; C11 per r2#20; developer and contracting party (r2#24; core supplier role = contracting party, T5); A04; the C17 year method (r2#50); C09 as the only purchase home (r2#14); A01; A02 narrowed (r2#11); A03 multi-select (S6 c); A09 unit (C4 a); four-answer safeguards (r2#10); the CX-61 gate (r2#9); `governance_direction`, `service_domain`; the per-activity relationship (r2#23); the C07 relation question with the shared relation list (R-017, r2#22); the discontinuation value inside signed CX-61 (C2 a). It codes activities on all 5 verdicts (r2#51), in round and gate order (R-008).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| T-011 activity question set | branch | merged | stop |
| T-021 page artifact | branch | merged | stop |
| T-022 spans | branch | merged | stop |
| T-020 chunker, T-027 record | branch | merged | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Pass-2 stage | `g3o/classify/jev_activity_code.py`†, `g3o/run/presweep/stage_activity_code.py`†, tests on branch `reclass/t023-pass2`† | T-026, T-032 | one record per activity, linked to page, span and chunk |

#### Execution resources
- Persona/role: engineer
- Tools/connectors: jev client (RS-012), pytest with mocks
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-a/`† on `reclass/t023-pass2`†, branched from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-011, T-020, T-021, T-022, T-027
- Enables: T-026, T-032
- Can run with: T-025, T-051
- Researcher gates: none beyond push

#### Ownership and collision control
- Read scope: T-011, T-020, T-021, T-022, T-027 outputs
- Write claim: the new modules and tests
- Shared surfaces: orchestrator → T-030 (eng-b)

#### Procedure boundary
- Included: pass 2
- Excluded: consolidation (T-026); quote extraction (T-032)
- Fixed decisions: DEC-010 a (spans only); DEC-009 a routing

#### Spec-change reporting
- Spec version: SPEC v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: the activity context exceeds the state limit after chunking
- Stop boundary: affected pages
- Safe continuation: rest
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: mocked multi-activity tests; tests that no nano text other than span offsets enters the jev request
- Independent review: T-031
- Acceptance tests: A-003 (via T-041)
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass.

#### Chunking trigger
Split the CX finding fields from Group D.

### T-032 — Build the pass-2 supporting-text call

Status: pending
Type: build
Priority: critical-path
Spec refs: R-040, R-044, C-001, A-003, A-021
Decision refs: DEC-010

#### Objective
After jev pass 2, nano extracts verbatim supporting text for every positive or substantive activity-level code. Each quote comes from the chunk that produced the code (PF-001, R-040, R-044). Output carries no code values (C-001). RC-D-002 row 43: the T-022 quote-step rules apply (blind to the answer, gate-aware, r2#18; named selections per C-001 v001.6); C22 / C23 spans only when the CX-61 gate is not `none` (r2#9); prompts generated by T-013.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| T-022 nano Batch client and chunk-tagged quote format | branch | merged | stop |
| T-023 activity records | branch | merged | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Pass-2 support module | `g3o/extract/pass2_support.py`† + tests on branch `reclass/t032-pass2-quotes`† | T-024, T-030 | one quote record per (activity, code) with chunk id; no code field |

#### Execution resources
- Persona/role: engineer
- Tools/connectors: OpenAI Batch client (RS-015, reused), pytest
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-c/`† on `reclass/t032-pass2-quotes`†, branched from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-013, T-022, T-023
- Enables: T-024, T-030
- Can run with: none
- Researcher gates: PI approves the pass-2 nano prompt text; push gate

#### Ownership and collision control
- Read scope: T-022, T-023 outputs
- Write claim: `g3o/extract/pass2_support.py`† and its tests
- Shared surfaces: nano Batch client reused read-only (owner T-022); `stage_extract.py` stays with T-022; orchestrator wiring → T-030 (eng-b)

#### Procedure boundary
- Included: pass-2 quote extraction
- Excluded: quote verification (T-024); pass-1 quotes (T-022)
- Fixed decisions: C-001; R-044 chunk provenance; DEC-010 a

#### Spec-change reporting
- Spec version: SPEC v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a second nano round per page makes runtime or cost infeasible against T-002 numbers
- Stop boundary: T-024 integration of pass-2 quotes
- Safe continuation: T-024 pass-1 path
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: fixture tests with multi-activity and chunked pages; grep confirms no code value parsed from nano
- Independent review: T-031
- Acceptance tests: A-003, A-021 (via T-041)
- Failure/rollback: branch

#### Decision points
- DP-009: One nano request per (page × activity) or one per page covering all its activities
  - Default: one request per page covering all activity spans
  - Recommendation: one per page — fewer Batch requests; switch only if T-002 shows per-page requests exceed size limits

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass; pass-2 prompt approved by the PI.

#### Chunking trigger
none

### T-024 — Build support check, downgrade and deterministic extraction

Status: pending
Type: build
Priority: critical-path
Spec refs: G-002, R-006, R-023 (CX-53), R-040, R-041, R-042, R-044, R-081
Decision refs: DEC-007, DEC-009

#### Objective
A module that fuzzy-matches every supporting quote, from pass 1 (T-022) and pass 2 (T-032), against the stored page text, using pinned `rapidfuzz` and the T-003 threshold. It downgrades unsupported positive or substantive codes, and codes below 0.8 including negatives (to `unclear` / `unknown`), and runs the deterministic extraction for contact emails (when contact = yes) and explicitly stated years (DEC-009 a).

RC-D-002 row 45 adds: X35 entailment per (code, quote) with the chosen-answer probability bar (r2#26); per-item `downgrade_to` except for page verdicts (r2#40); the support-status values incl. "quote does not state the value" and "set by rule" (r2#37, r2#53; SPEC R-041 v001.6); the developer lookup (r2#24), no longer filling `vendor`; contact e-mails stored in full, with domain + count for publication (S4 a, R-058). It runs between rounds (r2#41), not after both passes. RC-D-002 O4: T-024 delivers its checks as a library that T-021 and T-023 call between rounds; no new graph edge (RC-D-002 open item resolved by PI, 2026-10-29, chat "all accepted"). X22 / X27 / X28 / X37 / X38 go to T-015 (RC-D-002 O2).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Approved metric and threshold | T-003, spikes folder | PI-approved (Q-020 b) | stop |
| Pass-1 page-code quotes | T-022 | merged | stop |
| Pass-2 activity-code quotes | T-032 | merged | stop |
| v2.7 enums and no-evidence values | T-012 | merged | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Support check, downgrade and deterministic extraction module, plus tests | `g3o/common/support_check.py`†, tests; branch `reclass/t024-support`† | T-026, T-028, T-041 | each downgrade records its reason (`no_quote`, `low_confidence`); matcher library pinned |

#### Execution resources
- Persona/role: engineer (lane eng-c)
- Tools/connectors: Python, pytest, pinned `rapidfuzz` (DEC-007 a)
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-c/`†, feature branch from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-003, T-012, T-022, T-032
- Enables: T-026, T-028, T-041
- Can run with: none (W7)
- Researcher gates: push of the branch

#### Ownership and collision control
- Read scope: T-003 report, T-022 and T-032 modules, T-012 enum modules
- Write claim: `g3o/common/support_check.py`† and its tests
- Shared surfaces: none

#### Procedure boundary
- Included: quote check, downgrade, deterministic fields (contact emails, explicit years)
- Excluded: the threshold choice (T-003, PI); quote extraction (T-022, T-032)
- Fixed decisions: one threshold 0.8 for all codes (R-081; chosen-answer probability, RC-D-002 row 24); only positive or substantive codes need support (Q-010 a); presence check only, not entailment (R-042), with X35 entailment as a separate layer (RC-D-002 row 17); DEC-007 a; DEC-009 a

#### Spec-change reporting
- Spec version: SPEC v001.4 (`C:/Users/spaci/repos/G3O/planning/SPEC.md`), the Stage 6 locked version once locked
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a field has no defined no-evidence value
- Stop boundary: that field
- Safe continuation: all other fields
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: tests per the R-041 value list (Q-010 a), including a negative code below 0.8
- Self-check: quotes from both passes are checked, and a chunked-page quote is matched in the chunk that produced the code (R-044)
- Independent review: T-031
- Acceptance tests: A-002; A-016 via T-082
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass on branch `reclass/t024-support`†, return report filed with the integrator.

#### Chunking trigger
none

### T-025 — Build link following (3 hops, URL cap, once per URL, provenance)

Status: pending
Type: build
Priority: required
Spec refs: R-030, R-031, R-032, R-033, R-034, R-035, R-036, N-004, SC-03
Decision refs: DEC-003

#### Objective
Links from incomplete pages enter a separate follow-up leg after pass 1 (DEC-003 b). They are fetched and sent back through pass 1, up to 3 hops and up to the per-institution URL cap (R-032 v001.4). Each URL is fetched once per institution per run, the provenance chain is stored, "cap reached" is recorded per institution, and back-fill fetches are tagged per R-036. RC-D-002 row 46: `discovery_path` (X18) is set on every source in all runs; X39 keeps only `fetch_failed` and link-not-followed states (r2#7); procurement is exempt (r2#54).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| RS-016 scrape fetcher + `extract_links` (`g3o/scrape/html.py:36`, `pdf.py:53`) | `origin/main` | — | reuse |
| Link fan-out and Batch latency measurements; URL cap value | T-002 report; PI sets cap value | report done; cap value set by PI | build with cap as a config value; stop before merge until set |
| Page completeness flag | T-021 | merged | stop |
| Follow-up link candidates: the page's stored links (T-014) filtered by the quote step's selection (T-022) (RC-D-002 row 46; was "Follow-up links, T-022") | T-014, T-022 | merged | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Follow-up leg modules, plus tests | `g3o/scrape/follow.py`†, `g3o/run/presweep/stage_follow.py`†, tests; branch `reclass/t025-links`† | T-029, T-030 | provenance fields: origin page, hop, fetch date, release id; per-institution "cap reached" record |

#### Execution resources
- Persona/role: engineer (lane eng-b)
- Tools/connectors: Python, pytest; existing fetcher and politeness settings
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-b/`†, feature branch from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-002, T-014, T-021, T-022
- Enables: T-029, T-030
- Can run with: T-023, T-051 (W5)
- Researcher gates: PI sets the per-institution URL cap value after T-002; push of the branch

#### Ownership and collision control
- Read scope: RS-016 scrape modules, T-021, T-022
- Write claim: new modules `g3o/scrape/follow.py`†, `g3o/run/presweep/stage_follow.py`† and their tests
- Shared surfaces: none; `stage_scrape.py` is not owned (DEC-003 b); orchestrator wiring is done by T-030

#### Procedure boundary
- Included: link following, URL dedup, hop counter, URL cap, provenance, back-fill tagging
- Excluded: discovery, site pick, triage (N-004); orchestrator wiring (T-030)
- Fixed decisions: DEC-003 b (separate leg after pass 1); 3 hops (R-032); any cited link eligible (R-033); per-institution cap (item 22 b)

#### Spec-change reporting
- Spec version: SPEC v001.4, the Stage 6 locked version once locked
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: robots or politeness rules block a large share of cited links
- Stop boundary: none
- Safe continuation: all
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: loop, dedup and hop-limit tests (A-004)
- Self-check: cap-reached test: following stops at the cap and "cap reached" is recorded (SC-03)
- Independent review: T-031
- Acceptance tests: A-004, A-014
- Failure/rollback: feature flag off

#### Decision points
- DP-030: closed by RC-D-001 (B): in full runs the extractor calls in the follow-up legs use Message Batches; in test runs (T-041, T-072) they are sync. Original options: Batch queue vs synchronous, decided from T-002.
  - Default: Message Batches in full runs; sync in test runs (RC-D-001 B)
  - Recommendation: as default — ruled by the PI 2026-10-29 (RC-D-001 B)

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass on branch `reclass/t025-links`†, cap value configured from the PI's setting, return report filed with the integrator.

#### Chunking trigger
Split back-fill tagging into its own chunk.

### T-026 — Rewrite v2.6 consolidation against jev Stage 6

Status: pending
Type: build
Priority: critical-path
Spec refs: R-005, R-012, R-014, R-015, R-017, R-081, A-010
Decision refs: DEC-018

#### Objective
Stage 6 applies v2.6/v2.7 consolidation (explicit relations, no merge of unresolved relations, the `no` rule per SF-009 b) to the new page and activity records. It is rewritten against the jev Stage 6 (DEC-018 b), using `052fcb2` as reference only and its 30 `exval_cases` as tests.

RC-D-002 row 47: implements SPEC R-005 v001.6 (`background_only` in the `no` set, S2 b; a downgraded page counts as unresolved; `yes` from any pipeline and `no` from web pages only, with supported purchase records able to give `yes`, C5 a; `not_assessable` does not block `no`, C1 a; the chosen-answer probability bar); X30 with the shared relation list (R-017); X31 pooled with split (the T-020 routine); A06 per r2#21; A07 with 9 counts per pipeline; the r2#27 confidence; the unit-credit flag; X33; X34. Activities from non-confirmed pages are used for relations only (r2#51). The Stage 6 identical-name defect (RC-D-002 H Q2, `RC-D-002.md:105`; `g3o/validate/jev_validate.py:113` at `375f1ff` skips the same-activity question when names are identical) is the X30 case.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| RS-011 `evidence_review` + rules | ref `archive/exval-v2.6` `052fcb2` | — | reference only |
| RS-011 30 `exval_cases` | `052fcb2` | — | adapt as tests |
| RS-014 Stage 6 jev | `origin/main` | — | stop |
| Stage 6 question set | T-011 | merged | stop |
| Enums | T-012 | merged | stop |
| Activity codes | T-023 | merged | stop |
| Support check and downgrade | T-024 | merged | stop |
| jev answer record | T-027 | merged | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Rewritten Stage 6 consolidation, plus tests | `g3o/validate/jev_validate.py`, `g3o/run/presweep/stage_validate.py`, `g3o/common/evidence_review.py`†, tests; branch `reclass/t026-stage6`† | T-028 | institution verdict + dispositions; question-set version stamped |

#### Execution resources
- Persona/role: engineer (lane eng-a)
- Tools/connectors: Python, pytest, git (read `052fcb2`)
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-a/`†, feature branch from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-011, T-012, T-015, T-023, T-024, T-027
- Enables: T-028
- Can run with: none (W8)
- Researcher gates: push of the branch

#### Ownership and collision control
- Read scope: `052fcb2`, RS-014, T-011, T-012, T-023, T-024, T-027
- Write claim: the listed Stage 6 files and tests
- Shared surfaces: Stage 6 — sole owner T-026

#### Procedure boundary
- Included: consolidation rules on the v2.7 records
- Excluded: the retired OpenAI Stage 6 path; merging `052fcb2` code
- Fixed decisions: DEC-018 b (rewrite, reference only); R-005 `no` rule (SF-009 b)

#### Spec-change reporting
- Spec version: SPEC v001.4, the Stage 6 locked version once locked
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a v2.6 rule depends on removed fields
- Stop boundary: that rule
- Safe continuation: the remaining rules
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: the 30 `exval_cases`, adapted, pass
- Self-check: A-010 fixtures (complete context vs open signals) pass
- Independent review: T-031
- Acceptance tests: A-010
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass on branch `reclass/t026-stage6`†, return report filed with the integrator.

#### Chunking trigger
Split the `no` rule from the merge rules.

### T-027 — Build the shared jev answer record

Status: pending
Type: build
Priority: critical-path
Spec refs: R-026, A-013
Decision refs: DEC-004

#### Objective
One record type for every jev answer (probability distribution, confidence, model id, request id, question-set version, chunk id), used by T-021, T-023 and T-026. Under DEC-004 a it is written to per-institution JSON artifacts, with DB columns for confidence, model id and request id plus the full distribution in jsonb, via T-051/T-052. The API does not serve the distribution column (specified in T-050). RC-D-002 row 48: the record type covers every automated coder (P10a), stores the chosen-answer probability (r2#26), and links per-code coder details to the per-run version record (r2#57).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| RS-012, RS-013 answer-record pattern (Stage 2/3) | `origin/main` | — | follow |
| Enums | T-012 | merged | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Shared jev record module, plus tests | `g3o/common/jev_record.py`†, tests; branch `reclass/t027-record`† | T-021, T-023, T-026, T-028, T-050 | serialises to per-institution JSON artifacts; fields map to DB columns per DEC-004 a; fixes the RS-014 gap (first-chunk ids only) |

#### Execution resources
- Persona/role: engineer (lane eng-b)
- Tools/connectors: Python, pytest
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-b/`†, feature branch from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-012
- Enables: T-015, T-021, T-023, T-026, T-028, T-050
- Can run with: T-003, T-011, T-022 (W3)
- Researcher gates: push of the branch

#### Ownership and collision control
- Read scope: RS-012, RS-013, T-012
- Write claim: new module `g3o/common/jev_record.py`† and its tests
- Shared surfaces: none

#### Procedure boundary
- Included: record and serialisation
- Excluded: DB columns and migration (T-051); API exposure (T-050)
- Fixed decisions: DEC-004 a

#### Spec-change reporting
- Spec version: SPEC v001.4, the Stage 6 locked version once locked
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: jev returns no distribution for a question type
- Stop boundary: none
- Safe continuation: all
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: round-trip tests (record → JSON → record) for every field, including chunk id
- Independent review: T-031
- Acceptance tests: A-013
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass on branch `reclass/t027-record`†, return report filed with the integrator.

#### Chunking trigger
none

### T-028 — Update the Stage 7 writer for v2.7 rows

Status: pending
Type: build
Priority: critical-path
Spec refs: R-015, R-043, R-050, R-051
Decision refs: DEC-005, DEC-016

#### Objective
The CSV writer emits the page verdict, CX fields, full-length supporting text, jev summary fields and an explicit `contract_version` column on every row (DEC-005 a), with the column list as specified in T-050. RC-D-002 row 49: columns for every published item (R-057); codebook release label + setup pointer + `evidence_channel` in place of `contract_version` (r2#32); legacy-column fill (r2#46); `text_source` and the v2.5-rule label (R-059); support status; 9-value counts; e-mail domain + count and unmasked quotes (R-058); A06 / A07; the full quote text stays in CSV (DEC-016 c, r2#17).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| RS-018 writer | `origin/main` | — | stop |
| Enums and row schema | T-012 | merged | stop |
| Support check | T-024 | merged | stop |
| Stage 6 output | T-026 | merged | stop |
| jev answer record | T-027 | merged | stop |
| D-007 column list | T-050 | accepted by Colin (A-019) | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Updated writer, plus tests | `g3o/persist/writer.py`, tests; branch `reclass/t028-writer`† | T-030, T-052, T-090 | column list matches T-050; codebook release label + setup pointer + `evidence_channel` on every row (RC-D-002 row 49; was `contract_version`); supporting text not truncated in CSV (DEC-016 c) |

#### Execution resources
- Persona/role: engineer (lane eng-a)
- Tools/connectors: Python, pytest
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-a/`†, feature branch from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-012, T-015, T-024, T-026, T-027, T-050
- Enables: T-030, T-052, T-090
- Can run with: none (W9)
- Researcher gates: push of the branch

#### Ownership and collision control
- Read scope: RS-018, T-012, T-024, T-026, T-027, T-050
- Write claim: `g3o/persist/writer.py` and its tests
- Shared surfaces: CSV layout, agreed with T-050; integration by T-030

#### Procedure boundary
- Included: writer
- Excluded: DB ingest (T-052)
- Fixed decisions: DEC-005 a; DEC-016 c (full text in data, cap on the website only)

#### Spec-change reporting
- Spec version: SPEC v001.4, the Stage 6 locked version once locked
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a field has no CSV home
- Stop boundary: none
- Safe continuation: all
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: golden CSV for 3 fixture institutions
- Self-check: every row carries `contract_version` (R-050 rejection condition)
- Independent review: T-031
- Acceptance tests: A-007 (via T-095), A-017 (via T-090)
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass on branch `reclass/t028-writer`†, return report filed with the integrator.

#### Chunking trigger
none

### T-030 — Integrate the v2.7 new-run path (code integrator task)

Status: pending
Type: integrate
Priority: critical-path
Spec refs: D-002, R-050, C-007
Decision refs: DEC-013, DEC-020, DEC-021

#### Objective
Integrate the new-run path only: wire the new stages (T-021 to T-028, T-032) into the orchestrator, config and telemetry, merge those card branches into `reclass/v2.7`†, and get a mocked e2e green on the new-run entry point. Pins are not regenerated here; T-035 regenerates them once after the back-fill and transfer paths are merged (DEC-021).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Card branches T-021, T-022, T-023, T-024, T-025, T-026, T-027, T-028, T-032 | feature branches | merge-ready | stop |
| G3O base | `origin/main` `375f1ff` (#135 changed `orchestrator.py` and `tests/test_presweep.py`) | rebased | stop on conflict; report |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Integrated v2.7 pipeline | `g3o/run/presweep/{orchestrator,config}.py`, `g3o/run/telemetry.py`, `tests/test_e2e_presweep_smoke.py`; branch `reclass/v2.7`† | T-029 | new-run e2e green; pins untouched (regenerated in T-035) |

#### Execution resources
- Persona/role: engineer (lane eng-b, owner of `reclass/v2.7`†)
- Tools/connectors: git, Python, pytest
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-b/`†, branch `reclass/v2.7`† (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-021, T-025, T-028, T-032
- Note: the other integrated branches reach this card transitively through T-028 and T-032.
- Enables: T-029
- Can run with: T-052, T-090 (W10)
- Researcher gates: push of the integration branch

#### Ownership and collision control
- Read scope: all card branches
- Write claim: the listed orchestrator, config, telemetry and e2e files; merges of the new-run card branches into `reclass/v2.7`†
- Shared surfaces: orchestrator and the `reclass/v2.7`† branch — owner eng-b (T-030, then T-035); pins and `cli.py` hunks are T-035's

#### Procedure boundary
- Included: wiring, merging the new-run branches, new-run e2e test
- Excluded: stage logic changes (sent back to the owning card); back-fill and transfer merges, `cli.py` hunks and pin regeneration (T-035)
- Fixed decisions: DEC-020 (branch topology); DEC-021 (pins regenerated once, in T-035); DEC-013 a

#### Spec-change reporting
- Spec version: SPEC v001.4, the Stage 6 locked version once locked
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: stage order conflicts with R-040 ("after jev")
- Stop boundary: the e2e test
- Safe continuation: T-090
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: full test suite green on `reclass/v2.7`†
- Self-check: mocked e2e passes through the new-run entry point
- Independent review: T-031
- Failure/rollback: revert merge commits

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Suite green on `reclass/v2.7`† with the new-run e2e passing, return report filed with the integrator.

#### Chunking trigger
none

### T-029 — Build the back-fill entry point

Status: pending
Type: build
Priority: critical-path
Spec refs: R-035, R-036, R-056, R-070, R-071, R-072, R-073, R-074, R-075, R-076, A-005, A-015
Decision refs: DEC-002

#### Objective
A first-class `backfill` command (DEC-002 a) that runs the v2.7 stages for a fixed institution list from stored pages. It covers all pages of the latest run for documented and unclear institutions alike (R-076 v001.4, item 20 a), re-scrapes pages without usable text, follows links, does no re-triage, and gives each institution an end state (R-075). Every back-fill write carries a fresh release id and never reuses an original run_id (PF-004). Rows load hidden until release (R-056). RC-D-002 N32: back-fill rows carry `text_source` (stored vs live re-fetch, R-059); chrome text and links exist only for pages fetched live again (T-014), and the setup record says which.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| RS-017 runner and resume | `origin/main` | — | reuse |
| Integrated pipeline | T-030, `reclass/v2.7`† | green | stop |
| Link following | T-025 | merged | stop |
| Stored-text counts (documented + unclear) | T-001 | done | proceed, report |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Back-fill package and CLI subcommand | `g3o/run/backfill/`†; the `backfill` subcommand hunk for `g3o/cli.py` handed to T-035 as a patch, not written to `cli.py`; branch `reclass/t029-backfill`† | T-034, T-035 | named failure states enumerated; fresh release id; no run_id reuse; rows marked hidden until release |

#### Execution resources
- Persona/role: engineer (lane eng-a)
- Tools/connectors: Python, pytest
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-a/`†, feature branch from `reclass/v2.7`† (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-001, T-025, T-030
- Enables: T-034, T-035
- Can run with: T-053 (W11)
- Researcher gates: push of the branch

#### Ownership and collision control
- Read scope: RS-017, `reclass/v2.7`†, T-001 counts
- Write claim: new package `g3o/run/backfill/`† and its tests
- Shared surfaces: `cli.py` — T-029 hands its subcommand hunk to T-035 (eng-b), the sole writer of `cli.py` hunks

#### Procedure boundary
- Included: entry point, stored-page loading, re-scrape path, end-state accounting
- Excluded: Stages 1-3 (N-004); `none` institutions (N-001), except T-034's transfer owners; the WS10 transfer path (T-034)
- Fixed decisions: DEC-002 a; R-076 v001.4 (all pages for both groups); R-073 (no overwrite)

#### Spec-change reporting
- Spec version: SPEC v001.4, the Stage 6 locked version once locked
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: stored text is missing far above the T-001 counts
- Stop boundary: none
- Safe continuation: all
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: mocked back-fill of 5 institutions, including a no-text page and a raw-PDF page
- Self-check: a test that the entry point refuses to write under an existing run_id, and that rows carry the hidden flag
- Independent review: T-031
- Acceptance tests: A-005, A-015 (at release)
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass on branch `reclass/t029-backfill`†, return report filed with the integrator.

#### Chunking trigger
Split the re-scrape path into its own chunk.

### T-034 — Build the WS10 transfer path

Status: pending
Type: build
Priority: critical-path
Spec refs: R-077, R-071, N-001, C-005, A-022
Decision refs: —

#### Objective
The back-fill codes the 114 WS10 transfer activities (`activity-review-prepared.csv`, RQ-003) under their 45 verified owners, including owners currently published as `none` (item 23 ii, R-077, the N-001 exception). It produces correction-layer records with WS10 dispositions (A-022), and never invents search records or adds to denominators (C-005).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| 114-transfer list, 45 owners | RS-026 `activity-review-prepared.csv` (RQ-003 confirmed authoritative) | as listed | stop |
| Back-fill entry point | T-029 | merged | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Transfer module, plus tests | `g3o/run/backfill/transfers.py`†, tests; branch `reclass/t034-ws10`†; any `cli.py` hunk handed to T-035 as a patch | T-035 | each transfer coded under its verified owner with its WS10 disposition; linked to the original source observation; no search record, draw membership or pipeline stamp invented |

#### Execution resources
- Persona/role: engineer (lane eng-a)
- Tools/connectors: Python, pytest
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-a/`†, feature branch from `reclass/v2.7`† (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-029
- Enables: T-035
- Can run with: none (W12)
- Researcher gates: push of the branch

#### Ownership and collision control
- Read scope: RS-026 list, T-029 package
- Write claim: `g3o/run/backfill/transfers.py`† and its tests
- Shared surfaces: `cli.py` — any hunk handed to T-035 (eng-b), the sole writer of `cli.py` hunks

#### Procedure boundary
- Included: the transfer path inside the back-fill
- Excluded: the incomplete WS10 combined review (R-077: release does not wait for it); attribution transfers beyond the 114 (N-005)
- Fixed decisions: item 23 ii (owners currently `none` included); R-077; C-005

#### Spec-change reporting
- Spec version: SPEC v001.4, the Stage 6 locked version once locked
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a listed transfer's source page or owner cannot be resolved from the list and stored pages
- Stop boundary: that transfer
- Safe continuation: the remaining transfers
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: mocked run of 5 transfers, including one owner currently published as `none`
- Self-check: sweep and denominator counts are unchanged by the transfer path (C-005)
- Independent review: T-031
- Acceptance tests: A-022 (at release)
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Tests pass on branch `reclass/t034-ws10`†, return report filed with the integrator.

#### Chunking trigger
none

### T-035 — Integrate the back-fill and transfer paths

Status: pending
Type: integrate
Priority: critical-path
Spec refs: D-002, D-003, R-050, R-077, C-005, C-007
Decision refs: DEC-002, DEC-013, DEC-020, DEC-021

#### Objective
Merge the T-029 back-fill and T-034 transfer branches into `reclass/v2.7`†, apply their `cli.py` hunks as the sole writer of `cli.py`, get a mocked e2e green through the new-run, back-fill and transfer entry points (PF-018), and regenerate `contract_version_pin.json` and `reproducibility.json` once (DEC-021, moved here from T-030).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| New-run integration | `reclass/v2.7`† (T-030) | green | stop |
| Back-fill branch + `cli.py` subcommand hunk | T-029, `reclass/t029-backfill`† | merge-ready | stop |
| Transfer branch + any `cli.py` hunk | T-034, `reclass/t034-ws10`† | merge-ready | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Fully integrated v2.7 pipeline | `g3o/cli.py`, `tests/goldens/{contract_version_pin,reproducibility}.json`, `tests/test_e2e_presweep_smoke.py` (back-fill and transfer cases); branch `reclass/v2.7`† | T-031, T-041 | e2e green on new-run, back-fill and transfer entry points; pins regenerated once and match extract v2.7 + validate v1.5 (DEC-013 a) |

#### Execution resources
- Persona/role: engineer (lane eng-b, owner of `reclass/v2.7`†)
- Tools/connectors: git, Python, pytest
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-b/`†, branch `reclass/v2.7`† (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-029, T-034
- Enables: T-031, T-041
- Can run with: none (W13)
- Researcher gates: push of the integration branch

#### Ownership and collision control
- Read scope: T-029 and T-034 branches, `reclass/v2.7`†
- Write claim: `g3o/cli.py` hunks, the two pin files, e2e test additions; merges of T-029 and T-034 into `reclass/v2.7`†
- Shared surfaces: `cli.py` and pins — sole owner T-035 (eng-b)

#### Procedure boundary
- Included: merging the back-fill and transfer branches, `cli.py` hunks, back-fill and transfer e2e cases, the single pin regeneration
- Excluded: stage, back-fill or transfer logic changes (sent back to T-029 / T-034)
- Fixed decisions: DEC-002 a; DEC-020; DEC-021 (pins regenerated once, here); DEC-013 a; C-005 (transfers invent no search records)

#### Spec-change reporting
- Spec version: SPEC v001.4, the Stage 6 locked version once locked
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: the back-fill or transfer path cannot run without changing a new-run stage contract, or the pins cannot match the v2.7 / v1.5 labels
- Stop boundary: the pin regeneration and the T-031 handoff
- Safe continuation: e2e cases that do not touch the conflict
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: full test suite green on `reclass/v2.7`†
- Self-check: mocked e2e passes through the new-run, back-fill and transfer entry points (PF-018)
- Self-check: pin test matches extract v2.7 + validate v1.5; pins regenerated exactly once (one commit)
- Self-check: the transfer e2e leaves sweep and denominator counts unchanged (C-005)
- Independent review: T-031
- Failure/rollback: revert merge commits

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Suite green on `reclass/v2.7`† with all three entry-point e2e cases passing, pins regenerated once, return report filed with the integrator.

#### Chunking trigger
none

### T-031 — Independent code and contract review

Status: pending
Type: verify
Priority: required
Spec refs: R-001, R-007, R-025, R-056, R-073, R-087, C-001, C-005, C-006, C-007, C-008, N-004, N-005
Decision refs: DEC-010

#### Objective
A reviewer not involved in T-010 to T-035 checks the fully integrated branch from T-035 (new-run, back-fill and WS10 transfer paths, regenerated pins) against the SPEC and the contract.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Fully integrated pipeline (new-run, back-fill, transfer paths; regenerated pins) | `reclass/v2.7`† (T-035) | green | stop |
| Contract v2.7 with the §4.3 amendment (R-087) | T-010 | signed | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Review report | `C:/Users/spaci/repos/G3O/planning/reviews/Code-Review-T031.md`† | integrator, PI | findings ranked; each with file:line |

#### Execution resources
- Persona/role: independent reviewer, fresh session (lane berivox: Harsh `babulpatel1309`, Geet `geet000`; RC-D-001 D)
- Tools/connectors: Read, Grep, git (read-only), pytest
- Skills/protocols: `planning-adversarial-review-protocol.md`; `/code-review` skill
- Working directory/environment: its own read-only worktree `C:/Users/spaci/worktrees/G3O-reviewer/`†, branch `reclass/v2.7`† at the T-035 head (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-035
- Enables: T-071
- Can run with: T-041 (W14)
- Researcher gates: none

#### Ownership and collision control
- Read scope: all
- Write claim: the review file only
- Shared surfaces: none

#### Procedure boundary
- Included: review
- Excluded: fixes (sent back to the owning cards)
- Fixed decisions: all PI rulings in `Stage5-Rulings.md`

#### Spec-change reporting
- Spec version: SPEC v001.4, the Stage 6 locked version once locked
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a spec conflict is found
- Stop boundary: none
- Safe continuation: all
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Check: no nano-decided code fields (C-001); only character spans from nano reach jev pass 2 (DEC-010 a)
- Check: CX wording byte-diff against the re-signed CX version, CX-01.3† (R-025 v001.6; RC-D-002 row 39; was: against the frozen CX-01.2 text)
- Check (RC-D-002 N30): the codebook generators and CI (T-013): generated files match the codebook, generators assemble signed text verbatim, and the A-001 linkage holds
- Check (RC-D-002 N30): the quote step's named selections stay within the C-001 v001.6 list, each with a quote and a support check
- Check: pin test (C-007) on the pins regenerated in T-035
- Check: the procurement §4.3 amendment is present in contract v2.7 under the same version bumps, extract v2.7 + validate v1.5 (R-087)
- Check: no `pilot_v1` input and no `inputs/` writes (C-006, C-008)
- Check: the Stage 1-3 diff is empty except link intake (N-004)
- Check: no write under an original run_id; the hidden-until-release flag is set on v2.7 rows (R-056, R-073)
- Check: the transfer path invents no search records and adds nothing to denominators (C-005)

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Review filed; all critical findings closed by the owning cards.

#### Chunking trigger
Split pipeline review from contract review.

### T-040 — Build the v2.7 fixture set

Status: pending
Type: build
Priority: required
Spec refs: A-003, A-004, A-010, A-011, A-012, A-020, A-021, A-022, R-084, C-006
Decision refs: DEC-006

#### Objective
Labelled fixtures under DEC-006 c:
- synthetic pages for mechanics: hops, dedup, cap reached, loops, chunk combination;
- real pages for verdicts and CX coding: all 8 page verdicts (RC-D-002 row 50: all 9, incl. page-stated absence), the GenAI boundary, C2-C4, consolidation cases, multi-activity pages;
- RC-D-002 row 50 adds fixtures for: S1 translation; S2 `background_only` in `no`; the S3 order on chunked pages; S5 units and relations (R-017); S6 multi-select; C04 unit / parent / joint; A01 bases; X01 / X03 boundaries; X29 failure cases; applicability by activity_type; four-answer safeguards; the CX-61 gate; the new fields; calendar years; chrome-text contact / e-mail cases;
- WS10 transfer fixtures for T-034.
Real ones are labelled by the agent, then by the PI.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| RS-011 `exval_cases` (30) | `052fcb2` | — | adapt |
| RS-005 answers, RS-024 readcheck40 | Drive | — | mine |
| RS-008 / RS-009 pages | local | — | mine |
| Contract v2.7 | T-010 | signed | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Fixture set + label sheet | `tests/fixtures/v27/`† + label sheet; branch `reclass/t040-fixtures`† | T-041 | each fixture: expected value + PI label ref; synthetic/real marked |

#### Execution resources
- Persona/role: researcher session (lane integrator) with engineer support; PI labelling
- Tools/connectors: Read, Python
- Skills/protocols: none beyond this plan
- Working directory/environment: integrator worktree `C:/Users/spaci/worktrees/G3O-integrator/`†, feature branch from `origin/main` `375f1ff` (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-010
- Enables: T-041
- Can run with: T-002, T-012, T-014, T-016, T-061, T-063 (W2)
- Researcher gates: PI labels and approves expected values for real-page fixtures

#### Ownership and collision control
- Read scope: RS-005, RS-008, RS-009, RS-011, RS-024, T-010
- Write claim: `tests/fixtures/v27/`† and the label sheet
- Shared surfaces: none

#### Procedure boundary
- Included: fixtures and labels
- Excluded: pilot v1 as any source (C-006); agent-read material (T-081)
- Fixed decisions: DEC-006 c

#### Spec-change reporting
- Spec version: SPEC v001.4, the Stage 6 locked version once locked
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a case has no defined expected value under the contract
- Stop boundary: that case
- Safe continuation: the remaining cases
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: every listed A-ID has at least 3 fixtures
- Independent review: PI approves the real-page labels
- Acceptance tests: A-003, A-004, A-010, A-011, A-012, A-020, A-021 (run in T-041)
- Failure/rollback: branch

#### Decision points
- DP-031: How many fixtures per acceptance ID
  - Default: at least 3 per A-ID, as in the draft card
  - Recommendation: at least 3 per A-ID, more for A-011 (one per page-verdict value) — keeps PI labelling time bounded while covering every value

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Fixture set committed on its branch, with PI-approved labels for every real-page fixture.

#### Chunking trigger
Split per A-ID.

### T-041 — Run the fixtures on the integrated pipeline (paid, small)

Status: blocked
Type: verify
Priority: critical-path
Spec refs: A-003, A-004, A-010, A-011, A-012, A-013, A-020, A-021, A-022, R-084
Decision refs: DEC-014

#### Objective
A real jev/nano run of the T-040 fixtures through `reclass/v2.7`†, via the new-run entry point, the back-fill entry point and the transfer path (PF-018), with pass/fail per A-ID. Inside the same paid gate it also runs a small back-fill on at most 5 real institutions keyed to their real original observation ids, whose output feeds T-054's rehearsal of the correction-to-original links (A-006, DEC-001 a). The run is paid, so the agent prepares the exact command and a cost estimate, and Simone runs it (global red line 4, ruling 2026-10-28).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Support check | T-024 | merged | stop |
| Fully integrated pipeline (new-run, back-fill, transfer paths) | T-035, `reclass/v2.7`† | green | stop |
| ≤5 real back-fill institutions with their original observation ids | chosen from the T-001 counts; stored pages on the droplet | listed in the report | stop the real-id subset; fixtures continue |
| Fixture set | T-040 | PI-approved | stop |
| jev and OpenAI keys | RS-031, environment | valid | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Fixture-run results and report | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/fixture-run/`† + `T041-REPORT.md`† | T-054, T-060, T-071, PI | per-fixture expected vs got, per entry point; cost estimate vs actual |
| Real-id back-fill output (≤5 institutions) | fixture-run folder, `real-id-subset/`† | T-054 | rows keyed to real original observation ids, fresh release id, hidden flag set |

#### Execution resources
- Persona/role: engineer (lane eng-b)
- Tools/connectors: Python; command prepared for Simone to run as `! <command>`
- Skills/protocols: none beyond this plan
- Working directory/environment: lane worktree `C:/Users/spaci/worktrees/G3O-eng-b/`†, branch `reclass/v2.7`† (never the shared checkout `C:/Users/spaci/repos/G3O`)

#### Dependencies
- Requires: T-024, T-035, T-040
- Enables: T-054, T-060, T-071
- Can run with: T-031 (W14)
- Researcher gates: PI approves the cost estimate and runs the paid fixture run and the real-id subset via `! <command>`; SSH to read the subset's stored pages needs PI authorisation; PI rules on fixture failures

#### Ownership and collision control
- Read scope: `reclass/v2.7`†, fixtures
- Write claim: the fixture-run folder
- Shared surfaces: none

#### Procedure boundary
- Included: preparing the command and cost estimate, then reporting on the run Simone launches
- Excluded: running any paid call itself; fixing failures (sent back to the owning cards)
- Fixed decisions: red line 4 (paid calls run by Simone); DEC-014 b (procurement delta follows this task)

#### Spec-change reporting
- Spec version: SPEC v001.4, the Stage 6 locked version once locked
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: systematic failures trace to contract wording
- Stop boundary: T-071
- Safe continuation: T-090, T-050
- Forbidden: editing `SPEC.md`, `RESOURCES.md`, `PLAN.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: every listed A-ID reported, for each entry point
- Self-check: the real-id subset's rows carry their original observation ids, a fresh release id and the hidden flag
- Independent review: PI reads the failures
- Acceptance tests: A-003, A-004, A-010, A-011, A-012, A-013, A-020, A-021, A-022
- Failure/rollback: n/a (no live state changed)

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
All fixtures pass, or each failure is PI-ruled; report filed with the integrator.

#### Chunking trigger
More than one rerun cycle → new card.

### T-050 — Write the D-007 interface specification for Colin

Status: pending
Type: document
Priority: critical-path
Spec refs: D-007, R-043, R-050, R-051, R-052, R-055, R-056, R-073, A-019, C-005
Decision refs: DEC-001, DEC-004, DEC-005, DEC-015, DEC-016

#### Objective
An accepted interface specification giving Colin the exact fields, types, version display, most-recent rule, hidden-fields rule (Q-021 a), release flag, back-fill visibility (R-055, R-056), and the correction-layer interface, delivered as GitHub issues on g3o-api / g3o-website. RC-D-002 row 49: columns for every published item (R-057), with only confirmed activities in the public activity table (r2#51); codebook release label + setup pointer + `evidence_channel` in place of `contract_version` (r2#32); legacy-column fill (r2#46); `text_source` and the v2.5-rule label (R-059); support status; 9-value counts; e-mail domain + count and unmasked quotes (R-058); X41 display-only translation on the website; A06 / A07; full quote text in CSV / API (DEC-016 c, r2#17). Under Q6 the generated data dictionary owns the published definitions, and the API's evidence-status doc (g3o-api `docs/evidence-status-contract.md`) is restated for 9 values.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Contract v2.7 + validate v1.5 | T-010 | PI-signed | stop |
| Enum/schema constants + touchpoint inventory | T-012 | merged | stop |
| Shared jev answer record | T-027 | merged | stop |
| g3o-api schema, API contract doc | RS-020, RS-023 (`acdb030`) | as of 2026-10-28 | stop |
| `backfill_verdicts.py` safety pattern and `sql/007` refresh-trigger note | g3o-api `scripts/backfill_verdicts.py` (`acdb030`) | read | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| D-007 interface spec | `C:/Users/spaci/repos/G3O/planning/handoffs/D-007-interface-spec.md`† | Colin, T-028, T-051, T-052, T-053 | Covers: correction tables linked to original observation ids + most-recent projection view (DEC-001 a); `contract_version` column on every row (DEC-005 a); jev columns (confidence, model id, request id) with the distribution jsonb not served by the API (DEC-004 a); history parameter/endpoint for older rows (DEC-015 a); full supporting text in API, website display cap (DEC-016 c); release flag hiding every v2.7 row until release (R-056); ownership of `v_wave_*` views, materialized aggregates, `sql/013..020` and refresh, including an explicit refresh + watermark check because `sql/007` does not fire on updates (PF-007); ordinary runs keep per-wave latest-run-wins under wave windows, correction rows wave-free (R-055); ingest guard refusing a back-fill that reuses an original run_id (PF-004); `scripts/export_bulk.py` + `scripts/test_export_bulk.py` updated for v2.7 fields (PF-023); CSV column list agreed with T-028; acceptance block for A-019; the RC-D-002 row 49 additions |
| GitHub issues | g3o-api and g3o-website issues linking the spec | Colin | One issue per downstream card (T-051, T-052, T-053) unless DP-060 is changed |

#### Execution resources
- Persona/role: integrator (researcher session acting for the PI, DEC-012 a)
- Tools/connectors: Read/Grep over the three repos; `gh` for issues (external-message gate)
- Skills/protocols: `planning-protocol.md`; no prose drafting beyond field specification
- Working directory/environment: `C:/Users/spaci/repos/G3O/planning/`

#### Dependencies
- Requires: T-010, T-012, T-027
- Enables: T-028, T-051
- Can run with: T-015, T-021
- Researcher gates: PI approves the spec before it is sent; posting the GitHub issues is an external message

#### Ownership and collision control
- Read scope: G3O, g3o-api, g3o-website at the base refs; SPEC v001.4
- Write claim: `C:/Users/spaci/repos/G3O/planning/handoffs/D-007-interface-spec.md`†
- Shared surfaces: CSV/API field list — agreed between T-030 owner (eng-b) and Colin; this card drafts it

#### Procedure boundary
- Included: interface specification and its delivery
- Excluded: API, migration and site code (T-051..T-053)
- Fixed decisions: DEC-001 a, DEC-004 a, DEC-005 a, DEC-015 a, DEC-016 c, R-056, item 24 b, item 25 i

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: Colin rejects a field or shape; a required view/aggregate cannot honour R-055 or R-056
- Stop boundary: T-051
- Safe continuation: pipeline cards
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: every published field in the T-028 column list appears in the spec
- Self-check: every item in the Outputs contract is present
- Independent review: Colin's acceptance (A-019)
- Failure/rollback: n/a (document)

#### Decision points
- DP-060: Deliver the spec to Colin as one GitHub issue per downstream card, or one umbrella issue per repo
  - Default: one issue per downstream card (T-051, T-052 on g3o-api; T-053 on g3o-website), each linking the spec
  - Recommendation: one issue per card — each card's acceptance and review stays separately traceable

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Spec file written, PI-approved, issues posted, and Colin's acceptance recorded (A-019).

#### Chunking trigger
none

### T-051 — g3o-api migration: correction layer, per-row version, jev fields, page verdict

Status: pending
Type: migrate
Priority: critical-path
Spec refs: R-015, R-026, R-036, R-050, R-051, R-055, R-056, R-073, C-005
Decision refs: DEC-001, DEC-004, DEC-005

#### Objective
Reviewed forward and down migrations implementing T-050: new correction tables linked to original observation ids plus a most-recent projection view (DEC-001 a), release flag, `contract_version` column, jev columns, 8-value page verdict — additive only. RC-D-002 row 49: the T-050 additions, incl. the codebook release label + setup pointer + `evidence_channel` columns and the 9-value page verdict.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| D-007 interface spec | T-050 | accepted by Colin | stop |
| g3o-api schema and migrations `sql/000-020` | RS-020, g3o-api `acdb030` | as of base ref | stop |
| `scripts/backfill_verdicts.py` | g3o-api `acdb030` | read | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Forward migration | `g3o-api/sql/021_reclass_v27.sql`† | T-052, T-054, T-055, T-074 | No ALTER of original values; added columns nullable; correction tables + projection view; release flag; `contract_version`; jev columns |
| Down migration | `g3o-api/sql/down/021_reclass_v27.sql`† | T-054, T-055, T-074 | Restores pre-021 schema without touching original rows |
| Correction loader | `g3o-api/scripts/load_corrections.py`† | T-054, T-074 | Built on the `backfill_verdicts.py` safety pattern: dry-run by default, `--apply` required, shared parse function with ingest, explicit refresh + watermark verification |

#### Execution resources
- Persona/role: Colin (owner); fallback an engineer session under PI sign-off (item 25 ii)
- Tools/connectors: git on Colin's branch; disposable Neon branch for self-checks (PI-gated; Simone-run creation if billed)
- Skills/protocols: g3o-api migration idiom (`create … if not exists`, guarded constraints, per `sql/008` header)
- Working directory/environment: `C:/Users/spaci/repos/g3o-api` (Colin's branch)

#### Dependencies
- Requires: T-050
- Enables: T-052, T-054
- Can run with: T-023, T-025
- Researcher gates: PI authorises creation of and writes to the disposable branch used by this card's self-check; Neon branch creation, snapshots and writes each need a named PI gate; Neon branches and snapshots are free (Simone, 2026-10-28), so the agent runs these commands itself once the PI gate has passed; live apply is the T-055 gate; push on Colin's branch

#### Ownership and collision control
- Read scope: g3o-api repo
- Write claim: `sql/021*`†, `sql/down/021*`†, `scripts/load_corrections.py`†
- Shared surfaces: DB schema — sole owner Colin

#### Procedure boundary
- Included: DDL, down migration, correction loader
- Excluded: data load (T-074), ingest and endpoints (T-052)
- Fixed decisions: DEC-001 a (no in-place UPDATE of `g3o.sweeps`; no reclassification run rows), R-073, C-005

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: R-073 no-overwrite conflicts with existing triggers or views; a projection cannot be built without touching `g3o.sweeps`
- Stop boundary: T-052
- Safe continuation: other cards
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: apply and down on a disposable branch; schema diff shows only additive objects
- Self-check: loader dry-run prints planned writes and touches nothing
- Independent review: T-054 rehearsal
- Failure/rollback: down migration

#### Decision points
- DP-061: Implement the most-recent projection as a plain view or a materialized view
  - Default: plain view
  - Recommendation: plain view first, materialize only if T-054 timings show API latency problems — avoids adding another refresh dependency (PF-007)

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Forward + down migrations and loader reviewed on Colin's branch; disposable-branch apply/down clean.

#### Chunking trigger
Split the correction layer from the new columns if the migration exceeds one review.

### T-052 — g3o-api ingest and endpoints for v2.7

Status: pending
Type: build
Priority: critical-path
Spec refs: R-043, R-050, R-051, R-052, R-055, R-056, G-004
Decision refs: DEC-004, DEC-015, DEC-016

#### Objective
Ingest reads T-028 CSVs; the API serves v2.7 fields, version label, most-recent selection, older rows via the history parameter (DEC-015 a), full supporting text, back-fill rows outside wave gating, and hides all v2.7 rows until release (R-056); aggregates refresh and bulk export updated. RC-D-002 row 49: serves the T-050 additions (every published item, confirmed activities only, support status, 9-value counts, e-mail domain + count, unmasked full quotes, `text_source` and the v2.5-rule label).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Migration | T-051 | reviewed | stop |
| Golden v2.7 CSVs | T-028 | merged | stop |
| D-007 spec | T-050 | accepted | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Ingest | `g3o-api/scripts/ingest.py` | T-054, T-055, T-074 | Reads v2.7 columns; refuses a back-fill load that reuses an original run_id (PF-004) |
| API worker | `g3o-api/worker/src/index.js`, `g3o-api/schema/schema_core.sql` | T-053, public | Most-recent row by default, history parameter, version label, release flag honoured, distribution jsonb not served |
| Aggregates | `v_wave_*` views, materialized aggregates (`sql/013..020`) and refresh path | T-074, site | Explicit refresh + watermark check after any correction load (PF-007); ordinary runs keep per-wave latest-run-wins (item 24 b) |
| Bulk export | `g3o-api/scripts/export_bulk.py`, `scripts/test_export_bulk.py` | #175 lane | v2.7 fields and `contract_version` exported (PF-023) |
| API contract doc | RS-023 | Colin, public | Updated for v2.7 |

#### Execution resources
- Persona/role: Colin; fallback engineer session under PI sign-off
- Tools/connectors: git; `verify_api.py`; staging worker
- Skills/protocols: g3o-api conventions
- Working directory/environment: `C:/Users/spaci/repos/g3o-api` (Colin's branch)

#### Dependencies
- Requires: T-028, T-051
- Enables: T-053, T-054, T-055, T-074
- Can run with: T-030, T-090
- Researcher gates: deploy to staging only (production deploy is T-055); push on Colin's branch

#### Ownership and collision control
- Read scope: g3o-api, T-028 outputs
- Write claim: Colin's files listed in Outputs
- Shared surfaces: API contract — Colin

#### Procedure boundary
- Included: ingest, endpoints, aggregates refresh path, bulk export, staging deploy
- Excluded: index endpoints (N-003); website (T-053); production deploy (T-055)
- Fixed decisions: DEC-015 a, DEC-016 c, DEC-004 a (no distribution in API), R-056, item 24 b

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: most-recent selection conflicts with wave logic; the release flag cannot hide ordinary-run v2.7 rows
- Stop boundary: T-053
- Safe continuation: other cards
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: `verify_api.py` against staging
- Self-check: unreleased v2.7 rows absent from every public endpoint and aggregate
- Self-check: `test_export_bulk.py` passes with v2.7 fields
- Independent review: T-054
- Failure/rollback: worker revert

#### Decision points
- DP-062: Expose older rows as a query parameter on existing endpoints or as a separate history endpoint
  - Default: query parameter on existing institution endpoints
  - Recommendation: query parameter — one contract surface, fewer endpoints to document and test

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Staging API passes `verify_api.py` and the hidden-row and export checks.

#### Chunking trigger
Split ingest from worker changes.

### T-053 — Website changes for v2.7

Status: pending
Type: build
Priority: required
Spec refs: R-043, R-051, R-052, R-053 residual (Q-021 a), R-054, R-056, N-003
Decision refs: DEC-015, DEC-016

#### Objective
The staging site shows each institution's most recent row with its version label, new fields and supporting text (with the website display cap and access to the full text), hides new fields where the most recent row is v2.5, and shows no index UI. RC-D-002 row 49: shows the T-050 additions, incl. confirmed activities only, e-mail domain + count, the v2.5-rule label and the X41 display-only translation.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Staging API | T-052 | staged | stub responses |
| Website | RS-022, g3o-website `282ca6a` | re-check at start | stop |
| Website display cap value | PI, after T-003 | set | placeholder, blocks done |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Site changes | `src/pages/Institution.jsx`, `src/data/vocabulary.js`, `src/copy.js`, tests | T-095, public | Most-recent row + version label; supporting text capped with marker and "show full"; v2.5-latest rows hide new fields; copy strings PI-approved |

#### Execution resources
- Persona/role: Colin; fallback engineer session under PI sign-off
- Tools/connectors: git; site test runner
- Skills/protocols: g3o-website conventions
- Working directory/environment: `C:/Users/spaci/repos/g3o-website` (Colin's branch)

#### Dependencies
- Requires: T-052
- Enables: T-095
- Can run with: T-029
- Researcher gates: PI approves public copy and the display cap value; deploy gate

#### Ownership and collision control
- Read scope: g3o-website, staging API
- Write claim: Colin's files listed in Outputs
- Shared surfaces: none

#### Procedure boundary
- Included: UI
- Excluded: indices (N-003); API (T-052)
- Fixed decisions: DEC-016 c, Q-021 a

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: hiding fields conflicts with the existing layout
- Stop boundary: none
- Safe continuation: all
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: site tests
- Independent review: T-095 (A-007)
- Failure/rollback: GitHub Pages revert

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Staging site reviewed with PI-approved copy and cap value.

#### Chunking trigger
none

### T-054 — Rehearse migration, load and rollback on a disposable DB branch

Status: blocked (gate: Neon branch creation + writes)
Type: verify
Priority: critical-path
Spec refs: A-006, R-055, R-056, R-073, C-005
Decision refs: DEC-001

#### Objective
On a disposable Neon branch cut from live `br-wave1-cutover` (PF-004), apply T-051, ingest T-041 output including its real-id back-fill subset (≤5 institutions keyed to real original observation ids, so correction-to-original links are exercised: A-006, DEC-001 a), show no original value changed (A-006), verify hidden-until-release, the history parameter (R-051), correction rows visible regardless of wave windows (R-055) and refresh/watermark behaviour, roll back by release id and down migration, and record timings.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Migration + loader | T-051 | reviewed | stop |
| Ingest + endpoints | T-052 | reviewed | stop |
| Fixture-run outputs | T-041 | done | stop |
| Real-id back-fill subset (≤5 institutions, real original observation ids) | T-041 | done | stop |
| Neon access | memory g3o-access-surfaces | PI-authorised | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Rehearsal report | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/rehearsal/T054-REPORT.md`† | T-055, T-074 | Diff empty on original columns and rows; correction rows linked to real original ids; rollback by release id clean; down restores; refresh moved the watermark; unreleased rows not public; history parameter returns older rows; correction rows visible outside wave windows; timings |

#### Execution resources
- Persona/role: eng-b with Colin
- Tools/connectors: Neon branch tooling (SQL-only role creation per memory), psql/psycopg, `verify_api.py`
- Skills/protocols: none beyond this card
- Working directory/environment: disposable Neon branch only; any G3O code from `C:/Users/spaci/worktrees/G3O-eng-b/`†

#### Dependencies
- Requires: T-041, T-051, T-052
- Enables: T-055, T-074
- Can run with: T-060
- Researcher gates: PI authorises creation of and writes to the disposable branch; Neon branch creation, snapshots and writes each need a named PI gate; Neon branches and snapshots are free (Simone, 2026-10-28), so the agent runs these commands itself once the PI gate has passed

#### Ownership and collision control
- Read scope: live branch (branch source only)
- Write claim: the disposable Neon branch; rehearsal folder†
- Shared surfaces: none

#### Procedure boundary
- Included: rehearsal
- Excluded: live branch writes (T-074)
- Fixed decisions: DEC-001 a, R-056

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: rollback is not clean; any original value changes
- Stop boundary: T-055
- Safe continuation: docs
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: row-count and hash diff of original columns and rows before/after (A-006)
- Self-check: refresh watermark moved after load
- Self-check: unreleased rows absent from public endpoints
- Self-check: correction rows link to real original observation ids (real-id subset)
- Self-check: history parameter returns older rows (R-051)
- Self-check: correction rows visible regardless of wave windows (R-055)
- Independent review: integrator
- Failure/rollback: drop the disposable branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Clean apply, load, rollback and down on live-copy data, with report.

#### Chunking trigger
none

### T-055 — Take the v2.7 schema and ingest live before deploy

Status: blocked (gate: live DB write + production deploy)
Type: migrate
Priority: critical-path
Spec refs: R-055, R-056, R-073, A-006, C-005
Decision refs: DEC-001

#### Objective
After T-054 passes, migration 021 is applied to live `br-wave1-cutover` (after a pre-apply snapshot) and T-052's ingest and worker are deployed to production, verified so that v2.5 ordinary runs still ingest and publish as before and a synthetic v2.7 row loads hidden (R-056), with refresh/watermark behaviour checked. This makes item 21 b real: ordinary v2.7 runs after the T-071 deploy load hidden until release.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Rehearsal report | T-054 | clean | stop |
| Migration + down migration | T-051 | reviewed | stop |
| Ingest + worker | T-052 | staging green | stop |
| Neon access | memory g3o-access-surfaces | PI-authorised | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Pre-apply snapshot | Neon branch of live taken just before apply† | rollback | Restorable |
| Live schema | migration 021 applied on `br-wave1-cutover` | T-071, T-074, ordinary runs | Additive only; originals untouched (A-006) |
| Production ingest/worker | g3o-api production deploy | T-071, T-074 | v2.5 rows ingest and publish unchanged; v2.7 rows hidden until release |
| Go-live record | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/golive/T055-GOLIVE.md`† | T-071, integrator | Snapshot name; apply log; v2.5 ingest check; synthetic v2.7 hidden-row check; watermark before/after |

#### Execution resources
- Persona/role: Colin (owner); fallback an engineer session under PI sign-off (item 25 ii)
- Tools/connectors: Neon (snapshot), psql/psycopg, g3o-api deploy, `verify_api.py`
- Skills/protocols: memory g3o-access-surfaces, g3o-wave-window-gates-visibility
- Working directory/environment: `C:/Users/spaci/repos/g3o-api` (Colin's branch); live Neon branch `br-wave1-cutover`

#### Dependencies
- Requires: T-052, T-054
- Enables: T-071, T-074
- Can run with: none
- Researcher gates: PI authorises the live DB write (snapshot + apply) and the production deploy; Neon branch creation, snapshots and writes each need a named PI gate; Neon branches and snapshots are free (Simone, 2026-10-28), so the agent runs these commands itself once the PI gate has passed

#### Ownership and collision control
- Read scope: g3o-api, live DB
- Write claim: live DB schema (migration 021); production worker; golive folder†
- Shared surfaces: DB schema and API — sole owner Colin

#### Procedure boundary
- Included: snapshot, live apply of 021, production deploy of ingest/worker, go-live checks
- Excluded: back-fill load (T-074); release (T-095); pipeline deploy (T-071)
- Fixed decisions: DEC-001 a, R-056, item 21 b

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: v2.5 ingest or publication changes after apply; a synthetic v2.7 row is publicly visible; any original value changes
- Stop boundary: T-071
- Safe continuation: docs
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: hash diff of original columns and rows before/after apply (A-006)
- Self-check: a v2.5 ordinary-run CSV ingests and publishes exactly as before the deploy
- Self-check: a synthetic v2.7 row loads and is absent from every public endpoint and aggregate (R-056)
- Self-check: explicit refresh moves the watermark
- Independent review: integrator
- Failure/rollback: down migration + restore from the pre-apply snapshot; revert the worker

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
021 live, production ingest/worker deployed, all go-live checks recorded, PI informed.

#### Chunking trigger
Split the live apply from the production deploy if either needs a separate maintenance window.

### T-060 — Send the D-008 delta to the procurement integrator

Status: pending
Type: integrate
Priority: critical-path
Spec refs: D-008, R-085, R-087, C-007, A-018
Decision refs: DEC-013, DEC-014

#### Objective
After T-041 passes and before deployment (DEC-014 b), the procurement integrator accepts a delta listing the old→new enum mapping (4-value `genai_evidence` → 8-value page verdict; 9 values under R-015 v001.6), version pins (extract v2.7, validate v1.5; per C3 a, a pinned codebook release) and the §4.3 amendment status (R-087) (PF-022). RC-D-002 row 51: the delta content is SPEC D-008 v001.6 (schedule row 27). A heads-up draft (not sent) is prepared once the codebook is settled (Q1, Q4: procurement's stale documents). Procurement's plan change and migration are ruled by the PI in that plan (r2#12); acceptance stays before deploy (DEC-014 b).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Contract v2.7 | T-010 | PI-signed | stop |
| Enum surfaces | T-012 | merged | stop |
| Fixture pass | T-041 | passed | stop |
| Procurement plan | RS-029, `C:/Users/spaci/repos/g3o-wt-procurement/procurement/planning/` | read-only | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Delta | `C:/Users/spaci/repos/G3O/planning/handoffs/D-008-procurement-delta.md`† | procurement integrator | Old→new mapping; pins; §4.3 status; timing |
| Delivery | email via Simone (procurement DEC-010) + comment on G3O #134 | procurement integrator | Acceptance recorded for A-018 |

#### Execution resources
- Persona/role: integrator
- Tools/connectors: `gh` (external-message gate); email sent by Simone
- Skills/protocols: none beyond this card
- Working directory/environment: `C:/Users/spaci/repos/G3O/planning/`

#### Dependencies
- Requires: T-010, T-012, T-041
- Enables: T-071
- Can run with: T-054
- Researcher gates: PI approves delta text; posting and email are external

#### Ownership and collision control
- Read scope: procurement plan (read-only), G3O contract files
- Write claim: `planning/handoffs/D-008-procurement-delta.md`†
- Shared surfaces: none (never edits procurement files)

#### Procedure boundary
- Included: delta and delivery
- Excluded: procurement code
- Fixed decisions: DEC-013 a, DEC-014 b, R-087

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: procurement asks to keep 4 values or rejects the §4.3 wording
- Stop boundary: T-071
- Safe continuation: all else
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: delta lists every enum surface from T-012's inventory
- Independent review: procurement integrator's acceptance (A-018)
- Failure/rollback: n/a

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Acceptance recorded on G3O #134 and in the delta file.

#### Chunking trigger
none

### T-061 — Notify the G3O validation plan of the contract change

Status: pending
Type: integrate
Priority: required
Spec refs: N-002, C-007, D-001
Decision refs: DEC-013

#### Objective
The G3O validation plan's integrator (`C:/Users/spaci/repos/g3o_validation/planning/`, BL-001) receives a notice that this plan changes the output contract, naming the codebook release label (RC-D-002 N31, C3 a; extract v2.7 / validate v1.5 are recorded in the setup record), with timing against deployment, so its contract-pinned comparison inputs (its SRC-12) can be assessed by that plan (PF-020).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Contract v2.7 labels and scope | T-010 | PI-signed | stop |
| Validation plan governance | RS-033, `C:/Users/spaci/repos/g3o_validation/planning/` (SPEC builder-v004.3, PLAN plan-v001, Baseline-Lock-2026-10-27.json) | read-only | report, send notice anyway |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Notice | `C:/Users/spaci/repos/G3O/planning/handoffs/validation-notice.md`† | validation plan integrator | Labels, timing, statement that this plan does not edit the validation plan |
| Message | coord mailbox message to the validation plan's integrator | validation plan integrator | Links the notice |

#### Execution resources
- Persona/role: integrator
- Tools/connectors: Read; coord mailbox write
- Skills/protocols: `coord/SPEC.md` mailbox schema
- Working directory/environment: `C:/Users/spaci/repos/G3O/planning/`

#### Dependencies
- Requires: T-010
- Enables: T-071
- Can run with: T-002, T-012, T-014, T-016, T-040, T-063 (W2)
- Researcher gates: PI approves the notice text

#### Ownership and collision control
- Read scope: validation plan files (read-only)
- Write claim: `planning/handoffs/validation-notice.md`†; one mailbox file
- Shared surfaces: none (never edits the validation plan's files)

#### Procedure boundary
- Included: notice and message
- Excluded: any change to the validation plan (its integrator decides)
- Fixed decisions: N-002 (validation is a separate plan), DEC-013 a

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: the validation plan states that the contract change breaks a locked input
- Stop boundary: T-071
- Safe continuation: all other cards
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: notice names both version labels and the deployment timing
- Independent review: PI approves text
- Failure/rollback: n/a

#### Decision points
- DP-063: Send the notice by coord mailbox to the validation plan's integrator or by email via Simone
  - Default: coord mailbox message plus the notice file
  - Recommendation: coord mailbox — both plans run on this machine and the validation plan's integrator reads its mailbox

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
PI-approved notice delivered; receipt or reply recorded.

#### Chunking trigger
none

### T-062 — Send the D-009 delta to the AI-text-detection lane (RC-D-002 C, N29)

Status: pending
Type: integrate
Priority: required
Spec refs: D-009, C-007
Decision refs: none (RC-D-002 C, C6 b, Q1, Q5)

#### Objective
Sibling of T-060 for the AI-text-detection lane. After v2.7 deploys (C6 b), the AI-text-detection owner receives a delta, drafted per SPEC D-009 (schedule row 36), that moves the AI-text pipeline from its vendored `g3o/common/contract.py` to a pinned codebook release. It targets the cue SPEC (LOCKED v1.3) and the PI pilot spec (Q5). It is drafted, not sent, until the PI approves (Q1).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Codebook release | T-010, T-013 | signed, deployed | stop |
| Deployed v2.7 | T-071 | deployed | stop |
| AI-text repo, cue SPEC, PS v1 | RS-038 | read-only | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Delta | `C:/Users/spaci/repos/G3O/planning/handoffs/D-009-ai-text-delta.md`† | AI-text-detection owner | every D-009 item; release pin; timing |
| Delivery | channel chosen by the PI | AI-text-detection owner | acceptance recorded |

#### Execution resources
- Persona/role: integrator
- Tools/connectors: Read; external message gated on the PI
- Skills/protocols: none beyond this card
- Working directory/environment: `C:/Users/spaci/repos/G3O/planning/`

#### Dependencies
- Requires: T-071
- Enables: none
- Can run with: T-070 (W18)
- Researcher gates: PI approves delta text; sending is external

#### Ownership and collision control
- Read scope: AI-text repo (read-only), the codebook
- Write claim: `planning/handoffs/D-009-ai-text-delta.md`†
- Shared surfaces: none (never edits AI-text files)

#### Procedure boundary
- Included: delta and delivery
- Excluded: AI-text code and plan files
- Fixed decisions: C6 b (after v2.7 deploys); Q1 (drafted, not sent); Q5 (targets)

#### Spec-change reporting
- Spec version: SPEC v001.6 (RC-D-002)
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: the AI-text plan has no integrator or locked plan to receive the delta (RC-D-002 C, open)
- Stop boundary: this card
- Safe continuation: all else
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: the delta covers every D-009 item
- Independent review: PI approves text
- Failure/rollback: n/a

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
PI-approved delta delivered; acceptance recorded in the delta file.

#### Chunking trigger
none

### T-063 — Send the calendar-conversion heads-up to the multilingual subproject (RC-D-002 L, N23)

Status: pending
Type: integrate
Priority: required
Spec refs: D-010
Decision refs: none (RC-D-002 L, procedural; Q1)

#### Objective
The multilingual subproject (`subprojects/multilingual-pipeline/`, RS-040) receives a heads-up asking for the calendar and fiscal-year conversion rule the year method needs (r2#50), and noting that language coverage is its shared item and the language-barrier flag is dropped (r2#39, P16a). Drafted, not sent, until the PI approves (Q1).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Year method and language items | codebook, T-010 | settled | stop |
| Multilingual subproject files | RS-040 | read-only | report |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Heads-up | `C:/Users/spaci/repos/G3O/planning/handoffs/D-010-multilingual-heads-up.md`† | multilingual subproject | the rule requested, the items it serves, timing against T-011 |
| Delivery | channel chosen by the PI | multilingual subproject | reply recorded |

#### Execution resources
- Persona/role: integrator
- Tools/connectors: Read; external message gated on the PI
- Skills/protocols: the subproject's `CLAUDE.md` / `AGENTS.md` (read-only)
- Working directory/environment: `C:/Users/spaci/repos/G3O/planning/`

#### Dependencies
- Requires: T-010
- Enables: none (the rule it asks for is an input to T-011)
- Can run with: T-002, T-012, T-014, T-016, T-040, T-061 (W2)
- Researcher gates: PI approves the text; sending is external

#### Ownership and collision control
- Read scope: subproject files (read-only)
- Write claim: `planning/handoffs/D-010-multilingual-heads-up.md`†
- Shared surfaces: none (never edits the subproject's files)

#### Procedure boundary
- Included: heads-up and delivery
- Excluded: writing the conversion rule (the subproject owns it)
- Fixed decisions: RC-D-002 L (deliverable plus handoff); Q1

#### Spec-change reporting
- Spec version: SPEC v001.6 (RC-D-002)
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: the subproject cannot supply the rule before T-011
- Stop boundary: the year-candidate questions in T-011
- Safe continuation: all else
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: the heads-up names every item that needs the rule
- Independent review: PI approves text
- Failure/rollback: n/a

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
PI-approved heads-up delivered; reply recorded.

#### Chunking trigger
none

### T-071 — Deploy v2.7 pipeline to the droplet

Status: blocked (gate: deploy)
Type: operate
Priority: critical-path
Spec refs: D-002, R-070 (freeze = deploy date)
Decision refs: DEC-020, DEC-021

#### Objective
`reclass/v2.7` merged to `main` (PR + approving review) and the droplet checkout at the merge sha, with keys/optional features and free disk verified, deployed only after wave 5 (`r20261023T134656Z-be8a`) is published on the site (PF-008).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Code review | T-031 | criticals closed | stop |
| Fixture run | T-041 | passed | stop |
| Live schema + production ingest | T-055 | go-live checks recorded | stop |
| Procurement acceptance | T-060 | accepted | stop |
| Validation notice | T-061 | delivered | stop |
| Wave-5 publication | site / API | published | wait |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Droplet checkout | `/home/g3o/...` checkout at merge sha | T-070, T-072 | sha recorded |
| Deploy record | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/deploy/DEPLOY.md`† | integrator | sha, config/key check, free disk (PF-017) |

#### Execution resources
- Persona/role: eng-a
- Tools/connectors: SSH (`id_ed25519_g3o`, PI authorisation); `gh`
- Skills/protocols: memory g3o-prod-checkout-drifts-silently; g3o-merge-requires-approving-review
- Working directory/environment: droplet; merge prepared from `C:/Users/spaci/worktrees/G3O-eng-a/`†, never the shared checkout

#### Dependencies
- Requires: T-031, T-041, T-055, T-060, T-061
- Enables: T-062, T-070
- Can run with: none
- Researcher gates: PI approves merge and deploy; SSH authorisation; external gate — wave 5 published

#### Ownership and collision control
- Read scope: `reclass/v2.7`, droplet
- Write claim: droplet checkout; deploy folder†
- Shared surfaces: `main` — merge by integrator under PI approval

#### Procedure boundary
- Included: merge, deploy, config and disk checks
- Excluded: runs (T-072, T-073)
- Fixed decisions: DEC-020, DEC-021

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: deploy needs config not in SPEC; free disk below the T-001 estimate of the back-fill footprint
- Stop boundary: T-070
- Safe continuation: none
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: `git rev-parse HEAD` on the droplet equals the merge sha
- Self-check: required keys and optional features present (unlocker etc.)
- Self-check: free disk vs projected footprint
- Independent review: integrator
- Failure/rollback: check out the previous sha

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Sha verified on the droplet; config and disk checks recorded.

#### Chunking trigger
none

### T-070 — Freeze and draw the back-fill set

Status: blocked (BLOCKED-INPUT: wave 5 published; v2.7 deployed)
Type: operate
Priority: critical-path
Spec refs: R-070, R-071, R-076, R-077, N-001
Decision refs: DEC-019

#### Objective
A PI-confirmed fixed back-fill list: every institution published as documented or unclear at the freeze (API `meta.coverage.as_of`), plus the 45 verified owners of the 114 WS10 transfers, including owners currently published `none` (item 23 ii).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Public API | RS-030 | live, after wave 5 + deploy | wait |
| WS10 transfer list | RS-026 `activity-review-prepared.csv` | authoritative (RQ-003) | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Back-fill set | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/freeze/backfill-set.json`† | T-072, T-073, T-074, T-080 | Count = documented + unclear at `as_of`, plus transfer owners flagged; other `none` excluded |
| Freeze record | `.../freeze/FREEZE.md`† | integrator, PI | `as_of`, `total`, snapshot file (DEC-019) |

#### Execution resources
- Persona/role: eng-a
- Tools/connectors: free API GETs (authorised G8 c); Python
- Skills/protocols: none beyond this card
- Working directory/environment: agent-workspace freeze folder†; any code from `C:/Users/spaci/worktrees/G3O-eng-a/`†, never the shared checkout

#### Dependencies
- Requires: T-071
- Enables: T-072
- Can run with: T-062 (W18)
- Researcher gates: PI confirms the freeze date

#### Ownership and collision control
- Read scope: public API; RS-026
- Write claim: freeze folder†
- Shared surfaces: none

#### Procedure boundary
- Included: snapshot and list
- Excluded: runs
- Fixed decisions: R-070, R-071, item 23 ii

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: totals differ from 9,705 + 27,648 beyond wave-5 additions
- Stop boundary: none
- Safe continuation: none needed
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: totals vs API meta
- Self-check: all 45 owners present, `none` owners flagged
- Independent review: integrator recount
- Failure/rollback: re-snapshot

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
PI-confirmed list and freeze record written.

#### Chunking trigger
none

### T-072 — Back-fill smoke run (small sample)

Status: blocked (gate: paid run)
Type: verify
Priority: critical-path
Spec refs: R-032, R-035, R-036, R-074, R-075, R-076, R-077, C-002
Decision refs: DEC-002, DEC-003

#### Objective
About 50 institutions covering documented, unclear, no-text, raw-PDF, link chains and at least 5 WS10 transfers run end to end to correction-layer files (no live DB), with cap-reached counts and a full-set cost/runtime projection (PF-027).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Back-fill list | T-070 | frozen | stop |
| Stored-text counts, disk | T-001 | done | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Smoke run | `/home/g3o/runs/<backfill-smoke-id>/` | T-073 | Every institution has an end state |
| Smoke report | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/smoke/SMOKE.md`† | PI, T-073 | End states; failure-state share; cap-reached counts; per-field downgrade counts; full-set cost and runtime projection |

#### Execution resources
- Persona/role: eng-a
- Tools/connectors: SSH; back-fill entry point (T-029)
- Skills/protocols: memory nohup-inside-ssh-needs-stdin-redirect, droplet-clock-is-utc-behind-local
- Working directory/environment: droplet

#### Dependencies
- Requires: T-001, T-070
- Enables: T-073
- Can run with: none
- Researcher gates: paid run — the agent prepares the exact command and cost estimate and Simone runs it via `! <command>` (red line 4, 2026-10-28); SSH authorisation; PI reviews the smoke report

#### Ownership and collision control
- Read scope: droplet runs
- Write claim: smoke run dir; smoke folder†
- Shared surfaces: none (never touches the live DB)

#### Procedure boundary
- Included: smoke run and report
- Excluded: live DB load (T-074)
- Fixed decisions: DEC-002 a, DEC-003 b

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: failure-state share above 10%; cap reached for many institutions; projection makes the full run infeasible
- Stop boundary: T-073
- Safe continuation: reporting
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: end-state count = input count
- Independent review: integrator samples 10 institutions
- Failure/rollback: discard the run

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
PI accepts the smoke report and projection.

#### Chunking trigger
none

### T-073 — Full back-fill run

Status: blocked (gate: paid run)
Type: operate
Priority: critical-path
Spec refs: G-003, R-035, R-072, R-074, R-076
Decision refs: DEC-002

#### Objective
The frozen set run through the back-fill entry point, every institution ending in a v2.7 result or a named failure state, with progress and cost reported per batch.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Smoke acceptance + projection | T-072 | accepted | stop |
| Back-fill list | T-070 | frozen | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Back-fill run | `/home/g3o/runs/<backfill-id>/` + run log | T-074 | Progress and cost per batch; batches mixed by country |

#### Execution resources
- Persona/role: eng-a
- Tools/connectors: SSH; `nohup … < /dev/null`
- Skills/protocols: memory g3o-resume-pitfalls (failures cluster by country)
- Working directory/environment: droplet

#### Dependencies
- Requires: T-072
- Enables: T-074
- Can run with: none
- Researcher gates: paid run — the agent prepares the exact command and a cost estimate from the T-072 projection, and Simone runs it via `! <command>` (red line 4); SSH authorisation

#### Ownership and collision control
- Read scope: droplet
- Write claim: back-fill run dir
- Shared surfaces: none

#### Procedure boundary
- Included: run and monitoring
- Excluded: DB load
- Fixed decisions: DEC-002 a

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: failures cluster by country; cost exceeds the projection materially
- Stop boundary: the run
- Safe continuation: monitoring
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: per-batch counts against the list
- Independent review: integrator
- Failure/rollback: run is additive; discard

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
All institutions end-stated.

#### Chunking trigger
Split by group (documented / unclear) if the run exceeds one week.

### T-074 — Load the correction layer and reconcile

Status: blocked (gate: live DB write)
Type: migrate
Priority: critical-path
Spec refs: R-036, R-056, R-073, R-075, R-077, A-005, A-006, A-014, A-015, A-022, C-005
Decision refs: DEC-001

#### Objective
After a pre-load snapshot of the live branch (PF-004), with migration 021 already live from T-055, the back-fill output loaded as correction-layer rows under a fresh release id, hidden until release (R-056), with explicit refresh + watermark check (PF-007) and a reconciliation table.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Back-fill output | T-073 | complete | stop |
| Rehearsal | T-054 | clean | stop |
| Ingest + endpoints | T-052 | reviewed | stop |
| Live schema + production ingest | T-055 | go-live checks recorded | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Snapshot | Neon branch of live taken before load (name per DP-064) | rollback | Restorable |
| Live correction rows | live DB, release id | T-080, T-095 | Hidden until release; originals untouched |
| Reconciliation | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/reconciliation/RECON.md` + csv† | T-080, T-082, T-095 | A-005 count identity; A-006 diff empty; A-015 no-text list; A-022 transfers under verified owners; denominator unchanged |

#### Execution resources
- Persona/role: eng-a with Colin
- Tools/connectors: correction loader (T-051); Neon; psql/psycopg
- Skills/protocols: memory g3o-access-surfaces, g3o-wave-window-gates-visibility
- Working directory/environment: live Neon branch `br-wave1-cutover`

#### Dependencies
- Requires: T-052, T-054, T-055, T-073
- Enables: T-080, T-082, T-095
- Can run with: none
- Researcher gates: PI approves live writes (snapshot + load); Neon branch creation, snapshots and writes each need a named PI gate; Neon branches and snapshots are free (Simone, 2026-10-28), so the agent runs these commands itself once the PI gate has passed

#### Ownership and collision control
- Read scope: back-fill output, live DB
- Write claim: live DB under the release id; reconciliation folder†
- Shared surfaces: DB schema — Colin

#### Procedure boundary
- Included: snapshot, load, refresh, reconciliation (021 already applied by T-055)
- Excluded: release (T-095)
- Fixed decisions: DEC-001 a, R-056

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: any original value would change; refresh does not move the watermark
- Stop boundary: the load
- Safe continuation: none
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: hash diff of original columns and rows (A-006)
- Self-check: counts reconcile (A-005); 114-transfer check (A-022)
- Self-check: watermark moved; unreleased rows not public
- Independent review: integrator
- Failure/rollback: delete by release id; restore from snapshot

#### Decision points
- DP-064: Take the pre-load snapshot as a Neon branch of live or as a pg_dump
  - Default: Neon branch of live named `pre-reclass-<date>` just before load
  - Recommendation: Neon branch — instant and restorable; Neon PITR was not verified by the review

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
RECON signed by PI.

#### Chunking trigger
Split the 114 transfers from the back-fill load.

### T-080 — Draw the 400-institution quality sample

Status: pending
Type: verify
Priority: critical-path
Spec refs: R-082, R-086
Decision refs: DEC-011

#### Objective
A stratified sample of 400 (group documented/unclear × verdict changed/unchanged, 100 per stratum), a transfer-owner stratum on top, and the Sonnet 100 drawn as 25 per stratum, with fixed seeds recorded (DEC-011 a, item 27).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Reconciliation | T-074 | done | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Samples | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/quality/sample-400.json`, `sample-transfers.json`, `sample-sonnet-100.json`† | T-081, T-082 | Seeds, strata counts, stratum population sizes (for weights) |

#### Execution resources
- Persona/role: eng-b
- Tools/connectors: Python
- Skills/protocols: none beyond this card
- Working directory/environment: quality folder†; any code from `C:/Users/spaci/worktrees/G3O-eng-b/`†, never the shared checkout

#### Dependencies
- Requires: T-074
- Enables: T-081
- Can run with: none
- Researcher gates: none

#### Ownership and collision control
- Read scope: reconciliation outputs
- Write claim: quality sample files†
- Shared surfaces: none

#### Procedure boundary
- Included: draw
- Excluded: reading (T-081)
- Fixed decisions: DEC-011 a, item 27, R-086

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a stratum has fewer than 100 institutions
- Stop boundary: none
- Safe continuation: all
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: counts per stratum; Sonnet subset is 25 per stratum
- Independent review: integrator
- Failure/rollback: redraw with a new seed (logged)

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Sample files written with seeds and population sizes.

#### Chunking trigger
none

### T-081 — Agent-read swarm (Haiku 400 + transfer stratum, Sonnet 100)

Status: blocked (gate: swarm run)
Type: verify
Priority: critical-path
Spec refs: R-082, R-083, R-086, N-002, C-006
Decision refs: DEC-017, DEC-022

#### Objective
Blind agent reads: each subagent reads its 25 institutions' pages (not the pipeline codes) and records the institution verdict and every page verdict (DEC-017 b); Haiku reads the 400 plus the transfer stratum (about 18 subagents), Sonnet reads the 100 (4 subagents), with full traceability (PF-013).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Samples | T-080 | drawn | stop |
| Page texts | T-073 artifacts on the droplet | pulled under SSH gate | stop |
| Read rubric | DEC-017 b, R-086 | PI-approved prompt | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Reads | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/quality/reads/{haiku,sonnet}-NN.jsonl`† | T-082 | Per-record model id; institution verdict + page verdicts |
| Trace bundle | `.../quality/reads/manifest.json`, `prompt.sha256`, transcripts† | T-082, T-096 | Input manifests, prompt hash, identical inputs across models, transcripts kept |

#### Execution resources
- Persona/role: quality (coordinator session)
- Tools/connectors: Agent tool with Haiku and Sonnet (model ids recorded at launch, DEC-022); SSH pull of pages
- Skills/protocols: `workflow-authoring` only if Simone opts into a Workflow
- Working directory/environment: quality folder†

#### Dependencies
- Requires: T-080
- Enables: T-082
- Can run with: none
- Researcher gates: PI approves the read prompt and authorises the swarm launch (see DP-065); SSH authorisation for the page pull

#### Ownership and collision control
- Read scope: samples, page texts
- Write claim: `quality/reads/`†
- Shared surfaces: none

#### Procedure boundary
- Included: reads and trace bundle
- Excluded: agreement analysis (T-082)
- Fixed decisions: DEC-017 b (blind), R-086, DEC-022

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: the rubric cannot be applied to a verdict type
- Stop boundary: affected reads
- Safe continuation: other reads
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: record counts = sample sizes for each model
- Self-check: prompt hash and input manifest identical across Haiku and Sonnet
- Self-check: no pipeline codes present in any subagent input
- Independent review: T-083
- Failure/rollback: rerun the affected subagent

#### Decision points
- DP-065: Does the Claude subagent swarm count as "costs money" under red line 4
  - Default: treat it as paid — Simone authorises the launch before any subagent starts
  - Recommendation: treat as paid — the red line covers paid services, and whether this account's subagent usage is billed separately was not checked
- DP-066: Run the reads as Agent-tool subagents or as a Workflow
  - Default: Agent-tool subagents, at most 4 concurrent
  - Recommendation: Agent-tool subagents — a Workflow needs Simone's explicit opt-in

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
All read records and the trace bundle present.

#### Chunking trigger
Fewer than 5 free slots → serialise batches.

### T-082 — Compile the quality packet

Status: pending
Type: verify
Priority: critical-path
Spec refs: R-080, R-081, R-082, R-083, R-086, A-002, A-013, A-016, N-007
Decision refs: DEC-017

#### Objective
A quality packet with agreement tables (agent vs v2.7 on institution and page verdicts; Sonnet vs Haiku), overall figures weighted to the back-fill set (the transfer-owner stratum reported separately and excluded from the weighted figures), threshold/downgrade counts per field, quote traces, jev-record field checks, and the disagreement list that sets the PI audit load (PF-012); agreement never framed as accuracy (R-083).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Reads + trace bundle | T-081 | complete | stop |
| Reconciliation | T-074 | done | stop |
| Downgrade counts | T-024 outputs in the run | present | report |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Quality packet | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/quality/QUALITY-PACKET.md`† | T-083 | Weighted overall figures; Sonnet–Haiku difference; disagreement list + count; 25 random audit picks with seed |

#### Execution resources
- Persona/role: integrator (researcher session)
- Tools/connectors: Python
- Skills/protocols: `measuring-protocol` (if available), R-083 rule
- Working directory/environment: quality folder†

#### Dependencies
- Requires: T-074, T-081
- Enables: T-083
- Can run with: none
- Researcher gates: none

#### Ownership and collision control
- Read scope: quality reads, reconciliation
- Write claim: `quality/QUALITY-PACKET.md`†
- Shared surfaces: none

#### Procedure boundary
- Included: tables, counts, list
- Excluded: audit rulings (T-083)
- Fixed decisions: R-083, R-086, DEC-017 b

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: disagreement patterns point to contract defects
- Stop boundary: none
- Safe continuation: all
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: every number recomputed from raw reads
- Self-check: weights sum to the back-fill set; transfer-owner stratum excluded from weighted figures and reported on its own
- Independent review: PI
- Failure/rollback: n/a

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Packet complete with disagreement list and audit picks.

#### Chunking trigger
none

### T-083 — PI audit

Status: pending
Type: verify
Priority: critical-path
Spec refs: R-082, R-086, A-008
Decision refs: none

#### Objective
Simone audits every disagreement plus 25 at random and signs A-008.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Quality packet | T-082 | complete | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Signed audit | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/quality/PI-AUDIT.md`† | T-095 | Ruling per audited case; signature |

#### Execution resources
- Persona/role: researcher (Simone)
- Tools/connectors: none
- Skills/protocols: none
- Working directory/environment: quality folder†

#### Dependencies
- Requires: T-082
- Enables: T-095
- Can run with: none
- Researcher gates: this card is the gate

#### Ownership and collision control
- Read scope: quality packet
- Write claim: `quality/PI-AUDIT.md`†
- Shared surfaces: none

#### Procedure boundary
- Included: audit and sign-off
- Excluded: fixes (become deltas)
- Fixed decisions: R-086 (disagreement does not block release)

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a PI ruling changes a coding rule (becomes a delta)
- Stop boundary: none
- Safe continuation: all
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Signature recorded

#### Decision points
none

#### Return report
PI audit record.

#### Done condition
Audit signed.

#### Chunking trigger
none

### T-090 — Documentation: data dictionary, contract changelog, methods note

Status: pending
Type: document
Priority: required
Spec refs: D-006, R-090, A-017, N-007, G-004
Decision refs: DEC-013

#### Objective
Documentation of every new field, value, version (extract v2.7, validate v1.5), downgrade and link rule, plus the #175 README update (PF-023), with public prose approved by the PI. RC-D-002 row 52: the data dictionary is generated from the codebook (T-013 generator) and owns the published definitions (Q6); the docs list follows SPEC R-090 v001.6 (row 28); the methods note covers R-059 and the r2#55 activity-unit change; the version label is the codebook release (C3 a).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Contract v2.7 | T-010 | signed | stop |
| Enums/schema | T-012 | merged | stop |
| Writer column list | T-028 | merged | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Docs | `docs/data_dictionary.md`, `docs/contract-changelog.md`†, `docs/methods-v27.md`† on branch `reclass/t090-docs`† | public, Kaser, RAs, T-095 | Every field in T-028 documented |
| #175 README text | README for the bulk-access handoff (g3o-website#175)†; repo confirmed by T-050 | #175 lane | v2.7 fields and versions described; if the README lives in g3o-website or g3o-api, Colin's lane makes the edit from this card's PI-approved text; `export_bulk.py` itself owned by T-052 |

#### Execution resources
- Persona/role: integrator (structure and field coverage); prose drafted by the `writer` persona; PI approves
- Tools/connectors: git; field-coverage script
- Skills/protocols: writer persona for prose
- Working directory/environment: `C:/Users/spaci/worktrees/G3O-integrator/`† (branch `reclass/t090-docs`†), never the shared checkout

#### Dependencies
- Requires: T-010, T-012, T-028
- Enables: T-095
- Can run with: T-030, T-052
- Researcher gates: PI approves public prose; push

#### Ownership and collision control
- Read scope: contract, writer, D-007 spec
- Write claim: the docs files in the G3O repo listed in Outputs (and the #175 README text only, not its file in another repo)
- Shared surfaces: #175 README file — Colin if outside the G3O repo

#### Procedure boundary
- Included: docs
- Excluded: code; `export_bulk.py` (T-052)
- Fixed decisions: DEC-013 a

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a field has no documented meaning in the contract
- Stop boundary: none
- Safe continuation: all
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: field-coverage script against T-028 columns
- Independent review: PI (A-017)
- Failure/rollback: branch

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
PI-approved docs merged.

#### Chunking trigger
Split the methods note from the data dictionary.

### T-095 — Release decision and publication

Status: blocked (gate: publication)
Type: operate
Priority: critical-path
Spec refs: D-003, D-004, A-007, A-009, R-054, R-056, N-003, N-006
Decision refs: none

#### Objective
After the PI audit, the PI decides the release; the release flag is flipped so correction-layer and v2.7 rows become public; API and site deployed; A-007 and A-009 checked.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Signed audit | T-083 | signed | stop |
| Docs | T-090 | merged | stop |
| Staged site | T-053 | staged | stop |
| Loaded correction layer | T-074 | reconciled | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Release record | `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/release/RELEASE.md`† | public, T-096 | Release flag state; screenshots and API responses (A-007, A-009) |

#### Execution resources
- Persona/role: colin with integrator
- Tools/connectors: API deploy, Pages deploy, release-flag switch
- Skills/protocols: none beyond this card
- Working directory/environment: g3o-api, g3o-website, live DB

#### Dependencies
- Requires: T-053, T-074, T-083, T-090
- Enables: T-096
- Can run with: none
- Researcher gates: PI release sign-off; deploy; live DB write (release flag)

#### Ownership and collision control
- Read scope: all release inputs
- Write claim: release flag; deploys; release folder†
- Shared surfaces: DB and API — Colin

#### Procedure boundary
- Included: release and evidence
- Excluded: indices (N-003); Kaser extract (N-006)
- Fixed decisions: R-056, R-086 (release with reported disagreement)

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: released state differs from the staged state
- Stop boundary: publication
- Safe continuation: none
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: API responses for 20 sampled institutions show v2.7 fields, quotes and version labels
- Self-check: no CX-01 index published (A-009)
- Self-check: website shows supporting text up to the display cap, with the truncation marker and access to the full text (R-043)
- Self-check: the history parameter returns older rows (R-051)
- Self-check: correction rows visible regardless of wave windows (R-055)
- Independent review: PI
- Failure/rollback: flip the release flag back (hide by release id) and revert the site

#### Decision points
none

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
Released, with evidence filed.

#### Chunking trigger
none

### T-096 — Final traceability review and reproduction rerun

Status: pending
Type: verify
Priority: required
Spec refs: D-001, D-002, D-003, D-004, D-005, D-006, D-007, D-008, G-001, G-002, G-003, G-004, G-005
Decision refs: none

#### Objective
A rerun of the documented pipeline on 20 sampled institutions from the release record, judged against an explicit agreement criterion (PF-027), and a trace of each published code to page, quote, jev request and version, feeding Stage 8.

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Release record | T-095 | released | stop |
| Agreement criterion | DP-067 | PI-approved | stop |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| Trace review | `C:/Users/spaci/repos/G3O/planning/reviews/TRACE.md`† | integrator (Stage 8) | 20/20 traced or deltas raised; rerun agreement against the criterion |

#### Execution resources
- Persona/role: reviewer (fresh context)
- Tools/connectors: SSH; pipeline rerun
- Skills/protocols: `planning-spec-reconciliation-protocol.md`
- Working directory/environment: droplet + planning reviews folder†

#### Dependencies
- Requires: T-095
- Enables: none
- Can run with: none
- Researcher gates: paid rerun (sync calls, RC-D-001 E1) — the agent prepares the command and cost estimate and Simone runs it via `! <command>` (red line 4); SSH authorisation; PI approves the agreement criterion

#### Ownership and collision control
- Read scope: release record, run artifacts
- Write claim: `planning/reviews/TRACE.md`†
- Shared surfaces: none

#### Procedure boundary
- Included: rerun and trace; rerun output stays in a droplet scratch run dir and loads to no DB
- Excluded: fixes (become deltas); any DB load
- Fixed decisions: none reopened

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: integrator (coord mailbox `g3o-reclass-integrator`)
- Report when: a published code cannot be traced; rerun disagreement exceeds the criterion
- Stop boundary: none
- Safe continuation: all
- Forbidden: editing `SPEC.md` or `CHANGELOG.md` directly

#### Verification and review
- Self-check: trace table complete for 20 institutions
- Independent review: PI
- Failure/rollback: n/a

#### Decision points
- DP-067: Agreement criterion for the reproduction rerun
  - Default: criterion proposed in the card's first chunk and approved by the PI before the rerun
  - Recommendation: identical institution verdict on all 20, page-verdict agreement reported descriptively — jev answers are probabilistic, so exact page-level identity may be too strict

#### Return report
Changed files; verification results (each check above, with evidence); failures; blockers; unresolved decisions; proposed status (`verified` or `blocked`). Sent to the plan integrator, who alone marks `complete`.

#### Done condition
TRACE.md filed and handed to Stage 8.

#### Chunking trigger
none

### T-097 — Standing integration: deltas, CHANGELOG, claims

Status: pending
Type: integrate
Priority: required
Spec refs: all
Decision refs: DEC-012

#### Objective
The integrator receives card reports, prepares deltas for the PI, keeps CHANGELOG, marks tasks `complete`, and checks that a wave window is open beyond w001's expiry (2027-01-01) before then (item 24 b).

#### Inputs
| Input | Location/producer | Required state/version | Missing-input behavior |
|---|---|---|---|
| Card reports | all lanes, coord mailbox `g3o-reclass-integrator` | as received | n/a |
| Live wave windows | g3o-api `wave_windows` | read | report UNKNOWN |

#### Outputs
| Output | Exact path/interface/artifact | Consumer(s) | Contract / required properties |
|---|---|---|---|
| CHANGELOG | `C:/Users/spaci/repos/G3O/planning/CHANGELOG.md`† | PI, all lanes | One entry per delta with PI approval ref |
| Governance updates | SPEC/RESOURCES/PLAN after PI approval | all lanes | Version propagated |
| Wave-window reminder | message to Simone | PI | Sent before w001 expiry |

#### Execution resources
- Persona/role: integrator (DEC-012 a)
- Tools/connectors: coord mailbox; Read/Edit on governance files
- Skills/protocols: `planning-spec-reconciliation-protocol.md`
- Working directory/environment: `C:/Users/spaci/repos/G3O/planning/`

#### Dependencies
- Requires: none
- Enables: none
- Can run with: all tasks
- Researcher gates: PI approves every delta

#### Ownership and collision control
- Read scope: all plan outputs
- Write claim: SPEC.md, RESOURCES.md, PLAN.md, CHANGELOG.md (sole writer after lock)
- Shared surfaces: plan governance — this card

#### Procedure boundary
- Included: deltas, CHANGELOG, completion marks, wave-window check
- Excluded: substantive rulings (PI)
- Fixed decisions: DEC-012 a

#### Spec-change reporting
- Spec version: SPEC.md v001.4 → Stage 6 locked version
- Report to: PI (receiver card)
- Report when: n/a (receiver)
- Stop boundary: n/a
- Safe continuation: n/a
- Forbidden: applying a delta without PI approval

#### Verification and review
- Self-check: one CHANGELOG entry per delta with a PI approval reference
- Self-check: wave-window check recorded before the reminder date
- Independent review: PI

#### Decision points
- DP-068: When to check and remind about the wave window beyond w001 (expires 2027-01-01)
  - Default: check on 2026-12-01 and remind Simone then
  - Recommendation: 2026-12-01 — a month's margin before new runs would silently disappear from the site

#### Return report
Report to the PI.

#### Done condition
Stage 8 closed.

#### Chunking trigger
none

## Launch manifest

Wave 1 only. RC-D-001 (E): the W1 lanes run one at a time, in the order T-010 → T-002 → T-020 → T-001; the next lane starts when the previous lane returns its report. RC-D-002 (D): T-002 still follows T-010, and it now also waits for T-013 so that it measures the generated extractor prompt; T-013 is a new W1 card that the 2026-10-29 authorization does not cover. later waves get their lanes from the task-engineering queue as predecessors verify. No lane launches before the Stage 6 baseline lock and Simone's separate execution authorization (C-003). Engineer lanes work in git worktrees outside Drive (`C:/Users/spaci/worktrees/G3O-<lane>/`†, branched from `origin/main` `375f1ff`). Coord: native admission at start, claims via the native writer, mailbox `g3o-reclass-integrator` for questions and spec deltas, semantic close at exit (`coord/SPEC.md`, "Native coordination and startup read policy").

| Lane | Task/chunk | Persona | CWD | Inputs | Claim | Output | Researcher gates | Review | Release |
|---|---|---|---|---|---|---|---|---|---|
| integrator | T-010 | researcher | `H:/My Drive/Research/G3O`; contract edits in `C:/Users/spaci/worktrees/G3O-integrator/`† | SPEC v001.4, RS-010, RS-011, RS-004, RS-005, RS-024, RS-026; procurement §4.3 text | contract + prompt files on `reclass/t010-contract`† | Output Contract v2.7 + validate v1.5 drafts with hash | PI signs contract hash; push | T-031 | after PI hash sign-off |
| integrator | T-097 | researcher | `H:/My Drive/Research/G3O` | delta reports | `planning/CHANGELOG.md`†, delta log | CHANGELOG entries | PI approves every delta | PI | standing |
| eng-a | T-020 | engineer | `C:/Users/spaci/worktrees/G3O-eng-a/`† | RS-004 `byte_chunks`, RS-014 split | `g3o/common/page_chunks.py`† + tests | token-based chunker | push | T-031 | tests pass |
| eng-b | T-001 | engineer | `C:/Users/spaci/worktrees/G3O-eng-b/`† | RS-004 scripts, RS-025 lists, RS-007 runs | `agent-workspace/2026-10-27-reclass-plan/spikes/` (`SPIKE-T001*`) + droplet `~/reclass-spike-*/` | stored-text counts, disk check | PI authorises read-only SSH | integrator | counts file + note |
| eng-b | T-013 | engineer | `C:/Users/spaci/worktrees/G3O-eng-b/`† | RS-010, RS-013, RS-039; T-010 item template | `g3o/codebook/`†, `codebook/schema.json`†, tests, CI step | codebook schema, loader, generators, CI drift check | not authorized yet (RC-D-002); PI approves the item template (approved 2026-10-30, RC-D-003); push | T-031 | tests + CI pass |
| eng-c | T-002 | engineer | `C:/Users/spaci/worktrees/G3O-eng-c/`† | RS-004, RS-024, RS-008, RS-009, RS-031; signed codebook (T-010) and generated prompts (T-013) (RC-D-002 D) | spikes folder (`SPIKE-T002*`) | cost / latency / fan-out / token-estimator report | PI approves paid-spike budget; Simone runs the paid command (`! <command>`) | integrator | report + raw logs |

## Task-engineering queue

One packet per ready task, built by `task-engineering-protocol.md` from the card in `## Task cards` at launch time; each packet carries the card's inputs, outputs, write claim, researcher gates, checks, acceptance IDs, spec version (Stage 6 locked), delta triggers and stop/continue rule verbatim. Ready after the lock: T-010, T-020, T-097 (no gate beyond push / PI hash); ready pending gate: T-001 (SSH), T-002 (paid; Simone runs; after T-010 and T-013, RC-D-002 D); T-013 (needs Simone's authorization, RC-D-002). Every other card enters the queue when its Requires are `verified` and its gates have passed.

## Spec-change control

- Current locked spec/version: `C:/Users/spaci/repos/G3O/planning/SPEC.md` v001.4 (locks at Stage 6 together with RESOURCES.md v001 and this PLAN.md).
- Delta log: `C:/Users/spaci/repos/G3O/planning/CHANGELOG.md`†; the integrator (DEC-012 a) is the sole writer; Simone approves every delta.
- Delta recipient: integrator lane, coord mailbox `g3o-reclass-integrator`.
- Lane reporting contract: each card's `#### Spec-change reporting` names its trigger, stop boundary and safe continuation; lanes never edit SPEC / RESOURCES / PLAN / CHANGELOG.
- Post-execution reconciliation: `planning-spec-reconciliation-protocol.md` → `CHANGELOG.md` + `Spec-Reconciliation.md` (Stage 8; T-096 feeds it).

## Risks, approvals, rollback

| Risk | Trigger | Likelihood/impact | Prevention | Detection | Containment/rollback | Owner/task |
|---|---|---|---|---|---|---|
| jev two-pass cost / latency too high at ~37k institutions, now with all pages of unclear institutions (item 20 a) | T-002 numbers, T-001 page counts | M / H | spikes before build; token chunker; URL cap | T-002, T-072 projection | PI scope delta before T-073 | T-002, T-072, integrator |
| ~8 sequential Batch rounds per run make the back-fill slow | T-002 round latency | M / M | T-002 Batch subset projects runtime | T-002, T-072 | PI delta (full runs are Batch, RC-D-001 B) | T-025 |
| Many negatives fall below 0.8 → mass move to `unclear` (Q-019 a) | T-041, T-072 counts | M / H | per-field counts early | T-072 smoke | PI may revisit threshold via delta before T-073 | T-024, T-072 |
| Fuzzy matcher fails on CJK / Thai | T-003 error table | M / M | per-script calibration | T-003 | per-script threshold delta | T-003 |
| nano text steers jev (C-001) | spans leak paraphrase | L / H | spans only (DEC-010 a) | T-031 | fix T-022 | T-022, T-031 |
| Original observations overwritten | back-fill reuses a run_id; migration bug | L / critical | fresh release id + ingest guard; additive schema; rehearsal on live copy; pre-load snapshot | A-006 diff in T-054 / T-074 | restore snapshot; delete by release id; down migration | T-051, T-052, T-054, T-074 |
| v2.7 rows public before audit, or ordinary runs fail at ingest after deploy | release flag or schema not live at deploy | L / H | T-055 takes 021 and the ingest live before T-071 | T-054, T-055, T-095 | hide by flag; roll back by down migration + snapshot | T-051, T-052, T-055 |
| Corrected rows never reach the site | `sql/007` trigger ignores updates | M / H | explicit refresh + watermark check | T-054, T-074 | rerun refresh | T-052, T-074 |
| gpt-5-nano shutdown 2026-12-11 breaks any v2.5 run whose Stage 5 has not finished | date | H / H | wave 5 finished; waves 6 and 7 wait for v2.7 (RC-D-001 C) | calendar | no v2.5 runs after 2026-12-11 | integrator |
| New ordinary runs vanish after w001 expiry 2027-01-01 | no open window | M / H | T-097 standing check; waves 6 and 7 start after deploy (RC-D-001 C) | T-097 | PI opens next window | T-097, PI |
| Droplet checkout drifts / missing keys switch features off | deploy | M / H | config check in T-071 | DEPLOY record | redeploy | T-071 |
| Droplet disk fills | T-073 | U / M | T-001 / T-071 disk check | T-001, T-071 | prune scratch, PI decides | T-071 |
| Failures cluster by country | T-073 | M / M | batch by country mix | per-batch log | targeted rerun | T-073 |
| Procurement breaks on the new enum or §4.3 text not agreed | deploy before acceptance | M / M | T-060 before T-071; §4.3 placeholder in T-010 | A-018 | hold deploy | T-010, T-060 |
| Validation plan inputs drift silently | contract change | M / M | T-061 notice | T-061 | validation-plan delta (theirs) | T-061 |
| Wave 5 delays the freeze | wave-5 run stalls | M / M | track run | T-071 external gate | PI decides cut-off via delta | integrator |
| Agent read mistaken for accuracy | packet wording | M / M | R-083 rule in packet | T-083 | rewrite packet | T-082 |
| Audit load larger than expected | many disagreements | U / M | blind verdict + page-verdict unit only | T-082 count | PI decides audit order (release not blocked, R-086) | T-082, T-083 |
| Stored text missing for many pages | T-001 | U / M | spike | T-001 | live re-scrape load (R-074) grows | T-001 |
| A stratum of the 400 has fewer than 100 institutions (R-086 v001.4: 100 per stratum) | T-074 counts | U / M | none possible before the back-fill | T-080 stratum counts | T-080 reports and stops the draw; integrator raises a delta (e.g. take the whole stratum, re-weight) for PI ruling | T-080, integrator |

Gate list (researcher gates; none passes by lock alone):

| Gate | Cards |
|---|---|
| PI coding-rule wording / contract hash | T-010 (incl. the item template and the item-by-item CX signature, CX-01.3†), T-013 (item template, r2#59), T-011 (non-verbatim questions), T-022 / T-032 (nano prompts) |
| PI labels / thresholds / caps | T-003 (match threshold, website cap), T-025 (URL cap value after T-002), T-040, T-041 failures |
| Paid calls (Simone runs `! <command>`) | T-002, T-016, T-041, T-072, T-073, T-096; T-081 per its DP |
| SSH / droplet | T-001, T-071, T-072, T-073, T-081 (page pull), T-096 |
| DB writes (Neon branches / snapshots free; PI gate still required) | T-051 (disposable self-check), T-054 (disposable branch), T-055 (live schema), T-074 (live load) |
| Push / merge / deploy | every build card push; T-030 / T-035 integration branch; T-071; T-052 staging; T-055 production ingest; T-053 / T-095 deploy |
| External messages | T-050 (GitHub issues to Colin), T-060 (procurement email via Simone + #134; heads-up draft first), T-061 (validation-plan notice), T-062 (D-009, after deploy), T-063 (D-010 heads-up) |
| External wait | T-071 (wave 5 published); T-011 year-candidate questions (calendar rule via T-063); T-010 §4.3 wait closed by RC-D-002 row 38 |
| Public wording | T-053 copy, T-090 prose |
| Release | T-083, T-095 |

## Blocked/deferred items

- T-001 blocked on PI authorisation of read-only droplet SSH.
- T-002 blocked on PI approval of the paid-spike budget; Simone runs it.
- T-010 §4.3 block closed by RC-D-002 row 38 (r2#14): §4.3 is the removal of purchase language. Was: T-010 completion blocked on the procurement integrator's §4.3 text (R-087); drafting may start with a placeholder.
- T-002 waits for T-010 and T-013 (RC-D-002 D). T-016 is paid; Simone runs it.
- T-071 blocked on wave 5 publication (external) plus its edges.
- DEC-003 d closed by RC-D-001 (B).
- T-025 URL cap value, T-003 threshold and website cap: PI values set after the spikes; the cards carry them as gates / DPs.
- T-080: no fallback rule if a stratum is under 100 (R-086 v001.4); a delta is raised at draw time.
- Deferred: none. R11 prevalence restatement stays a non-goal (N-007).

## Readiness-audit results

| Check | Result |
|---|---|
| All critical / high findings resolved | PASS — 0 critical; 11 high resolved (dispositions above) |
| Every substantive user decision answered or its tasks blocked | PASS — DEC-001..DEC-018, SD-g, items 20-27 ruled; spike-dependent values are gates on named cards |
| Every must-have spec ID has a producer and verifier | PASS — traceability table, incl. new R-056, R-087 |
| DAG acyclic, inputs resolve | see `## Task graph` (checked by script and `plan_viewer.py --check`) |
| Concurrent write claims disjoint | PASS — one writer per path per wave; `contract.py`/`schema.py` T-012 only; `stage_extract.py` T-022 only; Stage 6 files T-026 only; `orchestrator.py`, `cli.py`, pins T-030 / eng-b only; g3o-api / website Colin only; governance files integrator only |
| Shared surfaces have one integrator | PASS — `reclass/v2.7` eng-b; g3o-api / website Colin; plan governance integrator |
| Review and integration capacity reserved | PASS — reviewer lane (T-031, T-096); integrator lane standing (T-097); peak concurrent agent lanes per wave ≤ 4 of the 5-slot Claude budget |
| Tools / skills / personas exist or prerequisites explicit | PASS — engineer, researcher, writer personas; `task-engineering-protocol.md`; `plan_viewer.py` |
| Approval, cost, sensitivity and rollback gates assigned | PASS — gate list; paid steps Simone-run (red line 4) |
| Packets preserve fixed decisions | PASS — each card's `Procedure boundary` lists its fixed decisions |
| Researcher gates carried into card, task graph and launch manifest | PASS for W1; later waves at task engineering |
| Every lane can report a spec delta; sole delta-log writer named | PASS — integrator (DEC-012 a) |
| `Spec-Reconciliation.md` required at closure | PASS — Stage 8, fed by T-096 |
| Execution authorization matches the request | PASS — PLAN_ONLY; no execution authorized |

Second review: a fresh-context read-only subagent checked this plan against SPEC v001.4, the rulings and the review findings on 2026-10-28 (1 critical, 2 high, 8 medium, 7 low); all accepted and applied (ledger rows RV2-*).

Overall: READY-WITH-BLOCKS (W1 blocks: SSH and paid-spike gates; external waits on §4.3 text and wave 5).

## User authorization to execute

2026-10-29 (Simone, chat "5 all but we go sequentially, first contract"; recorded in RC-D-001 E): W1 lanes T-010, T-002, T-020, T-001 are authorized, one at a time in that order, each under its own card gates. Nothing else is authorized. RC-D-002 (D) keeps that order and adds that T-002 waits for T-013; T-013 and the other new cards (T-014, T-015, T-016, T-062, T-063) are not authorized. Original text: None. Mode PLAN_ONLY. Execution needs (1) the Stage 6 baseline lock of SPEC v001.4 + RESOURCES v001 + this PLAN, and (2) Simone's separate authorization per lane; the lock alone grants no implementation, push, spend, SSH, DB write, deployment or external message.
