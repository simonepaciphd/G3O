# T-010 rulings record (codebook build)

Integrator session `20261029-claude-v2-b92f4144070ec139` (Claude Code, claude-opus-5-5, researcher persona). Uncommitted until the PI says (P6 / P4).

## 2026-10-29 — item template

PI, chat, verbatim: "1 a 2 a as long as when the codebook is procedurally loaded into a prompt the rules are filled out so that each value's definition has the full set of rules (even if repeated)"

- 1 a: question text, answer shape, rule prose, source rulings and wording state are their own template fields.
- 2 a: one rule slot per item; condition applied as generator check 16 in `item-template.md` (every value in a generated prompt or question carries the item's full rules, repeated).
- Procedural P1-P3 of that round (readable ids, explicit `none`, template uncommitted): put to the PI, not ruled separately; carried as defaults.

## 2026-10-29 — skeleton open fields

PI, chat, verbatim: "on all the above, you draft with subagents, sequentially if needed & I review; procedural accepted"

- 1 a: applicability table drafted by an agent, every cell marked for PI change → `drafts/applicability.*`.
- 2 a: per-item long-page combining rule proposed by an agent from the R-044 rule types → `drafts/combining-rules.*` (runs after the value lists, which its priority orders need).
- 3 a: value lists written word for word from the rulings, ambiguities flagged → `drafts/value-lists.*`.
- 4 a: minimal edits to the frozen questionnaire text following each direction, for PI line-edit → `drafts/cx-01.3-draft.*`.
- Procedural accepted: P1 procurement and AI-text items stay as placeholders outside the v2.7 build; P2 translation cells open until the translation table; P3 release label "2.7", set at sign-off; P4 skeleton and builder uncommitted until the PI says.

## 2026-10-29 — codebook review round 3 (drafts of the four open fields)

Pages: `codebook-review/round3/codebook-reference.html` and `questions-r3.html` (page hash `9842ea66d34e`). PI answered 22 of 61 on the page, then in chat: "pick the rest in keeping with my logic"; the integrator inferred the other 39 with confidence marks, plus a reading of the PI's comment on long-page checks; PI, chat: "all good". Record: `codebook-review/round3/codebook-rulings-round3.json`.

## 2026-10-29 — after the round-3 fold

PI, chat, verbatim: "1 draft & infer & show me for sign off, 2 minimal edit drafts 3 youd draft, 4 yes"

- 1: the 12 open item choices (fold-log-round3.md §2) are drafted and inferred by the integrator, then shown to the PI for sign-off.
- 2: the 5 owed sentences get minimal-edit drafts for PI line-edit.
- 3: the integrator drafts the delta for the 13 SPEC departures (fold-log-round3.md §3) → `planning/deltas/RC-D-003.md`, PI approval required.
- 4: sign-off: markers stripped, PI signs, integrator records the codebook hash (A-001).

## 2026-10-30 — final open choices, sentences, plan change

Shown in chat as A 1-16 (10 drafted picks, O12-O15 inferences, the pairs list, the activity-14 b reading), B 1-5 (minimal-edit sentences), C P1-P3 (pilot.py L134 sync, CX-50 stale clause removed, fold-log §4 mechanical choices = O16), D (RC-D-003, approval also approves `item-template.md`). Drafts: `drafts/final-open.*`.

PI, chat, verbatim: "all accepted"

## 2026-10-30 — after the final fold

Two points found by the fold, put to the PI in chat:
1. P1's target was misreported (no classifier file carries the sentence); the only other copy is the codebook's CX-01.3 classifier line on `core.disclosure_form` (mandated_report), "Otherwise a statutory annual report is formal_record." (no code formatting). a: apply the same insertion there; b: leave as signed.
2. Three ruling-option texts kept whole and tagged `amended_by` (record-02 a, activity-02 c, record-03 c). a: cut each before the overridden part, as for activity-14 b; b: keep whole, generator skips tagged text.

PI, chat, verbatim: "1a, 2a"

## 2026-10-30 — wording review method; repo cleanup procedurals

Integrator session `20261030-claude-v2-2b8200388885f8f9` (Claude Code, claude-opus-5-5, researcher persona). Asked in chat: "How do you want to do the wording review?" (a: agents draft the 136 missing definitions from the rulings, then one plain-language review page per page type, line-edit or approve in batches; b: PI writes them, agents lay out pages; c: chat, one item at a time), plus procedural P1-P5 (P1 builder and checklist stay uncommitted; P2 commit the status-only PLAN edits; P3 no push; P4 overlapping slot pairs shown side by side for the PI to drop one; P5 all-07 c summary work stays with T-028 / T-052 / T-053).

PI, chat, verbatim: "a (subagent), accept all"

## 2026-10-30 — wording review round 4 (pages `codebook-review/round4/`, 8 pages, 546 slots)

PI, chat, verbatim: "Reviewed the above; approve all the review items; give a subagent to disambiguate & propose default fixes where necessary. I want a single, clean final draft version of the codebook to look at & approve."

Integrator reading: every one of the 546 slots on the eight round-4 pages is approved as shown, including the 136 agent drafts (`drafts/definitions-r4.json`). A subagent proposes a default fix for each open point: the 13 `no_source` drafts, the six codebook problems the round-4 subagent reported, and the owed "Not required" sentence. It then folds the approved text and the proposed defaults into one clean draft codebook for the PI's approval. The proposed defaults are not approved by this ruling, and any of them that departs from SPEC v001.7 needs RC-D-004.

## 2026-10-30 — final draft codebook (`codebook-review/final-draft/codebook-final-draft.html`, built from sha256 `9ddf5a093ab836ee79d95ab04f70602ce1361b2db07512e14d9014f4b9d2cd8e`)

Shown in chat: approve the draft with all 13 proposed fixes (FX01-FX13, `drafts/fixes-r4.json`; none departs from SPEC v001.7, so no RC-D-004), or approve it except the fixes named. Next: sign-off (P3 / P4).

PI, chat, verbatim: "approved!"

Integrator reading: the final draft is approved as built, FX01-FX13 included.

## 2026-10-30 — sign-off form

Asked in chat. S1, 33 open translation cells (v2.5 to v2.7): a, sign now and fill them later by delta; b, an agent drafts the translation table, the PI reviews it, then signs. S2, the 26 questionnaire (CX-01.3) items: a, sign one by one on a page (r2#3); b, one batch signature in chat on the list of 26, which replaces r2#3's one-by-one form. Procedural: P1 `version_introduced` "2.7" on the 109 core items, the 11 placeholders open; P2 the sign-off build strips markers and keeps origin and source; P3 sign-off record `planning/t010/signoff-record.md`; P4 commits after signing, no push without the PI's word.

PI, chat, verbatim: "s1 b s2b; accept all"

## 2026-10-30 — RC-D-004 (batch signature, S2 b)

Shown in chat: RC-D-004 (`planning/deltas/RC-D-004.md`): R-025's "item by item" becomes one batch signature on the listed items; PLAN T-010 gate, task-graph row and W1 gate text to match.

PI, chat, verbatim: "approved"

## 2026-10-30 — translation table (S1 b; page `codebook-review/translation/translation-review.html`, page sha256 `cfc84824219a…`)

Shown in chat: the drafted v2.5↔v2.7 translation table for the 33 open leaves (`drafts/translation-r4.json`; 49 mapped, 38 not mappable, 16 `no_source` cells in 11 points, each with its default).

PI, chat, verbatim: "all review approved"

Integrator reading: every card on the page is approved as drafted, including the 11 `no_source` defaults.

## 2026-10-30 — signature

Put to the PI in chat: codebook release 2.7, sha256 `d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764` (sign-off build: translation folded, markers stripped, label 2.7, `version_introduced` 2.7 on 109 core items), and the 26 CX-01.3 items in one batch signature (RC-D-004).

PI, chat, verbatim: "all approved, I sign"

Record: `planning/t010/signoff-record.md`. Committed on `reclass/t010-contract` as `cb13571`, with `codebook/.gitattributes` (`-text`) so the signed CRLF bytes are kept on every OS; the builder pins CRLF to reproduce the hash.
