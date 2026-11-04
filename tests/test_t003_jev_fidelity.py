"""Offline tests for scripts/spikes/t003/jev_fidelity.py (no network, no key)."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_P = Path(__file__).resolve().parents[1] / "scripts" / "spikes" / "t003" / "jev_fidelity.py"
_spec = importlib.util.spec_from_file_location("jev_fidelity", _P)
jf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jf)

PAGE_A = ("The council adopted an artificial intelligence policy in March 2025. Staff use ChatGPT for drafting "
          "minutes and summaries. The policy requires human review of every output before publication.")
PAGE_B = "Library opening hours change during winter holidays because maintenance crews repaint ceilings."
PID_A = "RS-008:run:INST-0000001:aaaa"
PID_B = "RS-008:run:INST-0000002:bbbb"


def _write_recovery(tmp: Path, cands: list[tuple[str, str, str]]) -> Path:
    pages = [{"page_id": PID_A, "source_record": {"text": PAGE_A, "title": "A", "url": "u"}},
             {"page_id": PID_B, "source_record": {"text": PAGE_B, "title": "B", "url": "v"}}]
    (tmp / "SOURCE-PAGES.jsonl").write_text("\n".join(json.dumps(p) for p in pages) + "\n", encoding="utf-8")
    rows = [{"candidate_id": cid, "script": "latin",
             "saved_quote_record": {"page_id": pid, "chunk_id": f"{pid}#c1of1", "quote": q}}
            for cid, pid, q in cands]
    (tmp / "CANDIDATES.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return tmp


@pytest.fixture
def rec(tmp_path):
    return _write_recovery(tmp_path, [
        ("C1", PID_A, "Staff use ChatGPT for drafting minutes and summaries"),
        ("C2", PID_A, "Staff use ChatGPT for drafting minutes and summaries"),  # sync/batch duplicate
        ("C3", PID_A, "requires human review of every output"),
        ("C4", PID_B, "opening hours change during winter holidays"),
        ("C5", PID_B, "repaint"),  # too short for a control
    ])


def test_byte_chunks_roundtrip_and_cap():
    text = "é" * 50 + "abc" * 40
    parts = jf.byte_chunks(text, 37)
    assert "".join(parts) == text and all(jf.utf8_len(p) <= 37 for p in parts)


def test_parse_chunk_id():
    assert jf.parse_chunk_id("RS-008:r:INST-1:h#c2of3") == (1, 3)


def test_duplicates_share_one_item(rec):
    items, chunks, _, notes = jf.build_items(rec)
    cand = [x for x in items if x["kind"] == "candidate"]
    assert len(cand) == 4 and notes["candidates"] == 5
    dup = next(x for x in cand if "C1" in x["candidate_ids"])
    assert dup["candidate_ids"] == ["C1", "C2"]
    assert sum(len(x["candidate_ids"]) for x in cand) == 5
    assert chunks[f"{PID_A}#c1of1"] == PAGE_A


def test_controls_presence_by_kind(rec):
    items, _, _, notes = jf.build_items(rec)
    ctrl = [x for x in items if x["kind"] == "control"]
    on = [x for x in ctrl if x["control_kind"] == "onpage"]
    off = [x for x in ctrl if x["control_kind"] == "offpage"]
    assert len(on) == 3 and len(off) == 3          # C5 is too short
    assert notes["controls_skipped"] == {"latin:short": 2}
    assert all(x["presence_word"] == 1.0 for x in on)
    for x in off:
        n = len(jf.wp.word_tokens(x["quote"]))
        assert x["presence_word"] == pytest.approx(round((n - len(x["swaps"])) / n, 4))
        assert x["presence_word"] < 0.8
    for x in on + off:
        assert x["quote"] != next(y for y in items if y["item_id"] == x["control_of"])["quote"]


def test_build_is_deterministic(rec):
    a, _, _, _ = jf.build_items(rec)
    b, _, _, _ = jf.build_items(rec)
    assert jf.items_digest(a) == jf.items_digest(b)


def test_margin_estimate_is_190_percent():
    st = jf.make_state("1 of 1", "x" * 10_000, "quote")
    lo, hi = jf.est_tokens(st, "latin", False), jf.est_tokens(st, "latin", True)
    assert hi / lo == pytest.approx(1.9, rel=1e-3)


def test_question_has_five_ordered_levels():
    assert len(jf.QUESTION_LEVELS) == 5
    assert [lv[0] for lv in jf.QUESTION_LEVELS] == ["1", "2", "3", "4", "5"]


def _fake_ask(level_probs):
    calls = []

    def ask(state, qs):
        calls.append(state)
        probs = dict(level_probs)
        exp = sum(k * v for k, v in probs.items())
        a = SimpleNamespace(score=exp, confidence=0.9, probabilities=probs)
        return SimpleNamespace(answers={jf.QUESTION_ID: a}, request_id=f"r{len(calls)}", response_model="jev-x",
                               input_tokens=1000, output_tokens=5)
    return ask, calls


def test_score_items_writes_fidelity_and_resumes(rec, tmp_path):
    items, chunks, _, _ = jf.build_items(rec)
    ask, calls = _fake_ask({0: 0.1, 3: 0.7, 4: 0.2})
    log = jf.Log(tmp_path / "ans.jsonl")
    r = jf.score_items(items, chunks, ask, log, 1.0, question=None)
    log.close()
    assert r["scored_now"] == len(items) == len(calls)
    row = json.loads((tmp_path / "ans.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["level_argmax"] == 3 and row["fidelity_argmax"] == 4
    assert row["fidelity_expected"] == pytest.approx(row["score_level_expected"] + 1)
    assert set(calls[0]) == {"quote", "page_part", "source_text"}
    log2 = jf.Log(tmp_path / "ans.jsonl")
    r2 = jf.score_items(items, chunks, ask, log2, 1.0, question=None)
    log2.close()
    assert r2["scored_now"] == 0 and len(calls) == len(items)
    assert log2.spent == pytest.approx(len(items) * 1000 * jf.JEV_IN_PER_M / 1e6)


def test_cap_stops_before_the_call(rec, tmp_path):
    items, chunks, _, _ = jf.build_items(rec)
    ask, calls = _fake_ask({4: 1.0})
    log = jf.Log(tmp_path / "ans.jsonl")
    with pytest.raises(jf.CapReached):
        jf.score_items(items, chunks, ask, log, cap_usd=jf.jev_cost(jf.JEV_REQUEST_TOKENS) * 0.5, question=None)
    log.close()
    assert calls == []


def test_failure_is_recorded_not_halved(rec, tmp_path):
    items, chunks, _, _ = jf.build_items(rec)

    def ask(state, qs):
        raise RuntimeError("max_tokens_exceeded")
    log = jf.Log(tmp_path / "ans.jsonl")
    r = jf.score_items(items[:1], chunks, ask, log, 1.0, question=None)
    log.close()
    row = json.loads((tmp_path / "ans.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert r["failed_now"] == 1 and row["ok"] is False and row["max_tokens_exceeded"] is True


def test_account_error_is_reraised(rec, tmp_path):
    items, chunks, _, _ = jf.build_items(rec)

    class JevAccountError(RuntimeError):
        pass

    def ask(state, qs):
        raise JevAccountError("402")
    log = jf.Log(tmp_path / "ans.jsonl")
    with pytest.raises(JevAccountError):
        jf.score_items(items, chunks, ask, log, 1.0, question=None)
    log.close()


def test_paid_run_refuses_draft_wording_and_high_cap(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(jf, "WORDING_STATUS", "DRAFT")
    with pytest.raises(SystemExit, match="DRAFT"):
        jf.main(["run", "--out-dir", str(tmp_path), "--recovery-dir", str(tmp_path)])
    monkeypatch.setattr(jf, "WORDING_STATUS", "APPROVED test")
    with pytest.raises(SystemExit, match="refused"):
        jf.main(["run", "--out-dir", str(tmp_path), "--recovery-dir", str(tmp_path), "--cap", "1.5"])
    with pytest.raises(SystemExit, match="TYPESAFE_API_KEY"):
        jf.main(["run", "--out-dir", str(tmp_path), "--recovery-dir", str(tmp_path)])


def test_dry_run_writes_files_offline(rec, tmp_path):
    out = tmp_path / "out"
    rc = jf.main(["dry-run", "--recovery-dir", str(rec), "--out-dir", str(out),
                  "--t002-dryrun", str(tmp_path / "missing.json")])
    d = json.loads((out / "SPIKE-T003-jev-dryrun.json").read_text(encoding="utf-8"))
    assert rc == 0 and d["wording_status"].startswith("APPROVED") and d["estimate"]["all"]["items"] == 10
    assert len((out / "SPIKE-T003-jev-items.jsonl").read_text(encoding="utf-8").splitlines()) == 10


def test_rulings_recorded():
    assert jf.WORDING_STATUS.startswith("APPROVED 2026-11-04") and "v27-gates-1104" in jf.WORDING_STATUS
    assert jf.JEV_4PLUS_FIELD == "fidelity_argmax"
    assert jf.CONTROL_KINDS == ("onpage", "offpage") and jf.CONTROL_FRACTION == 0.4


def test_thai_controls_swap_whole_runs(tmp_path):
    th = "การนำปัญญาประดิษฐ์ มาใช้ ในงาน เกษตร แม่นยำ"
    pages = [{"page_id": PID_A, "source_record": {"text": th + " ของ จังหวัด", "title": "", "url": ""}},
             {"page_id": PID_B, "source_record": {"text": "โรงเรียน ห้องสมุด ถนน", "title": "", "url": ""}}]
    (tmp_path / "SOURCE-PAGES.jsonl").write_text("".join(json.dumps(p) + "\n" for p in pages), encoding="utf-8")
    rows = [{"candidate_id": "T1", "script": "thai",
             "saved_quote_record": {"page_id": PID_A, "chunk_id": f"{PID_A}#c1of1", "quote": th}},
            {"candidate_id": "T2", "script": "thai",
             "saved_quote_record": {"page_id": PID_B, "chunk_id": f"{PID_B}#c1of1", "quote": "โรงเรียน ถนน"}}]
    (tmp_path / "CANDIDATES.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    items, _, _, _ = jf.build_items(tmp_path)
    ctrl = [x for x in items if x["kind"] == "control"]
    assert {x["control_kind"] for x in ctrl} == {"onpage", "offpage"}  # T2 has 2 runs: too short
    page_runs = set(jf.wp.word_tokens(pages[0]["source_record"]["text"] + " " + pages[1]["source_record"]["text"]))
    for x in ctrl:
        for s in x["swaps"]:  # each swap is one whole space-delimited Thai run, never a fragment
            assert jf.wp.word_tokens(s["new"]) == [jf.wp.normalize(s["new"])]
            assert jf.wp.normalize(s["new"]) in page_runs


def test_no_drive_root_exits_2(monkeypatch, tmp_path):
    monkeypatch.delenv(jf.DRIVE_ENV, raising=False)
    with pytest.raises(SystemExit) as e:
        jf.main(["dry-run"])
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e:
        jf.drive_root(tmp_path)  # exists but has no agent-workspace/
    assert e.value.code == 2


def test_drive_root_from_setting(monkeypatch, tmp_path):
    (tmp_path / "agent-workspace").mkdir()
    monkeypatch.setenv(jf.DRIVE_ENV, str(tmp_path))
    assert jf.drive_root() == tmp_path


# Built from parts so this file itself carries none of the strings it forbids.
# The user-name check is a whole-word match: the approved jev wording has an ordinary word with that prefix.
_BAD = ["C:" + "/Users", "C:" + "\\" + "Users", "My " + "Drive", "H:" + "/", "H:" + "\\"]


def test_no_machine_paths_in_source():
    import re
    src = _P.read_text(encoding="utf-8")
    for bad in _BAD:
        assert bad not in src
    assert not re.search("spa" + r"ci(?![a-z])", src)


@pytest.mark.skipif(not __import__("os").environ.get("G3O_DRIVE_ROOT"), reason="needs G3O_DRIVE_ROOT (Drive data)")
def test_real_dry_run_reproduces_recorded_items(tmp_path):
    import os
    root = Path(os.environ["G3O_DRIVE_ROOT"])
    rec = json.loads((root / jf.REL_OUT_DIR / "SPIKE-T003-jev-dryrun.json").read_text(encoding="utf-8"))
    assert jf.main(["dry-run", "--out", str(tmp_path)]) == 0
    new = json.loads((tmp_path / "SPIKE-T003-jev-dryrun.json").read_text(encoding="utf-8"))
    assert new["items_sha256"] == rec["items_sha256"] and new["question"]["sha256"] == rec["question"]["sha256"]
