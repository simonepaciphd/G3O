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

def build_queries(
    institution_name: str,
    languages: Iterable[str],
    extra_terms: Iterable[str] | None = None,
    country: str | None = None,
) -> list[tuple[str, str]]:
    """Build (query_string, language) tuples for a given institution.

    For each language in `languages`, emit one query per GenAI term known
    for that language. Languages without a known term roster fall back to
    English. `extra_terms` (if given) are appended as language-agnostic
    additions to every language.

    `country` (if given and non-empty) is inserted as its own quoted phrase
    between the institution name and the GenAI term, disambiguating
    institutions whose name is shared by a more prominent entity elsewhere
    (e.g. "House of Representatives" without a country qualifier is
    dominated by US Congress results). Falls back to the unqualified
    two-term query when no country is known.
    """
    queries: list[tuple[str, str]] = []
    extras = list(extra_terms or [])

    for lang in languages:
        terms = GENAI_TERMS_BY_LANG.get(lang) or GENAI_TERMS_BY_LANG["en"]
        for term in terms + extras:
            if country:
                queries.append((f'"{institution_name}" "{country}" "{term}"', lang))
            else:
                queries.append((f'"{institution_name}" "{term}"', lang))

    return queries
