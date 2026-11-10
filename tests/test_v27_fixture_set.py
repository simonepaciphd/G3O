"""T-040 self-check on the v2.7 fixture set (tests/fixtures/v27/).

Offline structure test only: it checks coverage (DP-031 / RC-D-014 P3 b), that expected
values are codebook codes, that every expected value cites a rule, that real-page fixtures
carry no page text and a hash-pinned reference, and that judgement calls are registered.
It does not run the pipeline (that is T-041, paid).
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "v27"
CODEBOOK = ROOT / "codebook" / "codebook.yaml"
SIGNED_SHA = "fc29dbd96b50ab6f09c9a6958da0f0e6593ec77913f6d822cd744d3fa140fb66"
A_IDS = ["A-003", "A-004", "A-010", "A-011", "A-012", "A-020", "A-021", "A-022"]
VERDICTS = [
    "confirms_activity",
    "ambiguous_genai",
    "ambiguous_attribution",
    "other_body",
    "event_only",
    "background_only",
    "confirms_absence",
    "no_genai",
    "not_assessable",
]
MISSING = {"not_asked", "not_documented", "unknown", "_NA_"}


def _fixtures():
    out = []
    for name in ("synthetic.json", "real.json", "transfers.json"):
        p = FIX / name
        if p.exists():
            out += json.loads(p.read_text(encoding="utf-8"))["fixtures"]
    return out


@pytest.fixture(scope="module")
def fixtures():
    return _fixtures()


@pytest.fixture(scope="module")
def items():
    return yaml.safe_load(CODEBOOK.read_text(encoding="utf-8"))["items"]


def test_codebook_is_signed_release():
    assert hashlib.sha256(CODEBOOK.read_bytes()).hexdigest() == SIGNED_SHA


def test_fixture_ids_unique(fixtures):
    ids = [f["fixture_id"] for f in fixtures]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("a_id", A_IDS)
def test_at_least_three_fixtures_per_a_id(fixtures, a_id):
    assert sum(a_id in f["a_ids"] for f in fixtures) >= 3


@pytest.mark.parametrize("verdict", VERDICTS)
def test_every_page_verdict_value_has_a_fixture(fixtures, verdict):
    hits = [
        f
        for f in fixtures
        if "A-011" in f["a_ids"]
        and any(e["item"] == "core.page_verdict" and e["value"] == verdict for e in f["expected"])
    ]
    assert hits, verdict


def test_expected_values_are_codebook_codes(fixtures, items):
    for f in fixtures:
        for e in f["expected"]:
            it = items.get(e["item"])
            if it is None or e.get("value_kind"):
                continue  # mechanics keys (followed_urls, provenance, ...) and counts
            vals = it.get("values")
            if not isinstance(vals, list) or not all(
                isinstance(v, dict) and v.get("code") for v in vals
            ):
                continue  # free-text, list, date and year items
            codes = {v["code"] for v in vals} | MISSING
            assert e["value"] in codes, (f["fixture_id"], e["item"], e["value"])


def test_every_expected_value_cites_a_rule(fixtures):
    for f in fixtures:
        assert f["expected"], f["fixture_id"]
        for e in f["expected"]:
            assert e.get("rule"), (f["fixture_id"], e["item"])


def test_kinds_and_real_fixtures_carry_no_text(fixtures):
    for f in fixtures:
        assert f["kind"] in {"synthetic", "real", "real_transfer"}
        if f["kind"] == "real":
            refs = [f["page_ref"]] if "page_ref" in f else f["page_refs"]
            for ref in refs:
                assert len(ref["text_sha256"]) == 64 and ref["store"]
                assert ref.get("line_1based", 0) >= 1 or len(ref.get("member_sha256", "")) == 64
            assert "text" not in f and "pages" not in f
            for e in f["expected"]:
                assert e.get("labeller") == "agent" and "jev_score" in e


def test_judgement_calls_are_registered(fixtures):
    reg = {r["jc_id"] for r in csv.DictReader((FIX / "judgement-calls.csv").open(encoding="utf-8"))}
    used = {e["judgement_call"] for f in fixtures for e in f["expected"] if e.get("judgement_call")}
    assert used <= reg, used - reg


def test_label_sheet_matches_fixtures(fixtures):
    rows = list(csv.DictReader((FIX / "label-sheet.csv").open(encoding="utf-8")))
    n = sum(len(f["expected"]) for f in fixtures)
    assert len(rows) == n
    assert {r["fixture_id"] for r in rows} == {f["fixture_id"] for f in fixtures}


def test_synthetic_long_pages_exceed_chunk_threshold():
    import importlib.util

    spec = importlib.util.spec_from_file_location("fixture_text", FIX / "fixture_text.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    syn = json.loads((FIX / "synthetic.json").read_text(encoding="utf-8"))["fixtures"]
    long_pages = [p for f in syn for p in f["pages"] if "text_parts" in p]
    assert long_pages
    for p in long_pages:
        assert len(mod.page_text(p)) > 2 * 32000 * mod.CHARS_PER_TOKEN


def test_no_pilot_v1_input():
    for p in FIX.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".csv", ".py"}:
            t = p.read_text(encoding="utf-8")
            assert "pilot_v1" not in t and "g3o_full_database_v1" not in t, p


def test_jev_label_scores_join_and_readings():
    scores = list(csv.DictReader((FIX / "jev-label-scores.csv").open(encoding="utf-8")))
    sheet = list(csv.DictReader((FIX / "label-sheet.csv").open(encoding="utf-8")))
    keys = {s["key"] for s in scores}
    assert len(keys) == len(scores)
    # current real label keys that have a score are filled; superseded keys (relabels) stay in the scores file
    sheet_keys = {r["jev_key"] for r in sheet if r["jev_key"]}
    assert {r["jev_key"] for r in sheet if r["jev_argmax_1_5"]} == keys & sheet_keys
    for r in sheet:
        if r["label_version"] not in ("", "1"):
            assert r["jev_key"].endswith("@v" + r["label_version"])
    for s in scores:
        probs = {int(k): v for k, v in json.loads(s["probabilities_1_5"]).items()}
        top = max(probs, key=lambda k: (probs[k], -k))
        assert int(s["jev_argmax_1_5"]) == top
        assert abs(float(s["jev_expected_1_5"]) - (float(s["level_raw"]) + 1)) < 1e-6


def test_real_pages_resolve_and_quotes_occur():
    """Drive-backed: skipped when G3O_DRIVE_ROOT is unset (CI); hash-checks every real page and quote."""
    import importlib.util
    import os
    import re

    if not os.environ.get("G3O_DRIVE_ROOT"):
        pytest.skip("G3O_DRIVE_ROOT not set: real-page stores are not available")
    spec = importlib.util.spec_from_file_location("fixture_text", FIX / "fixture_text.py")
    ft = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ft)
    drive = ft.drive_root()

    def norm(s):
        return re.sub(r"\s+", " ", s).strip()

    real = json.loads((FIX / "real.json").read_text(encoding="utf-8"))["fixtures"]
    cache = {}
    for f in real:
        refs = [f["page_ref"]] if "page_ref" in f else f["page_refs"]
        texts = []
        for r in refs:
            k = r["text_sha256"]
            if k not in cache:
                cache[k] = norm(ft.load_real_text(r, drive))
            texts.append(cache[k])
        for e in f["expected"]:
            q = e.get("evidence_quote")
            assert not q or any(norm(q) in t for t in texts), (f["fixture_id"], q)


def _injected_answers(o):
    if isinstance(o, dict):
        if "value" in o and "support" in o:
            yield o
        else:
            for v in o.values():
                yield from _injected_answers(v)
    elif isinstance(o, list):
        for v in o:
            yield from _injected_answers(v)


def test_injected_support_follows_codebook_status_by_answer(fixtures):
    """An injected value the signed vocabulary maps to not_required is never `supported` (r13).

    It is `not_required`, or downgraded when it misses the 0.8 bar (R-081).
    """
    cb = yaml.safe_load(CODEBOOK.read_text(encoding="utf-8"))
    by_answer = cb["vocabularies"]["support_status"]["status_by_answer"]
    exempt = {k for k, v in by_answer.items() if v == "not_required"}
    assert {"no", "unresolved", "unclear", "none"} <= exempt
    bad = [
        (f["fixture_id"], a["value"], a["support"])
        for f in fixtures
        for a in _injected_answers(f.get("injected") or {})
        if str(a["value"]) in exempt and a["support"] == "supported"
    ]
    assert not bad, bad


def test_cap_fixture_follows_page_order_when_no_link_is_located(fixtures):
    """v27-syn-A004-02: RC-D-017 10a + RC-D-023 C-Q4 a fix which 10 of 13 links are followed (JC-S4 closed)."""
    f = next(x for x in fixtures if x["fixture_id"] == "v27-syn-A004-02")
    exp = {e["item"]: e["value"] for e in f["expected"]}
    links = [lk["url"].rsplit("/", 1)[1] for lk in f["pages"][0]["links"]]
    assert exp["n_followed"] == 10 and exp["cap_reached"] is True
    assert exp["which_followed"] == links[:10]
    assert exp["not_followed"] == links[10:]
    jc = {
        r["jc_id"]: r for r in csv.DictReader((FIX / "judgement-calls.csv").open(encoding="utf-8"))
    }
    assert jc["JC-S4"]["status"].startswith("closed")


def test_recovery_fixture_revisions_and_known_limits(fixtures):
    """PI E-Q1a/Q2a: new labels r13, known limits are expected behavior, no paid scoring."""
    new_ids = {f"v27-syn-A011-{n}" for n in (10, 11, 12)}
    new_ids |= {f"v27-syn-A021-{n}" for n in (12, 13, 14, 15, 16, 17)}
    new_ids |= {f"v27-syn-A004-{n:02d}" for n in (6, 7, 8, 9)}
    by = {f["fixture_id"]: f for f in fixtures}
    assert new_ids <= by.keys()
    for fid in new_ids:
        assert all(e["codebook_rev"] == "r13" for e in by[fid]["expected"])
    for f in fixtures:
        if f["kind"] == "synthetic" and f["fixture_id"] not in new_ids:
            assert all(e["codebook_rev"] == "r11" for e in f["expected"])
    for n in (12, 13, 14):
        f = by[f"v27-syn-A021-{n}"]
        assert "known_limit" in f["tags"]
        assert {e["item"]: e["value"] for e in f["expected"]}["support_status"] == "downgraded_no_quote"


def test_recovery_readability_fixtures_match_production(fixtures):
    from g3o.scrape.readability import readability_failure

    by = {f["fixture_id"]: f for f in fixtures}
    for n in (10, 11, 12):
        f = by[f"v27-syn-A011-{n}"]
        expected = {e["item"]: e["value"] for e in f["expected"]}
        assert readability_failure(f["pages"][0]["text"]) == expected["readability_failure"]
        assert expected["core.page_verdict"] == "not_assessable"
        assert expected["page_review_state"] == "reviewed"


def test_recovery_matcher_and_contact_fixtures_match_production(fixtures):
    from g3o.common.support_check import extract_contact_emails, match_quote

    by = {f["fixture_id"]: f for f in fixtures}
    for n in (12, 13, 14):
        f = by[f"v27-syn-A021-{n}"]
        answer = f["injected"]["p0"]["answer"]
        result = match_quote(answer["quote"], f["pages"][0]["text"])
        assert not result.matched, (f["fixture_id"], result)
    f = by["v27-syn-A021-17"]
    assert extract_contact_emails("yes", f["pages"][0]["text"]) == "not_documented"


def test_opened_gate_fixture_requires_extra_round_before_finalization(fixtures):
    from g3o.classify.questions.v27 import load_set

    fixture = next(f for f in fixtures if f["fixture_id"] == "v27-syn-A021-16")
    expected = {e["item"]: e["value"] for e in fixture["expected"]}
    question = next(q for q in load_set("activity")["questions"] if q["item_id"] == "core.model_origin")
    values = question["gate"]["values"]
    provisional = fixture["injected"]["p0"]["provisional"]
    assert provisional["core.activity_type"]["value"] not in values
    assert expected["core.activity_type"] in values
    assert expected["extra_round_questions"] == expected["gate_opened"] == ["core.model_origin"]
    assert expected["core.model_origin"] != provisional["core.model_origin"]["value"]
    order = expected["event_order"]
    assert order.index("support_check") < order.index("extra_round") < order.index("finalize")


def test_follow_recovery_fixture_sources_are_complete(fixtures):
    by = {f["fixture_id"]: f for f in fixtures}
    ranking = by["v27-syn-A004-07"]
    text = ranking["pages"][0]["text"]
    injected = ranking["injected"]["p0"]
    spans = injected["supported_quote_spans"] + injected["unsupported_quote_spans"]
    spans += list(injected["link_spans"].values())
    assert all(0 <= lo < hi <= len(text) for lo, hi in spans)
    assert text[slice(*injected["link_spans"]["far"])] == "far link passage"
    assert text[slice(*injected["link_spans"]["near"])] == "near link passage"
    fetching = by["v27-syn-A004-09"]
    pages = {p["page_key"]: p for p in fetching["pages"]}
    assert set(fetching["injected"]) <= pages.keys()
    targets = {p["url"] for p in pages.values()}
    assert all(link["url"] in targets for p in pages.values() for link in p["links"])
    assert all(p["text"] and p["fetch_status"] == "ok" for p in pages.values())


def _follow_fixture_page(fixture, raw):
    from g3o.common.page_chunks import Chunk
    from g3o.extract.request_v27 import Pass1Page

    fields = fixture["injected"][raw["page_key"]]
    return Pass1Page(
        page_id=raw["page_key"], institution_id=fixture["institution"]["institution_id"],
        institution_name=fixture["institution"]["name"], url=raw["url"], title=raw["title"],
        text=raw["text"], chunks=(Chunk("c1", raw["page_key"], 0, len(raw["text"]), raw["text"], 1),),
        codes=(), verdict=fields["core.page_verdict"]["value"],
        page_complete=fields["core.page_complete"]["value"], links=tuple(raw["links"]))


def _follow_fixture_extraction(page, passages):
    from g3o.extract.parser_v27 import Pass1Extraction, SelectedLink

    links = tuple(SelectedLink(f"L{i:03d}", link["url"], "c1", passages[i - 1])
                  for i, link in enumerate(page.links, 1))
    return Pass1Extraction(page_id=page.page_id, custom_id="fixture", quotes=(), links=links,
                          activities=(), publication_date=None, link_status=None)


def test_ranking_fixture_with_production_follow(fixtures):
    follow = pytest.importorskip("g3o.scrape.follow", reason="requires T-025 integration")
    f = next(f for f in fixtures if f["fixture_id"] == "v27-syn-A004-07")
    p = _follow_fixture_page(f, f["pages"][0])
    injected = f["injected"]["p0"]
    passages = [p.text[slice(*injected["link_spans"][key])] if key in injected["link_spans"]
                else "absent " + key for key in ("far", "near", "unlocated1", "unlocated2")]
    ex = _follow_fixture_extraction(p, passages)
    supported = [p.text[slice(*span)] for span in injected["supported_quote_spans"]]
    state = follow.InstitutionFollow(p.institution_id, "fixture")
    state.register_original(p.url)
    ranked = state.candidates([(p, ex)], supported={p.page_id: supported})
    expected = next(e["value"] for e in f["expected"] if e["item"] == "follow_order")
    assert [c.url.rsplit("/", 1)[1] for c in ranked] == expected


def test_target_page_fixture_with_production_follow(fixtures, tmp_path):
    follow = pytest.importorskip("g3o.scrape.follow", reason="requires T-025 integration")
    from g3o.run.presweep.stage_follow import FetchResult, run_follow_round
    from g3o.scrape.render import FetchMetadata, RenderedPage

    f = next(f for f in fixtures if f["fixture_id"] == "v27-syn-A004-09")
    pages = {p["url"]: p for p in f["pages"]}
    p0 = _follow_fixture_page(f, f["pages"][0])
    state = follow.InstitutionFollow(p0.institution_id, "fixture")
    state.register_original(p0.url)
    events = ["pass1:p0", "extract:p0"]
    ex = _follow_fixture_extraction(p0, [link["anchor"] for link in p0.links])

    def fetch(url):
        raw = pages[url]
        events.append("follow:" + raw["page_key"])
        return FetchResult(follow.FETCHED, RenderedPage(
            url=url, text=raw["text"], title=raw["title"], content_type="html",
            fetch_metadata=FetchMetadata(access_date="2026-11-07", fetch_method="html")))

    fetched = run_follow_round(tmp_path, {p0.institution_id: state}, [(p0, ex)], fetch=fetch, supported={})
    assert len(fetched) == 1 and fetched[0].page.text == pages[fetched[0].page.url]["text"]
    p1 = _follow_fixture_page(f, pages[fetched[0].page.url])
    events += ["pass1:p1", "extract:p1"]
    assert run_follow_round(tmp_path, {p0.institution_id: state},
                            [(p1, _follow_fixture_extraction(p1, []))], fetch=fetch, supported={}) == []
    expected = {e["item"]: e["value"] for e in f["expected"]}
    assert events == expected["event_order"]
    assert {k: events.count("extract:" + k) for k in ("p0", "p1")} == expected["extractor_calls"]
