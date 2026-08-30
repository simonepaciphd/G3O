# Pipeline status and measured benchmarks

**Last updated: 2026-08-30** (§1.1 added: which population each §1 figure is
about, and what PR #99 did and did not move. **No figure anywhere in this file
is changed, replaced or deleted by that pass** — it names populations that were
already there.)

**Previously last updated: 2026-08-27** (§7 appended: probe run `r20260826T214131Z-4cd7`, n=500, and
its forensics. §§1–6 are unchanged and still carry their 2026-08-02 basis; no figure in them
has been deleted or replaced — see §7.6 for the one that was tested and stands.)

**Previously last updated: 2026-08-02** · Branch of record: `main` (`8877db6`, PR #24 —
the two-query discovery chain is now the shipped default); instrumentation work
on `chore/instrumentation-side-tasks` · Suite: 766 passed, 2 deselected,
1 xfailed · ruff clean

The standing record of **what the G3O pipeline has actually been measured to
do**, stage by stage, and what remains unmeasured. It is deliberately separate
from [`budget/cost-model.md`](budget/cost-model.md), which *projects*, and from
[`architecture.md`](architecture.md), which describes design.

**Reading rule.** Every figure carries its evidence class:

| | meaning |
|---|---|
| **M** | Measured on a live run. Sample size and date given. |
| **T** | A PI-tunable *threshold* in `g3o/report/thresholds.py` — a target, not an observation. |
| **A** | Assumption in a budget or design document. Not evidence. |
| **—** | Not measured. |

Anything marked **A** has already been wrong once by ~4× (the Serper line in
the cost model), so treat the distinction as load-bearing rather than pedantic.

---

## 1. Input registry

| Metric | Value | Class |
|---|---:|:--:|
| Institution master rows | 719,588 | M (2026-08-01) |
| Rows with a non-empty `website` | 14,670 (2.04%) | M |
| …usable after placeholder filtering | 14,134 (1.96%) | M (2026-08-02) |
| — of which national | 1,800 | M (2026-08-02) |
| — United States share of the usable pool | 12,351 (87.4%) | M |
| Distinct countries in the usable pool | 219 | M |
| Rows carrying a `disambiguation` | 217,385 (30.2%) | M |
| Rows with both `duplicate=1` and a `website` | 0 | M |

**Rebuild note, 2026-08-02 — the frame is now code, and the `n/a` rule is fixed.**
The filter that defines this pool lived only in session scratchpads and was
re-typed each session, which is how the count drifted (14,131 → 14,130 across
two rebuilds of the same rule; the residual sits in how malformed URLs like
`http:///www.x.ms` parse). It is now
`g3o/run/presweep/eval_frame.py`, with tests, so the frame every rate below is
computed against is reproducible rather than re-derived.

With PI sign-off, `n/a` is now matched as a **delimited token** rather than a
bare substring. The substring rule **silently dropped four real institutions**
whose URL *paths* contain those characters across a segment boundary —
`e`**`n/a`**`bout`, `fi`**`n/a`**`ccueil`, `e`**`n/a`**`nti`: Bosnia's SIPA
financial intelligence department, Croatia's anti-money-laundering office,
France's TRACFIN and Romania's ASF. All four are national bodies, which is why
the national count moves 1,796 → 1,800 and the pool 14,130 → **14,134**.
`tbd` and `none` were checked against the full 719,588-row master at the same
time and have **zero** such collisions, so they remain substring matches rather
than being changed on speculation.

Consequence for comparability: seed 22294 now draws a different sample than it
did before 2026-08-02. Cross-run comparisons of head-of-funnel rates (§3) must
account for that.

**The single most important number in this document is 1.96%.** Ground truth
for any accuracy metric is the master's `website` column, so every accuracy
figure below is measured on ~2% of the registry — and that 2% is
national-institution-heavy while the other 98% is overwhelmingly US local
government. Yield figures are **national-institution figures, not registry
figures.** Do not project them onto a full sweep.

### 1.1 Which pool a §1 figure is about — and what PR #99 moved

**Added 2026-08-30.** Everything in this subsection is a restatement or a
pointer; **no figure above it changes.** It exists because §1 uses the word
"pool" for two different populations without ever saying so, and after PR #99
(merged 2026-08-30, `2a8e7fb`) the two moved in opposite directions — one by
43%, the other not at all. A reader who does not know which is which will read
the wrong one.

| | what it is | size | who reads it |
|---|---|---:|---|
| **Evaluation frame** | master rows carrying a usable `website`, per `g3o/run/presweep/eval_frame.py` | **14,134** | every accuracy and yield rate in §§2–5 |
| **Eligible pool** | every master row, website or not, per `g3o.run.frame.sampler.is_eligible` | **719,588** | the wave sampler (`g3o frame`), §7's wave-2 frame |

The evaluation frame is a **ground-truth** population: an accuracy rate needs a
known answer to score against, and the master's `website` column is the only one
there is. The eligible pool is a **sampling** population: a wave draws
institutions to go and look at, and not knowing a website in advance is the
normal case, not a disqualification. They are not a subset relation anybody
should reason with casually — 14,134 of 719,588 is 1.96%, and that ratio is
§1's own "single most important number".

**What PR #99 did.** The sampler admitted a row only when the master's
`duplicate` column was `0`. That column flags a **name collision** the
`disambiguation` field resolves — the master's schema says so, and G3O's own
`query_builder` already builds disambiguation-qualified queries for exactly
those rows — not a repeated row. Reading it as an eligibility test excluded
216,642 distinct institutions:

| | before | after |
|---|---:|---:|
| eligible pool | 502,946 | **719,588** |
| excluded as "duplicate" | 216,642 | 0 (now counted as `name_collision`) |

Not uniform: 29.7% of the `local` tier and 44.7% of `second_subnational`,
nothing at `national` or `first_subnational`; by country, India 34.0%, USA
35.2%, Rwanda 71.4%, 67 countries in all. Every frame drawn **after** 2026-08-30
draws from a pool 43% deeper than every frame drawn before it, and the two are
not comparable populations.

**What PR #99 did NOT move, and this is checkable rather than asserted.** The
**14,134 figure above is unchanged.** `eval_frame.py` carried a copy of the same
misreading and it was removed in the same commit — as a **provable no-op**,
because §1's own last row records that **0 of 719,588** master rows carry both
`duplicate=1` and a `website`. A filter that requires a website could never have
rejected one. That is also why the defect survived review for as long as it did:
it could not bite until this module started drawing website-free frames.

⚠️ **So the last row of §1's table is not trivia.** "Rows with both `duplicate=1`
and a `website` = 0" is the load-bearing fact that keeps every rate in §§2–5
standing across PR #99. Do not drop it as an obvious zero.

**Still open, and NOT settled here:** whether the 5,000-institution mix quota,
written against pools 30–70% shallower, still expresses what the next wave is
meant to reach. That is a sampling-design question for the PI, not a
documentation one.

---

## 2. Discovery (Stages 1a → 2 → 1b) — measured

200 institutions per arm, same sample, `--seed 22294`, drawn from the usable-
`website` pool, 120 countries. Credits are `GET /account` balance deltas.
Full report: `agent-workspace/2026-08-01-discovery-chain-validation.md` (Drive).

| Metric | `chain` (default) | `legacy` | Class |
|---|---:|---:|:--:|
| **Serper credits / institution** | **1.84** | 8.52 | M |
| Queries / institution | 1.88 | 8.52 | M |
| **Stage 1a** — institutions with ≥1 URL | 100% | 100% | M |
| URLs / institution (1a) | 8.54 | — | M |
| **Leg-1 recall** — true domain surfaced at any rank | **82.0%** | n/a | M |
| — at rank 1 | 62.5% (125/200) | n/a | M |
| Naive first-non-aggregator pick correct | 60.0% | n/a | M |
| **Stage 2** — official site found | **88.0%** (176/200) | **6.5%** (13/200) | M |
| — correct vs master, of those attempted | 86.9% (153/176) | 100% (13/13) | M |
| — correct as a share of all institutions | 76.5% | 6.5% | M |
| — conversion of leg-1 recall | **93.3%** (153/164) | n/a | M |
| **Stage 1b** — eligible institutions with ≥1 URL | 95.5% (168/176) | — | M |
| URLs / institution (1a+1b, deduped) | 16.07 | 20.48 | M |
| Own-domain URLs | 1,700 | 125 | M |
| Own-domain **relevant** URLs | 759 | 117 | M |
| **Institutions with ≥1 relevant hit** | **64.5%** | 20.0% | M |

Paired McNemar over all 200: **94 gains, 5 losses, exact two-sided
*p* = 2.4 × 10⁻²²**.

### The ceiling chain

The useful way to read discovery is as a sequence of ceilings, because each
stage can only ever pass on what the previous one surfaced:

```
  leg 1 surfaces the true domain          82.0%
    -> Stage 2 converts 93.3% of those    76.5%   correct official site
      -> evidence found on it             64.5%   >=1 own-domain relevant hit
```

Two consequences worth acting on: **leg 1's 82% is the binding constraint** —
Stage 2 is already converting 93% of what it is handed, so effort spent
improving the classifier is capped at ~7 points, while leg 1 has 18 available.
And the 60% naive-pick figure **understates leg 1**; it measures a pick rule
that is not used in production, and should not be cited as discovery accuracy.

### Metric definition (used above, implemented in `g3o/report/discovery_yield.py`)

**Own-domain relevant hit** — a URL on the institution's own registrable domain
(eTLD+1 via the bundled public-suffix snapshot, excluding
`autodiscover.`/`webmail.`-style hosts) whose title, snippet, *or* URL carries a
GenAI signal. The bare `AI` acronym matches **case-sensitively**; multi-word
phrases do not.

Both halves of that definition are load-bearing:

- **Scoring on domain match alone is misleading.** Dropping quotes lifts
  own-domain hits 5 → 20 while relevant hits stay at 5 — fifteen of the twenty
  are bare homepages with no AI content.
- **Case-insensitive `ai` inflates the count** by matching the French verb
  "ai", the Italian preposition "ai", and ebook spam. This produced a wrong
  headline once already.

### Leg-1 query structure — settled by measurement

Same 200 institutions, Stage 1a only:

| | unquoted (shipped) | quoted name | Class |
|---|---:|---:|:--:|
| True domain found (recall) | **82.0%** | 64.5% | M |
| — at rank 1 | 125 | 95 | M |
| Naive pick correct | 60.0% | 45.0% | M |
| Institutions returning **zero URLs** | 0 | 2 | M |

Paired McNemar: 37 unquoted-only wins, 2 quoted-only, *p* = 2.8 × 10⁻⁹. The
quoted-name failure mode the n=24 findings identified **does transfer** to
leg 1. `--discovery-domain-quote-name` exists so this stays reproducible rather
than becoming folklore.

---

## 3. Stages 1c–7 — measured through Stage 4

> **Status 2026-08-03 (superseding both notes below): the run is complete
> through Stage 7.** Every stage of `20260802-e2e-100` is now class **M**. The
> codebook gate cleared first — issue #30 was signed off and landed as contract
> **v2.1** (PR #39) — so the Stage 5/6 figures below describe the schema that
> ships, which is exactly what the hold existed to guarantee.
>
> **Read the code split.** `manifest.json` records no git commit, and the run
> was executed in two halves: **Stages 1a–4 at `191803c`** (2026-08-02) and
> **Stages 5–7 at `917dc29` plus the wave scheduler of PR #40** (2026-08-03).
> Two consequences. First, the Stage 1c row still reports the *pre-retirement*
> rules (`1c-draft-2026-08-01`, 2.2% pass / 3.9% recall) because 1c had already
> completed before PR #38 retired the snippet screen — the 94.8% / 99.5% figures
> in the decision note below are the replay, not this run's artifact. Second,
> Stage 5 ran in **8 token-sized waves** rather than one batch, which slightly
> depresses the measured prompt-cache rate (8 cache-cold first jobs instead of
> 1); see §4.
>
> *Prior status, 2026-08-02:* Stages 1c/3/4 measured, 5–7 held deliberately
> pending the codebook, because Stages 5 and 6 are two of the four Batch stages
> the run exists to measure and their yield, empty rate and token counts would
> otherwise have described a schema about to change.
>
> *Prior hold, 2026-08-02 (resolved):* the run was first prepared and held for
> the same reason; it never applied to 1c/3/4, which no codebook change can
> touch.

| Stage | Measured (n=100, 2026-08-02) | Threshold (T) | Budget assumption (A) |
|---|:--|---:|---|
| 1c filter_eligibility | as measured: **2.2% pass** (36/1,648), **shadow recall 3.9%** vs a 70% bar → **snippet screen retired same day**, giving 94.8% pass / **99.5% recall** | pass-rate bands set | shadow mode, nothing dropped ✓ |
| 3 classify_triage | **51.6% URL keep** (831/1,610); **96%** of institutions with a keep | 70% / 40% institutions with a keep; 30% / 15% URL keep-rate | ~40 URLs → ~12 kept |
| 4 scrape | **99.4% success** (826/831); 0 errors; 5 robots-disallowed; 83 render fallbacks | 70% / 40% success | ~2.4 rendered URLs / institution |
| 5 extract | **90.9% extracted** (619/681 eligible pages) ✓; **17.5% empty-dropped** (145/826 scraped) ✓; 62 parse failures; 71 pages truncated at the 60k cap; 84/100 institutions with ≥1 extract | 70% / 40% success; 30% / 60% empty | ~12 pages / institution → **measured 6.81** (681/100) |
| 6 validate | **96.4% consolidated** (81/84 with extracts) ✓; **50.6% unclear** (41/81) — **the one gauge that misses** its 40% bar; yes 12.3%, no 37.0% | 80% / 60% consolidated; 40% / 70% unclear | 1 call / institution → **84 calls** (only institutions with extracts) |
| 7 persist | 81 institutions → 22 activity rows, 588 activity-source rows, 81 summary rows; **0 load failures** | n/a (deterministic) | n/a |

### What the funnel looks like end to end (n=100, measured)

100 institutions → 846 candidate URLs → 90 official sites → 810 site-restricted
URLs → 831 URLs kept by triage → 826 pages scraped → **681 pages eligible for
extraction** → **619 extracts** → **84 institutions with any extract** → **81
consolidated** → **81 rows shipped**, carrying **22 activities** and 588
activity-source rows.

Two attritions in that chain deserve naming because neither is a failure and
both were invisible before this run:

- **826 → 681 pages** is the near-empty filter: 145 scraped pages (17.5%) had
  under 50 non-whitespace characters and never reached the LLM. This is the
  budget assumption's "~12 pages / institution" landing at a measured **6.81**.
- **100 → 84 → 81 institutions** is not run failure. 16 institutions produced no
  extract at all (no eligible page survived), and 3 more failed Stage 6 parsing.
  Only the latter 3 are defects; the 16 are institutions with nothing readable to
  read, which is a finding about the web, not the pipeline.

### The published outcome: 1 / 56 / 43, and why 43 is the number to fix

`institution_report.csv` for the finished run:

| `final_status` | `validation_status` | n |
|---|---|---:|
| `EVIDENCE_FOUND` | consolidated | **1** |
| `NO_EVIDENCE_FOUND` | consolidated | 42 |
| `NO_EVIDENCE_FOUND` | not_run | 14 |
| `PROCESSING_FAILED` | consolidated | **38** |
| `PROCESSING_FAILED` | not_run | 5 |

**All 43 `PROCESSING_FAILED` rows cite `extract:parse_failed`** — every one traces
to the contract-adherence defect in §5.6. And 38 of those 43 **already have a
Stage-6 verdict**: they are withheld not because the pipeline failed to reach a
conclusion but because the no-evidence publishing rule (PI, 2026-07-28) refuses
to publish "no publicly available information" for an institution whose
processing was incomplete. That rule is working exactly as designed; the defect
is what trips it.

**So a 9.1% page-level defect produces a 43% institution-level suppression.** One
unparseable page is enough to disqualify an institution, so the amplification is
structural, not incidental. That makes fixing `uncertainty_flags` the highest-
value change available to this pipeline by a wide margin — it could return up to
38 institutions to substantive verdicts without any change to the instrument's
judgement. **Do not read 1/56/43 as a prevalence estimate**; read it as one
confirmed positive, 56 defensible negatives, and 43 institutions the pipeline
declined to report on.

**Stage 6's unclear rate is the one gauge that misses, and it is the substantive
result of this run.** Of 81 consolidated institutions, 41 (50.6%) came back
`unclear` on `has_genai_activity`, against 30 `no` (37.0%) and just 10 `yes`
(12.3%) — a warn against the 40% bar. Half the institutions the pipeline can
process end in a verdict that supports no claim either way, and the
contract-adherence defect in §5.6 sits upstream of exactly this number: 62 pages
had their evidence rows dropped before consolidation, which can only push
verdicts toward `unclear`. Whether the residual is model capability, genuinely
ambiguous sources, or that dropped evidence is **unresolved and is the first
thing the next analysis should separate.**

> **2026-08-27, §7.6:** the n=500 probe measures `unclear` at **11.9%**, but on a
> population reading a mean of 2.95 pages per institution against this run's much
> deeper exposure. Within the probe, `unclear` rises from **1.1%** at one page to
> **52.9%** at nine or more — indistinguishable from the **50.6%** above. **The 50.6%
> is NOT superseded.** What the probe does evidence is the parse fix itself:
> `extract:parse_failed` fell from **43/100** here to **3/500** there.

Stages 3 and 4 clear their thresholds comfortably, and so does Stage 5 on both
of its gauges. **Stage 1c did not, and the
gap was not a threshold-calibration problem.** Of the 831 URLs Stage 3's triage
kept, only 32 also passed the 1c draft rules — 3.9% against PI decision 6's
provisional bar of ≥70%. Switching `filter_mode` to `enforce` on those rules
would have discarded ~96% of what the pipeline considers worth reading.

### Decision 2026-08-02 (PI): the 1c snippet screen is retired

`has_genai_signal` is no longer called from `eligibility.evaluate()`. Stage 1c is
now a **URL-hygiene screen only** (path patterns, shorteners, social profiles).
`RULES_VERSION` moves `1c-draft-2026-08-01` → `1c-url-hygiene-2026-08-02` so no
artifact can be misread as having been produced by rules that no longer run. The
function and its lexicon tests are retained, unreachable, for whatever replaces
it.

**Correcting the first write-up of this finding**, which mis-stated the
mechanism. The GenAI screen is **not** a URL-string test — `has_genai_signal`
reads the SERP **title ∪ snippet**; only `url_pattern_hits` looks at the URL. The
real mechanism is that a SERP snippet is not a statement about the page's topic.
That distinction matters because it changes which fix works, and two plausible
fixes turn out not to:

| 1c variant (replayed over the run's 1,648 URLs) | pass | shadow recall | vs 70% bar |
|---|---:|---:|---|
| as run — patterns + snippet screen | 2.2% | 3.9% | fails |
| exempt homepages from the screen | 10.5% | 13.8% | still fails |
| restrict the screen to the 1b leg | — | — | rejected, see below |
| **screen removed (shipped)** | **94.8%** | **99.5%** | **passes** |

Leg 1 asks `<name> <country> official website`, so its snippets describe the
institution and never AI — every homepage failed, which was expected. What was
not expected: **leg 2 fails almost as badly.** Although it asks
`site:<domain> AI`, Google returns the page's generic meta description rather
than an AI-matching excerpt, so 762 of ~802 leg-2 URLs were dropped too — and
*every one* of the 36 survivors was a leg-2 URL. So "restrict 1c to the 1b leg",
floated in the first write-up, would have fixed almost nothing.

**The trade-off, stated plainly:** 1c now removes 5.2% of candidate URLs rather
than 97.8%, so it is a correctness/hygiene stage and **no longer a cost-saving
one**. Any Stage 3 volume reduction that the budget attributed to 1c should be
removed from the model. Screening on page *text* after Stage 4, or on a
better-calibrated lexicon, remains open; the vocabulary machinery is intact for
it, and retuning it belongs to `subprojects/multilingual-pipeline/`.

Thresholds were calibrated for a ~10-institution smoke run and are explicitly
PI-tunable; they were **not** derived from observation. They have deliberately
**not** been recalibrated, and that still holds now that all seven stages are
measured: n=100 is one sample, and fitting the gauges to it is the failure mode
the measurement task was written to avoid. This applies specifically to Stage
6's `validate_unclear_warn_pct` of 0.4, which the measured 50.6% now trips —
**the right response is to ask whether a 50% unclear rate is acceptable, not to
move the bar to 55%.** Stage 5's two gauges pass on their existing values and
need no attention either way.

Also measured on this run, against the master's `website` (~2% of the registry,
national-heavy — a regression canary, not a registry accuracy estimate):

| Head-of-funnel | n=100, 2026-08-02 | n=200, 2026-08-01 |
|---|---:|---:|
| Leg-1 recall (master domain surfaced by leg 1) | 77.0% (59 at rank 1) | 82.0% |
| Stage 2 official site found | 90.0% | — |
| Stage 2 correct vs master, `website` **in** prompt | 72.0% | 86.9% |
| Stage 2 correct vs master, `website` **stripped** | **69.0%** | — |

The two runs are **not** the same sample: the evaluation frame changed by four
rows on 2026-08-02 (§1 note), so seed 22294 draws a different 100. Read the
77.0% vs 82.0% gap as sample variation, not regression.

The stripped-prompt row settles §5.5. See §4 for what it cost to find out.

### What is *not* a substitute for these measurements

- **`data/pilot_v1/`** — 1,336 rows, 917 institutions, 343 with
  `has_genai_activity=yes` (37.4%). This is a Jan–Mar 2026 **manual +
  ChatGPT-web snapshot**, assembled from nine upstream sources including RA
  hand-extractions. It is a *content* benchmark for the website. It says
  nothing about the automated pipeline's yield and must not be cited as a
  pipeline metric.
- **`docs/budget/cost-model.md` downstream lines** — universe averages from a
  budget recompute, class **A**. Its Serper line was understated by ~4× until
  today.

---

## 4. Cost

| Line | Value | Class |
|---|---:|:--:|
| Serper, `chain` | **1.84 credits / institution** | M (n=200 **and** n=100) |
| Serper, `legacy` | 8.52 credits / institution | M (n=200) |
| OpenAI Batch, Stages 2 + 3 | **$1.34 / 1,000 institutions** | M (n=100) |
| OpenAI Batch, Stages 5 + 6 | **$9.70 / 1,000 institutions** | M (n=100) |
| OpenAI Batch, whole LLM pipeline | **$11.04 / 1,000 institutions** | M (n=100) |
| Render fleet | — | A only |

Run `20260802-e2e-100` spent **184 Serper credits for 100 institutions —
1.84/institution, reproducing the n=200 figure exactly** as an independent
`get_balance()` delta (45,727 → 45,543).

### Corrected 2026-08-03: prompt caching **does** stack with the Batch discount — on the stages that matter

**The 2026-08-02 conclusion below was true but not general, and the
generalisation drawn from it was wrong.** `cached_tokens` really is 0 on all 300
Stage-2/3 jobs. But once Stages 5 and 6 ran, they came back **64.7% cached
overall**, verified on raw API responses and not only via the report script.

The mechanism explains both observations at once. OpenAI caches only prompts
**≥1,024 tokens with a matching prefix**. Stage 2/3 prompts are 900–1,650 tokens
with per-institution content early, so no shared prefix ever reaches the
threshold. Stages 5/6 carry the ~10.4k-token output contract as a byte-identical
prefix on every job, so nearly the whole input caches — 11,648–11,776 of ~12,300
prompt tokens on a typical Stage-5 job.

So the instruction "price batched input at the full uncached rate" holds for
Stages 2–3 and is **withdrawn for Stages 5–6**, which are the two stages that
dominate the budget. `docs/budget/cost-model.md` still carries the superseded
framing and needs the same correction.

| Stage (n=100) | jobs | input | cached | cache % | output | *of which reasoning* | USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2 classify_official_site | 100 | 74,817 | **0** | 0.0% | 129,844 | 123,648 | $0.0278 |
| 3 classify_triage | 100 | 111,162 | **0** | 0.0% | 516,621 | 421,952 | $0.1061 |
| 5 extract (8 waves) | 681 | 11,359,648 | 7,522,304 | **66.2%** | 3,365,110 | 2,958,179 | $0.7877 |
| 6 validate | 84 | 960,979 | 568,832 | **59.2%** | 857,515 | 721,728 | $0.1827 |
| **total** | **965** | **12,506,606** | **8,091,136** | **64.7%** | **4,869,090** | **4,225,507** | **$1.1044** |

**Two caveats on the cache figures.** They are a *floor*, not a ceiling: Stage 5
ran as 8 separate batches under the enqueued-token budget (§E of the roadmap),
so it paid 8 cache-cold first jobs instead of 1, and per-wave rates ranged
52.7%–76.6%. And caching reduces *billed* input only — OpenAI's enqueued-token
ceiling counts the full uncached prompt, which is why Stage 5 could be cheap and
still un-submittable.

**The cost driver is reasoning, not prompt length — and the whole run confirms
it.** Across all four LLM stages, reasoning tokens are **86.8%** of output
(4,225,507 / 4,869,090) at the pinned `reasoning_effort="medium"`, up from the
84.4% seen on Stages 2–3 alone. Two consequences worth carrying:

1. `reasoning_effort` is a larger cost lever than any prompt-length edit, and it
   is currently pinned in `batch_client.py` rather than being a run parameter.
2. It **weakens** the cost half of the Stage 5/6 codebook hold (§3), now
   retrospectively: a codebook prompt-length change moves cost far less than
   feared, and prompt caching absorbs most of what it would move. The yield and
   empty-rate half of that argument was the load-bearing one all along.

**The whole-pipeline figure is now measured: $11.04 / 1,000 institutions**, of
which Stages 5+6 are **$9.70 (87.9%)**. That is **63% of the cost model's
modelled $17.52 / 1,000** — so the model was conservative, not optimistic, and
`docs/budget/cost-model.md` should be re-based on measurement rather than
assumption. Note the direction of the surprise: the modelled figure was too
high on cost, while the constraint the model never represented at all
(enqueued-token throughput, roadmap §E) is the one that actually blocks a sweep.

**Serper at full-registry scale (719,588 institutions):**

| Mode | at $0.00056/credit | at $0.001/credit |
|---|---:|---:|
| `chain` | $742 | $1,324 |
| `legacy` | $3,434 | $6,131 |

**The USD-per-credit rate is unresolved and is a PI budgeting input, not an
engineering constant.** The cost model implies ~$0.00056; the findings memo
uses $0.001. Serper's pack pricing makes both defensible. Every site in the
repo that quotes a Serper cost carries both rather than picking one.

**`legacy` is cheaper than its 16-credit design cost only because most of it
never runs.** Stage 2 found a site for 13/200, so Stage 1b — which runs only
for those — was skipped for 187 institutions. Read 8.52 as a symptom, not a
saving; repairing Stage 2 under `legacy` would push it back toward 16.

**Closed 2026-08-03: every LLM stage now has a measured cost.** The
caching assumption that this line called unverified has been tested and came
back the *opposite* way for Stages 5–6 (see the correction above), and OpenAI's
measured share is $11.04 against the model's $17.52 / 1,000. What replaces this
as the largest open evidence gap is not cost at all but **throughput** — the
enqueued-token ceiling of roadmap §E, which no budget line represents.

Session spend for the record: 2,273 credits (smoke 6, chain arm 368, legacy arm
1,704, leg-1 quoted arm 195; leg-1 unquoted arm 0, fully cache-served).
**Stages 5–7 session, 2026-08-03:** zero Serper credits (discovery was already
cached on disk) and **$0.97 of OpenAI spend** for Stages 5+6, plus $0.06 for the
5-institution smoke run. The rejected 681-job submit cost nothing —
`request_counts` was `total=0 completed=0 failed=0`.

---

## 5. Known weaknesses in the instrumentation itself

1. ~~**The Stage 1a health gauge cannot go red in practice.**~~ **Fixed
   2026-08-02.** `% with ≥1 URL` reads 100% under leg 1, and `% with a usable
   domain` also reads 100%, because leg 1 nearly always returns *some*
   non-aggregator host. The chain now writes **leg-1 recall against the
   master** into the Stage 1a artifact at run time — did leg 1 surface the
   institution's own domain, and at what rank — which the health report
   aggregates and flags. This keeps the report disk-only (it still never
   imports the master) and is model-free, so no prompt can inflate it.
   Coverage is still the 1.96%; it is a regression canary, not a registry
   estimate, and it stays unflagged below 10 comparisons.
2. **`discovery_yield.py` only runs where ground truth exists** — 1.96% of the
   registry, unrepresentatively national.
3. ~~**Whole-run aborts are misattributed.**~~ **Fixed 2026-08-02.** The claim
   that nothing on disk distinguishes "never got a turn" from "got a turn and
   found nothing" was wrong: the resume machinery's `_state/.done/{stage}.json`
   markers do. An empty result is now only read as a finding when the stage
   that owed the institution an artifact is marked done; otherwise it reports
   `PROCESSING_FAILED` naming the unfinished stage. Per-institution, not
   run-wide — an institution whose triage completed and kept zero URLs stays
   `NO_EVIDENCE_FOUND` even if the run later died.
4. **The disambiguation slot is unmeasured.** It ships on first principles;
   zero of the 200 ground-truth institutions carry one.
5. **The Stage 2 accuracy figures in §2 are contaminated.** *(Found
   2026-08-02.)* `records.institution_record()` includes the master's
   `website`, and `g3o/classify/official_site.py::_user_prompt` serialises the
   whole record into the Stage 2 message. The classifier is handed the URL and
   then asked to pick the official homepage from candidates — **the value the
   accuracy metric scores it against is in its own input.** This affects
   "correct vs master" (86.9%), "correct as a share of all" (76.5%) and the
   conversion figure (93.3%); it plausibly explains why conversion is so high
   and why `legacy` was 13/13 correct on the few it attempted. Leg-1 recall
   (82.0%) is **not** affected — no model participates in it.

   Removing `website` from the prompt changes model input and breaks
   comparability with the n=200 run the chain default rests on, so it is a PI
   decision, not a cleanup. A test pins the contamination so the day it is
   resolved the caveat is forced to be revisited.

   **Measured 2026-08-02: the leak is worth +3.0 pp, not the large effect
   feared.** Rather than decide blind, Stage 2 was replayed over the *same*
   candidate URL sets from run `20260802-e2e-100` with `website` set to `None`
   and nothing else changed (control batch
   `batch_6a6fe83a…`; production code untouched, the strip happens in the
   harness; the two prompt-building files verified byte-identical between the
   checkout that built the control arm and the run's own).

   | Stage 2 correct vs master, n=100 | |
   |---|---:|
   | `website` in prompt (production) | 72.0% |
   | `website` stripped | 69.0% |
   | leak-attributable delta | **+3.0 pp** |
   | the two picks agree | 96/100 |

   Only four institutions moved, reconciling exactly: Denmark and Solomon
   Islands match→null, Malta match→`gov.mt` (a portal), Bahrain null→wrong.
   Three losses, no gains — stripping the field makes the classifier *worse*,
   not merely less informed, which is itself an argument for keeping it in
   production.

   **So the contamination is a caveat, not an invalidation.** Stage 2 accuracy
   is not mostly an echo of its own input; the affected figures are overstated
   by roughly three points. Two limits on that conclusion: this is n=100 on a
   fresh sample (72.0% contaminated here vs 86.9% on record at n=200 — a sample
   difference sits on top of the leak and the two must not be conflated), and it
   is measured at `reasoning_effort="medium"` on `gpt-5-nano-2025-08-07`, with no
   test of whether a stronger model leans on the leak more or less. The
   production-behaviour question — keep the field or drop it — is still the PI's,
   now with the effect size known.
6. **Stage 5 has a live contract-adherence defect.** *(Measured 2026-08-03.)*
   62 of 681 pages (9.1%) failed `ContractRow` validation, and the failures are
   not random — they concentrate in one field. `gpt-5-nano` emits either `_NA_`
   or an empty string into `uncertainty_flags`, both of which the contract
   forbids (`""` is barred by the "never emit null or an empty string" rule;
   `_NA_` is not in the allowed flag set). A smaller number returned empty
   assistant content. Each failure drops that page's evidence rows before
   consolidation.

   **Its cost is far larger than 9.1% suggests: it accounts for all 43
   `PROCESSING_FAILED` institutions (43% of the sample), 38 of which already
   hold a Stage-6 verdict** (§3). One unparseable page disqualifies an entire
   institution under the no-evidence publishing rule, so a page-level defect
   amplifies into an institution-level suppression. This is the highest-value
   fix available to the pipeline.

   Deliberately **not** fixed here: repairing it means touching either the
   contract (gated by `CONTRIBUTING.md` §Schema stability) or the validator, and
   doing so mid-measurement would have changed the instrument being measured.

   This independently corroborates Thomas's Week-6 determinism report of the
   same day, which flags "blank flags, invalid `_NA_` values" as measurement
   contamination from a 3×30-institution repeat study. That report reaches the
   defect from the reliability side; this run quantifies it at 681 pages.
   Interacts with Pending Decision §D — a different model has different failure
   modes, and this one may simply disappear.
7. **The preflight vets the wrong cap.** *(Found 2026-08-03.)* Thomas's Week-6
   preflight reported Stage 5 as "360 jobs at 61,758 bytes per job, 22,232,880
   bytes total, one chunk, **with no cap issue**" — a byte/chunk-count check.
   The cap that actually binds is the **enqueued-token ceiling** (roadmap §E),
   which the preflight does not model at all; 22.2 MB is roughly 5.6M estimated
   tokens against a 2M ceiling. A preflight that clears a submission the API
   will reject is worse than no preflight, because it converts a pre-spend check
   into false assurance. Open question for whoever picks this up: his runs did
   complete Stage 5, so either the ceiling was not binding for them or the two
   measurements are not comparable — that discrepancy is unexplained and should
   be resolved before the preflight is trusted again.
8. **A single transient API timeout kills a multi-hour stage.** *(Found
   2026-08-03.)* Stages 5–6 died twice mid-run on `APITimeoutError` and
   `APIConnectionError` raised from `poll_batch` after tenacity exhausted its
   five attempts. Recovery is cheap and lossless — the resume path skipped
   fetched chunks and re-adopted the in-flight one by `batch_id`, preserving 251
   and then 496 results across two unplanned deaths — so this is robustness, not
   correctness. But it needed a shell supervisor to babysit, and at sweep scale
   (thousands of waves per stage) an unattended run needs the poll loop to
   tolerate transient API faults rather than propagate them.

---

## 6. Avenues for improvement

Ordered by expected value per unit of effort. Items 1–3 buy evidence; 4–7 buy
yield; 8–10 buy durability.

### Buy evidence first

1. ~~**End-to-end run through Stage 6 on ~100 institutions.**~~ **Done
   2026-08-03** — run `20260802-e2e-100` is complete through Stage 7 (§3).
   Stages 1a–4 ran 2026-08-02 (184 Serper credits, $0.13 OpenAI, 2 h 15 min at
   `--max-workers 4`, ~80% of it scrape); Stages 5–7 resumed 2026-08-03 off
   `_state/` for **zero Serper credits and $0.97**, exactly as the resume design
   promised.
   Three things it settled, two of them against the prior conclusion:
   the prompt-cache question that 68% of the budget hung on — caching **does**
   stack, on the stages that matter (§4, superseding the 2026-08-02 reading);
   the whole-pipeline LLM cost, **$11.04 / 1,000** vs a modelled $17.52; and
   Stage 5/6 yield, where Stage 5 is green on both gauges and Stage 6 warns on a
   **50.6% unclear rate**. It also surfaced the constraint no budget line
   represented: the enqueued-token ceiling (roadmap §E), which rejected the first
   Stage-5 submit outright.
   The Stage 1c rule set, the run's other headline finding, was **fixed on
   2026-08-02** — snippet screen retired, 3.9% → 99.5% shadow recall (§3).
2. **Build a subnational ground-truth set.** ~200 hand-verified websites for US
   local government and non-US subnational units. Unblocks the disambiguation
   slot (30% of the registry) and answers whether 64.5% survives contact with
   the 98% of the master nobody has measured. Without it, every yield figure
   G3O quotes carries an unquantified generalisation gap.
3. ~~**Diagnose why `legacy` Stage 2 finds 13/200.**~~ **Done 2026-08-02** —
   from the surviving `cache/serp_v2_*` entries (1,704 legacy = 200×8 Stage 1a
   + 13×8 Stage 1b, reconciling exactly with the measured 8.52
   credits/institution). **It is not a classifier defect. It is input
   starvation, twice over:**

   | | legacy | chain |
   |---|---:|---:|
   | True domain present in Stage 1a candidates | **20.0%** (40/200) | 82.0% |
   | Stage 2 conversion of those | **32.5%** (13/40) | 93.3% |
   | Official site found | 6.5% | 88.0% |

   The ceiling is 20% — for 160 of 200 institutions the right answer was never
   in the candidate list. And of the 40 where it was, **39 (97.5%) had it only
   as a deep link** — a PDF, a document attachment, a news item — never as a
   homepage. Exactly one institution got a bare homepage. Stage 2 is asked to
   identify a *site*, and legacy Stage 1a searches for GenAI *content*, so it
   returns content pages: `mnb.hu/letoltes/mnb-recommendation-2025-12-en.pdf`
   is not a wrong answer to "what is the official website", it is not an
   answer at all. 41.4% of all legacy candidate URLs are social/aggregator
   hosts (instagram 631, facebook 564, linkedin 434).

   So legacy Stage 2 declining is largely correct behaviour on the input it
   was given, and the chain does not "route around" a bug — it fixes the
   category error by changing what leg 1 asks for. Any repair to legacy would
   be a design change (infer the site from a deep link's eTLD+1), not a bug
   fix, and needs sign-off rather than a patch.

### Then buy yield — leg 1 is the binding constraint

4. **Attack leg-1 recall (82%), not Stage 2 (93% conversion).** ~18 points are
   available at leg 1 against ~7 at the classifier. Untested levers, cheap to
   A/B on the existing harness: a second website-term wording; `num` beyond 10
   via pagination; using the master's `website` as a seed where present.
5. **Native-language legs.** Measured +2/24 in the findings and unreachable any
   other way. Owned by `subprojects/multilingual-pipeline/`, which also owns
   reshaping `GENAI_TERMS_BY_LANG` — the current roster is eight redundant
   English terms, and five evaluated countries silently fall back to English.
6. **Reconsider the volume reserve against evidence.** The chain collects
   16.07 URLs/institution against legacy's 20.48. That reduction was accepted on
   the understanding that more can be collected later. Draw on it only when
   Stages 1c/3 report starvation — and never via extra English tokens, which
   measure at exactly 0 pp.
7. **Decide whether the master's `website` should be corrected where live
   discovery beats it.** Live discovery won twice in 24 in the findings
   (`nbc.gov.kh` over a stale `nbc.org.kh`; `statistics.gov.sb` over a regional
   body). If the column is the ground truth for every accuracy metric, its
   errors are silently capping measured accuracy.

### Then buy durability

8. ~~**Give the health report an accuracy signal.**~~ **Done 2026-08-02** —
   see §5.1. Implemented as leg-1 recall rather than the Stage 2 comparison
   originally proposed here, because building it surfaced §5.5: the Stage 2
   pick cannot serve as an accuracy signal while the master's `website` sits
   in the Stage 2 prompt. Both gauges ship; only leg-1 recall is trustworthy.
9. **Recalibrate `thresholds.py` against measured values** once item 1 lands.
   The Stage 3–6 bands are still smoke-run guesses and will either never fire
   or fire constantly at production scale. *(The two ground-truth canary bands
   added 2026-08-02 are already set from the n=200 measurement.)*
10. ~~**Fix the whole-run-abort misattribution and the `_cmd_discover` cp1252
    crash.**~~ **Done 2026-08-02.** The abort fix is in §5.3. The cp1252 crash
    was fixed at the stream rather than at `g3o/cli.py:89`: that line is one of
    fifteen-odd `ensure_ascii=False` writes to stdout, so `main()` now
    reconfigures stdout/stderr to UTF-8 and `PYTHONIOENCODING=utf-8` stops
    being load-bearing. Only non-Latin-1 scripts ever triggered it, which is
    why it read as a Windows curiosity rather than a defect.

## 7. Probe run `r20260826T214131Z-4cd7` — n=500, wave-2 frame, 2026-08-26/27

**Added 2026-08-27 by `20260827-claude-g3o-diag` (card 2, probe forensics).** Every
figure in this section is class **M** unless marked otherwise. The run was built and
hand-adjudicated by `20260826-claude-g3o-pre`; the audits below are a second pass over
its artifacts, and where they correct it that is said explicitly. **Nothing above this
section has been deleted or replaced.** The two figures this section bears on — §3's
50.6% `unclear` rate and §3's 43% `extract:parse_failed` rate — are carried and
addressed in 7.6 rather than moved.

**Why this run is not comparable to `20260802-e2e-100`.** That run drew from master rows
**with a usable website**, skewed to higher levels of government. This one draws from the
wave-2 frame, which is **97.7% website-free** and 80% local-level. Nothing here supersedes
a §2–§5 figure by default, and 7.6 is the worked example of why.

### 7.1 The run

| | |
|---|---|
| institutions | 500 — 200 Anglophone stratum, 300 mix stratum. **No pooled rate is reported anywhere.** |
| discovery | English-only (`discovery_languages=("en",)`) — deliberate, so language is not a confound |
| wall clock | **9,057.0 s = 2.516 h** (`timing_summary.json`, `total_run_duration_seconds`) |
| cost | **$1.42** actual against a **$3.61** projection and an $8.00 ceiling — 39% of projection, $0.00284/institution |
| model | `gpt-5-nano`, Batch tier; 8,558,336 of 11,534,279 prompt tokens cached (74.2%) |
| database | never touched. Chain stopped at the loader-sha gate by design, `E2E_EXIT=1` |

**The cost under-run is a bad sign, not a good one, and §4's logic says why:** the
preflight assumed ~12 pages per institution for extraction and the actual was **1.44**,
because **53.6% of the frame exited at Stage 2 and half the pipeline never ran.**

*Correction to `G3O PRE`'s closeout, minor:* it reports the run at **2.38 h**. The run's
own `timing_summary.json` says **2.516 h**. The scaling in 7.5 uses the latter.

### 7.2 Stage 2, hand-adjudicated — 500 picks, five categories

`G3O PRE`'s adjudication (`probe-stage2-adjudicated.csv`, 500 rows, hand-assigned).
Reported per stratum:

| | Anglophone (n=200) | Mix (n=300) |
|---|---:|---:|
| **(a) the institution's own site** | **99 — 49.5%** | **94 — 31.3%** |
| **(b) a parent or ancestor unit** | **14 — 7.0%** | **18 — 6.0%** |
| (c) a sibling or homonym | 1 — 0.5% | 3 — 1.0% |
| (d) not a government site | 0 — 0.0% | 3 — 1.0% |
| (e) nothing picked | 86 — 43.0% | 182 — 60.7% |

**Supersedes an assumption, not a measurement.** The parity spec's §8 assumed a Stage-2
correct-site rate of **65% Anglophone / 25% mix** (class **A**, both untested). Measured:
**49.5% / 31.3%**. The Anglophone assumption was too high; the mix assumption was too low.
The 65% was a with-website number and could never have described this frame.

**The parent-unit match is a TIER effect, not a country effect** — the single most
consequential finding of the run, and it contradicts how the launch card, the parity spec
and `G3O FRAME` all framed it:

| government level | (b) as % of institutions drawn | (b) as % of the picks at that level |
|---|---:|---:|
| second_subnational | **17.6%** (13/74) | **26.5%** |
| local | 4.6% (18/389) | 11.6% |
| national | 4.5% (1/22) | 5.6% |
| first_subnational | 0.0% (0/15) | 0.0% |

By country it appears wherever the master carries a unit below the level that has its own
web presence: New Zealand community boards 5/8, Rwanda sectors 3/10, India blocks 9/37,
Uganda sub-counties 2/20, Philippines 2/15, Germany 2/31. **New Zealand — Anglophone,
wealthy, high state capacity — is the worst country in the frame.** No roster fixes this
and re-weighting the frame does not remove it.

**Confidence is not a usable filter for it: 91.4% of all picks returned `high`, exactly
one returned `low`.**

**A sixth mechanism the taxonomy has no box for.** Seven picks were the **correct entity
on a shared national portal** (`gov.kz` ×3, `ghana.gov.gh` ×2, `gov.uz`, `gov.bw`).
`G3O PRE` counted these as (a) — the pick *is* right — and flagged them separately. Leg 2
is `site:<domain>`-scoped, not path-scoped, so `site:gov.kz AI` returns everything the
Kazakh government publishes. **Same consequence as a parent-unit match, different cause,
different remedy.** Audited in 7.3: all seven ended `no` (5) or `unclear` (2), so this
channel contributed **zero** to the run's positives, and its footprint in this probe is
`unclear` inflation rather than false positives.

**An artifact rate that is HIGHER among positives than among picks** — new here, not in
`G3O PRE`'s closeout. Conditioning on consolidation:

| category | drawn | consolidated | `yes` | P(`yes` \| consolidated) |
|---|---:|---:|---:|---:|
| (a) own site | 193 | 168 (87.0%) | 6 | 3.6% |
| (b) parent/ancestor | 32 | 16 (50.0%) | 1 | **6.2%** |
| (c) sibling/homonym | 4 | 2 | 0 | 0.0% |
| (d) not government | 3 | 3 (100%) | 1 | **33.3%** |
| (e) nothing picked | 268 | 38 (14.2%) | 0 | 0.0% |

n is small and these rates carry no interval worth quoting, but the mechanism is not
subtle: **a parent district or a private college is far more likely to publish GenAI
content than the village or block it was substituted for.** The attribution bias is
therefore *amplified* between the pick and the published row, not diluted.

### 7.3 The finding rate, and the eight `yes` audited one by one

| | Anglophone | Mix |
|---|---:|---:|
| consolidated | 100 / 200 (50.0%) | 127 / 300 (42.3%) |
| **`yes`** | **7 — 3.5%** | **1 — 0.3%** |
| `unclear` | 13 — 6.5% | 14 — 4.7% |
| `no` | 80 — 40.0% | 112 — 37.3% |

**The mix figure is one institution and should carry almost no weight.** 300 institutions
at a ~2% expected rate estimates that rate badly.

**AUDIT A — all eight audited against the five categories, the shared-portal set, and the
actual source URLs behind each verdict.** Class **M**.

| institution | country / level | cat | picked | verdict |
|---|---|---|---|---|
| Kalgoorlie-Boulder | AU local | (a) | `ckb.wa.gov.au` | **holds** — own AI policy + council minutes |
| Longreach | AU local | (a) | `longreach.qld.gov.au` | **holds** — own policy; 7 of 10 sources `ambiguous`, evidence thinner than the rest |
| Carberry | CA local | (a) | `townofcarberry.ca` | **holds** — AI Usage Policy adopted by council 2025-04-08 |
| "Saskatchewan" | CA second_subnational | (a) | `saskatchewan.ca` | **frame defect** — see below |
| Bhojipura | IN second_subnational | **(d)** | `srms.ac.in/ims/` | **disqualified** — a **private** educational trust in Bareilly; the evidence is a college faculty-development programme |
| Christchurch Central Community | NZ local | **(b)** | `ccc.govt.nz` | **disqualified** — the **parent** City Council; the Assess24 evidence is on a `districtplanuat.` (UAT) subdomain |
| ACC | NZ national | (a) | `acc.co.nz` | **holds** — own `/about-us/generative-artificial-intelligence` page; a Crown entity on a `.co.nz` domain, confirmed government by a `govt.nz` source in the same set |
| COUNTY OF FAIRFAX | US second_subnational | (a) | `fairfaxcounty.gov` | **holds** — own hiring-AI policy + "Ask Fairfax" chatbot |

**None of the eight is a shared-portal pick.** That channel contributed zero positives.

**The "Saskatchewan" row is a master-data defect, not an instrument one, and it is worth
its own line.** `master_row_id` 29060 comes from `gadm41_CAN_2.json` — GADM level 2, i.e.
census divisions — but carries the **level-1 name** "Saskatchewan" with
`government_level=second_subnational, institution_type=district`. Stage 2 found
`saskatchewan.ca`, which is the correct answer *to the name it was given*; the published
row would attribute the **provincial** government's AI guidelines to a "district".

Sized, read-only, on the master (`~/data/master_institutions.csv`, 33,293
second_subnational rows): **346 rows (1.04%)** carry a name matching a first_subnational
name in the same country, and 1 carries the country name. **This is a LOWER BOUND and it
does not separate a defect from a legitimate same-name unit** — Rwanda's 212 are mostly
sectors genuinely named after their districts, whereas all 8 Australian first_subnational
names appearing as second_subnational rows look like true level duplication. Canada shows
3, and the master holds only 3 Canadian first_subnational rows against 13 provinces and
territories, so the Canadian count is certainly understated. **23 countries have zero
first_subnational rows in the master, and the test is blind in all of them.** At 1.04% the
wave's 1,300 second_subnational rows would carry roughly **14** such rows. Small, real,
and not a reason to change anything on its own.

**Corrected counts and projections.** Exact Clopper-Pearson, recomputed from scratch:

| basis | Anglophone | Mix | point | 95% interval |
|---|---|---|---:|---|
| as reported | 7/200 = 3.500% [1.42, 7.08] | 1/300 = 0.333% [0.008, 1.84] | **192** | **[71, 446]** |
| (b) and (d) dropped | 6/200 = 3.000% [1.11, 6.42] | **0/300 = 0.000% [0.00, 1.22]** | **150** | **[55, 382]** |
| frame defect also dropped | 5/200 = 2.500% [0.82, 5.74] | 0/300 | **125** | **[41, 348]** |

Projected to 5,000 + 5,000; per-stratum bounds added.

**The single largest consequence of AUDIT A: the mix stratum's only positive was the (d)
artifact, so the corrected mix count is ZERO of 300.** The mix half's contribution to the
wave is statistically indistinguishable from nothing, with an upper bound of 1.22%.

**A correction to the standing reading of these numbers.** `G3O PRE`'s closeout reports
~190 as *"against §8's ~425 and below its stated lower bound of 250"*. **The point
estimate is right; the conclusion does not follow.** §8's range of 250–650 is a range on
an assumed rate (class **A**), and 250 sits comfortably **inside** the probe's own
interval — under every basis above, including the most heavily corrected one. The probe
did not measure the wave below the floor. **It left the wave's yield unmeasured within a
factor of about five, with a lower centre.** Every correction so far has moved the centre
down without narrowing the interval.

### 7.4 The (e) bucket decomposed — 53.6% of the frame, and what it actually is

**AUDIT B.** Class **M**. The (e) bucket (268 institutions: 86 Anglophone, 182 mix; 267
Stage-2 declines plus 1 that never reached Stage 2) hand-decomposed on a **stratified SRS
without replacement, 60 per stratum, n=120, seed 20260827**. All 120 leg-1 candidate lists
read by hand — roughly 1,070 candidate URLs with titles and snippets. The Anglophone
sample is 60 of 86, so its intervals below are conservative (no finite-population
correction).

Categories and the standard of evidence, fixed before the audit and applied symmetrically:

- **(1) leg-1 shortfall** — no candidate at the institution's own level, and **no positive
  evidence that no own site exists.**
- **(2) classifier failure** — an acceptable own-site URL *was* in the list and Stage 2
  declined it. A URL is named for every case.
- **(3) evidenced absence** — either the parent/containing government unit's own site is in
  the list and nothing at or below the institution's level, or an authoritative registry
  states the institution has no government of its own.
- **(4) cannot tell** — reported, never forced.

| | Anglophone (e)=86 | Mix (e)=182 |
|---|---|---|
| **(1) leg-1 shortfall** | **45/60 = 75.0%** [62.1, 85.3] → ~64 | **49/60 = 81.7%** [69.6, 90.5] → ~149 |
| **(2) classifier failure** | 4/60 = 6.7% [1.8, 16.2] → ~6 | 1/60 = 1.7% [0.0, 8.9] → ~3 |
| **(3) evidenced absence** | 5/60 = 8.3% [2.8, 18.4] → ~7 | 4/60 = 6.7% [1.8, 16.2] → ~12 |
| **(4) cannot tell** | 5/60 = 8.3% [2.8, 18.4] → ~7 | 6/60 = 10.0% [3.8, 20.5] → ~18 |
| (0) never reached Stage 2 | 1/60 → ~1 | 0/60 |

**"The institution genuinely has no web presence" is the SMALLEST substantive bucket in
both strata — 8.3% and 6.7%, upper bounds under 19%.** The hypothesis that genuine absence
would dominate the bucket on a 99.2% website-free frame is **not supported**.

**A correction to the framing, and it matters more than the counts.** The (1) bucket is
**not** evidence of instrument failure. It is a **mixture** of instrument failure and
genuine absence, and this probe cannot separate them: judging absence requires a negative
claim, and for most of these institutions the candidate list supports neither direction.
Reading (1) as recoverable yield would overstate what any leg-1 repair can buy.

**Four mechanisms inside (1), all named and all evidenced.** None is a language problem:

1. **The institution name does not survive the query.** All 9 Laos rows in the mix sample
   returned country-level content only — the long official country name
   ("Lao People's Democratic Republic") dominates. One row got **exactly one candidate
   record in the whole run**. All 6 Kazakhstan rows collapsed to `akorda.kz` /
   `primeminister.kz` / `gov.kz`. All 5 Indonesian village rows collapsed to
   `evisa.imigrasi.go.id`, because "official website" + "Indonesia" ranks the national visa
   portal above everything.
2. **Homonyms with no disambiguation.** Whole candidate lists consumed by an unrelated
   sense of the name: Picard's Peanuts (a Canadian municipality), Éditions du Seuil (a
   French commune), the Philippine Navy ("Naval", Biliran), Fidel V. Ramos ("Ramos",
   Tarlac), the Juma Mosque (a district in Uzbekistan), Indian dessert recipes ("Khova",
   Zambia), a luxury sleepwear brand ("Lunya", Zambia), the "Languages of Uganda"
   ("LANGWIDIYIKA"), USD→UGX exchange rates ("AGWEE DOLA"), Better Business Bureau
   ("BUSIBE/BUDUTU" — the slash broke the query).
3. **The own site exists and leg 1 carried its URL inside a snippet without ever making it
   a candidate.** **5 of 60 mix rows (8.3%)**, usually the Wikidata `official website`
   property or a Facebook page header: `velichov.cz`, `villegongis.fr`,
   `comune.poggiodomo.pg.it`, `kemendagri.go.id`, `depkop.go.id`. **This is a lever §6.4
   does not list.**
4. **Two Indonesian national ministries exited at (e).** For the Ministry of Home Affairs,
   Stage 2's own rationale reads *"No candidate links point to the official Indonesian
   Ministry of Home Affairs homepage domain (kemendagri.go.id)"* — **Stage 2 knew the right
   answer and correctly reported that leg 1 had not supplied it.** If leg 1 cannot retrieve
   a national ministry's homepage, the mix stratum's Stage-2 rate is not measuring language
   readiness.

**This is direct evidence on §6.4's ranking** — leg 1 is the binding constraint, and the
probe puts numbers on it: **6.7% / 1.7%** of the (e) bucket is a classifier failure against
**75.0% / 81.7%** that is a leg-1 shortfall. §6.4's three untested levers are unchanged and
still untested; item 3 above is a fourth candidate and is **not** endorsed here.

**Inside (2), one sub-mechanism accounts for 3 of the 5 cases across both strata and is a
contract question, not a judgement question: Stage 2 rejects a correct own domain when the
candidate URL is not the root page.** Its own rationales say so —
`santalucijalc.gov.mt` (*"appears to be a subpage, not the main entry"*),
`loversallpc.org.uk` (*"is not present as a root page"*), `mpimbwedc.go.tz` (surfaced only
as `mail.mpimbwedc.go.tz`, *"a mail subdomain, not the district council's main
public-facing landing page"*). The remaining two are `croydon.qld.gov.au` (a homonym the
master cannot disambiguate — it records no state) and `leuwikidang.desaa.id`, titled
*"Website Resmi Desa Leuwikidang"* at **rank 1**, which Stage 2 described as
"social media, Wikipedia, third-party domains".

**Stage 2 also gets the parent-unit call right some of the time**, which the (b) rate alone
conceals: it correctly declined `dinagatislands.gov.ph` (the parent province, with a page
for the sampled municipality), `kulgam.nic.in` (the parent district),
`middevon.gov.uk` (the parent district council), and
`hinatuanwaterdistrict.gov.ph` (a sibling special district).

### 7.5 Throughput — arithmetic verified at source

Per-stage wall clock from `timing_summary.json`:

| stage | wall (s) | share | kind |
|---|---:|---:|---|
| 2 classify_official_site | 4,132.0 | 45.6% | **batch** |
| 4 scrape | 2,788.2 | 30.8% | network |
| 6 validate | 1,324.0 | 14.6% | **batch** |
| 3 classify_triage | 303.0 | 3.3% | **batch** |
| 5 extract | 303.0 | 3.3% | **batch** |
| 1a discovery_general | 130.7 | 1.4% | network |
| 1b discovery_site_restricted | 55.9 | 0.6% | network |
| 1c filter_eligibility | 0.7 | 0.0% | compute |

Sum 9,037.45 s against a total run duration of 9,057.02 s — 19.6 s of orchestration overhead.
*(`G3O PRE` reports Stage 2 at 3,789.5 s and validate at 1,327.2 s; `timing_summary.json`
says 4,132.0 and 1,324.0. Both sets are carried; the difference does not change any
conclusion.)*

**The four batch stages are 66.9% of the clock and are queue latency, which is roughly
fixed in n.** The evidence is stark: this 500-job batch cleared its slowest stage in 69
minutes while an abandoned **six-job** batch took **5 h 54 m**. Queue position, not job
count.

Scaling to n=10,000 — the network/compute half ×20, the batch half held flat:

| queue behaves like | scaling half | batch half | total |
|---|---:|---:|---:|
| its best stage tonight (303 s ×4) | 16.53 h | 0.34 h | **16.87 h** |
| tonight's run overall | 16.53 h | 1.68 h | **18.21 h** |
| the six-job batch (5 h 54 m ×4) | 16.53 h | 23.60 h | **40.13 h** |

**Card 10's ~15 h is not reachable: 16.53 h comes from the scaling half alone, and 15.49 h
of that is scrape.** Even an instantaneous batch queue leaves n=10,000 above 16.5 h.

**Correction to the standing reading.** `G3O PRE`'s closeout says the parity spec's >20 h
abort bar *"is met under any but a good queue"*. **It is not.** Tonight's own queue — not a
good queue, the observed one — gives **18.21 h, under the bar**. The bar is met only under
the pathological six-job queue, at 40.13 h. **The real argument is the tail, not the
centre.**

`scrape` ran 10,927.6 s of work in 2,788.2 s of wall clock at `--max-workers 4` — a 3.92×
ratio, so the four workers are ~98% utilised and the stage is worker-bound, not
latency-bound. Raising the worker count is the only lever on the scaling half and it points
directly at the render-browser RAM ceiling two commits exist to contain. **Not attempted
here and not recommended here.**

### 7.6 What this run does and does not say about the parse fix

**AUDIT E.** The question put was whether §3's **`unclear` at 50.6% of consolidated
institutions (41/81, n=100, 2026-08-02)** is superseded by this run's **11.9% (27/227;
Anglophone 13/100, mix 14/127)**.

**It is not, and the reason is measurable on this run's own artifacts.** The `unclear` rate
rises monotonically with the number of pages read:

| pages extracted | consolidated n | `unclear` | rate |
|---:|---:|---:|---:|
| 1 | 94 | 1 | **1.1%** |
| 2 | 45 | 4 | 8.9% |
| 3–4 | 45 | 8 | 17.8% |
| 5–8 | 26 | 5 | 19.2% |
| **9+** | **17** | **9** | **52.9%** |

Mean pages read among consolidated institutions: **2.95**, and 94 of 227 (41.4%) read
**exactly one page**. In the depth bucket comparable to the older run, the probe's
`unclear` rate is **52.9%** — indistinguishable from **50.6%**.

**So the drop from 50.6% to 11.9% is an exposure effect, not evidence that the fix worked.
`no` is easy when there is almost nothing to read. §3's 50.6% STANDS and is not
superseded.** Both values are now on the record with their sample sizes, dates and page
depths, which is the only way either is interpretable.

**The fix IS evidenced — on its own gauge, not on this one.** §3 records that all 43
`PROCESSING_FAILED` institutions in the n=100 run cited `extract:parse_failed`, a **43%**
institution-level suppression from a 9.1% page-level defect. In this run:

| | n=100, 2026-08-02 | n=500, 2026-08-26/27 |
|---|---:|---:|
| `extract:parse_failed` | **43 / 100 = 43.0%** | **3 / 500 = 0.6%** |

A ~70× reduction in the specific defect. Contract v2.3 and the `uncertainty_flags` parse
fix landed. **`unclear` was never the gauge for it; `extract:parse_failed` was.**

*One open observation, not a finding:* `consolidated_uncertainty_flags` is `none` for all
227 consolidated institutions and activity-level `uncertainty_flags` is `none` for all 14
activities. That is consistent with a population where verdicts are easy, and it is also
consistent with the field not propagating. **This probe cannot tell which, and it should
not be read as either.**

### 7.7 The failure mode has moved to scrape — and it is bigger than the modelled figure

New in this run, and not in `G3O PRE`'s closeout. `PROCESSING_FAILED` is **92 / 500 =
18.4%**, and its composition has completely changed since the n=100 run:

| reason | n |
|---|---:|
| `scrape:scrape_failed` | **85** |
| `validate:parse_failed` | 3 |
| `extract:parse_failed` | 3 |
| `classify_official_site:parse_failed` | 1 |

**Conditioned on having at least one URL to fetch, `scrape:scrape_failed` is 85 / 274 =
31.0%**, split 41 Anglophone / 44 mix — **balanced across strata, so not a country or
language effect.** The parity spec §8 assumes **~12.4%** egress loss at Stage 4 (class
**A**). The measured figure on this run is **2.5× that assumption**, and it is now the
single largest cause of institution-level suppression in the pipeline.

**Two of the eight `yes` were withheld by it.** `has_genai_activity=yes` is 8, but
`final_status=EVIDENCE_FOUND` is **6**: Christchurch Central Community and ACC both carry
`scrape:scrape_failed`. So the set this probe would actually have published is

> Kalgoorlie-Boulder, Longreach, Carberry, "Saskatchewan", **Bhojipura**, Fairfax County

— **six rows, of which two are wrong** (Bhojipura, a private college; "Saskatchewan", a
province at a district's level label) — while **one genuine positive (ACC) is suppressed by
a scrape failure.** Publishable *and* attribution-valid is **5/200 + 0/300 → point 125,
interval [41, 348]**; 4/200 if the frame defect drops, point 100, interval [27, 313].

### 7.8 Negative verdicts built on pages that are not the institution's site

New in this run. **38 of the 268 (e) institutions consolidated anyway (14.2%)**, and **31
of them produced a publishable negative** — `NO_EVIDENCE_FOUND`, `consolidated`,
`has_genai_activity=no` — **for an institution whose own site Stage 2 never identified.**
The pages came from leg-1 general candidates. 27 of the 31 are in the mix stratum
(Indonesia 6, Rwanda 4, Uzbekistan 4, Germany 3, Italy 3, India 2, Kazakhstan 2, and one
each in France, Uganda, the Philippines).

The institution summaries say it on their own face:

- Burhar (IN, block): *"No GenAI content found on the supplied **NHSRC Burhar** page"* — a
  national health-systems portal page.
- Bakti Agung (ID): *"The page shows a **suspended municipal website**; no evidence of
  generative AI activity ... is present in the supplied text."*
- Xotamtoy MFY (UZ): four sources, drawn from YouTube channels of the same name and a
  Tashkent city page.
- Ku Murenge (RW): the candidate list contained **other** districts' sites.

**This is the defect class the 2026-08-26 board notice named — *could not reach* rendered
as *searched and found nothing*.** Scaled to a 5,000-institution mix run at 27/300 it is
roughly **450 institutions** published as a negative on somebody else's web pages. Recorded
as a measured finding; **the remedy is a substantive decision and is not taken here.**

### 7.9 The pre-registered abort conditions, scored letter and intent

The parity spec §10 wrote four abort conditions **before** the run. Scored below on both
readings, because three of the four diverge. **Whether any of them fires is the PI's call,
not this document's.**

| # | as written | observed | letter | intent |
|---|---|---|---|---|
| 1 | Stage 2 below ~15% on the mix stratum | **31.3%** | **no**, comfortably | **no** — and the n=6 that produced the 25% assumption was pessimistic |
| 2 | parent-unit matches above ~5% **and concentrated in one country** | **7.0% / 6.0%**, and it is a **tier**, not a country | **no** — the conjunction fails | **yes** |
| 3 | throughput implying more than ~20 h for 10,000 | **16.87 / 18.21 / 40.13 h** | **no** — the central estimate is under the bar | **contested** — the tail is 2× the bar |
| 4 | cost per institution above ~2× projection | **0.39×** | **no** | **yes** — §10's own prose says under-projection is the worse signal, and 53.6% of the pipeline did not run |

**Condition 2 is the one that repays thinking about.** It is a conjunction, and **the half
that failed is the half that would have made the problem tractable.** A country effect can
be dropped or disclosed; a tier effect follows the instrument into every frame that
contains that tier. As drafted, the condition lets the wave through on a technicality while
the evidence argues more strongly for the remedy attached to it — an administrative-level
check in Stage 2. **The condition was well drafted for the failure everyone expected and is
mis-specified for the failure that occurred.**

**Condition 3's letter reading is now the honest one**, correcting `G3O PRE`: 18.21 h is
under 20 h, and the argument for concern is the 40.13 h tail and the fact that 16.53 h of
the central estimate is fixed by the scaling half.

**Condition 4 fires on intent and not on letter, for the reason §10 itself gives**: leg 2
only runs where leg 1 found a domain, so a cheap run has skipped the pipeline rather than
saved money. $1.42 against $3.61 is the 53.6% Stage-2 exit showing up in the invoice.

### 7.10 Provenance — one gap settled, and it was a lost write

`G3O FRAME`'s closeout (2026-08-26T19:10) states it wrote
`agent-workspace/2026-08-26-wave2-frame/` with `FRAME-RECORD-wave2-n10000.md` and appended
**5 rows to `asset-registry.csv` and 1 to `interaction-log.csv`**. `G3O PRE` reported none
of it present. Settled here:

- **No `2026-08-26-wave2-frame` directory exists anywhere on the machine.**
- **Both registries are provably append-only** since their 2026-08-25T22:24 backups: every
  line of each `.bak` is still present in the live file, so nothing was overwritten.
- **Neither registry contains a single row from `20260826-claude-g3o-frame`.** The nine
  rows appended since that backup are 2 from `g3o-api` (2026-08-25) and 7 from
  `20260826-claude-g3o-pre`.

**Verdict: a lost write, not Dropbox sync lag.** Sync lag cannot explain it — the write and
the read are the same local filesystem, and the file that would have received the append is
byte-for-byte intact around where the rows should be. The claim was made without being
verified. **`G3O FRAME`'s substantive work survives** in its closeout note and on the
droplet; only the Drive artifacts and the registry rows are gone.

### 7.11 What this run leaves unmeasured

- **Whether a leg-1 repair recovers any of the (1) bucket.** 7.4 sizes the bucket and names
  four mechanisms; it cannot say what fraction hides a findable site. §6.4's levers remain
  class **—**.
- **Whether the parse fix moved the `unclear` rate.** 7.6 shows this frame cannot answer it.
  A page-depth-matched comparison could.
- **The mix stratum's finding rate.** 0/300 with an upper bound of 1.22% is a bound, not an
  estimate.
- **Native-language discovery.** This run was English-only by design.
- **Whether `uncertainty_flags` propagates.** All-`none` is consistent with two very
  different worlds (7.6).

---

## How to update this document

1. Run `g3o presweep-report --run-dir runs/<run_id>` for the funnel figures.
2. Score yield with `g3o.report.discovery_yield.score_run(run_dir, truth)`,
   where `truth` maps `institution_id` → the master's `website`.
3. Bracket the run with `g3o.discovery.serper_client.get_balance()` and report
   the **delta**, never a rate multiplication.
4. Move any line you replace from class **A** or **T** to class **M**, and give
   its sample size and date. Do not delete the superseded figure silently —
   the cost model's ~4× error was invisible precisely because nothing recorded
   what it had been.
