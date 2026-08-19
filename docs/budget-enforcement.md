# Budget Enforcement

G3O provides two layers of cost protection to prevent unexpected API spend:

1. **Pre-flight cost gate**: Estimates total cost before any batches are submitted
2. **Runtime cost monitor**: Tracks actual spend during execution and aborts if budget is exceeded

Both layers are opt-in and can be configured via environment variables or CLI flags.

## Overview

The pre-flight gate (in `g3o.run.preflight`) projects the total OpenAI Batch API cost for a planned run based on sample size, pages per institution, and token estimates. If the projection exceeds your budget, the run aborts with exit code 3 before any API calls are made.

The runtime monitor (in `g3o.common.cost_monitor`) tracks actual token usage as each LLM stage completes. If cumulative spend exceeds your budget mid-run, the orchestrator raises `BudgetExceededError` and aborts cleanly, persisting a cost report for post-mortem analysis.

**Important**: The runtime monitor checks budget **after each stage completes**, not continuously. A single stage (e.g., a large extract batch) may spend significantly more than the remaining budget before the check triggers. Set your budget ceiling with enough headroom for one full stage's cost.

**Serper API costs are not tracked**. Serper uses a separate billing model (per-query credits, not token-based) and is not included in the running total. Only OpenAI Batch API spend is monitored. Factor Serper credits into your budget separately.

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
Projected OpenAI Batch cost: $15.23 USD
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
| `total_input_usd` | float | Sum of input costs across all stages |
| `total_output_usd` | float | Sum of output costs across all stages |
| `total_usd` | float | Total actual spend (input + output) |
| `pricing` | object | Pricing rates used (see below) |
| `vs_preflight_estimate` | object or null | Comparison to pre-flight projection (if preflight was run) |

### `stages` array

Each element represents one LLM stage:

```json
{
  "stage": "extract",
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
  "batch_input_per_1m_usd": 0.025,
  "batch_output_per_1m_usd": 0.20,
  "batch_cached_input_per_1m_usd": 0.0025,
  "batch_line_is_estimate": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `model` | string | The model used |
| `batch_input_per_1m_usd` | float | Cost per 1M prompt tokens (non-cached) |
| `batch_output_per_1m_usd` | float | Cost per 1M completion tokens |
| `batch_cached_input_per_1m_usd` | float | Cost per 1M cached prompt tokens |
| `batch_line_is_estimate` | boolean | True if the batch rates are estimates (see note below) |

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

### Scenario 4: Serper cost not included in budget

**Symptom**: Serper credits are depleted faster than expected, even though the OpenAI budget was not exceeded.

**Cause**: The runtime monitor only tracks OpenAI Batch API spend. Serper API calls (Stages 1a and 1b) use a separate billing model (per-query credits) and are not included in the running total.

**Resolution**:
- Factor Serper credits into your budget separately
- Monitor Serper credit balance in the Serper dashboard
- Reduce `--discovery-results-per-query` or use `--discovery-mode legacy` to reduce Serper spend

---

## Limitations

1. **Check-after-stage only**: Budget is checked after each LLM stage completes, not continuously. A single stage may exceed the budget before the check triggers. The budget ceiling should therefore be set with enough headroom for one full stage's cost.

2. **Serper cost not tracked**: Serper API calls have a separate billing model (per-query credits, not token-based) and are not included in the running total. Only OpenAI Batch API spend is monitored. Factor Serper credits into your budget separately.

3. **Pricing estimates**: The batch rates for `gpt-5-nano` are labeled as estimates because OpenAI's documentation does not explicitly publish the batch discount for this model. Reconcile against your first live invoice to verify the actual rates.

4. **Mid-stage abort not supported**: If a stage is running when the budget is exceeded, the stage will complete before the abort triggers. The orchestrator cannot interrupt a stage mid-execution.

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
