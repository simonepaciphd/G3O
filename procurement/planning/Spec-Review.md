# Spec-Review.md: G3O procurement pipeline SPEC v001-draft

- Reviewer: fresh, context-isolated general-purpose subagent (claude-opus-5-5), `planning-adversarial-review-protocol` v0.2 SPEC mode, spawned 2026-10-27 by researcher session `20261027-claude-v2-0307d4d58c63fd23`. Read-only; returned findings to the parent, who wrote this file. The reviewer got the brief (launch card), the draft and the cited inputs, with no drafting rationale.
- Verdict: **Requires user decisions.** 13 findings: 5 HIGH, 6 MEDIUM, 2 LOW.
- The parent checked SF-005 against the primary file `PP\agent-workspace\2026-08-04-reply-to-ainhoa.md` and confirmed it: the file is the PI's reply memo of 2026-08-04 and contains §4 "Re-pin once v2.2 lands … rather than re-pinning twice".

## Disposition ledger

| Finding | Severity / type | Disposition | Applied in |
|---|---|---|---|
| SF-001 absence needs language/recall precondition | HIGH / DESIGN | USER-DECISION (chat item 1); PI ruled b 2026-10-27 | SPEC v001-draft.3 |
| SF-002 grain of absence rows; extension scope | HIGH / COMPLETENESS | USER-DECISION (item 2); SC-03 wording neutralised as mechanical fix; PI ruled b (extension sub-question still OPEN, Q-030) 2026-10-27 | SPEC v001-draft.3 |
| SF-003 D6 collapse vs. CB §2 vs. 1:1 join; stage precedence | HIGH / CONSISTENCY | USER-DECISION (item 3); ES §6.1 precedence cited; PI ruled b (non-OCDS identifier and D-002 join OPEN, Q-031) 2026-10-27 | SPEC v001-draft.3 |
| SF-004 `not_assessable` / `cannot_type` in contract rows | HIGH / COMPLETENESS | USER-DECISION (item 4); PI ruled b (`not_assessable` representation OPEN, Q-032) 2026-10-27 | SPEC v001-draft.3 |
| SF-005 PI memo 2026-08-04 missing; 2026-10-07 directive second-hand | HIGH / CONSISTENCY | (a) MECHANICAL: memo added as key `PM`, ruling tags re-pointed; (b) USER-DECISION (item 5); PI ruled a 2026-10-27 | SPEC v001-draft.2, v001-draft.3 |
| SF-006 restatements promoting proposals to `must` | MEDIUM / CONSISTENCY | USER-DECISION (item 6); PI ruled a 2026-10-27 | SPEC v001-draft.3 |
| SF-007 classifier validation cannot estimate census recall | MEDIUM / DESIGN | USER-DECISION (item 7); PI ruled a 2026-10-27 | SPEC v001-draft.3 |
| SF-008 matcher validation vs. ES §5 stratification | MEDIUM / DESIGN | USER-DECISION (item 8); PI ruled a 2026-10-27 | SPEC v001-draft.3 |
| SF-009 reproducing RA unfilled; Ainhoa availability | MEDIUM / FEASIBILITY | USER-DECISION (item 9); PI ruled a 2026-10-27 | SPEC v001-draft.3 |
| SF-010 verification criterion + frame pin | MEDIUM / COMPLETENESS | USER-DECISION (item 10); PI ruled approver RA or PI; criterion stated (residuals OPEN, Q-038) 2026-10-27 | SPEC v001-draft.3 |
| SF-011 Italy already meets Q-023 conditions | MEDIUM / FEASIBILITY | MECHANICAL: Q-014 tied to R-002/Q-023 and to the milestone | SPEC v001-draft.2 |
| SF-012 D1/§4.3 cites incomplete | LOW / CONSISTENCY | MECHANICAL | SPEC v001-draft.2 |
| SF-013 cross-references and labels | LOW / CONSISTENCY | MECHANICAL | SPEC v001-draft.2 |

## Reviewer's findings (as returned)

### SF-001 — HIGH / DESIGN — `confirms_absence` has no language/recall precondition
- Evidence: G-003, R-021 (searched source with no match → `confirms_absence`); R-010 + inputs table (query set en/es/fr/pt only; GPT5 gap shipped); Q-012/Q-013 cover retrieval and typing only. Root G3O CLAUDE.md assigns `subprojects/multilingual-pipeline/` "the language-readiness bar and its recall smoke sets". Contract §4.1: `no` = pages "contain no mention of GenAI".
- Problem: no line conditions when a "searched, nothing found" result is evidence of absence. An Italian/German/Russian notice searched with en/es/fr/pt terms yields a `confirms_absence` row that only records the query set's language gap. G-001 covers all 191 sources, so most non-Ibero/Francophone countries are affected.
- Consequence: the census claim (G-003) is built on mass false absences; R-022 aggregation then sets institutions to `no`.
- Alternatives: (a) emit `confirms_absence` only for sources whose language has passed the multilingual readiness bar, else report as not-searched/not-assessable; (b) emit but flag language state per source in D-011; (c) defer absence rows for affected sources until rosters land.
- User decision required: yes. Confidence: high.

### SF-002 — HIGH / COMPLETENESS — grain of negative-evidence rows undefined; SC-03 silently picks one
- Evidence: SC-03 "one `confirms_absence` row" per release with text; CB §4: "a staged rejected candidate is not a contract `no`/`confirms_absence` row; that row is created only after a source/institution search is complete"; CT §3.1 is one-page-per-request; ES §2 "Two artifacts per *relevant* procurement record" vs. D-002 extension row "one per primary row"; C-007 (~1M Uruguay releases); R-018 + C-008 (0/132 Uruguay linked).
- Problem: not stated whether an absence row is per release, per (source × institution), or per search, nor whether absence rows get extension rows. SC-03 decides it without a cited ruling, against CB §4.
- Consequence: orders-of-magnitude difference in row volume; D-002's 1:1 rule conflicts with ES §2; A-001/A-002 unspecifiable; under R-018 almost no Uruguay absence rows can enter D-001.
- Alternatives: (a) one absence row per release; (b) one per (institution × source repository × window); (c) absence counted in D-011 only. Separately: extension for relevant rows only?
- User decision required: yes. Confidence: high.

### SF-003 — HIGH / CONSISTENCY — D6 collapse, activity identity and the D-001↔D-002 join conflict
- Evidence: R-012/SC-07 "one activity per release" (PI memo D6: "lots and awards carried in the extension table"); D-002 "One row per primary row, joined on `record_id`" while AI §5 defines `record_id` at award/lot level; CB §2: tender and award "covering the same contracting process are separate source observations… collapse onto the same activity"; IR R6(b) collapses across releases of the same OCID; ES §6.1 "the higher-evidence stage governs the activity" (not in the spec).
- Problem: a primary row is release-level (or process-level per CB §2) while `record_id` is award-level, so a 1:1 join on `record_id` cannot hold. "Per release" (D6) and "per contracting process" (CB §2) give different activity counts. The stage of an OCID with both tender (`proposed`, R-006) and award (`announced`, R-005) is unspecified.
- Consequence: D-001, D-002 and A-003 cannot be built consistently; activity counts become an artefact of the collapse rule.
- Alternatives: (a) activity per release as D6 states, extension keyed on activity plus a child award table; (b) activity per OCID/process per CB §2, with stage by ES §6.1 precedence; (c) keep OPEN alongside Q-004.
- User decision required: yes (D6 is the PI's; CB §2 may need reconciling). Confidence: high.

### SF-004 — HIGH / COMPLETENESS — `not_assessable` and `cannot_type` have no contract representation
- Evidence: R-007/SC-06 (untypeable GenAI → "reported, not coded"); R-023/SC-04 (`not_assessable`); contract §4.7 has four `genai_evidence` values, none `not_assessable`; CT §3.1 "The supplied page MUST produce at least one row"; R-022 aggregates `has_genai_activity` across sources; `models.py` `genai_evidence_type` is `None` when not_assessable.
- Problem: whether these records produce D-001 rows, and with which values, is unspecified. Contract-confirmed GenAI evidence (`cannot_type`) is excluded from D-001 entirely, so institution aggregation ignores it.
- Consequence: an institution whose only GenAI evidence is untypeable can aggregate to `no`/`unclear`; A-001 (no null) violated if staging values flow through; typing is English-only (Q-013), so this covers most non-English positives.
- Alternatives: (a) no D-001 row, D-011 counts only, and R-022 told to treat them as blocking `no`; (b) code `activity_type: unknown` under v2.5 (ties to Q-003); (c) map not_assessable to an existing contract value (needs a PI ruling, since that is a coding rule).
- User decision required: yes. Confidence: high.

### SF-005 — HIGH / CONSISTENCY — the primary PI-ruling record is missing; two rulings sit in it
- Evidence: `PP\agent-workspace\2026-08-04-reply-to-ainhoa.md` ("From: Simone (PI)"), cited by AR §4/§8 as "the PI's reply memo" and linked from HI §4, is absent from *Authoritative inputs*; all 2026-08-04 tags go "via PC/ES/CB" (RA-recorded restatements). It contains: §4 "Re-pin once v2.2 lands … rather than re-pinning twice" (a PI ruling bearing directly on Q-001, which presents re-pinning only as SP P3's proposal); §2 classes Q1a, Q5a-c, Q6 (staging) as "Confirmed — proceed, no ruling needed", distinct from "The six rulings"; §5 the go-ahead conditions behind D-010 (tagged "RM status"); §2 Q5a the 745 rename rows and "merges apply only from a PI-filled `pi_decision`" (Q-026, R-013). Also missing: the PI's 2026-10-07 directive, quoted second-hand in LOG 2026-10-07, the AI/UP/VP/SP headers ("the full Uruguay run", Italy pairing, shared interface, validation priorities, sprint board). Q-007, D-014, D-008 and actor assignments rest on it uncited.
- Consequence: rule 2a requires citing the ruling itself; Q-001 omits a standing PI instruction and could be resolved against it unknowingly.
- Alternatives: (a) add the memo as a key and re-tag 2026-08-04 items to it; (b) add the 2026-10-07 directive; if no primary copy exists in the tree, ask Simone for the email or tag `USER (second-hand)`.
- User decision required: yes, only on whether a second-hand directive may be cited. Confidence: high.

### SF-006 — MEDIUM / CONSISTENCY — agent-authored restatements promote proposals to `must`
- Evidence: R-023 "must [RC]", but RC "Hard rules" restates IR R8, a proposal pending review (Q-005); R-031 "must [RC]" for never-sum-across-currencies = IR R5; R-037 "must [RC]" derives from AI §1 (draft). LOG 2026-10-11 records only the PI rulings "(2) long-lived branch per country" and "commit a repo CLAUDE.md (2a)", not approval of its contents. G-005/D-006 "must [AR §7]": AR §7 requires smoke runs, pinning and per-record provenance, not per-run archives or reproduction "by a person other than the one who produced it" (that is AI §7.4/SP I3, proposals). D-007 "must [INFERRED]".
- Problem: the spec's own extraction rule says proposal-resting lines are not settled. Committing RC was PI-requested, but nothing records PI approval of the rules RC restates.
- Consequence: unapproved coding and money rules bind the acceptance tests (A-004, A-009, A-011) as if ruled.
- Alternatives: (a) re-tag these lines `SOURCE:… (proposal)`/`should` and route to Q-005/Q-016; (b) ask the PI whether committing RC on 2026-10-11 ratified its hard rules.
- User decision required: yes for (b). Confidence: high on citations, medium on the authority question.

### SF-007 — MEDIUM / DESIGN — classifier validation cannot estimate the recall a census claim needs
- Evidence: D-008 requires P/R for `yes` and `yes ∪ unclear`; VP §A positives = "other OCDS sources' records hitting substantive terms" or PI-known cases (30); negatives = 60 random `confirms_absence`; G-003 census claim; R-010 known GPT5 blind spot.
- Problem: positives found by the query terms cannot contain retrieval misses, so recall measured this way is biased upward; at near-zero prevalence 60 random negatives almost certainly contain no positives and bound false-omission only loosely. CB §9's sample composition (tenders, awards, national/subnational, Latin/non-Latin script) and its "before 1.0" gate are not carried into D-008.
- Consequence: D-008 can pass while saying little about the absence rows G-003 depends on.
- Alternatives: (a) scope D-008's claim to precision plus conditional recall, state the limit; (b) add a retrieval-independent positive source (PI-known cases, another G3O channel) as a required stratum; (c) make codebook 1.0 per CB §9 a deliverable.
- User decision required: yes. Confidence: medium-high.

### SF-008 — MEDIUM / DESIGN — matcher validation design conflicts with PI-ratified ES §5
- Evidence: D-009 cites ES §5 and VP §B. ES §5 (2026-07-28 ruling): "a stratified sample (national/subnational × several countries × Latin/non-Latin script), report precision and recall per tier". VP §B: every fuzzy buyer from "the full-run review queue" (Uruguay) + 20% of auto-accepts. C-008: 185 Uruguay master rows, 0/132 linked.
- Problem: the draft protocol samples one country and one script with very thin master coverage; recall per tier is not computable from a review-queue sample; the spec does not say whether the threshold is global or per country/script.
- Consequence: R-016/A-008 could set a threshold invalid for subnational non-Latin matching elsewhere.
- Alternatives: (a) ES §5 stratification governs and VP is amended; (b) VP for Uruguay only, threshold scoped per country until stratified data exists.
- User decision required: yes. Confidence: high.

### SF-009 — MEDIUM / FEASIBILITY — the reproducing-RA actor is unfilled
- Evidence: Reproducing-RA actor, SC-12, A-009, G-005 rest on AI §7.4/SP I3/onboarding ("Ainhoa reproduces"). LOG 2026-10-11 (PI): "Ainhoa is not a contact for Asenat (she is starting a new job)". C-006: Ainhoa not a G3O collaborator, login unknown. LC 4 still assigns her shared core + Uruguay.
- Consequence: A-009 has no feasible executor; the whole-pipeline scope (G-001) rests on two RAs, one possibly unavailable.
- Alternatives: (a) name the reproducer as a role, not a person; (b) PI or agent reproduces; (c) confirm Ainhoa's availability as an OPEN item.
- User decision required: yes. Confidence: medium (the 10-11 statement concerns contact, not necessarily availability).

### SF-010 — MEDIUM / COMPLETENESS — no criterion for a "verified" source; population frame unpinned
- Evidence: R-030 (unverified → probe only); all 150 rows `unverified_snapshot`; RM Phase 2 kept Uruguay unverified pending ToS/rate-limit/pagination; RC: "which sources … are in scope" is Simone's; inputs row "Snapshot 2026-07-14" of a live tracker (SR); A-012 needs a status for all 191.
- Problem: nothing defines what evidence flips `verification_status` or who approves it; the 191-row frame is not pinned to a tracker version.
- Consequence: no source can lawfully reach a full run under the spec; A-012's denominator can drift.
- Alternatives: (a) add a verification-criteria requirement with an approver (PI or RA); (b) pin the frame to the 2026-07-14 snapshot or a dated re-export.
- User decision required: yes, on the approver. Confidence: high.

### SF-011 — MEDIUM / FEASIBILITY — Italy, the active second source, already meets Q-023 conditions
- Evidence: RM Phase 2 "Italy ANAC's 403s past its WAF"; LOG 2026-10-26: dati portal "rejected automated requests … not circumvented"; Q-014 (OCP bulk files as same source) bears on R-002/N-003.
- Problem: Q-014/Q-023 are marked blocking for Italy, but the spec does not flag that the 2026-11-04 Italy milestone (Q-027) may be infeasible.
- Alternatives: keep OPEN; tie Q-014 explicitly to R-002.
- User decision required: already in Q-014. Confidence: medium.

### SF-012 — LOW / CONSISTENCY — D1/§4.3 status cites incomplete
- Evidence: MEM: `unknown` shipped as v2.2 (PR #51, 2026-08-06) with a §4.2 row that "needs a PI line-edit"; "Procurement's tender coding is still blocked" on §4.3. PI memo §5: tender-only records "are codeable". R-007's trigger ("until the contract admits `unknown`") now appears met under v2.5.
- Problem: Q-002/Q-003 should cite these conflicting statements; leaving them OPEN is correct.
- User decision required: no (citation fix). Confidence: high.

### SF-013 — LOW / CONSISTENCY — cross-references and labels
- D-014 "OPEN Q-020: AI is a draft": draft approval is Q-016; R-040/R-041 also point to Q-020 and should point to Q-016 (keep Q-020 for thresholds).
- Q-009 merges two separate RA asks (PU #1 fan-out, PU #2 threshold); keep source numbering.
- N-007 is a non-goal labelled "contested": the non-goal (do not repurpose) is not what Q-017 disputes (whether to emit at all).
- N-005 mixes a state ("not installed").
- R-016's "until then every fuzzy candidate goes to review" is from PU #2, not PC.
- D-007's recording surface (`docs/sources/*.md` + `verification_note`) differs from PC/RM Phase 4 (tracker `notes_RA`); surface it.
- OCDS count: sources say 67; `sources.yaml` has 65 `is_ocds: true`.
- User decision required: no. Confidence: high.

## Coverage (reviewer)

Findings filed against G-001, G-003, G-005; D-001-D-003, D-006-D-010, D-014; R-007, R-010, R-012, R-016, R-021-R-023, R-030, R-031, R-037; A-001-A-003, A-008, A-009, A-012; C-006. Examined with no finding: G-002, G-004, G-006; D-003-D-005, D-011-D-013; R-001-R-006, R-008, R-009, R-011, R-013-R-015, R-017-R-020, R-024-R-029, R-032-R-036, R-038-R-041 (except SF-013 cross-refs); A-004-A-007, A-010, A-011 (A-004 makes `should` items R-033/R-041 hard gates; follows from SF-006); C-001-C-005, C-007, C-008.

## What this review does not show (reviewer)

Drive `pipeline/` vs. repo drift (Stage 2). Tracker xlsx read only via SR's summary; extension/link schemas checked by name only. Contract read in relevant sections only. Not verified: whether the 2026-10-07 PI email exists as a primary record; whether PR #51's §4.2 row got the PI line-edit; whether board issues #85, #86, #87, #141, #143 record PI answers (the parent checked #141 and #143 on 2026-10-27: no comments). Time/cost feasibility beyond Uruguay not assessed.
