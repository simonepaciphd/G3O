# Budget Enforcement

G3O provides two layers of cost protection to prevent unexpected API spend:

1. **Pre-flight cost gate**: Estimates total cost before any batches are submitted
2. **Runtime cost monitor**: Tracks actual spend during execution and aborts if budget is exceeded

Both layers are opt-in and can be configured via environment variables or CLI flags.

## Overview

**One ceiling covers every paid API** (PI ruling, 2026-10-02): OpenAI, TypeSafe
jev, Serper and the Bright Data Web Unlocker. Before that date the ceiling
covered LLM tokens only, and the preflight priced the jev stages at OpenAI rates.

| API | Unit | Rate | Where | Counted at runtime |
|---|---|---|---|---|
| OpenAI (Batch) | tokens | per model row | `pricing.PRICING` | after each chunk and stage |
| TypeSafe jev | input tokens | $0.042 / 1M | `pricing.PRICING["jev-1.13.0"]` | after each call |
| Serper | credits (response `credits` field; 1 at `num=10`) | **$0.001 / credit**, overridable with `G3O_SERPER_USD_PER_CREDIT` (package-dependent) | `pricing.SERPER_PRICING` | each live query; enforced before the next query |
| Bright Data Web Unlocker | response bytes, successful requests | **$8 / GB** (10^9 B) | `pricing.UNLOCKER_PRICING` | each call; enforced before the next Stage 4 fetch |
| Residential proxy (`G3O_SCRAPE_PROXY`) | proxied GB | not priced | — | **not counted**; unset on the production host |

The Serper and unlocker rates are PI-supplied and flagged as estimates; the
unlocker byte count is the body the API returned, which may differ from Bright
Data's own count. Reconcile both against the first invoice.

The pre-flight gate (in `g3o.run.preflight`) projects the total cost of a planned run across all four APIs: each LLM stage at its own model's rates, Serper at a credits-per-institution figure taken from the discovery config (4.50 for the config of run `r20260912T001021Z-f4fb`, n=20,293, with cache hits counted as live), and the unlocker at the escalation rate measured on that run (0.47 requests per institution) times an assumed 250 KB per request — about twice the measured 128 KB mean. If the projection (`est_total_usd`) exceeds your budget, the run aborts with exit code 3 before any API calls are made.

The runtime monitor (in `g3o.common.cost_monitor`) tracks actual token usage as each LLM stage completes, and Serper and unlocker usage as each billable response arrives (via `g3o.common.spend_meter`). If cumulative spend exceeds your budget mid-run, the orchestrator raises `BudgetExceededError` and aborts cleanly, persisting a cost report for post-mortem analysis.

**Important**: LLM spend is checked after each chunk and each stage; Serper and unlocker spend before every query and every Stage 4 fetch. Calls already in flight (up to `max_workers`) finish after the ceiling is crossed, so set the ceiling with some headroom.

---

## Enabling Budget Enforcement

### Pre-flight gate

The pre-flight gate is enabled by setting either:

- **Environment variable**: `G3O_BUDGET_LIMIT_USD=<usd_amount>`
- **CLI flag**: `--cost-ceiling <usd_amount>` (overrides the env var)

Example:

```bash
# Via environment variable
export G3O_BUDGET_LIMIT_USD=10.00
python -m g3o presweep --preflight --run-id test --master-csv master.csv --sample-size 100

# Via CLI flag (takes precedence)
python -m g3o presweep --preflight --run-id test --master-csv master.csv --sample-size 100 --cost-ceiling 10.00
```

If the projected cost exceeds the budget, the command exits with code 3 and prints a circuit breaker message to stderr.

### Runtime monitor

The runtime monitor is automatically enabled when you set a budget via the same mechanisms:

```bash
# Set budget for runtime monitoring
export G3O_BUDGET_LIMIT_USD=10.00
python -m g3o presweep --execute --run-id test --master-csv master.csv --sample-size 100
```

The orchestrator will track actual spend after each LLM stage and abort if the running total exceeds the budget.

### Two further controls, both off by default

Neither is set by the runbook, and both change whether enforcement actually
enforces. They were documented nowhere outside the source until 2026-08-24.

#### `G3O_COST_MONITOR_DRY_RUN` — **disables enforcement**

| | |
|---|---|
| Values | `true`/`1`/`yes`/`on` — or `false`/`0`/`no`/`off`/empty (default) |
| CLI equivalent | `--cost-monitor-dry-run` |
| Default | off |

Read the name carefully: this is **not** "report what a budget would have done".
When it is on, a run that exceeds its budget **logs a warning and keeps
spending**. The stage is recorded in `budget_exceeded_stages` for the
post-mortem, `abort_stage` stays `null`, and the run continues to completion.

Use it to calibrate a ceiling on a run you are willing to pay for in full. Do
not use it on a run whose ceiling is the thing protecting you.

#### `G3O_PROJECTION_SAFETY_FACTOR` — enables the mid-run projection abort

| | |
|---|---|
| Values | a float `>= 1.0` |
| CLI equivalent | `--projection-safety-factor <float>` |
| Default | **unset, meaning the projection abort does not run at all** |

There is deliberately no default value. Unset does not mean "1.2" or any other
number — it means the check is off. With it set, the monitor scales the
remaining stages' preflight estimates by the actual-to-estimated ratio observed
so far and aborts *before* the next stage if the projected total would exceed
`budget x factor`.

It is opt-in because the projection scales the two cheap classify stages'
ratio onto the dominant extract estimate, and those stages are not comparable
enough for that ratio to end a live run uninvited. The ratio is clamped to
[0.5, 3.0] and the check is skipped until at least two stages have completed.

---

## What Happens When Budget Is Exceeded

### Pre-flight abort

If the pre-flight projection exceeds the budget:

- Exit code: **3**
- Message printed to stderr:

```
======================================================================
COST CIRCUIT BREAKER TRIGGERED
======================================================================
Projected cost, all paid APIs: $15.23 USD
Budget limit: $10.00 USD
Overrun: $5.23 USD

Aborting before batch submission to prevent budget overrun.

To proceed:
  1. Increase budget: export G3O_BUDGET_LIMIT_USD=<higher_value>
  2. Use --cost-ceiling <higher_value> to override
  3. Reduce sample size or scope to lower projected cost
======================================================================
```

No API calls are made. No state files are written.

### Runtime abort

If the runtime monitor detects budget overrun:

- Exit code: **3**
- Message printed to stderr:

```
======================================================================
BUDGET EXCEEDED — RUN ABORTED
======================================================================
Stage: extract
Actual spend so far: $10.2345 USD
Budget limit:        $10.0000 USD
Overrun:             $0.2345 USD

The run has been aborted to prevent further budget overrun.
Cost report and completed stages have been persisted.

To proceed with a higher budget:
  export G3O_BUDGET_LIMIT_USD=20.00
======================================================================
```

The orchestrator catches `BudgetExceededError` and exits cleanly. The `finally` block persists:

- `_cost_report.json` with full cost breakdown
- `institution_report.jsonl` and `institution_report.csv`
- `run_summary.json` and human-readable summary

Completed stages remain on disk and can be resumed if you re-run with a higher budget.

---

## Interpreting `_cost_report.json`

The cost report is a JSON file written to `runs/<run_id>/_cost_report.json` on every exit path (success, early `--stop-after`, or budget abort). It contains:

### Top-level fields

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | string | The run identifier |
| `budget_usd` | float or null | The configured budget limit (null if no limit) |
| `budget_exceeded` | boolean | True if `total_usd > budget_usd` |
| `abort_stage` | string or null | The stage that triggered the abort (null if run completed) |
| `stages` | array | Per-stage cost breakdown (see below) |
| `total_prompt_tokens` | integer | Sum of prompt tokens across all stages |
| `total_completion_tokens` | integer | Sum of completion tokens across all stages |
| `total_cached_tokens` | integer | Sum of cached tokens across all stages |
| `total_input_usd` | float | Sum of LLM input costs across all stages |
| `total_output_usd` | float | Sum of LLM output costs across all stages |
| `llm_total_usd` | float | LLM token spend (input + output) |
| `metered_total_usd` | float | Serper + Web Unlocker spend |
| `total_usd` | float | Total actual spend, every paid API (`llm_total_usd + metered_total_usd`) — the figure the ceiling is enforced on |
| `by_api` | object | Spend per API: `openai`, `typesafe` (`usd`); `serper` (`usd`, `credits`, `live_queries`, `usd_per_credit`); `brightdata_unlocker` (`usd`, `requests`, `requests_succeeded`, `billable_bytes`, `usd_per_gb`) |
| `pricing` | object | Pricing rates of the run-wide model (see below); per-stage models are on each `stages` row |
| `vs_preflight_estimate` | object or null | Comparison to pre-flight projection (if preflight was run) |

### `stages` array

Each element represents one LLM stage:

```json
{
  "stage": "extract",
  "model": "gpt-5-nano",
  "prompt_tokens": 500000,
  "completion_tokens": 50000,
  "cached_tokens": 300000,
  "input_usd": 0.012500,
  "output_usd": 0.010000,
  "total_usd": 0.022500,
  "n_jobs": 100,
  "n_chunks": 2
}
```

| Field | Type | Description |
|-------|------|-------------|
| `stage` | string | Stage name (e.g., `classify_official_site`, `classify_triage`, `extract`, `validate`) |
| `model` | string | The model whose rates priced this row (`jev-*` for TypeSafe stages) |
| `prompt_tokens` | integer | Total prompt tokens for this stage |
| `completion_tokens` | integer | Total completion tokens for this stage |
| `cached_tokens` | integer | Total cached tokens for this stage |
| `input_usd` | float | Input cost for this stage |
| `output_usd` | float | Output cost for this stage |
| `total_usd` | float | Total cost for this stage (input + output) |
| `n_jobs` | integer | Number of LLM calls in this stage |
| `n_chunks` | integer | Number of chunks the jobs were split into |

### `pricing` object

The pricing rates used to compute costs:

```json
{
  "model": "gpt-5-nano",
  "priced": true,
  "batch_input_per_1m_usd": 0.025,
  "batch_output_per_1m_usd": 0.20,
  "batch_cached_input_per_1m_usd": 0.0025,
  "batch_line_is_estimate": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `model` | string | The model the run actually submitted — and the model these rates are for. Before 2026-08-24 this was hard-wired to `gpt-5-nano` regardless of what ran (review F2). |
| `priced` | boolean | False when no rate row is registered for `model`; every USD figure in the report is then `null` |
| `batch_input_per_1m_usd` | float | Cost per 1M prompt tokens (non-cached) |
| `batch_output_per_1m_usd` | float | Cost per 1M completion tokens |
| `batch_cached_input_per_1m_usd` | float | Cost per 1M cached prompt tokens |
| `batch_line_is_estimate` | boolean | True if the batch rates are estimates (see note below) |

**Pricing is keyed by model id** (2026-08-24, review F2). Rates live in
`g3o.common.pricing.PRICING`, one row per model, and the row is selected by the
model the run submits — `--model`, `OPENAI_MODEL`, or the `PresweepConfig`
field. Until this change every projection and every cost report used the
`gpt-5-nano` table whatever model actually ran, so a one-word config change
silently under-reported spend and the breaker did not fire.

Two consequences for a run on a model with **no** registered row:

- **with a cost ceiling set, the run refuses to start.** A ceiling is a promise
  to stop at a number, and that promise cannot be kept for a model whose price
  is unknown. The refusal comes from the pre-flight, before anything is spent.
- **without a ceiling, the run proceeds** and reports `"priced": false`, the
  real model id, and `null` for every USD field. The token counts stay exact —
  they are measured; only the conversion to dollars is unavailable. Reporting
  `0.0` there would assert a spend that did not happen.

There is deliberately no "assume gpt-5-nano" fallback and no
`--allow-unpriced-model` flag. Adding a model means adding a row with its own
verified rates and its own `verified_on`.

**Note on pricing estimates**: The batch rates for `gpt-5-nano` are labeled as estimates because OpenAI's documentation does not explicitly publish the batch discount for this model. The rates are derived by applying the documented 50% batch discount (shown for the sibling `gpt-5.4-nano` model) to the published standard rates. **Reconcile against your first live invoice** to verify the actual rates.

### `vs_preflight_estimate` object

If preflight was run before execution, this field compares actual spend to the projection:

```json
{
  "preflight_est_usd": 0.05,
  "actual_usd": 0.0225,
  "ratio": 0.45
}
```

| Field | Type | Description |
|-------|------|-------------|
| `preflight_est_usd` | float | The pre-flight projection |
| `actual_usd` | float | The actual spend |
| `ratio` | float | `actual_usd / preflight_est_usd` (1.0 = perfect estimate) |

A ratio significantly above 1.0 suggests the preflight assumptions (pages per institution, tokens per job) were too low. Adjust the `--assume-*` flags accordingly.

---

## Common Failure Scenarios

### Scenario 1: Preflight abort

**Symptom**: Command exits with code 3 before any batches are submitted.

**Cause**: The projected cost exceeds the budget limit.

**Resolution**:
- Increase the budget: `export G3O_BUDGET_LIMIT_USD=<higher_value>` or `--cost-ceiling <higher_value>`
- Reduce sample size: `--sample-size <lower_value>`
- Reduce scope: `--stop-after classify_official_site` to run fewer stages
- Adjust preflight assumptions if they're too conservative: `--assume-pages-per-institution`, `--assume-output-tokens-per-job`

### Scenario 2: Runtime abort after extract

**Symptom**: Run aborts after the extract stage with "Budget exceeded" message.

**Cause**: The actual spend (sum of all stages up to extract) exceeded the budget.

**Resolution**:
- Increase the budget for the next run
- Reduce sample size
- Review `_cost_report.json` to see which stages dominated the cost
- Consider running extract with a smaller subset of institutions

### Scenario 3: Single stage exceeds budget before check triggers

**Symptom**: Final spend is significantly above the budget limit (e.g., budget was $10, but final spend is $15).

**Cause**: The runtime monitor checks budget after each stage completes. If a single stage (e.g., a large extract batch with 1000 jobs) costs $5, and the budget was $10 with $6 spent so far, the stage will complete ($11 total) before the check triggers.

**Resolution**:
- Set the budget ceiling with enough headroom for one full stage's cost
- Use preflight to estimate per-stage costs and set the budget accordingly
- Consider breaking large runs into smaller chunks (e.g., multiple runs with smaller sample sizes)

### Scenario 4: Run aborts during discovery or scrape

**Symptom**: `abort_stage` is a discovery stage or `scrape`, and `by_api` shows most of the spend under `serper` or `brightdata_unlocker`.

**Cause**: Since 2026-10-02 Serper and Web Unlocker spend count toward the ceiling. An institution interrupted mid-discovery writes no artifact, exactly as on a Serper failure, so a resume re-issues it; scrape keeps every page already written.

**Resolution**:
- Check `G3O_SERPER_USD_PER_CREDIT` matches the package you bought
- Raise the ceiling deliberately, or reduce `--sample-size`
- Compare `by_api` with the preflight's `est_by_api` to see which assumption was off

---

## Limitations

1. **Check-after-stage only**: Budget is checked after each LLM stage completes, not continuously. A single stage may exceed the budget before the check triggers. The budget ceiling should therefore be set with enough headroom for one full stage's cost.

2. **The residential proxy is not counted**: `G3O_SCRAPE_PROXY` bills per proxied GB, which the process cannot observe. It is unset on the production host; a run that sets it spends outside the ceiling, and the preflight and `g3o doctor` say so.

3. **Pricing estimates**: The batch rates for `gpt-5-nano` are labeled as estimates because OpenAI's documentation does not explicitly publish the batch discount for this model. Reconcile against your first live invoice to verify the actual rates.

4. **In-flight calls finish**: an abort stops new work; LLM batches already submitted, Serper queries and fetches already in flight complete first.

5. **Enforcement can be switched off, and one switch is easy to misread**: `G3O_COST_MONITOR_DRY_RUN=true` makes a budget overrun a **warning rather than an abort** — the run continues spending past its ceiling. It reports; it does not enforce. See "Two further controls" above.

6. **The mid-run projection abort is off unless asked for**: `G3O_PROJECTION_SAFETY_FACTOR` has no default. Without it, the only checks are the pre-flight projection and the after-each-stage actual — so a run can be visibly on course to overshoot and will not stop until it has.

---

## Examples

### Example 1: Setting a budget and running preflight

```bash
# Set budget limit
export G3O_BUDGET_LIMIT_USD=10.00

# Run preflight to estimate cost
python -m g3o presweep \
  --preflight \
  --run-id 20260811-test \
  --master-csv master.csv \
  --sample-size 100

# Output:
# {
#   "cost_preview": {
#     "est_openai_batch_total_usd": 8.23
#   },
#   "cost_ceiling_exceeded": false
# }
```

The projection ($8.23) is under the budget ($10.00), so the run can proceed.

### Example 2: Running with a budget and reading the cost report

```bash
# Set budget limit
export G3O_BUDGET_LIMIT_USD=10.00

# Run the pipeline
python -m g3o presweep \
  --execute \
  --run-id 20260811-test \
  --master-csv master.csv \
  --sample-size 100

# Output (to stderr):
# Cost: $7.4523 actual vs $8.2300 estimated (91% of preflight estimate)

# Read the cost report
cat runs/20260811-test/_cost_report.json | jq .
```

The actual spend ($7.45) was under the budget ($10.00), so the run completed successfully. The cost report shows a detailed breakdown by stage.

### Example 3: Responding to a budget abort

```bash
# Run with a low budget
export G3O_BUDGET_LIMIT_USD=5.00
python -m g3o presweep \
  --execute \
  --run-id 20260811-test \
  --master-csv master.csv \
  --sample-size 100

# Output (to stderr):
# ======================================================================
# BUDGET EXCEEDED — RUN ABORTED
# ======================================================================
# Stage: extract
# Actual spend so far: $5.2345 USD
# Budget limit:        $5.0000 USD
# Overrun:             $0.2345 USD
# ...

# Check the cost report to see which stages dominated
cat runs/20260811-test/_cost_report.json | jq '.stages[] | {stage, total_usd}'
# [
#   {"stage": "classify_official_site", "total_usd": 0.1234},
#   {"stage": "classify_triage", "total_usd": 0.2345},
#   {"stage": "extract", "total_usd": 4.8766}
# ]

# Extract dominated the cost. Options:
# 1. Increase the budget
# 2. Reduce sample size
# 3. Run extract separately with a smaller subset
```

---

## See Also

- `docs/budget/cost-model.md` — Detailed cost model and pricing assumptions
- `g3o.run.preflight` — Pre-flight cost estimation
- `g3o.common.cost_monitor` — Runtime cost monitoring implementation
- `g3o.common.pricing` — Shared pricing constants
