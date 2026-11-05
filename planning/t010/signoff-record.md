# T-010 signature record: release 2.7, r12 (RC-D-015 / RC-D-017 / RC-D-018)

## Current signature authorization

| | |
|---|---|
| sha256 | `93d77b1b2daf5cc7d287b5a3b6136a1a9fd13dacc9b6f0ea91133fd22df3e712` |
| File | `codebook/codebook.yaml` |
| Branch, commit | `orch1105/c-r12`, `5318d73` (committed blob; CRLF, `codebook/.gitattributes` `-text`; 11,995 lines) |
| Release | `2.7` |
| Approver | Simone Paci |
| Date | 2026-11-05, in chat |
| Recorder | researcher plan integrator, session `20261104-claude-v2-b18c125048383d63` (Claude Code, claude-opus-5-5; DEC-012 a) |

- **Words, verbatim:** "93d77b1b2daf5cc7d287b5a3b6136a1a9fd13dacc9b6f0ea91133fd22df3e712", sent alone in reply to the integrator's request "To sign, reply with the hash in the same message, for example: \"sign r12 93d77b1b…df3e712\"". This record takes that reply as the signature; it does not quote "I sign".
- **What was put to her:** the final unsigned r12 candidate above, after verification by the integrator (blob hash, CRLF, UTF-8, rule 2 text in all three year items, no local paths, codebook and question-set tests 55 passed / 1 skipped / 2 expected unsigned failures).
- **What r12 changes from r11:** W-R12-1 (`cx_grain` question-set state), W-R12-2b (year rule 1: fiscal-year labels; ranges give both end years), W-R12-3c (year rule 2: fiscal labels in any language, Japanese era, Buddhist Era, ROC and other digits by written form alone, never the country), W-R12-4/5 (quote step sees the chosen answer; 200-character cap), Q2 a round moves, local `source` paths stripped (RC-D-018 "5a"), r12 header (P5). Wording approvals: "4 yes", "5a" (RC-D-017); "yes", "all as rec" (RC-D-018). Provenance: `planning/t010/r12-provenance.json`.
- Frozen CX items remain covered by the existing batch-signature form (RC-D-004); the list below is unchanged.

## Unsigned candidate r13 (RC-D-019): not a signature

- Candidate sha256 (committed blob): `07610cc92c5c49f6fb80d22bfa128a1b4db7f6fb429a62f0ea8789943569c527`, `codebook/codebook.yaml` on branch `orch1106/f-r13`, commit `afc593e` (CRLF, `-text`).
- Status: UNSIGNED. The r12 signature above stays current until the PI signs this hash and the integrator records it here.
- Changes from r12: D1 b / F1 a (six answer values take `not_required`), C1 a (year value label), B2 a / B1 c (year rule 1), E2 a (contact e-mails); record `planning/t010/r13-provenance.json`.

## Superseded signature authorization (r11, `f948fe0b…`)

| | |
|---|---|
| sha256 | `f948fe0b2a36448db57b70b195567ffc39fb024efb986f9b0025581cee181e0d` |
| File | `codebook/codebook.yaml` |
| Release | `2.7` |
| Approver | Simone Paci |
| Date | 2026-11-01, current chat |
| Recorder | researcher integrator, 20261101-codex-v2-c10efbad5812817d |

Authorization is the PI's current instruction to publish approved governance changes including “the r11 release/signature work”, coupled to the exact r11 SHA256 in that same instruction. This record does not invent an earlier signature date or quote “I sign”. The complete engineering handoff records Q3a and the exact candidate; the current instruction retains r10's year rule. Prior wording approvals are recorded in the RC-D-007 clean copy; historical signature below is superseded.

The signed bytes are copied without rewriting. The release stays 2.7; r11 differs from r10 only in the channel rule text (`text_detection` to `ai_text`), with classifier questions and all year rules unchanged. Frozen CX items remain covered by the existing batch-signature form (RC-D-004). All applicable checks and fresh generation must pass before installation.

## Frozen CX items covered by this signature

| CX row | Item |
|---|---|
| CX-batch | `core.disclosure_form` |
| CX-batch | `core.disclosure_scope` |
| CX-batch | `core.content_contact_named` |
| CX-batch | `core.content_contact_details` |
| CX-batch | `core.content_contact` |
| CX-batch | `core.content_contact_emails` |
| CX-batch | `core.content_purpose` |
| CX-batch | `core.content_tool_or_model` |
| CX-batch | `core.content_vendor` |
| CX-batch | `core.content_data` |
| CX-batch | `core.content_users` |
| CX-batch | `core.content_status_date` |
| CX-batch | `core.content_human_oversight` |
| CX-batch | `core.content_risk_assessment` |
| CX-batch | `core.content_user_notification` |
| CX-batch | `core.outcome_kind` |
| CX-batch | `core.incident_kind` |
| CX-batch | `core.reported_outcomes` |
| CX-batch | `core.reported_incidents` |
| CX-batch | `core.evaluation_documented` |
| CX-batch | `core.evaluation_type_pre_deployment_testing` |
| CX-batch | `core.evaluation_type_pilot_evaluation` |
| CX-batch | `core.evaluation_type_independent_audit` |
| CX-batch | `core.evaluation_type_ongoing_monitoring` |
| CX-batch | `core.evaluation_type_user_feedback` |
| CX-batch | `core.evaluation_type_bias_or_safety_testing` |

## Historical signature record (superseded; retained verbatim below)

# T-010 sign-off record: codebook release 2.7 (re-signed under RC-D-005) and CX-01.3

The codebook file is signed only while this record holds its sha256 (A-001; `release.signature_record` in the file). The first signature table below is the current one; the 2026-10-30 morning signature (`d24bbc7c…`) is kept further down as superseded.

## Signature (current, RC-D-005)

- **Signed by:** Simone Paci (PI).
- **When:** 2026-10-30, in chat.
- **Words, verbatim:** "approved! go forth", answering a request to approve delta RC-D-005 and sign this hash ("delta approved, I sign", or changes; no change named). Record: `planning/t010/t010-rulings.md`, last section.
- **What was put to her:** the approved RC-D-005 candidate `planning/t010/candidate-r8/codebook-r8-signoff.yaml`, sha256 `f0b1348cddbbe1ab0de8e16b80dae64a3e3400fe71788a6673f5cfc52348c72f`, after the clean copy `planning/t010/RC-D-005-clean-copy.md` ("approved and cut"). The 26 CX-01.3 items listed below stay in the batch signature (RC-D-004, ruling S2 b).
- **Recorded by:** the plan integrator, session `20261030-claude-v2-74b5a83dce21f038` (Claude Code, claude-opus-5-5, researcher persona; DEC-012 a).

## The signed file (current)

| | |
|---|---|
| Path | `codebook/codebook.yaml` |
| Branch | `reclass/rc-d-005-codebook` (worktree `C:/Users/spaci/worktrees/G3O-codebook-r5`), a byte copy of `planning/t010/candidate-r8/codebook-r8-signoff.yaml` |
| sha256 | `f0b1348cddbbe1ab0de8e16b80dae64a3e3400fe71788a6673f5cfc52348c72f` |
| Size | 522,798 bytes, CRLF line endings; `codebook/.gitattributes` marks it `-text` |
| Builder | `python planning/t010/build_skeleton.py --spec-rev 2b43661` (default build `r8-signoff`): the signed 2.7 build from SPEC v001.8 plus `drafts/fixes-r5.json` .. `fixes-r8.json`. SPEC must be read at v001.8 (`2b43661`), because the builder copies SPEC row texts and v001.9 changed some rows; the signed bytes quote v001.8 |
| Checks at signature | builder checks r5-r8 (every slot change listed, W01-W45 byte-identical, r8 differs from r7 only by the cut); T-013 checks 1-16 on `reclass/t013-codebook` `307517f`: all PASS except 4 (this record, cleared by this signature) and 5 (generated files, pass on regeneration) |
| Approvals | RC-D-005 rulings, wording "drafts ok", resolver rounds 1-3, "approved and cut", "approved! go forth" — all verbatim in `t010-rulings.md`; every slot change in `drafts/fixes-r5.json` .. `fixes-r8.json` and `resolutions-r6.json` .. `-r8.json` |

## Superseded signature (`d24bbc7c…`, 2026-10-30 morning)

Superseded by RC-D-005 the same day: T-013's generator checks failed on this file (checks 1, 6, 7, 9, 10, 11, 13), so A-001 could not be met. No row was ever produced under this hash. It reproduces with `build_skeleton.py --build signed-2.7 --spec-rev 2b43661` (default out `planning/t010/superseded-d24bbc7c/codebook.yaml`).

The codebook file is signed only while this record holds its sha256 (A-001; `release.signature_record` in the file).

### Signature (superseded)

- **Signed by:** Simone Paci (PI).
- **When:** 2026-10-30, about 10:15 -07:00, in chat.
- **Words, verbatim:** "all approved, I sign"
- **What was put to her:** codebook release 2.7, sha256 `d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764`, and the 26 CX-01.3 questionnaire items listed below, in one batch signature (RC-D-004, ruling S2 b).
- **Recorded by:** the plan integrator, session `20261030-claude-v2-2b8200388885f8f9` (Claude Code, claude-opus-5-5, researcher persona; DEC-012 a).

### The signed file (superseded)

| | |
|---|---|
| Path | `codebook/codebook.yaml` (until RC-D-005) |
| Branch, commit | `reclass/t010-contract`, `cb13571` (worktree `C:/Users/spaci/worktrees/G3O-integrator`; parent `375f1ff`) |
| sha256 | `d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764` |
| Size | 477,920 bytes, CRLF line endings; `codebook/.gitattributes` marks it `-text`, so git stores and checks out these bytes unchanged |
| Builder | `planning/t010/build_skeleton.py` on branch `planning/reclass-v2.7`; it reads SPEC v001.8 and the approved drafts and writes CRLF on every OS. Two runs give the same sha256 |
| Contents | 120 items: 109 `core.*` items at `version_introduced` 2.7, plus 11 procurement and AI-text placeholders outside the 2.7 build, whose `version_introduced` stays open. 14 shared rules, 15 retired entries |
| Checks passed at build | `verify()` (round trip, shared rules); round-3 and final checks; round-4 checks (546 page slots approved, definitions and fixes verbatim, check 8); sign-off checks (no markers, no pending fixes, no unsigned CX tags, open leaves only the 11 placeholder `version_introduced`) |

### Approvals folded into the superseded file

All quoted verbatim in `planning/t010/t010-rulings.md`.

- Rounds 1-3 and the final fold: RC-D-002 and RC-D-003, chat "approve delta", "all accepted", "1a, 2a".
- Round 4 wording review: 546 slots on eight pages, including 136 agent-drafted definitions. Chat: "a (subagent), accept all", then "Reviewed the above; approve all the review items; …".
- Final draft with fixes FX01-FX13 (`drafts/fixes-r4.json`): "approved!" (draft sha256 `9ddf5a09…2cd8e`).
- Translation table, 33 leaves (`drafts/translation-r4.json`): "all review approved".
- Sign-off form: "s1 b s2b; accept all".
- RC-D-004 (batch signature): "approved".

## CX-01.3 items signed (26)

| CX rows | Items |
|---|---|
| CX-10..CX-18 | `core.disclosure_form` |
| CX-20..CX-25 | `core.disclosure_scope` |
| CX-30..CX-40 | `core.evaluation_documented` |
| CX-41 | `core.evaluation_type_pre_deployment_testing`, `_pilot_evaluation`, `_independent_audit`, `_ongoing_monitoring`, `_user_feedback`, `_bias_or_safety_testing` |
| CX-51 | `core.content_contact_named`, `core.content_contact_details`, `core.content_contact`, `core.content_purpose`, `core.content_tool_or_model`, `core.content_vendor`, `core.content_data`, `core.content_users`, `core.content_status_date` |
| CX-52 | `core.content_human_oversight`, `core.content_risk_assessment`, `core.content_user_notification` |
| CX-53 | `core.content_contact_emails` |
| CX-60 | `core.reported_outcomes`, `core.reported_incidents` |
| CX-61 | `core.outcome_kind`, `core.incident_kind` |

## Still open for A-001 and T-010 done

- T-013 regenerates the contract docs from this file and commits them; checks 1-16 must then all pass (A-001).
- `checklist.md` to be regenerated against `f0b1348c…`.
- Re-pilot: T-016 (scope RC-D-005 E9), paid, run by Simone.
- Any change to the signed file needs a delta and a new signature (PLAN T-010, shared surfaces).
