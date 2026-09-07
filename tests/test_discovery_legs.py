"""The two discovery legs added on 2026-09-03 — the localized leg-1 fallback and
the open evidence leg — behind their flags, unit and end to end.

PI rulings this file encodes (2026-09-03), and the measurements behind them:

- **Leg 1 goes multilingual as an English-first fallback.** The localized
  suffixes are issued only where Stage 2 found no official site, and Stage 2 is
  then re-run on the widened candidates. Card 2's probe measured the additive
  alternative at zero recall gain (n=1,412, McNemar p=1.0) for ~4x the credits,
  and the fallback recovering 7 of 26 English misses
  (``leg1-suffix-roster/FINDINGS-ordering.md``, ``FINDINGS-stratumB.md``).
- **The open evidence leg enters production as a fourth leg**, in every policy
  language, additive to the site-bound chain. Card 3 measured it surfacing 45
  institutions with confirmed evidence the chain never reaches (7.5% of n=600)
  and being worthless as a replacement (``leg3/READOUT.md``).

Both default off. The first test in each section pins that a run configured
without them is byte-identical to a run before they existed.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.common import batch_client
from g3o.common.batch_client import BatchHandle, BatchResult, BatchStatus
from g3o.common.run_state import done_path
from g3o.discovery import serper_client
from g3o.discovery.query_builder import (
    DOMAIN_QUERY_SUFFIX,
    DOMAIN_SUFFIX_BY_LANG,
    EVIDENCE_TERMS_BY_LANG,
    build_open_evidence_queries,
)
from g3o.extract.batch import url_hash
from g3o.report.health import compute_health_report
from g3o.run import presweep as ps
from g3o.run.api import launch
from g3o.run.presweep import STAGES, PresweepConfig, institution_record, plan_run
from g3o.run.presweep.stage_classify import STAGE_2_FALLBACK, _candidate_urls_union
from g3o.run.presweep.stage_discovery import STAGE_1A_FALLBACK, STAGE_1D
from g3o.run.presweep.stage_filter import _records_union
from g3o.scrape.render import FetchMetadata, RenderedPage
from tests import test_e2e_presweep_smoke as smoke
from tests._layout import inst_dir as inst_dir_of
from tests.test_discovery_chain import _patch_search, _Recorder

_POLICY_ID = "2026-08-30"

_COLUMNS = [
    "institution_uid", "master_row_id", "country", "country_iso3",
    "government_level", "institution_type", "branch", "institution_name",
    "website", "disambiguation", "official_site_url",
]


def _master(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "master.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNS)
        w.writeheader()
        for i, r in enumerate(rows, start=1):
            base = {c: "" for c in _COLUMNS}
            base.update({
                "institution_uid": f"G3O-I-{i:08d}",
                "master_row_id": str(i),
                "branch": "executive",
                "government_level": "national",
                "institution_type": "ministry",
            })
            base.update(r)
            w.writerow(base)
    return path


#: France's signed row is ``['fr']`` (English prepended by policy); Germany's is
#: ``['de', 'en', 'fr']``; the United States' is ``['en']``. Three institutions,
#: three countries, three strata — the sampler takes all three.
_ROWS = [
    {"country": "France", "country_iso3": "FRA", "institution_name": "Ministry of Things"},
    {"country": "Germany", "country_iso3": "DEU", "institution_name": "Ministerium"},
    {"country": "United States", "country_iso3": "USA", "institution_name": "Department"},
]


def _config(tmp_path: Path, rows: list[dict[str, str]] | None = None, **kw: Any):
    kw.setdefault("discovery_mode", "chain")
    kw.setdefault("language_policy", _POLICY_ID)
    return PresweepConfig(
        run_id="legs-test",
        runs_dir=tmp_path / "runs",
        master_csv=_master(tmp_path, rows if rows is not None else _ROWS),
        sample_size=len(rows) if rows is not None else len(_ROWS),
        seed=22294,
        dry_run=True,
        **kw,
    )


def _by_country(plan) -> dict[str, str]:
    return {row["country"]: ps.synth_institution_id(row) for row in plan.sample}


def _read(run_dir: Path, inst_id: str, name: str) -> dict[str, Any]:
    return json.loads((inst_dir_of(run_dir, inst_id) / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The open evidence leg — query construction
# ---------------------------------------------------------------------------


def test_open_evidence_query_is_the_retired_legs_shape_with_the_signed_term():
    """Quoted name, hinted country and disambiguation, quoted native term — one per language."""
    out = build_open_evidence_queries(
        "Ain Beida",
        {"en": "AI", "fr": EVIDENCE_TERMS_BY_LANG["fr"]},
        "Algeria",
        "Oum El Bouaghi — commune",
    )
    assert out == [
        ('"Ain Beida" Algeria Oum El Bouaghi — commune "AI"', "en"),
        ('"Ain Beida" Algeria Oum El Bouaghi — commune "intelligence artificielle"', "fr"),
    ]


def test_open_evidence_query_sanitises_like_the_other_legs():
    """Token-initial ``-`` and embedded quotes go through ``_hint``/``_phrase``."""
    (q, _), = build_open_evidence_queries(
        'Comisión Municipal "B"', {"en": "AI"}, "Argentina", "Kunkavav -Vadia"
    )
    assert q == '"Comisión Municipal B" Argentina Kunkavav Vadia "AI"'


def test_open_evidence_leg_requires_chain_mode(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="discovery_evidence_open requires"):
        _config(
            tmp_path, discovery_mode="legacy", language_policy=None,
            discovery_evidence_open=True,
        )


# ---------------------------------------------------------------------------
# The open evidence leg — runner
# ---------------------------------------------------------------------------


def test_open_leg_issues_one_query_per_policy_language_and_writes_1d(
    tmp_path, monkeypatch
):
    cfg = _config(tmp_path, discovery_evidence_open=True)
    plan = plan_run(cfg)
    ids = _by_country(plan)
    rec = _Recorder(links=["https://news.example.org/story"])
    _patch_search(monkeypatch, rec)

    out = ps._run_discovery_evidence_open(
        plan.run_dir, plan.sample, num_results=10,
        evidence_terms=cfg.evidence_terms, evidence_terms_for=cfg.evidence_terms_for,
    )

    # fr: en+fr · de: de+en+fr · us: en  → 6 credits, every one quoted-term shaped.
    assert len(rec.queries) == 6
    assert all(q.startswith('"') and q.endswith('"') for q in rec.queries)
    fr = _read(plan.run_dir, ids["France"], "1d_discovery_evidence_open.json")
    assert fr["leg"] == "evidence_open"
    assert [q["language"] for q in fr["queries"]] == ["en", "fr"]
    assert all(q["leg"] == "evidence_open" for q in fr["queries"])
    # Both queries returned the same URL: one record, attributed to both.
    assert len(fr["records"]) == 1
    assert [f["language"] for f in fr["records"][0]["found_by"]] == ["en", "fr"]
    de = _read(plan.run_dir, ids["Germany"], "1d_discovery_evidence_open.json")
    assert [q["language"] for q in de["queries"]] == ["de", "en", "fr"]
    assert set(out) == set(ids.values())
    assert done_path(plan.run_dir, STAGE_1D).exists()

    # Resume: nothing re-issued.
    ps._run_discovery_evidence_open(
        plan.run_dir, plan.sample, num_results=10,
        evidence_terms=cfg.evidence_terms, evidence_terms_for=cfg.evidence_terms_for,
    )
    assert len(rec.queries) == 6


def test_open_leg_urls_join_the_triage_and_filter_unions_last():
    general = {"i": [{"link": "https://a.gov/x"}]}
    site = {"i": [{"link": "https://a.gov/y"}]}
    open_leg = {"i": [{"link": "https://news.org/z"}, {"link": "https://a.gov/x/"}]}
    assert _candidate_urls_union(general, site, "i", open_leg) == [
        "https://a.gov/x", "https://a.gov/y", "https://news.org/z",
    ]
    assert [r["link"] for r in _records_union(general, site, "i", open_leg)] == [
        "https://a.gov/x", "https://a.gov/y", "https://news.org/z",
    ]
    # Without the leg, the union is exactly what it was.
    assert _candidate_urls_union(general, site, "i") == ["https://a.gov/x", "https://a.gov/y"]


# ---------------------------------------------------------------------------
# The leg-1 fallback — runner
# ---------------------------------------------------------------------------


def _first_pass(plan, monkeypatch, cfg) -> _Recorder:
    rec = _Recorder(links=["https://example.gov/a"])
    _patch_search(monkeypatch, rec)
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=cfg.discovery_languages,
        num_results=10, mode="chain",
    )
    assert len(rec.queries) == 3 and all(q.endswith(DOMAIN_QUERY_SUFFIX) for q in rec.queries)
    return rec


def test_fallback_issues_localized_queries_only_where_stage_2_found_nothing(
    tmp_path, monkeypatch
):
    cfg = _config(tmp_path, discovery_leg1_multilingual=True)
    plan = plan_run(cfg)
    ids = _by_country(plan)
    rec = _first_pass(plan, monkeypatch, cfg)
    # Germany: Stage 2 found a site. France and the US: it did not.
    official = {ids["Germany"]: "https://example.gov/", ids["France"]: None, ids["United States"]: None}
    rec._links = ["https://ministere.gouv.fr/"]

    general, stats = ps._run_discovery_general_fallback(
        plan.run_dir, plan.sample, ps.stage_discovery._read_existing_discovery_general(plan.run_dir, plan.sample),
        official, num_results=10, fallback_languages_for=cfg.leg1_fallback_languages_for,
    )

    # Exactly one extra credit: France's ``fr`` query. No English re-issue, nothing
    # for Germany (site found) or the US (English-only row).
    assert rec.queries[3:] == [f"Ministry of Things France {DOMAIN_SUFFIX_BY_LANG['fr']}"]
    assert stats == {
        "n_institutions": 2, "n_english_only": 1, "n_queries": 1, "n_new_records": 1,
    }

    fr = _read(plan.run_dir, ids["France"], "1a_discovery_general.json")
    assert fr["fallback_pass"] == {"languages": ["fr"], "n_queries": 1, "n_new_records": 1}
    assert [(q["language"], q.get("pass")) for q in fr["queries"]] == [("en", None), ("fr", "fallback")]
    assert [r["link"] for r in fr["records"]] == ["https://example.gov/a", "https://ministere.gouv.fr/"]
    assert fr["records"][1]["found_by"] == [
        {"query": rec.queries[3], "language": "fr"}
    ]
    assert fr["naive_domain"]["domain"] == "example.gov"  # recomputed over the union
    assert general[ids["France"]] == fr["records"]

    us = _read(plan.run_dir, ids["United States"], "1a_discovery_general.json")
    assert us["fallback_pass"]["reason"] == "policy_names_english_only"
    assert len(us["records"]) == 1

    de = _read(plan.run_dir, ids["Germany"], "1a_discovery_general.json")
    assert "fallback_pass" not in de
    assert done_path(plan.run_dir, STAGE_1A_FALLBACK).exists()

    # Resume, both with and without the done marker: no second credit.
    ps._run_discovery_general_fallback(
        plan.run_dir, plan.sample, general, official, num_results=10,
        fallback_languages_for=cfg.leg1_fallback_languages_for,
    )
    done_path(plan.run_dir, STAGE_1A_FALLBACK).unlink()
    ps._run_discovery_general_fallback(
        plan.run_dir, plan.sample, general, official, num_results=10,
        fallback_languages_for=cfg.leg1_fallback_languages_for,
    )
    assert len(rec.queries) == 4


def test_fallback_leaves_a_master_bypassed_institution_alone(tmp_path, monkeypatch):
    rows = [dict(_ROWS[0], official_site_url="https://ministere.gouv.fr/")]
    cfg = _config(tmp_path, rows=rows, discovery_leg1_multilingual=True)
    plan = plan_run(cfg)
    rec = _Recorder()
    _patch_search(monkeypatch, rec)
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=cfg.discovery_languages, num_results=10, mode="chain",
    )
    inst_id = ps.synth_institution_id(plan.sample[0])
    _, stats = ps._run_discovery_general_fallback(
        plan.run_dir, plan.sample, {inst_id: []}, {inst_id: None}, num_results=10,
        fallback_languages_for=cfg.leg1_fallback_languages_for,
    )
    assert rec.queries == []
    assert stats["n_institutions"] == 0
    assert "fallback_pass" not in _read(plan.run_dir, inst_id, "1a_discovery_general.json")


# ---------------------------------------------------------------------------
# The leg-1 fallback — Stage 2 second pass
# ---------------------------------------------------------------------------


def _fake_chunked(picks: dict[str, str | None]):
    """Stand in for ``run_chunked_stage``: answer every job from ``picks``."""

    def _run(run_dir, stage, jobs, *, process_chunk_results, **kw):
        from g3o.common.run_state import mark_done

        def _results():
            for job in jobs:
                content = json.dumps(
                    {"url": picks.get(job.custom_id), "confidence": "high", "rationale": "t"}
                )
                yield BatchResult(
                    custom_id=job.custom_id, success=True,
                    response={"body": {"choices": [{"message": {"content": content}}]}},
                    error=None,
                )

        process_chunk_results(_results())
        mark_done(run_dir, stage, no_batch=True)

    return _run


def test_stage_2_fallback_rewrites_the_official_site_artifact_with_provenance(
    tmp_path, monkeypatch
):
    cfg = _config(tmp_path, discovery_leg1_multilingual=True)
    plan = plan_run(cfg)
    ids = _by_country(plan)
    _first_pass(plan, monkeypatch, cfg)
    fr, de, us = ids["France"], ids["Germany"], ids["United States"]
    # First-pass Stage 2 verdicts on disk, as the real stage writes them.
    for inst_id, url in ((fr, None), (de, "https://example.gov/"), (us, None)):
        (inst_dir_of(plan.run_dir, inst_id) / "2_official_site.json").write_text(
            json.dumps({"url": url, "confidence": "low", "rationale": "first"}),
            encoding="utf-8",
        )
    official = {fr: None, de: "https://example.gov/", us: None}
    rec = _Recorder(links=["https://ministere.gouv.fr/"])
    _patch_search(monkeypatch, rec)
    general, _ = ps._run_discovery_general_fallback(
        plan.run_dir, plan.sample,
        ps.stage_discovery._read_existing_discovery_general(plan.run_dir, plan.sample),
        official, num_results=10, fallback_languages_for=cfg.leg1_fallback_languages_for,
    )

    seen_jobs: list[list[str]] = []
    fake = _fake_chunked({fr: "https://ministere.gouv.fr/"})

    def _spy(run_dir, stage, jobs, **kw):
        seen_jobs.append([j.custom_id for j in jobs])
        return fake(run_dir, stage, jobs, **kw)

    monkeypatch.setattr(ps.stage_classify, "run_chunked_stage", _spy)

    merged, stats = ps._run_classify_official_site_fallback(
        plan.run_dir, plan.sample, general, official,
        run_id="legs-test", model="m", poll_interval=0, max_wait=1,
    )

    # Only France had a new candidate; the US had no localized query and Germany
    # had a site. One job, one find.
    assert seen_jobs == [[fr]]
    assert stats == {"n_candidates": 1, "n_found": 1}
    assert merged == {fr: "https://ministere.gouv.fr/", de: "https://example.gov/", us: None}

    payload = _read(plan.run_dir, fr, "2_official_site.json")
    assert payload["url"] == "https://ministere.gouv.fr/"
    assert payload["via_fallback"] is True
    assert payload["fallback_languages"] == ["fr"]
    assert [f["language"] for f in payload["picked_found_by"]] == ["fr"]
    assert payload["first_pass"] == {"url": None, "confidence": "low", "rationale": "first"}
    # Untouched where the pass did not apply.
    assert "via_fallback" not in _read(plan.run_dir, de, "2_official_site.json")
    assert "via_fallback" not in _read(plan.run_dir, us, "2_official_site.json")
    assert done_path(plan.run_dir, STAGE_2_FALLBACK).exists()

    # The standard Stage 2 resume reader now returns the merged answer.
    assert ps.stage_classify._read_existing_official_sites(plan.run_dir, plan.sample) == merged
    # And the fallback's own resume path reports the same statistics.
    merged2, stats2 = ps._run_classify_official_site_fallback(
        plan.run_dir, plan.sample, general, official,
        run_id="legs-test", model="m", poll_interval=0, max_wait=1,
    )
    assert (merged2, stats2) == (merged, stats)
    assert seen_jobs == [[fr]]


def test_stage_2_fallback_submits_nothing_when_the_fallback_found_no_new_url(
    tmp_path, monkeypatch
):
    """Re-adjudicating identical candidates would re-roll a verdict, so it is skipped."""
    cfg = _config(tmp_path, rows=_ROWS[:1], discovery_leg1_multilingual=True)
    plan = plan_run(cfg)
    fr = ps.synth_institution_id(plan.sample[0])
    rec = _Recorder(links=["https://example.gov/a"])
    _patch_search(monkeypatch, rec)
    ps._run_discovery_general(
        plan.run_dir, plan.sample, languages=cfg.discovery_languages, num_results=10, mode="chain",
    )
    # The localized query returns the same URL the English one did.
    general, stats = ps._run_discovery_general_fallback(
        plan.run_dir, plan.sample, {fr: []}, {fr: None}, num_results=10,
        fallback_languages_for=cfg.leg1_fallback_languages_for,
    )
    assert stats["n_new_records"] == 0
    called = []
    monkeypatch.setattr(
        ps.stage_classify, "run_chunked_stage", lambda *a, **k: called.append(a)
    )
    merged, stats2 = ps._run_classify_official_site_fallback(
        plan.run_dir, plan.sample, general, {fr: None},
        run_id="legs-test", model="m", poll_interval=0, max_wait=1,
    )
    assert called == []
    assert stats2 == {"n_candidates": 0, "n_found": 0}
    assert merged == {fr: None}
    assert done_path(plan.run_dir, STAGE_2_FALLBACK).exists()


# ---------------------------------------------------------------------------
# End to end through the orchestrator, both flags on
# ---------------------------------------------------------------------------

_EN_URLS = ["https://example.gov/ai-policy", "https://example.gov/news"]
_FR_SITE = "https://ministere.gouv.fr/"
_FR_SITE_PAGE = "https://ministere.gouv.fr/accueil"


def _launch_with_legs(tmp_path: Path, monkeypatch, **flags: Any):
    master = _master(tmp_path / "m", _ROWS)
    config = PresweepConfig(
        run_id="legs-e2e",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=3,
        seed=22294,
        dry_run=False,
        stop_after="validate",
        poll_interval=0,
        max_wait_per_stage=10,
        scrape_respect_robots=False,
        scrape_host_delay_seconds=0,
        language_policy=_POLICY_ID,
        **flags,
    )
    monkeypatch.setenv("SERPER_API_KEY", "test-serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(serper_client, "_live_mode", False, raising=False)

    institutions: dict[str, dict[str, Any]] = {}
    for row in csv.DictReader(open(master, encoding="utf-8")):
        rec = institution_record(row)
        institutions[rec["institution_id"]] = rec
    country_of = {i: r["country"] for i, r in institutions.items()}

    url_by_hash: dict[str, str] = {}
    queries: list[str] = []

    def _serper(query, num_results=5, **kw):
        queries.append(query)
        if query.endswith(DOMAIN_QUERY_SUFFIX):
            links = list(_EN_URLS)
        elif query.endswith(DOMAIN_SUFFIX_BY_LANG["fr"]):
            links = [_FR_SITE_PAGE]
        elif query.startswith("site:"):
            domain = query.split()[0][len("site:"):]
            links = [f"https://{domain}/genai"]
        else:  # the open leg: one third-party page per distinct query
            links = [f"https://news.example.org/{len(url_by_hash)}"]
        for u in links:
            url_by_hash[url_hash(u)] = u
        return serper_client.SerperResult(
            results=[
                {"link": u, "title": "t", "snippet": "s", "domain": u.split("/")[2],
                 "position": i + 1, "date": None, "sitelinks": []}
                for i, u in enumerate(links)
            ],
            search_parameters={"q": query, "num": num_results},
            from_cache=False,
            payload={"q": query, "num": num_results},
        )

    monkeypatch.setattr(ps.stage_discovery, "search_google_detailed", _serper)
    monkeypatch.setattr(smoke, "URL_BY_HASH", url_by_hash)

    def _scrape(url: str, **kwargs) -> RenderedPage:
        return RenderedPage(
            url=url,
            text=f"This page describes the institution's public activities at length. {url}",
            title="page", content_type="html",
            fetch_metadata=FetchMetadata(
                access_date=smoke.ACCESS_DATE, http_status=200, final_url=url,
                fetch_method="html", elapsed_ms=10, wait_for=None,
            ),
        )

    monkeypatch.setattr(ps.stage_scrape, "scrape_url", _scrape)

    batches: dict[str, dict[str, Any]] = {}
    submitted_stages: list[str] = []

    def _submit(jobs, *, model, completion_window, endpoint, metadata, client=None):
        batch_id = f"batch-{metadata['g3o_stage']}-{metadata['g3o_chunk']}"
        batches[batch_id] = {"stage": metadata["g3o_stage"], "jobs": list(jobs)}
        submitted_stages.append(metadata["g3o_stage"])
        return BatchHandle(
            batch_id=batch_id, input_file_id="f", submitted_at=datetime.now(timezone.utc),
            n_jobs=len(jobs),
        )

    def _poll(batch_id, *, client=None):
        return BatchStatus(
            batch_id=batch_id, status="completed", request_counts={},
            output_file_id="out", error_file_id=None,
        )

    def _site(job, *, fallback: bool) -> str:
        country = country_of[job.custom_id]
        if country == "Germany":
            url = smoke.OFFICIAL_SITE
        elif country == "France" and fallback:
            url = _FR_SITE
        else:
            url = None
        return json.dumps({"url": url, "confidence": "high", "rationale": "e2e"})

    def _fetch(batch_id, *, client=None, status=None):
        rec = batches[batch_id]
        for job in rec["jobs"]:
            stage = rec["stage"]
            if stage == "classify_official_site":
                content = _site(job, fallback=False)
            elif stage == STAGE_2_FALLBACK:
                content = _site(job, fallback=True)
            elif stage == "classify_triage":
                content = smoke._triage_content(job)
            elif stage == "extract":
                content = smoke._extract_content(job, institutions)
            elif stage == "validate":
                content = smoke._validate_content(job, institutions)
            else:  # pragma: no cover
                raise AssertionError(stage)
            yield BatchResult(
                custom_id=job.custom_id, success=True,
                response={"body": {"choices": [{"message": {"content": content}}]}},
                error=None,
            )

    monkeypatch.setattr(batch_client, "submit_batch", _submit)
    monkeypatch.setattr(batch_client, "poll_batch", _poll)
    monkeypatch.setattr(batch_client, "fetch_results", _fetch)
    monkeypatch.setattr(batch_client, "find_batches_by_metadata", lambda md, **kw: [])

    receipt = launch(config, session_id="sess-legs", invocation="api")
    return receipt, institutions, queries, submitted_stages


def test_both_legs_end_to_end_through_validate(tmp_path, monkeypatch):
    receipt, institutions, queries, submitted = _launch_with_legs(
        tmp_path, monkeypatch,
        discovery_leg1_multilingual=True, discovery_evidence_open=True,
    )
    summary = receipt.summary
    run_dir = Path(summary["run_dir"])
    ids = {r["country"]: i for i, r in institutions.items()}
    fr, de, us = ids["France"], ids["Germany"], ids["United States"]

    # --- Leg 1: English first on all three; localized only for France, whose
    # Stage 2 came back empty and whose row names a non-English language.
    domain_en = [q for q in queries if q.endswith(DOMAIN_QUERY_SUFFIX)]
    domain_fr = [q for q in queries if q.endswith(DOMAIN_SUFFIX_BY_LANG["fr"]) and not q.startswith('"')]
    assert len(domain_en) == 3
    assert domain_fr == [f"Ministry of Things France {DOMAIN_SUFFIX_BY_LANG['fr']}"]
    assert summary["n_leg1_fallback_institutions"] == 2      # France + US
    assert summary["n_leg1_fallback_english_only"] == 1      # US
    assert summary["n_leg1_fallback_queries"] == 1
    assert summary["n_leg1_fallback_new_urls"] == 1
    assert summary["n_official_sites_fallback_candidates"] == 1
    assert summary["n_official_sites_fallback"] == 1
    assert summary["n_official_sites"] == 2                  # Germany + France

    fr_1a = _read(run_dir, fr, "1a_discovery_general.json")
    assert fr_1a["fallback_pass"]["languages"] == ["fr"]
    assert [q.get("pass") for q in fr_1a["queries"]] == [None, "fallback"]
    fr_2 = _read(run_dir, fr, "2_official_site.json")
    assert fr_2["url"] == _FR_SITE and fr_2["via_fallback"] is True
    assert fr_2["first_pass"]["url"] is None
    assert [f["language"] for f in fr_2["picked_found_by"]] == ["fr"]
    assert _read(run_dir, us, "1a_discovery_general.json")["fallback_pass"]["reason"] == (
        "policy_names_english_only"
    )
    assert "fallback_pass" not in _read(run_dir, de, "1a_discovery_general.json")
    assert "via_fallback" not in _read(run_dir, de, "2_official_site.json")

    # --- Leg 2 ran for both institutions with a site, France's on the fallback's domain.
    site_queries = [q for q in queries if q.startswith("site:")]
    assert any(q.startswith("site:ministere.gouv.fr ") for q in site_queries)
    assert (inst_dir_of(run_dir, fr) / "1b_discovery_site_restricted.json").exists()
    assert not (inst_dir_of(run_dir, us) / "1b_discovery_site_restricted.json").exists()

    # --- The open leg: every institution, every policy language, and its URLs
    # reached triage.
    open_queries = [q for q in queries if q.startswith('"')]
    assert len(open_queries) == 6  # fr 2 + de 3 + us 1
    for inst_id, langs in ((fr, ["en", "fr"]), (de, ["de", "en", "fr"]), (us, ["en"])):
        d1 = _read(run_dir, inst_id, "1d_discovery_evidence_open.json")
        assert [q["language"] for q in d1["queries"]] == langs
        triaged = {d["url"] for d in _read(run_dir, inst_id, "3_triage.json")["decisions"]}
        assert {r["link"] for r in d1["records"]} <= triaged
    assert summary["n_discovery_evidence_open"] == 6

    # --- Roster invariants hold with the sub-steps in the run: every roster
    # stage has its marker, so do the three sub-steps, and the event log shows
    # the sub-steps as their own spans without disturbing the roster order.
    for stage in (*STAGES, STAGE_1A_FALLBACK, STAGE_2_FALLBACK, STAGE_1D):
        assert done_path(run_dir, stage).exists(), stage
    events = [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    started = [e["stage"] for e in events if e["event"] == "stage_started"]
    assert [s for s in started if s in STAGES] == list(STAGES)
    assert started.index(STAGE_1A_FALLBACK) < started.index(STAGE_2_FALLBACK) < started.index(
        "discovery_site_restricted"
    ) < started.index(STAGE_1D) < started.index("filter_eligibility")
    assert submitted == [
        "classify_official_site", STAGE_2_FALLBACK, "classify_triage", "extract", "validate",
    ]
    assert receipt.outcome == "completed"

    # --- The health report sees the new leg and the merged Stage 2 answer.
    health = compute_health_report(run_dir)
    assert health["stages"]["1d_discovery_evidence_open"]["n_institutions_with_urls"] == 3
    assert health["stages"]["2_classify_official_site"]["n_official_site_found"] == 2


def test_with_both_flags_off_the_run_is_the_run_it_always_was(tmp_path, monkeypatch):
    receipt, institutions, queries, submitted = _launch_with_legs(tmp_path, monkeypatch)
    summary = receipt.summary
    run_dir = Path(summary["run_dir"])
    assert not any(k.startswith("n_leg1_fallback") for k in summary)
    assert "n_official_sites_fallback" not in summary
    assert "n_discovery_evidence_open" not in summary
    assert not any(q.startswith('"') for q in queries)
    assert not any(q.endswith(DOMAIN_SUFFIX_BY_LANG["fr"]) for q in queries)
    assert submitted == ["classify_official_site", "classify_triage", "extract", "validate"]
    for inst_id in institutions:
        assert not (inst_dir_of(run_dir, inst_id) / "1d_discovery_evidence_open.json").exists()
        assert "fallback_pass" not in _read(run_dir, inst_id, "1a_discovery_general.json")
    for stage in (STAGE_1A_FALLBACK, STAGE_2_FALLBACK, STAGE_1D):
        assert not done_path(run_dir, stage).exists()
    assert summary["n_official_sites"] == 1  # Germany; France has no fallback to find it
