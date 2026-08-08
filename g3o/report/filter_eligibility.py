"""Stage 1c health-report block (additive; disk-only, no network).

Kept in its own module so ``g3o.report.health`` — where RA ticket_0010 is also
working — takes only a one-line additive call site and stays rebase-friendly.

Reads the per-institution ``1c_filter_eligibility.json`` artifacts (plus the
1a/1b ``language`` tags and the Stage-3 ``3_triage.json`` decisions) and reports:

  * URLs in / passed / would-drop, overall and per language;
  * top drop reasons (url_pattern_noncontent vs no_genai_signal);
  * **shadow recall** per language — ``pass ∩ llm_keep / llm_keep``, the share
    of LLM-kept URLs that also survive the filter. This is stated in the same
    direction as PI decision 6's bar ("≥70% of LLM-kept URLs must also pass the
    filter"), so the reported number is compared against the bar directly.
    ``llm_keep_and_would_drop`` carries the complementary disagreement count.

    Direction note (PI ruling 2026-08-01): the memo's §Mechanics originally
    defined the metric as ``would_drop ∩ llm_keep / llm_keep`` — the complement
    — while decision 6 stated the bar on the pass-through share. Reporting the
    complement under the name "recall" meant a value of 0.75 (75% of LLM-kept
    URLs *discarded*, a severe failure) read as clearing a ≥70% bar. The metric
    is now reported in decision 6's direction and the memo is amended to match.

    Caveat (memo fact 1b): this measures *agreement* with a URL-only LLM judge,
    not filter correctness. It is only meaningful in ``shadow`` mode, where
    Stage 3 still sees the would-drop URLs; under ``enforce`` those URLs never
    reach Stage 3, so every surviving URL is trivially in the intersection and
    the number is 1.0 by construction.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.common.paths import (
    institution_dir,
    iter_institution_dirs,
    require_layout,
)

# Would-drop-rate thresholds (PI-tunable). The 1c block is informational in
# shadow mode, so these never escalate to "fail" and never feed the run's
# overall flag — they only surface an unusually aggressive draft rule set.
FILTER_WOULD_DROP_WARN_PCT = 0.60

# PI decision 6 (provisional): >=70% of LLM-kept URLs must also pass the filter,
# per language, before ``enforce`` is considered. Reported alongside the metric
# for comparison; deliberately NOT wired into ``flag`` — decision 6 says the bar
# is reviewed manually against actual disagreements, not auto-enforced.
SHADOW_RECALL_BAR = 0.70


def _iter_inst_dirs(run_dir: Path) -> list[Path]:
    manifest = run_dir / "manifest.json"
    if manifest.exists():
        ids = json.loads(manifest.read_text(encoding="utf-8")).get("institutions", [])
        if ids:
            return [institution_dir(run_dir, i) for i in ids]
    return list(iter_institution_dirs(run_dir))


def _url_languages(inst_dir: Path) -> dict[str, set[str]]:
    """Map each discovered URL to the set of languages that surfaced it (1a∪1b)."""
    out: dict[str, set[str]] = {}
    for fname in ("1a_discovery_general.json", "1b_discovery_site_restricted.json"):
        p = inst_dir / fname
        if not p.exists():
            continue
        for r in json.loads(p.read_text(encoding="utf-8")).get("records", []):
            url, lang = r.get("link"), r.get("language")
            if url and lang:
                out.setdefault(url, set()).add(lang)
    return out


def _llm_kept_urls(inst_dir: Path) -> set[str]:
    p = inst_dir / "3_triage.json"
    if not p.exists():
        return set()
    decisions = json.loads(p.read_text(encoding="utf-8")).get("decisions", [])
    return {d["url"] for d in decisions if d.get("decision") == "keep"}


def _pct(num: int, denom: int) -> float | None:
    return round(num / denom, 4) if denom else None


def compute_filter_block(
    run_dir: str | Path, language: str | None = None
) -> dict[str, Any]:
    """Compute the Stage 1c report block for a run directory.

    ``language``, when given, restricts the top-level counts to URLs surfaced by
    a query tagged with that language; the ``per_language`` map is always built
    across every language present (so one unrestricted call yields the full
    cross-language comparison).
    """
    run_dir = Path(run_dir)
    require_layout(run_dir)

    mode: str | None = None
    rules_version: str | None = None
    ran = False

    # url -> (decision, reason_bucket, langs, llm_kept)
    n_in = n_pass = n_drop = 0
    reasons: dict[str, int] = {}
    per_language: dict[str, dict[str, Any]] = {}

    for inst_dir in _iter_inst_dirs(run_dir):
        p = inst_dir / "1c_filter_eligibility.json"
        if not p.exists():
            continue
        ran = True
        payload = json.loads(p.read_text(encoding="utf-8"))
        mode = payload.get("mode", mode)
        rules_version = payload.get("rules_version", rules_version)
        url_langs = _url_languages(inst_dir)
        llm_kept = _llm_kept_urls(inst_dir)

        for d in payload.get("decisions", []):
            url = d.get("url", "")
            langs = url_langs.get(url, set())
            is_drop = d.get("decision") == "drop"
            reason = (
                "no_genai_signal"
                if d.get("matched_rules") == ["no_genai_signal"]
                else "url_pattern_noncontent"
            )

            # Per-language accumulation (always, across every language).
            for lang in langs:
                b = per_language.setdefault(
                    lang,
                    {
                        "n_in": 0,
                        "n_pass": 0,
                        "n_would_drop": 0,
                        "_llm_keep": 0,
                        "_would_drop_and_llm_keep": 0,
                    },
                )
                b["n_in"] += 1
                if is_drop:
                    b["n_would_drop"] += 1
                else:
                    b["n_pass"] += 1
                if url in llm_kept:
                    b["_llm_keep"] += 1
                    if is_drop:
                        b["_would_drop_and_llm_keep"] += 1

            # Top-level accumulation (honor the language filter if set).
            if language is not None and language not in langs:
                continue
            n_in += 1
            if is_drop:
                n_drop += 1
                reasons[reason] = reasons.get(reason, 0) + 1
            else:
                n_pass += 1

    if not ran:
        return {"ran": False, "flag": "not_run"}

    # Finalize per-language shadow recall.
    per_lang_out: dict[str, Any] = {}
    for lang, b in sorted(per_language.items()):
        per_lang_out[lang] = {
            "n_in": b["n_in"],
            "n_pass": b["n_pass"],
            "n_would_drop": b["n_would_drop"],
            "pct_pass": _pct(b["n_pass"], b["n_in"]),
            "llm_keep": b["_llm_keep"],
            "llm_keep_and_pass": b["_llm_keep"] - b["_would_drop_and_llm_keep"],
            "llm_keep_and_would_drop": b["_would_drop_and_llm_keep"],
            # pass ∩ llm_keep / llm_keep — stated in decision 6's direction, so
            # it is compared against SHADOW_RECALL_BAR directly (higher = better).
            "shadow_recall": _pct(
                b["_llm_keep"] - b["_would_drop_and_llm_keep"], b["_llm_keep"]
            ),
        }

    pct_would_drop = _pct(n_drop, n_in)
    flag = "green"
    if mode != "off" and pct_would_drop is not None and pct_would_drop >= FILTER_WOULD_DROP_WARN_PCT:
        flag = "warn"

    return {
        "ran": True,
        "mode": mode,
        "rules_version": rules_version,
        "n_urls_in": n_in,
        "n_pass": n_pass,
        "n_would_drop": n_drop,
        "pct_pass": _pct(n_pass, n_in),
        "pct_would_drop": pct_would_drop,
        "drop_reasons": reasons,
        "per_language": per_lang_out,
        "flag": flag,
        "shadow_recall_bar": SHADOW_RECALL_BAR,
        "note": (
            "shadow_recall is the share of LLM-kept URLs that ALSO pass the "
            f"filter (higher is better; PI decision 6 bar >= {SHADOW_RECALL_BAR:.0%} "
            "per language). It measures agreement with a URL-only LLM judge, not "
            "filter correctness (memo fact 1b) — review a sample of "
            "disagreements before treating them as filter errors. In shadow mode "
            "nothing is dropped."
        ),
    }


__all__ = [
    "compute_filter_block",
    "FILTER_WOULD_DROP_WARN_PCT",
    "SHADOW_RECALL_BAR",
]
