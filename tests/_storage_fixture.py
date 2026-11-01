"""Local explicit D-007 fixtures; no provider call or claimed production setup."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from g3o.common.instrument import build_instrument, sha256_text
from g3o.common.storage import VERDICTS, StorageEnvelope, support_id, table_fields
from g3o.common.storage_fields import CODEBOOK_SHA256, FIELDS
from tests._layout import uid_for
from tests.test_persist import _activity, _source, _yes_response


def instrument_payload() -> dict[str, Any]:
    return {
        "schema_version": "g3o-instrument-v1", "codebook_release": "2.7",
        "codebook_sha256": CODEBOOK_SHA256,
        "codebook_item_hashes": {k: v["schema"]["x-item-hash"] for k, v in FIELDS.items()
                                 if "x-item-hash" in v["schema"]},
        "extract_contract_label": "fixture-extract-v27", "validate_contract_label": "fixture-validate-v27",
        "question_set_version": "fixture-questions-r11", "question_hashes": {"fixture-question": sha256_text("fixture question")},
        "prompt_hashes": {"fixture-prompt": sha256_text("fixture prompt")}, "configured_jev_model": "fixture-jev",
        "extractor_model_id": "fixture-extractor", "extractor_prompt_sha256": sha256_text("fixture prompt"),
        "extractor_configuration": {"temperature": 0, "purpose": "offline explicit fixture"},
        "chunker_version": "fixture-chunker-v1", "estimator_version": "fixture-estimator-v1",
        "token_budget": 100, "matcher_library": "fixture-exact", "matcher_version": "1",
        "matcher_threshold": 1.0, "chosen_answer_confidence_threshold": 0.8,
        "producer_code_revision": "fixture-only-not-production", "instrument_approval_reference": "PI 2026-11-01 P1a explicit local fixtures only",
    }


def _values(table: str) -> dict[str, Any]:
    # These are deliberately declared fixture responses, never runtime defaults.
    values: dict[str, Any] = {}
    for key, field in table_fields(table).items():
        if key in {"core.codebook_release", "core.setup_pointer", "core.evidence_channel"}:
            continue
        if "parts" in field:
            values[key] = {p: codes[0] for p, codes in field["parts"].items()}
        elif field["answer_type"] in ("list", "multi"):
            values[key] = []
        elif field["codes"]:
            values[key] = field["codes"][0]
        else:
            values[key] = "not_documented"
    if table == "activities":
        values.update({"core.activity_name": "Copilot pilot", "core.tool_name": ['Tool; "Alpha"', "Tool beta"],
                       "core.reported_outcomes": ['A result; with "quotes"\nand a newline.'],
                       "core.deployment_scale_number": "1,000", "core.n_sources": 1,
                       "core.confidence": "high", "core.cx_display_rollup": {},
                       "core.year_announced": "2025"})
    elif table == "sources":
        values.update({"core.page_verdict": "confirms_activity", "core.source_url": "https://example.gov/page",
                       "core.source_title": "Fixture page", "core.source_access_date": "2026-11-01",
                       "core.source_publication_date": "2025-01", "core.source_language": "en",
                       "core.source_credibility": "high", "core.confidence": "high",
                       "core.content_contact_emails": ["Ada@EXAMPLE.GOV", "Ada@example.gov", "ada@example.gov", "Ada+pilot@example.gov"],
                       "core.evaluation_documented": "results_reported"})
    else:
        values.update({"core.has_genai_activity": "yes", "core.verdict_rule": "2.7",
                       "core.evidence_tier": "documented_use", "core.institution_summary": "Explicit fixture",
                       "core.review_depth": {"web_extract": {"n_pages_reviewed": 1,
                           "n_pages_by_verdict": {v: int(v == "confirms_activity") for v in VERDICTS},
                           "n_pages_failed": 0, "n_followed_links": 0}}})
    return values


def fixture_bundle(tmp_path: Path, *, merged: bool = False):
    text = 'First quote: Tool; "Alpha". Second quote: Tool beta.\n' + "Unabridged evidence. " * 80
    page = tmp_path / "page.txt"
    page.write_bytes(text.encode("utf-8"))
    payload = instrument_payload()
    record = build_instrument(payload)
    data = {"format": "g3o-storage-v1", "run_id": "R1", "institution_uid": uid_for("INST-0001"),
            "institution_id": "INST-0001", "codebook_release": "2.7", "setup_pointer": record["instrument_id"],
            "evidence_channel": "web_extract", "activities": {}, "sources": {},
            "summary": {"values": _values("summary"), "item_support": [], "coder_records": []}}
    for n in (1, 2):
        aid, sid, oid = f"A{1 if merged else n}", f"S{n}", f"O{n}"
        if aid not in data["activities"]:
            vals = _values("activities")
            vals["core.n_sources"] = 2 if merged else 1
            data["activities"][aid] = {"values": vals, "item_support": [], "coder_records": [], "observation_ids": [], "activity_relations": []}
        data["activities"][aid]["observation_ids"].append(oid)
        vals = _values("sources")
        vals["core.evaluation_documented"] = "results_reported" if n == 1 else "required_or_planned"
        data["sources"][sid] = {"values": vals, "item_support": [], "coder_records": [],
                               "observation_ids": [oid], "activity_id": aid,
                               "page_artifact_path": "page.txt", "page_content_sha256": sha256_text(text)}
        quote = text if n == 1 else "Second quote: Tool beta."
        support = {"item_id": "core.tool_name", "item_part": None,
                   "value_json": 'Tool; "Alpha"' if n == 1 else "Tool beta", "observation_id": oid,
                   "source_id": sid, "chunk_id": f"C{n}", "supporting_text": quote, "support_status": "supported",
                   "support_rule_name": "not_asked", "support_status_second_reason": "not_asked",
                   "uncertainty_flags": [], "input_support_ids": [], "support_text_sha256": sha256_text(quote),
                   "page_content_sha256": sha256_text(text), "passage": {"start": text.index(quote), "end": text.index(quote) + len(quote)}}
        support["support_id"] = support_id("R1", data["institution_uid"], support)
        data["activities"][aid]["item_support"].append(support)
        coder = {"support_id": support["support_id"], "observation_id": oid, "item_id": "core.tool_name",
                 "item_part": None, "coder_type": "quote_step", "coder_version": "fixture-v1",
                 "configured_model": "fixture-extractor", "actual_response_model": "fixture-response-model",
                 "request_id": f"fixture-request-{n}", "question_set_version": "fixture-questions-r11",
                 "chunk_id": f"C{n}", "chosen_value": support["value_json"],
                 "chosen_answer_probability": None, "probability_distribution": None}
        data["activities"][aid]["coder_records"].append(coder)
    if merged:
        (tmp_path / "page2.txt").write_bytes(text.encode("utf-8"))
        data["sources"]["S2"]["page_artifact_path"] = "page2.txt"
        data["sources"]["S2"]["values"]["core.source_url"] = "https://example.gov/second-page"
        depth = data["summary"]["values"]["core.review_depth"]["web_extract"]
        depth["n_pages_reviewed"] = 2
        depth["n_pages_by_verdict"]["confirms_activity"] = 2
    # Every classified/extracted selected value retains a keyed support record.
    for table in ("activities", "sources"):
        for row in data[table].values():
            oid = row["observation_ids"][0]
            sid = "S1" if oid == "O1" else "S2"
            for item, value in row["values"].items():
                field = FIELDS[item]
                if field["coder"] not in {"classifier", "quote_step"}:
                    continue
                pairs = list(value.items()) if "parts" in field else [(None, v) for v in value] if isinstance(value, list) else [(None, value)]
                for part, selected in pairs:
                    if any(s["item_id"] == item and s["item_part"] == part and s["value_json"] == selected for s in row["item_support"]):
                        continue
                    no_quote = selected in ("not_documented", "unknown", "no")
                    quote = "" if no_quote else text
                    support = {"item_id": item, "item_part": part, "value_json": selected,
                               "observation_id": oid, "source_id": sid, "chunk_id": "C1",
                               "supporting_text": quote, "support_status": "not_required" if no_quote else "supported",
                               "support_rule_name": "not_asked", "support_status_second_reason": "not_asked",
                               "uncertainty_flags": [], "input_support_ids": [], "support_text_sha256": sha256_text(quote),
                               "page_content_sha256": sha256_text(text), "passage": {"start": 0, "end": len(quote)}}
                    support["support_id"] = support_id("R1", data["institution_uid"], support)
                    row["item_support"].append(support)
    for table in ("activities", "sources"):
        for row in data[table].values():
            for support in row["item_support"]:
                if any(c["support_id"] == support["support_id"] for c in row["coder_records"]):
                    continue
                kind = FIELDS[support["item_id"]]["coder"]
                row["coder_records"].append({
                    "support_id": support["support_id"], "observation_id": support["observation_id"],
                    "item_id": support["item_id"], "item_part": support["item_part"], "coder_type": kind,
                    "coder_version": "fixture-v1", "configured_model": "fixture-jev" if kind == "classifier" else "fixture-extractor",
                    "actual_response_model": "fixture-response-model", "request_id": "fixture-" + support["support_id"],
                    "question_set_version": "fixture-questions-r11", "chunk_id": support["chunk_id"],
                    "chosen_value": support["value_json"], "chosen_answer_probability": None, "probability_distribution": None})
    relation = {"relation_id": "relation-fixture", "lhs_observation_id": "O1", "rhs_observation_id": "O2",
                "relation": "same_activity" if merged else "distinct_action", "source_refs": ["S1", "S2"],
                "support_ids": [], "lhs_final_activity_id": "A1", "rhs_final_activity_id": "A1" if merged else "A2",
                "relation_scope": "cross_page" if merged else "within_page"}
    data["activities"]["A1"]["activity_relations"].append(relation)
    activities = [_activity("A1", n_sources=2)] if merged else [_activity("A1"), _activity("A2")]
    sources = [_source("S1", "A1", source_url=data["sources"]["S1"]["values"]["core.source_url"]),
               _source("S2", "A1" if merged else "A2", source_url=data["sources"]["S2"]["values"]["core.source_url"])]
    response = _yes_response(activities=activities, sources=sources)
    return data, record, response, StorageEnvelope(data, record, artifact_root=tmp_path)