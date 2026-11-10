"""T-028 producer adapters: support/coder nodes and Stage 6 artifacts (offline, fake inputs).

Expectations are taken from the signed rules, not from the adapter:
R-042 (either the calibrated matcher or the 80% word rule, against the text the
quote came from), R-041/R-081 (downgrade to ``unknown``; page verdict tag-only),
R-026 (coder provenance per code) and the D-007 support record contract.
"""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from g3o.common.contract import ConsolidatedInstitutionResponse
from g3o.common.instrument import build_instrument
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.common.jev_record import ClassifierRule, CoderRecord
from g3o.common.storage import StorageEnvelope
from g3o.common.storage_fields import CODEBOOK_SHA256
from g3o.common.support_check import CodeEvidence, Entailment, PageSources, check_code, match_quote
from g3o.persist.stage6_adapters import (
    MissingUpstreamError,
    PageArtifact,
    SupportContext,
    activity_confidence_value,
    assemble_storage,
    coder_nodes,
    source_confidence,
    support_nodes,
    write_stage6_artifacts,
)
from tests._storage_fixture import fixture_bundle, instrument_payload

ITEM = "core.evaluation_documented"  # classifier, support required, downgrade_target unknown, X35-labelled
EXACT = "Second quote: Tool beta."
TRUE = Entailment("true", 0.95)


def _rapidfuzz_instrument():
    return build_instrument({**instrument_payload(), "matcher_library": "rapidfuzz",
                             "matcher_version": "3.14.3", "matcher_threshold": 93})


def _setup(tmp_path):
    data, _, response, _ = fixture_bundle(tmp_path)
    instrument = _rapidfuzz_instrument()
    data["setup_pointer"] = instrument["instrument_id"]
    text = (tmp_path / "page.txt").read_bytes().decode("utf-8")
    sources = PageSources("P1", {"C1": text})
    artifact = PageArtifact("S1", "page.txt", text, {"C1": (0, len(text))})
    ctx = SupportContext("R1", data["institution_uid"], "O1", "S1", [])
    return data, instrument, response, sources, artifact, ctx


def _check(sources, quote, *, value="results_reported", probability=0.95, item=ITEM):
    return check_code(CodeEvidence(item, value, "C1", probability=probability, quote=quote,
                                   quote_chunk_id="C1" if quote else None, entailment=TRUE), sources)


def _coder(nodes, instrument, *, value="results_reported", dist=None, item=ITEM):
    target = "tag_only" if item == "core.page_verdict" else "unknown"
    result = JevResult({"Q": JevAnswer("Q", "choice", choice=value, confidence=0.99,
                                       probabilities=dist or {value: 0.95})}, "fake-response-model", "fake-request", 1, 1)
    return CoderRecord.from_jev(result, question_id="Q", item_id=item, item_part=None,
                                support_id=nodes.original["support_id"], observation_id="O1", chunk_id="C1",
                                coder_version="fake-v1", configured_model="fixture-jev",
                                question_set_version="fixture-questions-r11",
                                setup_pointer=instrument["instrument_id"],
                                classifier_rule=ClassifierRule(item, None, CODEBOOK_SHA256, target))


def _envelope(tmp_path, data, instrument, nodes, coders, *, item=ITEM):
    data = deepcopy(data)
    row = data["sources"]["S1"]
    old = {s["support_id"] for s in row["item_support"] if s["item_id"] == item}
    row["item_support"] = [s for s in row["item_support"] if s["support_id"] not in old]
    row["coder_records"] = [c for c in row["coder_records"] if c["support_id"] not in old]
    row["item_support"] += [n for n in (nodes.original, nodes.final) if n is not None]
    row["coder_records"] += [c for c in coders if c is not None]
    row["values"][item] = (nodes.final or nodes.original)["value_json"]
    return StorageEnvelope(data, instrument, artifact_root=tmp_path)


# --- R-042 quote presence ------------------------------------------------------


def test_exact_quote_keeps_original_text_and_is_stored(tmp_path):
    data, instrument, _, sources, artifact, ctx = _setup(tmp_path)
    result = _check(sources, EXACT)
    assert result.support_status == "supported"
    nodes = support_nodes(result, sources, artifact, ctx, instrument)
    assert nodes.final is None
    assert nodes.original["supporting_text"] == EXACT
    assert nodes.original["value_json"] == "results_reported"
    assert nodes.original["support_rule_name"] == "not_asked"
    assert nodes.original["support_status_second_reason"] == "not_asked"
    assert nodes.provenance["channel"] == "main" and nodes.provenance["quote_segment"] == "C1"
    assert nodes.provenance["match"]["matched"] is True
    assert nodes.provenance["matcher"]["threshold"] == 93
    original, final, companion = coder_nodes(_coder(nodes, instrument), nodes, instrument)
    assert final is None and companion is None
    _envelope(tmp_path, data, instrument, nodes, [original])


FUZZY = "second QUOTE - tool, beta"  # case/punctuation differ: not a substring, matcher passes
WORDS = "Second quote: Tool beta extraordinarily"  # 4 of 5 words present: word rule only


def test_fuzzy_quote_accepted_by_matcher_keeps_original_quote(tmp_path):
    _, instrument, _, sources, artifact, ctx = _setup(tmp_path)
    assert FUZZY not in artifact.text
    result = _check(sources, FUZZY)
    assert result.support_status == "supported"
    nodes = support_nodes(result, sources, artifact, ctx, instrument)
    assert nodes.original["supporting_text"] == FUZZY  # never replaced with page text
    assert nodes.provenance["match"]["matcher_pass"] is True


def test_word_presence_quote_accepted_by_80_percent_rule(tmp_path):
    _, instrument, _, sources, artifact, ctx = _setup(tmp_path)
    result = _check(sources, WORDS)
    assert result.support_status == "supported"
    nodes = support_nodes(result, sources, artifact, ctx, instrument)
    match = nodes.provenance["match"]
    assert match["matcher_pass"] is False and match["rule_80"] is True
    assert match["decided_by"] == "word_rule" and match["presence_word"] == 0.8
    assert nodes.original["supporting_text"] == WORDS


def test_rejected_quote_is_downgraded_and_retained_verbatim(tmp_path):
    _, instrument, _, sources, artifact, ctx = _setup(tmp_path)
    quote = "The ministry cancelled every budget line for translation services."
    result = _check(sources, quote)
    assert result.support_status == "downgraded_no_quote"
    nodes = support_nodes(result, sources, artifact, ctx, instrument)
    assert nodes.original["supporting_text"] == quote
    assert nodes.original["support_status"] == "downgraded_no_quote"
    assert nodes.provenance["match"]["matched"] is False
    assert nodes.final["value_json"] == "unknown"
    assert nodes.final["supporting_text"] == ""  # no fabricated replacement quote


@pytest.mark.xfail(strict=True, reason="blocked: g3o/common/storage.py (T-012 claim) still requires an exact "
                   "substring and only lets mechanical coders back set_by_rule supports")
@pytest.mark.parametrize("quote", [FUZZY, WORDS])
def test_matcher_accepted_quote_is_stored(tmp_path, quote):
    data, instrument, _, sources, artifact, ctx = _setup(tmp_path)
    nodes = support_nodes(_check(sources, quote), sources, artifact, ctx, instrument)
    original, _, _ = coder_nodes(_coder(nodes, instrument), nodes, instrument)
    _envelope(tmp_path, data, instrument, nodes, [original])


# --- original vs final after a downgrade ----------------------------------------


def test_low_confidence_downgrade_keeps_original_and_links_mechanical_final(tmp_path):
    _, instrument, _, sources, artifact, ctx = _setup(tmp_path)
    result = _check(sources, EXACT, probability=0.5)
    assert (result.support_status, result.value) == ("downgraded_low_confidence", "unknown")
    nodes = support_nodes(result, sources, artifact, ctx, instrument)
    assert nodes.original["value_json"] == "results_reported"
    assert nodes.original["supporting_text"] == EXACT
    assert nodes.final["value_json"] == "unknown"
    assert nodes.final["support_status"] == "downgraded_low_confidence"
    assert nodes.final["input_support_ids"] == [nodes.original["support_id"]]
    assert nodes.final["support_id"] != nodes.original["support_id"]
    record = _coder(nodes, instrument, dist={"results_reported": 0.5, "not_documented": 0.5})
    original, final, companion = coder_nodes(record, nodes, instrument)
    assert original["coder_type"] == "classifier" and original["chosen_value"] == "results_reported"
    assert original["chosen_answer_probability"] == 0.5
    assert final["coder_type"] == "mechanical" and final["chosen_value"] == "unknown"
    assert final["support_id"] == nodes.final["support_id"]
    assert all(final[k] is None for k in ("configured_model", "actual_response_model", "request_id"))
    assert companion.rule_reference and CoderRecord.from_json(companion.to_json()).chosen_value == "unknown"
    assert record.chosen_value == "results_reported"  # original never overwritten


@pytest.mark.xfail(strict=True, reason="blocked: storage.py/jev_record.py accept a mechanical coder only for "
                   "set_by_rule; a downgraded final value needs a linked mechanical node")
def test_downgraded_final_node_is_stored(tmp_path):
    data, instrument, _, sources, artifact, ctx = _setup(tmp_path)
    nodes = support_nodes(_check(sources, EXACT, probability=0.5), sources, artifact, ctx, instrument)
    original, final, _ = coder_nodes(_coder(nodes, instrument, dist={"results_reported": 0.5}), nodes, instrument)
    _envelope(tmp_path, data, instrument, nodes, [original, final])


def test_page_verdict_downgrade_is_tag_only_without_final_node(tmp_path):
    data, instrument, _, sources, artifact, ctx = _setup(tmp_path)
    result = _check(sources, EXACT, item="core.page_verdict", value="confirms_activity", probability=0.5)
    assert result.support_status == "downgraded_low_confidence"
    nodes = support_nodes(result, sources, artifact, ctx, instrument)
    assert nodes.final is None and nodes.original["value_json"] == "confirms_activity"
    original, final, _ = coder_nodes(_coder(nodes, instrument, item="core.page_verdict", value="confirms_activity",
                                            dist={"confirms_activity": 0.5}), nodes, instrument)
    assert final is None
    _envelope(tmp_path, data, instrument, nodes, [original], item="core.page_verdict")


# --- refusals ---------------------------------------------------------------------


def test_refuses_match_not_reproduced_on_stored_artifact(tmp_path):
    _, instrument, _, sources, artifact, ctx = _setup(tmp_path)
    result = _check(sources, EXACT)
    forged = replace(result, match=match_quote(EXACT, "unrelated text"))
    with pytest.raises(ValueError, match="not reproduced"):
        support_nodes(forged, sources, artifact, ctx, instrument)
    shifted = PageArtifact("S1", "page.txt", artifact.text, {"C1": (1, len(artifact.text))})
    with pytest.raises(ValueError, match="differs from the checked text"):
        support_nodes(result, sources, shifted, ctx, instrument)
    with pytest.raises(ValueError, match="not located"):
        support_nodes(replace(result, quote_chunk_id="P1#chrome"), sources, artifact, ctx, instrument)


def test_refuses_instrument_without_the_t024_matcher(tmp_path):
    data, _, _, sources, artifact, ctx = _setup(tmp_path)
    _, fixture_instrument, _, _ = fixture_bundle(tmp_path)
    with pytest.raises(ValueError, match="not the T-024 matcher"):
        support_nodes(_check(sources, EXACT), sources, artifact, ctx, fixture_instrument)


def test_refuses_coder_below_bar_that_support_did_not_downgrade(tmp_path):
    _, instrument, _, sources, artifact, ctx = _setup(tmp_path)
    nodes = support_nodes(_check(sources, EXACT), sources, artifact, ctx, instrument)
    with pytest.raises(ValueError, match="did not downgrade"):
        coder_nodes(_coder(nodes, instrument, dist={"results_reported": 0.5}), nodes, instrument)


def test_missing_upstream_inputs_refuse_explicitly(tmp_path):
    data, instrument, response, sources, artifact, ctx = _setup(tmp_path)
    with pytest.raises(MissingUpstreamError, match="uncertainty"):
        support_nodes(_check(sources, EXACT), sources, artifact, replace(ctx, uncertainty_flags=None), instrument)
    common = dict(run_id="R1", institution_uid=data["institution_uid"], institution_id="INST-0001",
                  instrument=instrument, evidence_channel="web_extract", artifact_root=tmp_path)
    with pytest.raises(MissingUpstreamError, match="T-026"):
        assemble_storage(activities=None, sources=data["sources"], summary=data["summary"], **common)
    with pytest.raises(MissingUpstreamError, match="summary"):
        assemble_storage(activities=data["activities"], sources=data["sources"], summary=None, **common)
    partial = deepcopy(data["sources"])
    del partial["S1"]["values"]["core.source_credibility"]
    with pytest.raises(MissingUpstreamError, match="T-015") as err:
        assemble_storage(activities=data["activities"], sources=partial, summary=data["summary"], **common)
    assert err.value.missing == ("sources[S1].core.source_credibility (derived)",)
    envelope = assemble_storage(activities=data["activities"], sources=data["sources"],
                                summary=data["summary"], **common)
    with pytest.raises(MissingUpstreamError, match="6_validate.json"):
        write_stage6_artifacts(tmp_path / "inst", envelope, None)
    with pytest.raises(MissingUpstreamError, match="T-015 source-level confidence"):
        source_confidence("S1", None)
    with pytest.raises(MissingUpstreamError):
        activity_confidence_value(["S1", "S2"], {"S1": "medium"}, {"S1": "g1", "S2": "g2"})
    assert activity_confidence_value(["S1", "S2"], {"S1": "medium", "S2": "medium"}, {"S1": "g1", "S2": "g2"}) == "high"


def test_written_artifacts_reload_bound_to_each_other(tmp_path):
    data, instrument, response, *_ = _setup(tmp_path)
    envelope = assemble_storage(run_id="R1", institution_uid=data["institution_uid"], institution_id="INST-0001",
                                instrument=instrument, evidence_channel="web_extract",
                                activities=data["activities"], sources=data["sources"],
                                summary=data["summary"], artifact_root=tmp_path)
    validate_path, storage_path = write_stage6_artifacts(tmp_path / "inst", envelope, response)
    stored = json.loads(storage_path.read_text(encoding="utf-8"))
    assert "_page_text" not in stored["sources"]["S1"]
    assert StorageEnvelope(stored, instrument, artifact_root=tmp_path).data["setup_pointer"] == instrument["instrument_id"]
    ConsolidatedInstitutionResponse.model_validate(json.loads(validate_path.read_text(encoding="utf-8")))
    other = response.model_copy(update={"sources": response.sources[:1]})
    with pytest.raises(ValueError):
        write_stage6_artifacts(tmp_path / "inst2", envelope, other)
