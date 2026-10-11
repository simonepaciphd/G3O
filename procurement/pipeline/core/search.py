"""GenAI query-set loading, text normalization, and local filtering.

Two search strategies (see docs/architecture.md 5a):
  - query pushdown: the adapter passes terms to the source's own search.
  - local filter:   for bulk/full-dump sources, filter records here.

This module owns loading the query set, the shared normalizer, and the
high-recall local filter. The authoritative relevance decision belongs to
core/classify.py — a filter hit is a candidate, not a verdict (codebook §4).
"""

from __future__ import annotations

import re
import unicodedata

import yaml

from .models import GenAIQuerySet


def load_queries(path: str) -> GenAIQuerySet:
    """Load a query-set YAML into a GenAIQuerySet.

    NOTE: config/genai_queries.yaml is a PI-signed placeholder and
    config/genai_queries.DRAFT-v0.1.yaml is a parked RA draft that does not
    supersede it. Loading a file does not approve its terms; every record
    carries the set's `version` so a later reprocess is explicit.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    queries = GenAIQuerySet(
        version=str(data.get("version", "unknown")),
        terms=data.get("terms", {}) or {},
        regex=data.get("regex", []) or [],
        codes=data.get("codes", {}) or {},
        exclude_terms=data.get("exclude_terms", []) or [],
        context_required_terms=data.get("context_required_terms", []) or [],
    )
    for pattern in queries.regex:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid regex in {path}: {pattern!r}: {exc}") from exc
    return queries


def normalize(text: str) -> str:
    """Casefold, fold diacritics, and collapse whitespace/punctuation runs.

    Deliberately script-preserving: NFKD strips combining marks from Latin
    ("génerative" -> "generative") without transliterating non-Latin scripts,
    so Arabic, Cyrillic, and CJK terms still match themselves. The pipeline
    matches in the source's own language; it never routes text through English
    (spec §5, "match in native script").

    This is byte-level normalization only. Lemmatization (spaCy) and embedding
    similarity are the layer above and wait on the PI's classification-approach
    decision — see docs/architecture.md §5b.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = unicodedata.normalize("NFKC", stripped).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]+", " ", lowered)).strip()


def find_terms(text: str, terms: list[str]) -> list[str]:
    """Return the terms (original spelling) that occur in `text`.

    Matching is on normalized text with word-ish boundaries, so "AI" does not
    match inside "said" and hyphenation/casing differences do not cause misses.

    Deduplicated on the normalized form: the query set repeats product names
    across its language blocks, and counting "Microsoft Copilot" four times
    would inflate every score that depends on how many distinct signals fired.
    """
    haystack = normalize(text)
    if not haystack:
        return []
    hits: list[str] = []
    seen: set[str] = set()
    for term in terms:
        needle = normalize(term)
        if not needle or needle in seen:
            continue
        if re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack):
            seen.add(needle)
            hits.append(term)
    return hits


def find_regex(text: str, patterns: list[str]) -> list[str]:
    """Return the patterns that match the RAW text.

    Regexes run against the original string, not the normalized one: the query
    set's patterns encode casing and punctuation on purpose (\\bGPT-?\\d\\b),
    which normalization would destroy. Query files are compiled at load time,
    so a malformed pattern fails before collection rather than silently reducing
    recall.
    """
    if not text:
        return []
    hits = []
    for pattern in patterns:
        if re.search(pattern, str(text)):
            hits.append(pattern)
    return hits


def local_filter(text: str, queries: GenAIQuerySet) -> bool:
    """Cheap pre-filter for bulk sources: does `text` plausibly match the set?

    Recall-oriented first pass ONLY. Product names under
    `context_required_terms` pass this filter — they are good retrieval signals
    even though they cannot establish relevance on their own; the Classifier
    quarantines them afterwards. `exclude_terms` are not applied here, for the
    same reason: dropping a record at retrieval time hides it from review.
    """
    if find_terms(text, queries.all_terms()):
        return True
    return bool(find_regex(text, queries.regex))
