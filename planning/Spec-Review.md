# Spec-Review.md — G3O pipeline reclassification, SPEC v001-draft1

Reviewer: isolated read-only subagent (general-purpose, claude-opus-5-5), spawned 2026-10-27 by session `20261027-claude-v2-3d85fb1367912304` under `planning-adversarial-review-protocol.md` SPEC mode. Given only the brief (Stage1-Interview.md, HANDOFF.md), the spec draft and its cited sources. Findings below are the reviewer's, transcribed by the parent; the disposition column is the parent's and the PI's.
Verdict: requires user decisions. Critical 0, High 5, Medium 8, Low 3.
Not read by reviewer: SRC-8 REPORT (used HANDOFF summary), v2.6 REVIEW.md, OWNER-REPRESENTATION.md.

| ID | Sev | Class | Spec IDs | Finding (short) | Disposition |
|---|---|---|---|---|---|
| SF-001 | high | USER-DECISION | R-004, C-001, C-004 | Free-text Group D fields (`activity_name`, `tool_name`, `vendor`, years, `reported_*`, `scope_notes`) have no producer: jev returns no text and nano "is not a classifier". Options: nano extracts free text as extraction; jev Choice + deterministic extraction; drop fields. | PI: "1 b, then a for what jev can't cover" -> R-006 |
| SF-002 | high | USER-DECISION | R-035, R-073, C-005 | Live link-following in back-fill creates sources no original search produced; D5 says corrections never invent search records. Status of those pages undefined (new provenance-tagged records outside the sample / new run). | PI: "2 a" -> R-036 |
| SF-003 | high | USER-DECISION | R-070, R-074 | Which pages each back-fill institution is reclassified on (all stored pages vs ambiguous only; documented institutions unspecified). | PI: "3 b" -> R-076 |
| SF-004 | high | USER-DECISION | R-080, R-082, A-008 | Agent read / PI audit scope undefined (census vs sample; what "agree" is between). D6 left audit design to be approved. A-008 untestable. | PI: "4b" -> R-082, Q-017 |
| SF-005 | high | SPEC-QUESTION | C-004, R-002, R-004, R-040 | No combination rule for codes and quotes on chunked pages (>32k tokens). CX-01.2 §11.1 has one for its fields only. | PI: P6 accepted -> R-044 |
| SF-006 | medium | USER-DECISION | G-005, R-054, N-003, R-071, Q-016 | Q4 b + Q8 b: `none` never gets CX fields, so R-060 full coverage is never reached; indices withheld indefinitely, G-005 hollow. | PI: "6 ... a" -> G-005 restated |
| SF-007 | medium | SPEC-QUESTION | R-015, R-005, Q-012 | Page-verdict vocabulary not defined as a whole, nor mapped to v2.5 `genai_evidence` / `has_genai_activity` (re-pilot 2 has 7 values, no `confirms_absence`). | PI: 1 c (8 values) -> R-015 |
| SF-008 | medium | USER-DECISION | R-016, Q-003 | Does a named "AI chatbot" alone now override the rule-based-chatbot exclusion (contract L12)? Agent reinterpretation of Q7 b recorded after the answer. Fold into Q-003. | PI: Q-003 a, SF-008 a -> R-016 |
| SF-009 | medium | SPEC-QUESTION | R-041, R-005, SC-04 | Downgrade sends "no supported positive" to `unclear`, so institution-level `no` looks unreachable; precedence of R-041 vs R-005 unstated. | PI: SF-009 b -> R-005; Q-019 a -> R-081 |
| SF-010 | medium | SPEC-QUESTION | D-001, R-050, C-007 | Label "v2.6" already names the unpushed `052fcb2` instrument (no public column change); this spec's contract differs. Version label scheme needed. | PI: default P4 accepted (label v2.7) |
| SF-011 | medium | SPEC-QUESTION | R-051, R-053, SC-07 | "Side by side" ambiguous (two rows per institution vs one current version per institution); for `none`, "not coded" is permanent. | PI: site shows most recent row; backend row per institution per run -> R-051 |
| SF-012 | medium | fix-mechanical + SPEC-QUESTION | R-070, Inputs, A-005 | Freeze date not fixed; treatment of v2.5 runs published between freeze and v2.6 deployment unstated. | PI: 3 b -> R-070 |
| SF-013 | medium | USER-DECISION | R-080, Q-013, R-025 | CX-01.2 §10 prerequisites (RA gold set C-015, sequencing vs WS9 attribution corrections, C2-C4 text unrun) neither adopted nor superseded. | PI: 5 b -> R-084, A-020 |
| SF-014 | medium | USER-DECISION | R-053, R-042, R-090 | INFERRED items that are substantive: "not coded" as a public value; quote matching for non-English text / normalisation; R-090 not covered by A-001. | PI: i superseded (R-053; residual Q-021), ii c -> R-042, Q-020 |
| SF-015 | low | SPEC-QUESTION | R-003, R-031 | Is the second pass gated to `confirms_activity` pages? Which model extracts links? | PI: default P5 accepted for link model; second-pass gating: PI 5 c -> R-003 |
| SF-016 | low | fix-mechanical | A-006, Quality | "Empty diff of original tables" conflicts with added columns; scope to original values. | applied in draft2 |
| SF-017 | low | fix-mechanical (+USER-DECISION on Q-014) | many | Missing acceptance tests for R-005, R-015, R-016, R-026, R-035, R-074, R-081, R-090, C-007, D-007; SC-08 tests a non-goal; Q-014 non-blocking although D-004 fails without Colin. | tests added in draft2; Q-014 pending PI |

Strengths the reviewer asked to preserve: ruling-ID tagging; R-083/C-006 guards (agreement ≠ accuracy; no pilot v1); R-075/A-005 no-silent-drop.
Reviewer's limits: fidelity to cited sources only; no cost/runtime assessment (cap open); no code feasibility check.
