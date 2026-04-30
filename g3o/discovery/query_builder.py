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
    "en": ["generative AI", "ChatGPT", "AI policy", "AI pilot"],
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
) -> list[tuple[str, str]]:
    """Build (query_string, language) tuples for a given institution.

    For each language in `languages`, emit one query per GenAI term known
    for that language. Languages without a known term roster fall back to
    English. `extra_terms` (if given) are appended as language-agnostic
    additions to every language.
    """
    queries: list[tuple[str, str]] = []
    extras = list(extra_terms or [])

    for lang in languages:
        terms = GENAI_TERMS_BY_LANG.get(lang) or GENAI_TERMS_BY_LANG["en"]
        for term in terms + extras:
            queries.append((f'"{institution_name}" "{term}"', lang))

    return queries
