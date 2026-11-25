# T-010 signature record: release 2.7, r18 (RC-D-048, RC-D-049; clean-docs rulings of 2026-11-23)

## Current signature authorization

| | |
|---|---|
| sha256 | `64a8a2d808a3eb6c4583d7c65d1a9068e557785fdb17ed11e7ffd99e4ebe7dc5` |
| File | `codebook/codebook.yaml` |
| Branch, commit | `reclass/o1123-codebook-clean`, `16bc4be` (committed blob `99b5b3d37e6956d985a5b73ce1349bbc51503a78`; CRLF, `codebook/.gitattributes` `-text`; 10,681 lines); this record is on the same branch |
| Release | `2.7` |
| Approver | Simone Paci |
| Date | 2026-11-24, in chat |
| Recorder | Integrator session 20261124-claude-v2-9de68a0541729325 (Claude Code; claude-opus-5-5; engineer persona) |

- **Words, verbatim:** "ok i sign the codebook r18", in reply to the signature request naming codebook r18 sha256 64a8a2d8…e7dc5 on reclass/o1123-codebook-clean at 16bc4be, after the c2clean result was put to the PI
- **What was put to the PI:** Put to the PI in chat, 2026-11-24, by the integrator session 20261124-claude-v2-9de68a0541729325 (Claude Code; claude-opus-5-5), after reporting the main paid check (c2clean) result (cleaned R0 FN 80, FP 9, J 89 on 686 confirmatory units; recall 52.7%, precision 90.8%; Level 2 vs C2 F_r dJ +2, 95% -4 to 8; read descriptively, D5 (a)): signature request for the cleaned codebook r18, file codebook/codebook.yaml, sha256 64a8a2d8…e7dc5, on branch reclass/o1123-codebook-clean at commit 16bc4be; the signature record is clean-docs-audit/sign/signoff-r18-clean-block.TEMPLATE.md (what r18 changes from r17, the release note citing PREREG A34 and A38, known limits, and the corrected frozen-items line stating that core.reported_outcomes and core.reported_incidents no longer carry a rule text after the PI's P6 deletion of 2026-11-23); the PI's words in chat are the signature.
- **What r18 changes from r17:** r18 is the cleaned candidate (PI 2026-11-23, `RULINGS-1123.md` section 24, 1 (c)); the earlier r18 candidate `0cd68ed0…655e` was not signed. (1) Setting F, support-check half (RC-D-048): `core.support_entailment` gains `threshold_by_checked_item`; the bar of the support check is 0.6 when the checked item is `core.page_verdict` or `core.action_type`, and 0.8 for `core.activity_type` and every other checked item. (2) `core.has_genai_activity`: `rules/0` is the "AI purchase record" text (C-17 A) with the roll-up exception clause; `rules/1` is the page-verdict roll-up (RC-D-049, web pages only); `rules/2` is the supported-activity-observation rule (an activity observation is supported when its `activity_type` or its `action_type` is supported; PI 2026-11-23, 3 D). (3) Clean-docs layer 1: superseded slot texts and the release history moved out of the file to `planning/t010/codebook-history.json` (header lines 1-3 rewritten; `release.status` stays `signed`, R9). (4) Clean-docs layer 2: slot texts replaced, deleted or renumbered as the PI ruled on 2026-11-23 (`RULINGS-1123.md` sections 24-25: P1-P7, B1, B5, B6, B8, B11-B14, R2, R3, R9), each previous text in `codebook-history.json` `layer2`. Text sent to a model changes: pass 1 `e2a6b491691635f6af3f75de8d84b745d0113670404ab96dc2d0ca8d9d948277` and pass 2 `fbb438f572b33ffe159edcda04afc3f85cadd2e8d35da7508b4e2462e59ce197` (pins approved by the PI 2026-11-23, section 28), the jev activity criteria and the Stage 6 pooled requests that reuse them; item-hash lines no longer reach the model (R1 (c)); the Stage 6 quote instruction and the X35 instruction are unchanged. No value list changes (check 12 against r17 passes). Provenance: `planning/t010/codebook-history.json` (`0cd68ed0…` -> `dd3cc7e9…` -> this file).
- **Release note:** r18 adopts setting F (RC-D-048) and the page-verdict roll-up (RC-D-049) after the second confirmation run of the calibration study (study log: PREREG A34, the C2 pre-registration; PREREG A38, the C2 result).
- **Known limits recorded with the signature:** the other half of setting F is now codebook text (`core.has_genai_activity` `rules/2`), so a change of it is a codebook change and needs a new signature; the limits recorded with r17 stand.
- Frozen CX items remain covered by the existing batch-signature form (RC-D-004); the list below is unchanged. Two items on it, `core.reported_outcomes` and `core.reported_incidents`, no longer carry a rule text: the PI deleted their `rules/0` slots on 2026-11-23 (clean-docs P6, C-10 a); the previous texts are in `codebook-history.json` `layer2`.

## Superseded signature authorization (r17, `71f3576e…`)

| | |
|---|---|
| sha256 | `71f3576ecf96e47733f63849423e744f884e9876fc3669a1e1a87be7da08b0d4` |
| File | `codebook/codebook.yaml` |
| Branch, commit | `reclass/o1121-r17`, `3229e21` (committed blob `916bdf6e9bedb90e2ab66001a2eca9bf32045fff`; CRLF, `codebook/.gitattributes` `-text`; 12,881 lines); this record is on `codebook/r17-20261121` |
| Release | `2.7` |
| Approver | Simone Paci |
| Date | 2026-11-21, in chat |
| Recorder | G3O plan integrator `20261121-claude-v2-55bc915111fad15d` (Claude Code, claude-fable-5-2) (DEC-012 a; integrator by the PI's word of 2026-11-21) |

- **Words, verbatim:** "signed, go ahead", the entire reply, given in the integrator session to the message that put this file to the PI for signature. That message showed this sha256, asked for the signature in words on it, and asked for approval of the prompt diff with it. The hash itself was not pasted back (same practice as r14, r15 and r16); this record takes "signed" as the signature of that hash and as the approval of the prompt diff (ruling P, 2026-11-21: "approve after the development check, together with the signature").
- **What was put to the PI:** the rebuilt r17 file above; the table of every approval note before and after the rebuild; the prompt diff against signed r16, with the pins pass 1 `2024c61dc6c1600c1f9b20b9acd4ff5fd3c02627f47579269b5ddd08055a6d2b` and pass 2 `b96e903420aca2eb8b342da2128c9e44237fec533ba5be88d05046bcc3174bb9` (the Stage 6 quote instruction and the X35 instruction are unchanged from r16); the test results on commit `12569e3` (targeted unit batch of 32 files: 1,645 passed, 2 failed, both the two tests that read this record; end-to-end batch of 14 files: 396 passed); and what stands behind the text: a development check on 59 already-read pages, which is a check and not evidence, and no test on unread pages. The codebook checks were run before the signature on the candidate: 1 to 16 pass except 4 (this record). With `--previous` r16, check 12 flags `core.genai_mechanism_basis` (the value-list change below; C-007).
- **What r17 changes from r16:** the construct is AI adoption: any activity the institution's own page calls AI or machine learning counts, and generative AI is recorded as an attribute (`release.construct`; `core.page_verdict` and the other verdict values, labels and support-check labels follow; the generative attribute's own labels are unchanged). Staff training that the institution directs at public-sector staff is a confirmed activity. Content the institution publishes and credits to an AI tool counts. A rule the institution issues for others it regulates counts; a vendor page naming the institution as client counts; a ministry or department of a named government counts for that government. `ambiguous_genai` keeps its code and means that AI is mentioned at the institution but no specific activity can be made out. `core.genai_mechanism_basis` gains the value `no_generative_signal` (support status `not_required`; after the four generative signs in the long-page order): a value-list change that rides release 2.7's own two contract steps, label unchanged (C-007, as r16). `core.rule.genai_boundary`: the translation slot is rewritten. The title rule (`core.source_url`, `core.source_title`, `core.source_access_date`) defines the first heading and the PDF first line as the code produces them. 113 slot texts change in all; each keeps its r16 text beside it. Every change is traced to a ruling in `planning/t010/r17-provenance.json`.
- **Known limits recorded with the signature:** discovery, URL triage, the official-site prompt and the eligibility screen still search for generative AI (decided after the second confirmation run); the attribute items were written for generative tools and are left as signed; five explanatory `jev_missing_choice` strings still quote r16 text and are not sent to a model.
- Frozen CX items remain covered by the existing batch-signature form (RC-D-004); the list below is unchanged.

## Superseded signature authorization (r16, `381e41f8…`)

| | |
|---|---|
| sha256 | `381e41f8144bb68066c50fcf0241327943a9840f90a6239b9d8eabc0de881b8a` |
| File | `codebook/codebook.yaml` |
| Branch, commit | `codebook/r16-20261116`, `b2c3b2f` (committed blob `6837aef81fa97378405d0a94ce4bd5e89a7987f4`; CRLF, `codebook/.gitattributes` `-text`; 12,322 lines) |
| Release | `2.7` |
| Approver | Simone Paci |
| Date | 2026-11-17, in chat |
| Recorder | G3O integrator lane, plan integrator `20261117-claude-v2-304d807556676abd` (Claude Code, claude-opus-5-5) (DEC-012 a), on the relay of the morning-debrief session `20261117-claude-v2-17bb37b422d04368` |

- **Words, verbatim:** "1 i sign the codebook & approve the rest of the work as proposed -- use up to 5 subagents as needed", the entire reply, given in the morning-debrief session, where the single r16 candidate (this sha256; `agent-workspace/2026-11-16-overnight/governance/codebook-r16-candidate/SIGN-r16.md`) was the codebook put to her. The hash itself was not pasted back (same practice as r14 and r15); this record takes "i sign the codebook" as the signature of that hash. In the same session, on the r16 questions Q188-Q204: "all as rec accepted" (2026-11-17), which includes Q188 a (`core.content_vendor` keeps "looked up", as confirmed), Q189 b (the r16 release note quotes "rec" where the PI wrote "recl"; left), and Q204 a (below).
- **What was put to her:** the r16 candidate above, `SIGN-r16.md` and `DIFF-r15-r16.md` (same folder), and the rulings it applies (A8.1 a, A8.5 a, Q167 a, the rules/0 trim, Q185 a, Q186 a, Q187 a), each traced to a PI quote in `planning/t010/r16-provenance.json`. The codebook checks had **not** been run before the signature (`SIGN-r16.md`, "Owed after signing"). Run after it by this recorder (2026-11-17, without `--previous`, Q204 a; on this branch, before the record commit): checks 1-16 pass except 4 (this record) and 5 (generated files not yet regenerated on this branch; they are regenerated on `reclass/o1117-r16sign`); check 12 N/A. With `--previous` r15, check 12 fails: "value lists changed (['core.stage_as_of_basis']) but label 2.7 -> 2.7 is 0 steps". Under Q204 a the label stays 2.7 and that change is owed as a C-007 contract step (integrator).
- **What r16 changes from r15:** A8.1 a (`core.developer` coder derived -> quote_step, linkage pipeline -> extractor, one rule sentence), A8.5 a (`core.stage_as_of_basis` takes three codes `publication` / `stated` / `access`; its r2 five-value rule moved to `release.r16_dropped`), Q167 a (`core.developer` rules/1 lookup sentence dropped), the rules/0 trim ("from lookup or page" -> "stated on the page" in `core.contracting_party`, `core.developer`, `core.developer_basis`), Q185 a (`core.developer_basis` rules/2, rules/3; `core.stage_as_of_basis` rules/1), Q186 a and Q187 a (the "same five values" sentence dropped from `core.developer_basis` rules/1 and `vocabularies.provenance`). Changed item hashes: `core.contracting_party`, `core.developer`, `core.developer_basis`, `core.stage_as_of_basis`. `core.contracting_party` is on procurement's pipeline list, so the C-007 steps apply to it. Record `planning/t010/r16-provenance.json`.
- Frozen CX items remain covered by the existing batch-signature form (RC-D-004); the list below is unchanged.

## Superseded signature authorization (r15, `ca1bf616…`)

| | |
|---|---|
| sha256 | `ca1bf616d596213dad7064bd24921928186bce42d912a7b54e5723f41fc73d3a` |
| File | `codebook/codebook.yaml` |
| Branch, commit | `codebook/r15-20261110`, `3acf01a` (committed blob; CRLF, `codebook/.gitattributes` `-text`; 12,226 lines) |
| Release | `2.7` |
| Approver | Simone Paci |
| Date | 2026-11-10, in chat |
| Recorder | G3O BUILD lane, plan integrator `20261110-claude-v2-43cab3e7a582d021` (Claude Code, claude-opus-5-5) (DEC-012 a) |

- **Words, verbatim:** "signed & lock", the entire reply, given immediately after the integrator presented this exact sha256 and asked (1) for the signature of r15 and (2) for "lock" for RC-D-026. The hash itself was not pasted back (same practice as r14); this record takes the reply as the signature of the presented hash.
- **What was put to her:** the r15 candidate above, its check results (checks 1-16 pass except 4, this record; check 12 N/A), and the one changed sentence (`core.source_credibility` rules/1 adds "or `not_asked` on an unreadable page" to the missing-type `low` list; `credibility_map` gains `not_asked: low`), traced to the PI quote in `planning/t010/r15-provenance.json`.
- **What r15 changes from r14:** RC-D-026 10 a (PI 2026-11-10 chat "9a 10 a"): `core.source_credibility` credibility map missing keys gain `not_asked` -> `low`, and the rules/1 map sentence names it; record `planning/t010/r15-provenance.json`.
- Frozen CX items remain covered by the existing batch-signature form (RC-D-004); the list below is unchanged.

## Superseded signature authorization (r14, `7972b8c1…`)

| | |
|---|---|
| sha256 | `7972b8c1989af5e182c19d9d73c4ab20cb2440b06c7be33dff1701071658123b` |
| File | `codebook/codebook.yaml` |
| Branch, commit | `codebook/r14-20261110`, `a03ad72` (committed blob; CRLF, `codebook/.gitattributes` `-text`; 12,216 lines) |
| Release | `2.7` |
| Approver | Simone Paci |
| Date | 2026-11-10, in chat |
| Recorder | G3O BUILD lane, plan integrator `20261110-claude-v2-0da6eb1353858ba3` (Claude Code, claude-opus-5-5) (DEC-012 a) |

- **Words, verbatim:** "Signed and approved!", the entire reply, given immediately after the integrator presented this exact sha256 with the instruction "send the SHA256 above in chat to sign r14". The hash itself was not pasted back; this record takes the reply as the signature of the presented hash and states that difference from the r13 practice.
- **What was put to her:** the r14 candidate above, its check results (checks 1-16 pass except 4, this record; check 12 N/A), and the four agent- or integrator-drafted sentences quoted in full in chat (permanent_pilot same-part limit; credibility map sentence; C7 a phrase in `core.confidence` rules/1; C8 b `core.confidence` rules/2), with every other change traced to a PI quote in `planning/t010/r14-provenance.json`.
- **What r14 changes from r13:** RC-D-025 A1 (source-confidence rule), A2 / B2 a / B3 / C1 / C2 (`core.permanent_pilot` support-checked classifier with labels and pilot/production-only override), C4 c (v25 permanent-pilot rule and its across-parts note retired from `core.adoption_stage`), C5 / C6 a (X22 credibility map; undated = low), C7 a, C8 b; record `planning/t010/r14-provenance.json`.
- Frozen CX items remain covered by the existing batch-signature form (RC-D-004); the list below is unchanged.

## Superseded signature authorization (r13, `07610cc9…`)

| | |
|---|---|
| sha256 | `07610cc92c5c49f6fb80d22bfa128a1b4db7f6fb429a62f0ea8789943569c527` |
| File | `codebook/codebook.yaml` |
| Branch, commit | `orch1106/f-r13`, `afc593e` (committed blob; CRLF, `codebook/.gitattributes` `-text`; 12,032 lines) |
| Release | `2.7` |
| Approver | Simone Paci |
| Date | 2026-11-05, in chat |
| Recorder | v2.7 orchestrator lane F (Claude Code, claude-opus-5-5), on the orchestrator's relay of the PI's reply; the plan integrator confirms it (DEC-012 a) |

- **Words, verbatim:** "07610cc92c5c49f6fb80d22bfa128a1b4db7f6fb429a62f0ea8789943569c527", the entire reply, given after the orchestrator wrote "If you pick (a), sign by replying with the hash". This record takes that reply as the signature and as choice (a) on the r13 questions (Q2 a: the two-digit pivot covers every two-digit year, end years included; Q1 a: `release.r4_dropped` kept as history; Q3 a: no R-042 change); it does not quote "I sign".
- **What was put to her:** the unsigned r13 candidate above and the sentence list `agent-workspace/2026-11-06-v27-orch/lane-f-r13-sentences.md` (every changed signed sentence, old and new), after checks 1-16 (all pass except 4, this record) and the codebook, question-set, storage, fixture-set and extract tests.
- **What r13 changes from r12:** RC-D-019 D1 b / F1 a (`none_reported`, `none_documented`, `none`, `unclear`, `unresolved`, `not_an_activity` take `not_required`, by value on every item; the R-041 and FX09 list sentences in their four current copies), C1 a (X35 year value label: converted CE year), B2 a / B1 c (year rule 1: Japanese era, Buddhist Era and ROC years; two-digit pivot (current year mod 100) + 25), E2 a (`content_contact_emails`: no address found gives `not_documented`), r13 header. Provenance: `planning/t010/r13-provenance.json`.
- Frozen CX items remain covered by the existing batch-signature form (RC-D-004); the list below is unchanged.

## Superseded signature authorization (r12, `93d77b1b…`)

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
