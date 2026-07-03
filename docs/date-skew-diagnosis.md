# Diagnosis + options memo — the "2024 skew" in G3O dates

**For:** PI (Simone Paci)
**From:** RA engineer (ra_003), branch `feature/batch-3-date-diagnosis`
**Date:** 2026-07-02
**Status:** Diagnosis + recommendation only. **No collection-changing code has been
written.** Adding a recency filter to discovery needs your sign-off (it changes what
we collect).

> Doc note: the task referenced `00-OVERVIEW.md` and `01-working-agreement.md`; neither
> exists in this repo. I oriented off `README.md`, `docs/architecture.md`, and
> `g3o/discovery/README.md` instead. Flagging in case those files live elsewhere.

## Bottom line

The PI's hypothesis is **confirmed**. There is no date/recency filter anywhere in
discovery — we could not have "misconfigured" one because none exists. The temporal
concentration is **substantive** (real-world GenAI-in-government activity clusters
post-ChatGPT, 2023–2025), not a search artifact: it appears at the same magnitude in
the human-curated external inventories that involve no web search at all.

Secondary correction: the skew is better described as a **2023–2025 recency
concentration** than a "2024 skew." 2024 is only the single modal year in one slice.

## 1. No date handling in discovery (confirmed, with code)

**Query construction** (`g3o/discovery/query_builder.py:47-48`) — the query is just the
institution name × a GenAI term. No date operators, no `after:`/`before:`:

```python
for term in terms + extras:
    queries.append((f'"{institution_name}" "{term}"', lang))
```

**The Serper request** (`g3o/discovery/serper_client.py:114-115`) sends exactly two
fields — `q` and `num`. No `tbs`, no date range:

```python
headers = {"X-API-KEY": config.SERPER_API_KEY, "Content-Type": "application/json"}
payload = json.dumps({"q": query, "num": num_results})
```

A repo-wide grep for `tbs|qdr|recency|cd_min|cd_max|date_range|freshness|before:|after:`
across `g3o/` returns nothing relevant (only a `stop_after` stage name and a batch
pagination cursor `after`). We *do* passively read a `date` field off each result
(`serper_client.py:171`, `"date": item.get("date")`) but never filter or rank on it.

**Serper recency support & its cost.** Serper passes through Google's `tbs` time filter,
i.e. `tbs=qdr:d|w|m|y` (past day/week/month/year; a trailing count like `qdr:y2` = past
2 years also works). So a recency bias *is* available to us at ~zero implementation cost
(one payload field). The **coverage cost** is the real issue: `qdr:` restricts to pages
Google can date *and* that fall in-window, which would **drop undated pages and older
"we launched X in 2023" announcements** — exactly the early-adoption signal we most want
to keep. See §3.

## 2. The skew, in numbers (pilot v1, `data/pilot_v1/g3o_full_database_v1.csv`, n=1,336)

`source_publication_date` is **73% `unknown`** (only 360 rows dated). Among dated rows
and for the activity-year fields:

| field | modal year | 2024 | 2025 | 2023–2025 combined |
|---|---|---|---|---|
| `source_publication_date` (dated n=360) | 2025 | 27.8% | **53.6%** | 86.4% |
| `year_announced` (dated n=498) | 2024 | **49.0%** | 20.1% | 91.6% |
| `year_deployed` (dated n=339) | 2024 | **42.2%** | 29.5% | 91.7% |

## 3. It is not a search artifact (the decisive test)

Pilot v1 was assembled from three acquisition modes: ChatGPT-web search (485 rows),
external-DB ingest (575 rows — US Federal AI Use Case Inventory, EC PSTW, etc.), and RA
manual coding (276 rows). The external DBs involve **no web search at all**. If the skew
were a search-ranking effect, it would show up in the search rows and *not* in the
hand-curated inventories. Instead, the 2023–2025 concentration is present everywhere:

| acquisition mode | `year_announced` 2023–25 | `source_publication_date` 2023–25 |
|---|---|---|
| search (ChatGPT-web) | 89.3% | 82.5% |
| external-DB ingest (no search) | 88.2% | 91.9% |
| RA manual coding | 84.4% | (no dated rows) |

Two caveats that make this evidence *directional, not dispositive* for the production
pipeline:

1. **Pilot v1 was not built with Serper.** It predates the API pipeline. So it cannot
   directly test the Stage-1 Serper layer — but §1 already settles that by code
   inspection (no filter exists). The pilot characterizes the *phenomenon*.
2. GenAI-in-government is genuinely young (ChatGPT launched Nov 2022), so a real
   temporal floor near 2023 is expected regardless of method.

## 4. Options

### (a) Leave discovery as-is — recency-neutral
- **Changes about coverage:** nothing. We keep retrieving whatever Google ranks,
  including undated and older pages.
- **Cost:** none to coverage. The "skew" persists in the data — but it's a true
  property of the phenomenon, so it's a finding to *report*, not a bug to fix. Risk is
  only presentational (readers misreading the histogram as a filter artifact).

### (b) Add an optional recency bias at discovery (`tbs=qdr:*`)
- **Changes about coverage:** narrows retrieval to Google-dateable, in-window pages.
- **Cost:** **suppresses undated pages and older announcements** — precisely the
  early-adopter records (2020–2023) that make the panel valuable. Given 73% of pilot
  sources are undated, a `qdr` filter could silently discard a large fraction of hits.
  It also *changes what we collect* across runs, which breaks comparability of the
  quarterly panel unless applied uniformly and versioned. Only defensible as an
  explicitly-flagged, off-by-default knob for targeted "what's new this quarter" sweeps
  — never as the default.

### (c) Post-hoc weighting / flagging (no collection change)
- **Changes about coverage:** nothing at collection. We compute date coverage/skew
  diagnostics at analysis time — e.g. a per-run `date_coverage` stat (% undated, year
  histogram) and an optional recency weight or `is_recent` flag for downstream slices.
- **Cost:** modest analysis code + a documented caveat. Preserves the full record,
  keeps the panel comparable, and makes the skew transparent instead of hidden.

## Recommendation (yours to decide)

**(a) for discovery + (c) for reporting.** Keep discovery recency-neutral so we don't
amputate early-adoption and undated evidence, and add a post-hoc date-coverage
diagnostic so the 2023–2025 concentration is characterized honestly as a property of the
domain. Hold (b) as an explicit, versioned, off-by-default option only if you later want
targeted freshness sweeps — I'd want your sign-off before wiring it, since it changes
what we collect.

I have not touched any collection code. Tell me which option and I'll scope the
implementation.
