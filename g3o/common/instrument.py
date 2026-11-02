"""Immutable, content-addressed setup records for the approved 2.7 instrument.

Callers supply the executed configuration. There are no model, threshold,
version or approval defaults here. Runtime binding belongs to T-030/T-035.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from g3o.common.storage_fields import CODEBOOK_SHA256, FIELDS

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REQUIRED = {
    "schema_version", "codebook_release", "codebook_sha256", "codebook_item_hashes",
    "extract_contract_label", "validate_contract_label", "question_set_version",
    "question_hashes", "prompt_hashes", "configured_jev_model", "extractor_model_id",
    "extractor_prompt_sha256", "extractor_configuration", "chunker_version",
    "estimator_version", "token_budget", "matcher_library", "matcher_version",
    "matcher_threshold", "chosen_answer_confidence_threshold", "producer_code_revision",
    "instrument_approval_reference",
}


def canonical_json(value: Any) -> str:
    """The instrument payload identity encoding; also used for structured CSV cells."""
    def check(obj: Any) -> None:
        if isinstance(obj, str) and "\x00" in obj:
            raise ValueError("NUL-bearing text cannot be altered or stored in this contract")
        if isinstance(obj, dict):
            if any(not isinstance(key, str) for key in obj):
                raise ValueError("JSON object keys must be strings")
            for key, val in obj.items():
                check(key)
                check(val)
        elif isinstance(obj, (list, tuple)):
            for val in obj:
                check(val)
    check(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hashes(value: Any, label: str) -> None:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a nonempty hash map")
    if any(not isinstance(k, str) or not k or not isinstance(v, str) or not _HASH.fullmatch(v)
           for k, v in value.items()):
        raise ValueError(f"invalid {label}")


def validate_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict) or set(payload) != _REQUIRED:
        raise ValueError("instrument payload fields differ from the approved required fields")
    canonical_json(payload)  # reject non-JSON values and nonfinite numbers
    if payload["schema_version"] != "g3o-instrument-v1":
        raise ValueError("unsupported instrument schema version")
    if payload["codebook_release"] != "2.7" or payload["codebook_sha256"] != CODEBOOK_SHA256:
        raise ValueError("instrument is not bound to the signed r11 release")
    for name in ("codebook_item_hashes", "question_hashes", "prompt_hashes"):
        _hashes(payload[name], name)
    expected = {key: value["schema"]["x-item-hash"] for key, value in FIELDS.items()
                if "x-item-hash" in value["schema"]}
    if payload["codebook_item_hashes"] != expected:
        raise ValueError("instrument item hashes do not match signed r11")
    if not isinstance(payload["extractor_prompt_sha256"], str) or not _HASH.fullmatch(payload["extractor_prompt_sha256"]):
        raise ValueError("invalid extractor prompt hash")
    if type(payload["token_budget"]) is not int or payload["token_budget"] <= 0:
        raise ValueError("token_budget must be an explicit positive integer")
    if type(payload["matcher_threshold"]) not in (int, float) or not math.isfinite(payload["matcher_threshold"]):
        raise ValueError("matcher threshold must be explicit and finite")
    if payload["chosen_answer_confidence_threshold"] != 0.8:
        raise ValueError("chosen-answer threshold must retain the approved 0.8 bar")
    if not isinstance(payload["extractor_configuration"], dict) or not payload["extractor_configuration"]:
        raise ValueError("actual extractor configuration is required")
    for key in _REQUIRED - {"codebook_item_hashes", "question_hashes", "prompt_hashes",
                           "extractor_configuration", "token_budget", "matcher_threshold",
                           "chosen_answer_confidence_threshold"}:
        if not isinstance(payload[key], str) or not payload[key].strip():
            raise ValueError(f"instrument {key} must be explicit nonempty text")
    def reject_secrets(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, val in obj.items():
                if re.search(r"(^|_)(api_key|password|secret|credential|access_token|authorization)($|_)", key, re.I):
                    raise ValueError("credentials must not enter an instrument record")
                reject_secrets(val)
        elif isinstance(obj, list):
            for val in obj:
                reject_secrets(val)
    reject_secrets(payload)


def build_instrument(payload: dict[str, Any]) -> dict[str, Any]:
    validate_payload(payload)
    encoded = canonical_json(payload)
    return {"instrument_id": sha256_text(encoded), "payload": json.loads(encoded)}


def validate_instrument(record: dict[str, Any], *, expected_id: str | None = None) -> dict[str, Any]:
    if not isinstance(record, dict) or set(record) != {"instrument_id", "payload"}:
        raise ValueError("invalid instrument record shape")
    built = build_instrument(record["payload"])
    if record["instrument_id"] != built["instrument_id"] or (expected_id is not None and expected_id != built["instrument_id"]):
        raise ValueError("instrument payload identity mismatch")
    return built


def write_instrument(directory: Path, payload: dict[str, Any]) -> dict[str, str]:
    """Create once; identical repeats are idempotent, mismatched files refuse."""
    record = build_instrument(payload)
    raw = (canonical_json(record) + "\n").encode("utf-8")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['instrument_id']}.json"
    try:
        with path.open("xb") as stream:
            stream.write(raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError("immutable instrument record already exists with different bytes") from None
    return {"instrument_id": record["instrument_id"], "path": str(path),
            "record_sha256": hashlib.sha256(raw).hexdigest()}


def load_instrument(directory: Path, instrument_id: str) -> dict[str, Any]:
    if not isinstance(instrument_id, str) or not _HASH.fullmatch(instrument_id):
        raise ValueError("setup_pointer must be an actual instrument payload SHA256")
    record = json.loads((directory / f"{instrument_id}.json").read_text(encoding="utf-8"))
    return validate_instrument(record, expected_id=instrument_id)