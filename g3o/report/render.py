"""Human-readable text renderer for the health report dict."""

from __future__ import annotations

from typing import Any

_ICON = {"green": "[OK  ]", "warn": "[WARN]", "fail": "[FAIL]", "not_run": "[----]"}


def _icon(flag: str) -> str:
    return _ICON.get(flag, f"[{flag:4}]")


def _pct_str(v: float | None, denom: int | None = None) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:.1f}%"


def _reasons_line(reasons: list[dict[str, Any]]) -> str:
    if not reasons:
        return ""
    parts = [f"{r['reason']}={r['count']}" for r in reasons[:5]]
    return "  Attrition: " + ", ".join(parts)


def render_text_report(report: dict[str, Any]) -> str:
    """Render a health report dict as a human-readable text summary."""
    lines: list[str] = []
    w = lines.append

    overall = report.get("overall_flag", "?")
    n_inst = report.get("n_institutions", "?")
    w("=" * 70)
    w("  G3O Pipeline Health Report")
    w("=" * 70)
    w(f"  Run ID : {report.get('run_id', '?')}")
    w(f"  Date   : {report.get('run_date', '?')}")
    w(f"  Dir    : {report.get('run_dir', '?')}")
    w(f"  N inst : {n_inst}")
    w(f"  Overall: {_icon(overall)}  {overall.upper()}")
    lang = report.get("language_filter")
    if lang:
        w(f"  Filtered to language: {lang!r} (Stages 1a/1b/3/4/5 only — see caveats below)")
    w("=" * 70)
    w("")
    w("Stage funnel")
    w("─" * 70)

    stages = report.get("stages", {})

    # ── Stage 1a ──
    s = stages.get("1a_discovery_general", {})
    if s:
        w(f"\n{_icon(s.get('flag','?'))}  Stage 1a — Discovery (general Serper)")
        w(f"  Input:              {s.get('n_institutions_in')} institutions")
        w(
            f"  With ≥1 URL:        {s.get('n_institutions_with_urls')}"
            f" ({_pct_str(s.get('pct_institutions_with_urls'))})"
        )
        w(f"  Total candidate URLs: {s.get('total_candidate_urls')}")
        w(f"  Mean URLs / inst:   {s.get('mean_urls_per_institution')}")
        if s.get("discovery_mode") == "chain":
            # Chain mode's real recall gauge — "≥1 URL" above is trivially true
            # for leg 1 and is retained only for line-for-line comparability
            # with a legacy run. See health.compute_health_report.
            w("  Mode:               chain (leg 1 = domain discovery)")
            w(
                f"  With usable domain: {s.get('n_institutions_with_domain')}"
                f" ({_pct_str(s.get('pct_institutions_with_domain'))})   <- flagged"
            )
            w(
                f"  Domain at rank 1:   {s.get('n_domain_at_rank_1')}"
                f" ({_pct_str(s.get('pct_domain_at_rank_1'))})"
            )
        if s.get("n_serper_failed"):
            w(f"  Serper failures:    {s['n_serper_failed']}")
        rl = _reasons_line(s.get("top_drop_reasons", []))
        if rl:
            w(rl)

    # ── Stage 2 ──
    s = stages.get("2_classify_official_site", {})
    if s:
        w(f"\n{_icon(s.get('flag','?'))}  Stage 2 — Classify official site")
        w(
            f"  Input:              {s.get('n_institutions_in')}"
            " institutions (with ≥1 URL)"
        )
        w(
            f"  Official site found:{s.get('n_official_site_found'):>3}"
            f" ({_pct_str(s.get('pct_official_site_found'))})"
        )
        if s.get("n_bypassed_from_master"):
            w(f"  Bypassed (master):  {s['n_bypassed_from_master']}")
        if s.get("n_parse_failed"):
            w(f"  Parse failures:     {s['n_parse_failed']}")
        rl = _reasons_line(s.get("top_drop_reasons", []))
        if rl:
            w(rl)

    # ── Stage 1b ──
    s = stages.get("1b_discovery_site_restricted", {})
    if s:
        w(f"\n{_icon(s.get('flag','?'))}  Stage 1b — Discovery (site-restricted Serper)")
        w(f"  Eligible (official site): {s.get('n_institutions_eligible')}")
        w(
            f"  With ≥1 1b URL:     {s.get('n_institutions_with_1b_urls')}"
            f" ({_pct_str(s.get('pct_institutions_with_1b_urls'))})"
        )
        w(f"  Total 1b URLs:      {s.get('total_1b_urls')}")
        if s.get("n_official_site_unparseable"):
            w(f"  Unparseable domain: {s['n_official_site_unparseable']}")
        if s.get("n_serper_failed"):
            w(f"  Serper failures:    {s['n_serper_failed']}")
        rl = _reasons_line(s.get("top_drop_reasons", []))
        if rl:
            w(rl)

    # ── Stage 1c — eligibility pre-filter (additive block, design memo 2026-07-06) ──
    fb = report.get("filter_eligibility", {})
    if fb.get("ran"):
        w(f"\n{_icon(fb.get('flag', '?'))}  Stage 1c — Eligibility filter [{fb.get('mode', '?')}]")
        w(
            f"  URLs in: {fb.get('n_urls_in')}   Pass: {fb.get('n_pass')}"
            f" ({_pct_str(fb.get('pct_pass'))})"
        )
        drop_label = "Would drop" if fb.get("mode") == "shadow" else "Dropped"
        w(f"  {drop_label}: {fb.get('n_would_drop')} ({_pct_str(fb.get('pct_would_drop'))})")
        dr = fb.get("drop_reasons", {})
        if dr:
            w("  Drop reasons: " + ", ".join(f"{k}={v}" for k, v in sorted(dr.items())))
        per_lang = fb.get("per_language", {})
        if per_lang:
            bar = fb.get("shadow_recall_bar")
            bar_str = f" (bar >= {bar:.0%})" if isinstance(bar, (int, float)) else ""
            w(
                "  Per language (pass% | shadow recall = LLM-kept URLs that also "
                f"pass{bar_str}; higher is better):"
            )
            for lang, m in per_lang.items():
                w(
                    f"    {lang}: pass {_pct_str(m.get('pct_pass'))}"
                    f" ({m.get('n_pass')}/{m.get('n_in')})"
                    f" | recall {_pct_str(m.get('shadow_recall'))}"
                    f" ({m.get('llm_keep_and_pass')}/{m.get('llm_keep')})"
                )
        w(f"  Rules version: {fb.get('rules_version')}")

    # ── Stage 3 ──
    s = stages.get("3_classify_triage", {})
    if s:
        w(f"\n{_icon(s.get('flag','?'))}  Stage 3 — URL triage")
        w(
            f"  Input:  {s.get('n_institutions_in')} institutions,"
            f" {s.get('n_total_candidate_urls')} URLs"
        )
        w(
            f"  Kept:   {s.get('n_urls_kept')} URLs"
            f" ({_pct_str(s.get('pct_urls_kept'))} of triaged)"
        )
        w(f"  Dropped:{s.get('n_urls_dropped'):>4} URLs")
        w(
            f"  Insts with ≥1 kept: {s.get('n_institutions_with_kept_url')}"
            f" ({_pct_str(s.get('pct_institutions_with_kept_url'))})"
        )
        if s.get("n_parse_failed"):
            w(f"  Parse failures:     {s['n_parse_failed']}")
        rl = _reasons_line(s.get("top_drop_reasons", []))
        if rl:
            w(rl)

    # ── Stage 4 ──
    s = stages.get("4_scrape", {})
    if s:
        w(f"\n{_icon(s.get('flag','?'))}  Stage 4 — Scrape")
        w(f"  Attempted:          {s.get('n_urls_attempted')} URLs (kept by triage)")
        w(
            f"  Scraped:            {s.get('n_pages_scraped')}"
            f" ({_pct_str(s.get('pct_scrape_success'))})"
        )
        w(f"  Robots disallowed:  {s.get('n_robots_disallowed')}")
        w(f"  Scrape errors:      {s.get('n_scrape_failed')}")
        w(f"  Insts with ≥1 page: {s.get('n_institutions_with_pages')}")
        rl = _reasons_line(s.get("top_drop_reasons", []))
        if rl:
            w(rl)

    # ── Stage 5 ──
    s = stages.get("5_extract", {})
    if s:
        w(f"\n{_icon(s.get('flag','?'))}  Stage 5 — Extract")
        w(f"  Pages in:           {s.get('n_pages_in')} scraped")
        w(
            f"  Empty-dropped:      {s.get('n_empty_dropped')}"
            f" ({_pct_str(s.get('pct_empty_dropped'))} of scraped)"
        )
        w(f"  Eligible for LLM:   {s.get('n_pages_eligible')}")
        w(f"  Truncated (cap):    {s.get('n_pages_truncated')}")
        w(
            f"  Extracts produced:  {s.get('n_extracts')}"
            f" ({_pct_str(s.get('pct_extracted_of_eligible'))} of eligible)"
        )
        if s.get("n_parse_failed"):
            w(f"  Parse failures:     {s['n_parse_failed']}")
        w(f"  Insts with ≥1 ext:  {s.get('n_institutions_with_extracts')}")
        rl = _reasons_line(s.get("top_drop_reasons", []))
        if rl:
            w(rl)

    # ── Stage 6 ──
    s = stages.get("6_validate", {})
    if s:
        w(f"\n{_icon(s.get('flag','?'))}  Stage 6 — Validate / Consolidate")
        w(f"  Input:              {s.get('n_institutions_in')} (with ≥1 extract)")
        w(
            f"  Consolidated:       {s.get('n_consolidated')}"
            f" ({_pct_str(s.get('pct_consolidated'))})"
        )
        if s.get("n_missing_validate_json"):
            w(f"  Missing validate:   {s['n_missing_validate_json']}")
        hga = s.get("has_genai_activity", {})
        total_hga = sum(hga.values())
        if total_hga:
            w("  has_genai_activity (of consolidated):")
            w(
                f"    yes     : {hga.get('yes', 0):>3}"
                f"  ({_pct_str(_safe_pct(hga.get('yes', 0), total_hga))})"
            )
            w(
                f"    no      : {hga.get('no', 0):>3}"
                f"  ({_pct_str(_safe_pct(hga.get('no', 0), total_hga))})"
            )
            w(
                f"    unclear : {hga.get('unclear', 0):>3}"
                f"  ({_pct_str(s.get('pct_unclear'))})"
            )
        rl = _reasons_line(s.get("top_drop_reasons", []))
        if rl:
            w(rl)
        sbl = s.get("sources_by_language") or {}
        if sbl:
            w("  Sources by (content) language:")
            for src_lang in sorted(sbl):
                counts = ", ".join(f"{k}={v}" for k, v in sorted(sbl[src_lang].items()))
                w(f"    {src_lang}: {counts}")

    # ── Language caveats ──
    caveats = report.get("language_caveats")
    if caveats:
        w("")
        w("─" * 70)
        w("Language-filter caveats")
        for c in caveats:
            w(f"  - {c}")

    # ── Attrition summary ──
    top = report.get("attrition_top_reasons", [])
    if top:
        w("")
        w("─" * 70)
        w("Top attrition reasons (all stages combined)")
        for item in top[:10]:
            w(
                f"  {item['stage']:<35}  {item['reason']:<30}  {item['count']:>4}"
            )

    # ── Thresholds note ──
    w("")
    w("─" * 70)
    w(report.get("thresholds_note", ""))

    return "\n".join(lines)


def _safe_pct(num: int, denom: int) -> float | None:
    return round(num / denom, 4) if denom else None


__all__ = ["render_text_report"]
