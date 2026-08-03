"""Tests for Stage 1c — the deterministic eligibility pre-filter.

Mirrors ``test_health_report``'s fixture style: a minimal on-disk run directory
with 1a/1b discovery artifacts plus matching in-memory discovery dicts, so the
runner can be exercised without a live Serper/LLM path.

Coverage the design memo (2026-07-06) requires:
  * a dropped URL produces an attrition record and never reaches Stage 3;
  * shadow mode drops nothing (no attrition, union unchanged);
  * two runs over the same inputs produce byte-identical 1c artifacts;
  * the 1a/1b artifacts are untouched after the filter runs.
Plus unit coverage of the two screens (URL-pattern + keyword, incl. CJK).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from g3o.classify import eligibility as E
from g3o.common import attrition as _attrition
from g3o.report import compute_filter_block
from g3o.run.presweep import _candidate_urls_union, _run_filter_eligibility
from g3o.run.presweep.stage_filter import ARTIFACT_NAME

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

INST1 = "INST-0000001"
INST2 = "INST-0000002"

# INST1 1a: two passes and two url-pattern drops. `/minutes` carries no GenAI
# signal at all and passes anyway — that is the point of it since the snippet
# screen was retired (2026-08-02). The two drops are deliberately different
# url-pattern rules (a path rule and a host rule) so drop-reason tallies and
# shadow-recall math stay non-trivial now that only one screen remains.
# INST1 1b: one pass. INST2 1a: one pass.
_1A = {
    INST1: [
        {"link": "https://a.gov/ai-news", "title": "City adopts ChatGPT",
         "snippet": "a generative AI pilot", "language": "en"},
        {"link": "https://a.gov/robots.txt", "title": "", "snippet": "", "language": "en"},
        {"link": "https://www.facebook.com/CityDept", "title": "City Dept",
         "snippet": "our generative AI pilot", "language": "en"},
        {"link": "https://a.gov/minutes", "title": "Budget meeting",
         "snippet": "roads and parks funding", "language": "en"},
    ],
    INST2: [
        {"link": "https://b.gov/genai", "title": "GenAI",
         "snippet": "large language model deployment", "language": "en"},
    ],
}
_1B = {
    INST1: [
        {"link": "https://a.gov/ai-policy", "title": "AI policy",
         "snippet": "our generative AI policy", "language": "en",
         "site_domain": "a.gov"},
    ],
}

_DROP_URLS = {"https://a.gov/robots.txt", "https://www.facebook.com/CityDept"}
_PASS_URLS = {
    "https://a.gov/ai-news",
    "https://a.gov/ai-policy",
    "https://b.gov/genai",
    "https://a.gov/minutes",  # no GenAI signal; passes since the screen retired
}


def _sample() -> list[dict[str, Any]]:
    return [{"master_row_id": "1"}, {"master_row_id": "2"}]


def _write_discovery(run_dir: Path) -> None:
    """Write the 1a/1b discovery artifacts to disk (so inst dirs exist)."""
    for inst_id, records in _1A.items():
        p = run_dir / inst_id / "1a_discovery_general.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"queries": [{"query": "q", "language": "en"}],
                        "records": records}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    for inst_id, records in _1B.items():
        p = run_dir / inst_id / "1b_discovery_site_restricted.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"site_domain": "a.gov", "queries": [], "records": records},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run"
    d.mkdir()
    _write_discovery(d)
    _attrition._reset_cache()
    return d


def _general() -> dict[str, list[dict[str, Any]]]:
    return {k: [dict(r) for r in v] for k, v in _1A.items()}


def _site() -> dict[str, list[dict[str, Any]]]:
    return {k: [dict(r) for r in v] for k, v in _1B.items()}


# ---------------------------------------------------------------------------
# Runner behaviour
# ---------------------------------------------------------------------------


def test_shadow_drops_nothing(run_dir: Path) -> None:
    gen, site, stats = _run_filter_eligibility(
        run_dir, _sample(), _general(), _site(), mode="shadow"
    )

    # Artifact written per institution, mode recorded.
    payload = json.loads((run_dir / INST1 / ARTIFACT_NAME).read_text())
    assert payload["mode"] == "shadow"
    assert payload["rules_version"] == E.RULES_VERSION
    decisions = {d["url"]: d["decision"] for d in payload["decisions"]}
    assert decisions["https://a.gov/robots.txt"] == "drop"
    assert decisions["https://www.facebook.com/CityDept"] == "drop"
    assert decisions["https://a.gov/ai-news"] == "pass"
    assert decisions["https://a.gov/minutes"] == "pass"

    # Nothing dropped: no attrition, stats show would-drop but zero enforced.
    assert _attrition.read_records(run_dir) == []
    assert stats["n_would_drop"] == 2
    assert stats["n_enforced_drop"] == 0

    # Stage-3 union is unchanged — the would-drop URLs still reach triage.
    union = set(_candidate_urls_union(gen, site, INST1))
    assert _DROP_URLS <= union


def test_enforce_drops_and_excludes_from_triage(run_dir: Path) -> None:
    gen, site, stats = _run_filter_eligibility(
        run_dir, _sample(), _general(), _site(), mode="enforce"
    )

    # One attrition record per drop, with the coarse reason codes.
    recs = _attrition.read_records(run_dir)
    by_url = {r["url"]: r for r in recs}
    assert by_url["https://a.gov/robots.txt"]["reason"] == E.REASON_URL_PATTERN
    assert by_url["https://a.gov/robots.txt"]["stage"] == "filter_eligibility"
    assert by_url["https://www.facebook.com/CityDept"]["reason"] == E.REASON_URL_PATTERN
    assert stats["n_enforced_drop"] == 2

    # The dropped URLs never reach Stage 3; the passing ones do.
    union = set(_candidate_urls_union(gen, site, INST1))
    assert union.isdisjoint(_DROP_URLS)
    assert {"https://a.gov/ai-news", "https://a.gov/ai-policy"} <= union


def test_off_is_noop(run_dir: Path) -> None:
    gen, site, stats = _run_filter_eligibility(
        run_dir, _sample(), _general(), _site(), mode="off"
    )
    assert not (run_dir / INST1 / ARTIFACT_NAME).exists()
    assert _attrition.read_records(run_dir) == []
    assert stats["n_would_drop"] == 0
    # Union unchanged.
    assert _DROP_URLS <= set(_candidate_urls_union(gen, site, INST1))


def test_two_runs_byte_identical(tmp_path: Path) -> None:
    """Same inputs → byte-identical 1c artifacts across independent runs."""
    outputs = []
    for name in ("run_a", "run_b"):
        d = tmp_path / name
        d.mkdir()
        _write_discovery(d)
        _attrition._reset_cache()
        _run_filter_eligibility(d, _sample(), _general(), _site(), mode="enforce")
        outputs.append((d / INST1 / ARTIFACT_NAME).read_bytes())
    assert outputs[0] == outputs[1]


def test_1a_1b_artifacts_untouched(run_dir: Path) -> None:
    """The filter never mutates the discovery artifacts it reads."""
    targets = [
        run_dir / INST1 / "1a_discovery_general.json",
        run_dir / INST1 / "1b_discovery_site_restricted.json",
        run_dir / INST2 / "1a_discovery_general.json",
    ]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in targets}
    _run_filter_eligibility(run_dir, _sample(), _general(), _site(), mode="enforce")
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in targets}
    assert before == after


def test_resume_skips_but_still_enforces(run_dir: Path) -> None:
    """A .done marker short-circuits screening but still prunes + logs attrition."""
    _run_filter_eligibility(run_dir, _sample(), _general(), _site(), mode="enforce")
    _attrition._reset_cache()
    # Second call: marker present → reconstruct from disk, re-prune, dedup attrition.
    gen, site, stats = _run_filter_eligibility(
        run_dir, _sample(), _general(), _site(), mode="enforce"
    )
    assert stats["n_enforced_drop"] == 2
    assert set(_candidate_urls_union(gen, site, INST1)).isdisjoint(_DROP_URLS)


# ---------------------------------------------------------------------------
# Health-report block (incl. shadow recall)
# ---------------------------------------------------------------------------


def test_report_block_shadow_recall(run_dir: Path) -> None:
    _run_filter_eligibility(run_dir, _sample(), _general(), _site(), mode="shadow")
    # LLM (Stage 3) keeps one would-drop URL and one pass URL for INST1.
    (run_dir / INST1 / "3_triage.json").write_text(
        json.dumps({"decisions": [
            {"url": "https://www.facebook.com/CityDept", "decision": "keep", "rationale": "x"},
            {"url": "https://a.gov/ai-news", "decision": "keep", "rationale": "x"},
        ]}),
        encoding="utf-8",
    )

    block = compute_filter_block(run_dir)
    assert block["ran"] is True
    assert block["mode"] == "shadow"
    assert block["n_would_drop"] == 2
    # Both drops are url-pattern drops now that the snippet screen is retired.
    assert block["drop_reasons"] == {E.REASON_URL_PATTERN: 2}
    en = block["per_language"]["en"]
    # llm_keep = {facebook, /ai-news}; the filter would drop the facebook
    # profile and keeps /ai-news. shadow_recall is stated in PI decision 6's
    # direction — the share of LLM-kept URLs that ALSO pass — so 1/2, not the
    # complement.
    assert en["llm_keep"] == 2
    assert en["llm_keep_and_pass"] == 1
    assert en["llm_keep_and_would_drop"] == 1
    assert en["shadow_recall"] == 0.5
    assert block["shadow_recall_bar"] == 0.70


def test_shadow_recall_is_stated_in_decision_6_direction(run_dir: Path) -> None:
    """Regression for the polarity defect found in the 2026-07-31 rebase review.

    Decision 6's bar is ">=70% of LLM-kept URLs must ALSO pass the filter".
    Reporting the complement under the name "recall" meant a value of 0.75 —
    75% of LLM-kept URLs *discarded* — read as clearing the bar. Here the filter
    would drop 1 of 3 LLM-kept URLs, so a correctly-directed recall is 2/3
    (passing), not 1/3 (discarded).
    """
    _run_filter_eligibility(run_dir, _sample(), _general(), _site(), mode="shadow")
    (run_dir / INST1 / "3_triage.json").write_text(
        json.dumps({"decisions": [
            {"url": "https://a.gov/ai-news", "decision": "keep", "rationale": "x"},
            {"url": "https://a.gov/ai-policy", "decision": "keep", "rationale": "x"},
            {"url": "https://www.facebook.com/CityDept", "decision": "keep", "rationale": "x"},
        ]}),
        encoding="utf-8",
    )

    en = compute_filter_block(run_dir)["per_language"]["en"]
    assert en["llm_keep"] == 3
    assert en["llm_keep_and_pass"] == 2      # ai-news + ai-policy survive
    assert en["llm_keep_and_would_drop"] == 1  # the facebook profile is dropped
    assert en["shadow_recall"] == round(2 / 3, 4)
    # Higher is better: the reported value must exceed the complement here.
    assert en["shadow_recall"] > 0.5


def test_report_block_not_run(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    block = compute_filter_block(d)
    assert block == {"ran": False, "flag": "not_run"}


# ---------------------------------------------------------------------------
# Screen unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://x.gov/robots.txt", ["robots_txt"]),
        ("https://x.gov/sitemap.xml", ["sitemap"]),
        ("https://x.gov/sitemap-1.xml", ["sitemap"]),
        ("https://x.gov/cal/event.ics", ["calendar_feed"]),
        ("https://x.gov/news/feed/", ["calendar_feed"]),
        ("https://x.gov/login", ["login_auth"]),
        ("https://x.gov/account/sign-in", ["login_auth"]),
        ("https://x.gov/search?q=ai", ["search_results"]),
        ("https://x.gov/search/", ["search_results"]),
        # Server-page file extensions on segment rules (2026-07-09 fix).
        ("https://x.gov/login.aspx", ["login_auth"]),
        ("https://x.gov/login.php", ["login_auth"]),
        ("https://x.gov/account/signin.html", ["login_auth"]),
        ("https://x.gov/search.php", ["search_results"]),
        ("https://x.gov/search.aspx", ["search_results"]),
        ("https://x.gov/sitemap.html", ["sitemap"]),
        ("https://x.gov/sitemap.php", ["sitemap"]),
        ("https://x.gov/sitemap_index.xml", ["sitemap"]),   # regression: .xml still fires
        # Regression: legit content must still pass 1a (no over-firing).
        ("https://x.gov/newsroom/ai-strategy", []),
        ("https://x.gov/ai-strategy.html", []),             # content .html not dropped
        ("https://x.gov/search-results-for-ai-policy", []), # not a search endpoint
        ("https://x.gov/findings.html", []),                # 'find' not a whole segment
        # Host rules — PI ruling 2026-08-01 amending decision 4, closing issue
        # #8. These two previously asserted [] ("deferred pending issue #8").
        ("https://bit.ly/abc", ["url_shortener"]),
        ("https://twitter.com/agency", ["social_media_profile"]),
        ("not a url", []),                             # unparseable → fail-open
    ],
)
def test_url_pattern_hits(url: str, expected: list[str]) -> None:
    assert E.url_pattern_hits(url) == expected


@pytest.mark.parametrize(
    "title,snippet,expected",
    [
        (None, None, True),                                  # fail-open
        ("", "   ", True),                                   # whitespace → fail-open
        ("City adopts ChatGPT", "", True),                   # en
        (None, "powered by GPT4", True),                     # gpt\d no separator
        (None, "the GPT4o model", True),                     # gpt\d no separator
        (None, "GPT-4 rollout", True),                       # regression: hyphen form
        ("Politique d'IA générative", None, True),           # fr
        (None, "市の生成AI導入について", True),                # ja substring
        (None, "政府发布生成式AI政策", True),                  # zh substring
        ("Budget meeting", "roads and parks", False),        # no signal
        ("Alberta update", "provincial news", False),        # boundary: not 'albert'
    ],
)
def test_has_genai_signal(title, snippet, expected) -> None:
    assert E.has_genai_signal(title, snippet) is expected


# ---------------------------------------------------------------------------
# Stage-list integration — inserting 1c into STAGES has to reach the reporting
# modules that enumerate stages independently, or the stage is silently
# invisible in the run summary and mis-attributed in outcome tracking.
# (Gap found during the 2026-07-31 rebase; all three modules postdate PR #9.)
# ---------------------------------------------------------------------------


def test_run_summary_stage_order_matches_config_stages() -> None:
    """``run_summary._STAGE_ORDER`` claims to mirror ``config.STAGES``.

    It is a hand-maintained copy, so a new stage inserted into ``STAGES``
    silently drops out of ``per_stage_completion`` and the per-stage timing
    table unless this stays in sync.
    """
    from g3o.report.run_summary import _STAGE_ORDER
    from g3o.run.presweep.config import STAGES

    assert _STAGE_ORDER == tuple(STAGES)


def test_stage_reached_recognises_filter_eligibility_artifact(tmp_path: Path) -> None:
    """An institution whose newest artifact is 1c must report 1c as reached.

    Without this, ``--stop-after filter_eligibility`` reports every institution
    as having stopped at ``discovery_site_restricted``.
    """
    from g3o.report.outcomes import _stage_reached

    inst_dir = tmp_path / "inst"
    inst_dir.mkdir()
    (inst_dir / "1a_discovery_general.json").write_text("{}", encoding="utf-8")
    (inst_dir / "1b_discovery_site_restricted.json").write_text("{}", encoding="utf-8")
    assert _stage_reached(inst_dir) == "discovery_site_restricted"

    (inst_dir / ARTIFACT_NAME).write_text("{}", encoding="utf-8")
    assert _stage_reached(inst_dir) == "filter_eligibility"

    # Downstream stages still win over 1c.
    (inst_dir / "3_triage.json").write_text("{}", encoding="utf-8")
    assert _stage_reached(inst_dir) == "classify_triage"


def test_stage1c_writes_per_institution_timing(run_dir: Path) -> None:
    """1c is a deterministic stage, so it must emit per-institution timing like
    Stages 1a/1b/4 — otherwise it is a blank row in the run-summary timing table.
    """
    from g3o.common.timing import read_timing

    _run_filter_eligibility(run_dir, _sample(), _general(), _site(), mode="shadow")

    timing = read_timing(run_dir, INST1)
    assert timing is not None
    assert "filter_eligibility" in json.dumps(timing)


# ---------------------------------------------------------------------------
# 1a precision — the URLs the narrowed rules must NOT drop (PI ruling
# 2026-08-01, defect 8). Decision 4's posture is false-positives-near-zero, so
# each of these is a real G3O evidence surface an earlier draft rule ate.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,why",
    [
        ("https://algoritmeregister.amsterdam.nl/en/ai-register/", "AI register"),
        ("https://gov.example/register/ai-systems", "national algorithm register"),
        ("https://gov.example/registers/algorithms", "plural registers"),
        ("https://parliament.gov.example/session/2026/ai-debate", "parliamentary session"),
        ("https://parliament.gov.example/sessions/2026-spring", "plural sessions"),
        ("https://council.gov.example/find/ai-services", "'find' as content prefix"),
        ("https://gov.example/index.php?q=node/4211", "legacy Drupal content path"),
        ("https://gov.example/page?s=1&id=99", "'s' as a sort param"),
        ("https://gov.example/auth/ai-strategy", "'auth' = authority"),
    ],
)
def test_url_pattern_does_not_drop_real_evidence_surfaces(url, why) -> None:
    assert E.url_pattern_hits(url) == [], why


@pytest.mark.parametrize(
    "url,rule",
    [
        ("https://gov.example/robots.txt", "robots_txt"),
        ("https://gov.example/sitemap.xml", "sitemap"),
        ("https://gov.example/login", "login_auth"),
        ("https://gov.example/wp-login.php", "login_auth"),
        ("https://gov.example/signup/", "login_auth"),
        ("https://gov.example/search?q=ai", "search_results"),
        ("https://gov.example/results?query=ai", "search_results"),
        ("https://gov.example/events.ics", "calendar_feed"),
        ("https://gov.example/feed/", "calendar_feed"),
    ],
)
def test_url_pattern_still_drops_plumbing(url, rule) -> None:
    """Narrowing must not have gutted the rules it narrowed."""
    assert rule in E.url_pattern_hits(url)


# ---------------------------------------------------------------------------
# 1a host rules — PI ruling 2026-08-01 amending decision 4 (issue #8).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,rule",
    [
        ("https://bit.ly/3xYz12", "url_shortener"),
        ("https://t.co/abc123", "url_shortener"),
        ("https://tinyurl.com/ai-plan", "url_shortener"),
        ("https://twitter.com/some_ministry", "social_media_profile"),
        ("https://x.com/some_ministry/", "social_media_profile"),
        ("https://facebook.com/CityOfExample/", "social_media_profile"),
        ("https://www.linkedin.com/company/some-agency", "social_media_profile"),
        ("https://www.linkedin.com/in/some-official", "social_media_profile"),
    ],
)
def test_host_rules_drop_shorteners_and_bare_profiles(url, rule) -> None:
    assert rule in E.host_rule_hits(url)
    assert rule in E.url_pattern_hits(url)  # folded into the combined screen


@pytest.mark.parametrize(
    "url,why",
    [
        ("https://twitter.com/minister/status/1789", "a post may BE the record"),
        ("https://x.com/gov_dept/status/42", "post, not profile"),
        ("https://t.me/gov_channel/451", "channel post, not the channel"),
        ("https://www.youtube.com/watch?v=abc123", "youtube deliberately off the list"),
        ("https://www.youtube.com/@ministry", "youtube deliberately off the list"),
        ("https://www.linkedin.com/posts/some-agency-ai-launch", "post, not /company/"),
        ("https://notbit.ly/ai-policy", "host merely ends in similar text"),
        ("https://gov.example/t.co/report", "shortener name inside a path"),
        ("https://gov.example/about", "ordinary government page"),
    ],
)
def test_host_rules_keep_posts_and_lookalikes(url, why) -> None:
    assert E.host_rule_hits(url) == [], why


def test_host_rules_match_subdomains_and_strip_www() -> None:
    assert E.host_rule_hits("https://www.bit.ly/abc") == ["url_shortener"]
    assert E.host_rule_hits("https://m.facebook.com/Dept") == ["social_media_profile"]
    assert E.host_rule_hits("https://bit.ly:443/abc") == ["url_shortener"]


def test_snippet_screen_is_retired_from_evaluate() -> None:
    """PI decision 2026-08-02: 1c no longer screens title/snippet for GenAI.

    It measured 3.9% shadow recall against a >=70% bar on run
    20260802-e2e-100 — enforcing it would have discarded ~96% of the funnel.
    An institution's own homepage is the canonical casualty: leg 1 asks
    "<name> <country> official website", so the snippet describes the
    institution and never AI.
    """
    homepage = E.evaluate(
        {"link": "https://a.gov/", "title": "Ministry of Finance",
         "snippet": "Official website of the Ministry of Finance."}
    )
    assert homepage["decision"] == "pass"
    assert homepage["matched_rules"] == []
    assert homepage["reason"] is None

    # Nothing about the text matters any more — not even obvious non-content.
    assert E.evaluate(
        {"link": "https://a.gov/minutes", "title": "Budget meeting",
         "snippet": "roads and parks funding"}
    )["decision"] == "pass"

    # The screen itself is retained (and still correct) for whatever replaces
    # it; it is simply no longer reachable from evaluate().
    assert E.has_genai_signal("Ministry of Finance", "Official website.") is False
    assert E.has_genai_signal("AI strategy", "generative AI") is True


def test_retirement_is_recorded_in_the_rules_version() -> None:
    """A 1c decision must always be traceable to the rules that produced it.

    Artifacts written before 2026-08-02 carry `1c-draft-2026-08-01` and were
    produced by a screen that no longer runs, so the version must not still
    claim to be that rule set.
    """
    assert E.RULES_VERSION == "1c-url-hygiene-2026-08-02"


def test_host_rule_drop_flows_through_evaluate() -> None:
    """A shortener with a perfectly good GenAI snippet is still a 1a drop:
    1a runs first and the target text is not the shortener's text."""
    result = E.evaluate(
        {"link": "https://bit.ly/3xYz12", "title": "Generative AI strategy",
         "snippet": "our generative AI strategy"}
    )
    assert result["decision"] == "drop"
    assert result["reason"] == E.REASON_URL_PATTERN
    assert "url_shortener" in result["matched_rules"]
