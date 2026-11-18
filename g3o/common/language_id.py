"""Deterministic language identification of a page's stored main text (X27, RC-D-025 P15).

Signed rule (``items/core.source_language/rules/0``, codebook r15): "Pinned
local language-ID library on stored text; same tag grammar as
``institution_search_languages``; ``mul`` when no language exceeds a set share."
PI rulings 2026-11-11 (A3.1 a, A3.2 a, 2 b; build rulings 21-25):

- A3.1 a: lingua-language-detector, exact pin, offline.
- A3.2 a: the leading language's share of characters on **main** text
  (``RenderedPage.text``; the chrome text is never read here) > 0.5, else
  ``mul``; under a minimum length, ``unknown``. The minimum length is set here
  (:data:`MIN_MAIN_TEXT_CHARS`) and shown to the PI.
- 2 b: ``lingua-language-detector==2.2.0`` (:data:`PINNED_LINGUA`), Python >= 3.12.

Configuration (fixed; :func:`configuration` records it, and the instrument
binds it through ``extractor_configuration``):

- **Languages loaded:** every language lingua 2.2.0 ships
  (``LanguageDetectorBuilder.from_all_languages()``, 75 languages). No subset
  is chosen, so no country or roster decides which languages a page can be
  found to be in.
- **Accuracy mode:** lingua's default high-accuracy mode (``with_low_accuracy_mode``
  is not called). Low-accuracy mode drops the higher n-gram models and is
  weakest on exactly the short spans multi-language detection produces.
- **Minimum relative distance:** lingua's default (0.0), not set.
- **Model loading:** lazy (``with_preloaded_language_models`` is not called).
  Preloading changes start-up latency and memory only, not the result.
- **Detection call:** ``detect_multiple_languages_of(text)`` on the main text
  exactly as stored (no normalisation). Each result is a span
  ``[start_index, end_index)`` in characters (Python code points) with one
  language.
- **Share (letters only; PI ruling 23 b on the build questions, 2026-11-11):**
  the letters (``str.isalpha``) inside each language's spans, summed; the
  leading language is the one with the most letters (ties ordered by tag; two
  tied languages cannot both exceed 0.5, so a tie at the top is always
  ``mul``). share = leading letters / all letters of the main text. Whitespace,
  digits, punctuation and symbols count in neither; letters no span covers
  stay in the denominator: they are main text that no language accounts for.
- **Decision:** ``len(text) < MIN_MAIN_TEXT_CHARS`` -> ``unknown`` (the
  minimum length counts all characters, as signed: ruling 21); no span at
  all, or no letters (no language identified, e.g. a script lingua does not
  model) -> ``unknown``; share > :data:`MUL_SHARE` (strictly) -> the leading language's
  tag; otherwise ``mul``.

Tag grammar: ``institution_search_languages`` stores lowercase ISO 639-1
tags, ISO 639-3 only where no two-letter code exists, with an optional
four-letter script subtag (``g3o.common.languages._LANG_TAG``,
``contract.LANGS_PATTERN``). Every language lingua 2.2.0 ships has an ISO
639-1 code, so the tag is that code, lowercased; lingua reports no script, so
no script subtag is written. A language with no tag in that grammar is refused
(:class:`UnmappedLanguageError`), never guessed.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import version
from typing import Any

LIBRARY = "lingua-language-detector"
#: PI ruling 2 b (2026-11-11). Change only with a new ruling.
PINNED_LINGUA = "2.2.0"
LANGUAGE_ID_VERSION = "g3o.common.language_id.v2"  # v2: letters-only share (ruling 23 b)

#: Minimum main-text length, in characters (``len(RenderedPage.text)``), below
#: which no language is coded and the value is ``unknown`` (A3.2 a; shown to the PI).
#:
#: Rationale: 200 characters is about two to three ordinary sentences, roughly
#: 30-40 words in a Latin-script language. lingua's own evaluation reports its
#: accuracy separately for single words, word pairs and sentences, and is
#: reliable only from sentence length up; multi-language detection splits the
#: text further into spans, so a page needs several sentences before one
#: mis-attributed span cannot decide the share on its own (on a 251-character
#: English test paragraph lingua already assigns a two-word span to French).
#: A stored main text shorter than this is in practice an error, consent or
#: redirect stub rather than a page whose language is worth recording. The
#: cost is that a genuinely short page (and a short page in a dense script
#: such as Chinese, where 200 characters is a long paragraph) is recorded as
#: ``unknown`` rather than coded.
MIN_MAIN_TEXT_CHARS = 200
#: The ``mul`` share (A3.2 a): the leading language must exceed it strictly.
MUL_SHARE = 0.5
MUL = "mul"
UNKNOWN = "unknown"

#: Same as ``g3o.common.languages._LANG_TAG`` (the ``institution_search_languages`` tag grammar).
_TAG = re.compile(r"^[a-z]{2,3}(-[a-z]{4})?$")


class LanguageIdError(RuntimeError):
    """The installed library or its configuration differs from the pinned one."""


class UnmappedLanguageError(LanguageIdError):
    """lingua returned a language with no tag in the ``institution_search_languages`` grammar."""


def _lingua():
    installed = version(LIBRARY)
    if installed != PINNED_LINGUA:
        raise LanguageIdError(f"{LIBRARY} {installed} is installed; source_language is pinned to "
                              f"{PINNED_LINGUA} (PI ruling 2 b, 2026-11-11)")
    import lingua

    return lingua


def language_tag(language: Any) -> str:
    """The ``institution_search_languages`` tag of one lingua ``Language`` (ISO 639-1, lowercase)."""
    iso1 = getattr(language, "iso_code_639_1", None)
    tag = getattr(iso1, "name", "").lower() if iso1 is not None else ""
    if not _TAG.fullmatch(tag) or len(tag) != 2:
        raise UnmappedLanguageError(f"lingua language {language!r} has no ISO 639-1 tag ({tag!r}); "
                                    "not guessed")
    return tag


@lru_cache(maxsize=1)
def tag_table() -> tuple[tuple[str, str], ...]:
    """``(lingua language name, tag)`` for every loaded language, sorted by name."""
    lingua = _lingua()
    table = tuple(sorted((lang.name, language_tag(lang)) for lang in lingua.Language.all()))
    tags = [t for _, t in table]
    if len(set(tags)) != len(tags):
        raise UnmappedLanguageError("two lingua languages map onto one tag")
    return table


@lru_cache(maxsize=1)
def _detector():
    lingua = _lingua()
    return lingua.LanguageDetectorBuilder.from_all_languages().build()


def configuration() -> dict[str, Any]:
    """The pinned configuration, for the instrument record (all values fixed)."""
    table = tag_table()
    return {
        "version": LANGUAGE_ID_VERSION,
        "library": LIBRARY,
        "library_version": version(LIBRARY),
        "languages": "from_all_languages",
        "language_count": len(table),
        "tag_table_sha256": hashlib.sha256(json.dumps(table, separators=(",", ":")).encode()).hexdigest(),
        "accuracy_mode": "high",
        "minimum_relative_distance": "default",
        "preloaded_models": False,
        "detection": "detect_multiple_languages_of",
        "text": "main",
        "share_unit": "letters of main text (str.isalpha)",
        "mul_share": MUL_SHARE,
        "mul_share_comparison": "strictly_greater",
        "min_main_text_chars": MIN_MAIN_TEXT_CHARS,
    }


@dataclass(frozen=True)
class LanguageId:
    """One page's language decision and how it was reached."""

    tag: str  # a language tag, ``mul`` or ``unknown``
    reason: str  # ``language`` / ``mul`` / ``below_min_length`` / ``no_language_identified``
    text_chars: int
    shares: tuple[tuple[str, float], ...]  # (tag, share), descending share then tag

    @property
    def leading_share(self) -> float:
        return self.shares[0][1] if self.shares else 0.0


def identify(main_text: str) -> LanguageId:
    """The language of ``main_text`` (``RenderedPage.text``) under the pinned configuration."""
    if not isinstance(main_text, str):
        raise TypeError("main_text must be the stored main text (str)")
    n = len(main_text)
    if n < MIN_MAIN_TEXT_CHARS:
        return LanguageId(UNKNOWN, "below_min_length", n, ())
    letters = sum(1 for ch in main_text if ch.isalpha())
    chars: dict[str, int] = {}
    for span in _detector().detect_multiple_languages_of(main_text):
        tag = language_tag(span.language)
        if span.end_index < span.start_index or span.start_index < 0 or span.end_index > n:
            raise LanguageIdError(f"lingua span out of range: {span!r} on {n} characters")
        width = sum(1 for ch in main_text[span.start_index:span.end_index] if ch.isalpha())
        chars[tag] = chars.get(tag, 0) + width
    chars = {t: c for t, c in chars.items() if c}
    if not chars or not letters:
        return LanguageId(UNKNOWN, "no_language_identified", n, ())
    shares = tuple(sorted(((t, c / letters) for t, c in chars.items()), key=lambda x: (-x[1], x[0])))
    lead = shares[0][0]
    if chars[lead] > MUL_SHARE * letters:  # integer letters vs the share, no float division
        return LanguageId(lead, "language", n, shares)
    return LanguageId(MUL, "mul", n, shares)


__all__ = [
    "LANGUAGE_ID_VERSION", "LIBRARY", "MIN_MAIN_TEXT_CHARS", "MUL", "MUL_SHARE", "PINNED_LINGUA", "UNKNOWN",
    "LanguageId", "LanguageIdError", "UnmappedLanguageError", "configuration", "identify", "language_tag",
    "tag_table",
]
