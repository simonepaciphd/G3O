"""Extract layer (Stage 5): per-page LLM extraction in JSON mode via Batch API.

One Batch API call per scraped page. The model returns a ``BatchResponse``
(``g3o.common.contract``) — a ``batch_metadata`` envelope plus a non-empty
``data`` array of canonical Output Contract rows. Per-page calls are batched
across institutions to capture the OpenAI Batch API's 50% pricing tier.

Public surface:

- ``build_extract_job`` / ``build_extract_jobs`` — assemble Stage 5 batch jobs.
- ``submit_extract_batch`` / ``poll_extract_batch`` / ``fetch_extract_results``
  — single-owner Batch API access via ``g3o.common.batch_client``.
- ``parse_extract_result`` — JSON → ``BatchResponse`` with Q1=a access-date
  contract enforcement and Group-D ``_NA_`` salvage.
- ``salvage_group_d_na`` / ``GroupDSalvage`` — repair confirms_activity rows
  whose Group-D fields carry the illegal literal ``_NA_`` (see ``salvage.py``).
- ``RESPONSE_FORMAT`` / ``SYSTEM_MESSAGE`` / ``PROMPT_CACHE_KEY`` — exposed for
  introspection and tests.
"""

from g3o.extract.batch import (
    build_extract_jobs,
    fetch_extract_results,
    make_custom_id,
    poll_extract_batch,
    submit_extract_batch,
    url_hash,
)
from g3o.extract.client import (
    OUTPUT_CONTRACT_TEXT,
    PROMPT_CACHE_KEY,
    RESPONSE_FORMAT,
    SYSTEM_MESSAGE,
    SYSTEM_PROMPT_TEXT,
    build_extract_job,
)
from g3o.extract.parser import parse_extract_result
from g3o.extract.salvage import GroupDSalvage, salvage_group_d_na

__all__ = [
    "OUTPUT_CONTRACT_TEXT",
    "PROMPT_CACHE_KEY",
    "RESPONSE_FORMAT",
    "SYSTEM_MESSAGE",
    "SYSTEM_PROMPT_TEXT",
    "GroupDSalvage",
    "build_extract_job",
    "build_extract_jobs",
    "fetch_extract_results",
    "make_custom_id",
    "parse_extract_result",
    "poll_extract_batch",
    "salvage_group_d_na",
    "submit_extract_batch",
    "url_hash",
]
