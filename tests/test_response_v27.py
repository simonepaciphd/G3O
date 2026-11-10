"""v2.7 ``6_validate.json`` response: identity and row keys only (RC-D-028 4 a)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from g3o.common.contract import ConsolidatedInstitutionResponse
from g3o.common.instrument import canonical_json, write_instrument
from g3o.common.paths import institution_dir
from g3o.common.response_v27 import (
    VALIDATE_FORMAT_V27,
    ConsolidatedInstitutionResponseV27,
    build_response_v27,
    check_storage_binding,
    parse_validate_payload,
    response_from_storage,
)
from g3o.common.storage import table_fields
from g3o.persist.stage6_adapters import write_stage6_artifacts
from g3o.persist.writer import (
    build_activity_rows,
    build_source_rows,
    build_summary_row,
    load_consolidated_outputs,
    write_run_csvs,
)
from g3o.validate.qc import qc_per_run
from tests._layout import make_inst_dir, uid_for, write_manifest
from tests._storage_fixture import fixture_bundle, instrument_payload

IDENTITY = {"institution_id": "INST-0001", "institution_name": "Test Ministry", "country": "Testland",
            "branch_of_government": "executive", "level_of_government": "national",
            "institution_search_languages": "en"}
META = {"institution_id": "INST-0001", "n_input_pages": 2, "n_input_rows": 2,
        "response_timestamp": "2026-11-10T12:00:00Z", "model_label": "stage6-v27", "notes": "none"}


def _response(data) -> ConsolidatedInstitutionResponseV27:
    return response_from_storage(institution=IDENTITY, metadata=META, storage=data)


def _payload(data) -> dict:
    return _response(data).model_dump(mode="json")


def _stage(tmp_path: Path, data, payload, *, release="2.7", storage=True) -> Path:
    write_manifest(tmp_path, {"run_id": "R1", "institutions": ["INST-0001"],
                              "storage_contract": {"codebook_release": release}})
    d = make_inst_dir(tmp_path, "INST-0001")
    (d / "6_validate.json").write_text(canonical_json(payload), encoding="utf-8")
    if storage:
        (d / "6_storage.json").write_text(canonical_json(data), encoding="utf-8")
    write_instrument(tmp_path / "final" / "instruments", instrument_payload())
    return tmp_path


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def test_round_trip_identity_and_keys_only(tmp_path):
    data, *_ = fixture_bundle(tmp_path)
    response = _response(data)
    payload = json.loads(canonical_json(response.model_dump(mode="json")))
    assert payload["format"] == VALIDATE_FORMAT_V27 and payload["codebook_release"] == "2.7"
    assert set(payload) == {"format", "codebook_release", "consolidation_metadata", "institution",
                            "activities", "sources"}
    assert payload["activities"] == [{"activity_id": "A1"}, {"activity_id": "A2"}]
    assert payload["sources"] == [{"source_id": "S1", "activity_id": "A1"}, {"source_id": "S2", "activity_id": "A2"}]
    reloaded = parse_validate_payload(payload)
    assert isinstance(reloaded, ConsolidatedInstitutionResponseV27)
    assert reloaded == response


@pytest.mark.parametrize("where,field,value", [
    ("institution", "has_genai_activity", "yes"),
    ("institution", "institution_summary", "x"),
    ("activities", "tool_name", "Copilot"),
    ("activities", "access_type", "unknown"),
    ("activities", "vendor", "unknown"),
    ("sources", "genai_evidence", "confirms_activity"),
    ("sources", "source_url", "https://example.gov/page"),
    ("top", "values", {}),
])
def test_value_fields_refused(tmp_path, where, field, value):
    data, *_ = fixture_bundle(tmp_path)
    payload = _payload(data)
    target = payload if where == "top" else payload[where] if where == "institution" else payload[where][0]
    target[field] = value
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_validate_payload(payload)


def test_key_sequence_and_link_checks():
    with pytest.raises(ValidationError, match="activity_id sequence"):
        build_response_v27(institution=IDENTITY, metadata=META, activity_ids=["A2"], sources=[("S1", "A2")])
    with pytest.raises(ValidationError, match="source_id sequence"):
        build_response_v27(institution=IDENTITY, metadata=META, activity_ids=["A1"], sources=[("S2", "A1")])
    with pytest.raises(ValidationError, match="does not match any activity"):
        build_response_v27(institution=IDENTITY, metadata=META, activity_ids=["A1"], sources=[("S1", "A2")])
    with pytest.raises(ValidationError, match="does not match institution"):
        build_response_v27(institution=IDENTITY, metadata={**META, "institution_id": "X"},
                           activity_ids=[], sources=[("S1", "_NA_")])


def test_dispatch_keeps_legacy_payloads_on_the_legacy_model(tmp_path):
    _, _, legacy, _ = fixture_bundle(tmp_path)
    parsed = parse_validate_payload(legacy.model_dump(mode="json"))
    assert type(parsed) is ConsolidatedInstitutionResponse
    with pytest.raises(ValueError, match="unsupported 6_validate.json format"):
        parse_validate_payload({**legacy.model_dump(mode="json"), "format": "g3o-validate-v99"})
    # A v2.7 payload is never accepted by the legacy model, and vice versa.
    data, *_ = fixture_bundle(tmp_path)
    with pytest.raises(ValidationError):
        ConsolidatedInstitutionResponse.model_validate(_payload(data))
    with pytest.raises(ValidationError):
        ConsolidatedInstitutionResponseV27.model_validate(legacy.model_dump(mode="json"))


def test_storage_binding_refuses_key_or_link_drift(tmp_path):
    data, *_ = fixture_bundle(tmp_path)
    check_storage_binding(_response(data), data)
    relinked = build_response_v27(institution=IDENTITY, metadata=META, activity_ids=["A1", "A2"],
                                  sources=[("S1", "A1"), ("S2", "A1")])
    with pytest.raises(ValueError, match="activity link differs"):
        check_storage_binding(relinked, data)
    fewer = build_response_v27(institution=IDENTITY, metadata=META, activity_ids=["A1", "A2"],
                               sources=[("S1", "A1")])
    with pytest.raises(ValueError, match="source keys differ"):
        check_storage_binding(fewer, data)


# ---------------------------------------------------------------------------
# Serialisation and reload (stage6_adapters -> writer / qc)
# ---------------------------------------------------------------------------


def test_write_stage6_artifacts_serialises_the_v27_response(tmp_path):
    data, _, _, envelope = fixture_bundle(tmp_path)
    validate_path, _, _ = write_stage6_artifacts(tmp_path / "inst", envelope, _response(data), [])
    reloaded = parse_validate_payload(json.loads(validate_path.read_text(encoding="utf-8")))
    assert reloaded == _response(data)
    bad = build_response_v27(institution=IDENTITY, metadata=META, activity_ids=["A1", "A2"],
                             sources=[("S1", "A2"), ("S2", "A1")])
    with pytest.raises(ValueError, match="activity link differs"):
        write_stage6_artifacts(tmp_path / "inst2", envelope, bad, [])


def test_rows_take_every_value_from_storage(tmp_path):
    """Storage-mapped cells are identical to the legacy-response path; legacy-only
    cells come from storage or a signed fill, never from the response."""
    data, _, legacy, envelope = fixture_bundle(tmp_path)
    common = {"run_id": "R1", "institution_uid": uid_for("INST-0001"), "run_date": "2026-11-01", "storage": envelope}
    v27 = _response(data)
    for table, build in (("activities", build_activity_rows), ("sources", build_source_rows)):
        new = build(v27, run_model="m", **common)
        old = build(legacy, run_model="m", **common)
        mapped = {f["column_or_member"] for f in table_fields(table).values()}
        for a, b in zip(new, old, strict=True):
            assert list(a) == list(b)
            assert {c: a[c] for c in mapped} == {c: b[c] for c in mapped}
    act = build_activity_rows(v27, run_model="m", **common)[0]
    assert act["has_genai_activity"] == "yes" and act["institution_summary"] == "Explicit fixture"
    assert act["interaction_type"] == "not_asked" and act["scope_notes"] == "not_asked"
    assert act["year_deployed"] == "unknown"  # neither start year is a year (R-051)
    assert act["access_type"] is None and act["vendor"] is None  # no signed fill
    src = build_source_rows(v27, run_model="m", **common)[0]
    assert src["genai_evidence"] == "confirms_activity" and src["source_url"] == "https://example.gov/page"
    summary = build_summary_row(v27, **common)
    assert summary["has_genai_activity"] == "yes"
    assert summary["tools_found"] == 'Tool beta | Tool; "Alpha"'
    assert summary["vendors_found"] is None
    assert (summary["n_activities"], summary["n_sources"], summary["n_high_credibility_sources"]) == (2, 2, 2)
    assert summary["n_pages_extracted"] == 2 and summary["best_confidence"] == "high"


def test_retired_cells_use_only_signed_fills():
    from g3o.common.response_v27 import retired_legacy_cells, year_deployed

    assert year_deployed({"core.year_pilot_start": "2024", "core.year_production_start": "2023"}) == "2023"
    assert year_deployed({"core.year_pilot_start": "2025", "core.year_production_start": "unknown"}) == "2025"
    assert year_deployed({"core.year_pilot_start": "not_documented"}) == "unknown"
    cells = retired_legacy_cells(["access_type", "vendor", "interaction_type", "scope_notes", "year_deployed",
                                  "institution_id"], {"core.year_pilot_start": "2024"})
    assert cells == {"access_type": None, "vendor": None, "interaction_type": "not_asked",
                     "scope_notes": "not_asked", "year_deployed": "2024"}


def test_stage7_reload_writes_csvs_from_storage(tmp_path):
    data, *_ = fixture_bundle(tmp_path)
    _stage(tmp_path, data, _payload(data))
    loaded, failures = load_consolidated_outputs(tmp_path)
    assert not failures and isinstance(loaded[0].response, ConsolidatedInstitutionResponseV27)
    result = write_run_csvs(tmp_path, run_id="R1", run_model="fixture", run_date="2026-11-01")
    assert result["integrity"]["is_valid"] and result["n_institutions"] == 1
    with Path(result["outputs"]["activities"]["path"]).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["tool_name"] == canonical_json(['Tool; "Alpha"', "Tool beta"])
    assert rows[0]["access_type"] == "" and rows[0]["codebook_release"] == "2.7"


def test_stage7_refuses_unbound_or_storage_less_v27(tmp_path):
    data, *_ = fixture_bundle(tmp_path)
    _stage(tmp_path / "a", data, _payload(data), storage=False)
    # fixture artifacts live in tmp_path; the missing storage refuses before any read
    with pytest.raises(ValueError, match="lacks"):
        load_consolidated_outputs(tmp_path / "a")
    relinked = build_response_v27(institution=IDENTITY, metadata=META, activity_ids=["A1", "A2"],
                                  sources=[("S1", "A2"), ("S2", "A1")]).model_dump(mode="json")
    run = _stage(tmp_path, data, relinked)
    with pytest.raises(ValueError, match="activity link differs"):
        load_consolidated_outputs(run)


def test_stage7_refuses_v27_payload_in_a_v25_run(tmp_path):
    data, *_ = fixture_bundle(tmp_path)
    _stage(tmp_path, data, _payload(data), release="v2.5")
    with pytest.raises(ValueError, match="v2.7 6_validate.json in a v2.5 run"):
        load_consolidated_outputs(tmp_path)


def test_qc_reloads_v27_values_from_storage(tmp_path):
    data, *_ = fixture_bundle(tmp_path)
    _stage(tmp_path, data, _payload(data))
    qc = qc_per_run(tmp_path)
    assert qc["n_consolidated"] == 1 and qc["n_parse_failed"] == 0
    assert qc["has_genai_activity"] == {"yes": 1}
    assert qc["genai_evidence"] == {"confirms_activity": 2}
    assert qc["top_vendors"] == []
    assert dict(qc["top_tools"]) == {'Tool; "Alpha"': 1, "Tool beta": 1}


def test_qc_counts_unbound_v27_as_parse_failure(tmp_path):
    data, *_ = fixture_bundle(tmp_path)
    relinked = build_response_v27(institution=IDENTITY, metadata=META, activity_ids=["A1", "A2"],
                                  sources=[("S1", "A2"), ("S2", "A1")]).model_dump(mode="json")
    _stage(tmp_path, data, relinked)
    qc = qc_per_run(tmp_path)
    assert qc["n_parse_failed"] == 1 and qc["n_consolidated"] == 0


def test_legacy_run_unchanged(tmp_path):
    _, _, legacy, _ = fixture_bundle(tmp_path)
    write_manifest(tmp_path, {"run_id": "R1", "institutions": ["INST-0001"]})
    d = make_inst_dir(tmp_path, "INST-0001")
    (d / "6_validate.json").write_text(json.dumps(legacy.model_dump()), encoding="utf-8")
    loaded, failures = load_consolidated_outputs(tmp_path)
    assert not failures and type(loaded[0].response) is ConsolidatedInstitutionResponse
    assert loaded[0].storage is None
    assert institution_dir(tmp_path, "INST-0001") == d
    assert qc_per_run(tmp_path)["n_consolidated"] == 1
