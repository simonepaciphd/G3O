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
