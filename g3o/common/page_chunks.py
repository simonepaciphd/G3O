"""Token-based page chunking and long-page answer combination (T-020).

Spec refs: R-044, R-045 (RC-D-003), C-004, A-021; DEC-008 c.

Two halves, both deterministic and free of any jev call (callers inject the
request function):

**Chunking.** jev's state limit is 32k tokens per request (C-004), so a long
page is split into parts by *estimated tokens*, not bytes (DEC-008 c). The
estimator is additive per character: each character is assigned a script
bucket (Latin / CJK / Thai, the three scripts T-002 calibrates; everything
else falls back to a configurable bucket) and contributes
``(1 + margin) / chars_per_token`` tokens. A page is split at the coarsest
boundary that works (paragraph, line, sentence end, whitespace, character),
and parts are packed greedily in page order. Concatenating a page's parts
gives back the page text exactly; every part carries a stable ``chunk_id`` and
its character offsets. If jev still rejects a part as over the limit, the
part is halved and retried (halve-and-retry fallback, DEC-008 c), up to
``max_depth`` levels (3, as in RS-004 ``byte_chunks`` and RS-014
``MAX_SPLIT_DEPTH``). :func:`split_pool` is the same packing for pooled
Stage 6 evidence (C-004, r2#6) for T-026: entries ordered by source date,
then page order (all-06 a), with optional entries pinned into every part.

**Combination.** Each part's answer is checked before combining
(:func:`check_part_answer`; quote, then the 0.8 certainty bar, all-03 a /
R-041 / R-081); a failed answer enters as the item's downgrade target
(``unknown``), except page verdicts, which keep their value and the failure
note. The temporary part answer "not covered by this part" never votes; if
every part gives it, the answer is ``not_documented`` (all-03 a, PI comment).
Parts are then combined by the item's codebook rule type (RC-D-002 row 41,
R-044): ``first_section``, ``any_yes``, ``priority_order`` (incl. the two-tier
S3 a page-verdict order, page-02 b), ``earliest_year``, ``combined_list``
(with the optional mapping step, activity-22 b), ``highest_probability``
and ``same_part_as``; ``priority_order`` may carry the set mapping of
activity-11 a. In every order, real answers rank first, then
``not_documented``, then ``unknown`` (all-04 b). Among parts giving the
winning answer, the quote and certainty come from the most-sure part; ties go
to the earliest (all-05 a).

Rule types arrive as configuration (:class:`ItemRule`). The T-013 codebook
loader is not merged yet; :func:`rule_from_codebook_item` builds an
:class:`ItemRule` from one raw item mapping of ``codebook/codebook.yaml`` so
the loader can feed it directly. A case the configuration cannot express
raises :class:`UnresolvedCombineCase`; :func:`combine_page` stops that field
and carries on with the rest (card T-020, spec-change reporting).

Callers own: building the part prompts (T-013 / T-021), applicability
("not asked" is applied after the gating items are combined, so it never
reaches this module), grouping activity answers by linked passage
(convention ``activity_level``), and the entailment check behind
``downgraded_quote_not_stating_value`` (T-022), which arrives as a flag.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Generic, TypeVar

__all__ = [
    "ANY_YES",
    "COMBINED_LIST",
    "DEFAULT_MAX_SPLIT_DEPTH",
    "EARLIEST_YEAR",
    "FIRST_SECTION",
    "HIGHEST_PROBABILITY",
    "JEV_STATE_TOKEN_LIMIT",
    "NOT_COVERED",
    "PLACEHOLDER_CHARS_PER_TOKEN",
    "PLACEHOLDER_SAFETY_MARGIN",
    "PRIORITY_ORDER",
    "S3A_VERDICT_ORDER",
    "SAME_PART_AS",
    "CheckedAnswer",
    "Chunk",
    "CombinedAnswer",
    "HalvingOutcome",
    "ItemRule",
    "PageCombination",
    "PartAnswer",
    "PoolEntry",
    "PoolPart",
    "SpecConflict",
    "TokenEstimator",
    "UnresolvedCombineCase",
    "check_part_answer",
    "chunk_page",
    "combine_item",
    "combine_page",
    "halve_chunk",
    "halve_pool_part",
    "normalise_order",
    "quote_in_part",
    "rule_from_codebook_item",
    "run_with_halving",
    "script_of",
    "split_pool",
]

# ---------------------------------------------------------------------------
# Limits and estimator constants
# ---------------------------------------------------------------------------

#: jev state limit per request (C-004: "32k tokens"). Whether jev counts 32k
#: as 32,000 or 32,768 is not stated in SPEC; 32,000 is the lower reading.
#: Configurable per call.
JEV_STATE_TOKEN_LIMIT = 32_000

#: PLACEHOLDER — NOT CALIBRATED. Characters per token, per script bucket.
#: T-002 (``SPIKE-T002.md``) measures the real constants against jev's token
#: counts (DEC-008 c); these values are stand-ins so the build and its tests
#: can run. The card's done condition needs the T-002 values in place.
PLACEHOLDER_CHARS_PER_TOKEN: Mapping[str, float] = {
    "latin": 4.0,  # PLACEHOLDER (T-002)
    "cjk": 1.0,  # PLACEHOLDER (T-002)
    "thai": 2.0,  # PLACEHOLDER (T-002)
}

#: PLACEHOLDER — DP-007 is open: the safety margin below the 32k limit is not
#: chosen here. Card default (not applied): a margin equal to the largest
#: estimator error T-002 observes for the page's script. Expressed as a
#: relative inflation of the estimate (0.10 = +10 %). 0.0 means "no margin
#: yet", not a decision.
PLACEHOLDER_SAFETY_MARGIN: Mapping[str, float] = {
    "latin": 0.0,  # PLACEHOLDER (DP-007 / T-002)
    "cjk": 0.0,  # PLACEHOLDER (DP-007 / T-002)
    "thai": 0.0,  # PLACEHOLDER (DP-007 / T-002)
}

#: Halve-and-retry depth (RS-004 ``byte_chunks`` ×3; RS-014 ``MAX_SPLIT_DEPTH=3``).
DEFAULT_MAX_SPLIT_DEPTH = 3

# ---------------------------------------------------------------------------
# Tokens and vocabularies
# ---------------------------------------------------------------------------

NOT_ASKED = "not_asked"
NOT_DOCUMENTED = "not_documented"
UNKNOWN = "unknown"
NA = "_NA_"
MISSING_TOKENS = frozenset({NOT_ASKED, NOT_DOCUMENTED, UNKNOWN, NA})

#: The temporary part answer (R-044, all-03 a PI comment; codebook
#: ``combining_conventions.not_covered_by_this_part.temporary_value``). Not a
#: value of any item and not a reserved token; never votes; never published.
#: The jev choice spelling is T-013's; pass ``not_covered=`` if it differs.
NOT_COVERED = "not covered by this part"

#: Missing-answer rank inside every order (all-04 b): real answers, then these.
MISSING_RANK: tuple[str, ...] = (NOT_DOCUMENTED, UNKNOWN)

#: The S3 a verdict order (R-044; codebook ``core.page_verdict.long_page_rule``).
#: Differs from the item's value-list order (ambiguous_attribution comes
#: before ambiguous_genai here).
S3A_VERDICT_ORDER: tuple[str, ...] = (
    "confirms_activity",
    "ambiguous_attribution",
    "ambiguous_genai",
    "other_body",
    "event_only",
    "background_only",
    "confirms_absence",
    "no_genai",
    "not_assessable",
)

# Support-status values (R-041).
SUPPORTED = "supported"
DOWNGRADED_NO_QUOTE = "downgraded_no_quote"
DOWNGRADED_LOW_CONFIDENCE = "downgraded_low_confidence"
DOWNGRADED_QUOTE_NOT_STATING_VALUE = "downgraded_quote_not_stating_value"
NOT_REQUIRED = "not_required"

#: Chosen-answer probability bar (R-081, r2#26).
CERTAINTY_BAR = 0.8

# Rule types (R-044 rule-type list; codebook ``long_page_rule``).
FIRST_SECTION = "first_section"
ANY_YES = "any_yes"
PRIORITY_ORDER = "priority_order"
EARLIEST_YEAR = "earliest_year"
COMBINED_LIST = "combined_list"
HIGHEST_PROBABILITY = "highest_probability"
SAME_PART_AS = "same_part_as"
RULE_TYPES = frozenset(
    {
        FIRST_SECTION,
        ANY_YES,
        PRIORITY_ORDER,
        EARLIEST_YEAR,
        COMBINED_LIST,
        HIGHEST_PROBABILITY,
        SAME_PART_AS,
    }
)

DOWNGRADE_TAG_ONLY = "tag_only"


class UnresolvedCombineCase(Exception):
    """The configured rule cannot combine this field; stop the field, report it."""

    def __init__(self, item_id: str, reason: str) -> None:
        super().__init__(f"{item_id}: {reason}")
        self.item_id = item_id
        self.reason = reason


class SpecConflict(UnresolvedCombineCase):
    """The configuration contradicts a SPEC rule (e.g. the all-04 b rank)."""


# ---------------------------------------------------------------------------
# Token estimator
# ---------------------------------------------------------------------------

_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x1100, 0x11FF),  # Hangul Jamo
    (0x2E80, 0x2FDF),  # CJK radicals
    (0x3000, 0x303F),  # CJK symbols and punctuation
    (0x3040, 0x30FF),  # Hiragana, Katakana
    (0x3100, 0x31FF),  # Bopomofo, Hangul compat., Kanbun, Katakana ext.
    (0x3200, 0x33FF),  # enclosed CJK, compatibility
    (0x3400, 0x4DBF),  # CJK ext. A
    (0x4E00, 0x9FFF),  # CJK unified
    (0xA960, 0xA97F),  # Hangul Jamo ext. A
    (0xAC00, 0xD7FF),  # Hangul syllables, Jamo ext. B
    (0xF900, 0xFAFF),  # CJK compatibility ideographs
    (0xFE30, 0xFE4F),  # CJK compatibility forms
    (0xFF00, 0xFFEF),  # half/full-width forms
    (0x20000, 0x3FFFF),  # CJK ext. B onwards
)
_THAI_RANGE = (0x0E00, 0x0E7F)


def script_of(ch: str) -> str:
    """Script bucket of one character: ``"cjk"``, ``"thai"`` or ``"latin"``.

    ``"latin"`` is the catch-all (Latin, Cyrillic, Arabic, digits,
    punctuation, whitespace ...); T-002 calibrates only Latin / CJK / Thai.
    """
    cp = ord(ch)
    if _THAI_RANGE[0] <= cp <= _THAI_RANGE[1]:
        return "thai"
    for lo, hi in _CJK_RANGES:
        if lo <= cp <= hi:
            return "cjk"
    return "latin"


@dataclass(frozen=True)
class TokenEstimator:
    """Additive per-character token estimate, one constant per script.

    ``chars_per_token`` and ``safety_margin`` default to the PLACEHOLDER
    tables; ``placeholder`` stays ``True`` until real T-002 / DP-007 values
    are passed, and :meth:`assert_calibrated` refuses a placeholder estimator
    (production entry points should call it).
    """

    chars_per_token: Mapping[str, float] = field(
        default_factory=lambda: dict(PLACEHOLDER_CHARS_PER_TOKEN)
    )
    safety_margin: Mapping[str, float] = field(
        default_factory=lambda: dict(PLACEHOLDER_SAFETY_MARGIN)
    )
    placeholder: bool = True

    def __post_init__(self) -> None:
        for script in ("latin", "cjk", "thai"):
            cpt = self.chars_per_token.get(script)
            if cpt is None or cpt <= 0:
                raise ValueError(f"chars_per_token[{script!r}] must be > 0, got {cpt!r}")
            m = self.safety_margin.get(script, 0.0)
            if m < 0:
                raise ValueError(f"safety_margin[{script!r}] must be >= 0, got {m!r}")

    def assert_calibrated(self) -> None:
        if self.placeholder:
            raise RuntimeError(
                "TokenEstimator uses PLACEHOLDER constants; fill them from T-002 "
                "(SPIKE-T002.md) and DP-007 before a production run"
            )

    def _weight(self, script: str) -> float:
        return (1.0 + self.safety_margin.get(script, 0.0)) / self.chars_per_token[script]

    def raw(self, text: str) -> float:
        """Unrounded estimate (additive: ``raw(a + b) == raw(a) + raw(b)``)."""
        counts = {"latin": 0, "cjk": 0, "thai": 0}
        for ch in text:
            counts[script_of(ch)] += 1
        return sum(n * self._weight(s) for s, n in counts.items() if n)

    def tokens(self, text: str) -> int:
        return math.ceil(self.raw(text) - 1e-9)


# ---------------------------------------------------------------------------
# Page chunking
# ---------------------------------------------------------------------------

# Boundaries, coarsest first. Each regex matches the separator; the split
# point is the separator's end, so separators stay with the preceding text
# and concatenating the segments gives the input back.
_BOUNDARIES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\n[ \t]*\n\s*"),  # paragraph
    re.compile(r"\n"),  # line
    re.compile(r"(?<=[.!?。！？ฯ])\s+|[。！？](?!\s)"),  # sentence
    re.compile(r"\s+"),  # whitespace
)


@dataclass(frozen=True)
class Chunk:
    """One part of a page. ``text == page_text[start:end]``."""

    chunk_id: str
    page_id: str
    start: int
    end: int
    text: str
    estimated_tokens: int
    depth: int = 0  # halve-and-retry level (0 = from the token packer)


def _cut_points(text: str, level: int) -> list[int]:
    pts = [m.end() for m in _BOUNDARIES[level].finditer(text)]
    return sorted({p for p in pts if 0 < p < len(text)})


def _segments(text: str, level: int) -> list[str]:
    pts = _cut_points(text, level)
    bounds = [0, *pts, len(text)]
    return [text[a:b] for a, b in zip(bounds, bounds[1:], strict=False) if b > a]


def _split_to_fit(
    text: str, fits: Callable[[float], bool], est: TokenEstimator, level: int
) -> list[str]:
    """Split ``text`` into consecutive pieces that each fit, packing greedily."""
    if fits(est.raw(text)):
        return [text]
    if level >= len(_BOUNDARIES):
        # Character level: longest prefix that fits, repeatedly.
        out: list[str] = []
        i = 0
        while i < len(text):
            acc = 0.0
            j = i
            while j < len(text) and fits(acc + est.raw(text[j])):
                acc += est.raw(text[j])
                j += 1
            if j == i:
                raise ValueError("token budget is smaller than a single character")
            out.append(text[i:j])
            i = j
        return out
    segs = _segments(text, level)
    if len(segs) < 2:
        return _split_to_fit(text, fits, est, level + 1)
    pieces: list[str] = []
    for seg in segs:
        if fits(est.raw(seg)):
            pieces.append(seg)
        else:
            pieces.extend(_split_to_fit(seg, fits, est, level + 1))
    packed: list[str] = []
    cur = ""
    cur_raw = 0.0
    for p in pieces:
        p_raw = est.raw(p)
        if cur and fits(cur_raw + p_raw):
            cur += p
            cur_raw += p_raw
        else:
            if cur:
                packed.append(cur)
            cur, cur_raw = p, p_raw
    if cur:
        packed.append(cur)
    return packed


def chunk_page(
    page_id: str,
    text: str,
    *,
    estimator: TokenEstimator | None = None,
    limit_tokens: int = JEV_STATE_TOKEN_LIMIT,
    overhead_tokens: int = 0,
) -> list[Chunk]:
    """Split one page into parts whose estimated tokens fit the state limit.

    ``overhead_tokens`` is the estimated size of everything else in the jev
    state (question set, part-prompt sentence, institution fields); the page
    text gets ``limit_tokens - overhead_tokens``. A page that fits is one
    part. Part ids are ``f"{page_id}#p{n:03d}"`` in page order (1-based).
    Deterministic: same inputs, same parts.
    """
    est = estimator or TokenEstimator()
    budget = limit_tokens - overhead_tokens
    if budget <= 0:
        raise ValueError(
            f"no token budget left for page text (limit {limit_tokens}, overhead {overhead_tokens})"
        )

    def fits(raw: float) -> bool:
        return math.ceil(raw - 1e-9) <= budget

    pieces = _split_to_fit(text, fits, est, 0) if text else [""]
    chunks: list[Chunk] = []
    pos = 0
    for n, piece in enumerate(pieces, start=1):
        chunks.append(
            Chunk(
                chunk_id=f"{page_id}#p{n:03d}",
                page_id=page_id,
                start=pos,
                end=pos + len(piece),
                text=piece,
                estimated_tokens=est.tokens(piece),
            )
        )
        pos += len(piece)
    assert pos == len(text)
    return chunks


def _halve_point(text: str) -> int:
    """Boundary closest to the middle, at the coarsest level that has one."""
    mid = len(text) / 2
    for level in range(len(_BOUNDARIES)):
        pts = _cut_points(text, level)
        if pts:
            return min(pts, key=lambda p: (abs(p - mid), p))
    return len(text) // 2


def halve_chunk(
    chunk: Chunk, *, estimator: TokenEstimator | None = None
) -> tuple[Chunk, Chunk] | None:
    """Split a part in two at the boundary nearest its middle; ``None`` if too short.

    Halves get ids ``f"{chunk_id}.1"`` and ``f"{chunk_id}.2"``.
    """
    if len(chunk.text) < 2:
        return None
    est = estimator or TokenEstimator()
    cut = _halve_point(chunk.text)
    a, b = chunk.text[:cut], chunk.text[cut:]
    return (
        replace(
            chunk,
            chunk_id=f"{chunk.chunk_id}.1",
            end=chunk.start + cut,
            text=a,
            estimated_tokens=est.tokens(a),
            depth=chunk.depth + 1,
        ),
        replace(
            chunk,
            chunk_id=f"{chunk.chunk_id}.2",
            start=chunk.start + cut,
            text=b,
            estimated_tokens=est.tokens(b),
            depth=chunk.depth + 1,
        ),
    )


T = TypeVar("T")
R = TypeVar("R")


@dataclass
class HalvingOutcome(Generic[T, R]):
    """Results in part order (halves replace their parent in place)."""

    results: list[tuple[T, R]]
    n_halvings: int
    max_depth_reached: int


def run_with_halving(
    parts: Sequence[T],
    send: Callable[[T], R],
    *,
    is_over_limit: Callable[[BaseException], bool],
    halve: Callable[[T], tuple[T, T] | None],
    max_depth: int = DEFAULT_MAX_SPLIT_DEPTH,
) -> HalvingOutcome[T, R]:
    """Send each part; on an over-limit rejection halve it and retry (DEC-008 c).

    ``send`` is injected (this module makes no jev call). An exception for
    which ``is_over_limit`` is true is retried on the two halves, up to
    ``max_depth`` halvings deep; any other exception, or an over-limit one
    past the depth or on an unsplittable part, propagates.
    """
    results: list[tuple[T, R]] = []
    stats = {"halvings": 0, "depth": 0}

    def go(part: T, depth: int) -> None:
        stats["depth"] = max(stats["depth"], depth)
        try:
            res = send(part)
        except Exception as exc:
            if not is_over_limit(exc) or depth >= max_depth:
                raise
            halves = halve(part)
            if halves is None:
                raise
            stats["halvings"] += 1
            for h in halves:
                go(h, depth + 1)
            return
        results.append((part, res))

    for p in parts:
        go(p, 0)
    return HalvingOutcome(results, stats["halvings"], stats["depth"])


# ---------------------------------------------------------------------------
# Pooled Stage 6 evidence split (for T-026)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PoolEntry:
    """One piece of pooled evidence (e.g. a quote with its source)."""

    entry_id: str
    text: str
    source_date: str | None  # ISO-8601 (YYYY, YYYY-MM or YYYY-MM-DD)
    page_order: int


@dataclass(frozen=True)
class PoolPart:
    part_id: str
    index: int  # 1-based, the part order for first-section rules
    entries: tuple[PoolEntry, ...]  # pinned entries first, then members in pool order
    estimated_tokens: int
    depth: int = 0


def _pool_order(entries: Iterable[PoolEntry], undated: str) -> list[PoolEntry]:
    entries = list(entries)
    if undated not in ("error", "first", "last"):
        raise ValueError(f"undated must be 'error', 'first' or 'last', got {undated!r}")
    if undated == "error":
        missing = [e.entry_id for e in entries if not e.source_date]
        if missing:
            raise ValueError(
                f"pool entries without source_date: {missing}; all-06 a orders by source "
                "date and does not say where undated evidence goes — pass undated='first'/'last'"
            )
    flag = 1 if undated == "last" else -1

    def key(e: PoolEntry) -> tuple[int, str, int, str]:
        return (
            (0, e.source_date, e.page_order, e.entry_id)
            if e.source_date
            else (flag, "", e.page_order, e.entry_id)
        )

    return sorted(entries, key=key)


def split_pool(
    pool_id: str,
    entries: Iterable[PoolEntry],
    *,
    estimator: TokenEstimator | None = None,
    limit_tokens: int = JEV_STATE_TOKEN_LIMIT,
    overhead_tokens: int = 0,
    pinned: Sequence[PoolEntry] = (),
    undated: str = "error",
) -> list[PoolPart]:
    """Split pooled evidence into parts under the state limit (C-004, r2#6).

    Entries are ordered by source date, then page order (all-06 a), and
    packed greedily; ``pinned`` entries go into every part (e.g. both
    activities of a cross-page pair, ``core.activity_relation_cross_page``
    split rule "every part sees both activities"). An entry is never cut: one
    that cannot fit with the pinned entries raises ``ValueError``.
    """
    est = estimator or TokenEstimator()
    budget = limit_tokens - overhead_tokens
    pinned_raw = sum(est.raw(p.text) for p in pinned)

    def fits(raw: float) -> bool:
        return math.ceil(pinned_raw + raw - 1e-9) <= budget

    ordered = _pool_order(entries, undated)
    groups: list[list[PoolEntry]] = []
    cur: list[PoolEntry] = []
    cur_raw = 0.0
    for e in ordered:
        r = est.raw(e.text)
        if not fits(r):
            raise ValueError(f"pool entry {e.entry_id} does not fit the token budget on its own")
        if cur and fits(cur_raw + r):
            cur.append(e)
            cur_raw += r
        else:
            if cur:
                groups.append(cur)
            cur, cur_raw = [e], r
    if cur or not groups:
        groups.append(cur)
    return [
        PoolPart(
            part_id=f"{pool_id}#p{i:03d}",
            index=i,
            entries=tuple(pinned) + tuple(g),
            estimated_tokens=math.ceil(pinned_raw + sum(est.raw(e.text) for e in g) - 1e-9),
        )
        for i, g in enumerate(groups, start=1)
    ]


def halve_pool_part(
    part: PoolPart, *, n_pinned: int = 0, estimator: TokenEstimator | None = None
) -> tuple[PoolPart, PoolPart] | None:
    """Halve a pool part's members (pinned entries stay in both); ``None`` if one member."""
    est = estimator or TokenEstimator()
    pinned, members = part.entries[:n_pinned], part.entries[n_pinned:]
    if len(members) < 2:
        return None
    mid = len(members) // 2

    def mk(suffix: str, ms: tuple[PoolEntry, ...]) -> PoolPart:
        es = pinned + ms
        return replace(
            part,
            part_id=f"{part.part_id}.{suffix}",
            entries=es,
            estimated_tokens=est.tokens("".join(e.text for e in es)),
            depth=part.depth + 1,
        )

    return mk("1", members[:mid]), mk("2", members[mid:])


# ---------------------------------------------------------------------------
# Combination: configuration
# ---------------------------------------------------------------------------


def normalise_order(item_id: str, order: Sequence[str]) -> tuple[str, ...]:
    """Apply the all-04 b rank: real answers, then ``not_documented``, then ``unknown``.

    Missing tokens absent from ``order`` are appended in that rank. An order
    that puts a missing token before a real answer, or ``unknown`` before
    ``not_documented``, raises :class:`SpecConflict`.
    """
    order = tuple(order)
    seen_missing = False
    for v in order:
        if v in (NOT_ASKED, NA):
            raise SpecConflict(item_id, f"order contains {v!r}, which never competes (all-04)")
        if v in MISSING_RANK:
            seen_missing = True
        elif seen_missing:
            raise SpecConflict(
                item_id, f"real answer {v!r} ranked after a missing token (all-04 b)"
            )
    present = [v for v in order if v in MISSING_RANK]
    if present != [v for v in MISSING_RANK if v in present]:
        raise SpecConflict(item_id, "unknown ranked before not_documented (all-04 b)")
    return order + tuple(v for v in MISSING_RANK if v not in order)


@dataclass(frozen=True)
class ItemRule:
    """Long-page combining configuration for one item (RC-D-002 row 41).

    - ``rule``: one of the rule types.
    - ``order``: for ``priority_order`` / ``any_yes``; normalised with the
      all-04 b missing rank.
    - ``two_tier``: page-verdict order (page-02 b): supported verdicts in
      ``order``, then failed verdicts in the same order.
    - ``downgrade_target``: what a failed answer enters as (``"unknown"``),
      or ``"tag_only"``: keep the value, mark it failed (page verdicts).
    - ``values``: the item's real codes, if coded (validates answers).
    - ``no_support_values``: real values that need no supporting quote
      (``no``, negative page verdicts, R-041). For a ``tag_only`` item this
      must be given explicitly: SPEC does not list the negative verdicts.
    - ``pair_to_both``: mapping step of activity-22 b, ``(a, b, both)``.
    - ``set_maps``: mapping step of activity-11 a, ``((frozenset, result), ...)``.
    - ``same_part_as`` / ``fallback``: for ``same_part_as`` (activity-15 a O6).
    """

    item_id: str
    rule: str
    order: tuple[str, ...] | None = None
    two_tier: bool = False
    downgrade_target: str = UNKNOWN
    values: frozenset[str] | None = None
    no_support_values: frozenset[str] | None = None
    pair_to_both: tuple[str, str, str] | None = None
    set_maps: tuple[tuple[frozenset[str], str], ...] = ()
    same_part_as: str | None = None
    fallback: str | None = None
    order_gaps: tuple[str, ...] = field(default=(), init=False)

    def __post_init__(self) -> None:
        if self.rule not in RULE_TYPES:
            raise UnresolvedCombineCase(
                self.item_id, f"rule type {self.rule!r} is not one of {sorted(RULE_TYPES)}"
            )
        if self.rule == ANY_YES and self.order is None:
            # any_yes: yes if any part says yes; the rest by the all-04 b rank
            # with `no` a real answer (spelled out for content_data, F05).
            object.__setattr__(self, "order", ("yes", "no"))
        if self.order is not None:
            order = normalise_order(self.item_id, self.order)
            if self.two_tier:
                # Page verdicts are never rewritten to a missing token (R-041),
                # so the verdict order carries no missing rank.
                order = tuple(v for v in order if v not in MISSING_RANK)
            object.__setattr__(self, "order", order)
        elif self.rule == PRIORITY_ORDER:
            raise UnresolvedCombineCase(self.item_id, "priority_order without an order")
        if self.rule == SAME_PART_AS and not self.same_part_as:
            raise UnresolvedCombineCase(self.item_id, "same_part_as without a reference item")
        if self.fallback not in (None, HIGHEST_PROBABILITY):
            raise UnresolvedCombineCase(self.item_id, f"fallback {self.fallback!r} not supported")
        if self.downgrade_target not in (UNKNOWN, DOWNGRADE_TAG_ONLY):
            raise UnresolvedCombineCase(
                self.item_id, f"downgrade target {self.downgrade_target!r} not supported"
            )
        if self.order is not None and self.values is not None:
            # Real codes the order cannot place (combining them stops the field).
            gaps = tuple(sorted(v for v in self.values if v not in self.order))
            object.__setattr__(self, "order_gaps", gaps)


def _parse_plus_map(item_id: str, key: str) -> list[str]:
    key = re.sub(r"\(.*?\)", "", key)
    parts = [p.strip() for p in key.split("+")]
    if len(parts) < 2 or not all(re.fullmatch(r"[a-z_]+", p) for p in parts):
        raise UnresolvedCombineCase(item_id, f"cannot read mapping key {key!r}")
    return parts


def rule_from_codebook_item(item_id: str, item: Mapping[str, Any]) -> ItemRule | None:
    """Build an :class:`ItemRule` from one raw codebook item (``items[item_id]``).

    Returns ``None`` when the item has no long-page rule (absent / ``none``).
    Raises :class:`UnresolvedCombineCase` when the rule cannot be expressed.
    This is the interface the T-013 loader feeds.
    """
    lp = item.get("long_page_rule")
    if lp is None or lp == "none":
        return None
    lp_map: Mapping[str, Any] = lp if isinstance(lp, Mapping) else {"rule": lp}
    rule = lp_map.get("rule")
    if rule not in RULE_TYPES:
        raise UnresolvedCombineCase(item_id, f"rule type {rule!r} cannot be expressed")
    codes = (
        frozenset(
            v["code"] for v in (item.get("values") or []) if isinstance(v, Mapping) and "code" in v
        )
        or None
    )
    order_cfg = lp_map.get("order")
    two_tier = False
    order: tuple[str, ...] | None
    if order_cfg == "S3 a":
        order, two_tier = S3A_VERDICT_ORDER, True
    elif isinstance(order_cfg, list):
        order = tuple(order_cfg)
    elif order_cfg is None:
        order = None
    else:
        raise UnresolvedCombineCase(item_id, f"cannot read order {order_cfg!r}")
    downgrade = item.get("downgrade_target") or UNKNOWN
    pair_to_both = None
    set_maps: list[tuple[frozenset[str], str]] = []
    mapping = lp_map.get("mapping")
    if isinstance(mapping, Mapping) and isinstance(mapping.get("map"), Mapping):
        for key, result in mapping["map"].items():
            parts = _parse_plus_map(item_id, str(key))
            if rule == COMBINED_LIST:
                if len(parts) != 2 or pair_to_both is not None:
                    raise UnresolvedCombineCase(item_id, f"list mapping {key!r} not a single pair")
                pair_to_both = (parts[0], parts[1], str(result))
            elif rule == PRIORITY_ORDER:
                set_maps.append((frozenset(parts), str(result)))
            else:
                raise UnresolvedCombineCase(item_id, f"mapping step on rule {rule!r}")
    elif mapping is not None:
        raise UnresolvedCombineCase(item_id, f"cannot read mapping {mapping!r}")
    return ItemRule(
        item_id=item_id,
        rule=rule,
        order=order,
        two_tier=two_tier,
        downgrade_target=downgrade,
        values=codes,
        no_support_values=frozenset({"no"}) if downgrade != DOWNGRADE_TAG_ONLY else None,
        pair_to_both=pair_to_both,
        set_maps=tuple(set_maps),
        same_part_as=lp_map.get("item"),
        fallback=lp_map.get("fallback"),
    )


# ---------------------------------------------------------------------------
# Combination: per-part check (check-then-combine, all-03 a)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PartAnswer:
    """One part's answer to one item.

    ``part_index`` is the part order (1-based) used for "earliest" ties and
    first-section rules. ``combined_list`` items may give several answers per
    part (one per value, each with its own quote and certainty).
    ``quote_not_stating_value`` is the T-022 entailment result, if run.
    """

    part_id: str
    part_index: int
    value: Any
    probability: float | None
    quote: str | None = None
    quote_not_stating_value: bool = False


@dataclass(frozen=True)
class CheckedAnswer:
    answer: PartAnswer
    entered: Any  # what votes; NOT_COVERED never votes
    status: str | None  # R-041 support status; None for NOT_COVERED
    second_reason: str | None = None
    failed: bool = False

    @property
    def votes(self) -> bool:
        return self.status is not None


def quote_in_part(quote: str | None, part_text: str) -> bool:
    """Exact substring test: does the quote occur in the part that produced it?"""
    return bool(quote) and quote in part_text


def _is_missing(v: Any) -> bool:
    return isinstance(v, str) and v in MISSING_TOKENS


def _needs_support(rule: ItemRule, value: Any) -> bool:
    if _is_missing(value):
        return False
    if rule.no_support_values is None:
        raise UnresolvedCombineCase(
            rule.item_id,
            "which values need no supporting quote is not configured (negative page "
            "verdicts are not listed in SPEC/codebook; R-041)",
        )
    return value not in rule.no_support_values


def check_part_answer(
    rule: ItemRule,
    ans: PartAnswer,
    *,
    part_text: str | None = None,
    bar: float = CERTAINTY_BAR,
    not_covered: str = NOT_COVERED,
) -> CheckedAnswer:
    """Check one part's answer before combining (all-03 a, R-041, R-081).

    Order of checks: quote, then certainty; the status takes the first failed
    check and the other failed check is the second reason (record-03 c).
    The quote check applies to values that need support; with ``part_text``
    the quote must also occur in that part (R-044: the quote comes from the
    chunk that produced the code). The certainty bar applies to every
    classifier answer, negative and absence codes included (R-081). A failed
    answer enters as the item's downgrade target, or keeps its value with
    ``failed=True`` for ``tag_only`` items (page verdicts).
    """
    v = ans.value
    if v == not_covered:
        return CheckedAnswer(ans, entered=not_covered, status=None)
    if v in (NOT_ASKED, NA):
        raise ValueError(
            f"{rule.item_id}: part answer {v!r}; applicability is applied after combining (all-04)"
        )
    if rule.values is not None and not _is_missing(v) and v not in rule.values:
        raise ValueError(f"{rule.item_id}: {v!r} is not a value of the item")
    if ans.probability is None:
        raise ValueError(f"{rule.item_id}: part {ans.part_id} answer has no probability")
    needs = _needs_support(rule, v)
    fails: list[str] = []
    if needs:
        if not ans.quote or (part_text is not None and not quote_in_part(ans.quote, part_text)):
            fails.append(DOWNGRADED_NO_QUOTE)
        elif ans.quote_not_stating_value:
            fails.append(DOWNGRADED_QUOTE_NOT_STATING_VALUE)
    if ans.probability < bar:
        fails.append(DOWNGRADED_LOW_CONFIDENCE)
    if not fails:
        return CheckedAnswer(ans, entered=v, status=SUPPORTED if needs else NOT_REQUIRED)
    second = fails[1] if len(fails) > 1 else None
    if rule.downgrade_target == DOWNGRADE_TAG_ONLY:
        return CheckedAnswer(ans, entered=v, status=fails[0], second_reason=second, failed=True)
    return CheckedAnswer(
        ans, entered=rule.downgrade_target, status=fails[0], second_reason=second, failed=True
    )


# ---------------------------------------------------------------------------
# Combination: rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CombinedAnswer:
    """The page's answer to one item, with its producing part.

    ``part_id`` / ``quote`` / ``probability`` come from the producing part
    (most sure among parts giving the winning value; ties earliest, all-05 a).
    They are ``None`` when a mapping step formed the value from several parts
    (``mapped_from`` then names the inputs) or when every part was not
    covered. ``contributors`` are all parts that gave the winning value.
    ``elements`` holds the per-value answers of a combined list.
    """

    item_id: str
    value: Any
    status: str | None
    part_id: str | None
    part_index: int | None
    probability: float | None
    quote: str | None
    second_reason: str | None = None
    failed: bool = False
    contributors: tuple[str, ...] = ()
    elements: tuple[CombinedAnswer, ...] = ()
    mapped_from: tuple[str, ...] = ()
    note: str | None = None


def _most_sure(cands: Sequence[CheckedAnswer]) -> CheckedAnswer:
    return min(cands, key=lambda c: (-(c.answer.probability or 0.0), c.answer.part_index))


def _from(item_id: str, winners: Sequence[CheckedAnswer], value: Any = None) -> CombinedAnswer:
    best = _most_sure(winners)
    return CombinedAnswer(
        item_id=item_id,
        value=best.entered if value is None else value,
        status=best.status,
        part_id=best.answer.part_id,
        part_index=best.answer.part_index,
        probability=best.answer.probability,
        quote=best.answer.quote,
        second_reason=best.second_reason,
        failed=best.failed,
        contributors=tuple(
            sorted(
                {c.answer.part_id for c in winners},
                key=lambda p: min(c.answer.part_index for c in winners if c.answer.part_id == p),
            )
        ),
    )


def _all_not_covered(item_id: str) -> CombinedAnswer:
    return CombinedAnswer(
        item_id,
        NOT_DOCUMENTED,
        NOT_REQUIRED,
        None,
        None,
        None,
        None,
        note="every part answered 'not covered by this part' (all-03 a)",
    )


def _missing_fallback(rule: ItemRule, voting: Sequence[CheckedAnswer]) -> CombinedAnswer:
    if not voting:
        return _all_not_covered(rule.item_id)
    for tok in MISSING_RANK:
        winners = [c for c in voting if c.entered == tok]
        if winners:
            return _from(rule.item_id, winners)
    raise UnresolvedCombineCase(rule.item_id, "no real or missing answer to combine")


def _real(voting: Sequence[CheckedAnswer]) -> list[CheckedAnswer]:
    return [c for c in voting if not _is_missing(c.entered)]


def _rank(rule: ItemRule, value: Any) -> int:
    assert rule.order is not None
    try:
        return rule.order.index(value)
    except ValueError:
        raise UnresolvedCombineCase(
            rule.item_id, f"value {value!r} has no place in the priority order"
        ) from None


def _combine_priority(rule: ItemRule, voting: Sequence[CheckedAnswer]) -> CombinedAnswer:
    if not voting:
        if rule.two_tier:
            raise UnresolvedCombineCase(
                rule.item_id,
                "every part 'not covered': all-03 a gives not_documented, which is not a verdict value",
            )
        return _all_not_covered(rule.item_id)
    if rule.set_maps:
        supported = {c.entered for c in _real(voting)}
        for needed, result in rule.set_maps:
            if needed <= supported:
                direct = [c for c in voting if c.entered == result]
                if direct:
                    return _from(rule.item_id, direct)
                inputs = [c for c in voting if c.entered in needed]
                return CombinedAnswer(
                    rule.item_id,
                    result,
                    SUPPORTED,
                    None,
                    None,
                    None,
                    None,
                    contributors=tuple(
                        dict.fromkeys(
                            c.answer.part_id
                            for c in sorted(inputs, key=lambda c: c.answer.part_index)
                        )
                    ),
                    elements=tuple(
                        _from(rule.item_id, [c for c in inputs if c.entered == v])
                        for v in sorted(needed, key=lambda v: _rank(rule, v))
                    ),
                    mapped_from=tuple(sorted(needed, key=lambda v: _rank(rule, v))),
                    note="mapping step (activity-11 a)",
                )

    def key(c: CheckedAnswer) -> tuple[int, int]:
        return (1 if (rule.two_tier and c.failed) else 0, _rank(rule, c.entered))

    best_key = min(key(c) for c in voting)
    return _from(rule.item_id, [c for c in voting if key(c) == best_key])


def _combine_first_section(rule: ItemRule, voting: Sequence[CheckedAnswer]) -> CombinedAnswer:
    real = _real(voting)
    if real:
        first = min(real, key=lambda c: c.answer.part_index)
        return _from(rule.item_id, [c for c in real if c.entered == first.entered])
    return _missing_fallback(rule, voting)


def _year(item_id: str, v: Any) -> int:
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    if isinstance(v, str) and re.fullmatch(r"\d{4}", v.strip()):
        return int(v)
    raise ValueError(f"{item_id}: {v!r} is not a year")


def _combine_earliest_year(rule: ItemRule, voting: Sequence[CheckedAnswer]) -> CombinedAnswer:
    real = _real(voting)
    if real:
        y = min(_year(rule.item_id, c.entered) for c in real)
        return _from(rule.item_id, [c for c in real if _year(rule.item_id, c.entered) == y])
    return _missing_fallback(rule, voting)


def _combine_highest_probability(rule: ItemRule, voting: Sequence[CheckedAnswer]) -> CombinedAnswer:
    real = _real(voting)
    if real:
        best = _most_sure(real)
        return _from(rule.item_id, [c for c in real if c.entered == best.entered])
    return _missing_fallback(rule, voting)


def _combine_list(rule: ItemRule, voting: Sequence[CheckedAnswer]) -> CombinedAnswer:
    real = sorted(_real(voting), key=lambda c: c.answer.part_index)
    if not real:
        return _missing_fallback(rule, voting)
    groups: dict[Any, list[CheckedAnswer]] = {}
    for c in real:
        groups.setdefault(c.entered, []).append(c)
    elements = tuple(_from(rule.item_id, cs) for cs in groups.values())
    values = tuple(groups)
    contributors = tuple(dict.fromkeys(c.answer.part_id for c in real))
    if rule.pair_to_both is None:
        return CombinedAnswer(
            rule.item_id,
            values,
            SUPPORTED,
            None,
            None,
            None,
            None,
            contributors=contributors,
            elements=elements,
        )
    a, b, both = rule.pair_to_both
    unknown_vals = [v for v in values if v not in (a, b, both)]
    if unknown_vals:
        raise UnresolvedCombineCase(rule.item_id, f"mapping step cannot place {unknown_vals!r}")
    if both in groups:
        out = _from(rule.item_id, groups[both])
        return replace(out, elements=elements, note="mapping step (activity-22 b): 'both' given")
    if a in groups and b in groups:
        return CombinedAnswer(
            rule.item_id,
            both,
            SUPPORTED,
            None,
            None,
            None,
            None,
            contributors=contributors,
            elements=elements,
            mapped_from=(a, b),
            note="mapping step (activity-22 b)",
        )
    return replace(_from(rule.item_id, real), elements=elements)


def _combine_same_part(
    rule: ItemRule, voting: Sequence[CheckedAnswer], reference: CombinedAnswer | None
) -> CombinedAnswer:
    if reference is None:
        raise UnresolvedCombineCase(
            rule.item_id, f"reference item {rule.same_part_as} not combined"
        )
    real = _real(voting)
    same = [
        c for c in real if reference.part_id is not None and c.answer.part_id == reference.part_id
    ]
    if same:
        return _from(rule.item_id, same)
    if not real:
        return _missing_fallback(rule, voting)
    if rule.fallback == HIGHEST_PROBABILITY:
        return _combine_highest_probability(rule, voting)
    raise UnresolvedCombineCase(rule.item_id, "producing part gives no real answer and no fallback")


def combine_item(
    rule: ItemRule,
    answers: Sequence[PartAnswer],
    *,
    part_texts: Mapping[str, str] | None = None,
    reference: CombinedAnswer | None = None,
    bar: float = CERTAINTY_BAR,
    not_covered: str = NOT_COVERED,
) -> CombinedAnswer:
    """Check each part's answer, then combine them by the item's rule.

    ``part_texts`` maps part id to part text; when given, every quote must
    occur in its own part. ``reference`` is the combined answer of
    ``rule.same_part_as`` for ``same_part_as`` items.
    """
    if not answers:
        raise ValueError(f"{rule.item_id}: no part answers")
    if rule.rule != COMBINED_LIST:
        ids = [a.part_id for a in answers]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{rule.item_id}: several answers from one part")
    texts = part_texts or {}
    checked = [
        check_part_answer(rule, a, part_text=texts.get(a.part_id), bar=bar, not_covered=not_covered)
        for a in answers
    ]
    voting = [c for c in checked if c.votes]
    if rule.order_gaps:
        bad = sorted({str(c.entered) for c in voting if c.entered in rule.order_gaps})
        if bad:
            raise UnresolvedCombineCase(rule.item_id, f"values {bad} have no place in the order")
    if rule.rule in (PRIORITY_ORDER, ANY_YES):
        return _combine_priority(rule, voting)
    if rule.rule == FIRST_SECTION:
        return _combine_first_section(rule, voting)
    if rule.rule == EARLIEST_YEAR:
        return _combine_earliest_year(rule, voting)
    if rule.rule == HIGHEST_PROBABILITY:
        return _combine_highest_probability(rule, voting)
    if rule.rule == COMBINED_LIST:
        return _combine_list(rule, voting)
    return _combine_same_part(rule, voting, reference)


@dataclass
class PageCombination:
    combined: dict[str, CombinedAnswer]
    stopped: dict[str, str]  # item id -> reason (report to the integrator)


def combine_page(
    rules: Mapping[str, ItemRule],
    answers: Mapping[str, Sequence[PartAnswer]],
    *,
    part_texts: Mapping[str, str] | None = None,
    bar: float = CERTAINTY_BAR,
    not_covered: str = NOT_COVERED,
) -> PageCombination:
    """Combine every item of one page (or one activity); stop failing fields only.

    Reference items of ``same_part_as`` rules are combined first. A field
    whose rule cannot combine it (:class:`UnresolvedCombineCase`) is listed
    in ``stopped``; the rest carry on.
    """
    combined: dict[str, CombinedAnswer] = {}
    stopped: dict[str, str] = {}
    ordered = sorted(
        answers, key=lambda i: (rules[i].rule == SAME_PART_AS if i in rules else False, i)
    )
    for item_id in ordered:
        rule = rules.get(item_id)
        if rule is None:
            stopped[item_id] = "no long-page rule configured"
            continue
        try:
            ref = combined.get(rule.same_part_as) if rule.same_part_as else None
            combined[item_id] = combine_item(
                rule,
                answers[item_id],
                part_texts=part_texts,
                reference=ref,
                bar=bar,
                not_covered=not_covered,
            )
        except UnresolvedCombineCase as exc:
            stopped[item_id] = exc.reason
    return PageCombination(combined, stopped)
