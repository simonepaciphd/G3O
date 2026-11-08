"""T-002 spike: pure helpers (no SDK, no network). Chunker, script byte counts, prices and the spend cap.

Everything here is free and unit-tested in test_t002.py.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

# ---- Prices (PI brief 2026-10-30; sourced 2026-10-30 from platform.claude.com/docs/en/about-claude/pricing
# and docs.typesafe.ai/models). USD per million tokens.
JEV_IN_PER_M = 0.042           # jev: input only, output free, no batch discount
HAIKU_SYNC_IN_PER_M = 0.10     # claude-haiku-5-5, prompts up to 100k tokens
HAIKU_SYNC_OUT_PER_M = 0.50
HAIKU_BATCH_IN_PER_M = 0.05    # Message Batches: 50%
HAIKU_BATCH_OUT_PER_M = 0.25
HAIKU_LONG_PROMPT_TOKENS = 100_000  # above this the rate card is $0.50 / $2.50; the script refuses such prompts

# ---- Chunking (DEC-008 c; provisional estimator, DP-007 margin unset)
JEV_TOKENS_PER_BYTE = 0.3947   # provisional: 963,894,721 bytes / 58,654 pages, question-load.md section 3
CHUNK_STATE_TOKENS = 24_000    # chunk target, under jev's 32k state limit (64k request = 32k state + questions)
JEV_REQUEST_TOKENS = 64_000
JEV_STATE_TOKENS = 32_000
MAX_SPLITS = 3                 # halve-and-retry on max_tokens_exceeded, at most 3 times
HAIKU_BYTES_PER_TOKEN = 3.2    # dry-run assumption only (no free, keyless token counter)

SCRIPTS = ("latin", "cjk", "thai", "other")


def chunk_byte_cap(tokens: int = CHUNK_STATE_TOKENS, tokens_per_byte: float = JEV_TOKENS_PER_BYTE) -> int:
    return int(tokens / tokens_per_byte)


def utf8_len(s: str) -> int:
    return len(s.encode("utf-8"))


def byte_chunks(text: str, cap: int) -> list[str]:
    """Split text into the fewest pieces of at most `cap` UTF-8 bytes, balanced in size, never inside a character.

    Deterministic. Pieces concatenate back to `text`. An empty text gives [""].
    """
    if cap < 4:
        raise ValueError("cap must be at least 4 bytes (one UTF-8 character)")
    total = utf8_len(text)
    if total <= cap:
        return [text]
    n = math.ceil(total / cap)
    while True:
        target = math.ceil(total / n)
        out, cur, size = [], [], 0
        for ch in text:
            b = len(ch.encode("utf-8"))
            if size + b > target and cur:
                out.append("".join(cur))
                cur, size = [], 0
            cur.append(ch)
            size += b
        out.append("".join(cur))
        if all(utf8_len(p) <= cap for p in out):
            return out
        n += 1  # multi-byte boundary effects pushed a piece over; try one more piece


def halve(text: str) -> list[str]:
    """Halve a piece for the max_tokens_exceeded retry (unclear2.py pattern)."""
    return byte_chunks(text, max(utf8_len(text) // 2, 4))


def char_script(ch: str) -> str | None:
    """Script bucket of one character; None for whitespace, digits and punctuation in the ASCII range."""
    o = ord(ch)
    if o < 0x80:
        return "latin" if ch.isalpha() else None
    if 0x0E00 <= o <= 0x0E7F:
        return "thai"
    if (0x3040 <= o <= 0x30FF or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF
            or 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F or 0xFF66 <= o <= 0xFF9F
            or 0x20000 <= o <= 0x2FA1F):
        return "cjk"
    if 0x00C0 <= o <= 0x024F or 0x1E00 <= o <= 0x1EFF:
        return "latin"
    if ch.isspace() or not ch.isalpha():
        return None
    return "other"


def script_bytes(text: str) -> dict[str, int]:
    """UTF-8 bytes per script bucket; spaces, digits and punctuation go to 'neutral'."""
    out = dict.fromkeys(SCRIPTS + ("neutral",), 0)
    for ch in text:
        out[char_script(ch) or "neutral"] += len(ch.encode("utf-8"))
    return out


def dominant_script(text: str) -> str:
    sb = script_bytes(text)
    best = max(SCRIPTS, key=lambda s: sb[s])
    return best if sb[best] > 0 else "latin"


# ---- jev question sizing (what jev bills: state once + each question's wording)

def question_text(q: dict) -> str:
    """Billable wording of one proxy question {'instructions': str, 'criteria': {code: text}}."""
    parts = [q["instructions"]]
    for k, v in q["criteria"].items():
        parts += [k, v]
    return "\n".join(parts)


def state_text(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False)


def est_jev_tokens(state: dict, questions: dict[str, dict], tpb: float = JEV_TOKENS_PER_BYTE) -> int:
    b = utf8_len(state_text(state)) + sum(utf8_len(question_text(q)) for q in questions.values())
    return math.ceil(b * tpb)


def pack_questions(questions: dict[str, dict], budget_tokens: int, tpb: float = JEV_TOKENS_PER_BYTE) -> list[dict]:
    """Split a question set into groups whose estimated wording fits `budget_tokens` (request 64k minus state)."""
    groups, cur, used = [], {}, 0
    for qid, q in questions.items():
        t = math.ceil(utf8_len(question_text(q)) * tpb)
        if cur and used + t > budget_tokens:
            groups.append(cur)
            cur, used = {}, 0
        cur[qid] = q
        used += t
    if cur:
        groups.append(cur)
    return groups


# ---- Costs

def jev_cost(input_tokens: int) -> float:
    return input_tokens * JEV_IN_PER_M / 1e6


def haiku_cost(input_tokens: int, output_tokens: int, batch: bool = False) -> float:
    if batch:
        return (input_tokens * HAIKU_BATCH_IN_PER_M + output_tokens * HAIKU_BATCH_OUT_PER_M) / 1e6
    return (input_tokens * HAIKU_SYNC_IN_PER_M + output_tokens * HAIKU_SYNC_OUT_PER_M) / 1e6


def jev_upper_bound() -> float:
    """Most one jev request can cost: the 64k-token request limit."""
    return jev_cost(JEV_REQUEST_TOKENS)


def haiku_upper_bound(prompt_bytes: int, max_tokens: int, batch: bool = False) -> float:
    """Generous bound for one Haiku call: prompt at 1 token per 2 bytes (far above bytes/3.2), full max_tokens out."""
    return haiku_cost(math.ceil(prompt_bytes / 2), max_tokens, batch)


class CapReached(RuntimeError):
    """The next call could take spend over the cap; the run stops before sending it."""


@dataclass
class Budget:
    """Spend cap. `reserve(bound)` is called before every paid call with that call's worst-case cost; it raises
    CapReached if spent + bound would exceed the cap. `commit(actual)` records the measured cost afterwards."""

    cap_usd: float
    spent_usd: float = 0.0
    by_leg: dict = field(default_factory=dict)

    def reserve(self, bound_usd: float) -> None:
        if bound_usd < 0:
            raise ValueError("bound must be non-negative")
        if self.spent_usd + bound_usd > self.cap_usd:
            raise CapReached(f"cap ${self.cap_usd:.2f}: spent ${self.spent_usd:.4f} + next call bound "
                             f"${bound_usd:.4f} would exceed it")

    def commit(self, actual_usd: float, leg: str = "") -> None:
        self.spent_usd += actual_usd
        if leg:
            self.by_leg[leg] = self.by_leg.get(leg, 0.0) + actual_usd

    @property
    def remaining_usd(self) -> float:
        return self.cap_usd - self.spent_usd


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)
