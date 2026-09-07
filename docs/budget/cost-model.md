# G3O pipeline cost model

> **Measured figures live in [`../pipeline-status.md`](../pipeline-status.md).**
> This document *projects*; that one records what has been observed. Where the
> two disagree, the measurement wins — the Serper line here was understated by
> ~4× until 2026-08-01.

**Status: provisional — order-of-magnitude, not billing-grade.** This model is a
linear projection of the full-sweep budget recompute (review F20, 2026-06-11). It
inherits every assumption of that recompute, including the unresolved
prompt-cache stacking question (below), and is pending researcher sign-off before
it anchors any external figure. The machine-readable companion is
[`cost-model.csv`](./cost-model.csv).

It estimates the cost of one full pipeline sweep at three institution-universe
sizes — **1,000 / 100,000 / 675,000** institutions — broken out by **Serper**,
**OpenAI Batch**, and **infrastructure**.

**One line does not fit that shape.** Residential proxy egress (issue #90) bills
**per gigabyte of traffic**, not per institution or per token, and is projected
separately in [its own section](#residential-proxy-egress--per-gb-the-first-non-per-institution-cost-line).
It is off by default and no run has ever incurred it.

## What scales, and what doesn't

The pipeline is one call (or a fixed handful of calls) per institution at each
LLM stage, so the **variable** cost is linear in institution count:

- **Serper discovery** — see the correction immediately below; the modeled ~4
  queries/institution does not match what the pipeline issues.
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

## Correction — the Serper line is understated (2026-08-01)

**The Serper discovery figures below are wrong and are retained only until the
confirmation run replaces them.** Two independent problems:

1. **Query count.** The model assumes ~4 queries/institution. The pipeline in
   `discovery_mode="legacy"` issues **16**: `GENAI_TERMS_BY_LANG["en"]` holds
   eight terms (expanded from four on 2026-07-04, PI sign-off), Stage 1a emits
   one query per term, and Stage 1b wraps each of those eight in `site:`. The
   modeled count predates that expansion and never counted both stages.
2. **Per-credit rate is unresolved and is a PI input, not an engineering
   constant.** The $2.24/1,000-institution line implies ~$0.00056/query at 4
   queries. The findings memo prices credits at **$0.001** each. Serper sells
   credits in packs whose unit price falls with pack size, so both can be
   defensible — but they differ by ~1.8×, and this model should not silently
   pick one. **Flagged for the PI; not resolved here.**

### Measured, not modeled (confirmation run, 2026-08-01)

200 institutions per arm, same sample, seed 22294, drawn from master rows with
a usable `website`. Spend is a `GET /account` **balance delta**, not arithmetic:

| Mode | Design cost | **Measured credits/inst** | Total (n=200) |
|---|---:|---:|---:|
| `legacy` (production) | 16 | **8.52** | 1,704 |
| `chain` | 2 | **1.84** | 368 |

**Production does not actually cost 16 credits/institution — it costs ~8.5**,
and the gap is a symptom rather than a saving. Legacy Stage 1a's GenAI-term
queries rarely surface an institution's own homepage, so Stage 2 found an
official site for only **13 of 200 institutions (6.5%)**, and Stage 1b — which
runs only for institutions that have one — was skipped for the other 187.
Production is cheaper than designed because most of it never runs. Under the
chain, Stage 2 found a site for 176/200 (88%).

So the chain's saving is **6.68 credits/institution**, not 14:

| At 719,588 institutions | $0.00056/credit | $0.001/credit |
|---|---:|---:|
| `legacy` measured (8.52) | $3,434 | $6,131 |
| `chain` measured (1.84) | $742 | $1,324 |
| **Saving** | **$2,692** | **$4,807** |

Do not propagate the per-intervention figure of −$5,757 from the findings memo
for interventions #1 and #2 individually: that is 8 credits × 719,588 ×
$0.001, but each change is 8 → 1, so the arithmetic saving is 7 credits =
−$5,037 each. Both figures are in any case superseded by the measured rates
above, which price the baseline as it actually behaves rather than as designed.

A caveat that cuts the other way: if Stage 2's official-site rate under legacy
were repaired *without* adopting the chain, legacy's cost would rise toward its
16-credit design figure rather than stay at 8.5.

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

## Residential proxy egress — per-GB, the first non-per-institution cost line

**Added 2026-08-27 (issue #90). Evidence class: the byte rates are M, the dollar
figures are A and stay A until a proxied run measures them.** No G3O run has ever
fetched a page through a proxy, and **Bright Data's actual per-GB rate under the
partnership is not known to this document** — the figures below are therefore
parameterised on the rate rather than asserting one. That distinction is
load-bearing: the Serper line above was wrong by ~4× because an assumption
travelled unlabelled, and this is the second unlabelled assumption that document
nearly acquired.

**Every other line in this model is per-institution or per-token. Residential
proxies bill per gigabyte of traffic**, so `$1,000/month` of partnership credits
is a quantity of *bytes*, not of runs, and nothing in this model previously
represented that at all.

### Why the bytes had to be measured rather than read off disk

**G3O records no byte counts anywhere.** `FetchMetadata`
(`g3o/scrape/render.py:36`, `extra="forbid"`) holds `access_date`, `http_status`,
`final_url`, `fetch_method`, `elapsed_ms`, `wait_for` — and no content length.
`scrape/*.json.gz` artifacts hold *extracted text*, gzipped: for HTML the
stripped text, for PDF the extracted text, both far smaller than what crossed the
wire. Reading the artifacts would have understated a PDF by more than an order of
magnitude.

So the rates below were **measured directly, on 2026-08-27**, by re-fetching a
stratified sample of the URLs run `r20260824T215623Z-bb4e` actually scraped
(one URL per host, so no host was hit twice; `RobotsCache` consulted per URL;
bodies counted and discarded, never stored):

| path | n (2xx with body) | mean | median | p90 | max |
|---|---:|---:|---:|---:|---:|
| HTML fetch | 196 | **176.9 KB** | 90.0 KB | 305 KB | 5.5 MB |
| PDF fetch | 99 | **1,759.0 KB** | 589.8 KB | 4.3 MB | 16.8 MB |
| render — document only | 76 | 79.4 KB | 62.0 KB | 182 KB | 414 KB |
| **render — full page load** | 54 | **5,441.9 KB** | 2,044 KB | 8.7 MB | **102.9 MB** |

Measured from a residential ISP, deliberately: the droplet is the blocked
identity (0/120 on the paired probe), so measuring there would have counted
tiny 403/406 error pages and understated everything. A residential ISP is the
closest available analogue of the residential-proxy path.

Render figures are CDP `Network.loadingFinished.encodedDataLength` — compressed
bytes actually on the wire, per response, which is what a proxy meters — summed
across every request the page issued (**mean 65.8 responses per page**).

### The finding: the render fallback is two-thirds of the egress bill

**Answering the question the cost model never asked.** A headless render pulls
every subresource — images, fonts, CSS, JS, analytics — that a plain HTTP fetch
never touches. It is **69× the document alone**, and on run `bb4e`'s fetch mix
(12,598 HTML / 2,021 PDF / 2,255 render over 16,874 fetches):

| path | share of fetches | **share of bytes** |
|---|---:|---:|
| HTML | 74.7% | 12.2% |
| PDF | 12.0% | 19.5% |
| **render** | **13.4%** | **68.3%** |

**13% of fetches are 68% of the traffic, and nobody has ever counted it.** If
render subresources bill at the same per-GB rate as the document — which is the
assumption to confirm with the vendor, not with this document — then the render
fallback is the dominant per-GB cost line, and it is the one lever that could cut
the bill by roughly two-thirds. **Whether to disable the render fallback on a
proxied run is a substantive trade, not an engineering one:** the render exists to
recover JS-shell pages, so turning it off trades yield for bytes. Flagged for the
PI, not decided here.

A second observation with no home elsewhere: **there is no byte budget anywhere
in the pipeline.** The cost circuit breaker (`#42`, `#52`) meters tokens and
Serper credits. A single 103 MB page load — measured, not hypothetical — is
invisible to it.

### Weighted rate and per-scale projection

Weighted mean **1,080.6 KB per fetch** on `bb4e`'s mix.

Volumes come from the **n=500 wave-2 probe** (`r20260826T214131Z-4cd7`), not from
`bb4e`, because wave 2's frame behaves differently: 718 fetches succeeded and 227
URL-attempts failed across 500 institutions. Through a working proxy the
block-shaped failures largely succeed instead — 145 of the 227 were `HTTPError`
(a server answered with a refusing status), and the wave-1 residential arm
recovered 75.8% — so ~110 attempts convert, giving **828 fetches / 500
institutions = 1.656 fetches per frame institution ⇒ ~1.75 MB per frame
institution.**

| frame size | projected egress |
|---|---:|
| 1,000 | 1.7 GB |
| **10,000 (wave 2)** | **17.1 GB** |
| 22,000 (wall-clock ceiling) | 37.5 GB |
| 719,588 (full universe) | **1,228 GB ≈ 1.2 TB** |

### What the credits buy — parameterised, because the rate is unknown

Per 10,000-institution wave, and what `$1,000/month` of credits covers:

| rate | $ / wave | waves per $1,000 |
|---|---:|---:|
| $1/GB | $17 | 58.6 |
| $3/GB | $51 | 19.5 |
| $5/GB | $85 | 11.7 |
| $8/GB | $137 | 7.3 |
| $10/GB | $171 | 5.9 |

**Read across, not down.** Two conclusions survive every column:

1. **At wave scale the credits are not the binding constraint.** Even at $10/GB,
   `$1,000/month` buys ~6 waves of 10,000. Egress cost is not a reason to defer a
   wave.
2. **At full-universe scale it is material.** 1.2 TB at $8/GB is ~$9,800 per
   sweep — comparable to the entire OpenAI Batch line — and at `$1,000/month` of
   credits a single full sweep would consume ~10 months of them.

**Marginal cost per additional wave after the credits are exhausted** is the
`$ / wave` column, unchanged: this line is purely linear in bytes, with no fixed
component and no tier assumed.

### To resolve, in priority order

1. **Get the actual per-GB rate from the console or the agreement.** One number
   collapses the table above to a single column. Until then every dollar figure
   here is class **A**.
2. **Confirm whether render subresource traffic is billed at the same rate.** It
   is 68% of the projection; a different treatment changes the headline more than
   anything else on this page.
3. **Instrument bytes.** `FetchMetadata` forbids extras, so recording
   `content_length` is a schema change — but until it exists, every figure here
   has to be re-measured out of band rather than read out of a run. Note the
   2026-08-26 decision to retain raw bytes transiently (researcher-log,
   *evidence-layer custody*, decision 1) would make this free as a side effect.
4. **Re-measure per-institution fetch volume on the frame actually being run.**
   1.656 fetches/institution is wave-2's probe; `bb4e` ran 4.22, a 2.5× spread
   driven by Stage-2 attrition rather than by anything about egress.

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
