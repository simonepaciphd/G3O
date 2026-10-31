DRAFT — not sent; held for Simone (T-063; DP-063 ruled 2026-10-31)

# Heads-up to the multilingual subproject: a calendar and fiscal-year conversion rule is needed

To: the multilingual subproject, `H:/My Drive/Research/G3O/subprojects/multilingual-pipeline/` [addressee: Simone is reviewing the subproject and will contact Litong; see open item 1]
From: the integrator of the G3O pipeline reclassification plan
Date: [filled in at sending]

## The request

The G3O pipeline's new codebook (release 2.7, signed 2026-10-30) codes the year an activity was announced, piloted and put into production. The signed rule says that year candidates are "converted from other calendars and fiscal years under a multilingual-subproject rule". That rule does not exist yet. We are asking your subproject to own and write it.

The items that need the rule:

| Codebook item | What it codes |
|---|---|
| `core.year_announced` | Year the page says the activity was first announced |
| `core.year_pilot_start` | Year the pilot started |
| `core.year_production_start` | Year production started |

How these items work today, as signed: the pipeline extracts every four-digit year from 2015 to 2030 in the activity's text and context, and a classifier picks one of those years or `unknown`. There is no fallback to the page's publication year. The conversion rule would decide how years written in another calendar, or as a fiscal year, become candidate years.

No other item in the codebook refers to this rule.

Questions the rule will need to settle (for your subproject to answer; we do not propose answers):

1. Which calendars and fiscal-year conventions are in scope?
2. How does a fiscal year that spans two calendar years map to one year?
3. Is the rule set per country or per language?

## Two related items for your subproject

1. **Language coverage is your item.** The codebook has an item `core.language_coverage`, marked as owned by the multilingual subproject. Its definition reads "Defined with the language-readiness bar", that is, with your subproject's readiness bar. In release 2.7 it is tagged for the procurement and AI-text pipelines.
2. **The language-barrier flag is dropped.** The pipeline's `source_language_barrier` flag is removed everywhere. Language coverage is carried by your item instead.

## Timing

The rule is an input to the step that builds the pipeline's v2.7 classifier questions (card T-011). The year questions in that step wait for the rule; the rest of that step can go ahead without it. That step is scheduled after the current wave of work, but **no date has been set**. If your subproject cannot supply the rule before that step, please tell us; the year questions then stay paused.

[Target date: Simone to decide when she contacts the subproject.]

## What we are not asking

We are not asking your subproject to change the pipeline code, and this plan does not write the rule or edit your subproject's files.

Reply: people by email to Simone; agents by a comment on the GitHub issue or pull request that carries this request.

## Sources (pipeline reclassification plan, `C:/Users/spaci/repos/G3O/planning/`)

- Request and both related items: SPEC D-010; RESOURCES RS-040; RC-D-002 L (procedural point), governance schedule N23 and N43; rulings r2#50 (year method), r2#39 and P16 (language coverage, flag dropped).
- Year items and signed rule text: `codebook/codebook.yaml` release 2.7 (sha256 `f0b1348c…c72f`; re-signed 2026-10-30, superseding `d24bbc7c…0764`), items `core.year_announced`, `core.year_pilot_start`, `core.year_production_start` (refs C16, r2#50).
- Language coverage: `core.language_coverage` (status "slot (owned by the multilingual subproject)"; refs P16, r2#39). Flag dropped: `core.uncertainty_flags` rules (refs X24, r2#39).
- Timing: RC-D-002 M, O6 ("T-011's year questions wait for the calendar rule"); PLAN T-011 (wave W3), T-063.
- Signature: `planning/t010/signoff-record.md`.

---

## Internal — remove before sending

### Open items for the PI

1. **Addressee and channel: ruled 2026-10-31, held with Simone.** "I will look into the multilingual & reach out to Litong (he hasn't worked on it for a while)"; "agents should work through git issues/PRs, humans email". Simone contacts Litong by email; nothing is sent by an agent until she says so. The subproject has no repo of its own (it lives in Drive), so any agent-side copy would go as an issue on `simonepaciphd/G3O`.
2. **Scoping questions: ruled 5 a** (listed above). **Target date:** not ruled; left to Simone's contact.
3. **Other date fields: ruled 7 a.** The request stays with the three year items; `core.source_publication_date`, `core.content_status_date`, `core.date_upper_bound` and the 1 November 2022 cutoff are not raised.

### Observations for the plan integrator (not for the recipient)

- In the signed codebook, rule 1 of `core.year_pilot_start` and `core.year_production_start` repeats the announced-year question verbatim ("In which year does the page say this activity was first announced?"). This may be intended as the shared method text, but T-011 should not copy it as the pilot or production question without checking.
- `core.language_coverage` lists pipelines `procurement` and `ai_text` only, not the main pipeline. The heads-up states this as it stands.
- The subproject's `CLAUDE.md` still points its skills library at the retired Dropbox AI OS path. Not raised in the heads-up; outside this card.
- The card names `C:/Users/spaci/repos/G3O/planning/handoffs/`; this draft is in the integrator worktree.
