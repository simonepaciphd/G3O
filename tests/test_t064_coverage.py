"""Offline tests for scripts/spikes/t064/coverage.py (synthetic data only)."""
import gzip
import importlib.util
import io
import json
import tarfile
from pathlib import Path

_P = Path(__file__).resolve().parents[1] / "scripts" / "spikes" / "t064" / "coverage.py"
_spec = importlib.util.spec_from_file_location("t064_coverage", _P)
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)

TEXT = "Budget FY2024/25 adopted. Served USAF 1972-1976. See p. 2010-2020. Plan 2019 to 2021."


def test_loads_years_without_the_extract_package():
    assert cov.Y.__name__ == "t064_years" and cov.Y.RANGE in cov.LABEL_KINDS


def test_analyse_reports_ranges_lift_and_word_before():
    r = cov.analyse(TEXT)
    assert r["kind"][cov.Y.FISCAL_TWO] == 1 and r["kind"][cov.Y.RANGE] == 3
    assert r["range"]["numbered"] == 1  # "p. 2010-2020"
    assert r["range"]["both_ends_lifted"] == 1 and r["range"]["lifted_ends"] == 2  # 1972, 1976
    assert r["pre"] == {"usaf": 1, "plan": 1}  # numbered ranges are not tallied
    assert r["pre_lifted"] == {"usaf": 1}
    assert "[[1972-1976]]" in r["lifted_examples"][0]
    by_text = {f.text: (kept, pre) for f, kept, _d, _n, pre in r["labels"]}
    assert by_text["2010-2020"] == ([2020], "p.")
    assert by_text["1972-1976"] == ([1972, 1976], "usaf")


def _gz(rec):
    return gzip.compress(json.dumps(rec).encode())


def test_main_end_to_end(tmp_path):
    drive = tmp_path / "drive"
    pulled = drive / cov.readability.REL_RS009
    pulled.mkdir(parents=True)
    with tarfile.open(pulled / cov.readability.RS009_TARS[0], "w") as t:
        for i, text in enumerate([TEXT, "nothing here", TEXT]):
            data = _gz({"url": f"u{i}", "text": text})
            ti = tarfile.TarInfo(f"r20260903T1-aa/institutions/00/INST-{i}/scrape/h{i}.json.gz")
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
    out = tmp_path / "out"
    assert cov.main(["--drive", str(drive), "--out", str(out)]) == 0
    counts = json.loads((out / "SPIKE-T064-counts.json").read_text(encoding="utf-8"))
    assert counts["pages"]["RS-009"]["pages"] == 3 and counts["unique_texts"]["all"]["texts"] == 2
    assert counts["unique_texts"]["all"]["range_with_lifted_end"] == 1
    assert counts["range_word_before_unique_texts"]["with_lifted_end"] == {"usaf": 1}
    md = (out / "SPIKE-T064.md").read_text(encoding="utf-8")
    assert "| `usaf` | 1 | 1 |" in md and "[[1972-1976]]" in md
    rows = (out / "SPIKE-T064-candidates.csv").read_text(encoding="utf-8").splitlines()
    assert rows[0].endswith("numbered,word_before") and len(rows) == 1 + 2 * 4
