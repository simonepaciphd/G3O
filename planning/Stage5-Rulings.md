# Stage5-Rulings.md — G3O pipeline reclassification, Stage 5 PI rulings

Date: 2026-10-28
Session: `20261028-claude-v2-20be995c13d4020f` (Claude Code, claude-opus-5-5, researcher persona)
Relayed in chat, in batches, from Plan-Draft.md §8 (DEC-001..DEC-018), the 2026-10-27 Stage 4 relay (revised options and items 20-26; transcript `eb37db11-…jsonl`) and one new item (27). Source letters kept.
Plan-Review.md and Plan-Draft.md stay unchanged for provenance (`planning-adjudication-protocol` v0.3); finding dispositions are carried in PLAN.md.

## PI answers (verbatim)

- Batch 1: "1c, why can't it carry new features? can't we simply extend it? 2 a 3 b 4 a" → after explanation, "can we not record reclassifications as new rows in the database? As if they were new runs?" → after explanation, "fine let's do a"
- Batch 2: "all as rec"
- Batch 3: "all as rec ok" (also accepted adding item 27)
- Batch 4 + batch 5: "reviwed all these and the following batch from source, accept all the recommendations and move forward"
- Batch 6: "all good,"

Note on batch 5: its recommendations (DEC-017 b + blind, DEC-018 b, SD-g confirm) were first stated in the same message that relayed batch 6, after the PI's acceptance; the PI's "all good" answered that message.

## Rulings

| Item | Ruling | Notes / consequence |
|---|---|---|
| DEC-001 correction layer | **a** — new g3o-api correction tables linked to original observation ids + most-recent projection view; loader reuses `backfill_verdicts.py` safety pattern (dry-run default, shared parse function, explicit refresh + watermark check) | c rejected: in-place UPDATE of `g3o.sweeps` breaks R-073 and cannot map 1:N activities. b / b′ (flagged run rows) rejected: C-005, wave windows, silent-miscount risk |
| DEC-002 back-fill entry | **a** — new `backfill` command, Stages 4-7 on fixed list from stored pages, no re-triage | |
| DEC-003 link following | **b** — separate follow-up leg after pass 1, ≤3 hops; option d (synchronous nano for follow-up legs) decided after T-002 latency/cost | d is orthogonal to placement |
| DEC-004 jev answer storage | **a** — per-institution JSON artifacts + DB columns (confidence, model id, request id) + full distribution in jsonb; API does not serve the distribution column | API exclusion goes to T-050 |
| DEC-005 per-row contract version | **a** — explicit `contract_version` column on every CSV/DB row | Needed for correction rows under DEC-001 a |
| DEC-006 fixtures | **c** — synthetic for mechanics (hops, dedup, chunk combination), real pages for verdicts/CX; real ones labelled by agent then PI | |
| DEC-007 fuzzy matcher | **a** — pinned library (e.g. rapidfuzz); threshold from T-003, PI approves (Q-020 b) | |
| DEC-008 page chunker | **c** — split by estimated tokens, halve-and-retry kept as fallback; T-002 confirms the estimator | |
| DEC-009 free-text routing | **a** — proposed table (jev Choice: `year_announced`, `year_deployed`, CX-60/61; deterministic: contact emails, explicit years; nano: `activity_name`, `tool_name`, `vendor`, `reported_outcomes`, `reported_incidents`, `scope_notes`) | |
| DEC-010 segmentation → pass 2 | **a** — nano returns character spans only; jev sees page with span marked | |
| DEC-011 Sonnet 100 draw | **a** — proportional to strata of the 400, fixed seed | With item 27 → 25 per stratum |
| DEC-012 integrator | **a** — a researcher session acting for the PI, started by Simone | Sole CHANGELOG / delta-log writer |
| DEC-013 version labels | **a** — extract v2.7 + validate v1.5 (skip v1.4) | |
| DEC-014 D-008 timing | **b** — after T-041 passes, before deploy | |
| DEC-015 API older rows | **a** — default most recent; older rows via history parameter/endpoint | |
| DEC-016 supporting-text length | **c** — cap on website only, full text in API; cap value proposed by agent after T-003, PI sets | |
| DEC-017 agent-read unit | **b** — institution verdict + page verdicts; agents read **blind** (no pipeline codes shown) | |
| DEC-018 v2.6 reuse | **b** — rewrite against jev Stage 6; `052fcb2` reference only, its 30 fixtures as tests | |
| SD-g | **confirm** both R-086 inferences: disagreement = agent read vs v2.7 output and Sonnet vs Haiku on overlap; proportional Sonnet draw | |
| 20 PF-003 unclear institutions' other pages | **a** — reclassify every page of unclear institutions | SPEC delta (R-076); cost sized by T-001/T-002 before paid gate |
| 21 PF-009 runs between deploy and release | **b** — ordinary runs load; v2.7 rows hidden until release (reuses PF-006 release flag) | |
| 22 PF-010 link fan-out | **b** — hop limit + per-institution URL cap, value set by PI after T-002 | SPEC delta |
| 23 PF-011 114 WS10 transfers | **(i) on top of the 400** as own stratum; **(ii) include** owners currently `none` | (ii) SPEC clarification vs N-001 |
| 24 PF-015 publication model | **b** — keep waves; PI opens new windows; plan adds a check before w001 expiry (2027-01-01) | |
| 25 PF-019 Colin | **(i) GitHub issues** on g3o-api / g3o-website; **(ii) fallback** engineer session under PI sign-off | |
| 26 PF-022 §4.3 amendment | **a** — rides in v2.7 | v2.7 scope depends on procurement wording |
| 27 allocation of the 400 | **equal, 100 per stratum**; overall figures reported weighted | New item (gap in R-086 / T-080) |

## Procedural defaults accepted (2026-10-27 relay, unchanged)

Mechanical: PF-004 guard + snapshot; PF-013 audit trail; PF-025..PF-027 references and edges. Plan questions: PF-001 second quote step after pass 2; PF-002 quotes per chunk; PF-006 audit before public; PF-007 aggregates and views ownership; PF-008 wait for wave 5 before deploy; PF-014 assign every file; PF-018 integration test; PF-020 notice to the validation plan; PF-023 bulk export.

## SPEC deltas implied (to the integrator; SPEC not edited)

Applied as SPEC v001.4 (APPROVED by Simone 2026-10-28, chat: "all approved"): D-001, D-008, R-006, R-032, R-043, R-051, R-055, R-056 (new), R-076, R-077, R-086, R-087 (new), N-001. SD-a..SD-f were already applied in v001.3. Stage 6 lock requires v001.4 approved.
