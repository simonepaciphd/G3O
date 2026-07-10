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

# INST1 1a: one pass (signal), one url-pattern drop (robots.txt), one
# no-signal drop. INST1 1b: one pass. INST2 1a: one pass.
_1A = {
    INST1: [
        {"link": "https://a.gov/ai-news", "title": "City adopts ChatGPT",
         "snippet": "a generative AI pilot", "language": "en"},
        {"link": "https://a.gov/robots.txt", "title": "", "snippet": "", "language": "en"},
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

_DROP_URLS = {"https://a.gov/robots.txt", "https://a.gov/minutes"}
_PASS_URLS = {"https://a.gov/ai-news", "https://a.gov/ai-policy", "https://b.gov/genai"}


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
    assert decisions["https://a.gov/minutes"] == "drop"
    assert decisions["https://a.gov/ai-news"] == "pass"

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
    assert by_url["https://a.gov/minutes"]["reason"] == E.REASON_NO_SIGNAL
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
            {"url": "https://a.gov/minutes", "decision": "keep", "rationale": "x"},
            {"url": "https://a.gov/ai-news", "decision": "keep", "rationale": "x"},
        ]}),
        encoding="utf-8",
    )

    block = compute_filter_block(run_dir)
    assert block["ran"] is True
    assert block["mode"] == "shadow"
    assert block["n_would_drop"] == 2
    assert block["drop_reasons"] == {
        E.REASON_URL_PATTERN: 1,
        E.REASON_NO_SIGNAL: 1,
    }
    en = block["per_language"]["en"]
    # would_drop ∩ llm_keep = {/minutes}; llm_keep = {/minutes, /ai-news} → 1/2.
    assert en["llm_keep"] == 2
    assert en["would_drop_and_llm_keep"] == 1
    assert en["shadow_recall"] == 0.5


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
        ("https://bit.ly/abc", []),                    # shorteners deferred (issue #8)
        ("https://twitter.com/agency", []),            # social profiles deferred
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
