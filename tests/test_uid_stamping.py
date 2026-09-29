"""`institution_uid` / `sweep_uid` stamping — PI ruling 2026-08-14.

Every assertion here checks a value, not a header. That is the whole design of
this module, and it is not defensiveness: two of the four stamped surfaces have
no structural guard behind them.

- ``PersistedActivity.to_csv_dict`` merges ``institution.model_dump()``, so a
  uid modelled as an optional field on ``ConsolidatedInstitution`` would sit in
  the merged dict as ``None``, satisfy the ``missing`` guard, and ship an empty
  column with no error. It is modelled on ``ValidationProvenance`` as a
  *required* field instead, which is what makes the omission raise.
- ``institution_report.py:70`` is ``{col: r.get(col) for col in
  INSTITUTION_REPORT_COLUMNS}`` — a column the records never carry writes an
  empty cell and returns clean. Nothing but a value assertion catches that.

``extrasaction="raise"`` does not close either hole: it catches *extra* keys,
not missing ones, and a missing key takes ``DictWriter``'s restval silently.

The failure being prevented is measured, not hypothetical: Katon's replay of
``20260802-e2e-100`` quarantined 40 fact rows as ``missing_institution_uid``,
and a run that stamps empty strings quarantines exactly the same way while
looking green from inside the pipeline.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from g3o.common.contract import (
    INSTITUTION_UID_PATTERN,
    SWEEP_UID_PATTERN,
    ValidationProvenance,
)
from g3o.common.institution_report import write_institution_report
from g3o.common.paths import institution_uid_map
from g3o.common.schema import (
    ACTIVITY_COLUMNS,
    ACTIVITY_SOURCE_COLUMNS,
    INSTITUTION_REPORT_COLUMNS,
    SUMMARY_COLUMNS,
)
from g3o.persist.writer import sweep_uid_for, write_run_csvs
from g3o.run.presweep.config import PresweepConfig
from g3o.run.presweep.planning import build_manifest
from g3o.run.presweep.records import institution_record
from tests._layout import uid_for, write_manifest
from tests.test_outcomes import _make_run
from tests.test_persist import (
    _no_response,
    _read_csv,
    _stage_run_dir,
    _yes_response,
)

_INST_A = "INST-0001"
_INST_B = "INST-0002"
_UID_A = uid_for(_INST_A)
_UID_B = uid_for(_INST_B)


def _run_with_both(tmp_path: Path) -> Path:
    return _stage_run_dir(
        tmp_path, {_INST_A: _yes_response(), _INST_B: _no_response()}
    )


# ---------------------------------------------------------------------------
# The derivation
# ---------------------------------------------------------------------------


def test_sweep_uid_is_the_uid_tail_under_a_new_prefix() -> None:
    assert sweep_uid_for("G3O-I-00000001") == "G3O-S-00000001"
    assert sweep_uid_for("G3O-I-00719588") == "G3O-S-00719588"


def test_sweep_uid_is_stable_across_runs() -> None:
    """No counter, no wave, no run_id in the string: re-running an institution
    yields the same sweep_uid and a different ``(sweep_uid, run_id)`` pair,
    which is the composite key the loader upserts on."""
    assert sweep_uid_for(_UID_A) == sweep_uid_for(_UID_A)


@pytest.mark.parametrize(
    "bad", ["", "G3O-S-00000001", "G3O-I-1", "G3O-I-000000001", "00000001", "g3o-i-00000001"]
)
def test_sweep_uid_refuses_a_malformed_institution_uid(bad: str) -> None:
    """The 8-digit tail is the whole derivation, so a malformed input has no
    defensible output — and minting one anyway is how a row claims the wrong
    institution with nothing downstream able to catch it."""
    with pytest.raises(ValueError, match="cannot derive a sweep_uid"):
        sweep_uid_for(bad)


# ---------------------------------------------------------------------------
# The structural guard: required, not defaulted
# ---------------------------------------------------------------------------


def _provenance_kwargs(**overrides: str) -> dict[str, str]:
    base = {
        "global_row_id": "R1::INST-0001::A1",
        "run_id": "R1",
        "run_model": "gpt-5-nano",
        "run_tool": "g3o.persist.writer",
        "run_date": "2026-08-14",
        "institution_uid": _UID_A,
        "sweep_uid": sweep_uid_for(_UID_A),
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("field", ["institution_uid", "sweep_uid"])
def test_provenance_refuses_a_missing_uid(field: str) -> None:
    """A default here would be the silent-empty-column bug: the key would be
    present in every merged dict and every ``missing`` guard would pass."""
    kwargs = _provenance_kwargs()
    del kwargs[field]
    with pytest.raises(ValidationError):
        ValidationProvenance(**kwargs)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("institution_uid", ""),
        ("institution_uid", "G3O-S-00000001"),
        ("sweep_uid", ""),
        ("sweep_uid", "G3O-I-00000001"),
        ("sweep_uid", "G3O-S-w001-00000001"),  # the retired wave-slot format
    ],
)
def test_provenance_refuses_a_malformed_uid(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        ValidationProvenance(**_provenance_kwargs(**{field: value}))


# ---------------------------------------------------------------------------
# The four stamped surfaces — values, not headers
# ---------------------------------------------------------------------------


def test_activity_rows_carry_both_uids(tmp_path: Path) -> None:
    run_dir = _run_with_both(tmp_path)
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")
    fields, rows = _read_csv(run_dir / "final" / "g3o_activities_v1.csv")

    assert fields == ACTIVITY_COLUMNS
    assert rows, "fixture must produce at least one activity row"
    for r in rows:
        assert re.match(INSTITUTION_UID_PATTERN, r["institution_uid"]), r
        assert re.match(SWEEP_UID_PATTERN, r["sweep_uid"]), r
        assert r["sweep_uid"] == sweep_uid_for(r["institution_uid"])


def test_source_rows_carry_both_uids(tmp_path: Path) -> None:
    run_dir = _run_with_both(tmp_path)
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")
    fields, rows = _read_csv(run_dir / "final" / "g3o_activity_sources_v1.csv")

    assert fields == ACTIVITY_SOURCE_COLUMNS
    assert rows, "fixture must produce at least one source row"
    for r in rows:
        assert re.match(INSTITUTION_UID_PATTERN, r["institution_uid"]), r
        assert re.match(SWEEP_UID_PATTERN, r["sweep_uid"]), r
        assert r["sweep_uid"] == sweep_uid_for(r["institution_uid"])


def test_summary_rows_carry_the_uid_and_not_the_sweep_uid(tmp_path: Path) -> None:
    """The loader keys this CSV on ``institution_uid``, and at institution grain
    ``sweep_uid`` restates the uid — so it carries the join key only.

    The reason used to be "the summary CSV is not a loader input". That stopped
    being true on 2026-08-25, when ``g3o-api`` began reading the verdict off it
    (#17); the column list did not change, because the key layer is what moved.
    """
    run_dir = _run_with_both(tmp_path)
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")
    fields, rows = _read_csv(run_dir / "final" / "g3o_institution_summary_v1.csv")

    assert fields == SUMMARY_COLUMNS
    assert "sweep_uid" not in fields
    assert {r["institution_id"] for r in rows} == {_INST_A, _INST_B}
    by_id = {r["institution_id"]: r["institution_uid"] for r in rows}
    assert by_id == {_INST_A: _UID_A, _INST_B: _UID_B}


def test_institution_report_rows_carry_a_non_empty_uid(tmp_path: Path) -> None:
    """The surface with no structural guard: ``r.get(col)`` would have written
    an empty cell and returned a clean summary."""
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=[_INST_A, _INST_B])

    write_institution_report(run_dir)
    fields, rows = _read_csv(run_dir / "institution_report.csv")

    assert fields == INSTITUTION_REPORT_COLUMNS
    assert "sweep_uid" not in fields
    assert {r["institution_id"] for r in rows} == {_INST_A, _INST_B}
    for r in rows:
        assert re.match(INSTITUTION_UID_PATTERN, r["institution_uid"]), r
    assert {r["institution_id"]: r["institution_uid"] for r in rows} == {
        _INST_A: _UID_A,
        _INST_B: _UID_B,
    }


def test_the_same_institution_gets_one_uid_across_every_surface(tmp_path: Path) -> None:
    run_dir = _run_with_both(tmp_path)
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")
    final = run_dir / "final"

    seen: set[str] = set()
    for name in ("g3o_activities_v1.csv", "g3o_activity_sources_v1.csv"):
        _, rows = _read_csv(final / name)
        seen |= {r["institution_uid"] for r in rows if r["institution_id"] == _INST_A}
    _, summary = _read_csv(final / "g3o_institution_summary_v1.csv")
    seen |= {r["institution_uid"] for r in summary if r["institution_id"] == _INST_A}

    assert seen == {_UID_A}


# ---------------------------------------------------------------------------
# Refusals — an unstamped run must fail loudly, never write empties
# ---------------------------------------------------------------------------


def test_persist_refuses_a_manifest_with_no_uid_block(tmp_path: Path) -> None:
    run_dir = _run_with_both(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    del manifest["institution_uids"]
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="institution_uids"):
        write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")


def test_persist_refuses_an_institution_missing_from_the_uid_map(tmp_path: Path) -> None:
    run_dir = _run_with_both(tmp_path)
    write_manifest(
        run_dir,
        {
            "run_id": "R1",
            "institutions": [_INST_A, _INST_B],
            "institution_uids": {_INST_A: _UID_A},  # B dropped
        },
    )
    with pytest.raises(RuntimeError, match=_INST_B):
        write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")


def test_institution_report_refuses_a_manifest_with_no_uid_block(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=[_INST_A])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    del manifest["institution_uids"]
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="institution_uids"):
        write_institution_report(run_dir)


def test_uid_map_accessor_refuses_a_manifest_with_no_uid_block(tmp_path: Path) -> None:
    write_manifest(tmp_path, {"run_id": "R1", "institution_uids": None})
    with pytest.raises(RuntimeError, match="institution_uids"):
        institution_uid_map(tmp_path)


# ---------------------------------------------------------------------------
# Plan time — refuse before the compute is spent
# ---------------------------------------------------------------------------


def _config(tmp_path: Path) -> PresweepConfig:
    """A plan-time config; ``build_manifest`` never reads the master itself."""
    return PresweepConfig(
        run_id="20260814-uid-test",
        runs_dir=tmp_path / "runs",
        master_csv=tmp_path / "master.csv",
        sample_size=2,
        seed=22294,
        dry_run=True,
    )


def _sample_row(master_row_id: int, uid: str | None) -> dict[str, str]:
    row = {
        "master_row_id": str(master_row_id),
        "country": "Atlantis",
        "government_level": "national",
        "branch": "executive",
        "institution_type": "ministry",
        "institution_name": f"Ministry {master_row_id}",
        "website": "",
    }
    if uid is not None:
        row["institution_uid"] = uid
    return row


def test_build_manifest_carries_the_uid_map(tmp_path: Path) -> None:
    sample = [_sample_row(1, "G3O-I-00000001"), _sample_row(2, "G3O-I-00000002")]
    manifest = build_manifest(_config(tmp_path), sample)
    assert manifest["institution_uids"] == {
        "INST-0000001": "G3O-I-00000001",
        "INST-0000002": "G3O-I-00000002",
    }


@pytest.mark.parametrize("uid", [None, "", "G3O-I-1", "G3O-S-00000001"])
def test_build_manifest_refuses_a_master_row_without_a_uid(
    tmp_path: Path, uid: str | None
) -> None:
    """Failing here costs nothing; failing at ingest costs the whole run."""
    sample = [_sample_row(1, "G3O-I-00000001"), _sample_row(2, uid)]
    with pytest.raises(RuntimeError, match="institution_uid"):
        build_manifest(_config(tmp_path), sample)


# ---------------------------------------------------------------------------
# The uid must never reach a model
# ---------------------------------------------------------------------------


def test_institution_record_does_not_carry_the_uid() -> None:
    """``institution_record()`` is serialised to ``institution.json`` and
    embedded verbatim in the Stage 2/3/5/6 user prompts
    (``classify/official_site.py``, ``classify/url_triage.py``,
    ``extract/client.py``, ``validate/client.py`` all send
    ``{"institution": institution_row}``). The uids are bookkeeping and must
    not become model input — that is why the manifest carries them instead.

    This test exists to fail on the obvious future "simplification".
    """
    rec = institution_record(_sample_row(1, "G3O-I-00000001"))
    assert "institution_uid" not in rec
    assert "sweep_uid" not in rec
    assert not any("G3O-I-" in str(v) for v in rec.values())
