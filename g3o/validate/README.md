# `g3o.validate` — cross-source merge and consolidation

**Status:** scaffold (Push #1). Implementation lands in Push #2.

The validate layer takes structured records from `g3o.extract` (one
per institution × activity × source) and produces:

- a deduplicated `g3o_full_database_v{N}.csv` (one row per
  institution × activity × source after consolidation), and
- an `g3o_institution_summary_v{N}.csv` (one row per institution with
  rolled-up activity and tool fields).

Conservative merge rules (per the paper): primary sources outrank secondary
reporting; uncertainty flags propagate forward; disagreements between
sources surface in `uncertainty_flags` rather than silent overwrites.

## What lands in Push #2

- `merge.py` — institution × activity dedup, source-family precedence,
  uncertainty flag propagation.
- `qc.py` — per-run QC summary (row counts, blank-required-field counts,
  source-family breakdown), mirroring the local pilot's
  `merge_qc_summary.txt` artifact.
- CLI: `python -m g3o validate --inputs <extract.jsonl> --out <final/>`.
