"""Per-institution search-language selection — the mechanism, not the rule.

Discovery has always chosen its query languages **per run**:
``PresweepConfig.discovery_languages`` is a run-level tuple, and
``PresweepConfig.institution_search_languages`` records that same tuple verbatim
onto every row of the run (``g3o/cli.py``, ``contract.py`` group C). There is no
per-institution language selection anywhere in the pipeline, so a wave that
mixes twelve countries either searches every institution in every configured
language — paying ``n_languages`` leg-2 credits on all of them — or searches all
of them in one language and records a provenance string that is true of the run
and misleading about the row.

This module supplies the missing selector and nothing else. Three things it is
deliberately **not**:

**Not a mapping.** :class:`LanguagePolicy` has no default ``mapping`` and cannot
be constructed without one. The same discipline ``config.py`` applies to the
projection abort (``de96557``: "the projection abort has no default") applies
here for a stronger reason: which language a country's institutions are searched
in *is the instrument*, and a mapping with a default is a mapping that ships
itself. A candidate mapping is tabled for row-by-row PI signature; it is not in
this file, and this file will not run without one.

**Not a rule.** ``mapping`` says *what* the answer is; :attr:`LanguagePolicy.rule`
says *which question it answers* — official language(s), language of government
publication, majority language, most-spoken language. Those give different
answers on the same country and therefore measure different things. ``rule`` is
required and free-text on purpose: the policy cannot be constructed without
naming its own rule, so the rule reaches :func:`language_policy_hash` and the
run's provenance instead of being inferable only from the table.

**Not wired in.** Nothing here is imported by the orchestrator or by
``PresweepConfig``. ``build_queries`` already takes ``languages`` per call, so
per-institution selection needs no change to the query builders and the GenAI
roster hash cannot move on account of this module. What it *does* need is a
run-level validation choke point (:func:`assert_policy_rostered`) and honest
per-row provenance (:func:`search_languages_string`); both are here, and the
decision to route the orchestrator through them is the PI's.

Fail-loud, not fall-back
------------------------
:class:`UnmappedCountryError` is the A7 discipline (PI decision 2026-08-02)
carried into per-institution selection. Under a run-level tuple, a language that
could not be queried was rejected at config construction, before a Serper credit
was spent. Under per-institution selection the same failure moves inside the
loop and gets a new way to hide: an unmapped country that silently fell back to
English would issue **English** queries for that institution, record whatever
the fallback produced, and contribute a row to a per-country readiness figure
that never measured that country. That is
:class:`~g3o.discovery.query_builder.UnknownLanguageError` again, one level down.

A fallback is therefore opt-in and never implicit — see
:attr:`LanguagePolicy.fallback` — and :meth:`LanguagePolicy.languages_for`
reports whether the answer came from the mapping or from the fallback, so a
caller that records provenance can record which.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from g3o.discovery.query_builder import (
    DOMAIN_QUERY_LANG,
    assert_languages_rostered,
)

# One language tag as the extraction contract can store it.
#
# ``contract.LANGS_PATTERN`` constrains ``institution_search_languages`` to
# comma-joined lowercase ``language[-script]`` tags — ISO 639-1, or ISO 639-3
# where no two-letter code exists, with an optional four-letter script subtag
# (``uz-latn``). Widened from bare ISO 639-1 pairs by PI ruling 2026-08-29
# (extract contract v2.5 / validate v1.3), so a script variant is expressible
# and a 639-3-only language is recordable. Lowercase-only: BCP 47 is
# case-insensitive, and one canonical casing keeps ``uz-Latn`` / ``uz-latn``
# from coexisting as distinct provenance strings — the mixed-case form is
# rejected here, at construction, not at Stage 5 after the run is paid for.
_LANG_TAG = re.compile(r"^[a-z]{2,3}(-[a-z]{4})?$")


class LanguagePolicyError(ValueError):
    """Base class for every way a language policy can be wrong."""


class EmptyPolicyError(LanguagePolicyError):
    """A policy with no mapping, or a mapping entry with no languages.

    Rejected at construction rather than treated as "search nothing": an
    institution that is searched in zero languages produces no queries, no
    candidate URLs, and a funnel row indistinguishable from one whose queries
    all came back empty. The measurement would read as absence of activity.
    """


class UnmappedCountryError(LanguagePolicyError):
    """An institution's country has no entry in the policy and no fallback is set.

    Deliberately not an English fallback — see the module docstring.
    """


@dataclass(frozen=True)
class LanguagePolicy:
    """Which language(s) an institution's discovery queries are issued in.

    Parameters
    ----------
    rule:
        Free-text statement of the question the mapping answers — "official
        language(s) of the state", "language(s) of central-government web
        publication", "most-spoken language". **Required.** Different rules give
        different mappings on the same country, so a mapping presented without
        its rule is a table whose meaning has to be guessed. It is hashed into
        :func:`language_policy_hash`, which makes an edit to the rule a
        different instrument even when every row of the table is unchanged.
    mapping:
        Country key -> the language tag(s) to search that country's institutions
        in, in query order. **Required, and there is no default.** Keys are
        matched against the field named by ``key``, case-folded and stripped.
    key:
        Which field of the institution record carries the country. Defaults to
        ``"country"``, the field
        :func:`g3o.run.presweep.records.institution_record` projects; the
        wave-2 frame also carries ``country_iso3``, which is the stabler join
        key and the reason this is a parameter.
    fallback:
        Language(s) for an institution whose country is absent from ``mapping``.
        ``None`` (the default) means raise :class:`UnmappedCountryError`.
        Setting it is an explicit decision to measure unmapped countries in a
        language nobody chose for them.
    subnational_note:
        Free-text acknowledgement of the granularity the policy does **not**
        have. A country key is one answer for every institution in the country,
        which is crudest exactly where the frame is densest — an Indian block
        does not publish in the same language as another state's block. Optional
        and never enforced; it exists so the limitation travels with the policy
        instead of living only in a launch card.
    """

    rule: str
    mapping: Mapping[str, tuple[str, ...]]
    key: str = "country"
    fallback: tuple[str, ...] | None = None
    subnational_note: str = ""
    # Populated by __post_init__ from `mapping`; the canonical lookup surface.
    _normalized: dict[str, tuple[str, ...]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not self.rule or not self.rule.strip():
            raise EmptyPolicyError(
                "LanguagePolicy.rule is required and must be non-empty: a mapping "
                "without its rule does not say what it measured. State which "
                "question the table answers (official language(s), language of "
                "government publication, majority language, most-spoken)."
            )
        if not self.mapping:
            raise EmptyPolicyError(
                "LanguagePolicy.mapping is required and must be non-empty. There "
                "is deliberately no default mapping — see the module docstring."
            )

        normalized: dict[str, tuple[str, ...]] = {}
        for raw_key, langs in self.mapping.items():
            country = _normalize_key(raw_key)
            if not country:
                raise EmptyPolicyError(
                    f"empty country key in mapping (from {raw_key!r}); a blank key "
                    f"would silently claim every institution whose {self.key!r} is blank"
                )
            if country in normalized:
                raise LanguagePolicyError(
                    f"duplicate country key {country!r} after normalization: two "
                    f"entries in the mapping resolve to the same institution and "
                    f"which one wins would be an accident of dict order"
                )
            normalized[country] = _validate_languages(
                langs, context=f"mapping[{raw_key!r}]"
            )

        if self.fallback is not None:
            object.__setattr__(
                self,
                "fallback",
                _validate_languages(self.fallback, context="fallback"),
            )
        object.__setattr__(self, "_normalized", normalized)

    # ── lookup ───────────────────────────────────────────────────────────────

    def languages_for(self, record: Mapping[str, Any]) -> tuple[tuple[str, ...], bool]:
        """Languages for one institution record, and whether the fallback supplied them.

        Returns ``(languages, used_fallback)``. The flag is returned rather than
        logged so that a caller writing per-row provenance can record *how* the
        row's languages were chosen; a run in which 40% of rows fell back is a
        different measurement from one in which none did, and that difference is
        invisible in the language tags alone.
        """
        country = _normalize_key(record.get(self.key, ""))
        langs = self._normalized.get(country)
        if langs is not None:
            return langs, False
        if self.fallback is not None:
            return self.fallback, True
        raise UnmappedCountryError(
            f"no language mapping for {self.key}={record.get(self.key)!r} "
            f"(normalized {country!r}); mapped: {sorted(self._normalized)!r}. "
            f"Adding a country is a PI-signed row on the country->language table, "
            f"not a config change. Set LanguagePolicy.fallback only to deliberately "
            f"measure unmapped countries in a language nobody chose for them."
        )

    @property
    def countries(self) -> tuple[str, ...]:
        """Normalized country keys the policy covers, sorted."""
        return tuple(sorted(self._normalized))

    @property
    def selectable_languages(self) -> tuple[str, ...]:
        """Every language tag this policy could ever emit, sorted and deduplicated.

        Includes the fallback. This is the set :func:`assert_policy_rostered`
        checks, and it is what makes the run-level roster guarantee survive
        per-institution selection: today ``assert_languages_rostered`` promises
        that every *configured* language is rostered, checked once before any
        credit is spent. Per-institution selection would weaken that promise to
        "every language actually selected", which is only knowable after the
        run. Checking the whole selectable set restores the original strength.
        """
        langs: set[str] = set()
        for value in self._normalized.values():
            langs.update(value)
        if self.fallback is not None:
            langs.update(self.fallback)
        return tuple(sorted(langs))


def _normalize_key(value: Any) -> str:
    """Case-fold and collapse whitespace in a country key.

    Master ``country`` values are free text and reach here unchanged; matching on
    the raw string would make ``"Czechia"`` and ``"czechia "`` two countries.
    Normalization is applied identically to the mapping's keys and to the
    record's value, so the two cannot drift.
    """
    return " ".join(str(value or "").split()).casefold()


def _validate_languages(langs: Iterable[str], *, context: str) -> tuple[str, ...]:
    """Coerce to an ordered, duplicate-free tuple of contract-storable tags."""
    if isinstance(langs, str):
        raise LanguagePolicyError(
            f"{context}: expected a sequence of language tags, got the string "
            f"{langs!r}. A bare string would iterate as characters and silently "
            f"become two one-letter languages."
        )
    out: list[str] = []
    for lang in langs:
        if not isinstance(lang, str) or not _LANG_TAG.match(lang):
            raise LanguagePolicyError(
                f"{context}: {lang!r} is not a storable language tag. "
                f"contract.LANGS_PATTERN admits lowercase language[-script] tags "
                f"only — ISO 639-1 (or 639-3 where no two-letter code exists), "
                f"optionally with a four-letter lowercase script subtag, e.g. "
                f"'uz-latn'. Anything else cannot be recorded in "
                f"institution_search_languages and would fail at Stage 5, after "
                f"the run was paid for."
            )
        if lang not in out:
            out.append(lang)
    if not out:
        raise EmptyPolicyError(
            f"{context}: no languages. An institution searched in zero languages "
            f"issues no queries and reports as absence of activity."
        )
    return tuple(out)


def language_policy_hash(policy: LanguagePolicy) -> str:
    """Stable fingerprint of a whole language policy.

    The counterpart of
    :func:`g3o.discovery.query_builder.genai_terms_roster_hash`, and for the same
    reason: a run resumed after an edit to the policy is running a different
    instrument than it launched with, and the resume guard can only see that if
    the policy has a fingerprint.

    Hashed over ``rule``, ``key``, ``fallback`` and the normalized mapping —
    ``rule`` included, so restating what the same table measures moves the hash.
    Country keys are sorted (source-literal order must not leak in); each
    country's language tuple keeps its order, because query order is part of the
    instrument and sorting it here would hash a reordering identically and hide
    it. ``subnational_note`` is excluded: it documents the policy's limits and
    does not change a single query.
    """
    payload = json.dumps(
        {
            "rule": " ".join(policy.rule.split()),
            "key": policy.key,
            "fallback": list(policy.fallback) if policy.fallback is not None else None,
            "mapping": {
                country: list(policy.languages_for({policy.key: country})[0])
                for country in policy.countries
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def assert_policy_rostered(policy: LanguagePolicy, roster: Mapping[str, Any]) -> None:
    """Reject a policy that could select a language the run cannot query.

    The run-level choke point per-institution selection needs, and the reason
    :attr:`LanguagePolicy.selectable_languages` exists. Delegates to
    :func:`g3o.discovery.query_builder.assert_languages_rostered` so that
    "rostered" has exactly one definition and a mode-specific roster
    (``GENAI_TERMS_BY_LANG`` under ``legacy``, ``EVIDENCE_TERMS_BY_LANG`` under
    ``chain``) is honoured here too.

    Call it once, before the first credit is spent —
    :class:`~g3o.discovery.query_builder.UnknownLanguageError` raised on
    institution 3,000 of 10,000 has already cost 3,000 institutions' worth of
    queries.
    """
    assert_languages_rostered(policy.selectable_languages, dict(roster))


def search_languages_string(
    languages: Iterable[str],
    *,
    mode: str,
    domain_query_lang: str = DOMAIN_QUERY_LANG,
) -> str:
    """The per-institution counterpart of ``PresweepConfig.institution_search_languages``.

    Same contract as the run-level property, one grain finer: the string names
    the languages **this institution's** queries were actually issued in, in
    query order, comma-joined for ``ContractRow.institution_search_languages``.

    Mode-aware for the same reason the config property is (2026-08-02): chain
    mode's leg 1 carries the English ``official website`` suffix whatever
    ``discovery_languages`` says, so a chain run that reported only the leg-2
    language would claim a row was searched in ``kk`` when half its queries were
    English. English is therefore prepended under ``chain`` — first, because it
    is issued first — and deduplicated.

    Returns a value that satisfies ``contract.LANGS_PATTERN`` for any language
    tuple a :class:`LanguagePolicy` accepted, which is what
    :func:`_validate_languages` is guarding.
    """
    ordered: list[str] = []
    if mode == "chain":
        ordered.append(domain_query_lang)
    for lang in languages:
        if lang not in ordered:
            ordered.append(lang)
    if not ordered:
        raise EmptyPolicyError(
            "no languages to record: institution_search_languages must name at "
            "least one language, and a row that searched nothing is not a row "
            "whose provenance can be written honestly."
        )
    return ",".join(ordered)


__all__ = [
    "EmptyPolicyError",
    "LanguagePolicy",
    "LanguagePolicyError",
    "UnmappedCountryError",
    "assert_policy_rostered",
    "language_policy_hash",
    "search_languages_string",
]
