"""Stage-by-stage funnel health report for a finished (or partial) presweep run.

Reads only from disk: manifest.json, per-institution stage artifacts, and the
attrition ledger (_attrition.jsonl).  No network or API calls.

Usage::

    from g3o.report.health import compute_health_report
    report = compute_health_report(Path("runs/my-run-id"))

The returned dict is JSON-serialisable and mirrors the schema documented in
``render.py``'s text renderer.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from g3o.common import attrition as _attrition
from g3o.common.artifact_io import artifact_stem, glob_artifacts
from g3o.common.paths import (
    institution_dir,
    iter_institution_dirs,
    require_layout,
)
from g3o.report.filter_eligibility import compute_filter_block, record_languages
from g3o.report.thresholds import HealthThresholds

# Flag literals: green = within normal bounds, warn = below warn threshold,
# fail = below fail threshold, not_run = stage was not executed.
_Flag = str  # "green" | "warn" | "fail" | "not_run"


def _url_hash(url: str) -> str:
    """Same algorithm as ``g3o.extract.batch.url_hash`` (kept local to avoid a
    report -> extract import; report reads disk artifacts only)."""
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def _flag_low_is_bad(value: float | None, *, warn: float, fail: float) -> _Flag:
    """Flag when a rate is unexpectedly *low* (high is good)."""
    if value is None:
        return "not_run"
    if value <= fail:
        return "fail"
    if value <= warn:
        return "warn"
    return "green"


def _flag_high_is_bad(value: float | None, *, warn: float, fail: float) -> _Flag:
    """Flag when a rate is unexpectedly *high* (low is good, e.g. empty-page drop)."""
    if value is None:
        return "not_run"
    if value >= fail:
        return "fail"
    if value >= warn:
        return "warn"
    return "green"


def _worst(*flags: _Flag) -> _Flag:
    for level in ("fail", "warn"):
        if level in flags:
            return level
    if all(f == "not_run" for f in flags):
        return "not_run"
    return "green"


def _pct(num: int, denom: int) -> float | None:
    if denom == 0:
        return None
    return round(num / denom, 4)


def _top_reasons(
    att: dict[tuple[str, str], int], stage: str
) -> list[dict[str, Any]]:
    return sorted(
        [{"reason": r, "count": c} for (s, r), c in att.items() if s == stage],
        key=lambda x: -x["count"],
    )


def _attrition_counters(
    records: list[dict[str, Any]],
) -> dict[tuple[str, str], int]:
    c: Counter[tuple[str, str]] = Counter()
    for rec in records:
        stage = rec.get("stage", "")
        reason = rec.get("reason", "")
        if stage and reason:
            c[(stage, reason)] += 1
    return dict(c)


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    p = run_dir / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _stage_ran(
    run_dir: Path,
    stage: str,
    *,
    has_artifacts: bool,
    att: dict[tuple[str, str], int],
) -> bool:
    """True iff the pipeline stage left any trace on disk.

    A stage counts as executed when any institution has its artifact, when it
    recorded attrition, or when its ``_state/{stage}.json`` (active) or
    ``_state/.done/{stage}.json`` (terminal) file exists. Distinguishes a
    stage that ran and produced nothing from one that never ran, so partial
    runs (``--stop-after``, crash-resume) report ``not_run`` instead of a
    spurious ``fail``.
    """
    if has_artifacts:
        return True
    if any(s == stage for (s, _r) in att):
        return True
    state_dir = run_dir / "_state"
    return (state_dir / ".done" / f"{stage}.json").exists() or (
        state_dir / f"{stage}.json"
    ).exists()


def _merge_url_langs(
    into: dict[str, set[str]], records: list[dict[str, Any]]
) -> None:
    for r in records:
        url = r.get("link")
        if url:
            into.setdefault(url, set()).update(record_languages(r))


def _collect_institution(
    inst_dir: Path, inst_id: str, *, language: str | None = None
) -> dict[str, Any]:
    """Read disk artifacts for one institution; return a metrics dict.

    ``language``, when given, restricts URL-keyed stages (1a, 1b, 3, 4, 5) to
    URLs discovered by a query tagged with that language — *any* such query, not
    only the one that won dedup. See
    :func:`g3o.report.filter_eligibility.record_languages` for the ``found_by``
    set, and ``g3o.discovery.query_builder.build_queries`` for the tag itself. Stage 2 (official-site) and Stage 6 (has_genai_activity) are
    single per-institution decisions made over the *pooled* candidate/evidence
    set, not per-language — restricting only narrows *eligibility* for those
    stages to institutions this language actually contributed URLs for; see
    ``stage_6["sources_by_language"]`` for a decision-level per-language signal
    (each source's own recorded ``source_language``, independent of which
    query found it).
    """
    d: dict[str, Any] = {"institution_id": inst_id}
    url_langs: dict[str, set[str]] = {}

    def _in_lang(url_langs_set: set[str] | None) -> bool:
        return language is None or bool(url_langs_set and language in url_langs_set)

    # Stage 1a
    p = inst_dir / "1a_discovery_general.json"
    if p.exists():
        payload = json.loads(p.read_text(encoding="utf-8"))
        records_1a = payload.get("records", [])
        _merge_url_langs(url_langs, records_1a)
        d["has_1a"] = True
        d["n_urls_1a"] = (
            len(records_1a)
            if language is None
            else sum(1 for r in records_1a if language in record_languages(r))
        )
        # Two-query chain (2026-08-01). Under ``mode="chain"`` Stage 1a is
        # domain discovery, so "did Serper return >=1 URL" is trivially true
        # for nearly every institution and the legacy gauge below can no longer
        # go red. The honest chain-mode recall signal is whether leg 1 produced
        # a *usable domain*, which the stage records into the artifact (see
        # g3o.discovery.domain_pick). Read, not recomputed: report stays
        # disk-only and does not import the discovery package.
        d["discovery_mode"] = payload.get("mode", "legacy")
        naive = payload.get("naive_domain") or {}
        d["naive_domain"] = naive.get("domain")
        d["naive_domain_rank"] = naive.get("rank")
        # Leg-1 recall against the master, written at run time by the chain.
        leg1_truth = payload.get("ground_truth") or {}
        d["has_leg1_truth"] = bool(leg1_truth)
        d["leg1_surfaced_domain"] = bool(leg1_truth.get("leg1_surfaced_domain"))
    else:
        d["has_1a"] = False
        d["n_urls_1a"] = 0
        d["discovery_mode"] = "legacy"
        d["naive_domain"] = None
        d["naive_domain_rank"] = None
        d["has_leg1_truth"] = False
        d["leg1_surfaced_domain"] = False

    # Stage 2
    p = inst_dir / "2_official_site.json"
    if p.exists():
        payload = json.loads(p.read_text(encoding="utf-8"))
        d["has_2"] = True
        d["official_site"] = payload.get("url")  # None if LLM found nothing
        d["stage2_bypassed"] = bool(payload.get("bypassed"))
        # Accuracy canary (§5.1). Written at run time by the Stage 2 runner
        # where the master supplies a `website`; absent otherwise, which is the
        # ~98% of the registry that has no ground truth.
        truth = payload.get("ground_truth") or {}
        d["has_ground_truth"] = bool(truth)
        d["ground_truth_match"] = bool(truth.get("domain_match"))
    else:
        d["has_2"] = False
        d["official_site"] = None
        d["stage2_bypassed"] = False
        d["has_ground_truth"] = False
        d["ground_truth_match"] = False

    # Stage 1b
    p = inst_dir / "1b_discovery_site_restricted.json"
    if p.exists():
        payload = json.loads(p.read_text(encoding="utf-8"))
        records_1b = payload.get("records", [])
        _merge_url_langs(url_langs, records_1b)
        d["has_1b"] = True
        d["n_urls_1b"] = (
            len(records_1b)
            if language is None
            else sum(1 for r in records_1b if language in record_languages(r))
        )
    else:
        d["has_1b"] = False
        d["n_urls_1b"] = 0

    # Stage 1d — the open evidence leg (2026-09-03). Absent on every run that
    # predates it or ran without it; present for every institution when it ran.
    p = inst_dir / "1d_discovery_evidence_open.json"
    if p.exists():
        payload = json.loads(p.read_text(encoding="utf-8"))
        records_1d = payload.get("records", [])
        _merge_url_langs(url_langs, records_1d)
        d["has_1d"] = True
        d["n_urls_1d"] = (
            len(records_1d)
            if language is None
            else sum(1 for r in records_1d if language in record_languages(r))
        )
    else:
        d["has_1d"] = False
        d["n_urls_1d"] = 0

    # Stage 3 — decisions are per-URL; attribute via the 1a/1b/1d language map.
    p = inst_dir / "3_triage.json"
    if p.exists():
        payload = json.loads(p.read_text(encoding="utf-8"))
        decisions = payload.get("decisions", [])
        if language is not None:
            decisions = [d_ for d_ in decisions if _in_lang(url_langs.get(d_.get("url")))]
        d["has_3"] = True
        d["n_urls_triaged"] = len(decisions)
        d["n_urls_kept"] = sum(1 for dec in decisions if dec.get("decision") == "keep")
        d["_kept_urls"] = [dec["url"] for dec in decisions if dec.get("decision") == "keep"]
    else:
        d["has_3"] = False
        d["n_urls_triaged"] = 0
        d["n_urls_kept"] = 0
        d["_kept_urls"] = []

    # Stage 4/5 artifact counts — attribute via url_hash of language-kept URLs.
    #
    # The filename→hash comparison must go through
    # :func:`g3o.common.artifact_io.artifact_stem`, never ``Path.stem``:
    # ``stem`` strips one suffix, so on a Phase-2 ``<hash>.json.gz`` artifact it
    # yields ``<hash>.json``, which matches no url hash and silently zeroes both
    # counters. That failure mode is a wrong number, not an exception, so no test
    # would announce it as anything but a quietly-off count.
    for key, subdir in (("n_pages_scraped", "scrape"), ("n_extracts", "extract")):
        artifacts = glob_artifacts(inst_dir / subdir)
        if language is None:
            d[key] = len(artifacts)
        else:
            wanted_hashes = {_url_hash(u) for u in d["_kept_urls"]}
            d[key] = sum(1 for f in artifacts if artifact_stem(f) in wanted_hashes)

    # Expose the URL→languages attribution map so run-level passes (e.g.
    # attrition filtering under a language restriction) reuse it.
    d["_url_langs"] = url_langs

    # Stage 6
    p = inst_dir / "6_validate.json"
    d["sources_by_language"] = Counter()
    if p.exists():
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
            d["has_6"] = True
            d["has_genai_activity"] = payload.get("institution", {}).get(
                "has_genai_activity"
            )
            for src in payload.get("sources", []):
                src_lang = src.get("source_language")
                if src_lang:
                    d["sources_by_language"][(src_lang, src.get("genai_evidence"))] += 1
        except (json.JSONDecodeError, KeyError, AttributeError):
            d["has_6"] = False
            d["has_genai_activity"] = None
    else:
        d["has_6"] = False
        d["has_genai_activity"] = None

    return d


def compute_health_report(
    run_dir: str | Path,
    thresholds: HealthThresholds | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Compute a stage-by-stage funnel health report.

    Parameters
    ----------
    run_dir:
        Path to ``runs/<run_id>/`` produced by ``g3o presweep --execute``.
    thresholds:
        PI-tunable thresholds.  Defaults to :class:`HealthThresholds` defaults.
    language:
        Optional ISO 639-1 code (e.g. ``"en"``). When given, Stages 1a, 1b, 3,
        4, and 5 are restricted to URLs discovered by a query tagged with this
        language. Stage 2 and Stage 6's ``has_genai_activity`` are single
        per-institution decisions over the pooled candidate/evidence set and
        are *not* restricted — see ``language_caveats`` and
        ``stages["6_validate"]["sources_by_language"]``.

    Returns
    -------
    dict
        JSON-serialisable report with per-stage KPIs, green/warn/fail flags,
        attrition breakdown, and the thresholds used.  Suitable for both
        machine consumption (write as JSON) and human rendering via
        :func:`g3o.report.render.render_text_report`.
    """
    run_dir = Path(run_dir)
    require_layout(run_dir)
    thresholds = thresholds or HealthThresholds()

    manifest = _load_manifest(run_dir)
    institution_ids: list[str] = manifest.get("institutions", [])

    # Fallback if manifest absent: infer from the institutions/ level. Under
    # storage layout v2 that level holds nothing but institution dirs, so the
    # pre-v2 name filtering (which never excluded final/) is gone.
    if not institution_ids:
        institution_ids = [d.name for d in iter_institution_dirs(run_dir)]

    n_institutions = len(institution_ids)

    # Attrition ledger
    ledger = _attrition.read_records(run_dir)
    att = _attrition_counters(ledger)

    # Per-institution artifact pass
    inst_data = [
        _collect_institution(institution_dir(run_dir, iid), iid, language=language)
        for iid in institution_ids
    ]

    # URLs attributed to the language filter (union over institutions). Used
    # to restrict URL-keyed attrition counts (scrape/extract) to the filtered
    # language, so per-language Stage 4/5 arithmetic never mixes pooled drops
    # with filtered successes.
    lang_urls: set[str] = set()
    if language is not None:
        for d in inst_data:
            for url, langs in d["_url_langs"].items():
                if language in langs:
                    lang_urls.add(url)

    def _att_count(stage: str, reason: str) -> int:
        """Attrition count for (stage, reason), respecting the language filter."""
        if language is None:
            return att.get((stage, reason), 0)
        return sum(
            1
            for rec in ledger
            if rec.get("stage") == stage
            and rec.get("reason") == reason
            and rec.get("url") in lang_urls
        )

    # ── Stage 1a ──────────────────────────────────────────────────────────────
    n_1a_with_urls = sum(1 for d in inst_data if d["n_urls_1a"] > 0)
    total_urls_1a = sum(d["n_urls_1a"] for d in inst_data)
    pct_1a = _pct(n_1a_with_urls, n_institutions)

    stage_1a: dict[str, Any] = {
        "n_institutions_in": n_institutions,
        "n_institutions_with_urls": n_1a_with_urls,
        "pct_institutions_with_urls": pct_1a,
        "total_candidate_urls": total_urls_1a,
        "mean_urls_per_institution": (
            round(total_urls_1a / n_institutions, 2) if n_institutions else None
        ),
        "n_serper_failed": att.get(("discovery_general", "serper_request_failed"), 0),
        "top_drop_reasons": _top_reasons(att, "discovery_general"),
        "flag": _flag_low_is_bad(
            pct_1a,
            warn=thresholds.discovery_general_warn_pct,
            fail=thresholds.discovery_general_fail_pct,
        ),
    }

    # Chain mode: replace the stage flag with a gauge that can actually go red.
    #
    # ``pct_institutions_with_urls`` measures "Serper returned something". Under
    # the legacy roster that was a real recall signal (3/24 institutions
    # returned zero on the evaluation set). Under leg 1 —
    # ``<name> <country> official website`` — essentially every institution
    # gets results, so the legacy flag would sit permanently green while
    # reporting nothing. What matters in chain mode is whether leg 1 found a
    # *usable domain* for Stage 2 to adjudicate: 21/24 on the evaluation set.
    #
    # Both figures are always reported; only the flag switches, so a chain run
    # and a legacy run stay comparable line-for-line.
    if any(d["discovery_mode"] == "chain" for d in inst_data):
        chain_data = [d for d in inst_data if d["discovery_mode"] == "chain"]
        n_chain = len(chain_data)
        n_with_domain = sum(1 for d in chain_data if d["naive_domain"])
        n_rank_1 = sum(1 for d in chain_data if d["naive_domain_rank"] == 1)
        pct_domain = _pct(n_with_domain, n_chain)
        stage_1a.update(
            {
                "discovery_mode": "chain",
                "n_institutions_chain": n_chain,
                "n_institutions_with_domain": n_with_domain,
                "pct_institutions_with_domain": pct_domain,
                # Rank 1 = leg 1's very first organic result was usable. A
                # falling rank-1 share is the early warning that the query is
                # drifting off-target before the domain rate itself moves.
                "n_domain_at_rank_1": n_rank_1,
                "pct_domain_at_rank_1": _pct(n_rank_1, n_chain),
                "flag": _flag_low_is_bad(
                    pct_domain,
                    warn=thresholds.discovery_domain_warn_pct,
                    fail=thresholds.discovery_domain_fail_pct,
                ),
            }
        )
        # ── Leg-1 recall canary (§5.1, added 2026-08-02) ──────────────────
        # The gauge above cannot go red in practice: leg 1 nearly always
        # returns *some* non-aggregator host, so pct_institutions_with_domain
        # reads ~100% whatever the query does. This is the metric that moves
        # when leg 1 regresses — whether the host it returned is the RIGHT
        # one — and it is model-free, so nothing in a prompt can inflate it.
        # Unflagged below a minimum sample: ground truth covers ~2% of the
        # registry, so a small run yields too few comparisons to judge.
        leg1_data = [d for d in chain_data if d["has_leg1_truth"]]
        n_leg1 = len(leg1_data)
        n_leg1_hit = sum(1 for d in leg1_data if d["leg1_surfaced_domain"])
        pct_leg1 = _pct(n_leg1_hit, n_leg1) if n_leg1 else None
        stage_1a.update(
            {
                "n_ground_truth_available": n_leg1,
                "n_leg1_surfaced_true_domain": n_leg1_hit,
                "pct_leg1_recall": pct_leg1,
                "leg1_recall_flag": (
                    _flag_low_is_bad(
                        pct_leg1,
                        warn=thresholds.leg1_recall_warn_pct,
                        fail=thresholds.leg1_recall_fail_pct,
                    )
                    if n_leg1 >= thresholds.ground_truth_min_n
                    else "insufficient_ground_truth"
                ),
            }
        )

    # ── Stage 2 ───────────────────────────────────────────────────────────────
    # Eligible for a Stage 2 decision: institutions whose 1a discovery produced
    # candidates (LLM path), plus master-bypassed ones (bypass skips 1a). Under
    # a language filter, eligibility narrows to institutions with >=1 URL in
    # that language, and the numerator counts official sites only among them —
    # numerator and denominator always share a population.
    if language is None:
        eligible_2 = [
            d for d in inst_data if d["n_urls_1a"] > 0 or d["stage2_bypassed"]
        ]
    else:
        eligible_2 = [d for d in inst_data if d["n_urls_1a"] > 0]
    n_2_in = len(eligible_2)
    n_official_site = sum(1 for d in eligible_2 if d["official_site"])
    n_bypassed = sum(1 for d in inst_data if d["stage2_bypassed"])
    stage2_ran = _stage_ran(
        run_dir,
        "classify_official_site",
        has_artifacts=any(d["has_2"] for d in inst_data),
        att=att,
    )
    pct_official = _pct(n_official_site, n_2_in) if stage2_ran else None

    stage_2: dict[str, Any] = {
        "n_institutions_in": n_2_in,
        "n_official_site_found": n_official_site,
        "n_bypassed_from_master": n_bypassed,
        "pct_official_site_found": pct_official,
        "n_parse_failed": att.get(("classify_official_site", "parse_failed"), 0),
        "top_drop_reasons": _top_reasons(att, "classify_official_site"),
        "flag": _flag_low_is_bad(
            pct_official,
            warn=thresholds.official_site_warn_pct,
            fail=thresholds.official_site_fail_pct,
        ),
    }

    # ── Stage 2 accuracy canary (§5.1, added 2026-08-02) ──────────────────────
    # Every other Stage 1a/2 gauge measures whether the pipeline produced
    # *something*. This is the only one that measures whether it produced the
    # *right* thing, and it is the only defence against a leg-1 query
    # regression that keeps the volume gauges green.
    #
    # Two properties are deliberate. It is scored only where the master
    # supplies a `website` (~2% of the registry, national-heavy), so it is a
    # regression canary and NOT an accuracy estimate for a full sweep. And it
    # stays unflagged below a minimum sample — at 2% coverage a 10-institution
    # smoke run yields 0-1 comparisons, and a canary that fires on n=1 is
    # noise that trains you to ignore it.
    gt_data = [d for d in inst_data if d["has_ground_truth"]]
    n_gt = len(gt_data)
    n_gt_match = sum(1 for d in gt_data if d["ground_truth_match"])
    pct_gt = _pct(n_gt_match, n_gt) if n_gt else None
    stage_2.update(
        {
            "n_ground_truth_available": n_gt,
            "n_official_site_matches_master": n_gt_match,
            "pct_official_site_matches_master": pct_gt,
            "ground_truth_flag": (
                _flag_low_is_bad(
                    pct_gt,
                    warn=thresholds.official_site_accuracy_warn_pct,
                    fail=thresholds.official_site_accuracy_fail_pct,
                )
                if n_gt >= thresholds.ground_truth_min_n
                else "insufficient_ground_truth"
            ),
        }
    )

    # ── Stage 1b ──────────────────────────────────────────────────────────────
    n_1b_eligible = n_official_site  # only those with an official site get 1b queries
    n_1b_with_urls = sum(1 for d in inst_data if d["n_urls_1b"] > 0)
    total_urls_1b = sum(d["n_urls_1b"] for d in inst_data)
    pct_1b = _pct(n_1b_with_urls, n_1b_eligible)

    stage_1b: dict[str, Any] = {
        "n_institutions_eligible": n_1b_eligible,
        "n_institutions_with_1b_urls": n_1b_with_urls,
        "pct_institutions_with_1b_urls": pct_1b,
        "total_1b_urls": total_urls_1b,
        "mean_1b_urls_per_eligible": (
            round(total_urls_1b / n_1b_eligible, 2) if n_1b_eligible else None
        ),
        "n_official_site_unparseable": att.get(
            ("discovery_site_restricted", "official_site_unparseable"), 0
        ),
        "n_serper_failed": att.get(
            ("discovery_site_restricted", "serper_request_failed"), 0
        ),
        "top_drop_reasons": _top_reasons(att, "discovery_site_restricted"),
        "flag": (
            _flag_low_is_bad(
                pct_1b,
                warn=thresholds.discovery_site_restricted_warn_pct,
                fail=thresholds.discovery_site_restricted_fail_pct,
            )
            if n_1b_eligible
            else "not_run"
        ),
    }

    # ── Stage 1d — the open evidence leg (2026-09-03) ─────────────────────────
    # Every institution is eligible: the leg is not conditioned on Stage 2.
    # Informational — no threshold, no flag beyond ran / not_run — because the
    # leg's value was measured at the *institution-positive* level (card 3), and
    # a URL-count gauge here would say nothing about that.
    n_1d_with_urls = sum(1 for d in inst_data if d["n_urls_1d"] > 0)
    total_urls_1d = sum(d["n_urls_1d"] for d in inst_data)
    stage1d_ran = any(d["has_1d"] for d in inst_data)
    stage_1d: dict[str, Any] = {
        "n_institutions_in": n_institutions if stage1d_ran else 0,
        "n_institutions_with_urls": n_1d_with_urls,
        "pct_institutions_with_urls": (
            _pct(n_1d_with_urls, n_institutions) if stage1d_ran else None
        ),
        "total_candidate_urls": total_urls_1d,
        "mean_urls_per_institution": (
            round(total_urls_1d / n_institutions, 2)
            if stage1d_ran and n_institutions
            else None
        ),
        "n_serper_failed": att.get(("discovery_evidence_open", "serper_request_failed"), 0),
        "top_drop_reasons": _top_reasons(att, "discovery_evidence_open"),
        "flag": "ok" if stage1d_ran else "not_run",
    }

    # ── Stage 3 ───────────────────────────────────────────────────────────────
    n_3_eligible = sum(
        1
        for d in inst_data
        if d["n_urls_1a"] > 0 or d["n_urls_1b"] > 0 or d["n_urls_1d"] > 0
    )
    n_institutions_with_kept = sum(1 for d in inst_data if d["n_urls_kept"] > 0)
    total_urls_triaged = sum(d["n_urls_triaged"] for d in inst_data)
    total_urls_kept = sum(d["n_urls_kept"] for d in inst_data)
    stage3_ran = _stage_ran(
        run_dir,
        "classify_triage",
        has_artifacts=any(d["has_3"] for d in inst_data),
        att=att,
    )
    pct_inst_kept = _pct(n_institutions_with_kept, n_3_eligible) if stage3_ran else None
    pct_url_keep = _pct(total_urls_kept, total_urls_triaged) if stage3_ran else None

    flag_3_inst = _flag_low_is_bad(
        pct_inst_kept,
        warn=thresholds.triage_institutions_warn_pct,
        fail=thresholds.triage_institutions_fail_pct,
    )
    flag_3_url = _flag_low_is_bad(
        pct_url_keep,
        warn=thresholds.triage_url_keep_warn_pct,
        fail=thresholds.triage_url_keep_fail_pct,
    )

    stage_3: dict[str, Any] = {
        "n_institutions_in": n_3_eligible,
        "n_total_candidate_urls": total_urls_triaged,
        "n_urls_kept": total_urls_kept,
        "n_urls_dropped": total_urls_triaged - total_urls_kept,
        "pct_urls_kept": pct_url_keep,
        "n_institutions_with_kept_url": n_institutions_with_kept,
        "pct_institutions_with_kept_url": pct_inst_kept,
        "n_parse_failed": att.get(("classify_triage", "parse_failed"), 0),
        "top_drop_reasons": _top_reasons(att, "classify_triage"),
        "flag": _worst(flag_3_inst, flag_3_url),
        "_flag_institution_coverage": flag_3_inst,
        "_flag_url_keep_rate": flag_3_url,
    }

    # ── Stage 4 ───────────────────────────────────────────────────────────────
    n_urls_attempted = total_urls_kept
    n_scraped = sum(d["n_pages_scraped"] for d in inst_data)
    n_institutions_with_pages = sum(1 for d in inst_data if d["n_pages_scraped"] > 0)
    stage4_ran = _stage_ran(
        run_dir, "scrape", has_artifacts=n_scraped > 0, att=att
    )
    pct_scrape = (
        _pct(n_scraped, n_urls_attempted)
        if stage4_ran and n_urls_attempted
        else None
    )

    stage_4: dict[str, Any] = {
        "n_urls_attempted": n_urls_attempted,
        "n_pages_scraped": n_scraped,
        "n_robots_disallowed": _att_count("scrape", "robots_disallowed"),
        "n_scrape_failed": _att_count("scrape", "scrape_failed"),
        # Issue #96. Counted on its own rather than left to top_drop_reasons:
        # the other two Stage 4 drop classes are named here, and a budget expiry
        # is the one that silently shrinks coverage without any URL failing.
        "n_crawl_delay_exceeded": _att_count("scrape", "crawl_delay_exceeded"),
        # Circuit breaker (2026-09-06): the fourth Stage 4 drop class, and like
        # the budget it shrinks coverage without the skipped URL ever failing.
        "n_host_unreachable": _att_count("scrape", "host_unreachable"),
        "pct_scrape_success": pct_scrape,
        "n_institutions_with_pages": n_institutions_with_pages,
        "top_drop_reasons": _top_reasons(att, "scrape"),
        "flag": _flag_low_is_bad(
            pct_scrape,
            warn=thresholds.scrape_success_warn_pct,
            fail=thresholds.scrape_success_fail_pct,
        ),
    }

    # ── Stage 5 ───────────────────────────────────────────────────────────────
    n_empty_dropped = _att_count("extract", "empty_page_dropped")
    n_page_truncated = _att_count("extract", "page_text_truncated")
    n_extract_eligible = max(0, n_scraped - n_empty_dropped)
    total_extracts = sum(d["n_extracts"] for d in inst_data)
    n_institutions_with_extracts = sum(1 for d in inst_data if d["n_extracts"] > 0)
    pct_empty = _pct(n_empty_dropped, n_scraped)
    pct_extracted = _pct(total_extracts, n_extract_eligible)

    flag_5_extract = _flag_low_is_bad(
        pct_extracted,
        warn=thresholds.extract_success_warn_pct,
        fail=thresholds.extract_success_fail_pct,
    )
    flag_5_empty = _flag_high_is_bad(
        pct_empty,
        warn=thresholds.extract_empty_warn_pct,
        fail=thresholds.extract_empty_fail_pct,
    )

    stage_5: dict[str, Any] = {
        "n_pages_in": n_scraped,
        "n_empty_dropped": n_empty_dropped,
        "n_pages_eligible": n_extract_eligible,
        "n_pages_truncated": n_page_truncated,
        "n_extracts": total_extracts,
        "n_parse_failed": _att_count("extract", "parse_failed"),
        "pct_empty_dropped": pct_empty,
        "pct_extracted_of_eligible": pct_extracted,
        "n_institutions_with_extracts": n_institutions_with_extracts,
        "top_drop_reasons": _top_reasons(att, "extract"),
        "flag": (
            _worst(flag_5_extract, flag_5_empty) if n_scraped else "not_run"
        ),
        "_flag_extract_success": flag_5_extract,
        "_flag_empty_rate": flag_5_empty,
    }

    # ── Stage 6 ───────────────────────────────────────────────────────────────
    n_6_eligible = n_institutions_with_extracts
    n_6_consolidated = sum(1 for d in inst_data if d["has_6"])
    hga: Counter[str] = Counter(
        d["has_genai_activity"] for d in inst_data if d["has_genai_activity"]
    )
    n_6_yes = hga.get("yes", 0)
    n_6_no = hga.get("no", 0)
    n_6_unclear = hga.get("unclear", 0)
    pct_consolidated = _pct(n_6_consolidated, n_6_eligible)
    pct_unclear = _pct(n_6_unclear, n_6_consolidated)

    flag_6_consol = _flag_low_is_bad(
        pct_consolidated,
        warn=thresholds.validate_consolidated_warn_pct,
        fail=thresholds.validate_consolidated_fail_pct,
    )
    flag_6_unclear = _flag_high_is_bad(
        pct_unclear,
        warn=thresholds.validate_unclear_warn_pct,
        fail=thresholds.validate_unclear_fail_pct,
    )

    # Per-language, per-evidence source tally — a *content*-level signal (each
    # source's own recorded source_language) independent of the funnel's
    # query-provenance `language` restriction above. Always computed across
    # every language present, regardless of the `language` argument, so a
    # single unrestricted call already yields the cross-language comparison
    # `compute_language_breakdown` needs.
    sources_by_language: dict[str, dict[str, int]] = {}
    for d in inst_data:
        for (lang, evidence), count in d["sources_by_language"].items():
            bucket = sources_by_language.setdefault(lang, {})
            bucket[evidence or "unknown"] = bucket.get(evidence or "unknown", 0) + count

    stage_6: dict[str, Any] = {
        "n_institutions_in": n_6_eligible,
        "n_consolidated": n_6_consolidated,
        "n_missing_validate_json": max(0, n_6_eligible - n_6_consolidated),
        "pct_consolidated": pct_consolidated,
        "has_genai_activity": {"yes": n_6_yes, "no": n_6_no, "unclear": n_6_unclear},
        "pct_unclear": pct_unclear,
        "sources_by_language": sources_by_language,
        "top_drop_reasons": _top_reasons(att, "validate"),
        "flag": (
            _worst(flag_6_consol, flag_6_unclear) if n_6_eligible else "not_run"
        ),
        "_flag_consolidated_rate": flag_6_consol,
        "_flag_unclear_rate": flag_6_unclear,
    }

    # ── Overall ───────────────────────────────────────────────────────────────
    stages = {
        "1a_discovery_general": stage_1a,
        "2_classify_official_site": stage_2,
        "1b_discovery_site_restricted": stage_1b,
        "1d_discovery_evidence_open": stage_1d,
        "3_classify_triage": stage_3,
        "4_scrape": stage_4,
        "5_extract": stage_5,
        "6_validate": stage_6,
    }
    run_flags = [s["flag"] for s in stages.values() if s["flag"] != "not_run"]
    overall = _worst(*run_flags) if run_flags else "not_run"

    top_reasons = sorted(
        [{"stage": s, "reason": r, "count": c} for (s, r), c in att.items()],
        key=lambda x: -x["count"],
    )[:15]

    report: dict[str, Any] = {
        "run_id": manifest.get("run_id", run_dir.name),
        "run_dir": str(run_dir),
        "run_date": manifest.get("run_date"),
        "n_institutions": n_institutions,
        "stages_planned": manifest.get("stages_planned", []),
        "overall_flag": overall,
        "stages": stages,
        "attrition_top_reasons": top_reasons,
        "thresholds_used": asdict(thresholds),
        "thresholds_note": (
            "All thresholds are PI-tunable. Defaults target a smoke run "
            "(~10 institutions). Pass a custom HealthThresholds instance or "
            "--thresholds <json-file> to override."
        ),
        "language_filter": language,
        # Additive Stage 1c block (design memo 2026-07-06). Kept as its own
        # top-level key rather than inside ``stages`` so it never perturbs the
        # funnel's overall_flag — in shadow mode the filter is informational.
        "filter_eligibility": compute_filter_block(run_dir, language=language),
    }
    if language is not None:
        report["language_caveats"] = [
            "Stage 2 (official-site) is one pooled decision per institution over "
            "all candidate URLs regardless of language; only eligibility "
            f"(institutions with >=1 {language!r} URL from Stage 1a) is restricted here.",
            "Stage 6 has_genai_activity is a per-institution rollup over all "
            "evidence, not restricted to this language; see "
            "stages['6_validate']['sources_by_language'] for the per-source, "
            "per-language evidence tally instead.",
            "A URL discovered by queries in more than one language counts "
            "toward every language it was found under (Stages 3-5).",
            "Scrape/extract attrition *counts* (robots, failures, empty/"
            "truncated/parse drops) are restricted to this language's URLs; "
            "top_drop_reasons and attrition_top_reasons remain pooled.",
        ]
    return report


__all__ = ["compute_health_report", "compute_language_breakdown", "detect_languages"]


def detect_languages(run_dir: str | Path) -> list[str]:
    """Scan a run's 1a/1b discovery artifacts for every language actually queried.

    Reads only the ``queries`` list (present even for institutions with zero
    hits), so a language with no results still shows up as "attempted."
    """
    run_dir = Path(run_dir)
    require_layout(run_dir)
    langs: set[str] = set()
    for inst_dir in iter_institution_dirs(run_dir):
        for fname in (
            "1a_discovery_general.json",
            "1b_discovery_site_restricted.json",
            "1d_discovery_evidence_open.json",
        ):
            p = inst_dir / fname
            if not p.exists():
                continue
            payload = json.loads(p.read_text(encoding="utf-8"))
            for q in payload.get("queries", []):
                lang = q.get("language")
                if lang:
                    langs.add(lang)
    return sorted(langs)


def compute_language_breakdown(
    run_dir: str | Path,
    thresholds: HealthThresholds | None = None,
    languages: list[str] | None = None,
) -> dict[str, Any]:
    """Run :func:`compute_health_report` once per language for side-by-side comparison.

    Returns a compact table keyed by language, each holding the key funnel
    percentages plus the ``sources_by_language`` evidence tally, so Batch 5
    ("mirror English's quality into the other languages") can diff a candidate
    language against the English reference standard without re-deriving the
    per-stage math.
    """
    run_dir = Path(run_dir)
    require_layout(run_dir)
    languages = languages if languages is not None else detect_languages(run_dir)

    per_language: dict[str, Any] = {}
    for lang in languages:
        r = compute_health_report(run_dir, thresholds=thresholds, language=lang)
        s = r["stages"]
        per_language[lang] = {
            "overall_flag": r["overall_flag"],
            "pct_institutions_with_urls_1a": s["1a_discovery_general"][
                "pct_institutions_with_urls"
            ],
            "pct_official_site_found": s["2_classify_official_site"][
                "pct_official_site_found"
            ],
            "pct_institutions_with_1b_urls": s["1b_discovery_site_restricted"][
                "pct_institutions_with_1b_urls"
            ],
            "pct_institutions_with_kept_url": s["3_classify_triage"][
                "pct_institutions_with_kept_url"
            ],
            "pct_urls_kept": s["3_classify_triage"]["pct_urls_kept"],
            "pct_scrape_success": s["4_scrape"]["pct_scrape_success"],
            "pct_extracted_of_eligible": s["5_extract"]["pct_extracted_of_eligible"],
            "sources_by_language": s["6_validate"]["sources_by_language"].get(lang, {}),
        }

    return {
        "run_id": _load_manifest(run_dir).get("run_id", run_dir.name),
        "languages_detected": languages,
        "languages": per_language,
    }
