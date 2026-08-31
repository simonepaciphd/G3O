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

**Wired in, 2026-08-30.** This paragraph used to say "not wired in", and the
decision to route the orchestrator through this module was the PI's to take. He
took it: the 225-row mapping was signed row by row on 2026-08-30 and
``PresweepConfig.language_policy`` now names it. ``build_queries`` already took
``languages`` per call, so per-institution selection needed no change to the
query builders and the GenAI roster hash did not move on account of it. What it
needed was a run-level validation choke point (:func:`assert_policy_rostered`),
honest per-row provenance (:func:`search_languages_string`), and the policy
layer described under :attr:`LanguagePolicy.always_include`.

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
from functools import cache
from pathlib import Path
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
    always_include:
        Language(s) every institution is searched in whatever its row says —
        the *policy* layer, kept out of the *evidence* layer above. Empty by
        default.

        The signed 2026-08-30 policy sets ``("en",)``, PI ruling R1, and the
        reason is mechanical rather than stylistic. Leg 1 issues a hardcoded
        English domain-discovery query for every institution
        (:data:`~g3o.discovery.query_builder.DOMAIN_QUERY_LANG`), but leg 2
        issues one query **per configured language**, so a row that does not
        name ``en`` loses its English *evidence* query — which is the query
        production runs today. Without this field, adopting the mapping would
        have been a silent recall regression on the 120 rows that do not name
        English.

        It is not written into those 120 rows because :attr:`rule` says a
        language enters a row when it was *observed* published, and 120 rows
        never observed English (France 0/10 sites, Indonesia 0/5). Writing it
        in would make the table contradict its own method; carrying it here
        issues identical queries and leaves the evidence artifact intact.

        **Order.** A tag already named by a row keeps that row's position —
        query order is part of the instrument and the signed rows' order is
        signed. A tag the row does *not* name is prepended, matching the
        mechanism table R1 was signed against (``ar, fr`` + ``en`` issues
        ``site:X AI``, ``site:X <ar>``, ``site:X <fr>``). So nothing is
        reordered and nothing is duplicated.
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
    always_include: tuple[str, ...] = ()
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
        if self.always_include:
            object.__setattr__(
                self,
                "always_include",
                _validate_languages(self.always_include, context="always_include"),
            )
        else:
            # Normalize whatever empty sequence was passed to the empty tuple,
            # so an empty list and an empty tuple hash and compare identically.
            object.__setattr__(self, "always_include", ())
        object.__setattr__(self, "_normalized", normalized)

    # ── lookup ───────────────────────────────────────────────────────────────

    def languages_for(self, record: Mapping[str, Any]) -> tuple[tuple[str, ...], bool]:
        """Languages for one institution record, and whether the fallback supplied them.

        Returns ``(languages, used_fallback)``, with :attr:`always_include`
        already applied — this is the single surface a caller queries, so a
        caller cannot get the mapped row and forget the policy layer. Use
        :meth:`mapped_languages_for` for the row as signed, without it.

        The flag is returned rather than logged so that a caller writing per-row
        provenance can record *how* the row's languages were chosen; a run in
        which 40% of rows fell back is a different measurement from one in which
        none did, and that difference is invisible in the language tags alone.
        """
        langs, used_fallback = self.mapped_languages_for(record)
        return self._with_always_include(langs), used_fallback

    def mapped_languages_for(
        self, record: Mapping[str, Any]
    ) -> tuple[tuple[str, ...], bool]:
        """The row as signed, **without** :attr:`always_include`.

        The evidence layer on its own. Separated from :meth:`languages_for` so
        the signed table can be read back and checked against the artifact it
        came from without the policy layer contaminating the comparison — and
        so :func:`language_policy_hash` can fingerprint the two layers
        separately rather than hashing a table nobody signed.
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

    def _with_always_include(self, langs: tuple[str, ...]) -> tuple[str, ...]:
        """Prepend the always-include tags this row does not already name.

        Prepend, not append: R1's signed mechanism table issues the English
        evidence query first for a row that does not name English. Only the
        *missing* tags move, so a row that already names ``en`` — Bangladesh's
        signed ``bn, en`` — keeps the query order it was signed with. Query
        order is part of the instrument, and re-sorting 105 signed rows to make
        the policy layer uniform would be an edit to rows nobody amended.
        """
        if not self.always_include:
            return langs
        missing = tuple(t for t in self.always_include if t not in langs)
        return missing + langs

    @property
    def countries(self) -> tuple[str, ...]:
        """Normalized country keys the policy covers, sorted."""
        return tuple(sorted(self._normalized))

    @property
    def selectable_languages(self) -> tuple[str, ...]:
        """Every language tag this policy could ever emit, sorted and deduplicated.

        Includes the fallback and :attr:`always_include` — the latter because a
        policy layer that adds an unrostered tag would fail inside the loop
        exactly like a mapped one, and on every institution rather than on some.
        This is the set :func:`assert_policy_rostered` checks, and it is what makes the run-level roster guarantee survive
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
        langs.update(self.always_include)
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

    Hashed over ``rule``, ``key``, ``fallback``, ``always_include`` and the
    normalized mapping — ``rule`` included, so restating what the same table
    measures moves the hash. Country keys are sorted (source-literal order must
    not leak in); each country's language tuple keeps its order, because query
    order is part of the instrument and sorting it here would hash a reordering
    identically and hide it. ``subnational_note`` is excluded: it documents the
    policy's limits and does not change a single query.

    ``mapping`` is hashed **as signed**, before ``always_include`` is applied,
    and ``always_include`` is hashed as its own key. Folding the policy layer
    into the per-country lists instead would make the evidence table and the
    policy layer indistinguishable in the fingerprint: a run whose 225 rows all
    named ``en`` outright would hash identically to one that added it by policy,
    and those are different instruments answering different questions.
    """
    payload = json.dumps(
        {
            "rule": " ".join(policy.rule.split()),
            "key": policy.key,
            "fallback": list(policy.fallback) if policy.fallback is not None else None,
            "always_include": list(policy.always_include),
            "mapping": {
                country: list(policy.mapped_languages_for({policy.key: country})[0])
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


# ---------------------------------------------------------------------------
# Signed policies on disk
# ---------------------------------------------------------------------------

#: Where a signed policy asset lives. One JSON file per signature, named by its
#: ``policy_id``, never overwritten — an amended mapping is a new signature and
#: therefore a new file, so a run that recorded ``2026-08-30`` can always be
#: reconstructed from the tree even after a later policy supersedes it.
POLICIES_DIR = Path(__file__).resolve().parent / "policies"

#: Filename stem of a policy asset: ``language_policy_<policy_id>.json``.
_POLICY_FILENAME = "language_policy_{policy_id}.json"

#: ``policy_id`` of the mapping the PI signed row by row on 2026-08-30 (225
#: rows, 0 deferred). Not a default anywhere — naming it is still an explicit
#: act on ``PresweepConfig`` — but a constant so that callers and tests refer to
#: one string rather than retyping a date.
SIGNED_POLICY_2026_08_30 = "2026-08-30"


class UnknownPolicyError(LanguagePolicyError):
    """No signed policy asset by that id.

    Not a fallback to an unsigned mapping and not a fallback to English: a run
    that named a policy which does not exist has not chosen a language
    instrument, and guessing one for it is the failure
    :class:`UnmappedCountryError` exists to prevent, one level up.
    """


def available_policies() -> tuple[str, ...]:
    """Every signed ``policy_id`` present in :data:`POLICIES_DIR`, sorted."""
    if not POLICIES_DIR.is_dir():
        return ()
    prefix, suffix = _POLICY_FILENAME.split("{policy_id}")
    return tuple(
        sorted(
            path.name[len(prefix) : -len(suffix)]
            for path in POLICIES_DIR.glob(_POLICY_FILENAME.format(policy_id="*"))
        )
    )


def load_signed_policy(policy_id: str) -> LanguagePolicy:
    """Load the signed policy asset named ``policy_id``.

    The asset is the machine-readable form of a PI-signed markdown artifact and
    carries its own ``rule``, ``key``, ``always_include`` and ``mapping``; none
    of the four is supplied here, because supplying any of them would let this
    function decide something the signature decided. Extra keys the asset
    carries for people (``_comment``, ``source``, ``record``, ``provenance``)
    are read past deliberately — they document the signature and change no
    query, which is the same line :attr:`LanguagePolicy.subnational_note` sits
    on.

    Cached: a policy is an immutable file, the mapping is 225 rows, and
    :meth:`LanguagePolicy.languages_for` is called once per institution on runs
    of tens of thousands. The cache is keyed on the *directory* as well as the
    id, so redirecting :data:`POLICIES_DIR` cannot serve a policy loaded from
    somewhere else — a stale hit there would silently run a mapping the config
    did not name.
    """
    return _load_signed_policy(policy_id, POLICIES_DIR)


@cache
def _load_signed_policy(policy_id: str, policies_dir: Path) -> LanguagePolicy:
    path = policies_dir / _POLICY_FILENAME.format(policy_id=policy_id)
    if not path.is_file():
        raise UnknownPolicyError(
            f"no signed language policy {policy_id!r} at {path}. "
            f"Available: {list(available_policies())!r}. A policy is a PI-signed "
            f"artifact checked into the tree, not something a config file can "
            f"supply inline — see the module docstring."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        mapping = payload["mapping"]
        rule = payload["rule"]
    except KeyError as exc:
        raise LanguagePolicyError(
            f"signed policy {policy_id!r} at {path} is missing required key {exc}"
        ) from exc
    return LanguagePolicy(
        rule=rule,
        mapping={country: tuple(langs) for country, langs in mapping.items()},
        always_include=tuple(payload.get("always_include", ())),
        key=payload.get("key", "country"),
        subnational_note=payload.get("subnational_note", ""),
    )


__all__ = [
    "POLICIES_DIR",
    "SIGNED_POLICY_2026_08_30",
    "EmptyPolicyError",
    "LanguagePolicy",
    "LanguagePolicyError",
    "UnknownPolicyError",
    "UnmappedCountryError",
    "assert_policy_rostered",
    "available_policies",
    "language_policy_hash",
    "load_signed_policy",
    "search_languages_string",
]
