# T-027 engineering handoff — ready for capacity

Role: engineer, existing eng-b lane; integrator owns all governance.
Cwd for native activation: H:/My Drive/Research/G3O (exists; canonical project root).
Task implementation has not started. Input review started only after T-012 proposed verification. All four native Codex slots were occupied at preparation; queue until a fresh capacity check permits launch. Earlier extra-slot permission was for the D-007 review lane.

## Exact inputs

- T-012 base: C:/Users/spaci/worktrees/G3O-eng-b-t012, reclass/t012-enums, clean unpushed 6cbd55126bb1d1d6097156546133fcd464a356ee. Preserve that branch.
- Create isolated C:/Users/spaci/worktrees/G3O-eng-b-t027, reclass/t027-record from that exact commit only after current branch/capacity/claim reconciliation.
- Current governance: C:/Users/spaci/worktrees/G3O-orch-20261101/planning/, SPEC v001.14 and RC-D-010.
- Read D-007-interface-spec.md, D-007-field-map.json, T-012-Q2a-verification.json, RC-D-010 and exact archived chat reply.
- Signed r11: f948fe0b2a36448db57b70b195567ffc39fb024efb986f9b0025581cee181e0d; 52 generated questions (31 single,19 yes/no,2 multi), each with chosen-answer-probability threshold. Questions/year rules unchanged.

## Narrow ownership

Write only g3o/common/jev_record.py and its dedicated tests in the new worktree. Read the shared jev client, Stage2/3 patterns, Q2a storage CoderRecord and signed item rules. No governance/codebook edits, consumer rewiring, writer/schema changes, runtime call, DB or API work. Request a concrete interface delta from the integrator if needed; do not broaden claims. Claim paths through the fresh native activation or parent delegation and check every live claim before writes.

## Approved behavior

PI: Apply the existing downgrade rules to the affected code, recording that its probability was unavailable.

Preserve original code, actual per-code model/request/version/chunk metadata and full internal distribution. Preserve None for absent distribution or missing chosen entry; no synthetic 0/1, generic confidence, invented IDs or setup pointer. Record explicit unavailable-probability cause. Page verdict stays coded and is tagged downgraded; other items follow their existing signed downgrade mapping. Mechanical/rule-set not-applicable is a different condition. Do not silently implement a universal unknown mapping. If an item lacks the relevant signed mapping, report the exact gap.

The Stage2 adapter currently uses probabilities.get(choice,0.0); do not copy it. The generic client also has Noul answers without distributions by design, but this signed generated question set is categorical. Keep type-specific not-applicable distinct from unexpected absence for a probability-bearing classifier item. Round-trip all chunks, not only first-chunk IDs. Bind to existing storage records through an explicit documented adapter/interface; downstream callers are implemented by their owning cards.

## Verification and return

Use free local tests only. Cover exact0.8, below0.8, actual0, absent distribution, absent chosen key, page retention, signed item downgrade, mechanical not-applicable, complete distributions, original code, per-chunk distinct request/model IDs, JSON round-trips and refusal of fabricated required provenance. Show compatibility with Q2a storage for an explicit fixture; no fake runtime readiness. Run appropriate focused regressions and lint; broad suite only as justified. Preserve T-012 Windows I/O qualification and six existing T-035 strict exceptions.

Return clean local commit, exact file hashes, tests/transcripts, interface example, remaining consumer bindings and proposed verified/blocked status. Do not push/merge/deploy/send external messages. T-031 independent review remains. T-050B requires implemented T-012/T-027 conformance, authorized delivery and Colin acceptance. Runtime instrument wiring stays T-030/T-035.

> r12 note (integrator, 2026-11-05, RC-D-018 P2): codebook r12 is signed, SHA256 93d77b1b2daf5cc7d287b5a3b6136a1a9fd13dacc9b6f0ea91133fd22df3e712 (`planning/t010/signoff-record.md`). The r11 hash above is historical for this handoff; r12 changes the year rules (W-R12-2b/3c), the quote-step rule and round moves.
