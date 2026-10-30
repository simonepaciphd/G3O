# SPEC: G3O pipeline reclassification

Status: APPROVED
Approved: v001.4, 2026-10-28 (Simone Paci); not locked
Version: v001.4
Supersedes: none
Owner: Simone Paci (sole substantive approver)
Mode: revision (changes the production G3O pipeline and its published outputs)
Authoritative inputs:
- SRC-9 `planning/Stage5-Rulings.md` (Stage 5 PI rulings, 2026-10-28)
- SRC-1 `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-unclear-screen/HANDOFF.md` (rulings 1-11, S1-S9, P-A..P-H; verified facts 2026-10-27)
- SRC-2 `planning/Stage1-Interview.md` (rulings Q1-Q8, 2026-10-27)
- SRC-3 Output Contract v2.5, `G3O` origin/main `c6349d6`, `g3o/extract/prompts/output_contract.md` and `system_prompt.md`
- SRC-4 v2.6 / consolidation v1.4 / exval-1: local ref `archive/exval-v2.6` (`052fcb2`), `docs/extraction-validation-rulings.md` there; review `H:/My Drive/Research/G3O/agent-workspace/2026-09-06-extraction-validation/REVIEW.md`
- SRC-5 WS10 rulings D1-D6: `H:/My Drive/Research/G3O/agent-workspace/2026-09-05-combined-ws10-review/DECISIONS.md`, `DECISIONS-followup.md`, `OWNER-REPRESENTATION.md`
- SRC-6 CX-01.2 (signed, wording frozen 2026-10-25): `H:/My Drive/Research/G3O/archive/planning-drive-copy-superseded-2026-10-26/launch-analysis-pr/index-design/codebook-extension-proposal.md`
- SRC-7 re-pilot 2 page-verdict wording: `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-unclear-screen/unclear2.py` L32-55 (ruling 9 "b"/"ok"); results `report-repilot2.json`
- SRC-8 jev vs nano comparison: `H:/My Drive/Research/G3O/agent-workspace/2026-09-27-jev-compare/REPORT.md` (agreement with old pipeline, not accuracy)

Evidence tags: `USER` = PI ruling (ID given); `SOURCE:` = artifact; `INFERRED` = agent inference, provisional until approved; `OPEN` = unanswered.

## Goal and success

- G-001 [USER 5, 6, 11]: The production G3O pipeline classifies and extracts, for every institution it reviews, more fields about each GenAI activity, under an updated output contract (v2.6 rules plus the CX-01.2 fields), and the published database carries them.
- G-002 [USER 6 (architecture), S7 a, Q3 b, S8 a]: Every published classification code is backed by verbatim supporting text from the source page; a code without supporting text is not published as positive.
- G-003 [USER S3, S4, Q4 b]: Institutions already published as documented or unclear are reclassified under the new contract, the 27,648 unclear included, in the same change.
- G-004 [USER 6]: Downstream, the full updated database is handed to Kaser after this reclassification (bulk access, g3o-website#175). The handoff itself is not a deliverable of this plan (N-006).
- G-005 [SOURCE:SRC-6 §10; USER Q8 b, SF-006 a]: The CX-01.2 fields are produced for documented and unclear institutions. The transparency and governance indices stay withheld under R-060 as written; because `none` institutions are not back-filled (Q4 b), full coverage is not reached by this plan and the indices are not an outcome of it.

## Actors, audience, and operating context

| Actor | Needs / permissions | Context of use | Successful experience |
|---|---|---|---|
| PI (Simone) | Sole approver of codebook wording, thresholds, audits, release | Reviews audit packets and release diffs | Can see what changed per institution and why, and sign off once |
| Public API / website users | Read-only | Browse institutions, activities, evidence | See new fields, supporting text and which contract version produced each row |
| Kaser (downstream, via #175) | Bulk extract of the full updated database | After release | Receives one consistent, versioned database |
| Index work (CX-01) | Reads new page and finding fields | After full coverage per R-060 | Fields present, versioned, with jev confidence |
| Procurement subproject | Consumes the output contract | Ongoing | Contract changes announced; no silent break |
| Colin (g3o-api / website owner) | Owns publication surfaces | Implements publication from this plan's handoff | Receives an exact field/interface specification [USER P2] |

## Deliverables

| ID | Deliverable | Format/surface | Required contents | Consumer | Priority | Resources (Stage 2) |
|---|---|---|---|---|---|---|
| D-001 | Output Contract v2.7 (codebook of record; label per Q-018) | Contract and prompt documents in the pipeline repo, with version stamps | v2.6 rules (R-010..R-014); CX-01.2 fields (R-020..R-024); page-verdict vocabulary incl. `other_body` (R-015); generative-AI wording (R-016); page completeness and follow-up links (R-030); per-code supporting text (R-040); downgrade rule (R-041); contract version per row (R-050); procurement's owed §4.3 amendment (R-087); labels extract v2.7 + validate v1.5 (USER DEC-013 a) | Pipeline, PI, index work, procurement | must | RS-010, RS-011, RS-004, RS-005, RS-024, RS-026 |
| D-002 | Production pipeline producing v2.7 output | Pipeline runs (new and back-fill) | Behaviour R-001..R-006, R-026, R-030..R-034, R-040..R-044 | Every future run; D-003 | must | RS-012..RS-017, RS-011, RS-019, RS-031 (design gaps G3-G6, G10, G13) |
| D-003 | Back-filled reclassification release | Correction layer linked to original observations, then published | All documented + unclear institutions reclassified (R-070..R-075) | Public DB, API, site, Kaser | must | RS-005..RS-009, RS-025..RS-027, RS-020, RS-030, RS-032, RS-036 (G2, G3) |
| D-004 | Published v2.7 data | Public DB, API, website | New fields, supporting text, per-row contract version; website shows each institution's most recent row, backend keeps every run (R-050..R-052) | Public, Kaser, index work | must | RS-020, RS-021, RS-022, RS-030 (G6) |
| D-005 | Quality evidence packet | Report + PI audit record | Agent read, PI audit, jev confidence thresholds applied (R-080..R-083) | PI (release gate) | must | RS-025, RS-036, RS-005, RS-024, RS-009, RS-011, RS-019 (G9) |
| D-006 | Updated documentation | Data dictionary, contract changelog, methods note | Every new field, value, version and downgrade rule documented (R-090) | Public, Kaser, RAs | must | RS-018, RS-011, RS-010 |
| D-007 | Publication handoff for API/site owner | Interface specification | Exact fields, types, version display, mixed-version behaviour (R-052) | Colin [USER P2] | must | RS-023, RS-020, RS-022 |
| D-008 | Coordinated procurement contract update | Delta handoff to the procurement plan's integrator (that plan's DEC-009) | The 8-value page verdict replacing `genai_evidence` (procurement `contract.py` copies the 4-value enum), the §4.3 amendment (R-087), the version bumps (extract v2.7, validate v1.5), and timing against deployment (R-085: after the fixture run passes, before deployment, USER DEC-014 b) | Procurement plan integrator | must | RS-029 |

## Requirements

### Classification and extraction (D-001, D-002)

| ID | Requirement | Applies to | Source | Priority | Notes/example |
|---|---|---|---|---|---|
| R-001 | Classification is made by jev; gpt-5-nano does not decide codes. | D-002 | USER 6, S7 a | must | Fixed constraint C-001 |
| R-002 | First pass, per page: jev assigns the page-level codes: page verdict (R-015), CX-01.2 page fields (R-020, R-021, R-023), and page completeness (R-030). | D-002 | USER S7 a, Q3 b | must | |
| R-003 | After the first pass, the extraction model segments the page into one or more activities; each activity is a separate unit for the second pass. The second pass runs on every page with GenAI content: `confirms_activity`, `ambiguous_genai`, `ambiguous_attribution`, `other_body`, `event_only`. | D-002 | USER S7 a, Q3 b, SF-015 c | must | A page may carry 2+ activities with different types and stages. `background_only` excluded (documents no activity): INFERRED |
| R-004 | Second pass, per (page × activity): jev assigns every activity-level code (v2.5 Group D enums and flags under v2.6 rules; CX-01.2 finding fields R-022) with that activity as context. | D-002 | USER Q3 b; SOURCE:SRC-6 CX-02 | must | |
| R-006 | Free-text activity fields (`activity_name`, `tool_name`, `vendor`, `year_announced`, `year_deployed`, `reported_outcomes`, `reported_incidents`, `scope_notes`): jev answers them as Choice questions where a closed set exists, values are taken by deterministic extraction where possible, and gpt-5-nano extracts only what neither covers. Each value carries supporting text (R-040). | D-002 | USER SF-001 "b, then a for what jev can't cover" | must | Routing ruled DEC-009 a (SRC-9): jev Choice for `year_announced`, `year_deployed` and CX-60/61 normalisation; deterministic for contact emails and explicit years; nano for `activity_name`, `tool_name`, `vendor`, `reported_outcomes`, `reported_incidents`, `scope_notes` |
| R-005 | Institution-level consolidation (Stage 6) applies the v2.6 consolidation rules as jev questions or deterministic rules: explicit relations before merging observations; distinct/unresolved relations never merge; institution-level `no` only with complete supplied context and no unresolved signal. An institution whose reviewed pages are all negative at confidence ≥ 0.8 gets `no` directly; the complete-context rule blocks `no` only when an unresolved signal remains (a low-confidence negative downgraded under R-081 counts as one). | D-002 | USER S9 a, SF-009 b; SOURCE:SRC-4 | must | Replaces v1.4 rules that targeted the retired OpenAI Stage 6 path |
| R-010 | WS10 D1 action boundary: a public-facing GenAI event or educational programme is not a qualifying activity; an event page can support a separate record only when it documents the institution's own adoption, procurement, deployment or governance. | D-001 | SOURCE:SRC-5 D1 | must | |
| R-011 | WS10 D2: formal institution-issued GenAI governance qualifies whether it governs staff or external users; governance is recorded separately from deployment. | D-001 | SOURCE:SRC-5 D2 | must | |
| R-012 | WS10 D3: a completed review containing only clearly excluded events yields no qualifying evidence with exclusion reasons preserved; genuinely uncertain signals stay unclear. | D-001 | SOURCE:SRC-5 D3 | must | |
| R-013 | WS10 D4: institution-specific, explicitly GenAI proposals remain a qualifying activity. | D-001 | SOURCE:SRC-5 D4 | must | |
| R-014 | v2.6 rules: observed actor distinguished from query target; each detail field independently supported or cleared; every source keeps its disposition, reason and original mention; page-level extraction cannot issue institution-wide `no`. | D-001 | SOURCE:SRC-4 | must | |
| R-015 | Page-verdict vocabulary has 8 values: the 7 re-pilot 2 values (`confirms_activity`, `ambiguous_genai`, `ambiguous_attribution`, `other_body` = v2.6 `other_actor`, `event_only` = v2.6 `excluded_event`, `background_only`, `no_genai`) plus v2.5 `confirms_absence` (page states absence; distinct from `no_genai`, no relevant content). It replaces v2.5 `genai_evidence` in the same column. Rows produced under v2.5 keep their 4-value answers unconverted until the institution is rerun; the row's contract version (R-050) says which vocabulary applies. Rules that read the column (yes needs a `confirms_activity` row; activity fields `_NA_` otherwise) are updated to the 8 values. Enum change: two contract-version steps, procurement notified (C-007). | D-001 | USER 8 b, SF-007 c, SF-007 follow-up a; SOURCE:SRC-1, SRC-7 L45-54 | must | Names kept: `other_body`, `event_only` (Q-012, P7) |
| R-016 | Generative-AI wording: the re-pilot 2 wording governs (SRC-7 L34-45), including that a named "AI chatbot or AI assistant" counts as a generative product; `system_prompt.md` L15 rule ("chatbot" alone is not evidence) is amended to match. A named "AI chatbot" or "AI assistant" counts as generative and overrides the rule-based-chatbot exclusion (contract L12) for that naming. Contract §4.1 is unchanged: a generic "AI strategy" or "AI tools" stays `unclear`; the 17 ambiguous→no moves of re-pilot 2 are instrument error the v2.7 questions must not repeat. | D-001 | USER Q7 b, Q-003 a | must | SF-008 a |
| R-020 | CX-01.2 `disclosure_form` (page): CX-10..CX-18. | D-001 | SOURCE:SRC-6; USER S1 c | must | |
| R-021 | CX-01.2 `disclosure_scope` (page, all pages): CX-20..CX-25. | D-001 | SOURCE:SRC-6 | must | |
| R-022 | CX-01.2 `evaluation_documented` (finding × page) and gated `evaluation_type_*`: CX-30..CX-41. | D-001 | SOURCE:SRC-6 | must | |
| R-023 | CX-01.2 `content_*` items incl. safeguard items and the two contact sub-items: CX-50..CX-52; `content_contact_emails` by deterministic `@` extraction when contact = yes (CX-53). | D-001 | SOURCE:SRC-6 | must | |
| R-024 | CX-01.2 normalisation of `reported_outcomes` / `reported_incidents`: CX-60, CX-61. | D-001 | SOURCE:SRC-6 | must | |
| R-025 | CX-01.2 wording is used as frozen; any revision requires re-signature. | D-001 | SOURCE:SRC-6 §10 | must | |
| R-026 | Every jev answer is stored with its probability distribution, confidence, response model id and request id. | D-002 | SOURCE:SRC-6 CX-05 | must | |

### Completeness and follow-up links (D-001, D-002)

| ID | Requirement | Applies to | Source | Priority | Notes/example |
|---|---|---|---|---|---|
| R-030 | The first pass also records whether the page holds all available information about every activity it mentions, or links to further pages with information about any of them. | D-001, D-002 | USER Q3 | must | |
| R-031 | When a page is not complete, the LLM extracts the follow-up links and they are sent back to the scrape phase; fetched pages then pass through the same classification. | D-002 | USER Q3 | must | |
| R-032 | Following continues until pages are complete, subject to a hop limit: a followed page's links are followed again only up to 3 hops from the originally scraped page. A per-institution cap on followed URLs also applies; when it is reached, following stops and "cap reached" is recorded. | D-002 | USER Q6a iii, Q-001 b, "3 hops"; item 22 b (SRC-9) | must | Cap value set by the PI after the cost/latency spike (T-002) |
| R-033 | Any link the page cites is eligible, including news and vendor pages. | D-002 | USER Q6b ii | must | Link-loop and duplicate handling: R-034 |
| R-034 | Each URL is fetched at most once per institution per run; every followed link records the page it came from (provenance chain). | D-002 | INFERRED | must | Prevents loops under R-032 |
| R-035 | Link-following also applies in the back-fill (live fetching for reclassified institutions). | D-003 | USER Q6c i | must | |
| R-036 | Pages fetched live during the back-fill are new source records tagged with their provenance (origin page, fetch date, back-fill release). They count as evidence but sit outside the original searched sample and never add to its denominator. | D-003 | USER SF-002 a; SOURCE:SRC-5 D5 | must | |

### Supporting text and downgrade (D-001, D-002)

| ID | Requirement | Applies to | Source | Priority | Notes/example |
|---|---|---|---|---|---|
| R-040 | For every jev code on a page or activity, gpt-5-nano extracts the verbatim supporting text from the page, after jev has coded. | D-002 | USER 6, S7 a | must | |
| R-041 | A positive or substantive code with no supporting text is downgraded: field to `unknown` (or the field's no-evidence value); institution verdict to `unclear` when no supported positive remains. Only positive or substantive values need support; `no`, `unknown`, `not_documented`, `_NA_` and negative page verdicts need none. | D-001, D-002 | USER S8 a, Q-010 a | must | |
| R-042 | Supporting text is checked against the stored page text by fuzzy match; a quote below the match threshold counts as no supporting text. | D-002 | USER SF-014 ii c; SOURCE:SRC-4 quote-presence check | must | Presence only, not entailment. Threshold and metric calibrated on fixtures at Stage 3, PI approves (Q-020 b) |
| R-044 | Chunked pages (> 32k tokens, C-004): the CX-01.2 §11.1 combination rule applies to every field. Page fields take the first chunk's value; yes/no items are yes if any chunk says yes; ordered vocabularies take the first value in table order found in any chunk. The supporting quote comes from the chunk that produced the code. | D-002 | USER P6 (SF-005); SOURCE:SRC-6 §11.1 | must | |
| R-043 | Supporting text is published with the code it supports. The API carries the full text; the website shows it up to a display cap, with a marker and access to the full text. | D-004 | USER S2; DEC-016 c (SRC-9) | must | Cap value proposed after the quote-matcher spike (T-003), set by the PI |

### Versioning and publication (D-004, D-007)

| ID | Requirement | Applies to | Source | Priority | Notes/example |
|---|---|---|---|---|---|
| R-050 | Every published row carries the contract version that produced it. | D-002, D-004 | USER Q5 a | must | Today only per-run stamps exist (SRC-1) |
| R-051 | The backend keeps one row per institution per run, each with its contract version. The website shows only each institution's most recent row, with its version visible. | D-004 | USER Q5 a, SF-011 ("show just the most recent on the website") | must | Supersedes "side by side". API: most recent row by default; older rows through a history parameter or endpoint (USER DEC-015 a) |
| R-055 | Correction-layer and back-fill rows are visible on the API and website regardless of wave windows. | D-004 | USER G7 b | must | Wave windows keep governing ordinary new runs (confirmed item 24 b, SRC-9); new windows are opened by the PI, and the plan checks for an open window before w001 expires (2027-01-01) |
| R-056 | No v2.7 row, back-fill or ordinary run, is public before the release decision: a release flag keeps such rows loaded but hidden until the PI releases them after the audit (R-080..R-083). | D-003, D-004 | USER item 21 b, PF-006 default (SRC-9) | must | Ordinary runs continue to load between deployment and release |
| R-052 | New fields are published via the public API and the website. | D-004, D-007 | USER S2 | must | Owner: Colin (P2) |
| R-053 | SUPERSEDED (PI SF-014 i, "superseded", after R-051 ruling). | — | USER SF-014 i | — | Residual ruled Q-021 a: website hides new fields where the most recent row is v2.5 |
| R-054 | Indices built on CX-01.2 fields stay withheld until the new fields cover the whole post-sweep snapshot (R-060 of CX-01, unchanged). | D-004 | USER Q8 b | must | Under Q4 b this is not reached within this plan (N-003) |

### Back-fill (D-003)

| ID | Requirement | Applies to | Source | Priority | Notes/example |
|---|---|---|---|---|---|
| R-070 | Back-fill set: every institution published as documented or unclear at the freeze date (2026-10-24 aggregates: 9,705 + 27,648). The freeze date is the v2.7 deployment date; the back-fill starts after deployment, so no run is published under v2.5 after the freeze. Wave 5 (`r20261023T134656Z-be8a`, still running on 2026-10-27) is included: the back-fill set is drawn only after wave 5 is published. | D-003 | USER Q4 b, SF-012 b, G12 ("still running, we'll do the full update once it's in") | must | Supersedes Q-015 |
| R-071 | Institutions published as `none` keep their v2.5 verdict and are not back-filled. A `none` institution re-drawn by a future run is reviewed under v2.7 like any other. | D-003 | USER Q4 b, Q-016 a | must | |
| R-076 | Pages reclassified: for documented and unclear institutions alike, all pages of their latest run. Followed links (R-035) add to both. | D-003 | USER SF-003 b; item 20 a (SRC-9) supersedes ruling 10 b (ambiguous pages only, 58,654 with stored text) | must | Avoids mixing 4-value and 8-value page answers within one institution (PF-003). Page count and cost sized by T-001/T-002 before the paid gate |
| R-072 | The 27,648 unclear are reclassified in the same change as the rest. | D-003 | USER S4 | must | |
| R-073 | Verdict and field changes are recorded in a correction layer linked to the original observations; original run, rows, stamps and evidence are never overwritten. | D-003 | USER 5 a; SOURCE:SRC-5 D5 | must | |
| R-074 | Reclassification uses stored page text where it exists; pages without usable stored text (none stored, or raw `%PDF` bytes) are re-scraped live and then classified as usual; each re-fetch records its fetch date. A failed re-fetch ends in a named failure state (R-075). | D-003 | USER Q-011 a; SOURCE:SRC-1 (994 of 27,648 lack text; 97 raw-PDF pages) | must | Re-fetched original URLs stay original source records with new text (INFERRED); only newly followed links fall under R-036 |
| R-077 | The release includes the historical WS10 combined correction (114 activities from 64 source institutions to 45 verified owners), carried through the same correction layer (R-073) so attribution and WS10 dispositions publish together. The 114 (list: `activity-review-prepared.csv`, RQ-003 confirmed) are reclassified by the v2.7 pipeline and covered by the R-082 agent read; the release does not wait for the incomplete WS10 combined review (14 of 45 owner groups done). Verified owners currently published as `none` are included for these transfers (exception to R-071 / N-001). | D-003 | USER Q-013 a, G1 b, item 23 ii (SRC-9); SOURCE:SRC-5 D5 | must | |
| R-075 | Every institution in the back-fill set ends with exactly one of: reclassified under v2.7; or a named failure state. No silent drop. | D-003 | INFERRED | must | |

### Quality (D-005)

| ID | Requirement | Applies to | Source | Priority | Notes/example |
|---|---|---|---|---|---|
| R-080 | Quality bar = agent read + PI audit, plus jev confidence thresholds. | D-005 | USER S5 b+c | must | |
| R-081 | One confidence threshold for all jev codes: 0.8. A code below 0.8 is downgraded as under R-041. This includes negative and absence codes: a page or field coded negative below 0.8 goes to `unclear` / `unknown`. | D-002, D-005 | USER S5 c, Q-002 ("all codes, .8, downgrade"), Q-019 a | must | |
| R-082 | Review follows WS10 D6 (agent-led, PI audits and rules on exceptions) on a sample: the agent reads a stratified sample of reclassified institutions; the PI audits a subset of that sample. | D-005 | SOURCE:SRC-5 D6; USER 2 c, SF-004 b | must | Q-017 ruled: see R-086 |
| R-085 | The procurement subproject's contract dependency is updated in coordination with this plan, not only notified: a delta goes to the procurement plan's integrator before deployment, and procurement is told this in a message. | D-008 | USER G11 b ("add a message on the procurement pipeline about this") | must | Procurement `pipeline/core/contract.py` L73 copies the 4-value enum; procurement is pinned at v2.0 |
| R-087 | The procurement subproject's owed §4.3 contract amendment is carried in v2.7, in the same version bumps. | D-001, D-008 | USER item 26 a (SRC-9) | must | Text agreed with the procurement integrator; v2.7 scope depends on it |
| R-084 | The S5 bar (R-080..R-082) replaces the CX-01.2 §10 RA gold set (C-015) as the release gate for the CX-01.2 fields. The C2-C4 wording, never run before, passes a fixture test before the back-fill. | D-005 | USER SF-013 b | must | |
| R-086 | Sampling: 400 reclassified institutions, stratified by group (documented / unclear) × verdict changed vs unchanged, 100 per stratum; overall figures are reported weighted to the back-fill set. The owner institutions of the 114 WS10 transfers (R-077) are read as an additional stratum on top of the 400. The agent read is done by a subagent swarm, 25 institutions per subagent: Haiku reads all 400 (16 subagents) plus the transfer stratum, and Sonnet reads 100 of the 400 (4 subagents), drawn proportionally (25 per stratum, fixed seed); the Sonnet-Haiku difference on the shared 100 is reported. Agents read blind (pipeline codes not shown) and record the institution verdict and every page verdict. "Disagreement" = agent read vs v2.7 output on the institution verdict or any page verdict, and Sonnet vs Haiku on the overlap. The PI audits every disagreement plus 25 at random. Disagreement does not block release: the release goes ahead with the disagreement reported in the quality packet. | D-005 | USER Q-017 ("1 b ... 2 a 3c 4c"); DEC-011 a, DEC-017 b, SD-g, items 23 i, 27 (SRC-9) | must | Model ids recorded at run time (DEC-022) |
| R-083 | The quality packet reports agreement descriptively and never presents agreement with the old pipeline as accuracy. | D-005 | SOURCE:SRC-8 | must | |

### Documentation (D-006)

| ID | Requirement | Applies to | Source | Priority | Notes/example |
|---|---|---|---|---|---|
| R-090 | Data dictionary, contract changelog and a methods note document every new field, value, version, downgrade and link-following rule. | D-006 | INFERRED | must | |

## Scenarios

| ID | Actor/start | Trigger/input | Expected final state | Failure behavior | Requirement IDs |
|---|---|---|---|---|---|
| SC-01 Canonical | New run, institution with one page documenting a Copilot pilot | Normal run | Page coded; one activity; all codes with verbatim support; v2.6 row published | Missing quote → field `unknown` | R-002..R-005, R-040, R-041, R-050 |
| SC-02 Multi-activity | Page documents a GenAI policy and a chatbot pilot | Normal run | Two activities with different `activity_type` / `adoption_stage` | — | R-003, R-004 |
| SC-03 Incomplete page | Press release links to a council report on the same pilot | First pass says incomplete | Report fetched, classified, linked by provenance; activity fields drawn from both | Cap reached → stop, record "cap reached" | R-030..R-034 |
| SC-04 Back-fill unclear | Institution published unclear under v2.5 | Back-fill | Reclassified (e.g. documented, unclear, `no`); change in correction layer; both versions traceable | Fetch failures reported | R-070..R-075 |
| SC-05 Boundary: other body | Village page about a district's chatbot | Any run | `other_body`; not counted for the village | — | R-015 |
| SC-06 Boundary: no text | Unclear institution with no stored text | Back-fill | Pages re-scraped live, classified, reported | Re-fetch fails → named failure state | R-074, R-075 |
| SC-07 Mixed versions | User views a v2.5 institution and a v2.6 institution | During back-fill | Each shows its most recent row and version; backend holds both runs | — | R-050..R-052 |
| SC-08 Handoff (downstream, non-goal N-006) | #175 lane after release | Release complete | Released database is in a single versioned state the #175 lane can extract | — | G-004 |

## Inputs and provenance

| Input | Owner/source | Required? | Validity/freshness | Missing/conflict behavior |
|---|---|---|---|---|
| Stored page text of published runs | `/home/g3o/runs` on the droplet | yes | per run | R-074 |
| Published verdicts at freeze | Public DB / API | yes | freeze = v2.7 deployment date (R-070) | Freeze date recorded |
| Live web for follow-up links | Internet | yes (R-035) | fetch date recorded | Fetch failure recorded per URL |
| v2.6 rules, CX-01.2 wording, re-pilot 2 wording | SRC-4, SRC-6, SRC-7 | yes | signed / ruled | Conflicts → PI (Q-003) |

## Output/interface contracts

| Producer/result | Consumer | Format/granularity | Required fields/properties | Rejection condition |
|---|---|---|---|---|
| Pipeline (D-002) | DB / API | page, activity, institution rows | all v2.6 fields, jev confidence, supporting text, contract version, link provenance | Row without contract version |
| Correction layer (D-003) | DB views | linked to original observation ids | before/after values, release id, contract version, PI sign-off ref | Overwrite of original observation |
| API/site (D-004) | Public | per institution / activity / evidence | new fields, supporting text, version label | Mixed-version rows unlabelled |

## Quality attributes

| Attribute | Required outcome | Observable threshold/evidence | Priority |
|---|---|---|---|
| Traceability | Every published code traceable to page, quote, jev request, contract version | Spot-trace of sampled rows succeeds end to end | must |
| Correctness | Meets S5 bar | PI audit signed; thresholds Q-002 applied | must |
| Non-destructiveness | Original observations intact | Diff of original observation values (pre-existing columns and rows) before/after release is empty; added columns excluded | must |
| Transparency | Version and downgrade visible to users | Site shows version label on sampled pages | must |

## Acceptance tests

| ID | Given | When | Then | Evidence | Approver | Requirement IDs |
|---|---|---|---|---|---|---|
| A-001 | Contract v2.7 documents | PI review | Every R-010..R-030, R-040, R-041 rule appears in the contract text | Sign-off record with hash | PI | D-001 |
| A-002 | Sample of v2.7 rows | Trace check | Each positive code has a quote matching the stored text under R-042 | Trace report | agent + PI | R-040..R-042 |
| A-003 | Multi-activity test pages | Run | Activities coded separately | Fixture results | agent | R-003, R-004 |
| A-004 | Incomplete-page test cases | Run | Links followed, provenance stored, cap respected, no URL fetched twice | Run log | agent | R-030..R-034 |
| A-005 | Back-fill set | Release | Count reclassified + named failures = back-fill set size | Reconciliation table | PI | R-070, R-075 |
| A-006 | Original observation values (pre-existing columns and rows) | Before/after release | No original value changed; added columns excluded from the diff | Diff | agent + PI | R-073 |
| A-007 | API and site | After release | New fields, quotes and version labels visible; website shows the most recent row per institution; backend holds every run's row | Screenshots / API responses | PI | R-050..R-053 |
| A-008 | Quality packet | Release gate | Agent read + PI audit done; thresholds applied | Signed audit | PI | R-080..R-083 |
| A-009 | Index surfaces | After release | No CX-01 index published | API/site check | agent | R-054 |
| A-010 | Institution fixtures (complete context vs open signals) | Stage 6 run | Merges only with explicit relations; `no` only with complete context and no unresolved signal | Fixture results | agent | R-005 |
| A-011 | Page fixtures for every page-verdict value incl. `other_body`, `event_only` | Run | Each fixture receives its expected value | Fixture results | agent + PI | R-015 |
| A-012 | Generative-AI boundary fixtures (named chatbot/assistant; generic "AI strategy"; rule-based chatbot) | Run | Coded per R-016 and Q-003 ruling | Fixture results | PI | R-016 |
| A-013 | Sample of stored jev answers | Inspection | Each has probability distribution, confidence, model id, request id | Field check | agent | R-026 |
| A-014 | Back-fill sample | Release | Followed-link pages present with provenance and fetch date | Run log | agent | R-035 |
| A-015 | Back-fill institutions without usable stored text | Release | Each re-scraped (or in a named failure state) and listed in the reconciliation table | Reconciliation table | PI | R-074 |
| A-016 | Codes below threshold | Release | Each treated by the Q-002 rule; counts reported per field | Quality packet | PI | R-081 |
| A-017 | Data dictionary, contract changelog, methods note | Release | Every new field, value, version, downgrade and link rule documented | Doc review | PI | R-090 |
| A-018 | Procurement subproject | Before deployment | Delta accepted by the procurement plan's integrator, with version numbers; message sent (G3O issue #134, 2026-10-27) | Delta record + issue | PI | C-007, R-085, D-008 |
| A-019 | Publication handoff | Before API/site work | Owner has accepted the interface specification | Acceptance record | PI | D-007, R-052 |
| A-020 | C2-C4 fixture pages | Before back-fill | Each fixture receives its expected CX value | Fixture results | agent + PI | R-084 |
| A-021 | Chunked-page fixtures | Run | Combined codes follow R-044; each quote occurs in the chunk that produced the code | Fixture results | agent | R-044 |
| A-022 | The 114 WS10 transfers | Release | Each appears in the correction layer under its verified owner, with WS10 disposition | Reconciliation table | PI | R-077 |

## Constraints

- C-001 [USER 6]: jev classifies; gpt-5-nano extracts activities and supporting text after jev; nano is not a classifier.
- C-002 [USER S6]: no deadline and no cost ceiling for the plan. Each paid run still needs PI sign-off before launch (C-003).
- C-003 [SOURCE:card; CLAUDE.md]: PLAN_ONLY. No code change, paid run, DB write, push or deployment without separate PI sign-off after the baseline lock.
- C-004 [SOURCE:SRC-1]: jev returns codes only (no text); state limit 32k tokens per request, so long pages are chunked.
- C-005 [SOURCE:SRC-5 D5]: transfers and corrections never invent search records, draw membership or pipeline stamps, and never add to the original searched-sample denominator.
- C-006 [SOURCE:CLAUDE.md]: pilot v1 is never used as input, comparator or evidence.
- C-007 [SOURCE:memory contract-v2-2]: an enum change costs two contract-version bumps; the procurement subproject consumes the contract; its update is coordinated under R-085 / D-008 (G11 b supersedes "notification suffices").
- C-008 [SOURCE:CLAUDE.md]: `inputs/` is read-only.

## Non-goals

- N-001 [USER Q4 b]: back-fill of `none` institutions, except verified owners of the 114 WS10 transfers (R-077, item 23 ii).
- N-002 [SOURCE:validation plan BL-001]: human validation of the database (the separate G3O validation D001-D005 plan).
- N-003 [USER Q8 b]: publishing the CX-01 transparency/governance indices.
- N-004 [INFERRED]: changing discovery (Stage 1), site pick (Stage 2) or triage (Stage 3) beyond accepting follow-up links into scraping.
- N-005 [INFERRED]: a cross-institution canonical identity service or automatic attribution transfers (SRC-4 boundary). The 114 PI-ruled WS10 transfers are in scope (R-077).
- N-006 [USER 6; INFERRED]: delivering the extract to Kaser (owned by the #175 lane).
- N-007 [INFERRED]: R11 (prevalence restatement) stays deferred.

## Open questions and provisional assumptions

| ID | Question/assumption | Why it matters | Owner | Blocking? | Resolution |
|---|---|---|---|---|---|
| Q-001 | Follow-up link cap | Bounds cost/runtime; R-032 | PI | — | Resolved: hop limit, 3 hops |
| Q-002 | jev confidence thresholds | R-081 | PI | — | Resolved: one threshold, 0.8, all codes; below -> downgrade |
| Q-019 | What "downgrade" means for a low-confidence negative or absence code | R-081 | PI | — | Resolved a: to `unclear` / `unknown` (R-081) |
| Q-003 (resolved part) | 17 ambiguous->no moves | — | PI | — | Ruled a: instrument error; v2.7 jev questions keep generic AI mentions `unclear`; §4.1 unchanged (see R-016) |
| Q-003 (superseded, resolved) | Re-pilot 2 moved 17 institutions ambiguous→no although its wording keeps generic "AI strategy" as ambiguous (SRC-7 L45, = §4.1). Q7 b adopts the wording; does §4.1 stay as is (generic AI = unclear), with those 17 treated as instrument error to fix? | Q7 b framed §4.1 as conflicting; it does not | PI | — | Superseded by Q-003 (resolved part) |
| Q-010 | Which codes require supporting text | R-041 scope | PI | — | Resolved a: positive/substantive only |
| Q-020 | Fuzzy-match metric and threshold for supporting quotes | R-042 | PI | no (PI approves at Stage 3) | Resolved b: calibrated on fixtures at Stage 3, PI approves |
| Q-021 | How the website shows new fields for institutions whose most recent row is v2.5 | R-051, residual of R-053 | PI | — | Resolved a: fields hidden for those rows |
| Q-011 | Rule for back-fill institutions without usable stored text | R-074 | PI | — | Resolved a: re-scrape live (R-074) |
| Q-012 | Final value names for `other_body` / `event_only` | Contract text | PI | — | Resolved P7: keep re-pilot names |
| Q-013 | Does this release subsume the historical WS10 combined correction (114 activities from 64 source institutions to verified owners) or does that stay separate? | Overlaps R-073; D5 requires one combined publication | PI | — | Resolved a: included (R-077) |
| Q-014 | P2: API/site publication carried out by Colin from this plan's handoff | D-007 owner | PI | — | Default accepted ("defaults good"); Colin's acceptance tracked by A-019 |
| Q-015 | P3: wave 5 `r20261023T134656Z-be8a` included only if published on the site at the freeze date | R-070 | PI | — | Superseded by G12 ruling: wave 5 included; back-fill waits for it (R-070) |
| Q-018 | P4: contract label v2.7 (v2.6 = unpushed `052fcb2`, unpublished history); P5: nano extracts follow-up links in the supporting-text call | D-001, R-031, R-050 | PI | no | Defaults accepted |
| Q-017 | Agent-read sample size and strata; PI audit subset size; what a disagreement rate in the sample does to release (block, fix-and-rerun, or release with report) | R-082, A-008 | PI | — | Resolved after Stage 2 counts: R-086 |
| Q-016 | Do future new runs re-review `none` institutions under v2.6 when they are re-drawn? | Interaction with R-071 | PI | — | Resolved a (R-071) |

## Change history

| Version | Delta ID | Changed spec IDs | Change | Approved by/at | Reason | Downstream artifacts superseded |
|---|---|---|---|---|---|---|
| v001-draft1 | — | all | First draft | not approved | Stage 1 | none |
| v001.4 | — | D-001, D-008, R-006, R-032, R-043, R-051, R-055, R-056 (new), R-076, R-077, R-086, R-087 (new), N-001 | Stage 5 PI rulings: DEC-009 a, DEC-011 a, DEC-013 a, DEC-014 b, DEC-015 a, DEC-016 c, DEC-017 b + blind, SD-g, items 20 a, 21 b, 22 b, 23 i/ii, 24 b, 26 a, 27 | Simone Paci, 2026-10-28, chat: "all approved" | Stage 5 adjudication (`Stage5-Rulings.md`) | Plan-Draft task cards touching these IDs (carried into PLAN.md) |
| v001.3 | — | D-002, D-004, R-075, A-001, A-002, Q-003, Q-014, Sign-off | Mechanical fixes SD-a..SD-f from Plan-Draft §0.3 (labels v2.6→v2.7 where they name this contract; nonexistent R-060..R-062 replaced; A-002 aligned with R-042; stale blocking flags; Resources-column table cells) | fix-mechanical, no PI ruling needed | Stage 3 | none |
| v001.2 | — | R-082, R-086, A-018, Q-017 | PI ruling Q-017 (400; Haiku all, Sonnet 100; group × change; PI audits disagreements + 25; release with report); procurement message = G3O issue #134 | Simone Paci, 2026-10-27, chat | Q-017 | none |
| v001.1 | — | D-008, R-055, R-070, R-077, R-085, A-018, C-007, Q-015 | Stage 2 gap rulings G1 b, G7 b, G11 b, G12; RQ-003, RQ-007 yes | Simone Paci, 2026-10-27, chat | Stage 2 gap review | none |
| v001 | — | Status | Stage 1 approved by PI | Simone Paci, 2026-10-27 | Approval gate | none |
| v001-draft9 | — | R-015 | PI ruling SF-007 follow-up a: 8 values replace `genai_evidence`; old rows unconverted until rerun | not approved | Interview | none |
| v001-draft8 | — | R-042, R-053, Q-017, Q-020, Q-021 | PI rulings Q-020 b, Q-021 a, Q-017 deferred | not approved | Interview | none |
| v001-draft7 | — | D-004, R-003, R-015, R-041, R-042, R-051, R-053, R-070, R-071, SC-07, A-007, Q-010, Q-016, Q-020, Q-021 | PI rulings SF-007 c, SF-011 (most recent on site, row per run in backend), SF-012 b, SF-014 i superseded, ii c, SF-015 c, Q-010 a, Q-016 a | not approved | Interview | none |
| v001-draft6 | — | G-005, R-005, R-015, R-044, R-074, R-077, R-081, R-082, R-084, SC-06, A-015, A-020..A-022, N-005, Q-011..Q-013, Q-017, Q-019 | PI rulings Q-019 a, SF-009 b, Q-011 a, Q-013 a, SF-013 b, Q-017 after Stage 2, SF-006 a; P6, P7 accepted | not approved | Interview | none |
| v001-draft5 | — | R-016, R-032, R-081, Q-001, Q-002, Q-019 | PI rulings: 3 hops; one threshold 0.8 all codes, downgrade; SF-008 a | not approved | Interview | none |
| v001-draft4 | — | R-016, R-032, Q-001, Q-003, Q-014, Q-015, Q-018, D-001 | PI rulings Q-001 b, Q-003 a, defaults P2-P5 accepted | not approved | Interview | none |
| v001-draft3 | — | R-006, R-036, R-076, R-082, Q-017 | PI rulings SF-001 b+a, SF-002 a, SF-003 b, SF-004 b | not approved | Spec review | none |
| v001-draft2 | — | A-006, A-010..A-019, SC-08, Quality | Mechanical fixes SF-016, SF-017 from Spec-Review.md | not approved | Spec review | none |

## Sign-off

- Spec review: `Spec-Review.md` (17 findings; 2 mechanical applied; 15 ruled by PI)
- Approved by/at: Simone Paci, 2026-10-27, chat: "approved" (session `20261027-claude-v2-3d85fb1367912304`)
- Locked by/at (Stage 6 baseline): —
- Delegated inferences accepted: all items tagged INFERRED in v001 (R-003 background_only, R-034, R-043 length limits open, R-051 API exposure to Stage 3, R-074 re-fetch record, R-075, R-090, C-007, N-004..N-007)
- v001.4 approved by/at: Simone Paci, 2026-10-28, chat: "all approved" (session `20261028-claude-v2-20be995c13d4020f`)
- Open before lock: none
