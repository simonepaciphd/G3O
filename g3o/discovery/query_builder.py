"""Institution-driven query construction.

Given an institution and a list of languages, produce a list of
`(query_string, language)` tuples that the Serper client can execute.
The query-construction logic is deliberately simple in Push #1: a small
set of GenAI-term variants combined with the institution name, with
language-specific GenAI terms for the languages we currently support.
The full multilingual roster will land alongside the master institutions
universe.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

GENAI_TERMS_BY_LANG: dict[str, list[str]] = {
    # English roster expanded 2026-07-04 (PI sign-off): +Copilot, AI chatbot,
    # AI assistant, large language model — closes the discovery-recall gap vs
    # the extraction prompt's vocabulary (Copilot/chatbot deployments were
    # codeable but never searched for). Non-English rosters not yet expanded;
    # translate + promote per-language after the readiness-bar comparison.
    "en": [
        "generative AI",
        "ChatGPT",
        "AI policy",
        "AI pilot",
        "Copilot",
        "AI chatbot",
        "AI assistant",
        "large language model",
    ],
    "fr": ["IA générative", "ChatGPT", "politique IA", "pilote IA"],
    "es": ["IA generativa", "ChatGPT", "política de IA", "piloto de IA"],
    "de": ["generative KI", "ChatGPT", "KI-Richtlinie", "KI-Pilot"],
    "it": ["IA generativa", "ChatGPT", "politica IA", "progetto pilota IA"],
    "pt": ["IA generativa", "ChatGPT", "política de IA", "piloto de IA"],
    "ja": ["生成AI", "ChatGPT", "AIポリシー", "AIパイロット"],
    "zh": ["生成式AI", "ChatGPT", "AI政策", "AI试点"],
    "ar": ["الذكاء الاصطناعي التوليدي", "ChatGPT", "سياسة الذكاء الاصطناعي"],
    "fi": ["generatiivinen tekoäly", "ChatGPT", "tekoälyn periaatteet"],
}

def _phrase(value: str) -> str:
    """Quote `value` as a single Google exact-phrase slot — a binding match.

    Inner double quotes are dropped rather than escaped: Google has no
    in-phrase escape syntax, so an embedded `"` closes the phrase early and
    silently changes the query. 17 master rows carry one (the Argentine
    `Comisión Municipal "B"` entries).
    """
    return '"' + value.replace('"', "") + '"'

# A `-` at the start of a token is Google's exclusion operator, so bare
# `Kunkavav -Vadia` would actively suppress the very result we want (75 master
# rows, e.g. `Kunkavav -Vadia, Amreli, Gujarat — gram panchayat`). Mid-token
# hyphens (`Al-Anbar`) are inert and must survive, hence the `^|\s` anchor.
_TOKEN_INITIAL_MINUS = re.compile(r"(^|\s)-+(?=\S)")

def _hint(value: str) -> str:
    """Sanitize `value` for use as an UNQUOTED hint slot — non-binding.

    Unquoted slots bias ranking instead of constraining the result set, which
    is the point: a fourth mandatory phrase can empty a result set, a hint
    cannot. The cost is that characters inert inside quotes become live query
    syntax outside them, so anything operator-significant is neutralized here.
    Counts below are from a full scan of the 719,588-row master.

    - `"` (17 rows) — bare, an embedded quote *opens* a phrase, turning a hint
      into a stray binding match. Dropped.
    - `(` / `)` (35,179 disambiguation rows, 7 country rows — `Holy See
      (Vatican City State)`) — brackets removed, inner text kept, per the
      2026-07-30 decision to keep unit-type suffixes as hint tokens.
    - token-initial `-` (75 rows) — see `_TOKEN_INITIAL_MINUS`.
    - whitespace runs (173 rows, e.g. `Division No.  4, Manitoba`) collapsed,
      also mopping up any double space that bracket removal leaves behind.

    Em dashes, commas, and apostrophes carry no query meaning and pass through.
    """
    cleaned = value.replace('"', "").replace("(", "").replace(")", "")
    cleaned = _TOKEN_INITIAL_MINUS.sub(r"\1", cleaned)
    return " ".join(cleaned.split())

# ---------------------------------------------------------------------------
# Two-query discovery chain (2026-08-01). Additive: `build_queries` above is
# untouched and still serves the legacy Stage 1a/1b path.
#
# Findings (agent-workspace/2026-08-01-serper-discovery-yield-findings.md,
# n=24 with hand-adjudicated ground truth): the four-slot format asks one query
# to identify the institution *and* find GenAI evidence, and does neither well
# (6/24 relevant at 16 credits/inst). Splitting the jobs across two 1-credit
# legs scores 14/24 at 2 credits/inst; paired McNemar 9 gains / 1 loss, p=0.021.
#
# Two results from that work are load-bearing here and should not be
# re-litigated by tuning these functions:
#   - The **quoted institution name is the primary failure**. Master local names
#     are abbreviated (`Polson H S`, `KELLER ISD`) and quoting them exactly
#     matches almost nothing — three institutions returned zero URLs. Hence
#     `_hint`, not `_phrase`, in leg 1.
#   - Once site-bound, **extra English terms measure at exactly 0 pp** and
#     OR-chains are actively harmful (4/24 vs 16/24 for the bare token). Hence
#     leg 2 is one bare, unquoted token.
# ---------------------------------------------------------------------------

DOMAIN_QUERY_SUFFIX = "official website"

# Leg 2's default evidence token. Bare and unquoted by measurement, not by
# omission — see the module note above.
DEFAULT_EVIDENCE_TERM = "AI"


def build_domain_query(institution_name: str, country: str | None = None) -> str:
    """Leg 1 — identify the institution's own domain. One credit.

    ``<name> <country> official website``, every slot an unquoted hint. Found a
    usable domain for 21/24 institutions on the evaluation set (rank 1 for 18).

    The institution name is sanitized through :func:`_hint` for the same reason
    the qualifier slots are: outside quotes, a token-initial ``-`` is Google's
    exclusion operator and a stray ``"`` opens a phrase. Unquoted here is a
    measured choice — see the module note.
    """
    slots = [_hint(institution_name)]
    hint = _hint(country) if country else ""
    if hint:
        slots.append(hint)
    slots.append(DOMAIN_QUERY_SUFFIX)
    return " ".join(s for s in slots if s)


def build_evidence_query(site_domain: str, term: str = DEFAULT_EVIDENCE_TERM) -> str:
    """Leg 2 — find GenAI evidence on a known domain. One credit.

    ``site:<domain> AI``. Deliberately *not* wrapped around
    :func:`build_queries`: production Stage 1b wraps the whole four-slot query
    in ``site:``, repeating the institution name inside a query already bound
    to that institution's domain, and **93.2% of those queries (179/192) return
    zero results.**

    ``term`` stays a parameter so the multilingual subproject can pass a
    native-language token without touching this module; it is not a knob for
    adding English terms, which measure at 0 pp.
    """
    return f"site:{site_domain} {term}".strip()


def build_queries(
    institution_name: str,
    languages: Iterable[str],
    extra_terms: Iterable[str] | None = None,
    country: str | None = None,
    disambiguation: str | None = None,
) -> list[tuple[str, str]]:
    """Build (query_string, language) tuples for a given institution.

    For each language in `languages`, emit one query per GenAI term known
    for that language. Languages without a known term roster fall back to
    English. `extra_terms` (if given) are appended as language-agnostic
    additions to every language.

    Only two slots are binding: the institution name and the GenAI term stay
    quoted exact phrases. The two qualifier slots are **unquoted hints** —
    they bias ranking without constraining the result set:

        "Ain Beida" Algeria Oum El Bouaghi — commune "generative AI"

    `country` (if given and non-empty) disambiguates institutions whose name
    is shared by a more prominent entity elsewhere — "House of
    Representatives" unqualified is dominated by US Congress results.

    `disambiguation` (if given and non-empty) is the master's parent-geography
    annotation for rows flagged `duplicate=1`, produced by the same-name
    resolution work under ticket_0006 ("disambiguate genuinely-distinct
    same-name entries"). It separates units `country` alone cannot: same-named
    units recur both within a country and across countries (three distinct
    "Oran" local bodies sit in India and Uganda).

    Hint rather than phrase, decided 2026-07-30, reversing the quoted country
    slot shipped in 6878d1a. Master disambiguation values are compound
    (`"Prantij, Sabar Kantha, Gujarat — gram panchayat"`); as a mandatory
    fourth phrase such a value matches almost no document and would suppress
    recall on the 216,640 rows that carry one, so the qualifiers inform
    ranking instead. Values are otherwise passed through whole — no component
    is extracted, since choosing one would change what discovery collects and
    is a reviewed decision rather than something this function assumes. See
    `_hint` for the sanitizing that unquoting makes necessary.

    Slot order is name → country → disambiguation → term. Any absent slot is
    skipped, so an institution with neither qualifier reproduces the original
    two-phrase query exactly.
    """
    queries: list[tuple[str, str]] = []
    extras = list(extra_terms or [])

    for lang in languages:
        terms = GENAI_TERMS_BY_LANG.get(lang) or GENAI_TERMS_BY_LANG["en"]
        for term in terms + extras:
            slots = [_phrase(institution_name)]
            for qualifier in (country, disambiguation):
                # Sanitize before the emptiness check: a value that reduces to
                # nothing (say "()") must not leave a blank slot in the join.
                hint = _hint(qualifier) if qualifier else ""
                if hint:
                    slots.append(hint)
            slots.append(_phrase(term))
            queries.append((" ".join(slots), lang))

    return queries
