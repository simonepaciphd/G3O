"""Build tests/fixtures/v27/label-sheet.csv: one row per expected value across synthetic, real and transfer fixtures.

Run after build_synthetic.py and build_real.py: python -I -X utf8 tests/fixtures/v27/build_label_sheet.py
The jev columns are joined from jev-label-scores.csv (derived from the paid run of 2026-11-04, Simone-run; key =
<fixture_id>#<index in expected>). Both readings are kept: jev_argmax_1_5 (most likely level + 1) and
jev_expected_1_5 (probability-weighted level + 1). Which reading gates a label is not ruled. Blank = not scored.
"""

import csv
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("fixture_text", HERE / "fixture_text.py")
ft = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ft)
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
    "codebook_rev",
    "evidence_quote",
    "labeller",
    "label_date",
    "judgement_call",
    "label_version",
    "jev_key",
    "jev_argmax_1_5",
    "jev_expected_1_5",
    "jev_confidence",
    "jev_model",
    "jev_request_id",
]


def main():
    scores = {}
    sp = HERE / "jev-label-scores.csv"
    if sp.exists():
        scores = {r["key"]: r for r in csv.DictReader(sp.open(encoding="utf-8"))}
    rows = []
    for name in ("synthetic.json", "real.json", "transfers.json"):
        for f in json.loads((HERE / name).read_text(encoding="utf-8"))["fixtures"]:
            for k, e in enumerate(f["expected"]):
                v = e["value"]
                js = scores.get(ft.label_key(f["fixture_id"], k, e), {})
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
                        "codebook_rev": e.get("codebook_rev", "r11"),
                        "evidence_quote": e.get("evidence_quote") or "",
                        "labeller": e.get("labeller", "agent (synthetic: by construction)"),
                        "label_date": e.get("label_date", "2026-11-04"),
                        "judgement_call": e.get("judgement_call", ""),
                        "label_version": e.get("label_version", 1),
                        "jev_key": ft.label_key(f["fixture_id"], k, e)
                        if f["kind"] == "real"
                        else "",
                        "jev_argmax_1_5": js.get("jev_argmax_1_5", ""),
                        "jev_expected_1_5": js.get("jev_expected_1_5", ""),
                        "jev_confidence": js.get("confidence", ""),
                        "jev_model": js.get("response_model", ""),
                        "jev_request_id": js.get("request_id", ""),
                    }
                )
    with (HERE / "label-sheet.csv").open("w", encoding="utf-8", newline="") as fo:
        w = csv.DictWriter(fo, COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "label rows")


if __name__ == "__main__":
    main()
