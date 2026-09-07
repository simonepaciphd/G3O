"""Stage 1c — deterministic eligibility screens (pure, no I/O).

Two independent parts, per the signed design memo
``docs/eligibility-filter-design.md`` (PI sign-off 2026-07-06):

**1a. URL-pattern screen (negative rules).** Drop URLs that are structurally
non-content, decided from the URL string alone. Language-neutral. Two rosters:

  *Path/file-type patterns* (PI decision 4): login/auth paths, search-results
  paths, calendar/feed files, sitemaps, and ``robots.txt``.

  *Host patterns* (PI ruling 2026-08-01, amending decision 4; closes issue #8):
  a deliberately short list covering URL shorteners and social-media profile
  pages — the two categories the memo's 1a text names that cannot be recognized
  from the path alone. Scope is those two categories and only those; expansion
  is a signed amendment, not a drive-by commit. See :func:`host_rule_hits`.

**1b. Snippet/title keyword screen — RETIRED from the pipeline 2026-08-02
(PI decision).** :func:`has_genai_signal` is retained and still tested, but
:func:`evaluate` no longer calls it, so Stage 1c is now a URL-hygiene screen
only. It required ≥1 GenAI/AI-signal term in ``title ∪ snippet``, with the
vocabulary described below.

*Why it was retired.* Measured on run ``20260802-e2e-100`` (n=100, shadow mode),
the screen dropped 1,527 of 1,648 discovered URLs, and of the 831 URLs Stage 3's
LLM triage judged worth reading only **32 also passed — 3.9%, against PI
decision 6's ≥70% bar.** Enforcing it would have discarded ~96% of the funnel.

The cause is that a SERP snippet is not a statement about the page's topic. Leg
1 asks ``<name> <country> official website``, so its snippets describe the
institution, never AI — every one of an institution's homepages failed. That
much was expected. What was not: **leg 2 fails almost as badly.** Although it
asks ``site:<domain> AI``, Google returns the page's generic meta description
rather than an AI-matching excerpt, so 762 of ~802 leg-2 URLs were also dropped
and *every* one of the 36 survivors was a leg-2 URL. Restricting the screen to
leg 2 was therefore measured and rejected; so was exempting homepages, which
lifts recall only to 13.8%. Removing it takes 1c to 94.8% pass / **99.5% shadow
recall**.

The consequence to keep in view: 1c no longer reduces Stage 3 volume
meaningfully (5.2%, not 97.8%), so it is a correctness/hygiene stage rather than
a cost-saving one. Deciding what GenAI signal is worth screening on — page text
rather than snippets, or a better-calibrated lexicon — is open, and the
vocabulary machinery below is deliberately left intact for it. Retuning that
vocabulary belongs to ``subprojects/multilingual-pipeline/``.

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
RULES_VERSION = "1c-url-hygiene-2026-08-02"

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
    # Login / auth endpoints.
    #
    # Narrowed 2026-08-01 (PI ruling on rebase review, defect 8). The original
    # list carried three terms that name core G3O evidence surfaces rather than
    # site plumbing, and fired on real URLs:
    #   ``register``  — national AI / algorithm registers (``/register/ai-systems``).
    #                   Amsterdam's algoritmeregister is exactly this shape.
    #   ``session``   — parliamentary and council sessions (``/session/2026/ai-debate``),
    #                   where legislative GenAI activity is recorded.
    #   ``auth``      — a common abbreviation for "authority" (``/auth/ai-strategy``).
    # All three are dropped from the roster. ``signup``/``sign-up`` stay: they
    # name an action, not a document. ``registration`` is NOT added back — the
    # same collision applies. This narrows the rule's reach; it does not change
    # the rule *category* (login/auth endpoints) the PI signed.
    (
        "login_auth",
        re.compile(
            r"(?:^|/)(?:login|log-in|signin|sign-in|signup|sign-up|"
            r"logout|log-out|oauth|sso)" + _SEG_END
            + r"|wp-login\.php$"
        ),
    ),
    # On-site search-results endpoints (path form).
    #
    # Narrowed 2026-08-01: ``find`` dropped. It reads as a content-navigation
    # prefix at least as often as a search endpoint (``/find/ai-services``), and
    # unlike ``search`` it carries no convention of being a results page.
    ("search_results", re.compile(r"(?:^|/)(?:search|search-results)" + _SEG_END)),
]

# Query-string keys whose presence marks a search-results page.
#
# Narrowed 2026-08-01: ``q`` and ``s`` removed. Both are too generic to read as
# a search marker on their own —
#   ``?q=``  is legacy Drupal's *content* path parameter (``index.php?q=node/4211``),
#            so on an affected government site this rule dropped every page.
#   ``?s=``  is used for sort/section/session params as often as for search.
# ``search``/``query`` are explicit enough to keep. A search-results page whose
# only marker is ``?q=`` is now a false negative, which is the direction PI
# decision 4 asks us to err in.
_SEARCH_QUERY_KEYS = ("query", "search")


# ---------------------------------------------------------------------------
# 1a (host rules) — narrow, PI-authorized exception to "no domain blocklists"
# ---------------------------------------------------------------------------
#
# PI ruling 2026-08-01 AMENDS decision 4 (2026-07-06, "path/file-type patterns
# only — no domain-level blocklists"). Issue #8 established that the two
# categories the memo's own 1a text names — URL shorteners and social-media
# profile pages — cannot be recognized from the path alone. The PI authorized a
# deliberately short host list covering those two categories and only those, to
# be expanded later as shadow data shows what else is worth adding.
#
# This is a collection decision, not an engineering parameter: a list of hosts
# the observatory declines to look at shapes what it can ever see. Two
# consequences, both load-bearing:
#   1. The lists below are DRAFT and require PI sign-off before ``enforce``
#      gates a live run (memo decision 3). ``shadow`` is unaffected.
#   2. Additions belong in a signed amendment, not a drive-by commit.
#
# Matching is on the registrable host, suffix-anchored so ``t.co`` matches
# ``t.co`` and ``www.t.co`` but never ``not.co`` or ``example.com/t.co``.

# URL shorteners: the target is opaque, so the snippet/title screen has nothing
# to work with and the fetched page is a redirect stub.
_SHORTENER_HOSTS: frozenset[str] = frozenset({
    "bit.ly", "buff.ly", "cutt.ly", "dlvr.it", "goo.gl", "is.gd", "lnkd.in",
    "ow.ly", "rebrand.ly", "shorturl.at", "t.co", "tinyurl.com", "trib.al",
})

# Social-media hosts. NOTE the asymmetry: a *profile* page is boilerplate, but a
# *post* can be the only public record of an announcement. Only the bare-profile
# shape is dropped; anything deeper — where posts, threads and status URLs live
# — passes. Erring toward keeping.
#
# On most of these a profile is host + at most one segment (``twitter.com/dept``)
# while a post is deeper (``twitter.com/dept/status/123``), so a segment count
# separates them. LinkedIn is the exception: its profiles are always two
# segments under a fixed prefix, so it gets an explicit shape.
_SOCIAL_HOSTS: frozenset[str] = frozenset({
    "facebook.com", "instagram.com", "linkedin.com", "t.me", "threads.net",
    "tiktok.com", "twitter.com", "vk.com", "weibo.com", "x.com",
})

# ``youtube.com`` is deliberately ABSENT. Its profile and content URLs are the
# same shape (``/@ministry`` vs ``/watch?v=…`` are both one segment), so no
# segment rule separates them — and a video can be the only public record of an
# announcement. Dropping a channel page is not worth the risk of dropping the
# announcement, so YouTube is left entirely to the 1b keyword screen.

# Hosts whose profile URLs are two segments under a fixed first segment.
_SOCIAL_PROFILE_PREFIXES: dict[str, frozenset[str]] = {
    "linkedin.com": frozenset({"company", "in", "school", "showcase"}),
}


def _registrable_host(netloc: str) -> str:
    """Lowercased host with any port and a leading ``www.`` stripped."""
    host = netloc.lower().partition(":")[0]
    return host[4:] if host.startswith("www.") else host


def _host_matches(host: str, roster: frozenset[str]) -> bool:
    """True if ``host`` is a roster entry or a subdomain of one."""
    return any(host == h or host.endswith("." + h) for h in roster)


def _is_bare_social_profile(host: str, segments: list[str]) -> bool:
    """True if this path is a bare profile page rather than a post.

    A post/status/video URL may itself be the announcement, so anything that is
    not unambiguously a profile passes.
    """
    for prefix_host, prefixes in _SOCIAL_PROFILE_PREFIXES.items():
        if host == prefix_host or host.endswith("." + prefix_host):
            return len(segments) == 2 and segments[0] in prefixes
    return len(segments) <= 1


def host_rule_hits(url: str) -> list[str]:
    """Return the sorted 1a *host* rule names a URL trips (empty ⇒ passes).

    Separate from :func:`url_pattern_hits` so the path screen stays a pure
    path/file-type function and the PI-authorized host exception is auditable on
    its own — the artifact's ``matched_rules`` names which of the two fired.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return []
    host = _registrable_host(parsed.netloc or "")
    if not host:
        return []

    hits: set[str] = set()
    if _host_matches(host, _SHORTENER_HOSTS):
        hits.add("url_shortener")
    if _host_matches(host, _SOCIAL_HOSTS):
        segments = [s for s in (parsed.path or "").split("/") if s]
        if _is_bare_social_profile(host, segments):
            hits.add("social_media_profile")
    return sorted(hits)


def url_pattern_hits(url: str) -> list[str]:
    """Return the sorted list of 1a rule names a URL trips (empty ⇒ passes 1a).

    Path/file-type rules plus the PI-authorized host rules (see
    :func:`host_rule_hits`). Unparseable URLs pass (fail-open): the screen never
    manufactures a drop from a string it cannot interpret.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return []
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()

    hits: set[str] = set(host_rule_hits(url))
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

    ``decision`` is ``"pass"`` or ``"drop"``. Only the URL-pattern screen
    applies: ``matched_rules`` names the fired rules, or is ``[]`` for a pass,
    and ``reason`` is the coarse attrition code (``None`` for a pass).

    The snippet/title GenAI screen is **not** applied — retired 2026-08-02 by PI
    decision after it measured 3.9% shadow recall against a ≥70% bar (module
    docstring for the numbers and the two rejected alternatives).
    :data:`REASON_NO_SIGNAL` is kept so existing artifacts and the health
    report's reason tallies stay readable, and :func:`has_genai_signal` is kept
    for whatever replaces it; neither is reachable from here.
    """
    url = record.get("link", "") or ""
    pattern_rules = url_pattern_hits(url)
    if pattern_rules:
        return {
            "decision": "drop",
            "matched_rules": pattern_rules,
            "reason": REASON_URL_PATTERN,
        }
    return {"decision": "pass", "matched_rules": [], "reason": None}


__all__ = [
    "RULES_VERSION",
    "REASON_URL_PATTERN",
    "REASON_NO_SIGNAL",
    "host_rule_hits",
    "url_pattern_hits",
    "has_genai_signal",
    "evaluate",
]
