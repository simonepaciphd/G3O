"""T-027 offline acceptance; all provider responses are explicit fixtures."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from g3o.common.instrument import build_instrument
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.common.jev_record import (
    ClassifierRule,
    CoderRecord,
    load_classifier_rules,
    records_from_json,
    records_to_json,
)
from g3o.common.storage import StorageEnvelope, support_id
from g3o.common.storage_fields import CODEBOOK_SHA256, FIELDS
from tests._storage_fixture import fixture_bundle, instrument_payload


def _rule(item="core.page_verdict", part=None):
    # Explicit fixture mapping; exact signed-r11 coverage is audited separately.
    return ClassifierRule(item, part, CODEBOOK_SHA256,
                          "tag_only" if item == "core.page_verdict" else "unknown")


def _record(*, item="core.page_verdict", choice="confirms_activity", dist=None,
            confidence=0.99, chunk="C1", request="fixture-request-1", model="fixture-response-1",
            part=None, rule=True, **changes):
    result = JevResult({"Q1": JevAnswer("Q1", "choice", choice=choice,
                                      confidence=confidence, probabilities=dist)},
                       model, request, 12, 3)
    ctx = dict(item_id=item, item_part=part, support_id="fixture-support-1",
               observation_id="O1", chunk_id=chunk, coder_version="fixture-v1",
               configured_model="fixture-jev", question_set_version="fixture-questions-r11",
               setup_pointer=build_instrument(instrument_payload())["instrument_id"],
               classifier_rule=_rule(item, part) if rule else None)
    ctx.update(changes)
    return CoderRecord.from_jev(result, question_id="Q1", **ctx)


@pytest.mark.parametrize(("dist", "probability", "cause"), [
    ({"yes": 0.8, "no": 0.2}, 0.8, None),
    ({"yes": 0.7999, "no": 0.2001}, 0.7999, "below_threshold"),
    ({"yes": 0.0, "no": 1.0}, 0.0, "below_threshold"),
    (None, None, "distribution_unavailable"),
    ({"no": 1.0}, None, "chosen_answer_unavailable"),
    ({}, None, "chosen_answer_unavailable"),
])
def test_chosen_probability_not_generic_confidence(dist, probability, cause):
    record = _record(item="core.content_data", choice="yes", dist=dist)
    assert record.confidence == 0.99
    assert record.chosen_value == "yes"
    assert record.probability_distribution == dist
    assert record.chosen_answer_probability == probability
    assert record.downgrade_cause == cause
    assert record.final_value == ("yes" if cause is None else "unknown")
    assert record.downgraded is (cause is not None)
    assert CoderRecord.from_json(record.to_json()) == record


@pytest.mark.parametrize("choice", ["confirms_activity", "confirms_absence", "no_genai", "event_only"])
@pytest.mark.parametrize("dist", [None, {}, {"other_body": 1.0}])
def test_page_verdict_is_retained_and_tagged(choice, dist):
    record = _record(choice=choice, dist=dist)
    assert record.final_value == choice
    assert record.downgraded is True
    assert record.chosen_answer_probability is None
    assert CoderRecord.from_json(record.to_json()) == record


def test_negative_code_still_obeys_probability_bar():
    record = _record(item="core.content_data", choice="no", dist={"no": 0.79, "yes": 0.21})
    assert record.final_value == "unknown"
    assert record.chosen_value == "no"
    assert _record(dist={"confirms_activity": 0.9}, confidence=0.01).downgraded is False


def test_all_chunks_keep_distinct_actual_response_metadata():
    records = [_record(dist={"confirms_activity": p}, chunk=f"C{i}",
                       request=f"fixture-request-{i}", model=f"fixture-response-{i}")
               for i, p in enumerate((0.9, 0.8, 0.2), 1)]
    restored = records_from_json(records_to_json(records))
    assert restored == records
    assert [r.chunk_id for r in restored] == ["C1", "C2", "C3"]
    assert len({r.request_id for r in restored}) == 3
    assert len({r.actual_response_model for r in restored}) == 3
    assert len({r.question_id for r in restored}) == 1  # no deduplication by question


@pytest.mark.parametrize("item", ["core.governance_form", "core.service_domain"])
def test_multivalue_codes_are_recorded_and_checked_individually(item):
    # Fixtures stand for separate actual selected-code responses; no invented
    # joint probability or multi-select request expansion happens in this module.
    code_a, code_b = FIELDS[item]["codes"][:2]
    records = [_record(item=item, choice=code, dist={code: p, "unknown": 1-p})
               for code, p in [(code_a, 0.91), (code_b, 0.7)]]
    assert [r.final_value for r in records] == [code_a, "unknown"]
    assert [r.chosen_value for r in records] == [code_a, code_b]
    assert records_from_json(records_to_json(records)) == records


def test_multipart_and_year_value_remain_lexical():
    part = _record(item="core.observed_actor_relationship", part="searched_institution_role",
                   choice="beneficiary", dist={"beneficiary": 0.8})
    year = _record(item="core.year_announced", choice="2025", dist={"2025": 0.8, "2024": 0.2})
    assert records_from_json(records_to_json([part, year])) == [part, year]
    assert year.final_value == "2025"
    with pytest.raises(ValueError, match="different item/part"):
        replace(part, item_part="relationship")


def test_generic_score_roundtrip_preserves_integer_distribution_keys():
    base = _record(rule=False)
    result = JevResult({"score": JevAnswer("score", "score", score=1.0,
                                          confidence=0.9, probabilities={0: 0.1, 1: 0.9})},
                       "fixture-score-model", "fixture-score-request", 10, 1)
    context = {k: getattr(base, k) for k in ("item_id", "item_part", "support_id", "observation_id", "chunk_id", "coder_version", "configured_model", "question_set_version", "setup_pointer")}
    record = CoderRecord.from_jev(result, question_id="score", **context)
    restored = CoderRecord.from_json(record.to_json())
    assert restored.probability_distribution == {0: 0.1, 1: 0.9}
    assert all(type(k) is int for k in restored.probability_distribution)
    assert restored.chosen_answer_probability == 0.9
    assert restored.downgraded is None  # capture only, no signed categorical policy


def test_noul_absence_is_typed_not_applicable_not_provider_omission():
    record = replace(_record(rule=False), answer_type="noul", chosen_value=0.35,
                     confidence=None, probability_distribution=None)
    assert record.probability_status == "answer_type_not_applicable"
    assert record.chosen_answer_probability is None
    assert record.downgrade_cause is None
    assert record.downgraded is None
    assert CoderRecord.from_json(record.to_json()) == record
    with pytest.raises(ValueError, match="categorical"):
        replace(record, classifier_rule=_rule())


def test_mechanical_and_rule_set_values_use_nulls_and_actual_rule():
    record = replace(_record(rule=False), coder_type="mechanical", answer_type="rule",
                     chosen_value="not_assessable", configured_model=None,
                     actual_response_model=None, request_id=None, confidence=None,
                     probability_distribution=None, rule_reference="fixture-page-not-reviewed-v1")
    assert record.probability_status == "coder_not_applicable"
    assert record.downgraded is None
    assert record.final_value == "not_assessable"
    assert CoderRecord.from_json(record.to_json()) == record
    with pytest.raises(ValueError, match="rule_reference"):
        replace(record, rule_reference=None)
    with pytest.raises(ValueError, match="typed null"):
        replace(record, request_id="made-up")


@pytest.mark.parametrize(("coder", "answer_type", "value"), [
    ("quote_step", "extracted", 'verbatim; "quote"\nnew line'),
    ("detector", "detected", {"score": 0.51, "label": "fixture"}),
    ("derived", "rule", ["one", "two"]),
])
def test_other_automated_coders_preserve_typed_values(coder, answer_type, value):
    changes = dict(coder_type=coder, answer_type=answer_type, chosen_value=value,
                   confidence=None, probability_distribution=None)
    if coder == "derived":
        changes.update(configured_model=None, actual_response_model=None, request_id=None,
                       rule_reference="fixture-combining-rule")
    record = replace(_record(rule=False), **changes)
    assert CoderRecord.from_json(record.to_json()) == record


@pytest.mark.parametrize("field", ["configured_model", "actual_response_model", "request_id", "coder_version", "question_set_version"])
@pytest.mark.parametrize("value", [None, "", " "])
def test_required_provenance_is_not_fabricated(field, value):
    with pytest.raises(ValueError, match="actual provenance"):
        replace(_record(), **{field: value})


@pytest.mark.parametrize("value", [None, "", "setup-R1", "fixture-instrument"])
def test_setup_placeholders_are_refused(value):
    with pytest.raises(ValueError, match="instrument"):
        replace(_record(), setup_pointer=value)


@pytest.mark.parametrize("value", [-0.01, 1.01, True, float("nan"), float("inf"), "0.8"])
def test_invalid_distribution_values_refused(value):
    with pytest.raises(ValueError):
        _record(dist={"confirms_activity": value})


def test_input_mutation_cannot_change_captured_distribution():
    dist = {"confirms_activity": 0.8, "no_genai": 0.2}
    record = _record(dist=dist)
    dist["confirms_activity"] = 0.0
    assert record.chosen_answer_probability == 0.8


def test_roundtrip_rejects_tampered_derived_facts_and_duplicate_keys():
    record = _record()
    data = record.to_dict()
    data["chosen_answer_probability"] = 0.0
    with pytest.raises(ValueError, match="derived facts"):
        CoderRecord.from_dict(data)
    data = record.to_dict()
    data["probability_distribution"] = [["confirms_activity", 0.2], ["confirms_activity", 0.8]]
    with pytest.raises(ValueError, match="duplicate"):
        CoderRecord.from_dict(data)
    with pytest.raises(ValueError, match="duplicate JSON"):
        CoderRecord.from_json('{"format":"one","format":"two"}')


def test_exact_signed_rule_loader_and_precise_mapping_gaps():
    raw = b'''items:
  core.page_verdict:
    coder: classifier
    threshold: {metric: chosen_answer_probability, bar: 0.8}
    downgrade_target: tag_only
  fixture.special:
    coder: classifier
    threshold: {metric: chosen_answer_probability, bar: 0.8}
    downgrade_target: no_evidence
    values: {parts: [a, b]}
'''
    digest = hashlib.sha256(raw).hexdigest()
    rules = load_classifier_rules(raw, expected_sha256=digest)
    assert set(rules) == {("core.page_verdict", None), ("fixture.special", "a"), ("fixture.special", "b")}
    special = _record(item="fixture.special", part="a", classifier_rule=rules["fixture.special", "a"])
    assert special.final_value == "no_evidence"  # not a universal unknown fallback
    with pytest.raises(ValueError, match="SHA256"):
        load_classifier_rules(raw + b"\n", expected_sha256=digest)
    missing = raw.replace(b"downgrade_target: no_evidence", b"downgrade_target: none")
    with pytest.raises(ValueError, match="fixture.special: no signed"):
        load_classifier_rules(missing, expected_sha256=hashlib.sha256(missing).hexdigest())


@pytest.mark.parametrize("dist", [None, {}, {"confirms_activity": 0.0}, {"confirms_activity": 0.8}])
def test_q2a_storage_compatibility_with_original_support_and_full_companion(tmp_path, dist):
    data, instrument, _, _ = fixture_bundle(tmp_path)
    source = data["sources"]["S1"]
    support = next(s for s in source["item_support"] if s["item_id"] == "core.page_verdict")
    record = _record(dist=dist, support_id=support["support_id"], observation_id=support["observation_id"],
                     chunk=support["chunk_id"], setup_pointer=instrument["instrument_id"])
    projection = record.storage_projection(support=support, instrument=instrument)
    index = next(i for i, c in enumerate(source["coder_records"]) if c["support_id"] == support["support_id"])
    source["coder_records"][index] = projection
    envelope = StorageEnvelope(data, instrument, artifact_root=tmp_path)
    assert envelope is not None
    assert projection["chosen_answer_probability"] == record.chosen_answer_probability
    assert projection["probability_distribution"] == dist
    assert "downgrade_cause" not in projection  # unchanged writer's narrow schema
    companion = CoderRecord.from_json(record.to_json())
    assert companion.downgrade_cause == record.downgrade_cause
    assert companion.final_value == "confirms_activity"
    assert companion.chosen_value == support["value_json"]


def test_nonpage_downgrade_projection_retains_original_and_does_not_forge_final_support(tmp_path):
    data, instrument, _, _ = fixture_bundle(tmp_path)
    source = data["sources"]["S1"]
    support = next(s for s in source["item_support"] if s["item_id"] == "core.evaluation_documented")
    record = _record(item=support["item_id"], choice=support["value_json"], support_id=support["support_id"],
                     observation_id=support["observation_id"], chunk=support["chunk_id"])
    assert record.final_value == "unknown"
    projection = record.storage_projection(support=support, instrument=instrument)
    index = next(i for i, c in enumerate(source["coder_records"]) if c["support_id"] == support["support_id"])
    source["coder_records"][index] = projection
    StorageEnvelope(data, instrument, artifact_root=tmp_path)
    assert projection["chosen_value"] == "results_reported"
    assert CoderRecord.from_json(record.to_json()).final_value == "unknown"
    altered_support = {**support, "value_json": "unknown"}
    with pytest.raises(ValueError, match="original code"):
        record.storage_projection(support=altered_support, instrument=instrument)
    # Applying the final value without real downstream support must still fail.
    source["values"][support["item_id"]] = record.final_value
    with pytest.raises(ValueError, match="missing keyed support"):
        StorageEnvelope(data, instrument, artifact_root=tmp_path)


def test_q2a_refuses_invented_or_inconsistent_instrument_and_support(tmp_path):
    data, instrument, _, _ = fixture_bundle(tmp_path)
    support = next(s for s in data["sources"]["S1"]["item_support"] if s["item_id"] == "core.page_verdict")
    record = _record(support_id=support["support_id"])
    for changed in (replace(record, request_id="fixture-other", chunk_id="C999"),
                    replace(record, support_id=None), replace(record, setup_pointer="0"*64),
                    replace(record, configured_model="today-default"),
                    replace(record, question_set_version="today-default")):
        with pytest.raises(ValueError):
            changed.storage_projection(support=support, instrument=instrument)
    tampered = json.loads(json.dumps(instrument))
    tampered["payload"]["configured_jev_model"] = "today-default"
    with pytest.raises(ValueError, match="identity mismatch"):
        record.storage_projection(support=support, instrument=tampered)


def test_result_refuses_missing_answer_and_missing_request_id():
    context = dict(item_id="core.page_verdict", item_part=None, support_id=None,
                   observation_id=None, chunk_id="C1", coder_version="fixture",
                   configured_model="fixture", question_set_version="fixture",
                   setup_pointer="a"*64, classifier_rule=_rule())
    with pytest.raises(ValueError, match="missing answer"):
        CoderRecord.from_jev(JevResult({}, "fixture", "fixture", 0, 0), question_id="Q", **context)
    result = JevResult({"Q": JevAnswer("Q", "choice", choice="no_genai")}, "fixture", None, 0, 0)
    with pytest.raises(ValueError, match="request_id"):
        CoderRecord.from_jev(result, question_id="Q", **context)


def test_q2a_mechanical_projection_requires_matching_actual_rule(tmp_path):
    data, instrument, _, _ = fixture_bundle(tmp_path)
    row = data["sources"]["S1"]
    support = next(s for s in row["item_support"] if s["item_id"] == "core.content_data")
    old_id = support["support_id"]
    support.update(value_json="not_asked", support_status="set_by_rule",
                   support_rule_name="fixture-content-gate-rule-v1")
    support["support_id"] = support_id(data["run_id"], data["institution_uid"], support)
    record = replace(_record(item="core.content_data", rule=False), coder_type="mechanical", answer_type="rule",
                     chosen_value="not_asked", configured_model=None,
                     actual_response_model=None, request_id=None, confidence=None,
                     probability_distribution=None, support_id=support["support_id"],
                     rule_reference=support["support_rule_name"])
    projection = record.storage_projection(support=support, instrument=instrument)
    row["values"]["core.content_data"] = "not_asked"
    index = next(i for i, c in enumerate(row["coder_records"]) if c["support_id"] == old_id)
    row["coder_records"][index] = projection
    StorageEnvelope(data, instrument, artifact_root=tmp_path)
    assert set(projection["field_availability"].values()) == {"coder_not_applicable"}
    with pytest.raises(ValueError, match="actual mechanical rule"):
        replace(record, rule_reference="another-rule").storage_projection(support=support, instrument=instrument)


@pytest.mark.parametrize("bad", [None, [], {}, {"format": "other"}])
def test_malformed_json_record_is_refused(bad):
    with pytest.raises(ValueError):
        CoderRecord.from_json(json.dumps(bad))
