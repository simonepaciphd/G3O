# Plan-Review.md — G3O pipeline reclassification, Plan-Draft v001-draft1

Reviewer: isolated read-only subagent (general-purpose, claude-opus-5-5), spawned 2026-10-27 by session `20261027-claude-v2-3d85fb1367912304` under `planning-adversarial-review-protocol.md` PLAN mode. Given only Plan-Draft.md, SPEC.md v001.3, RESOURCES.md v001, Stage1-Interview.md and Spec-Review.md. Findings are the reviewer's, transcribed by the parent; the disposition column is the parent's and the PI's.
Verdict: requires user decisions. Critical 0, High 11, Medium 12, Low 4.
Parent spot-checks: g3o-api `scripts/ingest.py` upserts `ON CONFLICT (run_id, institution_uid, source_id)` (L105, L162) — PF-004 basis confirmed; `g3o/extract/batch.py:49` `DEFAULT_TEXT_CAP_CHARS = 60_000` — PF-002 basis confirmed; g3o-api origin/main `acdb030` — PF-025 confirmed.
Reviewer did not check: droplet layout/disk, Neon PITR, live wave_windows, jev/Batch latency, SRC-1/4/5/7 contents, whether DEC-002 b keeps the run_id, cost arithmetic.
Dispositions recorded 2026-10-29 by the plan integrator (session `20261029-claude-v2-4af5481b98caa926`, Simone's ruling "3 a"), copied from the locked PLAN.md `## Finding disposition ledger`; findings and the rest of this file unchanged.

| ID | Sev | Class | Plan / spec IDs | Finding (short) | Disposition |
|---|---|---|---|---|---|
| PF-001 | high | PLAN-QUESTION | T-022..T-024; R-040 | No producer of quotes for pass-2 (activity) codes; T-022 runs before pass 2 | ACCEPT-MODIFIED; procedural default accepted 2026-10-27 (PLAN.md ledger, RC-BL-001) |
| PF-002 | high | PLAN-QUESTION | T-022, T-020; R-044 | 60k-char head+tail cap loses mid-page quotes; quote must come from the producing chunk; missing T-020→T-022 edge | ACCEPT; procedural default (PLAN.md ledger, RC-BL-001) |
| PF-003 | high | SPEC-DELTA / USER-DECISION | T-029, DEC-005; R-015, R-076, R-050, R-005 | Unclear institutions: unreclassified pages keep 4-value answers, so Stage 6 mixes vocabularies; "complete context" undefined | USER-DECISION → resolved; item 20 a (PLAN.md ledger, RC-BL-001) |
| PF-004 | high | fix-mechanical | T-051, T-054, T-074, DEC-002; R-073, A-006 | Ingest upsert `DO UPDATE` overwrites originals if a back-fill reuses run_id; no snapshot; rehearsal not on live-copy data | ACCEPT; procedural default (PLAN.md ledger, RC-BL-001) |
| PF-005 | high | USER-DECISION | DEC-001; R-073, C-005, R-055 | DEC-001 c overwrites sweeps (breaks R-073, G-001); b risks C-005 and wave rules | USER-DECISION → resolved; DEC-001 a (PLAN.md ledger, RC-BL-001) |
| PF-006 | high | PLAN-QUESTION | T-074→T-080..T-083; R-055, A-008 | Back-fill rows public before the PI audit; no release flag | ACCEPT; procedural default; item 21 b (PLAN.md ledger, RC-BL-001) |
| PF-007 | high | OMISSION | T-051, T-052, T-095; A-007 | Nobody owns `v_wave_*` views, materialized aggregates, sql/013, refresh | ACCEPT; procedural default (PLAN.md ledger, RC-BL-001) |
| PF-008 | medium | DEPENDENCY | T-071, T-070; R-070 | Wave-5 wait sits on T-070 only; deploy could precede wave-5 publication | ACCEPT; procedural default (PLAN.md ledger, RC-BL-001) |
| PF-009 | high | USER-DECISION | T-071..T-095 | Ordinary runs between deploy and release unplanned | USER-DECISION → resolved; item 21 b (PLAN.md ledger, RC-BL-001) |
| PF-010 | high | USER-DECISION | T-002, T-025, T-072; R-032 | Link fan-out unbounded per page within 3 hops; no cost/runtime measure | USER-DECISION → resolved; item 22 b (PLAN.md ledger, RC-BL-001) |
| PF-011 | high | OMISSION + SPEC-QUESTION | T-029, T-080; R-077, R-086, A-022, R-071 | No mechanism for the 114 transfers; owners may be `none`; inside or on top of the 400? | USER-DECISION → resolved; item 23 i, ii (PLAN.md ledger, RC-BL-001) |
| PF-012 | high | USER-DECISION | DEC-017, T-081; R-083, R-086 | Agent read not blinded; audit load unstated | USER-DECISION → resolved; DEC-017 b + blind (PLAN.md ledger, RC-BL-001) |
| PF-013 | medium | fix-mechanical | T-081, T-082; R-086 | Agent-read traceability: manifests, prompt hash, identical inputs, transcripts, per-record model id, SSH/pull gate | ACCEPT; procedural default (PLAN.md ledger, RC-BL-001) |
| PF-014 | medium | OMISSION / COLLISION | T-010, T-012, T-022, T-026, T-052, T-053, T-090 | Unclaimed enum/contract touchpoints across 3 repos (34 G3O files) | ACCEPT-MODIFIED; procedural default (PLAN.md ledger, RC-BL-001) |
| PF-015 | medium | PLAN-QUESTION | T-052; R-051, R-055 | "Most recent row" replaces per-wave latest-run-wins; w001 expiry 2027-01-01 hides later runs | USER-DECISION → resolved; item 24 b (PLAN.md ledger, RC-BL-001) |
| PF-016 | medium | RISK | T-002, DEC-003, T-073 | ~8 sequential Batch rounds per run; no runtime estimate | ACCEPT; DEC-003 option d deferred to T-002 (PLAN.md ledger, RC-BL-001) |
| PF-017 | medium | RISK | T-001, T-072, DEC-004 | Droplet disk unchecked | ACCEPT; procedural default (PLAN.md ledger, RC-BL-001) |
| PF-018 | medium | DEPENDENCY | T-029, T-030 | No e2e re-run on integrated back-fill path | ACCEPT; procedural default (PLAN.md ledger, RC-BL-001) |
| PF-019 | medium | PLAN-QUESTION | T-050..T-054; D-007 | Colin lanes mislabelled slack; channel and fallback owner unstated | USER-DECISION → resolved; item 25 i, ii (PLAN.md ledger, RC-BL-001) |
| PF-020 | medium | PLAN-QUESTION | RS-033 | No notice to the locked validation plan (BL-001) | ACCEPT; procedural default (PLAN.md ledger, RC-BL-001) |
| PF-021 | medium | SPEC-DELTA | DEC-009 b, DEC-002 b/c | Options that change the spec are not labelled | ACCEPT; none further (PLAN.md ledger, RC-BL-001) |
| PF-022 | medium | PLAN-QUESTION | T-060, DEC-014; D-008 | DEC-014 a impossible under T-012 edge; delta lacks old→new mapping, pins, §4.3 status | ACCEPT; DEC-014 b, item 26 a (PLAN.md ledger, RC-BL-001) |
| PF-023 | medium | PLAN-QUESTION | SC-08, G-004 | `export_bulk.py` / #175 README not updated | ACCEPT; procedural default (PLAN.md ledger, RC-BL-001) |
| PF-024 | low | USER-DECISION | DEC-008; C-004 | Both chunker options byte-based; limit is tokens | USER-DECISION → resolved; DEC-008 c (PLAN.md ledger, RC-BL-001) |
| PF-025 | low | fix-mechanical | header | Stale SPEC version and g3o-api ref | ACCEPT (PLAN.md ledger, RC-BL-001) |
| PF-026 | low | fix-mechanical | §4.1 | Edge errors (T-050→T-028, T-020→T-022; soft vs hard edges) | ACCEPT (PLAN.md ledger, RC-BL-001) |
| PF-027 | low | fix-mechanical | T-096, T-025, T-072 | Missing rerun agreement criterion, cap-reached record, full-set projection | ACCEPT (PLAN.md ledger, RC-BL-001) |

Strengths to preserve: per-card stop/continue and spec-delta rules; sole integrator per shared surface; T-096/Stage 8 reconciliation; complete gate list for paid/SSH/DB/push/deploy/external; T-072 smoke never touches the live DB; plan proposes spec fixes without editing; R-083/C-006 guarded.
