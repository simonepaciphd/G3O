# Enabling TypeSafe jev Decision Model

This guide explains how to enable the TypeSafe jev decision model for different stages of the G3O pipeline.

## Overview

The jev integration replaces gpt-5-nano with TypeSafe's jev decision model for decision-shaped stages:
- **Stage 2** (classify_official_site): Official website classification
- **Stage 3** (classify_triage): URL triage (keep/drop decisions)
- **Stage 6** (validate): Validation and consolidation

Stage 5 (extract) remains on gpt-5-nano as it performs text generation, not decision-making.

## Prerequisites

1. **TypeSafe API Key**: Obtain from [TypeSafe Console](https://console.typesafe.ai)
2. **Set environment variable**:
   ```bash
   export TYPESAFE_API_KEY="your-api-key-here"
   ```

## Method 1: CLI Flags (Recommended for Testing)

Use per-stage model override flags to enable jev for specific stages:

### Enable jev for All Decision Stages

```bash
python -m g3o presweep \
  --master-csv data/master_institutions.csv \
  --sample-size 100 \
  --classify-official-site-model jev-1.13.0 \
  --classify-triage-model jev-1.13.0 \
  --validate-model jev-1.13.0 \
  --execute
```

### Enable jev for Specific Stages

**Stage 2 only (official site classification):**
```bash
python -m g3o presweep \
  --master-csv data/master_institutions.csv \
  --classify-official-site-model jev-1.13.0 \
  --execute
```

**Stage 3 only (URL triage):**
```bash
python -m g3o presweep \
  --master-csv data/master_institutions.csv \
  --classify-triage-model jev-1.13.0 \
  --execute
```

**Stage 6 only (validation):**
```bash
python -m g3o presweep \
  --master-csv data/master_institutions.csv \
  --validate-model jev-1.13.0 \
  --execute
```

### Mixed Configuration

You can mix jev and gpt-5-nano across stages:

```bash
python -m g3o presweep \
  --master-csv data/master_institutions.csv \
  --model gpt-5-nano \
  --classify-official-site-model jev-1.13.0 \
  --classify-triage-model jev-1.13.0 \
  --extract-model gpt-5-nano \
  --validate-model jev-1.13.0 \
  --execute
```

## Method 2: Programmatic Configuration

For programmatic usage, set per-stage models in `PresweepConfig`:

```python
from g3o.run.presweep.config import PresweepConfig
from pathlib import Path

config = PresweepConfig(
    run_id="my-run",
    runs_dir=Path("./runs"),
    master_csv=Path("./data/master_institutions.csv"),
    sample_size=100,
    
    # Pipeline-wide default (used when stage-specific model not set)
    model="gpt-5-nano",
    
    # Per-stage overrides
    classify_official_site_model="jev-1.13.0",
    classify_triage_model="jev-1.13.0",
    extract_model="gpt-5-nano",  # Stage 5 must use gpt-5-nano
    validate_model="jev-1.13.0",
)
```

## Verification

### Check Model Selection

The `model_for_stage()` method returns the effective model for each stage:

```python
print(config.model_for_stage("classify_official_site"))  # jev-1.13.0
print(config.model_for_stage("classify_triage"))          # jev-1.13.0
print(config.model_for_stage("extract"))                  # gpt-5-nano
print(config.model_for_stage("validate"))                 # jev-1.13.0
```

### Verify API Connectivity

Test the jev API connection:

```bash
python scripts/verify_jev_validate_live.py
```

This script:
1. Resolves the TypeSafe API key
2. Creates a jev client
3. Sends a test request
4. Validates the response

### Check Run Manifest

After a run, inspect the manifest to confirm which models were used:

```bash
cat runs/my-run/manifest.json | jq '.llm_provenance'
```

Expected output:
```json
{
  "classify_official_site": {
    "request_model": "jev-1.13.0",
    "response_model": "jev-1.13.0"
  },
  "classify_triage": {
    "request_model": "jev-1.13.0",
    "response_model": "jev-1.13.0"
  },
  "extract": {
    "request_model": "gpt-5-nano",
    "response_model": "gpt-5-nano-2024-12-01"
  },
  "validate": {
    "request_model": "jev-1.13.0",
    "response_model": "jev-1.13.0"
  }
}
```

## Cost Comparison

Based on the integration plan, jev offers significant cost savings for decision stages:

| Stage | gpt-5-nano Cost | jev Cost | Savings |
|-------|----------------|----------|---------|
| Stage 2 (per 1k institutions) | $0.13 | $0.03 | 77% |
| Stage 3 (per 1k institutions) | $0.40 | $0.08 | 80% |
| Stage 6 (per 1k institutions) | $1.39 | $0.25 | 82% |

**Total savings**: ~$1.60 per 1,000 institutions when using jev for all decision stages.

## Troubleshooting

### "TypeSafe API key is not set"

**Problem**: Missing `TYPESAFE_API_KEY` environment variable.

**Solution**:
```bash
export TYPESAFE_API_KEY="your-api-key-here"
```

### "No pricing information available for model: jev-1.13.0"

**Problem**: Cost monitoring enabled but jev pricing not configured.

**Solution**: This should not happen in the current implementation as jev pricing is hardcoded in `g3o/common/pricing.py`. If you see this error, check that you're using the latest code.

### "Stage 5 must use gpt-5-nano"

**Problem**: Attempting to use jev for Stage 5 (extract).

**Solution**: Stage 5 performs text generation, not decision-making. jev is designed for structured decision tasks. Keep Stage 5 on gpt-5-nano:

```bash
--extract-model gpt-5-nano  # or omit to use pipeline default
```

### Slow Performance

**Problem**: jev requests are slower than expected.

**Solution**: 
- jev is synchronous (not batch), so expect ~1-2 seconds per request
- For large runs, consider the throughput: ~1,200 requests/minute
- Monitor with `--cost-ceiling` to track spend in real-time

## Advanced Configuration

### Custom Confidence Thresholds

The jev integration uses hardcoded confidence thresholds. To adjust them, modify:

- **Stage 2**: `g3o/classify/jev_official_site.py` - `CONFIDENCE_THRESHOLD`
- **Stage 3**: `g3o/classify/jev_url_triage.py` - `CONFIDENCE_THRESHOLD`
- **Stage 6**: `g3o/validate/jev_validate.py` - confidence logic in `_assemble_response()`

### Question Set Versioning

Each jev stage has a versioned question set:
- Stage 2: `g3o.classify.official_site.jev.v1`
- Stage 3: `g3o.classify.url_triage.jev.v1`
- Stage 6: `g3o.validate.jev.v1`

These are recorded in the output artifacts for reproducibility.

## Migration Path

### Phase 1: Test on Small Sample

```bash
python -m g3o presweep \
  --master-csv data/master_institutions.csv \
  --sample-size 10 \
  --classify-official-site-model jev-1.13.0 \
  --classify-triage-model jev-1.13.0 \
  --validate-model jev-1.13.0 \
  --execute
```

### Phase 2: Compare with Baseline

Run the same sample with gpt-5-nano:

```bash
python -m g3o presweep \
  --master-csv data/master_institutions.csv \
  --sample-size 10 \
  --model gpt-5-nano \
  --execute
```

Compare outputs:
```bash
python -m g3o run-diff runs/baseline-run runs/jev-run
```

### Phase 3: Gradual Rollout

1. Enable jev for Stage 2 only, validate results
2. Enable jev for Stage 3, validate results
3. Enable jev for Stage 6, validate results
4. Full rollout with all decision stages on jev

## Support

For issues or questions:
- Check the integration plan: `jev-integration-plan.md`
- Review test scripts: `scripts/verify_jev_*.py`
- Inspect run artifacts: `runs/<run-id>/<institution-id>/*.json`
