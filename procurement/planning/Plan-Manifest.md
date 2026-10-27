# Plan manifest: G3O procurement pipeline

- Protocol: `planning-protocol v0.4` (`C:\Users\spaci\repos\ai-os-private\personal\skills\planning-protocol.md`, read by path), retrofit (no retrofit mode exists; see `Retrofit-Notes.md`)
- Plan name: G3O procurement pipeline, whole pipeline (191 repositories, API/bulk/scrape, roadmap Phases 0-5)
- Mode: `PLAN_ONLY` (PI ruling 4, 2026-10-26): Stages 1-6, then Stage 7 packages ready tasks as RA handoffs; agents launch no execution lanes
- Started: 2026-10-27, researcher session `20261027-claude-v2-0307d4d58c63fd23` (claude-opus-5-5), from launch card `coord/launch/2026-10-27/3-g3o-procurement-plan.txt`
- Integrator and sole `CHANGELOG.md` writer: an agent session acting for the PI, started by Simone (U-1 c, 2026-10-27)

## Location and deliberate departure from the protocol

Governance files sit in `procurement/planning/` of the shared `simonepaciphd/G3O` repo, branch `procurement/main`, worktree `C:\Users\spaci\repos\g3o-wt-procurement` (PI ruling 3a, 2026-10-26). This departs from two protocol rules on purpose:

1. Protocol: files directly in the project repo's root `planning/` (`planning-protocol.md` "Artifacts and stage gates"; BOARD 2026-10-25T13:54 and 14:05). Here: a subproject folder inside a shared repo.
2. Protocol: one live plan per project. G3O already has other plans (e.g. the blind-validation plan in `C:\Users\spaci\repos\g3o_validation\planning\`). This plan is a second live plan in the `g3o` ledger project, scoped to the procurement subproject.

Also noted: BOARD 2026-10-25T13:02 says plans begun before v0.4 "(G3O)" finish under v0.3. No earlier planning-protocol artifacts exist for the procurement subproject (`procurement/planning/` did not exist on 2026-10-27), so this plan starts under v0.4 per ruling 2a.

## Artifacts and stage status

| Stage | Artifact | Path | Status | Date / evidence |
|---|---|---|---|---|
| 1 Specify | `SPEC.md` (draft) | `procurement/planning/SPEC.md` | approved | v001-draft.3 approved by Simone 2026-10-27 in chat |
| 1 Specify | `Spec-Review.md` | `procurement/planning/Spec-Review.md` | dispositions complete | 2026-10-27, isolated subagent; 13 findings; 10 ruled by PI 2026-10-27, 3 mechanical |
| 2 Resources | `RESOURCES.md` | `procurement/planning/RESOURCES.md` | approved | 2026-10-27, read-only subagent; 64 assets; PI gap decisions S2 applied; SPEC Resources column linked |
| 3 Map | `Plan-Draft.md` | `procurement/planning/Plan-Draft.md` | draft complete | v001-draft.1 2026-10-27; complete T-001-T-009; new T-011-T-050 (no T-030) + per-source template T-034.x; integrator OPEN (DEC-009) |
| 4 Challenge | `Plan-Review.md` | `procurement/planning/Plan-Review.md` | complete | 2026-10-27, isolated reviewer; 25 findings (0 C / 7 H / 12 M / 6 L); evidence spot-checked; 8 user decisions U-1-U-8 |
| 5 Adjudicate | `PLAN.md` + `Plan-Visual.html` | `procurement/planning/` | complete | 2026-10-27; U-1-U-8 ruled (S3); 25 dispositions; READY-WITH-BLOCKS; visual sync badge passes |
| 6 Baseline lock | `SPEC.md` + `RESOURCES.md` + `PLAN.md` | `procurement/planning/` | locked | 2026-10-27T08:02-07:00, Simone Paci (chat); committed locally on `procurement/main`, not pushed |
| 7 Launch | RA handoffs | `procurement/planning/handoffs/` (U-2 c) | Wave 1 packaged | 2026-10-27: T-011, T-058, T-031, T-047, T-022, T-048, T-037; PLAN_ONLY stops here (no launch); Ainhoa handoffs held until her availability is confirmed |
| 8 Reconcile | `CHANGELOG.md` + `Spec-Reconciliation.md` | `procurement/planning/` | in-progress (deltas) | SD-001 2026-10-27: RA-agnostic ownership; SPEC v002 + PLAN v2 re-locked 2026-10-27T08:54-07:00; SD-002 jev classification, SPEC v003 + PLAN v3 re-locked 2026-10-27T09:20-07:00 |

Process notes: `procurement/planning/Retrofit-Notes.md`.
