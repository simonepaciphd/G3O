# Classifier question load and cost: codebook v2.7 rulings (round-2 item 52, R2C35)

Status: count and estimate only, for the PI's trim-or-keep decision. No recommendation. Free local analysis, 2026-10-29, by a subagent (Claude Code, `claude-opus-5-5`). No paid call was made and no key was read.
Inputs: `planning/t010/codebook-review/codebook-rulings-round1.json` (91 items) and `-round2.json` (62 items); SPEC/PLAN/RESOURCES; the evidence files below.
Path keys: **[RCE]** = `H:/My Drive/Research/G3O/archive/planning-drive-copy-superseded-2026-10-26/launch-analysis-pr/index-design/recode-cost-estimate.md`; **[PIL]** = same folder `pilot/PILOT-REPORT.md`; **[CXP]** = same folder `codebook-extension-proposal.md`; **[UCS]** = `H:/My Drive/Research/G3O/agent-workspace/2026-10-27-unclear-screen/`; **[JCR]** = `H:/My Drive/Research/G3O/agent-workspace/2026-09-27-jev-compare/REPORT.md`; code paths are in `C:/Users/spaci/repos/G3O` (branch `planning/reclass-v2.7`).

## 0. How jev is billed: the key fact for reading the counts

- Price: $0.042 per million input tokens, output free, no batch, no caching (`g3o/common/pricing.py:82-83`; [RCE]:81). [JCR]:121 records this as UNVERIFIED against a TypeSafe bill. [RCE]:81 notes it matches wave-4 spend in order of magnitude.
- One request = one state (page text) plus any number of questions, "evaluated in parallel against the same state" (`g3o/common/jev_client.py:166-169`). The limit is 64k tokens per request: 32k state plus the longest question (`jev_client.py:36-38`).
- Measured usage: 19 questions in one request came to 5,430 input tokens per page (1,547,614 / 285; [PIL]:11, :13; text truncated at 40k chars). One question per request came to 6,225 tokens per page (2,315,883 / 372; `[UCS]report-repilot2.json`). The page text is counted once per request, not once per question.
- So the **cost driver is requests × page tokens**. Questions add only their own wording, about 0.24–0.37k tokens each (4.5k–7k for 19 questions, [CXP]:129). The number of questions matters mostly through two things: how many **sequential rounds** the gates force (each round re-sends the page), and how many **separate units** get a request (activity, quote, pair).

## 1. Every classifier question implied by the rulings

Pass: P = page pass (per page × chunk); S = segmentation; A = activity pass (per page × activity × chunk); Q = quote check; C = consolidation (Stage 6). Rounds follow R2C05 a: gate items are asked first, then the quote, support and confidence downgrades are applied, then dependent items are asked.

| # | Item (ruling ids) | Pass / round | Gate (when asked) | Options |
|---|---|---|---|---|
| 1 | Page verdict (C01, R2P01 a, R2C01 b) | P1 | every reviewed page | 8 asked; 9th `not_assessable` set mechanically. **Ambiguous**: R2C01 "re-test the verdict question" may mean all 9 are asked |
| 2 | `disclosure_form` (X01, R-020) | P1 | every page; no gate ruled. X16: the first chunk's value is used | 7 (CX-10, 10b, 12, 14–17) |
| 3 | `source_type` remainder (X21, R2C19 a, R2P12 a) | P1 | only when not set by the domain (X37) or the archive URL | 7 |
| 4 | `disclosure_scope` (X02) | P2 | form ∈ {two register values, `mandated_report`} | 4 |
| 5 | Page refers onward / completeness (X17) | P2 | 5 GenAI-bearing verdicts (R-003) | 2 |
| 6–7 | `content_contact` named, details (X06, CX-51 w4, R2C24) | P2 | GenAI-bearing (X05); reads main + footer text | 2 each |
| 8 | `content_data` (X05) | P2 | GenAI-bearing | 2. **Ambiguous**: not in R2C10's derived list, so it may still be a question |
| – | `content_purpose/tool_or_model/vendor/users/status_date` (R2C10 a); safeguard `content_*` (R2C09 a) | – | derived from activity codes | 0 questions |
| 9 | Span relation within page (C07, R2C15 a) | S | each extractor span on GenAI-bearing pages | 7 (6 relations + not an activity). **Ambiguous**: one Choice per span, or one per span pair |
| 10 | `activity_type` (C08; the applicability key, R2C03 b) | A1 | every activity on the 5 verdicts (R2C28 a) | 6 |
| 11 | `action_type` (A02 narrowed by R2C12 c) | A1 | all | 5 (deployment, governance, staff_training, program, unknown) |
| 12 | `adoption_stage` (C09) | A1 | all | 6 (`contract.py:127-128`) |
| 13 | `procurement_status` (C09, R2P08 a) | A1 | all | 5 |
| 14 | Relationship to the searched institution, incl. attribution role (A05, R2P05 a, R2C16 a) | A1 | all | 5–8. **Ambiguous**: whether a separate v2.6 "role" Choice stays (would be +1 question) |
| 15 | `genai_mechanism_basis` (A01, R2C18) | A1 | **Ambiguous**: confirms_activity only (A01) or all 5 verdicts (R2C28) | 4 |
| 16 | `service_domain` (R2C34 a) | A1 | all | short list + 2; length not ruled |
| 17 | `evaluation_documented` (X03, R-022) | A1 | all | 5 |
| 18–19 | Outcome kind, incident kind (CX-61; R2C06 b) | A1 | all; the signed item is the only gate | 3 each. Incident may get +1 value for "discontinued" (R2C30). **Ambiguous**: whether C23's incident-type Choice survives R2C06 |
| 20–23 | Human oversight, transparency/notification, data classification, risk assessment (C18–C21, R2C09 a) | A1 | all | 4 each |
| 24 | `year_announced` (C16, R2C26 a) | A1 | only when ≥1 candidate year was extracted | k candidates + unknown |
| 25–26 | `model_origin`, `build_arrangement` (C10) | A2 | tool activity types (R2C03 b table) | 4 each |
| 27 | `interface` (C11 as cut by R2C11 b) | A2 | tool types | 5 |
| 28–35 | Eight function yes/no items (C11) | A2 | tool types | 2 each |
| 36–37 | `deployment_mode` (C14), `target_users` (C15) | A2 | tool types | 3, 4 (`contract.py:152-153`, without `_NA_`) |
| 38–39 | `year_pilot_start`, `year_production_start` (C17, R2C26 a) | A2 | tool types, ≥1 candidate year | k + 1 |
| 40 | Scale unit (A09) | A2 | tool types, scale span found | 5. **Ambiguous**: R2C08 lists scale as coded by the quote step (0 jev questions) |
| 41–43 | `governance_form` (A03), `governed_population` (A04), `governance_direction` (R2C31 a) | A2 | governance type (policy_guidance) | 6, 4, 5 or 6 (R2C31's wording "requires or promotes" reads as one value or two) |
| 44–49 | `evaluation_type_*` ×6 (X04) | A3 | `evaluation_documented` still positive after the R-041 and R-081 downgrades | 2 each |
| 50 | Quote entailment (X35) | Q | every positive or substantive code whose quote passed the presence check (R-042) | 2 (true/false) |
| 51 | Activity pair relation (X30, R2C15 a) | C | every pair of an institution's activity observations, incl. those on the 4 non-confirming verdicts (R2C28); deterministic skip only for obviously distinct pairs | 6 |
| 52 | Pooled field re-ask (X31, R2P26 a) | C | each merged activity with ≥2 sources | the applicable items 10–49, split into parts when too long |

No classifier question (deterministic or derived): institution verdict (X29, R2P10), evidence tier (A06, R2C13), summary (X33), confidence (X23, R2C21), uncertainty flags (X24, R2C30), credibility (X22), language (X27), dates (X26, A08), review counts (A07), official domain (X37), syndication (X38). Extractor-only, not a classifier: spans, tool and model names, developer and contracting party (R2C18, R2P02), quotes, scale span, follow-up links. Procurement contract terms (P05, R2P09) and the AI-text items (P09–P12) sit outside the web pipeline's load.

## 2. Per-unit counts

**Questions** (from §1; typical = without the ambiguous extras):

| Unit | Typical | Max | v2.5 production (for comparison) |
|---|---|---|---|
| Page × chunk, non-GenAI page | 2–3 (items 1–3) | 4 (+ scope) | 0 jev; one gpt-5-nano generation per page codes `genai_evidence` (4 values) and the Group D fields (`contract.py:215-230`) |
| Page × chunk, GenAI-bearing page | 6–7 (1–3, 5–7, ±3) | 8 | same |
| Segmentation, page with s spans | s | s + s(s−1)/2 if asked per pair | none |
| Activity × chunk, tool type | 30 (15 core + 15 tool) | 38 (+ scale, role, 6 eval types) | none (nano) |
| Activity × chunk, governance type | 18 (15 core + 3) | 26 | none |
| Quote checks per activity | = number of supported positive codes (k_q, unmeasured) | ≈ 30 | none (v2.5 has no entailment check) |
| Stage 6, institution with n activity observations | n(n−1)/2 pairs + Σ(merged activities × applicable items) | same | one request: pairs with differing names + field conflicts + 1 summary Choice (`g3o/validate/jev_validate.py:87-202`) |

**Requests** (what is billed): page pass = c × (1 + g); segmentation = g; activity pass = g × a × c × (2 + e); quote checks = g × a × k_q + page-level k_p (each is a small-state request). Here c = chunks per page, g = GenAI-bearing share of pages, a = activities per GenAI-bearing page, e = share of activities that reach round A3.

**Tokens per page** (T = page tokens, q ≈ 0.3k per question):
`T + 3cq` (P1) + `g(T + 5cq)` (P2) + `gT` (S) + `g·a·[(2+e)T + c(30–31 + 6e)q]` (A) + `(g·a·k_q + k_p)·w` (Q, w = quote-window tokens) + Stage 6.

## 3. Volumes, evaluated load and cost

| Parameter | Value used | Source |
|---|---|---|
| Back-fill institutions | 9,705 documented + 27,648 unclear = 37,353 | `planning/SPEC.md:119` (R-070), `planning/PLAN.md:2750` |
| Pages, documented institutions (all pages, R-076) | ≈86,100 (82,100–90,100); 8.87 pages per institution | [RCE]:75-76 |
| Pages, unclear institutions | ≥58,654 (ambiguous pages with text only); all-page count not yet measured (T-001) | `[UCS]count-pages.json:3`; `planning/PLAN.md:309` |
| Illustrative all-page bound, unclear | 27,648 × 6.81 = 188,283 (6.81 = Stage-5 jobs per institution, n = 100 run) | [RCE]:78. **Assumption**, not a measurement on unclear institutions |
| T, page tokens | 6.3k central (3k–15k) | [RCE]:78; 963,894,721 bytes / 58,654 × 0.3947 = 6.5k (`[UCS]count-pages.json:5,7`) |
| c, chunks per page | 1.18 mean (354 of 372 pages in 1 chunk; max 23) | computed from `[UCS]answers-repilot2.jsonl` |
| g, GenAI-bearing share | 0.2 / 0.3 / 0.5 scenarios. 0.195 = finding pages / all pages, documented (1.73 / 8.87); 0.507 = 188 / 371 ambiguous pages, re-pilot 2 | [RCE]:73,75; `[UCS]report-repilot2.json` |
| a, activities per GenAI page | 1.25 (v2.5: 17,475 findings × 1.20 evidence rows / 16,790 finding pages); 2.0 high scenario | [RCE]:71-74 |
| e, share reaching A3 | 0.2 (60 / 285 pages had evaluation documented, an inflated rate) | [PIL]:41 |
| Per wave | ≈81,219 pages extracted (wave 4) | [RCE]:110 |
| Followed links (R-031..R-035), URL cap, reruns | not included. The cap is unset (T-025). Reruns: ×1.1 central, ×2 high | `planning/SPEC.md:87`; [RCE]:80 |

**Evaluated jev tokens per page** (P1 + P2 + S + A; quote checks and Stage 6 excluded): low (g 0.2, a 1.25) 16.5k; central (0.3, 1.25) 21.1k; high (0.5, 2.0, e 0.3) 40.6k. One v2.7-style verdict-only pass is T ≈ 6.3k. The activity pass is 38% (low) to 64% (high) of the total.

| Run | Pages | jev cost, low – central – high (at $0.042/Mtok) |
|---|---|---|
| Back-fill, documented pages only | 86,100 | $60 – $76 – $147 |
| Back-fill, documented + measured unclear pages | 144,754 | $101 – $129 – $247 |
| Back-fill, documented + illustrative all unclear pages | 278,400 | $193 – $247 – $475 |
| Per wave (g 0.1 / 0.3, a 1.25) | 81,219 | $41 – $72 |
| Comparison: one verdict-only pass over the same pages | 144,754 / 278,400 | $38 / $74 |

Add-ons that are not evaluated (parameters):
- **Quote checks (X35):** tokens = pages × (g·a·k_q + k_p) × w. k_q, k_p and w are unmeasured. Sensitivity: each 1k tokens of w at k_q = 15 and g·a = 0.375 adds about 5.6k tokens per page (~$34 on 144,754 pages).
- **Stage 6:** in v2.5 the state is about 4–6k tokens per institution, ≈ $0.17–0.25 per 1k institutions (`jev_validate.py:14-16`). v2.7 adds the X31 re-asks and all pairs, O(n²) in activity observations per institution.
- **Extractor (Claude Haiku 5.5, Message Batches):** no Haiku price or batch discount appears in SPEC, RESOURCES, PLAN or the deltas. Cost = Σ calls × (input tokens × p_in + output tokens × p_out) × (1 − batch discount), with **p_in, p_out and the discount unfilled**. Calls per GenAI-bearing page ≥ 1 (spans) + 1 per support round (P, A1/A2, A3). PLAN already lists "~8 sequential Batch rounds per run" as a risk (`planning/PLAN.md:3591`).
- **Re-scrape** of pages without stored text (994 of 27,648 unclear institutions; `planning/SPEC.md:124`): unlocker cost, in [RCE]:64.

Every jev figure is a projection from pilot token counts at an unbilled rate. T-002 (`planning/PLAN.md:359-440`) is the card that measures real cost per 1k pages.

## 4. Where the load comes from (descriptive)

1. **The activity pass as a whole** (R-003, R-004, R2C28 a): every (page × activity × chunk) on 5 verdicts re-sends the full page text. It is the largest token share in every scenario.
2. **Sequential gating rounds** (R2C05 a, R2C03 b, X04): 2 page rounds and 2–3 activity rounds. Each round is one more full-page request. The A3 round exists only for the six `evaluation_type_*` items.
3. **Largest question families** (question-text tokens and wording or test burden): the eight function items (C11), the six `evaluation_type_*` items (X04), the four safeguards (C18–C21), the three year Choices (C16, C17, R2C26), and the 15-item core added by C09, C10, A01–A05, R2C31 and R2C34.
4. **Unit multipliers outside the page:** quote entailment (X35) adds one request per supported code. All-pairs consolidation (X30) grows with n². Pooled re-asks (X31) repeat the activity question set per merged activity.
5. **Volume parameters:** the unclear institutions' all-page count and the URL cap move the total more than any single item does.
