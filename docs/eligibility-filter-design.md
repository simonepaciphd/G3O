# Design memo — NLP eligibility pre-filter between discovery and Stage-3 triage

Status: SIGNED OFF by PI 2026-07-06 (decisions recorded below), AMENDED by PI
2026-08-01 (see "Amendments"). Drafted 2026-07-05 on branch
`feature/eligibility-filter-design`, baseline main @ `85fc694`. Implementation
delegated to the Data Validation Team RAs — see `RAs/Data Validation Team/
instruction-briefs/2026-07-06 Eligibility Filter and First Live Funnel Runs.md`
(Drive).

## Amendments (PI, 2026-08-01)

Two corrections raised during the rebase review of PR #9 and ruled on by the PI.
The original text of decisions 4 and 6 is preserved below; these amendments
govern where they conflict.

**A1 — decision 4 amended: a narrow host list is now in scope.** The original
decision read "path/file-type patterns only — no domain-level blocklists", but
the Option 1a text below names URL shorteners and social-media profile pages as
drop categories, and neither can be recognized from the path. That
contradiction was escalated as GitHub issue #8 and is now resolved: **1a may
carry a deliberately short host list covering those two categories and only
those**, to be expanded later as shadow data shows what else is worth adding.
Everything else remains path/file-type only. The list is a collection decision,
so additions require a signed amendment — not a commit. Implemented in
`g3o/classify/eligibility.py::host_rule_hits`. Issue #8 can close.

**A2 — the shadow-recall metric is restated in decision 6's direction.** The
Mechanics section below originally defined it as `would_drop ∩ llm_keep /
llm_keep`, which is the *complement* of the bar decision 6 states ("≥70% of
LLM-kept URLs must also pass the filter"). Reporting the complement under the
name "recall" meant a value of 0.75 — 75% of LLM-kept URLs discarded, a severe
failure — read as comfortably clearing a ≥70% bar. The metric is now
`pass ∩ llm_keep / llm_keep`: **higher is better, and it is compared against the
70% bar directly.** The complementary disagreement count is still reported
alongside as `llm_keep_and_would_drop`.

**Not amended.** Decision 3 stands: the rule and vocabulary lists are still
DRAFT (`RULES_VERSION = "1c-draft-2026-08-01"`) and require PI sign-off before
`enforce` gates any live run. `shadow` remains the default and drops nothing.

## PI decisions (2026-07-06)

1. **Filter tier:** Option 1a+1b (URL-pattern rules + per-language keyword screen).
2. **Mode:** shadow first; `enforce` only after PI reviews shadow metrics.
3. **Vocabulary/rules:** drafted by the RAs with a more advanced/nuanced
   regex-based approach (inflection, per-script boundary handling); PI signs
   the lists before anything gates a live run.
4. **URL-pattern scope:** path/file-type patterns only — no domain-level
   blocklists. PI expectation: low-fire-rate/high-signal rules (accept high
   false negatives, keep false positives near zero).
5. **Stage shape:** named stage `filter_eligibility` confirmed (own artifact,
   `.done` marker, `--stop-after` value, health-report block).
6. **Shadow recall bar (provisional):** ≥70% of LLM-kept URLs must also pass
   the filter, per language, before `enforce` is considered — reviewed
   manually against actual disagreements when the data exists.

## Problem

The English discovery roster was expanded 4→8 terms on 2026-07-04
(`g3o/discovery/query_builder.py:22-31`), roughly doubling English candidate
volume, with two loose terms ("AI chatbot", "AI assistant") accepted knowing
they pull in noise. Stage 3 sends the full path-aware deduped union of all
1a∪1b URLs to the LLM triage classifier, one Batch job per institution
(`g3o/run/presweep/stage_classify.py:162-183, 214-243`; dedup key:
`g3o/run/presweep/records.py:58-77`), so triage cost scales roughly linearly
with candidate volume. This memo designs a deterministic, language-aware
pre-filter that drops clearly-ineligible results cheaply before triage —
the precision counterweight to the broadened discovery, without re-narrowing it.

## Facts the design rests on (verified this session)

1. **The filter has more text signal than the classifier it protects.** Each
   1a/1b record carries `title`, `link`, `snippet`, `domain`, `position`,
   `date` (`g3o/discovery/serper_client.py:166-172`) plus `query` and
   `language` (`stage_discovery.py:103`; `site_domain` in 1b,
   `stage_discovery.py:187-189`). Stage 3's prompt contains only the
   institution record, the official site, and **bare URL strings** — no titles
   or snippets (`g3o/classify/url_triage.py:104-118`). Two consequences:
   (a) a snippet-based filter is not redundant with the LLM; (b) in shadow
   mode, LLM keep/drop decisions are a *comparison baseline*, not ground
   truth — disagreement ≠ error, in either direction.
2. **Triage is deliberately recall-first** ("when uncertain, prefer keep",
   `url_triage.py:46-47`). The filter must be strictly more conservative.
3. **Deterministic stages have a ready-made slot.** Stages 1a/1b/4 write a
   `no_batch` `.done` marker (`g3o/common/run_state.py:38, 199-220`); resume
   is auto-inferred from disk (`run_state.py:91-93`). A new deterministic
   stage inherits all of this for free.
4. **Attrition and health plumbing exist.** `attrition.record()` takes
   (institution_id, stage, reason, url) with resume-safe dedup
   (`g3o/common/attrition.py:78-119`). The health report auto-detects whether
   a stage ran (`g3o/report/health.py:101-124`) and already computes
   per-language funnels from the record `language` tags
   (`health.py:137-158, 681-726`); thresholds are PI-tunable
   (`g3o/report/thresholds.py`).
5. **Language-aware regex needs care.** `_compile_keyword_pattern`
   (`g3o/validate/qc.py:109-127`) asserts `(?<!\w)`/`(?!\w)` boundaries. In
   continuous CJK script, kanji/hanzi are word characters, so "生成AI" inside a
   Japanese sentence would *fail* to match. Reuse the helper for space-delimited
   scripts; compile bare-substring patterns for `ja`/`zh`. Non-English rosters
   are also smaller (4 terms vs English's 8; 3 for `ar`/`fi`,
   `query_builder.py:32-40`) — pass-rate comparisons must be read against that.

## Options

### Option 1 — deterministic rule screen (stdlib regex; two independent parts)

**1a. URL-pattern screen (negative rules).** Drop URLs that are structurally
non-content: URL shorteners, login/auth/search-results paths, calendar/feed
files, sitemaps/robots.txt, social-media profile pages — the same categories
the triage prompt already names as drops (`url_triage.py:40-44`), decided from
the URL string alone. Language-neutral by construction. (Shorteners and social
profiles are host-recognized; see amendment A1. A social *post* is kept — only
the bare profile shape is dropped.)
*Cost:* zero deps, negligible runtime; a small PI-signed rule list.
*Failure mode:* a real evidence page living on an odd URL shape (e.g. evidence
inside a search-result-like permalink) is wrongly dropped. Narrow rules keep
this rare. *Shadow detection:* would-drop ∩ LLM-keep, per rule.

**1b. Snippet/title keyword screen (positive eligibility).** Require ≥1
GenAI/AI-signal term in `title ∪ snippet` (optionally URL path), matching
against the **union of all language rosters** (a French snippet found by an
English query still passes on French terms). Seed vocabulary:
`GENAI_TERMS_BY_LANG` + the tool/model names in
`qc.py::GENERATIVE_SIGNAL_KEYWORDS` (`qc.py:38-60`) + localized generic terms;
PI signs the final list. **Fail-open:** missing/empty snippet+title → pass.
*Cost:* zero deps; vocabulary curation is a standing PI-owned decision.
*Failure mode:* drops pages whose snippet paraphrases without a roster term,
or where inflection defeats exact match (Finnish case endings; CJK boundaries
per fact 5). Also honest about yield: because 1a/1b queries quote a GenAI term,
most snippets echo it — so 1b's cut is modest; the *topical* noise from
"AI chatbot"/"AI assistant" (vendor spam, aggregators) usually **contains** the
term and passes. 1b mainly removes results whose snippet shows no AI signal at
all. *Shadow detection:* per-language would-drop ∩ LLM-keep rates; a language
with an elevated rate has a deficient roster.

### Option 2 — lightweight statistical scorer (TF-IDF + logistic over snippets)

Train on shadow-mode labels (Stage-3 decisions) from the first live run.
*Cost:* an sklearn dependency (or a hand-rolled logistic to stay stdlib),
a training/versioning pipeline, retraining maintenance.
*Failure modes:* (a) labels are URL-only LLM judgments — the scorer inherits
the classifier's blind spots rather than correcting them; (b) non-English
training data will be thin, so per-language calibration will be poor —
in direct tension with the language-fairness bar; (c) determinism holds only
under strict model-artifact pinning. *Shadow detection:* per-language
disagreement + calibration curves. **Not buildable now:** no live run has ever
completed, so no labels exist.

### Option 3 — small multilingual embedding model (offline, pinned)

Score snippet similarity to eligibility prototypes.
*Cost:* heavy deps (torch/onnxruntime; repo is currently stdlib + pydantic +
requests + tenacity + pytest — this is a flagged PI decision), model-file
distribution, version pinning. *Failure modes:* opaque thresholds
(hard to audit a drop); embedding quality varies by language, risking exactly
the systematic non-English disadvantage the fairness bar forbids; float
nondeterminism across platforms can flip borderline scores.
*Shadow detection:* per-language pass-rate skew + disagreement rates.

**Recommendation:** Option 1 (both parts), run in **shadow mode** first.
Revisit Option 2 only after the first live run produces labels and shadow
metrics show Option 1's recall floor is insufficient. Option 3's dependency
and fairness costs are not justified at snippet scale.

## Mechanics (common to all options)

- **New named stage** `filter_eligibility` inserted between
  `discovery_site_restricted` and `classify_triage` in `STAGES`/`StageName`
  (`config.py:18-35`), called in the orchestrator between 1b and triage
  (`orchestrator.py:141-167`), added to `--stop-after` choices
  (`cli.py:596-612`). Deterministic: `.done` marker with `no_batch=True`,
  idempotent per-institution artifact skip — same shape as 1a/1b.
- **Artifact:** `runs/<run>/<inst>/1c_filter_eligibility.json` — one decision
  per deduped URL: `{url, decision: pass|drop, matched_rules, mode,
  rules_version}`. 1a/1b artifacts are never mutated. Deterministic: pure
  function of the 1a/1b artifacts + a versioned rule set recorded in the
  artifact.
- **Mode flag** `filter_mode: off | shadow | enforce` (config + CLI).
  `off`: Stage 3 consumes the current union unchanged (bypass preserved).
  `shadow`: artifact written with would-drop decisions, **nothing dropped**.
  `enforce`: Stage 3 consumes only `pass` URLs. Proposed default for the first
  smoke run: `shadow`. Enabling `enforce` is a PI decision made on measured
  shadow recall.
- **Attrition:** every enforced drop → one ledger record, stage
  `filter_eligibility`, stable reasons `url_pattern_noncontent` /
  `no_genai_signal`; silent drops forbidden (fixture-tested).
- **Health report:** additive stage block — URLs in / passed / pct passed,
  per-language pass rates (via existing `language` attribution), top drop
  reasons, PI-tunable warn/fail thresholds; in shadow mode, `n_would_drop`.
  Additive-only in `g3o/report/` (RA ticket_0010 is working there; rebase-friendly).
- **Shadow recall metric** (the enable-decision input): after Stage 3, compute
  per-language `pass ∩ llm_keep / llm_keep` — the share of LLM-kept URLs that
  also survive the filter. *Higher is better*, stated in the same direction as
  decision 6's ≥70% bar so the two compare directly (amendment A2; this replaces
  the original `would_drop ∩ llm_keep / llm_keep`, which was its complement).
  The disagreement count is reported alongside. Caveat from fact 1b: this
  measures *agreement* with a URL-only judge; the PI reviews a sample of
  disagreements before treating them as filter errors.

## Out of scope / later

- A similar cheap gate before Stage 5 (post-scrape, pre-extract) — noted, not designed here.
- Non-English roster expansion (separate decision tied to the batch-5 readiness bar).
- Recall/precision tuning — impossible pre-first-run; this memo designs the measurement, the first smoke run supplies the data.

## Decisions for the PI

1. **Filter tier:** Option 1a only (URL patterns), Option 1a+1b (patterns +
   keyword screen), or defer to Option 2/3? (Recommendation: 1a+1b.)
2. **Mode default:** implement `off|shadow|enforce` with default `shadow` for
   the first smoke run; `enforce` only after you review shadow metrics — confirm?
3. **Vocabulary & rule sign-off:** I draft the per-language keyword roster and
   URL-pattern rules; nothing gates a live run until you sign the lists — confirm process?
4. **URL-pattern scope (open item):** are domain-level rules (e.g. known
   press-aggregator or social-media domains) in scope, or path/file-type
   patterns only? Domain blocklists are a collection decision I won't seed
   without direction.
5. **Stage shape:** confirm the named-stage design (own artifact, `.done`,
   `--stop-after`, health block) over a lighter pre-pass inside Stage 3.
6. **Shadow recall bar:** what disagreement level (would-drop ∩ LLM-keep)
   per language would you consider acceptable before enabling `enforce`?
   (No default proposed — this is a substantive collection threshold.)
