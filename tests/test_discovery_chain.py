"""Two-query discovery chain (2026-08-01).

Specification: ``agent-workspace/2026-08-01-serper-discovery-yield-findings.md``.
The chain replaces Stage 1a/1b's eight-term four-slot roster (16 credits/inst,
6/24 relevant) with two 1-credit legs (14/24; paired McNemar p=0.021):

    leg 1  <name> <country> official website     -> candidate domains
    leg 2  site:<domain> AI                      -> GenAI evidence on that domain

These tests pin the three things that make it correct rather than merely
cheaper: the credit count, the language tag the report layer depends on, and
the fact that legacy behaviour is genuinely unchanged when unopted-in.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from g3o.common import config as g3o_config
from g3o.discovery import domain_pick
from g3o.discovery.query_builder import (
    build_domain_query,
    build_evidence_query,
    build_queries,
)
from g3o.discovery.serper_client import SerperResult
from g3o.report.health import compute_health_report, detect_languages
from g3o.run import presweep as ps
from g3o.run.presweep import PresweepConfig, plan_run

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_COLUMNS = [
    "master_row_id", "country", "country_iso3", "government_level",
    "institution_type", "branch", "institution_name", "website",
    "disambiguation",
]


def _master(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "master.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNS)
        w.writeheader()
        for i, r in enumerate(rows, start=1):
            base = {c: "" for c in _COLUMNS}
            base.update({"master_row_id": str(i), "branch": "executive"})
            base.update(r)
            w.writerow(base)
    return path


def _rows(n: int = 3) -> list[dict[str, str]]:
    return [
        {
            "country": f"Country{i}", "country_iso3": f"C{i:02d}",
            "government_level": "national", "institution_type": "ministry",
            "institution_name": f"Ministry of Things {i}",
        }
        for i in range(n)
    ]


def _plan(tmp_path: Path, rows: list[dict[str, str]], **kw: Any):
    master = _master(tmp_path, rows)
    config = PresweepConfig(
        run_id="chain-test", runs_dir=tmp_path / "runs", master_csv=master,
        sample_size=len(rows), seed=22294, dry_run=True, **kw,
    )
    return plan_run(config)


class _Recorder:
    """Stands in for ``search_google_detailed``; records every query issued."""

    def __init__(self, links: list[str] | None = None, echo: dict | None = None):
        self.queries: list[str] = []
        self._links = links if links is not None else ["https://example.gov/a"]
        self._echo = echo if echo is not None else {"q": "x", "autocorrect": False}

    def __call__(self, query, num_results=10, force_refresh=False, options=None):
        self.queries.append(query)
        return SerperResult(
            results=[
                {"link": u, "title": "t", "snippet": "s", "domain": "example.gov",
                 "position": i + 1, "date": None, "sitelinks": []}
                for i, u in enumerate(self._links)
            ],
            search_parameters=self._echo,
            from_cache=False,
            payload={"q": query, "num": num_results},
        )


def _patch_search(monkeypatch, recorder: _Recorder) -> None:
    monkeypatch.setattr(ps.stage_discovery, "search_google_detailed", recorder)


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------


def test_domain_query_is_unquoted_name_country_suffix():
    assert (
        build_domain_query("Ministry of Health", "Kenya")
        == "Ministry of Health Kenya official website"
    )


def test_domain_query_omits_absent_country():
    assert build_domain_query("Polson H S", None) == "Polson H S official website"
    assert build_domain_query("Polson H S", "") == "Polson H S official website"


def test_domain_query_does_not_quote_the_institution_name():
    """The quoted name is the findings' primary failure mode.

    Master local names are abbreviated (``Polson H S``, ``KELLER ISD``); an
    exact-phrase match on them returns almost nothing, and three institutions
    returned zero URLs under the production control because of it.
    """
    assert '"' not in build_domain_query('Comisión Municipal "B"', "Argentina")


def test_domain_query_neutralises_token_initial_minus():
    """A bare leading ``-`` is Google's exclusion operator (75 master rows)."""
    q = build_domain_query("Kunkavav -Vadia", "India")
    assert " -Vadia" not in q
    assert "Vadia" in q


def test_domain_query_keeps_mid_token_hyphen():
    assert "Al-Anbar" in build_domain_query("Al-Anbar Governorate", "Iraq")


def test_evidence_query_is_one_bare_site_bound_token():
    """No quotes, no roster, no OR-chain — all three measured worse."""
    q = build_evidence_query("example.gov")
    assert q == "site:example.gov AI"
    assert '"' not in q and " OR " not in q


def test_evidence_query_accepts_a_native_language_term():
    """The multilingual subproject passes its own token; it does not edit here."""
    assert build_evidence_query("mairie.fr", "IA") == "site:mairie.fr IA"


# ---------------------------------------------------------------------------
# Naive domain pick (the baseline Stage 2 is scored against)
# ---------------------------------------------------------------------------


def test_pick_domain_takes_first_non_aggregator_and_reports_rank():
    got = domain_pick.pick_domain([
        {"link": "https://en.wikipedia.org/wiki/X"},
        {"link": "https://www.facebook.com/x"},
        {"link": "https://health.go.ke/about"},
        {"link": "https://other.gov/x"},
    ])
    assert got == {"domain": "health.go.ke", "url": "https://health.go.ke/about", "rank": 3}


def test_pick_domain_strips_www_and_reports_rank_one():
    got = domain_pick.pick_domain([{"link": "https://www.health.go.ke/"}])
    assert got["domain"] == "health.go.ke"
    assert got["rank"] == 1


def test_pick_domain_skips_mail_infrastructure_hosts():
    got = domain_pick.pick_domain([
        {"link": "https://autodiscover.health.go.ke/x"},
        {"link": "https://webmail.health.go.ke/x"},
        {"link": "https://health.go.ke/"},
    ])
    assert got["domain"] == "health.go.ke"


def test_pick_domain_returns_stable_empty_shape_when_nothing_usable():
    got = domain_pick.pick_domain([{"link": "https://en.wikipedia.org/wiki/X"}])
    assert got == {"domain": None, "url": None, "rank": None}
    assert domain_pick.pick_domain([]) == {"domain": None, "url": None, "rank": None}


# ---------------------------------------------------------------------------
# Credit cost — the whole point of the change
# ---------------------------------------------------------------------------


def test_chain_stage_1a_issues_exactly_one_query_per_institution(tmp_path, monkeypatch):
    plan = _plan(tmp_path, _rows(3), discovery_mode="chain")
    rec = _Recorder()
    _patch_search(monkeypatch, rec)
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=("en",), num_results=10, mode="chain",
    )
    assert len(rec.queries) == 3, "chain Stage 1a must cost 1 credit/institution"
    assert all(q.endswith("official website") for q in rec.queries)


def test_chain_stage_1b_issues_exactly_one_query_per_institution(tmp_path, monkeypatch):
    plan = _plan(tmp_path, _rows(3), discovery_mode="chain")
    official = {
        ps.synth_institution_id(r): "https://example.gov/" for r in plan.sample
    }
    rec = _Recorder()
    _patch_search(monkeypatch, rec)
    ps._run_discovery_site_restricted(
        plan.run_dir, plan.sample, official,
        languages=("en",), num_results=10, mode="chain",
    )
    assert len(rec.queries) == 3, "chain Stage 1b must cost 1 credit/institution"
    assert all(q == "site:example.gov AI" for q in rec.queries)


def test_legacy_stage_1a_still_issues_the_full_roster(tmp_path, monkeypatch):
    """The opt-out path is genuinely unchanged: 8 English terms, 8 credits."""
    plan = _plan(tmp_path, _rows(1))
    rec = _Recorder()
    _patch_search(monkeypatch, rec)
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=("en",), num_results=5,
    )
    expected = [q for q, _ in build_queries(
        "Ministry of Things 0", ["en"], country="Country0", disambiguation="",
    )]
    assert rec.queries == expected
    assert len(rec.queries) == 8


def test_default_config_is_legacy():
    """Nothing changes without opting in (branch is a pure addition)."""
    cfg = PresweepConfig(run_id="x", runs_dir=Path("."), master_csv=Path("m.csv"))
    assert cfg.discovery_mode == "legacy"
    assert cfg.serper_autocorrect is None


# ---------------------------------------------------------------------------
# Collision A — the language tag the report layer depends on
# ---------------------------------------------------------------------------


def test_chain_records_and_queries_carry_a_language_tag(tmp_path, monkeypatch):
    """``health._in_lang`` treats a missing tag as "in no language".

    An untagged leg would silently zero every language-filtered health figure
    and the language-readiness bar the multilingual subproject depends on, with
    no error anywhere. This is the regression guard for that.
    """
    plan = _plan(tmp_path, _rows(2), discovery_mode="chain")
    _patch_search(monkeypatch, _Recorder())
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=("en",), num_results=10, mode="chain",
    )
    official = {
        ps.synth_institution_id(r): "https://example.gov/" for r in plan.sample
    }
    ps._run_discovery_site_restricted(
        plan.run_dir, plan.sample, official,
        languages=("en",), num_results=10, mode="chain",
    )

    for row in plan.sample:
        inst = plan.run_dir / ps.synth_institution_id(row)
        for fname in ("1a_discovery_general.json", "1b_discovery_site_restricted.json"):
            payload = json.loads((inst / fname).read_text(encoding="utf-8"))
            assert payload["records"], f"{fname} wrote no records"
            for r in payload["records"]:
                assert r.get("language"), f"{fname} record has no language tag"
            for q in payload["queries"]:
                assert q.get("language"), f"{fname} query has no language tag"


def test_chain_language_survives_into_the_health_report(tmp_path, monkeypatch):
    """End-to-end form of the guard above: the report still resolves a language."""
    plan = _plan(tmp_path, _rows(2), discovery_mode="chain")
    _patch_search(monkeypatch, _Recorder())
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=("en",), num_results=10, mode="chain",
    )
    assert detect_languages(plan.run_dir) == ["en"]
    filtered = compute_health_report(plan.run_dir, language="en")
    assert filtered["stages"]["1a_discovery_general"]["total_candidate_urls"] > 0


# ---------------------------------------------------------------------------
# Provenance recorded into the artifact
# ---------------------------------------------------------------------------


def test_chain_artifact_records_mode_leg_and_search_parameters(tmp_path, monkeypatch):
    plan = _plan(tmp_path, _rows(1), discovery_mode="chain")
    echo = {"q": "x", "num": 10, "autocorrect": False, "engine": "google"}
    _patch_search(monkeypatch, _Recorder(echo=echo))
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=("en",), num_results=10, mode="chain",
    )
    inst = plan.run_dir / ps.synth_institution_id(plan.sample[0])
    payload = json.loads((inst / "1a_discovery_general.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "chain"
    assert payload["queries"][0]["leg"] == "domain_discovery"
    assert payload["queries"][0]["searchParameters"] == echo


def test_chain_1a_records_the_naive_domain_without_acting_on_it(tmp_path, monkeypatch):
    """Recorded for scoring against Stage 2, which remains the arbiter."""
    plan = _plan(tmp_path, _rows(1), discovery_mode="chain")
    _patch_search(monkeypatch, _Recorder(links=[
        "https://en.wikipedia.org/wiki/Ministry",
        "https://ministry.go.ke/",
    ]))
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=("en",), num_results=10, mode="chain",
    )
    inst = plan.run_dir / ps.synth_institution_id(plan.sample[0])
    payload = json.loads((inst / "1a_discovery_general.json").read_text(encoding="utf-8"))
    assert payload["naive_domain"] == {
        "domain": "ministry.go.ke", "url": "https://ministry.go.ke/", "rank": 2,
    }
    # Both URLs still reach Stage 2 — the pick narrows nothing.
    assert len(payload["records"]) == 2


def test_legacy_artifact_has_no_naive_domain_key(tmp_path, monkeypatch):
    plan = _plan(tmp_path, _rows(1))
    _patch_search(monkeypatch, _Recorder())
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=("en",), num_results=5,
    )
    inst = plan.run_dir / ps.synth_institution_id(plan.sample[0])
    payload = json.loads((inst / "1a_discovery_general.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "legacy"
    assert "naive_domain" not in payload


def test_chain_unions_and_dedupes_over_a_query_list(tmp_path, monkeypatch):
    """The reserve rule: adding a leg must stay a config change, not a refactor.

    Both stages iterate a list of ``(query, language)`` pairs and dedupe by URL
    across it. Feeding the runner a two-element list must therefore just work.
    """
    plan = _plan(tmp_path, _rows(1), discovery_mode="chain")
    rec = _Recorder(links=["https://example.gov/a", "https://example.gov/b"])
    _patch_search(monkeypatch, rec)
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=("en",), num_results=10, mode="chain",
    )
    inst = plan.run_dir / ps.synth_institution_id(plan.sample[0])
    payload = json.loads((inst / "1a_discovery_general.json").read_text(encoding="utf-8"))
    # One query, two distinct URLs, no duplicates.
    assert len(payload["queries"]) == 1
    assert [r["link"] for r in payload["records"]] == [
        "https://example.gov/a", "https://example.gov/b",
    ]


# ---------------------------------------------------------------------------
# Collision B — the Stage 1a gauge must still be able to go red in chain mode
# ---------------------------------------------------------------------------


def _run_chain_1a(tmp_path, monkeypatch, links_per_inst: list[list[str]]):
    plan = _plan(tmp_path, _rows(len(links_per_inst)), discovery_mode="chain")
    calls = {"i": -1}

    def _search(query, num_results=10, force_refresh=False, options=None):
        calls["i"] += 1
        return SerperResult(
            results=[{"link": u, "title": "t", "snippet": "s"}
                     for u in links_per_inst[calls["i"]]],
            search_parameters={}, from_cache=False, payload={},
        )

    monkeypatch.setattr(ps.stage_discovery, "search_google_detailed", _search)
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=("en",), num_results=10, mode="chain",
    )
    return compute_health_report(plan.run_dir)["stages"]["1a_discovery_general"]


def test_chain_health_reports_domain_rate_not_just_url_presence(tmp_path, monkeypatch):
    """All four institutions get URLs; only two get a usable domain."""
    s = _run_chain_1a(tmp_path, monkeypatch, [
        ["https://a.gov/"],                          # usable
        ["https://b.gov/"],                          # usable
        ["https://en.wikipedia.org/wiki/C"],         # aggregator only
        ["https://www.facebook.com/d"],              # aggregator only
    ])
    assert s["discovery_mode"] == "chain"
    assert s["pct_institutions_with_urls"] == 1.0     # the gauge that can't go red
    assert s["n_institutions_with_domain"] == 2
    assert s["pct_institutions_with_domain"] == 0.5
    assert s["flag"] == "fail", "chain flag must track the domain rate, not URL presence"


def test_chain_health_flag_is_green_when_domains_are_found(tmp_path, monkeypatch):
    s = _run_chain_1a(tmp_path, monkeypatch, [["https://a.gov/"]] * 4)
    assert s["pct_institutions_with_domain"] == 1.0
    assert s["pct_domain_at_rank_1"] == 1.0
    assert s["flag"] == "green"


def test_legacy_health_keeps_the_url_presence_flag(tmp_path, monkeypatch):
    """Nothing about the legacy report changes."""
    plan = _plan(tmp_path, _rows(2))
    _patch_search(monkeypatch, _Recorder())
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=("en",), num_results=5,
    )
    s = compute_health_report(plan.run_dir)["stages"]["1a_discovery_general"]
    assert "discovery_mode" not in s
    assert "n_institutions_with_domain" not in s
    assert s["flag"] == "green"


def test_evidence_term_is_configurable_end_to_end(tmp_path, monkeypatch):
    plan = _plan(tmp_path, _rows(1), discovery_mode="chain")
    official = {ps.synth_institution_id(plan.sample[0]): "https://example.gov/"}
    rec = _Recorder()
    _patch_search(monkeypatch, rec)
    ps._run_discovery_site_restricted(
        plan.run_dir, plan.sample, official,
        languages=("en",), num_results=10, mode="chain", evidence_term="IA",
    )
    assert rec.queries == ["site:example.gov IA"]
