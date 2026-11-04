"""Offline tests for scripts/spikes/t003/analyze_t003.py."""
import csv
import importlib.util
import json
from pathlib import Path

import pytest

_P = Path(__file__).resolve().parents[1] / "scripts" / "spikes" / "t003" / "analyze_t003.py"
_spec = importlib.util.spec_from_file_location("analyze_t003", _P)
an = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(an)


def test_rankdata_average_ties():
    assert an.rankdata([3, 1, 2, 2]) == [4, 1, 2.5, 2.5]


def test_spearman_known_values():
    assert an.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert an.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert an.spearman([1, 2, 2, 3], [1, 3, 2, 4]) == pytest.approx(4.5 / 22.5 ** 0.5)
    assert an.spearman([1, 1, 1], [1, 2, 3]) is None


def test_kappa_known_value():
    t = {"both": 20, "jev_only": 5, "rule_only": 10, "neither": 15, "n": 50}
    assert an.kappa(t) == pytest.approx(0.4)
    assert an.kappa({"both": 3, "jev_only": 0, "rule_only": 0, "neither": 0, "n": 3}) is None


def test_table2x2_cells():
    t = an.table2x2([True, True, False, False], [True, False, True, False])
    assert (t["both"], t["jev_only"], t["rule_only"], t["neither"], t["n"]) == (1, 1, 1, 1, 4)


def _fixture(tmp: Path) -> Path:
    items = [
        {"item_id": "P-a", "kind": "candidate", "script": "latin", "institution": "I1", "candidate_ids": ["C1", "C2"]},
        {"item_id": "P-b", "kind": "candidate", "script": "latin", "institution": "I2", "candidate_ids": ["C3"]},
        {"item_id": "N-onpage-a", "kind": "control", "control_kind": "onpage", "control_of": "P-a",
         "script": "latin", "presence_word": 1.0},
        {"item_id": "N-offpage-a", "kind": "control", "control_kind": "offpage", "control_of": "P-a",
         "script": "latin", "presence_word": 0.6},
    ]
    fid = {"P-a": 5, "P-b": 3, "N-onpage-a": 2, "N-offpage-a": 1}
    (tmp / "SPIKE-T003-jev-items.jsonl").write_text("".join(json.dumps(x) + "\n" for x in items), encoding="utf-8")
    ans = [{"kind": "meta"}] + [{"kind": "jev", "ok": True, "key": k, "fidelity_argmax": v,
                                 "fidelity_expected": v - 0.2} for k, v in fid.items()]
    (tmp / "SPIKE-T003-jev-answers.jsonl").write_text("".join(json.dumps(x) + "\n" for x in ans), encoding="utf-8")
    with open(tmp / "T003-word-presence-thai-fix.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["candidate_id", "script", "presence_word", "rule_80", "partition",
                                          "institution"])
        w.writeheader()
        w.writerow({"candidate_id": "C1", "script": "latin", "presence_word": "1.0", "rule_80": "True",
                    "partition": "tuning", "institution": "I1"})
        w.writerow({"candidate_id": "C2", "script": "latin", "presence_word": "1.0", "rule_80": "True",
                    "partition": "tuning", "institution": "I1"})
        w.writerow({"candidate_id": "C3", "script": "latin", "presence_word": "0.5", "rule_80": "False",
                    "partition": "holdout", "institution": "I2"})
    return tmp


def test_build_rows_maps_unique_pairs_back(tmp_path):
    items, ans, pres = an.load(_fixture(tmp_path), tmp_path / "T003-word-presence-thai-fix.csv")
    rows, missing = an.build_rows(items, ans, pres)
    assert missing == {}
    cands = [r for r in rows if r["row"] == "candidate"]
    assert [r["candidate_id"] for r in cands] == ["C1", "C2", "C3"]
    assert [r["unique_first"] for r in cands] == [True, False, True]
    assert cands[1]["fidelity_argmax"] == 5 and cands[1]["jev_4plus"] is True
    ctrl = {r["row"]: r for r in rows if r["row"] != "candidate"}
    assert ctrl["control_onpage"]["rule_80"] is True and ctrl["control_offpage"]["rule_80"] is False
    assert ctrl["control_onpage"]["partition"] == "tuning"  # inherits from its source pair's institution


def test_analyze_and_main_write_reports(tmp_path):
    lane = _fixture(tmp_path)
    assert an.main(["--lane-dir", str(lane)]) == 0
    res = json.loads((lane / "SPIKE-T003-analysis.json").read_text(encoding="utf-8"))
    a = res["agreement"]["candidates_331"]["latin"]
    assert (a["both"], a["jev_only"], a["rule_only"], a["neither"]) == (2, 0, 0, 1)
    assert res["controls"]["control_onpage"]["latin"]["rule_80_not_jev_4plus"] == 1
    assert res["bar"]["candidates_331_plus_controls"]["latin"]["n_ok"] is False
    assert "holdout" in res["partition"] and "flag" in res["partition"]["holdout"]["thai"]
    assert (lane / "SPIKE-T003-analysis.md").read_text(encoding="utf-8").startswith("# SPIKE-T003")
