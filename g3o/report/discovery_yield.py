"""Discovery yield scoring — own-domain **relevant** hits.

The metric the 2026-08-01 findings settled on, implemented once here rather
than as a throwaway script, so a later run measures the same thing.

**Score on relevance, never on domain match alone.** Dropping quotes from the
production query lifts own-domain hits 5 -> 20 but leaves *relevant* hits at 5:
fifteen of those twenty are bare homepages with no AI content. A domain-match
metric would have reported that change as a 4x win.

Two rules make the count defensible:

- **Case-sensitive standalone ``AI``.** The findings session's first pass
  matched ``ai`` case-insensitively and inflated a headline by counting Italian
  ebook spam and the French verb "ai". Multi-word phrases stay
  case-insensitive; only the bare two-letter acronym is case-sensitive.
- **Own host, excluding mail/infrastructure subdomains.** ``autodiscover.``
  and ``webmail.`` hosts sit on the institution's registrable domain but are
  not the institution's site.

Read-only from disk; no network. Mirrors :mod:`g3o.report.health`'s convention.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import tldextract

from g3o.discovery.domain_pick import is_infra_host

# Offline extractor: the bundled public-suffix snapshot, never a network fetch,
# so a score is reproducible and does not depend on when it was run.
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())

# The bare acronym, case-sensitive, on word boundaries. ``AI-powered`` and
# ``(AI)`` count; ``ai`` (French "j'ai", Italian "ai"), ``Ai``, ``Thai`` and
# ``AIDS`` do not.
_ACRONYM_AI = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])")

# Unambiguous multi-word / distinctive GenAI signals. Case-insensitive: these
# are not two-letter tokens, so casing carries no disambiguating information.
_PHRASES = (
    "artificial intelligence",
    "generative ai",
    "genai",
    "gen ai",
    "chatgpt",
    "chat gpt",
    "large language model",
    "machine learning",
    "chatbot",
    "copilot",
    "intelligence artificielle",
    "inteligencia artificial",
    "inteligência artificial",
    "künstliche intelligenz",
    "intelligenza artificiale",
)

# Case-sensitive acronyms other than AI that are unambiguous in isolation.
_ACRONYMS = (re.compile(r"(?<![A-Za-z])LLM(?![A-Za-z])"),)


# URL and slug separators. ``/generative-ai-policy`` and ``/generative_ai``
# carry the same signal as the prose phrase and must match it; without this the
# metric silently under-counts every signal that only appears in a URL path.
_SEPARATORS = re.compile(r"[-_/+.,:;]+")


def has_genai_signal(*fields: str | None) -> bool:
    """True if any of ``fields`` (title, snippet, URL) carries a GenAI signal."""
    for field in fields:
        if not field:
            continue
        if _ACRONYM_AI.search(field):
            return True
        if any(rx.search(field) for rx in _ACRONYMS):
            return True
        low = _SEPARATORS.sub(" ", field.lower())
        if any(p in low for p in _PHRASES):
            return True
    return False


def registrable_domain(url_or_host: str) -> str:
    """eTLD+1 for a URL or bare host; ``""`` when it cannot be determined.

    Registrable rather than exact-host so ``www.``, ``data.`` and other
    legitimate subdomains of the institution's own domain still count as
    own-domain — while ``wipo.int`` does not become ``douanes.gov.mg``.
    """
    if not url_or_host:
        return ""
    candidate = url_or_host if "//" in url_or_host else "https://" + url_or_host
    host = urlparse(candidate).netloc.lower()
    if not host:
        return ""
    ext = _EXTRACT(host)
    return f"{ext.domain}.{ext.suffix}" if ext.domain and ext.suffix else ""


def is_own_domain(url: str, truth_domain: str) -> bool:
    """True if ``url`` sits on ``truth_domain`` and is not a mail/infra host."""
    if not truth_domain:
        return False
    host = urlparse(url if "//" in url else "https://" + url).netloc.lower()
    host = host.removeprefix("www.")
    if is_infra_host(host):
        return False
    return registrable_domain(url) == truth_domain


def score_institution(records: list[dict], truth_website: str) -> dict[str, Any]:
    """Score one institution's discovered URLs against its known website.

    Returns own-domain and own-domain-*relevant* counts. The gap between them
    is the whole point of the metric.
    """
    truth = registrable_domain(truth_website)
    own, relevant, relevant_urls = 0, 0, []
    seen: set[str] = set()
    for rec in records:
        url = rec.get("link") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        if not is_own_domain(url, truth):
            continue
        own += 1
        if has_genai_signal(rec.get("title"), rec.get("snippet"), url):
            relevant += 1
            relevant_urls.append(url)
    return {
        "truth_domain": truth,
        "n_urls": len(seen),
        "n_own_domain": own,
        "n_own_domain_relevant": relevant,
        "hit": relevant > 0,
        "relevant_urls": relevant_urls,
    }


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def score_run(run_dir: str | Path, truth: dict[str, str]) -> dict[str, Any]:
    """Score a whole presweep run.

    ``truth`` maps ``institution_id -> the master's website`` for that
    institution. Institutions absent from ``truth`` are skipped: the metric is
    only defined where ground truth exists.

    Pools Stage 1a + Stage 1b records, which is what the pipeline hands to
    Stage 3 — scoring them separately would credit neither leg for the chain's
    division of labour.
    """
    run_dir = Path(run_dir)
    per_inst: dict[str, Any] = {}
    n_queries = n_cached = 0
    for inst_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        inst_id = inst_dir.name
        if inst_id.startswith("_") or inst_id.startswith(".") or inst_id not in truth:
            continue
        a = _read(inst_dir / "1a_discovery_general.json")
        b = _read(inst_dir / "1b_discovery_site_restricted.json")
        for payload in (a, b):
            for q in payload.get("queries", []):
                n_queries += 1
                n_cached += 1 if q.get("from_cache") else 0
        row = score_institution(
            list(a.get("records", [])) + list(b.get("records", [])), truth[inst_id]
        )
        row["naive_domain"] = (a.get("naive_domain") or {}).get("domain")
        row["naive_domain_rank"] = (a.get("naive_domain") or {}).get("rank")
        stage2 = _read(inst_dir / "2_official_site.json")
        row["stage2_url"] = stage2.get("url")
        row["stage2_domain"] = registrable_domain(stage2.get("url") or "")
        row["n_urls_1a"] = len(a.get("records", []))
        row["n_urls_1b"] = len(b.get("records", []))
        row["mode"] = a.get("mode", "legacy")
        per_inst[inst_id] = row

    n = len(per_inst)
    hits = sum(1 for r in per_inst.values() if r["hit"])
    naive_ok = sum(
        1 for r in per_inst.values()
        if r["naive_domain"] and r["naive_domain"] == r["truth_domain"]
    )
    naive_attempted = sum(1 for r in per_inst.values() if r["naive_domain"])
    stage2_ok = sum(
        1 for r in per_inst.values()
        if r["stage2_domain"] and r["stage2_domain"] == r["truth_domain"]
    )
    stage2_attempted = sum(1 for r in per_inst.values() if r["stage2_domain"])
    return {
        "n_institutions": n,
        "n_queries_issued": n_queries,
        "n_queries_from_cache": n_cached,
        "queries_per_institution": round(n_queries / n, 3) if n else None,
        "n_with_relevant_hit": hits,
        "pct_with_relevant_hit": round(hits / n, 4) if n else None,
        "total_own_domain_urls": sum(r["n_own_domain"] for r in per_inst.values()),
        "total_own_domain_relevant_urls": sum(
            r["n_own_domain_relevant"] for r in per_inst.values()
        ),
        "total_urls": sum(r["n_urls"] for r in per_inst.values()),
        "mean_urls_per_institution": (
            round(sum(r["n_urls"] for r in per_inst.values()) / n, 2) if n else None
        ),
        "naive_domain_attempted": naive_attempted,
        "naive_domain_correct": naive_ok,
        "stage2_domain_attempted": stage2_attempted,
        "stage2_domain_correct": stage2_ok,
        "per_institution": per_inst,
    }


def mcnemar(a_hits: dict[str, bool], b_hits: dict[str, bool]) -> dict[str, Any]:
    """Exact two-sided McNemar over the institutions both arms scored.

    Paired: the same institution under two configurations. Reports the
    discordant pairs, which are the only ones the test uses.
    """
    from math import comb

    shared = sorted(set(a_hits) & set(b_hits))
    gains = sum(1 for i in shared if a_hits[i] and not b_hits[i])
    losses = sum(1 for i in shared if b_hits[i] and not a_hits[i])
    n = gains + losses
    if n == 0:
        p = 1.0
    else:
        k = min(gains, losses)
        tail = sum(comb(n, i) for i in range(0, k + 1)) / (2**n)
        p = min(1.0, 2 * tail)
    return {"n_paired": len(shared), "gains": gains, "losses": losses, "p_two_sided": p}
