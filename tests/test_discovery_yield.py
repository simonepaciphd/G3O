"""Discovery-yield scoring — own-domain *relevant* hits (2026-08-01).

The metric's two documented traps, pinned as tests:

- scoring on domain match alone (own-domain hits leap 5->20 while relevant hits
  stay at 5, because fifteen are bare homepages), and
- matching ``ai`` case-insensitively, which counted Italian ebook spam and the
  French verb "ai" and inflated a headline in the findings session's first pass.
"""

from __future__ import annotations

import json

from g3o.report.discovery_yield import (
    has_genai_signal,
    is_own_domain,
    mcnemar,
    registrable_domain,
    score_institution,
    score_run,
)
from tests._layout import (
    make_inst_dir,
    write_manifest,
)

# ---------------------------------------------------------------------------
# The case-sensitivity rule
# ---------------------------------------------------------------------------


def test_standalone_ai_acronym_matches_case_sensitively():
    assert has_genai_signal("Council adopts AI policy")
    assert has_genai_signal("AI-powered permits")
    assert has_genai_signal("New tools (AI) for staff")


def test_lowercase_ai_does_not_match():
    """The regression that inflated the findings session's first pass."""
    assert not has_genai_signal("j'ai reçu le document")       # French verb
    assert not has_genai_signal("Guida ai servizi comunali")   # Italian preposition
    assert not has_genai_signal("Ai Weiwei exhibition")        # capitalised, not the acronym


def test_ai_inside_a_word_does_not_match():
    for text in ("Thailand office", "AIDS awareness week", "Chair of the Board", "email"):
        assert not has_genai_signal(text), text


def test_multiword_signals_are_case_insensitive():
    assert has_genai_signal("Artificial Intelligence strategy")
    assert has_genai_signal("generative ai pilot")
    assert has_genai_signal("Nuestra política de inteligencia artificial")
    assert has_genai_signal("ChatGPT trial")


def test_llm_acronym_is_case_sensitive():
    assert has_genai_signal("LLM deployment note")
    assert not has_genai_signal("llm.pdf")


def test_signal_may_come_from_the_url_itself():
    assert has_genai_signal(None, None, "https://x.gov/generative-ai-policy")


# ---------------------------------------------------------------------------
# Own-domain determination
# ---------------------------------------------------------------------------


def test_registrable_domain_handles_multi_level_suffixes():
    assert registrable_domain("https://www.douanes.gov.mg/x") == "douanes.gov.mg"
    assert registrable_domain("https://data.health.go.ke/") == "health.go.ke"
    assert registrable_domain("https://www.westminster.gov.uk/") == "westminster.gov.uk"
    assert registrable_domain("") == ""


def test_a_bare_public_suffix_has_no_registrable_domain():
    """``gov.uk`` is itself a suffix; treating it as a domain would make every
    UK council's URL 'own-domain' for every other UK council."""
    assert registrable_domain("gov.uk") == ""
    assert registrable_domain("https://gov.uk/") == ""


def test_subdomains_of_the_truth_domain_count_as_own():
    assert is_own_domain("https://data.douanes.gov.mg/x", "douanes.gov.mg")
    assert is_own_domain("https://www.douanes.gov.mg/", "douanes.gov.mg")


def test_a_different_host_is_not_own_domain():
    """wipo.int returned for Madagascar is exactly the leg-1 failure mode."""
    assert not is_own_domain("https://wipo.int/madagascar", "douanes.gov.mg")


def test_mail_infrastructure_hosts_are_excluded():
    assert not is_own_domain("https://autodiscover.douanes.gov.mg/", "douanes.gov.mg")
    assert not is_own_domain("https://webmail.douanes.gov.mg/", "douanes.gov.mg")


# ---------------------------------------------------------------------------
# The relevance gap — the reason the metric exists
# ---------------------------------------------------------------------------


def test_bare_homepages_count_as_own_domain_but_not_as_relevant():
    records = [
        {"link": "https://x.gov/", "title": "Home", "snippet": "Welcome to the city."},
        {"link": "https://x.gov/contact", "title": "Contact", "snippet": "Phone and address."},
        {"link": "https://x.gov/ai-policy", "title": "AI policy", "snippet": "Our approach."},
    ]
    got = score_institution(records, "https://x.gov")
    assert got["n_own_domain"] == 3
    assert got["n_own_domain_relevant"] == 1
    assert got["hit"] is True


def test_no_relevant_hit_is_not_a_hit():
    got = score_institution(
        [{"link": "https://x.gov/", "title": "Home", "snippet": "Welcome."}],
        "https://x.gov",
    )
    assert got["n_own_domain"] == 1
    assert got["n_own_domain_relevant"] == 0
    assert got["hit"] is False


def test_offsite_relevant_pages_do_not_count():
    got = score_institution(
        [{"link": "https://news.example.com/x", "title": "City adopts AI", "snippet": ""}],
        "https://x.gov",
    )
    assert got["n_own_domain"] == 0
    assert got["hit"] is False


def test_duplicate_urls_are_counted_once():
    rec = {"link": "https://x.gov/ai", "title": "AI", "snippet": ""}
    got = score_institution([rec, dict(rec)], "https://x.gov")
    assert got["n_urls"] == 1
    assert got["n_own_domain_relevant"] == 1


# ---------------------------------------------------------------------------
# Run-level scoring
# ---------------------------------------------------------------------------


def _write_run(tmp_path, insts):
    run = tmp_path / "run"
    write_manifest(run, {"run_id": "run", "institutions": sorted(insts)})
    for inst_id, (mode, recs_1a, recs_1b, naive, stage2) in insts.items():
        d = make_inst_dir(run, inst_id)
        a = {"mode": mode,
             "queries": [{"query": "q", "language": "en", "from_cache": False}],
             "records": recs_1a}
        if naive is not None:
            a["naive_domain"] = naive
        (d / "1a_discovery_general.json").write_text(json.dumps(a), encoding="utf-8")
        (d / "1b_discovery_site_restricted.json").write_text(
            json.dumps({"mode": mode,
                        "queries": [{"query": "q2", "language": "en", "from_cache": True}],
                        "records": recs_1b}),
            encoding="utf-8",
        )
        if stage2 is not None:
            (d / "2_official_site.json").write_text(
                json.dumps({"url": stage2}), encoding="utf-8"
            )
    return run


def test_score_run_pools_1a_and_1b_and_counts_queries(tmp_path):
    run = _write_run(tmp_path, {
        "INST-1": ("chain",
                   [{"link": "https://a.gov/", "title": "Home", "snippet": ""}],
                   [{"link": "https://a.gov/ai", "title": "AI plan", "snippet": ""}],
                   {"domain": "a.gov", "rank": 1}, "https://a.gov/"),
        "INST-2": ("chain",
                   [{"link": "https://b.gov/", "title": "Home", "snippet": ""}],
                   [], {"domain": "b.gov", "rank": 2}, "https://b.gov/"),
    })
    got = score_run(run, {"INST-1": "https://a.gov", "INST-2": "https://b.gov"})
    assert got["n_institutions"] == 2
    assert got["n_with_relevant_hit"] == 1          # only INST-1's 1b page is relevant
    assert got["pct_with_relevant_hit"] == 0.5
    assert got["n_queries_issued"] == 4             # 2 institutions x (1a + 1b)
    assert got["n_queries_from_cache"] == 2         # the 1b legs were cached
    assert got["queries_per_institution"] == 2.0
    assert got["naive_domain_correct"] == 2
    assert got["stage2_domain_correct"] == 2


def test_score_run_skips_institutions_without_ground_truth(tmp_path):
    run = _write_run(tmp_path, {
        "INST-1": ("chain", [{"link": "https://a.gov/ai", "title": "AI", "snippet": ""}],
                   [], None, None),
        "INST-2": ("chain", [{"link": "https://b.gov/ai", "title": "AI", "snippet": ""}],
                   [], None, None),
    })
    got = score_run(run, {"INST-1": "https://a.gov"})
    assert got["n_institutions"] == 1


def test_score_run_separates_naive_and_stage2_accuracy(tmp_path):
    """The findings' open question: does Stage 2 beat the naive rule?"""
    run = _write_run(tmp_path, {
        # Naive picks the wrong host (the wipo.int failure); Stage 2 corrects it.
        "INST-1": ("chain", [{"link": "https://wipo.int/x", "title": "t", "snippet": ""}],
                   [], {"domain": "wipo.int", "rank": 1}, "https://a.gov/"),
    })
    got = score_run(run, {"INST-1": "https://a.gov"})
    assert got["naive_domain_attempted"] == 1
    assert got["naive_domain_correct"] == 0
    assert got["stage2_domain_attempted"] == 1
    assert got["stage2_domain_correct"] == 1


# ---------------------------------------------------------------------------
# Paired significance
# ---------------------------------------------------------------------------


def test_mcnemar_reproduces_the_findings_figure():
    """9 gains, 1 loss -> two-sided p = 0.021 (the findings memo's figure)."""
    a = {f"i{n}": True for n in range(9)}
    b = {f"i{n}": False for n in range(9)}
    a["x"], b["x"] = False, True
    got = mcnemar(a, b)
    assert (got["gains"], got["losses"]) == (9, 1)
    assert round(got["p_two_sided"], 3) == 0.021


def test_mcnemar_with_no_discordant_pairs_is_p_one():
    a = {"i": True, "j": False}
    got = mcnemar(a, dict(a))
    assert got["gains"] == 0 and got["losses"] == 0
    assert got["p_two_sided"] == 1.0


def test_mcnemar_only_uses_shared_institutions():
    got = mcnemar({"i": True, "only_a": True}, {"i": False, "only_b": False})
    assert got["n_paired"] == 1


# ---------------------------------------------------------------------------
# Leg-1 recall — the ceiling on Stage 2
# ---------------------------------------------------------------------------


def test_leg1_recall_is_separate_from_the_naive_pick(tmp_path):
    """Distinguishes 'the query missed the site' from 'the pick rule chose wrong'.

    Stage 2 can only choose a domain leg 1 surfaced, so recall is the ceiling
    and the naive rule's accuracy is a floor beneath it.
    """
    run = _write_run(tmp_path, {
        # Truth IS present, at rank 2 — naive picked the aggregator-free first hit.
        "INST-1": ("chain",
                   [{"link": "https://wipo.int/x", "title": "t", "snippet": ""},
                    {"link": "https://a.gov/", "title": "Home", "snippet": ""}],
                   [], {"domain": "wipo.int", "rank": 1}, None),
        # Truth is absent entirely — no pick rule could have recovered it.
        "INST-2": ("chain",
                   [{"link": "https://wipo.int/y", "title": "t", "snippet": ""}],
                   [], {"domain": "wipo.int", "rank": 1}, None),
    })
    got = score_run(run, {"INST-1": "https://a.gov", "INST-2": "https://b.gov"})
    assert got["truth_in_leg1"] == 1          # only INST-1 surfaced its true domain
    assert got["truth_leg1_rank_1"] == 0      # and not at rank 1
    assert got["naive_domain_correct"] == 0   # the naive rule got neither
    per = got["per_institution"]
    assert per["INST-1"]["truth_leg1_rank"] == 2
    assert per["INST-2"]["truth_in_leg1"] is False


def test_leg1_recall_counts_rank_one_hits(tmp_path):
    run = _write_run(tmp_path, {
        "INST-1": ("chain", [{"link": "https://www.a.gov/", "title": "t", "snippet": ""}],
                   [], {"domain": "a.gov", "rank": 1}, None),
    })
    got = score_run(run, {"INST-1": "https://a.gov"})
    assert got["truth_in_leg1"] == 1
    assert got["truth_leg1_rank_1"] == 1
