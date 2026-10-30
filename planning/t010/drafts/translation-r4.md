# T-010 translation table v2.5 ↔ v2.7 (DRAFT, round 4)

Drafted 2026-10-30 by the translation subagent (Claude Code, claude-opus-5-5) for integrator session 20261030-claude-v2-2b8200388885f8f9, PI ruling S1 b. Not folded; for PI review. Codebook read at sha256 `9ddf5a09…2cd8e`.

33 open leaves on 32 items. Cells: 49 mapped, 38 not mappable; 16 rest on no ruling (marked **no source**).

## Missing labels (every coded item)

- `_NA_` → `_NA_` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §3.2 Group D rule
- `unknown` → `unknown` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §6 check 2
- `not_documented` → `unknown` — medium · **no source**; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.3-4.5 ('unknown: cannot determine'); §6 check 2; The old columns had no 'not documented' (except the safeguard items), so 'unknown' covered silent pages too. Alternative: leave it unmapped.
- `not_asked` → `not asked (shown with a version label)` — high; SPEC R-051; codebook-review/codebook-rulings-round2.json n=46

## Page verdict (`core.page_verdict` ← v2.5 `genai_evidence`; leaves: map, unmappable)

The old four-value evidence column becomes the nine-value page verdict.

Default value: `{"map": {"confirms_activity": "confirms_activity", "ambiguous_genai": "ambiguous", "ambiguous_attribution": "ambiguous", "background_only": "background_only", "confirms_absence": "confirms_absence", "no_genai": "confirms_absence"}, "unmappable": ["other_body", "event_only", "not_assessable"]}`

New → old:
- `confirms_activity` → `confirms_activity` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.7; SPEC R-015
- `ambiguous_genai` → `ambiguous` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.7 'Source mentions AI but unclear whether generative AI'
- `ambiguous_attribution` → `ambiguous` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.7 '...or mentions GenAI but unclear whether this institution is involved'; §4.2 country-wide rule
- `background_only` → `background_only` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.7
- `confirms_absence` → `confirms_absence` — high; SPEC R-015 ('v2.5 confirms_absence')
- `no_genai` → `confirms_absence` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.7 defines confirms_absence as 'The supplied page text contains no GenAI evidence relevant to this institution', the v2.7 no_genai meaning; Both v2.7 values collapse into the old absence code.
- `other_body` → not mappable — medium · **no source**; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md has no other-body value; codebook-review/codebook-rulings-round1.json C04 (attribution rule); Old rules sent such pages to 'ambiguous' or 'background only' depending on the reading; no fixed choice.
- `event_only` → not mappable — medium · **no source**; codebook rule core.rule.ws10_event (event rule new in v2.7); Old rules could code an event page as an activity or as background; no fixed choice.
- `not_assessable` → not mappable — high; SPEC R-015 (set mechanically when a page was not reviewed); G3O 375f1ff g3o/common/contract.py L169 (four values); The old version wrote no row for an unreviewed page.

Old → new:
- `confirms_activity` → `confirms_activity` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.7; Old positives may include pages v2.7 codes as event only or other body.
- `ambiguous` → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.7; Splits into the two v2.7 ambiguous values; the old row does not say which.
- `background_only` → `background_only` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.7; May include pages v2.7 codes as other body.
- `confirms_absence` → not mappable — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.7; SPEC R-015; The old meaning is v2.7 'no GenAI', but a page stating absence also took it.

New in v2.7, no old counterpart: other_body, event_only, not_assessable

Old rows stay unconverted (SPEC R-015); the reverse column is for reading old rows only.

## Source type (`core.source_type` ← v2.5 `source_type`; leaves: map)

Same codes and definitions; two old codes are now set automatically.

Default value: `{"map": {"news_major": "news_major", "news_trade": "news_trade", "vendor": "vendor", "academic": "academic", "policy_org": "policy_org", "social_media": "social_media", "procurement_tender": "procurement_tender", "other": "other"}}`

New → old:
- `news_major` → `news_major` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6; codebook value texts copy it
- `news_trade` → `news_trade` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6; codebook value texts copy it
- `vendor` → `vendor` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6; codebook value texts copy it
- `academic` → `academic` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6; codebook value texts copy it
- `policy_org` → `policy_org` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6; codebook value texts copy it
- `social_media` → `social_media` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6; codebook value texts copy it
- `procurement_tender` → `procurement_tender` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6; codebook value texts copy it
- `other` → `other` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6; codebook value texts copy it

Old → new:
- `news_major` → `news_major` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6
- `news_trade` → `news_trade` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6
- `vendor` → `vendor` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6
- `academic` → `academic` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6
- `policy_org` → `policy_org` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6
- `social_media` → `social_media` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6
- `procurement_tender` → `procurement_tender` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6
- `other` → `other` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.6
- `official_gov` → `official_gov (set from the domain field)` — medium; codebook.yaml (approved final draft, sha256 9ddf5a09) source_type rule 1 (r2#25); Not a classifier value in v2.7; pages typed from the domain keep the code in the same column.
- `archive` → `archive (set from the address)` — medium; codebook.yaml (approved final draft, sha256 9ddf5a09) source_type rule 1 (r2#25); Not a classifier value in v2.7; pages typed from the address keep the code in the same column.

'Other' no longer carries an explanation in the snippet, since snippets are now verbatim only.

## Source title (`core.source_title` ← v2.5 `source_title`; leaves: map)

Same text column; v2.7 takes the title from the page instead of the model.

Default value: `{"map": "identity"}`

New → old:
- (title text) → (same text) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 30; codebook.yaml (approved final draft, sha256 9ddf5a09) source_title rule; Method change: model-written 'as it appears' in v2.5, page title or first heading in v2.7.

Old → new:
- (title text) → (same text) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 30

## Source language (`core.source_language` ← v2.5 `source_language`; leaves: map)

Two-letter language tags carry over; tags the old column could not hold do not.

Default value: `{"map": {"<two-letter tag>": "<same tag>"}, "unmappable": ["<tag with a script subtag>", "<three-letter tag>", "mul"]}`

New → old:
- <two-letter tag> → <same tag> — high; G3O 375f1ff g3o/common/contract.py L104 LANG_PATTERN '^[a-z]{2}$'; codebook.yaml (approved final draft, sha256 9ddf5a09) source_language rule
- <tag with a script subtag> (e.g. uz-latn) → not mappable — high; G3O 375f1ff g3o/common/contract.py L104 vs L113 LANGS_PATTERN; Not stripped to the base tag: the script was ruled a different search instrument (contract.py L110).
- <three-letter tag> → not mappable — high; G3O 375f1ff g3o/common/contract.py L104
- `mul` → not mappable — high; codebook.yaml (approved final draft, sha256 9ddf5a09) source_language rule ('mul' when no language exceeds a set share)

Old → new:
- <two-letter tag> → <same tag> — high; G3O 375f1ff g3o/common/contract.py L104; Old tags were judged by the model; v2.7 uses a pinned language-ID library.

New in v2.7, no old counterpart: script-subtag tags, three-letter tags, mul

## Supporting snippet (`core.source_snippet` ← v2.5 `source_snippet`; leaves: map)

Same text column; old snippets may be paraphrased or translated.

Default value: `{"map": "identity"}`

New → old:
- (verbatim supporting text) → (same text) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 37; codebook.yaml (approved final draft, sha256 9ddf5a09) source_snippet rules (verbatim only, r2#35)

Old → new:
- (snippet text) → (same text, labelled) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 37; Old snippets could be a close paraphrase or an English translation with the original in brackets; they are not all verbatim.

## Source credibility (`core.source_credibility` ← v2.5 `source_credibility`; leaves: map)

Same three codes on the same ladder; v2.7 sets them by a fixed rule.

Default value: `{"map": {"high": "high", "medium": "medium", "low": "low"}}`

New → old:
- `high` → `high` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.8; codebook.yaml (approved final draft, sha256 9ddf5a09) source_credibility rule
- `medium` → `medium` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.8; codebook.yaml (approved final draft, sha256 9ddf5a09) source_credibility rule
- `low` → `low` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.8; codebook.yaml (approved final draft, sha256 9ddf5a09) source_credibility rule

Old → new:
- `high` → `high` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.8
- `medium` → `medium` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.8
- `low` → `low` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.8

v2.5: the model applied a hierarchy; v2.7: a fixed map from source type, plus 'low' when the publication date is unknown.

## Adoption stage (`core.adoption_stage` ← v2.5 `adoption_stage`; leaves: map)

Same five stages, same definitions.

Default value: `{"map": {"proposed": "proposed", "announced": "announced", "pilot": "pilot", "production": "production", "discontinued": "discontinued"}}`

New → old:
- `proposed` → `proposed` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.3; codebook value texts copy it
- `announced` → `announced` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.3; codebook value texts copy it
- `pilot` → `pilot` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.3; codebook value texts copy it
- `production` → `production` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.3; codebook value texts copy it
- `discontinued` → `discontinued` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.3; codebook value texts copy it

Old → new:
- `proposed` → `proposed` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.3
- `announced` → `announced` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.3
- `pilot` → `pilot` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.3
- `production` → `production` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.3
- `discontinued` → `discontinued` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.3

Series break: a purchase record without shown use is 'unknown' in v2.7 (its purchase status says what was bought); v2.5 may have given it a stage.

## Model origin (`core.model_origin` ← v2.5 `access_type`; leaves: map)

The old access-type column is split into model origin and build arrangement; the crosswalk is partial.

Default value: `{"map": {"commercial": "proprietary_vendor", "open_weight": "open_source"}, "unmappable": ["government_developed"], "condition": "When build arrangement is model_trained_or_fine_tuned_by_institution, the old column is not filled (old rules would give mixed or in_house)."}`

New → old:
- `commercial` → `proprietary_vendor` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4 (same examples: OpenAI, Microsoft, Google, Anthropic)
- `open_weight` → `open_source` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4 (same examples: Llama, Mistral, Falcon)
- `government_developed` → not mappable — medium · **no source**; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4 sovereign_model and in_house; codebook.yaml (approved final draft, sha256 9ddf5a09) government_developed definition; The v2.7 value covers both old 'sovereign model' and old 'in house'.
- (any origin) with build arrangement = trained or fine-tuned by the institution → not mappable — medium · **no source**; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4 mixed example 'proprietary API fine-tuned in-house'; The old column would say 'mixed' or 'in house', not the origin.

Old → new:
- `proprietary_vendor` → `commercial` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4
- `open_source` → `open_weight` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4
- `sovereign_model` → `government_developed` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4; codebook.yaml (approved final draft, sha256 9ddf5a09) (same examples: Albert, OpenGPT-X)
- `in_house` → `government_developed` — medium; codebook.yaml (approved final draft, sha256 9ddf5a09) government_developed ('including by the institution's own team')
- `mixed` → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4
- `unknown` → `unknown` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4

Condition: When build arrangement is model_trained_or_fine_tuned_by_institution, the old column is not filled (old rules would give mixed or in_house).

Round 1 recorded that this split breaks the series and the crosswalk is only partial.

## Build arrangement (`core.build_arrangement` ← v2.5 `access_type`; leaves: map)

New dimension; nothing in v2.7 fills the old column from it.

Default value: `{"map": {}, "unmappable": ["off_the_shelf_product", "custom_application_on_external_model", "model_trained_or_fine_tuned_by_institution"]}`

New → old:
- `off_the_shelf_product` → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4 (no build dimension); codebook-review/codebook-rulings-round1.json C10
- `custom_application_on_external_model` → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4 (no build dimension); codebook-review/codebook-rulings-round1.json C10
- `model_trained_or_fine_tuned_by_institution` → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4 (no build dimension); codebook-review/codebook-rulings-round1.json C10

Old → new:
- `in_house` → `model_trained_or_fine_tuned_by_institution` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4 'Built by the institution's own team, not based on a major external foundation model'
- `mixed` → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4
- (other old codes) → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.4; The old code says nothing about how the tool was built.

New in v2.7, no old counterpart: off_the_shelf_product, custom_application_on_external_model, model_trained_or_fine_tuned_by_institution

## Interface (`core.interface` ← v2.5 `interaction_type`; leaves: map)

Ruled in round 2: the old interaction-type column has no fixed mapping and shows 'not asked' on v2.7 rows.

Default value: `{"map": {}, "unmappable": ["conversational", "backend_or_api", "other_interface"]}`

New → old:
- `conversational` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); SPEC R-051
- `backend_or_api` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); SPEC R-051
- `other_interface` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); SPEC R-051

Old → new:
- `chatbot` → `conversational` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 ('Conversational interface for Q&A, navigation, or retrieval')
- `not_applicable` → `not_asked` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 (policy activities with no tool); codebook applicability table (policy_guidance: not asked)
- `unknown` → `unknown` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5
- (other old codes) → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5; They name a function, not how users reach the tool.

New in v2.7, no old counterpart: conversational, backend_or_api, other_interface

## Function: drafting and writing (`core.function_drafting_writing` ← v2.5 `interaction_type`; leaves: map)

The old single 'primary mode' column cannot be filled from a set of yes/no functions (round 2).

Default value: `{"map": {}, "unmappable": ["yes", "no"]}`

New → old:
- `yes` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11
- `no` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11

Old → new:
- (no single old code) → not mappable — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5; Old 'content creation' and 'document processing' each mix drafting with other functions.
- (any other old code) → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 ('Primary mode of human-AI interaction'); Never 'no': the old column recorded only the primary mode.

## Function: summarising (`core.function_summarization` ← v2.5 `interaction_type`; leaves: map)

The old single 'primary mode' column cannot be filled from a set of yes/no functions (round 2).

Default value: `{"map": {}, "unmappable": ["yes", "no"]}`

New → old:
- `yes` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11
- `no` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11

Old → new:
- (no single old code) → not mappable — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5; Old 'document processing' mixes summarising, extraction, classification and generation.
- (any other old code) → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 ('Primary mode of human-AI interaction'); Never 'no': the old column recorded only the primary mode.

## Function: translation (`core.function_translation` ← v2.5 `interaction_type`; leaves: map)

The old single 'primary mode' column cannot be filled from a set of yes/no functions (round 2).

Default value: `{"map": {}, "unmappable": ["yes", "no"]}`

New → old:
- `yes` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11
- `no` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11

Old → new:
- `translation` → `yes` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 (same definition)
- (any other old code) → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 ('Primary mode of human-AI interaction'); Never 'no': the old column recorded only the primary mode.

## Function: search and retrieval (`core.function_search_retrieval` ← v2.5 `interaction_type`; leaves: map)

The old single 'primary mode' column cannot be filled from a set of yes/no functions (round 2).

Default value: `{"map": {}, "unmappable": ["yes", "no"]}`

New → old:
- `yes` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11
- `no` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11

Old → new:
- `search_retrieval` → `yes` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 (same definition)
- (any other old code) → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 ('Primary mode of human-AI interaction'); Never 'no': the old column recorded only the primary mode.

## Function: code (`core.function_code` ← v2.5 `interaction_type`; leaves: map)

The old single 'primary mode' column cannot be filled from a set of yes/no functions (round 2).

Default value: `{"map": {}, "unmappable": ["yes", "no"]}`

New → old:
- `yes` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11
- `no` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11

Old → new:
- `code_generation` → `yes` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 (same definition)
- (any other old code) → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 ('Primary mode of human-AI interaction'); Never 'no': the old column recorded only the primary mode.

## Function: images, audio and video (`core.function_image_audio_video` ← v2.5 `interaction_type`; leaves: map)

The old single 'primary mode' column cannot be filled from a set of yes/no functions (round 2).

Default value: `{"map": {}, "unmappable": ["yes", "no"]}`

New → old:
- `yes` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11
- `no` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11

Old → new:
- (no single old code) → not mappable — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5; Old 'content creation' mixes text and multimedia.
- (any other old code) → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 ('Primary mode of human-AI interaction'); Never 'no': the old column recorded only the primary mode.

## Function: extraction and classification (`core.function_extraction_classification` ← v2.5 `interaction_type`; leaves: map)

The old single 'primary mode' column cannot be filled from a set of yes/no functions (round 2).

Default value: `{"map": {}, "unmappable": ["yes", "no"]}`

New → old:
- `yes` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11
- `no` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11

Old → new:
- (no single old code) → not mappable — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5; Old 'document processing' mixes several functions.
- (any other old code) → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 ('Primary mode of human-AI interaction'); Never 'no': the old column recorded only the primary mode.

## Function: analysis and recommendation (`core.function_analysis_recommendation` ← v2.5 `interaction_type`; leaves: map)

The old single 'primary mode' column cannot be filled from a set of yes/no functions (round 2).

Default value: `{"map": {}, "unmappable": ["yes", "no"]}`

New → old:
- `yes` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11
- `no` → not mappable — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); codebook-review/codebook-rulings-round1.json C11

Old → new:
- `decision_support` → `yes` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 (same definition)
- (any other old code) → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.5 ('Primary mode of human-AI interaction'); Never 'no': the old column recorded only the primary mode.

## Contracting party (`core.contracting_party` ← v2.5 `vendor`; leaves: map)

Not used to fill the old vendor column.

Default value: `{"map": {}, "unmappable": ["(contracting party text)"]}`

New → old:
- (contracting party text) → not mappable — medium · **no source**; codebook-review/codebook-rulings-round1.json C13 (old vendor = the supplier of the product); codebook.yaml (approved final draft, sha256 9ddf5a09) contracting_party rule 2 ('in purchase records is the contracting party'); The two rulings read the old vendor column differently; filling it from the contracting party could mix two meanings.

Old → new:
- (vendor text) → not mappable — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 17; Old rows do not say whether the vendor was the contracting party.

New in v2.7, no old counterpart: contracting party

## Developer (`core.developer` ← v2.5 `vendor`; leaves: map)

The old vendor column takes the developer the page names; a developer found by lookup does not fill it.

Default value: `{"map": {"(developer text, basis stated)": "(same text)"}, "unmappable": ["(developer text, basis lookup)"]}`

New → old:
- (developer text, basis stated) → (same text) — medium; codebook.yaml (approved final draft, sha256 9ddf5a09) developer rule 2 (= the round-1 vendor definition)
- (developer text, basis lookup) → not mappable — high; codebook.yaml (approved final draft, sha256 9ddf5a09) contracting_party rule 2 ('the lookup stops filling vendor')

Old → new:
- (vendor text) → (developer text, basis stated) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 17 ('Vendor or provider. For in-house tools: the institution or its parent agency')
- `unknown` → `unknown` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 17

New in v2.7, no old counterpart: developer found by lookup

## Deployment mode (`core.deployment_mode` ← v2.5 `deployment_mode`; leaves: map)

Same two codes, same definitions.

Default value: `{"map": {"integrated": "integrated", "standalone": "standalone"}}`

New → old:
- `integrated` → `integrated` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 18; codebook.yaml (approved final draft, sha256 9ddf5a09) deployment_mode instruction
- `standalone` → `standalone` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 18; codebook.yaml (approved final draft, sha256 9ddf5a09) deployment_mode instruction

Old → new:
- `integrated` → `integrated` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 18
- `standalone` → `standalone` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 18
- `unknown` → `unknown` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 18

## Year the pilot started (`core.year_pilot_start` ← v2.5 `year_deployed`; leaves: map)

Ruled in round 2: the old deployment year is the earlier of the pilot and production years.

Default value: `{"map": {"rule": "year_deployed = the earlier of year_pilot_start and year_production_start; if only one is a year, that year; if neither, unknown"}}`

New → old:
- (year) → `earlier of the two years` — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); SPEC R-051
- (only one of the two is a year) → `that year` — medium; codebook-review/codebook-rulings-round2.json n=46 (reading of 'the earlier of')
- (neither is a year) → `unknown` — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 21

Old → new:
- (year) → not mappable — high; codebook-review/codebook-rulings-round1.json C17 (split); The old year does not say whether it was a pilot or a production start.

For governance activities both years are 'not asked'; the old column then shows 'not asked' with a version label.

## Year production started (`core.year_production_start` ← v2.5 `year_deployed`; leaves: map)

Same rule as the pilot year: the old deployment year is the earlier of the two.

Default value: `{"map": {"rule": "year_deployed = the earlier of year_pilot_start and year_production_start; if only one is a year, that year; if neither, unknown"}}`

New → old:
- (year) → `earlier of the two years` — high; codebook-review/codebook-rulings-round2.json n=46 (R2P22); SPEC R-051

Old → new:
- (year) → not mappable — high; codebook-review/codebook-rulings-round1.json C17 (split); The old year does not say whether it was a pilot or a production start.

## Kind of outcome reported (`core.outcome_kind` ← v2.5 `reported_outcomes`; leaves: map)

'None reported' carries over; otherwise the old text column takes the quoted outcome text.

Default value: `{"map": {"none_reported": "none_reported"}, "via": {"quantified": "core.reported_outcomes", "qualitative": "core.reported_outcomes"}}`

New → old:
- `none_reported` → `none_reported` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 26
- `quantified` → (the quoted outcome text) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 26 (a text column); codebook.yaml (approved final draft, sha256 9ddf5a09) reported_outcomes; The kind itself has no old code.
- `qualitative` → (the quoted outcome text) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 26; codebook.yaml (approved final draft, sha256 9ddf5a09) reported_outcomes; The kind itself has no old code.

Old → new:
- `none_reported (and other 'nothing found' spellings)` → `none_reported` — high; codebook.yaml (approved final draft, sha256 9ddf5a09) reported_outcomes rule 1 (legacy normalisation)
- (outcome text) → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 26; Whether it was measured or described needs a reading of the text.

New in v2.7, no old counterpart: quantified, qualitative

## Kind of incident reported (`core.incident_kind` ← v2.5 `reported_incidents`; leaves: map)

As for outcomes; the new 'possibly discontinued' value goes to the old uncertainty flag, not to this column.

Default value: `{"map": {"none_reported": "none_reported"}, "unmappable": ["discontinuation_uncertain"], "via": {"quantified": "core.reported_incidents", "qualitative": "core.reported_incidents"}}`

New → old:
- `none_reported` → `none_reported` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 27
- `quantified` → (the quoted incident text) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 27; codebook.yaml (approved final draft, sha256 9ddf5a09) reported_incidents
- `qualitative` → (the quoted incident text) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 27; codebook.yaml (approved final draft, sha256 9ddf5a09) reported_incidents
- `discontinuation_uncertain` → not mappable — medium · **no source**; codebook-review/codebook-rulings-round2.json n=38 (folded from the old flag); codebook.yaml (approved final draft, sha256 9ddf5a09) incident_kind rule 'ignores stops unless a problem is reported'; Not written to the old incident column (neither 'none reported' nor text); it sets the old flag 'discontinued uncertain' instead.

Old → new:
- `none_reported (and other 'nothing found' spellings)` → `none_reported` — high; codebook.yaml (approved final draft, sha256 9ddf5a09) reported_incidents rule 1
- (incident text) → not mappable — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 27; Whether it was measured or described needs a reading.

New in v2.7, no old counterpart: quantified, qualitative, discontinuation_uncertain

## Reported outcomes (quoted text) (`core.reported_outcomes` ← v2.5 `reported_outcomes`; leaves: map)

The quoted outcome passages fill the old text column, joined, in full.

Default value: `{"map": {"rule": "the verbatim spans joined with ' | ', in full; 'none_reported' when the outcome kind is none_reported"}}`

New → old:
- (verbatim spans) → (spans joined with ' | ', in full) — medium · **no source**; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 26; SPEC R-043 (full text in the API); The separator and dropping the old 200-character limit are choices; the alternative is to cut at 200 characters as before.

Old → new:
- (outcome text) → (one span) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 26; Old text was not required to be verbatim.

## Reported incidents (quoted text) (`core.reported_incidents` ← v2.5 `reported_incidents`; leaves: map)

The quoted incident passages fill the old text column, joined, in full.

Default value: `{"map": {"rule": "the verbatim spans joined with ' | ', in full; 'none_reported' when the incident kind is none_reported"}}`

New → old:
- (verbatim spans) → (spans joined with ' | ', in full) — medium · **no source**; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 27; SPEC R-043; As for outcomes: separator and length are choices.

Old → new:
- (incident text) → (one span) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 27; Old text was not required to be verbatim.

## Uncertainty flags (`core.uncertainty_flags` ← v2.5 `uncertainty_flags`; leaves: map)

Two kept flags carry over; retired flags are not recomputed for the old column.

Default value: `{"map": {"stage_ambiguous": "stage_ambiguous", "incident_kind = discontinuation_uncertain": "discontinued_uncertain"}, "unmappable": ["identity_unresolved"]}`

New → old:
- `stage_ambiguous` → `stage_ambiguous` — high; codebook-review/codebook-rulings-round2.json n=38 (kept)
- (incident kind = possibly discontinued) → `discontinued_uncertain` — high; codebook-review/codebook-rulings-round2.json n=38 (folded into the incident question); respelling all-11
- `identity_unresolved` → not mappable — high; codebook-review/codebook-rulings-round2.json n=38; codebook-review/codebook-rulings-round1.json X24 (new, for consolidation links)
- (retired old flags) → not mappable — medium · **no source**; codebook-review/codebook-rulings-round2.json n=38 (retire flags that mirror a column); codebook-review/codebook-rulings-round1.json X24 ('compute each flag from codes'); Round 1 said flags are computed from codes, round 2 retired the ones that mirror a column. Default: not recomputed; the mirrored columns carry the information.

Old → new:
- `stage_ambiguous` → `stage_ambiguous` — high; codebook-review/codebook-rulings-round2.json n=38
- `discontinued_uncertain` → `incident kind: discontinuation_uncertain` — high; codebook-review/codebook-rulings-round2.json n=38
- `genai_vs_traditional_ai` → (reads as page verdict: ambiguous_genai) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.10; codebook-review/codebook-rulings-round2.json n=38
- `institution_attribution` → (reads as page verdict: ambiguous_attribution) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.10; codebook-review/codebook-rulings-round2.json n=38
- `date_uncertain` → (reads as year: unknown) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.10; codebook-review/codebook-rulings-round2.json n=38
- `vendor_undisclosed` → (reads as developer: not documented) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.10; codebook-review/codebook-rulings-round2.json n=38
- `scope_unclear` → (reads as target users: unknown) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.10; codebook-review/codebook-rulings-round2.json n=38
- `source_language_barrier` → not mappable — high; codebook-review/codebook-rulings-round2.json n=39 (dropped everywhere)

New in v2.7, no old counterpart: identity_unresolved

## Institution has GenAI activity (`core.has_genai_activity` ← v2.5 `has_genai_activity`; leaves: map)

Same three codes; v2.7's 'no' is stricter, and old 'no' results are labelled as produced by the old rule.

Default value: `{"map": {"yes": "yes", "no": "no", "unclear": "unclear"}}`

New → old:
- `yes` → `yes` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.1; codebook.yaml (approved final draft, sha256 9ddf5a09) has_genai_activity rules
- `no` → `no` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.1; codebook.yaml (approved final draft, sha256 9ddf5a09) has_genai_activity rules
- `unclear` → `unclear` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.1; codebook.yaml (approved final draft, sha256 9ddf5a09) has_genai_activity rules

Old → new:
- `yes` → `yes` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.1
- `unclear` → `unclear` — high; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.1
- `no` → `no (labelled: produced by the v2.5 rule)` — high; codebook-review/codebook-rulings-round2.json n=45 (R2P21); SPEC R-059 (verdict_rule)

## Confidence (`core.confidence` ← v2.5 `confidence`; leaves: map)

Same three codes, but a different rule and level; not carried over by default.

Default value: `{"map": {}, "unmappable": ["high", "medium", "low"]}`

New → old:
- `high` → not mappable — medium · **no source**; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.9 (model's confidence in the row's coded values); codebook.yaml (approved final draft, sha256 9ddf5a09) confidence rule (per source from credibility and quote support; per activity by consolidation); The codes match but the measure changed; the alternative is to carry the codes with a version label.
- `medium` → not mappable — medium · **no source**; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.9 (model's confidence in the row's coded values); codebook.yaml (approved final draft, sha256 9ddf5a09) confidence rule (per source from credibility and quote support; per activity by consolidation); The codes match but the measure changed; the alternative is to carry the codes with a version label.
- `low` → not mappable — medium · **no source**; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.9 (model's confidence in the row's coded values); codebook.yaml (approved final draft, sha256 9ddf5a09) confidence rule (per source from credibility and quote support; per activity by consolidation); The codes match but the measure changed; the alternative is to carry the codes with a version label.

Old → new:
- `high` → not mappable — medium · **no source**; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.9; Different measure.
- `medium` → not mappable — medium · **no source**; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.9; Different measure.
- `low` → not mappable — medium · **no source**; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md §4.9; Different measure.

## Institution summary (`core.institution_summary` ← v2.5 `institution_summary`; leaves: map)

Same text column; v2.7 writes it from the codes instead of the model.

Default value: `{"map": "identity"}`

New → old:
- (summary text) → (same text) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 9; codebook.yaml (approved final draft, sha256 9ddf5a09) institution_summary rule

Old → new:
- (summary text) → (same text, labelled) — medium; v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md col 9

## Codebook release (`core.codebook_release` ← v2.5 `contract_version`; leaves: map)

The old version column holds the codebook release label on v2.7 rows; old rows keep theirs.

Default value: `{"map": {"(codebook release label)": "(same label in contract_version)"}}`

New → old:
- (codebook release label, e.g. 2.7) → (same label) — high; SPEC R-050 (the codebook release replaces contract_version)

Old → new:
- (old contract version, e.g. v2.5) → (kept as is) — high; SPEC R-050 ('v2.5 rows keep their contract version')
