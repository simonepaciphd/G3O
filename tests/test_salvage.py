"""Stage 5 / Stage 6 ``_NA_`` salvage (fix/stage5-groupd-salvage, fix/NA-issue).

Two data-loss bugs with the same shape: an illegal literal ``_NA_`` fails
validation, and because validation is atomic over the page (Stage 5) or the
institution (Stage 6), it takes the whole unit down with it.

1. **Group-D ``_NA_`` on positive findings** — the Qatar MCIT bug. A
   ``confirms_activity`` row whose Group-D activity fields carry ``_NA_``.
2. **``uncertainty_flags`` ``_NA_``** — ``INST-0000580`` /
   ``windowsforum.com`` in run ``digitalocean-010-dry``. Column 39 is Group F
   with its own closed vocabulary whose empty value is ``none``, but §3.2 tells
   the model to set "every field in Group D" to ``_NA_`` and never marks column
   39 as an exception, so a model generalising the rule writes ``_NA_`` here.

These tests pin the salvage behaviour that repairs both to the contract's own
prescribed values instead of dropping the unit, keeps each repair targeted, and
writes one stable-reason attrition record per affected unit.

Layers covered:
  • ``salvage_group_d_na`` unit behaviour (repair / skip / unsalvageable / malformed).
  • ``salvage_uncertainty_flags`` unit behaviour (repair / boundaries / malformed).
  • ``parse_extract_result`` integration (salvaged row survives; targeted; sink).
  • ``_run_extract`` → ``_persist`` telemetry (one ledger record, stable code).
  • ``parse_consolidate_result`` + ``run_consolidate`` → ``_persist`` at Stage 6.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from g3o.common import attrition
from g3o.common.batch_client import BatchResult
from g3o.common.contract import GROUP_D_FIELDS, NA, UNCERTAINTY_FLAG_VOCAB
from g3o.common.run_state import mark_done
from g3o.extract import make_custom_id, parse_extract_result, url_hash
from g3o.extract.batch import EMPTY_PAGE_MIN_CHARS
from g3o.extract.parser import SalvageEvent
from g3o.extract.salvage import (
    GROUP_D_SALVAGE_DEFAULTS,
    GROUP_D_UNSALVAGEABLE,
    REASON_FLAGS_EMPTY_SALVAGED,
    REASON_FLAGS_LIST_NORMALIZED,
    REASON_FLAGS_SALVAGED,
    REASON_SALVAGED,
    REASON_UNSALVAGEABLE,
    UNCERTAINTY_FLAGS_EMPTY,
    GroupDSalvage,
    UncertaintyFlagsSalvage,
    repair_uncertainty_flags,
    salvage_group_d_na,
    salvage_uncertainty_flags,
)
from g3o.run import presweep as ps
from g3o.run.presweep import synth_institution_id
from g3o.run.presweep.stage_extract import _is_unsalvageable_group_d_failure
from g3o.scrape.render import FetchMetadata, RenderedPage
from g3o.validate import consolidate as vc
from g3o.validate.consolidate import parse_consolidate_result

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


# ---------------------------------------------------------------------------
# Reason attribution — the unsalvageable code must reflect the actual cause,
# not merely the presence of an unsalvageable salvage event.
# ---------------------------------------------------------------------------


def _capture_exc(payload: dict[str, Any]) -> Exception:
    sink: list[GroupDSalvage] = []
    try:
        parse_extract_result(
            _make_result("INST-QA-MCIT::x", payload),
            scrape_access_date=MCIT_ACCESS_DATE,
            salvage_sink=sink,
        )
    except Exception as exc:  # noqa: BLE001 — capturing for attribution assertions
        return exc
    raise AssertionError("expected parse_extract_result to raise")


def test_unsalvageable_attribution_true_on_group_d_validation_error():
    """A ValidationError caused by the unsalvageable Group-D field is attributed
    to the unsalvageable code."""
    exc = _capture_exc(_mcit_payload({"activity_type": "_NA_"}))
    event = GroupDSalvage(
        row_id=1, source_url="u", unsalvageable_fields=("activity_type",)
    )
    assert _is_unsalvageable_group_d_failure(exc, [event]) is True


def test_unsalvageable_attribution_false_on_unrelated_runtime_error():
    """An unrelated failure (e.g. an access-date mismatch, a RuntimeError with no
    .errors()) stays parse_failed even when an unsalvageable event coexists."""
    event = GroupDSalvage(
        row_id=1, source_url="u", unsalvageable_fields=("activity_type",)
    )
    exc = RuntimeError("Stage 5 access-date mismatch")
    assert _is_unsalvageable_group_d_failure(exc, [event]) is False


def test_unsalvageable_attribution_false_on_unrelated_validation_error():
    """A ValidationError about a different field (bad access-date pattern) is not
    attributed to the unsalvageable code just because an unsalvageable event is
    present in the sink."""
    exc = _capture_exc(_mcit_payload({"source_access_date": "not-a-date"}))
    event = GroupDSalvage(
        row_id=1, source_url="u", unsalvageable_fields=("activity_type",)
    )
    assert _is_unsalvageable_group_d_failure(exc, [event]) is False


# ---------------------------------------------------------------------------
# uncertainty_flags _NA_ — fixtures
# ---------------------------------------------------------------------------

# The real failing case, run digitalocean-010-dry / INST-0000580. Reconstructed
# from the run's attrition ledger, which preserves the source URL, the row_id and
# the offending value but truncates the rest of the payload — so the coded values
# below are representative rather than byte-identical. What matters is reproduced
# exactly: uncertainty_flags is the whole-value literal `_NA_` and is the row's
# *only* contract violation, so this payload hard-failed before the repair.
WINDOWSFORUM_URL = (
    "https://windowsforum.com/threads/"
    "qatars-mcit-launches-training-on-microsoft-copilot-for-government-efficiency.351450/"
)


def _absence_row(**overrides: Any) -> dict[str, Any]:
    """A negative-evidence row: has_genai_activity=no, every Group-D field _NA_.

    This is the shape the bug report identifies as the common case — most rows in
    a real run are negative evidence, and it is precisely the row where §3.2's
    "set every field in Group D to _NA_" instruction is active and therefore most
    likely to be over-generalised onto column 39.
    """
    base: dict[str, Any] = {
        **_mcit_row(),
        "has_genai_activity": "no",
        "institution_summary": "Supplied pages reviewed; no GenAI evidence found.",
        "genai_evidence": "confirms_absence",
        "source_snippet": "The supplied page text contains no mention of generative AI.",
        **{f: NA for f in GROUP_D_FIELDS},
    }
    base.update(overrides)
    return base


def _absence_payload(row_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "batch_metadata": _mcit_meta(n_institutions_with_genai=0),
        "data": [_absence_row(**(row_overrides or {}))],
    }


# ---------------------------------------------------------------------------
# salvage_uncertainty_flags — unit behaviour
# ---------------------------------------------------------------------------


def test_flags_salvage_module_invariants_hold():
    """The repair only makes sense while `_NA_` is illegal and `none` is not a
    flag. Both are asserted at import time in salvage.py; pin them here too so a
    vocabulary edit fails a test rather than only breaking an import."""
    assert NA not in UNCERTAINTY_FLAG_VOCAB
    assert UNCERTAINTY_FLAGS_EMPTY not in UNCERTAINTY_FLAG_VOCAB
    assert UNCERTAINTY_FLAGS_EMPTY == "none"


def test_flags_salvage_rewrites_na_to_none():
    rows = [{"row_id": 1, "source_url": "u", "uncertainty_flags": NA}]
    events = salvage_uncertainty_flags(rows)
    assert rows[0]["uncertainty_flags"] == "none"
    assert len(events) == 1
    assert events[0].row_id == 1
    assert events[0].source_url == "u"


@pytest.mark.parametrize(
    "evidence",
    ["confirms_activity", "confirms_absence", "ambiguous", "background_only"],
)
def test_flags_salvage_is_evidence_agnostic(evidence: str):
    """Unlike Group-D salvage, this repair does not condition on genai_evidence:
    `none` is the field's only legal empty value in every branch of the contract,
    so the substitution is faithful on a positive row too."""
    rows = [{"row_id": 1, "genai_evidence": evidence, "uncertainty_flags": NA}]
    assert len(salvage_uncertainty_flags(rows)) == 1
    assert rows[0]["uncertainty_flags"] == "none"


@pytest.mark.parametrize(
    "value",
    ["none", "stage_ambiguous", "stage_ambiguous;vendor_undisclosed"],
)
def test_flags_salvage_leaves_legal_values_untouched(value: str):
    rows = [{"row_id": 1, "uncertainty_flags": value}]
    assert salvage_uncertainty_flags(rows) == []
    assert rows[0]["uncertainty_flags"] == value


@pytest.mark.parametrize(
    "value",
    [
        "NA",                   # the bug report's transcription; never a legal token
        "n/a",
        "_na_",                 # case matters
        "bogus_flag",
        "stage ambiguous",      # a space *inside* a token, not around a separator
        "stage_ambiguous;bogus_flag",
        "stage_ambiguous;NA",   # a real flag plus an unrecognised token
    ],
)
def test_flags_salvage_refuses_values_holding_an_unrecognised_token(value: str):
    """The repair/relaxation line. We normalise values whose meaning the contract
    already fixes; we refuse to guess at a token the contract does not define, so
    genuine model drift still hard-fails loudly instead of being quietly rewritten.
    """
    rows = [{"row_id": 1, "uncertainty_flags": value}]
    assert salvage_uncertainty_flags(rows) == []
    assert rows[0]["uncertainty_flags"] == value


@pytest.mark.parametrize(
    ("value", "expected", "kind"),
    [
        (NA, "none", "na"),
        ("", "none", "empty"),
        ("   ", "none", "empty"),
        (" _NA_ ", "none", "list"),
        ("_NA_;_NA_", "none", "list"),
        ("none;none", "none", "list"),
        ("stage_ambiguous;_NA_", "stage_ambiguous", "list"),
        ("genai_vs_traditional_ai;none", "genai_vs_traditional_ai", "list"),
        ("genai_vs_traditional_ai; date_uncertain",
         "genai_vs_traditional_ai;date_uncertain", "list"),
        ("stage_ambiguous;", "stage_ambiguous", "list"),
    ],
)
def test_flags_salvage_repairs_every_observed_shape(
    value: str, expected: str, kind: str
):
    """Every `uncertainty_flags` failure shape seen in the n=100 run, plus the
    near neighbours of each. `_NA_` was the minority shape (18 records against 27
    for a bare empty string) — see the module docstring in salvage.py."""
    rows = [{"row_id": 1, "uncertainty_flags": value}]
    events = salvage_uncertainty_flags(rows)
    assert rows[0]["uncertainty_flags"] == expected
    assert len(events) == 1
    assert events[0].kind == kind
    assert events[0].original == value
    assert events[0].repaired == expected


def test_flags_salvage_reason_code_differs_per_shape():
    """Each shape gets its own ledger code so the shapes stay countable — in
    particular, inferring `none` from an empty string is a weaker inference than
    the `_NA_` synonym rewrite and must be auditable separately."""
    codes = {
        k: UncertaintyFlagsSalvage(kind=k).reason
        for k in ("na", "empty", "list")
    }
    assert codes == {
        "na": REASON_FLAGS_SALVAGED,
        "empty": REASON_FLAGS_EMPTY_SALVAGED,
        "list": REASON_FLAGS_LIST_NORMALIZED,
    }
    assert len(set(codes.values())) == 3


def test_flags_salvage_preserves_flag_order():
    """The contract asks Stage 6 to order flags alphabetically but the validator
    does not enforce it, so reordering would be normalisation beyond repair."""
    rows = [{"row_id": 1, "uncertainty_flags": "vendor_undisclosed;date_uncertain;none"}]
    assert len(salvage_uncertainty_flags(rows)) == 1
    assert rows[0]["uncertainty_flags"] == "vendor_undisclosed;date_uncertain"


def test_repair_uncertainty_flags_is_pure():
    """The row-writing and the decision are separable: repair_uncertainty_flags
    mutates nothing and returns None for "leave alone"."""
    assert repair_uncertainty_flags("none") is None
    assert repair_uncertainty_flags("stage_ambiguous") is None
    assert repair_uncertainty_flags("bogus") is None
    assert repair_uncertainty_flags(None) is None
    assert repair_uncertainty_flags(7) is None
    assert repair_uncertainty_flags(NA) == ("none", "na")


@pytest.mark.parametrize(
    "bad", [None, {}, "data", 7, [None], ["row"], [7], {"data": []}]
)
def test_flags_salvage_malformed_input_returns_empty(bad: Any):
    """Structurally malformed input is left for the validator; salvage no-ops."""
    assert salvage_uncertainty_flags(bad) == []


def test_flags_salvage_repairs_every_affected_row():
    rows = [
        {"row_id": 1, "uncertainty_flags": NA},
        {"row_id": 2, "uncertainty_flags": "stage_ambiguous"},
        {"row_id": 3, "uncertainty_flags": NA},
    ]
    events = salvage_uncertainty_flags(rows)
    assert [e.row_id for e in events] == [1, 3]
    assert [r["uncertainty_flags"] for r in rows] == [
        "none", "stage_ambiguous", "none",
    ]


def test_flags_salvage_ref_prefers_row_id_then_activity_id():
    """Stage 5 rows carry row_id; Stage 6 activities carry activity_id instead.
    The ledger `detail` uses whichever identity the row actually has."""
    assert UncertaintyFlagsSalvage(row_id=4).ref == "row_id=4"
    assert UncertaintyFlagsSalvage(activity_id="A2").ref == "activity_id=A2"
    assert UncertaintyFlagsSalvage().ref == "row_ref=?"


def test_flags_salvage_captures_activity_id_at_stage_6_shape():
    rows = [{"activity_id": "A1", "uncertainty_flags": NA}]
    events = salvage_uncertainty_flags(rows)
    assert events[0].activity_id == "A1"
    assert events[0].row_id is None
    assert events[0].source_url == ""


# ---------------------------------------------------------------------------
# parse_extract_result — uncertainty_flags salvage integration (Stage 5)
# ---------------------------------------------------------------------------


def test_windowsforum_row_preserved_rather_than_dropped():
    """The named INST-0000580 case: the page parses instead of failing validation
    and dropping the institution to PROCESSING_FAILED."""
    payload = _mcit_payload(
        {
            **_SALVAGEABLE_NA_ROW,          # Group D fully coded — flags are the sole defect
            "source_url": WINDOWSFORUM_URL,
            "source_type": "news_trade",
            "source_credibility": "medium",
            "confidence": "low",
            "uncertainty_flags": NA,
        }
    )
    result = _make_result(make_custom_id("INST-0000580", WINDOWSFORUM_URL), payload)
    sink: list[SalvageEvent] = []

    parsed = parse_extract_result(
        result, scrape_access_date=MCIT_ACCESS_DATE, salvage_sink=sink
    )

    assert len(parsed.data) == 1
    assert parsed.data[0].uncertainty_flags == "none"
    assert len(sink) == 1
    assert isinstance(sink[0], UncertaintyFlagsSalvage)
    assert sink[0].source_url == WINDOWSFORUM_URL


def test_windowsforum_payload_would_have_failed_without_the_repair():
    """Guards the regression test above against becoming vacuous: the same payload
    is still rejected when validated directly, so the parse above is passing
    because of the repair, not because the payload was legal all along."""
    from g3o.common.contract import BatchResponse

    payload = _mcit_payload(
        {**_SALVAGEABLE_NA_ROW, "uncertainty_flags": NA}
    )
    with pytest.raises(ValidationError, match="unknown uncertainty flag"):
        BatchResponse.model_validate(payload)


def test_flags_na_on_negative_evidence_row_parses():
    """The bug report's common case: a confirms_absence row where Group D is
    legitimately all _NA_ and the model carried _NA_ onto column 39 too."""
    result = _make_result(
        make_custom_id("INST-0000580", WINDOWSFORUM_URL),
        _absence_payload({"uncertainty_flags": NA}),
    )
    sink: list[SalvageEvent] = []

    parsed = parse_extract_result(
        result, scrape_access_date=MCIT_ACCESS_DATE, salvage_sink=sink
    )

    row = parsed.data[0]
    assert row.genai_evidence == "confirms_absence"
    assert row.uncertainty_flags == "none"
    # Group D is untouched: still legitimately _NA_ on a negative-evidence row.
    assert all(getattr(row, f) == NA for f in GROUP_D_FIELDS)
    assert len(sink) == 1 and isinstance(sink[0], UncertaintyFlagsSalvage)


def test_negative_evidence_row_without_flags_na_needs_no_salvage():
    """Control for the test above — the same row with `none` parses and salvages
    nothing, so the repair is not silently firing on every negative row."""
    result = _make_result("INST-0000580::x", _absence_payload())
    sink: list[SalvageEvent] = []
    parsed = parse_extract_result(
        result, scrape_access_date=MCIT_ACCESS_DATE, salvage_sink=sink
    )
    assert parsed.data[0].uncertainty_flags == "none"
    assert sink == []


def test_both_salvages_compose_on_one_row():
    """A confirms_activity row with Group-D _NA_ *and* uncertainty_flags _NA_ is
    fully repaired, and the sink reports both events without either clobbering
    the other."""
    result = _make_result(
        "INST-QA-MCIT::x", _mcit_payload({"uncertainty_flags": NA})
    )
    sink: list[SalvageEvent] = []

    parsed = parse_extract_result(
        result, scrape_access_date=MCIT_ACCESS_DATE, salvage_sink=sink
    )

    row = parsed.data[0]
    assert row.uncertainty_flags == "none"
    assert all(getattr(row, f) != NA for f in GROUP_D_FIELDS)
    assert len(sink) == 2
    assert {type(e) for e in sink} == {GroupDSalvage, UncertaintyFlagsSalvage}


@pytest.mark.parametrize("value", ["NA", "stage_ambiguous;bogus", "bogus_flag"])
def test_flags_drift_other_than_the_sentinel_still_hard_fails(value: str):
    """Repair, not relaxation: the vocabulary check still bites on anything that
    is not the exact documented sentinel."""
    result = _make_result("INST-QA-MCIT::x", _mcit_payload({"uncertainty_flags": value}))
    with pytest.raises(ValidationError, match="uncertainty_flags|uncertainty flag"):
        parse_extract_result(result, scrape_access_date=MCIT_ACCESS_DATE)


def test_flags_salvage_populates_sink_even_when_validation_raises():
    """Salvage runs before validation, so the caller can still see what was
    repaired on a page that failed for an unrelated reason."""
    result = _make_result(
        "INST-QA-MCIT::x",
        _mcit_payload(
            {**_SALVAGEABLE_NA_ROW, "uncertainty_flags": NA, "source_credibility": "_NA_"}
        ),
    )
    sink: list[SalvageEvent] = []
    with pytest.raises(ValidationError):
        parse_extract_result(
            result, scrape_access_date=MCIT_ACCESS_DATE, salvage_sink=sink
        )
    assert len(sink) == 1 and isinstance(sink[0], UncertaintyFlagsSalvage)


# ---------------------------------------------------------------------------
# _run_extract → _persist — uncertainty_flags telemetry (Stage 5)
# ---------------------------------------------------------------------------


def test_flags_salvage_writes_one_attrition_record_with_stable_code(tmp_path, monkeypatch):
    """One ledger record with the stable reason code, and the page is persisted."""
    payload = _mcit_payload({**_SALVAGEABLE_NA_ROW, "uncertainty_flags": NA})
    run_dir, inst_id, url = _run_one_page_extract(tmp_path, monkeypatch, payload, "flags")

    recs = attrition.read_records(run_dir)
    salvaged = [r for r in recs if r["reason"] == REASON_FLAGS_SALVAGED]
    assert len(salvaged) == 1
    assert salvaged[0]["url"] == url
    assert salvaged[0]["stage"] == "extract"
    assert "rows=[1]" in salvaged[0]["detail"]
    # No Group-D record: Group D was fully coded on this page.
    assert not any(r["reason"] == REASON_SALVAGED for r in recs)
    assert (run_dir / inst_id / "extract" / f"{url_hash(url)}.json").exists()


def test_both_salvage_codes_recorded_when_both_fired(tmp_path, monkeypatch):
    """The two repairs are reported independently, not merged into one record."""
    run_dir, _inst_id, _url = _run_one_page_extract(
        tmp_path, monkeypatch, _mcit_payload({"uncertainty_flags": NA}), "both"
    )
    reasons = {r["reason"] for r in attrition.read_records(run_dir)}
    assert REASON_SALVAGED in reasons
    assert REASON_FLAGS_SALVAGED in reasons
    assert "parse_failed" not in reasons


@pytest.mark.parametrize(
    ("value", "reason_name"),
    [
        ("", "REASON_FLAGS_EMPTY_SALVAGED"),
        ("genai_vs_traditional_ai;none", "REASON_FLAGS_LIST_NORMALIZED"),
        ("genai_vs_traditional_ai; date_uncertain", "REASON_FLAGS_LIST_NORMALIZED"),
    ],
)
def test_widened_shapes_reach_the_ledger_under_their_own_code(
    tmp_path, monkeypatch, value: str, reason_name: str
):
    """The three shapes the original repair declined — the empty string (the most
    common one in the n=100 run), `none` appended to real flags, and a space after
    a separator — now parse, and each lands in the ledger under its own code."""
    expected = {
        "REASON_FLAGS_EMPTY_SALVAGED": REASON_FLAGS_EMPTY_SALVAGED,
        "REASON_FLAGS_LIST_NORMALIZED": REASON_FLAGS_LIST_NORMALIZED,
    }[reason_name]
    payload = _mcit_payload({**_SALVAGEABLE_NA_ROW, "uncertainty_flags": value})
    run_dir, inst_id, url = _run_one_page_extract(
        tmp_path, monkeypatch, payload, f"widened{abs(hash(value)) % 997}"
    )
    recs = attrition.read_records(run_dir)
    hits = [r for r in recs if r["reason"] == expected]
    assert len(hits) == 1, [r["reason"] for r in recs]
    assert hits[0]["url"] == url
    assert "rows=[1]" in hits[0]["detail"]
    assert "parse_failed" not in {r["reason"] for r in recs}
    assert (run_dir / inst_id / "extract" / f"{url_hash(url)}.json").exists()


@pytest.mark.parametrize(
    "value", ["", "genai_vs_traditional_ai;none", "genai_vs_traditional_ai; x"]
)
def test_widened_shapes_would_have_failed_without_the_repair(value: str):
    """Keeps the test above honest: the same payloads still raise when validated
    directly, so the parse succeeds because of the repair and not because the
    validator was weakened. (`; x` carries an unrecognised token and must raise in
    both places — the refusal boundary, checked in the same breath.)"""
    from g3o.common.contract import BatchResponse

    payload = _mcit_payload({**_SALVAGEABLE_NA_ROW, "uncertainty_flags": value})
    with pytest.raises(ValidationError, match="uncertainty_flags|uncertainty flag"):
        BatchResponse.model_validate(payload)


def test_stage6_widened_shape_preserved(tmp_path, monkeypatch):
    """Stage 6 gets the widened repair too: an empty-string `uncertainty_flags` on
    one activity no longer drops the whole institution's consolidation."""
    events = salvage_uncertainty_flags([{"activity_id": "A1", "uncertainty_flags": ""}])
    assert len(events) == 1
    assert events[0].reason == REASON_FLAGS_EMPTY_SALVAGED
    assert events[0].activity_id == "A1"


def test_clean_page_records_no_flags_salvage(tmp_path, monkeypatch):
    payload = _mcit_payload({**_SALVAGEABLE_NA_ROW})
    run_dir, _inst_id, _url = _run_one_page_extract(
        tmp_path, monkeypatch, payload, "flagsclean"
    )
    reasons = {r["reason"] for r in attrition.read_records(run_dir)}
    assert REASON_FLAGS_SALVAGED not in reasons


def test_unrelated_failure_records_parse_failed_not_flags_salvaged(tmp_path, monkeypatch):
    """A page whose flags were repaired but which still dropped for another reason
    is reported by its actual failure, not as a salvage that did not save it."""
    payload = _mcit_payload(
        {**_SALVAGEABLE_NA_ROW, "uncertainty_flags": NA, "source_credibility": "_NA_"}
    )
    run_dir, inst_id, url = _run_one_page_extract(
        tmp_path, monkeypatch, payload, "flagsfail"
    )
    reasons = {r["reason"] for r in attrition.read_records(run_dir)}
    assert "parse_failed" in reasons
    assert REASON_FLAGS_SALVAGED not in reasons
    assert not (run_dir / inst_id / "extract" / f"{url_hash(url)}.json").exists()


# ---------------------------------------------------------------------------
# Stage 6 — the same _NA_ in a consolidated activity
# ---------------------------------------------------------------------------


def _consolidated_payload(
    institution_id: str, activity_overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    """A minimal valid Stage 6 response for one institution with one activity."""
    activity: dict[str, Any] = {
        "activity_id": "A1",
        "activity_name": "Microsoft Copilot adoption programme",
        "activity_type": "internal_operational",
        "adoption_stage": "production",
        "access_type": "proprietary_vendor",
        "interaction_type": "document_processing",
        "tool_name": "Microsoft 365 Copilot",
        "vendor": "Microsoft",
        "deployment_mode": "integrated",
        "target_users": "internal_staff",
        "year_announced": "2024",
        "year_deployed": "2024",
        "has_human_oversight": "not_documented",
        "has_transparency_notice": "not_documented",
        "has_data_classification": "not_documented",
        "has_risk_assessment": "not_documented",
        "reported_outcomes": "none_reported",
        "reported_incidents": "none_reported",
        "scope_notes": "none",
        "n_sources": 1,
        "confidence": "medium",
        "uncertainty_flags": "none",
    }
    activity.update(activity_overrides or {})
    return {
        "consolidation_metadata": {
            "institution_id": institution_id,
            "n_input_pages": 1,
            "n_input_rows": 1,
            "response_timestamp": "2026-06-10T12:00:00Z",
            "model_label": "gpt-5-nano",
            "notes": "none",
        },
        "institution": {
            "institution_id": institution_id,
            "institution_name": "Ministry of Communications and Information Technology",
            "country": "Qatar",
            "branch_of_government": "executive",
            "level_of_government": "national",
            "has_genai_activity": "yes",
            "institution_summary": "MCIT runs a Copilot adoption programme.",
            "institution_search_languages": "en,ar",
        },
        "activities": [activity],
        "sources": [
            {
                "source_id": "S1",
                "activity_id": "A1",
                "source_url": "https://www.mcit.gov.qa/en/genai-assistant",
                "source_title": "MCIT Copilot adoption programme",
                "source_publication_date": "2024-05",
                "source_access_date": MCIT_ACCESS_DATE,
                "source_type": "official_gov",
                "source_language": "en",
                "source_credibility": "high",
                "genai_evidence": "confirms_activity",
                "source_snippet": "MCIT announced a Copilot adoption programme.",
            }
        ],
    }


def test_stage6_flags_na_activity_preserved_rather_than_dropped():
    """ConsolidatedActivity carries byte-identical uncertainty_flags validation,
    and model_validate is atomic over the institution — so without the repair one
    activity's `_NA_` drops the entire consolidation."""
    payload = _consolidated_payload("INST-0000580", {"uncertainty_flags": NA})
    result = _make_result("INST-0000580", payload)
    sink: list[UncertaintyFlagsSalvage] = []

    response = parse_consolidate_result(result, salvage_sink=sink)

    assert response.activities[0].uncertainty_flags == "none"
    assert len(sink) == 1
    assert sink[0].activity_id == "A1"
    assert sink[0].ref == "activity_id=A1"


def test_stage6_payload_would_have_failed_without_the_repair():
    """Keeps the Stage 6 regression test non-vacuous."""
    from g3o.common.contract import ConsolidatedInstitutionResponse

    payload = _consolidated_payload("INST-0000580", {"uncertainty_flags": NA})
    with pytest.raises(ValidationError, match="unknown uncertainty flag"):
        ConsolidatedInstitutionResponse.model_validate(payload)


def test_stage6_clean_payload_salvages_nothing():
    result = _make_result("INST-0000580", _consolidated_payload("INST-0000580"))
    sink: list[UncertaintyFlagsSalvage] = []
    parse_consolidate_result(result, salvage_sink=sink)
    assert sink == []


def test_stage6_sink_optional():
    result = _make_result(
        "INST-0000580", _consolidated_payload("INST-0000580", {"uncertainty_flags": NA})
    )
    assert parse_consolidate_result(result).activities[0].uncertainty_flags == "none"


def test_stage6_flags_salvage_writes_attrition_record(tmp_path, monkeypatch):
    """End-to-end through run_consolidate's _persist: the ledger records the
    repair and the consolidation is written rather than dropped."""
    run_id = "stage6flags"
    inst_id = "INST-0000580"
    run_dir = tmp_path / "runs" / run_id
    inst_dir = run_dir / inst_id
    (inst_dir / "extract").mkdir(parents=True)
    # Stage 6 assembles its input from institution.json + Stage 5 extract outputs.
    (inst_dir / "institution.json").write_text(
        json.dumps(
            {
                "institution_id": inst_id,
                "institution_name": "Ministry of Communications and Information Technology",
                "country": "Qatar",
                "branch_of_government": "executive",
                "level_of_government": "national",
            }
        ),
        encoding="utf-8",
    )
    (inst_dir / "extract" / "page.json").write_text(
        json.dumps(_mcit_payload({**_SALVAGEABLE_NA_ROW})), encoding="utf-8"
    )

    result = _make_result(
        inst_id, _consolidated_payload(inst_id, {"uncertainty_flags": NA})
    )

    def _fake_chunked(rd, stage, jobs, **kw):
        kw["process_chunk_results"](iter([result]))
        mark_done(rd, stage, no_batch=True)

    monkeypatch.setattr(vc, "run_chunked_stage", _fake_chunked)

    summary = vc.run_consolidate(
        run_dir, institution_ids=[inst_id], model="gpt-5-nano",
        poll_interval=0, max_wait=1,
    )

    assert summary["n_failed"] == 0
    salvaged = [
        r for r in attrition.read_records(run_dir)
        if r["reason"] == REASON_FLAGS_SALVAGED
    ]
    assert len(salvaged) == 1
    assert salvaged[0]["stage"] == "validate"
    assert "activity_id=A1" in salvaged[0]["detail"]
    assert (inst_dir / "6_validate.json").exists()


# ---------------------------------------------------------------------------
# The prompt-side fix (Output Contract v2.2, carried forward to v2.3)
#
# The salvage above is defence in depth; the contract carve-out is the primary
# fix, and until these tests existed it had no coverage at all — the version pin
# detects that the contract *changed* but cannot require that the carve-out is
# still in it. The phrases asserted below are the load-bearing claims; if a
# rewording trips one of these, re-point the test deliberately rather than
# deleting it.
# ---------------------------------------------------------------------------


def _normalised_contract() -> str:
    from g3o.extract.client import OUTPUT_CONTRACT_TEXT

    return re.sub(r"\s+", " ", OUTPUT_CONTRACT_TEXT).lower()


def test_contract_states_uncertainty_flags_is_not_group_d():
    """§3.2 — the rule the model over-generalised now names its own exception."""
    text = _normalised_contract()
    assert "`uncertainty_flags` (column 39) is not a group d field" in text
    assert '"every field in group d" means columns 11-28 and nothing else' in text


def test_contract_forbids_na_in_the_uncertainty_flags_vocabulary_section():
    """§4.10 — stated again where the model actually fills the field, since a
    reader who jumps straight to the vocabulary would otherwise miss §3.2."""
    text = _normalised_contract()
    assert "do not emit `_na_` here" in text


def test_contract_consistency_check_covers_columns_outside_group_d():
    """§6 — the self-validation checklist the model runs before submitting."""
    text = _normalised_contract()
    assert "no column outside 11-28 may ever be `_na_`" in text


def test_worked_example_shows_uncertainty_flags_none_on_an_absence_row():
    """§7 Edge case A — the negative-evidence example now makes the contrast
    visible: Group D all `_NA_`, uncertainty_flags `none`, on the same row."""
    from g3o.extract.client import OUTPUT_CONTRACT_TEXT

    # The Edge case A table rows, which are the ones a model pattern-matches on.
    absence_rows = [
        line for line in OUTPUT_CONTRACT_TEXT.splitlines()
        if "nationalassembly.gov.bz" in line
    ]
    assert absence_rows, "Edge case A absence rows not found"
    for line in absence_rows:
        cells = [c.strip() for c in line.split("|")]
        assert "confirms_absence" in cells
        assert NA in cells                      # Group D still blanked
        assert UNCERTAINTY_FLAGS_EMPTY in cells  # ...but flags are `none`


def test_system_message_version_header_matches_the_contract_h1():
    """The SYSTEM_MESSAGE header hardcodes the contract version separately from
    the document's own H1 (client.py), so the two can silently drift — they did,
    and the v2.2/v2.3 bumps had to fix both by hand. Pin them together."""
    from g3o.extract.client import OUTPUT_CONTRACT_TEXT, SYSTEM_MESSAGE

    h1 = OUTPUT_CONTRACT_TEXT.splitlines()[0]
    m = re.search(r"\bv(\d+(?:\.\d+)*)\b", h1)
    assert m, f"no version token in the contract H1: {h1!r}"
    version = f"v{m.group(1)}"
    assert f"# G3O Output Contract {version} (canonical reference)" in SYSTEM_MESSAGE, (
        f"the contract H1 says {version} but SYSTEM_MESSAGE in g3o/extract/client.py "
        "announces a different version to the model"
    )


# EMPTY_PAGE_MIN_CHARS is imported to keep the near-empty page in the helper
# comfortably above the Stage 5 empty-page floor without hard-coding the number.
assert len("GenAI citizen assistant announcement. " * 5) >= EMPTY_PAGE_MIN_CHARS
