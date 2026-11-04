"""Build tests/fixtures/v27/label-sheet.csv: one row per expected value across synthetic, real and transfer fixtures.

Run after build_synthetic.py and build_real.py: python -I -X utf8 tests/fixtures/v27/build_label_sheet.py
Columns jev_score / jev_model / jev_request_id stay blank until the paid jev scoring of real-page labels (T-040, Simone-run).
"""

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLS = [
    "fixture_id",
    "kind",
    "mode",
    "a_ids",
    "institution_id",
    "item",
    "scope",
    "expected_value",
    "rule",
    "evidence_quote",
    "labeller",
    "label_date",
    "judgement_call",
    "jev_score",
    "jev_model",
    "jev_request_id",
]


def main():
    rows = []
    for name in ("synthetic.json", "real.json", "transfers.json"):
        for f in json.loads((HERE / name).read_text(encoding="utf-8"))["fixtures"]:
            for e in f["expected"]:
                v = e["value"]
                rows.append(
                    {
                        "fixture_id": f["fixture_id"],
                        "kind": f["kind"],
                        "mode": f.get("mode", "pipeline"),
                        "a_ids": ";".join(f["a_ids"]),
                        "institution_id": f["institution"]["institution_id"],
                        "item": e["item"],
                        "scope": e["scope"],
                        "expected_value": v
                        if isinstance(v, str)
                        else json.dumps(v, ensure_ascii=False),
                        "rule": e["rule"],
                        "evidence_quote": e.get("evidence_quote") or "",
                        "labeller": e.get("labeller", "agent (synthetic: by construction)"),
                        "label_date": e.get("label_date", "2026-11-04"),
                        "judgement_call": e.get("judgement_call", ""),
                        "jev_score": "",
                        "jev_model": "",
                        "jev_request_id": "",
                    }
                )
    with (HERE / "label-sheet.csv").open("w", encoding="utf-8", newline="") as fo:
        w = csv.DictWriter(fo, COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "label rows")


if __name__ == "__main__":
    main()
