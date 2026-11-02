"""Calibrated UTF-8 token estimation and lossless page chunking (T-020).

Mechanically extracted from reviewed calibration ffb5be2. Answer combination
remains owned by the accepted T-027 implementation in jev_record.py.
The selected DP-007 margin is not installed here: complete serialized-request
overhead and runtime verification remain required before production use.
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Generic, TypeVar

#: jev state limit per request (C-004: "32k tokens"). Whether jev counts 32k
#: as 32,000 or 32,768 is not stated in SPEC; 32,000 is the lower reading.
#: Configurable per call.
JEV_STATE_TOKEN_LIMIT = 32_000

#: Approved T-002 medians, tokens per UTF-8 byte (RC-D-006, PI 2 a).
#: Latin: 64 requests; CJK: 10; Thai: 3 (thin evidence, no stronger claim).
#: These ratios are calibrated; the DP-007 safety margin remains unresolved.
CALIBRATED_TOKENS_PER_BYTE: Mapping[str, float] = {
    "latin": 0.305,
    "cjk": 0.341,
    "thai": 0.334,
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
    """Additive token estimate using UTF-8 byte counts in each script bucket.

    ``tokens_per_byte`` defaults to the approved T-002 ratios. DP-007 remains
    unresolved: ``safety_margin=None`` uses zero placeholders for offline
    estimates only, and :meth:`assert_calibrated` refuses that configuration.
    Production callers must supply every script's margin and explicitly clear
    ``placeholder`` after the separate approval gate. Explicit configuration
    does not itself establish PI approval or full T-020 acceptance.
    """

    tokens_per_byte: Mapping[str, float] = field(
        default_factory=lambda: dict(CALIBRATED_TOKENS_PER_BYTE)
    )
    safety_margin: Mapping[str, float] | None = None
    placeholder: bool = True

    def __post_init__(self) -> None:
        for script in ("latin", "cjk", "thai"):
            tpb = self.tokens_per_byte.get(script)
            if tpb is None or not math.isfinite(tpb) or tpb <= 0:
                raise ValueError(f"tokens_per_byte[{script!r}] must be finite and > 0, got {tpb!r}")
            m = (self.safety_margin or PLACEHOLDER_SAFETY_MARGIN).get(script, 0.0)
            if not math.isfinite(m) or m < 0:
                raise ValueError(f"safety_margin[{script!r}] must be finite and >= 0, got {m!r}")

    def assert_calibrated(self) -> None:
        if self.placeholder or self.safety_margin is None or not {
            "latin", "cjk", "thai"
        }.issubset(self.safety_margin):
            raise RuntimeError(
                "DP-007 safety margin remains PLACEHOLDER; explicit complete margin "
                "configuration and approval are required before a production run"
            )

    def _weight(self, script: str) -> float:
        margin = (self.safety_margin or PLACEHOLDER_SAFETY_MARGIN).get(script, 0.0)
        return self.tokens_per_byte[script] * (1.0 + margin)

    def raw(self, text: str) -> float:
        """Unrounded estimate (additive: ``raw(a + b) == raw(a) + raw(b)``)."""
        counts = {"latin": 0, "cjk": 0, "thai": 0}
        for ch in text:
            counts[script_of(ch)] += len(ch.encode("utf-8"))
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
