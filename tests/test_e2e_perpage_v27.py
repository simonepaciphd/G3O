"""T-030 mocked end-to-end v2.7 new-run path: rendered pages -> final CSVs (no network; every answer is a fake).

Path exercised: ``bind_runtime`` -> ``stage_perpage_v27.run_perpage_v27``
(T-021 ``run_page_code_stage``; ``complete_page_rounds``; T-023
``stage_activity_code.run_stage``; ``complete_activity_rounds``; pair support
and ``finalize_pairs``; the per-page producer to T-028 nodes) ->
``stage_validate_v27.run_stage6_v27`` -> ``write_run_csvs``.

Fakes (declared, never runtime defaults): the jev answers, the support
provider (the real T-024 ``check_code`` over quotes the fake quote steps
copy from the stored part text, with a fake X35 ``true``), the T-022 spans,
and the explicit upstream values whose producers are absent (T-015 source
fields, T-022 quote-step values, T-024 derived values,
follow provenance, independence groups, merged values, uncertainty flags).
The page layout is fixed per paragraph by monkeypatching ``plan_layout``.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from g3o.classify import jev_page_code as jpc
from g3o.classify.jev_activity_code import ActivityPageInput
from g3o.classify.questions.v27 import JEV_QUESTION_SET_VERSION as QSV
from g3o.common import attrition
from g3o.common.instrument import canonical_json, load_instrument, sha256_text
from g3o.common.jev_client import JevAccountError, JevAnswer, JevResult
from g3o.common.jev_record import CoderRecord
from g3o.common.page_chunks import Chunk
from g3o.common.paths import institution_dir
from g3o.common.storage_fields import FIELDS
from g3o.common.support_check import CodeEvidence, Entailment, PageSources, check_code
from g3o.extract.parser_v27 import ActivitySpan, FieldValue
from g3o.persist.writer import write_run_csvs
from g3o.run.presweep import stage_page_code
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep import stage_validate_v27 as rt
from g3o.run.presweep.instrument_binding import RuntimeSettings, bind_runtime
from g3o.validate import stage6_v27 as s6
from tests._layout import uid_for, write_manifest
from tests._storage_fixture import _values

RUN_ID = "R-T030-PP"
TRUE = Entailment("true", 0.95)
CLOCK = lambda: datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)  # noqa: E731
SETTINGS = RuntimeSettings(jev_model="fake-jev", extractor_model="fake-extractor", extractor_effort="low",
                           extractor_max_tokens=1000, reserved_tokens=0, reference_year=2026,
                           approval_reference="T-030 offline e2e fixture; no provider execution")
SEP = "\n\n"
CHROME = "Site header\nContact the digital team"
EMAILS = ("ada@example.gov",)


# ---------------------------------------------------------------------------
# Pages, layout and spans
# ---------------------------------------------------------------------------


def _chunks(page_id, text):
    out, pos = [], 0
    pieces = text.split(SEP)
    for i, piece in enumerate(pieces):
        body = piece + (SEP if i < len(pieces) - 1 else "")
        out.append(Chunk(f"{page_id}#p{i}", page_id, pos, pos + len(body), body, 20))
        pos += len(body)
    return out


@pytest.fixture(autouse=True)
def _paragraph_layout(monkeypatch):
    monkeypatch.setattr(jpc, "plan_layout", lambda page, config, s: _chunks(page.page_id, page.text))


class Page:
    """One declared rendered page with its activities (name, tool, sentence)."""

    def __init__(self, inst, pid, paragraphs, activities=(), chrome=None, emails=()):
        self.inst, self.pid, self.text = inst, pid, SEP.join(paragraphs)
        self.url = f"https://{inst.lower()}.example.gov/{pid}"
        self.activities = list(activities)  # (aid, name, tool, sentence, last_sentence or None)
        self.input = jpc.PageInput(pid, inst, f"Council {inst}", "Australia", "local", self.url, f"Page {pid}",
                                   self.text, chrome, email_links=tuple(emails) if chrome is not None else None)

    def spans(self):
        chunks = _chunks(self.pid, self.text)
        out = []
        for aid, name, tool, first, last in self.activities:
            start = self.text.index(first)
            end = self.text.index(last or first) + len(last or first)
            chunk = next(c for c in chunks if c.start <= start < c.end)
            fields = (FieldValue("core.activity_name", name, chunk.chunk_id, first),
                      FieldValue("core.tool_name", tool, chunk.chunk_id, first))
            out.append(ActivitySpan(aid, chunk.chunk_id, start, end, "resolved", first[:20], (last or first)[-20:],
                                    fields))
        return tuple(out)

    def sources(self):
        return PageSources(self.pid, {c.chunk_id: c.text for c in _chunks(self.pid, self.text)},
                           jpc.contact_text(self.input))


class OwnGroup(dict):
    """Declared fixture: every source claim is its own independence group (P15 producer absent)."""

    def __missing__(self, key):
        return key


def _no_quote_value(item, value):
    return value == "no" or value in FIELDS[item]["missing_tokens"] or str(value).startswith("none")


class World:
    """The declared run: pages, fake providers, explicit upstream values."""

    def __init__(self, run_dir, bound, instrument, pages, *, withhold=()):
        self.run_dir, self.bound, self.instrument = run_dir, bound, instrument
        self.pages = {p.pid: p for p in pages}
        self.withhold = set(withhold)  # (page_id, activity_id|None, item_id, chunk_id): no quote returned
        self.support_calls = []
        self.log = []  # shared event order: ("jev", qids, activity name) / ("support", kind, items)
        self.n = 0

    # --- the support provider (fake quote steps + fake X35 + the real T-024 check) ---

    def _check(self, pid, rec, aid=None, linked=None):
        page = self.pages[pid]
        ps = page.sources()
        withheld = (pid, aid, rec.item_id, rec.chunk_id) in self.withhold
        quote = None if withheld else ps.parts[rec.chunk_id].strip()
        return check_code(CodeEvidence(rec.item_id, rec.chosen_value, rec.chunk_id, part=rec.item_part,
                                       probability=rec.confidence, quote=quote,
                                       quote_chunk_id=rec.chunk_id if quote else None,
                                       entailment=TRUE if quote else None, activity_id=aid,
                                       linked_activity=linked), ps)

    def page_support(self, page, result, records):
        self.support_calls.append(("page", page.page_id, [r.item_id for r in records]))
        self.log.append(("support", page.page_id, [r.item_id for r in records]))
        return [self._check(page.page_id, r) for r in records]

    def activity_input(self, page, page_round):
        p = self.pages[page.page_id]
        if not p.activities:
            return None
        return ActivityPageInput(jpc.to_pass1_page(page_round.result, page), "Australia", "local", p.spans())

    def activity_support(self, inp, result, records):
        self.support_calls.append(("activity", inp.page.page_id, [(a, r.item_id) for a, r in records]))
        self.log.append(("support", inp.page.page_id, [r.item_id for _, r in records]))
        return [self._check(inp.page.page_id, r, aid) for a, r in records for aid in [a]]

    def pair_support(self, inp, result):
        out = []
        for pair in result.pairs:
            for rec in pair.records:
                if rec.chosen_value != pp.NOT_COVERED:
                    out.append(self._check(inp.page.page_id, rec, pair.activity_id, pair.linked_activity))
        return out

    def providers(self):
        return pp.PerPageProviders(self.page_support, self.activity_input, self.activity_support, self.pair_support)

    # --- explicit upstream values (declared fixtures) ---

    def _code(self, pid, aid, item, value, text):
        page = self.pages[pid]
        ps = page.sources()
        chunk = next(c for c in _chunks(pid, page.text) if text is None or text in c.text)
        quote = None if _no_quote_value(item, value) else text
        sr = check_code(CodeEvidence(item, value, chunk.chunk_id, probability=0.95, quote=quote,
                                     quote_chunk_id=chunk.chunk_id if quote else None,
                                     entailment=TRUE if quote else None, activity_id=aid), ps)
        self.n += 1
        context = dict(item_id=item, item_part=None, support_id=None, observation_id=None, chunk_id=chunk.chunk_id,
                       coder_version="fake-upstream-v1", question_set_version=QSV,
                       setup_pointer=self.instrument["instrument_id"])
        if FIELDS[item]["coder"] == "classifier":  # core.source_type: T-015's classifier
            res = JevResult({"Q": JevAnswer("Q", "choice", choice=value, confidence=0.95,
                                            probabilities={value: 0.95})}, "fake-jev-response", f"up-{self.n}", 1, 1)
            rec = CoderRecord.from_jev(res, question_id="Q", configured_model="fake-jev",
                                       classifier_rule=self.bound.activity_config.rules[(item, None)], **context)
        else:
            rec = CoderRecord(question_id=None, coder_type="quote_step", configured_model="fake-extractor",
                              actual_response_model="fake-extractor-response", request_id=f"x-{self.n}",
                              answer_type="extracted", chosen_value=value, confidence=None,
                              probability_distribution=None, **context)
        return sr, rec

    def upstream(self, pid):
        page = self.pages[pid]
        artifact = Path("pages") / page.inst / f"{pid}.txt"
        chrome = jpc.contact_text(page.input)
        stored = page.text + ("\n" + chrome if chrome else "")
        (self.run_dir / artifact).parent.mkdir(parents=True, exist_ok=True)
        (self.run_dir / artifact).write_bytes(stored.encode("utf-8"))
        segments = {c.chunk_id: (c.start, c.end) for c in _chunks(pid, page.text)}
        if chrome:
            segments[f"{pid}#chrome"] = (len(page.text) + 1, len(stored))
        a_vals, s_vals, codes = {}, {}, {}
        for aid, name, tool, first, _ in page.activities:
            av = {k: v for k, v in _values("activities").items()
                  if k in pp.ACTIVITY_ITEMS and FIELDS[k]["coder"] != "classifier"}
            av.update({"core.activity_name": name, "core.tool_name": [tool], "core.reported_outcomes": [],
                       "core.deployment_scale_number": "not_documented"})
            sv = {k: v for k, v in _values("sources").items()
                  if k in pp.SOURCE_ITEMS and (FIELDS[k]["coder"] != "classifier" or k == "core.source_type")}
            sv.update({"core.source_url": page.url, "core.source_title": f"Page {pid}",
                       "core.content_contact_emails": list(page.input.email_links or ()),
                       "core.source_publication_date": "not_documented"})
            sample = first
            c = [self._code(pid, aid, "core.activity_name", name, sample),
                 self._code(pid, aid, "core.tool_name", tool, sample),
                 self._code(pid, aid, "core.observed_actor_name", av["core.observed_actor_name"], None),
                 self._code(pid, aid, "core.contracting_party", av["core.contracting_party"], None),
                 self._code(pid, aid, "core.deployment_scale_number", "not_documented", None),
                 self._code(pid, aid, "core.source_type", sv["core.source_type"], sample),
                 self._code(pid, aid, "core.source_publication_date", "not_documented", None),
                 self._code(pid, aid, "core.source_snippet", sv["core.source_snippet"], None)]
            a_vals[aid], s_vals[aid], codes[aid] = av, sv, c
        if not page.activities:  # RC-D-030 Y2 a: the page-level source row's upstream values and codes
            sv = {k: v for k, v in _values("sources").items()
                  if k in pp.SOURCE_ITEMS and (FIELDS[k]["coder"] != "classifier" or k == "core.source_type")}
            sv.update({"core.source_url": page.url, "core.source_title": f"Page {pid}",
                       "core.content_contact_emails": [], "core.source_publication_date": "not_documented"})
            s_vals[pp.NO_ACTIVITY] = sv
            codes[pp.NO_ACTIVITY] = [
                self._code(pid, None, "core.source_type", sv["core.source_type"], page.text.split(SEP)[0]),
                self._code(pid, None, "core.source_publication_date", "not_documented", None),
                self._code(pid, None, "core.source_snippet", sv["core.source_snippet"], None)]
        return pp.PageUpstream(artifact.as_posix(), segments, False, a_vals, s_vals, codes)

    def institution(self, inst, merged=None):
        pages = [p for p in self.pages.values() if p.inst == inst]
        identity = {"institution_id": inst, "institution_name": f"Council {inst}", "country": "Australia",
                    "branch_of_government": "executive", "level_of_government": "local",
                    "institution_search_languages": "en"}
        up = pp.InstitutionUpstream(OwnGroup(), merged, lambda sr: [])
        return pp.PerPageInstitution(RUN_ID, uid_for(inst), identity, "AU",
                                     [pp.PageSpec(p.input, self.upstream(p.pid)) for p in pages], up)


# ---------------------------------------------------------------------------
# The fake jev (per-page and Stage 6 questions)
# ---------------------------------------------------------------------------


def _default(codes):
    return next(c for c in ("not_documented", "unknown", "no", "none_documented", *codes) if c in codes)


class FakeJev:
    """``answers[qid]`` is a value or ``f(state) -> value | None``; default: a no-evidence code.

    Request ids hash the request, so a resumed run reproduces the reference bytes.
    """

    def __init__(self, answers=None, relations=None, fail=None):
        self.answers, self.relations, self.fail = answers or {}, relations or {}, fail
        self.calls = []
        self.log = None
        self.answered = []  # requests that returned a response (failed/interrupted ones are not here)

    def __call__(self, state, questions):
        self.calls.append((json.loads(json.dumps(state)), sorted(questions)))
        if self.log is not None:
            self.log.append(("jev", sorted(questions), state.get("activity_name")))
        if self.fail is not None:
            exc = self.fail(state, questions, len(self.calls))
            if exc is not None:
                raise exc
        out = {}
        for qid, q in questions.items():
            codes = list(q["criteria"])
            if qid == s6.RELATION_ITEM:
                value = self.relations[(state["first_record"]["activity_name"],
                                        state["second_record"]["activity_name"])]
            else:
                pick = self.answers.get(qid)
                value = pick(state) if callable(pick) else pick
                if value is None:
                    value = _default(codes)
            assert value in codes, (qid, value)
            out[qid] = JevAnswer(qid, "choice", choice=value, confidence=0.95, probabilities={value: 0.95})
        rid = sha256_text(canonical_json({"state": state, "questions": questions}))[:16]
        self.answered.append(self.calls[-1])
        return JevResult(out, "fake-jev-response", f"j-{rid}", 10, 2)


def _by_name(table, default=None):
    """Activity answer by the state's activity name (and page part, when the value is a mapping)."""
    def pick(state):
        value = table.get(state.get("activity_name"), default)
        if isinstance(value, dict):
            return value.get(state["page_part"].split(" of ")[0])
        return value
    return pick


NC = "not covered by this part"
ANSWERS = {
    jpc.VERDICT: "confirms_activity",
    "core.disclosure_form": "informal_official",
    "core.activity_type": _by_name({"Copilot drafting": "internal_operational", "Chatbot policy": "policy_guidance",
                                    "Resident chatbot": "public_facing_service", "Bin rules": "policy_guidance",
                                    "Eval bot": "internal_operational"}),
    "core.action_type": _by_name({"Chatbot policy": "governance", "Bin rules": "governance"}, "deployment"),
    "core.adoption_stage": _by_name({"Copilot drafting": "pilot"}),
    "core.evaluation_documented": _by_name({"Eval bot": {"1": "results_reported", "2": "not_documented", "3": NC}}),
    s6.RELATION_ITEM: None,
    "core.activity_segment": "governs",
}
RELATIONS = {("Copilot drafting", "Copilot drafting"): "same_activity", ("Bin rules", "Eval bot"): "distinct_action"}


# ---------------------------------------------------------------------------
# The declared run
# ---------------------------------------------------------------------------


P1 = "The council deployed Copilot for drafting letters in 2025."
P2 = "Council staff now draft letters with Copilot every day."
P3 = "The council adopted a policy that governs chatbot use."
P4 = "A public chatbot answers resident questions about bins."
P5 = "The council adopted rules for bin collection chatbots."
E1, E2, E3 = ("EVAL The evaluation bot was evaluated with reported results.",
              "EVAL The evaluation bot is used by staff.", "EVAL The evaluation bot ends here.")


def _pages():
    a = [Page("INST-0000001", "p1", ["Council information.", P1], [("a1", "Copilot drafting", "Copilot", P1, None)],
              chrome=CHROME, emails=EMAILS),
         Page("INST-0000001", "p2", [P2], [("a1", "Copilot drafting", "Copilot", P2, None)]),
         Page("INST-0000001", "p3", [P3, P4], [("a1", "Chatbot policy", "Policy", P3, None),
                                               ("a2", "Resident chatbot", "Binbot", P4, None)])]
    # A021-16 (b1: policy_guidance downgraded -> unknown opens model_origin) and A021-15 (b2: a part's
    # results_reported downgraded -> not_documented closes the evaluation types).
    b = [Page("INST-0000002", "b1", [P5], [("a1", "Bin rules", "Rulebook", P5, None)]),
         Page("INST-0000002", "b2", [E1, E2, E3], [("a1", "Eval bot", "Evalbot", E1, E3)])]
    # 75% count boundary: c1 has 2 of 4 verdict parts failed (coded), c2 has 3 of 4 (page fails).
    c = [Page("INST-0000003", "c1", ["FAIL one.", "FAIL two.", "Council text.", P1],
              [("a1", "Copilot drafting", "Copilot", P1, None)]),
         Page("INST-0000003", "c2", ["FAIL one.", "FAIL two.", "FAIL three.", "Council text."])]
    return a + b + c


WITHHOLD = {("b1", "a1", "core.activity_type", "b1#p0"), ("b2", "a1", "core.evaluation_documented", "b2#p0")}


def _fail_verdict(state, questions, n):
    if jpc.VERDICT in questions and state["page_text"].startswith("FAIL"):
        return RuntimeError("simulated part failure")
    return None


def _setup(tmp_path, name="run"):
    run_dir = tmp_path / name
    bound = bind_runtime(run_dir, SETTINGS)
    instrument = load_instrument(run_dir / "final" / "instruments", bound.instrument_id)
    world = World(run_dir, bound, instrument, _pages(), withhold=WITHHOLD)
    merged = None
    insts = [world.institution("INST-0000001", merged), world.institution("INST-0000002"),
             world.institution("INST-0000003")]
    return run_dir, bound, instrument, world, insts


def _with_merged(inst, ready):
    """Merged values with no rule computable from the merged row (RC-D-030 X1 R1 refused / unruled):
    a declared fixture."""
    st = next(i for i in ready if i.institution_id == inst)
    o1, o2 = pp.observation_id("p1", "a1"), pp.observation_id("p2", "a1")
    merged = {(o1, o2): {k: v for k, v in st.observation_inputs[o1].row["values"].items()
                         if k in rt.MERGE_INPUT_ITEMS}}
    from dataclasses import replace
    return [replace(i, merged_values=merged) if i.institution_id == inst else i for i in ready]


class FakeQuotes:
    def __init__(self):
        self.calls = 0

    def __call__(self, req):
        self.calls += 1
        first = req.candidates[0]
        return s6.Stage6Quote(first.quote_text, first.support_id, TRUE, {"fake": True})


def _perpage(run_dir, bound, instrument, world, insts, jev):
    return pp.run_perpage_v27(run_dir, insts, ask_fn=jev, providers=world.providers(),
                              page_config=bound.page_config, activity_config=bound.activity_config,
                              instrument=instrument)


def _full(run_dir, bound, instrument, world, insts, jev=None):
    jev = jev or FakeJev(ANSWERS, RELATIONS, _fail_verdict)
    jev.log = world.log
    ready, metrics = _perpage(run_dir, bound, instrument, world, insts, jev)
    ready = _with_merged("INST-0000001", ready)
    s6m = rt.run_stage6_v27(run_dir, ready, ask_fn=jev, quote_fn=FakeQuotes(), config=bound.stage6_config(),
                            instrument=instrument, now=CLOCK, test_only_unbound_quote_fn=True)
    return jev, ready, metrics, s6m


def _csvs(run_dir, insts):
    write_manifest(run_dir, {"run_id": RUN_ID, "institutions": [i.institution_id for i in insts],
                             "storage_contract": {"codebook_release": "2.7"}})
    result = write_run_csvs(run_dir, run_id=RUN_ID, run_model="fake-jev", run_date="2026-11-10")
    rows = {}
    for key, out in result["outputs"].items():
        with Path(out["path"]).open(encoding="utf-8", newline="") as stream:
            rows[key] = list(csv.DictReader(stream))
    return result, rows


def b2_inst_regated(run_dir, world):
    doc = json.loads((institution_dir(run_dir, "INST-0000002") / pp.WORK_DIR / pp.url_hash(world.pages["b2"].url)
                      / "activity.json").read_text(encoding="utf-8"))
    act = doc["result"]["activities"][0]
    return {r["item_id"] for r in act["records"] if r["coder_type"] == "classifier"}


def _storage(run_dir, inst):
    return json.loads((institution_dir(run_dir, inst) / "6_storage.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_support_result_roundtrip():
    page = Page("I", "x", [P1])
    rec = CoderRecord(item_id="core.activity_name", item_part=None, question_id=None, support_id=None,
                      observation_id=None, chunk_id="x#p0", coder_type="quote_step", coder_version="v",
                      configured_model="m", actual_response_model="m", request_id="r", question_set_version=QSV,
                      setup_pointer="a" * 64, answer_type="extracted", chosen_value="Copilot", confidence=None,
                      probability_distribution=None)
    world = World(None, None, None, [page])
    sr = world._check("x", rec, "a1", "a2")
    assert sr.match is not None
    assert pp.support_from_dict(json.loads(json.dumps(pp.support_to_dict(sr)))) == sr


def test_e2e_perpage_to_final_csvs(tmp_path):
    run_dir, bound, instrument, world, insts = _setup(tmp_path)
    jev, ready, metrics, s6m = _full(run_dir, bound, instrument, world, insts)
    assert metrics.ready == ["INST-0000001", "INST-0000002", "INST-0000003"] and not metrics.held
    assert s6m.written == ["INST-0000001", "INST-0000002", "INST-0000003"] and not s6m.held

    # Rendered contact: the stored chrome followed by the stored e-mails reaches the chrome questions.
    chrome_states = [s for s, q in jev.calls if s.get("page_url", "").endswith("/p1") and jpc.CHROME_STATE_FIELD in s]
    assert chrome_states and all(s[jpc.CHROME_STATE_FIELD] == CHROME + "\nada@example.gov" for s in chrome_states)
    assert all(jpc.CHROME_STATE_FIELD not in s for s, q in jev.calls if jpc.VERDICT in q)

    # 75% boundary by count through the real stage: c2 (3 of 4) fails, c1 (2 of 4) is coded.
    assert metrics.failed_pages == ["c2"]
    ledger = attrition.read_records(run_dir)
    c2_ledger = [r for r in ledger if r.get("url", "").endswith("/c2")]
    assert [(r["stage"], r["detail"]) for r in c2_ledger] == [
        (stage_page_code.STAGE, "3/4 verdict parts failed (at least 75%)")]
    assert [r["reason"] for r in ledger if r.get("url", "").endswith("/c1")] == [stage_page_code.PART_FAILURES]
    c1 = jpc.PageCodeResult.from_dict(json.loads((institution_dir(run_dir, "INST-0000003") / pp.WORK_DIR /
                                                  pp.url_hash(world.pages["c1"].url) / "page.json")
                                                 .read_text(encoding="utf-8"))["result"])
    assert len([f for f in c1.failures if jpc.VERDICT in f["question_ids"]]) == 2
    c_inst = next(i for i in ready if i.institution_id == "INST-0000003")
    c2 = next(p for p in c_inst.pages if p.page_id == "c2")
    assert (c2.reviewed, c2.failed, c2.failure_reason) == (False, True, c2_ledger[0]["reason"])

    # A021-16: the downgrade opens model_origin; it is asked after the support check, before finalization.
    b_inst = next(i for i in ready if i.institution_id == "INST-0000002")
    b1 = next(o for o in b_inst.observations if o.observation_id == "b1.a1")
    values = {o.item_id: o.value for o in b1.final_outcomes.values()}
    assert values["core.activity_type"] == "unknown"
    assert values["core.model_origin"] == "not_documented"
    log = world.log
    origin = [n for n, e in enumerate(log) if e == ("jev", ["core.model_origin"], "Bin rules")]
    downgraded = [n for n, e in enumerate(log) if e[0] == "support" and e[1] == "b1"
                  and "core.activity_type" in e[2]]
    origin_checked = [n for n, e in enumerate(log) if e == ("support", "b1", ["core.model_origin"])]
    assert len(origin) == 1 and downgraded and origin_checked  # an actual extra request, then its check
    assert downgraded[0] < origin[0] < origin_checked[0]  # support check -> recombine -> extra round -> check
    # A021-15: recombination after support closes the evaluation types (set by rule, raw answers kept).
    b2 = next(o for o in b_inst.observations if o.observation_id == "b2.a1")
    b2_values = {o.item_id: o.value for o in b2.final_outcomes.values()}
    assert b2_values["core.evaluation_documented"] == "not_documented"
    assert b2_values["core.evaluation_type_user_feedback"] == "not_asked"
    assert any(e[0] == "jev" and e[2] == "Eval bot" and "core.evaluation_type_user_feedback" in e[1]
               for e in log)  # asked on the provisional gate; raw answers kept, unpublished
    assert "core.evaluation_type_user_feedback" in b2_inst_regated(run_dir, world)
    b2_source = next(r for r in b_inst.sources.values() if r["observation_ids"] == ["b2.a1"])
    feedback = [s for s in b2_source["item_support"] if s["item_id"] == "core.evaluation_type_user_feedback"]
    assert any(s["support_status"] == "set_by_rule" and s["value_json"] == "not_asked" for s in feedback)

    # T-023 pair: support checked on the five-field key and finalized; the decision reaches storage.
    acts = _storage(run_dir, "INST-0000001")["activities"]
    relations = {(r["lhs_observation_id"], r["rhs_observation_id"]): r for a in acts.values()
                 for r in a["activity_relations"]}
    assert relations[("p3.a1", "p3.a2")]["relation"] == "governs"
    assert relations[("p3.a1", "p3.a2")]["relation_scope"] == "within_page"
    assert relations[("p1.a1", "p2.a1")]["relation"] == "same_activity"
    assert sorted(tuple(a["observation_ids"]) for a in acts.values()) == [("p1.a1", "p2.a1"), ("p3.a1",), ("p3.a2",)]

    result, rows = _csvs(run_dir, insts)
    assert result["integrity"]["is_valid"]
    assert all(r["setup_pointer"] == bound.instrument_id for t in rows.values() for r in t)
    contact = [r for r in rows["activity_sources"] if r["source_url"].endswith("/p1")]
    assert contact and "example.gov" in contact[0]["contact_email_domain_counts_json"]


def test_e2e_pending_extra_round_holds_then_resume_publishes(tmp_path):
    run_dir, bound, instrument, world, insts = _setup(tmp_path)
    b = [i for i in insts if i.institution_id == "INST-0000002"]

    def fail_origin(state, questions, n):
        return RuntimeError("extra round down") if list(questions) == ["core.model_origin"] else None
    jev = FakeJev(ANSWERS, RELATIONS, fail_origin)
    ready, metrics = _perpage(run_dir, bound, instrument, world, b, jev)
    assert not ready and metrics.held == ["INST-0000002"]
    inst_dir = institution_dir(run_dir, "INST-0000002")
    held = json.loads((inst_dir / pp.WORK_DIR / pp.HELD_FILE).read_text(encoding="utf-8"))
    assert held["held"][0]["stage"] == "activity_rounds"
    assert any(r["reason"] == pp.HELD_REASON for r in attrition.read_records(run_dir))
    jev2 = FakeJev(ANSWERS, RELATIONS)
    ready, metrics = _perpage(run_dir, bound, instrument, world, b, jev2)
    assert [i.institution_id for i in ready] == ["INST-0000002"]
    assert not (inst_dir / pp.WORK_DIR / pp.HELD_FILE).exists()
    assert all(q == ["core.model_origin"] or "core.model_origin" not in q for _, q in jev2.calls)
    assert not any(jpc.VERDICT in q for _, q in jev2.calls)  # coded pages are not re-asked


@pytest.mark.parametrize("stop_at", [5, 40, 82])
def test_e2e_interruption_resume_matches_uninterrupted_run(tmp_path, stop_at):
    ref_dir, ref_bound, ref_instrument, ref_world, ref = _setup(tmp_path, "reference")
    ref_jev, *_ = _full(ref_dir, ref_bound, ref_instrument, ref_world, ref)

    run_dir, bound, instrument, world, insts = _setup(tmp_path, "interrupted")
    assert bound.instrument_id == ref_bound.instrument_id

    def stop(state, questions, n):
        if n == stop_at:
            return JevAccountError("simulated interruption: account stopped")
        return _fail_verdict(state, questions, n)
    first = FakeJev(ANSWERS, RELATIONS, stop)
    with pytest.raises(JevAccountError):
        _full(run_dir, bound, instrument, world, insts, first)
    in_stage6 = (institution_dir(run_dir, "INST-0000001") / rt.WORK_DIR / rt.JOURNAL).exists()
    assert in_stage6 == (stop_at > 80)  # 5, 40: per-page stage (40: B's extra rounds); 82: Stage 6
    jev, ready, metrics, s6m = _full(run_dir, bound, instrument, world, insts)
    assert s6m.written == ["INST-0000001", "INST-0000002", "INST-0000003"]
    # No answered request is asked again, none is dropped: the two runs answer exactly the reference set.
    key = canonical_json
    assert sorted(map(key, first.answered + jev.answered)) == sorted(map(key, ref_jev.answered))
    for inst in ("INST-0000001", "INST-0000002", "INST-0000003"):
        for name in ("6_storage.json", "6_validate.json", "6_support_provenance.json"):
            assert ((institution_dir(run_dir, inst) / name).read_bytes()
                    == (institution_dir(ref_dir, inst) / name).read_bytes().replace(b"reference", b"interrupted"))


def test_perpage_refuses_absent_upstream(tmp_path):
    run_dir, bound, instrument, world, insts = _setup(tmp_path)
    a = next(i for i in insts if i.institution_id == "INST-0000001")
    from dataclasses import replace
    spec = replace(a.pages[0], upstream=replace(a.pages[0].upstream, followed=None))
    broken = replace(a, pages=[spec, *a.pages[1:]])
    with pytest.raises(pp.MissingUpstreamError, match="follow"):
        _perpage(run_dir, bound, instrument, world, [broken], FakeJev(ANSWERS, RELATIONS))


def test_cost_stop_is_not_a_page_failure_and_resumes(tmp_path):
    run_dir, bound, instrument, world, insts = _setup(tmp_path)
    c = [i for i in insts if i.institution_id == "INST-0000003"]
    calls = []

    def budget(stage, usage):
        calls.append(stage)
        return len(calls) < 2
    with pytest.raises(stage_page_code.StageStopped):
        pp.run_perpage_v27(run_dir, c, ask_fn=FakeJev(ANSWERS, RELATIONS, _fail_verdict), providers=world.providers(),
                           page_config=bound.page_config, activity_config=bound.activity_config,
                           instrument=instrument, cost_check_callback=budget)
    assert not any(r["reason"] == pp.HELD_REASON for r in attrition.read_records(run_dir))
    ready, metrics = _perpage(run_dir, bound, instrument, world, c, FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert [i.institution_id for i in ready] == ["INST-0000003"] and metrics.failed_pages == ["c2"]


# ---------------------------------------------------------------------------
# RC-D-030 rulings
# ---------------------------------------------------------------------------


def test_y1_supported_is_derived_from_activity_and_action_type(tmp_path):
    """Y1 b: supported = final activity_type and action_type both supported (no explicit input)."""
    run_dir, bound, instrument, world, insts = _setup(tmp_path)
    ready, _ = _perpage(run_dir, bound, instrument, world, insts[:2], FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    obs = {o.observation_id: o for i in ready for o in i.observations}
    assert obs["p1.a1"].supported and obs["p3.a2"].supported and obs["b2.a1"].supported
    assert not obs["b1.a1"].supported  # activity_type downgraded (no quote) -> unknown
    assert "supported" not in {f.name for f in __import__("dataclasses").fields(pp.PageUpstream)}


def test_y1_observation_supported_unit():
    from g3o.classify.jev_activity_code import ItemOutcome
    from g3o.common.support_check import SupportResult

    def sr(item, status, value):
        return SupportResult(item_id=item, part=None, activity_id="a1", chunk_id="c0", original_value=value,
                             value=value, support_status=status, support_status_second_reason=None,
                             support_rule_name=None, supporting_text="q" if status == "supported" else None,
                             quote_chunk_id="c0", match=None, chosen_answer_probability=0.9, entailment=None)
    out = {"t": ItemOutcome("t", "core.activity_type", None, "combined", "internal_operational", part_id="c0"),
           "a": ItemOutcome("a", "core.action_type", None, "combined", "deployment", part_id="c0")}
    support = {("a1", "core.activity_type", None, "c0", None): sr("core.activity_type", "supported",
                                                                   "internal_operational"),
               ("a1", "core.action_type", None, "c0", None): sr("core.action_type", "supported", "deployment")}
    assert pp.observation_supported("a1", out, support)
    low = dict(support)
    low[("a1", "core.action_type", None, "c0", None)] = sr("core.action_type", "downgraded_low_confidence",
                                                            "deployment")
    assert not pp.observation_supported("a1", out, low)
    gated = {**out, "a": ItemOutcome("a", "core.action_type", None, "gated_out", "not_asked")}
    assert not pp.observation_supported("a1", gated, support)
    failed = {**out, "t": ItemOutcome("t", "core.activity_type", None, "combined", "unknown", True, part_id="c0")}
    assert not pp.observation_supported("a1", failed, support)


def test_y5_within_page_decision_rule():
    """Y5 a: one relation -> it (lowest probability of the parts choosing it; supported only if all are);
    more than one value, or a value no part chose -> no decision (Stage 6 holds the pair)."""
    from g3o.classify.jev_activity_code import ItemOutcome, PairResult
    from g3o.common.support_check import SupportResult

    def rec(value, p):
        res = JevResult({"q": JevAnswer("q", "choice", choice=value, confidence=p, probabilities={value: p})},
                        "m", "r", 1, 1)
        return CoderRecord.from_jev(res, question_id="q", item_id="core.activity_segment", item_part=None,
                                    support_id=None, observation_id=None, chunk_id="c", coder_version="v",
                                    configured_model="m", question_set_version=QSV, setup_pointer="a" * 64,
                                    classifier_rule=None)

    def sr(value, status):
        return SupportResult(item_id="core.activity_segment", part=None, activity_id="a1", chunk_id="c",
                             original_value=value, value=value, support_status=status,
                             support_status_second_reason=None, support_rule_name=None, supporting_text=None,
                             quote_chunk_id=None, match=None, chosen_answer_probability=None, entailment=None)

    def pair(value, state="combined"):
        return PairResult("a1", "a2", ("c0", "c1"), (1, 2),
                          ItemOutcome("q", "core.activity_segment", None, state, value), ())
    both = [(rec("governs", 0.95), sr("governs", "supported")), (rec("governs", 0.85), sr("governs", "supported"))]
    assert pp.within_page_decision(pair(["governs"]), both) == ("governs", 0.85, "supported")
    assert pp.within_page_decision(pair("governs"), both) == ("governs", 0.85, "supported")
    mixed = [both[0], (rec("governs", 0.9), sr("governs", "downgraded_no_quote"))]
    assert pp.within_page_decision(pair(["governs"]), mixed) == ("governs", 0.9, "downgraded_no_quote")
    assert pp.within_page_decision(pair(["governs", "same_activity"]), both) is None
    assert pp.within_page_decision(pair(["unknown"]), both) is None  # no part chose it
    assert pp.within_page_decision(pair(None, "stopped"), both) is None


def test_y3_uncarried_combined_value_is_a_per_institution_hold(tmp_path):
    """Y3 b: every part of b2 gives the temporary answer to adoption_stage, so the combined value
    (not documented) is carried by no part node: INST-0000002 is held, not a crash; others go on."""
    run_dir, bound, instrument, world, insts = _setup(tmp_path)
    answers = {**ANSWERS, "core.adoption_stage": _by_name({"Copilot drafting": "pilot",
                                                            "Eval bot": {"1": NC, "2": NC, "3": NC}})}
    ready, metrics = _perpage(run_dir, bound, instrument, world, insts, FakeJev(answers, RELATIONS, _fail_verdict))
    assert metrics.held == ["INST-0000002"]
    assert [i.institution_id for i in ready] == ["INST-0000001", "INST-0000003"]
    held = json.loads((institution_dir(run_dir, "INST-0000002") / pp.WORK_DIR / pp.HELD_FILE)
                      .read_text(encoding="utf-8"))
    (hold,) = held["held"]
    assert hold["page_id"] == "b2" and hold["stage"] == pp.UNCARRIED_STAGE
    assert any(i.startswith("core.adoption_stage/") for i in hold["items"])
    assert any(r["reason"] == pp.HELD_REASON and r["detail"] == f"b2:{pp.UNCARRIED_STAGE}"
               for r in attrition.read_records(run_dir))


def test_y2_reviewed_page_with_no_activity_gets_a_page_level_na_source_row(tmp_path):
    """Y2 a: a reviewed page with no activity -> one source row, activity_id _NA_, empty observation_ids,
    through Stage 6 storage and the final CSVs; the activity-question source items are _NA_ by rule."""
    run_dir, bound, instrument, world, _ = _setup(tmp_path)
    world.pages["n1"] = Page("INST-0000009", "n1", ["The council does not use generative AI."])
    world.pages["n2"] = Page("INST-0000009", "n2", [P1], [("a1", "Copilot drafting", "Copilot", P1, None)])
    inst = world.institution("INST-0000009")
    verdict = lambda st: "no_genai" if "generative AI" in st.get("page_text", "") else "confirms_activity"  # noqa: E731
    jev = FakeJev({**ANSWERS, jpc.VERDICT: verdict}, RELATIONS)
    ready, metrics = _perpage(run_dir, bound, instrument, world, [inst], jev)
    assert metrics.ready == ["INST-0000009"]
    (st,) = ready
    n1 = next(p for p in st.pages if p.page_id == "n1")
    assert n1.reviewed and n1.page_verdict == "no_genai" and len(n1.source_ids) == 1
    row = st.sources[n1.source_ids[0]]
    assert row["observation_ids"] == []
    assert all(n["observation_id"] is None and n["source_id"] == n1.source_ids[0] for n in row["item_support"])
    assert row["values"]["core.evaluation_documented"] == pp.NO_ACTIVITY
    na = [n for n in row["item_support"] if n["item_id"] == "core.evaluation_documented"]
    assert na and all(n["support_status"] == "set_by_rule" and n["support_rule_name"] == pp.NA_RULE for n in na)
    s6m = rt.run_stage6_v27(run_dir, ready, ask_fn=jev, quote_fn=FakeQuotes(), config=bound.stage6_config(),
                            instrument=instrument, now=CLOCK, test_only_unbound_quote_fn=True)
    assert s6m.written == ["INST-0000009"]
    stored = _storage(run_dir, "INST-0000009")["sources"][n1.source_ids[0]]
    assert stored["activity_id"] == "_NA_" and stored["observation_ids"] == []
    result, rows = _csvs(run_dir, [inst])
    assert result["integrity"]["is_valid"]
    n1_rows = [r for r in rows["activity_sources"] if r["source_url"].endswith("/n1")]
    assert len(n1_rows) == 1 and n1_rows[0]["activity_id"] == "_NA_"
    assert json.loads(n1_rows[0]["observation_ids_json"]) == []



def test_rcd031_a1_pooled_answer_downgraded_for_no_copy_still_stores(tmp_path):
    """RC-D-031 A1 a: the quote step returns no copy for the pooled requests -> the pooled positive
    answers are downgraded (no quote) -> the final downgrade node's source is the pooled original,
    which names its shown inputs; the envelope builds and is stored."""
    run_dir, bound, instrument, world, insts = _setup(tmp_path)
    a = [i for i in insts if i.institution_id == "INST-0000001"]
    jev = FakeJev(ANSWERS, RELATIONS, _fail_verdict)
    ready, _ = _perpage(run_dir, bound, instrument, world, a, jev)
    ready = _with_merged("INST-0000001", ready)

    class NoCopyForPooled(FakeQuotes):
        def __call__(self, req):
            if req.kind == "pooled":
                self.calls += 1
                return s6.Stage6Quote(None, None, None, {"fake": True})
            return super().__call__(req)
    s6m = rt.run_stage6_v27(run_dir, ready, ask_fn=jev, quote_fn=NoCopyForPooled(), config=bound.stage6_config(),
                            instrument=instrument, now=CLOCK, test_only_unbound_quote_fn=True)
    assert s6m.written == ["INST-0000001"] and not s6m.failed
    merged = next(x for x in _storage(run_dir, "INST-0000001")["activities"].values()
                  if x["observation_ids"] == ["p1.a1", "p2.a1"])
    pooled = {s["support_id"]: s for s in merged["item_support"] if s["source_id"] is None
              and s["observation_id"] is None}
    finals = [s for s in pooled.values() if s["passage"].get("downgrade_of")]
    assert finals and all(pooled[f["input_support_ids"][0]]["input_support_ids"] for f in finals)
    assert all(f["support_status"] == "downgraded_no_quote" for f in finals)


def test_rcd031_a1_only_pooled_originals_may_name_inputs():
    from g3o.common.jev_record import pooled_original
    pooled = {"source_id": None, "observation_id": None, "item_id": "core.adoption_stage",
              "input_support_ids": ["x"]}
    assert pooled_original(pooled)
    assert not pooled_original({**pooled, "input_support_ids": []})
    assert not pooled_original({**pooled, "source_id": "S1"})
    assert not pooled_original({**pooled, "observation_id": "p1.a1"})
    assert not pooled_original({**pooled, "item_id": "core.activity_relation_cross_page"})
