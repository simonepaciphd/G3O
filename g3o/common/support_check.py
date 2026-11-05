"""v2.7 support check, downgrade and deterministic extraction (T-024).

A library the passes call between rounds (RC-D-002 O4); it makes no provider
call and writes nothing. Inputs are the jev answers with their chosen-answer
probabilities, the quotes copied by the quote step (pass 1, T-022; pass 2,
T-032; joined on ``task_id`` by the caller or the two join helpers below) and
the stored page text.

Rules applied, each as SPEC v001.20 / codebook r12 states it:

- **Quote presence (R-042; RC-D-017 1a, 2a).** A quote matches when rapidfuzz
  ``token_set_ratio`` of the normalized quote against the normalized source
  text is at least ``MATCH_THRESHOLD`` (93, one pooled threshold), rapidfuzz
  pinned ``==3.14.3`` (DEC-007 a). Normalization is the T-003 calibration's:
  NFKC, casefold, punctuation dropped, word runs joined by one space. A quote
  below the threshold counts as no supporting text. Presence only, not
  entailment.
- **80% word rule (R-042; RC-D-014 S1, RC-D-016).** The share of the quote's
  original-language words present in the source text is computed for every
  check and recorded with the 0.80 cutoff (``QuoteMatch.rule_80``). It is the
  rule the matcher was calibrated to (labels jev 4+ OR the rule); the decision
  is the matcher's (RC-D-017 "the support check uses rapidfuzz"). See
  ``MATCH_DECISION``.
- **Source surface (R-044, r2#48, RC-D-017 P3).** A quote is matched in the
  part that produced the code; for ``main_plus_chrome`` items it may instead
  come from the page's chrome text (``<page>#chrome``). A quote from any other
  part counts as no supporting text.
- **Length (R-043; RC-D-017 3, "2 whole").** Supporting text over
  ``QUOTE_MAX_CHARS`` (200) characters is kept whole and flagged
  ``quote_over_cap``; code never truncates it. :func:`display_cap` gives the
  website's 200-character prefix; the API keeps the full text.
- **Support status (R-041; codebook ``vocabularies.support_status``).**
  ``set_by_rule`` for any value a rule fixed (``not_asked``, ``_NA_``, the
  ``no`` on non-GenAI pages ...), with the rule name in ``support_rule_name``;
  ``not_required`` for ``not_documented``, ``unknown``, ``no`` and the negative
  page verdicts when they pass the 0.8 bar; ``supported`` for a positive or
  substantive value whose checks pass; otherwise one of the three
  ``downgraded_*`` codes.
- **Check order (``core.support_status_second_reason``, F10, FX05).** Quote
  first (no matching quote -> ``downgraded_no_quote``; a matching quote the
  X35 entailment check rejects -> ``downgraded_quote_not_stating_value``),
  then the 0.8 bar (``downgraded_low_confidence``). The main status takes the
  first failure, the second reason the other; with this order only
  ``downgraded_low_confidence`` can be a second reason.
- **0.8 bar (R-081, r2#26).** The chosen answer's probability, for every
  classifier code including ``no`` and negatives. A missing probability is
  retained as missing, the code is downgraded and the cause recorded
  (``probability_unavailable``; RC-D-010). X35 uses the same bar on its own
  answer: ``false``, below 0.8, or no probability fails the quote check.
- **Downgrade target (R-041, X14; item ``downgrade_target``).** ``unknown``
  replaces the value; ``tag_only`` (the page verdict) keeps it and only the
  status says downgraded (r2#40).
- **Contact e-mails (R-023 CX-53, R-058, RC-D-011).** When
  ``content_contact`` = yes: the signed regex over the stored main text,
  header and footer text and the page's e-mail links; whole addresses
  lowercased and de-duplicated per page (``storage.normalize_contact_emails``).
  Stored in full, published as domain + count (``storage.email_domain_counts``).
- **Year candidates (codebook r12 year rules 1-2; T-064).** Candidates from
  the activity span and its context via :mod:`g3o.extract.years`; the
  classifier chooses (T-023).

Gated pieces are stubs that raise :class:`SupportGateError` naming the gate:
the X35 entailment call itself, the year context window, and the value of
``content_contact_emails`` when the gate is open but no address is found.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from g3o.codebook.loader import Codebook, load_codebook

#: Codebook r12, PI-signed 2026-11-05 (planning/t010/signoff-record.md). Another file is refused.
SIGNED_CODEBOOK_SHA256 = "93d77b1b2daf5cc7d287b5a3b6136a1a9fd13dacc9b6f0ea91133fd22df3e712"

PINNED_RAPIDFUZZ = "3.14.3"  # DEC-007 a; RC-D-017 1a. Change only with a re-calibration (T-003).
MATCH_METRIC = "token_set_ratio_norm"  # RC-D-017 1a
MATCH_THRESHOLD = 93  # RC-D-017 2a: one pooled threshold, accept when score >= 93
WORD_RULE_CUTOFF = 0.80  # RC-D-014 S1; RC-D-016 (Latin, CJK; Thai default)
#: Which rule decides a match. RC-D-017 1a: "the support check uses rapidfuzz token_set_ratio".
#: The 80% word rule is recorded beside it (QuoteMatch.rule_80), not combined with it.
MATCH_DECISION = "matcher"

QUOTE_MAX_CHARS = 200  # RC-D-017 3: extraction-prompt cap and website display cap
OVER_CAP_FLAG = "quote_over_cap"  # RC-D-017 "2 whole"
PROBABILITY_UNAVAILABLE = "probability_unavailable"  # RC-D-010
ENTAILMENT_PROBABILITY_UNAVAILABLE = "entailment_probability_unavailable"  # RC-D-010, X35 answer

SUPPORTED = "supported"
NO_QUOTE = "downgraded_no_quote"
LOW_CONFIDENCE = "downgraded_low_confidence"
NOT_STATING = "downgraded_quote_not_stating_value"
SET_BY_RULE = "set_by_rule"
NOT_REQUIRED = "not_required"

PAGE_VERDICT = "core.page_verdict"
CONTACT_ITEM = "core.content_contact"
CONTACT_EMAILS_ITEM = "core.content_contact_emails"

#: The regex the signed CX-53 rule names (pilot ``contact.py``, ``EMAIL_RE``), copied verbatim.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


class SupportGateError(RuntimeError):
    """A piece of T-024 that waits on a named gate (PI ruling or another card)."""


# ---------------------------------------------------------------------------
# Normalization and matching (R-042)
# ---------------------------------------------------------------------------


def _mark_class() -> str:
    """Regex class body for every combining mark (Mn, Mc), as in the T-003 word rule."""
    ranges, start, prev = [], None, None
    for cp in range(sys.maxunicode + 1):
        if unicodedata.category(chr(cp)) in ("Mn", "Mc"):
            if start is None:
                start = cp
            elif cp != prev + 1:
                ranges.append((start, prev))
                start = cp
            prev = cp
    ranges.append((start, prev))
    return "".join(f"\\U{a:08x}-\\U{b:08x}" if a != b else f"\\U{a:08x}" for a, b in ranges)


_MARKS = _mark_class()
# A word starts with a letter or digit, then letters, digits or combining marks; apostrophe-joined parts allowed.
_WORD = re.compile(rf"[^\W_](?:[^\W_]|[{_MARKS}])*(?:['’][^\W_](?:[^\W_]|[{_MARKS}])*)*")


def word_tokens(text: str) -> list[str]:
    """NFKC + casefold, then word runs (the T-003 calibration tokenizer; words in every script)."""
    return _WORD.findall(unicodedata.normalize("NFKC", text).casefold())


def norm_text(text: str) -> str:
    """The matcher's input: word runs joined by one space (punctuation dropped)."""
    return " ".join(word_tokens(text))


def word_presence(quote: str, source: str) -> float | None:
    """Share of the quote's words (with repetition) present in the source. None if no words."""
    q = word_tokens(quote)
    if not q:
        return None
    page = set(word_tokens(source))
    return sum(t in page for t in q) / len(q)


@lru_cache(maxsize=1)
def _token_set_ratio():
    import rapidfuzz
    from rapidfuzz import fuzz

    if rapidfuzz.__version__ != PINNED_RAPIDFUZZ:
        raise RuntimeError(
            f"rapidfuzz {rapidfuzz.__version__} is installed; the R-042 threshold is calibrated on "
            f"{PINNED_RAPIDFUZZ} (DEC-007 a)")
    return fuzz.token_set_ratio


@dataclass(frozen=True)
class QuoteMatch:
    score: float  # token_set_ratio of the normalized texts, 0-100
    threshold: int
    matched: bool  # the R-042 decision (MATCH_DECISION)
    presence_word: float | None  # 80% rule input; None when the quote has no words
    rule_80: bool | None
    over_cap: bool


def match_quote(quote: str, source: str) -> QuoteMatch:
    """R-042 presence check of one quote against the text it came from."""
    q = norm_text(quote)
    presence = word_presence(quote, source)
    score = round(float(_token_set_ratio()(q, norm_text(source))), 2) if q else 0.0
    return QuoteMatch(
        score=score, threshold=MATCH_THRESHOLD, matched=bool(q) and score >= MATCH_THRESHOLD,
        presence_word=None if presence is None else round(presence, 4),
        rule_80=None if presence is None else presence >= WORD_RULE_CUTOFF,
        over_cap=len(quote) > QUOTE_MAX_CHARS,
    )


def display_cap(text: str) -> tuple[str, bool]:
    """Website display (R-043): the first 200 characters and whether a marker is needed."""
    return (text, False) if len(text) <= QUOTE_MAX_CHARS else (text[:QUOTE_MAX_CHARS], True)


# ---------------------------------------------------------------------------
# Codebook-derived rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SupportRules:
    items: dict[str, dict[str, Any]]
    not_required_values: frozenset[str]  # not_documented, unknown, no
    rule_values: frozenset[str]  # not_asked, _NA_ (always set_by_rule)
    negative_verdicts: frozenset[str]
    temporary_answer: str  # R-044; never reaches the support check
    entailment_labels: dict[str, dict[str, Any]]  # X35 label map (generated jev_questions.json)
    entailment_activity_form: str
    entailment_page_form: str
    entailment_bar: float

    def bar(self, item_id: str) -> float | None:
        th = self.items[item_id].get("threshold")
        return float(th["bar"]) if isinstance(th, dict) else None


def rules_from_codebook(cb: Codebook) -> SupportRules:
    if cb.sha256 != SIGNED_CODEBOOK_SHA256:
        raise ValueError(f"codebook sha256 {cb.sha256} is not the signed r12 release")
    from g3o.codebook.generators import gen_jev_questions

    status = cb.vocabularies["support_status"]
    by_answer = {k: v for k, v in status["status_by_answer"].items() if re.fullmatch(r"[A-Za-z_]+", k)}
    gen = json.loads(gen_jev_questions(cb).content)
    ent = next(q for q in gen["questions"] if q["item_id"] == "core.support_entailment")
    return SupportRules(
        items=cb.build_items(),
        not_required_values=frozenset(k for k, v in by_answer.items() if v == NOT_REQUIRED),
        rule_values=frozenset(k for k, v in by_answer.items() if v == SET_BY_RULE),
        negative_verdicts=frozenset(status["negative_page_verdicts"]["values"]),
        temporary_answer=cb.data["shared"]["part_prompt"]["temporary_answer"]["label"]["text"],
        entailment_labels=ent["labels"],
        entailment_activity_form=ent["instructions"],
        entailment_page_form=ent["instructions_page"],
        entailment_bar=float(ent["threshold"]["bar"]),
    )


@lru_cache(maxsize=1)
def default_rules() -> SupportRules:
    return rules_from_codebook(load_codebook())


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PageSources:
    """The stored texts a quote may come from: each part's main text, plus chrome (T-014)."""

    page_id: str
    parts: Mapping[str, str]  # chunk_id -> that part's main text
    chrome_text: str | None = None  # None = not measured

    @property
    def chrome_id(self) -> str:
        return f"{self.page_id}#chrome"

    @classmethod
    def from_page(cls, page: Any) -> PageSources:
        """From a :class:`g3o.extract.request_v27.Pass1Page` (or anything with the same fields)."""
        return cls(page.page_id, {c.chunk_id: c.text for c in page.chunks}, page.chrome_text)


@dataclass(frozen=True)
class Entailment:
    """The X35 answer for one (code, quote): ``"true"`` / ``"false"`` and its probability."""

    value: str
    probability: float | None


@dataclass(frozen=True)
class CodeEvidence:
    """One selected value of one item (one per value of a multi-value item; one per part of a parts item)."""

    item_id: str
    value: str
    chunk_id: str  # the part that produced the value (R-044)
    part: str | None = None  # parts item (e.g. observed_actor_relationship)
    probability: float | None = None  # chosen-answer probability; None = not returned (RC-D-010)
    quote: str | None = None  # verbatim, from the quote step
    quote_chunk_id: str | None = None  # the part (or `<page>#chrome`) the quote was copied from
    rule_name: str | None = None  # set when a rule fixed the value (status set_by_rule)
    entailment: Entailment | None = None  # X35 answer; required for a matched quote on a labelled item
    activity_id: str | None = None


@dataclass(frozen=True)
class SupportResult:
    item_id: str
    part: str | None
    activity_id: str | None
    chunk_id: str
    original_value: str
    value: str  # after the downgrade; a page verdict is never rewritten
    support_status: str
    support_status_second_reason: str | None  # empty unless two reasons hold
    support_rule_name: str | None  # filled only for set_by_rule
    supporting_text: str | None  # verbatim and whole
    quote_chunk_id: str | None
    match: QuoteMatch | None
    chosen_answer_probability: float | None
    entailment: Entailment | None
    flags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def downgraded(self) -> bool:
        return self.support_status.startswith("downgraded_")


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def _quote_source(ev: CodeEvidence, item: dict[str, Any], sources: PageSources) -> str | None:
    """The text the quote must match, or None when it came from a part that may not supply it."""
    qid = ev.quote_chunk_id or ev.chunk_id
    if qid == ev.chunk_id:
        if qid not in sources.parts:
            raise ValueError(f"{ev.item_id}: unknown part {qid!r} on page {sources.page_id}")
        return sources.parts[qid]
    if qid == sources.chrome_id and item.get("input_text") == "main_plus_chrome" and sources.chrome_text:
        return sources.chrome_text
    return None


def _needs_quote(ev: CodeEvidence, item: dict[str, Any], rules: SupportRules) -> bool:
    if item.get("support_required") is not True or ev.value in rules.not_required_values:
        return False
    return not (ev.item_id == PAGE_VERDICT and ev.value in rules.negative_verdicts)


def _entailment_fails(ent: Entailment, bar: float, flags: list[str]) -> bool:
    if ent.value not in ("true", "false"):
        raise ValueError(f"X35 answer must be 'true' or 'false', got {ent.value!r}")
    if ent.probability is None:
        flags.append(ENTAILMENT_PROBABILITY_UNAVAILABLE)
        return True
    return ent.value == "false" or ent.probability < bar


def check_code(ev: CodeEvidence, sources: PageSources, rules: SupportRules | None = None) -> SupportResult:
    """Support status and downgrade for one selected value (R-041, R-042, R-081, X35)."""
    rules = rules or default_rules()
    item = rules.items.get(ev.item_id)
    if item is None:
        raise ValueError(f"{ev.item_id} is not an item of the signed codebook build")
    if ev.value == rules.temporary_answer:
        raise ValueError("the temporary part answer is not checked; it never votes in combining (R-044)")
    flags: list[str] = []
    quote = ev.quote if ev.quote is not None and ev.quote.strip() else None
    if quote is not None and len(quote) > QUOTE_MAX_CHARS:
        flags.append(OVER_CAP_FLAG)

    def result(status: str, value: str, second: str | None = None, match: QuoteMatch | None = None,
               rule_name: str | None = None) -> SupportResult:
        return SupportResult(
            item_id=ev.item_id, part=ev.part, activity_id=ev.activity_id, chunk_id=ev.chunk_id,
            original_value=ev.value, value=value, support_status=status,
            support_status_second_reason=second, support_rule_name=rule_name,
            supporting_text=quote, quote_chunk_id=(ev.quote_chunk_id or ev.chunk_id) if quote else None,
            match=match, chosen_answer_probability=ev.probability, entailment=ev.entailment,
            flags=tuple(dict.fromkeys(flags)),
        )

    if ev.rule_name is not None:
        if not ev.rule_name.strip():
            raise ValueError("support_rule_name must name the rule")
        return result(SET_BY_RULE, ev.value, rule_name=ev.rule_name)
    if ev.value in rules.rule_values:
        raise ValueError(f"{ev.item_id}: {ev.value!r} is set by a rule; the rule name is required")

    failures: list[str] = []
    match: QuoteMatch | None = None
    if _needs_quote(ev, item, rules):
        src = _quote_source(ev, item, sources) if quote is not None else None
        if quote is None or src is None:
            failures.append(NO_QUOTE)
        else:
            match = match_quote(quote, src)
            if not match.matched:
                failures.append(NO_QUOTE)
            elif ev.item_id in rules.entailment_labels:
                if ev.entailment is None:
                    raise ValueError(f"{ev.item_id}: matched quote has no X35 entailment answer")
                if _entailment_fails(ev.entailment, rules.entailment_bar, flags):
                    failures.append(NOT_STATING)

    bar = rules.bar(ev.item_id) if item.get("coder") == "classifier" else None
    if bar is not None:
        if ev.probability is None:
            flags.append(PROBABILITY_UNAVAILABLE)
            failures.append(LOW_CONFIDENCE)
        elif ev.probability < bar:
            failures.append(LOW_CONFIDENCE)

    if not failures:
        return result(SUPPORTED if match is not None else NOT_REQUIRED, ev.value, match=match)
    target = item.get("downgrade_target")
    if target == "unknown":
        value = "unknown"
    elif target == "tag_only":
        value = ev.value
    else:
        raise ValueError(f"{ev.item_id}: downgrade_target {target!r} has no downgrade (report to integrator)")
    return result(failures[0], value, failures[1] if len(failures) > 1 else None, match)


def check_codes(evidence: Iterable[CodeEvidence], sources: PageSources,
                rules: SupportRules | None = None) -> list[SupportResult]:
    rules = rules or default_rules()
    return [check_code(ev, sources, rules) for ev in evidence]


# ---------------------------------------------------------------------------
# Joins from the two quote passes (task_id -> code)
# ---------------------------------------------------------------------------


def pass1_quotes(plan: Any, extraction: Any) -> dict[tuple[str, str], Any]:
    """Pass-1 quotes keyed (item_id, producing chunk_id), joined on ``task_id`` (T-022).

    One quote task covers an item in one part, so every value of that item from that part shares it.
    The result's ``chunk_id`` is the part (or chrome) the quote was copied from.
    """
    tasks = {t.task_id: t for t in plan.quote_tasks}
    out = {}
    for q in extraction.quotes:
        t = tasks[q.task_id]
        out[(t.item_id, t.chunk_id)] = q
    return out


def pass2_quotes(plan: Any, support: Any) -> dict[tuple[str, str, str, str], Any]:
    """Pass-2 quotes keyed (activity_id, item_id, chunk_id, answer), joined on ``task_id`` (T-032)."""
    tasks = {t.task_id: t for t in plan.quote_tasks}
    out = {}
    for q in support.quotes:
        t = tasks[q.task_id]
        out[(t.activity_id, t.item_id, t.chunk_id, t.answer)] = q
    return out


# ---------------------------------------------------------------------------
# X35 entailment question (labels only; the call is gated)
# ---------------------------------------------------------------------------


def entailment_question(item_id: str, value: str, *, part: str | None = None,
                        activity_name: str | None = None, rules: SupportRules | None = None) -> str:
    """The signed X35 question for one (item, value), filled from the generated label map.

    Page-form items use ``instruction_page``; others the activity form, naming the activity.
    Year items take the year as written. A missing label is an interface defect: raised, never
    filled with a raw code (T-024 label interface).
    """
    rules = rules or default_rules()
    lab = rules.entailment_labels.get(item_id)
    if lab is None:
        raise ValueError(f"{item_id} has no X35 label (free text or not a classifier item)")
    if "parts" in lab:
        if part is None or part not in lab["parts"]:
            raise ValueError(f"{item_id}: select the part explicitly ({sorted(lab['parts'])})")
        field_label, values = lab["parts"][part]["field"], lab["parts"][part]["values"]
    else:
        field_label, values = lab["field"], lab["values"]
    if lab.get("value_label") == "year":
        if not re.fullmatch(r"\d{4}", value):
            raise ValueError(f"{item_id}: year value must be the year as written")
        value_label = value
    elif value in values:
        value_label = values[value]["text"]
    else:
        raise ValueError(f"{item_id}: no X35 value label for {value!r}")
    if lab["frame"] == "page":
        return rules.entailment_page_form.replace("<field label>", field_label).replace(
            "<value label>", value_label)
    if not activity_name:
        raise ValueError(f"{item_id}: the activity form needs the activity name")
    return (rules.entailment_activity_form.replace("<field label>", field_label)
            .replace("<activity name>", activity_name).replace("<value label>", value_label))


def run_entailment(*_: Any, **__: Any) -> Entailment:
    # TODO(gate: X35 call wiring): the jev call needs (1) the "short window" around the quote that the
    # signed state "quote (plus a short window)" names but does not size, and (2) the jev client
    # binding of T-021/T-023 (runtime instrument T-030/T-035). Until both, callers pass Entailment in.
    raise SupportGateError("X35 entailment call not wired: window size unpinned; jev binding T-030/T-035")


# ---------------------------------------------------------------------------
# Deterministic extraction
# ---------------------------------------------------------------------------


def _mailto_addresses(links: Iterable[str]) -> list[str]:
    from urllib.parse import unquote

    out: list[str] = []
    for href in links:
        if href[:7].lower() != "mailto:":
            continue
        out.extend(EMAIL_RE.findall(unquote(href[7:].split("?", 1)[0])))
    return out


def extract_contact_emails(content_contact: str, main_text: str, *, header_text: str | None = None,
                           footer_text: str | None = None, email_links: Sequence[str] = ()) -> list[str] | str:
    """``content_contact_emails`` (CX-53): full normalized addresses in first-seen order, internal only.

    Gate closed (``content_contact`` is not ``yes``) -> ``not_asked`` (R-045; the caller records it as
    set_by_rule). Search order: main text, header, footer, e-mail links. Header/footer texts are T-014's
    (not yet verified at runtime); pass None when not measured.
    """
    from g3o.common.storage import normalize_contact_emails

    if content_contact != "yes":
        return "not_asked"
    found: list[str] = []
    for text in (main_text, header_text, footer_text):
        if text:
            found.extend(EMAIL_RE.findall(text))
    found.extend(_mailto_addresses(email_links))
    if not found:
        # TODO(gate: no-evidence value): the signed CX-53 rule does not say which value the item takes when
        # content_contact = yes and no address is found (PLAN T-024 "Report when: a field has no defined
        # no-evidence value"; stop boundary: this field). Reported to the integrator.
        raise SupportGateError("content_contact_emails: no defined value for gate open, no address found")
    return normalize_contact_emails(found)


def activity_year_candidates(page_text: str, start: int, end: int, *, context_chars: int | None = None) -> list[Any]:
    """Year candidates (T-064) from the activity span and its context (codebook r12 year rule 1).

    Returns :class:`g3o.extract.years.YearCandidate` values whose offsets are page offsets.
    """
    if context_chars is None:
        # TODO(gate: year context): r12 rule 1 says "the activity span and its context" without sizing the
        # context; T-011's DYNAMIC_YEAR_CHOICES (W-05, pending PI wording approval) points at the same rule.
        raise SupportGateError("year candidate context window is not pinned (r12 rule 1, W-05)")
    from g3o.extract.years import YearCandidate, YearSource, extract_year_candidates

    if not (0 <= start < end <= len(page_text)) or context_chars < 0:
        raise ValueError("span must lie on the page and context must be non-negative")
    lo, hi = max(0, start - context_chars), min(len(page_text), end + context_chars)
    return [YearCandidate(c.year, tuple(YearSource(s.start + lo, s.end + lo, s.text, s.form) for s in c.sources))
            for c in extract_year_candidates(page_text[lo:hi])]


__all__ = [
    "CodeEvidence",
    "Entailment",
    "EMAIL_RE",
    "LOW_CONFIDENCE",
    "MATCH_DECISION",
    "MATCH_THRESHOLD",
    "NOT_REQUIRED",
    "NOT_STATING",
    "NO_QUOTE",
    "OVER_CAP_FLAG",
    "PINNED_RAPIDFUZZ",
    "PageSources",
    "QUOTE_MAX_CHARS",
    "QuoteMatch",
    "SET_BY_RULE",
    "SUPPORTED",
    "SupportGateError",
    "SupportResult",
    "SupportRules",
    "activity_year_candidates",
    "check_code",
    "check_codes",
    "default_rules",
    "display_cap",
    "entailment_question",
    "extract_contact_emails",
    "match_quote",
    "norm_text",
    "pass1_quotes",
    "pass2_quotes",
    "rules_from_codebook",
    "run_entailment",
    "word_presence",
    "word_tokens",
]
