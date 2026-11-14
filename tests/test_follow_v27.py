"""T-025 follow leg in the v2.7 per-page stage (g3o.run.presweep.follow_v27): the ``followed`` / hop producer.

No network: every fetch is a fake, every jev / extractor answer is a fake. Covers the leg's rounds
(candidates from the page request's selected links on a page whose final ``core.page_complete`` is
``yes``, provenance, hop), resume (stored state and stored pages: no second fetch, no second paid
call), the Stage 6 entry of attempts not reviewed (PI rulings 79 b / 96 a / 102 a: a failed unreviewed
page and its source row), the A4 regrouping over searched and followed pages, ``discovery_path`` from
the hop, and the dispatch's ``follow_fetch`` seam.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any

import pytest

from g3o.classify.jev_page_code import COMPLETE, ItemOutcome
from g3o.common import attrition
from g3o.common import source_fields as sf
from g3o.common.artifact_io import artifact_exists
from g3o.common.instrument import load_instrument
from g3o.common.jev_client import JevAccountError
from g3o.common.paths import institution_dir
from g3o.extract.batch import url_hash
from g3o.extract.parser_v27 import Pass1Extraction, SelectedLink
from g3o.persist.stage6_adapters import MissingUpstreamError
from g3o.run.presweep import follow_v27 as fv
from g3o.run.presweep import orchestrator as orch
from g3o.run.presweep import perpage_inputs_v27 as pin
from g3o.run.presweep import source_row_v27 as srow
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep import stage_validate_v27 as rt
from g3o.run.presweep.instrument_binding import bind_runtime
from g3o.run.presweep.stage_follow import FetchResult
from g3o.scrape import follow as fl
from g3o.scrape.render import FetchMetadata, RenderedPage
from tests._layout import uid_for
from tests.test_e2e_perpage_v27 import (  # noqa: F401 - _paragraph_layout is an autouse fixture
    ANSWERS,
    RELATIONS,
    RUN_ID,
    SETTINGS,
    FakeJev,
    OwnGroup,
    Page,
    World,
    _paragraph_layout,
)
from tests.test_perpage_inputs_v27 import EN, I1, P_DUP, P_META, P_URL, _built

ACCESS = "2026-11-12"


def rendered(url: str, text: str, *, links=None) -> RenderedPage:
    return RenderedPage(url=url, text=text, title="Followed", content_type="html",
                        fetch_metadata=FetchMetadata(access_date=ACCESS, fetch_method="html"), links=links)


class FakeFetch:
    """``pages`` url -> text (fetched); ``fail`` / ``robots``: URLs not fetched; every call is kept."""

    def __init__(self, pages: dict[str, str], *, fail=(), robots=()):
        self.pages, self.fail, self.robots = pages, set(fail), set(robots)
        self.calls: list[str] = []

    def __call__(self, url: str) -> FetchResult:
        self.calls.append(url)
        if url in self.robots:
            return FetchResult(fv.ROBOTS_DISALLOWED)
        if url in self.fail:
            return FetchResult(fl.FETCH_FAILED)
        return FetchResult(fl.FETCHED, rendered(url, self.pages[url]))


def selection(page, urls, quote="AI pilot"):
    """The T-022 page request of ``page`` selecting ``urls`` among its stored links (``L<nnn>`` by position)."""
    stored = [ln.get("href") or ln.get("url") for ln in page.links]
    links = tuple(SelectedLink(f"L{stored.index(u) + 1:03d}", u, f"{page.page_id}#p0", quote) for u in urls)
    return Pass1Extraction(page_id=page.page_id, custom_id=f"x-{page.page_id}", quotes=(), links=links,
                           activities=(), publication_date=None, link_status=None)


def ledger(run_dir):
    return [(r["stage"], r["reason"], r.get("url")) for r in attrition.read_records(run_dir)
            if r["stage"] == fv.STAGE]


F1, F2 = "https://one.example.gov/report", "https://one.example.gov/annex"


def _one(tmp_path, links=(F1,)):
    """Institution I1 of the D1 a fixture, its first page (P_META) storing ``links``."""
    inst = _built(tmp_path)[I1]
    first = replace(inst.pages[0], page=replace(inst.pages[0].page, links=tuple({"href": u} for u in links)))
    return tmp_path / "run", replace(inst, pages=[first, *inst.pages[1:]])


# ---------------------------------------------------------------------------
# The leg's rounds
# ---------------------------------------------------------------------------


def test_searched_pages_are_followed_false_and_round_records_provenance(tmp_path):
    run_dir, inst = _one(tmp_path)
    assert all(s.upstream.followed is False and s.upstream.hop is None for s in inst.pages)  # ruling 61 a
    fetch = FakeFetch({F1: "The council report on the pilot."})
    leg = fv.FollowLeg(fetch).start(run_dir, inst)
    page = inst.pages[0].page
    out = leg.round([fv.RoundPage(page, "yes", selection(page, [F1]), (EN[:60],)),
                     fv.RoundPage(inst.pages[1].page, "no", None, ())])
    assert fetch.calls == [F1]
    (spec,) = out
    assert (spec.page.page_id, spec.page.url, spec.page.institution) == (url_hash(F1), F1, "Council One")
    assert (spec.upstream.followed, spec.upstream.hop) == (True, 1)
    assert artifact_exists(institution_dir(run_dir, I1) / fv.FOLLOW_DIR / f"{url_hash(F1)}.json")
    doc = json.loads((institution_dir(run_dir, I1) / fv.FOLLOW_DIR / fv.STATE_FILE).read_text(encoding="utf-8"))
    (rec,) = doc["records"]
    assert (rec["parent_page_id"], rec["hop"], rec["outcome"], rec["fetch_date"], rec["release_id"],
            rec["backfill"], rec["counted"]) == (page.page_id, 1, fl.FETCHED, ACCESS, inst.run_id, False, True)
    assert doc["cap"]["cap_reached"] is False and doc["followed"] == 1
    assert leg.unreviewed() == []


def test_final_page_complete_not_yes_offers_no_link(tmp_path):
    """R-031: only a page whose own final core.page_complete is ``yes`` is followed from."""
    run_dir, inst = _one(tmp_path)
    fetch = FakeFetch({F1: "x"})
    page = inst.pages[0].page
    for complete in ("no", "unknown", None):
        assert fv.FollowLeg(fetch).start(run_dir, inst).round(
            [fv.RoundPage(page, complete, selection(page, [F1]), ())]) == []
    assert fetch.calls == []


def test_round_page_reads_final_complete_and_supported_pass1_quotes():
    page_round = SimpleNamespace(
        final=SimpleNamespace(items={COMPLETE: ItemOutcome(COMPLETE, "combined", "yes")}),
        support=(SimpleNamespace(support_status="supported", supporting_text="Quote A"),
                 SimpleNamespace(support_status="downgraded_no_quote", supporting_text="Quote B"),
                 SimpleNamespace(support_status="supported", supporting_text=None),
                 SimpleNamespace(support_status="supported", supporting_text="Quote A")))
    page = SimpleNamespace(links=())
    spec = SimpleNamespace(page=page)
    rp = fv.round_page(spec, page_round, "ext", first_complete="yes")
    assert (rp.page, rp.page_complete, rp.extraction, rp.supported, rp.links_collected) == \
        (page, "yes", "ext", ("Quote A",), True)
    stopped = SimpleNamespace(final=SimpleNamespace(items={COMPLETE: ItemOutcome(COMPLETE, "pending", None)}),
                              support=())
    assert fv.round_page(spec, stopped, None, first_complete="yes").page_complete is None
    # PI ruling 82 c: yes only after an extra round (first request built on another answer), or links not
    # measured: the links were not collected.
    for first in ("no", "unknown", None):
        assert fv.round_page(spec, page_round, "ext", first_complete=first).links_collected is False
    unmeasured = SimpleNamespace(page=SimpleNamespace(links=None))
    assert fv.round_page(unmeasured, page_round, "ext", first_complete="yes").links_collected is False


def test_complete_page_with_links_not_collected_is_recorded_and_not_followed_82c(tmp_path):
    run_dir, inst = _one(tmp_path)
    fetch = FakeFetch({F1: "x"})
    page = inst.pages[0].page
    leg = fv.FollowLeg(fetch).start(run_dir, inst)
    out = leg.round([fv.RoundPage(page, "yes", selection(page, [F1]), (), links_collected=False),
                     fv.RoundPage(inst.pages[1].page, "yes", None, (), links_collected=False)])
    assert out == [] and fetch.calls == [] and leg.unreviewed() == []
    assert set(ledger(run_dir)) == {(fv.STAGE, fv.LINKS_NOT_COLLECTED, page.url),
                                    (fv.STAGE, fv.LINKS_NOT_COLLECTED, inst.pages[1].page.url)}
    # A page whose final answer is not yes is neither followed nor recorded.
    leg.round([fv.RoundPage(inst.pages[2].page, "no", None, (), links_collected=False)])
    assert (fv.STAGE, fv.LINKS_NOT_COLLECTED, inst.pages[2].page.url) not in ledger(run_dir)


def test_resume_reuses_the_state_and_the_stored_page_without_fetching_again(tmp_path):
    run_dir, inst = _one(tmp_path)
    page = inst.pages[0].page
    pages = [fv.RoundPage(page, "yes", selection(page, [F1]), ())]
    fetch = FakeFetch({F1: "The council report."})
    first = fv.FollowLeg(fetch).start(run_dir, inst).round(pages)
    again = fv.FollowLeg(fetch).start(run_dir, inst).round(pages)  # resume: state loaded
    assert fetch.calls == [F1] and again == first
    # Interrupted after the page was stored and before its record: the stored page is used.
    (institution_dir(run_dir, I1) / fv.FOLLOW_DIR / fv.STATE_FILE).unlink()
    third = fv.FollowLeg(fetch).start(run_dir, inst).round(pages)
    assert fetch.calls == [F1] and third == first


def test_stored_state_for_other_rules_is_refused(tmp_path):
    run_dir, inst = _one(tmp_path)
    page = inst.pages[0].page
    fv.FollowLeg(FakeFetch({F1: "x"})).start(run_dir, inst).round(
        [fv.RoundPage(page, "yes", selection(page, [F1]), ())])
    with pytest.raises(ValueError, match="another institution, release, back-fill flag or follow rules"):
        fv.FollowLeg(FakeFetch({}), fl.FollowRules(url_cap=5)).start(run_dir, inst)
    with pytest.raises(ValueError, match="another institution"):
        fv.FollowLeg(FakeFetch({})).start(run_dir, replace(inst, run_id="R-OTHER"))


def test_failed_robots_and_cap_attempts_are_recorded_as_unreviewed(tmp_path):
    """Every URL tried counts against the cap (C-Q5 b); attempts not reviewed are recorded (attrition,
    follow state) and listed for their Stage 6 entry (PI rulings 79 b / 96 a / 102 a)."""
    f3 = "https://one.example.gov/minutes"
    run_dir, inst = _one(tmp_path, links=(F1, F2, f3))
    fetch = FakeFetch({}, fail={F1}, robots={F2})
    leg = fv.FollowLeg(fetch, fl.FollowRules(url_cap=2)).start(run_dir, inst)
    page = inst.pages[0].page
    assert leg.round([fv.RoundPage(page, "yes", selection(page, [F1, F2, f3]), ())]) == []
    assert fetch.calls == [F1, F2]
    attempts = leg.unreviewed()
    assert [(a["url"], a["state"], a["hop"], a["parent_page_id"]) for a in attempts] == [
        (F1, fl.FETCH_FAILED, 1, page.page_id), (F2, fv.ROBOTS_DISALLOWED, 1, page.page_id),
        (f3, fl.LINK_NOT_FOLLOWED_CAP, 1, page.page_id)]
    cap = leg.state.cap_record()
    assert cap.cap_reached is True and cap.followed == 2
    assert set(ledger(run_dir)) == {(fv.STAGE, fl.FETCH_FAILED, F1), (fv.STAGE, fv.ROBOTS_DISALLOWED, F2),
                                    (fv.STAGE, fl.LINK_NOT_FOLLOWED_CAP, f3), (fv.STAGE, fv.CAP_REACHED, None)}
    # A resumed leg tries none of them again (R-034, reading 4) and lists the same attempts.
    again = fv.FollowLeg(fetch, fl.FollowRules(url_cap=2)).start(run_dir, inst)
    again.round([fv.RoundPage(page, "yes", selection(page, [F1, F2, f3]), ())])
    assert fetch.calls == [F1, F2] and again.unreviewed() == attempts


def test_attrition_is_recorded_before_the_state_save_l4(tmp_path, monkeypatch):
    """Review L4: an interruption at the state save never loses the attrition record, and the resume
    that records it again writes nothing new (the ledger dedups)."""
    f3 = "https://one.example.gov/minutes"
    run_dir, inst = _one(tmp_path, links=(F1, F2, f3))
    page = inst.pages[0].page
    pages = [fv.RoundPage(page, "yes", selection(page, [F1, F2, f3]), ())]
    real = fv._atomic_write

    def interrupted(path, text):
        raise OSError("interrupted at the state save")

    monkeypatch.setattr(fv, "_atomic_write", interrupted)
    fetch = FakeFetch({}, fail={F1}, robots={F2})
    with pytest.raises(OSError, match="interrupted"):
        fv.FollowLeg(fetch, fl.FollowRules(url_cap=2)).start(run_dir, inst).round(pages)
    assert not (institution_dir(run_dir, I1) / fv.FOLLOW_DIR / fv.STATE_FILE).exists()
    assert ledger(run_dir) == [(fv.STAGE, fl.FETCH_FAILED, F1)]  # recorded before the save that failed
    monkeypatch.setattr(fv, "_atomic_write", real)
    fv.FollowLeg(fetch, fl.FollowRules(url_cap=2)).start(run_dir, inst).round(pages)
    assert sorted(ledger(run_dir), key=str) == sorted(
        [(fv.STAGE, fl.FETCH_FAILED, F1), (fv.STAGE, fv.ROBOTS_DISALLOWED, F2),
         (fv.STAGE, fl.LINK_NOT_FOLLOWED_CAP, f3), (fv.STAGE, fv.CAP_REACHED, None)], key=str)


def test_hop_limit_and_second_round(tmp_path):
    """A followed page's own links are followed one hop further, up to 3 hops (R-032)."""
    run_dir, inst = _one(tmp_path)
    chain = [F1] + [f"https://one.example.gov/h{n}" for n in range(2, 5)]
    texts = {u: f"Hop page {u}." for u in chain}
    fetch = FakeFetch(texts)

    def fetch_with_links(url):
        res = fetch(url)
        nxt = chain.index(url) + 1
        links = [{"href": chain[nxt]}] if nxt < len(chain) else []
        return FetchResult(res.outcome, res.page.model_copy(update={"links": links}))

    leg = fv.FollowLeg(fetch_with_links).start(run_dir, inst)
    page = inst.pages[0].page
    pages = [fv.RoundPage(page, "yes", selection(page, [F1]), ())]
    hops = []
    while True:
        out = leg.round(pages)
        if not out:
            break
        hops += [s.upstream.hop for s in out]
        pages = [fv.RoundPage(s.page, "yes", selection(s.page, [ln["href"] for ln in s.page.links]), ())
                 for s in out]
    assert hops == [1, 2, 3] and fetch.calls == chain[:3]
    assert [(a["url"], a["state"], a["hop"]) for a in leg.unreviewed()] == [
        (chain[3], fl.LINK_NOT_FOLLOWED_HOPS, 4)]


def test_finish_regroups_a4_over_followed_pages_and_builds_their_page_fields(tmp_path):
    run_dir, inst = _one(tmp_path)
    group = {s.page.page_id: s.upstream.page_fields.syndication_group.value for s in inst.pages}
    meta, dup, url_only = (url_hash(p.url) for p in (P_META, P_DUP, P_URL))
    assert group[meta] == group[dup] != group[url_only]
    leg = fv.FollowLeg(FakeFetch({F1: EN})).start(run_dir, inst)  # the followed page repeats P_META's text
    page = inst.pages[0].page
    (spec,) = leg.round([fv.RoundPage(page, "yes", selection(page, [F1]), ())])
    assert spec.upstream.page_fields is None  # built once every page is known
    done = {s.page.page_id: s for s in leg.finish([*inst.pages, spec])}
    after = {k: s.upstream.page_fields.syndication_group.value for k, s in done.items()}
    assert after[meta] == after[dup] == after[url_hash(F1)] != group[meta]  # A4.2 a: one institution
    assert after[url_only] == group[url_only]
    fields = done[url_hash(F1)].upstream.page_fields
    assert (fields.url.value, fields.access_date.value, fields.text_source.value) == (F1, ACCESS, "new_run")
    assert (done[url_hash(F1)].upstream.followed, done[url_hash(F1)].upstream.hop) == (True, 1)
    rows = srow.assemble(spec.page, fields, {"core.page_verdict": "no_genai", "core.content_contact_named": "no",
                                             "core.content_contact_details": "no"}, {}, followed=True, hop=1)
    assert rows.source[sf.DISCOVERY].value == "followed_hop_1"  # ruling 61 a


def test_start_refuses_followed_input_pages(tmp_path):
    run_dir, inst = _one(tmp_path)
    bad = replace(inst, pages=[replace(inst.pages[0], upstream=replace(inst.pages[0].upstream, followed=True,
                                                                       hop=1))])
    with pytest.raises(ValueError, match="searched pages only"):
        fv.FollowLeg(FakeFetch({})).start(run_dir, bad)
    with pytest.raises(ValueError, match="fetch callable"):
        fv.FollowLeg(None)


# ---------------------------------------------------------------------------
# Inside run_perpage_v27 (fake jev, fake providers, injected row values)
# ---------------------------------------------------------------------------

INST = "INST-0000001"
SEARCHED = "FOLLOW The council deployed Copilot for drafting letters. See the full report."
REPORT = "The report describes how staff draft letters with Copilot."
REPORT_URL = "https://inst-0000001.example.gov/report"


@dataclass(frozen=True)
class FollowProviders(pp.PerPageProviders):
    page_extraction: Any = None


@dataclass(frozen=True)
class WorldLeg(fv.FollowLeg):
    """Declared fixture: a followed page's row values are injected (the T-015 assembler still refuses items)."""

    world: Any = None

    def followed_upstream(self, rendered_page, page, hop, grouping):
        return replace(self.world.upstream(page.page_id), followed=True, hop=hop)


def _follow_world(tmp_path):
    run_dir = tmp_path / "run"
    bound = bind_runtime(run_dir, SETTINGS)
    instrument = load_instrument(run_dir / "final" / "instruments", bound.instrument_id)
    searched = Page(INST, "s1", [SEARCHED], [("a1", "Copilot drafting", "Copilot", SEARCHED, None)])
    searched.input = replace(searched.input, links=({"href": REPORT_URL, "text": "full report"},))
    report = Page(INST, "r", [REPORT])
    rid = url_hash(REPORT_URL)
    report.pid, report.url = rid, REPORT_URL
    report.input = replace(report.input, page_id=rid, url=REPORT_URL, title="Followed")
    world = World(run_dir, bound, instrument, [searched, report])
    identity = {"institution_id": INST, "institution_name": f"Council {INST}", "country": "Australia",
                "branch_of_government": "executive", "level_of_government": "local",
                "institution_search_languages": "en"}
    inst = pp.PerPageInstitution(RUN_ID, uid_for(INST), identity, "Australia",
                                 [pp.PageSpec(searched.input, world.upstream("s1"))],
                                 pp.InstitutionUpstream(OwnGroup(), None))
    link = SelectedLink("L001", REPORT_URL, "s1#p0", "See the full report.")
    extractions = {"s1": Pass1Extraction(page_id="s1", custom_id="x-s1", quotes=(), links=(link,), activities=(),
                                         publication_date=None, link_status=None)}
    base = world.providers()
    providers = FollowProviders(base.page_support, base.activity_input, base.activity_support, base.pair_support,
                                extractions.get)
    return run_dir, bound, instrument, world, inst, providers


def _jev():
    complete = lambda st: "yes" if "FOLLOW" in st.get("page_text", "") else None  # noqa: E731
    verdict = lambda st: "confirms_activity" if "FOLLOW" in st.get("page_text", "") else "no_genai"  # noqa: E731
    return FakeJev({**ANSWERS, COMPLETE: complete, pp.jpc.VERDICT: verdict}, RELATIONS)


def _run(run_dir, bound, instrument, providers, inst, leg, jev):
    return pp.run_perpage_v27(run_dir, [inst], ask_fn=jev, providers=providers, page_config=bound.page_config,
                              activity_config=bound.activity_config, instrument=instrument,
                              test_only_unbound_providers=True, follow=leg)


def test_perpage_follows_codes_and_produces_the_followed_page_then_resumes_without_calls(tmp_path):
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)
    fetch = FakeFetch({REPORT_URL: REPORT})
    leg = WorldLeg(fetch, world=world)
    ready, metrics = _run(run_dir, bound, instrument, providers, inst, leg, _jev())
    assert metrics.ready == [INST] and metrics.held == [] and fetch.calls == [REPORT_URL]
    (st,) = ready
    assert [(p.page_id, p.followed, p.reviewed) for p in st.pages] == [("s1", False, True),
                                                                      (url_hash(REPORT_URL), True, True)]
    assert metrics.live_requests > 0
    doc = json.loads((institution_dir(run_dir, INST) / fv.FOLLOW_DIR / fv.STATE_FILE).read_text(encoding="utf-8"))
    assert [(r["url"], r["hop"], r["parent_page_id"]) for r in doc["records"]] == [(REPORT_URL, 1, "s1")]
    # Resume: the follow state and the stored page are reused, every jev answer is replayed.
    again, metrics2 = _run(run_dir, bound, instrument, providers, inst, WorldLeg(fetch, world=world), _jev())
    assert fetch.calls == [REPORT_URL] and metrics2.live_requests == 0 and metrics2.ready == [INST]
    assert [(p.page_id, p.followed) for p in again[0].pages] == [(p.page_id, p.followed) for p in st.pages]


def test_perpage_without_a_follow_leg_follows_nothing(tmp_path):
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)
    ready, metrics = _run(run_dir, bound, instrument, providers, inst, None, _jev())
    assert metrics.ready == [INST] and [p.page_id for p in ready[0].pages] == ["s1"]
    assert not (institution_dir(run_dir, INST) / fv.FOLLOW_DIR).exists()


REVIEW_STATE, PAGE_VERDICT = "core.page_review_state", "core.page_verdict"


def _unread(st):
    """The unreviewed pages of a ready institution and their source rows."""
    pages = [p for p in st.pages if not p.reviewed]
    return pages, {p.page_id: st.sources[p.source_ids[0]] for p in pages}


def test_perpage_failed_follow_fetch_enters_stage6_as_an_unread_page_102a(tmp_path):
    """PI rulings 79 b / 96 a / 102 a: a URL tried and not fetched is a failed unreviewed page plus one
    page-level source row (review state, URL, verdict not_assessable, every other item not_asked, all by
    the named rule follow_not_reviewed), with no artifact; the institution is no longer held."""
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)
    fetch = FakeFetch({}, fail={REPORT_URL})
    ready, metrics = _run(run_dir, bound, instrument, providers, inst, WorldLeg(fetch, world=world), _jev())
    assert metrics.ready == [INST] and metrics.held == [] and fetch.calls == [REPORT_URL]
    assert not (institution_dir(run_dir, INST) / pp.WORK_DIR / pp.HELD_FILE).exists()
    (st,) = ready
    (page,), rows = _unread(st)
    assert (page.page_id, page.page_verdict, page.support_status, page.reviewed, page.failed, page.followed,
            page.failure_reason) == (url_hash(REPORT_URL), fv.NOT_ASSESSABLE, "set_by_rule", False, True, True,
                                     fl.FETCH_FAILED)
    row = rows[page.page_id]
    (sid,) = page.source_ids
    assert sid not in st.artifacts and sid == f"S{len(st.sources)}"  # numbered after the coded pages' rows
    assert (row["page_artifact_path"], row["page_content_sha256"], row["observation_ids"]) == (None, None, [])
    values = row["values"]
    assert (values[REVIEW_STATE], values[sf.URL], values[PAGE_VERDICT]) == (fl.FETCH_FAILED, REPORT_URL,
                                                                           fv.NOT_ASSESSABLE)
    assert set(values) == set(pp.SOURCE_ITEMS)
    assert {v for k, v in values.items() if k not in (REVIEW_STATE, sf.URL, PAGE_VERDICT)} == {fv.NOT_ASKED}
    coded = {k for k in values if pp.FIELDS[k]["coder"] in ("classifier", "quote_step")}
    assert {s["item_id"] for s in row["item_support"]} == coded
    assert all((s["support_status"], s["support_rule_name"], s["supporting_text"], s["page_content_sha256"],
                s["source_id"], s["observation_id"]) == ("set_by_rule", fv.FOLLOW_NOT_REVIEWED, "", None, sid, None)
               for s in row["item_support"])
    assert {(c["coder_type"], c["support_id"]) for c in row["coder_records"]} == {
        ("mechanical", s["support_id"]) for s in row["item_support"]}
    assert {r["support_id"] for r in st.provenance} >= {s["support_id"] for s in row["item_support"]}


def test_robots_refusal_and_link_not_followed_review_states_79b(tmp_path):
    """79 b: a robots refusal enters as fetch_failed (the failure reason keeps the outcome); a link not
    followed (cap) is not counted as a followed link."""
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)
    leg = WorldLeg(FakeFetch({}, robots={REPORT_URL}), world=world)
    (st,), _ = _run(run_dir, bound, instrument, providers, inst, leg, _jev())
    (page,), rows = _unread(st)
    assert (page.failure_reason, page.followed) == (fv.ROBOTS_DISALLOWED, True)
    assert rows[page.page_id]["values"][REVIEW_STATE] == fl.FETCH_FAILED
    capped = tmp_path / "capped"
    capped.mkdir()
    run_dir, bound, instrument, world, inst, providers = _follow_world(capped)
    fetch = FakeFetch({REPORT_URL: REPORT})
    (st,), _ = _run(run_dir, bound, instrument, providers, inst,
                    WorldLeg(fetch, fl.FollowRules(url_cap=0), world=world), _jev())
    assert fetch.calls == []
    (page,), rows = _unread(st)
    assert (page.failure_reason, page.followed, page.failed) == (fl.LINK_NOT_FOLLOWED_CAP, False, True)
    assert rows[page.page_id]["values"][REVIEW_STATE] == fl.LINK_NOT_FOLLOWED_CAP


def test_unread_follow_page_reaches_stage6_storage_102a(tmp_path):
    """102 a end to end: the unread row passes the Stage 6 A8 pre-check and the storage envelope (no
    artifact, not counted as a reviewed page, exempt from the single-row check) and is stored as built."""
    from tests.test_e2e_perpage_v27 import CLOCK, FakeQuotes

    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)
    ready, _ = _run(run_dir, bound, instrument, providers, inst,
                    WorldLeg(FakeFetch({}, fail={REPORT_URL}), world=world), _jev())
    (page,), rows = _unread(ready[0])
    s6m = rt.run_stage6_v27(run_dir, ready, ask_fn=_jev(), quote_fn=FakeQuotes(), config=bound.stage6_config(),
                            instrument=instrument, now=CLOCK, test_only_unbound_quote_fn=True)
    assert s6m.written == [INST] and s6m.held == [] and s6m.failed == []
    storage = json.loads((institution_dir(run_dir, INST) / "6_storage.json").read_text(encoding="utf-8"))
    (sid,) = page.source_ids
    stored = storage["sources"][sid]
    assert (stored["activity_id"], stored["page_artifact_path"], stored["page_content_sha256"]) == ("_NA_", None, None)
    assert stored["values"] == rows[page.page_id]["values"]
    depth = storage["summary"]["values"]["core.review_depth"]["web_extract"]
    reviewed = [p for p in ready[0].pages if p.reviewed]
    assert (depth["n_pages_reviewed"], depth["n_pages_failed"], depth["n_followed_links"]) == (len(reviewed), 1, 1)
    assert depth["n_pages_by_verdict"][fv.NOT_ASSESSABLE] == 0
    assert storage["summary"]["values"]["core.has_genai_activity"] != "no"  # an unresolved signal (rules/0)


def test_unread_follow_rows_survive_a_resume_with_no_call_l8(tmp_path):
    """Review L8 (kept for 102 a): the next run finds the same unread attempt from the stored follow state
    and the journal: no fetch, no live jev or extractor call, the same row."""
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)
    fetch = FakeFetch({}, fail={REPORT_URL})
    first, _ = _run(run_dir, bound, instrument, providers, inst, WorldLeg(fetch, world=world), _jev())
    ready, metrics = _run(run_dir, bound, instrument, providers, inst, WorldLeg(fetch, world=world), _jev())
    assert metrics.ready == [INST] and metrics.held == [] and metrics.live_requests == 0
    assert fetch.calls == [REPORT_URL]  # R-034: the URL is not tried again
    assert _unread(ready[0])[1] == _unread(first[0])[1]


def test_a8_precheck_skips_unread_rows_only_102a():
    """102 a: the Stage 6 A8 pre-check (source_type check included) skips a non-reviewed row; the same
    malformed value on a reviewed row still stops the stage (ruling 32 b)."""
    from g3o.validate import merged_activity_v27 as ma

    def inst(state):
        return SimpleNamespace(sources={"S1": {"values": {REVIEW_STATE: state, "core.source_access_date": "garbage",
                                                          "core.source_type": "garbage"}}},
                               observation_inputs={})

    for state in (fl.FETCH_FAILED, fl.LINK_NOT_FOLLOWED_CAP, fl.LINK_NOT_FOLLOWED_HOPS, "no_usable_text"):
        ma.check_a8_inputs(inst(state))
    with pytest.raises(ma.MalformedA8Value):
        ma.check_a8_inputs(inst("reviewed"))


def test_a7_grouping_exempts_unread_rows_named_exception_to_13a():
    """96 a / 102 a: an unread row's not_asked syndication group does not hold the institution (named
    exception to A7 13 a); a reviewed row without one still does."""
    reviewed = {"values": {REVIEW_STATE: "reviewed", sf.SYNDICATION: "sg-1", sf.URL: "https://a.example.gov/x"}}
    unread = {"values": {REVIEW_STATE: fl.FETCH_FAILED, sf.SYNDICATION: fv.NOT_ASKED, sf.URL: REPORT_URL}}
    inst = SimpleNamespace(independence_groups=None, institution_id=INST, sources={"S1": reviewed, "S2": unread})
    assert set(rt.independence_groups_of(inst)) == {"S1"}
    assert "follow_not_reviewed" in rt.A7_UNREVIEWED_EXCEPTION
    held = {"values": {**unread["values"], REVIEW_STATE: "reviewed"}}
    with pytest.raises(MissingUpstreamError):
        rt.independence_groups_of(SimpleNamespace(independence_groups=None, institution_id=INST,
                                                  sources={"S1": reviewed, "S2": held}))


def test_unread_products_refuse_unknown_outcomes_and_repeated_pages(tmp_path):
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)
    kw = {"run_id": RUN_ID, "institution_uid": uid_for(INST), "institution_id": INST, "first_source": 3,
          "coder_version": bound.page_config.coder_version, "instrument": instrument}
    ok = {"url": REPORT_URL, "state": fl.LINK_NOT_FOLLOWED_HOPS, "hop": 4, "parent_page_id": "s1"}
    (product,) = fv.unread_products([ok], **kw)
    assert list(product.sources) == ["S3"] and product.page.followed is False
    with pytest.raises(pp.FollowWiringError, match="no signed non-reviewed review state"):
        fv.unread_products([{**ok, "state": fl.FETCHED}], **kw)
    with pytest.raises(pp.FollowWiringError, match="repeats page id"):
        fv.unread_products([ok], known_pages=[url_hash(REPORT_URL)], **kw)


def test_resume_interrupted_while_coding_a_followed_page_l8(tmp_path):
    """Review L8: a stop while the followed page is coded; the next run does not fetch it again and
    finishes the institution."""
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)
    fetch = FakeFetch({REPORT_URL: REPORT})

    def stop(state, questions, n):
        if REPORT in state.get("page_text", ""):
            return JevAccountError("simulated interruption while coding the followed page")
        return None

    first = _jev()
    first.fail = stop
    with pytest.raises(JevAccountError):
        _run(run_dir, bound, instrument, providers, inst, WorldLeg(fetch, world=world), first)
    assert fetch.calls == [REPORT_URL]
    ready, metrics = _run(run_dir, bound, instrument, providers, inst, WorldLeg(fetch, world=world), _jev())
    assert metrics.ready == [INST] and fetch.calls == [REPORT_URL]
    assert metrics.live_requests > 0  # the followed page is asked now; nothing was answered for it before
    assert [(p.page_id, p.followed) for p in ready[0].pages] == [("s1", False), (url_hash(REPORT_URL), True)]


def test_real_followed_page_reaches_the_assembler_l8(tmp_path, monkeypatch):
    """Review L8: the plain follow leg (no WorldLeg override) gives the followed page its D1 a page
    fields and hop; the T-015 assembler builds its rows and stops the stage on what it still refuses."""
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)
    seen = []
    real = srow.assemble
    monkeypatch.setattr(srow, "assemble", lambda *a, **k: seen.append((a[0].page_id, real(*a, **k))) or seen[-1][1])
    fetch = FakeFetch({REPORT_URL: REPORT})
    with pytest.raises(MissingUpstreamError, match="source-row assembler"):
        _run(run_dir, bound, instrument, providers, inst, fv.FollowLeg(fetch), _jev())
    assert fetch.calls == [REPORT_URL]
    (pid, rows), = seen  # the searched page carries injected values; only the followed page is assembled
    assert pid == url_hash(REPORT_URL)
    built = {k: v.value for k, v in rows.source.items()}
    assert (built[sf.URL], built[sf.DISCOVERY], built[sf.TEXT_SOURCE]) == (REPORT_URL, "followed_hop_1", "new_run")
    assert built[sf.ACCESS_DATE] == ACCESS and built[sf.TITLE] == "Followed"
    assert sf.OFFICIAL in rows.refused  # no official-site step in this run (PI ruling 70 b)


def test_zero_page_institution_is_not_followed_l5(tmp_path):
    """Review L5: an institution with no page (an injected builder may pass one) has nothing to follow
    from; the stage neither crashes nor fetches."""
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)
    fetch = FakeFetch({REPORT_URL: REPORT})
    _run(run_dir, bound, instrument, providers, replace(inst, pages=[]), WorldLeg(fetch, world=world), _jev())
    assert fetch.calls == [] and not (institution_dir(run_dir, INST) / fv.FOLLOW_DIR).exists()


def test_follow_data_error_holds_the_institution_l5(tmp_path):
    """Review L5: a follow-leg error that is institution data (here a fetched page whose URL is not the
    URL tried) holds that institution instead of stopping the stage."""
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)

    def moved(url):
        return FetchResult(fl.FETCHED, rendered("https://elsewhere.example.org/x", REPORT))

    ready, metrics = _run(run_dir, bound, instrument, providers, inst, WorldLeg(moved, world=world), _jev())
    assert ready == [] and metrics.held == [INST]
    held = json.loads((institution_dir(run_dir, INST) / pp.WORK_DIR / pp.HELD_FILE).read_text(encoding="utf-8"))
    (hold,) = held["held"]
    assert hold["stage"] == pp.FOLLOW_FAILED and "is not the URL tried" in hold["error"]


@pytest.mark.parametrize("raw, match", [
    (json.dumps({"format": "another-format"}).encode("utf-8"), "unsupported follow state format"),
    (b"{not json", "not UTF-8 JSON"),
    (b"\xff\xfe", "not UTF-8 JSON"),
    (json.dumps([1, 2]).encode("utf-8"), "not a JSON object"),
    (json.dumps({"format": fv.STATE_FORMAT}).encode("utf-8"), "malformed: KeyError"),
])
def test_unusable_stored_follow_state_stops_the_stage_m3(tmp_path, raw, match):
    """Review M3: a stored follow state of another format, undecodable JSON, a missing key: a stage stop."""
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)
    state = institution_dir(run_dir, INST) / fv.FOLLOW_DIR / fv.STATE_FILE
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_bytes(raw)
    fetch = FakeFetch({REPORT_URL: REPORT})
    with pytest.raises(pp.FollowWiringError, match=match):
        _run(run_dir, bound, instrument, providers, inst, WorldLeg(fetch, world=world), _jev())
    assert fetch.calls == []


def test_load_state_mismatch_and_bad_count_are_wiring_errors_m3(tmp_path):
    run_dir, inst = _one(tmp_path)
    page = inst.pages[0].page
    fv.FollowLeg(FakeFetch({F1: "x"})).start(run_dir, inst).round(
        [fv.RoundPage(page, "yes", selection(page, [F1]), ())])
    doc = json.loads((institution_dir(run_dir, I1) / fv.FOLLOW_DIR / fv.STATE_FILE).read_text(encoding="utf-8"))
    rules = fl.FollowRules()
    with pytest.raises(pp.FollowWiringError, match="another institution"):
        fv.load_state(doc, institution_id=I1, release_id="R-OTHER", rules=rules)
    with pytest.raises(pp.FollowWiringError, match="disagrees with its records"):
        fv.load_state({**doc, "followed": 7}, institution_id=I1, release_id=inst.run_id, rules=rules)
    with pytest.raises(pp.FollowWiringError, match="malformed: a records entry has keys"):
        fv.load_state({**doc, "records": [{"bogus": 1}]}, institution_id=I1, release_id=inst.run_id, rules=rules)
    with pytest.raises(pp.FollowWiringError, match="no searched page"):
        fv.FollowLeg(FakeFetch({})).start(run_dir, replace(inst, pages=[]))


def test_load_state_checks_types_and_never_converts_l1(tmp_path):
    """Review L-1: a stored value of the wrong type is refused (FollowWiringError), never converted:
    ``bool("false")`` is True and ``int("3")`` passes; a bool is not an int; 0 is not False."""
    run_dir, inst = _one(tmp_path)
    page = inst.pages[0].page
    fv.FollowLeg(FakeFetch({F1: "x"})).start(run_dir, inst).round(
        [fv.RoundPage(page, "yes", selection(page, [F1]), ())])
    doc = json.loads((institution_dir(run_dir, I1) / fv.FOLLOW_DIR / fv.STATE_FILE).read_text(encoding="utf-8"))
    rules = fl.FollowRules()
    kw = {"institution_id": I1, "release_id": inst.run_id, "rules": rules}
    loaded = fv.load_state(doc, **kw)  # the state as written loads
    assert loaded.followed == doc["followed"] and loaded.records and loaded.hops == doc["hops"]
    rec = doc["records"][0]
    bad = [
        ({**doc, "cap_reached": "false"}, "cap_reached is str"),
        ({**doc, "cap_reached": 0}, "cap_reached is int"),
        ({**doc, "followed": str(doc["followed"])}, "followed is str"),
        ({**doc, "followed": True}, "followed is bool"),
        ({**doc, "hops": {"k": "1"}}, r"hops\['k'\] is str"),
        ({**doc, "hops": {"k": True}}, r"hops\['k'\] is bool"),
        ({**doc, "hops": [["k", 1]]}, "hops is list"),
        ({**doc, "records": {"0": rec}}, "records is dict"),
        ({**doc, "records": [{**rec, "hop": str(rec["hop"])}]}, r"records\.hop is str"),
        ({**doc, "records": [{**rec, "counted": "true"}]}, r"records\.counted is str"),
        ({**doc, "records": [{**rec, "backfill": 0}]}, r"records\.backfill is int"),
        ({**doc, "records": [{**rec, "fetch_date": 20261114}]}, r"records\.fetch_date is int"),
        ({**doc, "records": [{**rec, "extra": 1}]}, "a records entry has keys"),
        ({**doc, "backfill": 0}, "another institution"),
        ({**doc, "rules": {**doc["rules"], "url_cap": float(doc["rules"]["url_cap"])}}, "another institution"),
    ]
    for broken, match in bad:
        with pytest.raises(pp.FollowWiringError, match=match):
            fv.load_state(broken, **kw)
    if doc["not_followed"]:
        nf = doc["not_followed"][0]
        with pytest.raises(pp.FollowWiringError, match=r"not_followed\.hop is str"):
            fv.load_state({**doc, "not_followed": [{**nf, "hop": str(nf["hop"])}]}, **kw)


def test_follow_state_write_failure_leaves_the_stage_l4(tmp_path, monkeypatch):
    """Review L4: an OSError writing the follow state is not held as follow_failed (the searched-page
    path holds an OSError only for a page-state archive, ruling 28 a): it leaves the stage."""
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)

    def broken(path, text):
        raise OSError("disk full")

    monkeypatch.setattr(fv, "_atomic_write", broken)
    with pytest.raises(OSError, match="disk full"):
        _run(run_dir, bound, instrument, providers, inst, WorldLeg(FakeFetch({REPORT_URL: REPORT}), world=world),
             _jev())
    assert not (institution_dir(run_dir, INST) / pp.WORK_DIR / pp.HELD_FILE).exists()


def test_follow_wiring_error_stops_the_stage_l5(tmp_path):
    """Review L5: a fetch seam that breaks its contract is a wiring gap: the stage stops."""
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)

    def bogus(url):
        return FetchResult("bogus_outcome")

    with pytest.raises(pp.FollowWiringError, match="unknown outcome"):
        _run(run_dir, bound, instrument, providers, inst, WorldLeg(bogus, world=world), _jev())
    assert pp.FollowWiringError in pp.STAGE_STOPS


# ---------------------------------------------------------------------------
# Dispatch seam and entry refusal
# ---------------------------------------------------------------------------


def test_missing_producers_no_longer_name_the_attempted_pages_102a():
    """PI rulings 79 b / 96 a / 102 a: attempted pages not reviewed enter Stage 6; the entry is gone."""
    assert not hasattr(pin, "FOLLOW_ATTEMPTS_MISSING")
    assert not any("T-025" in m for m in pin.MISSING_PRODUCERS)
    assert pp.FOLLOW_PRODUCER not in pin.MISSING_PRODUCERS


def test_default_builder_needs_follow_fetch_once_producers_exist(monkeypatch):
    from tests.test_perpage_providers_v27 import FakeEntail

    monkeypatch.setattr(pin, "MISSING_PRODUCERS", ())
    v27 = orch.V27Dispatch(settings=SETTINGS, jev_ask_fn=FakeJev(), extract_fn=lambda j: None,
                           entail_fn=FakeEntail())
    with pytest.raises(MissingUpstreamError, match="follow leg") as exc:
        orch._require_v27_dispatch(v27)
    assert exc.value.missing == ("follow_fetch",)
    with_fetch = replace(v27, follow_fetch=FakeFetch({}))
    assert orch._require_v27_dispatch(with_fetch) is with_fetch
    with pytest.raises(ValueError, match="follow_fetch must be a callable"):
        orch._require_v27_dispatch(replace(v27, follow_fetch="not callable"))
    injected = replace(v27, perpage_inputs=lambda *a: [])  # an injected builder may follow nothing
    assert orch._require_v27_dispatch(injected) is injected
