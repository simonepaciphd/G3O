"""T-025 follow-up leg runner (g3o.run.presweep.stage_follow). No network: fetch is a fake."""

from __future__ import annotations

import json

import pytest

from g3o.common import attrition
from g3o.common.artifact_io import read_artifact
from g3o.common.paths import institution_dir
from g3o.run.presweep import stage_follow
from g3o.run.presweep.stage_follow import FetchResult, polite_fetch, run_follow_round
from g3o.scrape.follow import FETCH_FAILED, FETCHED, InstitutionFollow
from g3o.scrape.render import FetchMetadata, RenderedPage
from tests.test_follow import INST, extraction, page, rules


def rendered(url: str) -> RenderedPage:
    return RenderedPage(url=url, text=f"text of {url}", title="", content_type="html",
                        fetch_metadata=FetchMetadata(access_date="2026-11-05", fetch_method="html"))


class FakeFetch:
    def __init__(self, fail: set[str] = frozenset()):
        self.calls: list[str] = []
        self.fail = fail

    def __call__(self, url: str) -> FetchResult:
        self.calls.append(url)
        if url in self.fail:
            return FetchResult(FETCH_FAILED)
        return FetchResult(FETCHED, rendered(url))


def ledger(run_dir):
    path = attrition.ledger_path(run_dir)
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] \
        if path.exists() else []


def test_round_fetches_writes_and_records(tmp_path):
    st = InstitutionFollow(INST, "rel-1", rules(url_cap=2))
    p0 = page("https://a/0", ["https://a/1", "https://a/2", "https://a/3"])
    st.register_original(p0.url)
    fetch = FakeFetch(fail={"https://a/2"})
    out = run_follow_round(tmp_path, {INST: st}, [(p0, extraction(p0))], fetch=fetch)
    assert fetch.calls == ["https://a/1", "https://a/2", "https://a/3"]
    assert [f.page.url for f in out] == ["https://a/1", "https://a/3"]
    assert json.loads(read_artifact(out[0].artifact))["url"] == "https://a/1"
    saved = json.loads((institution_dir(tmp_path, INST) / "follow" / "state.json")
                       .read_text(encoding="utf-8"))
    assert saved["cap"] == {"institution_id": INST, "url_cap": 2, "followed": 2,
                            "cap_reached": True, "not_followed_cap": 0, "not_followed_hops": 0}
    assert [r["outcome"] for r in saved["records"]] == [FETCHED, FETCH_FAILED, FETCHED]
    assert {r["release_id"] for r in saved["records"]} == {"rel-1"}
    assert [(e["reason"], e["url"]) for e in ledger(tmp_path)] == [(FETCH_FAILED, "https://a/2")]


def test_rounds_chain_until_hop_limit(tmp_path):
    st = InstitutionFollow(INST, "rel-1", rules())
    p0 = page("https://a/0", ["https://a/1"])
    st.register_original(p0.url)
    fetch = FakeFetch()
    current = [(p0, extraction(p0))]
    for i in range(1, 6):
        out = run_follow_round(tmp_path, {INST: st}, current, fetch=fetch)
        current = []
        for f in out:  # next pass-1 round on the fetched page (mocked T-021 output)
            nxt = page(f.page.url, [f"https://a/{i + 1}"])
            current.append((nxt, extraction(nxt)))
    assert fetch.calls == ["https://a/1", "https://a/2", "https://a/3"]
    assert [(e["reason"], e["url"]) for e in ledger(tmp_path)] == [
        ("link_not_followed_hops", "https://a/4")]


def test_unknown_institution_raises(tmp_path):
    p0 = page("https://a/0", ["https://a/1"])
    with pytest.raises(KeyError):
        run_follow_round(tmp_path, {}, [(p0, extraction(p0))], fetch=FakeFetch())


def test_polite_fetch_robots_throttle_and_failure(monkeypatch):
    class Robots:
        def allowed(self, url):
            return "blocked" not in url

        def crawl_delay(self, url):
            return 2.0

    class Throttle:
        def __init__(self):
            self.waits = []

        def wait(self, url, *, extra_delay=None, max_wait=None):
            self.waits.append((url, extra_delay))
            return True

    def fake_scrape_url(url, *, on_redirect_hop, on_scrape_failure, **kw):
        if "dead" in url:
            on_scrape_failure(url=url)
        return rendered(url)

    import g3o.scrape.fetcher as fetcher
    monkeypatch.setattr(fetcher, "scrape_url", fake_scrape_url)
    th = Throttle()
    fetch = polite_fetch(Robots(), th)
    assert fetch("https://a/blocked").outcome == stage_follow.ROBOTS_DISALLOWED
    assert fetch("https://a/dead").outcome == FETCH_FAILED
    ok = fetch("https://a/ok")
    assert ok.outcome == FETCHED and ok.page.url == "https://a/ok"
    assert th.waits == [("https://a/dead", 2.0), ("https://a/ok", 2.0)]
