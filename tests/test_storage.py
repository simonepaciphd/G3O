from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from g3o.common.instrument import canonical_json, sha256_text, write_instrument
from g3o.common.paths import institution_dir
from g3o.common.schema import (
    ACTIVITY_COLUMNS,
    ACTIVITY_COLUMNS_V25,
    ACTIVITY_SOURCE_COLUMNS,
    ACTIVITY_SOURCE_COLUMNS_V25,
    SUMMARY_COLUMNS,
    SUMMARY_COLUMNS_V25,
)
from g3o.common.storage import (
    StorageEnvelope,
    email_domain_counts,
    public_projection,
    support_id,
)
from g3o.common.storage_fields import FIELDS
from g3o.persist.writer import (
    build_activity_rows,
    build_source_rows,
    build_summary_row,
    write_run_csvs,
)
from tests._layout import uid_for, write_manifest
from tests._storage_fixture import fixture_bundle, instrument_payload
from tests.test_persist import _stage_run_dir, _yes_response


def _rows(response, envelope, metadata=None):
    common = {"run_id": "R1", "institution_uid": uid_for("INST-0001"), "run_date": "2026-11-01", "storage": envelope, "storage_metadata": metadata}
    return {
        "activities": build_activity_rows(response, run_model="fixture-model", **common),
        "sources": build_source_rows(response, run_model="fixture-model", **common),
        "summary": [build_summary_row(response, **common)],
    }


def test_complete_map_and_preserved_column_prefixes():
    assert len(FIELDS) == 120
    assert sum(f["state"] == "excluded" for f in FIELDS.values()) == 11
    assert sum(f["state"] == "external_owner_pending" for f in FIELDS.values()) == 1
    for columns, frozen in ((ACTIVITY_COLUMNS, ACTIVITY_COLUMNS_V25),
                            (ACTIVITY_SOURCE_COLUMNS, ACTIVITY_SOURCE_COLUMNS_V25),
                            (SUMMARY_COLUMNS, SUMMARY_COLUMNS_V25)):
        assert columns[:len(frozen)] == list(frozen)
        assert len(set(columns)) == len(columns)
        assert {"codebook_release", "setup_pointer", "evidence_channel", "item_support_json", "coder_records_json", "field_availability_json"} <= set(columns)
    assert "evaluation_documented" not in ACTIVITY_COLUMNS
    assert "evaluation_documented" in ACTIVITY_SOURCE_COLUMNS
    assert "date_upper_bound" in ACTIVITY_COLUMNS and "date_upper_bound" in ACTIVITY_SOURCE_COLUMNS


def test_legacy_does_not_invent_version_or_questionnaire_answers():
    rows = _rows(_yes_response(), None)
    for table in rows.values():
        row = table[0]
        assert row["codebook_release"] is None
        assert row["setup_pointer"] is None
        reasons = json.loads(row["field_availability_json"])
        assert reasons["core.codebook_release"] == "historical_provenance_unavailable"
        assert row["item_support_json"] is None
    assert rows["activities"][0]["tool_name"] == "Microsoft 365 Copilot"
    assert rows["sources"][0]["evaluation_documented"] is None
    assert json.loads(rows["sources"][0]["field_availability_json"])["core.evaluation_documented"] == "legacy_not_collected"


def test_explicit_legacy_release_is_retained_without_new_provenance():
    row = build_summary_row(_yes_response(), run_id="R1", institution_uid=uid_for("INST-0001"), storage_metadata={"codebook_release": "v2.5"})
    assert row["codebook_release"] == "v2.5"
    assert row["setup_pointer"] is None
    assert "core.codebook_release" not in json.loads(row["field_availability_json"])


@pytest.mark.parametrize("version", ["v2.7", "2.5", "v2.6", "3", "2.7"])
def test_legacy_builder_never_upgrades_or_accepts_unknown_versions(version):
    with pytest.raises(ValueError):
        build_summary_row(_yes_response(), run_id="R1", institution_uid=uid_for("INST-0001"), storage_metadata={"codebook_release": version})


def test_claim_grain_round_trip_and_unabridged_support(tmp_path):
    _, _, response, envelope = fixture_bundle(tmp_path)
    rows = _rows(response, envelope)
    assert [r["source_id"] for r in rows["sources"]] == ["S1", "S2"]
    assert [r["evaluation_documented"] for r in rows["sources"]] == ["results_reported", "required_or_planned"]
    assert rows["summary"][0]["n_sources"] == 2
    assert json.loads(rows["summary"][0]["review_depth"])["web_extract"]["n_pages_reviewed"] == 1
    activity = rows["activities"][0]
    assert json.loads(activity["tool_name"]) == ['Tool; "Alpha"', "Tool beta"]
    assert activity["deployment_scale_number"] == "1,000"
    supports = json.loads(activity["item_support_json"])
    assert len(supports[0]["supporting_text"]) > 1000
    assert json.loads(activity["coder_records_json"])[0]["chosen_answer_probability"] is None
    path = tmp_path / "roundtrip.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=ACTIVITY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows["activities"])
    with path.open(encoding="utf-8", newline="") as stream:
        read = list(csv.DictReader(stream))
    assert json.loads(read[0]["item_support_json"]) == supports
    assert json.loads(read[0]["observed_actor_relationship"]) == envelope.data["activities"]["A1"]["values"]["core.observed_actor_relationship"]


def test_merged_final_activity_retains_both_original_endpoints(tmp_path):
    _, _, response, envelope = fixture_bundle(tmp_path, merged=True)
    rows = _rows(response, envelope)
    assert len(rows["activities"]) == 1
    assert rows["activities"][0]["n_sources"] == 2
    assert json.loads(rows["activities"][0]["observation_ids_json"]) == ["O1", "O2"]
    relation = json.loads(rows["activities"][0]["activity_relations_json"])[0]
    assert relation["lhs_observation_id"] != relation["rhs_observation_id"]
    assert relation["lhs_final_activity_id"] == relation["rhs_final_activity_id"] == "A1"


def test_email_counts_are_distinct_with_whole_address_lowercasing():
    assert email_domain_counts(["Ada@EXAMPLE.GOV", "Ada@example.gov", "ada@example.gov", "Ada+pilot@example.gov", "x@other.gov"]) == [
        {"domain": "example.gov", "count": 2}, {"domain": "other.gov", "count": 1}]
    assert email_domain_counts([]) == []
    assert email_domain_counts("not_asked") == "not_asked"


def test_public_projection_hides_internal_extracted_fields(tmp_path):
    _, _, response, envelope = fixture_bundle(tmp_path)
    rows = _rows(response, envelope)
    public = public_projection("sources", rows["sources"][0])
    assert "content_contact_emails_json" not in public
    assert "page_artifact_path" not in public
    assert "coder_records_json" not in public
    assert json.loads(public["contact_email_domain_counts_json"]) == [{"domain": "example.gov", "count": 2}]
    assert "observed_actor_role" not in public_projection("activities", rows["activities"][0])


@pytest.mark.parametrize("damage,match", [
    (lambda d: d["sources"]["S1"]["values"].pop("core.evaluation_documented"), "questionnaire values"),
    (lambda d: d["sources"]["S1"]["values"].update({"core.page_verdict": "ambiguous"}), "invalid code"),
    (lambda d: d["activities"]["A1"]["values"].update({"core.tool_name": "Tool; Tool"}), "array or signed"),
    (lambda d: d["sources"]["S1"].update(page_content_sha256="0" * 64), "artifact hash"),
    (lambda d: d["activities"]["A1"]["activity_relations"][0].update(rhs_observation_id="missing"), "endpoint"),
    (lambda d: d["activities"]["A1"]["values"].update({"core.n_sources": 2}), "evidence claims"),
    (lambda d: d["summary"]["values"]["core.review_depth"]["web_extract"]["n_pages_by_verdict"].pop("event_only"), "nine verdict"),
    (lambda d: d.update(evidence_channel="text_detection"), "canonical evidence"),
    (lambda d: d.update(codebook_release="v2.7"), "unsupported"),
    # RC-D-030 Y2 a: only a page-level _NA_ source row may have no observation
    (lambda d: d["sources"]["S1"].update(observation_ids=[]), "retain original observations"),
    (lambda d: d["activities"]["A1"].update(observation_ids=[]), "retain original observations"),
])
def test_incomplete_or_incompatible_new_storage_refuses(tmp_path, damage, match):
    data, record, _, _ = fixture_bundle(tmp_path)
    damage(data)
    with pytest.raises(ValueError, match=match):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_support_quote_and_input_references_verified(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)
    support = data["activities"]["A1"]["item_support"][0]
    support["supporting_text"] = "This was never on the page"
    support["support_text_sha256"] = sha256_text(support["supporting_text"])
    support["support_id"] = support_id("R1", data["institution_uid"], support)
    with pytest.raises(ValueError, match="not verbatim"):
        StorageEnvelope(data, record, artifact_root=tmp_path)
    data, record, _, _ = fixture_bundle(tmp_path)
    support = data["activities"]["A1"]["item_support"][0]
    support["input_support_ids"] = ["missing-support"]
    with pytest.raises(ValueError, match="input does not resolve"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_stage7_requires_actual_instrument_and_storage_before_writing(tmp_path):
    data, _, response, _ = fixture_bundle(tmp_path)
    _stage_run_dir(tmp_path, {"INST-0001": response})
    write_manifest(tmp_path, {"run_id": "R1", "institutions": ["INST-0001"], "storage_contract": {"codebook_release": "2.7"}})
    with pytest.raises(ValueError, match="lacks explicit"):
        write_run_csvs(tmp_path, run_id="R1", run_model="fixture", run_date="2026-11-01")
    assert not list((tmp_path / "final").glob("*.csv"))
    (institution_dir(tmp_path, "INST-0001") / "6_storage.json").write_text(canonical_json(data), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        write_run_csvs(tmp_path, run_id="R1", run_model="fixture", run_date="2026-11-01")
    write_instrument(tmp_path / "final" / "instruments", instrument_payload())
    result = write_run_csvs(tmp_path, run_id="R1", run_model="fixture", run_date="2026-11-01")
    assert result["n_institutions"] == 1
    assert result["integrity"]["is_valid"]
    with Path(result["outputs"]["activity_sources"]["path"]).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["setup_pointer"] == data["setup_pointer"]
    assert rows[1]["evaluation_documented"] == "required_or_planned"


def test_storage_context_does_not_change_request_schema():
    from g3o.common.contract import ConsolidatedInstitutionResponse
    assert "storage" not in ConsolidatedInstitutionResponse.model_json_schema()["properties"]


@pytest.mark.parametrize("scenario", ["legacy", "page_two_activities", "combined_activity"])
def test_three_representative_normalized_goldens(tmp_path, scenario):
    if scenario == "legacy":
        rows = _rows(_yes_response(), None, {"codebook_release": "v2.5"})
    else:
        _, _, response, envelope = fixture_bundle(tmp_path, merged=scenario == "combined_activity")
        rows = _rows(response, envelope)
    for table, columns in (("activities", ACTIVITY_COLUMNS), ("sources", ACTIVITY_SOURCE_COLUMNS), ("summary", SUMMARY_COLUMNS)):
        expected = Path(__file__).parent / "fixtures" / "storage_contract" / scenario / f"{table}.csv"
        with expected.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == columns
            actual = [{key: "" if val is None else str(val) for key, val in row.items()} for row in rows[table]]
            assert list(reader) == actual

def test_each_selected_value_requires_its_own_support(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)
    row = data["sources"]["S1"]
    row["item_support"] = [s for s in row["item_support"] if s["item_id"] != "core.evaluation_documented"]
    with pytest.raises(ValueError, match="missing keyed support"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_coder_key_cannot_be_attached_to_another_value(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)
    data["activities"]["A1"]["coder_records"][0]["chosen_value"] = "different"
    with pytest.raises(ValueError, match="does not match its support key"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_same_content_on_distinct_pages_is_counted_twice(tmp_path):
    _, _, response, envelope = fixture_bundle(tmp_path, merged=True)
    rows = _rows(response, envelope)
    assert rows["sources"][0]["page_content_sha256"] == rows["sources"][1]["page_content_sha256"]
    assert rows["sources"][0]["source_url"] != rows["sources"][1]["source_url"]
    assert json.loads(rows["summary"][0]["review_depth"])["web_extract"]["n_pages_reviewed"] == 2


def test_validated_envelope_view_is_detached(tmp_path):
    _, _, response, envelope = fixture_bundle(tmp_path)
    view = envelope.data
    view["activities"]["A1"]["values"]["core.tool_name"] = "broken"
    assert isinstance(envelope.data["activities"]["A1"]["values"]["core.tool_name"], list)
    _rows(response, envelope)


def test_nul_in_quote_is_refused_before_hash_or_serialization(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)
    data["sources"]["S1"]["values"]["core.source_snippet"] = "bad\x00text"
    with pytest.raises(ValueError, match="NUL"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_duplicate_claims_cannot_inflate_review_depth(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)
    depth = data["summary"]["values"]["core.review_depth"]["web_extract"]
    depth["n_pages_reviewed"] = 2
    depth["n_pages_by_verdict"]["confirms_activity"] = 2
    with pytest.raises(ValueError, match="exactly count"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_classifier_rows_cannot_drop_coder_provenance(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)
    data["sources"]["S1"]["coder_records"] = []
    with pytest.raises(ValueError, match="per-code coder provenance"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_source_claim_cannot_borrow_other_claim_support(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)
    support = next(s for s in data["sources"]["S2"]["item_support"] if s["item_id"] == "core.page_verdict")
    row = data["sources"]["S1"]
    row["item_support"] = [s for s in row["item_support"] if s["item_id"] != "core.page_verdict"] + [support]
    with pytest.raises(ValueError, match="borrowed another claim"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_activity_cannot_borrow_other_observation_support(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)
    support = next(s for s in data["activities"]["A2"]["item_support"] if s["item_id"] == "core.activity_name")
    row = data["activities"]["A1"]
    row["item_support"] = [s for s in row["item_support"] if s["item_id"] != "core.activity_name"] + [support]
    with pytest.raises(ValueError, match="borrowed another observation"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_pooled_coder_can_retain_real_null_observation_context(tmp_path):
    from copy import deepcopy
    data, record, _, _ = fixture_bundle(tmp_path, merged=True)
    row = data["activities"]["A1"]
    original = row["item_support"][0]
    pooled = deepcopy(original)
    pooled.update(observation_id=None, source_id=None, chunk_id=None, page_content_sha256=None,
                  input_support_ids=[original["support_id"]], passage={"pooled_occurrence": 0})
    pooled["support_id"] = support_id("R1", data["institution_uid"], pooled)
    row["item_support"].append(pooled)
    coder = deepcopy(row["coder_records"][0])
    coder.update(support_id=pooled["support_id"], observation_id=None, chunk_id=None)
    row["coder_records"].append(coder)
    validated = StorageEnvelope(data, record, artifact_root=tmp_path)
    assert validated.data["activities"]["A1"]["coder_records"][-1]["observation_id"] is None


def test_rule_set_value_uses_typed_mechanical_provenance(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)
    row = data["activities"]["A1"]
    item = "core.function_code"
    prior = next(s for s in row["item_support"] if s["item_id"] == item)
    old_id = prior["support_id"]
    row["values"][item] = "not_asked"
    prior.update(value_json="not_asked", support_status="set_by_rule", support_rule_name="fixture-signed-gate",
                 supporting_text="", support_text_sha256=sha256_text(""), passage={"start": 0, "end": 0})
    prior["support_id"] = support_id("R1", data["institution_uid"], prior)
    coder = next(c for c in row["coder_records"] if c["support_id"] == old_id)
    coder.update(support_id=prior["support_id"], chosen_value="not_asked", coder_type="mechanical")
    inapplicable = ["configured_model", "actual_response_model", "request_id", "chosen_answer_probability", "probability_distribution"]
    coder.update({key: None for key in inapplicable})
    coder["field_availability"] = {key: "coder_not_applicable" for key in inapplicable}
    StorageEnvelope(data, record, artifact_root=tmp_path)
    coder["request_id"] = "invented-provider-request"
    with pytest.raises(ValueError, match="typed null"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_public_projection_removes_internal_nested_rollup_values(tmp_path):
    data, record, response, _ = fixture_bundle(tmp_path)
    rollup = data["activities"]["A1"]["values"]["core.cx_display_rollup"]
    for item, value in (("core.observed_actor_role", "issuer"),
                        ("core.content_contact_emails", ["private@example.gov"]),
                        ("core.evaluation_documented", "results_reported")):
        rollup[item] = {"value": value, "input_support_ids": [], "source_ids": ["S1"],
                        "observation_ids": ["O1"], "combining_rule_ref": "fixture-combining-rule"}
    envelope = StorageEnvelope(data, record, artifact_root=tmp_path)
    row = _rows(response, envelope)["activities"][0]
    public = public_projection("activities", row)
    kept = json.loads(public["cx_display_rollup"])
    assert set(kept) == {"core.evaluation_documented"}
    assert "private@example.gov" not in public["cx_display_rollup"]
    assert "issuer" not in public["cx_display_rollup"]
    assert json.loads(public["item_support_json"])[0]["supporting_text"] == json.loads(row["item_support_json"])[0]["supporting_text"]


def test_review_depth_cannot_omit_the_active_channel(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)
    depth = data["summary"]["values"]["core.review_depth"]
    counts = depth.pop("web_extract")
    counts["n_pages_reviewed"] = 0
    counts["n_pages_by_verdict"] = {verdict: 0 for verdict in counts["n_pages_by_verdict"]}
    depth["ai_text"] = counts
    with pytest.raises(ValueError, match="active evidence channel"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_pooled_quote_cannot_invent_text(tmp_path):
    from copy import deepcopy
    data, record, _, _ = fixture_bundle(tmp_path, merged=True)
    row = data["activities"]["A1"]
    original = row["item_support"][0]
    pooled = deepcopy(original)
    pooled.update(observation_id=None, source_id=None, chunk_id=None, page_content_sha256=None,
                  input_support_ids=[original["support_id"]], passage={"pooled_occurrence": 0},
                  supporting_text="Fabricated quote", support_text_sha256=sha256_text("Fabricated quote"))
    pooled["support_id"] = support_id("R1", data["institution_uid"], pooled)
    row["item_support"].append(pooled)
    coder = deepcopy(row["coder_records"][0])
    coder.update(support_id=pooled["support_id"], observation_id=None, chunk_id=None)
    row["coder_records"].append(coder)
    with pytest.raises(ValueError, match="pooled support quote"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_summary_only_support_cycle_is_rejected(tmp_path):
    from copy import deepcopy
    data, record, _, _ = fixture_bundle(tmp_path)
    source = data["activities"]["A1"]["item_support"][0]
    summary_support = deepcopy(source)
    summary_support.update(item_id="core.institution_summary", value_json="Explicit fixture",
                           observation_id=None, source_id=None, chunk_id=None,
                           supporting_text="", support_text_sha256=sha256_text(""),
                           support_status="set_by_rule", support_rule_name="fixture-summary-rule",
                           page_content_sha256=None, passage={"summary_occurrence": 0})
    summary_support["support_id"] = support_id("R1", data["institution_uid"], summary_support)
    summary_support["input_support_ids"] = [summary_support["support_id"]]
    data["summary"]["item_support"].append(summary_support)
    with pytest.raises(ValueError, match="cyclic pooled"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


@pytest.mark.parametrize("emails,expected", [
    (["Alice@EXAMPLE.org", "alice@example.org", "Alice@example.org"],
     [{"domain": "example.org", "count": 1}]),
    (["Alice@EXAMPLE.org", "bob@example.org", "alice+news@example.org",
      "ALICE+NEWS@EXAMPLE.ORG", "a.lice@example.org", "Alice@OTHER.org"],
     [{"domain": "example.org", "count": 4}, {"domain": "other.org", "count": 1}]),
    ([], []),
    ("not_asked", "not_asked"),
    ("not_documented", "not_documented"),
    ("unknown", "unknown"),
])
def test_rcd011_direct_email_counts(emails, expected):
    assert email_domain_counts(emails) == expected


@pytest.mark.parametrize("emails", [None, "", ["not-an-address"], ["a b@example.org"]])
def test_rcd011_unavailable_or_malformed_email_input_is_not_zero(emails):
    with pytest.raises(ValueError):
        email_domain_counts(emails)


def test_rcd011_internal_and_public_email_json_csv_roundtrip(tmp_path):
    data, record, response, _ = fixture_bundle(tmp_path)
    raw = ["Alice@EXAMPLE.org", "alice@example.org", "Alice@example.org",
           "Bob@example.org", "alice+news@example.org", "ALICE+NEWS@example.org"]
    expected = ["alice@example.org", "bob@example.org", "alice+news@example.org"]
    for source in data["sources"].values():
        source["values"]["core.content_contact_emails"] = list(raw)
    before_support = canonical_json([s["item_support"] for s in data["sources"].values()])
    envelope = StorageEnvelope(json.loads(canonical_json(data)), record, artifact_root=tmp_path)
    for source in envelope.data["sources"].values():
        assert source["values"]["core.content_contact_emails"] == expected
    assert data["sources"]["S1"]["values"]["core.content_contact_emails"] == raw
    assert canonical_json([s["item_support"] for s in envelope.data["sources"].values()]) == before_support
    rows = _rows(response, envelope)
    # Both claims belong to one actual page: each repeats its count, never sums it.
    assert len(rows["sources"]) == 2
    assert json.loads(rows["summary"][0]["review_depth"])["web_extract"]["n_pages_reviewed"] == 1
    path = tmp_path / "email-roundtrip.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=ACTIVITY_SOURCE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows["sources"])
    with path.open(encoding="utf-8", newline="") as stream:
        restored = list(csv.DictReader(stream))
    for row in restored:
        assert json.loads(row["content_contact_emails_json"]) == expected
        counts = [{"domain": "example.org", "count": 3}]
        assert json.loads(row["contact_email_domain_counts_json"]) == counts
        public = public_projection("sources", row)
        assert "content_contact_emails_json" not in public
        assert "page_artifact_path" not in public
        assert "coder_records_json" not in public
        assert json.loads(public["contact_email_domain_counts_json"]) == counts
        assert "@" not in public["contact_email_domain_counts_json"]
        assert str(tmp_path) not in canonical_json(public)


def test_rcd011_extractor_to_storage_agrees_with_direct_input(tmp_path):
    from bs4 import BeautifulSoup

    from g3o.scrape.html import extract_email_links

    raw = ["Alice@EXAMPLE.org", "alice@example.org", "Alice@example.org", "Alice+news@example.org"]
    html = "".join(f'<a href="mailto:{email}">Contact</a>' for email in raw)
    extracted = extract_email_links(BeautifulSoup(html, "html.parser"))
    assert extracted == ["alice@example.org", "alice+news@example.org"]
    data, record, response, _ = fixture_bundle(tmp_path)
    results = []
    for emails in (raw, extracted):
        for source in data["sources"].values():
            source["values"]["core.content_contact_emails"] = list(emails)
        envelope = StorageEnvelope(data, record, artifact_root=tmp_path)
        row = _rows(response, envelope)["sources"][0]
        results.append((row["content_contact_emails_json"], row["contact_email_domain_counts_json"]))
    assert results[0] == results[1]
    assert json.loads(results[0][0]) == extracted
    assert json.loads(results[0][1]) == [{"domain": "example.org", "count": 2}]


@pytest.mark.parametrize("value", [[], "not_asked", "not_documented", "unknown"])
def test_rcd011_empty_and_signed_missing_values_survive_storage(tmp_path, value):
    data, record, response, _ = fixture_bundle(tmp_path)
    for source in data["sources"].values():
        source["values"]["core.content_contact_emails"] = value
    envelope = StorageEnvelope(data, record, artifact_root=tmp_path)
    for row in _rows(response, envelope)["sources"]:
        assert json.loads(row["content_contact_emails_json"]) == value
        assert json.loads(row["contact_email_domain_counts_json"]) == value


def test_rcd011_unavailable_legacy_email_remains_null():
    row = _rows(_yes_response(), None)["sources"][0]
    assert row["content_contact_emails_json"] is None
    assert row["contact_email_domain_counts_json"] is None
    assert public_projection("sources", row)["contact_email_domain_counts_json"] is None


# --- RC-D-030 Y2 a, narrowed (QA round 2 LOW-D): the page-level `_NA_` source row -------------------


def _page_level_row(tmp_path, data, sid, *, page="page3.txt", url="https://example.gov/no-activity-page"):
    """A copy of S1 as the page-level source row of a reviewed page with no activity."""
    import copy

    row = copy.deepcopy(data["sources"]["S1"])
    text = (tmp_path / "page.txt").read_bytes()
    (tmp_path / page).write_bytes(text)
    row.update(activity_id="_NA_", observation_ids=[], page_artifact_path=page)
    row["values"]["core.source_url"] = url
    ids = {}
    for support in row["item_support"]:
        old = support["support_id"]
        support.update(source_id=sid, observation_id=None)
        support["support_id"] = support_id("R1", data["institution_uid"], support)
        ids[old] = support["support_id"]
    for coder in row["coder_records"]:
        coder.update(support_id=ids[coder["support_id"]], observation_id=None)
    data["sources"][sid] = row
    return row


def _count_page(data, n=1):
    depth = data["summary"]["values"]["core.review_depth"]["web_extract"]
    depth["n_pages_reviewed"] += n
    depth["n_pages_by_verdict"]["confirms_activity"] += n


def test_page_level_na_source_row_of_its_own_page_is_accepted(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)
    _page_level_row(tmp_path, data, "S3")
    _count_page(data)
    StorageEnvelope(data, record, artifact_root=tmp_path)


def test_page_level_na_source_row_on_a_page_with_another_source_row_refuses(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)  # S1, S2 (activities) are on page.txt
    _page_level_row(tmp_path, data, "S3", page="page.txt", url=data["sources"]["S1"]["values"]["core.source_url"])
    with pytest.raises(ValueError, match="page-level"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_page_level_na_source_row_sharing_only_the_stored_artifact_refuses(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)  # same page artifact as S1/S2, its own URL
    _page_level_row(tmp_path, data, "S3", page="page.txt")
    assert data["sources"]["S3"]["values"]["core.source_url"] != data["sources"]["S1"]["values"]["core.source_url"]
    _count_page(data)
    with pytest.raises(ValueError, match="page-level"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_page_level_na_source_row_sharing_only_the_url_refuses(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)  # its own stored artifact, S1's URL
    _page_level_row(tmp_path, data, "S3", url=data["sources"]["S1"]["values"]["core.source_url"])
    assert data["sources"]["S3"]["page_artifact_path"] != data["sources"]["S1"]["page_artifact_path"]
    _count_page(data)
    with pytest.raises(ValueError, match="page-level"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_two_page_level_na_source_rows_on_one_page_refuse(tmp_path):
    data, record, _, _ = fixture_bundle(tmp_path)
    _page_level_row(tmp_path, data, "S3")
    _page_level_row(tmp_path, data, "S4")
    _count_page(data)
    with pytest.raises(ValueError, match="page-level"):
        StorageEnvelope(data, record, artifact_root=tmp_path)


def test_na_source_row_of_an_unpublished_observation_keeps_its_observation_ids(tmp_path):
    # X3 a (i) `_NA_` rows keep their observation ids; their supports cannot drop the observation
    data, record, _, _ = fixture_bundle(tmp_path)
    row = _page_level_row(tmp_path, data, "S3")
    row["observation_ids"] = ["O9"]
    _count_page(data)
    with pytest.raises(ValueError, match="endpoint does not resolve"):
        StorageEnvelope(data, record, artifact_root=tmp_path)
