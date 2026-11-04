"""Offline test of the T-040 jev label-score readings (no API call)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "jev_label_score", ROOT / "scripts" / "spikes" / "t040" / "jev_label_score.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_real_01_0_argmax_is_5_not_truncated_expected():
    # stored answer for v27-real-01#0 (T040-jev-answers.jsonl, 2026-11-04): level 3.56, argmax level 4
    probs = {"0": 0.06, "1": 0.02, "2": 0.03, "3": 0.07, "4": 0.82}
    f = mod.score_fields(probs, 3.56)
    assert f["jev_argmax_1_5"] == 5
    assert abs(f["jev_expected_1_5"] - 4.56) < 1e-9
    assert f["level_raw"] == 3.56
    assert "jev_score_1_5" not in f


def test_tie_goes_to_lower_level_and_missing_values():
    assert mod.score_fields({"2": 0.5, "3": 0.5}, 2.5)["jev_argmax_1_5"] == 3
    assert mod.score_fields(None, None) == {
        "level_raw": None,
        "jev_argmax_1_5": None,
        "jev_expected_1_5": None,
    }
