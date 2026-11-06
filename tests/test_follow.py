"""T-025 link-following rules (g3o.scrape.follow): hops, once per URL, cap, ranking, provenance.

The nearness and URL-identity rules are OPEN (lane report QUESTION block); these tests pass
explicit test stand-ins, which are fixtures, not proposals.
"""

from __future__ import annotations

import pytest

from g3o.common.page_chunks import Chunk
from g3o.extract.parser_v27 import Pass1Extraction, SelectedLink
from g3o.extract.request_v27 import Pass1Page
from g3o.scrape.follow import (
    FETCH_FAILED,
    FETCHED,
    LINK_NOT_FOLLOWED_CAP,
    LINK_NOT_FOLLOWED_HOPS,
    MAX_HOPS,
    PASS1_PAGE_FIELDS,
    URL_CAP,
    FollowRules,
    InstitutionFollow,
)

INST = "inst-1"


def page(url: str, links: list[str], *, complete: str | None = "yes", text: str | None = None,
         inst: str = INST) -> Pass1Page:
    text = text or f"page {url} text"
    pid = f"p:{url}"
    return Pass1Page(
        page_id=pid, institution_id=inst, institution_name="X", url=url, title=None, text=text,
        chunks=(Chunk("c1", pid, 0, len(text), text, 1),), codes=(), verdict="no_genai",
        page_complete=complete, links=tuple({"url": u, "anchor_text": u} for u in links),
    )


def extraction(p: Pass1Page, selected: list[str] | None = None,
               nearness: dict[str, float] | None = None) -> Pass1Extraction:
    urls = [ln["url"] for ln in p.links]
    selected = urls if selected is None else selected
    links = tuple(SelectedLink(f"L{urls.index(u) + 1:03d}", u, "c1",
                               str((nearness or {}).get(u, 0.0))) for u in selected)
    return Pass1Extraction(page_id=p.page_id, custom_id="x", quotes=(), links=links,
                           activities=(), publication_date=None, link_status=None)


def stand_in_nearness(_page, _extraction, link) -> float:
    # test fixture: the nearness value is carried in the link passage
    return float(link.quote)


def rules(**kw) -> FollowRules:
    base = dict(url_key=lambda u: u, nearness=stand_in_nearness, count_unfetched=False)
    base.update(kw)
    return FollowRules(**base)


def state(**kw) -> InstitutionFollow:
    s = InstitutionFollow(INST, release_id="rel-test", rules=rules(**kw))
    return s


def follow_all(s: InstitutionFollow, pairs, outcome=FETCHED):
    taken = []
    for c in s.candidates(pairs):
        if s.take(c):
            s.record(c, outcome, "2026-11-05" if outcome == FETCHED else None)
            taken.append(c)
    return taken


def test_defaults_are_the_signed_values():
    assert URL_CAP == 10  # RC-D-014 S4
    assert MAX_HOPS == 3  # R-032
    assert PASS1_PAGE_FIELDS == ("page_id", "institution_id", "url", "text", "page_complete",
                                 "links")


def test_procurement_is_refused():
    with pytest.raises(ValueError, match="procurement"):
        InstitutionFollow(INST, "rel", rules(), pipeline="procurement")


def test_complete_page_gives_no_candidates():
    s = state()
    p = page("https://a/0", ["https://a/1"], complete="no")
    s.register_original(p.url)
    assert s.candidates([(p, extraction(p))]) == []


def test_only_quote_step_selected_links_are_candidates():
    s = state()
    p = page("https://a/0", ["https://a/1", "https://a/2"])
    s.register_original(p.url)
    cands = s.candidates([(p, extraction(p, selected=["https://a/2"]))])
    assert [c.url for c in cands] == ["https://a/2"]
    assert cands[0].link_order == 2


def test_hop_limit_three_hops_then_recorded_not_followed():
    s = state()
    urls = [f"https://a/{i}" for i in range(6)]
    p0 = page(urls[0], [urls[1]])
    s.register_original(p0.url)
    current = [(p0, extraction(p0))]
    hops_seen = []
    for i in range(1, 5):
        taken = follow_all(s, current)
        hops_seen += [c.hop for c in taken]
        nxt = page(urls[i], [urls[i + 1]])
        current = [(nxt, extraction(nxt))] if taken else []
    assert hops_seen == [1, 2, 3]
    assert [(n.url, n.reason, n.hop) for n in s.not_followed] == [
        (urls[4], LINK_NOT_FOLLOWED_HOPS, 4)]
    assert s.cap_record().not_followed_hops == 1


def test_once_per_url_loops_and_originals():
    s = state()
    a, b = "https://a/A", "https://a/B"
    pa = page(a, [b, a])  # self-link
    s.register_original(a)
    assert [c.url for c in follow_all(s, [(pa, extraction(pa))])] == [b]
    pb = page(b, [a, b])  # loop back to the original and to itself
    assert s.candidates([(pb, extraction(pb))]) == []
    assert len(s.records) == 1


def test_same_url_on_two_pages_parent_is_first_queued():
    s = state()
    x = "https://a/X"
    p1 = page("https://a/1", [x])
    p2 = page("https://a/2", [x])
    for p in (p1, p2):
        s.register_original(p.url)
    cands = s.candidates([(p1, extraction(p1, nearness={x: 50})),
                          (p2, extraction(p2, nearness={x: 5}))])
    assert [(c.url, c.parent_url) for c in cands] == [(x, p2.url)]  # F2 a, rank order


def test_url_key_defines_identity():
    s = state(url_key=lambda u: u.rstrip("/"))
    p = page("https://a/0", ["https://a/1", "https://a/1/"])
    s.register_original(p.url)
    assert [c.url for c in s.candidates([(p, extraction(p))])] == ["https://a/1"]


def test_ranking_nearest_first_ties_page_order():
    s = state(url_cap=3)
    links = [f"https://a/{i}" for i in range(1, 6)]
    p = page("https://a/0", links)
    s.register_original(p.url)
    near = {links[0]: 40, links[1]: 10, links[2]: 10, links[3]: 5, links[4]: 99}
    taken = follow_all(s, [(p, extraction(p, nearness=near))])
    assert [c.url for c in taken] == [links[3], links[1], links[2]]
    assert [n.url for n in s.not_followed] == [links[0], links[4]]
    assert all(n.reason == LINK_NOT_FOLLOWED_CAP for n in s.not_followed)


def test_cap_reached_recorded_sc03():
    s = state()
    links = [f"https://a/{i}" for i in range(1, 13)]
    p = page("https://a/0", links)
    s.register_original(p.url)
    taken = follow_all(s, [(p, extraction(p))])
    assert len(taken) == 10
    cap = s.cap_record()
    assert (cap.followed, cap.cap_reached, cap.not_followed_cap, cap.url_cap) == (10, True, 2, 10)


def test_cap_counts_over_hops():
    s = state()
    p0 = page("https://a/0", [f"https://a/h1/{i}" for i in range(8)])
    s.register_original(p0.url)
    assert len(follow_all(s, [(p0, extraction(p0))])) == 8
    p1 = page("https://a/h1/0", [f"https://a/h2/{i}" for i in range(5)])
    assert len(follow_all(s, [(p1, extraction(p1))])) == 2
    cap = s.cap_record()
    assert (cap.followed, cap.cap_reached, cap.not_followed_cap) == (10, True, 3)
    # later rounds follow nothing more; a URL is recorded once
    assert follow_all(s, [(p1, extraction(p1))]) == []
    assert s.cap_record().not_followed_cap == 3


def test_cap_reached_when_count_hits_cap_exactly():
    s = state(url_cap=2)
    p = page("https://a/0", ["https://a/1", "https://a/2"])
    s.register_original(p.url)
    follow_all(s, [(p, extraction(p))])
    assert s.cap_record().cap_reached is True
    assert s.cap_record().not_followed_cap == 0


@pytest.mark.parametrize("count_unfetched,followed", [(False, 0), (True, 2)])
def test_unfetched_counting_is_a_rule_input(count_unfetched, followed):
    s = state(count_unfetched=count_unfetched)
    p = page("https://a/0", ["https://a/1", "https://a/2"])
    s.register_original(p.url)
    follow_all(s, [(p, extraction(p))], outcome=FETCH_FAILED)
    assert s.followed == followed
    assert [r.fetch_date for r in s.records] == [None, None]
    # a failed URL is not tried again (R-034)
    assert s.candidates([(p, extraction(p))]) == []


def test_provenance_fields():
    s = InstitutionFollow(INST, "rel-9", rules(), backfill=True)
    p = page("https://a/0", ["https://a/1"])
    s.register_original(p.url)
    (c,) = s.candidates([(p, extraction(p))])
    rec = s.record(c, FETCHED, "2026-11-05")
    assert (rec.parent_page_id, rec.parent_url, rec.hop, rec.fetch_date, rec.release_id,
            rec.backfill, rec.counted, rec.link_id) == (
        p.page_id, p.url, 1, "2026-11-05", "rel-9", True, True, "L001")
    with pytest.raises(ValueError, match="already fetched"):
        s.record(c, FETCHED, "2026-11-05")
    assert s.hop_of("https://a/1") == 1


def test_guards():
    s = state()
    p = page("https://a/0", ["https://a/1"])
    with pytest.raises(KeyError):
        s.candidates([(p, extraction(p))])  # page never fetched for this institution
    s.register_original(p.url)
    other = page("https://b/0", [], inst="inst-2")
    with pytest.raises(ValueError, match="not inst-1"):
        s.candidates([(other, extraction(other))])
    (c,) = s.candidates([(p, extraction(p))])
    with pytest.raises(ValueError, match="fetch date"):
        s.record(c, FETCHED, None)
    with pytest.raises(ValueError, match="unknown outcome"):
        s.record(c, "bogus", None)
