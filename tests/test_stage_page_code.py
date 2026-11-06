"""Tests for the T-021 page-code stage driver (mocked jev)."""

from __future__ import annotations

import pytest

from g3o.classify import jev_page_code as jpc
from g3o.common import attrition
from g3o.common.artifact_io import artifact_exists, read_artifact
from g3o.common.cost_monitor import BudgetExceededError
from g3o.common.jev_client import JevAccountError
from g3o.run.presweep import stage_page_code as spc
from tests.test_jev_page_code import DEFAULTS, FakeJev, cfg, rules  # noqa: F401


def pages(n=2):
    return [jpc.PageInput(page_id=f"i{k}:u", institution_id=f"i{k}", institution="City", country="X",
                          level_of_government="local", url=f"https://c{k}.example/ai", title="AI",
                          text="The council launched a ChatGPT pilot.", chrome_text=None) for k in range(n)]


@pytest.fixture(autouse=True)
def _fresh_ledger():
    attrition._reset_cache()
    yield
    attrition._reset_cache()


def test_writes_artifacts_and_resumes(tmp_path, rules):  # noqa: F811
    fake = FakeJev(dict(DEFAULTS))
    m = spc.run_page_code_stage(tmp_path, pages(), ask_fn=fake, config=cfg(rules), concurrency=2)
    assert (m.n_coded, m.n_failed, m.n_skipped) == (2, 0, 0) and m.n_requests == len(fake.calls)
    p = spc.artifact_path(tmp_path, "i0", "https://c0.example/ai")
    res = jpc.PageCodeResult.from_json(read_artifact(p))
    assert res.verdict.value == "confirms_activity"
    n_calls = len(fake.calls)
    m2 = spc.run_page_code_stage(tmp_path, pages(), ask_fn=fake, config=cfg(rules))
    assert m2.n_skipped == 2 and len(fake.calls) == n_calls


def test_failed_page_goes_to_attrition_without_artifact(tmp_path, rules):  # noqa: F811
    fake = FakeJev(dict(DEFAULTS), request_id=None)
    m = spc.run_page_code_stage(tmp_path, pages(1), ask_fn=fake, config=cfg(rules))
    assert m.n_failed == 1
    assert not artifact_exists(spc.artifact_path(tmp_path, "i0", "https://c0.example/ai"))
    recs = attrition.read_records(tmp_path)
    assert [r["reason"] for r in recs] == [jpc.MISSING_REQUEST_ID]


def test_part_failures_recorded_once_per_page(tmp_path, rules):  # noqa: F811
    fake = FakeJev(dict(DEFAULTS), fail=lambda s, q: RuntimeError("x") if "core.content_data" in q else None)
    m = spc.run_page_code_stage(tmp_path, pages(1), ask_fn=fake, config=cfg(rules))
    assert m.n_coded == 1
    assert [r["reason"] for r in attrition.read_records(tmp_path)] == [spc.PART_FAILURES]


def test_account_error_stops_stage(tmp_path, rules):  # noqa: F811
    fake = FakeJev(dict(DEFAULTS), fail=lambda s, q: JevAccountError("402"))
    with pytest.raises(JevAccountError):
        spc.run_page_code_stage(tmp_path, pages(3), ask_fn=fake, config=cfg(rules), concurrency=1)
    assert attrition.read_records(tmp_path) == []


def test_cost_check_false_stops(tmp_path, rules):  # noqa: F811
    fake = FakeJev(dict(DEFAULTS))
    m = spc.run_page_code_stage(tmp_path, pages(3), ask_fn=fake, config=cfg(rules), concurrency=1,
                                cost_check_callback=lambda stage, usage: False)
    assert m.stopped_early and m.n_coded == 0 and len(fake.calls) == 1


def test_budget_error_propagates(tmp_path, rules):  # noqa: F811
    def cb(stage, usage):
        raise BudgetExceededError(2.0, 1.0, stage)

    with pytest.raises(BudgetExceededError):
        spc.run_page_code_stage(tmp_path, pages(1), ask_fn=FakeJev(dict(DEFAULTS)), config=cfg(rules),
                                cost_check_callback=cb)


def test_duplicate_page_ids_refused(tmp_path, rules):  # noqa: F811
    with pytest.raises(ValueError):
        spc.run_page_code_stage(tmp_path, pages(1) * 2, ask_fn=FakeJev(dict(DEFAULTS)), config=cfg(rules))


def test_jev_ask_adapter_builds_choices():
    seen = {}

    class Client:
        def system_one(self, state, questions, model=None):
            seen["q"] = questions
            raise RuntimeError("stop")

    ask = spc.jev_ask(Client())
    with pytest.raises(RuntimeError):
        ask({"a": 1}, {"q1": {"instructions": "i", "criteria": {"x": "y"}}})
    assert seen["q"]["q1"].model_dump()["criteria"] == {"x": "y"}
