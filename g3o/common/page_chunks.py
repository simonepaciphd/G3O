"""Local T-020 chunking preparation; no provider calls or answer combination.

The DP-007 uniform 90% margin is selected, but actual provider accounting and
runtime/instrument binding remain separate gates. `chunk_page` and `split_pool`
are text-only primitives: use `prepare_page_requests` for full serialized request
budgeting. The serializer must include every request field; this module cannot
infer omitted provider framing or validate a caller's request builder.
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Generic, TypeVar

APPROVED_SAFETY_MARGIN = {"latin": 0.9, "cjk": 0.9, "thai": 0.9}

JEV_STATE_TOKEN_LIMIT = 32_000


CALIBRATED_TOKENS_PER_BYTE: Mapping[str, float] = {
    "latin": 0.305,
    "cjk": 0.341,
    "thai": 0.334,
}


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
    """UTF-8 per-script estimator with PI-selected DP-007 margins.

    Custom configurations are available for offline testing; callers must retain
    the approved bases and margins for approved local preparation. Passing None,
    incomplete margins, or placeholder=True cannot pass assert_calibrated.
    This configuration check is not provider/runtime verification.
    """

    tokens_per_byte: Mapping[str, float] = field(
        default_factory=lambda: dict(CALIBRATED_TOKENS_PER_BYTE)
    )
    safety_margin: Mapping[str, float] | None = field(
        default_factory=lambda: dict(APPROVED_SAFETY_MARGIN)
    )
    placeholder: bool = False

    def __post_init__(self) -> None:
        for script in ("latin", "cjk", "thai"):
            tpb = self.tokens_per_byte.get(script)
            if tpb is None or not math.isfinite(tpb) or tpb <= 0:
                raise ValueError(f"tokens_per_byte[{script!r}] must be finite and > 0, got {tpb!r}")
            m = (self.safety_margin or {}).get(script, 0.0)
            if not math.isfinite(m) or m < 0:
                raise ValueError(f"safety_margin[{script!r}] must be finite and >= 0, got {m!r}")

    def assert_calibrated(self) -> None:
        if self.placeholder or self.safety_margin is None or not {
            "latin", "cjk", "thai"
        }.issubset(self.safety_margin):
            raise RuntimeError(
                "DP-007 margin is incomplete or PLACEHOLDER; explicit complete margin "
                "configuration and approval are required before a production run"
            )

    def assert_approved(self) -> None:
        """Require the selected bases/margins; this is not runtime verification."""
        self.assert_calibrated()
        if (dict(self.tokens_per_byte) != dict(CALIBRATED_TOKENS_PER_BYTE)
                or dict(self.safety_margin or {}) != APPROVED_SAFETY_MARGIN):
            raise RuntimeError("full-request preparation requires the PI-approved DP-007 configuration")

    def _weight(self, script: str) -> float:
        margin = (self.safety_margin or {}).get(script, 0.0)
        return self.tokens_per_byte[script] * (1.0 + margin)

    def raw(self, text: str) -> float:
        """Unrounded estimate (additive: ``raw(a + b) == raw(a) + raw(b)``)."""
        counts = {"latin": 0, "cjk": 0, "thai": 0}
        for ch in text:
            counts[script_of(ch)] += len(ch.encode("utf-8"))
        return sum(n * self._weight(s) for s, n in counts.items() if n)

    def tokens(self, text: str) -> int:
        return math.ceil(self.raw(text) - 1e-9)


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
    if type(limit_tokens) is not int or type(overhead_tokens) is not int:
        raise ValueError("token limit and overhead must be integers")
    if overhead_tokens < 0:
        raise ValueError("overhead_tokens must be nonnegative")
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
    if type(limit_tokens) is not int or type(overhead_tokens) is not int:
        raise ValueError("token limit and overhead must be integers")
    if overhead_tokens < 0 or budget <= 0:
        raise ValueError("no positive token budget remains after overhead")
    pinned_raw = sum(est.raw(p.text) for p in pinned)
    if math.ceil(pinned_raw - 1e-9) > budget:
        raise ValueError("pinned pool entries exceed the token budget")

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


@dataclass(frozen=True)
class PreparedPageRequest:
    """An exact UTF-8 payload and the chunk it was measured against.

    `estimated_request_tokens` includes the whole serialized payload, not just
    page text. `reserved_tokens` is an explicit allowance for known overhead
    absent from the payload (for example an output budget where applicable).
    Actual provider usage is not represented by this estimate.
    """

    chunk: Chunk
    payload: bytes
    estimated_request_tokens: int
    reserved_tokens: int


def prepare_page_requests(
    page_id: str,
    text: str,
    *,
    serialize_request: Callable[[Chunk], str | bytes],
    estimator: TokenEstimator | None = None,
    limit_tokens: int = JEV_STATE_TOKEN_LIMIT,
    reserved_tokens: int,
) -> list[PreparedPageRequest]:
    """Prepare lossless parts, checking the exact full payload for each part.

    Required serializer: the same complete request builder/serializer the caller
    will send, including state, questions, instructions, metadata, schema,
    options and framing. Do not pass page text or a partial state serializer.
    An unknown serializer/reserve fails closed; zero reserve must be explicit.
    The 32k default conservatively bounds the full request, rather than claiming
    that provider state and full-request limits have identical semantics.

    Oversized parts are split at preferred boundaries until they fit; the
    returned byte payloads are the measured ones. Rebuilding or modifying them
    before sending invalidates this check. Provider rejection still requires the
    separately bounded `run_with_halving` retry path.
    """
    if not callable(serialize_request):
        raise TypeError("a complete request serializer is required")
    if type(limit_tokens) is not int or limit_tokens <= 0:
        raise ValueError("limit_tokens must be a positive integer")
    if type(reserved_tokens) is not int or not 0 <= reserved_tokens < limit_tokens:
        raise ValueError("reserved_tokens must be a known nonnegative integer below limit")
    est = estimator or TokenEstimator()
    est.assert_approved()
    budget = limit_tokens - reserved_tokens

    def encode(chunk: Chunk) -> tuple[bytes, int]:
        payload = serialize_request(chunk)
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        if not isinstance(payload, bytes) or not payload:
            raise TypeError("serializer must return a nonempty complete UTF-8 payload")
        return payload, est.tokens(payload.decode("utf-8", errors="strict"))

    initial = chunk_page(page_id, text, estimator=est, limit_tokens=budget)
    pending = list(reversed(initial))
    prepared = []
    while pending:
        chunk = pending.pop()
        payload, estimate = encode(chunk)
        if estimate <= budget:
            prepared.append(PreparedPageRequest(chunk, payload, estimate, reserved_tokens))
            continue
        # Refuse impossible fixed overhead before repeatedly subdividing text.
        _, empty_estimate = encode(replace(chunk, text="", end=chunk.start))
        if empty_estimate >= budget:
            raise ValueError("serialized request overhead leaves no page-text budget")
        halves = halve_chunk(chunk, estimator=est)
        if halves is None:
            raise ValueError("serialized request cannot fit even at one character")
        pending.extend(reversed(halves))
    return prepared


@dataclass(frozen=True)
class PreparedPoolRequest:
    """A pooled part with the exact measured UTF-8 request payload."""

    part: PoolPart
    payload: bytes
    estimated_request_tokens: int
    reserved_tokens: int


def prepare_pool_requests(
    pool_id: str,
    entries: Iterable[PoolEntry],
    *,
    serialize_request: Callable[[PoolPart], str | bytes],
    estimator: TokenEstimator | None = None,
    limit_tokens: int = JEV_STATE_TOKEN_LIMIT,
    reserved_tokens: int,
    pinned: Sequence[PoolEntry] = (),
    undated: str = "error",
) -> list[PreparedPoolRequest]:
    """Prepare complete pooled request payloads without changing evidence order.

    The full serializer/reserve contract is the same as prepare_page_requests.
    Every final part repeats all pinned entries. Members remain indivisible and
    retain the existing source-date/page-order sort. Fixed overhead or a single
    member that cannot fit raises; evidence is never silently dropped.
    Final indexes are 1..N and assigned before serialization; unique IDs retain
    the initial group/split lineage. Actual T-026 builder and provider/runtime
    verification remain separate from this generic offline adapter.
    """
    if not callable(serialize_request):
        raise TypeError("a complete request serializer is required")
    if type(limit_tokens) is not int or limit_tokens <= 0:
        raise ValueError("limit_tokens must be a positive integer")
    if type(reserved_tokens) is not int or not 0 <= reserved_tokens < limit_tokens:
        raise ValueError("reserved_tokens must be a known nonnegative integer below limit")
    est = estimator or TokenEstimator()
    est.assert_approved()
    budget = limit_tokens - reserved_tokens
    pins = tuple(pinned)
    initial = split_pool(pool_id, entries, estimator=est, limit_tokens=budget,
                         pinned=pins, undated=undated)
    pending = list(reversed(initial))
    prepared = []
    while pending:
        part = replace(pending.pop(), index=len(prepared) + 1)
        payload = serialize_request(part)
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        if not isinstance(payload, bytes) or not payload:
            raise TypeError("serializer must return a nonempty complete UTF-8 payload")
        estimate = est.tokens(payload.decode("utf-8", errors="strict"))
        if estimate <= budget:
            prepared.append(PreparedPoolRequest(part, payload, estimate, reserved_tokens))
            continue
        halves = halve_pool_part(part, n_pinned=len(pins), estimator=est)
        if halves is None:
            raise ValueError("serialized pooled request cannot fit indivisible member or pinned-only overhead")
        pending.extend(reversed(halves))
    return prepared
