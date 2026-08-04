"""Stage 5 — Per-page LLM extraction.

Builds the OpenAI Batch API job for one (institution × scraped page) pair.
Loads the canonical extraction prompts from ``g3o/extract/prompts/`` and
emits a ``BatchJob`` with ``response_format=json_schema`` derived from the
Pydantic ``BatchResponse`` model in ``g3o.common.contract``.

Per pipeline-spec §1: scrape-then-extract mode. The model evaluates the
supplied page text and produces 0+ canonical contract rows per page.

Per Q1 (2026-05-09, decision (a)): the scrape access date is injected into
the per-page user message and the LLM copies it verbatim into
``source_access_date``. ``parser.parse_extract_result`` enforces that
contract (no silent overwrite).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.common.batch_client import BatchJob
from g3o.common.contract import BatchResponse
from g3o.scrape.render import RenderedPage

PROMPT_CACHE_KEY = "g3o.extract.v1"

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_SYSTEM_PROMPT_PATH = _PROMPTS_DIR / "system_prompt.md"
_OUTPUT_CONTRACT_PATH = _PROMPTS_DIR / "output_contract.md"


def _load_prompt_assets() -> tuple[str, str]:
    """Load the system instructions and the output-contract schema from disk."""
    system_prompt = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    output_contract = _OUTPUT_CONTRACT_PATH.read_text(encoding="utf-8")
    return system_prompt, output_contract


SYSTEM_PROMPT_TEXT, OUTPUT_CONTRACT_TEXT = _load_prompt_assets()


# The system message is the persona + Output Contract schema concatenated, with a
# clear separator. Identical across all jobs in a batch so OpenAI's prompt caching
# (≥1024 tokens, matching prefix) hits.
SYSTEM_MESSAGE = (
    f"{SYSTEM_PROMPT_TEXT}\n\n"
    f"---\n\n"
    f"# G3O Output Contract v2.3 (canonical reference)\n\n"
    f"{OUTPUT_CONTRACT_TEXT}"
)


def _inline_defs(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively inline ``$defs`` / ``$ref`` for OpenAI strict-mode JSON schemas.

    Mirrors the pattern used in ``g3o.classify.url_triage`` so OpenAI's
    ``response_format=json_schema`` ``strict=true`` validator does not need to
    follow refs (some SDK paths still trip on them).
    """
    defs = schema.pop("$defs", {})

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node and len(node) == 1:
                ref = node["$ref"]
                # Form: "#/$defs/Name"
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
    """OpenAI ``response_format=json_schema`` payload for ``BatchResponse``."""
    schema = BatchResponse.model_json_schema()
    schema = _inline_defs(schema)
    schema["additionalProperties"] = False
    # Strip Pydantic's "title" cosmetics; not required by OpenAI strict mode.
    schema.pop("title", None)
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "g3o_batch_response_v2",
            "strict": True,
            "schema": schema,
        },
    }


RESPONSE_FORMAT: dict[str, Any] = _build_response_format()


def _user_prompt(
    institution_row: dict[str, Any],
    scraped_page: RenderedPage,
    *,
    batch_id: str,
    institution_search_languages: str,
    chat_type: str = "web",
    model_label: str | None = None,
    notes: str = "none",
) -> str:
    """Build the per-page user message.

    Embeds the batch-level metadata (so the LLM populates ``batch_metadata``
    correctly with `n_data_rows` etc.), the institution row (so all
    institution-shared fields are copied verbatim per consistency check #4),
    and the page envelope (URL, title, text, scrape access date per Q1=a).
    """
    payload = {
        "batch_metadata_inputs": {
            "batch_id": batch_id,
            "chat_type": chat_type,
            "model_label": model_label or "gpt-5-nano",
            "search_languages": institution_search_languages,
            "search_strategy_summary": (
                "URLs supplied by the G3O pipeline (Stage 1 Discovery via Serper, "
                "Stages 2 + 3 official-site + URL-triage classifiers). "
                "The model evaluates the supplied page texts only."
            ),
            "notes": notes,
        },
        "institution": institution_row,
        "institution_search_languages": institution_search_languages,
        "page": {
            "source_url": scraped_page.url,
            "source_title": scraped_page.title,
            "source_access_date": scraped_page.fetch_metadata.access_date,
            "content_type": scraped_page.content_type,
            "text": scraped_page.text,
        },
    }
    return (
        "You are extracting one batch response per (institution × supplied page). "
        "Produce a JSON object that matches the Output Contract schema in your "
        "system instructions. Use the provided `source_access_date` verbatim in "
        "every row's `source_access_date` field.\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_extract_job(
    institution_row: dict[str, Any],
    scraped_page: RenderedPage,
    *,
    custom_id: str,
    batch_id: str,
    institution_search_languages: str,
    chat_type: str = "web",
    model_label: str | None = None,
    notes: str = "none",
) -> BatchJob:
    """Build a ``BatchJob`` for Stage 5 extraction of one (institution × page) pair."""
    if not custom_id:
        raise ValueError("custom_id is required and must be non-empty")
    if not institution_search_languages:
        raise ValueError("institution_search_languages is required")
    return BatchJob(
        custom_id=custom_id,
        messages=[
            {"role": "system", "content": SYSTEM_MESSAGE},
            {
                "role": "user",
                "content": _user_prompt(
                    institution_row,
                    scraped_page,
                    batch_id=batch_id,
                    institution_search_languages=institution_search_languages,
                    chat_type=chat_type,
                    model_label=model_label,
                    notes=notes,
                ),
            },
        ],
        response_format=RESPONSE_FORMAT,
        prompt_cache_key=PROMPT_CACHE_KEY,
        metadata={
            "stage": "5_extract",
            "institution_id": institution_row.get("institution_id", ""),
            "source_url": scraped_page.url,
        },
    )


__all__ = [
    "PROMPT_CACHE_KEY",
    "SYSTEM_MESSAGE",
    "SYSTEM_PROMPT_TEXT",
    "OUTPUT_CONTRACT_TEXT",
    "RESPONSE_FORMAT",
    "build_extract_job",
]
