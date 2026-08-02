# Pipeline status and measured benchmarks

**Last updated: 2026-08-01** · Branch of record: `feat/discovery-chain`
(`d568a98`, pushed, no PR) · Suite: 727 passed, 1 skipped, 2 deselected,
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
| …usable after placeholder filtering | 14,131 (1.96%) | M |
| — of which national / local | 1,796 / 12,335 | M |
| — United States share of the usable pool | 12,351 (87.4%) | M |
| Distinct countries in the usable pool | 219 | M |
| Rows carrying a `disambiguation` | 217,385 (30.2%) | M |
| Rows with both `duplicate=1` and a `website` | 0 | M |

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

## 3. Stages 1c–7 — not measured

**No live chain run has gone past Stage 1b.** This is the largest gap in the
project's evidence base.

| Stage | Measured | Threshold (T) | Budget assumption (A) |
|---|:--:|---:|---|
| 1c filter_eligibility | — | pass-rate bands set | shadow mode, nothing dropped |
| 3 classify_triage | — | 70% / 40% institutions with a keep; 30% / 15% URL keep-rate | ~40 URLs → ~12 kept |
| 4 scrape | — | 70% / 40% success | ~2.4 rendered URLs / institution |
| 5 extract | — | 70% / 40% success; 30% / 60% empty | ~12 pages / institution |
| 6 validate | — | 80% / 60% consolidated; 40% / 70% unclear | 1 call / institution |
| 7 persist | — | n/a (deterministic) | n/a |

Thresholds are calibrated for a ~10-institution smoke run and are explicitly
PI-tunable; they were **not** derived from observation and should not be read
as expectations.

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
| Serper, `chain` | **1.84 credits / institution** | M (n=200) |
| Serper, `legacy` | 8.52 credits / institution | M (n=200) |
| OpenAI Batch, all LLM stages | — | A only |
| Render fleet | — | A only |

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

1. **The Stage 1a health gauge cannot go red in practice.** `% with ≥1 URL`
   reads 100% under leg 1, so chain mode reports `% with a usable domain`
   instead — which also reads **100%**, because leg 1 nearly always returns
   *some* non-aggregator host, just not always the right one. It catches "only
   aggregators came back" and nothing subtler. The metric that discriminates
   (82% recall) needs ground truth, which the health report has no access to by
   design (it is disk-only). **The health report currently cannot detect leg-1
   accuracy regression.**
2. **`discovery_yield.py` only runs where ground truth exists** — 1.96% of the
   registry, unrepresentatively national.
3. **Whole-run aborts — fixed report-side, 2026-08-02.** A run that died
   mid-flight used to leave queued institutions classified `NO_EVIDENCE_FOUND`.
   `g3o/report/outcomes.py` now reads the `_state/.done/{stage}.json` markers
   and issues `NO_EVIDENCE_FOUND` only when every configured stage completed;
   otherwise the institution is `PROCESSING_INCOMPLETE`, naming the stage the
   run never finished. **Residual:** this catches a loud abort (no marker). It
   cannot see silent loss inside a stage that completed and wrote its marker —
   that needs run-time reconciliation in `run_state` / `batch_client`, which is
   a separate, unimplemented work item.
4. **The disambiguation slot is unmeasured.** It ships on first principles;
   zero of the 200 ground-truth institutions carry one.

---

## 6. Avenues for improvement

Ordered by expected value per unit of effort. Items 1–3 buy evidence; 4–7 buy
yield; 8–10 buy durability.

### Buy evidence first

1. **End-to-end run through Stage 6 on ~100 institutions.** Produces the first
   measured Stage 3–7 numbers *and* the first measured OpenAI cost, resolving
   the prompt-cache-stacking question that 68% of the budget hangs on. Cost:
   ~200 Serper credits plus real Batch spend; wall-clock in hours, since Stage 2
   alone took 208 s for three institutions. **This is the highest-value action
   available and nothing downstream should be tuned before it.**
2. **Build a subnational ground-truth set.** ~200 hand-verified websites for US
   local government and non-US subnational units. Unblocks the disambiguation
   slot (30% of the registry) and answers whether 64.5% survives contact with
   the 98% of the master nobody has measured. Without it, every yield figure
   G3O quotes carries an unquantified generalisation gap.
3. **Diagnose why `legacy` Stage 2 finds 13/200.** The chain routes around this
   rather than fixing it, so the defect is still live in any legacy replication
   and its cause is unknown.

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

8. **Give the health report an accuracy signal.** Today it cannot detect leg-1
   regression (§5.1). Options: persist a small held-out ground-truth set into
   the run, or have the chain record whether Stage 2's pick matches the master's
   `website` where one exists — cheap, and turns 2% coverage into a live
   regression canary rather than a one-off study.
9. **Recalibrate `thresholds.py` against measured values** once item 1 lands.
   They are currently smoke-run guesses and will either never fire or fire
   constantly at production scale.
10. ~~**Fix the whole-run-abort misattribution** (§5.3) and the `_cmd_discover`
    cp1252 crash (search succeeds; only the print dies).~~ **Both done
    2026-08-02.** The abort fix is report-side only — see §5.3 for the residual.
    The CLI now forces UTF-8 on stdout/stderr at entry (`cli._force_utf8_streams`),
    so `PYTHONIOENCODING=utf-8` is no longer needed as a workaround.

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
