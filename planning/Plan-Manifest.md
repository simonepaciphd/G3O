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
