# Retrofit notes: what planning-protocol v0.4 lacked for this plan

Input for a later skill amendment (PI ruling 2a, 2026-10-26). The skill was not edited. Running list; one line per gap, with where it bit.

1. **No retrofit mode.** The output-specification protocol assumes an interview from a broad goal. A retrofit starts from many existing documents of unequal authority. Needed: an evidence tag that separates PI rulings from RA/agent proposals. Used here: `SOURCE:<key> (proposal)` alongside `USER:<ruling, date>` (`SPEC.md` "Extraction rule").
2. **No place for already-done work before Stage 3.** Ruling 2a says completed work enters the plan as completed tasks with evidence; the spec template has no field for "already delivered" and the implementation-map protocol starts from zero. Stage 3 will need a `complete (evidence: …)` task state.
3. **Location rule assumes one repo per project and one live plan.** A subproject inside a shared repo, with a second live plan in the same ledger project, has no defined home (`Plan-Manifest.md` "Location").
4. **v0.3/v0.4 cut-over is stated per project, not per plan.** BOARD 2026-10-25 says G3O plans begun before v0.4 finish under v0.3; a new plan in the same project has no stated rule.
5. **Spec "what before how" vs. operating constraints.** Retrofitted specs inherit constraints written in implementation terms (CLI flags, branches). Recorded as constraints/requirements with their source; the protocol gives no guidance on rewording inherited ones.
6. **Stage-1 gate assumes few open questions.** A retrofit of a live pipeline inherits ~40 unsettled operational questions; the approval gate (no approval while blocking questions remain) would stall the plan. Used here: PI procedural P1 (2026-10-27) redefines "Blocking" as blocking named tasks, each becoming a plan gate (`SPEC.md` open-questions preamble).
