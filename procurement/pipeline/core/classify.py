"""GenAI relevance classification — pluggable backend.

The decision "is this record about generative AI, and which category" is a
`Classifier` interface with swappable backends so the PI can choose the approach
without rewiring the pipeline (see docs/architecture.md §5b):

  - NLPClassifier  (DEFAULT, built): term/regex matching over normalized text.
  - LLMClassifier  (SCOPED, do NOT build this phase): LLM adjudication.

This module supplies the mechanism, not the labels. Two hard boundaries:

  1. It never invents terms. Everything it matches comes from the query-set
     config, which is the PI's.
  2. It assigns `genai_category` only under ruling Q1a (2026-08-04), which
     authorises applying the contract's `activity_type` members directly to
     procurement records — §4.2's "Typical evidence" column names procurement
     records for three of them. The signal table lives in `core.coding`, is
     drawn from the contract's own definitions, and is applied only to records
     already judged relevant. When a relevant record gives no basis for choosing,
     it is REPORTED, NOT CODED (ruling D1): `unknown` is the ruled answer but is
     not a legal enum member until contract v2.2 lands.

What this backend produces is a per-source disposition, which the contract does
support: `genai_evidence` (column 36) is assessed per source, and Edge Case A
codes a supplied page with no GenAI mention as `confirms_absence` on that row.
What it must NOT produce is `has_genai_activity` (column 8) — that is an
institution-level verdict, "same value on every row for the same institution",
so it can only be settled once every source for an institution has been read.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .coding import CANNOT_TYPE, activity_type_for
from .contract import ACTIVITY_TYPE, GENAI_EVIDENCE, SOURCE_SNIPPET_MAX_CHARS, UNCERTAINTY_FLAGS
from .models import Classification, GenAIQuerySet
from .search import find_regex, find_terms, normalize

# Fields whose text is read for classification (codebook §4.2 "assemble context").
CONTEXT_FIELDS = ("title", "description", "buyer_name", "supplier_name")

EVIDENCE_MAX_CHARS = SOURCE_SNIPPET_MAX_CHARS   # contract E37 cap

# Review triggers this backend raises. Flags that exist in the contract's closed
# column-39 vocabulary may be emitted downstream verbatim; the internal_ ones
# are operational only and must be dropped before contract output, because the
# contract says "use these exact strings" and does not know ours.
INTERNAL_FLAG_PREFIX = "internal_"
LOW_SCORE_FLAG = "internal_low_match_density"

# Ruling D1: a relevant record that cannot be typed is reported, never coded.
# Carrying it as a flag keeps it visible in staging and in the run report.
CANNOT_TYPE_FLAG = "internal_cannot_type_pending_v2.2"

# Rule R8 (PI, 2026-10-07): a record with no descriptive text cannot be
# negative evidence just because no keyword matched. Buyer/supplier names are
# matched but do not count as descriptive text.
DESCRIPTIVE_FIELDS = ("title", "description")
INSUFFICIENT_TEXT_FLAG = "internal_insufficient_text"
NOT_ASSESSABLE = "not_assessable"

# Flags that record provenance or assessability, not a judgement a reviewer
# must make. They are kept on the record but never open a review.
INFORMATIONAL_FLAGS = frozenset({
    INSUFFICIENT_TEXT_FLAG,
    "internal_description_from_items",
    "internal_value_from_items",
    "internal_value_partial_items_unpriced",
    "internal_value_mixed_currency",
    "internal_value_currency_missing",
})


def needs_review(flags) -> bool:
    return any(f not in INFORMATIONAL_FLAGS for f in flags or [])


def contract_uncertainty_flags(flags: list[str]) -> list[str]:
    """Filter staging review flags down to the contract's column-39 vocabulary.

    The primary-row builder calls this before writing `uncertainty_flags`.
    Anything not in the closed vocabulary — our operational triggers — is
    dropped rather than smuggled into contract output under a made-up name.
    """
    return [f for f in flags if f in UNCERTAINTY_FLAGS]


def is_valid_activity_type(value) -> bool:
    """True if `value` is a contract activity_type (D12) member, or unset.

    Guard for anything that later assigns `genai_category`: the enum is the
    contract's and admits no variations, capitalization changes, or synonyms.
    """
    return value is None or value in ACTIVITY_TYPE


class Classifier(ABC):
    """Common interface. Every record's classifier_version is recorded for the
    transparency trail."""

    version: str = "unset"

    @abstractmethod
    def classify(self, fields: dict) -> Classification:
        """Given the intermediate field dict (title/description/etc.), return a
        Classification (relevance, score, evidence)."""
        raise NotImplementedError


class NLPClassifier(Classifier):
    """DEFAULT backend. Multilingual term/phrase + regex matching over
    accent-folded, casefolded text (core.search.normalize).

    Implemented as the deterministic layer only. Lemmatization (spaCy) and
    embedding similarity are deliberately not wired in: the NLP-only vs.
    NLP+LLM question is the PI's (docs/architecture.md §8), and adding a model
    dependency would prejudge it. The interface below does not change when
    either is added — a scorer swap, not a rewrite.

    These are per-source dispositions, not finished contract rows:

      substantive term matched         -> yes     / confirms_activity
      only a context-required product  -> unclear / ambiguous  + genai_vs_traditional_ai
      only an acronym regex            -> unclear / ambiguous  + genai_vs_traditional_ai
      nothing matched, no descriptive  -> not_assessable / (none) + internal_insufficient_text
        text (title/description)
      nothing matched                  -> no      / confirms_absence

    The `relevance` column is this source's contribution, NOT contract column 8.
    `has_genai_activity` is institution-level and is settled by aggregating every
    source for an institution: one `confirms_absence` record says nothing about
    the institution until all of its sources have been read. That aggregation
    step is not built yet.

    `background_only` is a fourth contract evidence value this backend never
    emits: it means a source gives general context without documenting activity
    at the institution, and the procurement channel reads only procurement
    records for a named buyer. Leave it to the primary-row builder.

    `threshold` does not gate the verdict — with the deterministic backend the
    verdict is the codebook rule. It marks the uncertainty band for review, and
    is the hook a scored backend (embeddings / supervised) plugs into later.
    Set it from the validation sample, never from the default.
    """

    def __init__(self, queries: GenAIQuerySet, model: str | None = None,
                 embedding_model: str | None = None, threshold: float = 0.5):
        self.queries = queries
        self.model = model
        self.embedding_model = embedding_model
        self.threshold = threshold
        self.version = f"nlp/{model or 'terms'}@{queries.version}"

    # -- scoring ---------------------------------------------------------- #

    def _score(self, substantive: list[str], contextual: list[str],
               regexes: list[str]) -> float:
        """Match-density heuristic in [0, 1]. NOT a probability.

        Deterministic and monotone in the number of distinct signals, which is
        all it claims to be. The auto-accept threshold must be set from the
        hand-labelled validation sample (spec §5), never from this default.
        """
        weighted = len(substantive) + 0.5 * len(contextual) + 0.25 * len(regexes)
        return round(min(1.0, weighted / 3.0), 3)

    # -- verdict ---------------------------------------------------------- #

    def classify(self, fields: dict) -> Classification:
        text = " \n".join(
            str(fields[k]) for k in CONTEXT_FIELDS
            if fields.get(k)
        )

        quarantined = {normalize(t) for t in self.queries.context_required_terms}
        matched = find_terms(text, self.queries.all_terms())
        substantive = [t for t in matched if normalize(t) not in quarantined]
        contextual = [t for t in matched if normalize(t) in quarantined]
        regexes = find_regex(text, self.queries.regex)
        excluded = find_terms(text, self.queries.exclude_terms)

        # An exclude term is a known acronym collision ("GPT partition"). It
        # kills acronym-regex evidence, which is what it was written to catch —
        # it does not override an explicit generative-AI term.
        if excluded and not substantive:
            regexes = []
            contextual = []

        score = self._score(substantive, contextual, regexes)
        flags: list[str] = []

        if substantive:
            # An explicit generative-AI term IS the inclusion rule (codebook
            # §3.1), so the verdict is rule-based and the score never overrides
            # it. A thin match is still routed to review: codebook §8 lists
            # "score inside the uncertainty band" as its own trigger.
            relevance, evidence_type, relevant = "yes", "confirms_activity", True
            if score < self.threshold:
                flags.append(LOW_SCORE_FLAG)
        elif contextual or regexes:
            relevance, evidence_type, relevant = "unclear", "ambiguous", False
            flags.append("genai_vs_traditional_ai")
        elif not any(str(fields.get(k) or "").strip() for k in DESCRIPTIVE_FIELDS):
            # R8: nothing to read, so no evidence either way. Not coded.
            relevance, evidence_type, relevant = NOT_ASSESSABLE, None, False
            flags.append(INSUFFICIENT_TEXT_FLAG)
        else:
            # Per-source absence, per contract Edge Case A. This is NOT the
            # institution-level `no`; see the class docstring.
            relevance, evidence_type, relevant = "no", "confirms_absence", False

        assert evidence_type is None or evidence_type in GENAI_EVIDENCE, evidence_type   # contract column 36

        # activity_type (Q1a) — only for records that are actually relevant.
        category = None
        if relevance == "yes":
            typed, signals = activity_type_for(fields)
            if typed is CANNOT_TYPE or typed == CANNOT_TYPE:
                flags.append(CANNOT_TYPE_FLAG)
            else:
                category = typed
                assert category in ACTIVITY_TYPE, category

        return Classification(
            genai_relevant=relevant,
            relevance=relevance,
            genai_evidence_type=evidence_type,
            genai_relevance_score=score,
            genai_category=category,   # contract activity_type (D12), ruling Q1a
            genai_evidence=self._evidence(substantive, contextual, regexes, excluded, text),
            review_flags=flags,
            classifier_version=self.version,
        )

    # -- transparency trail ----------------------------------------------- #

    def _evidence(self, substantive: list[str], contextual: list[str],
                  regexes: list[str], excluded: list[str], text: str) -> str | None:
        """Human-readable record of why the verdict came out as it did.

        Matched terms are reported in their ORIGINAL spelling, and the snippet
        is verbatim source text — never a paraphrase, never a translation
        (codebook §7, "preserve original-language evidence").
        """
        parts = []
        if substantive:
            parts.append("terms: " + "; ".join(substantive))
        if contextual:
            parts.append("context-required: " + "; ".join(contextual))
        if regexes:
            parts.append("regex: " + "; ".join(regexes))
        if excluded:
            parts.append("excluded-by: " + "; ".join(excluded))
        if not parts:
            return None
        snippet = " ".join(text.split())
        evidence = " | ".join(parts) + (f" || {snippet}" if snippet else "")
        return evidence[:EVIDENCE_MAX_CHARS]


class LLMClassifier(Classifier):
    """SCOPED — NOT for this phase. Sends record text to an LLM with the
    taxonomy in the prompt; returns structured relevance + rationale.

    Before building: PI decision + data-governance review (sending procurement
    text to an external API), pinned model id + temperature 0, and cached
    responses for reproducibility. Recommended use is second-pass adjudication
    of the uncertain band only, not every record (cost). See
    docs/architecture.md §5b.
    """

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "LLM classification is scoped but not approved for this phase. "
            "Requires PI sign-off (approach + governance) before implementation."
        )

    def classify(self, fields: dict) -> Classification:  # pragma: no cover
        raise NotImplementedError
