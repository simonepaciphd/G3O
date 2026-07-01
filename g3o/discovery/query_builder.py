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

# Batch 5 (2026-07): proposed English term expansion, NOT active in
# GENAI_TERMS_BY_LANG. Adding search terms changes what the pipeline
# collects (working agreement, "Decision authority" -- escalate before
# coding), so this stays inert until Simone reviews and promotes it into
# GENAI_TERMS_BY_LANG["en"] in the GitHub issue first.
#
# Rationale: `g3o/extract/prompts/system_prompt.md` explicitly instructs the
# extractor to recognize Copilot, Gemini, Claude, LLaMA, CodeWhisperer, and
# "GenAI-powered chatbots" as in-scope GenAI evidence, and the output
# contract's own worked examples (Edge cases B and D) use "Microsoft 365
# Copilot" and a public chatbot as the flagship illustrations of what this
# pipeline is built to find. None of that vocabulary appears in the Stage 1a/1b
# *discovery* query terms below -- an institution whose only public coverage
# says "deployed Microsoft Copilot" or "launched an AI chatbot" (and never the
# literal phrases "generative AI", "ChatGPT", "AI policy", or "AI pilot") is
# never even discovered, so Stage 5/6 never gets a chance to classify it.
# This is a discovery-stage recall gap, not an extraction-stage one.
#
# Not yet validated against a live run (no SERPER_API_KEY/OPENAI_API_KEY were
# configured this session -- see Batch 5 deliverable writeup). Confirm with a
# live smoke run before promoting.
PROPOSED_GENAI_TERMS_EN: list[str] = [
    "generative AI",
    "ChatGPT",
    "AI policy",
    "AI pilot",
    "Copilot",
    "AI chatbot",
    "AI assistant",
    "large language model",
]


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
