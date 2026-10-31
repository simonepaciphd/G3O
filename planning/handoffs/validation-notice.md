DRAFT — not sent; sending gated on the PI (T-061; DP-063 ruled 2026-10-31)

# Notice to the G3O validation plan: the pipeline output contract is changing

To: Ludovico Marini, integrator of the G3O validation plan (D001–D005), `simonepaciphd/g3o_validation`
From: the integrator of the G3O pipeline reclassification plan
Date: [filled in at sending]

## What is changing

The G3O pipeline reclassification plan replaces the pipeline's output contract with a codebook release.

1. **Release label: `2.7`.** Each published row will carry one version label, the codebook release, in place of today's `contract_version`. The extract and validate contract labels (extract v2.7, validate v1.5) are recorded only in the run's setup record, not on rows.
2. **The codebook is the source of the contract.** One machine-readable file, `codebook/codebook.yaml` in the `G3O` repo, is the contract of record. The contract and prompt documents, including `g3o/extract/prompts/output_contract.md`, the enums and the JSON schema, are to be generated from it.
3. **The signed file.** Release 2.7 was signed by Simone Paci on 2026-10-30 (re-signed the same day after a correction; the first hash, `d24bbc7c…0764`, is superseded and no row was produced under it). Its sha256 is `f0b1348cddbbe1ab0de8e16b80dae64a3e3400fe71788a6673f5cfc52348c72f`, and it is on `G3O` `main`. The generated contract documents do not exist yet; they come from a later step of this plan.
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

Please acknowledge receipt, and say whether the change breaks a locked input of the validation plan. If it does, that affects our deploy step.

Reply: agents by a comment on the GitHub issue that carries this notice; people by email to Simone.

## Sources (pipeline reclassification plan, `simonepaciphd/G3O`, `planning/` on `main`)

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

### Channel (DP-063, PI 2026-10-31)

Agents work through git issues and pull requests; people email. So the notice goes two ways, both only on Simone's word:

1. **GitHub issue** on `simonepaciphd/g3o_validation` (Ludovico's repo; his agent setup works through git), body = the notice above from "What is changing" to "Sources". Title: `Notice: G3O pipeline output contract changes to codebook release 2.7`. The plan integrator opens it after Simone says "send".
2. **Email** from Simone to Ludovico, short, pointing to the issue:

```
Subject: G3O pipeline contract is moving to codebook release 2.7

Hi Ludovico,

The pipeline reclassification plan replaces Output Contract v2.5 (which your SRC-12 / RS-016 pin at G3O 85e93e0) with codebook release 2.7. No deployment date is set. The full notice is in an issue on g3o_validation: <issue link>.

Could you acknowledge, and tell me whether this breaks a locked input of the validation plan? Your agent can answer on the issue.

Simone
```

### Open items for the PI

1. **Recipient and channel (DP-063): ruled 2026-10-31.** "Ludovico is integrator but will use a minimal system"; "agents should work through git issues/PRs, humans email". Recipient Ludovico Marini; channel a GitHub issue on `simonepaciphd/g3o_validation` plus Simone's email.
2. **Notice path: settled.** The file is on `G3O` `main` (PR #139); the issue carries the text itself.
3. **What to ask for: ruled 2 b** (acknowledgement plus whether the change breaks a locked input).
4. **Date of sending.** Filled in when Simone says "send".
5. Card inputs name the validation plan's BL-001 / SPEC builder-v004.3 / PLAN plan-v001. The current lock is BL-002 (2026-10-29, a format-only restructure: SPEC builder-v004.4). The SRC-12 / RS-016 pin was checked in the current files.
