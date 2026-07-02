"""Validate layer (Stage 6): per-institution LLM consolidation + deterministic QC.

One Batch API call per institution that takes all extract-stage rows for that
institution and consolidates them into a final per-institution record. The model
applies the source-credibility hierarchy from the Output Contract, dedupes
activities within institution, and propagates uncertainty flags. Deterministic
QC (row counts, blank-required-field counts, source-family breakdown) runs
afterwards.

See ``g3o/validate/prompts/system_prompt.md`` and ``output_contract.md`` for
the canonical contract; ``g3o.common.contract.ConsolidatedInstitutionResponse``
is the runtime schema source of truth.
"""

from __future__ import annotations

from g3o.validate.client import (
    OUTPUT_CONTRACT_TEXT,
    PROMPT_CACHE_KEY,
    RESPONSE_FORMAT,
    SYSTEM_MESSAGE,
    SYSTEM_PROMPT_TEXT,
    build_consolidate_job,
)
from g3o.validate.consolidate import (
    assemble_per_institution_inputs,
    build_consolidate_jobs,
    fetch_consolidate_results,
    load_extract_outputs,
    make_consolidate_custom_id,
    parse_consolidate_result,
    poll_consolidate_batch,
    run_consolidate,
    submit_consolidate_batch,
    write_consolidated_output,
)
from g3o.validate.qc import (
    qc_per_institution,
    qc_per_run,
    speculative_adoption_activities,
    weak_generative_signal_activities,
)

__all__ = [
    "OUTPUT_CONTRACT_TEXT",
    "PROMPT_CACHE_KEY",
    "RESPONSE_FORMAT",
    "SYSTEM_MESSAGE",
    "SYSTEM_PROMPT_TEXT",
    "assemble_per_institution_inputs",
    "build_consolidate_job",
    "build_consolidate_jobs",
    "fetch_consolidate_results",
    "load_extract_outputs",
    "make_consolidate_custom_id",
    "parse_consolidate_result",
    "poll_consolidate_batch",
    "qc_per_institution",
    "qc_per_run",
    "run_consolidate",
    "speculative_adoption_activities",
    "submit_consolidate_batch",
    "weak_generative_signal_activities",
    "write_consolidated_output",
]
