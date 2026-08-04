# Pipeline status and measured benchmarks

**Last updated: 2026-08-02** · Branch of record: `main` (`8877db6`, PR #24 —
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
