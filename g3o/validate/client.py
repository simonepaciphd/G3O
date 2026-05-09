"""Stage 6 — Per-institution LLM consolidation (client).

Builds the OpenAI Batch API job for one institution. Loads the canonical
validation prompts from ``g3o/validate/prompts/`` and emits a ``BatchJob``
with ``response_format=json_schema`` derived from
``g3o.common.contract.ConsolidatedInstitutionResponse``.

The Stage 6 LLM consumes all Stage 5 ``ContractRow`` rows for one institution
and returns a single canonical ``ConsolidatedInstitutionResponse``. One
``BatchJob`` per institution; the institution_id is the ``custom_id`` so the
result can be matched back deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.common.batch_client import BatchJob
from g3o.common.contract import ConsolidatedInstitutionResponse

PROMPT_CACHE_KEY = "g3o.validate.v1"

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_SYSTEM_PROMPT_PATH = _PROMPTS_DIR / "system_prompt.md"
_OUTPUT_CONTRACT_PATH = _PROMPTS_DIR / "output_contract.md"


def _load_prompt_assets() -> tuple[str, str]:
    """Load the system instructions and the output-contract schema from disk."""
    system_prompt = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    output_contract = _OUTPUT_CONTRACT_PATH.read_text(encoding="utf-8")
    return system_prompt, output_contract


SYSTEM_PROMPT_TEXT, OUTPUT_CONTRACT_TEXT = _load_prompt_assets()


# Persona + Validation Contract concatenated. Identical across all jobs in a
# batch so OpenAI prompt caching (≥1024 tokens, matching prefix) hits.
SYSTEM_MESSAGE = (
    f"{SYSTEM_PROMPT_TEXT}\n\n"
    f"---\n\n"
    f"# G3O Validation Contract v1.0 (canonical reference)\n\n"
    f"{OUTPUT_CONTRACT_TEXT}"
)


def _inline_defs(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively inline ``$defs`` / ``$ref`` for OpenAI strict-mode JSON schemas.

    Mirrors ``g3o.extract.client._inline_defs``.
    """
    defs = schema.pop("$defs", {})

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node and len(node) == 1:
                ref = node["$ref"]
                name = ref.split("/")[-1]
                if name not in defs:
                    raise KeyError(
                        f"$ref {ref!r} could not be resolved against $defs keys "
                        f"{sorted(defs)}"
                    )
                return _walk(json.loads(json.dumps(defs[name])))
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(item) for item in node]
        return node

    return _walk(schema)


def _build_response_format() -> dict[str, Any]:
    """OpenAI ``response_format=json_schema`` payload for ``ConsolidatedInstitutionResponse``."""
    schema = ConsolidatedInstitutionResponse.model_json_schema()
    schema = _inline_defs(schema)
    schema["additionalProperties"] = False
    schema.pop("title", None)
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "g3o_consolidated_institution_v1",
            "strict": True,
            "schema": schema,
        },
    }


RESPONSE_FORMAT: dict[str, Any] = _build_response_format()


def _user_prompt(
    institution_row: dict[str, Any],
    input_rows: list[dict[str, Any]],
    *,
    n_input_pages: int,
    model_label: str | None = None,
    notes: str = "none",
) -> str:
    """Build the per-institution user message.

    Embeds the consolidation-metadata inputs (so the LLM populates
    ``consolidation_metadata`` correctly), the institution row (for the
    institution-level block), and the flat list of Stage 5 ``ContractRow``
    objects to consolidate.
    """
    payload = {
        "consolidation_metadata_inputs": {
            "institution_id": institution_row.get("institution_id", ""),
            "n_input_pages": n_input_pages,
            "n_input_rows": len(input_rows),
            "model_label": model_label or "gpt-5-nano",
            "notes": notes,
        },
        "institution": institution_row,
        "stage5_rows": input_rows,
    }
    return (
        "You are consolidating one institution's worth of Stage 5 extract rows "
        "into a single canonical record. Produce a JSON object that matches "
        "the G3O Validation Contract v1.0 schema in your system instructions.\n\n"
        "Rules of thumb (full text in system instructions):\n"
        "- Activity dedup by `activity_name`; near-duplicates stay separate "
        "with `scope_unclear` flag.\n"
        "- Conflict resolution: Tier 1 > Tier 2 > Tier 3 (most-recent date "
        "tiebreaker, then largest snippet).\n"
        "- Uncertainty flags: union across input rows, alphabetical order.\n"
        "- `has_genai_activity` verdict from §3.1 of the contract.\n"
        "- `activity_id` and `source_id` sequences are gapless (`A1, A2, ...`; "
        "`S1, S2, ...`) in input-row-appearance order.\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_consolidate_job(
    institution_row: dict[str, Any],
    input_rows: list[dict[str, Any]],
    *,
    custom_id: str,
    n_input_pages: int,
    model_label: str | None = None,
    notes: str = "none",
) -> BatchJob:
    """Build a ``BatchJob`` for Stage 6 consolidation of one institution."""
    if not custom_id:
        raise ValueError("custom_id is required and must be non-empty")
    if n_input_pages < 1:
        raise ValueError("n_input_pages must be ≥1")
    if not input_rows:
        raise ValueError("input_rows must be non-empty")
    return BatchJob(
        custom_id=custom_id,
        messages=[
            {"role": "system", "content": SYSTEM_MESSAGE},
            {
                "role": "user",
                "content": _user_prompt(
                    institution_row,
                    input_rows,
                    n_input_pages=n_input_pages,
                    model_label=model_label,
                    notes=notes,
                ),
            },
        ],
        response_format=RESPONSE_FORMAT,
        prompt_cache_key=PROMPT_CACHE_KEY,
        metadata={
            "stage": "6_validate",
            "institution_id": institution_row.get("institution_id", ""),
            "n_input_rows": len(input_rows),
        },
    )


__all__ = [
    "PROMPT_CACHE_KEY",
    "SYSTEM_MESSAGE",
    "SYSTEM_PROMPT_TEXT",
    "OUTPUT_CONTRACT_TEXT",
    "RESPONSE_FORMAT",
    "build_consolidate_job",
]
