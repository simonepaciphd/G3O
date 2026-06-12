# G3O pipeline cost model

**Status: provisional — order-of-magnitude, not billing-grade.** This model is a
linear projection of the full-sweep budget recompute (review F20, 2026-06-11). It
inherits every assumption of that recompute, including the unresolved
prompt-cache stacking question (below), and is pending researcher sign-off before
it anchors any external figure. The machine-readable companion is
[`cost-model.csv`](./cost-model.csv).

It estimates the cost of one full pipeline sweep at three institution-universe
sizes — **1,000 / 100,000 / 675,000** institutions — broken out by **Serper**,
**OpenAI Batch**, and **infrastructure**.

## What scales, and what doesn't

The pipeline is one call (or a fixed handful of calls) per institution at each
LLM stage, so the **variable** cost is linear in institution count:

- **Serper discovery** — ~4 queries/institution.
- **OpenAI Batch** — official-site classify (1 call), URL triage (1 call),
  extraction (~12 pages), validation (1 consolidation call) per institution, all
  on `gpt-5-nano` via the Batch API.
- **Headless render fleet** — ~2.4 rendered URLs/institution; provisioned compute
  sized for the sweep's scrape window, so it scales with render volume.

**Standing infrastructure** does not scale with institution count: the
orchestration VM + managed Postgres ($1,019/yr) is fixed capacity, and database
storage floors at the smallest Spaces tier (~$60/yr) until retained text exceeds
250 GB (~$72/yr at the full universe). This is why the model reports
**per-sweep variable cost** and **standing infra per year** separately rather
than fabricating a sweep cadence — the cadence (how many full sweeps run per
quarter/year) is a research/operations decision, not an engineering constant.
Multiply per-sweep variable cost by your chosen cadence and add the annual
standing infra to get a periodized figure.

## Per-institution unit rates (basis of the projection)

Derived by dividing each full-sweep budget line by the budget's modeled universe
(~770,000 institutions). All figures use the budget's per-call rates verbatim.

| Component | Line item | $ / institution | Scenario |
|---|---|---|---|
| Serper | discovery search | $0.0022403 | invariant |
| OpenAI Batch | official-site classifier | $0.0001325 | invariant |
| OpenAI Batch | URL triage | $0.0004000 | invariant |
| OpenAI Batch | information extraction | **$0.0118584** | conservative (no cache stack) |
| OpenAI Batch | information extraction | $0.0065896 | optimistic (cache stacks) |
| OpenAI Batch | information validation | $0.0013909 | invariant |
| Infra | headless render fleet | $0.0014961 | invariant |

## Per-scale summary

Per-sweep variable cost (USD), with the standing infra line shown per year:

| | 1,000 | 100,000 | 675,000 |
|---|---:|---:|---:|
| Serper | 2.24 | 224.03 | 1,512.18 |
| OpenAI Batch (conservative) | 13.78 | 1,378.18 | 9,302.73 |
| Render fleet | 1.50 | 149.61 | 1,009.87 |
| **Per-sweep total (conservative)** | **17.52** | **1,751.82** | **11,824.78** |
| *Per-sweep total (optimistic)* | *12.25* | *1,224.94* | *8,268.32* |
| Standing infra / year | 1,079 | 1,079 | 1,082 |

Cross-check: at the full 770k universe the conservative per-sweep variable total
is ~$13,489, matching the budget's variable + render lines
($1,725 + $102 + $308 + $9,131 + $1,071 + $1,152).

## The dominant uncertainty: prompt-cache stacking

Extraction is **~68% of the variable cost**, and its figure hinges on one
unresolved question. Each extraction call sends an identical ~9,756-token system
message (persona + Output Contract). That prefix is cache-eligible (≥1,024
tokens), and OpenAI prompt caching discounts cached input up to 90%
($0.05 → $0.005 / 1M). **Whether prompt caching stacks with the Batch API's
discount is not documented** (verified silent at developers.openai.com,
2026-06-11). `architecture.md` assumes it does; that assumption is unverified.

- **Conservative (headline):** caching does *not* stack → extraction priced at
  the full system-message overhead. This model's headline figures.
- **Optimistic:** caching stacks → extraction system-message overhead is largely
  discounted, cutting the per-sweep total by ~30%.

**Resolve with telemetry, not estimate.** The first live pre-sweep invoice
reports cached-token counts directly. Recompute the extraction line against the
measured counts then, and confirm the stacking behavior empirically.

## Assumptions, caveats, and provenance

- **Source:** `docs/budget/budget-draft-05-08-26.md` (parent G3O workspace, not
  in this repo), Information-extraction recompute note, review F20.
- **Per-institution counts** (4 queries, 12 pages, 2.4 renders) are universe
  averages baked into the budget; real per-institution counts vary by country,
  institution size, and web presence. The first live pre-sweep replaces these
  averages with measured telemetry.
- **Pricing** is taken from the budget's per-stage dollar figures verbatim
  ($0.05/1M input, $0.40/1M output for `gpt-5-nano`). Whether those already
  reflect the Batch 50% discount is the same telemetry question as cache
  stacking — do not treat the figures as Batch-discounted until the first
  invoice confirms it. Verified facts (2026-06-11): `gpt-5-nano` standard input
  $0.05/1M, cached input $0.005/1M, output $0.40/1M; Batch input-file limit
  200 MB; 50,000 requests/batch; caching minimum 1,024 tokens.
- **Render fleet** is modeled as linear in render volume. In practice it floors
  at one droplet-month: at 1,000 institutions you provision one small droplet
  briefly, not a $1.50 slice of the full fleet.
- **Not modeled:** one-time engineering, RA labor, Serper top-up-pack
  granularity (packs are bought in fixed sizes), and any second search backend
  (WS1 pending-decision C-1).

## How to update

1. After the first live pre-sweep, read cached-token counts and actual
   per-stage spend from the OpenAI invoice + Serper dashboard.
2. Replace the per-institution unit rates above with measured values.
3. Resolve the cache-stacking scenario empirically; collapse the
   conservative/optimistic split to a single extraction rate.
4. Re-derive the per-scale table and `cost-model.csv` from the updated rates.

---

*Generated by the engineer persona, session 2026-06-11 (WS4 T9). Provisional and
pending researcher sign-off; figures are a linear projection of an
order-of-magnitude budget with an unverified caching assumption, not verified
costs.*
