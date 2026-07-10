"""Stage 1c — deterministic eligibility screens (pure, no I/O).

Two independent parts, per the signed design memo
``docs/eligibility-filter-design.md`` (PI sign-off 2026-07-06):

**1a. URL-pattern screen (negative rules).** Drop URLs that are structurally
non-content, decided from the URL string alone. Language-neutral. Scope is
**path/file-type patterns only** (PI decision 4: no domain-level blocklists):
login/auth paths, search-results paths, calendar/feed files, sitemaps, and
``robots.txt``.

  URL shorteners and social-media *profile* pages — both named in the memo's
  1a text — inherently require host recognition, which is in tension with
  decision 4 ("no domain blocklists"). They are **deliberately out of scope
  here** pending PI sign-off (escalated as GitHub issue #8). Do not add
  host-based rules to this module until that decision lands.

**1b. Snippet/title keyword screen (positive eligibility).** Require ≥1
GenAI/AI-signal term in ``title ∪ snippet``. Vocabulary is the union of every
language roster in ``GENAI_TERMS_BY_LANG`` plus the tool/model names in
``qc.GENERATIVE_SIGNAL_KEYWORDS`` — a French snippet found by an English query
still passes on French terms. **Fail-open:** if both title and snippet are
empty/missing, the record passes (we never drop for absence of text we do not
have).

Per fact 5 of the memo, ``qc._compile_keyword_pattern`` asserts ``\\w``
boundaries, which are wrong for continuous CJK script (kanji/hanzi are word
characters, so "生成AI" inside a Japanese sentence would fail to match). So the
``ja``/``zh`` roster terms are matched as **bare substrings**; every other
(space-delimited) script reuses the boundary-aware helper.

Everything here is a pure function of its inputs — no filesystem, no network,
no clock — so the Stage 1c artifact is byte-reproducible across runs.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from g3o.discovery.query_builder import GENAI_TERMS_BY_LANG
from g3o.validate.qc import GENERATIVE_SIGNAL_KEYWORDS, _compile_keyword_pattern

# Bumped whenever the rule set or vocabulary below changes; recorded verbatim
# into every 1c artifact so a decision can always be traced to the rules that
# produced it. NOT yet PI-signed — the memo (decision 3) requires PI sign-off
# on the lists before ``enforce`` gates any live run; ``shadow`` is unaffected.
RULES_VERSION = "1c-draft-2026-07-09"

# Coarse attrition reason codes (stable; participate in the attrition dedup
# key). The per-URL ``matched_rules`` in the artifact carry the fine detail.
REASON_URL_PATTERN = "url_pattern_noncontent"
REASON_NO_SIGNAL = "no_genai_signal"


# ---------------------------------------------------------------------------
# 1a — URL-pattern screen (path/file-type only; no host recognition)
# ---------------------------------------------------------------------------

# A path segment ends at a ``/``, at end-of-path, or at a server-page file
# extension (``login.aspx``, ``search.php``, ``sitemap.html``). Matching the
# extension closes the blind spot where segment-only rules missed endpoints
# rendered by a scripting engine (2026-07-09 review). ``parsed.path`` never
# carries the query string, so the extension always sits at end-of-path.
_SEG_END = r"(?:/|$|\.(?:php|aspx|html?|jsp)(?:/|$))"

# Each entry is (rule_name, compiled_pattern) tested against the lowercased URL
# path (and, for a couple, the query string). Patterns are intentionally narrow
# — the memo's stated posture is low-fire-rate / high-signal: accept false
# negatives, keep false positives near zero.
_PATH_RULES: list[tuple[str, re.Pattern[str]]] = [
    # robots.txt — exact file at any depth.
    ("robots_txt", re.compile(r"(?:^|/)robots\.txt$")),
    # Sitemaps: sitemap.xml / sitemap_index.xml / sitemap-1.xml, plus HTML/
    # script-rendered sitemap pages (sitemap.html, sitemap.php, …).
    ("sitemap", re.compile(r"(?:^|/)sitemap[a-z0-9._-]*\.(?:xml|php|aspx|html?|jsp)$")),
    # Calendar / syndication feed files and endpoints.
    ("calendar_feed", re.compile(r"\.(?:ics|rss|atom)$|(?:^|/)(?:feed|rss|atom)/?$")),
    # Login / auth / session / registration endpoints.
    (
        "login_auth",
        re.compile(
            r"(?:^|/)(?:login|log-in|signin|sign-in|signup|sign-up|register|"
            r"logout|log-out|auth|oauth|sso|session)" + _SEG_END
            + r"|wp-login\.php$"
        ),
    ),
    # On-site search-results endpoints (path form).
    ("search_results", re.compile(r"(?:^|/)(?:search|search-results|find)" + _SEG_END)),
]

# Query-string keys whose presence marks a search-results page.
_SEARCH_QUERY_KEYS = ("q", "query", "search", "s")


def url_pattern_hits(url: str) -> list[str]:
    """Return the sorted list of 1a rule names a URL trips (empty ⇒ passes 1a).

    Path/file-type rules only. Unparseable URLs pass (fail-open): the screen
    never manufactures a drop from a string it cannot interpret.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return []
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()

    hits: set[str] = set()
    for name, pattern in _PATH_RULES:
        if pattern.search(path):
            hits.add(name)

    # Query-string search detection (path form is covered by the rule above).
    if "search_results" not in hits and query:
        for key in _SEARCH_QUERY_KEYS:
            if re.search(rf"(?:^|&){re.escape(key)}=", query):
                hits.add("search_results")
                break

    return sorted(hits)


# ---------------------------------------------------------------------------
# 1b — snippet/title keyword screen (per-script boundary handling)
# ---------------------------------------------------------------------------

# ``ja``/``zh`` roster terms match as bare substrings (CJK is continuous script;
# \w boundaries are wrong here — memo fact 5). Everything else — the remaining
# language rosters plus the qc generative-signal tool/model names — reuses the
# boundary-aware helper. All lowercased so matching is case-insensitive.
_CJK_TERMS: frozenset[str] = frozenset(
    t.lower() for t in GENAI_TERMS_BY_LANG["ja"] + GENAI_TERMS_BY_LANG["zh"]
)
_BOUNDARY_TERMS: frozenset[str] = frozenset(
    t.lower()
    for lang, terms in GENAI_TERMS_BY_LANG.items()
    if lang not in ("ja", "zh")
    for t in terms
) | frozenset(k.lower() for k in GENERATIVE_SIGNAL_KEYWORDS)

_BOUNDARY_PATTERN = _compile_keyword_pattern(_BOUNDARY_TERMS)

# The qc-derived ``gpt`` term is boundary-matched, so "GPT-4" passes (the hyphen
# is a non-word edge) but "GPT4"/"GPT4o" do not (the digit is a word char). This
# supplemental pattern catches the no-separator model versions (2026-07-09
# review). Not a new vocabulary term — a robustness fix for the existing ``gpt``.
_GPT_VERSION_PATTERN = re.compile(r"(?<!\w)gpt-?\d")


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace (same shape as ``qc._normalize``)."""
    return re.sub(r"\s+", " ", text.lower())


def has_genai_signal(title: str | None, snippet: str | None) -> bool:
    """True iff ``title ∪ snippet`` carries ≥1 GenAI/AI-signal term.

    **Fail-open:** when both fields are empty/missing there is no text to
    screen, so the record passes (returns True). This is the memo's explicit
    1b rule — 1b removes results whose snippet shows *no* AI signal, never
    results whose snippet we simply do not have.
    """
    text = _normalize(f"{title or ''} {snippet or ''}").strip()
    if not text:
        return True  # fail-open: no text ⇒ do not drop
    if _BOUNDARY_PATTERN.search(text) or _GPT_VERSION_PATTERN.search(text):
        return True
    return any(term in text for term in _CJK_TERMS)


# ---------------------------------------------------------------------------
# Combined per-record decision
# ---------------------------------------------------------------------------


def evaluate(record: dict) -> dict:
    """Screen one discovery record → ``{decision, matched_rules, reason}``.

    ``decision`` is ``"pass"`` or ``"drop"``. 1a runs first (URL string alone);
    only URLs that survive 1a are keyword-screened. ``matched_rules`` names the
    fired 1a rules, or ``["no_genai_signal"]`` for a 1b drop, or ``[]`` for a
    pass. ``reason`` is the coarse attrition code (``None`` for a pass).
    """
    url = record.get("link", "") or ""
    pattern_rules = url_pattern_hits(url)
    if pattern_rules:
        return {
            "decision": "drop",
            "matched_rules": pattern_rules,
            "reason": REASON_URL_PATTERN,
        }
    if not has_genai_signal(record.get("title"), record.get("snippet")):
        return {
            "decision": "drop",
            "matched_rules": [REASON_NO_SIGNAL],
            "reason": REASON_NO_SIGNAL,
        }
    return {"decision": "pass", "matched_rules": [], "reason": None}


__all__ = [
    "RULES_VERSION",
    "REASON_URL_PATTERN",
    "REASON_NO_SIGNAL",
    "url_pattern_hits",
    "has_genai_signal",
    "evaluate",
]
