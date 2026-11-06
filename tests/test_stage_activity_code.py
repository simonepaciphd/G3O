"""T-023 stage: artifacts and attrition (mocked jev and combiner)."""

from __future__ import annotations

import json

import pytest

from g3o.classify import jev_activity_code as jac
from g3o.common import attrition
from g3o.common.artifact_io import read_artifact
from g3o.common.jev_client import JevAccountError
from g3o.run.presweep import stage_activity_code as stage
from tests.test_jev_activity_code import A1, BASE, TEXT, FakeJev, config, make_page, span


@pytest.fixture(autouse=True)
def _fresh_ledger():
    attrition._reset_cache()
    yield
    attrition._reset_cache()


def test_stage_writes_artifact_and_attrition(tmp_path):
    from dataclasses import replace
    bad = replace(span("x0", None, None), status="unresolved_start")
    cut = TEXT.index("pilot")
    inp = make_page(TEXT, cuts=[cut, len(TEXT)], spans=[bad, span("x1", *A1)])
    out = stage.run_stage([inp], FakeJev(BASE, fail_parts=("2",)), config(),
                          out_dir=tmp_path / "art", run_dir=tmp_path / "run")
    assert out.skipped_activities == 1 and out.failed_parts > 0
    d = json.loads(read_artifact(out.artifacts[0]))
    assert d["format"] == "g3o-activity-code-v1" and d["activities"][0]["activity_id"] == "x1"
    reasons = {r["reason"] for r in attrition.read_records(tmp_path / "run")}
    assert reasons == {jac.MISSING_REQUEST_ID, jac.SPAN_UNRESOLVED}


def test_account_error_stops_stage():
    def acct(state, questions):
        raise JevAccountError("402")
    with pytest.raises(JevAccountError):
        stage.run_stage([make_page(TEXT, spans=[span("x1", *A1)])], acct, config())
