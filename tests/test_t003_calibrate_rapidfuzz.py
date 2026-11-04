"""Offline tests for scripts/spikes/t003/calibrate_rapidfuzz.py. rapidfuzz-dependent tests skip when it is absent."""
import csv
import importlib.util
from pathlib import Path

import pytest

_P = Path(__file__).resolve().parents[1] / "scripts" / "spikes" / "t003" / "calibrate_rapidfuzz.py"
_spec = importlib.util.spec_from_file_location("calibrate_rapidfuzz", _P)
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)


def _row(score, jev4, presence, partition="tuning", script="latin", row="candidate", **kw):
    r = {"row": row, "script": script, "partition": partition, "jev_4plus": jev4, "presence_word": presence,
         "institution": "I1", "item_id": "x", **kw}
    for m in cr.METRICS:
        r[m] = score
        r[m + "_chunk"] = score
    return r


def test_normalizers():
    assert cr.norm_text("Ａ  Big, BIG—deal!") == "a big big deal"
    assert cr.light_text("Ａ  Big,\n BIG") == "a big, big"


def test_gold_is_jev_or_rule():
    assert cr.gold(_row(0, True, 0.1))
    assert cr.gold(_row(0, False, 0.8))
    assert not cr.gold(_row(0, False, 0.79))


def test_errors_counts():
    rows = [_row(90, True, 1.0), _row(40, True, 1.0), _row(90, False, 0.5), _row(40, False, 0.5)]
    e = cr.errors(rows, "partial_ratio_norm", 50)
    assert (e["false_match"], e["false_reject"], e["gold_true"], e["gold_false"]) == (1, 1, 2, 2)


def test_tune_lower_median_of_argmin():
    rows = [_row(80, True, 1.0), _row(30, False, 0.5)]
    t = cr.tune(rows, "partial_ratio_norm")
    assert (t["argmin_lo"], t["argmin_hi"], t["tuning_errors"]) == (31, 80, 0)
    assert t["tuned"] == 55   # 50 values 31..80 -> lower median is the 25th, 55


def test_wilson_known_values():
    lo, hi = cr.wilson(5, 10)
    assert lo == pytest.approx(0.237, abs=1e-3) and hi == pytest.approx(0.763, abs=1e-3)
    assert cr.wilson(0, 10)[0] == 0.0
    assert cr.wilson(0, 0) is None


def test_calibrate_structure_and_thai_flag():
    rows = []
    for s in ("latin", "cjk", "thai"):
        for p in ("tuning", "holdout"):
            rows += [_row(95, True, 1.0, p, s), _row(20, False, 0.6, p, s, row="control_offpage"),
                     _row(97, False, 1.0, p, s, row="control_onpage")]
    res = cr.calibrate(rows)
    for m in cr.METRICS:
        r = res[m]
        assert r["holdout"]["latin"]["per_script"]["false_match"] == 0
        assert "per_script" not in r["holdout"]["thai"] and r["holdout"]["thai"]["flag"] == cr.THAI_FLAG
        assert r["scrambled_accepted"]["latin"]["accepted_jev_below_4"] == 1
        assert r["agrees_with_rule_80"] == 1.0


def test_length_table_and_caps():
    qs = [("latin", "a" * 120), ("latin", "word " * 5), ("cjk", "中文字")]
    t = cr.length_table(qs, caps=(100, 150))
    assert t["latin"]["n"] == 2 and t["latin"]["chars"]["max"] == 120
    assert t["latin"]["truncated"][100] == {"count": 1, "share": 0.5}
    assert t["latin"]["truncated"][150]["count"] == 0
    assert t["all"]["n"] == 3 and t["cjk"]["words"]["max"] == 1
    assert "thai" not in t


def test_nearest_rank():
    xs = list(range(1, 11))
    assert cr.nearest_rank(xs, 50) == 5 and cr.nearest_rank(xs, 90) == 9 and cr.nearest_rank(xs, 99) == 10


def test_write_pairs_marks_holdout(tmp_path):
    rows = [_row(90, True, 1.0, "holdout", candidate_id="C1"), _row(10, False, 0.5, row="control_offpage")]
    for r in rows:
        r.update(quote="q one", page_id="p", chunk_id="p#c1of1", fidelity_argmax=4, fidelity_expected=4.2)
    out = tmp_path / "pairs.csv"
    cr.write_pairs(rows, out)
    got = list(csv.DictReader(open(out, encoding="utf-8")))
    assert [g["holdout"] for g in got] == ["True", "False"]
    assert [g["gold_label"] for g in got] == ["True", "False"]
    assert got[0]["quote_words"] == "2" and list(got[0]) == cr.PAIR_FIELDS


def test_score_all_exact_and_swapped():
    pytest.importorskip("rapidfuzz")
    page = "The council adopted an artificial intelligence policy in March. 市议会通过了人工智能政策。"
    texts = {"a": {"quote": "adopted an Artificial Intelligence policy", "page_id": "p", "chunk_id": "c",
                   "page": page, "chunk": page},
             "b": {"quote": "rejected a quantum bicycle policy", "page_id": "p", "chunk_id": "c",
                   "page": page, "chunk": page},
             "c": {"quote": "通过了人工智能政策", "page_id": "p", "chunk_id": "c", "page": page, "chunk": page}}
    rows = [{"item_id": k} for k in texts]
    cr.score_all(rows, texts)
    a, b, c = rows
    for m in cr.METRICS:
        assert a[m] == 100 and b[m] < a[m]
        assert a[m + "_chunk"] == a[m]
    # CJK: a quote cut inside a page's letter run aligns fully by characters, but is a different token
    assert c["partial_ratio_norm"] == 100 and c["partial_ratio_light"] == 100
    assert c["token_set_ratio_norm"] < 50


def test_check_version(monkeypatch):
    rf = pytest.importorskip("rapidfuzz")
    monkeypatch.setattr(cr, "PINNED_RAPIDFUZZ", rf.__version__)
    assert cr.check_version() == rf.__version__
    monkeypatch.setattr(cr, "PINNED_RAPIDFUZZ", "0.0.0")
    with pytest.raises(SystemExit):
        cr.check_version()
    assert cr.check_version(allow_other=True) == rf.__version__
