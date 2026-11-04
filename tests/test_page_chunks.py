"""Offline T-020 chunking and exact full-request budgeting regressions."""
import copy
import json
from pathlib import Path

import pytest

from g3o.common import page_chunks as pc
from g3o.common.page_chunks import PoolEntry, TokenEstimator

EST = TokenEstimator(tokens_per_byte={"latin": 1.0, "cjk": 1 / 3, "thai": 1 / 3}, safety_margin={"latin": 0, "cjk": 0, "thai": 0})


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


def _entries():
    return [
        PoolEntry("e3", "c" * 30, "2024-05-01", 1),
        PoolEntry("e1", "a" * 30, "2023-01-01", 2),
        PoolEntry("e2", "b" * 30, "2023-01-01", 1),
        PoolEntry("e4", "d" * 30, "2025", 0),
    ]


def test_pool_split_orders_by_source_date_then_page_order():
    parts = pc.split_pool("inst", _entries(), estimator=EST, limit_tokens=60)
    assert [[e.entry_id for e in p.entries] for p in parts] == [["e2", "e1"], ["e3", "e4"]]
    assert [p.part_id for p in parts] == ["inst#p001", "inst#p002"]
    assert all(p.estimated_tokens <= 60 for p in parts)


def test_pool_split_pins_entries_into_every_part():
    pins = [PoolEntry("actA", "A" * 10, "2020", 0), PoolEntry("actB", "B" * 10, "2020", 0)]
    parts = pc.split_pool("pair", _entries(), estimator=EST, limit_tokens=80, pinned=pins)
    assert len(parts) == 2
    for p in parts:
        assert [e.entry_id for e in p.entries[:2]] == ["actA", "actB"]
        assert p.estimated_tokens <= 80
    h = pc.halve_pool_part(parts[0], n_pinned=2, estimator=EST)
    assert [[e.entry_id for e in x.entries] for x in h] == [
        ["actA", "actB", "e2"],
        ["actA", "actB", "e1"],
    ]


def test_pool_undated_entries_need_an_explicit_policy():
    es = [*_entries(), PoolEntry("e0", "z", None, 0)]
    with pytest.raises(ValueError, match="undated"):
        pc.split_pool("inst", es, estimator=EST, limit_tokens=1000)
    last = pc.split_pool("inst", es, estimator=EST, limit_tokens=1000, undated="last")
    assert last[0].entries[-1].entry_id == "e0"
    first = pc.split_pool("inst", es, estimator=EST, limit_tokens=1000, undated="first")
    assert first[0].entries[0].entry_id == "e0"


def test_pool_entry_too_large_raises():
    with pytest.raises(ValueError, match="does not fit"):
        pc.split_pool(
            "inst", [PoolEntry("big", "x" * 100, "2020", 0)], estimator=EST, limit_tokens=50
        )


def test_selected_margin_rates():
    e = TokenEstimator()
    e.assert_approved()
    assert [e._weight(k) for k in ("latin", "cjk", "thai")] == pytest.approx([.5795, .6479, .6346])
    assert e.raw("é政ก𠀀 A") == pytest.approx(4*.5795 + 7*.6479 + 3*.6346)


@pytest.mark.parametrize("margin", [None, {}, {"latin": .9}, {"latin": 0, "cjk": 0, "thai": 0}])
def test_preparation_rejects_missing_or_unapproved_margin(margin):
    with pytest.raises(RuntimeError, match="DP-007"):
        pc.prepare_page_requests("p", "abc", serialize_request=lambda c: c.text,
                                 estimator=TokenEstimator(safety_margin=margin), reserved_tokens=0)


def test_preparation_rejects_changed_base_or_placeholder():
    for e in (TokenEstimator(tokens_per_byte={"latin": .1, "cjk": .341, "thai": .334}),
              TokenEstimator(placeholder=True)):
        with pytest.raises(RuntimeError):
            pc.prepare_page_requests("p", "abc", serialize_request=lambda c: c.text,
                                     estimator=e, reserved_tokens=0)


@pytest.mark.parametrize("limit,overhead,pinned", [(10, 10, ()), (0, 0, ()), (10, -1, ()),
    (10, 0, (PoolEntry("x", "x"*100, "2026", 0),))])
def test_empty_or_pinned_pool_fails_closed(limit, overhead, pinned):
    with pytest.raises(ValueError):
        pc.split_pool("p", [], limit_tokens=limit, overhead_tokens=overhead, pinned=pinned)


def test_empty_pool_and_fitting_pins():
    assert pc.split_pool("p", [], limit_tokens=10)[0].estimated_tokens == 0
    pin = PoolEntry("x", "x", "2026", 0)
    assert pc.split_pool("p", [], pinned=[pin], limit_tokens=10)[0].entries == (pin,)


def envelope(c):
    return json.dumps({"model": "fixture", "state": {"page_text": c.text, "chunk_id": c.chunk_id},
                       "questions": {"q": {"instructions": "context"*30, "criteria": {"yes": "y", "no": "n"}}},
                       "schema": {"type": "object"}, "options": {"effort": "medium"}}, ensure_ascii=True)


def test_whole_payload_counts_questions_escapes_options_and_metadata():
    text = ('é政ก\"\n' * 90)
    result = pc.prepare_page_requests("page", text, serialize_request=envelope, limit_tokens=600, reserved_tokens=40)
    assert len(result) > 1
    assert ''.join(r.chunk.text for r in result) == text
    for r in result:
        assert r.payload == envelope(r.chunk).encode()
        assert r.estimated_request_tokens == TokenEstimator().tokens(r.payload.decode())
        assert r.estimated_request_tokens + r.reserved_tokens <= 600
        assert r.estimated_request_tokens > r.chunk.estimated_tokens
        assert text[r.chunk.start:r.chunk.end] == r.chunk.text
    assert result == pc.prepare_page_requests("page", text, serialize_request=envelope, limit_tokens=600, reserved_tokens=40)


def test_fixed_overhead_refuses_before_subdivision():
    with pytest.raises(ValueError, match="overhead"):
        pc.prepare_page_requests("p", "abc"*500, serialize_request=envelope, limit_tokens=20, reserved_tokens=0)


@pytest.mark.parametrize("serializer", [None, lambda c: b'', lambda c: {}, lambda c: b'\xff'])
def test_missing_or_invalid_serializer_fails_closed(serializer):
    with pytest.raises((TypeError, UnicodeError)):
        pc.prepare_page_requests("p", "a", serialize_request=serializer, reserved_tokens=0)


@pytest.mark.parametrize("reserve", [None, -1, 32000, 1.5, True])
def test_unknown_or_invalid_reserve_fails_closed(reserve):
    with pytest.raises(ValueError):
        pc.prepare_page_requests("p", "a", serialize_request=envelope, reserved_tokens=reserve)


def test_reserved_budget_and_empty_page():
    result = pc.prepare_page_requests("p", "", serialize_request=envelope, reserved_tokens=100)
    assert len(result) == 1 and result[0].chunk.text == ""
    with pytest.raises(TypeError):
        pc.prepare_page_requests("p", "a", serialize_request=envelope)


def test_saved_reconstructed_real_request():
    directory = Path(__file__).parent / "fixtures" / "t020"
    request = json.loads((directory / "reconstructed-p1.json").read_text(encoding="utf-8"))
    provenance = json.loads((directory / "reconstructed-p1.provenance.json").read_text(encoding="utf-8"))
    text = request["state"]["page_text"]
    assert provenance["kind"] == "offline_reconstruction_not_wire_capture"
    assert len(text.encode()) == provenance["original_chunk_utf8_bytes"]
    def render(c):
        body = copy.deepcopy(request)
        body["state"]["page_text"] = c.text
        body["state"]["page_part"] = c.chunk_id
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    parts = pc.prepare_page_requests(provenance["page_id"], text, serialize_request=render,
                                     reserved_tokens=0, limit_tokens=8000)
    assert ''.join(p.chunk.text for p in parts) == text
    assert all(p.estimated_request_tokens <= 8000 for p in parts)
    assert all(json.loads(p.payload)["questions"] == request["questions"] for p in parts)


def test_no_legacy_combiner_exported():
    assert not hasattr(pc, "combine_page")
    assert not hasattr(pc, "PartAnswer")


@pytest.mark.parametrize("limit,overhead", [(10,-1), (True,0), (10.0,0), (10,False), (0,0)])
def test_low_level_page_budget_rejects_invalid_values(limit, overhead):
    with pytest.raises(ValueError):
        pc.chunk_page("p", "text", limit_tokens=limit, overhead_tokens=overhead)



def pooled_envelope(part):
    return json.dumps({"part_id": part.part_id, "index": part.index,
                       "state": {"evidence": [{"id": e.entry_id, "text": e.text,
                                  "source_date": e.source_date, "page_order": e.page_order}
                                 for e in part.entries]},
                       "questions": {"q": {"instructions": "synthetic pool"*20}},
                       "options": {"fixture": True}}, ensure_ascii=True)


def test_saved_synthetic_pool_exact_payload_order_pins_and_indexes():
    f = json.loads((Path(__file__).parent / "fixtures/t020/synthetic-pool.json").read_text(encoding="utf-8"))
    assert f["provenance"] == "synthetic_functional_fixture_not_real_T026_request"
    members = [PoolEntry(**e) for e in f["entries"]]
    pins = [PoolEntry(**e) for e in f["pinned"]]
    def render(part):
        body = copy.deepcopy(f["request"])
        body["part_id"], body["index"] = part.part_id, part.index
        body["state"]["evidence"] = [{"id": e.entry_id, "text": e.text,
                                     "source_date": e.source_date} for e in part.entries]
        return json.dumps(body, ensure_ascii=True)
    result = pc.prepare_pool_requests("pool", reversed(members), pinned=pins,
        serialize_request=render, limit_tokens=620, reserved_tokens=80)
    assert len(result) >= 10  # crosses a decimal index-width boundary
    assert [r.part.index for r in result] == list(range(1, len(result)+1))
    assert len({r.part.part_id for r in result}) == len(result)
    assert [e for r in result for e in r.part.entries[len(pins):]] == members
    for r in result:
        assert list(r.part.entries[:len(pins)]) == pins
        assert r.payload == render(r.part).encode()
        assert json.loads(r.payload)["index"] == r.part.index
        assert r.estimated_request_tokens == TokenEstimator().tokens(r.payload.decode())
        assert r.estimated_request_tokens + r.reserved_tokens <= 620
    assert result == pc.prepare_pool_requests("pool", reversed(members), pinned=pins,
        serialize_request=render, limit_tokens=620, reserved_tokens=80)


def test_pool_overhead_splits_members_and_reindexes_before_measurement():
    members = [PoolEntry(str(i), "x"*100, "2026", i) for i in range(20)]
    result = pc.prepare_pool_requests("pool", members, serialize_request=pooled_envelope,
                                     limit_tokens=700, reserved_tokens=25)
    assert len(result) > 1
    assert [r.part.index for r in result] == list(range(1, len(result)+1))
    assert [e for r in result for e in r.part.entries] == members
    assert any(r.part.depth for r in result)
    assert all(r.payload == pooled_envelope(r.part).encode() for r in result)
    assert all(r.estimated_request_tokens + r.reserved_tokens <= 700 for r in result)


@pytest.mark.parametrize("members,pins", [([], []), ([], [PoolEntry("p", "x", "2026", 0)]),
    ([PoolEntry("e", "x", "2026", 0)], [])])
def test_pool_indivisible_and_pinned_only_overhead_fails(members, pins):
    with pytest.raises(ValueError, match="cannot fit"):
        pc.prepare_pool_requests("p", members, pinned=pins, serialize_request=pooled_envelope,
                                 limit_tokens=40, reserved_tokens=0)


def test_pool_empty_and_pinned_only_exact_payloads():
    for pins in ([], [PoolEntry("p", "x", "2026", 0)]):
        result = pc.prepare_pool_requests("p", [], pinned=pins, serialize_request=pooled_envelope,
                                         reserved_tokens=0)
        assert len(result) == 1 and result[0].part.index == 1
        assert list(result[0].part.entries) == pins
        assert result[0].payload == pooled_envelope(result[0].part).encode()


@pytest.mark.parametrize("serializer", [None, lambda p: b'', lambda p: {}, lambda p: b'\xff'])
def test_pool_invalid_serializer_fails_closed(serializer):
    with pytest.raises((TypeError, UnicodeError)):
        pc.prepare_pool_requests("p", [], serialize_request=serializer, reserved_tokens=0)


@pytest.mark.parametrize("reserve", [None, -1, 32000, 1.5, True])
def test_pool_unknown_reserve_fails_closed(reserve):
    with pytest.raises(ValueError):
        pc.prepare_pool_requests("p", [], serialize_request=pooled_envelope, reserved_tokens=reserve)


def test_pool_unapproved_calibration_and_unknown_date_refuse():
    with pytest.raises(RuntimeError):
        pc.prepare_pool_requests("p", [], serialize_request=pooled_envelope, reserved_tokens=0,
                                 estimator=TokenEstimator(safety_margin=None))
    with pytest.raises(ValueError, match="source_date"):
        pc.prepare_pool_requests("p", [PoolEntry("e", "x", None, 0)],
                                 serialize_request=pooled_envelope, reserved_tokens=0)
