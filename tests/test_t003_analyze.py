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


def _row(script, partition, kind, presence, fid):
    return {"script": script, "partition": partition, "row": kind, "presence_word": presence,
            "fidelity_argmax": fid, "jev_4plus": fid >= 4}


def test_gold_is_or_at_080():
    assert an.gold(_row("latin", "tuning", "candidate", 0.8, 1)) is True
    assert an.gold(_row("latin", "tuning", "candidate", 0.5, 4)) is True
    assert an.gold(_row("latin", "tuning", "candidate", 0.79, 3)) is False


def test_cutoff_table_counts():
    rows = [_row("latin", "tuning", "candidate", 1.0, 5),
            _row("latin", "tuning", "candidate", 0.6, 2),      # FM for c <= 0.60
            _row("latin", "tuning", "candidate", 0.85, 2),     # gold true by rule; FR for c > 0.85
            _row("latin", "tuning", "control_offpage", 0.6, 5),  # gold true by jev; FR for c > 0.60
            _row("latin", "tuning", "control_onpage", 1.0, 2),   # scrambled, accepted at every cutoff
            _row("latin", "holdout", "candidate", 0.6, 2)]       # other partition: ignored
    t = {r["cutoff"]: r for r in an.cutoff_table(rows, "latin", "tuning")}
    assert [r for r in t] == list(an.CUTOFFS) and an.CUTOFFS[0] == 0.5 and an.CUTOFFS[-1] == 1.0
    assert t[0.6]["candidates_false_match"] == 1 and t[0.65]["candidates_false_match"] == 0
    assert t[0.85]["candidates_false_reject"] == 0 and t[0.9]["candidates_false_reject"] == 1
    assert t[0.6]["offpage_false_reject"] == 0 and t[0.65]["offpage_false_reject"] == 1
    assert all(r["onpage_scrambled_accepted"] == 1 for r in t.values())
    assert all(r["candidates_false_match"] == 0 for c, r in t.items() if c >= 0.8)  # OR gold: no FM at >= 0.80
    assert t[0.5]["candidates_n"] == 3


def test_rulings_and_ruled_bar(tmp_path):
    assert {"A3", "P1", "R1", "R2", "R3"} <= set(an.RULINGS)
    assert (an.BAR_SET, an.BAR_FIELD) == ("candidates_331_plus_controls", "rho_expected")
    lane = _fixture(tmp_path)
    an.main(["--lane-dir", str(lane)])
    res = json.loads((lane / "SPIKE-T003-analysis.json").read_text(encoding="utf-8"))
    assert res["meta"]["rulings"]["R1"].startswith("v27-results-1104 R1 b")
    assert res["bar_ruled"]["latin"]["verdict"] == "n/a (n < 30)"
    assert set(res["cutoffs"]["tuning"]) == {"latin", "cjk"}


def test_chosen_cutoffs_recorded(tmp_path):
    assert an.CHOSEN_CUTOFFS == {"latin": 0.8, "cjk": 0.8, "thai": 0.8}
    assert ".8 for both is fine" in an.RULINGS["R3_values"]
    lane = _fixture(tmp_path)
    an.main(["--lane-dir", str(lane)])
    res = json.loads((lane / "SPIKE-T003-analysis.json").read_text(encoding="utf-8"))
    ch = res["chosen_cutoffs"]["latin"]
    assert ch["cutoff"] == 0.8 and ch["tuning"]["candidates_false_match"] == 0
    assert ch["holdout"]["candidates_n"] == 1 and "note" in res["chosen_cutoffs"]["thai"]


def test_no_drive_root_exits_2(monkeypatch):
    monkeypatch.delenv(an.DRIVE_ENV, raising=False)
    with pytest.raises(SystemExit) as e:
        an.main([])
    assert e.value.code == 2


def test_out_override_writes_elsewhere(tmp_path):
    lane = _fixture(tmp_path)
    out = tmp_path / "reports"
    assert an.main(["--lane-dir", str(lane), "--out", str(out)]) == 0
    assert (out / "SPIKE-T003-analysis.json").exists() and not (lane / "SPIKE-T003-analysis.json").exists()


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
def test_real_analysis_reproduces_ruled_bar(tmp_path):
    assert an.main(["--out", str(tmp_path)]) == 0
    res = json.loads((tmp_path / "SPIKE-T003-analysis.json").read_text(encoding="utf-8"))
    assert res["bar_ruled"]["latin"]["rho"] == 0.5277 and res["bar_ruled"]["cjk"]["rho"] == 0.5755
