# T-010 sign-off record: codebook release 2.7 and CX-01.3

The codebook file is signed only while this record holds its sha256 (A-001; `release.signature_record` in the file).

## Signature

- **Signed by:** Simone Paci (PI).
- **When:** 2026-10-30, about 10:15 -07:00, in chat.
- **Words, verbatim:** "all approved, I sign"
- **What was put to her:** codebook release 2.7, sha256 `d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764`, and the 26 CX-01.3 questionnaire items listed below, in one batch signature (RC-D-004, ruling S2 b).
- **Recorded by:** the plan integrator, session `20261030-claude-v2-2b8200388885f8f9` (Claude Code, claude-opus-5-5, researcher persona; DEC-012 a).

## The signed file

| | |
|---|---|
| Path | `codebook/codebook.yaml` |
| Branch, commit | `reclass/t010-contract`, `cb13571` (worktree `C:/Users/spaci/worktrees/G3O-integrator`; parent `375f1ff`) |
| sha256 | `d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764` |
| Size | 477,920 bytes, CRLF line endings; `codebook/.gitattributes` marks it `-text`, so git stores and checks out these bytes unchanged |
| Builder | `planning/t010/build_skeleton.py` on branch `planning/reclass-v2.7`; it reads SPEC v001.8 and the approved drafts and writes CRLF on every OS. Two runs give the same sha256 |
| Contents | 120 items: 109 `core.*` items at `version_introduced` 2.7, plus 11 procurement and AI-text placeholders outside the 2.7 build, whose `version_introduced` stays open. 14 shared rules, 15 retired entries |
| Checks passed at build | `verify()` (round trip, shared rules); round-3 and final checks; round-4 checks (546 page slots approved, definitions and fixes verbatim, check 8); sign-off checks (no markers, no pending fixes, no unsigned CX tags, open leaves only the 11 placeholder `version_introduced`) |

## Approvals folded into the file

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

- A-001 also requires generator checks 1-16 to pass on this file (RC-D-003 §14). Those checks come with T-013, which has not started.
- The three contract docs are generated from this file by T-013's generators.
- `checklist.md` was generated against the earlier build `23cb4857…`. It must be regenerated against this hash before T-010's self-check is complete.
- Re-pilot of the re-signed items: T-016, paid, run by Simone.
- Any change to the signed file needs a delta and a new signature (PLAN T-010, shared surfaces).
