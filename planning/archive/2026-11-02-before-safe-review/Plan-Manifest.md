# Plan manifest: G3O pipeline reclassification

Protocol: planning-protocol v0.4 (2026-10-25)
Plan name: G3O pipeline reclassification (jev classifies, gpt-5-nano extracts support; contract v2.6 + CX-01.2; back-fill)
Mode: PLAN_ONLY (card `coord/launch/2026-10-27/7-g3o-pipeline-reclass-plan.txt`; no code change, paid run or DB write without later sign-off) Lock grants no execution authority.
Owner / sole substantive approver: Simone Paci
Project repo: `C:/Users/spaci/repos/G3O` (pipeline repo; PI ruling Q2 b1, 2026-10-27). Files stay uncommitted until sign-off; no push.
Relation to other plans: separate from "G3O validation D001-D005" (`C:/Users/spaci/repos/g3o_validation/planning/`, BL-001). PI ruling Q1, 2026-10-27: "this is a different plan, about the main pipeline, validation is about human validation of the database". That plan may later need a narrow delta for its contract-pinned comparison inputs (its RS-016 / SRC-12); not raised here.
Started: 2026-10-27, researcher session `20261027-claude-v2-3d85fb1367912304` (Claude Code, claude-opus-5-5)
Prior scoping: `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-unclear-screen/HANDOFF.md` (rulings 1-11, S1-S9, P-A..P-H)

| Stage | Artifact | Status |
|---|---|---|
| 1. Specify | `SPEC.md` + `Spec-Review.md` | approved 2026-10-27 (v001); v001.4 approved 2026-10-28 (Stage 5 deltas, `Stage5-Rulings.md`) |
| 2. Resources | `RESOURCES.md` | approved 2026-10-27 (v001) |
| 3. Map | `Plan-Draft.md` | draft1 complete |
| 4. Challenge | `Plan-Review.md` | complete (27 findings; dispositions in PLAN.md ledger, 2026-10-28) |
| 5. Adjudicate | `PLAN.md` + `Plan-Visual.html` | complete 2026-10-28: READY-WITH-BLOCKS, 44 cards / 27 waves; rulings `Stage5-Rulings.md`; second independent review applied (RV2-*); `plan_viewer.py --check` ok |
| 6. Baseline lock | SPEC + RESOURCES + PLAN | locked 2026-10-28T09:50-07:00 by Simone Paci (RC-BL-001, chat "lock"); record `Baseline-Lock-2026-10-28.json`; pre-lock copies `archive/2026-10-28-baseline-prelock/` |
| 7. Launch | handoffs (engineer cards) | not-started (PLAN_ONLY) |
| 8. Reconcile | `CHANGELOG.md` + `Spec-Reconciliation.md` | not-started |

## Current continuation (2026-11-01)

The historical stage table above describes the original baseline. Current SPEC v001.13 applies approved RC-D-007/009 and the exact S1a/S2a/P1a/P2 reply. T-050A approved; T-012 Q2a active, T-027 gated. Local branch planning/r11-rcd009; no remote push/merge/deploy. Current generated page: page/Plan-Visual.html. Delta application lock retains original RC-BL-001 history.

Current execution update: SPEC v001.14 / RC-D-010; T-012 proposed verified locally with qualified test evidence; T-027 input review complete, engineering queued for capacity. See Delta-Lock-RC-D-010-2026-11-01.json and handoffs/T-027-engineering-handoff.md. Prior hash records are historical snapshots.

Latest bounded execution (2026-11-01): startup B approved; T-027 local library independently verified at 6868825 (245 regressions, 72 record tests, 260 independent cases). One implementation defect corrected with no spec delta. See handoffs/T-027-local-verification.json and archive/records/T-027-local-reconciliation.md. SPEC remains v001.14; no successor launch, external delivery, push/merge/deploy or full pipeline acceptance.

Latest bounded execution (2026-11-02): RC-D-011 email follow-up independently accepted locally at 36d88bc7e20b3347b92f72e749d12f43a36ccc27; 326 engineer regressions, 22 independent conformance tests and 192 independent regressions. SPEC v001.15/RESOURCES v001.3 and D-007 v1.1 unchanged. See handoffs/RC-D-011-local-verification.json and handoffs/RC-D-011-next-stage.md. Four subagents covered implementation, contract review, source/readiness audit and independent final verification. Full T-050B/runtime/external/T-031 remain gated. Historical stage table and application lock remain original records.

Latest bounded preparation (2026-11-02): source assembly 2812ca22253adfa1f70f81d08f377fa15a8619f9 and separate estimator calibration ffb5be23fe8b25cdf12ee4315002e8c8d88c7bce independently verified locally; no task status promoted to complete.16source checks/9outputs,342engineer tests/1optional skip,66chunker tests,92independent assertions/205regressions/1optional skip. T016 offline report correction is separate; accepted wording retained. DP007,calendar,T024/T028 producers and fullT050B,T030/T035/T031/release gates remain. See handoffs/Preparation-local-verification.json and Preparation-next-stage.md; locked SPEC/RESOURCES/application records unchanged.
