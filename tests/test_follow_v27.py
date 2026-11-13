"""T-025 follow leg in the v2.7 per-page stage (g3o.run.presweep.follow_v27): the ``followed`` / hop producer.

No network: every fetch is a fake, every jev / extractor answer is a fake. Covers the leg's rounds
(candidates from the page request's selected links on a page whose final ``core.page_complete`` is
``yes``, provenance, hop), resume (stored state and stored pages: no second fetch, no second paid
call), the hold for attempts whose Stage 6 entry is unruled, the A4 regrouping over searched and
followed pages, ``discovery_path`` from the hop, and the dispatch's ``follow_fetch`` seam.
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
from g3o.common.paths import institution_dir
from g3o.extract.batch import url_hash
from g3o.extract.parser_v27 import Pass1Extraction, SelectedLink
from g3o.persist.stage6_adapters import MissingUpstreamError
from g3o.run.presweep import follow_v27 as fv
from g3o.run.presweep import orchestrator as orch
from g3o.run.presweep import perpage_inputs_v27 as pin
from g3o.run.presweep import source_row_v27 as srow
from g3o.run.presweep import stage_perpage_v27 as pp
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
    assert leg.hold() is None


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
    spec = SimpleNamespace(page="page")
    rp = fv.round_page(spec, page_round, "ext")
    assert (rp.page, rp.page_complete, rp.extraction, rp.supported) == ("page", "yes", "ext", ("Quote A",))
    stopped = SimpleNamespace(final=SimpleNamespace(items={COMPLETE: ItemOutcome(COMPLETE, "pending", None)}),
                              support=())
    assert fv.round_page(spec, stopped, None).page_complete is None


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


def test_failed_robots_and_cap_attempts_hold_the_institution(tmp_path):
    """Every URL tried counts against the cap (C-Q5 b); attempts not reviewed are recorded and hold the
    institution (their Stage 6 entry is a PI question)."""
    f3 = "https://one.example.gov/minutes"
    run_dir, inst = _one(tmp_path, links=(F1, F2, f3))
    fetch = FakeFetch({}, fail={F1}, robots={F2})
    leg = fv.FollowLeg(fetch, fl.FollowRules(url_cap=2)).start(run_dir, inst)
    page = inst.pages[0].page
    assert leg.round([fv.RoundPage(page, "yes", selection(page, [F1, F2, f3]), ())]) == []
    assert fetch.calls == [F1, F2]
    hold = leg.hold()
    assert hold["stage"] == fv.FOLLOW_ATTEMPTS_UNRULED and hold["page_id"] == fv.FOLLOW_HOLD_PAGE
    assert [(a["url"], a["state"]) for a in hold["attempts"]] == [
        (F1, fl.FETCH_FAILED), (F2, fv.ROBOTS_DISALLOWED), (f3, fl.LINK_NOT_FOLLOWED_CAP)]
    assert hold["cap"]["cap_reached"] is True and hold["cap"]["followed"] == 2
    assert "PI question" in hold["error"]
    assert set(ledger(run_dir)) == {(fv.STAGE, fl.FETCH_FAILED, F1), (fv.STAGE, fv.ROBOTS_DISALLOWED, F2),
                                    (fv.STAGE, fl.LINK_NOT_FOLLOWED_CAP, f3), (fv.STAGE, fv.CAP_REACHED, None)}
    # A resumed leg tries none of them again (R-034, reading 4).
    again = fv.FollowLeg(fetch, fl.FollowRules(url_cap=2)).start(run_dir, inst)
    again.round([fv.RoundPage(page, "yes", selection(page, [F1, F2, f3]), ())])
    assert fetch.calls == [F1, F2] and again.hold() == hold


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


def test_perpage_failed_follow_fetch_holds_the_institution(tmp_path):
    run_dir, bound, instrument, world, inst, providers = _follow_world(tmp_path)
    fetch = FakeFetch({}, fail={REPORT_URL})
    ready, metrics = _run(run_dir, bound, instrument, providers, inst, WorldLeg(fetch, world=world), _jev())
    assert ready == [] and metrics.held == [INST] and fetch.calls == [REPORT_URL]
    held = json.loads((institution_dir(run_dir, INST) / pp.WORK_DIR / pp.HELD_FILE).read_text(encoding="utf-8"))
    (hold,) = held["held"]
    assert hold["stage"] == fv.FOLLOW_ATTEMPTS_UNRULED
    assert [(a["url"], a["state"]) for a in hold["attempts"]] == [(REPORT_URL, fl.FETCH_FAILED)]
    assert any(r["reason"] == pp.HELD_REASON and fv.FOLLOW_ATTEMPTS_UNRULED in r["detail"]
               for r in attrition.read_records(run_dir))


# ---------------------------------------------------------------------------
# Dispatch seam and entry refusal
# ---------------------------------------------------------------------------


def test_missing_producers_keep_the_attempted_pages_entry():
    assert pin.MISSING_PRODUCERS[0] == pin.FOLLOW_ATTEMPTS_MISSING
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
