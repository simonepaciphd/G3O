# Codebook item template and generator checks (r2#59)

Status: APPROVED 2026-10-30 with delta RC-D-003 (PI, chat, "all accepted"; RC-D-003 §14), as amended there. Drafted 2026-10-29 by the plan integrator (session `20261029-claude-v2-b92f4144070ec139`, claude-opus-5-5, researcher persona).
PI rulings, 2026-10-29, chat, verbatim: "1 a 2 a as long as when the codebook is procedurally loaded into a prompt the rules are filled out so that each value's definition has the full set of rules (even if repeated)". 1 a: fields 11, 12, 14, 26 and 27 (marked †) are their own fields. 2 a: one rule slot per item (field 14), with the condition applied as generator check 16. T-013 builds against this approved template (T-013 inputs; RC-D-002 O3).
Sources: SPEC v001.7 R-007, A-001, C-007; RC-D-002 A, J, L; RC-D-003 §14; round-2 rulings r2#5, 16, 26, 28, 29, 40, 41, 42, 48, 54, 57, 59, 60.

## 1. File layout

One file, `codebook/codebook.yaml`, with three top-level keys:

- `release` — release label (C-007 / r2#5: one version for the whole codebook), status (`draft` | `signed`), signature record pointer, hash rule (A-001: sha256 of the file bytes at sign-off, after the slot markers are removed, P4).
- `vocabularies` — lists shared by several items, defined once and referenced by name:
  - `missing` — `not_asked`, `not_documented`, `unknown` (r2#16), `_NA_` for items on a row with no activity (all-01 b; RC-D-003 §1);
  - `provenance` — the five "how we know" values (r2#57);
  - `support_status` — quote-support values (R-041, r2#37/53, r2#40);
  - `relation` — activity link values (r2#22);
  - `pipeline` — `web_extract`, `stage6`, `procurement`, `ai_text`;
  - `level` — `institution`, `page`, `activity`, `source`, `contract`, `document`, `row`, `run`.
- `shared_rules` — rule texts that several items use (for example the generative-AI boundary), each a signed text slot defined once with an id; items list them in `rules` by id.
- `items` — one entry per codebook item, keyed by `id`, in the fields of section 2.

## 2. Item fields

Every item fills every field. A field that does not apply holds an explicit `none`, never a blank. Fields marked † are not in the r2#59 list; the PI added them (ruling 1 a).

| # | Field | r2#59 term | Content | Allowed form |
|---|---|---|---|---|
| 1 | `id` | id | Stable identifier, `<namespace>.<name>` | e.g. `core.page_verdict`; never reused or renamed after a signed release |
| 2 | `family` | family | Item family | free label from a fixed list in `vocabularies` (e.g. `verdict`, `activity_typing`, `safeguard`, `disclosure`, `source`, `provenance`, `quality`) |
| 3 | `name` | name | Column name in the output data | snake_case |
| 4 | `level` | level | Unit the value describes; r2#29 level tags | one or more of `vocabularies.level` |
| 5 | `pipelines` | (coverage tag, R-007) | Pipelines that code the item; r2#54 exemptions | one or more of `vocabularies.pipeline` |
| 6 | `linkage` | (RC-D-002 A) | How the value is produced in code | `jev_choice` / `deterministic` / `extractor` / `pipeline` |
| 7 | `coder` | coder | Who fills it (r2#28) | `classifier` / `mechanical` / `quote_step` / `derived` |
| 8 | `pass` | pass | Classifier pass | `1` (page) / `2` (activity) / `stage6` / `none` |
| 9 | `round` | round | Order within the pass (r2#41: gate items first) | integer ≥ 1, or `none` |
| 10 | `gate` | gate | Condition for asking the item | `none`, or item id + list of values that open it; gated-out rows take `not_asked` unless the gate names another gated-out value (e.g. `no`, page-09 c; RC-D-003 §9) |
| 11 | `answer_type` † | — | Shape of the answer | `single` / `multi` (S6 c) / `yes_no` / `text` / `number` / `date` / `list` |
| 12 | `instruction` † | (signed wording) | The question or extraction instruction | signed text slot (section 3) |
| 13 | `values` | values with definitions | Ordered list of `{code, definition}` | each `definition` is a signed text slot; `none` for `text`/`number`/`date` items |
| 14 | `rules` † | (signed wording) | Coding rule prose beyond the value definitions (ruling 2 a) | list of signed text slots and references to shared rules (section 1), or `none` |
| 15 | `order_tie_rule` | order and tie rule | What to do when several values fit | `first_in_order` / `single_best` / `all_that_apply` / `none` |
| 16 | `long_page_rule` | long-page rule | How answers on page parts combine (r2#42; S3 a for the verdict) | `first_section` / `any_yes` / `priority_order` / `earliest_year` / `combined_list` / `highest_probability` / `none`; `priority_order` names its order; a rule may end with a mapping step to one value (activity-11 a, 22 b); the verdict order has two tiers, supported then failed (page-02 b) (RC-D-003 §3) |
| 17 | `support_required` | whether support is required | A supporting quote must exist (R-040) | `true` / `false` |
| 18 | `downgrade_target` | downgrade target | What happens when support or confidence fails (R-041, r2#40) | a value code, `unknown`, `tag_only` (verdict kept, support status tagged), or `none` |
| 19 | `threshold` | threshold metric | Confidence bar (r2#26) | `{metric: chosen_answer_probability, bar: 0.8}`, or `none` for non-classifier items |
| 20 | `missing_tokens` | missing-value tokens | Missing labels the item can take | subset of `vocabularies.missing`; frozen items add `missing_map` from their signed spellings (r2#16) |
| 21 | `input_text` | input text | Text the coder reads (r2#48) | `main` / `main_plus_chrome` / `links` / `quote_source` / `metadata` |
| 22 | `visibility` | public or internal | Publication (r2#60; S4 a, A05) | `public` / `internal` / `public_derived` (e.g. e-mail domain and count only) |
| 23 | `frozen_signature` | frozen signature id | Signed questionnaire row | e.g. `CX-01.3:CX-10`, or `none` |
| 24 | `version_introduced` | version introduced | Release in which the item first appears | release label |
| 25 | `translation_v25` | translation to current production | Map to v2.5 (r2#43, r2#46) | `{column, map: {v2.7 code: v2.5 code}, unmappable: [...]}`, or `new` |
| 26 | `refs` † | — | SPEC rows and rulings behind the item | list of R-ids, ruling ids (C01, r2#7, …) |
| 27 | `status` † | — | Wording state | `slot` / `pi_edited` / `signed` |

## 3. Signed text slots

Fields 12, 13 (`definition`) and 14, and each entry in `shared_rules`, are text slots. Each slot holds:

```yaml
text: |
  <verbatim text>
origin: spec | ruling | cx-01.2 | repilot2 | v2.5 | pi
marker: "SPEC text — PI to write or line-edit"   # removed at sign-off (P4)
```

- Seeded verbatim from the SPEC wording (ruling 1 a), a signed ruling option, CX-01.2 (P3, byte-identical) or re-pilot 2 (`unclear2.py` L32-54, P3).
- v2.5 text that a v2.7 rule overrides stays with the marker "v2.5 text — affected by R-0xx; PI to rewrite or delete" (P2).
- The integrator writes no rule prose. Only the PI changes `text`.

## 4. Generator checks (CI; T-013 implements)

1. **Template complete.** Every item has all 27 fields; values come from the allowed forms above; no blanks.
2. **IDs stable.** IDs are unique. An ID in a signed release never disappears or changes meaning in a later release without a retirement entry.
3. **Verbatim only.** Every slot `text` appears byte-identical in each generated file that uses it. Generators add only fixed scaffolding (headings, item ids, hashes, numbering); a declared escaping step is the only transformation.
4. **Frozen items.** An item with `frozen_signature` matches the hash in its signature record; any change to its text fails until it is re-signed.
5. **No drift.** Regenerating from the codebook reproduces every committed generated file byte for byte; CI fails on any difference.
6. **Linkage (A-001).** Each generated question, prompt section and enum carries its item id and the item's hash. Each `jev_choice` item yields exactly one question; each `extractor` item exactly one prompt section; nothing is generated without an item.
7. **Gates.** A gate names an existing item and existing values; gates have no cycles; a gated item's round is later than its gate's round in the same or an earlier pass.
8. **Values.** Codes are unique and snake_case within an item and never equal a missing token (frozen items exempt through `missing_map`).
9. **Coder fits fields.** `classifier` items have an instruction, value definitions and a threshold; `mechanical` and `derived` items have `rules` and no threshold; `quote_step` items set `support_required`.
10. **Long pages.** Every page-level classifier item declares a long-page rule other than `none`; `priority_order` lists its order.
11. **Coverage.** Each item names at least one pipeline; link-following, completeness, link review state and chrome-text items exclude `procurement` (r2#54).
12. **Version steps.** A changed value list against the previous release requires the release label to rise by the two steps C-007 requires (r2#5: counted per release).
13. **Sign-off gate.** A `signed` release build fails if any slot still carries a marker or any item has `status` other than `signed`.
14. **Translation.** Every item with a v2.5 counterpart has a `translation_v25` map; unmappable cells are listed.
15. **Hash.** The release hash is sha256 of the file bytes; every generated file records it in its header.
16. **Full rules beside every value (ruling 2 a condition).** In every generated question and prompt section, each value's definition is followed by the item's full set of rules: its own rule slots and every shared rule it references, expanded verbatim, repeated for each value. The check fails if any value in a generated output lacks any of its item's rules. The data dictionary and `output_contract.md` may state the rules once per item. Every part prompt for a long page also carries the sentence that the text is only part of the document, and every question in it the temporary answer "not covered by this part", which never votes and is never published (all-03 a; RC-D-003 §2).
