"""Stage 5 Group-D ``_NA_`` salvage (fix/stage5-groupd-salvage).

A ``confirms_activity`` row whose Group-D activity fields carry the illegal
literal ``_NA_`` used to fail ``BatchResponse`` validation and, because
validation is atomic over the page, take the whole page (and its confirmed
positive finding) down with it — the Qatar MCIT data-loss bug. These tests pin
the salvage behaviour that repairs such rows to the contract's prescribed
defaults instead of dropping them, keeps the repair targeted, and writes one
stable-reason attrition record per salvaged page.

Layers covered:
  • ``salvage_group_d_na`` unit behaviour (repair / skip / unsalvageable / malformed).
  • ``parse_extract_result`` integration (salvaged row survives; targeted; sink).
  • ``_run_extract`` → ``_persist`` telemetry (one ledger record, stable code).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from g3o.common import attrition
from g3o.common.batch_client import BatchResult
from g3o.common.contract import GROUP_D_FIELDS
from g3o.extract import make_custom_id, parse_extract_result, url_hash
from g3o.extract.batch import EMPTY_PAGE_MIN_CHARS
from g3o.extract.salvage import (
    GROUP_D_SALVAGE_DEFAULTS,
    GROUP_D_UNSALVAGEABLE,
    REASON_SALVAGED,
    REASON_UNSALVAGEABLE,
    GroupDSalvage,
    salvage_group_d_na,
)
from g3o.run import presweep as ps
from g3o.run.presweep import synth_institution_id
from g3o.scrape.render import FetchMetadata, RenderedPage

MCIT_ACCESS_DATE = "2026-06-10"


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_attrition_cache():
    attrition._reset_cache()
    yield
    attrition._reset_cache()


def _mcit_row(**overrides: Any) -> dict[str, Any]:
    """Named fixture: the Qatar MCIT failure case.

    Ministry of Communications and Information Technology (Qatar) has a real,
    confirmed public GenAI assistant, but the extractor left several Group-D
    fields (adoption stage, deployment mode, a deploy year, all four governance
    flags, outcomes/incidents, scope notes) as the illegal literal ``_NA_``
    while ``genai_evidence == confirms_activity``. ``activity_name`` and
    ``activity_type`` are populated, so every ``_NA_`` here is *salvageable*.
    """
    base: dict[str, Any] = {
        "row_id": 1,
        "batch_id": "b-mcit",
        "institution_id": "INST-QA-MCIT",
        "institution_name": "Ministry of Communications and Information Technology",
        "country": "Qatar",
        "branch_of_government": "executive",
        "level_of_government": "national",
        "has_genai_activity": "yes",
        "institution_summary": "MCIT operates a public-facing GenAI assistant.",
        "institution_search_languages": "en,ar",
        # Group D — activity_name + activity_type populated; the rest _NA_.
        "activity_name": "Lamma GenAI citizen assistant",
        "activity_type": "public_facing_service",
        "adoption_stage": "_NA_",
        "access_type": "proprietary_vendor",
        "interaction_type": "chatbot",
        "tool_name": "_NA_",
        "vendor": "Microsoft",
        "deployment_mode": "_NA_",
        "target_users": "public",
        "year_announced": "2024",
        "year_deployed": "_NA_",
        "has_human_oversight": "_NA_",
        "has_transparency_notice": "_NA_",
        "has_data_classification": "_NA_",
        "has_risk_assessment": "_NA_",
        "reported_outcomes": "_NA_",
        "reported_incidents": "_NA_",
        "scope_notes": "_NA_",
        # Group E — source (always filled).
        "source_url": "https://www.mcit.gov.qa/en/genai-assistant",
        "source_title": "MCIT launches citizen GenAI assistant",
        "source_publication_date": "2024-05",
        "source_access_date": MCIT_ACCESS_DATE,
        "source_type": "official_gov",
        "source_language": "en",
        "source_credibility": "high",
        "genai_evidence": "confirms_activity",
        "source_snippet": "The Ministry launched a generative-AI citizen assistant.",
        # Group F.
        "confidence": "medium",
        "uncertainty_flags": "none",
    }
    base.update(overrides)
    return base


def _mcit_meta(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "batch_id": "b-mcit",
        "chat_type": "web",
        "model_label": "gpt-5-nano",
        "response_timestamp": "2026-06-10T10:00:00Z",
        "n_institutions_in_batch": 1,
        "n_institutions_with_genai": 1,
        "n_data_rows": 1,
        "search_languages": "en,ar",
        "search_strategy_summary": "URLs supplied by the pipeline.",
        "notes": "none",
    }
    base.update(overrides)
    return base


def _mcit_payload(row_overrides: dict[str, Any] | None = None, **meta_overrides: Any) -> dict[str, Any]:
    return {
        "batch_metadata": _mcit_meta(**meta_overrides),
        "data": [_mcit_row(**(row_overrides or {}))],
    }


def _make_result(custom_id: str, content: dict[str, Any] | list[Any] | str) -> BatchResult:
    content_str = content if isinstance(content, str) else json.dumps(content)
    return BatchResult(
        custom_id=custom_id,
        success=True,
        response={"status_code": 200, "body": {"choices": [{"message": {"content": content_str}}]}},
        error=None,
        status_code=200,
    )


# The 16 salvageable Group-D fields with the exact default each _NA_ becomes.
_SALVAGEABLE_NA_ROW = {
    "adoption_stage": "unknown",
    "access_type": "unknown",
    "interaction_type": "unknown",
    "tool_name": "unknown",
    "vendor": "unknown",
    "deployment_mode": "unknown",
    "target_users": "unknown",
    "year_announced": "unknown",
    "year_deployed": "unknown",
    "has_human_oversight": "not_documented",
    "has_transparency_notice": "not_documented",
    "has_data_classification": "not_documented",
    "has_risk_assessment": "not_documented",
    "reported_outcomes": "none_reported",
    "reported_incidents": "none_reported",
    "scope_notes": "none",
}


# ---------------------------------------------------------------------------
# salvage_group_d_na — unit behaviour
# ---------------------------------------------------------------------------


def test_salvage_defaults_partition_covers_all_group_d_fields():
    """Every Group-D field is either salvageable or explicitly unsalvageable."""
    assert set(GROUP_D_SALVAGE_DEFAULTS) | GROUP_D_UNSALVAGEABLE == set(GROUP_D_FIELDS)
    assert not (set(GROUP_D_SALVAGE_DEFAULTS) & GROUP_D_UNSALVAGEABLE)
    assert GROUP_D_UNSALVAGEABLE == {"activity_type", "activity_name"}


def test_salvage_repairs_each_field_to_contract_default():
    """Every salvageable Group-D _NA_ becomes its exact prescribed default."""
    row = _mcit_row(**dict.fromkeys(GROUP_D_SALVAGE_DEFAULTS, "_NA_"))
    payload = {"batch_metadata": _mcit_meta(), "data": [row]}

    events = salvage_group_d_na(payload)

    assert len(events) == 1
    ev = events[0]
    assert ev.is_salvageable
    assert ev.row_id == 1
    assert ev.source_url == row["source_url"]
    assert set(ev.salvaged_fields) == set(_SALVAGEABLE_NA_ROW)
    assert not ev.unsalvageable_fields
    # The row was mutated in place to the contract defaults.
    for field_name, expected in _SALVAGEABLE_NA_ROW.items():
        assert payload["data"][0][field_name] == expected


def test_salvage_only_touches_the_na_group_d_fields():
    """Non-_NA_ Group-D values and all non-Group-D fields are left untouched."""
    payload = _mcit_payload()
    before = json.loads(json.dumps(payload))
    events = salvage_group_d_na(payload)

    assert len(events) == 1
    row = payload["data"][0]
    # Populated Group-D fields are unchanged.
    assert row["activity_name"] == before["data"][0]["activity_name"]
    assert row["activity_type"] == "public_facing_service"
    assert row["access_type"] == "proprietary_vendor"
    assert row["year_announced"] == "2024"
    # Group C/E/F untouched.
    assert row["has_genai_activity"] == "yes"
    assert row["genai_evidence"] == "confirms_activity"
    assert row["source_credibility"] == "high"
    assert row["uncertainty_flags"] == "none"


def test_salvage_ignores_rows_without_group_d_na():
    """A fully coded confirms_activity row produces no salvage event."""
    row = _mcit_row(
        adoption_stage="production", tool_name="Copilot", deployment_mode="integrated",
        year_deployed="2024", has_human_oversight="yes", has_transparency_notice="yes",
        has_data_classification="yes", has_risk_assessment="yes",
        reported_outcomes="none_reported", reported_incidents="none_reported",
        scope_notes="none",
    )
    payload = {"batch_metadata": _mcit_meta(), "data": [row]}
    assert salvage_group_d_na(payload) == []


def test_salvage_ignores_non_confirms_activity_rows():
    """A confirms_absence row keeps its Group-D _NA_ (that is correct for it)."""
    payload = {
        "batch_metadata": _mcit_meta(n_institutions_with_genai=0),
        "data": [
            _mcit_row(
                has_genai_activity="no",
                genai_evidence="confirms_absence",
                **dict.fromkeys(GROUP_D_FIELDS, "_NA_"),
            )
        ],
    }
    before = json.loads(json.dumps(payload))
    assert salvage_group_d_na(payload) == []
    assert payload == before


def test_salvage_unsalvageable_activity_type_left_untouched():
    """activity_type _NA_ cannot be repaired → row untouched, reported unsalvageable."""
    payload = _mcit_payload({"activity_type": "_NA_"})
    before_row = json.loads(json.dumps(payload["data"][0]))

    events = salvage_group_d_na(payload)

    assert len(events) == 1
    ev = events[0]
    assert not ev.is_salvageable
    assert "activity_type" in ev.unsalvageable_fields
    assert ev.salvaged_fields == ()
    # The doomed row is NOT mutated — not even its salvageable _NA_ siblings.
    assert payload["data"][0] == before_row


def test_salvage_unsalvageable_activity_name_left_untouched():
    payload = _mcit_payload({"activity_name": "_NA_"})
    events = salvage_group_d_na(payload)
    assert len(events) == 1
    assert not events[0].is_salvageable
    assert "activity_name" in events[0].unsalvageable_fields


@pytest.mark.parametrize("bad", [None, [], "x", 42, {"data": {}}, {"data": [1, "x"]}, {}])
def test_salvage_malformed_payload_returns_empty(bad: Any):
    """Structurally malformed payloads are left for the validator; salvage no-ops."""
    assert salvage_group_d_na(bad) == []


# ---------------------------------------------------------------------------
# parse_extract_result — Group-D salvage integration
# ---------------------------------------------------------------------------


def test_qatar_mcit_row_preserved_rather_than_dropped():
    """The named Qatar MCIT case: parse succeeds and the confirmed activity row
    survives instead of failing validation and dropping the whole page."""
    result = _make_result(make_custom_id("INST-QA-MCIT", _mcit_row()["source_url"]), _mcit_payload())
    sink: list[GroupDSalvage] = []

    parsed = parse_extract_result(result, scrape_access_date=MCIT_ACCESS_DATE, salvage_sink=sink)

    assert len(parsed.data) == 1
    row = parsed.data[0]
    assert row.has_genai_activity == "yes"
    assert row.genai_evidence == "confirms_activity"
    assert row.activity_name == "Lamma GenAI citizen assistant"
    # No _NA_ remains on the salvaged confirms_activity row.
    assert all(getattr(row, f) != "_NA_" for f in GROUP_D_FIELDS)


def test_qatar_mcit_salvage_is_recorded_and_distinguishable():
    """The salvaged row is marked schema-imperfect via the salvage record: it
    names exactly which fields were repaired, so an auditor can tell it apart
    from a row the model coded 'unknown' on its own."""
    result = _make_result(make_custom_id("INST-QA-MCIT", _mcit_row()["source_url"]), _mcit_payload())
    sink: list[GroupDSalvage] = []

    parse_extract_result(result, scrape_access_date=MCIT_ACCESS_DATE, salvage_sink=sink)

    assert len(sink) == 1
    ev = sink[0]
    assert ev.is_salvageable
    assert ev.row_id == 1
    # The repaired fields are exactly the _NA_ Group-D fields of the fixture.
    expected = {
        "adoption_stage", "tool_name", "deployment_mode", "year_deployed",
        "has_human_oversight", "has_transparency_notice", "has_data_classification",
        "has_risk_assessment", "reported_outcomes", "reported_incidents", "scope_notes",
    }
    assert set(ev.salvaged_fields) == expected


def test_salvage_leaves_non_group_d_na_to_hard_fail():
    """Targeted, not blanket: a confirms_activity row with salvageable Group-D
    _NA_ AND a bad non-Group-D field still fails — salvage repairs Group D but
    does not rescue the out-of-enum source_credibility."""
    result = _make_result(
        "INST-QA-MCIT::x", _mcit_payload({"source_credibility": "_NA_"})
    )
    sink: list[GroupDSalvage] = []
    with pytest.raises(ValidationError):
        parse_extract_result(result, scrape_access_date=MCIT_ACCESS_DATE, salvage_sink=sink)
    # Salvage still ran (and populated the sink) before validation raised.
    assert len(sink) == 1 and sink[0].is_salvageable


def test_na_in_non_group_d_required_field_alone_hard_fails():
    """A row whose ONLY problem is _NA_ in a non-Group-D field is not salvaged.

    Group D here is fully coded, so salvage has nothing to do; the illegal
    _NA_ on the Group-F ``confidence`` enum must still hard-fail.
    """
    row_ok_group_d = dict(_SALVAGEABLE_NA_ROW)  # every salvageable field -> a valid coded value
    result = _make_result(
        "INST-QA-MCIT::x", _mcit_payload({**row_ok_group_d, "confidence": "_NA_"})
    )
    with pytest.raises(ValidationError):
        parse_extract_result(result, scrape_access_date=MCIT_ACCESS_DATE)


def test_unsalvageable_activity_type_still_fails_parse():
    """activity_type _NA_ cannot be repaired, so the page still hard-fails —
    but the sink flags it unsalvageable so the caller can escalate distinctly."""
    result = _make_result("INST-QA-MCIT::x", _mcit_payload({"activity_type": "_NA_"}))
    sink: list[GroupDSalvage] = []
    with pytest.raises(ValidationError):
        parse_extract_result(result, scrape_access_date=MCIT_ACCESS_DATE, salvage_sink=sink)
    assert len(sink) == 1 and not sink[0].is_salvageable


def test_salvage_sink_optional():
    """Omitting the sink still salvages the payload and parses cleanly."""
    result = _make_result(make_custom_id("INST-QA-MCIT", _mcit_row()["source_url"]), _mcit_payload())
    parsed = parse_extract_result(result, scrape_access_date=MCIT_ACCESS_DATE)
    assert all(getattr(parsed.data[0], f) != "_NA_" for f in GROUP_D_FIELDS)


# ---------------------------------------------------------------------------
# _run_extract → _persist — attrition telemetry
# ---------------------------------------------------------------------------


def _write_master(path: Path) -> Path:
    fieldnames = [
        "master_row_id", "country", "government_level", "branch",
        "institution_type", "institution_name", "website",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerow({
            "master_row_id": "1", "country": "Qatar", "government_level": "national",
            "branch": "executive", "institution_type": "ministry",
            "institution_name": "Ministry of Communications and Information Technology",
            "website": "",
        })
    return path


def _make_page(url: str, text: str) -> RenderedPage:
    return RenderedPage(
        url=url, text=text, title="t", content_type="html",
        fetch_metadata=FetchMetadata(
            access_date=MCIT_ACCESS_DATE, http_status=200, final_url=url,
            fetch_method="html", elapsed_ms=1, wait_for=None,
        ),
    )


def _run_one_page_extract(tmp_path: Path, monkeypatch, payload: dict[str, Any], run_id: str) -> tuple[Path, str, str]:
    """Drive _run_extract for a single scraped page, feeding `payload` back
    through _persist via a faked chunked stage. Returns (run_dir, inst_id, url)."""
    master = _write_master(tmp_path / "m.csv")
    rows = list(csv.DictReader(open(master, encoding="utf-8")))
    inst_id = synth_institution_id(rows[0])
    run_dir = tmp_path / "runs" / run_id
    (run_dir / inst_id).mkdir(parents=True)

    url = "https://www.mcit.gov.qa/en/genai-assistant"
    page = _make_page(url, "GenAI citizen assistant announcement. " * 5)
    result = _make_result(make_custom_id(inst_id, url), payload)

    def _fake_chunked(rd, stage, jobs, **kw):
        kw["process_chunk_results"](iter([result]))

    monkeypatch.setattr(ps.stage_extract, "run_chunked_stage", _fake_chunked)

    ps._run_extract(
        run_dir, rows, {inst_id: [page]},
        institution_search_languages="en,ar", model="gpt-5-nano",
        poll_interval=0, max_wait=1, run_id=run_id,
    )
    return run_dir, inst_id, url


def test_salvage_writes_one_attrition_record_with_stable_code(tmp_path, monkeypatch):
    """Every salvage writes exactly one attrition record with the stable reason
    code, and the salvaged page is persisted (not dropped)."""
    run_dir, inst_id, url = _run_one_page_extract(tmp_path, monkeypatch, _mcit_payload(), "salv")

    recs = attrition.read_records(run_dir)
    salvaged = [r for r in recs if r["reason"] == REASON_SALVAGED]
    assert len(salvaged) == 1
    assert salvaged[0]["url"] == url
    assert salvaged[0]["stage"] == "extract"
    assert "year_deployed" in salvaged[0]["detail"]
    # The confirmed finding was preserved on disk for Stage 6.
    assert (run_dir / inst_id / "extract" / f"{url_hash(url)}.json").exists()


def test_unsalvageable_page_records_distinct_code_and_drops(tmp_path, monkeypatch):
    """A confirms_activity row with unsalvageable Group-D _NA_ still drops, but
    is tagged with its own reason code (not parse_failed)."""
    run_dir, inst_id, url = _run_one_page_extract(
        tmp_path, monkeypatch, _mcit_payload({"activity_type": "_NA_"}), "unsalv"
    )
    recs = attrition.read_records(run_dir)
    reasons = {r["reason"] for r in recs}
    assert REASON_UNSALVAGEABLE in reasons
    assert "parse_failed" not in reasons
    assert REASON_SALVAGED not in reasons
    # The page dropped — no extract artifact written.
    assert not (run_dir / inst_id / "extract" / f"{url_hash(url)}.json").exists()


def test_clean_page_records_no_salvage(tmp_path, monkeypatch):
    """A fully coded confirms_activity page writes no salvage record."""
    clean = _mcit_payload({
        "adoption_stage": "production", "tool_name": "Copilot",
        "deployment_mode": "integrated", "year_deployed": "2024",
        "has_human_oversight": "yes", "has_transparency_notice": "yes",
        "has_data_classification": "yes", "has_risk_assessment": "yes",
        "reported_outcomes": "none_reported", "reported_incidents": "none_reported",
        "scope_notes": "none",
    })
    run_dir, inst_id, url = _run_one_page_extract(tmp_path, monkeypatch, clean, "clean")
    recs = attrition.read_records(run_dir)
    assert not any(r["reason"] in (REASON_SALVAGED, REASON_UNSALVAGEABLE) for r in recs)
    assert (run_dir / inst_id / "extract" / f"{url_hash(url)}.json").exists()


# EMPTY_PAGE_MIN_CHARS is imported to keep the near-empty page in the helper
# comfortably above the Stage 5 empty-page floor without hard-coding the number.
assert len("GenAI citizen assistant announcement. " * 5) >= EMPTY_PAGE_MIN_CHARS
