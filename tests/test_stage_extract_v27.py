"""T-022: the v2.7 Stage 5 runner (``stage_extract._run_extract_v27``).

All extractor calls go to an in-memory fake; no network, no SDK.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from g3o.common import attrition
from g3o.common.artifact_io import read_artifact
from g3o.common.page_chunks import chunk_page
from g3o.common.run_state import done_path, state_path
from g3o.extract.anthropic_client import ExtractorResult
from g3o.extract.request_v27 import PageCode, Pass1Page
from g3o.run.presweep import stage_extract
from g3o.run.presweep.stage_extract import _run_extract_v27, _v27_artifact_path

TEXT = "Town of Example. The council launched the CivicBot chatbot for residents in March 2024."


def page(pid: str, *, verdict: str = "confirms_activity", codes=None, url=None) -> Pass1Page:
    if codes is None:
        codes = [PageCode("core.page_verdict", f"{pid}#p001", verdict)]
    return Pass1Page(
        page_id=pid, institution_id="inst-1", institution_name="Town of Example",
        url=url or f"https://example.gov/{pid}", title="CivicBot", text=TEXT,
        chunks=tuple(chunk_page(pid, TEXT)), codes=tuple(codes), verdict=verdict,
        page_complete=None, has_metadata_date=True,
    )


def answer_for(p: Pass1Page) -> str:
    return json.dumps({
        "quotes": [{"task_id": "q001", "part_id": f"{p.page_id}#p001",
                    "quote": "The council launched the CivicBot chatbot"}],
        "links": [], "activities": [], "publication_date": None,
    })


class FakeExtractor:
    """Stands in for AnthropicExtractorClient (sync + batch)."""

    def __init__(self, answers: dict[str, str], *, polls_before_end: int = 0):
        self.answers = answers  # custom_id -> answer text (missing = errored)
        self.created: list[str] = []
        self.submitted: list[list[str]] = []
        self.polls_before_end = polls_before_end
        self.polls = 0

    def _result(self, cid: str) -> ExtractorResult:
        if cid not in self.answers:
            return ExtractorResult(cid, False, None, {"type": "errored"})
        return ExtractorResult(cid, True, self.answers[cid], None, response_model="claude-haiku-5-5",
                               usage={"input_tokens": 1, "output_tokens": 1})

    def create(self, job):
        self.created.append(job.custom_id)
        return self._result(job.custom_id)

    def submit_batch(self, jobs):
        self.submitted.append([j.custom_id for j in jobs])
        return f"msgbatch_{len(self.submitted)}"

    def batch_status(self, batch_id):
        self.polls += 1
        return "ended" if self.polls > self.polls_before_end else "in_progress"

    def batch_results(self, batch_id):
        n = int(batch_id.rsplit("_", 1)[1]) - 1
        for cid in self.submitted[n]:
            yield self._result(cid)


def _answers(pages):
    from g3o.extract.request_v27 import build_jobs

    jobs, _ = build_jobs(pages)
    by_pid = {p.page_id: p for p in pages}
    return {j.custom_id: answer_for(by_pid[j.metadata["page_id"]]) for j in jobs}


@pytest.fixture(autouse=True)
def _fresh_ledger_cache():
    attrition._reset_cache()
    yield
    attrition._reset_cache()


def _load(run_dir: Path, p: Pass1Page) -> dict:
    return json.loads(read_artifact(_v27_artifact_path(run_dir, p.institution_id, p.url)))


def test_sync_writes_one_artifact_per_page_and_marks_done(tmp_path):
    pages = [page("P1"), page("P2", verdict="no_genai")]
    fake = FakeExtractor(_answers(pages))
    counts = _run_extract_v27(tmp_path, pages, client=fake, mode="sync")
    assert counts == {"pages": 2, "skipped": 0, "no_request": 1, "refused": 0,
                      "extracted": 1, "failed": 0}
    a1, a2 = _load(tmp_path, pages[0]), _load(tmp_path, pages[1])
    assert a1["status"] == "extracted" and a1["prompt_version"].startswith("extract_v27")
    q = a1["extraction"]["quotes"][0]
    assert (q["chunk_id"], q["status"]) == ("P1#p001", "quoted")
    assert a2["status"] == "no_request" and a2["plan"]["quote_tasks"] == []
    assert done_path(tmp_path, "extract_v27").exists()
    assert len(fake.created) == 1


def test_done_marker_skips_everything(tmp_path):
    pages = [page("P1")]
    _run_extract_v27(tmp_path, pages, client=FakeExtractor(_answers(pages)), mode="sync")
    fake = FakeExtractor({})
    counts = _run_extract_v27(tmp_path, pages, client=fake, mode="sync")
    assert counts["skipped"] == 1 and fake.created == []


def test_failures_go_to_the_ledger_not_to_artifacts(tmp_path):
    pages = [page("P1"), page("P2")]
    answers = _answers(pages)
    cid_p1, cid_p2 = list(answers)
    answers[cid_p2] = json.dumps({"quotes": [], "links": [], "activities": [],
                                  "publication_date": None, "page_verdict": "x"})
    del answers[cid_p1]
    counts = _run_extract_v27(tmp_path, pages, client=FakeExtractor(answers), mode="sync")
    assert counts["failed"] == 2 and counts["extracted"] == 0
    reasons = sorted(r["reason"] for r in attrition.read_records(tmp_path))
    assert reasons == ["v27_extract_failed", "v27_parse_failed"]
    assert not any(stage_extract._v27_has_artifact(tmp_path, p) for p in pages)


def test_oversize_request_is_refused_whole_and_recorded(tmp_path, monkeypatch):
    import g3o.extract.anthropic_client as ac

    real = ac.split_for_batches
    monkeypatch.setattr(ac, "split_for_batches",
                        lambda jobs: real(jobs, max_request_bytes=10))
    pages = [page("P1")]
    fake = FakeExtractor(_answers(pages))
    counts = _run_extract_v27(tmp_path, pages, client=fake, mode="sync")
    assert counts["refused"] == 1 and fake.created == []
    assert [r["reason"] for r in attrition.read_records(tmp_path)] == ["v27_request_too_large"]


def test_cost_check_false_sends_nothing(tmp_path):
    pages = [page("P1")]
    fake = FakeExtractor(_answers(pages))
    with pytest.raises(RuntimeError, match="cost check"):
        _run_extract_v27(tmp_path, pages, client=fake, mode="batch",
                         cost_check_callback=lambda jobs: False)
    assert fake.submitted == [] and not done_path(tmp_path, "extract_v27").exists()


def test_batch_mode_polls_then_persists(tmp_path):
    pages = [page("P1"), page("P2")]
    fake = FakeExtractor(_answers(pages), polls_before_end=2)
    sleeps: list[float] = []
    counts = _run_extract_v27(tmp_path, pages, client=fake, mode="batch",
                              poll_interval=5, sleep=sleeps.append)
    assert counts["extracted"] == 2 and len(fake.submitted) == 1
    assert sleeps == [5, 5]
    marker = json.loads(done_path(tmp_path, "extract_v27").read_text(encoding="utf-8"))
    assert marker["batches"][0]["batch_id"] == "msgbatch_1"


def test_batch_timeout_keeps_state_and_rerun_rejoins_without_resubmitting(tmp_path):
    pages = [page("P1")]
    fake = FakeExtractor(_answers(pages), polls_before_end=10)
    with pytest.raises(TimeoutError, match="re-run to rejoin"):
        _run_extract_v27(tmp_path, pages, client=fake, mode="batch",
                         poll_interval=1, max_wait=2, sleep=lambda s: None)
    state = json.loads(state_path(tmp_path, "extract_v27").read_text(encoding="utf-8"))
    assert [b["batch_id"] for b in state["batches"]] == ["msgbatch_1"]
    fake.polls_before_end = 0
    fake.polls = 0
    counts = _run_extract_v27(tmp_path, pages, client=fake, mode="batch", sleep=lambda s: None)
    assert counts["extracted"] == 1 and len(fake.submitted) == 1
    assert not state_path(tmp_path, "extract_v27").exists()


def test_batch_state_that_does_not_match_the_input_is_refused(tmp_path):
    pages = [page("P1")]
    fake = FakeExtractor(_answers(pages), polls_before_end=10)
    with pytest.raises(TimeoutError):
        _run_extract_v27(tmp_path, pages, client=fake, mode="batch",
                         poll_interval=1, max_wait=1, sleep=lambda s: None)
    with pytest.raises(RuntimeError, match="do not match"):
        _run_extract_v27(tmp_path, [page("P9")], client=fake, mode="batch")
    assert len(fake.submitted) == 1


def test_no_head_tail_cap_on_the_v27_path(tmp_path):
    long_text = "GenAI pilot sentence. " * 4000  # > the v2.5 60,000-character cap
    p = Pass1Page(
        page_id="P1", institution_id="inst-1", institution_name="Town of Example",
        url="https://example.gov/long", title=None, text=long_text,
        chunks=tuple(chunk_page("P1", long_text)),
        codes=(PageCode("core.page_verdict", "P1#p001", "confirms_activity"),),
        verdict="confirms_activity", page_complete=None, has_metadata_date=True,
    )
    assert len(long_text) > stage_extract.DEFAULT_TEXT_CAP_CHARS
    fake = FakeExtractor({})
    _run_extract_v27(tmp_path, [p], client=fake, mode="sync")
    assert len(fake.created) == 1
    from g3o.extract.request_v27 import build_jobs

    user = build_jobs([p])[0][0].params["messages"][0]["content"]
    assert all(c.text in user for c in p.chunks)
    assert sum(len(c.text) for c in p.chunks) == len(long_text)


def test_bad_mode_and_duplicate_pages_fail_closed(tmp_path):
    with pytest.raises(ValueError):
        _run_extract_v27(tmp_path, [page("P1")], client=FakeExtractor({}), mode="stream")
    with pytest.raises(ValueError, match="duplicate page_id"):
        _run_extract_v27(tmp_path, [page("P1"), page("P1")], client=FakeExtractor({}), mode="sync")


# ---------------------------------------------------------------------------
# Lane B F2, F6
# ---------------------------------------------------------------------------


def test_billed_failed_response_keeps_usage_and_rerun_reports_failed(tmp_path):
    # F2: a paid response that breaks the contract keeps its usage; the page is not retried
    # (v2.5 Stage 5 precedent) and a re-run reports it as failed, not skipped.
    pages = [page("P1"), page("P2")]
    answers = _answers(pages)
    cid_p1, cid_p2 = list(answers)

    class Billed(FakeExtractor):
        def _result(self, cid):
            if cid == cid_p2:
                return ExtractorResult(cid, True, '{"quotes": [], "oops": 1}', None,
                                       response_model="claude-haiku-5-5",
                                       usage={"input_tokens": 50_000, "output_tokens": 3_000})
            return super()._result(cid)

    counts = _run_extract_v27(tmp_path, pages, client=Billed(answers), mode="sync")
    assert (counts["extracted"], counts["failed"]) == (1, 1)
    (rec,) = [r for r in attrition.read_records(tmp_path) if r["reason"] == "v27_parse_failed"]
    assert rec["usage"] == {"input_tokens": 50_000, "output_tokens": 3_000}
    marker = json.loads(done_path(tmp_path, "extract_v27").read_text(encoding="utf-8"))
    assert marker["response_usage"] == {"input_tokens": 50_001, "output_tokens": 3_001}
    assert marker["n_responses"] == 2 and marker["failed_pages"] == ["P2"]
    again = FakeExtractor(answers)
    counts = _run_extract_v27(tmp_path, pages, client=again, mode="sync")
    assert (counts["skipped"], counts["failed"], again.created) == (1, 1, [])


def test_batch_failed_response_usage_in_marker(tmp_path):
    pages = [page("P1"), page("P2")]
    answers = _answers(pages)
    del answers[list(answers)[0]]  # errored result: no usage
    counts = _run_extract_v27(tmp_path, pages, client=FakeExtractor(answers), mode="batch",
                              sleep=lambda s: None)
    assert (counts["extracted"], counts["failed"]) == (1, 1)
    marker = json.loads(done_path(tmp_path, "extract_v27").read_text(encoding="utf-8"))
    assert marker["response_usage"] == {"input_tokens": 1, "output_tokens": 1}
    assert len(marker["batches"]) == 1 and marker["failed_pages"] == ["P1"]


def test_bad_code_or_bad_page_does_not_stop_the_stage(tmp_path):
    # F6: a bad code is recorded and left out; a page whose plan cannot be built fails alone.
    p1 = page("P1", codes=[PageCode("core.page_verdict", "P1#p001", "confirms_activity"),
                           PageCode("core.activity_type", "P1#p001", "pilot_experiment")])
    p2 = page("P2", verdict="made_up")
    p3 = page("P3")
    answers = _answers([p1, p3])
    counts = _run_extract_v27(tmp_path, [p1, p2, p3], client=FakeExtractor(answers), mode="sync")
    assert (counts["extracted"], counts["failed"]) == (2, 1)
    recs = {r["reason"]: r for r in attrition.read_records(tmp_path)}
    assert set(recs) == {"v27_code_skipped", "v27_plan_failed"}
    assert recs["v27_code_skipped"]["codes"][0]["reason"] == "not_a_support_item"
    assert "made_up" in recs["v27_plan_failed"]["detail"]
    assert _load(tmp_path, p1)["plan"]["skipped_codes"][0]["item_id"] == "core.activity_type"
