# Round-4 default fixes (PROPOSED, pending PI approval)

Claude Code, claude-opus-5-5, round-4 fold subagent (fork) of integrator session 20261030-claude-v2-2b8200388885f8f9. 2026-10-30.

Ruling: PI, chat, 2026-10-30, verbatim: "Reviewed the above; approve all the review items; give a subagent to disambiguate & propose default fixes where necessary. I want a single, clean final draft version of the codebook to look at & approve." (planning/t010/t010-rulings.md)

Each fix has one default (marked). None departs from SPEC v001.7 text, so no delta is drafted.

## FX01. Shared participation: does the link merge the two activities?

The drafted meaning of "shared participation" (within a page and across pages) had no source, and nothing said whether the two passages or records become one activity.

- **a.** They are one activity and merge; the link needs at least two bodies named as taking part, with a quote **(default)**. For: Keeps the version 2.6 rule; no behaviour change. Against: A wrong link merges two activities, which is harder to undo than a link.
- **b.** They stay separate activities, linked only (as program components do). For: Reversible; matches the 'link, never merge' choice for components. Against: Changes version 2.6 behaviour without a ruling; a joint action is then counted twice.
- **c.** Leave the definition as drafted. For: No new text. Against: The merge question stays open for the engineers.

Confidence: medium. SPEC departure: no. Version steps: none (definition text only).
Sources: git 052fcb2:g3o/common/evidence_review.py L218-229 (v2.6: shared_participation keeps one activity id and needs at least two explicitly documented participating actors with a participation quote); SPEC v001.7 R-017 (components are linked, never merged; silent on shared participation).

## FX02. "Not an activity" when links are coded per pair

The value describes one passage, but within-page links are now coded per pair of passages.

- **a.** In a pair, use it when either passage is not an activity; no other link is coded for that pair **(default)**. For: Smallest change; keeps the ruled list and the per-pair coding. Against: The pair does not record which passage was not an activity.
- **b.** Use it only when both passages are not activities. For: Symmetric. Against: Leaves pairs with one non-activity without a fitting link.
- **c.** Move it out of the link list into a per-passage yes/no item. For: Records the passage exactly. Against: A list change and a new item, beyond the rulings.

Confidence: medium. SPEC departure: no. Version steps: none (definition text only).
Sources: SPEC v001.7 R-017 (not-an-activity within a page; links coded per pair of passages).

## FX03. Role values "unit" and "joint" next to the relationship values

The role list of the searched institution has "unit" and "joint", which look like the relationship values "unit of institution" and "joint participant"; no text defined them.

- **a.** No change: keep both roles with the approved definitions **(default)**. For: The round-2 ruling and the approved round-3 option text both list them; the approved definitions describe the searched institution's own part, which the relationship does not. Against: Some combinations read twice (for example joint participant : joint).
- **b.** Drop both roles. For: No overlap. Against: A list change against two rulings that list them.
- **c.** Keep them, allowed only when the relationship is "other". For: Removes the double reading. Against: A new coding rule no ruling supports.

Confidence: low. SPEC departure: no. Version steps: none.
Sources: codebook-rulings-round2.json (observed_actor_relationship rules[1]: contracting authority, beneficiary, central purchasing body, unit, joint); questions-r3.json activity-14 b option text (approved round-3 slot, same list).

## FX04. Which observed-actor roles count as taking part

The six roles of the observed actor came only as code names. The approved definitions read the names; the ruling says "code it as before", and version 2.6 also said which roles count as taking part.

- **a.** Keep the approved definitions and add the version 2.6 rule on which roles count as taking part **(default)**. For: Carries over the 'as before' behaviour the ruling asks for. Against: Adds a rule sentence you have not seen yet.
- **b.** Keep the approved definitions only. For: No new text. Against: The internal item loses the one rule version 2.6 attached to it.

Confidence: medium. SPEC departure: no. Version steps: none (rule text only).
Sources: git 052fcb2:g3o/common/evidence_review.py L44-47 (role list), L93-97 and L218-222 (only institutional_actor, issuer and participant count as documented participation); questions-r3.json activity-15 a ("Code it as before; not published.").

## FX05. The second reason can only be low certainty

Under the approved check order (quote first, then the 0.8 bar), a failed quote check is always the main reason, so only "low certainty" can be a second reason; two of the three approved codes never occur.

- **a.** Keep the three approved codes and say that only low certainty can occur as a second reason **(default)**. For: Keeps the approved list, so it still matches the support-status list. Against: Two codes on the list are never used.
- **b.** Keep only "low certainty" on the list. For: Nothing unused. Against: Changes a list you approved on 30 October.
- **c.** Change the check order. For: All three codes become possible. Against: Reopens an approved rule for no gain in information.

Confidence: medium. SPEC departure: no. Version steps: none (rule text only).
Sources: final-open.json F10 (approved values and check order); RC-D-003 §16 O10.

## FX06. Reserved missing labels used as answer codes on 17 items

Seventeen items list `unknown` (12) or `not_documented` (5) among their answer codes, but these are reserved missing labels; the approved item template forbids an answer code that equals one (check 8).

- **a.** Take the label out of the answer list and keep its item-specific meaning as a rule line on the item **(default)**. For: Meets check 8 with no loss of text; the label stays allowed through the item's missing labels. Against: The item's own meaning of the label now sits among its rules, not beside the answers.
- **b.** Keep the label as an answer code and exempt these items. For: No move. Against: Breaks check 8 for 14 items that are not frozen; only frozen items may be exempt.
- **c.** Take it out and drop the item-specific meaning. For: Shortest. Against: Loses approved text.

Confidence: medium. SPEC departure: no. Version steps: list change on 17 items; rides v2.7's two steps (C-007, r2#5).
Sources: planning/t010/item-template.md §4 check 8; fold-log-round3.md §4 choice 3 (missing-token codes kept out of value lists; accepted as O16); SPEC v001.7 R-045 (new and non-frozen fields adopt the reserved set).
Note: The allowed (type, action) pairs table keeps its `unknown` rows: `unknown` stays a valid answer through the missing labels. The approved safeguard rule still says "the four answers" (yes, no, unclear, not documented); after this move the fourth is a missing label, so the sentence stays true but reads differently.

## FX07. Purchase status "none documented" next to the reserved "not documented"

The purchase-status answer `none_documented` (the page shows the activity but no purchase step) is very close to the reserved label `not_documented`.

- **a.** Keep the ruled code and say that, for this item, a page with no purchase step takes `none_documented`; `not_documented` is not used **(default)**. For: Keeps the ruled list; one answer per situation. Against: The item still lists `not_documented` among its allowed labels, which the rule then overrides.
- **b.** Drop `none_documented` and use `not_documented`. For: No near-duplicate. Against: A list change against the round-1 ruling's list.
- **c.** Rename it (for example `no_purchase_documented`). For: Clearer. Against: A respelling no ruling asked for.

Confidence: medium. SPEC departure: no. Version steps: none (rule text only).
Sources: codebook-rulings-round1.json (procurement_status: none_documented / tender_or_rfp / award_or_contract / payment_or_subscription / unknown); drafts/definitions-r4.json (approved definition of none_documented).

## FX08. Rules written twice: keep the plan text in each pair

The five 'same rule written twice' cards had no approve option, so 'approve all' does not settle them; you asked (P4) to keep one text of each pair. This also removes the role-gate text that appeared twice on the observed-actor relationship.

- **a.** In each pair keep the plan text (the longer text, which contains the other) and drop the restatement **(default)**. For: Nothing is lost: each dropped text is contained in the kept one; the role gate and the shared lists keep their own copy. Against: Drops texts you approved on 30 October, which are shorter and plainer.
- **b.** In each pair keep the text you approved on 30 October and drop the plan text. For: Shorter, plainer texts. Against: The plan texts carry other rules (quality flag, beneficiary rule, truth table) that would be lost.
- **c.** Keep both. For: No loss. Against: Against your P4 choice; the rule is repeated in every prompt.

Confidence: medium. SPEC departure: no. Version steps: none.
Sources: PI 2026-10-30 P4 (accepted: show each pair side by side and drop one); codebook-review/round4 cards O1, O2.

## FX09. Your sentence for the support status "Not required"

After the 2a cut the option text reads only "Not required". The approved status list says which answers take it.

- **a.** "`not_required`: the answer needs no supporting quote by its nature. It is given to `not_documented`, `unknown`, `no` and negative page verdicts." **(default)**. For: Built from the cut option text and the approved status list; no new rule. Against: Agent wording.
- **b.** Restore the full round-3 option text. For: Your earlier text. Against: It names only not documented and unknown, which the 30 October sign-off widened.
- **c.** Leave "Not required". For: No change. Against: Says nothing about which answers take it.

Confidence: high. SPEC departure: no. Version steps: none.
Sources: questions-r3.json record-02 a (option text and its cut tail); deltas/RC-D-003.md:96 (O12).

## FX10. Remove the 'wording owed' notes inside six texts

Four plan texts still carry six bracketed notes saying wording is owed (for example "[wording: PI — RC-D-002 row 8: value definitions for the 9 values]"). Your approval of every slot supplies that wording, and the notes would otherwise go into every prompt.

- **a.** Remove the six notes from the codebook texts **(default)**. For: Clean prompts; the owed wording now exists in the approved slots. Against: The codebook text then differs from the plan text by these notes.
- **b.** Keep them until sign-off strips the markers. For: No change now. Against: The final draft would still show them; sign-off strips markers, not text.

Confidence: high. SPEC departure: no. Version steps: none.
Sources: SPEC v001.7 (the [wording: PI] markers point to the codebook slots); PI 2026-10-30 round-4 approval.
Note: SPEC v001.7 keeps its 20 markers; they are discharged when the codebook is signed.

## FX11. Remove the superseded version-1.5 text from the verdict rule

The plan text on the page verdict ends with its superseded history ("v001.5 text: Page-verdict vocabulary has 8 values ..."), which contradicts the 9-value rule before it and would go into every prompt.

- **a.** Cut the history tail from the codebook text **(default)**. For: The rule says one thing; the history stays in the plan. Against: The codebook text then differs from the plan row.
- **b.** Keep it. For: Verbatim plan row. Against: Prompts carry an 8-value rule next to the 9-value rule.

Confidence: high. SPEC departure: no. Version steps: none.
Sources: SPEC v001.7 R-015 (the 9-value rule; the v001.5 text is kept there as history).

## FX12. Remove planning remarks (costs, version steps, test pages) from rule texts

Several approved ruling texts end with remarks about what the change costs the project (version steps, re-pilots, test pages, procurement copies). They are not coding rules, and they would go into every prompt.

- **a.** Cut only the listed remarks; keep every coding rule **(default)**. For: Clean prompts; the remarks stay in the ruling records and the plan. Against: The codebook text then differs from the ruling text by these remarks.
- **b.** Keep them. For: Verbatim ruling texts. Against: Prompts carry project bookkeeping.

Confidence: medium. SPEC departure: no. Version steps: none.
Sources: codebook-rulings-round2.json (the 'means' texts); SPEC v001.7 rows R-015, R-045, R-087.
Note: Mixed sentences that also carry a rule are kept whole (for example the outcome and incident gate sentence, and the transparency re-wording sentence).

## FX13. Remove reference codes from rule texts

Plan and ruling texts carry reference codes in brackets, for example "(r2#22; activity-16 b; all-11)", and lead-ins such as "RC-D-002 row 8:". They would go into every prompt.

- **a.** Remove brackets that hold only reference codes, and the 'RC-D-00x row N:' lead-ins at a sentence start; keep every bracket with words in it **(default)**. For: Clean prompts; the references stay in each item's refs and in the slot's earlier text. Against: Codes that name a thing (for example "the C04 grain rule", "X29 truth table") stay, as they are content.
- **b.** Keep them. For: Verbatim texts. Against: Prompts carry planning codes.

Confidence: medium. SPEC departure: no. Version steps: none.
Sources: item-template.md §3 (only the PI changes text; references belong in refs).
