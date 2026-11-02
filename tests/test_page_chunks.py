"""Reviewed estimator, lossless page splitting and bounded retry fixtures."""
from __future__ import annotations

import pytest

from g3o.common import page_chunks as pc
from g3o.common.page_chunks import TokenEstimator

# ---------------------------------------------------------------------------
# Estimator
# ---------------------------------------------------------------------------


def test_calibrated_ratios_keep_unresolved_margin_guard():
    est = TokenEstimator()
    assert est.placeholder is True
    with pytest.raises(RuntimeError, match="PLACEHOLDER"):
        est.assert_calibrated()
    TokenEstimator(
        tokens_per_byte={"latin": 0.25, "cjk": 0.3, "thai": 0.2},
        safety_margin={"latin": 0.05, "cjk": 0.05, "thai": 0.05},
        placeholder=False,
    ).assert_calibrated()


def test_estimator_per_script_constants_and_additivity():
    est = TokenEstimator(tokens_per_byte={"latin": 0.25, "cjk": 1 / 3, "thai": 1 / 6})
    assert est.tokens("abcd" * 10) == 10
    assert est.tokens("政府" * 5) == 10
    assert est.tokens("ภาษาไทย!") == 4  # 7 Thai chars / 2 + 1 latin / 4
    a, b = "hello world ", "政府のAI"
    assert est.raw(a + b) == pytest.approx(est.raw(a) + est.raw(b))
    assert pc.script_of("a") == "latin" and pc.script_of("ж") == "latin"
    assert pc.script_of("한") == "cjk" and pc.script_of("ก") == "thai"


def test_safety_margin_inflates_the_estimate():
    base = TokenEstimator(tokens_per_byte={"latin": 0.25, "cjk": 1 / 3, "thai": 1 / 6})
    margin = TokenEstimator(
        tokens_per_byte={"latin": 0.25, "cjk": 1 / 3, "thai": 1 / 6},
        safety_margin={"latin": 0.5, "cjk": 0.0, "thai": 0.0},
    )
    assert base.tokens("a" * 40) == 10
    assert margin.tokens("a" * 40) == 15
    assert margin.tokens("政" * 10) == 10


def test_estimator_rejects_bad_constants():
    with pytest.raises(ValueError):
        TokenEstimator(tokens_per_byte={"latin": 0, "cjk": 1, "thai": 1})
    with pytest.raises(ValueError):
        TokenEstimator(safety_margin={"latin": -0.1})


@pytest.mark.parametrize("margin", [None, {}, {"latin": 0.1}, {"latin": 0.1, "cjk": 0.1}])
def test_unresolved_or_partial_margin_cannot_bypass_guard(margin):
    with pytest.raises(RuntimeError, match="DP-007"):
        TokenEstimator(safety_margin=margin, placeholder=False).assert_calibrated()


def test_explicit_margin_does_not_clear_placeholder_implicitly():
    # Fixture values demonstrate configuration, not PI-approved safety margins.
    with pytest.raises(RuntimeError, match="DP-007"):
        TokenEstimator(safety_margin={"latin": 0, "cjk": 0, "thai": 0}).assert_calibrated()


@pytest.mark.parametrize(
    ("text", "raw", "rounded"),
    [("a" * 100, 30.5, 31), ("é" * 100, 61.0, 61),
     ("政府" * 50, 102.3, 103), ("ภาษาไทย" * 10, 70.14, 71),
     ("𠀀" * 10, 13.64, 14)],
)
def test_approved_ratios_count_utf8_bytes(text, raw, rounded):
    est = TokenEstimator()
    assert est.tokens_per_byte == {"latin": 0.305, "cjk": 0.341, "thai": 0.334}
    assert est.raw(text) == pytest.approx(raw)
    assert est.tokens(text) == rounded


def test_calibrated_mixed_scripts_are_additive_and_chunks_lossless():
    est = TokenEstimator()
    text = "é政ก𠀀 A" * 80
    expected_unit = 4 * 0.305 + 7 * 0.341 + 3 * 0.334
    assert est.raw(text) == pytest.approx(80 * expected_unit)
    assert est.raw(text[:17]) + est.raw(text[17:]) == pytest.approx(est.raw(text))
    chunks = pc.chunk_page("mixed", text, estimator=est, limit_tokens=30, overhead_tokens=5)
    assert len(chunks) > 1
    assert "".join(c.text for c in chunks) == text
    assert all(c.estimated_tokens <= 25 for c in chunks)
    assert all(text[c.start:c.end] == c.text for c in chunks)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1])
def test_estimator_rejects_nonfinite_or_negative_parameters(value):
    with pytest.raises(ValueError):
        TokenEstimator(tokens_per_byte={"latin": value, "cjk": 0.341, "thai": 0.334})
    with pytest.raises(ValueError):
        TokenEstimator(safety_margin={"latin": value})


# ---------------------------------------------------------------------------
# Page chunking
# ---------------------------------------------------------------------------

EST = TokenEstimator(tokens_per_byte={"latin": 1.0, "cjk": 1 / 3, "thai": 1 / 3})


def _page(n_paras: int = 6, para_len: int = 30) -> str:
    return "\n\n".join(" ".join(f"w{i}x{j}" for j in range(para_len // 5)) for i in range(n_paras))


def test_short_page_is_one_part_with_id():
    chunks = pc.chunk_page("pg", "short text", estimator=EST, limit_tokens=100)
    assert [c.chunk_id for c in chunks] == ["pg#p001"]
    assert chunks[0].start == 0 and chunks[0].end == 10


def test_chunks_fit_budget_are_lossless_and_ordered():
    text = _page(20, 60)
    chunks = pc.chunk_page("pg", text, estimator=EST, limit_tokens=150, overhead_tokens=30)
    assert len(chunks) > 1
    assert "".join(c.text for c in chunks) == text
    assert all(c.estimated_tokens <= 120 for c in chunks)
    assert [c.chunk_id for c in chunks] == [f"pg#p{i:03d}" for i in range(1, len(chunks) + 1)]
    for c in chunks:
        assert text[c.start : c.end] == c.text
    # Paragraph boundaries are preferred: every chunk but the last ends at one.
    assert all(c.text.endswith("\n\n") for c in chunks[:-1])


def test_chunking_is_deterministic():
    text = _page(15, 80) + "\n" + "政府" * 200
    a = pc.chunk_page("pg", text, estimator=EST, limit_tokens=90)
    b = pc.chunk_page("pg", text, estimator=EST, limit_tokens=90)
    assert a == b


def test_unbroken_text_falls_back_to_character_cuts():
    text = "x" * 250
    chunks = pc.chunk_page("pg", text, estimator=EST, limit_tokens=100)
    assert [len(c.text) for c in chunks] == [100, 100, 50]


def test_cjk_text_splits_on_sentence_marks():
    text = "政府はAIを導入した。" * 30
    chunks = pc.chunk_page("pg", text, estimator=EST, limit_tokens=50)
    assert "".join(c.text for c in chunks) == text
    assert all(c.text.endswith("。") for c in chunks)
    assert all(c.estimated_tokens <= 50 for c in chunks)


def test_no_budget_raises():
    with pytest.raises(ValueError):
        pc.chunk_page("pg", "abc", estimator=EST, limit_tokens=10, overhead_tokens=10)


# ---------------------------------------------------------------------------
# Halve-and-retry (DEC-008 c)
# ---------------------------------------------------------------------------


class OverLimit(Exception):
    pass


def test_over_limit_chunk_triggers_halve_and_retry():
    text = _page(8, 40)
    chunks = pc.chunk_page("pg", text, estimator=EST, limit_tokens=10_000)
    assert len(chunks) == 1
    real_limit = 90  # what "jev" really accepts: the estimate was too low

    def send(c):
        if len(c.text) > real_limit:
            raise OverLimit("max_tokens_exceeded")
        return c.chunk_id

    out = pc.run_with_halving(
        chunks,
        send,
        is_over_limit=lambda e: isinstance(e, OverLimit),
        halve=lambda c: pc.halve_chunk(c, estimator=EST),
    )
    parts = [c for c, _ in out.results]
    assert out.n_halvings >= 1
    assert "".join(c.text for c in parts) == text  # halves stay in page order
    assert all(len(c.text) <= real_limit for c in parts)
    assert parts[0].chunk_id.startswith("pg#p001.1")
    assert all(c.depth >= 1 for c in parts)


def test_halving_stops_at_max_depth():
    chunks = pc.chunk_page("pg", "y" * 64, estimator=EST, limit_tokens=1_000)

    def send(c):
        raise OverLimit()

    with pytest.raises(OverLimit):
        pc.run_with_halving(
            chunks,
            send,
            is_over_limit=lambda e: isinstance(e, OverLimit),
            halve=lambda c: pc.halve_chunk(c, estimator=EST),
            max_depth=3,
        )
    calls: list[int] = []

    def send2(c):
        calls.append(c.depth)
        raise OverLimit()

    with pytest.raises(OverLimit):
        pc.run_with_halving(
            chunks,
            send2,
            is_over_limit=lambda e: isinstance(e, OverLimit),
            halve=lambda c: pc.halve_chunk(c, estimator=EST),
            max_depth=2,
        )
    assert max(calls) == 2


def test_other_errors_are_not_retried():
    chunks = pc.chunk_page("pg", "abc def", estimator=EST, limit_tokens=100)

    def send(c):
        raise KeyError("boom")

    with pytest.raises(KeyError):
        pc.run_with_halving(
            chunks, send, is_over_limit=lambda e: isinstance(e, OverLimit), halve=pc.halve_chunk
        )


def test_halve_prefers_boundary_near_middle():
    c = pc.chunk_page("pg", "aaaa\n\nbbbb\n\ncccc dddd", estimator=EST, limit_tokens=100)[0]
    h1, h2 = pc.halve_chunk(c, estimator=EST)
    assert h1.text == "aaaa\n\nbbbb\n\n" and h2.text == "cccc dddd"
    assert (h1.end, h2.start) == (12, 12)
    assert pc.halve_chunk(pc.Chunk("x", "pg", 0, 1, "x", 1)) is None
