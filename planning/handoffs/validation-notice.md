DRAFT — not sent; PI approval required (T-061)

# Notice to the G3O validation plan: the pipeline output contract is changing

To: the integrator of the G3O validation plan (D001–D005), `C:/Users/spaci/repos/g3o_validation/planning/`
From: the integrator of the G3O pipeline reclassification plan
Date: [PI to decide: date of sending]

## What is changing

The G3O pipeline reclassification plan replaces the pipeline's output contract with a codebook release.

1. **Release label: `2.7`.** Each published row will carry one version label, the codebook release, in place of today's `contract_version`. The extract and validate contract labels (extract v2.7, validate v1.5) are recorded only in the run's setup record, not on rows.
2. **The codebook is the source of the contract.** One machine-readable file, `codebook/codebook.yaml` in the `G3O` repo, is the contract of record. The contract and prompt documents, including `g3o/extract/prompts/output_contract.md`, the enums and the JSON schema, are to be generated from it.
3. **The signed file.** Release 2.7 was signed by Simone Paci on 2026-10-30. Its sha256 is `d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764`, and it is on `G3O` `main`. The generated contract documents do not exist yet; they come from a later step of this plan.
4. **Vocabulary changes include:** a 9-value page-verdict vocabulary that replaces the 4-value `genai_evidence` enum; more activity-level fields; per-code supporting text from the source page.
5. **Already-published institutions are reclassified.** Institutions already published as documented or unclear, including the 27,648 unclear, are reclassified under the new contract in the same change.
6. **Old rows stay as they were.** v2.5 rows keep their contract version and are not converted. A two-way v2.5 ↔ v2.7 translation table is published, with unmappable cells marked.

## Why this concerns your plan

Your SPEC (SRC-12) and RESOURCES (RS-016) pin the G3O extraction prompt and output contract at `G3O` commit `85e93e09b352b072bf6a079520667cab0e1100f4` (2026-10-17), which is Output Contract v2.5. Pipeline rows produced after deployment follow release 2.7. Whether this affects your locked inputs or your frozen comparisons is for your plan to assess.

## Timing against deployment

- This plan does not deploy v2.7 until this notice has been delivered: the notice is a required step before the deploy card.
- The deploy itself waits on Simone's approval of the merge and deploy and on wave 5 being published. **No deployment date has been set.**
- After deployment, v2.7 rows are loaded but kept hidden from the public API and website until Simone releases them after an audit. Ordinary runs keep loading during that period.

## What this plan does not do

This plan does not edit any file of the validation plan. Any change to your SPEC, PLAN, RESOURCES or lock is decided by your plan's integrator and approved by Simone.

## What we ask

[PI to decide: (a) acknowledgement of receipt only; or (b) acknowledgement plus a statement of whether the change breaks a locked input of the validation plan.]
If the change does break a locked input, please tell us, as that affects our deploy step.

Reply to: coord mailbox `g3o-reclass-integrator`.

## Sources (pipeline reclassification plan, `C:/Users/spaci/repos/G3O/planning/`)

- Release label, one label per row, setup-record labels: SPEC D-001, R-050; delta RC-D-002 C3 a; DEC-013 a as amended.
- Codebook as source of truth, generated documents: SPEC D-001; RC-D-002 A.
- Signature and hash: `planning/t010/signoff-record.md`; codebook `release.label`.
- Page verdict, 9 values: SPEC R-015; replaces `genai_evidence`: SPEC D-008. More activity-level fields: SPEC G-001, R-004. Supporting text per code: SPEC G-002, R-040.
- Reclassification of published institutions: SPEC G-003.
- v2.5 rows unconverted, translation table: SPEC R-015, R-050, R-059.
- Hidden until release: SPEC R-056.
- Deployment gates and order: PLAN T-061, T-071 (wave W17).
- Validation is a separate plan: SPEC N-002. Two-step version rule for enum changes: SPEC C-007.

---

## Internal — remove before sending

### Coord mailbox message (draft; to be placed by the plan integrator after PI approval)

Recipient is unresolved (see open item 1). Proposed file: `C:/Users/spaci/repos/ai-os-private/coord/mailbox/<recipient>/YYYYMMDD-HHMM-from-g3o-reclass-integrator.md`

```
---
from: g3o-reclass-integrator
to: <recipient>
sent: <ISO timestamp at sending>
re: G3O pipeline output contract changes to codebook release 2.7 (notice)
ack: requested
---
The G3O pipeline reclassification plan changes the pipeline output contract to codebook release 2.7 (signed 2026-10-30, sha256 d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764). Your SRC-12 / RS-016 pin Output Contract v2.5 at G3O 85e93e0. No deployment date is set.

Notice: C:/Users/spaci/repos/G3O/planning/handoffs/validation-notice.md

This plan does not edit the validation plan. Please acknowledge, and say whether the change breaks a locked input. Reply to g3o-reclass-integrator.
```

### Open items for the PI

1. **Recipient and channel (DP-063).** The card recommends the coord mailbox, but the validation plan has no integrator mailbox yet: its PLAN binds the integrator's mailbox "at staffing/launch", and staffing is deferred. No `coord/mailbox/` directory for a validation integrator exists. Options: (a) create a role-alias mailbox (for example `g3o-validation-integrator`) and send there, so a future integrator finds it; (b) email via Simone; (c) both. [PI to decide]
2. **Notice path.** The card names `C:/Users/spaci/repos/G3O/planning/handoffs/validation-notice.md`; this draft sits in the integrator worktree (`planning/w1-orchestration`). The mailbox message links the main-checkout path, which exists only once the branch is merged or the file is copied there. [PI to decide: link the worktree path, or merge first]
3. **What to ask for** (see "What we ask"). [PI to decide]
4. Card inputs name the validation plan's BL-001 / SPEC builder-v004.3 / PLAN plan-v001. The current lock is BL-002 (2026-10-29, a format-only restructure: SPEC builder-v004.4). The SRC-12 / RS-016 pin was checked in the current files.
