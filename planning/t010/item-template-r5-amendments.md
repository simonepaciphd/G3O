# Item template: RC-D-005 amendments (draft, not approved)

Status: DRAFT for the PI's approval with `planning/t010/RC-D-005-clean-copy.md` (section D). It amends `planning/t010/item-template.md` (approved 2026-10-30 with RC-D-003 §14), which is not edited until approval; on approval the integrator folds these sections into it.
Drafted 2026-10-30 by the resolver subagent of the plan integrator (Claude Code, claude-opus-5-5). PI ruling, chat, 2026-10-30: "drafts ok, give a subagent the task to resolve ambiguities in a way that's coherent with the rest, i will approve final clean copy". Procedural defaults F1 a, F2 a, F6 a, F7 a and G1 (put to the PI with the RC-D-005 follow-ups) and resolutions R2 b, W33 and E1 (`drafts/resolutions-r6.json`).
Implemented in T-013's checks and generators, `reclass/t013-codebook` (G3O-eng-b), commit named in the clean copy. `codebook/schema.json` in that branch still has the pre-amendment shapes (outside the resolver's edit scope; T-013 follow-up).

## A1. Values `none` on mechanical and derived items (F1 a) — §2 field 13

`values: none` is also allowed (a) for `list` items (a list of extracted strings has no codes), and (b) for every `mechanical` or `derived` item, whatever its answer type. Such an item's codes, where it has a closed set, come from one of: `value_codes` (a plain list of snake_case codes), `value_vocabulary` (the name of a list in `vocabularies`, e.g. `support_status`), or, for a `yes_no` item, `yes` / `no`. Checks 1 and 7 read codes this way.

## A2. Computed value list for the year classifiers (F2 a) — §2 field 13

A single-answer `classifier` item may hold `values: {candidates: <text>}`: its choices are computed per row (the year items: deterministic year extraction plus the candidate `unknown`, C16). Such an item has no value definitions; its question carries the item's full rules once after the instruction (the check-16 condition read for choices without definitions).

## A3. "Any value" gate (F6 a) — §2 field 10

A gate may read `{item: <id>, values: any}`: any real (non-missing) value of the gate item opens it. Used for the scale unit (`as_ruled: any stated`).

## A4. `missing_tokens: none` (F7 a) — §2 field 20

`missing_tokens` may be `none` for an item that takes none of the reserved labels (`core.page_verdict`; its `not_assessable` is a value).

## A5. Gate order through a non-classifier gate item — §4 check 7

When a gate item has no classifier pass and round (an extractor or mechanical step), its position is that of its own gate item (it exists once that item does); a gate item with neither takes no position, and a gated classifier round on it fails check 7.

## A6. Parts form (R2 b) — §2 fields 12, 13; §4 checks 1, 6, 8, 9, 16

An item made of linked parts (`core.observed_actor_relationship`: relationship; role of the searched institution) holds `values` as a mapping: `parts` lists the part keys in order; each part key holds an ordered `{code, definition}` list; `part_instructions.<part>` holds the question of every part after the first (the first part uses field 12); a mapping with `part: <part>` holds that part's gate. Each part yields one jev question (check 6 counts one per part); codes are checked per part (check 8); every part needs its question and definitions (check 9) and its definitions are followed by the item's full rules (check 16). The parts are published as one column under the item's own rule.

## A7. Shared prompt slots, jev flags and missing choices (G1) — §1, §3, §4 checks 3, 16

- §1: a top-level key `shared` holds signed text slots used by every prompt: `part_prompt.sentence`, `part_prompt.temporary_answer.label` and `.meaning` (all-03 a, RC-D-005 5 a), `system_prompt` and `system_prompt_stage6` (RC-D-005 6 a), each with `applies_to`.
- A value may carry `jev_choice: false`: it is a value of the item but never offered as a choice (`not_assessable`, P3).
- An item may carry `jev_missing_choice: {offered, rule}`: the missing labels offered as choices and the rule slot(s) giving their meaning (RC-D-005 12 a). An offered label needs its rule (check 1); the generated question offers exactly the values not flagged `jev_choice: false` plus the offered labels (check 16).
- Generators write the system prompts (`system_prompt.md`) and put the part sentence and the temporary answer in the question file (one copy of the sentence; the temporary answer on every question), so the check-16 part-prompt clause is checked instead of noted.

## A8. Question context (W33) — §2 field 21

An item may carry `question_context: {shows_value_of: [<item id>]}`: the value of the named item for the same row is shown with the question (the scale unit question shows the extracted number). The shown value is data, not wording; the generator passes the key through to the question.
