"""Every query that finds a URL is recorded, not just the one that wins dedup.

PI ruling 2026-08-30, on the question "why can't we have a union without
dropping info?". The answer the code gave was: the union never dropped a *URL*
-- both legs iterate every query and keep every distinct link, and the coding
decision for an institution has always seen the full candidate set. What it
dropped was **attribution**. A URL returned by the English, Arabic and French
queries was written once and stamped with whichever query got there first, and
``_query_provenance`` records a query's parameters but never its result URLs,
so the other two findings were unrecoverable from the artifact.

That made ``report.health`` and ``report.filter_eligibility`` quietly wrong
about a question they both ask by name: which languages surfaced this URL.
Their per-URL language set could only ever be a singleton per leg, so a
per-language health figure measured *which language got there first* and
undercounted every language behind English in issue order -- on a 90-language
policy, nearly all of them.

``found_by`` fixes it at the recording layer and costs nothing: every query in
it was issued and paid for either way. Order still decides which query's title
and snippet the record carries -- that is a single query's text and stays
first-writer -- but it no longer decides what the artifact *knows*.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.discovery.serper_client import SerperResult
from g3o.report.filter_eligibility import record_languages
from g3o.run import presweep as ps
from tests._layout import inst_dir as inst_dir_of
from tests.test_discovery_chain import _plan, _rows


class _PerQueryRecorder:
    """Returns a different link set per query, so a union can be told from a pick."""

    def __init__(self, by_substring: dict[str, list[str]], default: list[str]):
        self.queries: list[str] = []
        self._by_substring = by_substring
        self._default = default

    def __call__(
        self, query, num_results=10, force_refresh=False, options=None,
        credentials=None,
    ):
        self.queries.append(query)
        links = self._default
        for needle, ls in self._by_substring.items():
            if needle in query:
                links = ls
                break
        return SerperResult(
            results=[
                {"link": u, "title": "t::" + query, "snippet": "s::" + query,
                 "domain": "example.gov", "position": i + 1, "date": None,
                 "sitelinks": []}
                for i, u in enumerate(links)
            ],
            search_parameters={"q": query, "autocorrect": False},
            from_cache=False,
            payload={"q": query, "num": num_results},
        )


# Deliberately not substrings of one another: the recorder routes by substring,
# and "AI" inside "AI-ar-term" would make every query look like the English one.
TERMS = {"en": "term-en", "ar": "term-ar", "fr": "term-fr"}
SHARED = "https://example.gov/shared"
ARABIC_ONLY = "https://example.gov/arabic-only"


def _run_1b(tmp_path: Path, monkeypatch, links_by_lang: dict[str, list[str]]):
    plan = _plan(tmp_path, _rows(1), discovery_mode="chain")
    official = {ps.synth_institution_id(r): "https://example.gov/" for r in plan.sample}
    rec = _PerQueryRecorder(
        {TERMS[lang]: links for lang, links in links_by_lang.items()},
        default=[SHARED],
    )
    monkeypatch.setattr(ps.stage_discovery, "search_google_detailed", rec)
    out = ps._run_discovery_site_restricted(
        plan.run_dir, plan.sample, official,
        languages=("en", "ar", "fr"), num_results=10, mode="chain",
        evidence_terms=TERMS,
    )
    inst_id = ps.synth_institution_id(plan.sample[0])
    return plan, inst_id, out[inst_id], rec


def _record_for(records: list[dict[str, Any]], url: str) -> dict[str, Any]:
    matches = [r for r in records if r["link"] == url]
    assert len(matches) == 1, f"{url} should appear once, got {len(matches)}"
    return matches[0]


def test_a_url_three_languages_found_names_all_three(tmp_path, monkeypatch):
    """The load-bearing one. Every language that returned the URL is recorded."""
    _, _, records, rec = _run_1b(
        tmp_path, monkeypatch,
        {"en": [SHARED], "ar": [SHARED], "fr": [SHARED]},
    )
    assert len(rec.queries) == 3, "three configured languages, three leg-2 queries"
    shared = _record_for(records, SHARED)
    assert {f["language"] for f in shared["found_by"]} == {"en", "ar", "fr"}
    assert record_languages(shared) == {"en", "ar", "fr"}


def test_the_first_finder_still_owns_query_language_title_and_snippet(
    tmp_path, monkeypatch
):
    """``found_by`` is additive. The record's own text is still one query's."""
    _, _, records, _ = _run_1b(
        tmp_path, monkeypatch,
        {"en": [SHARED], "ar": [SHARED], "fr": [SHARED]},
    )
    shared = _record_for(records, SHARED)
    assert shared["language"] == "en"
    assert TERMS["en"] in shared["query"]
    assert shared["snippet"] == "s::" + shared["query"]
    assert shared["found_by"][0] == {
        "query": shared["query"], "language": shared["language"]
    }, "the first finder leads found_by rather than being appended to it"


def test_the_union_is_still_a_union_and_loses_no_url(tmp_path, monkeypatch):
    """The premise this change did NOT alter: no query's URL is dropped."""
    _, _, records, _ = _run_1b(
        tmp_path, monkeypatch,
        {"en": [SHARED], "ar": [SHARED, ARABIC_ONLY], "fr": [SHARED]},
    )
    assert {r["link"] for r in records} == {SHARED, ARABIC_ONLY}
    arabic_only = _record_for(records, ARABIC_ONLY)
    assert record_languages(arabic_only) == {"ar"}


def test_query_order_no_longer_decides_the_language_set(tmp_path, monkeypatch):
    """The twin. Reversing which language is issued first moves ``language`` --
    the first-writer field -- but leaves ``found_by`` identical. That is the
    whole point: attribution stops depending on issue order.
    """
    _, _, forward, _ = _run_1b(
        tmp_path, monkeypatch, {"en": [SHARED], "ar": [SHARED], "fr": [SHARED]},
    )
    rev_root = tmp_path / "rev"
    rev_root.mkdir()
    plan = _plan(rev_root, _rows(1), discovery_mode="chain")
    official = {ps.synth_institution_id(r): "https://example.gov/" for r in plan.sample}
    rec = _PerQueryRecorder({}, default=[SHARED])
    monkeypatch.setattr(ps.stage_discovery, "search_google_detailed", rec)
    # Order is reversed by reversing the *terms mapping*, not the ``languages``
    # tuple: in chain mode leg 1b builds its query list from ``terms.items()``
    # (``stage_discovery`` ~L470), so the mapping's insertion order is the issue
    # order. ``languages`` does not reach this leg at all under a chain run.
    # That is why the policy path can control order -- ``evidence_terms_for``
    # builds its dict in ``languages_for`` order -- and why passing a reordered
    # ``languages`` alone would be a no-op here.
    out = ps._run_discovery_site_restricted(
        plan.run_dir, plan.sample, official,
        languages=("fr", "ar", "en"), num_results=10, mode="chain",
        evidence_terms={"fr": TERMS["fr"], "ar": TERMS["ar"], "en": TERMS["en"]},
    )
    reversed_records = out[ps.synth_institution_id(plan.sample[0])]
    fwd = _record_for(forward, SHARED)
    rev = _record_for(reversed_records, SHARED)
    assert fwd["language"] == "en" and rev["language"] == "fr"
    assert record_languages(fwd) == record_languages(rev) == {"en", "ar", "fr"}


def test_leg_1a_records_every_finding_language_too(tmp_path, monkeypatch):
    """Leg 1a issues one English domain query in chain mode, but the legacy
    path issues the whole roster and hits the same dedup.
    """
    plan = _plan(tmp_path, _rows(1))
    rec = _PerQueryRecorder({}, default=[SHARED])
    monkeypatch.setattr(ps.stage_discovery, "search_google_detailed", rec)
    out = ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=("en",), num_results=10, mode="legacy",
    )
    records = out[ps.synth_institution_id(plan.sample[0])]
    shared = _record_for(records, SHARED)
    assert len(rec.queries) > 1, "legacy 1a issues the full English roster"
    assert len(shared["found_by"]) == len(rec.queries), (
        "every roster query returned this URL, so every one of them is recorded"
    )
    assert record_languages(shared) == {"en"}


def test_the_artifact_on_disk_carries_found_by(tmp_path, monkeypatch):
    """Not just the in-memory return: the persisted record is what the report
    layer reads, and it is the only place the losing queries survive.
    """
    plan, inst_id, _, _ = _run_1b(
        tmp_path, monkeypatch, {"en": [SHARED], "ar": [SHARED], "fr": [SHARED]},
    )
    payload = json.loads(
        (inst_dir_of(plan.run_dir, inst_id) / "1b_discovery_site_restricted.json")
        .read_text(encoding="utf-8")
    )
    shared = _record_for(payload["records"], SHARED)
    assert {f["language"] for f in shared["found_by"]} == {"en", "ar", "fr"}


def test_a_pre_2026_08_30_record_falls_back_to_its_single_language():
    """Artifacts written before ``found_by`` have no such key. They must keep
    reporting exactly what they always did rather than erroring or reading
    empty -- a silent empty here would zero every language-filtered figure for
    every historical run.
    """
    assert record_languages({"link": "u", "language": "ar"}) == {"ar"}
    assert record_languages({"link": "u"}) == set()
    assert record_languages({"link": "u", "found_by": [{"language": "ar"}]}) == {"ar"}
