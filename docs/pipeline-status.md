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

> **Status 2026-08-02 (superseding the hold below).** Run
> `20260802-e2e-100` — 100 institutions, `--stop-after scrape`,
> `--filter-mode shadow`, seed 22294, chain defaults, code at `191803c` — is
> complete. Stages 1c, 3 and 4 are now class **M**. Stages 5–7 remain unrun
> **deliberately**: the codebook is still an open decision register, so their
> yield, empty rate and token counts would describe a schema about to change.
> Stopping after scrape was a PI decision taken on the reasoning below, and it
> still answered the cost model's dominant uncertainty (§4) off the Stage 2 and
> Stage 3 Batch responses.
>
> *Prior hold, 2026-08-02 (resolved):* the run was first prepared and held
> pending the codebook rework, because Stages 5 and 6 are two of the four Batch
> stages the run exists to measure. That reasoning is why 5–7 are still blank;
> it did not apply to 1c/3/4, which no codebook change can touch.

| Stage | Measured (n=100, 2026-08-02) | Threshold (T) | Budget assumption (A) |
|---|:--|---:|---|
| 1c filter_eligibility | **2.2% pass** (36/1,648); would-drop 97.8%; **shadow recall 3.9%** vs a 70% bar | pass-rate bands set | shadow mode, nothing dropped ✓ |
| 3 classify_triage | **51.6% URL keep** (831/1,610); **96%** of institutions with a keep | 70% / 40% institutions with a keep; 30% / 15% URL keep-rate | ~40 URLs → ~12 kept |
| 4 scrape | **99.4% success** (826/831); 0 errors; 5 robots-disallowed; 83 render fallbacks | 70% / 40% success | ~2.4 rendered URLs / institution |
| 5 extract | — *(not run — codebook open)* | 70% / 40% success; 30% / 60% empty | ~12 pages / institution |
| 6 validate | — *(not run — codebook open)* | 80% / 60% consolidated; 40% / 70% unclear | 1 call / institution |
| 7 persist | — *(not run)* | n/a (deterministic) | n/a |

Stages 3 and 4 clear their thresholds comfortably. **Stage 1c does not, and the
gap is not a threshold-calibration problem.** Of the 831 URLs Stage 3's triage
kept, only 32 also pass the 1c draft rules — 3.9% against PI decision 6's
provisional bar of ≥70%. Switching `filter_mode` to `enforce` on these rules
would discard ~96% of what the pipeline currently considers worth reading. The
dominant drop reason is `no_genai_signal` (1,527 of 1,612), which is what a
URL-string GenAI test does to homepages and about-pages: leg 1 is *supposed* to
return the homepage, so the filter is penalising the chain for working. Whether
to redesign the 1c rules, restrict them to the 1b leg, or retire the stage is a
design decision, not a recalibration — flagged, not acted on.

Thresholds were calibrated for a ~10-institution smoke run and are explicitly
PI-tunable; they were **not** derived from observation. They have deliberately
**not** been recalibrated to the values above: n=100 is one sample, Stages 5–7
are still unmeasured, and fitting the gauges to this run is the failure mode the
measurement task was written to avoid.

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
| OpenAI Batch, Stages 5 + 6 | — | A only (not run) |
| Render fleet | — | A only |

Run `20260802-e2e-100` spent **184 Serper credits for 100 institutions —
1.84/institution, reproducing the n=200 figure exactly** as an independent
`get_balance()` delta (45,727 → 45,543).

### The dominant uncertainty is resolved: prompt caching does **not** stack with the Batch discount

Measured off the Batch responses, not assumed. `prompt_tokens_details.cached_tokens`
is **0 on all 300 batched jobs** across three independent batches (Stage 2,
Stage 3, and the §5.5 control arm). Budget lines must therefore price batched
input at the full uncached rate, halved once by the Batch discount and not
again.

| Stage (n=100) | jobs | input | cached | output | *of which reasoning* | USD |
|---|---:|---:|---:|---:|---:|---:|
| 2 classify_official_site | 100 | 74,817 | **0** | 129,844 | 123,648 | $0.0278 |
| 3 classify_triage | 100 | 111,162 | **0** | 516,621 | 421,952 | $0.1061 |
| **total** | **200** | **185,979** | **0** | **646,465** | **545,600** | **$0.1339** |

**The cost driver is reasoning, not prompt length.** Reasoning tokens are 84.4%
of all output tokens, and input is only 22% of total tokens, at the pinned
`reasoning_effort="medium"`. This has two consequences worth carrying:

1. `reasoning_effort` is a larger cost lever than any prompt-length edit, and it
   is currently pinned in `batch_client.py` rather than being a run parameter.
2. It **weakens** the cost half of the Stage 5/6 codebook hold (§3): a codebook
   prompt-length change moves cost far less than feared. The yield and
   empty-rate half of that argument is untouched and still stands on its own.

Stages 5 and 6 are the expensive ones and remain unmeasured, so the $1.34 /
1,000 figure is **not** a whole-pipeline cost and must not be compared against
the cost model's $17.52 / 1,000 as though it were.

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

**OpenAI is ~68% of the modeled budget and rests on an unverified assumption**
(whether prompt caching stacks with the Batch discount). No live LLM-stage cost
has ever been measured. This is the second-largest evidence gap.

Session spend for the record: 2,273 credits (smoke 6, chain arm 368, legacy arm
1,704, leg-1 quoted arm 195; leg-1 unquoted arm 0, fully cache-served).

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

---

## 6. Avenues for improvement

Ordered by expected value per unit of effort. Items 1–3 buy evidence; 4–7 buy
yield; 8–10 buy durability.

### Buy evidence first

1. ~~**End-to-end run through Stage 6 on ~100 institutions.**~~ **Partly done
   2026-08-02** — run `20260802-e2e-100` went through Stage 4 (§3). It resolved
   the prompt-cache-stacking question that 68% of the budget hung on (it does
   **not** stack, §4) and produced measured 1c/3/4 numbers. **Still open: Stages
   5–7**, held until the codebook decision register closes, since their yield and
   empty rate would describe a superseded schema. Actuals for the part that ran:
   184 Serper credits, $0.13 OpenAI, 2 h 15 min wall-clock at
   `--max-workers 4`, of which scrape was ~80%. Resuming for 5–7 costs only the
   two remaining Batch stages — `--execute` against the same `--run-id` reuses
   the completed stages off `_state/`.
   **New highest-value item from this run: the Stage 1c rule set (§3), which
   would discard ~96% of triage keeps if enforced.**
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
