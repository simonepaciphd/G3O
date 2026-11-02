from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from g3o.common.instrument import (
    build_instrument,
    canonical_json,
    load_instrument,
    validate_instrument,
    write_instrument,
)
from tests._storage_fixture import instrument_payload


def test_instrument_payload_identity_and_record_bytes_are_distinct(tmp_path: Path):
    payload = instrument_payload()
    first = write_instrument(tmp_path, payload)
    assert first == write_instrument(tmp_path, dict(reversed(list(payload.items()))))
    raw = Path(first["path"]).read_bytes()
    assert first["instrument_id"] == hashlib.sha256(canonical_json(payload).encode()).hexdigest()
    assert first["record_sha256"] == hashlib.sha256(raw).hexdigest()
    assert first["record_sha256"] != first["instrument_id"]
    assert load_instrument(tmp_path, first["instrument_id"])["payload"] == payload


@pytest.mark.parametrize("field", list(instrument_payload()))
def test_missing_real_configuration_refused(field):
    payload = instrument_payload()
    del payload[field]
    with pytest.raises(ValueError):
        build_instrument(payload)


def test_no_imaginary_item_hashes_or_default_threshold():
    payload = instrument_payload()
    payload["codebook_item_hashes"]["core.page_verdict"] = "0" * 64
    with pytest.raises(ValueError, match="item hashes"):
        build_instrument(payload)
    payload = instrument_payload()
    payload["chosen_answer_confidence_threshold"] = 0.5
    with pytest.raises(ValueError, match="0.8"):
        build_instrument(payload)


def test_record_tamper_and_mutation_are_refused(tmp_path: Path):
    payload = instrument_payload()
    result = write_instrument(tmp_path, payload)
    record = load_instrument(tmp_path, result["instrument_id"])
    record["payload"]["configured_jev_model"] = "different"
    with pytest.raises(ValueError, match="identity mismatch"):
        validate_instrument(record)
    Path(result["path"]).write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="immutable"):
        write_instrument(tmp_path, payload)


@pytest.mark.parametrize("bad", ["setup-R1", "../instrument", "0" * 63])
def test_setup_pointer_is_never_synthetic(tmp_path: Path, bad):
    with pytest.raises(ValueError):
        load_instrument(tmp_path, bad)


def test_secrets_and_nonfinite_configuration_refused():
    payload = instrument_payload()
    payload["extractor_configuration"]["api_key"] = "test-secret-not-real"
    with pytest.raises(ValueError, match="credentials"):
        build_instrument(payload)
    payload = instrument_payload()
    payload["extractor_configuration"]["temperature"] = float("nan")
    with pytest.raises(ValueError):
        build_instrument(payload)


def test_builder_copies_payload():
    payload = instrument_payload()
    before = deepcopy(payload)
    record = build_instrument(payload)
    payload["question_hashes"].clear()
    assert record["payload"] == before