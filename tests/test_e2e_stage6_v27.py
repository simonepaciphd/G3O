"""T-030 mocked end-to-end v2.7 Stage 6 -> final CSVs (no network; every provider answer is a fake).

Path exercised: ``bind_runtime`` (immutable instrument bound to the signed r15
codebook) -> ``stage_validate_v27.run_stage6_v27`` (T-026 relations, support
checks and pooled reclassification through the durable request journal) ->
T-028 storage envelope with relation/pooled support nodes ->
``6_validate.json`` / ``6_storage.json`` / ``6_support_provenance.json`` ->
``write_run_csvs`` (Stage 7) -> the three final CSVs.

The per-page inputs (final per-page values, their support nodes and the source
rows) are declared fixtures built with the real T-024 check and T-028
``support_nodes`` on stored page artifacts; the per-page producers that would
make them from T-021/T-023 artifacts are not wired here (see the T-030 report).
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from g3o.classify.jev_activity_code import ItemOutcome
from g3o.classify.permanent_pilot import PERMANENT_PILOT_RULE
from g3o.classify.questions.v27 import JEV_QUESTION_SET_VERSION as QSV
from g3o.common import attrition
from g3o.common.instrument import canonical_json, load_instrument, sha256_text
from g3o.common.jev_client import JevAccountError, JevAnswer, JevResult
from g3o.common.jev_record import CoderRecord
from g3o.common.paths import institution_dir
from g3o.common.run_state import is_done
from g3o.common.storage_fields import FIELDS
from g3o.common.support_check import CodeEvidence, Entailment, PageSources, check_code
from g3o.persist.stage6_adapters import PageArtifact, SupportContext, coder_nodes, support_nodes
from g3o.persist.writer import write_run_csvs
from g3o.run.presweep import stage_validate_v27 as rt
from g3o.run.presweep.instrument_binding import RuntimeSettings, bind_runtime
from g3o.validate import stage6_v27 as s6
from g3o.validate.consolidate_v27 import ActivityObservation, RelationDecision, ReviewedPage
from tests._layout import uid_for, write_manifest
from tests._storage_fixture import _values

R15 = "ca1bf616d596213dad7064bd24921928186bce42d912a7b54e5723f41fc73d3a"
RUN_ID = "R-T030-E2E"
TRUE = Entailment("true", 0.95)
CLOCK = lambda: datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)  # noqa: E731
SETTINGS = RuntimeSettings(jev_model="fake-jev", extractor_model="fake-extractor", extractor_effort="low",
                           extractor_max_tokens=1000, reserved_tokens=0, reference_year=2026,
                           approval_reference="T-030 offline e2e fixture; no provider execution",
                           x35_model="fake-x35")


def _exempt(item, value):
    return value == "no" or value in FIELDS[item]["missing_tokens"] or value.startswith("none")


class Builder:
    """Declared per-page fixtures: page artifacts, per-page fragments with real T-024/T-028 nodes."""

    def __init__(self, run_dir, bound, instrument, inst_id):
        self.run_dir, self.bound, self.instrument, self.inst_id = run_dir, bound, instrument, inst_id
        self.uid = uid_for(inst_id)
        self.rules = bound.activity_config.rules
        self.n = 0
        self.pages, self.observations, self.records, self.quotes = [], [], [], []
        self.inputs, self.sources, self.artifacts, self.provenance, self.within = {}, {}, {}, [], []
        self.text, self.page_sources = {}, {}

    def page(self, pid, sentences, emails=()):
        text = f"Page {pid}. " + " ".join(sentences)
        path = Path("pages") / self.inst_id / f"{pid}.txt"
        (self.run_dir / path).parent.mkdir(parents=True, exist_ok=True)
        (self.run_dir / path).write_bytes(text.encode("utf-8"))
        self.text[pid] = (text, path.as_posix(), list(emails))
        self.page_sources[pid] = PageSources(pid, {f"{pid}#c1": text})

    def _node(self, item, part, value, oid, sid, pid, quote, *, linked=None):
        chunk = f"{pid}#c1"
        quote = None if _exempt(item, value) else quote
        sr = check_code(CodeEvidence(item, value, chunk, part=part, probability=0.95, quote=quote,
                                     quote_chunk_id=chunk if quote else None, entailment=TRUE if quote else None,
                                     activity_id=oid, linked_activity=linked), self.page_sources[pid])
        nodes = support_nodes(sr, self.page_sources[pid], self.artifacts[sid],
                              SupportContext(RUN_ID, self.uid, oid, sid, []), self.instrument)
        self.n += 1
        context = dict(item_id=item, item_part=part, support_id=nodes.original["support_id"], observation_id=oid,
                       chunk_id=chunk, coder_version="fake-per-page-v1", question_set_version=QSV,
                       setup_pointer=self.instrument["instrument_id"])
        if FIELDS[item]["coder"] == "classifier":
            res = JevResult({"Q": JevAnswer("Q", "choice", choice=value, confidence=0.95,
                                            probabilities={value: 0.95})}, "fake-jev-response", f"pp-{self.n}", 1, 1)
            rec = CoderRecord.from_jev(res, question_id="Q", configured_model="fake-jev",
                                       classifier_rule=self.rules[(item, part)], **context)
        else:
            rec = CoderRecord(question_id=None, coder_type="quote_step", configured_model="fake-extractor",
                              actual_response_model="fake-extractor-response", request_id=f"x-{self.n}",
                              answer_type="extracted", chosen_value=value, confidence=None,
                              probability_distribution=None, **context)
        projection, final, _ = coder_nodes(rec, nodes, self.instrument)
        self.provenance.append(nodes.provenance)
        return sr, [n for n in (nodes.original, nodes.final) if n], [c for c in (projection, final) if c]

    def _row(self, table, values, oid, sid, pid, quote):
        row = {"values": values, "item_support": [], "coder_records": []}
        for item, value in values.items():
            if FIELDS[item]["coder"] not in {"classifier", "quote_step"}:
                continue
            pairs = (list(value.items()) if isinstance(value, dict) else [(None, v) for v in value]
                     if isinstance(value, list) else [(None, value)])
            for part, selected in pairs:
                _, nodes, coders = self._node(item, part, selected, oid, sid, pid, quote)
                row["item_support"] += nodes
                row["coder_records"] += coders
        return row

    def observation(self, oid, pid, *, name, activity_type, tool, quote, verdict="confirms_activity"):
        sid = f"S{len(self.sources) + 1}"
        text, path, emails = self.text[pid]
        self.artifacts[sid] = PageArtifact(sid, path, text, {f"{pid}#c1": (0, len(text))})
        values = _values("activities")
        for k in ("core.n_sources", "core.confidence"):
            values.pop(k)
        values.update({"core.activity_name": name, "core.activity_type": activity_type, "core.tool_name": [tool],
                       "core.reported_outcomes": [], "core.deployment_scale_number": "not_documented"})
        frag = self._row("activities", values, oid, sid, pid, quote)
        tool_node = next(s for s in frag["item_support"] if s["item_id"] == "core.tool_name")
        src_values = _values("sources")
        src_values.update({"core.page_verdict": verdict, "core.source_url": f"https://example.gov/{pid}",
                           "core.content_contact_emails": emails})
        src = self._row("sources", src_values, oid, sid, pid, quote)
        src.update(observation_ids=[oid], page_artifact_path=path, page_content_sha256=sha256_text(text))
        self.sources[sid] = src
        self.inputs[oid] = rt.ObservationInput(oid, sid, frag)
        ps = self.page_sources[pid]
        q = s6.InputQuote(tool_node["support_id"], oid, sid, ps, f"{pid}#c1", f"{pid}#c1", quote, "a government page",
                          "2025-01-01", "2026-03-01", f"https://example.gov/{pid}", len(self.pages), 0)
        self.quotes.append(q)
        outcome = ItemOutcome("core.action_type", "core.action_type", None, "combined", values["core.action_type"])
        self.observations.append(ActivityObservation(oid, pid, {outcome.question_id: outcome},
                                                     {"core.activity_name": name}, True,
                                                     tuple(frag["coder_records"]), tuple(frag["item_support"])))
        self.records.append(s6.ObservationRecord(oid, pid, {**values}, f"https://example.gov/{pid}", (q,)))
        if not any(p.page_id == pid for p in self.pages):
            self.pages.append(ReviewedPage(pid, "web_extract", verdict, 0.95, "supported", True, False, False,
                                           (sid,), ({"fake": "coder"},), ({"fake": "support"},)))
        return sid

    def within_pair(self, lhs, rhs, relation, pid, quote):
        sid = self.inputs[lhs].source_id
        _, nodes, coders = self._node("core.activity_segment", None, relation, lhs, sid, pid, quote, linked=rhs)
        self.inputs[lhs].row["item_support"].extend(nodes)
        self.inputs[lhs].row["coder_records"].extend(coders)
        self.within.append(RelationDecision(lhs, rhs, relation, 0.95, "supported", ({"fake": "coder"},),
                                            (nodes[0]["support_id"],), "within_page"))

    def institution(self, merged=None):
        identity = {"institution_id": self.inst_id, "institution_name": f"Council {self.inst_id}",
                    "country": "Australia", "branch_of_government": "executive", "level_of_government": "local",
                    "institution_search_languages": "en"}
        # Ruling 38 a: the institution's country is the master country name.
        return rt.Stage6Institution(
            RUN_ID, self.uid, identity, identity["country"], self.pages, self.observations, self.records,
            self.within, self.quotes, self.inputs, self.sources, self.artifacts, self.provenance,
            independence_groups={sid: sid for sid in self.sources}, merged_values=merged)


class FakeJev:
    """Relations by activity-name pair; every other question gets a declared answer or a no-evidence code."""

    def __init__(self, relations, answers):
        self.relations, self.answers, self.calls = relations, answers, []

    def __call__(self, state, questions):
        self.calls.append(questions)
        out = {}
        for qid, q in questions.items():
            if qid == s6.RELATION_ITEM:
                value = self.relations[(state["first_record"]["activity_name"], state["second_record"]["activity_name"])]
            else:
                codes = list(q["criteria"])
                value = self.answers.get(qid) or next(c for c in ("not_documented", "unknown", "no", *codes)
                                                      if c in codes)
            out[qid] = JevAnswer(qid, "choice", choice=value, confidence=0.95, probabilities={value: 0.95})
        # request id from the request content, so a resumed run reproduces the reference bytes
        rid = sha256_text(canonical_json({"state": state, "questions": questions}))[:16]
        return JevResult(out, "fake-jev-response", f"s6-{rid}", 10, 2)


class FakeQuotes:
    """The Stage 6 quote step (draft wording: fakes only): copies the first shown input verbatim."""

    def __init__(self, fail_at=None):
        self.calls, self.fail_at = 0, fail_at

    def __call__(self, req):
        self.calls += 1
        if self.fail_at is not None and self.calls == self.fail_at:
            raise JevAccountError("simulated interruption: account stopped")
        first = req.candidates[0]
        return s6.Stage6Quote(first.quote_text, first.support_id, TRUE, {"fake": True})


Q1 = "The council deployed Copilot for drafting letters in 2025."
Q2 = "Council staff now draft letters with Copilot every day."
Q3 = "The council adopted a policy that governs chatbot use."
Q4 = "A public chatbot answers resident questions about bins."
RELATIONS = {("Copilot drafting", "Copilot drafting"): "same_activity"}
POOLED = {"core.adoption_stage": "pilot", "core.permanent_pilot": "yes"}


def _setup(tmp_path, name="run"):
    run_dir = tmp_path / name
    bound = bind_runtime(run_dir, SETTINGS)
    instrument = load_instrument(run_dir / "final" / "instruments", bound.instrument_id)
    return run_dir, bound, instrument


def _institutions(run_dir, bound, instrument):
    a = Builder(run_dir, bound, instrument, "INST-0000001")
    a.page("p1", [Q1], emails=["Ada@Example.GOV", "ada@example.gov"])
    a.page("p2", [Q2])
    a.page("p3", [Q3, Q4], emails=["info@council.example.gov"])
    a.observation("o1", "p1", name="Copilot drafting", activity_type="internal_operational", tool="Copilot", quote=Q1)
    a.observation("o2", "p2", name="Copilot drafting", activity_type="internal_operational", tool="Copilot", quote=Q2)
    a.observation("o3", "p3", name="Chatbot policy", activity_type="policy_guidance", tool="Policy", quote=Q3)
    a.observation("o4", "p3", name="Resident chatbot", activity_type="public_facing_service", tool="Binbot", quote=Q4)
    a.within_pair("o3", "o4", "governs", "p3", Q3)
    # declared fixture: only the merged values with no rule computable from the merged row (RC-D-030 X1)
    merged = {("o1", "o2"): {k: v for k, v in a.inputs["o1"].row["values"].items() if k in rt.MERGE_INPUT_ITEMS}}
    b = Builder(run_dir, bound, instrument, "INST-0000002")
    b.page("q1", ["The council does not use generative AI."])
    b.observation("n1", "q1", name="Copilot drafting", activity_type="internal_operational", tool="Copilot",
                  quote="The council does not use generative AI.", verdict="confirms_activity")
    return [a.institution(merged), b.institution()]


def _pooled_answers():
    from g3o.classify.questions.v27 import load_set
    by_item = {q["item_id"]: q["question_id"] for q in load_set("activity")["questions"] if q.get("part") is None}
    return {by_item[item]: value for item, value in POOLED.items() if item in by_item}


def _run(run_dir, bound, instrument, insts, quote_fn, jev=None):
    jev = jev or FakeJev(RELATIONS, _pooled_answers())
    return jev, rt.run_stage6_v27(run_dir, insts, ask_fn=jev, quote_fn=quote_fn, config=bound.stage6_config(),
                                  instrument=instrument, now=CLOCK,
                                  test_only_unbound_quote_fn=not getattr(quote_fn, "bound_instrument_id", None))


def _csvs(run_dir, insts):
    write_manifest(run_dir, {"run_id": RUN_ID, "institutions": [i.institution_id for i in insts],
                             "storage_contract": {"codebook_release": "2.7"}})
    result = write_run_csvs(run_dir, run_id=RUN_ID, run_model="fake-jev", run_date="2026-11-10")
    rows = {}
    for key, out in result["outputs"].items():
        with Path(out["path"]).open(encoding="utf-8", newline="") as stream:
            rows[key] = list(csv.DictReader(stream))
    return result, rows


def test_instrument_is_bound_to_signed_r15_and_stage6_config_to_it(tmp_path):
    run_dir, bound, instrument = _setup(tmp_path)
    assert instrument["payload"]["codebook_sha256"] == R15
    config = bound.stage6_config()
    assert config.setup_pointer == instrument["instrument_id"] == bound.instrument_id
    assert config.configured_model == instrument["payload"]["configured_jev_model"]
    with pytest.raises(ValueError, match="different instrument"):
        rt.run_stage6_v27(run_dir, [], ask_fn=None, quote_fn=None, config=s6.Stage6Config(
            **{**config.__dict__, "setup_pointer": "0" * 64}), instrument=instrument)


def test_e2e_stage6_to_final_csvs(tmp_path):
    run_dir, bound, instrument = _setup(tmp_path)
    insts = _institutions(run_dir, bound, instrument)
    jev, metrics = _run(run_dir, bound, instrument, insts, FakeQuotes())
    assert metrics.written == ["INST-0000001", "INST-0000002"] and not metrics.held
    inst_dir = institution_dir(run_dir, "INST-0000001")
    storage = json.loads((inst_dir / "6_storage.json").read_text(encoding="utf-8"))
    acts = storage["activities"]
    # o1/o2: supported same_activity -> one merged, pooled activity; o3, o4 separate (pre-filter distinct).
    assert sorted(tuple(a["observation_ids"]) for a in acts.values()) == [("o1", "o2"), ("o3",), ("o4",)]
    merged = next(a for a in acts.values() if a["observation_ids"] == ["o1", "o2"])
    assert merged["values"]["core.n_sources"] == 2
    # RC-D-025 B2 a re-applied after pooling: supported permanent_pilot yes turns pooled pilot into production.
    assert merged["values"]["core.adoption_stage"] == "production"
    pooled_nodes = [s for s in merged["item_support"] if s["source_id"] is None and s["observation_id"] is None]
    assert pooled_nodes and all(s["input_support_ids"] for s in pooled_nodes)
    assert any(s["passage"].get("quote_source_id") for s in pooled_nodes)  # quote matched on its input page
    assert any(s["support_rule_name"] == PERMANENT_PILOT_RULE and s["value_json"] == "production"
               for s in pooled_nodes if s["support_status"] == "set_by_rule")
    relations = {(r["lhs_observation_id"], r["rhs_observation_id"]): r for a in acts.values()
                 for r in a["activity_relations"]}
    assert relations[("o1", "o2")]["relation"] == "same_activity"
    assert relations[("o3", "o4")]["relation"] == "governs"  # T-023 within-page pair, not re-asked
    assert relations[("o3", "o4")]["relation_scope"] == "within_page"
    assert relations[("o1", "o3")]["relation"] == "distinct_action"  # pre-filter, set by rule
    prov = json.loads((inst_dir / "6_support_provenance.json").read_text(encoding="utf-8"))
    assert prov["storage_sha256"] == sha256_text((inst_dir / "6_storage.json").read_bytes().decode("utf-8"))
    result, rows = _csvs(run_dir, insts)
    assert result["integrity"]["is_valid"]
    summary = {r["institution_id"]: r for r in rows["institution_summary"]}
    assert summary["INST-0000001"]["has_genai_activity"] == "yes"
    assert all(r["setup_pointer"] == bound.instrument_id for t in rows.values() for r in t)
    contact = [r for r in rows["activity_sources"] if r["source_url"].endswith("/p1")]
    assert contact and "example.gov" in contact[0]["contact_email_domain_counts_json"]


def test_e2e_missing_quote_step_holds_then_resume_publishes(tmp_path):
    run_dir, bound, instrument = _setup(tmp_path)
    insts = _institutions(run_dir, bound, instrument)
    _, metrics = _run(run_dir, bound, instrument, insts[:1], None)
    assert metrics.held == ["INST-0000001"] and not metrics.written
    inst_dir = institution_dir(run_dir, "INST-0000001")
    held = json.loads((inst_dir / rt.WORK_DIR / rt.HELD_FILE).read_text(encoding="utf-8"))
    assert {h["reason"] for h in held["held"]} == {s6.QUOTE_STEP_ABSENT}
    assert not (inst_dir / "6_storage.json").exists()  # pending work is never published
    ledger = [r for r in attrition.read_records(run_dir) if r["institution_id"] == "INST-0000001"]
    assert [r["reason"] for r in ledger] == [f"{rt.HELD_REASON}:{rt.MISSING_RELATION}",
                                             f"{rt.HELD_REASON}:{s6.QUOTE_STEP_ABSENT}"]
    jev, metrics = _run(run_dir, bound, instrument, insts[:1], FakeQuotes())
    assert metrics.written == ["INST-0000001"] and not (inst_dir / rt.WORK_DIR / rt.HELD_FILE).exists()
    assert not any(s6.RELATION_ITEM in q for q in jev.calls)  # the relation answer was replayed, not re-asked


def test_e2e_interruption_resume_matches_uninterrupted_run(tmp_path):
    ref_dir, ref_bound, ref_instrument = _setup(tmp_path, "reference")
    ref = _institutions(ref_dir, ref_bound, ref_instrument)
    ref_jev, _ = _run(ref_dir, ref_bound, ref_instrument, ref, FakeQuotes())

    run_dir, bound, instrument = _setup(tmp_path, "interrupted")
    assert bound.instrument_id == ref_bound.instrument_id
    insts = _institutions(run_dir, bound, instrument)
    with pytest.raises(JevAccountError):
        _run(run_dir, bound, instrument, insts, FakeQuotes(fail_at=2))
    inst_dir = institution_dir(run_dir, "INST-0000001")
    assert not (inst_dir / "6_storage.json").exists()
    journal = (inst_dir / rt.WORK_DIR / rt.JOURNAL).read_bytes()
    (inst_dir / rt.WORK_DIR / rt.JOURNAL).write_bytes(journal + b'{"kind": "jev", "key": "torn')  # torn tail
    first_usage = rt.RequestJournal(inst_dir / rt.WORK_DIR / rt.JOURNAL).usage()
    assert first_usage["jev_responses"] >= 1 and first_usage["input_tokens"] > 0  # partial run accounted
    jev, metrics = _run(run_dir, bound, instrument, insts, FakeQuotes())
    assert metrics.written == ["INST-0000001", "INST-0000002"]
    assert metrics.replayed_requests >= first_usage["jev_responses"] + first_usage["quote_responses"]
    assert len(jev.calls) == len(ref_jev.calls) - first_usage["jev_responses"]  # no completed request repeated
    for name in ("6_storage.json", "6_validate.json", "6_support_provenance.json"):
        for inst in ("INST-0000001", "INST-0000002"):
            assert ((institution_dir(run_dir, inst) / name).read_bytes()
                    == (institution_dir(ref_dir, inst) / name).read_bytes().replace(b"reference", b"interrupted"))
    _, again = _run(run_dir, bound, instrument, insts, FakeQuotes())
    assert again.skipped == ["INST-0000001", "INST-0000002"] and again.live_requests == 0


def test_done_marker_written_on_completion_not_on_a_stage_stop(tmp_path):
    """Ruling 48.3 a: ``_state/.done/stage6_v27.json`` once the whole pass finished, never
    after a stage stop; v2.5's ``validate`` marker name is not used."""
    run_dir, bound, instrument = _setup(tmp_path)
    insts = _institutions(run_dir, bound, instrument)
    with pytest.raises(JevAccountError):
        _run(run_dir, bound, instrument, insts, FakeQuotes(fail_at=2))
    assert not is_done(run_dir, rt.DONE_MARKER)
    _run(run_dir, bound, instrument, insts, FakeQuotes())
    assert rt.DONE_MARKER == "stage6_v27"
    assert is_done(run_dir, rt.DONE_MARKER)
    assert not is_done(run_dir, "validate")


def test_done_marker_written_when_the_pass_finishes_with_a_hold(tmp_path):
    """Ruling 48.3 a: a held institution does not keep the pass from finishing; it stays
    pending (held.json), which the report reads first (ruling 45 a)."""
    run_dir, bound, instrument = _setup(tmp_path)
    insts = _institutions(run_dir, bound, instrument)
    _, metrics = _run(run_dir, bound, instrument, insts[:1], None)
    assert metrics.held == ["INST-0000001"]
    assert is_done(run_dir, rt.DONE_MARKER)


def test_stale_done_marker_is_cleared_when_a_resumed_pass_stops(tmp_path, monkeypatch):
    """Ruling 48.3 a / 45 a: a finished pass's marker does not outlive a later pass that stops,
    so an institution queued behind the stop is never read as concluded."""
    run_dir, bound, instrument = _setup(tmp_path)
    insts = _institutions(run_dir, bound, instrument)
    _run(run_dir, bound, instrument, insts[:1], FakeQuotes())
    assert is_done(run_dir, rt.DONE_MARKER)

    def stopped(**kw):
        raise JevAccountError("simulated stop before the next institution")
    monkeypatch.setattr(rt, "run_stage6", stopped)
    with pytest.raises(JevAccountError):
        _run(run_dir, bound, instrument, insts, FakeQuotes())
    assert not is_done(run_dir, rt.DONE_MARKER)
    assert not (institution_dir(run_dir, "INST-0000002") / "6_validate.json").exists()
